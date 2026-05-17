"""
Projects API Routes - Read projects from shared database.

CB-2666: the LIST and GET-by-id endpoints disclose project-level
identifiers (CUID, name, formerly the abspath via `path`). The threat
model is identical to CB-2216 / CB-2217 — Origin-less callers (curl,
server-to-server, malicious local processes) bypass the
`validate_origin` middleware in `app.main` by design, and on a non-
loopback bind (`ALLOW_LAN=true`) the LIST endpoint became a one-call
project enumeration that defeated the CB-2217 collection-name redaction.

Two-layer fix (defense-in-depth):

  1. Field minimization — `ProjectResponse` no longer serializes
     `path`. The abspath is never required across the HTTP boundary;
     internal callers use the ORM. `extra="forbid"` on the schema
     pins the contract so a future regression that re-adds a path-
     shaped field fails at serialization time.
  2. Internal-token gate — `app.security.require_local_or_token`
     short-circuits when `INTERNAL_API_TOKEN` is empty (preserves dev
     workflow on loopback bind) and blocks Origin-less callers
     otherwise. The token is the deploy precondition for widening
     `HOST` / `ALLOW_LAN`. See backend/docs/DOC_PIPELINE_RUNBOOK.md §3.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.rate_limit import limiter
from app.security import InternalAuthDep
from models import get_db, Project, ProjectResponse, IssueSequence

router = APIRouter()


# GET /api/projects - List all projects
@router.get(
    "/projects",
    response_model=List[ProjectResponse],
    dependencies=[InternalAuthDep],
)
@limiter.limit("30/minute")
async def list_projects(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List all projects.

    CB-2666: gated by `InternalAuthDep`; `ProjectResponse` redacts `path`;
    rate-limited at 30/minute per client to bound enumeration speed even
    on the bypass paths that the global 200/minute would otherwise allow.
    """
    result = await db.execute(select(Project).order_by(Project.name))
    projects = result.scalars().all()
    return [ProjectResponse.model_validate(project) for project in projects]


# GET /api/projects/{project_id} - Get a single project
@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    dependencies=[InternalAuthDep],
)
@limiter.limit("30/minute")
async def get_project(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single project by ID.

    CB-2666: gated by `InternalAuthDep`; `ProjectResponse` redacts `path`.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse.model_validate(project)


# POST /api/projects/{project_id}/initialize-sequence - Initialize issue sequence
@router.post(
    "/projects/{project_id}/initialize-sequence",
    dependencies=[InternalAuthDep],
)
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
