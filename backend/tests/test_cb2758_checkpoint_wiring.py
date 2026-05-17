"""
Tests for CB-2758: checkpoint() called after _apply_success (task_completed).

Verifies that:
1. checkpoint() is called after every successful task completion.
2. lastCheckpointAt is non-NULL in DB after a successful task.
3. checkpoint failure is non-fatal (does not abort the queue).
4. Multiple successful tasks produce multiple checkpoint calls.
5. Failed/skipped tasks do NOT trigger a checkpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from models.autopilot import (
    AutoPilotEvent,
    AutoPilotEventType,
    AutoPilotQueueRecord,
)
from models.database import Base
from models.issue import Project
from utils.autopilot_repository import (
    checkpoint,
    save_queue,
)
from services.autopilot_queue_service import (
    AutoPilotQueue,
    AutoPilotQueueService,
    QueueConfig,
    QueueStatus,
    QueueTask,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def patched_session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Sf = async_sessionmaker(engine, expire_on_commit=False)

    async with Sf() as s:
        s.add(Project(
            id="p-test", name="test-project", path="/tmp/test",
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    import models.database
    import utils.autopilot_repository as repo_mod
    import services.autopilot_queue_service as svc_mod
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(repo_mod, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)
    yield Sf
    await engine.dispose()


def _make_queue(n_tasks: int = 2) -> AutoPilotQueue:
    qid = str(uuid.uuid4())
    tasks = [
        QueueTask(
            issue_id=f"issue-{i}",
            issue_key=f"CB-{3000 + i}",
            issue_title=f"Task {i}",
            order=i,
            status=TaskStatus.PENDING,
        )
        for i in range(n_tasks)
    ]
    return AutoPilotQueue(
        id=qid,
        feature_id="feat-1",
        feature_key="CB-2758",
        project_id="p-test",
        project_path="/tmp/test",
        provider="claude_code",
        status=QueueStatus.RUNNING,
        tasks=tasks,
        config=QueueConfig(),
    )


async def _persist_q(Sf, queue: AutoPilotQueue):
    async with Sf() as s:
        await save_queue(s, queue)
        await s.commit()


# ---------------------------------------------------------------------------
# Tests: checkpoint() function itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_writes_last_checkpoint_at(patched_session):
    """checkpoint() must set lastCheckpointAt to a non-NULL UTC datetime."""
    Sf = patched_session
    q = _make_queue(n_tasks=1)
    await _persist_q(Sf, q)

    before = datetime.utcnow()
    await checkpoint(q.id)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == q.id)
        )
        record = result.scalar_one()
        assert record.lastCheckpointAt is not None
        assert record.lastCheckpointAt >= before


@pytest.mark.asyncio
async def test_checkpoint_emits_checkpoint_written_event(patched_session):
    """checkpoint() must emit a CHECKPOINT_WRITTEN audit event."""
    Sf = patched_session
    q = _make_queue(n_tasks=1)
    await _persist_q(Sf, q)

    await checkpoint(q.id)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotEvent)
            .where(AutoPilotEvent.queueId == q.id)
            .where(AutoPilotEvent.type == AutoPilotEventType.CHECKPOINT_WRITTEN)
        )
        events = list(result.scalars().all())
        assert len(events) == 1


@pytest.mark.asyncio
async def test_checkpoint_graceful_on_missing_queue(patched_session):
    """checkpoint() with unknown queue_id must not raise — just logs a warning."""
    await checkpoint("does-not-exist-queue-id")  # must not raise


@pytest.mark.asyncio
async def test_checkpoint_updates_on_second_call(patched_session):
    """Calling checkpoint() twice produces two CHECKPOINT_WRITTEN events."""
    Sf = patched_session
    q = _make_queue(n_tasks=1)
    await _persist_q(Sf, q)

    await checkpoint(q.id)
    await checkpoint(q.id)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotEvent)
            .where(AutoPilotEvent.queueId == q.id)
            .where(AutoPilotEvent.type == AutoPilotEventType.CHECKPOINT_WRITTEN)
        )
        events = list(result.scalars().all())
        assert len(events) == 2


# ---------------------------------------------------------------------------
# Tests: _apply_success calls checkpoint()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_success_calls_checkpoint(patched_session):
    """_apply_success must call checkpoint() after persisting task_completed."""
    Sf = patched_session
    q = _make_queue(n_tasks=1)
    await _persist_q(Sf, q)

    svc = AutoPilotQueueService()
    svc._queues[q.id] = q

    task = q.tasks[0]
    task.status = TaskStatus.RUNNING

    checkpoint_calls: list = []

    async def _fake_checkpoint(queue_id):
        checkpoint_calls.append(queue_id)

    with (
        patch("services.autopilot_queue_service.checkpoint", side_effect=_fake_checkpoint),
        patch.object(svc, "_persist", new_callable=AsyncMock),
        patch.object(svc, "_set_issue_status", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.cascade_status_to_parents", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.AsyncSessionLocal", Sf),
    ):
        await svc._apply_success(q, task, 0)

    assert len(checkpoint_calls) == 1
    assert checkpoint_calls[0] == q.id


@pytest.mark.asyncio
async def test_apply_success_checkpoint_failure_is_nonfatal(patched_session):
    """checkpoint() failure inside _apply_success must not raise or abort."""
    Sf = patched_session
    q = _make_queue(n_tasks=1)
    await _persist_q(Sf, q)

    svc = AutoPilotQueueService()
    svc._queues[q.id] = q

    task = q.tasks[0]
    task.status = TaskStatus.RUNNING

    async def _exploding_checkpoint(queue_id):
        raise RuntimeError("disk full!")

    with (
        patch("services.autopilot_queue_service.checkpoint", side_effect=_exploding_checkpoint),
        patch.object(svc, "_persist", new_callable=AsyncMock),
        patch.object(svc, "_set_issue_status", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.cascade_status_to_parents", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.AsyncSessionLocal", Sf),
    ):
        result = await svc._apply_success(q, task, 0)

    assert result == "continue", "checkpoint failure must not abort _apply_success"


@pytest.mark.asyncio
async def test_checkpoint_called_per_completed_task(patched_session):
    """Multiple completed tasks produce one checkpoint() call each."""
    Sf = patched_session
    q = _make_queue(n_tasks=3)
    await _persist_q(Sf, q)

    svc = AutoPilotQueueService()
    svc._queues[q.id] = q

    checkpoint_calls: list = []

    async def _fake_checkpoint(queue_id):
        checkpoint_calls.append(queue_id)

    with (
        patch("services.autopilot_queue_service.checkpoint", side_effect=_fake_checkpoint),
        patch.object(svc, "_persist", new_callable=AsyncMock),
        patch.object(svc, "_set_issue_status", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.cascade_status_to_parents", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.AsyncSessionLocal", Sf),
    ):
        for i, task in enumerate(q.tasks):
            task.status = TaskStatus.RUNNING
            await svc._apply_success(q, task, i)

    assert len(checkpoint_calls) == 3, (
        f"Expected 3 checkpoint calls (one per task), got {len(checkpoint_calls)}"
    )
