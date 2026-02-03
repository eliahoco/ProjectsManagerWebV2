#!/bin/bash

# ProjectsManagerWebV2Production Stop Script
# Stops the FastAPI backend and Next.js frontend

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

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}        ${BOLD}ProjectsManagerWebV2 - Stopping...${NC}                  ${CYAN}║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Stop Backend
echo -ne "  [1/2] Backend (FastAPI)     "
if [ -f logs/backend.pid ]; then
    PID=$(cat logs/backend.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID 2>/dev/null || true
        sleep 1
        kill -9 $PID 2>/dev/null || true
        echo -e "[${GREEN}STOPPED${NC}]"
    else
        echo -e "[${YELLOW}NOT RUNNING${NC}]"
    fi
    rm -f logs/backend.pid
else
    echo -e "[${YELLOW}NOT RUNNING${NC}]"
fi

# Stop Frontend
echo -ne "  [2/2] Frontend (Next.js)    "
if [ -f logs/frontend.pid ]; then
    PID=$(cat logs/frontend.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID 2>/dev/null || true
        sleep 1
        kill -9 $PID 2>/dev/null || true
        echo -e "[${GREEN}STOPPED${NC}]"
    else
        echo -e "[${YELLOW}NOT RUNNING${NC}]"
    fi
    rm -f logs/frontend.pid
else
    echo -e "[${YELLOW}NOT RUNNING${NC}]"
fi

# Clean up any remaining processes on the ports
echo ""
echo -e "  ${CYAN}Cleaning up ports...${NC}"
lsof -ti:$BACKEND_PORT | xargs kill -9 2>/dev/null || true
lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  ${BOLD}All Services Stopped${NC}                                     ${GREEN}║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
