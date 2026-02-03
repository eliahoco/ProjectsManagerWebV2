# CB-702: Database Deployment Process Review

**Task:** Review database deployment process
**Story:** CB-692: As a user, I want to...
**Date:** 2026-01-27

---

## Executive Summary

This document provides a comprehensive review of the database deployment process for ProjectsManagerWebV2. It identifies current approaches, gaps, and provides actionable recommendations for production-ready database deployments.

**Overall Status: NEEDS IMPROVEMENT**

| Area | Current State | Production Ready |
|------|---------------|------------------|
| Database Technology | SQLite | No (single-user) |
| Schema Initialization | Implicit | No |
| Migrations | None | No |
| Backups | None | No |
| Health Checks | Partial | No |
| CI/CD Integration | Configured | Yes |

---

## 1. Current Database Architecture

### 1.1 Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Database | SQLite | 3.x (file-based) |
| Frontend ORM | Prisma | 6.0.0 |
| Backend ORM | SQLAlchemy | 2.0.36 (async) |
| Async Driver | aiosqlite | 0.20.0 |
| Vector Database | ChromaDB | latest |

### 1.2 Database File Locations

| Environment | Location | Notes |
|-------------|----------|-------|
| Development | `frontend/prisma/dev.db` | Shared by frontend and backend |
| Docker (Backend) | `/app/data/codeboard.db` | Volume-mounted |
| Docker (Frontend) | `/app/prisma/` | Prisma client files |
| CI/CD Tests | `./test_codeboard.db` | Ephemeral per test run |

### 1.3 Dual ORM Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     SQLite Database                         │
│                   (Single .db file)                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Prisma    │   │ SQLAlchemy  │   │  ChromaDB   │
│  (Frontend) │   │  (Backend)  │   │  (Vectors)  │
├─────────────┤   ├─────────────┤   ├─────────────┤
│ Project     │   │ Issue       │   │ Embeddings  │
│ Port        │   │ Comment     │   │ RAG data    │
│ Session     │   │ Activity    │   │             │
│ Setting     │   │ QATask      │   │             │
│             │   │ GitSync     │   │             │
└─────────────┘   └─────────────┘   └─────────────┘
```

---

## 2. Current Deployment Process

### 2.1 Development Environment

**Setup Process:**
```bash
# 1. Frontend - Initialize Prisma
cd frontend
npm install
npm run db:push     # Apply schema to SQLite
npm run db:seed     # Optional: seed test data

# 2. Backend - No explicit initialization
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# Tables created implicitly on first query
```

**Gap:** No explicit database initialization in backend startup.

### 2.2 Docker Deployment

**docker-compose.yml Overview:**
```yaml
services:
  frontend:
    volumes:
      - frontend_data:/app/prisma    # Prisma client

  backend:
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./data/codeboard.db
    volumes:
      - backend_data:/app/data       # SQLite database

  chromadb:
    volumes:
      - chroma_data:/chroma/chroma   # Vector store
```

**Gap:** No initialization container, no migration runner.

### 2.3 CI/CD Pipeline

**Current GitHub Actions Workflow:**
```yaml
# .github/workflows/test.yml
backend:
  env:
    DATABASE_URL: sqlite+aiosqlite:///./test_codeboard.db
  steps:
    - Run pytest    # Tables created implicitly
```

**Status:** CI/CD is configured and functional.

---

## 3. Database Initialization Analysis

### 3.1 Current Initialization Flow

```
Application Start
       │
       ▼
FastAPI Lifespan (main.py)
       │
       │ ❌ init_db() NOT called
       ▼
First Database Query
       │
       ▼
SQLAlchemy creates tables
(if they don't exist)
```

**Problem:** The `init_db()` function exists in `backend/models/database.py` but is **never called** in the application lifecycle:

```python
# backend/models/database.py
async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# backend/app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting ProjectsManagerWebV2 Backend...")
    yield
    # Shutdown - NO init_db() call
```

### 3.2 Risks of Implicit Initialization

| Risk | Severity | Impact |
|------|----------|--------|
| Race conditions | High | Multiple requests may try to create tables simultaneously |
| Silent failures | High | Database unavailable won't be detected until first query |
| Missing tables | Medium | New models may not be created if no queries hit them |
| No validation | Medium | Schema mismatches go undetected at startup |

---

## 4. Migration Strategy Analysis

### 4.1 Current State: No Migrations

| Framework | Migration Tool | Status |
|-----------|---------------|--------|
| Prisma | `prisma migrate` | Available but not used |
| SQLAlchemy | Alembic | Not installed |

**Current Approach:** Schema-first with direct pushes
- Prisma: `npm run db:push` applies schema directly
- SQLAlchemy: `create_all()` creates tables based on models

### 4.2 Problems Without Migrations

1. **No Rollback Capability**: Cannot revert schema changes
2. **No History**: Schema changes not tracked in version control
3. **Team Coordination**: Multiple developers may have conflicting changes
4. **Production Deployments**: No safe path for schema updates
5. **Data Preservation**: Schema pushes may drop data

### 4.3 Recommended Migration Strategy

**Option A: Alembic (Recommended)**
```
backend/
├── alembic/
│   ├── versions/          # Migration files
│   │   ├── 001_initial.py
│   │   └── 002_add_qa_tables.py
│   ├── env.py
│   └── script.py.mako
├── alembic.ini
```

**Benefits:**
- SQLAlchemy native integration
- Autogenerate migrations from model changes
- Reversible migrations
- Migration history tracking

**Option B: Keep Prisma as Source of Truth**
```
frontend/
├── prisma/
│   └── migrations/       # Export migrations here
│       ├── 20260127_001/
│       └── 20260127_002/
```

**Benefits:**
- Single source of truth
- Visual schema editor (Prisma Studio)
- Already familiar to frontend developers

---

## 5. Backup and Recovery

### 5.1 Current State: No Automated Backups

| Environment | Backup Strategy | Status |
|-------------|----------------|--------|
| Development | None | Manual only |
| Docker | Volume persistence | No backup |
| Production | N/A | Not deployed |

### 5.2 SQLite Backup Approaches

**Simple Copy (Development):**
```bash
# Safe when no writes are occurring
cp frontend/prisma/dev.db backup/dev.db.$(date +%Y%m%d)
```

**Online Backup (Production-safe):**
```bash
# Uses SQLite backup API, safe during writes
sqlite3 dev.db ".backup backup.db"
```

**Automated Docker Backup:**
```yaml
# docker-compose.yml addition
services:
  backup:
    image: alpine
    volumes:
      - backend_data:/data:ro
      - ./backups:/backups
    command: |
      sh -c 'while true; do
        cp /data/codeboard.db /backups/codeboard.$(date +%Y%m%d_%H%M%S).db
        sleep 86400
      done'
```

### 5.3 Recovery Time Objectives

| Scenario | Current RTO | Target RTO |
|----------|-------------|------------|
| File corruption | Unknown | < 1 hour |
| Accidental deletion | Unknown | < 15 minutes |
| Schema rollback | Not possible | < 30 minutes |

---

## 6. Health Check Analysis

### 6.1 Current Health Checks

**FastAPI Endpoint:**
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy"}  # No database check!
```

**Docker Healthcheck:**
```dockerfile
HEALTHCHECK CMD python -c "import httpx; httpx.get('http://localhost:8401/health')"
```

**Gap:** Health check does not verify database connectivity.

### 6.2 Recommended Health Check

```python
@app.get("/health")
async def health_check():
    """Health check with database connectivity verification"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e)
            }
        )
```

---

## 7. Production Deployment Recommendations

### 7.1 Immediate Actions (Before Production)

#### 7.1.1 Add Explicit Database Initialization

**File:** `backend/app/main.py`
```python
from models.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()
    logger.info(f"Starting on port {settings.PORT}")
    yield
    # Shutdown
    logger.info("Shutting down...")
```

#### 7.1.2 Add Database Health Check

**File:** `backend/app/main.py`
```python
from sqlalchemy import text
from models.database import AsyncSessionLocal

@app.get("/health")
async def health_check():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )
```

#### 7.1.3 Add Startup Validation Script

**File:** `backend/scripts/validate_db.py`
```python
#!/usr/bin/env python
"""Validate database schema on deployment"""
import asyncio
from models.database import engine, Base
from sqlalchemy import inspect

async def validate_schema():
    async with engine.connect() as conn:
        def check_tables(sync_conn):
            inspector = inspect(sync_conn)
            existing = set(inspector.get_table_names())
            expected = set(Base.metadata.tables.keys())
            missing = expected - existing
            if missing:
                raise RuntimeError(f"Missing tables: {missing}")
            print(f"Schema validated: {len(existing)} tables")

        await conn.run_sync(check_tables)

if __name__ == "__main__":
    asyncio.run(validate_schema())
```

### 7.2 Short-term Actions (First Production Release)

#### 7.2.1 Install and Configure Alembic

```bash
cd backend
pip install alembic
alembic init alembic
```

**Configure `alembic.ini`:**
```ini
sqlalchemy.url = sqlite+aiosqlite:///./data/codeboard.db
```

**Generate Initial Migration:**
```bash
alembic revision --autogenerate -m "Initial schema"
```

#### 7.2.2 Add Backup Script to Docker Compose

```yaml
# docker-compose.yml
services:
  backup:
    image: alpine
    volumes:
      - backend_data:/data:ro
      - ./backups:/backups
    entrypoint: /bin/sh
    command: -c "while true; do sqlite3 /data/codeboard.db '.backup /backups/codeboard-$$(date +%Y%m%d-%H%M%S).db'; sleep 3600; done"
    restart: unless-stopped
```

### 7.3 Medium-term Actions (Operational Stability)

#### 7.3.1 Consider PostgreSQL Migration

| Factor | SQLite | PostgreSQL |
|--------|--------|------------|
| Concurrent writes | Limited (file locks) | Excellent |
| Connection pooling | N/A | Supported |
| Scalability | Single file | Multi-server |
| Backups | File copy | pg_dump, WAL |
| Monitoring | Limited | Extensive |

**When to Migrate:**
- More than ~10 concurrent users
- Need for read replicas
- Require point-in-time recovery
- Need advanced query features

#### 7.3.2 Implement Connection Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def get_db_with_retry():
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
        return session
```

---

## 8. Deployment Checklist

### 8.1 Pre-deployment Checklist

- [ ] Database file location configured correctly
- [ ] Environment variables set (DATABASE_URL)
- [ ] Volume mounts configured for persistence
- [ ] Health check includes database connectivity
- [ ] Backup strategy documented
- [ ] Rollback procedure documented

### 8.2 Deployment Checklist

- [ ] Run database schema validation
- [ ] Verify all tables exist
- [ ] Check foreign key constraints
- [ ] Verify indexes are created
- [ ] Test health endpoint returns healthy
- [ ] Confirm backup job is running

### 8.3 Post-deployment Checklist

- [ ] Monitor health endpoint
- [ ] Check application logs for database errors
- [ ] Verify first backup completed
- [ ] Test a sample CRUD operation
- [ ] Document deployment timestamp

---

## 9. Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Data loss (no backup) | Critical | Medium | Implement automated backups |
| Schema drift | High | High | Implement Alembic migrations |
| Silent init failure | High | Medium | Add explicit init_db() call |
| Concurrent write conflicts | Medium | Low | Document SQLite limitations |
| Health check false positive | Medium | High | Add database connectivity check |
| Rollback impossible | High | Medium | Implement migration versioning |

---

## 10. Implementation Priority Matrix

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| **P0** | Add `init_db()` to lifespan | 5 min | High |
| **P0** | Add database health check | 15 min | High |
| **P1** | Add backup script | 30 min | Critical |
| **P1** | Create schema validation script | 30 min | Medium |
| **P2** | Install and configure Alembic | 2 hrs | High |
| **P2** | Create deployment documentation | 1 hr | Medium |
| **P3** | Evaluate PostgreSQL migration | 4 hrs | High |
| **P3** | Implement connection retry logic | 1 hr | Low |

---

## 11. Conclusion

The current database deployment process has significant gaps for production readiness:

**Critical Issues:**
1. No explicit database initialization at startup
2. No migration tracking (Alembic not installed)
3. No automated backup strategy
4. Health check does not verify database connectivity

**Recommendations:**
1. **Immediate:** Add `init_db()` call and database health check
2. **Short-term:** Implement Alembic migrations and backup scripts
3. **Medium-term:** Evaluate PostgreSQL for production scaling

The SQLite database is appropriate for development and single-user deployments but will require migration to PostgreSQL for multi-user production environments.

---

## Appendix A: Key File Locations

| Purpose | File Path |
|---------|-----------|
| Database Config | `backend/app/config.py` |
| Database Connection | `backend/models/database.py` |
| Application Entry | `backend/app/main.py` |
| Docker Compose | `docker-compose.yml` |
| Backend Dockerfile | `backend/Dockerfile` |
| CI/CD Workflow | `.github/workflows/test.yml` |
| Prisma Schema | `frontend/prisma/schema.prisma` |
| SQLAlchemy Models | `backend/models/*.py` |

## Appendix B: Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | SQLite connection string | `sqlite+aiosqlite:///./codeboard.db` |
| `DEBUG` | Enable SQL query logging | `false` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8401` |

## Appendix C: Useful Commands

```bash
# Development
npm run db:push          # Apply Prisma schema
npm run db:studio        # Open Prisma Studio

# Docker
docker-compose up -d     # Start all services
docker-compose logs -f   # View logs

# Database inspection
sqlite3 dev.db ".tables"        # List tables
sqlite3 dev.db ".schema Issue"  # Show table schema

# Backup
sqlite3 dev.db ".backup backup.db"
```

---

*Document generated: 2026-01-27*
*Task: CB-702*
