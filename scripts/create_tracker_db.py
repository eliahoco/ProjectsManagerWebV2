#!/usr/bin/env python3
"""
Create and seed the implementation tracker database.
This database tracks all epics, stories, tasks, and subtasks for ProjectsManagerWebV2.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "implementation_tracker.db"

# Schema
SCHEMA = """
-- Drop existing tables
DROP TABLE IF EXISTS subtasks;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS stories;
DROP TABLE IF EXISTS epics;

-- Epics table (highest level)
CREATE TABLE epics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG' CHECK(status IN ('BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE')),
    priority TEXT DEFAULT 'HIGH' CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    progress INTEGER DEFAULT 0,
    github_issue_number INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
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
    github_issue_number INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME
);

-- Tasks table (belongs to story)
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'BACKLOG' CHECK(status IN ('BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE')),
    priority TEXT DEFAULT 'MEDIUM' CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    estimated_hours REAL,
    actual_hours REAL,
    github_issue_number INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME
);

-- Subtasks table (belongs to task)
CREATE TABLE subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'BACKLOG' CHECK(status IN ('BACKLOG', 'TODO', 'IN_PROGRESS', 'DONE')),
    github_issue_number INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

-- Indexes
CREATE INDEX idx_stories_epic ON stories(epic_id);
CREATE INDEX idx_tasks_story ON tasks(story_id);
CREATE INDEX idx_subtasks_task ON subtasks(task_id);
CREATE INDEX idx_epics_status ON epics(status);
CREATE INDEX idx_stories_status ON stories(status);
CREATE INDEX idx_tasks_status ON tasks(status);

-- Views for progress calculation
CREATE VIEW epic_progress AS
SELECT
    e.id,
    e.title,
    e.status,
    e.priority,
    COUNT(DISTINCT s.id) as total_stories,
    COUNT(DISTINCT CASE WHEN s.status = 'DONE' THEN s.id END) as done_stories,
    COUNT(DISTINCT t.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.status = 'DONE' THEN t.id END) as done_tasks,
    ROUND(COUNT(DISTINCT CASE WHEN t.status = 'DONE' THEN t.id END) * 100.0 / NULLIF(COUNT(DISTINCT t.id), 0), 1) as progress_pct
FROM epics e
LEFT JOIN stories s ON s.epic_id = e.id
LEFT JOIN tasks t ON t.story_id = s.id
GROUP BY e.id
ORDER BY e.id;

CREATE VIEW overall_progress AS
SELECT
    COUNT(DISTINCT e.id) as total_epics,
    COUNT(DISTINCT CASE WHEN e.status = 'DONE' THEN e.id END) as done_epics,
    COUNT(DISTINCT s.id) as total_stories,
    COUNT(DISTINCT CASE WHEN s.status = 'DONE' THEN s.id END) as done_stories,
    COUNT(DISTINCT t.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN t.status = 'DONE' THEN t.id END) as done_tasks,
    COUNT(st.id) as total_subtasks,
    COUNT(CASE WHEN st.status = 'DONE' THEN 1 END) as done_subtasks,
    ROUND(COUNT(DISTINCT CASE WHEN t.status = 'DONE' THEN t.id END) * 100.0 / NULLIF(COUNT(DISTINCT t.id), 0), 1) as progress_pct
FROM epics e
LEFT JOIN stories s ON s.epic_id = e.id
LEFT JOIN tasks t ON t.story_id = s.id
LEFT JOIN subtasks st ON st.task_id = t.id;

CREATE VIEW current_work AS
SELECT
    'task' as type,
    t.id,
    t.title,
    t.status,
    s.title as parent_title,
    e.title as epic_title,
    t.estimated_hours
FROM tasks t
JOIN stories s ON t.story_id = s.id
JOIN epics e ON s.epic_id = e.id
WHERE t.status = 'IN_PROGRESS'
UNION ALL
SELECT
    'story' as type,
    s.id,
    s.title,
    s.status,
    e.title as parent_title,
    NULL as epic_title,
    NULL as estimated_hours
FROM stories s
JOIN epics e ON s.epic_id = e.id
WHERE s.status = 'IN_PROGRESS';
"""

# Seed Data - All Epics, Stories, Tasks
SEED_DATA = {
    "epics": [
        {
            "id": "E1",
            "title": "Project Setup & Infrastructure",
            "description": "Set up complete project infrastructure including directory structure, Next.js frontend, FastAPI backend, Docker configuration, and launch scripts.",
            "priority": "CRITICAL",
            "stories": [
                {
                    "id": "S1.1",
                    "title": "Create Project Structure",
                    "description": "Create base project directory and folder structure",
                    "priority": "CRITICAL",
                    "tasks": [
                        {"id": "T1.1.1", "title": "Create ProjectsManagerWebV2 directory", "description": "Create root directory with frontend/, backend/, docs/, scripts/ folders", "estimated_hours": 0.25, "subtasks": ["Create root folder", "Create frontend folder structure", "Create backend folder structure", "Initialize git repository", "Create README.md"]},
                        {"id": "T1.1.2", "title": "Set up implementation tracker database", "description": "Create SQLite database to track implementation progress", "estimated_hours": 1, "subtasks": ["Create database schema", "Create seed script", "Seed with all tasks", "Create query script", "Verify data integrity"]},
                        {"id": "T1.1.3", "title": "Create PORT_CONFIG.md and update registry", "description": "Document port allocations (3601, 8401, 8501)", "estimated_hours": 0.25, "subtasks": ["Create PORT_CONFIG.md", "Document all ports", "Update central registry if exists"]},
                    ]
                },
                {
                    "id": "S1.2",
                    "title": "Set Up Next.js Frontend",
                    "description": "Initialize and configure Next.js frontend application",
                    "priority": "CRITICAL",
                    "tasks": [
                        {"id": "T1.2.1", "title": "Duplicate base from ProjectsManagerWebProduction", "description": "Copy app/, components/, lib/, config files", "estimated_hours": 0.5, "subtasks": ["Copy app/ directory", "Copy components/ directory", "Copy lib/ directory", "Copy config files", "Update package.json name", "Verify imports"]},
                        {"id": "T1.2.2", "title": "Update port configuration", "description": "Change dev server port to 3601", "estimated_hours": 0.33, "subtasks": ["Change port in package.json", "Update .ports.env", "Search for hardcoded references", "Update any hardcoded refs", "Test dev server startup"]},
                        {"id": "T1.2.3", "title": "Update environment variables", "description": "Create .env with DATABASE_URL, BACKEND_URL", "estimated_hours": 0.25, "subtasks": ["Create .env file", "Set DATABASE_URL", "Set BACKEND_URL to 8401", "Create .env.example", "Update .gitignore"]},
                        {"id": "T1.2.4", "title": "Install dependencies and verify", "description": "Run npm install, generate Prisma client, verify startup", "estimated_hours": 0.5, "subtasks": ["Run npm install", "Generate Prisma client", "Start dev server", "Verify homepage loads", "Check for console errors"]},
                    ]
                },
                {
                    "id": "S1.3",
                    "title": "Set Up Python FastAPI Backend",
                    "description": "Initialize FastAPI backend service",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T1.3.1", "title": "Create backend folder structure", "description": "Create app/, api/, models/, services/, tests/ directories", "estimated_hours": 0.5, "subtasks": ["Create app/ directory", "Create api/ directory", "Create models/ directory", "Create services/ directory", "Create tests/ directory", "Create requirements.txt", "Create virtual environment", "Create .env file"]},
                        {"id": "T1.3.2", "title": "Set up FastAPI application", "description": "Create main.py with CORS, health endpoint, uvicorn config", "estimated_hours": 0.75, "subtasks": ["Create main.py with FastAPI app", "Configure CORS middleware", "Create health endpoint", "Create config.py", "Configure uvicorn", "Test startup"]},
                        {"id": "T1.3.3", "title": "Create Dockerfile for backend", "description": "Multi-stage build with non-root user", "estimated_hours": 0.5, "subtasks": ["Create multi-stage Dockerfile", "Install dependencies in builder", "Set up non-root user", "Set entrypoint", "Create .dockerignore", "Test build and run"]},
                    ]
                },
                {
                    "id": "S1.4",
                    "title": "Set Up Docker & Scripts",
                    "description": "Create Docker Compose and launch/stop scripts",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T1.4.1", "title": "Create docker-compose.yml", "description": "Define frontend, backend, ChromaDB services with networking", "estimated_hours": 0.75, "subtasks": ["Define frontend service", "Define backend service", "Define ChromaDB service", "Configure network", "Configure volumes", "Add health checks", "Test full stack"]},
                        {"id": "T1.4.2", "title": "Create launch.sh with progress dashboard", "description": "Start all services and display implementation progress", "estimated_hours": 1, "subtasks": ["Create bash script structure", "Add port checking", "Query tracker.db for progress", "Display ASCII progress dashboard", "Start all services", "Save PIDs for stop script", "Add Docker mode"]},
                        {"id": "T1.4.3", "title": "Create stop.sh", "description": "Stop all services and clean up", "estimated_hours": 0.33, "subtasks": ["Stop processes from PID files", "Clean up PID files", "Stop Docker containers", "Kill processes on ports", "Display status"]},
                        {"id": "T1.4.4", "title": "Test full stack startup", "description": "Verify all services work together", "estimated_hours": 0.5, "subtasks": ["Run launch.sh", "Verify all services running", "Test health endpoints", "Check inter-service communication", "Test stop.sh", "Document any issues"]},
                    ]
                },
            ]
        },
        {
            "id": "E2",
            "title": "Database & API Foundation",
            "description": "Establish database schema for CodeBoard and implement FastAPI CRUD endpoints for issues.",
            "priority": "HIGH",
            "stories": [
                {
                    "id": "S2.1",
                    "title": "Extend Prisma Schema",
                    "description": "Add CodeBoard models to database",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T2.1.1", "title": "Add Issue model to schema.prisma", "description": "Define Issue model with all fields, relations, indexes", "estimated_hours": 0.75, "subtasks": ["Define IssueType enum", "Define IssueStatus enum", "Define Priority enum", "Define Assignee enum", "Create Issue model", "Add relations", "Add indexes", "Validate schema"]},
                        {"id": "T2.1.2", "title": "Add Comment model", "description": "Create Comment model linked to Issue", "estimated_hours": 0.33, "subtasks": ["Define Comment model", "Link to Issue", "Add author tracking"]},
                        {"id": "T2.1.3", "title": "Add Activity model", "description": "Create Activity model for audit trail", "estimated_hours": 0.33, "subtasks": ["Define ActivityType enum", "Create Activity model", "Link to Issue"]},
                        {"id": "T2.1.4", "title": "Add IssueLink model", "description": "Create model for relating issues (blocks, duplicates, etc.)", "estimated_hours": 0.33, "subtasks": ["Define LinkType enum", "Create IssueLink model", "Add unique constraint"]},
                        {"id": "T2.1.5", "title": "Add IssueSequence model", "description": "Create model for auto-incrementing issue keys", "estimated_hours": 0.25, "subtasks": ["Create IssueSequence model", "Add unique constraint on projectId", "Update Project model"]},
                        {"id": "T2.1.6", "title": "Add enums (IssueType, IssueStatus, Priority)", "description": "Define all enum values with documentation", "estimated_hours": 0.17, "subtasks": ["Define all enum values", "Add documentation comments"]},
                        {"id": "T2.1.7", "title": "Run prisma db push and verify", "description": "Apply schema and test with Prisma Studio", "estimated_hours": 0.25, "subtasks": ["Run prisma validate", "Run prisma format", "Apply schema with db push", "Generate Prisma client", "Check migrations", "Test with Prisma Studio", "Run test queries"]},
                    ]
                },
                {
                    "id": "S2.2",
                    "title": "Create FastAPI Models",
                    "description": "Define SQLAlchemy models and Pydantic schemas",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T2.2.1", "title": "Create SQLAlchemy Issue model", "description": "Mirror Prisma schema with relationships", "estimated_hours": 0.75, "subtasks": ["Create base.py", "Define all enums", "Create Issue model", "Create Comment model", "Create Activity model", "Create IssueSequence model", "Set up relationships"]},
                        {"id": "T2.2.2", "title": "Create Pydantic schemas", "description": "Define IssueCreate, IssueUpdate, IssueResponse schemas", "estimated_hours": 0.5, "subtasks": ["Create enum types", "Create IssueCreate schema", "Create IssueUpdate schema", "Create IssueResponse schema", "Create IssueDetailResponse", "Create Comment schemas", "Create Activity schema", "Create pagination schemas"]},
                        {"id": "T2.2.3", "title": "Set up database connection", "description": "Configure SQLAlchemy with async support", "estimated_hours": 0.5, "subtasks": ["Create sync engine", "Create async engine", "Create session factories", "Create dependency function", "Add init_db function", "Test connection"]},
                    ]
                },
                {
                    "id": "S2.3",
                    "title": "Implement Issue CRUD API",
                    "description": "Create REST endpoints for issue management",
                    "priority": "CRITICAL",
                    "tasks": [
                        {"id": "T2.3.1", "title": "GET /api/projects/{id}/issues", "description": "List issues with filters, pagination, sorting", "estimated_hours": 1, "subtasks": ["Create base query", "Implement type filter", "Implement status filter", "Implement priority filter", "Implement assignee filter", "Implement parent filter", "Implement search", "Implement label filter", "Add pagination", "Add sorting", "Add counts"]},
                        {"id": "T2.3.2", "title": "POST /api/projects/{id}/issues", "description": "Create issue with auto key generation", "estimated_hours": 0.75, "subtasks": ["Validate project exists", "Validate parent issue", "Enforce hierarchy rules", "Generate issue key", "Create issue record", "Log creation activity", "Return created issue"]},
                        {"id": "T2.3.3", "title": "GET /api/issues/{id}", "description": "Get full issue details with comments and activities", "estimated_hours": 0.5, "subtasks": ["Fetch issue by ID", "Load comments", "Load activities", "Load children", "Load parent", "Build response"]},
                        {"id": "T2.3.4", "title": "PATCH /api/issues/{id}", "description": "Update issue with change tracking", "estimated_hours": 0.75, "subtasks": ["Fetch existing issue", "Compare old vs new values", "Validate parent change", "Log activity per field", "Handle DONE status", "Update timestamp", "Return updated issue"]},
                        {"id": "T2.3.5", "title": "DELETE /api/issues/{id}", "description": "Soft delete with optional cascade", "estimated_hours": 0.33, "subtasks": ["Fetch issue", "Implement soft delete", "Implement hard delete", "Cascade to children", "Return 204"]},
                        {"id": "T2.3.6", "title": "POST /api/issues/{id}/comments", "description": "Add comment with activity logging", "estimated_hours": 0.33, "subtasks": ["Verify issue exists", "Create comment", "Log activity", "Update issue timestamp", "Return comment"]},
                    ]
                },
                {
                    "id": "S2.4",
                    "title": "Issue Sequence Generation",
                    "description": "Implement automatic issue key generation",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T2.4.1", "title": "Create sequence service", "description": "Get next number with thread safety", "estimated_hours": 0.5, "subtasks": ["Get next number", "Thread safety"]},
                        {"id": "T2.4.2", "title": "Initialize sequence for projects", "description": "Create sequence on first issue", "estimated_hours": 0.25, "subtasks": ["Create on first issue", "Default prefix"]},
                    ]
                },
                {
                    "id": "S2.5",
                    "title": "API Proxy Routes",
                    "description": "Create Next.js API routes that proxy to FastAPI",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T2.5.1", "title": "Create /api/codeboard/[...path] catch-all", "description": "Proxy all requests to backend", "estimated_hours": 0.5, "subtasks": ["Create catch-all route", "Implement proxy function", "Handle all HTTP methods", "Forward query params", "Forward request body", "Handle errors"]},
                        {"id": "T2.5.2", "title": "Add authentication headers if needed", "description": "Pass through auth and handle CORS", "estimated_hours": 0.25, "subtasks": ["Pass through auth", "Handle CORS"]},
                    ]
                },
            ]
        },
        {
            "id": "E3",
            "title": "CodeBoard UI",
            "description": "Build complete CodeBoard user interface with Kanban board, list view, filters, and issue management.",
            "priority": "HIGH",
            "stories": [
                {
                    "id": "S3.1",
                    "title": "Navigation & Layout",
                    "description": "Add CodeBoard to navigation and create page layout",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T3.1.1", "title": "Add CodeBoard link to sidebar", "description": "Add navigation item with icon", "estimated_hours": 0.25, "subtasks": ["Add navigation item", "Add route matching", "Test navigation"]},
                        {"id": "T3.1.2", "title": "Create /codeboard page layout", "description": "Header, project selector, view toggle, content area", "estimated_hours": 0.75, "subtasks": ["Create page component", "Add header section", "Add project selector", "Add view toggle", "Add filter bar integration", "Add content area", "Add create issue button", "Handle URL params"]},
                    ]
                },
                {
                    "id": "S3.2",
                    "title": "Kanban Board",
                    "description": "Implement Kanban board with drag-and-drop",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T3.2.1", "title": "Create KanbanBoard component", "description": "Board container with state management", "estimated_hours": 0.75, "subtasks": ["Set up DndContext", "Configure sensors", "Group issues by status", "Handle drag start", "Handle drag end", "Add drag overlay"]},
                        {"id": "T3.2.2", "title": "Create KanbanColumn component", "description": "Column with header, issue list, count badge", "estimated_hours": 0.5, "subtasks": ["Create column container", "Add column header", "Set up droppable zone", "Add hover state", "Render issue cards", "Add empty state"]},
                        {"id": "T3.2.3", "title": "Create IssueCard component", "description": "Card with type icon, priority, title, assignee", "estimated_hours": 0.75, "subtasks": ["Set up draggable", "Add type icon", "Add priority icon", "Display title", "Show labels", "Show assignee", "Add story points", "Style drag state"]},
                        {"id": "T3.2.4", "title": "Implement drag-and-drop", "description": "Full DnD with animations and accessibility", "estimated_hours": 1, "subtasks": ["Install @dnd-kit packages", "Configure pointer sensor", "Configure keyboard sensor", "Configure touch sensor", "Add drop animation", "Add accessibility announcements", "Test on mobile"]},
                        {"id": "T3.2.5", "title": "Connect to API", "description": "Fetch issues and handle optimistic updates", "estimated_hours": 0.5, "subtasks": ["Create API functions", "Create useIssues hook", "Implement optimistic updates", "Add error rollback", "Add cache invalidation"]},
                    ]
                },
                {
                    "id": "S3.3",
                    "title": "List View",
                    "description": "Implement table/list view",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T3.3.1", "title": "Create IssueList component", "description": "Table with column headers", "estimated_hours": 0.5, "subtasks": ["Create table structure", "Add column headers"]},
                        {"id": "T3.3.2", "title": "Create IssueRow component", "description": "Row with key, type, status, actions", "estimated_hours": 0.5, "subtasks": ["Issue key link", "Type badge", "Status dropdown"]},
                        {"id": "T3.3.3", "title": "Add sorting functionality", "description": "Click column headers to sort", "estimated_hours": 0.33, "subtasks": ["Sort by column", "Sort direction"]},
                        {"id": "T3.3.4", "title": "Add pagination", "description": "Page size selector and navigation", "estimated_hours": 0.33, "subtasks": ["Page size selector", "Page navigation"]},
                    ]
                },
                {
                    "id": "S3.4",
                    "title": "Filter Bar",
                    "description": "Implement filtering capabilities",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T3.4.1", "title": "Create FilterBar component", "description": "Container with clear all button", "estimated_hours": 0.33, "subtasks": ["Filter container", "Clear all button"]},
                        {"id": "T3.4.2", "title": "Add type filter dropdown", "description": "Multi-select with type icons", "estimated_hours": 0.25, "subtasks": ["Multi-select", "Type icons"]},
                        {"id": "T3.4.3", "title": "Add status filter dropdown", "description": "Multi-select with status colors", "estimated_hours": 0.25, "subtasks": ["Status colors"]},
                        {"id": "T3.4.4", "title": "Add priority filter dropdown", "description": "Multi-select with priority badges", "estimated_hours": 0.25, "subtasks": ["Priority badges"]},
                        {"id": "T3.4.5", "title": "Add assignee filter", "description": "AI vs Human toggle", "estimated_hours": 0.25, "subtasks": ["AI vs Human toggle"]},
                        {"id": "T3.4.6", "title": "Add text search", "description": "Debounced search input", "estimated_hours": 0.33, "subtasks": ["Debounced input", "Clear button"]},
                    ]
                },
                {
                    "id": "S3.5",
                    "title": "Issue Detail View",
                    "description": "Create issue detail page/modal",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T3.5.1", "title": "Create IssueDetail component", "description": "Header with key/title, status/priority selectors", "estimated_hours": 0.75, "subtasks": ["Header with key/title", "Status/priority selectors"]},
                        {"id": "T3.5.2", "title": "Create DescriptionSection", "description": "Markdown rendering with edit mode", "estimated_hours": 0.5, "subtasks": ["Markdown rendering", "Edit mode"]},
                        {"id": "T3.5.3", "title": "Create ActivityLog component", "description": "Timeline view with activity icons", "estimated_hours": 0.5, "subtasks": ["Timeline view", "Activity icons"]},
                        {"id": "T3.5.4", "title": "Create LinkedItems component", "description": "Parent/children, related issues, commits", "estimated_hours": 0.5, "subtasks": ["Parent/children", "Related issues", "Commits"]},
                        {"id": "T3.5.5", "title": "Create CommentsSection", "description": "Comment list with add form", "estimated_hours": 0.5, "subtasks": ["Comment list", "Add comment form"]},
                    ]
                },
                {
                    "id": "S3.6",
                    "title": "Create Issue Modal",
                    "description": "Implement issue creation",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T3.6.1", "title": "Create CreateIssueModal component", "description": "Modal wrapper with form layout", "estimated_hours": 0.5, "subtasks": ["Modal wrapper", "Form layout"]},
                        {"id": "T3.6.2", "title": "Add form fields", "description": "Title, type, priority, description inputs", "estimated_hours": 0.5, "subtasks": ["Title input", "Type selector", "Priority selector", "Description textarea"]},
                        {"id": "T3.6.3", "title": "Add parent selector", "description": "Hierarchy selection for sub-tasks", "estimated_hours": 0.33, "subtasks": ["For sub-tasks", "Epic/Story hierarchy"]},
                        {"id": "T3.6.4", "title": "Form validation and submission", "description": "Required fields, API call, error handling", "estimated_hours": 0.5, "subtasks": ["Required fields", "API call", "Success/error handling"]},
                    ]
                },
            ]
        },
        {
            "id": "E4",
            "title": "RAG Integration",
            "description": "Integrate ChromaDB for vector storage and semantic search.",
            "priority": "MEDIUM",
            "stories": [
                {
                    "id": "S4.1",
                    "title": "ChromaDB Setup",
                    "description": "Initialize and configure ChromaDB",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T4.1.1", "title": "Configure ChromaDB in docker-compose", "description": "Add service with persistent storage on port 8501", "estimated_hours": 0.5, "subtasks": ["Persistent storage", "Port 8501"]},
                        {"id": "T4.1.2", "title": "Create RAG service class", "description": "Client connection and collection management", "estimated_hours": 0.75, "subtasks": ["Client connection", "Collection management"]},
                        {"id": "T4.1.3", "title": "Initialize collections per project", "description": "Create project_context, issues, decisions collections", "estimated_hours": 0.5, "subtasks": ["project_context", "issues", "decisions"]},
                    ]
                },
                {
                    "id": "S4.2",
                    "title": "Embedding Service",
                    "description": "Implement document embedding",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T4.2.1", "title": "Create embedding function", "description": "Text to vector conversion with batch processing", "estimated_hours": 0.5, "subtasks": ["Text to vector", "Batch processing"]},
                        {"id": "T4.2.2", "title": "Auto-embed on issue create", "description": "Hook into create API", "estimated_hours": 0.33, "subtasks": ["Hook into create API"]},
                        {"id": "T4.2.3", "title": "Auto-embed on issue update", "description": "Hook into update API", "estimated_hours": 0.33, "subtasks": ["Hook into update API"]},
                        {"id": "T4.2.4", "title": "Embed project context", "description": "Index PROJECT_DESCRIPTOR.md, README.md", "estimated_hours": 0.5, "subtasks": ["PROJECT_DESCRIPTOR.md", "README.md"]},
                    ]
                },
                {
                    "id": "S4.3",
                    "title": "Semantic Search",
                    "description": "Implement search functionality",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T4.3.1", "title": "Create search endpoint", "description": "Query embedding with similarity search", "estimated_hours": 0.75, "subtasks": ["Query embedding", "Similarity search"]},
                        {"id": "T4.3.2", "title": "Add search UI to CodeBoard", "description": "Search input with results dropdown", "estimated_hours": 0.5, "subtasks": ["Search input", "Results dropdown"]},
                        {"id": "T4.3.3", "title": "Integrate with filter bar", "description": "Combine semantic search with filters", "estimated_hours": 0.33, "subtasks": ["Combine with filters"]},
                    ]
                },
            ]
        },
        {
            "id": "E5",
            "title": "AI Engine",
            "description": "Implement AI-powered features for automated task management.",
            "priority": "MEDIUM",
            "stories": [
                {
                    "id": "S5.1",
                    "title": "Feature Breakdown Agent",
                    "description": "Auto-generate issues from feature descriptions",
                    "priority": "HIGH",
                    "tasks": [
                        {"id": "T5.1.1", "title": "Create breakdown prompt template", "description": "System prompt with output format", "estimated_hours": 0.5, "subtasks": ["System prompt", "Output format"]},
                        {"id": "T5.1.2", "title": "Implement breakdown service", "description": "Parse description and generate hierarchy", "estimated_hours": 1, "subtasks": ["Parse description", "Generate hierarchy"]},
                        {"id": "T5.1.3", "title": "Create /api/ai/breakdown endpoint", "description": "Input validation, AI call, create issues", "estimated_hours": 0.75, "subtasks": ["Input validation", "Call AI", "Create issues"]},
                        {"id": "T5.1.4", "title": "Add AI Breakdown button to UI", "description": "Feature input modal with progress indicator", "estimated_hours": 0.75, "subtasks": ["Feature input modal", "Progress indicator"]},
                    ]
                },
                {
                    "id": "S5.2",
                    "title": "Auto-Status Updates",
                    "description": "Automatically update issue status based on activity",
                    "priority": "LOW",
                    "tasks": [
                        {"id": "T5.2.1", "title": "Define status transition rules", "description": "Commit → In Progress, PR → In Review", "estimated_hours": 0.33, "subtasks": ["Commit → In Progress", "PR → In Review"]},
                        {"id": "T5.2.2", "title": "Create automation service", "description": "Event handlers and status updates", "estimated_hours": 0.5, "subtasks": ["Event handlers", "Status updates"]},
                        {"id": "T5.2.3", "title": "Create /api/ai/update endpoint", "description": "Process events and update issues", "estimated_hours": 0.5, "subtasks": ["Process events", "Update issues"]},
                    ]
                },
                {
                    "id": "S5.3",
                    "title": "Bug Detection",
                    "description": "Create bugs from test failures",
                    "priority": "LOW",
                    "tasks": [
                        {"id": "T5.3.1", "title": "Create bug prompt template", "description": "Parse error and generate steps to reproduce", "estimated_hours": 0.5, "subtasks": ["Parse error", "Generate steps to reproduce"]},
                        {"id": "T5.3.2", "title": "Create /api/ai/bug endpoint", "description": "Input error details and create bug issue", "estimated_hours": 0.5, "subtasks": ["Input error details", "Create bug issue"]},
                    ]
                },
                {
                    "id": "S5.4",
                    "title": "QA Task Generation",
                    "description": "Generate QA tasks when features complete",
                    "priority": "LOW",
                    "tasks": [
                        {"id": "T5.4.1", "title": "Create QA prompt template", "description": "Test scenarios with acceptance criteria", "estimated_hours": 0.5, "subtasks": ["Test scenarios", "Acceptance criteria"]},
                        {"id": "T5.4.2", "title": "Create /api/ai/qa endpoint", "description": "Input story ID and generate QA tasks", "estimated_hours": 0.5, "subtasks": ["Input story ID", "Generate QA tasks"]},
                    ]
                },
            ]
        },
        {
            "id": "E6",
            "title": "Git Integration & Automation",
            "description": "Link commits to issues and update status from commits.",
            "priority": "LOW",
            "stories": [
                {
                    "id": "S6.1",
                    "title": "Commit Tracking",
                    "description": "Link commits to issues",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T6.1.1", "title": "Parse commit messages for issue keys", "description": "Regex pattern to extract keys like PM-123", "estimated_hours": 0.33, "subtasks": ["Regex pattern", "Extract keys"]},
                        {"id": "T6.1.2", "title": "Create commit-issue link", "description": "Store in database and display in UI", "estimated_hours": 0.5, "subtasks": ["Store in database", "Display in UI"]},
                    ]
                },
                {
                    "id": "S6.2",
                    "title": "Auto-Status from Commits",
                    "description": "Update status based on commit patterns",
                    "priority": "LOW",
                    "tasks": [
                        {"id": "T6.2.1", "title": "Define commit patterns", "description": "Patterns: fix:, feat:, wip:", "estimated_hours": 0.25, "subtasks": ["fix:", "feat:", "wip:"]},
                        {"id": "T6.2.2", "title": "Trigger status updates", "description": "Call automation service on commit", "estimated_hours": 0.33, "subtasks": ["Call automation service"]},
                    ]
                },
            ]
        },
        {
            "id": "E7",
            "title": "Polish & Testing",
            "description": "Add keyboard shortcuts, improve error handling, and perform testing.",
            "priority": "LOW",
            "stories": [
                {
                    "id": "S7.1",
                    "title": "Keyboard Shortcuts",
                    "description": "Add keyboard navigation",
                    "priority": "LOW",
                    "tasks": [
                        {"id": "T7.1.1", "title": "Add board shortcuts", "description": "N: New issue, /: Search", "estimated_hours": 0.5, "subtasks": ["N: New issue", "/: Search"]},
                        {"id": "T7.1.2", "title": "Add issue shortcuts", "description": "E: Edit, Esc: Close", "estimated_hours": 0.33, "subtasks": ["E: Edit", "Esc: Close"]},
                    ]
                },
                {
                    "id": "S7.2",
                    "title": "Error Handling & Polish",
                    "description": "Improve UX and reliability",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T7.2.1", "title": "Add loading states", "description": "Skeleton screens and spinners", "estimated_hours": 0.5, "subtasks": ["Skeleton screens", "Spinners"]},
                        {"id": "T7.2.2", "title": "Add error boundaries", "description": "Graceful fallbacks for errors", "estimated_hours": 0.5, "subtasks": ["Graceful fallbacks"]},
                        {"id": "T7.2.3", "title": "Add toast notifications", "description": "Success/error messages", "estimated_hours": 0.33, "subtasks": ["Success/error messages"]},
                    ]
                },
                {
                    "id": "S7.3",
                    "title": "Testing",
                    "description": "End-to-end testing",
                    "priority": "MEDIUM",
                    "tasks": [
                        {"id": "T7.3.1", "title": "Test all CRUD operations", "description": "Create, read, update, delete", "estimated_hours": 1, "subtasks": ["Create", "Read", "Update", "Delete"]},
                        {"id": "T7.3.2", "title": "Test drag-and-drop", "description": "Status changes via drag", "estimated_hours": 0.5, "subtasks": ["Status changes"]},
                        {"id": "T7.3.3", "title": "Test AI features", "description": "Breakdown and QA generation", "estimated_hours": 0.5, "subtasks": ["Breakdown", "QA generation"]},
                    ]
                },
            ]
        },
    ]
}


def create_database():
    """Create the database and seed with data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create schema
    cursor.executescript(SCHEMA)
    conn.commit()

    # Seed data
    for epic_data in SEED_DATA["epics"]:
        # Insert epic
        cursor.execute("""
            INSERT INTO epics (id, title, description, priority, status)
            VALUES (?, ?, ?, ?, 'BACKLOG')
        """, (epic_data["id"], epic_data["title"], epic_data["description"], epic_data["priority"]))

        for story_data in epic_data["stories"]:
            # Insert story
            cursor.execute("""
                INSERT INTO stories (id, epic_id, title, description, priority, status)
                VALUES (?, ?, ?, ?, ?, 'BACKLOG')
            """, (story_data["id"], epic_data["id"], story_data["title"], story_data["description"], story_data["priority"]))

            for task_data in story_data["tasks"]:
                # Insert task
                cursor.execute("""
                    INSERT INTO tasks (id, story_id, title, description, priority, status, estimated_hours)
                    VALUES (?, ?, ?, ?, 'MEDIUM', 'BACKLOG', ?)
                """, (task_data["id"], story_data["id"], task_data["title"], task_data["description"], task_data.get("estimated_hours", 1)))

                for i, subtask_title in enumerate(task_data.get("subtasks", [])):
                    subtask_id = f"{task_data['id']}.{i+1}"
                    cursor.execute("""
                        INSERT INTO subtasks (id, task_id, title, status)
                        VALUES (?, ?, ?, 'BACKLOG')
                    """, (subtask_id, task_data["id"], subtask_title))

    conn.commit()

    # Print summary
    cursor.execute("SELECT * FROM overall_progress")
    progress = cursor.fetchone()
    print(f"""
Database created: {DB_PATH}

Summary:
- Epics: {progress[0]}
- Stories: {progress[2]}
- Tasks: {progress[4]}
- Subtasks: {progress[6]}
- Total items: {progress[0] + progress[2] + progress[4] + progress[6]}
""")

    conn.close()


if __name__ == "__main__":
    create_database()
