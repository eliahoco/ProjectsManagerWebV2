"""
CB-1973 — GET /api/issues/{id}/relations.

Covers the list contract:
  * 200 — happy path: outbound + inbound rows with summaries (CB-1960)
  * 200 — empty when no relations exist
  * 200 — primary+companion split: BLOCKS row in outbound,
    IS_BLOCKED_BY companion in inbound for the source issue
  * 200 — ordering: createdAt DESC, id DESC tiebreak
  * 200 — pageSize cap clamps each direction independently
  * 422 — pageSize out of [1, 100]
  * 404 — source issue missing
  * Both outbound and inbound items embed fromIssue/toIssue summaries

Uses the same isolated on-disk SQLite pattern as test_relations_post.py
so tests never touch production codeboard.db.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
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
    tmp_dir = tempfile.mkdtemp(prefix="relations-get-test-")
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
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        for i in range(1, n + 1):
            db.add(_make_issue(f"i{i}", f"CB-{i}", title=f"Issue {i}"))
        await db.commit()


def _make_link(
    from_id: str,
    to_id: str,
    link_type: str,
    *,
    created_at: datetime | None = None,
    link_id: str | None = None,
) -> IssueLink:
    return IssueLink(
        id=link_id or str(uuid.uuid4()),
        fromIssueId=from_id,
        toIssueId=to_id,
        linkType=link_type,
        createdAt=created_at or datetime.utcnow(),
    )


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_get_returns_empty_for_issue_with_no_relations(
    client: AsyncClient, factory,
):
    await _seed_chain(factory, 1)

    resp = await client.get("/api/issues/i1/relations")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"outbound": [], "inbound": []}


@pytest.mark.asyncio
async def test_get_splits_blocks_into_outbound_and_companion_inbound(
    client: AsyncClient, factory,
):
    """A → B BLOCKS writes (A,B,BLOCKS) primary + (B,A,IS_BLOCKED_BY)
    companion. From A's perspective: outbound has BLOCKS, inbound has the
    IS_BLOCKED_BY companion row. Both embed summaries (CB-1960)."""
    await _seed_chain(factory, 2)

    # Use the POST endpoint to write the realistic primary+companion pair.
    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "BLOCKS"},
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get("/api/issues/i1/relations")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["outbound"]) == 1
    out = body["outbound"][0]
    assert out["fromIssueId"] == "i1"
    assert out["toIssueId"] == "i2"
    assert out["linkType"] == "BLOCKS"
    assert out["fromIssue"]["id"] == "i1"
    assert out["toIssue"]["id"] == "i2"

    assert len(body["inbound"]) == 1
    inn = body["inbound"][0]
    assert inn["fromIssueId"] == "i2"
    assert inn["toIssueId"] == "i1"
    assert inn["linkType"] == "IS_BLOCKED_BY"
    assert inn["fromIssue"]["id"] == "i2"
    assert inn["toIssue"]["id"] == "i1"


@pytest.mark.asyncio
async def test_get_relates_to_appears_in_both_directions(
    client: AsyncClient, factory,
):
    """RELATES_TO is symmetric: companion is (to, from, RELATES_TO).
    For A's view, outbound is the (A→B) row, inbound is the (B→A) row;
    both linkType = RELATES_TO."""
    await _seed_chain(factory, 2)

    resp = await client.post(
        "/api/issues/i1/relations",
        json={"toIssueId": "i2", "linkType": "RELATES_TO"},
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get("/api/issues/i1/relations")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["outbound"]) == 1
    assert len(body["inbound"]) == 1
    assert body["outbound"][0]["linkType"] == "RELATES_TO"
    assert body["inbound"][0]["linkType"] == "RELATES_TO"
    assert body["outbound"][0]["fromIssueId"] == "i1"
    assert body["outbound"][0]["toIssueId"] == "i2"
    assert body["inbound"][0]["fromIssueId"] == "i2"
    assert body["inbound"][0]["toIssueId"] == "i1"


@pytest.mark.asyncio
async def test_get_orders_newest_first_with_id_tiebreak(
    client: AsyncClient, factory,
):
    """Order is createdAt DESC, id DESC. Equal-timestamp rows tiebreak
    by id descending — deterministic across reads."""
    await _seed_chain(factory, 4)

    base = datetime(2026, 5, 1, 12, 0, 0)
    async with factory() as db:
        # Three outbound rows from i1 with strictly increasing timestamps.
        db.add(_make_link(
            "i1", "i2", "RELATES_TO",
            created_at=base, link_id="aaa-old",
        ))
        db.add(_make_link(
            "i1", "i3", "RELATES_TO",
            created_at=base + timedelta(seconds=10),
            link_id="bbb-mid",
        ))
        db.add(_make_link(
            "i1", "i4", "RELATES_TO",
            created_at=base + timedelta(seconds=20),
            link_id="ccc-new",
        ))
        # Two equal-timestamp rows to exercise the id tiebreak.
        db.add(_make_link(
            "i1", "i2", "BLOCKS",
            created_at=base + timedelta(seconds=20),
            link_id="zzz-tie",
        ))
        await db.commit()

    resp = await client.get("/api/issues/i1/relations")
    assert resp.status_code == 200, resp.text
    out = resp.json()["outbound"]
    # zzz-tie and ccc-new share createdAt; zzz > ccc lexicographically so
    # zzz comes first under id DESC. Then ccc, then bbb, then aaa.
    assert [r["id"] for r in out] == [
        "zzz-tie", "ccc-new", "bbb-mid", "aaa-old",
    ]


@pytest.mark.asyncio
async def test_get_pagesize_caps_each_direction_independently(
    client: AsyncClient, factory,
):
    """pageSize=2 returns at most 2 outbound + 2 inbound rows."""
    await _seed_chain(factory, 6)

    base = datetime(2026, 5, 1, 12, 0, 0)
    async with factory() as db:
        # 4 outbound from i1.
        for idx, target in enumerate(["i2", "i3", "i4", "i5"]):
            db.add(_make_link(
                "i1", target, "RELATES_TO",
                created_at=base + timedelta(seconds=idx),
                link_id=f"out-{idx}",
            ))
        # 4 inbound to i1.
        for idx, source in enumerate(["i2", "i3", "i4", "i5"]):
            db.add(_make_link(
                source, "i1", "BLOCKS",
                created_at=base + timedelta(seconds=idx),
                link_id=f"in-{idx}",
            ))
        await db.commit()

    resp = await client.get("/api/issues/i1/relations?pageSize=2")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["outbound"]) == 2
    assert len(body["inbound"]) == 2
    # Newest-first per direction.
    assert [r["id"] for r in body["outbound"]] == ["out-3", "out-2"]
    assert [r["id"] for r in body["inbound"]] == ["in-3", "in-2"]


# ---------- validation -----------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("page_size", [0, -1, 101, 1000])
async def test_get_pagesize_out_of_range_rejected(
    client: AsyncClient, factory, page_size: int,
):
    await _seed_chain(factory, 1)
    resp = await client.get(f"/api/issues/i1/relations?pageSize={page_size}")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_pagesize_default_is_100(
    client: AsyncClient, factory,
):
    """No pageSize param → default 100 per direction. Insert 100 outbound
    rows and confirm all are returned."""
    # Need 101 issues so we can write 100 distinct outbound links from i1.
    await _seed_chain(factory, 101)

    base = datetime(2026, 5, 1, 12, 0, 0)
    async with factory() as db:
        for idx in range(2, 102):  # i2..i101
            db.add(_make_link(
                "i1", f"i{idx}", "RELATES_TO",
                created_at=base + timedelta(seconds=idx),
                link_id=f"link-{idx:04d}",
            ))
        await db.commit()

    resp = await client.get("/api/issues/i1/relations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["outbound"]) == 100
    assert body["inbound"] == []


@pytest.mark.asyncio
async def test_get_unknown_issue_returns_404(
    client: AsyncClient, factory,
):
    await _seed_chain(factory, 1)
    resp = await client.get("/api/issues/does-not-exist/relations")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Issue"
    assert body["details"]["identifier"] == "does-not-exist"


@pytest.mark.asyncio
async def test_get_isolates_relations_across_projects(
    client: AsyncClient, factory,
):
    """A relation that lives in proj-2 must not surface in a proj-1
    issue's view (and vice versa). Locks the contract so that future
    refactors of the WHERE clause don't accidentally widen the scope.

    Note: cross-project relations can't be created via the POST endpoint
    (CB-1971 rejects them), but stale rows from older code paths or
    direct-write tooling could exist. This test seeds them directly to
    prove the GET filter is purely on `fromIssueId`/`toIssueId` equality
    and won't expose cross-project edges if they ever appear.
    """
    async with factory() as db:
        db.add(_make_project("proj-1"))
        db.add(_make_project("proj-2"))
        await db.flush()
        db.add(_make_issue("p1-i1", "P1-1", project_id="proj-1"))
        db.add(_make_issue("p1-i2", "P1-2", project_id="proj-1"))
        db.add(_make_issue("p2-i1", "P2-1", project_id="proj-2"))
        db.add(_make_issue("p2-i2", "P2-2", project_id="proj-2"))
        await db.flush()
        # Same-project relations on both sides.
        db.add(_make_link("p1-i1", "p1-i2", "RELATES_TO", link_id="p1-link"))
        db.add(_make_link("p2-i1", "p2-i2", "RELATES_TO", link_id="p2-link"))
        await db.commit()

    resp = await client.get("/api/issues/p1-i1/relations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["id"] for r in body["outbound"]] == ["p1-link"]
    assert body["inbound"] == []

    resp = await client.get("/api/issues/p2-i1/relations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["id"] for r in body["outbound"]] == ["p2-link"]
    assert body["inbound"] == []


@pytest.mark.asyncio
async def test_get_only_returns_relations_for_requested_issue(
    client: AsyncClient, factory,
):
    """Relations between unrelated issues must not leak into i1's view."""
    await _seed_chain(factory, 4)

    base = datetime(2026, 5, 1, 12, 0, 0)
    async with factory() as db:
        # i2 ↔ i3, i3 ↔ i4 — none touch i1.
        db.add(_make_link("i2", "i3", "RELATES_TO", created_at=base))
        db.add(_make_link("i3", "i2", "RELATES_TO", created_at=base))
        db.add(_make_link("i3", "i4", "BLOCKS", created_at=base))
        db.add(_make_link("i4", "i3", "IS_BLOCKED_BY", created_at=base))
        # One link involving i1 — must be the only thing returned.
        db.add(_make_link(
            "i1", "i2", "RELATES_TO",
            created_at=base, link_id="i1-only",
        ))
        await db.commit()

    resp = await client.get("/api/issues/i1/relations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["outbound"]) == 1
    assert body["outbound"][0]["id"] == "i1-only"
    assert body["inbound"] == []
