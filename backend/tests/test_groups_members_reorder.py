"""
CB-2015 — PATCH /api/groups/{group_id}/members/reorder (bulk reorder).

Covers the bulk-reorder membership contract:
  * 200 — happy path: full reverse order rewrites positions 1..N
  * 200 — partial swap: only changed rows count as `reordered`
  * 200 — no-op: every position already matches -> reordered=0, no UPDATE
  * 200 — response.members is sorted in caller-supplied order (1..N)
  * 200 — response.members carries embedded IssueSummary projection
  * 404 — group_id does not exist
  * 400 — orderedIssueIds missing a current member (set inequality)
  * 400 — orderedIssueIds includes a non-member (set inequality)
  * 422 — orderedIssueIds duplicates within the request
  * 422 — empty orderedIssueIds (Pydantic min_length=1)
  * 422 — oversized orderedIssueIds (max_length=500)

Mirrors test_groups_members_post.py fixture pattern: isolated on-disk SQLite,
fresh schema per test module, no production codeboard.db touch.
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
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.grouping import IssueGroup, IssueGroupMember  # noqa: E402
from models.issue import Issue, Project  # noqa: E402


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="groups-members-reorder-test-")
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


def _make_group(group_id: str, project_id: str, title: str = "G") -> IssueGroup:
    return IssueGroup(
        id=group_id,
        projectId=project_id,
        title=title,
    )


def _make_member(
    group_id: str, issue_id: str, position: int,
) -> IssueGroupMember:
    return IssueGroupMember(
        id=str(uuid.uuid4()),
        groupId=group_id,
        issueId=issue_id,
        position=position,
    )


async def _seed_group_with_members(
    factory,
    project_id: str = "proj-1",
    group_id: str = "grp-1",
    member_issue_ids: list[str] | None = None,
) -> None:
    """Seed `project_id`, three issues (i1, i2, i3), and a group with members.

    `member_issue_ids` (defaulted to [i1, i2, i3]) seeds the group with those
    issues already as members at positions 1..N in list order.
    """
    members = member_issue_ids if member_issue_ids is not None else [
        "i1", "i2", "i3",
    ]
    async with factory() as db:
        db.add(_make_project(project_id))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id=project_id, title="One"))
        db.add(_make_issue("i2", "CB-2", project_id=project_id, title="Two"))
        db.add(_make_issue("i3", "CB-3", project_id=project_id, title="Three"))
        await db.flush()
        db.add(_make_group(group_id, project_id, title="Test Group"))
        await db.flush()
        for pos, iid in enumerate(members, start=1):
            db.add(_make_member(group_id, iid, pos))
        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_reorder_full_reverse(client: AsyncClient, factory):
    """Reverse the order: positions 1..N rewritten in caller order."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i3", "i2", "i1"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # All three rows changed position (1->3, 3->1; i2 stays at 2 -> NOT changed).
    # Reordered count therefore is 2, not 3.
    assert body["reordered"] == 2
    # Members in caller-supplied order, positions 1..N.
    assert [m["issueId"] for m in body["members"]] == ["i3", "i2", "i1"]
    assert [m["position"] for m in body["members"]] == [1, 2, 3]
    # Embedded issue summaries preserved.
    assert all(m["issue"] is not None for m in body["members"])
    assert body["members"][0]["issue"]["key"] == "CB-3"

    # DB state matches.
    async with factory() as db:
        rows = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.position)
        )).scalars().all()
    assert [(r.position, r.issueId) for r in rows] == [
        (1, "i3"), (2, "i2"), (3, "i1"),
    ]


@pytest.mark.asyncio
async def test_reorder_no_op(client: AsyncClient, factory):
    """Same order as current -> reordered=0, no UPDATE statements."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i1", "i2", "i3"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reordered"] == 0
    assert [m["issueId"] for m in body["members"]] == ["i1", "i2", "i3"]
    assert [m["position"] for m in body["members"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_reorder_single_swap(client: AsyncClient, factory):
    """Swap two adjacent members: only the two changed rows count as reordered."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i2", "i1", "i3"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # i1: 1->2, i2: 2->1, i3: 3->3 (unchanged). Two rows changed.
    assert body["reordered"] == 2
    assert [m["issueId"] for m in body["members"]] == ["i2", "i1", "i3"]
    assert [m["position"] for m in body["members"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_reorder_response_carries_issue_summary(
    client: AsyncClient, factory,
):
    """Response.members embeds the IssueSummary projection (id, key, title, status)."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i2", "i3", "i1"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    issue = body["members"][0]["issue"]
    assert issue["id"] == "i2"
    assert issue["key"] == "CB-2"
    assert issue["title"] == "Two"
    assert issue["status"] == "BACKLOG"


# ---------- error paths ----------------------------------------------------

@pytest.mark.asyncio
async def test_reorder_404_group_missing(client: AsyncClient, factory):
    """Unknown group_id surfaces NOT_FOUND with the typed code."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/does-not-exist/members/reorder",
        json={"orderedIssueIds": ["i1"]},
    )
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "IssueGroup"


@pytest.mark.asyncio
async def test_reorder_400_missing_current_member(client: AsyncClient, factory):
    """Payload omitting a current member -> 400 with `missing` populated."""
    await _seed_group_with_members(factory)

    # Drop i3 from the payload — it's a current member, so this is invalid.
    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i1", "i2"]},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    details = body["details"]
    assert details["groupId"] == "grp-1"
    assert details["missing"] == ["i3"]
    assert details["extra"] == []


@pytest.mark.asyncio
async def test_reorder_400_extra_non_member(client: AsyncClient, factory):
    """Payload including a non-member id -> 400 with `extra` populated."""
    await _seed_group_with_members(factory)
    # Add a fourth issue that isn't in the group.
    async with factory() as db:
        db.add(_make_issue("i4", "CB-4", project_id="proj-1", title="Four"))
        await db.commit()

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i1", "i2", "i3", "i4"]},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    details = body["details"]
    assert details["groupId"] == "grp-1"
    assert details["missing"] == []
    assert details["extra"] == ["i4"]


@pytest.mark.asyncio
async def test_reorder_400_both_missing_and_extra(
    client: AsyncClient, factory,
):
    """Set inequality with both directions -> both lists populated."""
    await _seed_group_with_members(factory)
    async with factory() as db:
        db.add(_make_issue("i4", "CB-4", project_id="proj-1", title="Four"))
        await db.commit()

    # Drop i3 (member), add i4 (non-member).
    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i1", "i2", "i4"]},
    )
    assert resp.status_code == 400, resp.text
    details = resp.json()["details"]
    assert details["missing"] == ["i3"]
    assert details["extra"] == ["i4"]


@pytest.mark.asyncio
async def test_reorder_422_duplicate_ids(client: AsyncClient, factory):
    """Repeated id in payload -> 422 from the schema validator."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i1", "i2", "i1"]},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_reorder_422_empty_payload(client: AsyncClient, factory):
    """Empty orderedIssueIds -> 422 (min_length=1)."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": []},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_reorder_422_oversized_payload(client: AsyncClient, factory):
    """501-element orderedIssueIds -> 422 (max_length=500)."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": [f"id-{i}" for i in range(501)]},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_reorder_persists_across_get(client: AsyncClient, factory):
    """End-to-end: reorder, then GET /groups/{id} returns members in new order."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i3", "i1", "i2"]},
    )
    assert resp.status_code == 200, resp.text

    detail = await client.get("/api/groups/grp-1")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert [m["issueId"] for m in body["members"]] == ["i3", "i1", "i2"]
    assert [m["position"] for m in body["members"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_reorder_extra_field_rejected(client: AsyncClient, factory):
    """Schema config `extra: forbid` rejects unknown fields with 422."""
    await _seed_group_with_members(factory)

    resp = await client.patch(
        "/api/groups/grp-1/members/reorder",
        json={"orderedIssueIds": ["i1", "i2", "i3"], "rogue": True},
    )
    assert resp.status_code == 422, resp.text
