#!/bin/bash
# =============================================================================
# Full 1-hour soak test — ProjectsManagerWebV2
# =============================================================================
# PRECONDITION: Backend MUST be restarted via ./launch.sh AFTER stability fixes
#               are in effect (shutdown-on-idle guard, watchdog cooldown fixes).
#               Running this against the OLD code defeats the purpose.
#
# Duration:     3600 seconds
# Acceptance:   CRASH_DETECTED delta == 0  AND  error rate == 0%
#               p95 latency <= 200ms
#
# Usage:  ./tests/soak/run_soak.sh [duration_seconds]
#         (default 3600; pass e.g. 300 for a quick smoke run)
#
# Deps:   curl, jq, bash 3+
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8401}"
DURATION="${1:-3600}"
POLL_INTERVAL=10
LOG_DIR="$(dirname "$0")/results"
LOG_FILE="$LOG_DIR/soak_$(date +%Y%m%d_%H%M%S).log"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
WATCHDOG_LOG="$ROOT_DIR/logs/backend-watchdog.log"

mkdir -p "$LOG_DIR"

# --------------------------------------------------------------------------
# Cleanup on exit
# --------------------------------------------------------------------------
_BGPIDS=()
cleanup() {
  for pid in "${_BGPIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

# --------------------------------------------------------------------------
# Pre-flight checks
# --------------------------------------------------------------------------
log "=== 1-HOUR SOAK TEST START ==="
log "Duration: ${DURATION}s  |  Poll interval: ${POLL_INTERVAL}s"
log "Target: $BASE_URL"

if ! curl -sf -m 5 "$BASE_URL/health" >/dev/null; then
  log "FATAL: Backend unreachable at $BASE_URL — aborting soak."
  log "Ensure ./launch.sh was run AFTER applying stability fixes."
  exit 1
fi
log "Backend reachable. Starting soak..."

CRASH_BEFORE=$(grep -c "CRASH DETECTED" "$WATCHDOG_LOG" 2>/dev/null || echo 0)
log "CRASH_DETECTED before soak: $CRASH_BEFORE"

# --------------------------------------------------------------------------
# Helper: pick a random issue ID from the project list
# --------------------------------------------------------------------------
pick_issue_id() {
  curl -sf -m 10 "$BASE_URL/api/projects" 2>/dev/null \
    | jq -r '.[0].id // empty' 2>/dev/null || echo ""
}

# --------------------------------------------------------------------------
# Phase 1: Continuous poll loop (background)
# --------------------------------------------------------------------------
declare -a LATENCIES=()
POLL_ERRORS=0
POLL_TOTAL=0
POLL_LOG="$LOG_DIR/.poll_tmp_$$"

(
  start=$(date +%s)
  end=$((start + DURATION))
  while [ "$(date +%s)" -lt "$end" ]; do
    t1=$(date +%s%N)
    h_code=$(curl -sf -m 5 -o /dev/null -w "%{http_code}" "$BASE_URL/health" 2>/dev/null || echo "000")
    t2=$(date +%s%N)
    ms_h=$(( (t2 - t1) / 1000000 ))

    t3=$(date +%s%N)
    p_code=$(curl -sf -m 5 -o /dev/null -w "%{http_code}" "$BASE_URL/api/projects" 2>/dev/null || echo "000")
    t4=$(date +%s%N)
    ms_p=$(( (t4 - t3) / 1000000 ))

    elapsed=$(( $(date +%s) - start ))
    err=0
    [[ "$h_code" != "200" ]] && err=1
    [[ "$p_code" != "200" ]] && err=1
    echo "$ms_h $ms_p $err $elapsed $h_code $p_code" >> "$POLL_LOG"
    sleep "$POLL_INTERVAL"
  done
) &
_BGPIDS+=($!)
POLL_PID=$!

# --------------------------------------------------------------------------
# Phase 2: 50x PATCH mutations on issues (spread evenly)
# --------------------------------------------------------------------------
MUTATION_ERRORS=0
MUTATION_COUNT=50
STATES=("TODO" "IN_PROGRESS" "COMPLETED_WAITING_QA" "DONE" "BACKLOG")

log "--- Phase 2: $MUTATION_COUNT issue state mutations ---"
# Grab a real issue key to mutate; fall back to a synthetic one for the test
ISSUE_LIST=$(curl -sf -m 10 "$BASE_URL/api/projects" 2>/dev/null | jq -r '.[].key // empty' 2>/dev/null | head -5 || true)
if [ -z "$ISSUE_LIST" ]; then
  log "WARNING: No issues found; skipping mutation phase."
else
  MUTATION_SLEEP=$(( (DURATION / MUTATION_COUNT) ))
  (
    i=0
    while [ $i -lt $MUTATION_COUNT ]; do
      key=$(echo "$ISSUE_LIST" | shuf -n1 2>/dev/null || echo "$ISSUE_LIST" | head -1)
      state="${STATES[$((i % ${#STATES[@]}))]}"
      code=$(curl -sf -m 10 -o /dev/null -w "%{http_code}" \
        -X PATCH "$BASE_URL/api/issues/$key" \
        -H "Content-Type: application/json" \
        -d "{\"status\": \"$state\"}" 2>/dev/null || echo "000")
      if [[ "$code" != "200" && "$code" != "201" && "$code" != "204" ]]; then
        echo "MUTATION_ERROR key=$key state=$state code=$code" >> "$POLL_LOG"
      fi
      i=$((i + 1))
      sleep "$MUTATION_SLEEP"
    done
  ) &
  _BGPIDS+=($!)
fi

# --------------------------------------------------------------------------
# Phase 3: 5x AI execute calls (skipped if ANTHROPIC_API_KEY not set)
# --------------------------------------------------------------------------
AI_ERRORS=0
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  log "--- Phase 3: 5 AI execute calls ---"
  AI_SLEEP=$(( DURATION / 5 ))
  (
    for i in 1 2 3 4 5; do
      code=$(curl -sf -m 30 -o /dev/null -w "%{http_code}" \
        -X POST "$BASE_URL/api/codeboard/execute" \
        -H "Content-Type: application/json" \
        -d '{"prompt":"List 3 short project status phrases.","max_tokens":50}' 2>/dev/null || echo "000")
      [[ "$code" != "200" ]] && echo "AI_ERROR code=$code" >> "$POLL_LOG"
      sleep "$AI_SLEEP"
    done
  ) &
  _BGPIDS+=($!)
else
  log "--- Phase 3: SKIPPED (ANTHROPIC_API_KEY not set) ---"
fi

# --------------------------------------------------------------------------
# Wait for poll loop to finish
# --------------------------------------------------------------------------
log "Soak running for ${DURATION}s ... ($(date))"
wait "$POLL_PID" 2>/dev/null || true

# --------------------------------------------------------------------------
# Compute results
# --------------------------------------------------------------------------
log "=== RESULTS ==="

CRASH_AFTER=$(grep -c "CRASH DETECTED" "$WATCHDOG_LOG" 2>/dev/null || echo 0)
CRASH_DELTA=$(( CRASH_AFTER - CRASH_BEFORE ))

if [ -f "$POLL_LOG" ]; then
  POLL_TOTAL=$(wc -l < "$POLL_LOG" | tr -d ' ')
  POLL_ERRORS=$(grep -c "^MUTATION_ERROR\|^AI_ERROR\| 0[0-9][0-9] " "$POLL_LOG" 2>/dev/null || echo 0)

  # Collect latencies for percentile calc
  mapfile -t LAT_ARR < <(awk '{print $1; print $2}' "$POLL_LOG" 2>/dev/null | grep -E '^[0-9]+$' | sort -n)
  N=${#LAT_ARR[@]}
  if [ "$N" -gt 0 ]; then
    P50=${LAT_ARR[$((N * 50 / 100))]}
    P95=${LAT_ARR[$((N * 95 / 100))]}
    P99=${LAT_ARR[$((N * 99 / 100))]}
  else
    P50="-"; P95="-"; P99="-"
  fi
  rm -f "$POLL_LOG"
fi

ERR_LINES=$(grep -c "ERROR\|code=0" "$LOG_FILE" 2>/dev/null || echo 0)

log "CRASH_DETECTED delta:  $CRASH_DELTA  (before=$CRASH_BEFORE after=$CRASH_AFTER)"
log "Poll errors:           $ERR_LINES"
log "Latency (n=$N):        p50=${P50}ms  p95=${P95}ms  p99=${P99}ms"

# --------------------------------------------------------------------------
# Pass/Fail
# --------------------------------------------------------------------------
PASS=true
[ "$CRASH_DELTA" -gt 0 ] && PASS=false && log "FAIL: $CRASH_DELTA crash(es) detected during soak"
[ "$ERR_LINES"   -gt 0 ] && PASS=false && log "FAIL: $ERR_LINES HTTP errors during soak"
# p95 guard (numeric check only if we have data)
if [[ "$P95" =~ ^[0-9]+$ ]] && [ "$P95" -gt 200 ]; then
  PASS=false
  log "FAIL: p95 latency ${P95}ms exceeds 200ms threshold"
fi

if $PASS; then
  log "RESULT: PASS — backend stable for ${DURATION}s post-restart"
else
  log "RESULT: FAIL — see findings above"
fi

log "Full log: $LOG_FILE"
log "=== SOAK TEST END ==="
