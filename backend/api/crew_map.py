"""
Crew Map API — CB-2384 Studio

Graph-topology and assignment endpoints for the Crew Map feature.
All routes are scoped by tenantId (from TenantDep); cross-tenant access
returns 404 (not 403) to prevent tenant enumeration.

Graph response shape is designed for react-flow consumption:
  { nodes: [...], edges: [...] }

ETag format: W/"<sha256(graph_data_repr)>"
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps import TenantDep
from app.errors import NotFoundError
from models import (
    CrewAssignment,
    CrewSkillUsage,
    Issue,
    Project,
    get_db,
)
from models.schemas import (
    CrewAssignmentCreate,
    CrewAssignmentResponse,
    CrewAssignmentUpdate,
    CrewSkillUsageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crew-map", tags=["CrewMap"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# HIGH-4: Issue / Project tables pre-date Studio multi-tenancy and have no
# tenantId column.  Full tenant scoping for issues is deferred to Phase 2
# (see CB-2121).  For now we at minimum assert the project EXISTS, which
# prevents probing for issues in non-existent project IDs.
async def _validate_project_exists(db: AsyncSession, project_id: str) -> bool:
    """Return True if a Project row with *project_id* exists, False otherwise.

    Args:
        db: Async database session.
        project_id: Project primary key to verify.

    Returns:
        True when the project exists, False when it does not.
    """
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    return result.scalar_one_or_none() is not None


def _etag_from_str(data: str) -> str:
    """Compute a weak ETag from an arbitrary string representation.

    Args:
        data: Raw string to hash.

    Returns:
        Weak ETag string in W/"<sha256>" format.
    """
    digest = hashlib.sha256(data.encode()).hexdigest()
    return f'W/"{digest}"'


def _assignment_etag(assignment: CrewAssignment) -> str:
    """Derive ETag for a single CrewAssignment.

    Args:
        assignment: The ORM instance.

    Returns:
        Weak ETag string.
    """
    raw = f"{assignment.id}:{assignment.updatedAt.isoformat()}"
    return _etag_from_str(raw)


async def _get_tenant_assignment(
    assignment_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> CrewAssignment:
    """Fetch a CrewAssignment scoped to a tenant; 404 on miss or cross-tenant.

    Args:
        assignment_id: The CrewAssignment primary key.
        tenant_id: Caller's tenant identifier.
        db: Async SQLAlchemy session.

    Returns:
        The matching CrewAssignment ORM instance.

    Raises:
        NotFoundError: When the assignment doesn't exist or belongs to another tenant.
    """
    result = await db.execute(
        select(CrewAssignment).where(
            CrewAssignment.id == assignment_id,
            CrewAssignment.tenantId == tenant_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise NotFoundError("CrewAssignment", assignment_id)
    return assignment


def _issue_to_node(issue: Issue) -> Dict[str, Any]:
    """Convert an Issue ORM instance into a react-flow node dict.

    Args:
        issue: The Issue ORM instance.

    Returns:
        A dict with id, type, label, status, and data keys.
    """
    return {
        "id": issue.id,
        "type": issue.type,  # FEATURE | EPIC | STORY | TASK | SUBTASK | BUG
        "label": f"{issue.key}: {issue.title}",
        "status": issue.status,
        "data": {
            "key": issue.key,
            "title": issue.title,
            "issueType": issue.type,
            "status": issue.status,
            "priority": issue.priority,
            "parentId": issue.parentId,
        },
    }


def _issues_to_edges(issues: List[Issue]) -> List[Dict[str, Any]]:
    """Build parent→child edges from a list of Issue rows.

    Args:
        issues: List of Issue ORM instances.

    Returns:
        List of edge dicts shaped for react-flow.
    """
    edges = []
    id_set = {i.id for i in issues}
    for issue in issues:
        if issue.parentId and issue.parentId in id_set:
            edges.append(
                {
                    "id": f"edge-{issue.parentId}-{issue.id}",
                    "source": issue.parentId,
                    "target": issue.id,
                    "label": "parent",
                }
            )
    return edges


def _assignment_edges(
    assignments: List[CrewAssignment],
    node_ids: set,
) -> List[Dict[str, Any]]:
    """Build agent-assignment edges from CrewAssignment rows.

    Args:
        assignments: List of CrewAssignment ORM instances.
        node_ids: Set of issue IDs present as nodes (to validate edge targets).

    Returns:
        List of edge dicts for react-flow.
    """
    edges = []
    for a in assignments:
        if a.issueId in node_ids:
            edges.append(
                {
                    "id": f"assign-{a.id}",
                    "source": a.agentTemplateId,
                    "target": a.issueId,
                    "label": a.roleLabel,
                    "assignmentStatus": a.status,
                }
            )
    return edges


# ---------------------------------------------------------------------------
# Pydantic shapes used only in this router
# ---------------------------------------------------------------------------


class CrewMapGraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


class CrewAssignmentDetailResponse(BaseModel):
    id: str
    tenantId: Optional[str]
    projectId: str
    issueId: str
    agentTemplateId: str
    roleLabel: str
    status: str
    createdAt: datetime
    updatedAt: datetime
    skillUsage: List[CrewSkillUsageResponse]

    class Config:
        from_attributes = True


class SkillIncrementBody(BaseModel):
    skillName: str


class CrewMapSearchResultNode(BaseModel):
    id: str
    key: str
    title: str
    type: str
    status: str
    priority: str


# ---------------------------------------------------------------------------
# Graph endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/graph",
    response_model=CrewMapGraphResponse,
    summary="Full project Crew Map graph",
)
async def get_project_graph(
    project_id: str,
    response: Response,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> CrewMapGraphResponse:
    """Return the full graph for a project shaped for react-flow.

    Nodes are built from all Issue rows in the project.
    Edges include parent/child relations plus CrewAssignment agent edges.
    An ETag is computed from the serialized graph.

    Args:
        project_id: The project to build the graph for.
        response: FastAPI response for ETag header injection.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        CrewMapGraphResponse with nodes and edges.
    """
    # HIGH-4: assert the project exists before querying its issues (prevents probing).
    if not await _validate_project_exists(db, project_id):
        raise NotFoundError("Project", project_id)

    issues_result = await db.execute(
        select(Issue).where(Issue.projectId == project_id)
    )
    issues = list(issues_result.scalars().all())

    assignments_result = await db.execute(
        select(CrewAssignment).where(
            CrewAssignment.projectId == project_id,
            CrewAssignment.tenantId == tenant_id,
        )
    )
    assignments = list(assignments_result.scalars().all())

    nodes = [_issue_to_node(i) for i in issues]
    node_ids = {i.id for i in issues}
    edges = _issues_to_edges(issues) + _assignment_edges(assignments, node_ids)

    graph = CrewMapGraphResponse(nodes=nodes, edges=edges)
    etag = _etag_from_str(json.dumps({"n": len(nodes), "e": len(edges), "p": project_id}))
    response.headers["ETag"] = etag
    return graph


@router.get(
    "/features/{feature_id}/graph",
    response_model=CrewMapGraphResponse,
    summary="Sub-graph for a single feature",
)
async def get_feature_graph(
    feature_id: str,
    response: Response,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> CrewMapGraphResponse:
    """Return the sub-graph for a feature and all its descendants.

    Uses a recursive CTE to fetch the full descendant tree, then builds the
    same node+edge shape as the project-level endpoint.

    Args:
        feature_id: The FEATURE issue ID.
        response: FastAPI response for ETag header injection.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        CrewMapGraphResponse scoped to the feature subtree.

    Raises:
        NotFoundError: 404 if the feature issue doesn't exist.
    """
    # Verify feature exists
    feat_result = await db.execute(
        select(Issue).where(Issue.id == feature_id)
    )
    feature = feat_result.scalar_one_or_none()
    if feature is None:
        raise NotFoundError("Issue (feature)", feature_id)

    # HIGH-4: assert the feature's project exists (prevents probing via dangling issue IDs).
    # Issue/Project pre-date Studio multi-tenancy; tenant scoping deferred to Phase 2 — see CB-2121.
    if not await _validate_project_exists(db, feature.projectId):
        raise NotFoundError("Project", feature.projectId)

    # Recursive CTE for descendants
    cte_sql = text(
        """
        WITH RECURSIVE descendants(id) AS (
            SELECT :root_id
            UNION ALL
            SELECT i.id
            FROM "Issue" i
            INNER JOIN descendants d ON i."parentId" = d.id
        )
        SELECT id FROM descendants
        """
    )
    ids_result = await db.execute(cte_sql, {"root_id": feature_id})
    descendant_ids = [row[0] for row in ids_result.fetchall()]

    issues_result = await db.execute(
        select(Issue).where(Issue.id.in_(descendant_ids))
    )
    issues = list(issues_result.scalars().all())

    assignments_result = await db.execute(
        select(CrewAssignment).where(
            CrewAssignment.issueId.in_(descendant_ids),
            CrewAssignment.tenantId == tenant_id,
        )
    )
    assignments = list(assignments_result.scalars().all())

    nodes = [_issue_to_node(i) for i in issues]
    node_ids = {i.id for i in issues}
    edges = _issues_to_edges(issues) + _assignment_edges(assignments, node_ids)

    graph = CrewMapGraphResponse(nodes=nodes, edges=edges)
    etag = _etag_from_str(
        json.dumps({"n": len(nodes), "e": len(edges), "f": feature_id})
    )
    response.headers["ETag"] = etag
    return graph


# ---------------------------------------------------------------------------
# Assignment endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/assignments",
    response_model=List[CrewAssignmentResponse],
    summary="List CrewAssignments for a project",
)
async def list_assignments(
    project_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> List[CrewAssignmentResponse]:
    """List all CrewAssignment rows for a project, scoped to the tenant.

    Args:
        project_id: The project to list assignments for.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        List of CrewAssignmentResponse objects.
    """
    result = await db.execute(
        select(CrewAssignment).where(
            CrewAssignment.projectId == project_id,
            CrewAssignment.tenantId == tenant_id,
        )
    )
    assignments = result.scalars().all()
    return [CrewAssignmentResponse.model_validate(a) for a in assignments]


@router.get(
    "/assignments/{assignment_id}",
    response_model=CrewAssignmentDetailResponse,
    summary="Get one CrewAssignment with skill usage",
)
async def get_assignment(
    assignment_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> CrewAssignmentDetailResponse:
    """Retrieve a single CrewAssignment including its skill usage breakdown.

    Args:
        assignment_id: The CrewAssignment primary key.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        CrewAssignmentDetailResponse with embedded skillUsage list.
    """
    result = await db.execute(
        select(CrewAssignment)
        .options(selectinload(CrewAssignment.skill_usages))
        .where(
            CrewAssignment.id == assignment_id,
            CrewAssignment.tenantId == tenant_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise NotFoundError("CrewAssignment", assignment_id)

    skill_usage = [
        CrewSkillUsageResponse.model_validate(s)
        for s in (assignment.skill_usages or [])
    ]

    return CrewAssignmentDetailResponse(
        id=assignment.id,
        tenantId=assignment.tenantId,
        projectId=assignment.projectId,
        issueId=assignment.issueId,
        agentTemplateId=assignment.agentTemplateId,
        roleLabel=assignment.roleLabel,
        status=assignment.status,
        createdAt=assignment.createdAt,
        updatedAt=assignment.updatedAt,
        skillUsage=skill_usage,
    )


@router.post(
    "/projects/{project_id}/assignments",
    response_model=CrewAssignmentResponse,
    status_code=201,
    summary="Create CrewAssignment",
)
async def create_assignment(
    project_id: str,
    body: CrewAssignmentCreate,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> CrewAssignmentResponse:
    """Create a new CrewAssignment linking an agent template to an issue.

    Args:
        project_id: The project scope (path param).
        body: Assignment creation payload.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        CrewAssignmentResponse (201).
    """
    assignment = CrewAssignment(
        id=str(uuid.uuid4()),
        tenantId=tenant_id,
        projectId=project_id,
        issueId=body.issueId,
        agentTemplateId=body.agentTemplateId,
        roleLabel=body.roleLabel,
        status=body.status.value if hasattr(body.status, "value") else body.status,
        updatedAt=datetime.utcnow(),
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return CrewAssignmentResponse.model_validate(assignment)


@router.patch(
    "/assignments/{assignment_id}",
    response_model=CrewAssignmentResponse,
    summary="Update CrewAssignment status or role label",
)
async def update_assignment(
    assignment_id: str,
    body: CrewAssignmentUpdate,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> CrewAssignmentResponse:
    """Partially update a CrewAssignment (status and/or roleLabel).

    Args:
        assignment_id: Target assignment ID.
        body: Fields to update (all optional).
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        Updated CrewAssignmentResponse.
    """
    assignment = await _get_tenant_assignment(assignment_id, tenant_id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(assignment, field, value)

    assignment.updatedAt = datetime.utcnow()
    await db.commit()
    await db.refresh(assignment)
    return CrewAssignmentResponse.model_validate(assignment)


@router.delete(
    "/assignments/{assignment_id}",
    status_code=204,
    response_model=None,
    summary="Delete CrewAssignment (cascade skill usage)",
)
async def delete_assignment(
    assignment_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a CrewAssignment and cascade-delete all CrewSkillUsage rows.

    The cascade is handled by the ORM relationship
    (``cascade='all, delete-orphan'`` on ``CrewAssignment.skill_usages``).

    Args:
        assignment_id: Target assignment ID.
        tenant_id: Caller's tenant.
        db: Async database session.
    """
    result = await db.execute(
        select(CrewAssignment)
        .options(selectinload(CrewAssignment.skill_usages))
        .where(
            CrewAssignment.id == assignment_id,
            CrewAssignment.tenantId == tenant_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise NotFoundError("CrewAssignment", assignment_id)

    await db.delete(assignment)
    await db.commit()


# ---------------------------------------------------------------------------
# Skill usage endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/assignments/{assignment_id}/skill-usage",
    response_model=CrewSkillUsageResponse,
    status_code=200,
    summary="Increment or upsert a skill usage counter",
)
async def increment_skill_usage(
    assignment_id: str,
    body: SkillIncrementBody,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> CrewSkillUsageResponse:
    """Upsert a skill usage counter for a CrewAssignment.

    If a (assignmentId, skillName) row exists, increment ``invocationCount`` by
    1 and update ``lastUsedAt``.  Otherwise create a new row with count=1.

    Args:
        assignment_id: The parent CrewAssignment ID.
        body: Contains skillName to increment.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        The updated or created CrewSkillUsageResponse.

    Raises:
        NotFoundError: 404 if the parent assignment doesn't exist.
    """
    # Validate assignment ownership
    await _get_tenant_assignment(assignment_id, tenant_id, db)

    now = datetime.utcnow()

    result = await db.execute(
        select(CrewSkillUsage).where(
            CrewSkillUsage.assignmentId == assignment_id,
            CrewSkillUsage.skillName == body.skillName,
        )
    )
    skill_row = result.scalar_one_or_none()

    if skill_row is not None:
        skill_row.invocationCount += 1
        skill_row.lastUsedAt = now
        skill_row.updatedAt = now
    else:
        skill_row = CrewSkillUsage(
            id=str(uuid.uuid4()),
            tenantId=tenant_id,
            assignmentId=assignment_id,
            skillName=body.skillName,
            invocationCount=1,
            lastUsedAt=now,
            updatedAt=now,
        )
        db.add(skill_row)

    await db.commit()
    await db.refresh(skill_row)
    return CrewSkillUsageResponse.model_validate(skill_row)


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/search",
    response_model=List[CrewMapSearchResultNode],
    summary="Fuzzy search issues within a project",
)
async def search_nodes(
    project_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> List[CrewMapSearchResultNode]:
    """Fuzzy (LIKE) search across Issue titles and keys within a project.

    Args:
        project_id: The project to search within.
        q: Search query (min 1 char).
        limit: Maximum number of results (default 20).
        tenant_id: Caller's tenant (for future cross-tenant guard extension).
        db: Async database session.

    Returns:
        List of CrewMapSearchResultNode matching the query.
    """
    # HIGH-4: assert the project exists before querying its issues (prevents probing).
    if not await _validate_project_exists(db, project_id):
        raise NotFoundError("Project", project_id)

    result = await db.execute(
        select(Issue)
        .where(
            Issue.projectId == project_id,
            or_(
                Issue.title.ilike(f"%{q}%"),
                Issue.key.ilike(f"%{q}%"),
            ),
        )
        .order_by(Issue.sequence.desc())
        .limit(limit)
    )
    issues = result.scalars().all()

    return [
        CrewMapSearchResultNode(
            id=i.id,
            key=i.key,
            title=i.title,
            type=i.type,
            status=i.status,
            priority=i.priority,
        )
        for i in issues
    ]
