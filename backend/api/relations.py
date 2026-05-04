"""
Issue Relations API — typed m2m links between issues (CB-1955 / EPIC CB-1969).

Implements `/api/issues/{id}/relations` per the api-designer contract.
This module currently ships POST single (CB-1971); the bulk / GET / DELETE
siblings (CB-1972..CB-1974) extend the same router.

Link semantics:
  * Each user-facing link writes a primary row + a companion inverse row in
    the same transaction so callers can read either direction without
    walking the inverse map. UNIQUE(fromIssueId, toIssueId, linkType)
    prevents duplicates per direction.
  * Cycle detection runs only for the two transitive families
    (BLOCKS/IS_BLOCKED_BY → "BLOCKS" graph, CAUSES/CAUSED_BY → "CAUSES"
    graph). RELATES_TO and DUPLICATES are non-transitive — no cycle check.
"""

from __future__ import annotations

import logging
import uuid
from typing import Tuple

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.errors import (
    AlreadyExistsError,
    CycleDetectedError,
    DatabaseError,
    NotFoundError,
    ValidationError,
)
from models import (
    Issue,
    IssueLink,
    IssueLinkBulkCreate,
    IssueLinkBulkResponse,
    IssueLinkBulkSkipped,
    IssueLinkCreate,
    IssueLinkDeleteResponse,
    IssueLinkResponse,
    IssueRelationsListResponse,
    LinkType,
    get_db,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Inverse mapping for the companion row. RELATES_TO is its own inverse
# (symmetric), so the companion is (to, from, RELATES_TO) — a different
# row under UNIQUE(from, to, type).
_INVERSE_LINK_TYPE: dict[str, str] = {
    "BLOCKS": "IS_BLOCKED_BY",
    "IS_BLOCKED_BY": "BLOCKS",
    "DUPLICATES": "IS_DUPLICATED_BY",
    "IS_DUPLICATED_BY": "DUPLICATES",
    "CAUSES": "CAUSED_BY",
    "CAUSED_BY": "CAUSES",
    "RELATES_TO": "RELATES_TO",
}

# Import-time guard: any future LinkType enum value must register an inverse
# here, otherwise the endpoint would 500 at runtime on the new value.
assert set(_INVERSE_LINK_TYPE) == {t.value for t in LinkType}, (
    "_INVERSE_LINK_TYPE is out of sync with LinkType enum"
)

# Transitive types live in two independent canonical-direction graphs.
# Adding a link in any of these families could close a cycle.
_TRANSITIVE_FAMILIES: dict[str, str] = {
    "BLOCKS": "BLOCKS",
    "IS_BLOCKED_BY": "BLOCKS",
    "CAUSES": "CAUSES",
    "CAUSED_BY": "CAUSES",
}

# Hard cap on cycle-BFS work. Without it an adversarial graph (or a buggy
# bulk-import) of N nodes turns every POST into N round-trip SELECTs.
# 5000 covers any realistic project hierarchy; beyond that we fail closed
# rather than burn the worker.
_MAX_CYCLE_VISIT = 5000


def _canonical_edge(
    from_id: str, to_id: str, link_type: str
) -> Tuple[str, str, str]:
    """Map a (from, to, type) into its canonical edge in the family graph.

    Returns ``(a, b, family)`` such that "a → b" is the canonical edge that
    will exist in the family graph after insertion. For BLOCKS/CAUSES the
    edge stays from→to; for the inverse forms (IS_BLOCKED_BY, CAUSED_BY)
    it flips because the canonical row stored in the family is actually
    the companion.
    """
    family = _TRANSITIVE_FAMILIES[link_type]
    if link_type in ("BLOCKS", "CAUSES"):
        return from_id, to_id, family
    return to_id, from_id, family


# Cap on the path returned in details.path. With _MAX_CYCLE_VISIT=5000,
# a worst-case linear cycle could ship 5000+ IDs to the client in one
# response. Real cycles are short (2..10 hops); cap at 50 nodes and flag
# truncated=true in details so the client can render an ellipsis. The
# cap is independent of the BFS visit budget — BFS still walks the full
# graph to detect the cycle, only the *response* shape is bounded.
_MAX_CYCLE_PATH_NODES = 50


async def _has_cycle(
    db: AsyncSession,
    src: str,
    dst: str,
    family: str,
    project_id: str,
    *,
    budget: list[int] | None = None,
) -> list[str] | None:
    """Would adding edge ``src → dst`` create a cycle in the family graph?

    Returns the closed cycle path ``[src, dst, ..., src]`` (in canonical
    family-graph direction) when a cycle would form, or ``None`` when the
    insert is safe. Returning the path lets the POST endpoint surface
    ``details.path`` per the CB-1977 contract without a second BFS.

    A cycle exists iff ``dst`` can already reach ``src`` via existing
    canonical-family rows. BFS from ``dst`` walking only rows of the
    canonical family (we deliberately skip the inverse rows so each edge
    is counted exactly once).

    Filters on ``linkType == family`` AND ``Issue.projectId == project_id``
    via JOIN. The same-project rule is enforced at write time on the
    ``(from, to)`` pair, but the BFS walks pre-existing rows — without the
    project filter, legacy rows or a future relaxation could let a caller
    in project A see issue IDs from project B in ``details.path``. Filter
    is defense-in-depth so BFS *cannot* traverse outside the caller's
    project regardless of stored data (CB-1977 audit fix).

    Bounded by ``_MAX_CYCLE_VISIT`` to avoid pathological graphs DoS-ing
    the worker pool. The ``budget`` arg lets callers share a single visit
    budget across many cycle checks in the same request — bulk-create
    runs up to 100 cycle checks in one POST, and without a shared budget
    a malicious/buggy graph could turn into 100 × _MAX_CYCLE_VISIT round
    trips per request. The single-create path passes ``budget=None`` and
    falls back to the per-call cap.
    """
    # parent[node] = previous node in BFS — used to reconstruct the
    # dst → ... → src walk once we hit src. dst has no parent (it's the
    # BFS root) so we sentinel it with itself.
    parent: dict[str, str] = {dst: dst}
    stack: list[str] = [dst]
    while stack:
        # FIFO would give shortest path; LIFO matches the previous
        # implementation's traversal order. Either is valid for cycle
        # detection — path length is not part of the contract.
        node = stack.pop()
        if node == src:
            # Reconstruct dst → ... → src by walking parents.
            chain: list[str] = [node]
            while chain[-1] != dst:
                chain.append(parent[chain[-1]])
            chain.reverse()  # now dst → ... → src
            # Closed cycle in canonical direction: src → dst → ... → src.
            return [src, *chain]
        # Either decrement the shared budget (bulk path) or cap on the
        # local parent-table size (single-create path). The shared budget
        # lets one bulk request burn at most _MAX_CYCLE_VISIT total
        # node-visits across all of its candidates instead of per-candidate.
        # `parent` grows one BFS-frontier ahead of pops (we record parents
        # at neighbor-discovery, not at pop), so this caps slightly looser
        # than the previous on-pop ``visited`` cap — still within a small
        # constant of _MAX_CYCLE_VISIT.
        if budget is not None:
            budget[0] -= 1
            if budget[0] < 0:
                raise ValidationError(
                    "Relation graph too large for cycle validation",
                    details={
                        "limit": _MAX_CYCLE_VISIT,
                        "family": family,
                    },
                )
        elif len(parent) > _MAX_CYCLE_VISIT:
            raise ValidationError(
                "Relation graph too large for cycle validation",
                details={
                    "limit": _MAX_CYCLE_VISIT,
                    "family": family,
                },
            )
        # JOIN to Issue on toIssueId so the BFS only follows edges into
        # issues belonging to ``project_id``. Without the JOIN, a stray
        # cross-project row (legacy data or a future migration) could
        # leak IDs from another tenant in ``details.path``.
        result = await db.execute(
            select(IssueLink.toIssueId)
            .join(Issue, Issue.id == IssueLink.toIssueId)
            .where(
                IssueLink.fromIssueId == node,
                IssueLink.linkType == family,
                Issue.projectId == project_id,
            )
        )
        for next_id in result.scalars():
            if next_id not in parent:
                parent[next_id] = node
                stack.append(next_id)
    return None


def _truncate_cycle_path(path: list[str]) -> tuple[list[str], bool]:
    """Cap the cycle path at ``_MAX_CYCLE_PATH_NODES`` for the response.

    Returns ``(possibly-truncated path, truncated_flag)``. Strategy: keep
    the first half from the head and the last half from the tail, joined
    by an ellipsis sentinel ``"..."`` in the middle. Endpoints stay
    visible (cycle starts and ends at the same node — caller needs both).
    """
    if len(path) <= _MAX_CYCLE_PATH_NODES:
        return path, False
    head = _MAX_CYCLE_PATH_NODES // 2
    tail = _MAX_CYCLE_PATH_NODES - head - 1  # leave room for the sentinel
    return [*path[:head], "...", *path[-tail:]], True


@router.post(
    "/issues/{issue_id}/relations",
    response_model=IssueLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_relation(
    issue_id: str,
    payload: IssueLinkCreate,
    db: AsyncSession = Depends(get_db),
) -> IssueLinkResponse:
    """Create a typed relation from ``issue_id`` → ``payload.toIssueId``.

    Writes the primary row plus its companion inverse row in the same
    transaction. Returns the primary row with ``fromIssue`` / ``toIssue``
    summaries embedded (CB-1960).

    Errors:
      * 400 VALIDATION_ERROR — self-link
      * 400 VALIDATION_ERROR — cross-project
      * 404 NOT_FOUND        — either source or target issue missing
      * 409 ALREADY_EXISTS   — same (from, to, type) already linked
      * 409 CYCLE_DETECTED   — would close a cycle in a transitive family
        (BLOCKS / CAUSES). ``details.path`` is the closed cycle in
        canonical family-graph direction, ``[src, dst, ..., src]``.
    """
    from_id = issue_id
    to_id = payload.toIssueId
    link_type = payload.linkType.value
    inverse_type = _INVERSE_LINK_TYPE[link_type]

    # 1. Self-link guard. No DB hit needed.
    if from_id == to_id:
        raise ValidationError(
            "Cannot link an issue to itself",
            details={"issueId": from_id},
        )

    # 2. Both issues must exist. Fetch both in a single round-trip.
    result = await db.execute(
        select(Issue.id, Issue.projectId).where(
            Issue.id.in_([from_id, to_id])
        )
    )
    project_by_id = {row[0]: row[1] for row in result.all()}
    if from_id not in project_by_id:
        raise NotFoundError("Issue", from_id)
    if to_id not in project_by_id:
        raise NotFoundError("Issue", to_id)

    # 3. Same-project enforcement (CB-1955 — no cross-project relations).
    if project_by_id[from_id] != project_by_id[to_id]:
        raise ValidationError(
            "Cannot link issues from different projects",
            details={
                "fromProjectId": project_by_id[from_id],
                "toProjectId": project_by_id[to_id],
            },
        )

    # 4. Duplicate guard. Check both the primary row AND the would-be
    #    companion row — if either exists, we treat the relation as a
    #    duplicate. This catches data-corruption cases where only the
    #    companion survived a partial commit, and surfaces a clean 409
    #    instead of letting the IntegrityError bubble up.
    existing = await db.execute(
        select(IssueLink.id).where(
            or_(
                and_(
                    IssueLink.fromIssueId == from_id,
                    IssueLink.toIssueId == to_id,
                    IssueLink.linkType == link_type,
                ),
                and_(
                    IssueLink.fromIssueId == to_id,
                    IssueLink.toIssueId == from_id,
                    IssueLink.linkType == inverse_type,
                ),
            )
        )
    )
    if existing.first() is not None:
        raise AlreadyExistsError(
            "Relation already exists",
            details={
                "fromIssueId": from_id,
                "toIssueId": to_id,
                "linkType": link_type,
            },
        )

    # 5. Cycle check (transitive families only). Helper returns the closed
    #    cycle path in canonical family-graph direction, or None. Path is
    #    truncated to _MAX_CYCLE_PATH_NODES before serialization so a
    #    pathological graph can't ship a multi-KB array to the client.
    if link_type in _TRANSITIVE_FAMILIES:
        a, b, family = _canonical_edge(from_id, to_id, link_type)
        cycle_path = await _has_cycle(
            db, a, b, family, project_by_id[from_id],
        )
        if cycle_path is not None:
            response_path, truncated = _truncate_cycle_path(cycle_path)
            details: dict = {
                "fromIssueId": from_id,
                "toIssueId": to_id,
                "linkType": link_type,
                "path": response_path,
            }
            if truncated:
                details["truncated"] = True
            raise CycleDetectedError(
                "Relation would create a cycle",
                details=details,
            )

    # 6. Insert primary + companion in the same transaction.
    primary_id = str(uuid.uuid4())
    db.add(IssueLink(
        id=primary_id,
        fromIssueId=from_id,
        toIssueId=to_id,
        linkType=link_type,
    ))
    db.add(IssueLink(
        id=str(uuid.uuid4()),
        fromIssueId=to_id,
        toIssueId=from_id,
        linkType=inverse_type,
    ))

    try:
        await db.commit()
    except IntegrityError as exc:
        # IntegrityError can fire on UNIQUE (concurrent dup race) or FK
        # (concurrent issue delete). Only the UNIQUE case is ALREADY_EXISTS
        # — anything else needs to surface as a generic 500/conflict so
        # the caller doesn't act on a wrong error code.
        await db.rollback()
        cause = str(getattr(exc, "orig", exc)).lower()
        is_unique = "unique" in cause or "issuelink" in cause
        # %r escapes control chars in user-supplied IDs (CRLF log injection).
        logger.info(
            "IntegrityError on relation create from=%r to=%r type=%r unique=%s: %s",
            from_id, to_id, link_type, is_unique, exc,
        )
        if is_unique:
            raise AlreadyExistsError(
                "Relation already exists",
                details={
                    "fromIssueId": from_id,
                    "toIssueId": to_id,
                    "linkType": link_type,
                },
            )
        # Non-unique integrity violation (most likely concurrent issue
        # delete). Re-raise so the global handler returns 500 instead of
        # masking it as a duplicate.
        raise

    # 7. Re-fetch with eager-loaded summaries for the response. The
    #    relationship is configured with lazy="raise_on_sql" (CB-1960), so
    #    selectinload is required — accessing fromIssue/toIssue without it
    #    would raise.
    result = await db.execute(
        select(IssueLink)
        .where(IssueLink.id == primary_id)
        .options(
            selectinload(IssueLink.fromIssue),
            selectinload(IssueLink.toIssue),
        )
    )
    return IssueLinkResponse.model_validate(result.scalar_one())


# Hard cap on per-direction page size for the GET endpoint (CB-1973).
# Mirrors the bulk-create cap (`_ISSUE_LINK_BULK_MAX_TARGETS` in
# models/schemas.py) so a freshly bulk-linked issue can be read back in
# one round-trip; also bounds the worst-case row count per response so a
# single GET can't fan out beyond 200 rows + 200 summary fetches.
_ISSUE_LINK_LIST_MAX_PAGE_SIZE = 100


@router.get(
    "/issues/{issue_id}/relations",
    response_model=IssueRelationsListResponse,
)
async def list_relations(
    issue_id: str,
    pageSize: int = Query(
        _ISSUE_LINK_LIST_MAX_PAGE_SIZE,
        ge=1,
        le=_ISSUE_LINK_LIST_MAX_PAGE_SIZE,
        description="Max rows per direction (1..100, default 100)",
    ),
    db: AsyncSession = Depends(get_db),
) -> IssueRelationsListResponse:
    """List relations involving ``issue_id``, split by direction.

    Returns ``{outbound, inbound}`` where:
      * ``outbound`` are rows whose ``fromIssueId == issue_id`` (the
        issue's own authored direction plus any companion rows pointing
        outward — see CB-1971 for the primary/companion contract).
      * ``inbound`` are rows whose ``toIssueId == issue_id``.

    Each row is returned as ``IssueLinkResponse`` with embedded
    ``fromIssue`` / ``toIssue`` summaries (CB-1960), so the consumer can
    render either direction without an extra round-trip.

    Ordering is ``createdAt DESC, id DESC`` per direction — newest first,
    deterministic on createdAt ties (id break-tie) so the response is
    stable across repeated reads.

    ``pageSize`` is applied independently to each direction and clamped to
    [1, 100] by the query layer (Pydantic). No cursor pagination yet — the
    cap matches the bulk-create cap (CB-1972), so any issue that fits a
    single bulk POST also fits a single GET.

    Errors:
      * 404 NOT_FOUND — ``issue_id`` does not exist.
      * 422 — ``pageSize`` outside [1, 100] (FastAPI/Pydantic).
    """
    # 1. Source must exist. Returning 404 here matches the contract used by
    #    the POST endpoints (CB-1971/CB-1972); we don't want to silently
    #    return an empty list for a non-existent issue and let bugs hide.
    #    Capture src.projectId for the cross-project filter below (CB-2126).
    src = (await db.execute(
        select(Issue.id, Issue.projectId).where(Issue.id == issue_id)
    )).first()
    if src is None:
        raise NotFoundError("Issue", issue_id)
    src_project_id = src[1]

    # 2. Outbound + inbound queries. Both eager-load fromIssue/toIssue via
    #    selectinload — the ORM relationship is configured with
    #    lazy="raise_on_sql" (CB-1960), so accessing the summaries without
    #    eager loading would raise. Two separate selectinloads run as two
    #    extra round-trips per direction; acceptable at the 100-row cap.
    #
    #    CB-2126 defense-in-depth: even though same-project enforcement
    #    runs on every CREATE (CB-1980), legacy or out-of-band IssueLink
    #    rows could span projects (pre-CB-1980 data, future migration,
    #    direct DB write). Filter both directions on the *opposite* end's
    #    projectId so a foreign-project row is never surfaced via this
    #    endpoint regardless of how it landed in the DB. Mirrors the
    #    `_has_cycle` defensive filter (CB-1977).
    OtherIssue = aliased(Issue)  # noqa: N806

    out_result = await db.execute(
        select(IssueLink)
        .join(OtherIssue, IssueLink.toIssueId == OtherIssue.id)
        .where(IssueLink.fromIssueId == issue_id)
        .where(OtherIssue.projectId == src_project_id)
        .options(
            selectinload(IssueLink.fromIssue),
            selectinload(IssueLink.toIssue),
        )
        .order_by(IssueLink.createdAt.desc(), IssueLink.id.desc())
        .limit(pageSize)
    )
    outbound = [
        IssueLinkResponse.model_validate(r) for r in out_result.scalars()
    ]

    in_result = await db.execute(
        select(IssueLink)
        .join(OtherIssue, IssueLink.fromIssueId == OtherIssue.id)
        .where(IssueLink.toIssueId == issue_id)
        .where(OtherIssue.projectId == src_project_id)
        .options(
            selectinload(IssueLink.fromIssue),
            selectinload(IssueLink.toIssue),
        )
        .order_by(IssueLink.createdAt.desc(), IssueLink.id.desc())
        .limit(pageSize)
    )
    inbound = [
        IssueLinkResponse.model_validate(r) for r in in_result.scalars()
    ]

    return IssueRelationsListResponse(outbound=outbound, inbound=inbound)


_SKIP_REASON_DUPLICATE = "DUPLICATE"
_SKIP_REASON_CYCLE = "CYCLE"


@router.post(
    "/issues/{issue_id}/relations/bulk",
    response_model=IssueLinkBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_relations_bulk(
    issue_id: str,
    payload: IssueLinkBulkCreate,
    db: AsyncSession = Depends(get_db),
) -> IssueLinkBulkResponse:
    """Create many typed relations from ``issue_id`` in one transaction.

    Mirrors the single-create contract (CB-1971) at scale:
      * Same `linkType` for every target — bulk-link with mixed types is
        out of scope (callers can run multiple bulk requests).
      * For each accepted target, primary + companion rows are inserted in
        the same transaction (atomic per request).
      * Targets that are already linked (primary OR companion already in
        the DB) are silently skipped with reason ``DUPLICATE``.
      * For transitive types (BLOCKS / IS_BLOCKED_BY / CAUSES / CAUSED_BY)
        each candidate runs the family cycle BFS *with previously inserted
        candidates of the same batch flushed and visible*. A target that
        would close a cycle is skipped with reason ``CYCLE`` rather than
        rejecting the whole batch — the rest of the batch still applies.

    Errors:
      * 400 VALIDATION_ERROR + ``details.invalidIds`` — any toIssueId is
        the source itself, missing, or in a different project. The whole
        batch is rejected (no partial inserts) so the caller fixes the
        list and retries.
      * 404 NOT_FOUND — source issue (``issue_id``) doesn't exist.
      * 422 — payload shape (Pydantic) — empty list, oversized list,
        unknown linkType, malformed id chars.

    Response shape: ``{created: [IssueLinkResponse], skipped: [{toIssueId,
    reason}]}`` — see IssueLinkBulkResponse / IssueLinkBulkSkipped.
    """
    from_id = issue_id
    link_type = payload.linkType.value
    inverse_type = _INVERSE_LINK_TYPE[link_type]

    # 1. Dedupe targets within the request, preserving caller-supplied
    #    order. dict.fromkeys is the standard order-preserving dedupe in
    #    Python 3.7+. Without this, two repeated ids in the body would
    #    fight each other inside the same transaction (one inserts, the
    #    second hits the in-flight UNIQUE).
    to_ids = list(dict.fromkeys(payload.toIssueIds))

    # 2. Source must exist. Returning 404 here mirrors the single-POST
    #    behavior — the caller's URL is wrong, not their body.
    src_row = (await db.execute(
        select(Issue.id, Issue.projectId).where(Issue.id == from_id)
    )).first()
    if src_row is None:
        raise NotFoundError("Issue", from_id)
    src_project = src_row[1]

    # 3. Fetch every target's project in a single round-trip. Missing
    #    targets are inferred from set difference below.
    rows = (await db.execute(
        select(Issue.id, Issue.projectId).where(Issue.id.in_(to_ids))
    )).all()
    project_by_id: dict[str, str] = {row[0]: row[1] for row in rows}

    # 4. Partition into invalid (self-link, missing, cross-project) vs
    #    candidates. Any invalid ids → 400 with the full list so the
    #    caller can fix all of them in one edit, rather than learning
    #    about them one at a time across retries.
    invalid_ids: list[str] = []
    candidates: list[str] = []
    for tid in to_ids:
        if tid == from_id:
            invalid_ids.append(tid)
            continue
        project = project_by_id.get(tid)
        if project is None or project != src_project:
            invalid_ids.append(tid)
            continue
        candidates.append(tid)

    if invalid_ids:
        raise ValidationError(
            "Invalid issue ids in bulk relation create",
            details={"invalidIds": invalid_ids},
        )

    # 5. Single round-trip duplicate scan — any row matching either the
    #    primary direction (from→tid, link_type) or the companion-equivalent
    #    direction (tid→from, inverse_type) means the relation already
    #    exists in either canonical form, so we skip it silently per the
    #    CB-1972 contract.
    skipped: list[IssueLinkBulkSkipped] = []
    duplicates: set[str] = set()
    if candidates:
        existing = await db.execute(
            select(
                IssueLink.fromIssueId,
                IssueLink.toIssueId,
                IssueLink.linkType,
            ).where(
                or_(
                    and_(
                        IssueLink.fromIssueId == from_id,
                        IssueLink.toIssueId.in_(candidates),
                        IssueLink.linkType == link_type,
                    ),
                    and_(
                        IssueLink.fromIssueId.in_(candidates),
                        IssueLink.toIssueId == from_id,
                        IssueLink.linkType == inverse_type,
                    ),
                )
            )
        )
        for from_, to_, lt in existing.all():
            # Walk both arms: primary match → tid is the `to_`; inverse
            # companion match → tid is the `from_`. Either way the
            # candidate id is the one that *isn't* the source.
            if from_ == from_id and lt == link_type:
                duplicates.add(to_)
            elif to_ == from_id and lt == inverse_type:
                duplicates.add(from_)

    # 6. Iterate candidates in caller order. Cycle BFS reads
    #    in-flight rows committed by `db.flush()` from previous
    #    iterations, so a batch of N transitive links can correctly
    #    detect "second link in this batch closes the cycle".
    #
    #    Cycle BFS shares a single visit budget across the whole batch
    #    (security audit, CB-1972): a 100-target transitive bulk would
    #    otherwise be able to issue 100 × _MAX_CYCLE_VISIT SELECTs per
    #    request, turning one POST into a worker-saturating amplifier.
    #    With one shared budget the worst case stays at _MAX_CYCLE_VISIT
    #    total — same ceiling the single-POST path already accepts.
    is_transitive = link_type in _TRANSITIVE_FAMILIES
    cycle_budget: list[int] = [_MAX_CYCLE_VISIT]
    created_ids: list[str] = []
    for tid in candidates:
        if tid in duplicates:
            skipped.append(IssueLinkBulkSkipped(
                toIssueId=tid, reason=_SKIP_REASON_DUPLICATE,
            ))
            continue
        if is_transitive:
            a, b, family = _canonical_edge(from_id, tid, link_type)
            # Helper returns Optional[list[str]] (CB-1977); bulk only needs
            # the boolean ("did this candidate cycle?"). The path is
            # discarded here because the bulk skip contract (CB-1972) is
            # `{toIssueId, reason}` — adding a path would extend the
            # response schema beyond that contract.
            cycle_path = await _has_cycle(
                db, a, b, family, src_project, budget=cycle_budget,
            )
            if cycle_path is not None:
                skipped.append(IssueLinkBulkSkipped(
                    toIssueId=tid, reason=_SKIP_REASON_CYCLE,
                ))
                continue
        primary_id = str(uuid.uuid4())
        db.add(IssueLink(
            id=primary_id,
            fromIssueId=from_id,
            toIssueId=tid,
            linkType=link_type,
        ))
        db.add(IssueLink(
            id=str(uuid.uuid4()),
            fromIssueId=tid,
            toIssueId=from_id,
            linkType=inverse_type,
        ))
        # Flush so subsequent cycle BFS sees the new edges. Without flush
        # a 3-link batch like A→B, B→C, C→A would all pass the cycle check
        # because the BFS would see an empty graph each time.
        await db.flush()
        created_ids.append(primary_id)

    try:
        await db.commit()
    except IntegrityError as exc:
        # Concurrent writer raced us into the UNIQUE constraint. The
        # safest behavior is to fail the whole batch — partial-commit with
        # a "some duplicates" mid-flight is impossible under one
        # transaction. We return 409 ALREADY_EXISTS so the caller can
        # retry with GET /relations to learn the new state.
        await db.rollback()
        cause = str(getattr(exc, "orig", exc)).lower()
        is_unique = "unique" in cause or "issuelink" in cause
        # %r escapes control chars in user-supplied IDs (CRLF log injection).
        logger.info(
            "IntegrityError on bulk relation create from=%r type=%r unique=%s: %s",
            from_id, link_type, is_unique, exc,
        )
        if is_unique:
            raise AlreadyExistsError(
                "One or more relations already exist (concurrent writer)",
                details={"fromIssueId": from_id, "linkType": link_type},
            )
        raise

    # 7. Re-fetch the inserted rows with eager-loaded summaries. We sort
    #    back into insertion order (the order the caller's de-duplicated
    #    list applied) so the response is deterministic.
    created: list[IssueLinkResponse] = []
    if created_ids:
        result = await db.execute(
            select(IssueLink)
            .where(IssueLink.id.in_(created_ids))
            .options(
                selectinload(IssueLink.fromIssue),
                selectinload(IssueLink.toIssue),
            )
        )
        order = {pid: idx for idx, pid in enumerate(created_ids)}
        rows_out = sorted(result.scalars(), key=lambda r: order[r.id])
        created = [IssueLinkResponse.model_validate(r) for r in rows_out]

    return IssueLinkBulkResponse(created=created, skipped=skipped)


@router.delete(
    "/issues/{issue_id}/relations/{relation_id}",
    response_model=IssueLinkDeleteResponse,
)
async def delete_relation(
    issue_id: str,
    relation_id: str,
    db: AsyncSession = Depends(get_db),
) -> IssueLinkDeleteResponse:
    """Delete a relation by id and its companion inverse row in the same txn.

    Either participant can delete: the URL must address the relation via
    one of its endpoints (the primary's `fromIssueId` or `toIssueId`), and
    that endpoint may equally be the user-authored side or the companion
    side written by the create path (CB-1971). Both rows go away together
    so the primary/companion invariant holds after the delete.

    Errors:
      * 404 NOT_FOUND — relation_id does not exist, or it exists but
        ``issue_id`` is not one of its participants. We collapse "wrong
        owner" into 404 (rather than 403/400) to avoid leaking the
        existence of relations addressable via someone else's issue id.

    Response:
      * 200 ``{"deleted": <int>}`` — count of rows actually deleted.
        Normally 2 (primary + companion). 1 surfaces if the companion
        row was missing in the DB beforehand (legacy data; partial
        commit from before CB-1971 hardening) — we still finish the
        cleanup and report the honest count rather than silently
        backfilling a row.
    """
    # 1. Look up the targeted relation. We need from/to/type to compute the
    #    companion row's coordinates, and to verify ``issue_id`` is one of
    #    the participants. Single round-trip; nothing else to fetch.
    row = (await db.execute(
        select(
            IssueLink.fromIssueId,
            IssueLink.toIssueId,
            IssueLink.linkType,
        ).where(IssueLink.id == relation_id)
    )).first()
    if row is None:
        raise NotFoundError("Relation", relation_id)

    from_id, to_id, link_type = row

    # 2. Same-issue scoping: the URL claims this relation belongs to
    #    ``issue_id``. If neither end matches, treat as 404 — we don't want
    #    a caller to be able to probe relation ids by addressing them via
    #    arbitrary issue urls. (Also matches the path semantics — the
    #    relation truly is not under this issue's namespace.)
    #
    #    Cross-project safety note: the create-time same-project rule
    #    (`relations.py` create_relation, ~line 218) guarantees from_id
    #    and to_id always share a projectId. Combined with this
    #    participant check, an attacker cannot use an issue they can
    #    address in project A to delete a relation in project B — the
    #    ids simply won't line up. Relax this check only if the
    #    same-project create constraint is also relaxed.
    if issue_id != from_id and issue_id != to_id:
        raise NotFoundError("Relation", relation_id)

    inverse_type = _INVERSE_LINK_TYPE.get(link_type)
    if inverse_type is None:
        # Defensive: a row with a linkType outside the LinkType enum could
        # only land in the DB via direct-write tooling (the import-time
        # guard above keeps the code path in sync with the enum). The
        # request itself is valid — the DB is corrupt — so surface as a
        # 500 DATABASE_ERROR with the offending values in `details` so an
        # operator can clean up. ValidationError (400) would mislead the
        # caller into thinking they could fix this client-side.
        raise DatabaseError(
            "Relation has an unknown linkType; cannot resolve companion",
            details={"relationId": relation_id, "linkType": link_type},
        )

    # 3. Delete primary + companion in a single statement / single txn.
    #    The OR matches:
    #      * ``IssueLink.id == relation_id`` — the targeted row.
    #      * ``(to → from, inverse_type)`` — the companion written by the
    #        create path. For RELATES_TO (symmetric) the companion is
    #        ``(to, from, RELATES_TO)``, distinct under UNIQUE(from, to,
    #        type) so this still removes a different row.
    #    rowcount tells us how many rows actually went away — usually 2,
    #    1 if the companion was missing pre-call.
    result = await db.execute(
        delete(IssueLink).where(
            or_(
                IssueLink.id == relation_id,
                and_(
                    IssueLink.fromIssueId == to_id,
                    IssueLink.toIssueId == from_id,
                    IssueLink.linkType == inverse_type,
                ),
            )
        )
    )
    deleted = result.rowcount or 0

    if deleted == 0:
        # Concurrent DELETE raced us between SELECT and DELETE. Surface as
        # 404 (instead of returning {"deleted": 0}) so the caller sees a
        # consistent "the relation is gone" outcome regardless of which
        # request lost the race.
        await db.rollback()
        raise NotFoundError("Relation", relation_id)

    await db.commit()
    return IssueLinkDeleteResponse(deleted=deleted)
