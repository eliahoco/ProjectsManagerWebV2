#!/bin/bash

# ProjectsManagerWebV2Production Park Script
# Safely parks (shuts down) services in reverse dependency order:
#   AI Sessions → Frontend → Backend → ChromaDB → Cleanup

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

# Ports
FRONTEND_PORT=3601
BACKEND_PORT=8401
CHROMADB_PORT=8402

# ---------------------------------------------------------------------------
# graceful_stop <pid_file> <service_name>
#   Sends SIGTERM, waits up to 5s checking each second, then SIGKILL.
#   Removes the PID file on exit.
# ---------------------------------------------------------------------------
graceful_stop() {
    local pid_file="$1"
    local name="$2"

    if [ ! -f "$pid_file" ]; then
        echo -e "[${YELLOW}SKIPPED${NC}]"
        return 0
    fi

    local PID
    PID=$(cat "$pid_file" 2>/dev/null)

    if [ -z "$PID" ]; then
        rm -f "$pid_file"
        echo -e "[${YELLOW}SKIPPED${NC}]"
        return 0
    fi

    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$pid_file"
        echo -e "[${YELLOW}SKIPPED${NC}]"
        return 0
    fi

    # SIGTERM
    kill -TERM "$PID" 2>/dev/null || true

    # Wait up to 5 seconds
    local waited=0
    while [ $waited -lt 5 ]; do
        sleep 1
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$pid_file"
            echo -e "[${GREEN}PARKED${NC}]"
            return 0
        fi
        ((waited++))
    done

    # SIGKILL fallback
    kill -9 "$PID" 2>/dev/null || true
    sleep 1
    rm -f "$pid_file"
    echo -e "[${GREEN}PARKED${NC}]"
    return 0
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}        ${BOLD}Parking ProjectsManagerWebV2...${NC}                     ${CYAN}║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ---------------------------------------------------------------------------
# Step 1/5 — Stop AI Executions (only if backend is reachable)
# ---------------------------------------------------------------------------
echo -ne "  [1/5] AI Sessions           "
if curl -s --max-time 2 "http://localhost:${BACKEND_PORT}/api/execute/sessions" >/dev/null 2>&1; then
    # Fetch all active session IDs and stop each one
    SESSION_IDS=$(curl -s --max-time 3 "http://localhost:${BACKEND_PORT}/api/execute/sessions" \
        2>/dev/null | grep -o '"id":"[^"]*"' | cut -d'"' -f4 || true)

    if [ -n "$SESSION_IDS" ]; then
        for sid in $SESSION_IDS; do
            # Validate session ID is a safe UUID/alphanumeric string
            [[ "$sid" =~ ^[a-zA-Z0-9_-]+$ ]] || continue
            curl -s --max-time 3 -X POST \
                "http://localhost:${BACKEND_PORT}/api/execute/session/${sid}/stop" \
                >/dev/null 2>&1 || true
        done
        echo -e "[${GREEN}PARKED${NC}]"
    else
        echo -e "[${YELLOW}SKIPPED${NC}]"
    fi
else
    echo -e "[${YELLOW}SKIPPED${NC}]"
fi

# ---------------------------------------------------------------------------
# Step 2/5 — Stop Frontend (Next.js, port 3601)
# ---------------------------------------------------------------------------
echo -ne "  [2/5] Frontend (Next.js)    "
graceful_stop "logs/frontend.pid" "Frontend"

# ---------------------------------------------------------------------------
# Step 3/5 — Stop Backend (FastAPI, port 8401)
# ---------------------------------------------------------------------------
echo -ne "  [3/5] Backend (FastAPI)     "
graceful_stop "logs/backend.pid" "Backend"

# ---------------------------------------------------------------------------
# Step 4/5 — Stop ChromaDB (Docker container, port 8402)
# ---------------------------------------------------------------------------
echo -ne "  [4/5] ChromaDB (Docker)     "
if docker compose stop -t 10 chromadb >/dev/null 2>&1; then
    echo -e "[${GREEN}PARKED${NC}]"
else
    # Non-fatal — container may already be stopped
    echo -e "[${YELLOW}SKIPPED${NC}]"
fi

# ---------------------------------------------------------------------------
# Step 5/5 — Cleanup: kill any zombie processes still holding ports
# ---------------------------------------------------------------------------
echo -ne "  [5/5] Cleanup (ports)       "
lsof -ti:${FRONTEND_PORT}  | xargs kill -9 2>/dev/null || true
lsof -ti:${BACKEND_PORT}   | xargs kill -9 2>/dev/null || true
lsof -ti:${CHROMADB_PORT}  | xargs kill -9 2>/dev/null || true
rm -f logs/frontend.pid logs/backend.pid
echo -e "[${GREEN}PARKED${NC}]"

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  ${BOLD}Project Parked${NC}                                           ${GREEN}║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
