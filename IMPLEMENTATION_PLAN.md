# ProjectsManagerWebV2 with CodeBoard - Implementation Plan

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

## Complete Task Breakdown

### EPIC 1: Project Setup & Infrastructure
**ID:** E1 | **Priority:** Critical | **Status:** BACKLOG

#### Story 1.1: Create Project Structure
**ID:** S1.1 | Create the base project directory and folder structure

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T1.1.1 | Create ProjectsManagerWebV2 directory | - Create root folder<br>- Create frontend/ folder<br>- Create backend/ folder |
| T1.1.2 | Set up implementation tracker database | - Create schema<br>- Seed with all tasks<br>- Create query script |
| T1.1.3 | Create PORT_CONFIG.md and update registry | - Document ports 3601, 8401, 8501<br>- Update central PORT_REGISTRY.md |

#### Story 1.2: Set Up Next.js Frontend
**ID:** S1.2 | Initialize and configure the Next.js frontend application

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T1.2.1 | Duplicate base from ProjectsManagerWebProduction | - Copy app/, components/, lib/<br>- Copy config files<br>- Update package.json name |
| T1.2.2 | Update port configuration | - Change port to 3601 in package.json<br>- Update .ports.env<br>- Update any hardcoded references |
| T1.2.3 | Update environment variables | - Create .env<br>- Set DATABASE_URL<br>- Set BACKEND_URL to 8401 |
| T1.2.4 | Install dependencies and verify | - Run npm install<br>- Start dev server<br>- Verify homepage loads |

#### Story 1.3: Set Up Python FastAPI Backend
**ID:** S1.3 | Initialize the FastAPI backend service

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T1.3.1 | Create backend folder structure | - Create app/, api/, models/, services/<br>- Create requirements.txt<br>- Create .env |
| T1.3.2 | Set up FastAPI application | - Create main.py with CORS<br>- Create health endpoint<br>- Configure uvicorn |
| T1.3.3 | Create Dockerfile for backend | - Multi-stage build<br>- Install dependencies<br>- Set entrypoint |

#### Story 1.4: Set Up Docker & Scripts
**ID:** S1.4 | Create Docker Compose and launch scripts

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T1.4.1 | Create docker-compose.yml | - Frontend service<br>- Backend service<br>- ChromaDB service<br>- Network configuration |
| T1.4.2 | Create launch.sh with progress dashboard | - Start all services<br>- Query tracker.db<br>- Display progress |
| T1.4.3 | Create stop.sh | - Stop all services<br>- Clean up PIDs |
| T1.4.4 | Test full stack startup | - Run launch.sh<br>- Verify all services<br>- Check health endpoints |

---

### EPIC 2: Database & API Foundation
**ID:** E2 | **Priority:** High | **Status:** BACKLOG

#### Story 2.1: Extend Prisma Schema
**ID:** S2.1 | Add CodeBoard models to the database

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T2.1.1 | Add Issue model to schema.prisma | - Define fields<br>- Add relations<br>- Add indexes |
| T2.1.2 | Add Comment model | - Define fields<br>- Link to Issue |
| T2.1.3 | Add Activity model | - Define fields<br>- Link to Issue |
| T2.1.4 | Add IssueLink model | - Define link types<br>- Self-referential relations |
| T2.1.5 | Add IssueSequence model | - Project prefix<br>- Auto-increment |
| T2.1.6 | Add enums (IssueType, IssueStatus, Priority) | - Define all enum values |
| T2.1.7 | Run prisma db push and verify | - Apply schema<br>- Check migrations<br>- Test with Prisma Studio |

#### Story 2.2: Create FastAPI Models
**ID:** S2.2 | Define SQLAlchemy models and Pydantic schemas

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T2.2.1 | Create SQLAlchemy Issue model | - Mirror Prisma schema<br>- Set up relationships |
| T2.2.2 | Create Pydantic schemas | - IssueCreate<br>- IssueUpdate<br>- IssueResponse |
| T2.2.3 | Set up database connection | - SQLite connection<br>- Session management |

#### Story 2.3: Implement Issue CRUD API
**ID:** S2.3 | Create REST endpoints for issue management

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T2.3.1 | GET /api/projects/{id}/issues | - Query with filters<br>- Pagination<br>- Sorting |
| T2.3.2 | POST /api/projects/{id}/issues | - Validate input<br>- Generate issue key<br>- Return created issue |
| T2.3.3 | GET /api/issues/{id} | - Full issue details<br>- Include comments<br>- Include activity |
| T2.3.4 | PATCH /api/issues/{id} | - Partial updates<br>- Log activity<br>- Update timestamp |
| T2.3.5 | DELETE /api/issues/{id} | - Soft delete option<br>- Cascade handling |
| T2.3.6 | POST /api/issues/{id}/comments | - Add comment<br>- Log activity |

#### Story 2.4: Issue Sequence Generation
**ID:** S2.4 | Implement automatic issue key generation

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T2.4.1 | Create sequence service | - Get next number<br>- Thread safety |
| T2.4.2 | Initialize sequence for projects | - Create on first issue<br>- Default prefix |

#### Story 2.5: API Proxy Routes
**ID:** S2.5 | Create Next.js API routes that proxy to FastAPI

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T2.5.1 | Create /api/codeboard/[...path] catch-all | - Proxy to backend<br>- Handle errors |
| T2.5.2 | Add authentication headers if needed | - Pass through auth<br>- Handle CORS |

---

### EPIC 3: CodeBoard UI
**ID:** E3 | **Priority:** High | **Status:** BACKLOG

#### Story 3.1: Navigation & Layout
**ID:** S3.1 | Add CodeBoard to application navigation

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T3.1.1 | Add CodeBoard link to sidebar | - Add icon<br>- Add route |
| T3.1.2 | Create /codeboard page layout | - Header<br>- Project selector |

#### Story 3.2: Kanban Board
**ID:** S3.2 | Implement the main Kanban board view

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T3.2.1 | Create KanbanBoard component | - Board container<br>- State management |
| T3.2.2 | Create KanbanColumn component | - Column header<br>- Issue list<br>- Count badge |
| T3.2.3 | Create IssueCard component | - Type icon<br>- Priority badge<br>- Title<br>- Assignee |
| T3.2.4 | Implement drag-and-drop | - Install @hello-pangea/dnd<br>- Handle reorder<br>- Update status on drop |
| T3.2.5 | Connect to API | - Fetch issues<br>- Update on change<br>- Optimistic updates |

#### Story 3.3: List View
**ID:** S3.3 | Implement the table/list view

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T3.3.1 | Create IssueList component | - Table structure<br>- Column headers |
| T3.3.2 | Create IssueRow component | - Issue key link<br>- Type badge<br>- Status dropdown |
| T3.3.3 | Add sorting functionality | - Sort by column<br>- Sort direction |
| T3.3.4 | Add pagination | - Page size selector<br>- Page navigation |

#### Story 3.4: Filter Bar
**ID:** S3.4 | Implement filtering capabilities

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T3.4.1 | Create FilterBar component | - Filter container<br>- Clear all button |
| T3.4.2 | Add type filter dropdown | - Multi-select<br>- Type icons |
| T3.4.3 | Add status filter dropdown | - Status colors |
| T3.4.4 | Add priority filter dropdown | - Priority badges |
| T3.4.5 | Add assignee filter | - AI vs Human toggle |
| T3.4.6 | Add text search | - Debounced input<br>- Clear button |

#### Story 3.5: Issue Detail View
**ID:** S3.5 | Create the issue detail page/modal

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T3.5.1 | Create IssueDetail component | - Header with key/title<br>- Status/priority selectors |
| T3.5.2 | Create DescriptionSection | - Markdown rendering<br>- Edit mode |
| T3.5.3 | Create ActivityLog component | - Timeline view<br>- Activity icons |
| T3.5.4 | Create LinkedItems component | - Parent/children<br>- Related issues<br>- Commits |
| T3.5.5 | Create CommentsSection | - Comment list<br>- Add comment form |

#### Story 3.6: Create Issue Modal
**ID:** S3.6 | Implement issue creation

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T3.6.1 | Create CreateIssueModal component | - Modal wrapper<br>- Form layout |
| T3.6.2 | Add form fields | - Title input<br>- Type selector<br>- Priority selector<br>- Description textarea |
| T3.6.3 | Add parent selector | - For sub-tasks<br>- Epic/Story hierarchy |
| T3.6.4 | Form validation and submission | - Required fields<br>- API call<br>- Success/error handling |

---

### EPIC 4: RAG Integration
**ID:** E4 | **Priority:** Medium | **Status:** BACKLOG

#### Story 4.1: ChromaDB Setup
**ID:** S4.1 | Initialize and configure ChromaDB

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T4.1.1 | Configure ChromaDB in docker-compose | - Persistent storage<br>- Port 8501 |
| T4.1.2 | Create RAG service class | - Client connection<br>- Collection management |
| T4.1.3 | Initialize collections per project | - project_context<br>- issues<br>- decisions |

#### Story 4.2: Embedding Service
**ID:** S4.2 | Implement document embedding

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T4.2.1 | Create embedding function | - Text to vector<br>- Batch processing |
| T4.2.2 | Auto-embed on issue create | - Hook into create API |
| T4.2.3 | Auto-embed on issue update | - Hook into update API |
| T4.2.4 | Embed project context | - PROJECT_DESCRIPTOR.md<br>- README.md |

#### Story 4.3: Semantic Search
**ID:** S4.3 | Implement search functionality

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T4.3.1 | Create search endpoint | - Query embedding<br>- Similarity search |
| T4.3.2 | Add search UI to CodeBoard | - Search input<br>- Results dropdown |
| T4.3.3 | Integrate with filter bar | - Combine with filters |

---

### EPIC 5: AI Engine
**ID:** E5 | **Priority:** Medium | **Status:** BACKLOG

#### Story 5.1: Feature Breakdown Agent
**ID:** S5.1 | Auto-generate issues from feature descriptions

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T5.1.1 | Create breakdown prompt template | - System prompt<br>- Output format |
| T5.1.2 | Implement breakdown service | - Parse description<br>- Generate hierarchy |
| T5.1.3 | Create /api/ai/breakdown endpoint | - Input validation<br>- Call AI<br>- Create issues |
| T5.1.4 | Add "AI Breakdown" button to UI | - Feature input modal<br>- Progress indicator |

#### Story 5.2: Auto-Status Updates
**ID:** S5.2 | Automatically update issue status based on activity

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T5.2.1 | Define status transition rules | - Commit → In Progress<br>- PR → In Review |
| T5.2.2 | Create automation service | - Event handlers<br>- Status updates |
| T5.2.3 | Create /api/ai/update endpoint | - Process events<br>- Update issues |

#### Story 5.3: Bug Detection
**ID:** S5.3 | Create bugs from test failures

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T5.3.1 | Create bug prompt template | - Parse error<br>- Generate steps to reproduce |
| T5.3.2 | Create /api/ai/bug endpoint | - Input error details<br>- Create bug issue |

#### Story 5.4: QA Task Generation
**ID:** S5.4 | Generate QA tasks when features complete

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T5.4.1 | Create QA prompt template | - Test scenarios<br>- Acceptance criteria |
| T5.4.2 | Create /api/ai/qa endpoint | - Input story ID<br>- Generate QA tasks |

---

### EPIC 6: Git Integration & Automation
**ID:** E6 | **Priority:** Low | **Status:** BACKLOG

#### Story 6.1: Commit Tracking
**ID:** S6.1 | Link commits to issues

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T6.1.1 | Parse commit messages for issue keys | - Regex pattern<br>- Extract keys |
| T6.1.2 | Create commit-issue link | - Store in database<br>- Display in UI |

#### Story 6.2: Auto-Status from Commits
**ID:** S6.2 | Update status based on commit patterns

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T6.2.1 | Define commit patterns | - "fix:", "feat:", "wip:" |
| T6.2.2 | Trigger status updates | - Call automation service |

---

### EPIC 7: Polish & Testing
**ID:** E7 | **Priority:** Low | **Status:** BACKLOG

#### Story 7.1: Keyboard Shortcuts
**ID:** S7.1 | Add keyboard navigation

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T7.1.1 | Add board shortcuts | - N: New issue<br>- /: Search |
| T7.1.2 | Add issue shortcuts | - E: Edit<br>- Esc: Close |

#### Story 7.2: Error Handling & Polish
**ID:** S7.2 | Improve UX and reliability

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T7.2.1 | Add loading states | - Skeleton screens<br>- Spinners |
| T7.2.2 | Add error boundaries | - Graceful fallbacks |
| T7.2.3 | Add toast notifications | - Success/error messages |

#### Story 7.3: Testing
**ID:** S7.3 | End-to-end testing

| Task ID | Title | Sub-tasks |
|---------|-------|-----------|
| T7.3.1 | Test all CRUD operations | - Create, read, update, delete |
| T7.3.2 | Test drag-and-drop | - Status changes |
| T7.3.3 | Test AI features | - Breakdown, QA generation |

---

## Task Summary

| Epic | Stories | Tasks | Sub-tasks | Total Items |
|------|---------|-------|-----------|-------------|
| E1: Setup | 4 | 14 | ~40 | ~58 |
| E2: Database & API | 5 | 16 | ~35 | ~56 |
| E3: CodeBoard UI | 6 | 22 | ~50 | ~78 |
| E4: RAG Integration | 3 | 8 | ~15 | ~26 |
| E5: AI Engine | 4 | 10 | ~20 | ~34 |
| E6: Git Integration | 2 | 4 | ~8 | ~14 |
| E7: Polish | 3 | 6 | ~12 | ~21 |
| **TOTAL** | **27** | **80** | **~180** | **~287** |

---

## First Steps (What I'll Do Now)

1. **Create ProjectsManagerWebV2 directory**
2. **Create implementation_tracker.db** with all tasks seeded
3. **Create launch.sh** with progress dashboard
4. **Begin Epic 1: Project Setup**

---

## Verification Plan

1. **After Each Task:**
   - Update tracker.db status to DONE
   - Run launch.sh to see updated progress

2. **After Each Story:**
   - Verify feature works end-to-end
   - Document any bugs found

3. **After Each Epic:**
   - Full integration test
   - Update PROJECT_DESCRIPTOR.md

---

## Files to Create First

1. `/Users/elic/Documents/Claude/ProjectsManagerWebV2/` (directory)
2. `/Users/elic/Documents/Claude/ProjectsManagerWebV2/implementation_tracker.db`
3. `/Users/elic/Documents/Claude/ProjectsManagerWebV2/launch.sh`
4. `/Users/elic/Documents/Claude/ProjectsManagerWebV2/stop.sh`
5. `/Users/elic/Documents/Claude/ProjectsManagerWebV2/PORT_CONFIG.md`
6. `/Users/elic/Documents/Claude/ProjectsManagerWebV2/PROJECT_DESCRIPTOR.md`
