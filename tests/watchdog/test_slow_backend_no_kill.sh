#!/bin/bash
# T1 — STARTUP_WAIT=90 + HTTP gate must NOT kill a backend that takes 60s to bind.
# The watchdog's start_backend() loop runs for up to STARTUP_WAIT seconds.
# After the loop, if is_backend_alive() returns true the watchdog logs "alive but
# not yet responding" and returns 0 (no kill).  This test verifies that path.
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
    lsof -ti :18401 2>/dev/null | xargs kill -9 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

# Write the override start_backend to a separate sourced file
cat > "$WORK/start_backend_override.sh" <<OVERRIDE_EOF
start_backend() {
    log "start_backend OVERRIDE -- launching slow stub (60s delay)"
    (
        sleep 60
        python3 -m http.server 18401 --bind 127.0.0.1 >/dev/null 2>&1 &
        echo \$! > "$WORK/logs/backend.pid"
        wait
    ) &
    local stub_wrapper=\$!
    # Write wrapper PID immediately so is_backend_alive can find any child
    # We store the wrapper; the real port-holder PID lands after 60s
    echo \$stub_wrapper > "$WORK/logs/backend.pid"

    # Mirror real watchdog: poll up to STARTUP_WAIT for HTTP response
    local waited=0
    while [ \$waited -lt \$STARTUP_WAIT ]; do
        sleep 5
        waited=\$((waited + 5))
        if is_backend_responding; then
            log "stub responding after \${waited}s"
            return 0
        fi
    done
    # Process alive check (wrapper still sleeping even if port not bound yet)
    if kill -0 \$stub_wrapper 2>/dev/null; then
        log "stub alive but not yet responding after \${waited}s -- will keep checking"
        return 0
    fi
    log "ERROR: stub failed to start after \${waited}s"
    return 1
}
OVERRIDE_EOF

# Patch watchdog: redirect port and paths, tighten CHECK_INTERVAL
sed \
    -e 's|BACKEND_PORT=8401|BACKEND_PORT=18401|g' \
    -e "s|PROJECT_ROOT=.*|PROJECT_ROOT=\"$WORK\"|g" \
    -e 's|CHECK_INTERVAL=15|CHECK_INTERVAL=10|g' \
    "$WORK/backend-watchdog.sh" > "$WORK/watchdog_patched.sh"

# Inject: source override at top of run_watchdog()
sed "s|^run_watchdog() {|run_watchdog() {\n    source \"$WORK/start_backend_override.sh\"|" \
    "$WORK/watchdog_patched.sh" > "$WORK/watchdog_final.sh"
chmod +x "$WORK/watchdog_final.sh"

# --- Launch watchdog in foreground (debug mode) ---
cd "$WORK"
bash "$WORK/watchdog_final.sh" debug > "$WORK/logs/backend-watchdog.log" 2>&1 &
WATCHDOG_PID=$!

# Stub binds at T=60. We check at T=95 that the original wrapper PID is alive.
echo "Waiting 95s for slow-start scenario (stub sleeps 60s before binding)..."
sleep 95

# --- Assertions ---
if [ ! -f "$WORK/logs/backend.pid" ]; then
    echo "FAIL: backend.pid not created -- start_backend was never called"
    exit 1
fi

BACKEND_PID=$(cat "$WORK/logs/backend.pid")

# The wrapper process should still be alive (or the python3 server it spawned)
ALIVE=0
kill -0 "$BACKEND_PID" 2>/dev/null && ALIVE=1
# Also accept: port 18401 is now bound by python3
lsof -ti :18401 >/dev/null 2>&1 && ALIVE=1

if [ "$ALIVE" -eq 0 ]; then
    echo "FAIL: backend process (PID $BACKEND_PID) is gone and port 18401 not bound -- watchdog killed slow-starting backend"
    echo "--- watchdog log tail ---"
    tail -20 "$WORK/logs/backend-watchdog.log" 2>/dev/null || true
    exit 1
fi

# Confirm no kill -9 was issued in the log
if grep -q "kill -9" "$WORK/logs/backend-watchdog.log" 2>/dev/null; then
    echo "FAIL: watchdog log contains 'kill -9' -- backend was forcibly killed"
    exit 1
fi

echo "PASS: slow-starting backend (60s bind) survived STARTUP_WAIT=90 without being killed"
exit 0
