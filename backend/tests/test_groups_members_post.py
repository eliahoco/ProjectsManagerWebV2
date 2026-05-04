"""
CB-1989 — POST /api/groups/{group_id}/members (bulk add).

Covers the bulk-add membership contract:
  * 201 — happy path: all ids new, returned in `added` in deduped request order
  * 201 — partial: already-members surface in `skipped`, new ids in `added`
  * 201 — full skip: every id is already a member -> empty added, full skipped
  * 201 — payload duplicates within the same request are deduped by the schema
  * 201 — positions of newly inserted rows continue from MAX(existing)+1
  * 404 — group_id does not exist
  * 404 — any issueIds entry does not exist (precedence over cross-project)
  * 400 — any issueIds entry belongs to a different project; details.invalidIssueIds
  * 422 — empty issueIds list (Pydantic min_length=1)
  * 422 — oversized list (max_length=500)

Mirrors test_groups_post.py fixture pattern: isolated on-disk SQLite, fresh
schema per test module, no production codeboard.db touch.
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
    tmp_dir = tempfile.mkdtemp(prefix="groups-members-post-test-")
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


async def _seed_group_with_issues(
    factory,
    project_id: str = "proj-1",
    group_id: str = "grp-1",
    initial_member_issue_ids: list[str] | None = None,
) -> None:
    """Seed `project_id`, three issues (i1, i2, i3), and a group.

    `initial_member_issue_ids` (optional) seeds the group with those issues
    already as members (positions assigned 1..N) so the test can exercise
    the skip-existing path.
    """
    async with factory() as db:
        db.add(_make_project(project_id))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id=project_id, title="Issue 1"))
        db.add(_make_issue("i2", "CB-2", project_id=project_id, title="Issue 2"))
        db.add(_make_issue("i3", "CB-3", project_id=project_id, title="Issue 3"))
        await db.flush()
        db.add(_make_group(group_id, project_id, title="Test Group"))
        await db.flush()
        if initial_member_issue_ids:
            for pos, iid in enumerate(initial_member_issue_ids, start=1):
                db.add(_make_member(group_id, iid, pos))
        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_add_all_new_members(client: AsyncClient, factory):
    """All ids new -> all in `added`, none in `skipped`."""
    await _seed_group_with_issues(factory)

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i2", "i1", "i3"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Caller order preserved.
    assert body["added"] == ["i2", "i1", "i3"]
    assert body["skipped"] == []

    async with factory() as db:
        rows = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.position)
        )).scalars().all()
    # Empty group -> base position is 1; 1..3 in caller order.
    assert [(r.position, r.issueId) for r in rows] == [
        (1, "i2"), (2, "i1"), (3, "i3"),
    ]


@pytest.mark.asyncio
async def test_bulk_add_partial_skip_existing(client: AsyncClient, factory):
    """Already-members surface in `skipped`; new ids in `added`. Order preserved."""
    await _seed_group_with_issues(
        factory, initial_member_issue_ids=["i1", "i2"],
    )

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "i3", "i2"]},  # i1, i2 already members
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["added"] == ["i3"]
    assert body["skipped"] == ["i1", "i2"]

    async with factory() as db:
        rows = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.position)
        )).scalars().all()
    # Existing i1=1, i2=2 untouched. i3 gets the next slot (3 = MAX(2)+1).
    assert [(r.position, r.issueId) for r in rows] == [
        (1, "i1"), (2, "i2"), (3, "i3"),
    ]


@pytest.mark.asyncio
async def test_bulk_add_all_already_members(client: AsyncClient, factory):
    """Every id is already a member -> empty added, full skipped, no DB writes."""
    await _seed_group_with_issues(
        factory, initial_member_issue_ids=["i1", "i2"],
    )

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "i2"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["added"] == []
    assert body["skipped"] == ["i1", "i2"]

    async with factory() as db:
        rows = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.position)
        )).scalars().all()
    # Membership unchanged: still exactly the two original rows.
    assert [(r.position, r.issueId) for r in rows] == [
        (1, "i1"), (2, "i2"),
    ]


@pytest.mark.asyncio
async def test_bulk_add_dedupes_request_payload(client: AsyncClient, factory):
    """Repeated ids in the body are deduped by the schema before being processed."""
    await _seed_group_with_issues(factory)

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "i2", "i1", "i3", "i2"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Dedupe preserves first-seen order.
    assert body["added"] == ["i1", "i2", "i3"]
    assert body["skipped"] == []

    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert sorted(r.issueId for r in rows) == ["i1", "i2", "i3"]


@pytest.mark.asyncio
async def test_bulk_add_continues_position_from_max(
    client: AsyncClient, factory,
):
    """Position assignment for new members continues from MAX(existing) + 1."""
    # Group already has i1 at position 5 (gap simulating a future delete-and-reorder
    # scenario). The bulk-add should keep going from 6, not from 1.
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id="proj-1"))
        db.add(_make_issue("i2", "CB-2", project_id="proj-1"))
        db.add(_make_issue("i3", "CB-3", project_id="proj-1"))
        await db.flush()
        db.add(_make_group("grp-1", "proj-1"))
        await db.flush()
        db.add(_make_member("grp-1", "i1", 5))
        await db.commit()

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i2", "i3"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["added"] == ["i2", "i3"]
    assert body["skipped"] == []

    async with factory() as db:
        rows = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.position)
        )).scalars().all()
    assert [(r.position, r.issueId) for r in rows] == [
        (5, "i1"), (6, "i2"), (7, "i3"),
    ]


# ---------- 404 ------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_missing_returns_404(client: AsyncClient, factory):
    resp = await client.post(
        "/api/groups/does-not-exist/members",
        json={"issueIds": ["i1"]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "IssueGroup"


@pytest.mark.asyncio
async def test_issue_missing_returns_404(client: AsyncClient, factory):
    """If any issueIds entry doesn't exist, 404 NOT_FOUND for the first missing.
    Missing-issue 404 takes precedence over cross-project 400 (the caller's
    list is wrong before we can even check projects)."""
    await _seed_group_with_issues(factory)

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "ghost"]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Issue"
    assert body["details"]["identifier"] == "ghost"

    # No partial inserts (i1 didn't sneak in).
    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert rows == []


# ---------- 400 cross-project ---------------------------------------------

@pytest.mark.asyncio
async def test_cross_project_member_returns_400(
    client: AsyncClient, factory,
):
    """An issue belonging to a different project than the group is rejected
    with 400 + details.invalidIssueIds listing every offender."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        db.add(_make_project("proj-2"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id="proj-1"))
        db.add(_make_issue("p2-a", "P2-1", project_id="proj-2"))
        db.add(_make_issue("p2-b", "P2-2", project_id="proj-2"))
        await db.flush()
        db.add(_make_group("grp-1", "proj-1", title="Group P1"))
        await db.commit()

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "p2-a", "p2-b"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["groupId"] == "grp-1"
    assert body["details"]["projectId"] == "proj-1"
    assert sorted(body["details"]["invalidIssueIds"]) == ["p2-a", "p2-b"]

    # No partial inserts.
    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert rows == []


# ---------- 422 schema enforcement ----------------------------------------

@pytest.mark.asyncio
async def test_empty_issue_ids_returns_422(client: AsyncClient, factory):
    """Pydantic min_length=1 — a no-op bulk-add isn't a valid request."""
    await _seed_group_with_issues(factory)

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oversized_issue_ids_returns_422(client: AsyncClient, factory):
    """Pydantic max_length=500 — caller can't ship a giant list."""
    await _seed_group_with_issues(factory)

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": [f"id-{n}" for n in range(501)]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_extra_fields_rejected_422(client: AsyncClient, factory):
    """`extra='forbid'` on the schema blocks over-posting."""
    await _seed_group_with_issues(factory)

    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1"], "rogueField": "evil"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oversized_id_returns_422(client: AsyncClient, factory):
    """Per-id length cap (64 chars) enforced by the field validator."""
    await _seed_group_with_issues(factory)

    big_id = "x" * 65
    resp = await client.post(
        "/api/groups/grp-1/members",
        json={"issueIds": [big_id]},
    )
    assert resp.status_code == 422
