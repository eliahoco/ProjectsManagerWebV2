"""
End-to-end persistence + rehydration tests for CB-1951 E2.

Verifies:
- Crash mid-queue → next backend startup rehydrates the queue
- Stale RUNNING tasks become failed(crash_recovery) on rehydration
- Queue itself flips to paused/crash_recovery
- ``get_recovered_queues`` returns the rehydrated queue
- ``clear_recovery_state`` removes it once the user acts
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.database import Base
from models import Project
from services.autopilot_queue_service import (
    AutoPilotQueue,
    AutoPilotQueueService,
    QueueConfig,
    QueueStatus,
    QueueTask,
    TaskStatus,
)
from utils.autopilot_repository import save_queue


@pytest_asyncio.fixture
async def engine_and_session_factory(monkeypatch):
    """In-memory engine + session factory; patched into AsyncSessionLocal so
    the service uses our test DB instead of the real one."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Sf = async_sessionmaker(engine, expire_on_commit=False)

    # Seed a project so FK constraints satisfy
    async with Sf() as s:
        s.add(Project(
            id="p-test", name="test-project", path="/tmp/test",
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    # Monkeypatch AsyncSessionLocal everywhere it's used in the service
    import models.database
    import services.autopilot_queue_service as svc_mod
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)

    yield engine, Sf
    await engine.dispose()


def _make_queue(qid: str | None = None, n_tasks: int = 3) -> AutoPilotQueue:
    qid = qid or str(uuid.uuid4())
    tasks = [
        QueueTask(
            issue_id=f"issue-{i}",
            issue_key=f"CB-{1000 + i}",
            issue_title=f"Task {i}",
            order=i,
            status=TaskStatus.PENDING,
        )
        for i in range(n_tasks)
    ]
    return AutoPilotQueue(
        id=qid, feature_id="feat-1", feature_key="CB-1951",
        project_id="p-test", project_path="/tmp/test",
        status=QueueStatus.RUNNING, tasks=tasks,
        config=QueueConfig(),
        created_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_rehydrate_recovers_running_queue(engine_and_session_factory):
    """Persist a RUNNING queue, drop in-memory state, verify rehydrate restores it."""
    _, Sf = engine_and_session_factory

    # ---- "Pre-crash" service: persist a queue with one running task ----
    pre_svc = AutoPilotQueueService()
    queue = _make_queue(n_tasks=3)
    queue.tasks[0].status = TaskStatus.COMPLETED
    queue.tasks[1].status = TaskStatus.RUNNING  # got killed by crash
    queue.tasks[2].status = TaskStatus.PENDING
    queue.current_index = 1
    pre_svc._queues[queue.id] = queue
    pre_svc._active_queue_id = queue.id

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # ---- "Post-crash" service: fresh instance simulating restart ----
    post_svc = AutoPilotQueueService()
    recovered_ids = await post_svc.rehydrate_from_db()

    assert recovered_ids == [queue.id]
    assert queue.id in post_svc._queues
    assert post_svc._active_queue_id == queue.id

    rehydrated = post_svc._queues[queue.id]
    # Queue should be paused with crash_recovery reason
    assert rehydrated.status == QueueStatus.PAUSED
    assert rehydrated.pause_reason == "crash_recovery"  # type: ignore[attr-defined]
    assert rehydrated.current_index == 1

    # Task 1 (was RUNNING) should now be FAILED with crash_recovery reason
    statuses = {t.order: (t.status, t.error) for t in rehydrated.tasks}
    assert statuses[0][0] == TaskStatus.COMPLETED
    assert statuses[1][0] == TaskStatus.FAILED
    assert statuses[1][1] == "backend_crash_recovery"
    assert statuses[2][0] == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_rehydrate_clean_startup_returns_empty(engine_and_session_factory):
    """No persisted queues → rehydrate returns empty list, no errors."""
    _, _ = engine_and_session_factory
    svc = AutoPilotQueueService()
    recovered = await svc.rehydrate_from_db()
    assert recovered == []
    assert svc._queues == {}
    assert svc._active_queue_id is None


@pytest.mark.asyncio
async def test_get_recovered_queues_filters(engine_and_session_factory):
    """Only queues marked as recovered should be returned."""
    _, Sf = engine_and_session_factory
    svc = AutoPilotQueueService()

    q_recovered = _make_queue()
    q_recovered.tasks[0].status = TaskStatus.RUNNING
    async with Sf() as db:
        await save_queue(db, q_recovered)
        await db.commit()

    await svc.rehydrate_from_db()

    # Add a fresh queue NOT from recovery
    q_fresh = _make_queue()
    svc._queues[q_fresh.id] = q_fresh

    recovered = svc.get_recovered_queues()
    assert len(recovered) == 1
    assert recovered[0].id == q_recovered.id


@pytest.mark.asyncio
async def test_clear_recovery_state(engine_and_session_factory):
    """clear_recovery_state should drop a queue from the recovery set."""
    _, Sf = engine_and_session_factory
    svc = AutoPilotQueueService()

    q = _make_queue()
    async with Sf() as db:
        await save_queue(db, q)
        await db.commit()

    await svc.rehydrate_from_db()
    assert q.id in svc._recovered_queue_ids

    svc.clear_recovery_state(q.id)
    assert q.id not in svc._recovered_queue_ids
    # Queue should still be in _queues — clearing recovery doesn't delete
    assert q.id in svc._queues


@pytest.mark.asyncio
async def test_rehydrate_skips_terminal_queues(engine_and_session_factory):
    """Completed / aborted queues should NOT be rehydrated."""
    _, Sf = engine_and_session_factory

    q_completed = _make_queue()
    q_completed.status = QueueStatus.COMPLETED
    q_aborted = _make_queue()
    q_aborted.status = QueueStatus.ABORTED

    async with Sf() as db:
        await save_queue(db, q_completed)
        await save_queue(db, q_aborted)
        await db.commit()

    svc = AutoPilotQueueService()
    recovered = await svc.rehydrate_from_db()

    assert recovered == []
    assert svc._queues == {}
