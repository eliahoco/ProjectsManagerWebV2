"""
CB-1990 — DELETE /api/groups/{group_id}/members (bulk remove).

Covers the bulk-remove membership contract:
  * 200 — happy path: every id is a current member, all rows removed
  * 200 — partial: some ids are members (removed), some are not (notFound)
  * 200 — none are members: removed=0, notFound = full request order
  * 200 — request dedupes duplicate ids (response arrays carry each once)
  * 200 — non-existent issue ids and other-group members both bucketed in notFound
  * 200 — issues themselves survive; only the GroupMember row is deleted
  * 200 — other groups' membership is untouched (DELETE scoped by groupId)
  * 404 — group_id does not exist
  * 422 — empty issueIds list (Pydantic min_length=1)
  * 422 — oversized issueIds list (max_length=500)
  * 422 — extra fields (extra='forbid')
  * 422 — id longer than 64 chars

Mirrors test_groups_members_post.py fixture pattern: isolated on-disk
SQLite, fresh schema per test, no production codeboard.db touch. DELETE
with a JSON body is sent via ``client.request("DELETE", ..., json=...)``
because httpx's ``client.delete`` does not accept ``json=`` directly.
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
    tmp_dir = tempfile.mkdtemp(prefix="groups-members-delete-test-")
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
    """Seed `project_id`, three issues (i1, i2, i3), the group, and
    optionally seed it with `member_issue_ids` (positions 1..N)."""
    async with factory() as db:
        db.add(_make_project(project_id))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", project_id=project_id))
        db.add(_make_issue("i2", "CB-2", project_id=project_id))
        db.add(_make_issue("i3", "CB-3", project_id=project_id))
        await db.flush()
        db.add(_make_group(group_id, project_id, title="Test Group"))
        await db.flush()
        if member_issue_ids:
            for pos, iid in enumerate(member_issue_ids, start=1):
                db.add(_make_member(group_id, iid, pos))
        await db.commit()


# ---------- happy path -----------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_remove_all_members(client: AsyncClient, factory):
    """All ids are members -> all removed, notFound empty, count = len(ids)."""
    await _seed_group_with_members(
        factory, member_issue_ids=["i1", "i2", "i3"],
    )

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": ["i2", "i1", "i3"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["removed"] == 3
    assert body["notFound"] == []

    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_bulk_remove_partial(client: AsyncClient, factory):
    """Mix of members + non-members. Members removed; non-members in notFound."""
    await _seed_group_with_members(
        factory, member_issue_ids=["i1", "i2"],
    )

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        # i3 is a real issue but not a member; ghost doesn't exist.
        json={"issueIds": ["i1", "i3", "i2", "ghost"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["removed"] == 2
    # notFound preserves request order (i3 before ghost).
    assert body["notFound"] == ["i3", "ghost"]

    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_bulk_remove_no_members_match(client: AsyncClient, factory):
    """No id is a member -> removed=0, notFound = full request order."""
    await _seed_group_with_members(factory, member_issue_ids=["i1"])

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": ["i2", "i3", "ghost"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["removed"] == 0
    assert body["notFound"] == ["i2", "i3", "ghost"]

    # Existing membership untouched.
    async with factory() as db:
        rows = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert sorted(r.issueId for r in rows) == ["i1"]


@pytest.mark.asyncio
async def test_bulk_remove_dedupes_request_payload(
    client: AsyncClient, factory,
):
    """Repeated ids in the body are deduped by the schema before processing.
    A doubled-up member id can only be classified once (the row is gone
    after the first match)."""
    await _seed_group_with_members(
        factory, member_issue_ids=["i1", "i2"],
    )

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "i2", "i1", "ghost", "i2"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # i1 + i2 deduped -> 2 removed, ghost in notFound.
    assert body["removed"] == 2
    assert body["notFound"] == ["ghost"]


@pytest.mark.asyncio
async def test_bulk_remove_does_not_delete_issues(
    client: AsyncClient, factory,
):
    """Issues themselves survive — only the GroupMember row goes."""
    await _seed_group_with_members(
        factory, member_issue_ids=["i1", "i2"],
    )

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "i2"]},
    )
    assert resp.status_code == 200, resp.text

    async with factory() as db:
        # Issue rows still present (RESTRICT-by-omission on FK; this
        # endpoint never touches Issue rows directly).
        issues = (await db.execute(select(Issue))).scalars().all()
        assert sorted(i.id for i in issues) == ["i1", "i2", "i3"]
        # Membership rows for grp-1 are gone.
        members = (await db.execute(select(IssueGroupMember))).scalars().all()
        assert members == []


@pytest.mark.asyncio
async def test_bulk_remove_other_groups_isolated(
    client: AsyncClient, factory,
):
    """DELETE scoped by groupId — membership in OTHER groups is untouched
    even when the same issue id appears in both."""
    await _seed_group_with_members(
        factory, group_id="grp-1", member_issue_ids=["i1", "i2"],
    )
    # Add second group with overlapping membership (i1 in both).
    async with factory() as db:
        db.add(_make_group("grp-2", "proj-1", title="Second Group"))
        await db.flush()
        db.add(_make_member("grp-2", "i1", 1))
        db.add(_make_member("grp-2", "i3", 2))
        await db.commit()

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1", "i2"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["removed"] == 2
    assert body["notFound"] == []

    # grp-2 still has i1 + i3 — the i1 membership in grp-2 was NOT swept
    # by an over-broad DELETE on issueId alone.
    async with factory() as db:
        grp2_rows = (await db.execute(
            select(IssueGroupMember).where(
                IssueGroupMember.groupId == "grp-2",
            ).order_by(IssueGroupMember.position)
        )).scalars().all()
    assert [(r.position, r.issueId) for r in grp2_rows] == [
        (1, "i1"), (2, "i3"),
    ]


@pytest.mark.asyncio
async def test_bulk_remove_non_member_in_same_project_is_notfound(
    client: AsyncClient, factory,
):
    """An issue that exists in the SAME project but isn't a group member
    lands in notFound (lumped with non-existent ids — see schema docstring
    on the existence-oracle rationale)."""
    await _seed_group_with_members(
        factory, member_issue_ids=["i1"],
    )

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": ["i2"]},  # i2 exists, but isn't in grp-1
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["removed"] == 0
    assert body["notFound"] == ["i2"]


# ---------- 404 ------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_missing_returns_404(client: AsyncClient, factory):
    """Stale URL -> consistent 404 NOT_FOUND, matching add_group_members."""
    resp = await client.request(
        "DELETE",
        "/api/groups/does-not-exist/members",
        json={"issueIds": ["i1"]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "IssueGroup"


# ---------- 422 schema enforcement ----------------------------------------

@pytest.mark.asyncio
async def test_empty_issue_ids_returns_422(client: AsyncClient, factory):
    """Pydantic min_length=1 — a no-op bulk-remove is rejected."""
    await _seed_group_with_members(factory, member_issue_ids=["i1"])

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oversized_issue_ids_returns_422(
    client: AsyncClient, factory,
):
    """Pydantic max_length=500 — bound DELETE blast radius per request."""
    await _seed_group_with_members(factory, member_issue_ids=["i1"])

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": [f"id-{n}" for n in range(501)]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_extra_fields_rejected_422(client: AsyncClient, factory):
    """`extra='forbid'` blocks over-posting on the bulk-remove schema too."""
    await _seed_group_with_members(factory, member_issue_ids=["i1"])

    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": ["i1"], "rogueField": "evil"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oversized_id_returns_422(client: AsyncClient, factory):
    """Per-id 64-char cap on bulk-remove matches bulk-add."""
    await _seed_group_with_members(factory, member_issue_ids=["i1"])

    big_id = "x" * 65
    resp = await client.request(
        "DELETE",
        "/api/groups/grp-1/members",
        json={"issueIds": [big_id]},
    )
    assert resp.status_code == 422
