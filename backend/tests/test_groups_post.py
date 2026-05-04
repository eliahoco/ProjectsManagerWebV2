"""
CB-1984 — POST /api/projects/{project_id}/groups.

Covers the create-group contract:
  * 201 — happy path with no members (empty group)
  * 201 — happy path with members; 1-based positions in payload order
  * 201 — duplicate issueIds in payload are deduped by the schema
  * 404 — project does not exist
  * 404 — any issueIds entry does not exist (precedence over cross-project)
  * 400 — any issueIds entry belongs to a different project
        ; details.invalidIssueIds lists every offender
  * 422 — empty title (Pydantic min_length=1)
  * 422 — issueIds list larger than 500 (Pydantic max_length)
  * Response shape: IssueGroupResponse with memberCount + server-side
    timestamps populated.

Mirrors the test_relations_post.py fixture pattern: isolated on-disk SQLite,
fresh schema per test module, no production codeboard.db touch.
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


from api.groups import router as groups_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.grouping import IssueGroup, IssueGroupMember  # noqa: E402
from models.issue import Issue, Project  # noqa: E402


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="groups-post-test-")
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


async def _seed_project_with_issues(factory, project_id: str = "proj-1") -> None:
    """Seed `project_id` plus three issues (i1, i2, i3)."""
    async with factory() as db:
        db.add(_make_project(project_id))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id=project_id, title="Issue 1"))
        db.add(_make_issue(
            "i2", "CB-2", project_id=project_id,
            title="Issue 2", status_="IN_PROGRESS",
        ))
        db.add(_make_issue(
            "i3", "CB-3", project_id=project_id,
            title="Issue 3", status_="DONE",
        ))
        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_create_group_no_members(client: AsyncClient, factory):
    """An empty group is valid — title only."""
    await _seed_project_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-1/groups",
        json={"title": "Sprint 5 candidates"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["projectId"] == "proj-1"
    assert body["title"] == "Sprint 5 candidates"
    assert body["description"] is None
    assert body["memberCount"] == 0
    # Server-side timestamps populate on commit; refresh hydrates them.
    assert body["createdAt"]
    assert body["updatedAt"]

    # Group row is in the DB; no membership rows.
    async with factory() as db:
        groups = (await db.execute(select(IssueGroup))).scalars().all()
        members = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert len(groups) == 1
    assert groups[0].title == "Sprint 5 candidates"
    assert members == []


@pytest.mark.asyncio
async def test_create_group_with_members_assigns_positions(
    client: AsyncClient, factory,
):
    """Members are written 1..N in payload order with the position column set."""
    await _seed_project_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-1/groups",
        json={
            "title": "Group with members",
            "description": "Three issues bundled together.",
            "issueIds": ["i2", "i1", "i3"],  # caller order matters
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["memberCount"] == 3
    assert body["description"] == "Three issues bundled together."

    async with factory() as db:
        members = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.position)
        )).scalars().all()
    # Caller order preserved: i2 -> 1, i1 -> 2, i3 -> 3.
    assert [(m.position, m.issueId) for m in members] == [
        (1, "i2"),
        (2, "i1"),
        (3, "i3"),
    ]


@pytest.mark.asyncio
async def test_create_group_dedupes_payload_issue_ids(
    client: AsyncClient, factory,
):
    """Repeated issueIds in the body are deduped by the schema; the server
    stores N members for N unique ids, not N + duplicates."""
    await _seed_project_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-1/groups",
        json={
            "title": "Dedupe me",
            "issueIds": ["i1", "i2", "i1", "i2", "i3"],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["memberCount"] == 3

    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert sorted(r.issueId for r in rows) == ["i1", "i2", "i3"]


# ---------- 404 ------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_missing_returns_404(client: AsyncClient, factory):
    resp = await client.post(
        "/api/projects/does-not-exist/groups",
        json={"title": "Group X"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Project"


@pytest.mark.asyncio
async def test_member_issue_missing_returns_404(client: AsyncClient, factory):
    """If any issueIds entry doesn't exist, return 404 NOT_FOUND for it.
    Missing-issue 404 takes precedence over cross-project 400."""
    await _seed_project_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-1/groups",
        json={"title": "Group X", "issueIds": ["i1", "ghost"]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Issue"
    assert body["details"]["identifier"] == "ghost"


# ---------- 400 cross-project ---------------------------------------------

@pytest.mark.asyncio
async def test_cross_project_member_returns_400(
    client: AsyncClient, factory,
):
    """An issue belonging to a different project is rejected with 400 +
    details.invalidIssueIds listing every offender."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        db.add(_make_project("proj-2"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id="proj-1"))
        db.add(_make_issue("p2-a", "P2-1", project_id="proj-2"))
        db.add(_make_issue("p2-b", "P2-2", project_id="proj-2"))
        await db.commit()

    resp = await client.post(
        "/api/projects/proj-1/groups",
        json={
            "title": "Mixed project",
            "issueIds": ["i1", "p2-a", "p2-b"],
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["projectId"] == "proj-1"
    # Both cross-project ids surfaced — caller fixes whole list in one edit.
    assert sorted(body["details"]["invalidIssueIds"]) == ["p2-a", "p2-b"]

    # No partial inserts: nothing landed in either grouping table.
    async with factory() as db:
        groups = (await db.execute(select(IssueGroup))).scalars().all()
        members = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert groups == []
    assert members == []


# ---------- 422 schema enforcement ----------------------------------------

@pytest.mark.asyncio
async def test_empty_title_returns_422(client: AsyncClient, factory):
    """Pydantic min_length=1 on title — Fastapi short-circuits with 422."""
    await _seed_project_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-1/groups",
        json={"title": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oversized_member_list_returns_422(
    client: AsyncClient, factory,
):
    """Pydantic max_length=500 on issueIds — caller can't post a giant list."""
    await _seed_project_with_issues(factory)

    resp = await client.post(
        "/api/projects/proj-1/groups",
        json={
            "title": "Too many",
            "issueIds": [f"id-{n}" for n in range(501)],
        },
    )
    assert resp.status_code == 422
