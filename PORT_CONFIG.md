# Port Configuration

**IMPORTANT: This project has allocated ports. Use ONLY these ports to avoid conflicts with other projects.**

## Allocated Ports for ProjectsManagerWebV2Production

| Service | Port | URL |
|---------|------|-----|
| Frontend (Next.js) | 3601 | http://localhost:3601 |
| Backend API (FastAPI) | 8401 | http://localhost:8401 |
| ChromaDB | 8402 | http://localhost:8402 |

## Rules

1. **NEVER** change these ports without updating the central port registry
2. **NEVER** use ports from other projects (check PORT_REGISTRY.md)
3. If you need additional ports, use `suggest_available_ports` function
4. All port changes must be reflected in:
   - docker-compose.yml
   - .env files
   - PORT_CONFIG.md (this file)
   - Central ports.db

## How to Check for Conflicts

```bash
# From ProjectsManagerProduction directory:
sqlite3 ports.db "SELECT * FROM port_collisions;"
```
