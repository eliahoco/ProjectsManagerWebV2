# ProjectsManagerWebV2 with CodeBoard - Detailed Implementation Plan

## Project Overview

**Project Name:** ProjectsManagerWebV2
**Location:** `/Users/elic/Documents/Claude/ProjectsManagerWebV2`
**Description:** A next-generation project manager with AI-automated task management (CodeBoard)

## Allocated Ports

| Service | Port | URL |
|---------|------|-----|
| Frontend (Next.js) | 3601 | http://localhost:3601 |
| Backend (FastAPI) | 8401 | http://localhost:8401 |
| ChromaDB | 8501 | http://localhost:8501 |

---

## Implementation Tracking System

We will use an SQLite database (`implementation_tracker.db`) to track our own progress using the same methodology we're building.

### Tracker Database Schema

```sql
CREATE TABLE epics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG',
    progress INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE TABLE stories (
    id TEXT PRIMARY KEY,
    epic_id TEXT REFERENCES epics(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG',
    priority TEXT DEFAULT 'MEDIUM',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    story_id TEXT REFERENCES stories(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE TABLE subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    title TEXT NOT NULL,
    status TEXT DEFAULT 'BACKLOG',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);
```

### launch.sh Progress Dashboard

```
╔══════════════════════════════════════════════════════════════════╗
║           ProjectsManagerWebV2 - Implementation Progress         ║
╠══════════════════════════════════════════════════════════════════╣
║  Overall Progress: ████████░░░░░░░░░░░░ 42% (15/36 tasks)       ║
╠══════════════════════════════════════════════════════════════════╣
║  EPICS:                                                          ║
║  ✅ E1: Project Setup & Infrastructure      [DONE]               ║
║  🔄 E2: Database & API Foundation           [IN PROGRESS] 60%    ║
║  ⬚  E3: CodeBoard UI                        [TODO]               ║
║  ⬚  E4: RAG Integration                     [BACKLOG]            ║
║  ⬚  E5: AI Engine                           [BACKLOG]            ║
║  ⬚  E6: Git Integration & Automation        [BACKLOG]            ║
║  ⬚  E7: Polish & Testing                    [BACKLOG]            ║
╠══════════════════════════════════════════════════════════════════╣
║  CURRENT TASK:                                                   ║
║  📋 T2.3: Create FastAPI Issue CRUD endpoints                    ║
║  └─ Sub-tasks: 2/4 complete                                      ║
╠══════════════════════════════════════════════════════════════════╣
║  NEXT UP:                                                        ║
║  • T2.4: Set up issue sequence generation                        ║
║  • T2.5: Create API proxy routes in Next.js                      ║
╚══════════════════════════════════════════════════════════════════╝
```

---

# EPIC 1: Project Setup & Infrastructure

**ID:** E1
**Priority:** Critical
**Status:** BACKLOG
**Description:** Set up the complete project infrastructure including directory structure, Next.js frontend, FastAPI backend, Docker configuration, and launch scripts. This epic establishes the foundation for all subsequent development.

**Acceptance Criteria:**
- All services can be started with a single `./launch.sh` command
- Frontend accessible at http://localhost:3601
- Backend accessible at http://localhost:8401
- ChromaDB accessible at http://localhost:8501
- Health endpoints return 200 OK for all services

---

## Story 1.1: Create Project Structure

**ID:** S1.1
**Epic:** E1
**Priority:** Critical
**Description:** Create the base project directory structure with separate folders for frontend, backend, and shared resources. Establish the implementation tracker database to monitor our own progress.

---

### Task T1.1.1: Create ProjectsManagerWebV2 Directory

**ID:** T1.1.1
**Story:** S1.1
**Priority:** Critical
**Estimated Effort:** 15 minutes

**Description:**
Create the root project directory and establish the folder hierarchy for the entire application. The structure must support a monorepo-style organization with separate frontend and backend directories, shared configuration files at the root, and proper separation of concerns.

**Technical Requirements:**
- Create root directory at `/Users/elic/Documents/Claude/ProjectsManagerWebV2`
- Create `frontend/` directory for Next.js application
- Create `backend/` directory for FastAPI service
- Create `docs/` directory for additional documentation
- Create `scripts/` directory for utility scripts

**Directory Structure to Create:**
```
ProjectsManagerWebV2/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── prisma/
│   └── public/
├── backend/
│   ├── app/
│   ├── api/
│   ├── models/
│   ├── services/
│   └── tests/
├── docs/
├── scripts/
├── docker-compose.yml
├── launch.sh
├── stop.sh
├── .gitignore
└── README.md
```

**Acceptance Criteria:**
- [ ] Root directory exists and is a git repository
- [ ] All subdirectories are created with proper permissions
- [ ] .gitignore file includes node_modules, __pycache__, .env, *.db, .next, venv
- [ ] README.md contains basic project description

**Sub-tasks:**
1. **Create root folder** - `mkdir -p /Users/elic/Documents/Claude/ProjectsManagerWebV2`
2. **Create frontend folder structure** - Create app/, components/, lib/, prisma/, public/ inside frontend/
3. **Create backend folder structure** - Create app/, api/, models/, services/, tests/ inside backend/
4. **Initialize git repository** - Run `git init` and create initial .gitignore
5. **Create README.md** - Basic project description with setup instructions

---

### Task T1.1.2: Set Up Implementation Tracker Database

**ID:** T1.1.2
**Story:** S1.1
**Priority:** High
**Estimated Effort:** 1 hour

**Description:**
Create an SQLite database to track the implementation progress of this very project. This database will store all epics, stories, tasks, and subtasks defined in this plan, allowing us to query progress and display it in the launch script dashboard. This is a meta-feature: we're building a task tracker while using a task tracker to track building the task tracker.

**Technical Requirements:**
- SQLite database file at `implementation_tracker.db`
- Schema supports hierarchical task structure (Epic → Story → Task → Subtask)
- Each level has status tracking (BACKLOG, TODO, IN_PROGRESS, DONE)
- Timestamps for creation and completion
- Progress percentage calculation capability

**Database Schema:**
```sql
-- Epics table (highest level)
CREATE TABLE epics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG' CHECK(status IN ('BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE')),
    progress INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

-- Stories table (belongs to epic)
CREATE TABLE stories (
    id TEXT PRIMARY KEY,
    epic_id TEXT NOT NULL REFERENCES epics(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG' CHECK(status IN ('BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE')),
    priority TEXT DEFAULT 'MEDIUM' CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

-- Tasks table (belongs to story)
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG' CHECK(status IN ('BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

-- Subtasks table (belongs to task)
CREATE TABLE subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'BACKLOG' CHECK(status IN ('BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

-- Indexes for performance
CREATE INDEX idx_stories_epic ON stories(epic_id);
CREATE INDEX idx_tasks_story ON tasks(story_id);
CREATE INDEX idx_subtasks_task ON subtasks(task_id);

-- View for progress calculation
CREATE VIEW epic_progress AS
SELECT
    e.id,
    e.title,
    e.status,
    COUNT(CASE WHEN t.status = 'DONE' THEN 1 END) as completed_tasks,
    COUNT(t.id) as total_tasks,
    ROUND(COUNT(CASE WHEN t.status = 'DONE' THEN 1 END) * 100.0 / NULLIF(COUNT(t.id), 0), 1) as progress_pct
FROM epics e
LEFT JOIN stories s ON s.epic_id = e.id
LEFT JOIN tasks t ON t.story_id = s.id
GROUP BY e.id;
```

**Seed Data:**
Insert all 7 epics, 27 stories, and 80 tasks from this implementation plan.

**Acceptance Criteria:**
- [ ] Database file created at project root
- [ ] All tables created with proper constraints
- [ ] All epics, stories, tasks seeded from this plan
- [ ] Progress view returns accurate percentages
- [ ] Query script can display current status

**Sub-tasks:**
1. **Create database schema** - Write and execute CREATE TABLE statements
2. **Create seed script** - Python or SQL script to insert all items from this plan
3. **Seed with all tasks** - Execute seed script to populate database
4. **Create query script** - `scripts/progress.sh` to query and display progress
5. **Verify data integrity** - Run queries to ensure all relationships are correct

---

### Task T1.1.3: Create PORT_CONFIG.md and Update Registry

**ID:** T1.1.3
**Story:** S1.1
**Priority:** Medium
**Estimated Effort:** 15 minutes

**Description:**
Document the port allocations for this project and update the central port registry (if one exists). This ensures no port conflicts with other projects and provides a quick reference for all services.

**Technical Requirements:**
- PORT_CONFIG.md in project root
- Document all three services with their ports
- Include health check endpoints
- Note any environment variable overrides

**File Content (PORT_CONFIG.md):**
```markdown
# ProjectsManagerWebV2 - Port Configuration

## Allocated Ports

| Service | Port | Health Check | Environment Variable |
|---------|------|--------------|---------------------|
| Frontend (Next.js) | 3601 | http://localhost:3601/api/health | FRONTEND_PORT |
| Backend (FastAPI) | 8401 | http://localhost:8401/health | BACKEND_PORT |
| ChromaDB | 8501 | http://localhost:8501/api/v1/heartbeat | CHROMA_PORT |

## Port Ranges

This project uses ports in the following ranges:
- **3600-3699**: Frontend services
- **8400-8499**: Backend API services
- **8500-8599**: Database/Vector store services

## Conflict Resolution

If any port is in use, set the corresponding environment variable:
```bash
export FRONTEND_PORT=3602
export BACKEND_PORT=8402
export CHROMA_PORT=8502
```

## Related Projects

- ProjectsManagerWebProduction: 3500 (frontend)
- ProjectsManagerProduction: 3000 (CLI)
```

**Acceptance Criteria:**
- [ ] PORT_CONFIG.md created with all port information
- [ ] Environment variable overrides documented
- [ ] Central PORT_REGISTRY.md updated (if exists)

**Sub-tasks:**
1. **Create PORT_CONFIG.md** - Write file with port documentation
2. **Document ports 3601, 8401, 8501** - Include all service details
3. **Update central PORT_REGISTRY.md** - Add entry for this project (if registry exists)

---

## Story 1.2: Set Up Next.js Frontend

**ID:** S1.2
**Epic:** E1
**Priority:** Critical
**Description:** Initialize and configure the Next.js frontend application by duplicating the base from ProjectsManagerWebProduction and updating configurations for the new port and environment.

---

### Task T1.2.1: Duplicate Base from ProjectsManagerWebProduction

**ID:** T1.2.1
**Story:** S1.2
**Priority:** Critical
**Estimated Effort:** 30 minutes

**Description:**
Copy the existing Next.js application structure from ProjectsManagerWebProduction as a starting point. This includes the app directory structure, components, utilities, configuration files, and styling. We will then modify this base to add CodeBoard functionality.

**Technical Requirements:**
- Copy from `/Users/elic/Documents/Claude/ProjectsManagerWebProduction`
- Preserve directory structure and file organization
- Update package.json with new project name
- Retain all shadcn/ui components and Tailwind configuration

**Files/Directories to Copy:**
```
From ProjectsManagerWebProduction/    To frontend/
├── app/                              ├── app/
├── components/                       ├── components/
├── lib/                              ├── lib/
├── prisma/                           ├── prisma/
├── public/                           ├── public/
├── package.json                      ├── package.json (modify name)
├── package-lock.json                 ├── package-lock.json
├── tsconfig.json                     ├── tsconfig.json
├── tailwind.config.ts                ├── tailwind.config.ts
├── postcss.config.js                 ├── postcss.config.js
├── next.config.js                    ├── next.config.js
├── components.json                   ├── components.json
└── .env.example                      └── .env.example
```

**Files to Modify After Copy:**
- `package.json`: Change name to "projects-manager-web-v2"
- `package.json`: Update description
- Remove any V1-specific code that won't be needed

**Acceptance Criteria:**
- [ ] All source files copied to frontend/ directory
- [ ] package.json updated with new project name
- [ ] No broken imports after copy
- [ ] Git history preserved (if using git mv)

**Sub-tasks:**
1. **Copy app/ directory** - All routes, layouts, and pages
2. **Copy components/ directory** - All UI components including shadcn/ui
3. **Copy lib/ directory** - Utilities, database client, hooks
4. **Copy config files** - package.json, tsconfig, tailwind, etc.
5. **Update package.json name** - Change to "projects-manager-web-v2"
6. **Verify imports** - Ensure all imports resolve correctly

---

### Task T1.2.2: Update Port Configuration

**ID:** T1.2.2
**Story:** S1.2
**Priority:** Critical
**Estimated Effort:** 20 minutes

**Description:**
Update all port references from the original port (3500) to the new port (3601). This includes the package.json dev script, any hardcoded URLs, and environment files.

**Technical Requirements:**
- Change dev server port to 3601
- Update any API URL references
- Create/update .ports.env file
- Ensure hot reload still works

**Files to Modify:**
```json
// package.json
{
  "scripts": {
    "dev": "next dev --port 3601",
    "start": "next start --port 3601"
  }
}
```

```env
# .ports.env
FRONTEND_PORT=3601
BACKEND_PORT=8401
CHROMA_PORT=8501
NEXT_PUBLIC_API_URL=http://localhost:8401
```

**Search and Replace:**
- Find: `localhost:3500` → Replace: `localhost:3601`
- Find: `port 3500` → Replace: `port 3601`
- Find: `:3500` in URLs → Replace: `:3601`

**Acceptance Criteria:**
- [ ] Dev server starts on port 3601
- [ ] No hardcoded references to old port remain
- [ ] .ports.env file created with all ports
- [ ] Environment variables properly loaded

**Sub-tasks:**
1. **Change port to 3601 in package.json** - Update dev and start scripts
2. **Update .ports.env** - Create file with all port configurations
3. **Search for hardcoded references** - Use grep to find any remaining old ports
4. **Update any hardcoded references** - Replace with environment variables where possible
5. **Test dev server startup** - Verify server runs on correct port

---

### Task T1.2.3: Update Environment Variables

**ID:** T1.2.3
**Story:** S1.2
**Priority:** High
**Estimated Effort:** 15 minutes

**Description:**
Create and configure the .env file with all necessary environment variables for the frontend application, including database URL, backend API URL, and any feature flags.

**Technical Requirements:**
- .env file in frontend/ directory
- .env.example with all variables (without secrets)
- Database URL pointing to local SQLite
- Backend URL for API proxy

**Environment Variables:**
```env
# .env

# Database
DATABASE_URL="file:./prisma/dev.db"

# Backend API
BACKEND_URL=http://localhost:8401
NEXT_PUBLIC_BACKEND_URL=http://localhost:8401

# ChromaDB
CHROMA_URL=http://localhost:8501

# Feature Flags
ENABLE_AI_FEATURES=true
ENABLE_RAG_SEARCH=true

# Development
NODE_ENV=development
```

```env
# .env.example (committed to git)

# Database
DATABASE_URL="file:./prisma/dev.db"

# Backend API
BACKEND_URL=http://localhost:8401
NEXT_PUBLIC_BACKEND_URL=http://localhost:8401

# ChromaDB
CHROMA_URL=http://localhost:8501

# Feature Flags
ENABLE_AI_FEATURES=true
ENABLE_RAG_SEARCH=true
```

**Acceptance Criteria:**
- [ ] .env file created with all required variables
- [ ] .env.example created for documentation
- [ ] .env added to .gitignore
- [ ] Application reads environment variables correctly

**Sub-tasks:**
1. **Create .env file** - Add all environment variables
2. **Set DATABASE_URL** - Point to local SQLite in prisma directory
3. **Set BACKEND_URL to 8401** - Configure API endpoint
4. **Create .env.example** - Template without sensitive values
5. **Update .gitignore** - Ensure .env is not committed

---

### Task T1.2.4: Install Dependencies and Verify

**ID:** T1.2.4
**Story:** S1.2
**Priority:** Critical
**Estimated Effort:** 30 minutes

**Description:**
Install all Node.js dependencies, generate Prisma client, and verify the application starts correctly on the new port. Fix any dependency conflicts or missing packages.

**Technical Requirements:**
- Run npm install successfully
- Generate Prisma client
- Application starts without errors
- Homepage loads in browser

**Commands to Execute:**
```bash
cd frontend/

# Install dependencies
npm install

# Generate Prisma client
npx prisma generate

# Initialize database (if needed)
npx prisma db push

# Start development server
npm run dev
```

**Expected Output:**
```
> projects-manager-web-v2@1.0.0 dev
> next dev --port 3601

  ▲ Next.js 14.x.x
  - Local:        http://localhost:3601
  - Environments: .env

 ✓ Ready in Xs
```

**Troubleshooting:**
- If port in use: `lsof -i :3601` and kill process
- If Prisma error: Delete node_modules/.prisma and regenerate
- If module not found: Delete node_modules and reinstall

**Acceptance Criteria:**
- [ ] npm install completes without errors
- [ ] Prisma client generated successfully
- [ ] Dev server starts on port 3601
- [ ] Homepage loads at http://localhost:3601
- [ ] No console errors in browser

**Sub-tasks:**
1. **Run npm install** - Install all dependencies from package-lock.json
2. **Generate Prisma client** - Run npx prisma generate
3. **Start dev server** - Run npm run dev
4. **Verify homepage loads** - Open http://localhost:3601 in browser
5. **Check for console errors** - Verify no JavaScript errors

---

## Story 1.3: Set Up Python FastAPI Backend

**ID:** S1.3
**Epic:** E1
**Priority:** High
**Description:** Initialize the FastAPI backend service with proper project structure, dependencies, CORS configuration, and health endpoints.

---

### Task T1.3.1: Create Backend Folder Structure

**ID:** T1.3.1
**Story:** S1.3
**Priority:** High
**Estimated Effort:** 30 minutes

**Description:**
Create the Python backend directory structure following best practices for FastAPI applications. This includes separate directories for API routes, models, services, and configuration.

**Technical Requirements:**
- Python 3.11+ compatible structure
- Modular organization for scalability
- Proper __init__.py files for imports
- Virtual environment setup

**Directory Structure:**
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration and settings
│   └── dependencies.py      # Dependency injection
├── api/
│   ├── __init__.py
│   ├── router.py            # Main API router
│   ├── issues.py            # Issue CRUD endpoints
│   ├── comments.py          # Comment endpoints
│   ├── projects.py          # Project endpoints
│   └── ai.py                # AI-related endpoints
├── models/
│   ├── __init__.py
│   ├── issue.py             # SQLAlchemy Issue model
│   ├── comment.py           # SQLAlchemy Comment model
│   ├── activity.py          # SQLAlchemy Activity model
│   └── schemas.py           # Pydantic schemas for API
├── services/
│   ├── __init__.py
│   ├── database.py          # Database connection and session
│   ├── issue_service.py     # Issue business logic
│   ├── rag.py               # RAG/ChromaDB service
│   ├── embedding.py         # Text embedding service
│   └── ai_engine.py         # AI task breakdown service
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures
│   ├── test_issues.py       # Issue endpoint tests
│   └── test_ai.py           # AI endpoint tests
├── requirements.txt         # Python dependencies
├── requirements-dev.txt     # Development dependencies
├── .env                     # Environment variables
├── .env.example             # Environment template
├── Dockerfile               # Container definition
└── README.md                # Backend documentation
```

**Acceptance Criteria:**
- [ ] All directories created with __init__.py files
- [ ] Virtual environment created and activated
- [ ] requirements.txt with initial dependencies
- [ ] README.md with setup instructions

**Sub-tasks:**
1. **Create app/ directory** - Main application module with __init__.py
2. **Create api/ directory** - API route modules
3. **Create models/ directory** - Database models and schemas
4. **Create services/ directory** - Business logic services
5. **Create tests/ directory** - Test modules
6. **Create requirements.txt** - List all Python dependencies
7. **Create virtual environment** - python -m venv venv
8. **Create .env file** - Environment configuration

---

### Task T1.3.2: Set Up FastAPI Application

**ID:** T1.3.2
**Story:** S1.3
**Priority:** High
**Estimated Effort:** 45 minutes

**Description:**
Create the main FastAPI application with CORS configuration, health endpoints, and basic routing structure. The application should be production-ready with proper error handling and logging.

**Technical Requirements:**
- FastAPI application instance
- CORS middleware for frontend access
- Health check endpoint
- Request logging middleware
- Exception handlers

**File: app/main.py**
```python
"""
ProjectsManagerWebV2 - FastAPI Backend
Main application entry point
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

from app.config import settings
from api.router import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info(f"Starting ProjectsManagerWebV2 Backend on port {settings.PORT}")
    logger.info(f"CORS origins: {settings.CORS_ORIGINS}")
    yield
    # Shutdown
    logger.info("Shutting down ProjectsManagerWebV2 Backend")

# Create FastAPI application
app = FastAPI(
    title="ProjectsManagerWebV2 API",
    description="Backend API for ProjectsManagerWebV2 with CodeBoard",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {
        "status": "healthy",
        "service": "projects-manager-web-v2-backend",
        "version": "1.0.0"
    }

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "message": "ProjectsManagerWebV2 API",
        "docs": "/docs",
        "health": "/health"
    }

# Include API router
app.include_router(api_router, prefix="/api")

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

**File: app/config.py**
```python
"""Application configuration using Pydantic settings."""

from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server
    PORT: int = 8401
    HOST: str = "0.0.0.0"
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3601",
        "http://127.0.0.1:3601",
    ]

    # Database
    DATABASE_URL: str = "sqlite:///./codeboard.db"

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8501

    # AI (for future use)
    ANTHROPIC_API_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**File: requirements.txt**
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
sqlalchemy==2.0.25
aiosqlite==0.19.0
chromadb==0.4.22
httpx==0.26.0
python-multipart==0.0.6
python-dotenv==1.0.0
```

**Acceptance Criteria:**
- [ ] FastAPI app starts without errors
- [ ] CORS configured for frontend origin
- [ ] GET /health returns 200 with status
- [ ] GET /docs shows Swagger UI
- [ ] Logging outputs to console

**Sub-tasks:**
1. **Create main.py with FastAPI app** - Application instance with lifespan
2. **Configure CORS middleware** - Allow frontend origin
3. **Create health endpoint** - GET /health with status response
4. **Create config.py** - Pydantic settings class
5. **Configure uvicorn** - Create run configuration
6. **Test startup** - Verify application runs on port 8401

---

### Task T1.3.3: Create Dockerfile for Backend

**ID:** T1.3.3
**Story:** S1.3
**Priority:** Medium
**Estimated Effort:** 30 minutes

**Description:**
Create a production-ready Dockerfile for the FastAPI backend using multi-stage builds for smaller image size and better security.

**Technical Requirements:**
- Multi-stage build
- Non-root user for security
- Health check in container
- Optimized layer caching
- Python 3.11 base image

**File: backend/Dockerfile**
```dockerfile
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8401

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8401/health')" || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8401"]
```

**File: backend/.dockerignore**
```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
venv/
.env
*.db
.git
.gitignore
Dockerfile
.dockerignore
tests/
*.md
.pytest_cache/
.coverage
htmlcov/
```

**Build and Run Commands:**
```bash
# Build image
docker build -t pmwv2-backend:latest ./backend

# Run container
docker run -d \
    --name pmwv2-backend \
    -p 8401:8401 \
    -e DATABASE_URL=sqlite:///./codeboard.db \
    pmwv2-backend:latest

# Check health
curl http://localhost:8401/health
```

**Acceptance Criteria:**
- [ ] Dockerfile builds successfully
- [ ] Image size under 200MB
- [ ] Container runs with non-root user
- [ ] Health check passes
- [ ] Application accessible on port 8401

**Sub-tasks:**
1. **Create multi-stage Dockerfile** - Builder and runtime stages
2. **Install dependencies in builder** - Optimize layer caching
3. **Set up non-root user** - Security best practice
4. **Set entrypoint** - uvicorn command with correct host/port
5. **Create .dockerignore** - Exclude unnecessary files
6. **Test build and run** - Verify container works

---

## Story 1.4: Set Up Docker & Scripts

**ID:** S1.4
**Epic:** E1
**Priority:** High
**Description:** Create Docker Compose configuration for all services and launch/stop scripts for easy development and deployment.

---

### Task T1.4.1: Create docker-compose.yml

**ID:** T1.4.1
**Story:** S1.4
**Priority:** High
**Estimated Effort:** 45 minutes

**Description:**
Create a Docker Compose configuration that orchestrates all three services (frontend, backend, ChromaDB) with proper networking, volumes, and environment configuration.

**Technical Requirements:**
- All three services defined
- Shared network for inter-service communication
- Volume mounts for development
- Environment variable configuration
- Health checks for dependencies

**File: docker-compose.yml**
```yaml
version: '3.8'

services:
  # Next.js Frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: pmwv2-frontend
    ports:
      - "3601:3601"
    environment:
      - NODE_ENV=development
      - BACKEND_URL=http://backend:8401
      - NEXT_PUBLIC_BACKEND_URL=http://localhost:8401
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - pmwv2-network
    restart: unless-stopped

  # FastAPI Backend
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: pmwv2-backend
    ports:
      - "8401:8401"
    environment:
      - DATABASE_URL=sqlite:///./data/codeboard.db
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8501
      - CORS_ORIGINS=["http://localhost:3601","http://frontend:3601"]
    volumes:
      - ./backend:/app
      - backend-data:/app/data
    depends_on:
      chromadb:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8401/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - pmwv2-network
    restart: unless-stopped

  # ChromaDB Vector Database
  chromadb:
    image: chromadb/chroma:latest
    container_name: pmwv2-chromadb
    ports:
      - "8501:8000"
    environment:
      - IS_PERSISTENT=TRUE
      - PERSIST_DIRECTORY=/chroma/chroma
      - ANONYMIZED_TELEMETRY=FALSE
    volumes:
      - chroma-data:/chroma/chroma
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - pmwv2-network
    restart: unless-stopped

networks:
  pmwv2-network:
    driver: bridge
    name: pmwv2-network

volumes:
  backend-data:
    name: pmwv2-backend-data
  chroma-data:
    name: pmwv2-chroma-data
```

**Docker Compose Commands:**
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Rebuild and start
docker-compose up -d --build

# Check service status
docker-compose ps
```

**Acceptance Criteria:**
- [ ] All three services start successfully
- [ ] Services can communicate over network
- [ ] Volumes persist data between restarts
- [ ] Health checks pass for all services
- [ ] Frontend can reach backend API

**Sub-tasks:**
1. **Define frontend service** - Next.js with hot reload volumes
2. **Define backend service** - FastAPI with health check
3. **Define ChromaDB service** - Vector database with persistence
4. **Configure network** - Shared bridge network
5. **Configure volumes** - Data persistence for db and chroma
6. **Add health checks** - Ensure services are ready before dependents start
7. **Test full stack** - docker-compose up and verify all services

---

### Task T1.4.2: Create launch.sh with Progress Dashboard

**ID:** T1.4.2
**Story:** S1.4
**Priority:** High
**Estimated Effort:** 1 hour

**Description:**
Create a comprehensive launch script that starts all services and displays a progress dashboard showing implementation status from the tracker database. This script should handle both Docker and local development modes.

**Technical Requirements:**
- Bash script with error handling
- Progress dashboard from tracker.db
- Support for Docker and local modes
- Port availability checking
- Colorized output

**File: launch.sh**
```bash
#!/bin/bash

#############################################
# ProjectsManagerWebV2 - Launch Script
# Starts all services and displays progress
#############################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_PORT=3601
BACKEND_PORT=8401
CHROMA_PORT=8501
TRACKER_DB="$SCRIPT_DIR/implementation_tracker.db"

# Functions
print_header() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║           ProjectsManagerWebV2 - Launch Script                   ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

display_progress() {
    if [ ! -f "$TRACKER_DB" ]; then
        echo -e "${YELLOW}No tracker database found. Skipping progress display.${NC}"
        return
    fi

    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║           Implementation Progress                                 ║"
    echo "╠══════════════════════════════════════════════════════════════════╣"

    # Get overall progress
    local total_tasks=$(sqlite3 "$TRACKER_DB" "SELECT COUNT(*) FROM tasks;")
    local done_tasks=$(sqlite3 "$TRACKER_DB" "SELECT COUNT(*) FROM tasks WHERE status='DONE';")
    local progress_pct=0
    if [ "$total_tasks" -gt 0 ]; then
        progress_pct=$((done_tasks * 100 / total_tasks))
    fi

    # Create progress bar
    local filled=$((progress_pct / 5))
    local empty=$((20 - filled))
    local bar=$(printf '█%.0s' $(seq 1 $filled 2>/dev/null) || echo "")
    local spaces=$(printf '░%.0s' $(seq 1 $empty 2>/dev/null) || echo "")

    printf "║  Overall Progress: ${bar}${spaces} %3d%% (%d/%d tasks)       ║\n" "$progress_pct" "$done_tasks" "$total_tasks"
    echo "╠══════════════════════════════════════════════════════════════════╣"
    echo "║  EPICS:                                                          ║"

    # Display each epic
    sqlite3 "$TRACKER_DB" "
        SELECT e.id, e.title, e.status,
               COUNT(CASE WHEN t.status = 'DONE' THEN 1 END) as done,
               COUNT(t.id) as total
        FROM epics e
        LEFT JOIN stories s ON s.epic_id = e.id
        LEFT JOIN tasks t ON t.story_id = s.id
        GROUP BY e.id
        ORDER BY e.id;
    " | while IFS='|' read -r id title status done total; do
        local icon="⬚ "
        local status_text="[BACKLOG]"
        local epic_pct=0

        if [ "$total" -gt 0 ]; then
            epic_pct=$((done * 100 / total))
        fi

        case "$status" in
            "DONE") icon="✅"; status_text="[DONE]" ;;
            "IN_PROGRESS") icon="🔄"; status_text="[IN PROGRESS] ${epic_pct}%" ;;
            "TODO") icon="⬚ "; status_text="[TODO]" ;;
        esac

        printf "║  %s %s: %-30s %s\n" "$icon" "$id" "$title" "$status_text"
    done

    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

start_local() {
    echo -e "${BLUE}Starting services in local mode...${NC}"

    # Check ports
    for port in $FRONTEND_PORT $BACKEND_PORT $CHROMA_PORT; do
        if check_port $port; then
            echo -e "${YELLOW}Warning: Port $port is already in use${NC}"
        fi
    done

    # Start backend
    echo -e "${GREEN}Starting backend on port $BACKEND_PORT...${NC}"
    cd "$SCRIPT_DIR/backend"
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload &
    BACKEND_PID=$!
    echo $BACKEND_PID > "$SCRIPT_DIR/.backend.pid"

    # Start frontend
    echo -e "${GREEN}Starting frontend on port $FRONTEND_PORT...${NC}"
    cd "$SCRIPT_DIR/frontend"
    npm run dev &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$SCRIPT_DIR/.frontend.pid"

    cd "$SCRIPT_DIR"

    # Wait for services to be ready
    echo -e "${YELLOW}Waiting for services to start...${NC}"
    sleep 5

    echo -e "${GREEN}Services started!${NC}"
    echo -e "  Frontend: http://localhost:$FRONTEND_PORT"
    echo -e "  Backend:  http://localhost:$BACKEND_PORT"
    echo -e "  Docs:     http://localhost:$BACKEND_PORT/docs"
}

start_docker() {
    echo -e "${BLUE}Starting services with Docker Compose...${NC}"
    docker-compose up -d

    echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
    sleep 10

    echo -e "${GREEN}Services started!${NC}"
    docker-compose ps
}

# Main
print_header
display_progress

MODE=${1:-local}

case "$MODE" in
    local)
        start_local
        ;;
    docker)
        start_docker
        ;;
    *)
        echo "Usage: $0 [local|docker]"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✓ ProjectsManagerWebV2 is running!${NC}"
```

**Acceptance Criteria:**
- [ ] Script starts all services successfully
- [ ] Progress dashboard displays correctly
- [ ] Port conflicts detected and reported
- [ ] Both local and Docker modes work
- [ ] PID files created for stop script

**Sub-tasks:**
1. **Create bash script structure** - Header, functions, main logic
2. **Add port checking** - Detect conflicts before starting
3. **Query tracker.db for progress** - SQLite queries for epic/task status
4. **Display ASCII progress dashboard** - Formatted output with colors
5. **Start all services** - Backend and frontend processes
6. **Save PIDs for stop script** - Write to .pid files
7. **Add Docker mode** - docker-compose up option

---

### Task T1.4.3: Create stop.sh

**ID:** T1.4.3
**Story:** S1.4
**Priority:** Medium
**Estimated Effort:** 20 minutes

**Description:**
Create a stop script that gracefully shuts down all services started by launch.sh, cleaning up PID files and Docker containers.

**File: stop.sh**
```bash
#!/bin/bash

#############################################
# ProjectsManagerWebV2 - Stop Script
# Stops all running services
#############################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${YELLOW}Stopping ProjectsManagerWebV2 services...${NC}"

# Stop local processes
stop_local() {
    # Stop backend
    if [ -f "$SCRIPT_DIR/.backend.pid" ]; then
        PID=$(cat "$SCRIPT_DIR/.backend.pid")
        if kill -0 $PID 2>/dev/null; then
            echo -e "Stopping backend (PID: $PID)..."
            kill $PID
            rm "$SCRIPT_DIR/.backend.pid"
            echo -e "${GREEN}Backend stopped${NC}"
        else
            rm "$SCRIPT_DIR/.backend.pid"
        fi
    fi

    # Stop frontend
    if [ -f "$SCRIPT_DIR/.frontend.pid" ]; then
        PID=$(cat "$SCRIPT_DIR/.frontend.pid")
        if kill -0 $PID 2>/dev/null; then
            echo -e "Stopping frontend (PID: $PID)..."
            kill $PID
            rm "$SCRIPT_DIR/.frontend.pid"
            echo -e "${GREEN}Frontend stopped${NC}"
        else
            rm "$SCRIPT_DIR/.frontend.pid"
        fi
    fi

    # Kill any remaining processes on our ports
    for port in 3601 8401; do
        PID=$(lsof -ti:$port 2>/dev/null)
        if [ -n "$PID" ]; then
            echo -e "Killing process on port $port (PID: $PID)..."
            kill $PID 2>/dev/null
        fi
    done
}

# Stop Docker containers
stop_docker() {
    if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
        echo -e "Stopping Docker containers..."
        cd "$SCRIPT_DIR"
        docker-compose down
        echo -e "${GREEN}Docker containers stopped${NC}"
    fi
}

# Detect mode and stop
if docker-compose ps 2>/dev/null | grep -q "pmwv2"; then
    stop_docker
fi

stop_local

echo -e "${GREEN}✓ All services stopped${NC}"
```

**Acceptance Criteria:**
- [ ] Script stops all running services
- [ ] PID files cleaned up
- [ ] Docker containers stopped if running
- [ ] Ports freed for next launch
- [ ] No orphan processes remain

**Sub-tasks:**
1. **Stop processes from PID files** - Read and kill stored PIDs
2. **Clean up PID files** - Remove .pid files after stopping
3. **Stop Docker containers** - docker-compose down
4. **Kill processes on ports** - Fallback cleanup
5. **Display status** - Show what was stopped

---

### Task T1.4.4: Test Full Stack Startup

**ID:** T1.4.4
**Story:** S1.4
**Priority:** Critical
**Estimated Effort:** 30 minutes

**Description:**
Comprehensive testing of the full stack startup to ensure all services work together correctly. This includes health checks, inter-service communication, and basic functionality verification.

**Test Plan:**

1. **Clean Start Test:**
```bash
# Ensure nothing is running
./stop.sh

# Start fresh
./launch.sh local

# Verify processes
ps aux | grep -E "uvicorn|next"
```

2. **Health Check Tests:**
```bash
# Frontend health
curl -s http://localhost:3601/api/health | jq

# Backend health
curl -s http://localhost:8401/health | jq

# Expected responses
# Frontend: {"status":"ok"}
# Backend: {"status":"healthy","service":"projects-manager-web-v2-backend","version":"1.0.0"}
```

3. **API Documentation Test:**
```bash
# Open Swagger UI
open http://localhost:8401/docs

# Verify API endpoints are listed
```

4. **Frontend-Backend Communication Test:**
```bash
# Test CORS by making request from frontend
# In browser console at http://localhost:3601:
fetch('http://localhost:8401/health')
  .then(r => r.json())
  .then(console.log)
```

5. **Docker Mode Test:**
```bash
./stop.sh
./launch.sh docker
docker-compose ps
curl -s http://localhost:8401/health
./stop.sh
```

**Acceptance Criteria:**
- [ ] launch.sh completes without errors
- [ ] All health endpoints return 200
- [ ] Swagger UI loads at /docs
- [ ] Frontend can fetch from backend (CORS works)
- [ ] stop.sh cleanly stops all services
- [ ] Docker mode works end-to-end

**Sub-tasks:**
1. **Run launch.sh** - Execute script and verify output
2. **Verify all services are running** - Check processes and ports
3. **Test health endpoints** - curl each service
4. **Check inter-service communication** - Frontend to backend
5. **Test stop.sh** - Verify clean shutdown
6. **Document any issues** - Note problems and fixes

---

# EPIC 2: Database & API Foundation

**ID:** E2
**Priority:** High
**Status:** BACKLOG
**Description:** Establish the database schema for CodeBoard issue tracking and implement the FastAPI CRUD endpoints. This includes the Issue, Comment, Activity, and related models, along with all necessary API routes for managing issues.

**Acceptance Criteria:**
- All database models created and migrated
- Full CRUD API for issues implemented
- Issue key sequence generation working
- API proxy routes in Next.js functional

---

## Story 2.1: Extend Prisma Schema

**ID:** S2.1
**Epic:** E2
**Priority:** High
**Description:** Add all CodeBoard-related models to the Prisma schema including Issue, Comment, Activity, IssueLink, and IssueSequence.

---

### Task T2.1.1: Add Issue Model to schema.prisma

**ID:** T2.1.1
**Story:** S2.1
**Priority:** Critical
**Estimated Effort:** 45 minutes

**Description:**
Define the Issue model in Prisma schema with all necessary fields for a Jira-like issue tracking system. The Issue model is the core entity of CodeBoard and must support various issue types (Epic, Story, Task, Subtask, Bug), statuses, priorities, and relationships.

**Technical Requirements:**
- Unique issue key (e.g., "PM-123")
- Support for issue hierarchy (parent/child relationships)
- Integration with existing Project model
- Timestamps for tracking
- Soft delete capability

**Prisma Schema Addition:**
```prisma
// Add to frontend/prisma/schema.prisma

// Enums for Issue
enum IssueType {
  EPIC
  STORY
  TASK
  SUBTASK
  BUG
}

enum IssueStatus {
  BACKLOG
  TODO
  IN_PROGRESS
  IN_REVIEW
  DONE
  CANCELLED
}

enum Priority {
  LOWEST
  LOW
  MEDIUM
  HIGH
  HIGHEST
}

enum Assignee {
  AI
  HUMAN
  UNASSIGNED
}

// Issue Model
model Issue {
  id          String      @id @default(cuid())
  key         String      @unique  // e.g., "PM-123"
  title       String
  description String?     @db.Text
  type        IssueType   @default(TASK)
  status      IssueStatus @default(BACKLOG)
  priority    Priority    @default(MEDIUM)
  assignee    Assignee    @default(UNASSIGNED)

  // Relationships
  projectId   String
  project     Project     @relation(fields: [projectId], references: [id], onDelete: Cascade)

  parentId    String?
  parent      Issue?      @relation("IssueHierarchy", fields: [parentId], references: [id])
  children    Issue[]     @relation("IssueHierarchy")

  comments    Comment[]
  activities  Activity[]

  // Links to other issues
  linkedFrom  IssueLink[] @relation("LinkedFrom")
  linkedTo    IssueLink[] @relation("LinkedTo")

  // Metadata
  storyPoints Int?
  estimate    Int?        // in minutes
  timeSpent   Int?        // in minutes
  labels      String?     // comma-separated labels

  // Timestamps
  createdAt   DateTime    @default(now())
  updatedAt   DateTime    @updatedAt
  dueDate     DateTime?
  completedAt DateTime?

  // Soft delete
  deletedAt   DateTime?

  @@index([projectId])
  @@index([parentId])
  @@index([status])
  @@index([type])
  @@index([key])
}
```

**Field Descriptions:**
- `id`: Unique identifier (CUID)
- `key`: Human-readable issue key like "PM-123"
- `title`: Issue title/summary (required)
- `description`: Detailed description (markdown supported)
- `type`: EPIC, STORY, TASK, SUBTASK, or BUG
- `status`: Current workflow status
- `priority`: Importance level
- `assignee`: AI, HUMAN, or UNASSIGNED
- `projectId`: Foreign key to Project
- `parentId`: Self-referential for hierarchy (Epic → Story → Task → Subtask)
- `storyPoints`: Agile story points estimation
- `estimate`: Time estimate in minutes
- `timeSpent`: Actual time spent in minutes
- `labels`: Comma-separated labels for filtering
- `dueDate`: Optional deadline
- `completedAt`: When issue was marked done
- `deletedAt`: Soft delete timestamp (null = not deleted)

**Acceptance Criteria:**
- [ ] Issue model defined in schema.prisma
- [ ] All enum types defined
- [ ] Self-referential relationship for hierarchy
- [ ] Indexes for common query patterns
- [ ] Schema validates without errors

**Sub-tasks:**
1. **Define IssueType enum** - EPIC, STORY, TASK, SUBTASK, BUG
2. **Define IssueStatus enum** - BACKLOG through CANCELLED
3. **Define Priority enum** - LOWEST through HIGHEST
4. **Define Assignee enum** - AI, HUMAN, UNASSIGNED
5. **Create Issue model** - All fields with proper types
6. **Add relations** - Project, parent/children, comments, activities
7. **Add indexes** - projectId, parentId, status, type, key
8. **Validate schema** - Run prisma validate

---

### Task T2.1.2: Add Comment Model

**ID:** T2.1.2
**Story:** S2.1
**Priority:** High
**Estimated Effort:** 20 minutes

**Description:**
Create the Comment model for issue discussions. Comments support markdown content and can be marked as AI-generated.

**Prisma Schema Addition:**
```prisma
model Comment {
  id        String   @id @default(cuid())
  content   String   @db.Text

  // Author info
  author    String   @default("user")  // "user" or "ai"
  authorId  String?  // Future: link to User model

  // Relationship
  issueId   String
  issue     Issue    @relation(fields: [issueId], references: [id], onDelete: Cascade)

  // Timestamps
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
  editedAt  DateTime?

  @@index([issueId])
  @@index([createdAt])
}
```

**Acceptance Criteria:**
- [ ] Comment model defined
- [ ] Linked to Issue with cascade delete
- [ ] Supports markdown content
- [ ] Tracks edit history

**Sub-tasks:**
1. **Define Comment model** - All fields
2. **Link to Issue** - Foreign key with cascade
3. **Add author tracking** - Distinguish user vs AI comments

---

### Task T2.1.3: Add Activity Model

**ID:** T2.1.3
**Story:** S2.1
**Priority:** High
**Estimated Effort:** 20 minutes

**Description:**
Create the Activity model to track all changes made to issues. This provides a complete audit trail and enables the activity log feature.

**Prisma Schema Addition:**
```prisma
enum ActivityType {
  CREATED
  STATUS_CHANGED
  PRIORITY_CHANGED
  ASSIGNEE_CHANGED
  DESCRIPTION_UPDATED
  TITLE_UPDATED
  COMMENT_ADDED
  LINKED
  UNLINKED
  PARENT_CHANGED
  LABELS_CHANGED
  ESTIMATE_CHANGED
  DUE_DATE_CHANGED
}

model Activity {
  id        String       @id @default(cuid())
  type      ActivityType

  // What changed
  field     String?      // Which field changed
  oldValue  String?      // Previous value
  newValue  String?      // New value

  // Who made the change
  actor     String       @default("user")  // "user" or "ai" or "system"

  // Relationship
  issueId   String
  issue     Issue        @relation(fields: [issueId], references: [id], onDelete: Cascade)

  // Timestamp
  createdAt DateTime     @default(now())

  @@index([issueId])
  @@index([createdAt])
  @@index([type])
}
```

**Acceptance Criteria:**
- [ ] Activity model defined
- [ ] All activity types enumerated
- [ ] Stores old and new values
- [ ] Tracks actor (user/AI/system)

**Sub-tasks:**
1. **Define ActivityType enum** - All possible activity types
2. **Create Activity model** - Track what changed and by whom
3. **Link to Issue** - Foreign key with cascade delete

---

### Task T2.1.4: Add IssueLink Model

**ID:** T2.1.4
**Story:** S2.1
**Priority:** Medium
**Estimated Effort:** 20 minutes

**Description:**
Create the IssueLink model for relating issues to each other (blocks, is blocked by, relates to, duplicates, etc.).

**Prisma Schema Addition:**
```prisma
enum LinkType {
  BLOCKS
  IS_BLOCKED_BY
  RELATES_TO
  DUPLICATES
  IS_DUPLICATED_BY
  CLONES
  IS_CLONED_BY
}

model IssueLink {
  id           String   @id @default(cuid())
  type         LinkType

  // The issue that has this link
  fromIssueId  String
  fromIssue    Issue    @relation("LinkedFrom", fields: [fromIssueId], references: [id], onDelete: Cascade)

  // The issue being linked to
  toIssueId    String
  toIssue      Issue    @relation("LinkedTo", fields: [toIssueId], references: [id], onDelete: Cascade)

  createdAt    DateTime @default(now())

  @@unique([fromIssueId, toIssueId, type])
  @@index([fromIssueId])
  @@index([toIssueId])
}
```

**Acceptance Criteria:**
- [ ] IssueLink model defined
- [ ] All link types enumerated
- [ ] Bidirectional relationship support
- [ ] Unique constraint prevents duplicate links

**Sub-tasks:**
1. **Define LinkType enum** - BLOCKS, RELATES_TO, DUPLICATES, etc.
2. **Create IssueLink model** - From/To issue references
3. **Add unique constraint** - Prevent duplicate links of same type

---

### Task T2.1.5: Add IssueSequence Model

**ID:** T2.1.5
**Story:** S2.1
**Priority:** High
**Estimated Effort:** 15 minutes

**Description:**
Create the IssueSequence model to manage auto-incrementing issue keys per project. Each project has its own sequence (e.g., "PM" project generates PM-1, PM-2, PM-3...).

**Prisma Schema Addition:**
```prisma
model IssueSequence {
  id         String  @id @default(cuid())
  projectId  String  @unique
  project    Project @relation(fields: [projectId], references: [id], onDelete: Cascade)
  prefix     String  // e.g., "PM"
  nextNumber Int     @default(1)

  @@index([projectId])
}
```

**Usage:**
```typescript
// Get next issue key for a project
async function getNextIssueKey(projectId: string): Promise<string> {
  const sequence = await prisma.issueSequence.update({
    where: { projectId },
    data: { nextNumber: { increment: 1 } },
  });
  return `${sequence.prefix}-${sequence.nextNumber - 1}`;
}
```

**Acceptance Criteria:**
- [ ] IssueSequence model defined
- [ ] One sequence per project
- [ ] Atomic increment operation possible

**Sub-tasks:**
1. **Create IssueSequence model** - projectId, prefix, nextNumber
2. **Add unique constraint on projectId** - One sequence per project
3. **Update Project model** - Add relation to IssueSequence

---

### Task T2.1.6: Add Enums (IssueType, IssueStatus, Priority)

**ID:** T2.1.6
**Story:** S2.1
**Priority:** High
**Estimated Effort:** 10 minutes

**Description:**
Ensure all enum types are properly defined and documented. This task consolidates all enum definitions.

**All Enums:**
```prisma
// Issue Types - hierarchical structure
enum IssueType {
  EPIC      // Largest work item, contains Stories
  STORY     // User-facing feature, contains Tasks
  TASK      // Unit of work
  SUBTASK   // Breakdown of Task
  BUG       // Defect to fix
}

// Issue Status - workflow states
enum IssueStatus {
  BACKLOG     // Not yet prioritized
  TODO        // Ready to work on
  IN_PROGRESS // Currently being worked on
  IN_REVIEW   // Code review or testing
  DONE        // Completed
  CANCELLED   // Won't be done
}

// Priority levels
enum Priority {
  LOWEST   // Nice to have
  LOW      // Low impact
  MEDIUM   // Normal priority
  HIGH     // Important
  HIGHEST  // Critical/blocking
}

// Assignee types
enum Assignee {
  AI         // Assigned to AI for implementation
  HUMAN      // Assigned to human developer
  UNASSIGNED // Not yet assigned
}

// Activity types for audit log
enum ActivityType {
  CREATED
  STATUS_CHANGED
  PRIORITY_CHANGED
  ASSIGNEE_CHANGED
  DESCRIPTION_UPDATED
  TITLE_UPDATED
  COMMENT_ADDED
  LINKED
  UNLINKED
  PARENT_CHANGED
  LABELS_CHANGED
  ESTIMATE_CHANGED
  DUE_DATE_CHANGED
}

// Link types for issue relationships
enum LinkType {
  BLOCKS          // This issue blocks another
  IS_BLOCKED_BY   // This issue is blocked by another
  RELATES_TO      // Related issues
  DUPLICATES      // This is a duplicate of another
  IS_DUPLICATED_BY
  CLONES          // This was cloned from another
  IS_CLONED_BY
}
```

**Acceptance Criteria:**
- [ ] All enums defined in schema
- [ ] Each enum value documented
- [ ] Enums used consistently in models

**Sub-tasks:**
1. **Define all enum values** - Ensure comprehensive list
2. **Add documentation comments** - Explain each value's purpose

---

### Task T2.1.7: Run prisma db push and Verify

**ID:** T2.1.7
**Story:** S2.1
**Priority:** Critical
**Estimated Effort:** 15 minutes

**Description:**
Apply the schema changes to the database and verify all models are created correctly. Test with Prisma Studio to inspect the database structure.

**Commands:**
```bash
cd frontend/

# Validate schema
npx prisma validate

# Format schema
npx prisma format

# Push to database (creates tables)
npx prisma db push

# Generate Prisma client
npx prisma generate

# Open Prisma Studio to inspect
npx prisma studio
```

**Verification Queries:**
```typescript
// Test in a script or REPL
import { PrismaClient } from '@prisma/client';
const prisma = new PrismaClient();

// Verify Issue model
const issues = await prisma.issue.findMany();
console.log('Issues:', issues.length);

// Verify enum types work
const testIssue = await prisma.issue.create({
  data: {
    key: 'TEST-1',
    title: 'Test Issue',
    type: 'TASK',
    status: 'BACKLOG',
    priority: 'MEDIUM',
    projectId: 'some-project-id',
  },
});
console.log('Created:', testIssue);

// Clean up
await prisma.issue.delete({ where: { id: testIssue.id } });
```

**Acceptance Criteria:**
- [ ] Schema validates without errors
- [ ] db push completes successfully
- [ ] Prisma client generates without errors
- [ ] Prisma Studio shows all tables
- [ ] Test create/read operations work

**Sub-tasks:**
1. **Run prisma validate** - Check schema syntax
2. **Run prisma format** - Consistent formatting
3. **Apply schema with db push** - Create database tables
4. **Generate Prisma client** - TypeScript types
5. **Check migrations** - Verify migration files created
6. **Test with Prisma Studio** - Inspect tables and relationships
7. **Run test queries** - Verify CRUD operations

---

[Content continues with Epic 2 Stories 2.2-2.5 and Epics 3-7...]

---

# Task Summary

| Epic | Stories | Tasks | Estimated Hours |
|------|---------|-------|-----------------|
| E1: Setup | 4 | 14 | 8-10 |
| E2: Database & API | 5 | 16 | 12-15 |
| E3: CodeBoard UI | 6 | 22 | 20-25 |
| E4: RAG Integration | 3 | 8 | 8-10 |
| E5: AI Engine | 4 | 10 | 10-12 |
| E6: Git Integration | 2 | 4 | 4-5 |
| E7: Polish | 3 | 6 | 6-8 |
| **TOTAL** | **27** | **80** | **68-85** |

---

# Next: Continue with remaining Epics...

This file continues in `IMPLEMENTATION_PLAN_DETAILED_PART2.md` with:
- Epic 2: Stories 2.2-2.5 (FastAPI models, CRUD API, Sequences, Proxy routes)
- Epic 3: CodeBoard UI (Kanban, List, Filters, Issue Details)
- Epic 4: RAG Integration
- Epic 5: AI Engine
- Epic 6: Git Integration
- Epic 7: Polish & Testing
