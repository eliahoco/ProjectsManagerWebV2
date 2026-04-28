#!/bin/bash
# T2 — Real backend crash: watchdog must restart within one check cycle (30s budget).
# A fake backend binds port 18402, then is SIGKILL'd.
# We verify a NEW process binds the same port within CHECK_INTERVAL + tolerance.
set -e

# --- Prerequisites ---
for tool in lsof python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "SKIP: required tool '$tool' not found"
        exit 0
    fi
done

WORK=$(mktemp -d)
PROJECT_ROOT=/Volumes/Seagate/Claude/ProjectsManagerWebV2Production
cp "$PROJECT_ROOT/backend-watchdog.sh" "$WORK/"
mkdir -p "$WORK/logs" "$WORK/backend"

WATCHDOG_PID=""

cleanup() {
    [ -n "$WATCHDOG_PID" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
    lsof -ti :18402 2>/dev/null | xargs kill -9 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

RESTART_MARKER="$WORK/logs/restart_count"
echo "0" > "$RESTART_MARKER"

# Write the override function to a separate file
cat > "$WORK/start_backend_override.sh" <<OVERRIDE_EOF
start_backend() {
    log "start_backend OVERRIDE -- launching stub HTTP server on 18402"
    python3 -m http.server 18402 --bind 127.0.0.1 >/dev/null 2>&1 &
    local pid=\$!
    echo \$pid > "$WORK/logs/backend.pid"
    log "stub started PID \$pid"
    local cnt
    cnt=\$(cat "$RESTART_MARKER" 2>/dev/null || echo 0)
    echo \$((cnt + 1)) > "$RESTART_MARKER"
    local w=0
    while [ \$w -lt 10 ]; do
        sleep 1; w=\$((w+1))
        lsof -ti :18402 >/dev/null 2>&1 && return 0
    done
    return 1
}
OVERRIDE_EOF

# Patch watchdog: adjust port and intervals, then source the override at top of run_watchdog
sed \
    -e 's|BACKEND_PORT=8401|BACKEND_PORT=18402|g' \
    -e "s|PROJECT_ROOT=.*|PROJECT_ROOT=\"$WORK\"|g" \
    -e 's|CHECK_INTERVAL=15|CHECK_INTERVAL=8|g' \
    -e 's|STARTUP_WAIT=90|STARTUP_WAIT=30|g' \
    "$WORK/backend-watchdog.sh" > "$WORK/watchdog_patched.sh"

# Inject: source override file at top of run_watchdog()
sed "s|^run_watchdog() {|run_watchdog() {\n    source \"$WORK/start_backend_override.sh\"|" \
    "$WORK/watchdog_patched.sh" > "$WORK/watchdog_final.sh"
chmod +x "$WORK/watchdog_final.sh"

# --- Launch watchdog ---
cd "$WORK"
bash "$WORK/watchdog_final.sh" debug > "$WORK/logs/backend-watchdog.log" 2>&1 &
WATCHDOG_PID=$!

# Wait for watchdog to start the stub backend (up to 20s)
echo "Waiting for initial stub backend to bind port 18402..."
for i in $(seq 1 20); do
    lsof -ti :18402 >/dev/null 2>&1 && break
    sleep 1
done

if ! lsof -ti :18402 >/dev/null 2>&1; then
    echo "FAIL: stub backend never bound port 18402 -- test setup broken"
    echo "--- watchdog log ---"
    cat "$WORK/logs/backend-watchdog.log" 2>/dev/null || true
    exit 1
fi

ORIGINAL_PID=$(cat "$WORK/logs/backend.pid")
echo "Stub backend running as PID $ORIGINAL_PID -- killing it now..."
kill -9 "$ORIGINAL_PID" 2>/dev/null || true

# --- Wait for watchdog to detect crash and restart ---
# Budget: CHECK_INTERVAL(8) + start overhead(10) + tolerance(12) = 30s
DEADLINE=30
ELAPSED=0
RESTARTED=0

while [ $ELAPSED -lt $DEADLINE ]; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    CURRENT_PID=$(cat "$WORK/logs/backend.pid" 2>/dev/null || echo "")
    if [ "$CURRENT_PID" != "$ORIGINAL_PID" ] && [ -n "$CURRENT_PID" ]; then
        if kill -0 "$CURRENT_PID" 2>/dev/null; then
            RESTARTED=1
            break
        fi
    fi
done

if [ "$RESTARTED" -eq 1 ]; then
    RESTART_COUNT=$(cat "$RESTART_MARKER" 2>/dev/null || echo "?")
    echo "PASS: watchdog restarted crashed backend within ${ELAPSED}s (restart count: $RESTART_COUNT)"
    exit 0
else
    echo "FAIL: watchdog did NOT restart backend within ${DEADLINE}s after SIGKILL"
    echo "--- watchdog log tail ---"
    tail -20 "$WORK/logs/backend-watchdog.log" 2>/dev/null || true
    exit 1
fi
