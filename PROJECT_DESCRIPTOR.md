# ProjectsManagerWebV2 with CodeBoard

## Overview

A next-generation project manager with AI-automated task management (CodeBoard). This project extends ProjectsManagerWebProduction with a Jira-like issue tracking system that uses AI to automatically break down features, track progress, and manage development workflows.

## Key Features

- **CodeBoard**: Kanban board for issue tracking (Epics, Stories, Tasks, Subtasks, Bugs)
- **RAG Integration**: ChromaDB for semantic search and context retrieval
- **AI Engine**: Automatic feature breakdown, bug detection, QA task generation
- **Git Integration**: Link commits to issues, auto-update status

## Tech Stack

- **Frontend**: Next.js 14, React, Tailwind CSS, shadcn/ui
- **Backend**: Python FastAPI
- **Database**: SQLite (Prisma) + ChromaDB for vectors
- **AI**: Claude API for intelligent task management

## Architecture

```
ProjectsManagerWebV2/
├── frontend/          # Next.js app (port 3601)
│   ├── app/
│   ├── components/
│   └── lib/
├── backend/           # FastAPI service (port 8401)
│   ├── app/
│   ├── api/
│   ├── models/
│   └── services/
├── docker-compose.yml
├── launch.sh
└── stop.sh
```

## Related Projects

- **ProjectsManagerWebProduction**: Base project this extends
- **ProjectsManagerProduction**: Original CLI version
