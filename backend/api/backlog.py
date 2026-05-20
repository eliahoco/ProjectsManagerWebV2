"""
Backlog API — CB-2384 Studio

CRUD + comment/activity/promote endpoints for BacklogItem resources.
All routes are scoped by tenantId (from TenantDep); cross-tenant access
returns 404 (not 403) to prevent tenant enumeration.

ETag format: W/"<sha256(id:updatedAt.isoformat())>"
Conditional writes: PATCH accepts If-Match; 412 on stale ETag.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import TenantDep
from app.errors import ConflictError, NotFoundError, ValidationError
from models import (
    BacklogActivity,
    BacklogComment,
    BacklogItem,
    get_db,
)
from models.schemas import (
    BacklogActivityResponse,
    BacklogCommentCreate,
    BacklogCommentResponse,
    BacklogItemCreate,
    BacklogItemResponse,
    BacklogItemUpdate,
    BacklogItemStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backlog", tags=["Backlog"])

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_etag(item_id: str, updated_at: datetime) -> str:
    """Compute a weak ETag for a BacklogItem.

    Args:
        item_id: The item's primary key.
        updated_at: The item's last-updated timestamp.

    Returns:
        A weak ETag string in W/"<hex>" format.
    """
    raw = f"{item_id}:{updated_at.isoformat()}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f'W/"{digest}"'


def _check_etag(
    item: BacklogItem,
    if_match: Optional[str],
) -> None:
    """Raise 412 if the request ETag doesn't match the resource ETag.

    Args:
        item: The current BacklogItem ORM instance.
        if_match: The If-Match header value from the request (may be None).

    Raises:
        HTTPException: 412 Precondition Failed when ETag mismatches.
    """
    if if_match is None:
        return
    current_etag = _compute_etag(item.id, item.updatedAt)
    # Strip surrounding quotes for flexible matching
    candidate = if_match.strip()
    if candidate not in (current_etag, current_etag.removeprefix('W/')):
        raise HTTPException(
            status_code=412,
            detail="Precondition Failed: ETag mismatch — resource has been modified",
        )


async def _get_tenant_item(
    item_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> BacklogItem:
    """Fetch a BacklogItem scoped to a tenant; 404 on miss or cross-tenant.

    Args:
        item_id: The BacklogItem primary key.
        tenant_id: The caller's resolved tenant identifier.
        db: Async SQLAlchemy session.

    Returns:
        The matching BacklogItem ORM instance.

    Raises:
        NotFoundError: When the item does not exist or belongs to another tenant.
    """
    result = await db.execute(
        select(BacklogItem).where(
            BacklogItem.id == item_id,
            BacklogItem.tenantId == tenant_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundError("BacklogItem", item_id)
    return item


async def _append_activity(
    db: AsyncSession,
    item_id: str,
    tenant_id: str,
    action: str,
    payload: Dict[str, Any],
    actor: str = "system",
) -> BacklogActivity:
    """Create and add a BacklogActivity row (not yet flushed).

    Args:
        db: The current SQLAlchemy session.
        item_id: FK → BacklogItem.id.
        tenant_id: Tenant scope for the activity row.
        action: Action label (e.g. "UPDATED", "COMMENTED", "PROMOTE_STARTED").
        payload: JSON-serialisable dict carrying action-specific data.
        actor: Who or what triggered the action.

    Returns:
        The newly created BacklogActivity ORM instance (not yet committed).
    """
    activity = BacklogActivity(
        id=str(uuid.uuid4()),
        tenantId=tenant_id,
        itemId=item_id,
        action=action,
        payload=payload,
        actor=actor,
    )
    db.add(activity)
    return activity


# ---------------------------------------------------------------------------
# Schedule validation helpers
# ---------------------------------------------------------------------------

# Minimal regex: m1-5 fields, each digit/*/range/step, separated by spaces.
_CRON_FIELD_RE = re.compile(
    r"^(\*|[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*|(\*/[0-9]+))"
)
_CRON_REGEX = re.compile(
    r"^\s*"
    r"(\*|[0-9\-,*/]+)\s+"   # minute
    r"(\*|[0-9\-,*/]+)\s+"   # hour
    r"(\*|[0-9\-,*/]+)\s+"   # day-of-month
    r"(\*|[0-9\-,*/]+)\s+"   # month
    r"(\*|[0-9\-,*/]+)"      # day-of-week
    r"\s*$"
)


def _validate_cron(expression: str):
    """Validate a cron expression using croniter if available, else regex.

    Args:
        expression: The cron expression string to validate.

    Returns:
        A tuple (valid: bool, next_firing: datetime | None, error: str | None).
    """
    try:
        from croniter import croniter  # type: ignore

        is_valid = croniter.is_valid(expression)
        if not is_valid:
            return False, None, "Invalid cron expression"
        now = datetime.now(tz=timezone.utc)
        it = croniter(expression, now)
        next_dt = it.get_next(datetime)
        return True, next_dt, None
    except ImportError:
        pass

    # Fallback: minimal regex
    if _CRON_REGEX.match(expression):
        return True, None, None
    return False, None, "Invalid cron expression (regex check failed)"


# ---------------------------------------------------------------------------
# Schemas specific to this router
# ---------------------------------------------------------------------------


class ValidateScheduleBody(BaseModel):
    cronExpression: Optional[str] = None
    scheduledFor: Optional[datetime] = None


class ValidateScheduleResponse(BaseModel):
    valid: bool
    nextFiring: Optional[datetime] = None
    error: Optional[str] = None


class PromoteJobStatusResponse(BaseModel):
    jobId: str
    itemId: str
    action: str  # PROMOTE_STARTED | PROMOTE_DONE | PROMOTE_FAILED
    payload: Dict[str, Any]
    createdAt: datetime


class PromoteAcceptedResponse(BaseModel):
    promoteJobId: str
    status: str


# ---------------------------------------------------------------------------
# BacklogItem CRUD endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/items",
    response_model=BacklogItemResponse,
    status_code=201,
    summary="Create BacklogItem",
)
async def create_backlog_item(
    project_id: str,
    body: BacklogItemCreate,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> BacklogItemResponse:
    """Create a new BacklogItem in a project.

    Args:
        project_id: The target project ID (path param).
        body: Creation payload.
        tenant_id: Resolved from X-Tenant-ID header or settings default.
        db: Async database session.

    Returns:
        The created BacklogItemResponse (201).
    """
    item = BacklogItem(
        id=str(uuid.uuid4()),
        tenantId=tenant_id,
        projectId=project_id,
        title=body.title,
        description=body.description,
        priority=body.priority.value if hasattr(body.priority, "value") else body.priority,
        status=body.status.value if hasattr(body.status, "value") else body.status,
        scheduledFor=body.scheduledFor,
        cronExpression=body.cronExpression,
        sourceSessionId=body.sourceSessionId,
        sourceArtifactId=body.sourceArtifactId,
        ownerEmail=body.ownerEmail,
    )
    db.add(item)

    await db.flush()  # get item.id before activity creation

    await _append_activity(
        db,
        item.id,
        tenant_id,
        "CREATED",
        {"title": item.title, "priority": item.priority, "status": item.status},
        actor="system",
    )

    await db.commit()
    await db.refresh(item)
    return BacklogItemResponse.model_validate(item)


@router.get(
    "/projects/{project_id}/items",
    response_model=List[BacklogItemResponse],
    summary="List BacklogItems",
)
async def list_backlog_items(
    project_id: str,
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> List[BacklogItemResponse]:
    """List BacklogItems for a project with optional filtering.

    Args:
        project_id: Project scope.
        status: Filter by status string.
        priority: Filter by priority string.
        search: Full-text search across title and description.
        limit: Max items to return (default 50).
        offset: Pagination offset.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        List of BacklogItemResponse objects sorted by createdAt DESC.
    """
    query = select(BacklogItem).where(
        and_(
            BacklogItem.projectId == project_id,
            BacklogItem.tenantId == tenant_id,
        )
    )

    if status:
        query = query.where(BacklogItem.status == status)
    if priority:
        query = query.where(BacklogItem.priority == priority)
    if search:
        query = query.where(
            or_(
                BacklogItem.title.ilike(f"%{search}%"),
                BacklogItem.description.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(BacklogItem.createdAt.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()
    return [BacklogItemResponse.model_validate(i) for i in items]


@router.get(
    "/items/{item_id}",
    response_model=BacklogItemResponse,
    summary="Get BacklogItem",
)
async def get_backlog_item(
    item_id: str,
    response: Response,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> BacklogItemResponse:
    """Retrieve a single BacklogItem by ID.

    Attaches an ETag header so clients can use If-Match on subsequent PATCHes.

    Args:
        item_id: The BacklogItem ID.
        response: FastAPI response object (for header injection).
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        BacklogItemResponse with ETag header.
    """
    item = await _get_tenant_item(item_id, tenant_id, db)
    response.headers["ETag"] = _compute_etag(item.id, item.updatedAt)
    return BacklogItemResponse.model_validate(item)


@router.patch(
    "/items/{item_id}",
    response_model=BacklogItemResponse,
    summary="Update BacklogItem",
)
async def update_backlog_item(
    item_id: str,
    body: BacklogItemUpdate,
    response: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> BacklogItemResponse:
    """Partially update a BacklogItem.

    Supports conditional writes via If-Match: <etag>; returns 412 on stale ETag.
    Appends a BacklogActivity row with action=UPDATED and a diff payload.

    Args:
        item_id: Target item ID.
        body: Fields to update (all optional).
        response: FastAPI response for ETag header.
        if_match: Optional request ETag for optimistic concurrency.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        Updated BacklogItemResponse with refreshed ETag.
    """
    item = await _get_tenant_item(item_id, tenant_id, db)
    _check_etag(item, if_match)

    update_data = body.model_dump(exclude_unset=True)
    diff: Dict[str, Any] = {}

    for field, new_value in update_data.items():
        old_value = getattr(item, field, None)
        # Resolve enum
        if hasattr(new_value, "value"):
            new_value = new_value.value
        if old_value != new_value:
            diff[field] = {"from": str(old_value), "to": str(new_value)}
            setattr(item, field, new_value)

    if diff:
        # onupdate=func.now() on the column handles updatedAt automatically.
        await _append_activity(
            db,
            item.id,
            tenant_id,
            "UPDATED",
            {"diff": diff},
            actor="system",
        )

    await db.commit()
    await db.refresh(item)
    response.headers["ETag"] = _compute_etag(item.id, item.updatedAt)
    return BacklogItemResponse.model_validate(item)


@router.delete(
    "/items/{item_id}",
    status_code=204,
    response_model=None,
    summary="Soft-delete BacklogItem",
)
async def delete_backlog_item(
    item_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a BacklogItem by setting status=ARCHIVED.

    Args:
        item_id: Target item ID.
        tenant_id: Caller's tenant.
        db: Async database session.
    """
    item = await _get_tenant_item(item_id, tenant_id, db)

    item.status = BacklogItemStatus.ARCHIVED.value
    # onupdate=func.now() handles updatedAt automatically.

    await _append_activity(
        db,
        item.id,
        tenant_id,
        "ARCHIVED",
        {},
        actor="system",
    )

    await db.commit()


# ---------------------------------------------------------------------------
# Comments endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/items/{item_id}/comments",
    response_model=BacklogCommentResponse,
    status_code=201,
    summary="Add comment to BacklogItem",
)
async def create_comment(
    item_id: str,
    body: BacklogCommentCreate,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> BacklogCommentResponse:
    """Add a comment to a BacklogItem.

    Also appends a BacklogActivity row with action=COMMENTED.

    Args:
        item_id: The parent BacklogItem ID.
        body: Comment creation payload.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        BacklogCommentResponse (201).
    """
    item = await _get_tenant_item(item_id, tenant_id, db)

    comment = BacklogComment(
        id=str(uuid.uuid4()),
        tenantId=tenant_id,
        itemId=item.id,
        author=body.author,
        content=body.content,
        # onupdate=func.now() handles updatedAt automatically.
    )
    db.add(comment)

    await _append_activity(
        db,
        item.id,
        tenant_id,
        "COMMENTED",
        {"author": body.author, "contentPreview": body.content[:200]},
        actor=body.author,
    )

    # Touch item so its updatedAt is refreshed by onupdate trigger.
    item.title = item.title  # noqa: SIM005 — force SQLAlchemy to mark row dirty

    await db.commit()
    await db.refresh(comment)
    return BacklogCommentResponse.model_validate(comment)


@router.get(
    "/items/{item_id}/comments",
    response_model=List[BacklogCommentResponse],
    summary="List comments on BacklogItem",
)
async def list_comments(
    item_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> List[BacklogCommentResponse]:
    """Return all comments on a BacklogItem (newest first).

    Args:
        item_id: Parent BacklogItem ID.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        List of BacklogCommentResponse sorted by createdAt DESC.
    """
    # Verify item existence + tenant scope first
    await _get_tenant_item(item_id, tenant_id, db)

    result = await db.execute(
        select(BacklogComment)
        .where(
            BacklogComment.itemId == item_id,
            BacklogComment.tenantId == tenant_id,
        )
        .order_by(BacklogComment.createdAt.desc())
    )
    comments = result.scalars().all()
    return [BacklogCommentResponse.model_validate(c) for c in comments]


# ---------------------------------------------------------------------------
# Activity endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/items/{item_id}/activity",
    response_model=List[BacklogActivityResponse],
    summary="Activity log for BacklogItem",
)
async def list_activity(
    item_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> List[BacklogActivityResponse]:
    """Return the full append-only audit trail for a BacklogItem.

    Args:
        item_id: Target item ID.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        List of BacklogActivityResponse, oldest first.
    """
    await _get_tenant_item(item_id, tenant_id, db)

    result = await db.execute(
        select(BacklogActivity)
        .where(
            BacklogActivity.itemId == item_id,
            BacklogActivity.tenantId == tenant_id,
        )
        .order_by(BacklogActivity.createdAt.asc())
    )
    activities = result.scalars().all()
    return [BacklogActivityResponse.model_validate(a) for a in activities]


# ---------------------------------------------------------------------------
# Promote endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/items/{item_id}/promote",
    status_code=202,
    response_model=PromoteAcceptedResponse,
    summary="Promote BacklogItem to CodeBoard",
)
async def promote_item(
    item_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> PromoteAcceptedResponse:
    """Initiate promotion of a BacklogItem to a CodeBoard feature hierarchy.

    The item must be in APPROVED status. Synchronously:
      1. Validates status
      2. Transitions item to PROMOTED
      3. Generates a promoteJobId
      4. Writes BacklogActivity action=PROMOTE_STARTED

    The actual pipeline work is deferred to
    ``services.backlog_promoter.start_promote`` (stub fires PROMOTE_DONE after
    100ms).

    Args:
        item_id: Target BacklogItem ID.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        202 Accepted with promoteJobId and status="queued".

    Raises:
        ConflictError: 409 if item is not in APPROVED status.
        NotFoundError: 404 if item not found or wrong tenant.
    """
    from services.backlog_promoter import start_promote  # deferred import

    item = await _get_tenant_item(item_id, tenant_id, db)

    if item.status != BacklogItemStatus.APPROVED.value:
        raise ConflictError(
            f"BacklogItem must be in APPROVED status to promote (current: {item.status})"
        )

    job_id = str(uuid.uuid4())

    item.status = BacklogItemStatus.PROMOTED.value
    item.promoteJobId = job_id
    # onupdate=func.now() handles updatedAt automatically.

    await _append_activity(
        db,
        item.id,
        tenant_id,
        "PROMOTE_STARTED",
        {"promoteJobId": job_id},
        actor="system",
    )

    await db.commit()

    # Fire-and-forget — don't await; the stub writes PROMOTE_DONE after 100ms
    asyncio.ensure_future(start_promote(item_id, job_id, db))

    return PromoteAcceptedResponse(promoteJobId=job_id, status="queued")


@router.get(
    "/items/{item_id}/promote-jobs/{job_id}",
    response_model=PromoteJobStatusResponse,
    summary="Get promote job status",
)
async def get_promote_job(
    item_id: str,
    job_id: str,
    tenant_id: str = TenantDep,
    db: AsyncSession = Depends(get_db),
) -> PromoteJobStatusResponse:
    """Return the latest BacklogActivity row matching a promote job ID.

    Args:
        item_id: The BacklogItem that was promoted.
        job_id: The promoteJobId returned by POST /promote.
        tenant_id: Caller's tenant.
        db: Async database session.

    Returns:
        PromoteJobStatusResponse with the latest PROMOTE_* activity.

    Raises:
        NotFoundError: 404 if no matching activity exists.
    """
    await _get_tenant_item(item_id, tenant_id, db)

    result = await db.execute(
        select(BacklogActivity)
        .where(
            BacklogActivity.itemId == item_id,
            BacklogActivity.tenantId == tenant_id,
            BacklogActivity.payload["promoteJobId"].as_string() == job_id,
        )
        .order_by(BacklogActivity.createdAt.desc())
        .limit(1)
    )
    activity = result.scalar_one_or_none()

    if activity is None:
        raise NotFoundError("PromoteJob", job_id)

    return PromoteJobStatusResponse(
        jobId=job_id,
        itemId=item_id,
        action=activity.action,
        payload=activity.payload or {},
        createdAt=activity.createdAt,
    )


# ---------------------------------------------------------------------------
# Schedule validation (no DB, < 100ms)
# ---------------------------------------------------------------------------


@router.post(
    "/validate-schedule",
    response_model=ValidateScheduleResponse,
    summary="Validate cron or one-shot schedule",
)
async def validate_schedule(
    body: ValidateScheduleBody,
) -> ValidateScheduleResponse:
    """Validate a schedule expression without touching the database.

    Handles two mutually exclusive modes:
    - ``cronExpression``: validated via croniter (if installed) or minimal regex.
    - ``scheduledFor``: validated as a parseable datetime (ISO 8601).

    Must respond in < 100ms — no DB I/O.

    Args:
        body: Contains optional cronExpression and/or scheduledFor.

    Returns:
        ValidateScheduleResponse with valid flag, optional nextFiring, and error.
    """
    if body.cronExpression:
        valid, next_firing, error = _validate_cron(body.cronExpression)
        return ValidateScheduleResponse(
            valid=valid,
            nextFiring=next_firing,
            error=error,
        )

    if body.scheduledFor is not None:
        # Ensure it's in the future
        now = datetime.now(tz=timezone.utc)
        scheduled = body.scheduledFor
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        if scheduled <= now:
            return ValidateScheduleResponse(
                valid=False,
                error="scheduledFor must be a future datetime",
            )
        return ValidateScheduleResponse(
            valid=True,
            nextFiring=scheduled,
        )

    return ValidateScheduleResponse(
        valid=False,
        error="Provide either cronExpression or scheduledFor",
    )
