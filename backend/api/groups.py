"""
Issue Groups API — named clusters of issues within a project (CB-1955 / EPIC CB-1982).

Implements `/api/projects/{project_id}/groups` and `/api/groups/{group_id}` per
the api-designer contract. This module currently ships POST create (CB-1984);
the GET list / GET detail / DELETE siblings (CB-1985..CB-1987) extend the same
router.

Group semantics:
  * A group is a *project-scoped* cluster — every member must belong to the
    same project as the group. Cross-project membership is rejected at write
    time (400) so the aggregate-status helper (compute_group_status) and
    every list/detail endpoint can assume single-project rows without
    re-validating.
  * Aggregate status (statusBreakdown / completionPercent / dominantStatus)
    is computed on read by the CB-1958 helper — there is no stored column.
    This endpoint therefore returns IssueGroupResponse (group summary only),
    not IssueGroupDetailResponse.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import and_, delete as sa_delete, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import (
    AlreadyExistsError,
    ConflictError,
    DatabaseError,
    NotFoundError,
    ValidationError,
)
from models import (
    Issue,
    IssueGroup,
    IssueGroupCreate,
    IssueGroupDetailResponse,
    IssueGroupMember,
    IssueGroupMemberResponse,
    IssueGroupMembersBulkAdd,
    IssueGroupMembersBulkAddResponse,
    IssueGroupMembersBulkRemove,
    IssueGroupMembersBulkRemoveResponse,
    IssueGroupMembersReorder,
    IssueGroupMembersReorderResponse,
    IssueGroupResponse,
    IssueSummary,
    PaginatedGroupResponse,
    Project,
    get_db,
    next_member_position,
)
from utils.db_queries import compute_group_status
from utils.validators import validate_same_project_members

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/projects/{project_id}/groups",
    response_model=IssueGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    project_id: str,
    payload: IssueGroupCreate,
    db: AsyncSession = Depends(get_db),
) -> IssueGroupResponse:
    """Create a new IssueGroup within ``project_id``.

    Body: ``{title, description?, issueIds?}`` — see IssueGroupCreate.
    ``issueIds`` is the optional initial-member list; the schema dedupes and
    caps the list at 500 entries, anything bigger is the GET-list / future
    bulk-add endpoint's domain.

    Member position (CB-1965) is assigned 1..N in the caller-supplied (and
    schema-deduped) order — the loop computes positions in Python rather
    than calling ``next_member_position`` per row, because that helper reads
    committed rows only and would assign every row the same `1` inside one
    transaction (see same-session pitfall on `next_member_position`).

    Errors:
      * 400 VALIDATION_ERROR — one or more ``issueIds`` belong to a
        different project. ``details.invalidIssueIds`` lists every offender
        so the caller can fix the whole list in one edit.
      * 404 NOT_FOUND — ``project_id`` doesn't exist, OR any ``issueIds``
        entry doesn't exist. Missing-issue 404 takes precedence over
        cross-project 400 because the caller's id list is wrong before we
        can even check projects.
      * 422 — payload shape (Pydantic): empty title, oversized list,
        non-string ids, etc.

    Response: ``IssueGroupResponse`` with ``memberCount`` set from the
    inserted membership count. Aggregate status is intentionally NOT
    included (clients that need it call the detail endpoint, CB-1986).
    """
    # 1. Project must exist (404). Single-column SELECT — we don't need the
    #    full Project row, just confirmation it's there. The check runs
    #    before payload validation so a caller hitting a stale URL gets a
    #    clean 404 instead of a misleading 400 from an unrelated id check.
    project_row = (await db.execute(
        select(Project.id).where(Project.id == project_id)
    )).first()
    if project_row is None:
        raise NotFoundError("Project", project_id)

    # 2. Validate member ids (when supplied) — existence + same-project.
    #    Delegated to the shared helper (CB-1992) so this endpoint and
    #    add_group_members stay in lock-step on the 404/400 precedence
    #    and the cross-project ``details`` envelope. The helper is a
    #    no-op on an empty list, so we pass payload.issueIds directly.
    issue_ids = list(payload.issueIds or [])
    await validate_same_project_members(db, project_id, issue_ids)

    # 3. Create group + members in a single transaction. Position is the
    #    1-based ordinal in caller order (CB-1965). We compute positions in
    #    Python rather than calling next_member_position per row because
    #    the helper reads committed rows only — calling it in a loop would
    #    assign every member position=1 since none of the inserts have
    #    flushed yet (see grouping.py:135 same-session pitfall).
    group_id = str(uuid.uuid4())
    group = IssueGroup(
        id=group_id,
        projectId=project_id,
        title=payload.title,
        description=payload.description,
    )
    db.add(group)

    for position, issue_id in enumerate(issue_ids, start=1):
        db.add(IssueGroupMember(
            id=str(uuid.uuid4()),
            groupId=group_id,
            issueId=issue_id,
            position=position,
        ))

    try:
        await db.commit()
    except IntegrityError as exc:
        # The (groupId, issueId) UNIQUE can't fire on a fresh group_id, and
        # the FK-on-Issue is checked at validation time above. The only
        # realistic IntegrityError path here is a concurrent issue delete
        # between validation and commit (TOCTOU window). The IssueGroupMember
        # row will not insert because the FK-on-issueId resolves to a
        # missing parent. Roll back, log with traceback at ERROR (this is a
        # real anomaly, not a routine race), and surface as 500
        # DATABASE_ERROR so the response carries a typed code instead of the
        # generic INTERNAL_ERROR an unwrapped IntegrityError would yield.
        # %r escapes control chars in user-supplied IDs (CRLF log injection).
        await db.rollback()
        logger.exception(
            "IntegrityError on group create project=%r members=%d: %s",
            project_id, len(issue_ids), exc,
        )
        raise DatabaseError(
            "Could not create group due to a concurrent change",
            details={"projectId": project_id, "memberCount": len(issue_ids)},
        )

    # 4. Refresh the group so server-side defaults (createdAt / updatedAt)
    #    populate on the in-memory ORM object. Without this, IssueGroupResponse
    #    validation would fail on the NOT NULL datetime fields.
    await db.refresh(group)

    # 5. memberCount is populated via setattr per the IssueGroupResponse
    #    contract (no ORM column). We just inserted len(issue_ids) members
    #    with a fresh group_id, so the count is exactly that — no need for
    #    a follow-up COUNT() round-trip.
    setattr(group, "memberCount", len(issue_ids))
    return IssueGroupResponse.model_validate(group)


# Hard cap on per-page rows for the list endpoint (CB-1985). Each row carries
# a `memberCount` aggregate computed via outer-join + GROUP BY in a single
# query, so the cost per page is roughly O(pageSize) — not the size of the
# project's group catalog. 100 mirrors the relations list cap (CB-1973) so
# the frontend can reuse one pagination component for both.
_GROUP_LIST_MAX_PAGE_SIZE = 100
_GROUP_LIST_DEFAULT_PAGE_SIZE = 50


@router.get(
    "/projects/{project_id}/groups",
    response_model=PaginatedGroupResponse,
)
async def list_groups(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(
        _GROUP_LIST_DEFAULT_PAGE_SIZE,
        ge=1,
        le=_GROUP_LIST_MAX_PAGE_SIZE,
        alias="pageSize",
    ),
    search: str | None = Query(
        None, max_length=500,
        description="Case-insensitive substring match on title or description.",
    ),
    db: AsyncSession = Depends(get_db),
) -> PaginatedGroupResponse:
    """List groups for ``project_id`` with pagination.

    Returns ``PaginatedGroupResponse`` — each item is the group summary
    (``IssueGroupResponse``) with ``memberCount`` populated. Members are NOT
    embedded; clients that need the membership list call the detail
    endpoint (CB-1986).

    Ordering is ``createdAt DESC, id DESC`` — newest first, deterministic on
    timestamp ties so the response is stable across repeated reads.

    `search` (optional) performs a case-insensitive substring match on
    title OR description. The 500-char cap matches the title field width;
    longer queries return 422 from FastAPI/Pydantic before hitting the DB.

    Errors:
      * 404 NOT_FOUND — ``project_id`` does not exist. Returning 404 here
        (instead of an empty list) matches the POST contract (CB-1984) and
        prevents a stale URL from silently looking like an empty project.
      * 422 — ``page`` < 1, ``pageSize`` outside [1, 100], or ``search``
        longer than 500 chars (FastAPI/Pydantic).

    `memberCount` is computed via a single outer-join + GROUP BY against
    ``IssueGroupMember.groupId`` — O(pageSize) per request rather than one
    COUNT round-trip per group. The outer join keeps empty groups in the
    result with ``memberCount = 0``.
    """
    # 1. Project must exist (404). Cheap single-column SELECT — same pattern
    #    as create_group, kept consistent so a stale URL produces a clean
    #    404 instead of an empty list that hides the typo.
    project_row = (await db.execute(
        select(Project.id).where(Project.id == project_id)
    )).first()
    if project_row is None:
        raise NotFoundError("Project", project_id)

    # 2. Build the base filter once, reuse for both COUNT and items query
    #    so they stay in sync when filters evolve.
    filters = [IssueGroup.projectId == project_id]
    if search:
        # ilike with %{search}% — same substring pattern issues.py uses for
        # its title/description search (issues.py:300). SQLite ilike is
        # case-insensitive on ASCII; the pattern uses %s parameters so the
        # search string can't break out into SQL. The 500-char cap on the
        # query param keeps the LIKE pattern bounded.
        like = f"%{search}%"
        filters.append(or_(
            IssueGroup.title.ilike(like),
            IssueGroup.description.ilike(like),
        ))

    # 3. Total row count for pagination metadata. Filter-only — the GROUP
    #    BY for memberCount happens on the items query; counting rows
    #    doesn't need to know membership counts.
    total_result = await db.execute(
        select(func.count()).select_from(IssueGroup).where(*filters)
    )
    total = int(total_result.scalar() or 0)

    # 4. Items query: outer-join to IssueGroupMember and group by IssueGroup
    #    columns so each row carries its own COUNT(member). Outer join keeps
    #    empty groups (count = 0). GROUP BY on the PK is enough — the other
    #    IssueGroup columns are functionally dependent and SQLite tolerates
    #    a partial GROUP BY list, but we list all selected non-aggregate
    #    columns explicitly to stay portable across PostgreSQL too (the
    #    project may swap engines later).
    offset = (page - 1) * page_size
    items_query = (
        select(
            IssueGroup,
            func.count(IssueGroupMember.id).label("member_count"),
        )
        .outerjoin(
            IssueGroupMember,
            IssueGroupMember.groupId == IssueGroup.id,
        )
        .where(*filters)
        .group_by(
            IssueGroup.id,
            IssueGroup.projectId,
            IssueGroup.title,
            IssueGroup.description,
            IssueGroup.createdAt,
            IssueGroup.updatedAt,
        )
        # Newest first; id breaks createdAt ties so paging is deterministic.
        .order_by(IssueGroup.createdAt.desc(), IssueGroup.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(items_query)).all()

    # 5. Hydrate IssueGroupResponse for each row. memberCount is set via
    #    setattr per the schema contract (no ORM column; see
    #    IssueGroupResponse docstring) before model_validate.
    items: list[IssueGroupResponse] = []
    for group, member_count in rows:
        setattr(group, "memberCount", int(member_count))
        items.append(IssueGroupResponse.model_validate(group))

    return PaginatedGroupResponse(
        items=items,
        total=total,
        page=page,
        pageSize=page_size,
        # Ceil division: matches issues.py:385 pattern. With total=0 this
        # gives 0, which is what the frontend pagination component expects.
        totalPages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get(
    "/groups/{group_id}",
    response_model=IssueGroupDetailResponse,
)
async def get_group_detail(
    group_id: str,
    db: AsyncSession = Depends(get_db),
) -> IssueGroupDetailResponse:
    """Return a single group + full member list + computed aggregate status.

    Members are eager-loaded with their embedded issue summary and ordered by
    ``(position ASC, id ASC)`` — the relationship's declared order — so the
    response is deterministic even when two members share a `position`
    (see same-position race documented on `next_member_position`).

    Aggregate status is computed on read by `compute_group_status` (CB-1958).
    Empty groups return ``aggregateStatus`` defaults: ``{}``, 0.0, None.

    Errors:
      * 404 NOT_FOUND — ``group_id`` does not exist.

    The `IssueGroupMember.issue` relationship is configured with
    ``lazy="raise_on_sql"`` so accessing it without an explicit eager load
    would raise mid-serialization. Two-level selectinload keeps the read to
    three round trips: group, members (one IN clause), member issues
    (one IN clause).
    """
    # 1. Load the group with members + each member's issue summary in one
    #    eager load. selectinload is mandatory because IssueGroupMember.issue
    #    has lazy="raise_on_sql" — a bare lazy access during model_validate
    #    would surface as a 500 in async context.
    result = await db.execute(
        select(IssueGroup)
        .where(IssueGroup.id == group_id)
        .options(
            selectinload(IssueGroup.members).selectinload(IssueGroupMember.issue),
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise NotFoundError("IssueGroup", group_id)

    # 2. Build the member list ordered by (position, id) to match the
    #    relationship contract. The relationship is already declared with
    #    that order, but SQLAlchemy's selectinload doesn't always preserve
    #    the order_by on the loaded collection across dialects — explicit
    #    sort here makes the API contract a Python-level guarantee.
    sorted_members = sorted(
        group.members, key=lambda m: (m.position, m.id),
    )
    members_payload = [
        IssueGroupMemberResponse(
            id=m.id,
            groupId=m.groupId,
            issueId=m.issueId,
            position=m.position,
            createdAt=m.createdAt,
            # `m.issue` is None only if a future migration switches the
            # IssueGroupMember.issueId FK away from ondelete=CASCADE — under
            # the current schema (grouping.py:91) an orphaned member is
            # impossible because deleting the issue cascades the row. The
            # `if m.issue else None` guard is defense-in-depth so a schema
            # drift surfaces as a None summary, not a 500 from
            # IssueSummary.model_validate(None).
            issue=IssueSummary.model_validate(m.issue) if m.issue else None,
        )
        for m in sorted_members
    ]

    # 3. Aggregate status — single GROUP BY against IssueGroupMember + Issue.
    #    Authorization note (db_queries.py:1046): the helper does NOT scope
    #    by project; we already loaded the group by id, so any caller who
    #    can hit the route can read this aggregate. There's no project-level
    #    auth in this app today, so the helper's IDOR caveat doesn't apply.
    #
    #    Perf note: this re-reads IssueGroupMember + Issue with a GROUP BY
    #    even though we already eager-loaded the same rows above. Kept as a
    #    helper call so compute_group_status remains the single source of
    #    truth for the aggregate-status contract (CB-1958) — every consumer
    #    must agree on the dominantStatus tie-break and CANCELLED-in-the-
    #    denominator semantics. Total cost is one extra GROUP BY query;
    #    membership is capped at 500 so the row count stays bounded.
    aggregate = await compute_group_status(db, group_id)

    return IssueGroupDetailResponse(
        id=group.id,
        projectId=group.projectId,
        title=group.title,
        description=group.description,
        createdAt=group.createdAt,
        updatedAt=group.updatedAt,
        members=members_payload,
        aggregateStatus=aggregate,
    )


# Reader-rule status constant (CB-1987 / Web Security p. 15). Centralised so
# the delete-group guard, future bulk-add, and any other reader-rule consumer
# all agree on the live-work predicate. The codebase already uses raw status
# strings (compute_group_status, cascade_status_to_parents) — keep that
# convention here rather than introducing an enum import drift.
_LIVE_WORK_STATUS = "IN_PROGRESS"


@router.delete(
    "/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete an IssueGroup; cascade ``IssueGroupMember`` rows. Issues survive.

    Reader-rule guard (CB-1987 / Web Security p. 15): refuse the delete with
    409 CONFLICT if any current member is still ``IN_PROGRESS``. The intent
    is that a group cannot be silently dissolved while live work references
    it — a reader expects an in-flight item's grouping context to remain
    intact until the work itself is complete or cancelled. The 409 surfaces
    every offending member id+key in ``details`` so the caller can either
    finish/cancel them or remove them from the group before retrying.

    The cascade itself is handled by the FK
    ``IssueGroupMember.groupId ON DELETE CASCADE`` (grouping.py:85). Issues
    are NOT touched — ``IssueGroupMember.issueId`` has no inverse cascade
    back to ``Issue``.

    Concurrency / TOCTOU: the IN_PROGRESS guard is fused into the DELETE's
    WHERE clause (``NOT EXISTS (SELECT 1 FROM IssueGroupMember m JOIN Issue
    i ON m.issueId = i.id WHERE m.groupId = :id AND i.status =
    'IN_PROGRESS')``) so a member transitioning into IN_PROGRESS between
    the existence check and the DELETE cannot slip through. If the
    fused-DELETE matches zero rows we re-scan inside the same transaction
    to disambiguate the cause (group genuinely gone vs. a member just
    flipped to IN_PROGRESS) and raise the corresponding 404 / 409.

    Errors:
      * 404 NOT_FOUND — ``group_id`` does not exist (or vanished between
        the SELECT and the DELETE due to a concurrent delete; surfaced as
        404 so the caller sees a consistent "gone" outcome regardless of
        who won the race).
      * 409 CONFLICT — at least one member is in ``IN_PROGRESS``. ``details``
        carries ``{groupId, inProgressIssueIds, inProgressIssueKeys}``.

    Response:
      * 204 No Content — group + member rows removed.
    """
    # 1. Verify the group exists up-front so a stale URL returns 404 rather
    #    than falling through to a no-op DELETE (rowcount=0) that would be
    #    indistinguishable from a successful delete on the wire. Same
    #    cheap single-column pattern as get_group_detail / list_groups.
    group_row = (await db.execute(
        select(IssueGroup.id).where(IssueGroup.id == group_id)
    )).first()
    if group_row is None:
        raise NotFoundError("IssueGroup", group_id)

    # 2. Atomic guard + delete: the DELETE only fires when NO member of the
    #    group is in IN_PROGRESS. Fusing the predicate into the DELETE
    #    closes the TOCTOU window between a separate SELECT-then-DELETE —
    #    a concurrent BACKLOG → IN_PROGRESS transition committed between
    #    the two statements would otherwise let the cascade silently drop
    #    a live-work member (defeating the reader rule). The cascade
    #    itself is FK-driven (IssueGroupMember.groupId ON DELETE CASCADE,
    #    grouping.py:85) — no second statement needed for membership
    #    rows.
    in_progress_subq = (
        select(IssueGroupMember.id)
        .join(Issue, Issue.id == IssueGroupMember.issueId)
        .where(
            IssueGroupMember.groupId == group_id,
            Issue.status == _LIVE_WORK_STATUS,
        )
    )
    delete_result = await db.execute(
        sa_delete(IssueGroup).where(
            and_(
                IssueGroup.id == group_id,
                ~exists(in_progress_subq),
            )
        )
    )

    if (delete_result.rowcount or 0) == 0:
        # Either the group was concurrently deleted (404) or a member just
        # transitioned into IN_PROGRESS and the guard correctly suppressed
        # the DELETE (409). Re-scan inside the same transaction to pick
        # the right disposition. We rollback first so the failed-DELETE
        # statement is closed before the diagnostic SELECTs run.
        await db.rollback()
        still_there = (await db.execute(
            select(IssueGroup.id).where(IssueGroup.id == group_id)
        )).first()
        if still_there is None:
            raise NotFoundError("IssueGroup", group_id)

        # Group still exists → the IN_PROGRESS guard is what blocked us.
        # Enumerate the offenders for the 409 details payload. No LIMIT —
        # membership is capped at 500 by the create endpoint, so the
        # offender list is bounded by design.
        in_progress_rows = (await db.execute(
            select(Issue.id, Issue.key)
            .join(IssueGroupMember, IssueGroupMember.issueId == Issue.id)
            .where(
                IssueGroupMember.groupId == group_id,
                Issue.status == _LIVE_WORK_STATUS,
            )
        )).all()
        # Defensive: if the second-scan finds no offenders (the IN_PROGRESS
        # member just flipped back out between the failed DELETE and this
        # re-scan), fall through to a fresh DELETE attempt would invite an
        # unbounded retry loop. Surface as 409 with an empty list rather
        # than retrying — the caller's view ("delete blocked") matches
        # what was true a moment ago and a retry will succeed cleanly.
        raise ConflictError(
            "Cannot delete group while members are IN_PROGRESS",
            details={
                "groupId": group_id,
                "inProgressIssueIds": [r[0] for r in in_progress_rows],
                "inProgressIssueKeys": [r[1] for r in in_progress_rows],
            },
        )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/groups/{group_id}/members",
    response_model=IssueGroupMembersBulkAddResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_members(
    group_id: str,
    payload: IssueGroupMembersBulkAdd,
    db: AsyncSession = Depends(get_db),
) -> IssueGroupMembersBulkAddResponse:
    """Bulk-add members to ``group_id``.

    Body: ``{issueIds: [str]}`` — see IssueGroupMembersBulkAdd. The schema
    dedupes within the request and caps the list at 500. Issues that are
    already members of the group are silently skipped (the
    UNIQUE(groupId, issueId) constraint would otherwise fire); they are
    surfaced in ``skipped`` so the caller can distinguish "added" from
    "no-op" without a follow-up GET.

    Errors:
      * 400 VALIDATION_ERROR — one or more ``issueIds`` belong to a
        different project than the group. ``details.invalidIssueIds`` lists
        every offender so the caller can fix the whole list in one edit.
      * 404 NOT_FOUND — ``group_id`` doesn't exist, OR any ``issueIds``
        entry doesn't exist. Missing-issue 404 takes precedence over
        cross-project 400 (the caller's id list is wrong before we can
        even check projects), mirroring the create-group contract
        (CB-1984).
      * 422 — payload shape (Pydantic): empty list, oversized list,
        non-string ids, etc.

    Response: ``{added: [issueId], skipped: [issueId]}`` — both lists
    preserve the deduped request order so the caller can correlate against
    their input.

    Position assignment (CB-1965): new members are appended to the end of
    the group's existing ordering. We compute the base
    (``next_member_position``) once and increment in Python — the helper
    reads committed rows only, so calling it per row would assign every
    insert the same position (see grouping.py:135 same-session pitfall).

    Position counts only ``added`` rows (skipped issues already have a
    position from when they were originally added; we don't renumber).
    """
    # 1. Group must exist (404). We need projectId to validate cross-project
    #    membership, so fetch both columns up-front rather than separate
    #    existence + project SELECTs.
    group_row = (await db.execute(
        select(IssueGroup.id, IssueGroup.projectId)
        .where(IssueGroup.id == group_id)
    )).first()
    if group_row is None:
        raise NotFoundError("IssueGroup", group_id)
    group_project_id = group_row[1]

    # 2. Validate member ids: existence + same-project. Delegated to the
    #    shared helper (CB-1992) so this endpoint and create_group stay
    #    in lock-step on 404/400 precedence and ``details`` envelope.
    #    Passing group_id makes the cross-project payload include the
    #    groupId field per the add-members contract.
    issue_ids = list(payload.issueIds)
    await validate_same_project_members(
        db, group_project_id, issue_ids, group_id=group_id,
    )

    # 3. Detect already-members in a single round-trip. The
    #    UNIQUE(groupId, issueId) would catch this at INSERT time, but we
    #    skip silently per the contract — pre-screening lets us partition
    #    {added, skipped} cleanly and avoid an IntegrityError-driven
    #    rollback for a routine no-op.
    existing_rows = (await db.execute(
        select(IssueGroupMember.issueId).where(
            IssueGroupMember.groupId == group_id,
            IssueGroupMember.issueId.in_(issue_ids),
        )
    )).all()
    already_members: set[str] = {row[0] for row in existing_rows}

    # 4. Partition into accepted vs skipped, preserving request order.
    accepted: list[str] = []
    skipped: list[str] = []
    for iid in issue_ids:
        if iid in already_members:
            skipped.append(iid)
        else:
            accepted.append(iid)

    # 5. Insert accepted rows. Compute the position base once and increment
    #    in Python to avoid the same-session pitfall (next_member_position
    #    sees committed state only — calling it per row would hand every
    #    new member the same position).
    if accepted:
        base = await next_member_position(db, group_id)
        for offset_, issue_id in enumerate(accepted):
            db.add(IssueGroupMember(
                id=str(uuid.uuid4()),
                groupId=group_id,
                issueId=issue_id,
                position=base + offset_,
            ))

        try:
            await db.commit()
        except IntegrityError as exc:
            # The pre-screen above eliminates the (groupId, issueId) UNIQUE
            # path under sequential traffic. The realistic IntegrityError
            # paths here are:
            #   (a) a concurrent writer added one of the same ids between
            #       our existence check and our INSERT (TOCTOU on UNIQUE), or
            #   (b) a concurrent issue delete dropped a parent FK row
            #       between validation and INSERT.
            # Disambiguate via the error string so the response carries the
            # right typed code: UNIQUE-race -> 409 ALREADY_EXISTS (matching
            # the relations bulk-create pattern, CB-1972) so the caller can
            # safely retry — the second attempt will see the concurrent
            # member as already_members and skip it. FK / other anomalies
            # surface as 500 DATABASE_ERROR. %r escapes control chars in
            # user-supplied IDs (CRLF log injection).
            await db.rollback()
            cause = str(getattr(exc, "orig", exc)).lower()
            is_unique = (
                "unique" in cause or "issuegroupmember" in cause
            )
            logger.info(
                "IntegrityError on bulk member add group=%r members=%d unique=%s: %s",
                group_id, len(accepted), is_unique, exc,
            )
            if is_unique:
                raise AlreadyExistsError(
                    "One or more members already exist (concurrent writer)",
                    details={
                        "groupId": group_id,
                        "memberCount": len(accepted),
                    },
                )
            raise DatabaseError(
                "Could not add members due to a concurrent change",
                details={
                    "groupId": group_id,
                    "memberCount": len(accepted),
                },
            )
    # else: nothing to insert; both lists land on the response unchanged
    # and we deliberately skip the commit/rollback dance.

    return IssueGroupMembersBulkAddResponse(added=accepted, skipped=skipped)


@router.delete(
    "/groups/{group_id}/members",
    response_model=IssueGroupMembersBulkRemoveResponse,
)
async def remove_group_members(
    group_id: str,
    payload: IssueGroupMembersBulkRemove,
    db: AsyncSession = Depends(get_db),
) -> IssueGroupMembersBulkRemoveResponse:
    """Bulk-remove members from ``group_id``.

    Body: ``{issueIds: [str]}`` — see IssueGroupMembersBulkRemove. The
    schema dedupes within the request and caps the list at 500. Issues
    that are not currently members of the group are returned in
    ``notFound`` (whether they don't exist at all or belong to a different
    group — both classified the same way to avoid leaking issue
    existence to a probing caller via differing error shapes).

    Issues themselves survive: only the IssueGroupMember row is removed.
    The DELETE is scoped by ``(groupId, issueId)`` so members of OTHER
    groups (or the same issue's other relations / parents / etc.) are
    untouched.

    Errors:
      * 404 NOT_FOUND — ``group_id`` doesn't exist.
      * 422 — payload shape (Pydantic): empty list, oversized list,
        non-string ids, or per-id length violation.

    Response: ``{removed: int, notFound: [issueId]}`` — ``removed`` is the
    DELETE statement's rowcount (truthful under concurrent unmember races,
    rather than ``len(existing_members)`` which would over-count if a
    parallel writer dropped a row between our SELECT and our DELETE).
    ``notFound`` preserves deduped request order so the caller can
    correlate against their input array.

    Concurrency: SELECT-then-DELETE leaves a small window where a parallel
    POST /members could re-add an id we just classified as notFound, or a
    parallel DELETE could drop a row before ours. Both are tolerated:
      * concurrent re-add → caller's request arrived before the add, so
        notFound (at SELECT time) is the honest answer; the new row
        survives because our DELETE filters by the membership snapshot we
        just read, not by id alone.
      * concurrent unmember → our DELETE's rowcount drops accordingly,
        which is exactly what ``removed`` reports.

    No reader-rule guard (CB-1987): bulk-remove is the *intended* way to
    drop a member from a group while keeping the group itself alive, so
    blocking on IN_PROGRESS membership would defeat the purpose. The
    delete-group endpoint guards because dropping the whole group
    silently dissolves the reader's grouping context for live work; this
    endpoint surgically removes one membership and is the documented
    escape hatch the caller would use to satisfy that guard.
    """
    # 1. Group must exist (404). Cheap single-column SELECT mirroring
    #    add_group_members / get_group_detail so a stale URL produces a
    #    consistent NOT_FOUND code regardless of which membership endpoint
    #    the caller hits.
    group_row = (await db.execute(
        select(IssueGroup.id).where(IssueGroup.id == group_id)
    )).first()
    if group_row is None:
        raise NotFoundError("IssueGroup", group_id)

    # 2. Classify the request into {existing-in-group, notFound} via a
    #    single round-trip. notFound captures BOTH "issue doesn't exist"
    #    and "issue exists but isn't a member of THIS group" — see the
    #    response-schema docstring for why those two are bucketed
    #    together (avoids existence-oracle leakage to a probing caller).
    issue_ids = list(payload.issueIds)
    existing_rows = (await db.execute(
        select(IssueGroupMember.issueId).where(
            IssueGroupMember.groupId == group_id,
            IssueGroupMember.issueId.in_(issue_ids),
        )
    )).all()
    existing_member_ids: set[str] = {row[0] for row in existing_rows}

    # Preserve deduped request order in notFound so the caller can map
    # response indices back to their input array.
    not_found = [iid for iid in issue_ids if iid not in existing_member_ids]

    # 3. Fused DELETE scoped by (groupId, issueId IN existing). The
    #    UNIQUE(groupId, issueId) constraint means filtering by issue_ids
    #    would already match the same rows, but we narrow the filter to
    #    `existing_member_ids` to (a) shrink the IN-list the planner sees
    #    on long requests and (b) provide defence-in-depth if a future
    #    refactor ever broadens the classification logic above.
    #
    #    rowcount is the truthful "removed" count under concurrent races;
    #    len(existing) would over-count if a parallel writer dropped one
    #    of our rows after our SELECT.
    #
    #    No try/except IntegrityError wrapper here (deliberately; the
    #    sibling add_group_members has one for UNIQUE/FK races on INSERT,
    #    but a DELETE on this table can't violate UNIQUE/FK under the
    #    current schema — IssueGroupMember has no inbound FKs). If a
    #    future schema adds an inbound FK, re-add the wrapper to surface
    #    the failure as a typed DATABASE_ERROR instead of a bare 500.
    removed_count = 0
    if existing_member_ids:
        delete_result = await db.execute(
            sa_delete(IssueGroupMember).where(
                IssueGroupMember.groupId == group_id,
                IssueGroupMember.issueId.in_(existing_member_ids),
            )
        )
        removed_count = int(delete_result.rowcount or 0)
        await db.commit()
    # else: nothing to delete; skip commit/rollback dance entirely.

    return IssueGroupMembersBulkRemoveResponse(
        removed=removed_count,
        notFound=not_found,
    )


@router.patch(
    "/groups/{group_id}/members/reorder",
    response_model=IssueGroupMembersReorderResponse,
)
async def reorder_group_members(
    group_id: str,
    payload: IssueGroupMembersReorder,
    db: AsyncSession = Depends(get_db),
) -> IssueGroupMembersReorderResponse:
    """Bulk-rewrite member positions to match the caller-supplied order (CB-2015).

    Body: ``{orderedIssueIds: [str]}`` — the COMPLETE current membership of
    the group in the new desired order. Positions are reassigned 1..N in
    the supplied order in a single transaction. The set of ids in the
    request MUST exactly equal the current member set: any extra
    (id-not-a-member) or any missing (member-not-in-payload) is rejected
    with 400 VALIDATION_ERROR so the caller can re-fetch and retry against
    fresh state. This deliberately closes the TOCTOU window where a
    concurrent member-add/remove between the client's last GET and this
    PATCH would otherwise let a silent demotion or duplicate slip through.

    Why a bulk rewrite rather than per-row PATCH:
      * Drag-to-reorder UX moves one row but renumbers a contiguous range;
        a per-row PATCH would force N round-trips and a half-numbered
        intermediate state visible on the wire.
      * Single-shot rewrite is atomic — partial failure rolls back to the
        pre-reorder ordering, never to a half-renumbered state.
      * No transient unique-violation suspension required (the schema
        doesn't have UNIQUE(groupId, position), but a future tightening
        would still work because every position is set in the same
        statement window).

    Why we reject duplicates in the payload at the schema layer:
      * A repeated id in `orderedIssueIds` means the caller's frame of the
        ordering is internally inconsistent. Silently deduping would pick
        an arbitrary slot for the duplicate; surfacing 422 forces the UI
        to re-derive the order from server state.

    Errors:
      * 404 NOT_FOUND — ``group_id`` does not exist.
      * 400 VALIDATION_ERROR — ``orderedIssueIds`` does not exactly match
        the current member set. ``details`` carries
        ``{groupId, missing, extra}`` so the caller can diff client-side
        and retry. ``missing`` are member issueIds the caller forgot to
        list; ``extra`` are payload issueIds that aren't members of this
        group.
      * 422 — payload shape (Pydantic): empty list, oversized list,
        non-string ids, or duplicate id within the request.

    Response: ``{reordered, members}`` — ``reordered`` is the count of
    member rows the UPDATE actually re-positioned (sourced from
    SQLAlchemy's `is_modified` / dirty tracking, NOT len(payload)) so a
    no-op reorder honestly reports 0. ``members`` is the post-update full
    member list sorted by the new position 1..N with embedded
    IssueSummary projections, ready for the frontend to prime its
    ``['issue-group', groupId]`` cache without a follow-up GET.
    """
    # 1. Group must exist (404). Cheap single-column SELECT mirroring the
    #    sibling endpoints so a stale URL produces a consistent NOT_FOUND
    #    regardless of which membership endpoint the caller hits.
    group_row = (await db.execute(
        select(IssueGroup.id).where(IssueGroup.id == group_id)
    )).first()
    if group_row is None:
        raise NotFoundError("IssueGroup", group_id)

    # 2. Load the current member rows with their embedded issue projection
    #    in one round-trip. selectinload on `.issue` is mandatory here
    #    because the response schema embeds IssueSummary and the
    #    relationship is configured with lazy="raise_on_sql" — a bare lazy
    #    access during model_validate would surface as a 500 in async
    #    context. Same pattern as get_group_detail.
    member_rows = (await db.execute(
        select(IssueGroupMember)
        .where(IssueGroupMember.groupId == group_id)
        .options(selectinload(IssueGroupMember.issue))
    )).scalars().all()

    # 3. Build the current-member index. issueId is unique per group (the
    #    UNIQUE(groupId, issueId) constraint guarantees this), so the dict
    #    keyed by issueId is one-to-one with the membership rows.
    current_by_issue_id: dict[str, IssueGroupMember] = {
        m.issueId: m for m in member_rows
    }
    current_member_ids: set[str] = set(current_by_issue_id.keys())
    requested_ids: list[str] = list(payload.orderedIssueIds)
    requested_set: set[str] = set(requested_ids)

    # 4. Set-equality precondition. Diff both directions and surface the
    #    full lists in the 400 details so the caller can fix the entire
    #    payload in one edit instead of learning about offenders one
    #    PATCH at a time. This mirrors the relations bulk-create and
    #    cross-project member-add patterns (CB-1972 / CB-1992).
    #
    #    `missing` — ids that ARE members but the payload forgot. If we
    #    silently kept their existing positions, two of them would end up
    #    sharing a position with the renumbered ones. Reject up front.
    #    `extra` — ids in the payload that AREN'T members of this group.
    #    Could be a stale GET vs concurrent unmember, or a typo. Same
    #    decision: reject and let the caller re-fetch.
    if current_member_ids != requested_set:
        missing = sorted(current_member_ids - requested_set)
        extra = sorted(requested_set - current_member_ids)
        raise ValidationError(
            "orderedIssueIds must equal the current member set exactly",
            details={
                "groupId": group_id,
                # Both lists are sorted to give the response a deterministic
                # shape — easier on test assertions and on a UI that wants
                # to render the diff.
                "missing": missing,
                "extra": extra,
            },
        )

    # 5. Apply the new positions. Iterate in caller order, bumping
    #    `position` to the 1-based index — but only when the value
    #    actually changes, so `reordered` reflects the count of rows the
    #    UPDATE statement(s) will hit. SQLAlchemy's session-dirty tracking
    #    will only emit an UPDATE for rows whose attribute was assigned a
    #    new value; assigning the same value still marks it dirty under
    #    the default attribute-event strategy, so we gate the assignment
    #    explicitly on `!=` to keep the statement budget honest.
    #
    #    Bounded by the request schema's _ISSUE_GROUP_MAX_INITIAL_MEMBERS
    #    cap (500), so the per-row UPDATE storm is at most 500 statements.
    #    Acceptable for a drag-reorder request and matches the bulk-add
    #    insert budget.
    reordered_count = 0
    for new_position, issue_id in enumerate(requested_ids, start=1):
        member = current_by_issue_id[issue_id]
        if member.position != new_position:
            member.position = new_position
            reordered_count += 1

    if reordered_count > 0:
        try:
            await db.commit()
        except IntegrityError as exc:
            # No UNIQUE on (groupId, position) today, so an IntegrityError
            # here is an unexpected anomaly (e.g. a future schema change
            # that adds the constraint, or a concurrent migration). Roll
            # back, log with traceback at ERROR (real anomaly, not a
            # routine race), and surface as 500 DATABASE_ERROR so the
            # response carries a typed code instead of the generic
            # INTERNAL_ERROR an unwrapped IntegrityError would yield.
            # `raise ... from exc` preserves the IntegrityError as
            # `__cause__` so the dev-log traceback chains both frames.
            # %r escapes control chars in user-supplied IDs (CRLF log
            # injection).
            await db.rollback()
            logger.exception(
                "IntegrityError on member reorder group=%r members=%d: %s",
                group_id, len(requested_ids), exc,
            )
            raise DatabaseError(
                "Could not reorder members due to a concurrent change",
                details={
                    "groupId": group_id,
                    "memberCount": len(requested_ids),
                },
            ) from exc
    # else: every position already matched — nothing to commit. Skipping
    # commit avoids a no-op transaction round-trip and keeps the response
    # truthful (`reordered == 0`). FastAPI's `get_db` generator closes
    # the session on request teardown, releasing the implicit BEGIN that
    # the SELECTs above opened — same pattern as `add_group_members` /
    # `remove_group_members` no-op branches. We deliberately do NOT issue
    # `await db.rollback()` here: rollback expires loaded ORM state,
    # which would force the `members_payload` loop below to lazy-load
    # `member.issue` and fail with MissingGreenlet (the relationship has
    # `lazy="raise_on_sql"`).

    # 6. Build the post-update member list in caller-supplied order
    #    (1..N). The session is still attached so `member.position` and
    #    `member.issue` are live; no re-fetch needed. Order by traversing
    #    `requested_ids` rather than re-sorting the dict, so the response
    #    is byte-for-byte the order the caller asked for.
    members_payload: list[IssueGroupMemberResponse] = []
    for issue_id in requested_ids:
        member = current_by_issue_id[issue_id]
        members_payload.append(IssueGroupMemberResponse(
            id=member.id,
            groupId=member.groupId,
            issueId=member.issueId,
            position=member.position,
            createdAt=member.createdAt,
            # Same defense-in-depth as get_group_detail: `member.issue`
            # is None only if a future migration breaks the FK CASCADE
            # on issueId. Under the current schema this is unreachable.
            issue=IssueSummary.model_validate(member.issue) if member.issue else None,
        ))

    return IssueGroupMembersReorderResponse(
        reordered=reordered_count,
        members=members_payload,
    )
