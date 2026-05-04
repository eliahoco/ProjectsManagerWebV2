"""
CB-1971 — POST /api/issues/{id}/relations.

Covers the full validation and behavior contract:
  * 201 — happy path (transitive + non-transitive types)
  * primary + companion inverse rows written in same transaction
  * RELATES_TO writes a symmetric companion (different (from,to) row)
  * 400 — self-link rejection
  * 400 — cross-project rejection
  * 409 CYCLE_DETECTED — cycle detection (BLOCKS, IS_BLOCKED_BY, CAUSES,
    CAUSED_BY). Body includes ``details.path`` = closed cycle in canonical
    family-graph direction (CB-1977).
  * 404 — source missing / target missing
  * 409 ALREADY_EXISTS — duplicate primary row, duplicate companion-only row,
    same (from,to,type) re-POST
  * 422 — unknown linkType (Pydantic enum guard)
  * Response embeds fromIssue / toIssue summaries (CB-1960 contract)

Uses an isolated on-disk SQLite mirroring the test_doc_settings.py pattern,
so tests never touch production codeboard.db.
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


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="relations-post-test-")
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

def _make_project(project_id: str = "proj-1") -> Project:
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
    project_id: str = "proj-1",
    title: str = "Test Issue",
    status_: str = "BACKLOG",
) -> Issue:
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


async def _seed_two_issues(factory) -> None:
    """Seed proj-1 + two issues (i1, i2) used by the bulk of tests."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", title="Issue 1"))
        db.add(_make_issue("i2", "CB-2", title="Issue 2", status_="IN_PROGRESS"))
        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_create_blocks_writes_primary_and_companion(
    client: AsyncClient, factory,
):
    """A BLOCKS B → primary (A,B,BLOCKS) + companion (B,A,IS_BLOCKED_BY)."""
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["fromIssueId"] == "i1"
    assert body["toIssueId"] == "i2"
    assert body["linkType"] == "BLOCKS"
    assert body["fromIssue"] == {
        "id": "i1", "key": "CB-1", "title": "Issue 1", "status": "BACKLOG",
    }
    assert body["toIssue"] == {
        "id": "i2", "key": "CB-2", "title": "Issue 2", "status": "IN_PROGRESS",
    }

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "BLOCKS"),
        ("i2", "i1", "IS_BLOCKED_BY"),
    ]


@pytest.mark.asyncio
async def test_create_relates_to_writes_symmetric_companion(
    client: AsyncClient, factory,
):
    """RELATES_TO is its own inverse — companion is (to, from, RELATES_TO),
    a distinct row under UNIQUE(from, to, type)."""
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 201, resp.text

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "RELATES_TO"),
        ("i2", "i1", "RELATES_TO"),
    ]


@pytest.mark.asyncio
async def test_create_duplicates_writes_inverse_pair(
    client: AsyncClient, factory,
):
    """DUPLICATES → IS_DUPLICATED_BY companion."""
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "DUPLICATES"},
    )
    assert resp.status_code == 201, resp.text

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "DUPLICATES"),
        ("i2", "i1", "IS_DUPLICATED_BY"),
    ]


# ---------- self-link & cross-project & 404 --------------------------------

@pytest.mark.asyncio
async def test_self_link_rejected(client: AsyncClient, factory):
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i1", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "itself" in body["message"].lower()

    # Nothing inserted.
    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_cross_project_rejected(client: AsyncClient, factory):
    """Issues from different projects cannot be linked."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        db.add(_make_project("proj-2"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id="proj-1"))
        db.add(_make_issue("i2", "CB-2", project_id="proj-2"))
        await db.commit()

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "different projects" in body["message"].lower()


@pytest.mark.asyncio
async def test_source_missing_returns_404(client: AsyncClient, factory):
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/does-not-exist/relations",
        json={"toIssueId": "i1", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_target_missing_returns_404(client: AsyncClient, factory):
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "ghost", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------- 409 ALREADY_EXISTS --------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_primary_returns_409(client: AsyncClient, factory):
    """Re-POSTing the same (from, to, type) yields ALREADY_EXISTS."""
    await _seed_two_issues(factory)

    first = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_inverse_existing_blocks_create(client: AsyncClient, factory):
    """If a companion-equivalent row already exists from a prior insert
    (e.g. user POSTed B IS_BLOCKED_BY A, which wrote (A, B, BLOCKS) as
    companion), POSTing (A, BLOCKS, B) is treated as duplicate."""
    await _seed_two_issues(factory)

    # User A: i2 IS_BLOCKED_BY i1 → primary (i2,i1,IS_BLOCKED_BY) + companion (i1,i2,BLOCKS)
    first = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "IS_BLOCKED_BY"},
    )
    assert first.status_code == 201

    # User B then tries to write (i1, BLOCKS, i2) — already in DB as companion.
    second = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "ALREADY_EXISTS"


# ---------- cycle detection ------------------------------------------------

@pytest.mark.asyncio
async def test_blocks_cycle_rejected(client: AsyncClient, factory):
    """A BLOCKS B, B BLOCKS C, then C BLOCKS A → 409 CYCLE_DETECTED.

    Asserts the CB-1977 contract: status 409, code CYCLE_DETECTED, body
    carries ``details.path`` = closed cycle in canonical family direction.
    For BLOCKS the canonical direction matches user-facing direction, so
    the path is [i3, i1, i2, i3] (new edge i3→i1 plus existing i1→i2→i3).
    """
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i, key in enumerate(["CB-1", "CB-2", "CB-3"], start=1):
            db.add(_make_issue(f"i{i}", key))
        await db.commit()

    a = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert a.status_code == 201, a.text
    b = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i3", "linkType": "BLOCKS"},
    )
    assert b.status_code == 201, b.text

    cyc = await client.post(
        "/api/issues/i3/relations",
        json={"toIssueId": "i1", "linkType": "BLOCKS"},
    )
    assert cyc.status_code == 409
    body = cyc.json()
    assert body["code"] == "CYCLE_DETECTED"
    assert "cycle" in body["message"].lower()
    details = body["details"]
    assert details["fromIssueId"] == "i3"
    assert details["toIssueId"] == "i1"
    assert details["linkType"] == "BLOCKS"
    # Path is closed cycle in canonical direction. For BLOCKS canonical
    # is from→to, so new edge i3→i1 plus existing i1→i2→i3 = [i3,i1,i2,i3].
    assert details["path"] == ["i3", "i1", "i2", "i3"]

    # Nothing inserted on cycle rejection — txn rolled back.
    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "BLOCKS"),
        ("i2", "i1", "IS_BLOCKED_BY"),
        ("i2", "i3", "BLOCKS"),
        ("i3", "i2", "IS_BLOCKED_BY"),
    ]


@pytest.mark.asyncio
async def test_is_blocked_by_cycle_rejected(client: AsyncClient, factory):
    """A IS_BLOCKED_BY B (≡ B BLOCKS A), B IS_BLOCKED_BY C, then A BLOCKS C
    would close: A→C exists already as transitive — adding A BLOCKS C is fine.
    But adding C IS_BLOCKED_BY A (≡ A BLOCKS C) when A is already blocked-by
    chain leading to C should fail."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i, key in enumerate(["CB-1", "CB-2", "CB-3"], start=1):
            db.add(_make_issue(f"i{i}", key))
        await db.commit()

    # i1 IS_BLOCKED_BY i2 → BLOCKS graph: i2→i1
    r1 = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "IS_BLOCKED_BY"},
    )
    assert r1.status_code == 201
    # i2 IS_BLOCKED_BY i3 → BLOCKS graph: i3→i2
    r2 = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i3", "linkType": "IS_BLOCKED_BY"},
    )
    assert r2.status_code == 201

    # i3 IS_BLOCKED_BY i1 → BLOCKS graph would add i1→i3, closing i1→i3→i2→i1.
    cyc = await client.post(
        "/api/issues/i3/relations",
        json={"toIssueId": "i1", "linkType": "IS_BLOCKED_BY"},
    )
    assert cyc.status_code == 409
    body = cyc.json()
    assert body["code"] == "CYCLE_DETECTED"
    # Canonical edge for "i3 IS_BLOCKED_BY i1" flips to i1→i3 in the BLOCKS
    # family. Existing canonical edges are i2→i1 and i3→i2 (from earlier
    # IS_BLOCKED_BY posts). New edge + existing path: i1→i3→i2→i1.
    assert body["details"]["path"] == ["i1", "i3", "i2", "i1"]


@pytest.mark.asyncio
async def test_causes_cycle_rejected(client: AsyncClient, factory):
    """CAUSES is its own independent transitive graph from BLOCKS."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i, key in enumerate(["CB-1", "CB-2", "CB-3"], start=1):
            db.add(_make_issue(f"i{i}", key))
        await db.commit()

    a = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "CAUSES"},
    )
    assert a.status_code == 201
    b = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i3", "linkType": "CAUSES"},
    )
    assert b.status_code == 201

    cyc = await client.post(
        "/api/issues/i3/relations",
        json={"toIssueId": "i1", "linkType": "CAUSES"},
    )
    assert cyc.status_code == 409
    body = cyc.json()
    assert body["code"] == "CYCLE_DETECTED"
    assert body["details"]["path"] == ["i3", "i1", "i2", "i3"]


@pytest.mark.asyncio
async def test_blocks_and_causes_are_independent_graphs(
    client: AsyncClient, factory,
):
    """BLOCKS-chain doesn't cause CAUSES-chain to be flagged as cyclic."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i, key in enumerate(["CB-1", "CB-2"], start=1):
            db.add(_make_issue(f"i{i}", key))
        await db.commit()

    # i1 BLOCKS i2 — populates BLOCKS graph only.
    r1 = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert r1.status_code == 201

    # i2 CAUSES i1 — different family, must not be flagged.
    r2 = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "CAUSES"},
    )
    assert r2.status_code == 201, r2.text


@pytest.mark.asyncio
async def test_relates_to_skips_cycle_check(client: AsyncClient, factory):
    """RELATES_TO is non-transitive — chains never produce cycle errors."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i, key in enumerate(["CB-1", "CB-2", "CB-3"], start=1):
            db.add(_make_issue(f"i{i}", key))
        await db.commit()

    for src, dst in (("i1", "i2"), ("i2", "i3"), ("i3", "i1")):
        r = await client.post(
            f"/api/issues/{src}/relations",
            json={"toIssueId": dst, "linkType": "RELATES_TO"},
        )
        assert r.status_code == 201, r.text


# ---------- input shape ----------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_link_type_returns_422(client: AsyncClient, factory):
    """Unknown linkType is rejected by Pydantic enum validation."""
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BOGUS_TYPE"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_extra_fields_rejected(client: AsyncClient, factory):
    """Over-posting unknown fields is rejected by extra='forbid' (CB-1971
    security hardening — defense in depth against mass assignment)."""
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={
            "toIssueId": "i2",
            "linkType": "RELATES_TO",
            "id": "attacker-chosen-id",
            "fromIssueId": "wrong",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_to_issue_id_with_control_char_rejected(
    client: AsyncClient, factory,
):
    """CRLF / control chars in toIssueId are rejected by the regex pattern,
    blocking log-injection through the IntegrityError handler."""
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={
            "toIssueId": "i2\r\nFAKE LOG LINE",
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_blocks_length_two_cycle_rejected(
    client: AsyncClient, factory,
):
    """Length-2 cycle: A BLOCKS B then B BLOCKS A → cycle detected.

    The duplicate guard only fires on identical or inverse-companion rows;
    here neither (i2,i1,BLOCKS) nor (i1,i2,IS_BLOCKED_BY) exists yet, so
    the request reaches the cycle check, which sees i1→i2 in the BLOCKS
    graph and rejects the would-be i2→i1 edge as a 2-cycle.
    """
    await _seed_two_issues(factory)

    first = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "BLOCKS"},
    )
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "CYCLE_DETECTED"
    assert "cycle" in body["message"].lower()
    # Length-2 cycle path: new i2→i1 plus existing i1→i2 = [i2,i1,i2].
    assert body["details"]["path"] == ["i2", "i1", "i2"]


@pytest.mark.asyncio
async def test_cycle_detected_response_envelope(
    client: AsyncClient, factory,
):
    """CB-1977: cycle response must carry ``code: CYCLE_DETECTED`` and
    a ``details.path`` of strings under the standard ErrorResponse envelope.
    Distinct from ALREADY_EXISTS / VALIDATION_ERROR despite all sharing
    the 4xx range — clients distinguish on ``code``, not status.
    """
    await _seed_two_issues(factory)

    first = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert first.status_code == 201

    cyc = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "BLOCKS"},
    )
    assert cyc.status_code == 409
    body = cyc.json()
    # Standard ErrorResponse envelope.
    assert body["success"] is False
    assert body["error"] == "CYCLE_DETECTED"
    assert body["code"] == "CYCLE_DETECTED"
    # Distinguishable from ALREADY_EXISTS (also 409).
    assert body["code"] != "ALREADY_EXISTS"
    # Details shape.
    details = body["details"]
    assert set(details) == {"fromIssueId", "toIssueId", "linkType", "path"}
    assert isinstance(details["path"], list)
    assert all(isinstance(node, str) for node in details["path"])
    # Path is a closed cycle: starts and ends at the same node.
    assert details["path"][0] == details["path"][-1]
    # Path contains both endpoints of the would-be edge.
    assert "i1" in details["path"]
    assert "i2" in details["path"]


@pytest.mark.asyncio
async def test_cycle_path_truncated_for_long_chains(
    client: AsyncClient, factory,
):
    """CB-1977 audit fix: ``details.path`` is capped at 50 nodes with
    ``truncated: true`` so a pathological 100-link chain can't ship a
    multi-KB array to the client. Build a 60-node BLOCKS chain
    i1→i2→...→i60, then close it with i60 BLOCKS i1.
    """
    # Seed 60 issues + chain.
    n = 60
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i in range(1, n + 1):
            db.add(_make_issue(f"i{i}", f"CB-{i}"))
        await db.commit()

    # Build chain via repeated POSTs (each writes 2 rows in same txn).
    for i in range(1, n):
        r = await client.post(
            f"/api/issues/i{i}/relations",
            json={"toIssueId": f"i{i+1}", "linkType": "BLOCKS"},
        )
        assert r.status_code == 201, r.text

    # Closing edge i60 BLOCKS i1 → cycle of length 61 ([i60, i1, i2, ..., i60]).
    cyc = await client.post(
        f"/api/issues/i{n}/relations",
        json={"toIssueId": "i1", "linkType": "BLOCKS"},
    )
    assert cyc.status_code == 409
    body = cyc.json()
    assert body["code"] == "CYCLE_DETECTED"
    details = body["details"]
    assert details["truncated"] is True
    # Path is capped at 50 elements (including the "..." sentinel).
    assert len(details["path"]) <= 50
    assert "..." in details["path"]
    # Endpoints (the source) stay visible at start + end.
    assert details["path"][0] == "i60"
    assert details["path"][-1] == "i60"


@pytest.mark.asyncio
async def test_cycle_bfs_does_not_traverse_other_projects(
    client: AsyncClient, factory,
):
    """CB-1977 audit fix: BFS filters by ``Issue.projectId``, so a row in
    project B cannot leak into ``details.path`` for a request that posts
    a relation in project A. Direct DB write seeds a cross-project row
    (which the create path would normally reject) and confirms the BFS
    skips it.
    """
    async with factory() as db:
        db.add(_make_project("proj-1"))
        db.add(_make_project("proj-2"))
        await db.flush()
        # proj-1: i1, i2; proj-2: i3
        db.add(_make_issue("i1", "CB-1", project_id="proj-1"))
        db.add(_make_issue("i2", "CB-2", project_id="proj-1"))
        db.add(_make_issue("i3", "CB-3", project_id="proj-2"))
        await db.flush()
        # Direct-write a cross-project BLOCKS row i2→i3 (bypassing the
        # create endpoint's same-project guard) — simulates legacy data
        # or a future migration leaking into the family graph.
        db.add(IssueLink(
            id="cross-proj-link",
            fromIssueId="i2",
            toIssueId="i3",
            linkType="BLOCKS",
        ))
        await db.commit()

    # Build i1 BLOCKS i2 in proj-1 normally.
    r = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert r.status_code == 201

    # Now post i2 BLOCKS i1 in proj-1 → 2-cycle. BFS from i1 in proj-1
    # must NOT traverse the cross-project i2→i3 edge while reconstructing
    # the path. (i3 should never appear in details.path.)
    cyc = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "BLOCKS"},
    )
    assert cyc.status_code == 409
    body = cyc.json()
    assert body["code"] == "CYCLE_DETECTED"
    # i3 (different project) MUST NOT appear in the path.
    assert "i3" not in body["details"]["path"]
    assert body["details"]["path"] == ["i2", "i1", "i2"]


@pytest.mark.asyncio
async def test_self_link_with_missing_issue_returns_400_not_404(
    client: AsyncClient, factory,
):
    """Validation order: self-link is checked before existence. POSTing a
    self-link with a non-existent issue must surface 400 (self-link), not
    404 (not found)."""
    await _seed_two_issues(factory)

    resp = await client.post(
        "/api/issues/ghost/relations",
        json={"toIssueId": "ghost", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"
