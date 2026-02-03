#!/bin/bash

# ProjectsManagerWebV2Production Launch Script
# Starts the FastAPI backend and Next.js frontend with progress dashboard

set -e

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

# Create logs directory
mkdir -p logs

# Function to check if port is in use
check_port() {
    lsof -i :$1 >/dev/null 2>&1
}

# Function to wait for service
wait_for_service() {
    local port=$1
    local name=$2
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://localhost:$port" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        ((attempt++))
    done
    return 1
}

# Print header
clear
echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}        ${BOLD}ProjectsManagerWebV2 - CodeBoard${NC}                    ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}        AI-Powered Project Management                       ${CYAN}║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Progress Dashboard
echo -e "${BOLD}Starting Services...${NC}"
echo ""

# Backend
echo -ne "  [1/2] Backend (FastAPI)     "
if [ -f logs/backend.pid ] && kill -0 $(cat logs/backend.pid) 2>/dev/null; then
    echo -e "[${YELLOW}ALREADY RUNNING${NC}]"
else
    echo -ne "[${CYAN}STARTING${NC}]"
    cd backend
    # Use venv python directly instead of sourcing activate (more reliable in nohup)
    PYTHON_BIN="python3"
    if [ -f "venv/bin/python" ]; then
        PYTHON_BIN="./venv/bin/python"
    fi
    nohup $PYTHON_BIN -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload > ../logs/backend.log 2>&1 &
    echo $! > ../logs/backend.pid
    cd ..

    # Wait for backend to be ready
    sleep 2
    if wait_for_service $BACKEND_PORT "Backend"; then
        echo -e "\r  [1/2] Backend (FastAPI)     [${GREEN}RUNNING${NC}]    "
    else
        echo -e "\r  [1/2] Backend (FastAPI)     [${YELLOW}STARTING...${NC}]"
    fi
fi

# Frontend
echo -ne "  [2/2] Frontend (Next.js)    "
if [ -f logs/frontend.pid ] && kill -0 $(cat logs/frontend.pid) 2>/dev/null; then
    echo -e "[${YELLOW}ALREADY RUNNING${NC}]"
else
    echo -ne "[${CYAN}STARTING${NC}]"
    cd frontend
    nohup npm run dev > ../logs/frontend.log 2>&1 &
    echo $! > ../logs/frontend.pid
    cd ..

    # Wait for frontend to be ready
    sleep 3
    if wait_for_service $FRONTEND_PORT "Frontend"; then
        echo -e "\r  [2/2] Frontend (Next.js)    [${GREEN}RUNNING${NC}]    "
    else
        echo -e "\r  [2/2] Frontend (Next.js)    [${YELLOW}STARTING...${NC}]"
    fi
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  ${BOLD}Services Started Successfully!${NC}                           ${GREEN}║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Frontend:${NC}  http://localhost:${FRONTEND_PORT}"
echo -e "  ${BOLD}Backend:${NC}   http://localhost:${BACKEND_PORT}"
echo -e "  ${BOLD}API Docs:${NC}  http://localhost:${BACKEND_PORT}/docs"
echo ""
echo -e "  ${CYAN}Logs:${NC}      ./logs/frontend.log"
echo -e "             ./logs/backend.log"
echo ""
echo -e "  ${YELLOW}Stop:${NC}      ./stop.sh"
echo ""
