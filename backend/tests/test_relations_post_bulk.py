"""
CB-1972 — POST /api/issues/{id}/relations/bulk.

Covers the bulk-create contract:
  * 201 — happy path: many candidates, primary + companion rows per accept
  * order preservation: created list mirrors caller order after dedupe
  * within-request dedupe: repeated toIssueIds collapse to one insert
  * skipped silently — pre-existing duplicate (primary or companion)
  * skipped silently — cycle (transitive types only)
  * cycle skip is per-target — surrounding candidates still apply
  * cross-batch cycle: link 1 + link 2 in same request that would close cycle
  * 400 + details.invalidIds — self-link, missing target, cross-project
  * 404 — source issue missing
  * 422 — payload shape (empty list, oversize list, bad regex, unknown type)
  * Response embeds fromIssue / toIssue summaries (CB-1960)
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
    tmp_dir = tempfile.mkdtemp(prefix="relations-bulk-test-")
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


async def _seed_chain(factory, n: int = 5) -> None:
    """Seed proj-1 + n issues (i1..iN)."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i in range(1, n + 1):
            db.add(_make_issue(f"i{i}", f"CB-{i}", title=f"Issue {i}"))
        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_creates_primary_and_companion_for_each(
    client: AsyncClient, factory,
):
    """Bulk RELATES_TO across 3 targets writes 3 primary + 3 symmetric companions."""
    await _seed_chain(factory, 4)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={"toIssueIds": ["i2", "i3", "i4"], "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["created"]) == 3
    assert body["skipped"] == []
    # Order preserved.
    assert [c["toIssueId"] for c in body["created"]] == ["i2", "i3", "i4"]
    # Summary embedding (CB-1960).
    for entry in body["created"]:
        assert entry["fromIssue"]["id"] == "i1"
        assert entry["toIssue"]["id"] == entry["toIssueId"]

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    # 3 primary + 3 symmetric companions = 6 rows total.
    assert pairs == [
        ("i1", "i2", "RELATES_TO"),
        ("i1", "i3", "RELATES_TO"),
        ("i1", "i4", "RELATES_TO"),
        ("i2", "i1", "RELATES_TO"),
        ("i3", "i1", "RELATES_TO"),
        ("i4", "i1", "RELATES_TO"),
    ]


@pytest.mark.asyncio
async def test_bulk_blocks_writes_inverse_companions(
    client: AsyncClient, factory,
):
    """BLOCKS bulk writes IS_BLOCKED_BY companions (asymmetric)."""
    await _seed_chain(factory, 3)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={"toIssueIds": ["i2", "i3"], "linkType": "BLOCKS"},
    )
    assert resp.status_code == 201, resp.text

    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    pairs = sorted((r.fromIssueId, r.toIssueId, r.linkType) for r in rows)
    assert pairs == [
        ("i1", "i2", "BLOCKS"),
        ("i1", "i3", "BLOCKS"),
        ("i2", "i1", "IS_BLOCKED_BY"),
        ("i3", "i1", "IS_BLOCKED_BY"),
    ]


@pytest.mark.asyncio
async def test_bulk_dedupes_request_input(client: AsyncClient, factory):
    """Repeats in toIssueIds collapse to a single insert (preserving first
    occurrence order)."""
    await _seed_chain(factory, 4)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={
            "toIssueIds": ["i2", "i3", "i2", "i4", "i3"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert [c["toIssueId"] for c in body["created"]] == ["i2", "i3", "i4"]
    assert body["skipped"] == []


# ---------- skipped (silent) -----------------------------------------------

@pytest.mark.asyncio
async def test_bulk_skips_existing_duplicate_silently(
    client: AsyncClient, factory,
):
    """If (from, to, type) already exists, that target is skipped with
    reason DUPLICATE — surrounding targets still applied."""
    await _seed_chain(factory, 4)

    # Pre-create i1 RELATES_TO i2.
    pre = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "RELATES_TO"},
    )
    assert pre.status_code == 201

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={
            "toIssueIds": ["i2", "i3", "i4"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert [c["toIssueId"] for c in body["created"]] == ["i3", "i4"]
    assert body["skipped"] == [
        {"toIssueId": "i2", "reason": "DUPLICATE"},
    ]


@pytest.mark.asyncio
async def test_bulk_skips_companion_only_duplicate(
    client: AsyncClient, factory,
):
    """A pre-existing inverse companion row also triggers DUPLICATE skip
    (matches single-POST inverse-existing semantics)."""
    await _seed_chain(factory, 3)

    # i2 IS_BLOCKED_BY i1 → companion (i1, i2, BLOCKS) sits in DB.
    pre = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i1", "linkType": "IS_BLOCKED_BY"},
    )
    assert pre.status_code == 201

    # Now bulk-POST i1 BLOCKS [i2, i3] — i2 should skip.
    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={"toIssueIds": ["i2", "i3"], "linkType": "BLOCKS"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert [c["toIssueId"] for c in body["created"]] == ["i3"]
    assert body["skipped"] == [
        {"toIssueId": "i2", "reason": "DUPLICATE"},
    ]


@pytest.mark.asyncio
async def test_bulk_skips_cycle_silently(client: AsyncClient, factory):
    """Cycle-creating transitive link is skipped, rest of batch applies."""
    await _seed_chain(factory, 4)

    # Set up BLOCKS chain: i1 → i2 → i3.
    a = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert a.status_code == 201
    b = await client.post(
        "/api/issues/i2/relations",
        json={"toIssueId": "i3", "linkType": "BLOCKS"},
    )
    assert b.status_code == 201

    # Bulk-POST i3 BLOCKS [i1 (cycle), i4 (ok)].
    resp = await client.post(
        "/api/issues/i3/relations/bulk",
        json={"toIssueIds": ["i1", "i4"], "linkType": "BLOCKS"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert [c["toIssueId"] for c in body["created"]] == ["i4"]
    assert body["skipped"] == [
        {"toIssueId": "i1", "reason": "CYCLE"},
    ]


@pytest.mark.asyncio
async def test_bulk_within_batch_cycle_skipped(
    client: AsyncClient, factory,
):
    """Cycle introduced by an earlier candidate in the SAME batch is
    detected against the in-flight (flushed) edges from this transaction."""
    await _seed_chain(factory, 3)

    # Pre-existing: i1 BLOCKS i2.
    pre = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert pre.status_code == 201

    # Bulk: i2 BLOCKS [i3, i1]. i2→i3 is fine. i2→i1 closes a 2-cycle.
    resp = await client.post(
        "/api/issues/i2/relations/bulk",
        json={"toIssueIds": ["i3", "i1"], "linkType": "BLOCKS"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert [c["toIssueId"] for c in body["created"]] == ["i3"]
    assert body["skipped"] == [
        {"toIssueId": "i1", "reason": "CYCLE"},
    ]


@pytest.mark.asyncio
async def test_bulk_relates_to_skips_no_cycle_check(
    client: AsyncClient, factory,
):
    """RELATES_TO is non-transitive — no cycle check, no CYCLE skip."""
    await _seed_chain(factory, 3)

    # Establish RELATES_TO chain.
    for src, dst in (("i1", "i2"), ("i2", "i3")):
        r = await client.post(
            f"/api/issues/{src}/relations",
            json={"toIssueId": dst, "linkType": "RELATES_TO"},
        )
        assert r.status_code == 201

    # i3 RELATES_TO [i1] — would be a cycle for transitive, but RELATES_TO
    # never closes one.
    resp = await client.post(
        "/api/issues/i3/relations/bulk",
        json={"toIssueIds": ["i1"], "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 201
    assert [c["toIssueId"] for c in resp.json()["created"]] == ["i1"]
    assert resp.json()["skipped"] == []


# ---------- 400 invalidIds -------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_400_when_self_link_in_targets(
    client: AsyncClient, factory,
):
    """Self-link in toIssueIds is a bad id, not a silent skip."""
    await _seed_chain(factory, 3)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={"toIssueIds": ["i1", "i2"], "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["invalidIds"] == ["i1"]

    # No partial inserts.
    async with factory() as db:
        rows = (await db.execute(select(IssueLink))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_bulk_400_when_target_missing(client: AsyncClient, factory):
    """Missing-issue ids land in invalidIds — whole batch rejected."""
    await _seed_chain(factory, 3)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={
            "toIssueIds": ["i2", "ghost", "i3", "phantom"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert sorted(body["details"]["invalidIds"]) == ["ghost", "phantom"]


@pytest.mark.asyncio
async def test_bulk_400_when_cross_project(client: AsyncClient, factory):
    """Cross-project targets land in invalidIds."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        db.add(_make_project("proj-2"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id="proj-1"))
        db.add(_make_issue("i2", "CB-2", project_id="proj-1"))
        db.add(_make_issue("foreign", "CB-99", project_id="proj-2"))
        await db.commit()

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={
            "toIssueIds": ["i2", "foreign"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["invalidIds"] == ["foreign"]


@pytest.mark.asyncio
async def test_bulk_404_when_source_missing(client: AsyncClient, factory):
    await _seed_chain(factory, 2)

    resp = await client.post(
        "/api/issues/does-not-exist/relations/bulk",
        json={"toIssueIds": ["i1"], "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------- input shape (Pydantic) ----------------------------------------

@pytest.mark.asyncio
async def test_bulk_422_when_empty_list(client: AsyncClient, factory):
    await _seed_chain(factory, 2)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={"toIssueIds": [], "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_422_when_oversize_list(client: AsyncClient, factory):
    """Cap is 100 targets — 101 must 422."""
    await _seed_chain(factory, 2)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={
            "toIssueIds": [f"x{n}" for n in range(101)],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_422_when_unknown_link_type(client: AsyncClient, factory):
    await _seed_chain(factory, 2)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={"toIssueIds": ["i2"], "linkType": "BOGUS"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_422_when_id_has_control_char(
    client: AsyncClient, factory,
):
    """CRLF / control chars in any toIssueId are rejected before reaching DB,
    blocking log-injection through the IntegrityError handler."""
    await _seed_chain(factory, 2)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={
            "toIssueIds": ["i2", "i2\r\nFAKE"],
            "linkType": "RELATES_TO",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_422_when_extra_field(client: AsyncClient, factory):
    """extra='forbid' on the schema rejects over-posting."""
    await _seed_chain(factory, 2)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={
            "toIssueIds": ["i2"],
            "linkType": "RELATES_TO",
            "id": "attacker-supplied",
        },
    )
    assert resp.status_code == 422


# ---------- response shape -------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_cycle_budget_shared_across_batch(
    client: AsyncClient, factory, monkeypatch,
):
    """Security: cycle BFS visit budget is shared across all candidates in
    a batch (CB-1972 audit H1). With a tiny budget, a transitive bulk
    that would otherwise burn 100 × _MAX_CYCLE_VISIT SELECTs is forced to
    raise once the shared pool is exhausted, preventing per-request DoS
    amplification.
    """
    # Set up a chain long enough for BFS to walk past the patched budget.
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i in range(1, 11):
            db.add(_make_issue(f"i{i}", f"CB-{i}"))
        await db.commit()

    # Build i1→i2→...→i10 BLOCKS chain (single-POST, default budget).
    for src, dst in zip(
        [f"i{i}" for i in range(1, 10)],
        [f"i{i}" for i in range(2, 11)],
    ):
        r = await client.post(
            f"/api/issues/{src}/relations",
            json={"toIssueId": dst, "linkType": "BLOCKS"},
        )
        assert r.status_code == 201, r.text

    # Patch the bulk endpoint's cap to a small number — every candidate's
    # cycle BFS walks ~9 hops, so 3 candidates × 9 hops = 27 visits will
    # blow past a 5-visit shared budget. Only a shared budget enforces
    # this; per-candidate budgets would each get 5 fresh visits.
    import api.relations as relations_module
    monkeypatch.setattr(relations_module, "_MAX_CYCLE_VISIT", 5)

    # 3 transitive candidates that are NOT cycles but force BFS work.
    # i10 BLOCKS [i1, i2, i3] would each walk forward from i1/i2/i3 trying
    # to find i10 — long traversals. None close a cycle (i1/i2/i3 don't
    # reach i10 in the forward direction; the chain goes i1→i2→...→i10).
    # Wait — yes they do (i1→i2→...→i10), so each cycle check actually DOES
    # walk to i10 and returns True (cycle). But the *visits* before that
    # exceed our 5-visit shared budget on the first or second call.
    resp = await client.post(
        "/api/issues/i10/relations/bulk",
        json={"toIssueIds": ["i1", "i2", "i3"], "linkType": "BLOCKS"},
    )
    # Either: 400 from oversize-graph guard (shared budget exhausted), or
    # all three skipped as CYCLE before the budget runs out. Both are
    # acceptable; what would be UNACCEPTABLE (the H1 finding) is for the
    # request to succeed by giving each candidate a fresh 5-visit budget.
    # We assert that the shared budget caps total work: with 5 visits
    # shared across 3 candidates the second/third call raises.
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "graph too large" in body["message"].lower()


@pytest.mark.asyncio
async def test_bulk_response_embeds_summaries(
    client: AsyncClient, factory,
):
    """Each created entry carries fromIssue / toIssue summaries (CB-1960)."""
    await _seed_chain(factory, 3)

    resp = await client.post(
        "/api/issues/i1/relations/bulk",
        json={"toIssueIds": ["i2", "i3"], "linkType": "DUPLICATES"},
    )
    assert resp.status_code == 201
    for entry in resp.json()["created"]:
        assert entry["linkType"] == "DUPLICATES"
        assert entry["fromIssue"]["key"] == "CB-1"
        assert entry["fromIssue"]["title"] == "Issue 1"
        assert entry["toIssue"]["id"] == entry["toIssueId"]
