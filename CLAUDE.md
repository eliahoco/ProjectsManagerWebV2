# CLAUDE.md — ProjectsManagerWebV2Production

## Project Overview

ProjectsManagerWebV2 is an AI-automated project management platform with CodeBoard (issue tracking), QA Board (test management), and an AI execution pipeline that runs Claude Code CLI against issues. It manages multiple software projects, their ports, sessions, and full development lifecycle.

## Architecture

```
frontend/          Next.js 16.1.2 (Turbopack) — port 3601
backend/           FastAPI + SQLAlchemy async — port 8401
ChromaDB           Vector database for RAG — port 8402
```

### Frontend Structure
```
frontend/
├── app/                    # Next.js App Router pages
│   ├── api/                # Next.js API routes (proxy/utility)
│   ├── codeboard/          # CodeBoard — issue tracking UI
│   ├── projects/           # Project management dashboard
│   ├── settings/           # App settings
│   ├── github/             # GitHub integration
│   ├── import/             # Issue import
│   ├── create/             # Project creation
│   ├── ports/              # Port management
│   ├── build/, logs/       # Build & log viewers
│   ├── layout.tsx          # Root layout
│   └── page.tsx            # Home page
├── components/
│   ├── codeboard/          # CodeBoard components (IssueDetail, BoardView, GlobalAgentStatusBar, etc.)
│   ├── projects/           # Project list/card components
│   ├── layout/             # Layout components (Sidebar, Header)
│   ├── ui/                 # Reusable UI primitives (Button, Dialog, Input, etc.)
│   ├── providers.tsx       # React Query + Theme providers
│   └── service-monitor.tsx # Service health monitor
├── hooks/                  # Custom React hooks
│   ├── useCodeBoard.ts     # CodeBoard data fetching & mutations (React Query)
│   ├── useQABoard.ts       # QA Board hooks
│   └── use-*.ts            # Other hooks
├── lib/
│   ├── api/                # API client functions
│   ├── shell.ts            # Project launch/stop via shell
│   ├── db.ts               # Prisma client
│   └── utils.ts            # Utility functions
├── prisma/
│   └── schema.prisma       # Database schema (SQLite)
└── types/                  # TypeScript type definitions
```

### Backend Structure
```
backend/
├── app/
│   ├── main.py             # FastAPI app, CORS, middleware, lifespan
│   ├── config.py           # Settings (pydantic-settings)
│   └── errors.py           # Standardized error handling
├── api/                    # API routers
│   ├── issues.py           # CRUD for issues (CodeBoard)
│   ├── projects.py         # Project management
│   ├── execution.py        # AI execution endpoints
│   ├── ai.py               # AI service endpoints (breakdown, analysis)
│   ├── qa.py               # QA Board endpoints
│   ├── git.py              # Git operations
│   ├── git_webhook.py      # Git webhook handler
│   ├── search.py           # Full-text search
│   └── import_tracker.py   # Issue import
├── models/                 # SQLAlchemy ORM models + Pydantic schemas
│   ├── issue.py            # Issue, Comment, Activity, IssueLink, Project
│   ├── qa.py               # QATask, QASequence, QASettings
│   ├── documentation.py    # ExecutionSummary, FeatureDocumentation
│   ├── git.py              # CommitLink, GitSyncState
│   ├── schemas.py          # Pydantic request/response schemas
│   └── database.py         # Engine, session factory, Base
├── services/
│   ├── terminal_service.py # AI execution: Claude Code CLI + local AI
│   ├── ai_service.py       # AI operations (breakdown, QA generation)
│   ├── rag_service.py      # ChromaDB RAG pipeline
│   ├── qa_service.py       # QA test execution
│   ├── git_service.py      # Git operations
│   └── commit_sync_service.py
├── middleware/              # Auth, rate limiting
├── utils/                  # Helper utilities (db_queries, etc.)
└── tests/                  # pytest + pytest-asyncio
```

## Conventions

### Frontend
- **Components**: PascalCase filenames, functional components with hooks
- **Styling**: Tailwind CSS v4 with `cn()` utility (clsx + tailwind-merge)
- **State**: React Query (`@tanstack/react-query`) for server state, `useState`/`useReducer` for local
- **API calls**: `fetch()` to `http://localhost:8401/api/...` — no axios
- **Path alias**: `@/` maps to frontend root
- **Icons**: `lucide-react`
- **UI primitives**: `components/ui/` — shadcn-style (Button, Dialog, Input, Select, etc.)

### Backend
- **Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Routers**: FastAPI `APIRouter` with prefix, included in `api/__init__.py`
- **ORM**: SQLAlchemy 2.0 async with `AsyncSession`
- **Validation**: Pydantic v2 models in `models/schemas.py`
- **Database**: SQLite via `aiosqlite`, async engine
- **Logging**: Python `logging` module (no print statements)
- **Exceptions**: Specific exception types (no bare `except:`)

### Database
- **Frontend (Prisma)**: SQLite at `frontend/prisma/dev.db`
- **Backend (SQLAlchemy)**: SQLite at `backend/data/codeboard.db`
- **Field naming**: camelCase in Prisma schema, maps to camelCase in SQLAlchemy models
- **IDs**: CUID strings (`@default(cuid())`)
- **Timestamps**: `createdAt`, `updatedAt` (auto-managed)

### Issue Hierarchy
```
FEATURE → EPIC → STORY → TASK → SUBTASK
```
- Issues have `parentId` for tree structure
- `key` format: `CB-{sequence}` (auto-generated per project)
- Status flow: `BACKLOG → TODO → IN_PROGRESS → COMPLETED_WAITING_QA → DONE`
- **Never skip to DONE** — always go through COMPLETED_WAITING_QA for QA verification

### AI Execution
- `terminal_service.py` spawns Claude Code CLI as subprocess
- Sessions tracked in memory (`TerminalSession` dataclass)
- Progress parsed from CLI output (phase, files read/written, commands run)
- `GlobalAgentStatusBar` shows active sessions filtered by project
- `FloatingAgentStatusBar` overlays AutoPilot modal (z-[60])
- Auto-marks issues as `COMPLETED_WAITING_QA` on successful execution

### AutoPilot Queue (CB-1951)
- `services/autopilot_queue_service.py` orchestrates sequential task execution
- **Persistent state:** every queue + task + event is write-through-persisted
  to `AutoPilotQueueRecord` / `AutoPilotTaskRecord` / `AutoPilotEvent` tables
  (mirrors in `models/autopilot.py` and `frontend/prisma/schema.prisma`)
- **Crash recovery:** lifespan startup hook calls `rehydrate_from_db()` —
  RUNNING tasks become failed(crash_recovery), queue → paused(crash_recovery),
  user must manually resume via `/api/execute/queue/recovery-status`
- **Token-exhaustion auto-pause:** when `is_token_exhaustion(session)` matches,
  queue → WAITING_RESET; `_schedule_auto_resume(reset_time)` arms an asyncio
  timer that fires at `reset_time + 60s` (cancellable on manual resume / abort)
- **Circuit breaker:** `_AUTO_RESUME_MAX_ATTEMPTS=3` consecutive auto-resumes
  → downgrade to `pauseReason='manual'`, require explicit user action
- **Audit log:** every state transition appends to `AutoPilotEvent` with
  redacted error text (Bearer/sk-/api_key= patterns stripped) and 8 KB cap
- **Operational runbook:** `backend/docs/AUTOPILOT_RUNBOOK.md`
- **Migration notes:** `backend/MIGRATION_NOTES.md`

## Key Patterns

### React Query Hooks (frontend)
All data fetching in `hooks/useCodeBoard.ts`:
- `useProjects()` — list projects
- `useProjectIssues(projectId)` — issues for a project
- `useIssue(issueId)` — single issue detail
- `useCreateIssue()`, `useUpdateIssue()`, `useDeleteIssue()` — mutations
- `useExecutionSessions()` — polling active AI sessions (2s interval)
- `useStartExecution()`, `useStopExecution()`, `useCompleteExecution()` — execution control

### API Endpoints (backend)
- `POST /api/execute/issue/{id}` — start AI execution
- `GET /api/execute/sessions` — list all sessions
- `POST /api/execute/session/{id}/complete` — mark done (cascades to children + parents)
- `GET /api/issues/{project_id}` — list issues
- `POST /api/issues/{project_id}` — create issue
- `PATCH /api/issues/issue/{id}` — update issue
- `POST /api/ai/breakdown/{id}` — AI breakdown of issue into subtasks
- `GET /api/qa/{project_id}/tasks` — QA tasks

### Status Cascade
- Starting execution → cascades `IN_PROGRESS` up to parent containers
- Completing execution → marks issue `COMPLETED_WAITING_QA`
- Manual complete → cascades `DONE` down to all children and up to parents (if all siblings done)

## Docker
- `docker-compose.yml` at project root
- Runtime: Colima (not Docker Desktop)
- Three services: frontend, backend, chromadb
- Volumes: `frontend_data`, `backend_data`, `chroma_data`

## Testing
- **Frontend**: Vitest + React Testing Library (`npm test`)
- **E2E**: Playwright (`npm run test:e2e`)
- **Backend**: pytest + pytest-asyncio (`pytest`)

## QA Pipeline (bindings for the `qa-regression` skill — Jonny Rule 30)

The `qa-regression` skill sources project-specific commands from this section. When the skill runs against PMv2 work, it uses exactly these invocations.

### Stage 2 — Automated layer commands

| Layer | Command |
|---|---|
| Backend tests | `cd backend && HOST=127.0.0.1 DATABASE_URL="sqlite+aiosqlite:///./data/codeboard.db" venv/bin/python -m pytest -q --tb=short` |
| Frontend tests | `cd frontend && npx vitest run` |
| Type check | `cd frontend && npx tsc --noEmit` |
| Backend lint | `cd backend && venv/bin/python -m ruff check .` (optional — surface findings, don't block on warnings) |

A non-zero exit in any of the first three rows is a Stage 2 FAIL — qa-regression stops there.

### Stage 3 — Manual layer (Chrome MCP) targets

| Target | URL |
|---|---|
| Frontend | `http://localhost:3601` |
| Backend health probe | `http://localhost:8401/health` |
| Backend API (for synthetic state setup) | `http://localhost:8401/api/...` |
| ChromaDB (RAG inspections) | `http://localhost:8402` |

Theme toggle lives on the navbar — click to toggle `.dark` on `<html>`. WorkspaceSwitcher lives in the sidebar — open to swap project context. Any AC touching project-scoped state MUST be run in at least two distinct projects.

### Stage 4 — Adjacent flows the regression matrix MUST sweep

When a fix touches a shared module, include the relevant adjacent flows in the regression matrix:

| Touched module / store | Sweep these adjacent flows |
|---|---|
| `useStudioStore` / Studio panel | Studio chat send, panel resize + reload, Studio empty state, theme toggle, project switch |
| `useTenant` / project context | Sidebar nav, CodeBoard project list, WorkspaceSwitcher, AutoPilot queue scoping |
| CodeBoard `useCodeBoard` hooks | Issue list, issue detail, status cascade, parent/child tree, search |
| `terminal_service` / AI execution | `GlobalAgentStatusBar`, `FloatingAgentStatusBar`, AutoPilot queue, session cleanup on completion |
| `autopilot_queue_service` | Queue start/pause/resume, crash recovery rehydrate, token-exhaustion auto-resume, audit log redaction |
| Prisma schema / `frontend/prisma/dev.db` | Migration replay, fresh-DB init, AutoPilot rehydrate from a populated DB |
| Backend SQLAlchemy / `backend/data/codeboard.db` | Issue CRUD, comment append, activity log, migration replay |

### Stage 5 — Destructive cases mandatory in this project

In addition to the three universal cases (corrupt persisted state, private window, network blip), PMv2 fixes touching the listed surfaces MUST add:

| Surface | Required destructive case |
|---|---|
| AutoPilot queue | Crash mid-execution → rehydrate → confirm RUNNING tasks become failed(crash_recovery) and queue → paused(crash_recovery). |
| Token-exhaustion auto-resume | Mock `is_token_exhaustion` true 3× → confirm circuit-breaker downgrades to `pauseReason='manual'`. |
| AutoPilot audit log | Inject a log line containing `Bearer abc.def`, `sk-abc123`, `api_key=xyz` → assert all redacted before persistence. |
| Studio persistence | Plant `stub-…` session IDs in `studio-state-v2` → reload → assert filtered out. |
| Issue status cascade | Mark deepest leaf DONE → assert parent + grandparent only flip when all siblings DONE. |

## Design-Intent Comments (Jonny Rule 31)

Any code comment that justifies a behavior by appealing to design intent ("intentional", "by design", "deliberate", "on purpose", "as designed", or any synonym implying design authority) MUST cite the exact source — doc path + section or line. Examples that pass review:

```ts
// Intentional per docs/plans/2026-05-07-ai-project-workspace-master-plan.md §E2.S2.T5
// Per backend/docs/AUTOPILOT_RUNBOOK.md "Auto-resume" section: 60s grace after reset_time.
```

Un-cited intent-claims are removed during code review (`code-reviewer` agent flags them as MEDIUM severity). Decision test: *"If a reviewer audited this claim against the source doc, would they find it written there?"* If not — delete the claim or write the doc first. Rule added 2026-05-22 after CB-2814: an un-cited "intentional per architecture doc" comment in `useStudioStore.ts` directly contradicted master plan §E2.S2.T5 and masked a real defect for weeks.

Project doc index for citations:

| Topic | Doc path |
|---|---|
| AI workspace / Studio master plan | `docs/plans/2026-05-07-ai-project-workspace-master-plan.md` |
| AutoPilot operational behavior | `backend/docs/AUTOPILOT_RUNBOOK.md` |
| AutoPilot migration notes | `backend/MIGRATION_NOTES.md` |
| CodeBoard issue conventions | `/Volumes/Seagate/Claude/_shared/codeboard-instructions.md` |
| Jonny bible | `/Users/elic/.claude/skills/jonny/SKILL.md` + `references/bible-extended.md` |

## Scripts
- `launch.sh` — start all services
- `stop.sh` — stop all services
- `frontend/lib/shell.ts` — programmatic launch/stop from UI (sets `LAUNCHED_FROM_WEB=1`, `NONINTERACTIVE=1`)

## CodeBoard Integration
For creating issues, planning features, and managing work items in CodeBoard, see:
`/Volumes/Seagate/Claude/_shared/codeboard-instructions.md`
