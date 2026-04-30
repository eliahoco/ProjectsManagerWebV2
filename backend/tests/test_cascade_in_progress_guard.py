"""
Regression tests for CB-1952 — cascade guard against demoting completed parents.

When AutoPilot starts a new task while a sibling tree is already
COMPLETED_WAITING_QA, the in-progress cascade walking upward must NOT downgrade
the CWQ ancestor or walk past it. Walking past a CWQ ancestor caused subsequent
flows to corrupt sibling status during the CB-1578 AutoPilot run on 2026-04-30.
"""

from __future__ import annotations

import uuid
from datetime import datetime
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.database import Base
from models import Issue
from utils.db_queries import (
    cascade_in_progress_to_parents,
    cascade_revert_to_parents,
)


def _make_issue(
    type_: str,
    status: str,
    parent_id: str | None = None,
    seq: int = 1,
    project_id: str = "p",
) -> Issue:
    return Issue(
        id=str(uuid.uuid4()),
        projectId=project_id,
        key=f"T-{seq}",
        sequence=seq,
        type=type_,
        status=status,
        title=f"{type_}-{seq}",
        reporter="t",
        priority="MEDIUM",
        parentId=parent_id,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Sf = async_sessionmaker(engine, expire_on_commit=False)
    async with Sf() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_cascade_in_progress_does_not_demote_cwq_parent(session):
    """STORY=CWQ -> TASK_A=CWQ, TASK_B=IN_PROGRESS. Cascade must not flip STORY."""
    story = _make_issue("STORY", "COMPLETED_WAITING_QA", seq=1)
    task_a = _make_issue("TASK", "COMPLETED_WAITING_QA", parent_id=story.id, seq=2)
    task_b = _make_issue("TASK", "IN_PROGRESS", parent_id=story.id, seq=3)
    session.add_all([story, task_a, task_b])
    await session.commit()

    await cascade_in_progress_to_parents(session, task_b.id)
    await session.commit()

    await session.refresh(story)
    assert story.status == "COMPLETED_WAITING_QA", (
        f"cascade_in_progress_to_parents demoted STORY to {story.status}"
    )
    await session.refresh(task_a)
    assert task_a.status == "COMPLETED_WAITING_QA", (
        f"sibling TASK_A demoted to {task_a.status}"
    )


@pytest.mark.asyncio
async def test_cascade_in_progress_stops_at_done_ancestor(session):
    """FEATURE=DONE -> EPIC=BACKLOG -> STORY=BACKLOG -> TASK=IN_PROGRESS.
    Cascade must stop at DONE FEATURE without demoting it."""
    feat = _make_issue("FEATURE", "DONE", seq=1)
    epic = _make_issue("EPIC", "BACKLOG", parent_id=feat.id, seq=2)
    story = _make_issue("STORY", "BACKLOG", parent_id=epic.id, seq=3)
    task = _make_issue("TASK", "IN_PROGRESS", parent_id=story.id, seq=4)
    session.add_all([feat, epic, story, task])
    await session.commit()

    await cascade_in_progress_to_parents(session, task.id)
    await session.commit()

    await session.refresh(feat)
    await session.refresh(epic)
    await session.refresh(story)
    # Critical: the closed FEATURE must NOT be demoted by sibling activity.
    assert feat.status == "DONE", f"FEATURE demoted to {feat.status}"
    # The intermediate BACKLOG ancestors are promoted to IN_PROGRESS as the
    # walker passes through them — that is correct. The walker then stops at
    # the DONE FEATURE without touching it.
    assert epic.status == "IN_PROGRESS"
    assert story.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_cascade_in_progress_still_promotes_open_ancestors(session):
    """STORY=BACKLOG -> TASK=IN_PROGRESS. Cascade still rolls open parents up."""
    story = _make_issue("STORY", "BACKLOG", seq=1)
    task = _make_issue("TASK", "IN_PROGRESS", parent_id=story.id, seq=2)
    session.add_all([story, task])
    await session.commit()

    updated = await cascade_in_progress_to_parents(session, task.id)
    await session.commit()

    await session.refresh(story)
    assert story.status == "IN_PROGRESS", (
        f"cascade did not promote BACKLOG STORY (got {story.status})"
    )
    assert story.id in updated


@pytest.mark.asyncio
async def test_revert_reopens_cwq_parent_after_failure(session):
    """STORY=CWQ -> TASK_A=CWQ, TASK_B=TODO (just failed). Revert must
    walk up and reopen STORY because not all children are CWQ/DONE."""
    story = _make_issue("STORY", "COMPLETED_WAITING_QA", seq=1)
    task_a = _make_issue("TASK", "COMPLETED_WAITING_QA", parent_id=story.id, seq=2)
    task_b = _make_issue("TASK", "TODO", parent_id=story.id, seq=3)
    session.add_all([story, task_a, task_b])
    await session.commit()

    await cascade_revert_to_parents(session, task_b.id)
    await session.commit()

    await session.refresh(story)
    assert story.status in ("IN_PROGRESS", "TODO", "BACKLOG"), (
        f"STORY remained {story.status}; revert should have reopened the gate"
    )
    await session.refresh(task_a)
    assert task_a.status == "COMPLETED_WAITING_QA", (
        f"TASK_A demoted to {task_a.status} (revert must not touch siblings)"
    )
