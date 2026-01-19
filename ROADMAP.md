# ProjectsManagerWebV2 - Implementation Roadmap

## Epic Overview

| Epic | Description | Priority | Status |
|------|-------------|----------|--------|
| E1 | Project Setup & Infrastructure | Critical | BACKLOG |
| E2 | Database & API Foundation | High | BACKLOG |
| E3 | CodeBoard UI | High | BACKLOG |
| E4 | RAG Integration | Medium | BACKLOG |
| E5 | AI Engine | Medium | BACKLOG |
| E6 | Git Integration & Automation | Low | BACKLOG |
| E7 | Polish & Testing | Low | BACKLOG |

---

## EPIC 1: Project Setup & Infrastructure

### Story 1.1: Create Project Structure
- [ ] T1.1.1: Create ProjectsManagerWebV2 directory structure
- [ ] T1.1.2: Set up implementation tracker database
- [ ] T1.1.3: Create PORT_CONFIG.md and update registry

### Story 1.2: Set Up Next.js Frontend
- [ ] T1.2.1: Duplicate base from ProjectsManagerWebProduction
- [ ] T1.2.2: Update port configuration to 3601
- [ ] T1.2.3: Update environment variables
- [ ] T1.2.4: Install dependencies and verify

### Story 1.3: Set Up Python FastAPI Backend
- [ ] T1.3.1: Create backend folder structure
- [ ] T1.3.2: Set up FastAPI application with CORS
- [ ] T1.3.3: Create Dockerfile for backend

### Story 1.4: Set Up Docker & Scripts
- [ ] T1.4.1: Create docker-compose.yml
- [ ] T1.4.2: Create launch.sh with progress dashboard
- [ ] T1.4.3: Create stop.sh
- [ ] T1.4.4: Test full stack startup

---

## EPIC 2: Database & API Foundation

### Story 2.1: Extend Prisma Schema
- [ ] T2.1.1: Add Issue model to schema.prisma
- [ ] T2.1.2: Add Comment model
- [ ] T2.1.3: Add Activity model
- [ ] T2.1.4: Add IssueLink model
- [ ] T2.1.5: Add IssueSequence model
- [ ] T2.1.6: Add enums (IssueType, IssueStatus, Priority)
- [ ] T2.1.7: Run prisma db push and verify

### Story 2.2: Create FastAPI Models
- [ ] T2.2.1: Create SQLAlchemy Issue model
- [ ] T2.2.2: Create Pydantic schemas
- [ ] T2.2.3: Set up database connection

### Story 2.3: Implement Issue CRUD API
- [ ] T2.3.1: GET /api/projects/{id}/issues
- [ ] T2.3.2: POST /api/projects/{id}/issues
- [ ] T2.3.3: GET /api/issues/{id}
- [ ] T2.3.4: PATCH /api/issues/{id}
- [ ] T2.3.5: DELETE /api/issues/{id}
- [ ] T2.3.6: POST /api/issues/{id}/comments

### Story 2.4: Issue Sequence Generation
- [ ] T2.4.1: Create sequence service
- [ ] T2.4.2: Initialize sequence for projects

### Story 2.5: API Proxy Routes
- [ ] T2.5.1: Create /api/codeboard/[...path] catch-all
- [ ] T2.5.2: Add authentication headers if needed

---

## EPIC 3: CodeBoard UI

### Story 3.1: Navigation & Layout
- [ ] T3.1.1: Add CodeBoard link to sidebar
- [ ] T3.1.2: Create /codeboard page layout

### Story 3.2: Kanban Board
- [ ] T3.2.1: Create KanbanBoard component
- [ ] T3.2.2: Create KanbanColumn component
- [ ] T3.2.3: Create IssueCard component
- [ ] T3.2.4: Implement drag-and-drop with @hello-pangea/dnd
- [ ] T3.2.5: Connect to API

### Story 3.3: List View
- [ ] T3.3.1: Create IssueList component
- [ ] T3.3.2: Create IssueRow component
- [ ] T3.3.3: Add sorting functionality
- [ ] T3.3.4: Add pagination

### Story 3.4: Filter Bar
- [ ] T3.4.1: Create FilterBar component
- [ ] T3.4.2: Add type filter dropdown
- [ ] T3.4.3: Add status filter dropdown
- [ ] T3.4.4: Add priority filter dropdown
- [ ] T3.4.5: Add assignee filter
- [ ] T3.4.6: Add text search

### Story 3.5: Issue Detail View
- [ ] T3.5.1: Create IssueDetail component
- [ ] T3.5.2: Create DescriptionSection
- [ ] T3.5.3: Create ActivityLog component
- [ ] T3.5.4: Create LinkedItems component
- [ ] T3.5.5: Create CommentsSection

### Story 3.6: Create Issue Modal
- [ ] T3.6.1: Create CreateIssueModal component
- [ ] T3.6.2: Add form fields
- [ ] T3.6.3: Add parent selector
- [ ] T3.6.4: Form validation and submission

---

## EPIC 4: RAG Integration

### Story 4.1: ChromaDB Setup
- [ ] T4.1.1: Configure ChromaDB in docker-compose
- [ ] T4.1.2: Create RAG service class
- [ ] T4.1.3: Initialize collections per project

### Story 4.2: Embedding Service
- [ ] T4.2.1: Create embedding function
- [ ] T4.2.2: Auto-embed on issue create
- [ ] T4.2.3: Auto-embed on issue update
- [ ] T4.2.4: Embed project context

### Story 4.3: Semantic Search
- [ ] T4.3.1: Create search endpoint
- [ ] T4.3.2: Add search UI to CodeBoard
- [ ] T4.3.3: Integrate with filter bar

---

## EPIC 5: AI Engine

### Story 5.1: Feature Breakdown Agent
- [ ] T5.1.1: Create breakdown prompt template
- [ ] T5.1.2: Implement breakdown service
- [ ] T5.1.3: Create /api/ai/breakdown endpoint
- [ ] T5.1.4: Add "AI Breakdown" button to UI

### Story 5.2: Auto-Status Updates
- [ ] T5.2.1: Define status transition rules
- [ ] T5.2.2: Create automation service
- [ ] T5.2.3: Create /api/ai/update endpoint

### Story 5.3: Bug Detection
- [ ] T5.3.1: Create bug prompt template
- [ ] T5.3.2: Create /api/ai/bug endpoint

### Story 5.4: QA Task Generation
- [ ] T5.4.1: Create QA prompt template
- [ ] T5.4.2: Create /api/ai/qa endpoint

---

## EPIC 6: Git Integration & Automation

### Story 6.1: Commit Tracking
- [ ] T6.1.1: Parse commit messages for issue keys
- [ ] T6.1.2: Create commit-issue link

### Story 6.2: Auto-Status from Commits
- [ ] T6.2.1: Define commit patterns
- [ ] T6.2.2: Trigger status updates

---

## EPIC 7: Polish & Testing

### Story 7.1: Keyboard Shortcuts
- [ ] T7.1.1: Add board shortcuts (N: New, /: Search)
- [ ] T7.1.2: Add issue shortcuts (E: Edit, Esc: Close)

### Story 7.2: Error Handling & Polish
- [ ] T7.2.1: Add loading states
- [ ] T7.2.2: Add error boundaries
- [ ] T7.2.3: Add toast notifications

### Story 7.3: Testing
- [ ] T7.3.1: Test all CRUD operations
- [ ] T7.3.2: Test drag-and-drop
- [ ] T7.3.3: Test AI features

---

## Task Summary

| Epic | Stories | Tasks |
|------|---------|-------|
| E1: Setup | 4 | 14 |
| E2: Database & API | 5 | 16 |
| E3: CodeBoard UI | 6 | 22 |
| E4: RAG Integration | 3 | 8 |
| E5: AI Engine | 4 | 10 |
| E6: Git Integration | 2 | 4 |
| E7: Polish | 3 | 6 |
| **TOTAL** | **27** | **80** |
