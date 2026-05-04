"""
CB-1985 — GET /api/projects/{project_id}/groups (paginated).

Covers the list-groups contract:
  * 200 — empty project returns {items: [], total: 0, page: 1, pageSize: 50,
          totalPages: 0}.
  * 200 — happy path: each item carries memberCount; members NOT embedded
          (IssueGroupResponse, not IssueGroupDetailResponse).
  * 200 — empty groups appear with memberCount == 0 (outer join keeps them).
  * 200 — ordering is createdAt DESC, id DESC tie-break (deterministic).
  * 200 — pagination metadata: total / page / pageSize / totalPages math
          (page 1 of 3, page 3 returns the tail, page 4 returns []).
  * 200 — search matches title OR description, case-insensitive substring.
  * 200 — search with no matches returns empty items + total=0.
  * 200 — pageSize defaults to 50; alias accepts ?pageSize=N.
  * 404 — project does not exist.
  * 422 — pageSize > 100 (Pydantic le=100).
  * 422 — page < 1 (Pydantic ge=1).
  * 422 — search > 500 chars (Pydantic max_length).
  * Cross-project isolation: groups in other projects are not returned.

Mirrors test_groups_post.py fixture pattern: isolated on-disk SQLite, fresh
schema per test module, no production codeboard.db touch.
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


from api.groups import router as groups_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.grouping import IssueGroup, IssueGroupMember  # noqa: E402
from models.issue import Issue, Project  # noqa: E402


# ---------- fixtures -------------------------------------------------------

@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="groups-get-test-")
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
) -> Issue:
    return Issue(
        id=issue_id,
        projectId=project_id,
        key=key,
        sequence=int(key.split("-")[-1]) if "-" in key else 1,
        title=f"Issue {key}",
        type="TASK",
        status="BACKLOG",
        priority="MEDIUM",
        updatedAt=datetime.utcnow(),
    )


def _make_group(
    group_id: str,
    project_id: str,
    title: str,
    description: str | None,
    created_at: datetime,
) -> IssueGroup:
    """IssueGroup row with explicit timestamps so ordering is deterministic.

    The model uses server_default=func.now() for createdAt — providing it
    explicitly bypasses that default and gives the test full control over
    ordering. updatedAt mirrors createdAt for symmetry.
    """
    return IssueGroup(
        id=group_id,
        projectId=project_id,
        title=title,
        description=description,
        createdAt=created_at,
        updatedAt=created_at,
    )


def _make_member(group_id: str, issue_id: str, position: int) -> IssueGroupMember:
    return IssueGroupMember(
        id=str(uuid.uuid4()),
        groupId=group_id,
        issueId=issue_id,
        position=position,
    )


async def _seed_groups(factory, project_id: str = "proj-1") -> None:
    """Seed `project_id` + three issues + three groups with varied membership.

    Groups (newest → oldest by createdAt):
      g3: 'Frontend polish'        — 0 members (empty group; tests outer join)
      g2: 'API contracts'          — 2 members (i1, i2)
      g1: 'Database migrations'    — 3 members (i1, i2, i3)
    """
    base = datetime(2026, 1, 1, 0, 0, 0)
    async with factory() as db:
        db.add(_make_project(project_id))
        await db.flush()

        db.add(_make_issue("i1", "CB-1", project_id=project_id))
        db.add(_make_issue("i2", "CB-2", project_id=project_id))
        db.add(_make_issue("i3", "CB-3", project_id=project_id))

        db.add(_make_group(
            "g1", project_id, "Database migrations",
            "All Postgres migration tickets.", base,
        ))
        db.add(_make_group(
            "g2", project_id, "API contracts",
            "OpenAPI work bundle.", base + timedelta(hours=1),
        ))
        db.add(_make_group(
            "g3", project_id, "Frontend polish",
            None, base + timedelta(hours=2),
        ))

        # g1: 3 members, g2: 2 members, g3: 0 members.
        db.add(_make_member("g1", "i1", 1))
        db.add(_make_member("g1", "i2", 2))
        db.add(_make_member("g1", "i3", 3))
        db.add(_make_member("g2", "i1", 1))
        db.add(_make_member("g2", "i2", 2))

        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_empty_project_returns_empty_page(client: AsyncClient, factory):
    """Project exists but has no groups — empty items, zeros for pagination."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.commit()

    resp = await client.get("/api/projects/proj-1/groups")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "items": [],
        "total": 0,
        "page": 1,
        "pageSize": 50,
        "totalPages": 0,
    }


@pytest.mark.asyncio
async def test_list_groups_happy_path(client: AsyncClient, factory):
    """Each item carries memberCount; members NOT embedded; ordering newest-first."""
    await _seed_groups(factory)

    resp = await client.get("/api/projects/proj-1/groups")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 3
    assert body["page"] == 1
    assert body["pageSize"] == 50
    assert body["totalPages"] == 1
    assert len(body["items"]) == 3

    # Ordering: createdAt DESC → g3, g2, g1.
    assert [it["id"] for it in body["items"]] == ["g3", "g2", "g1"]
    # memberCount populated for every item, including the empty group.
    assert [it["memberCount"] for it in body["items"]] == [0, 2, 3]

    # Members are NOT embedded — the response is IssueGroupResponse, not the
    # detail variant. Field set should match the summary schema exactly.
    expected_keys = {
        "id", "projectId", "title", "description",
        "memberCount", "createdAt", "updatedAt",
    }
    for item in body["items"]:
        assert set(item.keys()) == expected_keys
        assert item["projectId"] == "proj-1"


@pytest.mark.asyncio
async def test_pagination_math(client: AsyncClient, factory):
    """page 1/3 with pageSize=1 returns g3, page 3 returns g1, page 4 empty."""
    await _seed_groups(factory)

    # Page 1 of 3.
    resp = await client.get("/api/projects/proj-1/groups?page=1&pageSize=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["pageSize"] == 1
    assert body["totalPages"] == 3
    assert [it["id"] for it in body["items"]] == ["g3"]

    # Page 3 of 3 — tail (oldest).
    resp = await client.get("/api/projects/proj-1/groups?page=3&pageSize=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [it["id"] for it in body["items"]] == ["g1"]

    # Page 4 — beyond the last page; empty items but the metadata still
    # carries total/totalPages so the client can render correctly.
    resp = await client.get("/api/projects/proj-1/groups?page=4&pageSize=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 3
    assert body["totalPages"] == 3


@pytest.mark.asyncio
async def test_search_matches_title(client: AsyncClient, factory):
    """Case-insensitive substring on title."""
    await _seed_groups(factory)

    resp = await client.get("/api/projects/proj-1/groups?search=API")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert [it["id"] for it in body["items"]] == ["g2"]
    assert body["items"][0]["title"] == "API contracts"


@pytest.mark.asyncio
async def test_search_matches_description(client: AsyncClient, factory):
    """Substring also matches description; case-insensitive ASCII."""
    await _seed_groups(factory)

    resp = await client.get("/api/projects/proj-1/groups?search=postgres")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert [it["id"] for it in body["items"]] == ["g1"]


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(client: AsyncClient, factory):
    """A non-matching search returns total=0 + items=[] (not 404)."""
    await _seed_groups(factory)

    resp = await client.get("/api/projects/proj-1/groups?search=does-not-exist")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["totalPages"] == 0


@pytest.mark.asyncio
async def test_cross_project_isolation(client: AsyncClient, factory):
    """Groups in another project must not appear in this project's list."""
    await _seed_groups(factory, project_id="proj-1")
    async with factory() as db:
        db.add(_make_project("proj-2"))
        await db.flush()
        db.add(_make_group(
            "p2-g1", "proj-2", "Other project group", None,
            datetime(2026, 2, 1, 0, 0, 0),
        ))
        await db.commit()

    resp = await client.get("/api/projects/proj-1/groups")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # proj-1 still sees only its own three groups.
    assert body["total"] == 3
    assert all(it["projectId"] == "proj-1" for it in body["items"])
    assert "p2-g1" not in {it["id"] for it in body["items"]}


# ---------- 404 ------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_missing_returns_404(client: AsyncClient, factory):
    """Stale URL → 404 (not an empty list, which would hide the typo)."""
    resp = await client.get("/api/projects/does-not-exist/groups")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "Project"
    assert body["details"]["identifier"] == "does-not-exist"


# ---------- 422 schema enforcement ----------------------------------------

@pytest.mark.asyncio
async def test_pagesize_over_cap_returns_422(client: AsyncClient, factory):
    """pageSize > 100 — FastAPI/Pydantic short-circuits with 422."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.commit()

    resp = await client.get("/api/projects/proj-1/groups?pageSize=101")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_page_under_one_returns_422(client: AsyncClient, factory):
    """page < 1 — Pydantic ge=1."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.commit()

    resp = await client.get("/api/projects/proj-1/groups?page=0")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oversized_search_returns_422(client: AsyncClient, factory):
    """search > 500 chars — Pydantic max_length keeps the LIKE pattern bounded."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.commit()

    resp = await client.get(
        "/api/projects/proj-1/groups",
        params={"search": "x" * 501},
    )
    assert resp.status_code == 422
