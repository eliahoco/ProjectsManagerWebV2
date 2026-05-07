"""
Documentation API Routes — read-only endpoints (CB-1588).

Exposes ExecutionSummary and ImplementationNote records produced by the
post-execution documentation pipeline (CB-1579) so the issue detail page
and downstream consumers can fetch them.

Sibling tasks layer additional surface on top of this router:
  - CB-1589: ImplementationNote create + delete (POST / DELETE)
  - CB-1590: FeatureDocumentation endpoints (GET / POST generate)
  - CB-1591: Export ImplementationNote model + register router in api/__init__.py
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppException, ErrorCode, NotFoundError
from models import (
    ExecutionSummary,
    ExecutionSummaryResponse,
    FeatureDocumentation,
    FeatureDocumentationResponse,
    Issue,
    get_db,
)
from models.documentation import ImplementationNote
from models.schemas import (
    ImplementationNoteCreate,
    ImplementationNoteResponse,
)
from services.documentation_generator import documentation_generator

logger = logging.getLogger(__name__)

router = APIRouter()


# CB-2117: every endpoint takes a required ``projectId`` query param so the
# id-only path lookups (``Issue.id == issue_id``) cannot be exploited for
# cross-project IDOR. The helpers below scope on ``(id, projectId)`` and
# return 404 on mismatch — caller-supplied projectId never widens the query.
ProjectIdQuery = Query(
    ...,
    alias="projectId",
    min_length=1,
    max_length=128,
    description=(
        "Project the issue belongs to. Required to scope lookups and "
        "block cross-project access via guessed issue ids (CB-2117)."
    ),
)


async def _ensure_issue_exists(
    db: AsyncSession, issue_id: str, project_id: str
) -> None:
    """Raise NotFoundError if the issue does not exist within ``project_id``.

    Distinguishes "issue missing" from "issue exists but has no docs yet" so
    callers can render the empty state without surfacing a 404 when the
    issue itself is fine. The ``projectId`` predicate is the IDOR guard
    (CB-2117) — a wrong projectId returns the same 404 as a missing id, so
    the response can never be used to enumerate the issue/project space.
    """
    result = await db.execute(
        select(Issue.id).where(
            Issue.id == issue_id,
            Issue.projectId == project_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Issue", issue_id)


@router.get(
    "/issues/{issue_id}/documentation",
    response_model=List[ExecutionSummaryResponse],
)
async def list_execution_summaries(
    issue_id: str,
    project_id: str = ProjectIdQuery,
    db: AsyncSession = Depends(get_db),
) -> List[ExecutionSummaryResponse]:
    """Return all ExecutionSummaries for an issue, newest first.

    404 only when the parent issue does not exist within ``projectId``. An
    issue with no summaries yet returns an empty list.
    """
    await _ensure_issue_exists(db, issue_id, project_id)

    result = await db.execute(
        select(ExecutionSummary)
        .where(ExecutionSummary.issueId == issue_id)
        .order_by(ExecutionSummary.executedAt.desc())
    )
    summaries = result.scalars().all()
    return [ExecutionSummaryResponse.model_validate(s) for s in summaries]


@router.get(
    "/issues/{issue_id}/documentation/latest",
    response_model=ExecutionSummaryResponse,
)
async def get_latest_execution_summary(
    issue_id: str,
    project_id: str = ProjectIdQuery,
    db: AsyncSession = Depends(get_db),
) -> ExecutionSummaryResponse:
    """Return the most recent ExecutionSummary for an issue.

    404 when the issue does not exist in ``projectId`` OR when the issue
    has no summaries — the caller wants a single record, so "no record"
    is a not-found.
    """
    await _ensure_issue_exists(db, issue_id, project_id)

    result = await db.execute(
        select(ExecutionSummary)
        .where(ExecutionSummary.issueId == issue_id)
        .order_by(ExecutionSummary.executedAt.desc())
        .limit(1)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise NotFoundError("ExecutionSummary", f"issue={issue_id}")

    return ExecutionSummaryResponse.model_validate(summary)


@router.get(
    "/issues/{issue_id}/documentation/notes",
    response_model=List[ImplementationNoteResponse],
)
async def list_implementation_notes(
    issue_id: str,
    project_id: str = ProjectIdQuery,
    db: AsyncSession = Depends(get_db),
) -> List[ImplementationNoteResponse]:
    """Return all ImplementationNotes for an issue, newest first.

    404 only when the parent issue does not exist within ``projectId``. An
    issue with no notes returns an empty list.
    """
    await _ensure_issue_exists(db, issue_id, project_id)

    result = await db.execute(
        select(ImplementationNote)
        .where(ImplementationNote.issueId == issue_id)
        .order_by(ImplementationNote.createdAt.desc())
    )
    notes = result.scalars().all()
    return [ImplementationNoteResponse.model_validate(n) for n in notes]


@router.post(
    "/issues/{issue_id}/documentation/notes",
    response_model=ImplementationNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_implementation_note(
    issue_id: str,
    payload: ImplementationNoteCreate,
    project_id: str = ProjectIdQuery,
    db: AsyncSession = Depends(get_db),
) -> ImplementationNoteResponse:
    """Create an ImplementationNote attached to an issue.

    The note ID is server-generated (uuid4) — callers must not supply one.
    Pydantic enums for category/importance reject invalid values up-front
    so the SQLite layer never sees a malformed enum string.

    ``projectId`` is required so that a caller cannot inject a 100 KB note
    into an arbitrary issue by guessing only its id (CB-2117).
    """
    await _ensure_issue_exists(db, issue_id, project_id)

    note = ImplementationNote(
        id=str(uuid.uuid4()),
        issueId=issue_id,
        title=payload.title,
        content=payload.content,
        category=payload.category.value,
        importance=payload.importance.value,
        tags=payload.tags,
        references=payload.references,
        author=payload.author or "System",
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    return ImplementationNoteResponse.model_validate(note)


@router.delete(
    "/issues/{issue_id}/documentation/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_implementation_note(
    issue_id: str,
    note_id: str,
    project_id: str = ProjectIdQuery,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an ImplementationNote.

    Validates the note belongs to the path's issue — prevents
    cross-issue deletes via guessed UUIDs even though IDs are unique
    globally. Returns 404 when the issue is missing in ``projectId`` or
    the note does not exist under that issue (CB-2117).
    """
    await _ensure_issue_exists(db, issue_id, project_id)

    result = await db.execute(
        select(ImplementationNote)
        .where(ImplementationNote.id == note_id)
        .where(ImplementationNote.issueId == issue_id)
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise NotFoundError("ImplementationNote", note_id)

    await db.delete(note)
    await db.commit()


# ---------------------------------------------------------------------------
# FeatureDocumentation endpoints (CB-1590)
# ---------------------------------------------------------------------------

class _BadRequestError(AppException):
    """400 BAD_REQUEST for FeatureDocumentation type-mismatch responses.

    Defined locally because `app.errors` exposes only NotFoundError /
    ValidationError as convenience subclasses. We need the 400 status code
    with a distinct `BAD_REQUEST` code field so the frontend can differentiate
    "issue exists but is not a feature" from validation errors.
    """

    def __init__(self, message: str):
        super().__init__(
            status_code=400,
            code=ErrorCode.BAD_REQUEST,
            message=message,
        )


async def _load_feature_issue(
    db: AsyncSession, issue_id: str, project_id: str
) -> Issue:
    """Return the FEATURE issue with this id under ``project_id`` or raise.

    404 when the issue does not exist in the given project. 400 when the
    issue exists but is not of type FEATURE — surfacing that distinction
    lets the caller redirect to the right context instead of seeing a
    misleading "not found".

    The ``projectId`` predicate is the IDOR guard (CB-2117): a caller
    cannot trigger the most expensive endpoint
    (POST /features/{id}/documentation/generate, which walks the descendant
    tree and calls the AI provider) on an arbitrary feature without
    asserting which project it belongs to.
    """
    result = await db.execute(
        select(Issue).where(
            Issue.id == issue_id,
            Issue.projectId == project_id,
        )
    )
    issue = result.scalar_one_or_none()
    if issue is None:
        raise NotFoundError("Issue", issue_id)
    if (issue.type or "").upper() != "FEATURE":
        raise _BadRequestError(
            f"Issue {issue.key or issue.id} is type {issue.type!r}, "
            f"not FEATURE — FeatureDocumentation only applies to features."
        )
    return issue


@router.get(
    "/features/{issue_id}/documentation",
    response_model=FeatureDocumentationResponse,
)
async def get_feature_documentation(
    issue_id: str,
    project_id: str = ProjectIdQuery,
    db: AsyncSession = Depends(get_db),
) -> FeatureDocumentationResponse:
    """Return the FeatureDocumentation row for a feature.

    404 when the issue is missing in ``projectId`` OR when no
    FeatureDocumentation has been generated yet — clients distinguish
    "feature exists but un-documented" by calling POST /generate. 400 when
    the issue exists but is not of type FEATURE.
    """
    feature = await _load_feature_issue(db, issue_id, project_id)

    result = await db.execute(
        select(FeatureDocumentation)
        .where(FeatureDocumentation.featureIssueId == feature.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError("FeatureDocumentation", f"feature={feature.key}")

    return FeatureDocumentationResponse.model_validate(doc)


@router.post(
    "/features/{issue_id}/documentation/generate",
    response_model=FeatureDocumentationResponse,
)
async def generate_feature_documentation_endpoint(
    issue_id: str,
    project_id: str = ProjectIdQuery,
    db: AsyncSession = Depends(get_db),
) -> FeatureDocumentationResponse:
    """Generate (or refresh) the FeatureDocumentation row for a feature.

    Calls `documentation_generator.generate_feature_documentation` which
    aggregates execution summaries, descendant counts, and QA results into
    a single FeatureDocumentation row, upserting on the natural key
    `featureIssueId`. The endpoint owns the transaction — the service
    flushes but never commits.

    ``projectId`` scoping (CB-2117) is critical here: this is the most
    expensive endpoint in the router (descendant walk + AI provider call),
    so requiring callers to assert the owning project blocks abuse via
    issue-id enumeration.
    """
    feature = await _load_feature_issue(db, issue_id, project_id)

    try:
        doc = await documentation_generator.generate_feature_documentation(
            db=db, feature=feature,
        )
    except ValueError as exc:
        # Service layer raises ValueError if the issue is somehow not a
        # FEATURE — already screened above, but keep the guard so a future
        # caller change cannot quietly produce a 500.
        raise _BadRequestError(str(exc)) from exc

    await db.commit()
    await db.refresh(doc)
    return FeatureDocumentationResponse.model_validate(doc)
