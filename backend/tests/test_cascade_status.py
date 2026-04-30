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
    cascade_revert_to_parents,
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
async def test_cascade_revert_walks_full_hierarchy(session_factory):
    """CB-1943: cascade_revert_to_parents reverses the full chain in one call.

    Pre-state mirrors a fully-completed FEATURE→EPIC→STORY→TASK chain. When the
    leaf TASK is moved off CWQ in memory, every CWQ ancestor must drop to
    IN_PROGRESS — STORY first, then EPIC, then FEATURE — in a single call.
    """
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()

        feature = _make_issue(
            session, project_id=project.id, seq=1, title="Feature",
            issue_type="FEATURE", status="COMPLETED_WAITING_QA",
        )
        await session.flush()
        epic = _make_issue(
            session, project_id=project.id, seq=2, title="Epic",
            issue_type="EPIC", status="COMPLETED_WAITING_QA",
            parent_id=feature.id,
        )
        await session.flush()
        story = _make_issue(
            session, project_id=project.id, seq=3, title="Story",
            issue_type="STORY", status="COMPLETED_WAITING_QA",
            parent_id=epic.id,
        )
        await session.flush()
        task = _make_issue(
            session, project_id=project.id, seq=4, title="Task",
            issue_type="TASK", status="COMPLETED_WAITING_QA",
            parent_id=story.id,
        )
        await session.flush()

        # In-memory revert
        task.status = "BACKLOG"
        reverted = await cascade_revert_to_parents(session, task.id)

        assert story.id in reverted
        assert epic.id in reverted
        assert feature.id in reverted
        assert story.status == "IN_PROGRESS"
        assert epic.status == "IN_PROGRESS"
        assert feature.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_cascade_revert_propagates_through_sibling_subtrees(session_factory):
    """A reverted leaf invalidates the gate for its STORY parent and, in
    consequence, for every CWQ ancestor — even when the EPIC has another
    fully-complete STORY subtree (`story_b`). The revert reaches story_a's
    gate first; that revert then re-opens the EPIC's gate; the EPIC reverts;
    that re-opens the FEATURE's gate; the FEATURE reverts. story_b is
    untouched because it has no path to the patched leaf.
    """
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()

        feature = _make_issue(
            session, project_id=project.id, seq=1, title="Feature",
            issue_type="FEATURE", status="COMPLETED_WAITING_QA",
        )
        await session.flush()
        epic = _make_issue(
            session, project_id=project.id, seq=2, title="Epic",
            issue_type="EPIC", status="COMPLETED_WAITING_QA",
            parent_id=feature.id,
        )
        await session.flush()

        # Two stories under the epic — both CWQ
        story_a = _make_issue(
            session, project_id=project.id, seq=3, title="StoryA",
            issue_type="STORY", status="COMPLETED_WAITING_QA",
            parent_id=epic.id,
        )
        story_b = _make_issue(
            session, project_id=project.id, seq=4, title="StoryB",
            issue_type="STORY", status="COMPLETED_WAITING_QA",
            parent_id=epic.id,
        )
        await session.flush()

        # Story A has two TASK children, both CWQ.
        task_a1 = _make_issue(
            session, project_id=project.id, seq=10, title="t-a1",
            issue_type="TASK", status="COMPLETED_WAITING_QA",
            parent_id=story_a.id,
        )
        task_a2 = _make_issue(
            session, project_id=project.id, seq=11, title="t-a2",
            issue_type="TASK", status="COMPLETED_WAITING_QA",
            parent_id=story_a.id,
        )
        await session.flush()

        # Revert one TASK under story_a
        task_a1.status = "IN_PROGRESS"
        reverted = await cascade_revert_to_parents(session, task_a1.id)

        # story_a flips off CWQ (it has a non-CWQ child now)
        assert story_a.id in reverted
        assert story_a.status == "IN_PROGRESS"
        # epic also flips, because one of its STORY children (story_a) is no
        # longer CWQ — even though story_b is still CWQ
        assert epic.id in reverted
        # feature also flips, since the epic just reverted
        assert feature.id in reverted

        # story_b untouched
        assert story_b.status == "COMPLETED_WAITING_QA"


@pytest.mark.asyncio
async def test_cascade_revert_skips_parent_already_below_cwq(session_factory):
    """If an ancestor is already at IN_PROGRESS or earlier, walking stops.

    The cascade_revert function exits as soon as it encounters an ancestor
    whose status is not CWQ/DONE — its further ancestors are unaffected by
    this child's revert.
    """
    async with session_factory() as session:
        project = _make_project(session)
        await session.flush()

        feature = _make_issue(
            session, project_id=project.id, seq=1, title="Feature",
            issue_type="FEATURE", status="IN_PROGRESS",   # already in_progress
        )
        await session.flush()
        epic = _make_issue(
            session, project_id=project.id, seq=2, title="Epic",
            issue_type="EPIC", status="IN_PROGRESS",       # already in_progress
            parent_id=feature.id,
        )
        await session.flush()
        story = _make_issue(
            session, project_id=project.id, seq=3, title="Story",
            issue_type="STORY", status="COMPLETED_WAITING_QA",
            parent_id=epic.id,
        )
        await session.flush()
        task = _make_issue(
            session, project_id=project.id, seq=4, title="Task",
            issue_type="TASK", status="COMPLETED_WAITING_QA",
            parent_id=story.id,
        )
        await session.flush()

        task.status = "BACKLOG"
        reverted = await cascade_revert_to_parents(session, task.id)

        # Story reverts (it was at CWQ, now has a non-CWQ child)
        assert story.id in reverted
        assert story.status == "IN_PROGRESS"
        # Epic was already IN_PROGRESS — function stops walking, no change
        assert epic.id not in reverted
        assert feature.id not in reverted


@pytest.mark.asyncio
async def test_cascade_revert_noop_when_child_returns_to_cwq_via_round_trip(session_factory):
    """Round-trip: revert then re-complete should leave parents at CWQ."""
    async with session_factory() as session:
        feature, children = await _seed_feature_with_task_children(session, n_children=3)
        # Force everyone to CWQ first
        for c in children:
            c.status = "COMPLETED_WAITING_QA"
        feature.status = "COMPLETED_WAITING_QA"
        await session.flush()

        # Revert one child
        children[0].status = "BACKLOG"
        reverted = await cascade_revert_to_parents(session, children[0].id)
        assert feature.id in reverted
        assert feature.status == "IN_PROGRESS"

        # Re-complete it
        children[0].status = "COMPLETED_WAITING_QA"
        updated = await cascade_status_to_parents(
            session, children[0].id, "COMPLETED_WAITING_QA"
        )
        assert feature.id in updated
        assert feature.status == "COMPLETED_WAITING_QA"


@pytest.mark.asyncio
async def test_cascade_revert_fires_when_parent_is_done_not_just_cwq(session_factory):
    """Function entry condition is `status in (CWQ, DONE)` — exercise the DONE branch."""
    async with session_factory() as session:
        feature, children = await _seed_feature_with_task_children(session, n_children=3)
        for c in children:
            c.status = "DONE"
        feature.status = "DONE"
        await session.flush()

        children[0].status = "IN_PROGRESS"
        reverted = await cascade_revert_to_parents(session, children[0].id)
        assert feature.id in reverted
        assert feature.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_cascade_revert_triggered_by_in_review_transition(session_factory):
    """The dispatcher in update_issue calls cascade_revert for any of
    BACKLOG / TODO / IN_PROGRESS / IN_REVIEW. Exercise IN_REVIEW path here."""
    async with session_factory() as session:
        feature, children = await _seed_feature_with_task_children(session, n_children=2)
        for c in children:
            c.status = "COMPLETED_WAITING_QA"
        feature.status = "COMPLETED_WAITING_QA"
        await session.flush()

        children[0].status = "IN_REVIEW"
        reverted = await cascade_revert_to_parents(session, children[0].id)
        assert feature.id in reverted
        assert feature.status == "IN_PROGRESS"


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
