"""
Tests for CB-2756: subprocess PID written to AutoPilotTaskRecord after _execute_task spawn.

Verifies that:
1. set_subprocess_pid is called with the correct pid after session spawn.
2. set_subprocess_pid is called with None to clear pid on completed/failed/stopped/skipped paths.
3. get_task_record_id correctly looks up the DB record id by queue+sequence.
4. PID tracking is best-effort: errors do NOT abort the task.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.autopilot import (
    AutoPilotEvent,
    AutoPilotQueueRecord,
    AutoPilotTaskRecord,
)
from models.database import Base
from models.issue import Project
from utils.autopilot_repository import (
    get_task_record_id,
    save_queue,
    set_subprocess_pid,
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
async def mem_session():
    """In-memory SQLite engine with schema created and patched into AsyncSessionLocal."""
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
    with (
        patch.object(models.database, "AsyncSessionLocal", Sf),
        patch.object(repo_mod, "AsyncSessionLocal", Sf),
        patch.object(svc_mod, "AsyncSessionLocal", Sf),
    ):
        yield Sf

    await engine.dispose()


def _make_queue(n_tasks: int = 2) -> AutoPilotQueue:
    qid = str(uuid.uuid4())
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
        feature_id="feat-1",
        feature_key="CB-2756",
        project_id="p-test",
        project_path="/tmp/test",
        provider="claude_code",
        status=QueueStatus.PENDING,
        tasks=tasks,
        config=QueueConfig(),
    )


async def _persist_queue_record(Sf, queue: AutoPilotQueue) -> AutoPilotQueueRecord:
    """Save queue + tasks to DB and return the record."""
    async with Sf() as s:
        record = await save_queue(s, queue)
        await s.commit()
    return record


# ---------------------------------------------------------------------------
# Tests: get_task_record_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_record_id_returns_correct_id(mem_session):
    """get_task_record_id must return the DB UUID for the given queue+sequence."""
    Sf = mem_session
    queue = _make_queue(n_tasks=3)
    await _persist_queue_record(Sf, queue)

    for seq in range(3):
        task_db_id = await get_task_record_id(queue.id, seq)
        assert task_db_id is not None, f"Expected DB id for sequence={seq}"
        assert isinstance(task_db_id, str)


@pytest.mark.asyncio
async def test_get_task_record_id_returns_none_for_missing(mem_session):
    """get_task_record_id returns None when sequence does not exist."""
    result = await get_task_record_id(str(uuid.uuid4()), 99)
    assert result is None


@pytest.mark.asyncio
async def test_get_task_record_id_distinct_per_sequence(mem_session):
    """Each sequence number returns a distinct DB id."""
    Sf = mem_session
    queue = _make_queue(n_tasks=3)
    await _persist_queue_record(Sf, queue)

    ids = [await get_task_record_id(queue.id, i) for i in range(3)]
    assert len(set(ids)) == 3, "Each task must have a distinct DB id"


# ---------------------------------------------------------------------------
# Tests: set_subprocess_pid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_subprocess_pid_writes_pid(mem_session):
    """set_subprocess_pid persists the PID on the task record."""
    Sf = mem_session
    queue = _make_queue(n_tasks=1)
    await _persist_queue_record(Sf, queue)

    task_db_id = await get_task_record_id(queue.id, 0)
    assert task_db_id is not None

    await set_subprocess_pid(task_db_id, 12345, queue_id=queue.id)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotTaskRecord).where(AutoPilotTaskRecord.id == task_db_id)
        )
        record = result.scalar_one()
        assert record.subprocessPid == 12345


@pytest.mark.asyncio
async def test_set_subprocess_pid_clears_pid(mem_session):
    """set_subprocess_pid with None clears the PID (task finished)."""
    Sf = mem_session
    queue = _make_queue(n_tasks=1)
    await _persist_queue_record(Sf, queue)

    task_db_id = await get_task_record_id(queue.id, 0)
    await set_subprocess_pid(task_db_id, 99999, queue_id=queue.id)
    await set_subprocess_pid(task_db_id, None)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotTaskRecord).where(AutoPilotTaskRecord.id == task_db_id)
        )
        record = result.scalar_one()
        assert record.subprocessPid is None


@pytest.mark.asyncio
async def test_set_subprocess_pid_emits_event(mem_session):
    """set_subprocess_pid emits SUBPROCESS_PID_RECORDED event when pid is non-None."""
    Sf = mem_session
    queue = _make_queue(n_tasks=1)
    await _persist_queue_record(Sf, queue)

    task_db_id = await get_task_record_id(queue.id, 0)

    # Persist queue record first (event has FK to queue)
    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue.id)
        )
        assert result.scalar_one_or_none() is not None

    await set_subprocess_pid(task_db_id, 5555, queue_id=queue.id)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotEvent)
            .where(AutoPilotEvent.queueId == queue.id)
            .where(AutoPilotEvent.type == "SUBPROCESS_PID_RECORDED")
        )
        events = result.scalars().all()
        assert len(events) >= 1


@pytest.mark.asyncio
async def test_set_subprocess_pid_no_event_on_clear(mem_session):
    """set_subprocess_pid with None (clear) does NOT emit an event."""
    Sf = mem_session
    queue = _make_queue(n_tasks=1)
    await _persist_queue_record(Sf, queue)

    task_db_id = await get_task_record_id(queue.id, 0)
    # Set then clear
    await set_subprocess_pid(task_db_id, 1234, queue_id=queue.id)
    await set_subprocess_pid(task_db_id, None)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotEvent)
            .where(AutoPilotEvent.queueId == queue.id)
            .where(AutoPilotEvent.type == "SUBPROCESS_PID_RECORDED")
        )
        events = result.scalars().all()
        # Only 1 event (the initial set), not 2
        assert len(events) == 1


@pytest.mark.asyncio
async def test_set_subprocess_pid_graceful_on_missing_task(mem_session):
    """set_subprocess_pid with unknown task_id logs and returns without error."""
    # Should not raise — PID tracking is best-effort
    await set_subprocess_pid("nonexistent-id", 9999)


# ---------------------------------------------------------------------------
# Tests: PID wiring call site (via mock patching)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_task_calls_set_subprocess_pid_after_spawn(mem_session):
    """_execute_task must call set_subprocess_pid with the real PID after spawn."""
    Sf = mem_session
    queue = _make_queue(n_tasks=1)
    queue.status = QueueStatus.RUNNING
    await _persist_queue_record(Sf, queue)

    task = queue.tasks[0]
    task.status = TaskStatus.RUNNING

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    # Mock a session with process.pid=42
    mock_process = MagicMock()
    mock_process.pid = 42

    mock_session = MagicMock()
    mock_session.id = "sess-1"
    mock_session.status.value = "running"
    from services.terminal_service import ExecutionStatus
    mock_session.status = ExecutionStatus.COMPLETED
    mock_session.process = mock_process
    mock_session.error = None

    pid_calls: list = []

    async def _fake_set_pid(task_id, pid, queue_id=None):
        pid_calls.append((task_id, pid, queue_id))

    with (
        patch("services.autopilot_queue_service.set_subprocess_pid", side_effect=_fake_set_pid),
        patch("services.autopilot_queue_service.get_task_record_id", return_value="db-task-id-0"),
        patch("services.autopilot_queue_service.terminal_service") as mock_ts,
        patch.object(svc, "_resume_preflight", return_value="ok"),
        patch.object(svc, "_poll_session", return_value="completed"),
        patch.object(svc, "_persist", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.AsyncSessionLocal", Sf),
    ):
        mock_ts.start_execution = AsyncMock(return_value=mock_session)
        mock_ts.get_session = MagicMock(return_value=mock_session)

        from models.issue import Issue
        async with Sf() as db:
            db.add(Issue(
                id="issue-0", key="CB-1000", title="Task 0",
                type="TASK", status="TODO", sequence=1,
                projectId="p-test", reporter="AI",
                createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
            ))
            await db.commit()

        with patch("services.autopilot_queue_service.build_execution_context", new_callable=AsyncMock, return_value="prompt"):
            with patch("services.autopilot_queue_service.get_parent_chain", new_callable=AsyncMock, return_value=[]):
                with patch("services.autopilot_queue_service.cascade_in_progress_to_parents", new_callable=AsyncMock):
                    await svc._execute_task(queue, task)

    set_pid_calls = [c for c in pid_calls if c[1] is not None]
    assert len(set_pid_calls) >= 1, "set_subprocess_pid should be called with PID after spawn"
    assert set_pid_calls[0][1] == 42, "PID should match session.process.pid"


@pytest.mark.asyncio
async def test_execute_task_clears_pid_on_completion(mem_session):
    """_execute_task must call set_subprocess_pid(None) when task finishes."""
    Sf = mem_session
    queue = _make_queue(n_tasks=1)
    queue.status = QueueStatus.RUNNING
    await _persist_queue_record(Sf, queue)

    task = queue.tasks[0]
    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    mock_process = MagicMock()
    mock_process.pid = 999

    mock_session = MagicMock()
    mock_session.id = "sess-2"
    from services.terminal_service import ExecutionStatus
    mock_session.status = ExecutionStatus.COMPLETED
    mock_session.process = mock_process
    mock_session.error = None

    pid_calls: list = []

    async def _fake_set_pid(task_id, pid, queue_id=None):
        pid_calls.append((task_id, pid, queue_id))

    from models.issue import Issue
    async with Sf() as db:
        db.add(Issue(
            id="issue-0", key="CB-1000", title="Task 0",
            type="TASK", status="TODO", sequence=2,
            projectId="p-test", reporter="AI",
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        ))
        await db.commit()

    with (
        patch("services.autopilot_queue_service.set_subprocess_pid", side_effect=_fake_set_pid),
        patch("services.autopilot_queue_service.get_task_record_id", return_value="db-task-id-0"),
        patch("services.autopilot_queue_service.terminal_service") as mock_ts,
        patch.object(svc, "_resume_preflight", return_value="ok"),
        patch.object(svc, "_poll_session", return_value="completed"),
        patch.object(svc, "_persist", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.AsyncSessionLocal", Sf),
    ):
        mock_ts.start_execution = AsyncMock(return_value=mock_session)
        mock_ts.get_session = MagicMock(return_value=mock_session)

        with patch("services.autopilot_queue_service.build_execution_context", new_callable=AsyncMock, return_value="prompt"):
            with patch("services.autopilot_queue_service.get_parent_chain", new_callable=AsyncMock, return_value=[]):
                with patch("services.autopilot_queue_service.cascade_in_progress_to_parents", new_callable=AsyncMock):
                    await svc._execute_task(queue, task)

    clear_calls = [c for c in pid_calls if c[1] is None]
    assert len(clear_calls) >= 1, "set_subprocess_pid(None) must be called to clear PID on finish"


@pytest.mark.asyncio
async def test_execute_task_pid_tracking_fails_gracefully(mem_session):
    """PID tracking errors must not abort the task execution."""
    Sf = mem_session
    queue = _make_queue(n_tasks=1)
    queue.status = QueueStatus.RUNNING
    await _persist_queue_record(Sf, queue)

    task = queue.tasks[0]
    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    mock_process = MagicMock()
    mock_process.pid = 1234

    mock_session = MagicMock()
    mock_session.id = "sess-3"
    from services.terminal_service import ExecutionStatus
    mock_session.status = ExecutionStatus.COMPLETED
    mock_session.process = mock_process
    mock_session.error = None

    async def _exploding_set_pid(*args, **kwargs):
        raise RuntimeError("DB exploded")

    from models.issue import Issue
    async with Sf() as db:
        db.add(Issue(
            id="issue-0", key="CB-1000", title="Task 0",
            type="TASK", status="TODO", sequence=3,
            projectId="p-test", reporter="AI",
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        ))
        await db.commit()

    with (
        patch("services.autopilot_queue_service.set_subprocess_pid", side_effect=_exploding_set_pid),
        patch("services.autopilot_queue_service.get_task_record_id", return_value="db-task-id-0"),
        patch("services.autopilot_queue_service.terminal_service") as mock_ts,
        patch.object(svc, "_resume_preflight", return_value="ok"),
        patch.object(svc, "_poll_session", return_value="completed"),
        patch.object(svc, "_persist", new_callable=AsyncMock),
        patch("services.autopilot_queue_service.AsyncSessionLocal", Sf),
    ):
        mock_ts.start_execution = AsyncMock(return_value=mock_session)
        mock_ts.get_session = MagicMock(return_value=mock_session)

        with patch("services.autopilot_queue_service.build_execution_context", new_callable=AsyncMock, return_value="prompt"):
            with patch("services.autopilot_queue_service.get_parent_chain", new_callable=AsyncMock, return_value=[]):
                with patch("services.autopilot_queue_service.cascade_in_progress_to_parents", new_callable=AsyncMock):
                    # Must not raise
                    result = await svc._execute_task(queue, task)

    assert result == "completed", "PID tracking failure must not abort task execution"
