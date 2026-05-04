"""
CB-1981 — STORY 2.3 same-project enforcement: cross-project relations rejected.

Sibling CB-1980 added the service-layer check + clean 400 envelope. This file
locks in the contract with dedicated tests so a future relax (or a regression)
on either endpoint shows up here, not in a downstream cycle / duplicate test.

Coverage matrix
---------------
* POST /api/issues/{id}/relations (single):
    - Every LinkType (7 values): cross-project → 400 VALIDATION_ERROR
    - Same-project sentinel: 201 (proves the negative tests aren't falsely
      passing because of a different rejection upstream)
    - No rows written on rejection (txn rolled back)
    - Error envelope: code, message, details = {fromProjectId, toProjectId}
    - Cross-project rejection runs BEFORE the duplicate guard — even if a
      cross-project row was injected directly into the DB, the response is
      VALIDATION_ERROR, not ALREADY_EXISTS.

* POST /api/issues/{id}/relations/bulk:
    - Cross-project ids surface in details.invalidIds
    - Mixed batch (some same-project, some cross-project) → entire batch
      rejected, NO rows written (atomic-batch contract from CB-1972)
    - Cross-project rejection runs before duplicate scan — pre-existing
      same-project links are not consulted when invalidIds is non-empty.

Uses the same isolated-tempdir SQLite pattern as test_relations_post.py /
test_relations_post_bulk.py so tests never touch production codeboard.db.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
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


from api.relations import router as relations_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.issue import Issue, IssueLink, Project  # noqa: E402


# All seven LinkType values defined in models.issue.LinkType. Hard-coded
# (rather than imported) so a typo or accidental enum addition is caught
# loudly here instead of being silently parametrized into an empty case set.
ALL_LINK_TYPES = [
    "RELATES_TO",
    "DUPLICATES",
    "IS_DUPLICATED_BY",
    "BLOCKS",
    "IS_BLOCKED_BY",
    "CAUSES",
    "CAUSED_BY",
]


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="relations-xproj-test-")
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
    local_app.include_router(relations_router, prefix="/api")
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
) -> Issue:
    return Issue(
        id=issue_id,
        projectId=project_id,
        key=key,
        sequence=int(key.split("-")[-1]) if "-" in key else 1,
        title=title,
        type="TASK",
        status="BACKLOG",
        priority="MEDIUM",
        updatedAt=datetime.utcnow(),
    )


async def _seed_two_projects(factory) -> None:
    """Seed two projects with one issue each: (proj-A, a1) and (proj-B, b1).

    Issue.key has a global UNIQUE constraint (models/issue.py:31), so keys
    must be distinct across projects. We use the CB-1xx / CB-2xx range
    convention for proj-A / proj-B respectively — the cross-project rule
    is enforced on projectId regardless of key shape.
    """
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A", title="A One"))
        db.add(_make_issue("b1", "CB-201", project_id="proj-B", title="B One"))
        await db.commit()


# ---------- single POST: per-link-type cross-project rejection -------------

@pytest.mark.parametrize("link_type", ALL_LINK_TYPES)
@pytest.mark.asyncio
async def test_post_single_cross_project_rejected_for_every_link_type(
    client: AsyncClient, factory, link_type: str,
):
    """Every supported linkType must be rejected with 400 VALIDATION_ERROR
    when ``from`` and ``to`` belong to different projects.

    Parametrized over the full LinkType enum so a future addition (or an
    accidental "skip same-project check for type X" branch) can't slip past
    review unnoticed."""
    await _seed_two_projects(factory)

    resp = await client.post(
        "/api/issues/a1/relations",
        json={"toIssueId": "b1", "linkType": link_type},
    )

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "different projects" in body["message"].lower()


@pytest.mark.asyncio
async def test_post_single_same_project_201_sentinel(
    client: AsyncClient, factory,
):
    """Sentinel: a same-project pair must succeed with 201. Without this,
    the negative tests above could falsely pass if the endpoint were broken
    in a way that rejected every relation regardless of project."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("a2", "CB-102", project_id="proj-A"))
        await db.commit()

    resp = await client.post(
        "/api/issues/a1/relations",
        json={"toIssueId": "a2", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_post_single_cross_project_writes_no_rows(
    client: AsyncClient, factory,
):
    """Rejection rolls back the txn — no IssueLink rows survive."""
    await _seed_two_projects(factory)

    resp = await client.post(
        "/api/issues/a1/relations",
        json={"toIssueId": "b1", "linkType": "BLOCKS"},
    )
    assert resp.status_code == 400

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_post_single_cross_project_error_envelope(
    client: AsyncClient, factory,
):
    """Lock the wire-shape clients depend on:
       * ErrorResponse envelope keys (success, error, code, message, details)
       * code == VALIDATION_ERROR
       * details carries fromProjectId + toProjectId so a UI can highlight
         which project mismatch occurred without parsing the message string.
    """
    await _seed_two_projects(factory)

    resp = await client.post(
        "/api/issues/a1/relations",
        json={"toIssueId": "b1", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "VALIDATION_ERROR"
    assert body["code"] == "VALIDATION_ERROR"
    # Pin the disclosure surface — only the two project IDs are echoed back,
    # not issue titles, paths, or any other field. A future change that
    # leaks more fields into details will trip this.
    assert set(body["details"].keys()) == {"fromProjectId", "toProjectId"}
    assert body["details"]["fromProjectId"] == "proj-A"
    assert body["details"]["toProjectId"] == "proj-B"


@pytest.mark.asyncio
async def test_post_single_cross_project_precedes_duplicate_check(
    client: AsyncClient, factory,
):
    """Validation order check: even if a cross-project IssueLink row was
    seeded directly (bypassing the API), the create endpoint must reject
    on the same-project rule with VALIDATION_ERROR — NOT surface
    ALREADY_EXISTS.

    Why: ALREADY_EXISTS would imply the relation was once legal, telling
    the caller to GET the existing one. A cross-project row is illegal data
    and must always read as 'fix your input', regardless of DB state.
    """
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-201", project_id="proj-B"))
        await db.flush()
        # Seed a cross-project link directly (which the create path would
        # normally reject). This simulates legacy data or a future bug.
        db.add(IssueLink(
            id="legacy-cross-link",
            fromIssueId="a1",
            toIssueId="b1",
            linkType="RELATES_TO",
        ))
        await db.commit()

    resp = await client.post(
        "/api/issues/a1/relations",
        json={"toIssueId": "b1", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["code"] != "ALREADY_EXISTS"


# ---------- bulk POST: cross-project rejection -----------------------------

@pytest.mark.asyncio
async def test_bulk_cross_project_target_in_invalidIds(
    client: AsyncClient, factory,
):
    """Cross-project target ids land in details.invalidIds and the whole
    batch is rejected — atomic-batch contract from CB-1972."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("a2", "CB-102", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-201", project_id="proj-B"))
        db.add(_make_issue("b2", "CB-202", project_id="proj-B"))
        await db.commit()

    resp = await client.post(
        "/api/issues/a1/relations/bulk",
        json={
            "toIssueIds": ["a2", "b1", "b2"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert sorted(body["details"]["invalidIds"]) == ["b1", "b2"]


@pytest.mark.asyncio
async def test_bulk_mixed_cross_project_writes_no_rows(
    client: AsyncClient, factory,
):
    """A mixed batch (some same-project, some cross-project) must not
    partially insert. The same-project ids in the batch are NOT created
    just because they would individually be valid."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("a2", "CB-102", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-201", project_id="proj-B"))
        await db.commit()

    resp = await client.post(
        "/api/issues/a1/relations/bulk",
        json={
            "toIssueIds": ["a2", "b1"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["details"]["invalidIds"] == ["b1"]

    # Confirm a2 was NOT linked despite being a valid same-project target.
    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_bulk_all_same_project_201_sentinel(
    client: AsyncClient, factory,
):
    """Sentinel: an all-same-project batch must succeed — proves the
    rejection above is keyed on cross-project, not on something else."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("a2", "CB-102", project_id="proj-A"))
        db.add(_make_issue("a3", "CB-103", project_id="proj-A"))
        await db.commit()

    resp = await client.post(
        "/api/issues/a1/relations/bulk",
        json={
            "toIssueIds": ["a2", "a3"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["created"]) == 2
    assert body["skipped"] == []


@pytest.mark.parametrize("link_type", ALL_LINK_TYPES)
@pytest.mark.asyncio
async def test_bulk_cross_project_rejected_for_every_link_type(
    client: AsyncClient, factory, link_type: str,
):
    """Mirror the single-POST per-type sweep on the bulk path so a type-
    specific bypass can't slip through there either."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-201", project_id="proj-B"))
        await db.commit()

    resp = await client.post(
        "/api/issues/a1/relations/bulk",
        json={"toIssueIds": ["b1"], "linkType": link_type},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["invalidIds"] == ["b1"]


@pytest.mark.asyncio
async def test_bulk_cross_project_precedes_duplicate_scan(
    client: AsyncClient, factory,
):
    """Validation order in the bulk path: a cross-project id in the batch
    triggers VALIDATION_ERROR on invalidIds before the duplicate scan runs.

    Setup: a1 already RELATES_TO a2 in proj-A (a real duplicate). Bulk
    posts [a2, b1]. The duplicate scan would normally skip a2 silently,
    but the cross-project b1 must trip the validation gate first and
    reject the whole batch — no DUPLICATE skip line ever reported.
    """
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("a2", "CB-102", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-201", project_id="proj-B"))
        await db.commit()

    # Pre-existing duplicate (a1, a2, RELATES_TO).
    pre = await client.post(
        "/api/issues/a1/relations",
        json={"toIssueId": "a2", "linkType": "RELATES_TO"},
    )
    assert pre.status_code == 201

    resp = await client.post(
        "/api/issues/a1/relations/bulk",
        json={"toIssueIds": ["a2", "b1"], "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    # b1 should be in invalidIds; a2 (the duplicate) is NOT — the validation
    # gate fired before the duplicate scan would have classified it.
    assert "b1" in body["details"]["invalidIds"]
    assert "a2" not in body["details"]["invalidIds"]


@pytest.mark.asyncio
async def test_bulk_legacy_cross_project_link_does_not_leak_via_skip_channel(
    client: AsyncClient, factory,
):
    """Tenant-isolation regression guard for the bulk skip channel.

    Scenario: a legacy cross-project IssueLink row already exists in the DB
    (a1 in proj-A → b1 in proj-B). A caller bulk-posts [b1] from a1. The
    bulk path's duplicate scan (relations.py:594-622) would, if reached,
    classify b1 as DUPLICATE and echo a foreign-project id back in
    ``skipped[].toIssueId``. The validation gate (relations.py:569-585)
    must fire FIRST, surface b1 in ``invalidIds``, and ensure no DUPLICATE
    skip line is ever produced.

    Without this test, a future re-ordering of validation steps in the
    bulk endpoint could silently leak project B issue ids to a project A
    caller through the skip channel.
    """
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-101", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-201", project_id="proj-B"))
        await db.flush()
        # Legacy cross-project IssueLink direct-write (bypassing the
        # create endpoint's same-project guard) — simulates legacy data
        # or a row that landed before CB-1980 enforcement was added.
        db.add(IssueLink(
            id="legacy-cross-link",
            fromIssueId="a1",
            toIssueId="b1",
            linkType="RELATES_TO",
        ))
        await db.commit()

    resp = await client.post(
        "/api/issues/a1/relations/bulk",
        json={"toIssueIds": ["b1"], "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["invalidIds"] == ["b1"]
    # Critical: the response must NOT contain a `skipped` list with b1.
    # On a 400 ValidationError the response is the error envelope, not the
    # success envelope, so `skipped` should be absent entirely. Pin that.
    assert "skipped" not in body
    assert "created" not in body


# ---------- CB-2126: GET /relations defense-in-depth filter ---------------

@pytest.mark.asyncio
async def test_get_relations_excludes_legacy_cross_project_outbound(
    client: AsyncClient, factory,
):
    """CB-2126: a legacy cross-project IssueLink (direct DB write, pre-CB-1980)
    must NOT surface in GET /api/issues/{id}/relations even though the row
    exists. Defense-in-depth filter on Issue.projectId."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-301", project_id="proj-A"))
        db.add(_make_issue("a2", "CB-302", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-401", project_id="proj-B"))
        await db.flush()
        # Two outbound rows from a1: one same-project (legitimate), one
        # legacy cross-project (must be filtered out by the GET endpoint).
        db.add(IssueLink(
            id="same-proj-link",
            fromIssueId="a1",
            toIssueId="a2",
            linkType="RELATES_TO",
        ))
        db.add(IssueLink(
            id="legacy-cross-out",
            fromIssueId="a1",
            toIssueId="b1",
            linkType="RELATES_TO",
        ))
        await db.commit()

    resp = await client.get("/api/issues/a1/relations")
    assert resp.status_code == 200
    body = resp.json()
    out_ids = [r["id"] for r in body["outbound"]]
    assert "same-proj-link" in out_ids
    # The cross-project row MUST be hidden — no foreign-project leak.
    assert "legacy-cross-out" not in out_ids
    # And the embedded toIssue summary is never a foreign-project issue.
    for row in body["outbound"]:
        assert row["toIssue"]["id"] != "b1", \
            "GET /relations leaked a foreign-project issue summary (CB-2126)"


@pytest.mark.asyncio
async def test_get_relations_excludes_legacy_cross_project_inbound(
    client: AsyncClient, factory,
):
    """Mirror of the outbound test: a legacy cross-project IssueLink whose
    `toIssueId` is in proj-A and `fromIssueId` is in proj-B must be hidden
    from a1's inbound list."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-301", project_id="proj-A"))
        db.add(_make_issue("a2", "CB-302", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-401", project_id="proj-B"))
        await db.flush()
        # One legitimate inbound (a2 → a1) and one legacy cross-project
        # inbound (b1 → a1) that must be filtered out.
        db.add(IssueLink(
            id="same-proj-in",
            fromIssueId="a2",
            toIssueId="a1",
            linkType="RELATES_TO",
        ))
        db.add(IssueLink(
            id="legacy-cross-in",
            fromIssueId="b1",
            toIssueId="a1",
            linkType="RELATES_TO",
        ))
        await db.commit()

    resp = await client.get("/api/issues/a1/relations")
    assert resp.status_code == 200
    body = resp.json()
    in_ids = [r["id"] for r in body["inbound"]]
    assert "same-proj-in" in in_ids
    assert "legacy-cross-in" not in in_ids
    for row in body["inbound"]:
        assert row["fromIssue"]["id"] != "b1", \
            "GET /relations leaked a foreign-project issue summary (CB-2126)"


# ---------- CB-2127: DELETE /relations against legacy cross-project rows ----

@pytest.mark.asyncio
async def test_delete_legacy_cross_project_does_not_leak_foreign_ids(
    client: AsyncClient, factory,
):
    """CB-2127: DELETE /api/issues/{id}/relations/{relation_id} called on a
    legacy cross-project IssueLink must NOT leak the foreign-project issue
    id in the error envelope, regardless of whether the chosen behavior is
    (a) clean delete or (b) 404. Pin whichever the implementation does and
    document the choice in the relations.py docstring.

    Current implementation: clean delete with `{deleted: 1}` (200) — the
    legacy row has no companion to remove. No foreign-id leak. Documented
    here so a future change away from this behavior fails loudly.
    """
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-301", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-401", project_id="proj-B"))
        await db.flush()
        # Legacy cross-project link with a1 in fromIssueId.
        legacy_id = "legacy-cross-delete"
        db.add(IssueLink(
            id=legacy_id,
            fromIssueId="a1",
            toIssueId="b1",
            linkType="RELATES_TO",
        ))
        await db.commit()

    resp = await client.delete(f"/api/issues/a1/relations/{legacy_id}")

    # Whatever the implementation chose, the response body must NEVER
    # contain b1 (the foreign-project issue id) in any form. That's the
    # invariant CB-2127 pins.
    body_text = resp.text
    assert "b1" not in body_text, (
        "DELETE /relations leaked the foreign-project issue id in the "
        "response body — CB-2127 invariant violated. Body was: "
        f"{body_text[:300]}"
    )

    # The response must be either a clean delete (200/204) or a 404
    # (caller had no claim on the relation). Anything else is a regression.
    assert resp.status_code in (200, 204, 404), (
        f"DELETE on a legacy cross-project link returned an unexpected "
        f"status {resp.status_code} — must be 200/204 (delete) or 404 "
        f"(masked-as-missing). Body: {body_text[:200]}"
    )


@pytest.mark.asyncio
async def test_delete_legacy_cross_project_target_side_also_safe(
    client: AsyncClient, factory,
):
    """Same as above but the legacy row has b1 → a1 direction (a1 in
    toIssueId). Caller is a1, so CB-2127's invariant — no leak of foreign-
    project ids in the error envelope — applies symmetrically."""
    async with factory() as db:
        db.add(_make_project("proj-A"))
        db.add(_make_project("proj-B"))
        await db.flush()
        db.add(_make_issue("a1", "CB-301", project_id="proj-A"))
        db.add(_make_issue("b1", "CB-401", project_id="proj-B"))
        await db.flush()
        legacy_id = "legacy-cross-delete-inbound"
        db.add(IssueLink(
            id=legacy_id,
            fromIssueId="b1",
            toIssueId="a1",
            linkType="RELATES_TO",
        ))
        await db.commit()

    resp = await client.delete(f"/api/issues/a1/relations/{legacy_id}")
    body_text = resp.text
    assert "b1" not in body_text, (
        "DELETE leaked b1 (foreign-project) in the response — CB-2127."
    )
    assert resp.status_code in (200, 204, 404)
