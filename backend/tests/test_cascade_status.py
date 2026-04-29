"""
Regression tests for status cascade — CB-1941.

The bug: cascade_status_to_parents and friends ran a sibling-status SELECT
without flushing the just-mutated child first. Because the session uses
autoflush=False, the SELECT read pre-mutation DB state and the parent
"all children done" gate never closed when the calling code had already
set the last child to COMPLETED_WAITING_QA in memory.

These tests mirror the production session config (autoflush=False) and
the production call pattern (mutate child in memory, then call the
cascade fn before commit). Without the flush the asserts fail.
"""

import asyncio
import os
import shutil
import tempfile
import time
import uuid
from typing import List, Tuple

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models.database import Base
from models.issue import Issue, Project
from utils.db_queries import (
    cascade_done_to_parents,
    cascade_status_to_parents,
    cascade_status_to_parents_detailed,
)


@pytest_asyncio.fixture
async def session_factory():
    """Async session factory backed by a fresh on-disk SQLite DB.

    Mirrors production: expire_on_commit=False, autoflush=False.
    """
    tmp_dir = tempfile.mkdtemp(prefix="cascade-test-")
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
        path="/tmp/test-project",
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
    title: str,
    issue_type: str,
    status: str,
    parent_id: str | None = None,
) -> Issue:
    issue = Issue(
        id=str(uuid.uuid4()),
        projectId=project_id,
        key=f"CB-{seq}",
        sequence=seq,
        title=title,
        type=issue_type,
        status=status,
        priority="MEDIUM",
        parentId=parent_id,
    )
    session.add(issue)
    return issue


async def _seed_feature_with_task_children(
    session: AsyncSession, n_children: int
) -> Tuple[Issue, List[Issue]]:
    """Build a FEATURE with `n_children` direct TASK children — mirrors JM-F1."""
    project = _make_project(session)
    await session.flush()

    feature = _make_issue(
        session,
        project_id=project.id,
        seq=1,
        title="Feature parent",
        issue_type="FEATURE",
        status="IN_PROGRESS",
    )
    await session.flush()

    children: List[Issue] = []
    for i in range(n_children):
        is_last_blocking = i == n_children - 1
        child = _make_issue(
            session,
            project_id=project.id,
            seq=10 + i,
            title=f"Child {i}",
            issue_type="TASK",
            status="IN_PROGRESS" if is_last_blocking else "COMPLETED_WAITING_QA",
            parent_id=feature.id,
        )
        children.append(child)
    await session.flush()
    return feature, children


@pytest.mark.asyncio
async def test_cascade_status_fires_when_last_child_flips_in_memory(session_factory):
    """The exact CB-1941 scenario.

    13 of 14 TASK children of a FEATURE are already COMPLETED_WAITING_QA.
    The PATCH endpoint sets the 14th child to COMPLETED_WAITING_QA in
    memory and calls cascade_status_to_parents BEFORE commit.
    The parent must be flipped to COMPLETED_WAITING_QA in the same call.
    """
    async with session_factory() as session:
        feature, children = await _seed_feature_with_task_children(session, n_children=14)

        last_child = children[-1]
        last_child.status = "COMPLETED_WAITING_QA"

        updated = await cascade_status_to_parents(
            session, last_child.id, "COMPLETED_WAITING_QA"
        )

        assert feature.id in updated, (
            "FEATURE parent must be cascaded to COMPLETED_WAITING_QA "
            "after the last blocking TASK child is flipped in memory"
        )
        assert feature.status == "COMPLETED_WAITING_QA"


@pytest.mark.asyncio
async def test_cascade_skips_when_a_sibling_still_in_progress(session_factory):
    """Negative case: cascade must NOT fire when one sibling is still IN_PROGRESS."""
    async with session_factory() as session:
        feature, children = await _seed_feature_with_task_children(session, n_children=3)
        # Leave children[0] as COMPLETED_WAITING_QA, children[1] IN_PROGRESS,
        # mark children[2] as COMPLETED_WAITING_QA
        assert children[1].status == "COMPLETED_WAITING_QA"
        children[1].status = "IN_PROGRESS"
        children[-1].status = "COMPLETED_WAITING_QA"

        updated = await cascade_status_to_parents(
            session, children[-1].id, "COMPLETED_WAITING_QA"
        )

        assert updated == []
        assert feature.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_cascade_status_detailed_fires_on_in_memory_flip(session_factory):
    """Detailed variant must also see in-memory child mutation."""
    async with session_factory() as session:
        feature, children = await _seed_feature_with_task_children(session, n_children=4)

        last_child = children[-1]
        last_child.status = "COMPLETED_WAITING_QA"

        transitions = await cascade_status_to_parents_detailed(
            session, last_child.id, "COMPLETED_WAITING_QA"
        )

        assert any(t["id"] == feature.id for t in transitions)
        assert feature.status == "COMPLETED_WAITING_QA"


@pytest.mark.asyncio
async def test_cascade_done_fires_on_in_memory_flip(session_factory):
    """cascade_done_to_parents must also flush before reading siblings."""
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()
        feature = _make_issue(
            session,
            project_id=project.id,
            seq=1,
            title="Feature",
            issue_type="FEATURE",
            status="COMPLETED_WAITING_QA",
        )
        await session.flush()
        c1 = _make_issue(
            session,
            project_id=project.id,
            seq=2,
            title="c1",
            issue_type="TASK",
            status="DONE",
            parent_id=feature.id,
        )
        c2 = _make_issue(
            session,
            project_id=project.id,
            seq=3,
            title="c2",
            issue_type="TASK",
            status="COMPLETED_WAITING_QA",
            parent_id=feature.id,
        )
        await session.flush()

        # In-memory flip: c2 -> DONE
        c2.status = "DONE"

        updated = await cascade_done_to_parents(session, c2.id)

        assert feature.id in updated
        assert feature.status == "DONE"


@pytest.mark.asyncio
async def test_cascade_walks_full_hierarchy_in_one_call(session_factory):
    """Multi-level cascade: TASK -> STORY -> EPIC -> FEATURE in a single call.

    When the last TASK under a STORY flips to CWQ in memory, the cascade must
    flush, see all siblings as CWQ, flip the STORY, then flush again, see the
    EPIC's only child STORY as CWQ, flip the EPIC, etc. — all the way to the
    FEATURE. Without flushing between iterations, the walk would stall after
    the first level.
    """
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()

        feature = _make_issue(
            session,
            project_id=project.id,
            seq=1,
            title="Feature",
            issue_type="FEATURE",
            status="IN_PROGRESS",
        )
        await session.flush()
        epic = _make_issue(
            session,
            project_id=project.id,
            seq=2,
            title="Epic",
            issue_type="EPIC",
            status="IN_PROGRESS",
            parent_id=feature.id,
        )
        await session.flush()
        story = _make_issue(
            session,
            project_id=project.id,
            seq=3,
            title="Story",
            issue_type="STORY",
            status="IN_PROGRESS",
            parent_id=epic.id,
        )
        await session.flush()

        task1 = _make_issue(
            session,
            project_id=project.id,
            seq=4,
            title="t1",
            issue_type="TASK",
            status="COMPLETED_WAITING_QA",
            parent_id=story.id,
        )
        task2 = _make_issue(
            session,
            project_id=project.id,
            seq=5,
            title="t2",
            issue_type="TASK",
            status="IN_PROGRESS",
            parent_id=story.id,
        )
        await session.flush()

        task2.status = "COMPLETED_WAITING_QA"
        updated = await cascade_status_to_parents(
            session, task2.id, "COMPLETED_WAITING_QA"
        )

        assert story.id in updated
        assert epic.id in updated
        assert feature.id in updated
        assert story.status == "COMPLETED_WAITING_QA"
        assert epic.status == "COMPLETED_WAITING_QA"
        assert feature.status == "COMPLETED_WAITING_QA"


@pytest.mark.asyncio
async def test_batch_loop_simulates_endpoint_path(session_factory):
    """Simulate the batch endpoint loop semantics from backend/api/issues.py.

    The endpoint iterates issues, mutates each in memory, then calls
    cascade_status_to_parents on each. With autoflush=False, the LAST
    iteration must still close the gate.
    """
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()

        feature = _make_issue(
            session,
            project_id=project.id,
            seq=1,
            title="Feature",
            issue_type="FEATURE",
            status="IN_PROGRESS",
        )
        await session.flush()

        children = []
        for i in range(5):
            children.append(
                _make_issue(
                    session,
                    project_id=project.id,
                    seq=10 + i,
                    title=f"c{i}",
                    issue_type="TASK",
                    status="IN_PROGRESS",
                    parent_id=feature.id,
                )
            )
        await session.flush()

        # Mirror backend/api/issues.py:715-749 — mutate then cascade per item.
        for child in children:
            child.status = "COMPLETED_WAITING_QA"
            await cascade_status_to_parents(session, child.id, "COMPLETED_WAITING_QA")

        assert feature.status == "COMPLETED_WAITING_QA"
