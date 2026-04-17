#!/bin/bash
# =============================================================================
# Frontend Watchdog — Auto-restarts Next.js dev server on crash
# =============================================================================
#
# ROOT CAUSE: Turbopack's memory-mapped cache files on the Seagate external HDD
# trigger SIGBUS (FS pagein error) when macOS can't page in data fast enough.
# This kills the Node.js process instantly. There's no code fix — it's a
# hardware I/O limitation with the external drive.
#
# This watchdog monitors port 3601 and restarts the dev server if it dies.
#
# Usage:
#   ./watchdog.sh start    — Start the watchdog (backgrounds itself) + backend-watchdog.sh
#   ./watchdog.sh stop     — Stop the watchdog + backend-watchdog.sh
#   ./watchdog.sh status   — Check watchdog and frontend status + backend-watchdog.sh
#   ./watchdog.sh debug    — Run in foreground (no nohup) for interactive troubleshooting
#
# The watchdog writes its PID to logs/watchdog.pid and logs to logs/watchdog.log
# =============================================================================

set -euo pipefail

# Absolute path to this script (survives cd and terminal close)
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
LOGS_DIR="$SCRIPT_DIR/logs"
WATCHDOG_PID_FILE="$LOGS_DIR/watchdog.pid"
WATCHDOG_LOG="$LOGS_DIR/watchdog.log"
FRONTEND_PORT=3601
CHECK_INTERVAL=15        # seconds between health checks
STARTUP_WAIT=30          # seconds to wait after starting frontend
MAX_RESTARTS_PER_HOUR=10 # circuit breaker

mkdir -p "$LOGS_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$WATCHDOG_LOG"
}

is_frontend_alive() {
    lsof -ti :$FRONTEND_PORT >/dev/null 2>&1
}

is_frontend_responding() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://localhost:$FRONTEND_PORT/api/projects" 2>/dev/null || echo "000")
    [[ "$code" =~ ^[2345] ]]  # 2xx, 3xx, 4xx, 5xx all mean server is alive
}

kill_frontend() {
    lsof -ti :$FRONTEND_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
    sleep 2
}

start_frontend() {
    log "Starting frontend dev server..."

    # Clean .next cache to avoid stale mmap'd files
    rm -rf "$FRONTEND_DIR/.next"

    # Start in background, redirect output to log
    cd "$FRONTEND_DIR"
    nohup npm run dev >> "$LOGS_DIR/frontend.log" 2>&1 &
    local pid=$!
    echo $pid > "$LOGS_DIR/frontend.pid"
    log "Frontend started with PID $pid"

    # Wait for it to be ready
    local waited=0
    while [ $waited -lt $STARTUP_WAIT ]; do
        sleep 5
        waited=$((waited + 5))
        if is_frontend_responding; then
            log "Frontend is responding after ${waited}s"
            return 0
        fi
    done

    # Check if process is at least alive (may be slow to compile)
    if is_frontend_alive; then
        log "Frontend process alive but not yet responding after ${waited}s — will keep checking"
        return 0
    fi

    log "ERROR: Frontend failed to start after ${waited}s"
    return 1
}

run_watchdog() {
    log "=========================================="
    log "Watchdog started (PID $$)"
    log "Monitoring frontend on port $FRONTEND_PORT"
    log "Check interval: ${CHECK_INTERVAL}s"
    log "=========================================="

    echo $$ > "$WATCHDOG_PID_FILE"

    local restart_count=0
    local hour_start=$(date +%s)
    local consecutive_failures=0

    # Make sure frontend is running initially
    if ! is_frontend_alive; then
        log "Frontend not running — starting it"
        start_frontend || true
    fi

    while true; do
        sleep $CHECK_INTERVAL

        # Reset restart counter every hour
        local now=$(date +%s)
        if [ $((now - hour_start)) -ge 3600 ]; then
            restart_count=0
            hour_start=$now
        fi

        # Circuit breaker
        if [ $restart_count -ge $MAX_RESTARTS_PER_HOUR ]; then
            log "CIRCUIT BREAKER: $restart_count restarts in the last hour. Sleeping 15 min before re-arming."
            sleep 900
            restart_count=0
            hour_start=$(date +%s)
            log "Circuit breaker reset. Resuming monitoring."
            continue
        fi

        # Health check
        if is_frontend_alive; then
            consecutive_failures=0
        else
            consecutive_failures=$((consecutive_failures + 1))
            log "CRASH DETECTED (attempt $consecutive_failures) — frontend not running on port $FRONTEND_PORT"

            # Kill any orphan processes
            kill_frontend

            # Restart
            restart_count=$((restart_count + 1))
            log "Restarting frontend (restart #$restart_count this hour)..."
            start_frontend || {
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
                echo "Watchdog already running (PID $old_pid)"
                exit 0
            fi
        fi

        echo "Starting frontend watchdog..."
        nohup "$SCRIPT_PATH" _run >> "$WATCHDOG_LOG" 2>&1 &
        disown
        echo "Frontend watchdog started (PID $!)"
        echo "Log: $WATCHDOG_LOG"

        # Also start the backend watchdog
        if [ -x "$SCRIPT_DIR/backend-watchdog.sh" ]; then
            "$SCRIPT_DIR/backend-watchdog.sh" start
        else
            echo "WARNING: backend-watchdog.sh not found or not executable — skipping"
        fi
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
                echo "Frontend watchdog stopped (PID $pid)"
            else
                rm -f "$WATCHDOG_PID_FILE"
                echo "Frontend watchdog was not running (stale PID file removed)"
            fi
        else
            echo "No frontend watchdog PID file found"
        fi

        # Also stop the backend watchdog
        if [ -x "$SCRIPT_DIR/backend-watchdog.sh" ]; then
            "$SCRIPT_DIR/backend-watchdog.sh" stop
        fi
        ;;

    status)
        echo "=== Frontend Watchdog ==="
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
        echo "=== Frontend (port $FRONTEND_PORT) ==="
        if is_frontend_alive; then
            echo "  Process: ALIVE"
            if is_frontend_responding; then
                echo "  HTTP: RESPONDING"
            else
                echo "  HTTP: NOT RESPONDING (may be compiling)"
            fi
        else
            echo "  Process: DOWN"
        fi

        echo ""
        echo "=== Recent frontend crashes ==="
        grep "CRASH DETECTED" "$WATCHDOG_LOG" 2>/dev/null | tail -5 || echo "  None recorded"

        # Also show backend watchdog status
        echo ""
        if [ -x "$SCRIPT_DIR/backend-watchdog.sh" ]; then
            "$SCRIPT_DIR/backend-watchdog.sh" status
        fi
        ;;

    debug)
        # Run watchdog directly in the foreground — for interactive troubleshooting only
        echo "Running frontend watchdog in DEBUG mode (foreground, no nohup)..."
        echo "Press Ctrl-C to stop."
        run_watchdog
        ;;

    *)
        echo "Usage: $0 {start|stop|status|debug}"
        exit 1
        ;;
esac
