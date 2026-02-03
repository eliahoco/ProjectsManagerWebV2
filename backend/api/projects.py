"""
Projects API Routes - Read projects from shared database
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from models import get_db, Project, ProjectResponse, IssueSequence

router = APIRouter()


# GET /api/projects - List all projects
@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
):
    """List all projects"""
    result = await db.execute(select(Project).order_by(Project.name))
    projects = result.scalars().all()
    return [ProjectResponse.model_validate(project) for project in projects]


# GET /api/projects/{project_id} - Get a single project
@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single project by ID"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse.model_validate(project)


# POST /api/projects/{project_id}/initialize-sequence - Initialize issue sequence
@router.post("/projects/{project_id}/initialize-sequence")
async def initialize_sequence(
    project_id: str,
    prefix: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Initialize issue sequence for a project (idempotent)"""
    # Check if project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if sequence already exists
    result = await db.execute(
        select(IssueSequence).where(IssueSequence.projectId == project_id)
    )
    sequence = result.scalar_one_or_none()

    if sequence:
        return {
            "status": "exists",
            "prefix": sequence.prefix,
            "lastNumber": sequence.lastNumber,
        }

    # Generate prefix from project name
    if not prefix:
        # Use first letters of each word, up to 4 chars
        words = project.name.replace("-", " ").replace("_", " ").split()
        if len(words) >= 2:
            prefix = "".join(word[0].upper() for word in words[:4])
        else:
            prefix = project.name[:4].upper()

    # Create sequence
    import uuid
    sequence = IssueSequence(
        id=str(uuid.uuid4()),
        projectId=project_id,
        prefix=prefix,
        lastNumber=0,
    )
    db.add(sequence)
    await db.commit()

    return {
        "status": "created",
        "prefix": prefix,
        "lastNumber": 0,
    }
