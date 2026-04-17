#!/bin/bash

# ProjectsManagerWebV2Production Launch Script
# Starts all services in dependency order:
#   Colima (Docker VM) → ChromaDB (vector DB) → Backend (FastAPI) → Frontend (Next.js)

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
CHROMADB_PORT=8402

# Create logs directory
mkdir -p logs

# --- Port Validation ---
SHARED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_shared"
if [[ -f "$SHARED_DIR/validate-ports.sh" ]]; then
    source "$SHARED_DIR/validate-ports.sh"
    _parse_args "$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")"
    validate_project_ports || exit 1
else
    echo -e "\033[1;33mWarning: validate-ports.sh not found, skipping port validation\033[0m"
fi

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

# Step 1: Colima (Docker VM) — everything depends on this
echo -ne "  [1/4] Colima (Docker VM)    "
if docker info >/dev/null 2>&1; then
    echo -e "[${YELLOW}ALREADY RUNNING${NC}]"
elif colima status 2>&1 | grep -q "running"; then
    # Colima VM up but Docker socket may be stale — restart
    echo -ne "[${CYAN}RECONNECTING${NC}]"
    colima stop > logs/colima.log 2>&1 || true
    colima start >> logs/colima.log 2>&1
    if docker info >/dev/null 2>&1; then
        echo -e "\r  [1/4] Colima (Docker VM)    [${GREEN}RUNNING${NC}]    "
    else
        echo -e "\r  [1/4] Colima (Docker VM)    [${RED}FAILED${NC}]     "
        echo -e "  ${RED}Error: Colima running but Docker not responding. Check logs/colima.log${NC}"
        exit 1
    fi
else
    echo -ne "[${CYAN}STARTING${NC}]"
    colima start > logs/colima.log 2>&1
    if docker info >/dev/null 2>&1; then
        echo -e "\r  [1/4] Colima (Docker VM)    [${GREEN}RUNNING${NC}]    "
    else
        echo -e "\r  [1/4] Colima (Docker VM)    [${RED}FAILED${NC}]     "
        echo -e "  ${RED}Error: Colima failed to start. Check logs/colima.log${NC}"
        exit 1
    fi
fi

# Step 2: ChromaDB (Docker container) — backend depends on this
echo -ne "  [2/4] ChromaDB (Vector DB)  "
if check_port $CHROMADB_PORT; then
    echo -e "[${YELLOW}ALREADY RUNNING${NC}]"
else
    echo -ne "[${CYAN}STARTING${NC}]"
    docker compose up -d chromadb > logs/chromadb.log 2>&1
    sleep 2
    if wait_for_service $CHROMADB_PORT "ChromaDB"; then
        echo -e "\r  [2/4] ChromaDB (Vector DB)  [${GREEN}RUNNING${NC}]    "
    else
        echo -e "\r  [2/4] ChromaDB (Vector DB)  [${YELLOW}STARTING...${NC}]"
    fi
fi

# Step 3: Backend (FastAPI) — depends on ChromaDB
echo -ne "  [3/4] Backend (FastAPI)     "
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
    # Bind to 127.0.0.1 by default (local dev). Set ALLOW_LAN=true or HOST=0.0.0.0 for LAN access.
    BACKEND_HOST="${HOST:-127.0.0.1}"
    if [ "${ALLOW_LAN:-false}" = "true" ]; then BACKEND_HOST="0.0.0.0"; fi
    nohup $PYTHON_BIN -m uvicorn app.main:app --host $BACKEND_HOST --port $BACKEND_PORT --reload > ../logs/backend.log 2>&1 &
    echo $! > ../logs/backend.pid
    cd ..

    # Wait for backend to be ready
    sleep 2
    if wait_for_service $BACKEND_PORT "Backend"; then
        echo -e "\r  [3/4] Backend (FastAPI)     [${GREEN}RUNNING${NC}]    "
    else
        echo -e "\r  [3/4] Backend (FastAPI)     [${YELLOW}STARTING...${NC}]"
    fi
fi

# Step 4: Frontend (Next.js) — depends on backend
echo -ne "  [4/4] Frontend (Next.js)    "
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
        echo -e "\r  [4/4] Frontend (Next.js)    [${GREEN}RUNNING${NC}]    "
    else
        echo -e "\r  [4/4] Frontend (Next.js)    [${YELLOW}STARTING...${NC}]"
    fi
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  ${BOLD}Services Started Successfully!${NC}                           ${GREEN}║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Frontend:${NC}  http://localhost:${FRONTEND_PORT}"
echo -e "  ${BOLD}Backend:${NC}   http://localhost:${BACKEND_PORT}"
echo -e "  ${BOLD}ChromaDB:${NC}  http://localhost:${CHROMADB_PORT}"
echo -e "  ${BOLD}API Docs:${NC}  http://localhost:${BACKEND_PORT}/docs"
echo ""
echo -e "  ${CYAN}Logs:${NC}      ./logs/frontend.log"
echo -e "             ./logs/backend.log"
echo -e "             ./logs/colima.log"
echo -e "             ./logs/chromadb.log"
echo ""
echo -e "  ${YELLOW}Park:${NC}      ./stop.sh"
echo ""
