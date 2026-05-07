"""
Service-layer validators (CB-1992 / STORY CB-1991).

Reusable cross-cutting checks that the issue-grouping endpoints (and any
sibling feature with the same shape) need to apply consistently. Each
validator either returns ``None`` on success or raises a typed
``app.errors`` exception so the FastAPI exception handlers translate it
into the standard error envelope (``{code, message, details}``) the API
contract guarantees.

Why a helper module rather than inlining
----------------------------------------
``api/groups.py::create_group`` and ``api/groups.py::add_group_members``
were carrying byte-identical same-project validation blocks. Two copies
means one of them drifts the day a maintainer fixes a bug or extends the
``details`` payload — the contract test in ``test_groups_post.py`` and
``test_groups_members_post.py`` would only catch divergence on whichever
endpoint they happen to assert. Centralising the check here keeps the
two endpoints in lock-step and gives future endpoints (``PATCH``
membership reorder, drag-to-reorder, etc.) a single call site to plug
into.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError, ValidationError
from models.issue import Issue


async def validate_same_project_members(
    db: AsyncSession,
    project_id: str,
    issue_ids: Iterable[str],
    *,
    group_id: str | None = None,
) -> None:
    """Verify every id in ``issue_ids`` exists AND belongs to ``project_id``.

    Used by the group-create and group-add-member endpoints to enforce the
    same-project contract (CB-1955 / STORY CB-1991): a group's membership
    is project-scoped, so any member id from another project is rejected
    at write time. This guarantee lets ``compute_group_status`` and every
    list/detail read assume single-project rows without re-validating.

    The 404 / 400 precedence mirrors the create-group contract (CB-1984):
    a missing issue is the caller's id-list-shape problem and surfaces
    BEFORE we can even classify the project, so it wins over the
    cross-project 400. The cross-project 400 then surfaces the FULL list
    of offenders (not the first one) so the caller can fix the entire
    request in a single edit, mirroring the relations bulk-create
    pattern (CB-1972).

    Parameters
    ----------
    db:
        Active ``AsyncSession``. The helper performs a single
        ``SELECT id, projectId FROM Issue WHERE id IN (...)`` round-trip
        and partitions the result in Python; no commit/rollback is
        issued, so the caller's transaction is preserved.
    project_id:
        The project the membership is being attached to. The caller is
        responsible for verifying this project exists — this helper
        assumes the FK is valid and only checks the issue ids against
        it. (Both call sites already perform an explicit project
        existence check up-front to differentiate "stale URL" from "bad
        payload".)
    issue_ids:
        Caller-supplied member ids. Already deduped and capped by the
        request schema (``IssueGroupCreate`` / ``IssueGroupMembersBulkAdd``);
        the helper does not enforce length or uniqueness. An empty
        iterable is a no-op (returns immediately without a DB hit), so
        ``create_group`` with ``issueIds=None`` is safe to delegate
        unconditionally.
    group_id:
        Keyword-only. When supplied, the cross-project ``details`` payload
        carries ``groupId`` alongside ``projectId`` and ``invalidIssueIds``
        — required by the add-members contract so the caller can
        correlate the failure against the route. Omit (``None``) for the
        create-group call site, which has no groupId to surface yet.

    Raises
    ------
    NotFoundError
        ``Issue`` with the FIRST missing id. Surfacing only the first
        missing id (rather than the whole list) matches the create-group
        contract documented at ``api/groups.py::create_group`` — the
        caller's id list is wrong before we can even check projects, so
        we fail fast on the first symptom.
    ValidationError
        ``code="VALIDATION_ERROR"`` with
        ``details={"projectId": ..., ["groupId": ...,] "invalidIssueIds": [...]}``.
        The full offender list is included so the caller can fix every
        bad id in one edit instead of learning about them one POST at a
        time.

    Returns
    -------
    None
        On success. The caller proceeds to the insert phase knowing
        every id is real and same-project.
    """
    # Materialise once — the iterable may be a generator and we need two
    # passes (existence partition + cross-project partition).
    ids = list(issue_ids)
    if not ids:
        # No-op fast path: create_group with issueIds=None lands here
        # and we skip the round-trip entirely.
        return

    # Single round-trip: fetch (id, projectId) for every requested id and
    # partition in Python. The IN-list size is bounded by the request
    # schema's 500-cap so the query plan stays predictable.
    rows = (await db.execute(
        select(Issue.id, Issue.projectId).where(Issue.id.in_(ids))
    )).all()
    project_by_id: dict[str, str] = {row[0]: row[1] for row in rows}

    # 404 precedence: missing-issue wins over cross-project. Surface the
    # first missing id; the request schema already validated id shape so
    # we trust the strings here.
    missing = [iid for iid in ids if iid not in project_by_id]
    if missing:
        raise NotFoundError("Issue", missing[0])

    # 400 cross-project: enumerate the full offender list so the caller
    # fixes every bad id in one edit (CB-1972 pattern).
    cross = [iid for iid in ids if project_by_id[iid] != project_id]
    if cross:
        details: dict[str, object] = {
            "projectId": project_id,
            "invalidIssueIds": cross,
        }
        # group_id is only available on the add-members call site. The
        # create-group endpoint has no groupId yet (group is being
        # created in the same transaction), so it omits the key rather
        # than carrying a misleading None. Note: the parameter toggles
        # BOTH the message string AND a details key — keeping the two
        # transitions side-by-side here so a future caller-rename can't
        # accidentally diverge them.
        if group_id is not None:
            details["groupId"] = group_id
            message = "Issues do not belong to group's project"
        else:
            message = "Issues do not belong to project"
        raise ValidationError(message, details=details)
