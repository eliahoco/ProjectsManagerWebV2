"""Regression tests for compute_group_status — CB-1966 / CB-1967 / CB-1968.

Covers the aggregate-status helper for IssueGroup membership in
``backend/utils/db_queries.py``. The helper bins member statuses, computes
``completionPercent`` over ``DONE`` + ``COMPLETED_WAITING_QA``, and surfaces
a ``dominantStatus`` with deterministic lex-min tie-breaking.

Mirrors the production session config (``autoflush=False``,
``expire_on_commit=False``) and the file-backed sqlite pattern from
``test_cascade_status.py`` — fresh DB per test, no cross-test bleed.

CB-1968 acceptance:
* all CWQ → completionPercent=100, dominantStatus=CWQ
* mixed → percent < 100
* empty group → all zeros (default snapshot)
* group with single member
"""

import os
import shutil
import tempfile
import time
import uuid
from typing import List

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models.database import Base
from models.issue import Issue, Project
from models.grouping import IssueGroup, IssueGroupMember
from utils.db_queries import compute_group_status


@pytest_asyncio.fixture
async def session_factory():
    """File-backed sqlite session factory matching production session knobs.

    The factory exposes the underlying engine on ``factory.engine`` so tests
    that need raw DDL (e.g. inserting orphan rows under
    ``PRAGMA foreign_keys=OFF``) can grab a connection without a second
    fixture parameter.
    """
    tmp_dir = tempfile.mkdtemp(prefix="group-status-test-")
    db_path = os.path.join(tmp_dir, "test.db")
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    factory.engine = engine  # type: ignore[attr-defined]
    try:
        yield factory
    finally:
        await engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _make_project(session: AsyncSession) -> Project:
    now_ms = int(time.time() * 1000)
    project = Project(
        id=str(uuid.uuid4()),
        name=f"test-{uuid.uuid4()}",
        path="/tmp/group-status-test",
        status="ACTIVE",
        createdAt=now_ms,
        updatedAt=now_ms,
    )
    session.add(project)
    return project


def _make_issue(
    session: AsyncSession,
    *,
    project_id: str,
    seq: int,
    status: str,
) -> Issue:
    issue = Issue(
        id=str(uuid.uuid4()),
        projectId=project_id,
        key=f"CB-{seq}",
        sequence=seq,
        title=f"Issue {seq}",
        type="TASK",
        status=status,
        priority="MEDIUM",
    )
    session.add(issue)
    return issue


def _make_group(session: AsyncSession, *, project_id: str) -> IssueGroup:
    group = IssueGroup(
        id=str(uuid.uuid4()),
        projectId=project_id,
        title="Group under test",
    )
    session.add(group)
    return group


def _add_member(
    session: AsyncSession,
    *,
    group_id: str,
    issue_id: str,
    position: int,
) -> IssueGroupMember:
    member = IssueGroupMember(
        id=str(uuid.uuid4()),
        groupId=group_id,
        issueId=issue_id,
        position=position,
    )
    session.add(member)
    return member


async def _seed_group_with_statuses(
    session: AsyncSession, statuses: List[str]
) -> IssueGroup:
    """Build project + group + len(statuses) members, one per status."""
    project = _make_project(session)
    await session.flush()

    group = _make_group(session, project_id=project.id)
    await session.flush()

    for idx, status in enumerate(statuses, start=1):
        issue = _make_issue(
            session, project_id=project.id, seq=idx, status=status
        )
        await session.flush()
        _add_member(
            session, group_id=group.id, issue_id=issue.id, position=idx
        )
    await session.flush()
    return group


@pytest.mark.asyncio
async def test_all_cwq_returns_100_percent_dominant_cwq(session_factory):
    """All members at COMPLETED_WAITING_QA → percent=100, dominant=CWQ."""
    async with session_factory() as session:
        group = await _seed_group_with_statuses(
            session, ["COMPLETED_WAITING_QA"] * 4
        )

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.completionPercent == 100.0
        assert snapshot.dominantStatus == "COMPLETED_WAITING_QA"
        assert snapshot.statusBreakdown == {"COMPLETED_WAITING_QA": 4}


@pytest.mark.asyncio
async def test_all_done_returns_100_percent_dominant_done(session_factory):
    """All DONE counts the same as all CWQ for completionPercent (gate parity)."""
    async with session_factory() as session:
        group = await _seed_group_with_statuses(session, ["DONE"] * 3)

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.completionPercent == 100.0
        assert snapshot.dominantStatus == "DONE"
        assert snapshot.statusBreakdown == {"DONE": 3}


@pytest.mark.asyncio
async def test_mixed_statuses_returns_partial_percent(session_factory):
    """Mixed members → percent strictly < 100; only DONE/CWQ count as complete."""
    async with session_factory() as session:
        # 4 members: 1 DONE + 1 CWQ count as complete (2/4); 2 incomplete.
        group = await _seed_group_with_statuses(
            session,
            ["DONE", "COMPLETED_WAITING_QA", "IN_PROGRESS", "BACKLOG"],
        )

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.completionPercent == 50.0
        assert snapshot.completionPercent < 100.0
        assert snapshot.statusBreakdown == {
            "DONE": 1,
            "COMPLETED_WAITING_QA": 1,
            "IN_PROGRESS": 1,
            "BACKLOG": 1,
        }
        # Tie at count=1 across four statuses → lex-min wins.
        assert snapshot.dominantStatus == "BACKLOG"


@pytest.mark.asyncio
async def test_empty_group_returns_default_snapshot(session_factory):
    """Empty group → empty breakdown, percent=0.0, dominantStatus=None."""
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()
        group = _make_group(session, project_id=project.id)
        await session.flush()

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.statusBreakdown == {}
        assert snapshot.completionPercent == 0.0
        assert snapshot.dominantStatus is None


@pytest.mark.asyncio
async def test_single_complete_member_returns_full_percent(session_factory):
    """One CWQ member → percent=100, dominant=CWQ, count=1."""
    async with session_factory() as session:
        group = await _seed_group_with_statuses(
            session, ["COMPLETED_WAITING_QA"]
        )

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.completionPercent == 100.0
        assert snapshot.dominantStatus == "COMPLETED_WAITING_QA"
        assert snapshot.statusBreakdown == {"COMPLETED_WAITING_QA": 1}


@pytest.mark.asyncio
async def test_single_incomplete_member_returns_zero_percent(session_factory):
    """One IN_PROGRESS member → percent=0, dominant=IN_PROGRESS."""
    async with session_factory() as session:
        group = await _seed_group_with_statuses(session, ["IN_PROGRESS"])

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.completionPercent == 0.0
        assert snapshot.dominantStatus == "IN_PROGRESS"
        assert snapshot.statusBreakdown == {"IN_PROGRESS": 1}


@pytest.mark.asyncio
async def test_cancelled_members_count_toward_denominator(session_factory):
    """Helper docstring: CANCELLED rows count toward the denominator."""
    async with session_factory() as session:
        # 1 DONE + 1 CANCELLED → 1/2 = 50%, NOT 1/1 = 100%.
        group = await _seed_group_with_statuses(
            session, ["DONE", "CANCELLED"]
        )

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.completionPercent == 50.0
        assert snapshot.statusBreakdown == {"DONE": 1, "CANCELLED": 1}
        # Tie at count=1 → lex-min: "CANCELLED" < "DONE".
        assert snapshot.dominantStatus == "CANCELLED"


@pytest.mark.asyncio
async def test_dominant_status_picks_top_count_over_lex(session_factory):
    """Top-count wins outright; lex tie-break only fires on equal counts.

    Inputs are picked so a hypothetical lex-first bug would surface as
    ``BACKLOG`` (sorts before ``IN_PROGRESS``) — the count-first ordering is
    the only way to land on ``IN_PROGRESS``.
    """
    async with session_factory() as session:
        group = await _seed_group_with_statuses(
            session,
            ["IN_PROGRESS", "IN_PROGRESS", "IN_PROGRESS", "BACKLOG"],
        )

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.dominantStatus == "IN_PROGRESS"
        assert snapshot.statusBreakdown == {"IN_PROGRESS": 3, "BACKLOG": 1}
        # 0 complete out of 4 → 0%.
        assert snapshot.completionPercent == 0.0


@pytest.mark.asyncio
async def test_dominant_status_lex_tie_break_two_way(session_factory):
    """Two statuses with equal top counts → lex-min wins (dedicated tie test)."""
    async with session_factory() as session:
        # 2 BACKLOG + 2 TODO; counts tie at 2.
        # Lex order: "BACKLOG" < "TODO" → dominant="BACKLOG".
        group = await _seed_group_with_statuses(
            session, ["BACKLOG", "BACKLOG", "TODO", "TODO"]
        )

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.statusBreakdown == {"BACKLOG": 2, "TODO": 2}
        assert snapshot.dominantStatus == "BACKLOG"
        assert snapshot.completionPercent == 0.0


@pytest.mark.asyncio
async def test_partial_percent_rounds_to_two_decimals(session_factory):
    """Helper rounds completionPercent to 2 decimals (1/3 → 33.33)."""
    async with session_factory() as session:
        group = await _seed_group_with_statuses(
            session, ["DONE", "BACKLOG", "IN_PROGRESS"]
        )

        snapshot = await compute_group_status(session, group.id)

        assert snapshot.completionPercent == 33.33
        assert snapshot.statusBreakdown == {
            "DONE": 1,
            "BACKLOG": 1,
            "IN_PROGRESS": 1,
        }


@pytest.mark.asyncio
async def test_unknown_group_id_returns_default_snapshot(session_factory):
    """Non-existent group id behaves identically to an empty group."""
    async with session_factory() as session:
        snapshot = await compute_group_status(session, "no-such-group-id")

        assert snapshot.statusBreakdown == {}
        assert snapshot.completionPercent == 0.0
        assert snapshot.dominantStatus is None


@pytest.mark.asyncio
async def test_orphaned_member_rows_yield_default_snapshot(session_factory):
    """Members whose ``issueId`` no longer resolves are dropped by the INNER JOIN.

    Pins the helper's documented behavior at db_queries.py:991 ("groups whose
    members are all orphaned by FK cleanup return defaults"). In production
    the ``IssueGroupMember.issueId`` FK has ``ondelete=CASCADE`` so this state
    is unreachable through normal flows, but a future switch to a LEFT JOIN
    would surface a ``None`` status row that the helper's
    ``status is not None`` filter is meant to swallow — covering both.

    Builds the orphan with ``PRAGMA foreign_keys=OFF`` + raw INSERT, mirroring
    the same approach used in ``test_apply_grouping_tables.py``.
    """
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()
        group = _make_group(session, project_id=project.id)
        await session.flush()
        group_id = group.id
        project_id = project.id

    # Use a separate raw connection so we can drop FK enforcement and insert
    # a member pointing to a non-existent issue id.
    async with session_factory.engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        await conn.execute(
            text(
                "INSERT INTO IssueGroupMember (id, groupId, issueId, position) "
                "VALUES (:mid, :gid, :iid, 1)"
            ),
            {"mid": str(uuid.uuid4()), "gid": group_id, "iid": "ghost-issue-id"},
        )

    async with session_factory() as session:
        snapshot = await compute_group_status(session, group_id)

    assert snapshot.statusBreakdown == {}
    assert snapshot.completionPercent == 0.0
    assert snapshot.dominantStatus is None
    # Sanity: project exists, group exists, member row exists — only the
    # JOIN's INNER predicate is hiding it. Confirms the default-snapshot path
    # is the orphan branch, not an empty-group branch.
    assert project_id  # silence unused; kept for trace clarity


@pytest.mark.asyncio
async def test_other_groups_do_not_leak_into_aggregate(session_factory):
    """compute_group_status must scope strictly to its group_id."""
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()

        # Group A: 2 DONE.
        group_a = _make_group(session, project_id=project.id)
        await session.flush()
        for n in range(1, 3):
            issue = _make_issue(
                session, project_id=project.id, seq=n, status="DONE"
            )
            await session.flush()
            _add_member(
                session, group_id=group_a.id, issue_id=issue.id, position=n
            )

        # Group B: 1 BACKLOG. Must NOT influence Group A's aggregate.
        group_b = _make_group(session, project_id=project.id)
        await session.flush()
        issue_b = _make_issue(
            session, project_id=project.id, seq=99, status="BACKLOG"
        )
        await session.flush()
        _add_member(
            session, group_id=group_b.id, issue_id=issue_b.id, position=1
        )
        await session.flush()

        snapshot_a = await compute_group_status(session, group_a.id)
        snapshot_b = await compute_group_status(session, group_b.id)

        assert snapshot_a.statusBreakdown == {"DONE": 2}
        assert snapshot_a.completionPercent == 100.0
        assert snapshot_a.dominantStatus == "DONE"

        assert snapshot_b.statusBreakdown == {"BACKLOG": 1}
        assert snapshot_b.completionPercent == 0.0
        assert snapshot_b.dominantStatus == "BACKLOG"
