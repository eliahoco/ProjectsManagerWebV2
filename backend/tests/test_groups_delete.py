"""
CB-1987 — DELETE /api/groups/{group_id}.

Covers the delete-group contract:
  * 204 — happy path: group with no members, group with non-IN_PROGRESS
          members. Members cascade away via FK ondelete=CASCADE; underlying
          issues survive.
  * 404 — group does not exist.
  * 409 — at least one member is IN_PROGRESS (Reader rule from Web Security
          p. 15). details carries inProgressIssueIds + inProgressIssueKeys.
          Group + member rows remain intact (no partial delete).
  * Cross-group isolation: deleting group A does not touch group B's
          members, even when both groups share members.

Mirrors test_groups_get_detail.py / test_groups_post.py fixture pattern:
isolated on-disk SQLite, fresh schema per test module, no production
codeboard.db touch.
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
    tmp_dir = tempfile.mkdtemp(prefix="groups-delete-test-")
    db_path = os.path.join(tmp_dir, "test.db")
    # IssueGroupMember.groupId has ON DELETE CASCADE — SQLite enforces FK
    # cascades only when `PRAGMA foreign_keys = ON`. The aiosqlite driver
    # leaves it OFF by default; without it, deleting the group would leave
    # orphan member rows behind and the cascade test would fail. Wire the
    # pragma via a connect-level event so every connection from this engine
    # turns FK enforcement on.
    from sqlalchemy import event

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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


# ---------- happy path: empty group ----------------------------------------

@pytest.mark.asyncio
async def test_delete_empty_group_returns_204(client: AsyncClient, factory):
    """A group with zero members deletes cleanly with 204 No Content."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_group("g-empty", "proj-1", "Nothing here"))
        await db.commit()

    resp = await client.delete("/api/groups/g-empty")
    assert resp.status_code == 204, resp.text
    assert resp.content == b""

    async with factory() as db:
        groups = (await db.execute(select(IssueGroup))).scalars().all()
    assert groups == []


# ---------- happy path: cascade members, leave issues alone ----------------

@pytest.mark.asyncio
async def test_delete_group_cascades_members_preserves_issues(
    client: AsyncClient, factory,
):
    """Deleting a group drops its IssueGroupMember rows but leaves the
    underlying Issue rows intact. Cascade is the FK ondelete=CASCADE on
    IssueGroupMember.groupId (grouping.py:85)."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        # Statuses chosen so none are IN_PROGRESS — the 409 guard does NOT
        # fire and we exercise the cascade branch.
        db.add(_make_issue("i1", "CB-1", status_="DONE"))
        db.add(_make_issue("i2", "CB-2", status_="BACKLOG"))
        db.add(_make_issue("i3", "CB-3", status_="COMPLETED_WAITING_QA"))
        db.add(_make_group("g1", "proj-1", "Doomed"))
        await db.flush()
        db.add(_make_member("g1", "i1", 1, member_id="m-1"))
        db.add(_make_member("g1", "i2", 2, member_id="m-2"))
        db.add(_make_member("g1", "i3", 3, member_id="m-3"))
        await db.commit()

    resp = await client.delete("/api/groups/g1")
    assert resp.status_code == 204, resp.text

    async with factory() as db:
        groups = (await db.execute(select(IssueGroup))).scalars().all()
        members = (await db.execute(select(IssueGroupMember))).scalars().all()
        issues = (await db.execute(select(Issue))).scalars().all()
    assert groups == []
    assert members == []
    # Issues survive — the FK from IssueGroupMember.issueId back to Issue
    # is one-way; deleting a group never touches Issue rows.
    assert sorted(i.id for i in issues) == ["i1", "i2", "i3"]


# ---------- 404 -----------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_missing_group_returns_404(client: AsyncClient, factory):
    """A stale URL produces 404 NOT_FOUND, not a silent 204 no-op."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.commit()

    resp = await client.delete("/api/groups/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["details"]["resource"] == "IssueGroup"
    assert body["details"]["identifier"] == "does-not-exist"


# ---------- 409 IN_PROGRESS guard ------------------------------------------

@pytest.mark.asyncio
async def test_delete_group_with_in_progress_member_returns_409(
    client: AsyncClient, factory,
):
    """Reader rule (Web Security p. 15): block delete while any member is
    IN_PROGRESS. Response carries every offender's id + key in details so
    the caller can fix the whole list in one batch instead of poking the
    DELETE one offender at a time."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_issue("i1", "CB-1", status_="DONE"))
        db.add(_make_issue("i2", "CB-2", status_="IN_PROGRESS"))
        db.add(_make_issue("i3", "CB-3", status_="BACKLOG"))
        db.add(_make_issue("i4", "CB-4", status_="IN_PROGRESS"))
        db.add(_make_group("g-blocked", "proj-1", "Live work"))
        await db.flush()
        db.add(_make_member("g-blocked", "i1", 1, member_id="m-1"))
        db.add(_make_member("g-blocked", "i2", 2, member_id="m-2"))
        db.add(_make_member("g-blocked", "i3", 3, member_id="m-3"))
        db.add(_make_member("g-blocked", "i4", 4, member_id="m-4"))
        await db.commit()

    resp = await client.delete("/api/groups/g-blocked")
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "CONFLICT"
    assert body["details"]["groupId"] == "g-blocked"
    # Every IN_PROGRESS member surfaces — caller fixes whole list at once.
    assert sorted(body["details"]["inProgressIssueIds"]) == ["i2", "i4"]
    assert sorted(body["details"]["inProgressIssueKeys"]) == ["CB-2", "CB-4"]
    # Non-IN_PROGRESS members do NOT leak into the offender list.
    assert "i1" not in body["details"]["inProgressIssueIds"]
    assert "i3" not in body["details"]["inProgressIssueIds"]

    # No partial delete: the group + every member row is still there.
    async with factory() as db:
        groups = (await db.execute(select(IssueGroup))).scalars().all()
        members = (await db.execute(select(IssueGroupMember))).scalars().all()
    assert [g.id for g in groups] == ["g-blocked"]
    assert sorted(m.issueId for m in members) == ["i1", "i2", "i3", "i4"]


# ---------- cross-group isolation ------------------------------------------

@pytest.mark.asyncio
async def test_delete_group_does_not_touch_other_groups(
    client: AsyncClient, factory,
):
    """Deleting g1 must leave g2 + its memberships fully intact, even when
    both groups share an issue. Guards against an over-broad cascade or a
    DELETE that filters on issueId instead of groupId."""
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()
        db.add(_make_issue("shared", "CB-100", status_="DONE"))
        db.add(_make_issue("only-g1", "CB-101", status_="DONE"))
        db.add(_make_issue("only-g2", "CB-102", status_="DONE"))

        db.add(_make_group("g1", "proj-1", "Doomed"))
        db.add(_make_group("g2", "proj-1", "Survivor"))
        await db.flush()

        db.add(_make_member("g1", "shared", 1, member_id="g1-m1"))
        db.add(_make_member("g1", "only-g1", 2, member_id="g1-m2"))
        db.add(_make_member("g2", "shared", 1, member_id="g2-m1"))
        db.add(_make_member("g2", "only-g2", 2, member_id="g2-m2"))
        await db.commit()

    resp = await client.delete("/api/groups/g1")
    assert resp.status_code == 204, resp.text

    async with factory() as db:
        groups = (await db.execute(
            select(IssueGroup).order_by(IssueGroup.id)
        )).scalars().all()
        members = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.id)
        )).scalars().all()

    # g2 survives; g1 gone.
    assert [g.id for g in groups] == ["g2"]
    # g2's both members remain; g1's both rows gone.
    assert sorted((m.groupId, m.issueId) for m in members) == [
        ("g2", "only-g2"),
        ("g2", "shared"),
    ]


# ---------- guard scoping: shared IN_PROGRESS member ---------------------

@pytest.mark.asyncio
async def test_delete_blocked_only_when_member_belongs_to_target_group(
    client: AsyncClient, factory,
):
    """Reader-rule guard scopes by ``groupId``, not by issue status alone.

    Same IN_PROGRESS issue is in g1 AND g2:
      * Deleting g1 (it has the IN_PROGRESS issue as a member) → 409.
      * Deleting g3 (which has its own member that happens to be the same
        IN_PROGRESS issue) → 409 too. Symmetry check.
      * Deleting g-clean (members are all DONE; the IN_PROGRESS issue is
        NOT a member here) → 204 even though the same IN_PROGRESS issue
        exists in the project. Confirms the guard joins through
        IssueGroupMember.groupId rather than scanning Issue.status
        project-wide.
    """
    async with factory() as db:
        db.add(_make_project("proj-1"))
        await db.flush()

        db.add(_make_issue("live", "CB-1", status_="IN_PROGRESS"))
        db.add(_make_issue("done-1", "CB-2", status_="DONE"))
        db.add(_make_issue("done-2", "CB-3", status_="DONE"))

        db.add(_make_group("g1", "proj-1", "Has live"))
        db.add(_make_group("g3", "proj-1", "Also has live"))
        db.add(_make_group("g-clean", "proj-1", "All done"))
        await db.flush()

        # g1 + g3 both contain the live member.
        db.add(_make_member("g1", "live", 1, member_id="g1-live"))
        db.add(_make_member("g1", "done-1", 2, member_id="g1-done"))
        db.add(_make_member("g3", "live", 1, member_id="g3-live"))
        # g-clean does NOT contain the live member — only DONE issues.
        db.add(_make_member(
            "g-clean", "done-1", 1, member_id="gc-d1",
        ))
        db.add(_make_member(
            "g-clean", "done-2", 2, member_id="gc-d2",
        ))
        await db.commit()

    # g-clean deletes cleanly — the IN_PROGRESS issue is in the project but
    # not in this group, so the guard does not fire.
    resp = await client.delete("/api/groups/g-clean")
    assert resp.status_code == 204, resp.text

    # g1 is blocked (its own membership row points at the IN_PROGRESS issue).
    resp = await client.delete("/api/groups/g1")
    assert resp.status_code == 409
    assert resp.json()["details"]["inProgressIssueIds"] == ["live"]

    # g3 is blocked for the same reason — guard scopes per-group, so a
    # second group sharing the live member is independently blocked.
    resp = await client.delete("/api/groups/g3")
    assert resp.status_code == 409
    assert resp.json()["details"]["inProgressIssueIds"] == ["live"]

    # State check: only g-clean is gone; g1 + g3 + their members survived.
    async with factory() as db:
        groups = (await db.execute(
            select(IssueGroup).order_by(IssueGroup.id)
        )).scalars().all()
        members = (await db.execute(
            select(IssueGroupMember).order_by(IssueGroupMember.id)
        )).scalars().all()

    assert [g.id for g in groups] == ["g1", "g3"]
    # g1 retains both rows; g3 retains its row; g-clean's two rows gone.
    assert sorted(m.id for m in members) == ["g1-done", "g1-live", "g3-live"]
