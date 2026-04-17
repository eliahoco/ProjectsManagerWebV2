#!/bin/bash
# =============================================================================
# Backend Watchdog — Auto-restarts FastAPI/uvicorn server on crash
# =============================================================================
#
# Mirrors the frontend watchdog pattern.
# Monitors port 8401 via HTTP health check and restarts the backend on crash.
#
# Usage:
#   ./backend-watchdog.sh start    — Start the watchdog (backgrounds itself)
#   ./backend-watchdog.sh stop     — Stop the watchdog
#   ./backend-watchdog.sh status   — Check watchdog and backend status
#   ./backend-watchdog.sh debug    — Run in foreground for interactive troubleshooting
#
# The watchdog writes its PID to logs/backend-watchdog.pid
# and logs to logs/backend-watchdog.log
# =============================================================================

set -euo pipefail

# Absolute path to this script (survives cd and terminal close)
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
LOGS_DIR="$PROJECT_ROOT/logs"
WATCHDOG_PID_FILE="$LOGS_DIR/backend-watchdog.pid"
WATCHDOG_LOG="$LOGS_DIR/backend-watchdog.log"
BACKEND_PORT=8401
CHECK_INTERVAL=15        # seconds between health checks
STARTUP_WAIT=30          # seconds to wait after starting backend
MAX_RESTARTS_PER_HOUR=10 # circuit breaker

mkdir -p "$LOGS_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$WATCHDOG_LOG"
}

is_backend_alive() {
    lsof -ti :$BACKEND_PORT >/dev/null 2>&1
}

is_backend_responding() {
    curl -sf --max-time 10 "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1
}

kill_backend() {
    lsof -ti :$BACKEND_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
    sleep 2
}

start_backend() {
    log "Starting backend uvicorn server..."

    cd "$BACKEND_DIR"
    nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port $BACKEND_PORT > "$LOGS_DIR/backend.log" 2>&1 &
    local pid=$!
    echo $pid > "$LOGS_DIR/backend.pid"
    log "Backend started with PID $pid"

    # Wait for it to be ready
    local waited=0
    while [ $waited -lt $STARTUP_WAIT ]; do
        sleep 5
        waited=$((waited + 5))
        if is_backend_responding; then
            log "Backend is responding after ${waited}s"
            return 0
        fi
    done

    # Check if process is at least alive (may be slow to initialize)
    if is_backend_alive; then
        log "Backend process alive but not yet responding after ${waited}s — will keep checking"
        return 0
    fi

    log "ERROR: Backend failed to start after ${waited}s"
    return 1
}

run_watchdog() {
    log "=========================================="
    log "Backend watchdog started (PID $$)"
    log "Monitoring backend on port $BACKEND_PORT"
    log "Check interval: ${CHECK_INTERVAL}s"
    log "=========================================="

    echo $$ > "$WATCHDOG_PID_FILE"

    local restart_count=0
    local hour_start=$(date +%s)
    local consecutive_failures=0

    # Make sure backend is running initially
    if ! is_backend_alive; then
        log "Backend not running — starting it"
        start_backend || true
    fi

    while true; do
        sleep $CHECK_INTERVAL

        # Reset restart counter every hour
        local now=$(date +%s)
        if [ $((now - hour_start)) -ge 3600 ]; then
            restart_count=0
            hour_start=$now
        fi

        # Circuit breaker — back-off sleep instead of exit
        if [ $restart_count -ge $MAX_RESTARTS_PER_HOUR ]; then
            log "CIRCUIT BREAKER: $restart_count restarts in the last hour. Sleeping 15 min before re-arming."
            sleep 900
            restart_count=0
            hour_start=$(date +%s)
            log "Circuit breaker reset. Resuming monitoring."
            continue
        fi

        # Health check
        if is_backend_alive; then
            consecutive_failures=0
        else
            consecutive_failures=$((consecutive_failures + 1))
            log "CRASH DETECTED (attempt $consecutive_failures) — backend not running on port $BACKEND_PORT"

            # Kill any orphan processes
            kill_backend

            # Restart
            restart_count=$((restart_count + 1))
            log "Restarting backend (restart #$restart_count this hour)..."
            start_backend || {
                log "Restart failed — will retry in ${CHECK_INTERVAL}s"
            }
        fi
    done
}

case "${1:-}" in
    start)
        # Check if already running
        if [ -f "$WATCHDOG_PID_FILE" ]; then
            old_pid=$(cat "$WATCHDOG_PID_FILE")
            if kill -0 "$old_pid" 2>/dev/null; then
                echo "Backend watchdog already running (PID $old_pid)"
                exit 0
            fi
        fi

        echo "Starting backend watchdog..."
        nohup "$SCRIPT_PATH" _run >> "$WATCHDOG_LOG" 2>&1 &
        disown
        echo "Backend watchdog started (PID $!)"
        echo "Log: $WATCHDOG_LOG"
        ;;

    _run)
        # Internal — called by start
        run_watchdog
        ;;

    stop)
        if [ -f "$WATCHDOG_PID_FILE" ]; then
            pid=$(cat "$WATCHDOG_PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null
                rm -f "$WATCHDOG_PID_FILE"
                echo "Backend watchdog stopped (PID $pid)"
            else
                rm -f "$WATCHDOG_PID_FILE"
                echo "Backend watchdog was not running (stale PID file removed)"
            fi
        else
            echo "No backend watchdog PID file found"
        fi
        ;;

    status)
        echo "=== Backend Watchdog ==="
        if [ -f "$WATCHDOG_PID_FILE" ]; then
            pid=$(cat "$WATCHDOG_PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                echo "  Running (PID $pid)"
            else
                echo "  NOT running (stale PID file)"
            fi
        else
            echo "  NOT running"
        fi

        echo ""
        echo "=== Backend (port $BACKEND_PORT) ==="
        if is_backend_alive; then
            echo "  Process: ALIVE"
            if is_backend_responding; then
                echo "  HTTP: RESPONDING"
            else
                echo "  HTTP: NOT RESPONDING (may be initializing)"
            fi
        else
            echo "  Process: DOWN"
        fi

        echo ""
        echo "=== Recent backend crashes ==="
        grep "CRASH DETECTED" "$WATCHDOG_LOG" 2>/dev/null | tail -5 || echo "  None recorded"
        ;;

    debug)
        # Run watchdog directly in the foreground — for interactive troubleshooting only
        echo "Running backend watchdog in DEBUG mode (foreground, no nohup)..."
        echo "Press Ctrl-C to stop."
        run_watchdog
        ;;

    *)
        echo "Usage: $0 {start|stop|status|debug}"
        exit 1
        ;;
esac
