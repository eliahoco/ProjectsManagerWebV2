"""
CB-1986 — GET /api/groups/{group_id} (detail).

Covers the detail-group contract:
  * 200 — happy path: group + members ordered by position + embedded
          issue summary (id/key/title/status) + computed aggregateStatus
          (statusBreakdown, completionPercent, dominantStatus).
  * 200 — empty group: members=[], aggregateStatus carries defaults
          (empty breakdown, 0.0%, dominantStatus=None).
  * 200 — members ordering: positions written out of insertion order are
          surfaced in (position ASC, id ASC) order regardless of insert
          sequence.
  * 200 — aggregate math: mixed statuses → DONE+CWQ count toward the
          completionPercent numerator; non-complete statuses do not.
  * 200 — embedded issue summary surfaces id/key/title/status only —
          downstream callers should not see internal fields like
          description.
  * 404 — group does not exist.

Mirrors test_groups_get.py / test_groups_post.py fixture pattern: isolated
on-disk SQLite, fresh schema per test module, no production codeboard.db
touch.
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
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from api.groups import router as groups_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.grouping import IssueGroup, IssueGroupMember  # noqa: E402
from models.issue import Issue, Project  # noqa: E402


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="groups-detail-test-")
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


def _make_group(
    group_id: str,
    project_id: str,
    title: str,
    description: str | None = None,
) -> IssueGroup:
    base = datetime(2026, 1, 1, 0, 0, 0)
    return IssueGroup(
        id=group_id,
        projectId=project_id,
        title=title,
        description=description,
        createdAt=base,
        updatedAt=base,
    )


def _make_member(
    group_id: str, issue_id: str, position: int,
    member_id: str | None = None,
) -> IssueGroupMember:
    return IssueGroupMember(
        id=member_id or str(uuid.uuid4()),
        groupId=group_id,
        issueId=issue_id,
        position=position,
    )


async def _seed_group_with_mixed_members(factory) -> None:
    """Seed proj-1 + 4 issues + group g1 with mixed statuses.

    Issues:
      i1: CB-1, title="Migration ticket",  status="DONE"
      i2: CB-2, title="Endpoint wiring",   status="COMPLETED_WAITING_QA"
      i3: CB-3, title="Frontend polish",   status="IN_PROGRESS"
      i4: CB-4, title="Edge case audit",   status="BACKLOG"

    Group g1 has all four as members, positions 1..4 in id order.
    Aggregate (CB-1958): DONE+CWQ = 2/4 = 50%, dominantStatus tied at 1
    each → lex-min = "BACKLOG".
    """
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()

        db.add(_make_issue(
            "i1", "CB-1", title="Migration ticket", status_="DONE",
        ))
        db.add(_make_issue(
            "i2", "CB-2", title="Endpoint wiring",
            status_="COMPLETED_WAITING_QA",
        ))
        db.add(_make_issue(
            "i3", "CB-3", title="Frontend polish", status_="IN_PROGRESS",
        ))
        db.add(_make_issue(
            "i4", "CB-4", title="Edge case audit", status_="BACKLOG",
        ))

        db.add(_make_group("g1", "proj-1", "Sprint 5", "Mixed bag."))
        await db.flush()

        db.add(_make_member("g1", "i1", 1, member_id="m-1"))
        db.add(_make_member("g1", "i2", 2, member_id="m-2"))
        db.add(_make_member("g1", "i3", 3, member_id="m-3"))
        db.add(_make_member("g1", "i4", 4, member_id="m-4"))
        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_get_group_detail_happy_path(client: AsyncClient, factory):
    """Group + ordered members + embedded issue summary + aggregateStatus."""
    await _seed_group_with_mixed_members(factory)

    resp = await client.get("/api/groups/g1")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Top-level group fields.
    assert body["id"] == "g1"
    assert body["projectId"] == "proj-1"
    assert body["title"] == "Sprint 5"
    assert body["description"] == "Mixed bag."
    assert body["createdAt"]
    assert body["updatedAt"]

    # Members ordered by position 1..4. Each carries the embedded issue
    # summary projection (id/key/title/status) — no `description` leak.
    assert [m["position"] for m in body["members"]] == [1, 2, 3, 4]
    assert [m["issueId"] for m in body["members"]] == ["i1", "i2", "i3", "i4"]
    for m in body["members"]:
        assert set(m.keys()) >= {
            "id", "groupId", "issueId", "position", "createdAt", "issue",
        }
        assert m["groupId"] == "g1"
        assert set(m["issue"].keys()) == {"id", "key", "title", "status"}

    # Embedded summary correctness on the first member.
    first = body["members"][0]
    assert first["issue"] == {
        "id": "i1",
        "key": "CB-1",
        "title": "Migration ticket",
        "status": "DONE",
    }

    # Aggregate (CB-1958): 1 DONE + 1 CWQ + 1 IN_PROGRESS + 1 BACKLOG.
    # DONE + CWQ = 2 / 4 = 50%; tie at count=1 → lex-min "BACKLOG".
    agg = body["aggregateStatus"]
    assert agg["statusBreakdown"] == {
        "DONE": 1,
        "COMPLETED_WAITING_QA": 1,
        "IN_PROGRESS": 1,
        "BACKLOG": 1,
    }
    assert agg["completionPercent"] == 50.0
    assert agg["dominantStatus"] == "BACKLOG"


@pytest.mark.asyncio
async def test_get_group_detail_empty_group(client: AsyncClient, factory):
    """Empty group → members=[], aggregateStatus defaults."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_group("g-empty", "proj-1", "Empty group"))
        await db.commit()

    resp = await client.get("/api/groups/g-empty")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["id"] == "g-empty"
    assert body["members"] == []
    assert body["aggregateStatus"] == {
        "statusBreakdown": {},
        "completionPercent": 0.0,
        "dominantStatus": None,
    }


@pytest.mark.asyncio
async def test_members_ordered_by_position_not_insert_order(
    client: AsyncClient, factory,
):
    """Members inserted with positions 3,1,2 are returned 1,2,3."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1"))
        db.add(_make_issue("i2", "CB-2"))
        db.add(_make_issue("i3", "CB-3"))
        db.add(_make_group("g1", "proj-1", "Order test"))
        await db.flush()
        # Deliberately insert out-of-order to prove the endpoint sorts on
        # `position` and not on insertion order or row id.
        db.add(_make_member("g1", "i1", 3, member_id="m-a"))
        db.add(_make_member("g1", "i2", 1, member_id="m-b"))
        db.add(_make_member("g1", "i3", 2, member_id="m-c"))
        await db.commit()

    resp = await client.get("/api/groups/g1")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert [m["position"] for m in body["members"]] == [1, 2, 3]
    assert [m["issueId"] for m in body["members"]] == ["i2", "i3", "i1"]


@pytest.mark.asyncio
async def test_same_position_breaks_tie_by_member_id(
    client: AsyncClient, factory,
):
    """Two members sharing a `position` are surfaced in (position, id) lex
    order — pins the relationship's order_by contract and the endpoint's
    explicit Python sort against the same key tuple.

    Same-position rows are reachable in production via the cross-session
    race documented on `next_member_position`: two concurrent appenders can
    both compute the same `position` and only the second is rejected by the
    UNIQUE(groupId, issueId) constraint, not by a position-uniqueness check.
    The relationship's `order_by="(position, id)"` then makes the read
    deterministic; this test asserts the contract end-to-end.
    """
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1"))
        db.add(_make_issue("i2", "CB-2"))
        db.add(_make_group("g1", "proj-1", "Tied positions"))
        await db.flush()
        # Both members at position=1; member ids "m-a" < "m-b" lex-sort, so
        # the response order is [m-a, m-b] regardless of insertion order.
        db.add(_make_member("g1", "i2", 1, member_id="m-b"))
        db.add(_make_member("g1", "i1", 1, member_id="m-a"))
        await db.commit()

    resp = await client.get("/api/groups/g1")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert [m["id"] for m in body["members"]] == ["m-a", "m-b"]
    assert [m["position"] for m in body["members"]] == [1, 1]
    # Both rows present — the tied position did not collapse them.
    assert {m["issueId"] for m in body["members"]} == {"i1", "i2"}


@pytest.mark.asyncio
async def test_aggregate_all_complete_returns_100_percent(
    client: AsyncClient, factory,
):
    """All members at DONE/CWQ → completionPercent=100, dominant=DONE (lex)."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", status_="DONE"))
        db.add(_make_issue("i2", "CB-2", status_="COMPLETED_WAITING_QA"))
        db.add(_make_group("g1", "proj-1", "Done bundle"))
        await db.flush()
        db.add(_make_member("g1", "i1", 1, member_id="m-1"))
        db.add(_make_member("g1", "i2", 2, member_id="m-2"))
        await db.commit()

    resp = await client.get("/api/groups/g1")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    agg = body["aggregateStatus"]
    assert agg["completionPercent"] == 100.0
    assert agg["statusBreakdown"] == {
        "DONE": 1,
        "COMPLETED_WAITING_QA": 1,
    }
    # Tie at 1/1 → lex-min: "COMPLETED_WAITING_QA" < "DONE".
    assert agg["dominantStatus"] == "COMPLETED_WAITING_QA"


@pytest.mark.asyncio
async def test_member_issue_summary_does_not_leak_internal_fields(
    client: AsyncClient, factory,
):
    """Embedded `issue` projection is the IssueSummary contract — exactly
    {id, key, title, status}. No description, projectId, type, or any
    other internal column leaks through."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        # Note: description not exposed in summary even when set.
        issue = _make_issue("i1", "CB-1", title="Visible title")
        issue.description = "secret-internal-only"
        db.add(issue)
        db.add(_make_group("g1", "proj-1", "Leak check"))
        await db.flush()
        db.add(_make_member("g1", "i1", 1, member_id="m-1"))
        await db.commit()

    resp = await client.get("/api/groups/g1")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    summary = body["members"][0]["issue"]
    assert set(summary.keys()) == {"id", "key", "title", "status"}
    # Defense-in-depth: confirm the description string is not present
    # anywhere in the response payload.
    assert "secret-internal-only" not in resp.text


# ---------- 404 ------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_missing_returns_404(client: AsyncClient, factory):
    """Stale URL → 404 with structured details (resource=IssueGroup)."""
    resp = await client.get("/api/groups/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "IssueGroup"
    assert body["details"]["identifier"] == "does-not-exist"
