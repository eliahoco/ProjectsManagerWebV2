# ProjectsManagerWebV2 - Implementation Roadmap

## Epic Overview

| Epic | Description | Priority | Status |
|------|-------------|----------|--------|
| E1 | Project Setup & Infrastructure | Critical | DONE |
| E2 | Database & API Foundation | High | DONE |
| E3 | CodeBoard UI | High | DONE |
| E4 | RAG Integration | Medium | DONE |
| E5 | AI Engine | Medium | DONE |
| E6 | Git Integration & Automation | Low | PARTIAL |
| E7 | Polish & Testing | Low | IN_PROGRESS |

---

## EPIC 1: Project Setup & Infrastructure - DONE

### Story 1.1: Create Project Structure
- [x] T1.1.1: Create ProjectsManagerWebV2 directory structure
- [x] T1.1.2: Set up implementation tracker database
- [x] T1.1.3: Create PORT_CONFIG.md and update registry

### Story 1.2: Set Up Next.js Frontend
- [x] T1.2.1: Duplicate base from ProjectsManagerWebProduction
- [x] T1.2.2: Update port configuration to 3601
- [x] T1.2.3: Update environment variables
- [x] T1.2.4: Install dependencies and verify

### Story 1.3: Set Up Python FastAPI Backend
- [x] T1.3.1: Create backend folder structure
- [x] T1.3.2: Set up FastAPI application with CORS
- [x] T1.3.3: Create Dockerfile for backend

### Story 1.4: Set Up Docker & Scripts
- [x] T1.4.1: Create docker-compose.yml
- [x] T1.4.2: Create launch.sh with progress dashboard
- [x] T1.4.3: Create stop.sh
- [x] T1.4.4: Test full stack startup

---

## EPIC 2: Database & API Foundation - DONE

### Story 2.1: Extend Prisma Schema
- [x] T2.1.1: Add Issue model to schema.prisma
- [x] T2.1.2: Add Comment model
- [x] T2.1.3: Add Activity model
- [x] T2.1.4: Add IssueLink model
- [x] T2.1.5: Add IssueSequence model
- [x] T2.1.6: Add enums (IssueType, IssueStatus, Priority)
- [x] T2.1.7: Run prisma db push and verify

### Story 2.2: Create FastAPI Models
- [x] T2.2.1: Create SQLAlchemy Issue model
- [x] T2.2.2: Create Pydantic schemas
- [x] T2.2.3: Set up database connection

### Story 2.3: Implement Issue CRUD API
- [x] T2.3.1: GET /api/projects/{id}/issues
- [x] T2.3.2: POST /api/projects/{id}/issues
- [x] T2.3.3: GET /api/issues/{id}
- [x] T2.3.4: PATCH /api/issues/{id}
- [x] T2.3.5: DELETE /api/issues/{id}
- [x] T2.3.6: POST /api/issues/{id}/comments

### Story 2.4: Issue Sequence Generation
- [x] T2.4.1: Create sequence service
- [x] T2.4.2: Initialize sequence for projects

### Story 2.5: API Proxy Routes
- [x] T2.5.1: Create /api/codeboard/[...path] catch-all
- [x] T2.5.2: Add authentication headers if needed

---

## EPIC 3: CodeBoard UI - DONE

### Story 3.1: Navigation & Layout
- [x] T3.1.1: Add CodeBoard link to sidebar
- [x] T3.1.2: Create /codeboard page layout

### Story 3.2: Kanban Board
- [x] T3.2.1: Create KanbanBoard component
- [x] T3.2.2: Create KanbanColumn component
- [x] T3.2.3: Create IssueCard component
- [x] T3.2.4: Implement drag-and-drop with @hello-pangea/dnd
- [x] T3.2.5: Connect to API

### Story 3.3: List View
- [ ] T3.3.1: Create IssueList component
- [ ] T3.3.2: Create IssueRow component
- [ ] T3.3.3: Add sorting functionality
- [ ] T3.3.4: Add pagination

### Story 3.4: Filter Bar
- [x] T3.4.1: Create FilterBar component
- [x] T3.4.2: Add type filter dropdown
- [x] T3.4.3: Add status filter dropdown
- [x] T3.4.4: Add priority filter dropdown
- [ ] T3.4.5: Add assignee filter
- [x] T3.4.6: Add text search

### Story 3.5: Issue Detail View
- [x] T3.5.1: Create IssueDetail component
- [x] T3.5.2: Create DescriptionSection
- [x] T3.5.3: Create ActivityLog component
- [x] T3.5.4: Create LinkedItems component
- [x] T3.5.5: Create CommentsSection

### Story 3.6: Create Issue Modal
- [x] T3.6.1: Create CreateIssueModal component
- [x] T3.6.2: Add form fields
- [x] T3.6.3: Add parent selector
- [x] T3.6.4: Form validation and submission

---

## EPIC 4: RAG Integration - DONE

### Story 4.1: ChromaDB Setup
- [x] T4.1.1: Configure ChromaDB in docker-compose
- [x] T4.1.2: Create RAG service class
- [x] T4.1.3: Initialize collections per project

### Story 4.2: Embedding Service
- [x] T4.2.1: Create embedding function
- [x] T4.2.2: Auto-embed on issue create
- [x] T4.2.3: Auto-embed on issue update
- [x] T4.2.4: Embed project context

### Story 4.3: Semantic Search
- [x] T4.3.1: Create search endpoint
- [ ] T4.3.2: Add search UI to CodeBoard
- [x] T4.3.3: Integrate with filter bar

---

## EPIC 5: AI Engine - DONE

### Story 5.1: Feature Breakdown Agent
- [x] T5.1.1: Create breakdown prompt template
- [x] T5.1.2: Implement breakdown service (with Ollama + Claude fallback)
- [x] T5.1.3: Create /api/ai/breakdown endpoint
- [x] T5.1.4: Add "AI Breakdown" button to UI

### Story 5.2: Auto-Status Updates
- [x] T5.2.1: Define status transition rules
- [x] T5.2.2: Create automation service
- [x] T5.2.3: Create /api/ai/suggest-status endpoint

### Story 5.3: Bug Detection
- [x] T5.3.1: Create bug prompt template
- [x] T5.3.2: Create /api/ai/detect-bug endpoint

### Story 5.4: QA Task Generation
- [x] T5.4.1: Create QA prompt template
- [x] T5.4.2: Create /api/ai/generate-qa endpoint

---

## EPIC 6: Git Integration & Automation - PARTIAL

### Story 6.1: Commit Tracking
- [ ] T6.1.1: Parse commit messages for issue keys
- [ ] T6.1.2: Create commit-issue link

### Story 6.2: Auto-Status from Commits
- [ ] T6.2.1: Define commit patterns
- [ ] T6.2.2: Trigger status updates

### Story 6.3: Git Sync UI Enhancements ✅
- [x] T6.3.1: Add progress bar for push/pull operations
- [x] T6.3.2: Show phase status (staging, committing, pushing)
- [x] T6.3.3: Add terminal output toggle button
- [x] T6.3.4: Improve error handling with meaningful messages
- [x] T6.3.5: Add toast notifications for success/failure

### Story 6.4: Service Control Actions ✅
- [x] T6.4.1: Implement individual service stop action
- [x] T6.4.2: Implement individual service start action (detached process)
- [x] T6.4.3: Implement individual service restart action
- [x] T6.4.4: Add global service health monitoring panel

---

## EPIC 7: Polish & Testing - IN_PROGRESS

### Story 7.1: Keyboard Shortcuts
- [ ] T7.1.1: Add board shortcuts (N: New, /: Search)
- [ ] T7.1.2: Add issue shortcuts (E: Edit, Esc: Close)

### Story 7.2: Error Handling & Polish
- [x] T7.2.1: Add loading states
- [ ] T7.2.2: Add error boundaries
- [ ] T7.2.3: Add toast notifications

### Story 7.3: Testing
- [x] T7.3.1: Test all CRUD operations
- [x] T7.3.2: Test drag-and-drop
- [x] T7.3.3: Test AI features

---

## Task Summary

| Epic | Stories | Tasks | Done |
|------|---------|-------|------|
| E1: Setup | 4 | 14 | 14 |
| E2: Database & API | 5 | 16 | 16 |
| E3: CodeBoard UI | 6 | 22 | 17 |
| E4: RAG Integration | 3 | 8 | 7 |
| E5: AI Engine | 4 | 10 | 10 |
| E6: Git Integration | 2 | 4 | 0 |
| E7: Polish | 3 | 6 | 4 |
| **TOTAL** | **27** | **80** | **68** |

---

## AI Provider Support

The AI Engine supports multiple providers:

1. **Ollama (Local)** - Primary, free, runs locally
   - Supports: llama3.2, llama3, mistral, codellama, deepseek-coder
   - Port: 11434
   - Text format fallback parser for smaller models

2. **Claude (API)** - Fallback when Ollama unavailable
   - Model: claude-sonnet-4-20250514
   - Requires: ANTHROPIC_API_KEY in environment

---

## Recent Updates

- **2024-01**: Added Ollama support as primary AI provider
- **2024-01**: Added text format parser for small model compatibility
- **2024-01**: Fixed API routing for /api/ai/* endpoints
- **2024-01**: Added auto-embedding for issues in RAG service
