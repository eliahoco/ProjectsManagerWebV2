"""
Unit tests for utils.autopilot_repository — CB-1951 E1.2.2.

Covers: save_queue (insert + update), load_queue, load_active_queue / queues,
record_event, list_events, mark_running_tasks_failed_on_recovery, and the
queue_status_counts metrics helper.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.database import Base
from models import (
    AutoPilotEvent,
    AutoPilotQueueRecord,
    AutoPilotTaskRecord,
    Issue,
    Project,
)
from services.autopilot_queue_service import (
    AutoPilotQueue,
    QueueConfig,
    QueueStatus,
    QueueTask,
    TaskStatus,
)
from utils.autopilot_repository import (
    list_events,
    load_active_queue,
    load_active_queues,
    load_queue,
    mark_running_tasks_failed_on_recovery,
    queue_status_counts,
    record_event,
    save_queue,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Sf = async_sessionmaker(engine, expire_on_commit=False)
    async with Sf() as s:
        # Seed a project so FK constraints are satisfied.
        s.add(Project(
            id="p-test",
            name="test-project",
            path="/tmp/test",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()
        yield s
    await engine.dispose()


def _make_queue(
    queue_id: str | None = None,
    status: QueueStatus = QueueStatus.RUNNING,
    n_tasks: int = 3,
    feature_id: str = "feat-1",
) -> AutoPilotQueue:
    qid = queue_id or str(uuid.uuid4())
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
        id=qid,
        feature_id=feature_id,
        feature_key="CB-1951",
        project_id="p-test",
        project_path="/tmp/test",
        status=status,
        tasks=tasks,
        config=QueueConfig(on_success="MARK_WAITING_QA", on_fail="RETRY", max_retries=2),
        current_index=0,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# save_queue + load_queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_queue_roundtrip(session):
    q = _make_queue(n_tasks=3)
    await save_queue(session, q)
    await session.commit()

    record = await load_queue(session, q.id)
    assert record is not None
    assert record.id == q.id
    assert record.projectId == "p-test"
    assert record.featureId == "feat-1"
    assert record.status == "running"
    assert record.currentIndex == 0
    assert len(record.tasks) == 3
    # Tasks ordered by sequence
    assert [t.sequence for t in record.tasks] == [0, 1, 2]
    assert [t.issueId for t in record.tasks] == ["issue-0", "issue-1", "issue-2"]
    # Config JSON serialized
    cfg = json.loads(record.config)
    assert cfg["max_retries"] == 2
    assert cfg["on_fail"] == "RETRY"


@pytest.mark.asyncio
async def test_save_queue_update_idempotent(session):
    """Saving the same queue twice should NOT create duplicate task rows."""
    q = _make_queue(n_tasks=2)
    await save_queue(session, q)
    await session.commit()

    # Mutate in-memory and re-save
    q.current_index = 1
    q.tasks[0].status = TaskStatus.COMPLETED
    q.tasks[0].completed_at = datetime.utcnow()
    await save_queue(session, q)
    await session.commit()

    record = await load_queue(session, q.id)
    assert record.currentIndex == 1
    assert len(record.tasks) == 2  # No duplicates
    statuses = {t.sequence: t.status for t in record.tasks}
    assert statuses[0] == "completed"
    assert statuses[1] == "pending"


@pytest.mark.asyncio
async def test_save_queue_terminal_completed_at(session):
    q = _make_queue(status=QueueStatus.COMPLETED, n_tasks=1)
    q.completed_at = datetime.utcnow()
    await save_queue(session, q)
    await session.commit()

    record = await load_queue(session, q.id)
    assert record.status == "completed"
    assert record.completedAt is not None


# ---------------------------------------------------------------------------
# load_active_queue(s)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_active_queue_filters_terminal(session):
    """Only non-terminal queues should be returned."""
    running = _make_queue(status=QueueStatus.RUNNING)
    completed = _make_queue(status=QueueStatus.COMPLETED)
    aborted = _make_queue(status=QueueStatus.ABORTED)
    paused = _make_queue(status=QueueStatus.PAUSED)
    waiting = _make_queue(status=QueueStatus.WAITING_RESET)
    for q in (running, completed, aborted, paused, waiting):
        await save_queue(session, q)
    await session.commit()

    active = await load_active_queues(session)
    active_ids = {q.id for q in active}
    assert running.id in active_ids
    assert paused.id in active_ids
    assert waiting.id in active_ids
    assert completed.id not in active_ids
    assert aborted.id not in active_ids


@pytest.mark.asyncio
async def test_load_active_queue_returns_most_recent(session):
    """When multiple non-terminal exist (post-crash anomaly), pick newest."""
    older = _make_queue()
    newer = _make_queue()
    await save_queue(session, older)
    await session.commit()
    # Force older to look older
    old_record = await load_queue(session, older.id)
    old_record.updatedAt = datetime.utcnow() - timedelta(hours=1)
    await session.commit()

    await save_queue(session, newer)
    await session.commit()

    picked = await load_active_queue(session)
    assert picked is not None
    assert picked.id == newer.id


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_event_appends(session):
    q = _make_queue()
    await save_queue(session, q)
    await session.commit()

    await record_event(session, q.id, "created", {"feature": "CB-1951"})
    await record_event(session, q.id, "task_started", {"index": 0})
    await record_event(session, q.id, "task_completed", {"index": 0, "session_id": "s-1"})
    await session.commit()

    events = await list_events(session, q.id)
    assert len(events) == 3
    # Newest first
    types = [e.type for e in events]
    assert types == ["task_completed", "task_started", "created"]
    payload = json.loads(events[-1].payload)
    assert payload["feature"] == "CB-1951"


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_running_tasks_failed_on_recovery(session):
    q = _make_queue(n_tasks=4, status=QueueStatus.RUNNING)
    # Pretend tasks 1 and 2 were running when backend died
    q.tasks[1].status = TaskStatus.RUNNING
    q.tasks[2].status = TaskStatus.RUNNING
    q.tasks[0].status = TaskStatus.COMPLETED
    q.tasks[3].status = TaskStatus.PENDING
    await save_queue(session, q)
    await session.commit()

    n = await mark_running_tasks_failed_on_recovery(session, q.id)
    await session.commit()
    assert n == 2

    record = await load_queue(session, q.id)
    statuses = {t.sequence: (t.status, t.failureReason) for t in record.tasks}
    assert statuses[0] == ("completed", None)
    assert statuses[1][0] == "failed"
    assert statuses[1][1] == "backend_crash_recovery"
    assert statuses[2][0] == "failed"
    assert statuses[3] == ("pending", None)
    # Recovery should also flip the queue itself to paused/crash_recovery
    assert record.status == "paused"
    assert record.pauseReason == "crash_recovery"


@pytest.mark.asyncio
async def test_mark_running_tasks_recovery_skips_terminal_queues(session):
    """Already-completed/aborted queues should not be flipped back to paused."""
    q = _make_queue(n_tasks=2, status=QueueStatus.COMPLETED)
    q.tasks[0].status = TaskStatus.COMPLETED
    q.tasks[1].status = TaskStatus.RUNNING  # Pathological, but should be cleaned
    await save_queue(session, q)
    await session.commit()

    await mark_running_tasks_failed_on_recovery(session, q.id)
    await session.commit()

    record = await load_queue(session, q.id)
    assert record.status == "completed"  # Unchanged
    assert record.pauseReason is None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_status_counts(session):
    for status in (QueueStatus.RUNNING, QueueStatus.RUNNING, QueueStatus.PAUSED, QueueStatus.COMPLETED):
        await save_queue(session, _make_queue(status=status))
    await session.commit()

    counts = await queue_status_counts(session)
    assert counts.get("running") == 2
    assert counts.get("paused") == 1
    assert counts.get("completed") == 1
