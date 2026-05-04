"""
CB-1993 — STORY 3.3 same-project enforcement: cross-project group members rejected.

Sibling CB-1992 added the shared service-layer validator
(``backend/utils/validators.py::validate_same_project_members``) that both
group write endpoints delegate to. This file locks in the contract with a
dedicated coverage matrix so any future relax (or regression) on either
endpoint, on the helper, on the response envelope, or on the validation order
shows up here — not in a downstream cycle / duplicate test.

Why a dedicated file (vs. piggy-backing on test_groups_post.py /
test_groups_members_post.py)
-----------------------------------------------------------------
Both endpoint test files already contain a single cross-project happy-path
case. That's enough to prove the rejection works at all, but it's not enough
to lock in the *contract* — the wire shape every client now depends on:

  * 404 precedence: missing-issue beats cross-project (the helper's
    documented precedence — a missing id is a shape problem before we
    can even classify projects).
  * Full offender enumeration: ``invalidIssueIds`` lists EVERY cross-
    project id, not just the first, so the caller fixes the whole batch
    in one edit (CB-1972 pattern).
  * Per-call-site envelope: create_group returns ``details = {projectId,
    invalidIssueIds}``; add_group_members returns ``details = {projectId,
    groupId, invalidIssueIds}`` — and the message string toggles too,
    keyed off the same ``group_id`` parameter on the helper.
  * No partial state: a rejected request leaves zero rows behind in the
    grouping tables — the helper raises BEFORE any insert, but a future
    refactor that flushes the group row before validating could regress
    this silently.
  * No-leak / tenant isolation: the response must surface the offending
    ids the caller already supplied, but never the projectId those
    offenders belong to (and never any other field). Mirrors the
    relations bulk-leak guard (test_relations_cross_project.py
    ``test_bulk_legacy_cross_project_link_does_not_leak_via_skip_channel``).
  * Helper unit-layer: the validator module is shared, so a direct
    invocation pins the exception types/details independent of which
    HTTP route happens to call it.

Mirrors the test_relations_cross_project.py / test_groups_post.py fixture
pattern: isolated on-disk SQLite, fresh schema per test, no production
codeboard.db touch.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from api.groups import router as groups_router  # noqa: E402
from app.errors import NotFoundError, ValidationError, setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.grouping import IssueGroup, IssueGroupMember  # noqa: E402
from models.issue import Issue, Project  # noqa: E402
from utils.validators import validate_same_project_members  # noqa: E402


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="groups-xproj-test-")
    db_path = os.path.join(tmp_dir, "test.db")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession,
        expire_on_commit=False, autocommit=False, autoflush=False,
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    local_app = FastAPI()
    setup_exception_handlers(local_app)
    local_app.include_router(groups_router, prefix="/api")
    local_app.dependency_overrides[get_db] = _override_get_db

    try:
        yield local_app, factory
    finally:
        await engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def factory(test_app_and_db):
    _, f = test_app_and_db
    yield f


@pytest_asyncio.fixture
async def client(test_app_and_db) -> AsyncGenerator[AsyncClient, None]:
    local_app, _ = test_app_and_db
    transport = ASGITransport(app=local_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------- seed helpers ---------------------------------------------------

def _make_project(project_id: str) -> Project:
    now_ms = 1700000000000
    return Project(
        id=project_id,
        name=f"proj-{project_id}",
        path=f"/tmp/{project_id}",
        status="ACTIVE",
        createdAt=now_ms,
        updatedAt=now_ms,
    )


def _make_issue(
    issue_id: str,
    key: str,
    project_id: str,
    title: str = "Test Issue",
    status_: str = "BACKLOG",
) -> Issue:
    # Issue.key has a global UNIQUE constraint (models/issue.py); keys are
    # unique across projects in this fixture set, with the project letter
    # encoded into the key prefix so a debug failure shows the project at a
    # glance.
    return Issue(
        id=issue_id,
        projectId=project_id,
        key=key,
        sequence=int(key.split("-")[-1]) if "-" in key else 1,
        title=title,
        type="TASK",
        status=status_,
        priority="MEDIUM",
        updatedAt=datetime.utcnow(),
    )


def _make_group(group_id: str, project_id: str, title: str = "G") -> IssueGroup:
    return IssueGroup(id=group_id, projectId=project_id, title=title)


async def _seed_two_projects_with_issues(factory) -> None:
    """Seed proj-A (a1, a2) + proj-B (b1, b2). Common scaffolding for create
    and add-members rejection tests.

    Issue.key uses the ``A-`` / ``B-`` prefix so a failing assert print makes
    the cross-project shape obvious without hunting the seed.
    """
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "A-101", project_id="proj-A", title="A One"))
        db.add(_make_issue("a2", "A-102", project_id="proj-A", title="A Two"))
        db.add(_make_issue("b1", "B-201", project_id="proj-B", title="B One"))
        db.add(_make_issue("b2", "B-202", project_id="proj-B", title="B Two"))
        await db.commit()


async def _seed_group_in_proj_a(
    factory, group_id: str = "grp-A",
) -> None:
    """Seed proj-A + proj-B + their issues + an empty group living in proj-A.

    Used by the add-members tests so they can attempt to add proj-B issues
    into a proj-A group.
    """
    await _seed_two_projects_with_issues(factory)
    async with factory() as db:
        db.add(_make_group(group_id, "proj-A", title="A Group"))
        await db.commit()


# =========================================================================
# create_group: POST /api/projects/{project_id}/groups
# =========================================================================

@pytest.mark.asyncio
async def test_create_single_cross_project_member_rejected(
    client: AsyncClient, factory,
):
    """One cross-project id in payload → 400 with that id in invalidIssueIds.

    Smallest possible failing case: list of length 1, payload contains only
    a foreign-project id. Pin the rejection works even when there's nothing
    same-project to validate against in the request.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "X", "issueIds": ["b1"]},
    )

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["projectId"] == "proj-A"
    assert body["details"]["invalidIssueIds"] == ["b1"]


@pytest.mark.asyncio
async def test_create_multiple_cross_project_members_all_listed(
    client: AsyncClient, factory,
):
    """Every cross-project id is enumerated in invalidIssueIds — caller
    fixes the whole batch in one edit (CB-1972 pattern).

    Payload mixes 1 same-project + 2 cross-project ids; the response must
    name BOTH cross-project ids, not just the first one encountered.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "Mixed", "issueIds": ["a1", "b1", "b2"]},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    # Order IS contract: validators.py:132 builds `cross` via list-comp over
    # the request `ids`, preserving caller order. The schema-level dedupe
    # (schemas.py:404-407) is also order-preserving (first-seen wins). A
    # future refactor that switched to set-based filtering would lose this
    # property silently — sibling response fields like
    # IssueGroupMembersBulkAddResponse.added/skipped already document
    # order-preservation as contract (schemas.py:579-581), so this helper
    # should match.
    assert body["details"]["invalidIssueIds"] == ["b1", "b2"]


@pytest.mark.asyncio
async def test_create_cross_project_offenders_preserve_request_order(
    client: AsyncClient, factory,
):
    """Reverse the request order to confirm the helper isn't accidentally
    sorting offenders. Without this, "preserve request order" would only be
    locked in one direction and a deterministic-sort regression would slip
    past the alphabetic-friendly fixture above.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "Reverse", "issueIds": ["b2", "b1"]},
    )
    assert resp.status_code == 400
    # Exact match on caller order — NOT sorted.
    assert resp.json()["details"]["invalidIssueIds"] == ["b2", "b1"]


@pytest.mark.asyncio
async def test_create_all_cross_project_members_all_listed(
    client: AsyncClient, factory,
):
    """An all-cross-project payload (zero same-project ids) still enumerates
    every offender. Sentinel against a future "early-out when no same-
    project ids are present" branch that would silently swallow the list.

    Also pins the full ``details`` key set on the all-cross-project path —
    the dedicated envelope test below uses a single-id payload, so without
    this assertion a future "add offenderProjectIds when 100% are foreign"
    debug branch would slip past.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "All-cross", "issueIds": ["b1", "b2"]},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["details"]["invalidIssueIds"] == ["b1", "b2"]
    assert set(body["details"].keys()) == {"projectId", "invalidIssueIds"}


@pytest.mark.asyncio
async def test_create_cross_project_writes_no_rows(
    client: AsyncClient, factory,
):
    """A rejected create must not leave a half-formed IssueGroup or
    IssueGroupMember row behind. The helper raises BEFORE any insert today,
    but a future refactor that flushes the group row before validating
    members would regress this silently.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "Should not persist", "issueIds": ["a1", "b1"]},
    )
    assert resp.status_code == 400

    async with factory() as db:
        groups = (await db.execute(select(IssueGroup))).scalars().all()
        members = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert groups == []
    assert members == []


@pytest.mark.asyncio
async def test_create_cross_project_error_envelope(
    client: AsyncClient, factory,
):
    """Lock the wire-shape clients depend on for the create endpoint:
       * ErrorResponse envelope (success, error, code, message, details)
       * code == VALIDATION_ERROR
       * message string differentiates "project" (no group context yet)
       * details = {projectId, invalidIssueIds} — and NOTHING else
       * groupId is NOT included on this endpoint (no group exists yet)
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "Group X", "issueIds": ["b1"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "VALIDATION_ERROR"
    assert body["code"] == "VALIDATION_ERROR"
    # Message string is a contract surface — toggling between create and
    # add-members helps client-side switch on message vs. details.
    assert body["message"] == "Issues do not belong to project"
    # Pin the disclosure surface — only projectId + invalidIssueIds. The
    # caller-supplied ids are legitimate echo (they sent them); a future
    # change that adds the foreign projectId, issue title, key, etc. would
    # trip this.
    assert set(body["details"].keys()) == {"projectId", "invalidIssueIds"}
    assert body["details"]["projectId"] == "proj-A"
    assert body["details"]["invalidIssueIds"] == ["b1"]
    # Defence-in-depth: also walk the full body for the foreign projectId
    # string. Mirrors the add-members no-leak guard so a future change that
    # injected proj-B into the message format string (e.g.,
    # f"... foreign={offender_project}") would trip here too — the `==`
    # message assertion above only catches an exact-string flip, not a
    # parameterised template that happens to keep the prefix.
    assert "proj-B" not in repr(body)
    # Envelope shape closed: any new top-level field appearing in the
    # error body is a leak-channel candidate. ErrorResponse exposes
    # success / error / code / message / details / request_id (errors.py)
    # — pin that the rejection cannot quietly grow a new key.
    _ALLOWED_TOP_LEVEL = {
        "success", "error", "code", "message", "details", "request_id",
    }
    assert set(body.keys()) <= _ALLOWED_TOP_LEVEL


@pytest.mark.asyncio
async def test_create_missing_issue_404_beats_cross_project_400(
    client: AsyncClient, factory,
):
    """404 precedence (CB-1992 contract): a payload with BOTH a missing id
    AND a cross-project id surfaces the missing-id 404, NOT the cross-
    project 400.

    Why: the helper's documented precedence — a missing id is a shape
    problem with the caller's request, surfaced before we can even classify
    the project of an id that doesn't exist. Without this test, swapping
    the helper's two checks could silently flip a 404 to a 400 for callers
    whose batch contained a real ghost id.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "Mixed", "issueIds": ["b1", "ghost"]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Issue"
    assert body["details"]["identifier"] == "ghost"
    # 404-envelope leak guard: the cross-project id and its foreign project
    # must NOT leak through the 404 path. A future "while validating, we
    # also noticed these other cross-project ids" diagnostic addition would
    # turn the 404 into a partial existence-oracle for foreign-project ids.
    assert set(body["details"].keys()) == {"resource", "identifier"}
    assert "b1" not in repr(body)
    assert "proj-B" not in repr(body)


@pytest.mark.asyncio
async def test_create_first_missing_id_wins_with_multiple_missing(
    client: AsyncClient, factory,
):
    """Helper contract (validators.py:88-93): when MULTIPLE ids are missing,
    the FIRST one in request order is surfaced.

    The basic precedence test only includes one ghost; this case has two
    ghosts plus a cross-project id and pins that the helper picks the
    first-in-iteration-order missing id, not the last and not a random
    pick. Without this, a future swap to ``missing[-1]`` or
    ``random.choice(missing)`` would still pass the single-missing test.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={
            "title": "Multi-missing",
            # Order matters: ghost1 first, ghost2 second, cross third.
            "issueIds": ["ghost1", "ghost2", "b1"],
        },
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["details"]["identifier"] == "ghost1"


@pytest.mark.asyncio
async def test_create_cross_project_dedupes_offenders_in_envelope(
    client: AsyncClient, factory,
):
    """Schema-level dedupe ↔ validator interaction (CB-1992):
    ``IssueGroupCreate.issueIds`` is deduped by the schema (schemas.py:404)
    BEFORE the validator runs. A payload of ``["b1", "b1", "b2"]`` must
    therefore surface as ``invalidIssueIds = ["b1", "b2"]`` — never with
    ``b1`` repeated.

    Without this test, a future schema change that dropped the dedupe
    step (or moved it after the validator) would silently leak duplicates
    into the offender list, breaking any client that builds a Set from it.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "Dup-cross", "issueIds": ["b1", "b1", "b2"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    # Length: 2, not 3. Order: first-seen preserved.
    assert body["details"]["invalidIssueIds"] == ["b1", "b2"]


# =========================================================================
# add_group_members: POST /api/groups/{group_id}/members
# =========================================================================

@pytest.mark.asyncio
async def test_add_members_single_cross_project_rejected(
    client: AsyncClient, factory,
):
    """One cross-project id → 400 with that id in invalidIssueIds AND
    groupId echoed back in the details envelope.

    The add-members call site differs from create_group on two axes:
    a `groupId` key in details, and a slightly different message string
    ("group's project" vs. "project"). Both are pinned in the envelope test
    below; this test pins the smallest happy-rejection.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1"]},
    )

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["groupId"] == "grp-A"
    assert body["details"]["projectId"] == "proj-A"
    assert body["details"]["invalidIssueIds"] == ["b1"]


@pytest.mark.asyncio
async def test_add_members_multiple_cross_project_all_listed(
    client: AsyncClient, factory,
):
    """Every cross-project id surfaces in invalidIssueIds — same one-edit
    batch-fix contract as create_group, mirrored on the add-members path.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["a1", "b1", "b2"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    # Order IS contract: caller order preserved (see create-side rationale
    # at test_create_multiple_cross_project_members_all_listed).
    assert body["details"]["invalidIssueIds"] == ["b1", "b2"]


@pytest.mark.asyncio
async def test_add_members_all_cross_project_all_listed(
    client: AsyncClient, factory,
):
    """Sentinel: an all-cross-project payload still enumerates every
    offender — no early-out swallowing the list when zero same-project ids
    are present.

    Also pins the full ``details`` key set on the all-cross-project path
    for the add-members endpoint — guards against an "add foreign-project
    diagnostic field on 100%-cross payloads" branch slipping past.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1", "b2"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["details"]["invalidIssueIds"] == ["b1", "b2"]
    assert set(body["details"].keys()) == {
        "projectId", "groupId", "invalidIssueIds",
    }


@pytest.mark.asyncio
async def test_add_members_cross_project_writes_no_rows(
    client: AsyncClient, factory,
):
    """A rejected bulk-add must not partially insert. The same-project ids
    in the batch are NOT created just because they would individually be
    valid — the validator raises before any INSERT runs.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["a1", "b1"]},
    )
    assert resp.status_code == 400

    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_add_members_cross_project_error_envelope(
    client: AsyncClient, factory,
):
    """Lock the wire shape for add-members:
       * code == VALIDATION_ERROR
       * message string differentiates "group's project" (vs. create's
         "project") — caller can branch on either string or details.groupId
       * details = {projectId, groupId, invalidIssueIds} EXACTLY — adding a
         leak surface (foreign projectId, issue titles, etc.) trips this
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Issues do not belong to group's project"
    assert set(body["details"].keys()) == {
        "projectId", "groupId", "invalidIssueIds",
    }
    assert body["details"]["projectId"] == "proj-A"
    assert body["details"]["groupId"] == "grp-A"
    assert body["details"]["invalidIssueIds"] == ["b1"]
    # Envelope shape closed: see create-side rationale. Add-members shares
    # the same ErrorResponse so the same allowed top-level set applies.
    _ALLOWED_TOP_LEVEL = {
        "success", "error", "code", "message", "details", "request_id",
    }
    assert set(body.keys()) <= _ALLOWED_TOP_LEVEL


@pytest.mark.asyncio
async def test_add_members_missing_issue_404_beats_cross_project_400(
    client: AsyncClient, factory,
):
    """Mirror the 404-precedence contract on the add-members path. The
    helper is shared, so this also serves as a regression guard against
    a future "split helper into two endpoint-specific copies" refactor
    diverging the precedence on one side.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1", "ghost"]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Issue"
    assert body["details"]["identifier"] == "ghost"
    # 404-envelope leak guard mirroring the create side: foreign-project
    # diagnostics must NOT slip into the 404 path.
    assert set(body["details"].keys()) == {"resource", "identifier"}
    assert "b1" not in repr(body)
    assert "proj-B" not in repr(body)


@pytest.mark.asyncio
async def test_add_members_legacy_cross_project_row_does_not_leak_via_skip_channel(
    client: AsyncClient, factory,
):
    """Tenant-isolation regression guard mirroring
    ``test_relations_cross_project.py::
    test_bulk_legacy_cross_project_link_does_not_leak_via_skip_channel``.

    Scenario: a legacy ``IssueGroupMember`` row already exists pointing
    grp-A (proj-A) at b1 (proj-B) — pre-CB-1992 data, or a future bug
    that bypassed the validator. A caller bulk-adds [b1].

    The validator gate (groups.py:604) MUST fire before the
    already-members pre-screen (groups.py:613-619). If the order ever
    flipped, the response would be 201 with ``skipped: ["b1"]`` — leaking
    the foreign-project id back through the success channel and treating
    a project-isolation violation as a routine no-op.

    Asserts:
    * Status is 400, not 201.
    * VALIDATION_ERROR (the gate fired), not ALREADY_EXISTS or a 201.
    * Neither ``added`` nor ``skipped`` appear in the body — those are
      success-shape fields and must not coexist with the error envelope.
    """
    await _seed_group_in_proj_a(factory)
    async with factory() as db:
        # Direct-write a legacy cross-project membership (bypassing the
        # API validation gate — simulates pre-enforcement data or a
        # future regression).
        db.add(IssueGroupMember(
            id=str(uuid.uuid4()),
            groupId="grp-A",
            issueId="b1",
            position=1,
        ))
        await db.commit()

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["invalidIssueIds"] == ["b1"]
    # Critical: the response must NOT carry the success-shape fields.
    # On a 400 the response is the error envelope, so `added`/`skipped`
    # should be absent entirely.
    assert "added" not in body
    assert "skipped" not in body
    # And no foreign-project leakage through any channel.
    assert "proj-B" not in repr(body)


@pytest.mark.asyncio
async def test_add_members_dedupes_offenders_in_envelope(
    client: AsyncClient, factory,
):
    """Mirror of ``test_create_cross_project_dedupes_offenders_in_envelope``
    on the add-members path — both schemas dedupe ``issueIds`` before the
    validator runs (schemas.py:566-569 for IssueGroupMembersBulkAdd). A
    payload of ``["b1", "b1", "b2"]`` must surface exactly two offenders.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1", "b1", "b2"]},
    )
    assert resp.status_code == 400
    assert resp.json()["details"]["invalidIssueIds"] == ["b1", "b2"]


@pytest.mark.asyncio
async def test_add_members_does_not_leak_foreign_project_id(
    client: AsyncClient, factory,
):
    """Tenant-isolation regression guard: the response carries the
    caller-supplied invalidIssueIds (legitimate echo — they sent them) and
    the GROUP's project id, but NEVER the foreign project's id those
    offenders belong to.

    Without this test, a future helper change that surfaced
    ``offenderProjectIds`` "for debugging" would leak project B's existence
    to a project A caller through the error envelope.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1", "b2"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    # The group's projectId is fine — caller is allowed to know that.
    assert body["details"]["projectId"] == "proj-A"
    # But proj-B (the foreign project) must not appear anywhere in the
    # response — not in details, not in the message string, not as a
    # value of any other field. Walk the JSON looking for it.
    payload_text = repr(body)
    assert "proj-B" not in payload_text


@pytest.mark.asyncio
async def test_add_members_existing_membership_unchanged_after_rejection(
    client: AsyncClient, factory,
):
    """A rejected bulk-add must not disturb existing membership rows.

    Setup: group already has a1 as member (position=1). Bulk-post adds
    [b1] — which is cross-project and must reject. After the failed call,
    a1's membership row must be unchanged (same id, same position).

    Guards against a future ``DELETE then re-INSERT`` refactor that would
    drop existing rows in a transaction that then aborts on the validator
    raise — leaving the table empty if rollback is missed.
    """
    await _seed_group_in_proj_a(factory)
    async with factory() as db:
        db.add(IssueGroupMember(
            id=str(uuid.uuid4()),
            groupId="grp-A", issueId="a1", position=1,
        ))
        await db.commit()

    # Snapshot the row before the failed call.
    async with factory() as db:
        before = (await db.execute(
            select(IssueGroupMember).where(
                IssueGroupMember.groupId == "grp-A",
            )
        )).scalars().all()
    before_snapshot = sorted((m.issueId, m.position) for m in before)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["b1"]},
    )
    assert resp.status_code == 400

    # Re-read and confirm membership unchanged.
    async with factory() as db:
        after = (await db.execute(
            select(IssueGroupMember).where(
                IssueGroupMember.groupId == "grp-A",
            )
        )).scalars().all()
    after_snapshot = sorted((m.issueId, m.position) for m in after)
    assert after_snapshot == before_snapshot
    assert before_snapshot == [("a1", 1)]


# =========================================================================
# Sentinel cases — proves the rejections above are keyed on cross-project
# =========================================================================

@pytest.mark.asyncio
async def test_create_same_project_201_sentinel(
    client: AsyncClient, factory,
):
    """All-same-project create must succeed. Without this sentinel, the
    negative tests could falsely pass if the endpoint were broken in a way
    that rejected every payload regardless of project.
    """
    await _seed_two_projects_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-A/groups",
        json={"title": "Sane", "issueIds": ["a1", "a2"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["projectId"] == "proj-A"
    assert body["memberCount"] == 2


@pytest.mark.asyncio
async def test_add_members_same_project_201_sentinel(
    client: AsyncClient, factory,
):
    """Same sentinel for add_group_members — proves the negative tests
    aren't silently passing because of a different upstream rejection.

    Confirms BOTH the wire response AND the persisted DB rows. Without
    the DB-side check, a future refactor that returned added=[a1,a2]
    from the request payload without actually inserting (e.g. background
    job queueing) would falsely pass.
    """
    await _seed_group_in_proj_a(factory)

    resp = await client.post(
        "/api/groups/grp-A/members",
        json={"issueIds": ["a1", "a2"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["added"] == ["a1", "a2"]
    assert body["skipped"] == []

    async with factory() as db:
        rows = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.position)
        )).scalars().all()
    assert [(r.issueId, r.position) for r in rows] == [("a1", 1), ("a2", 2)]


# =========================================================================
# Helper unit-layer — pin the shared validator's contract directly
# =========================================================================
#
# Both routes delegate to ``utils.validators.validate_same_project_members``.
# Hitting the helper directly gives us a route-independent guarantee on the
# exception types, message text, and details envelope — so a future
# refactor that swaps which endpoint calls which helper can't silently
# break the contract on one side.

@pytest.mark.asyncio
async def test_helper_raises_validation_error_create_call_site(factory):
    """Direct invocation without ``group_id``: ValidationError carries
    {projectId, invalidIssueIds} and the create-shaped message."""
    await _seed_two_projects_with_issues(factory)

    async with factory() as db:
        with pytest.raises(ValidationError) as excinfo:
            await validate_same_project_members(
                db, "proj-A", ["a1", "b1", "b2"],
            )

    err = excinfo.value
    assert err.code.value == "VALIDATION_ERROR"
    assert err.message == "Issues do not belong to project"
    assert err.details is not None
    assert set(err.details.keys()) == {"projectId", "invalidIssueIds"}
    assert err.details["projectId"] == "proj-A"
    # Order IS contract: the helper preserves request order in the cross
    # list (validators.py:132). Pin it directly at the helper layer too.
    assert err.details["invalidIssueIds"] == ["b1", "b2"]
    # No foreign-id leakage at the helper layer either — neither in the
    # message format nor inside any details value. A future helper that
    # injected the foreign projectId for "debugging" would trip here.
    assert "proj-B" not in err.message
    assert "proj-B" not in repr(err.details)


@pytest.mark.asyncio
async def test_helper_raises_validation_error_add_members_call_site(factory):
    """Direct invocation WITH ``group_id``: ValidationError carries
    {projectId, groupId, invalidIssueIds} and the add-shaped message."""
    await _seed_two_projects_with_issues(factory)

    async with factory() as db:
        with pytest.raises(ValidationError) as excinfo:
            await validate_same_project_members(
                db, "proj-A", ["b1"], group_id="grp-A",
            )

    err = excinfo.value
    assert err.code.value == "VALIDATION_ERROR"
    assert err.message == "Issues do not belong to group's project"
    assert err.details is not None
    assert set(err.details.keys()) == {
        "projectId", "groupId", "invalidIssueIds",
    }
    assert err.details["groupId"] == "grp-A"
    assert err.details["invalidIssueIds"] == ["b1"]
    # Helper-layer no-leak guard mirroring the create-call-site test.
    assert "proj-B" not in err.message
    assert "proj-B" not in repr(err.details)


@pytest.mark.asyncio
async def test_helper_404_precedence_unit_layer(factory):
    """At the helper layer: missing id raises NotFoundError(Issue)
    instead of ValidationError, even when other ids in the same call are
    cross-project. The integration tests above already cover this through
    the route, but pinning at the helper layer keeps the precedence intact
    if the route were rewritten to call multiple helpers in sequence.
    """
    await _seed_two_projects_with_issues(factory)

    async with factory() as db:
        with pytest.raises(NotFoundError) as excinfo:
            await validate_same_project_members(
                db, "proj-A", ["b1", "ghost"],
            )

    err = excinfo.value
    assert err.code.value == "NOT_FOUND"
    assert err.details is not None
    assert err.details["resource"] == "Issue"
    assert err.details["identifier"] == "ghost"
    # 404 envelope leak guard at the helper layer: keys pinned, no
    # foreign-id / cross-project-id leakage through diagnostic details.
    assert set(err.details.keys()) == {"resource", "identifier"}
    assert "b1" not in repr(err.details)
    assert "proj-B" not in repr(err.details)


@pytest.mark.asyncio
async def test_helper_first_missing_wins_with_multiple_missing(factory):
    """Helper-layer pin of the docstring contract (validators.py:88-93):
    when MULTIPLE ids are missing, surface the FIRST in iteration order.
    Direct route test ``test_create_first_missing_id_wins_with_multiple_missing``
    covers the route layer; this fixes the contract at the helper itself
    so a future ``missing[-1]`` / ``random.choice(missing)`` regression is
    caught regardless of which endpoint happens to call it.
    """
    await _seed_two_projects_with_issues(factory)

    async with factory() as db:
        with pytest.raises(NotFoundError) as excinfo:
            await validate_same_project_members(
                db, "proj-A", ["ghost1", "ghost2", "b1"],
            )
    assert excinfo.value.details["identifier"] == "ghost1"


@pytest.mark.asyncio
async def test_helper_unknown_project_classifies_all_as_cross_project(factory):
    """Helper docstring (validators.py:69-71): "the caller is responsible
    for verifying this project exists — this helper assumes the FK is valid
    and only checks the issue ids against it."

    Concrete consequence: passing an unknown ``project_id`` with valid
    same-project issues yields ``cross = [all issue ids]`` — every id is
    classified as cross-project because none of them belong to the unknown
    project. This test pins that documented responsibility split so a
    future refactor that quietly added project-existence verification
    inside the helper (and changed the error type from ValidationError to
    NotFoundError) gets caught here for explicit review.
    """
    await _seed_two_projects_with_issues(factory)

    async with factory() as db:
        with pytest.raises(ValidationError) as excinfo:
            await validate_same_project_members(
                db, "proj-ghost", ["a1"],
            )

    err = excinfo.value
    assert err.code.value == "VALIDATION_ERROR"
    assert err.details["projectId"] == "proj-ghost"
    assert err.details["invalidIssueIds"] == ["a1"]


@pytest.mark.asyncio
async def test_helper_empty_id_list_is_noop(factory):
    """Empty iterable returns None without a DB round-trip — important so
    create_group with ``issueIds=None`` (which the schema converts to an
    empty list before delegating) is safe to call unconditionally."""
    await _seed_two_projects_with_issues(factory)

    async with factory() as db:
        # No raise expected. ``None`` return is implicit; the assertion is
        # that the call completes without an exception.
        result = await validate_same_project_members(db, "proj-A", [])
    assert result is None


@pytest.mark.asyncio
async def test_helper_all_same_project_passes(factory):
    """Sentinel at the helper layer: all-same-project ids are accepted
    silently, mirroring the route-level 201 sentinel."""
    await _seed_two_projects_with_issues(factory)

    async with factory() as db:
        result = await validate_same_project_members(
            db, "proj-A", ["a1", "a2"],
        )
    assert result is None
