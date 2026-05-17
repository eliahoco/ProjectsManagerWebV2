"""
CB-2745 regression tests — all 6 queue-control methods must work on DB-only queues.

Bug class: pause_queue / resume_queue / skip_current / abort_queue /
wait_for_reset / switch_model all used self._queues.get(queue_id) (in-memory
only). When the queue was paused and the backend restarted (or the queue was
never rehydrated to memory), every one returned None and the operation silently
400/404'd.

Fix: every method now calls await self.get_or_load_queue(queue_id) which checks
memory first, then falls back to loading from the DB.

Each test below:
  1. Persists a paused queue to the DB (with appropriate task state).
  2. Creates a fresh service instance (empty _queues — no in-memory state).
  3. Patches AsyncSessionLocal so the service sees the in-memory test DB.
  4. Calls the method under test.
  5. Asserts:
     (a) The method did NOT return False/None due to queue not found.
     (b) The queue is now in memory (get_or_load_queue cached it).
     (c) DB state changed as expected (where applicable).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session_factory(monkeypatch):
    """In-memory SQLite + project seed; patches AsyncSessionLocal everywhere."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Sf = async_sessionmaker(engine, expire_on_commit=False)

    async with Sf() as s:
        s.add(Project(
            id="p-cb2745",
            name="cb2745-test-project",
            path="/tmp/cb2745-test",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    import models.database
    import services.autopilot_queue_service as svc_mod

    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)

    yield Sf
    await engine.dispose()


def _paused_queue(
    n_tasks: int = 4,
    status: QueueStatus = QueueStatus.PAUSED,
    pause_reason: str = "crash_recovery",
    task_status: TaskStatus = TaskStatus.PENDING,
    current_index: int = 0,
) -> AutoPilotQueue:
    """Build an AutoPilotQueue suitable for persisting to DB as a paused queue."""
    qid = str(uuid.uuid4())
    tasks = [
        QueueTask(
            issue_id=f"issue-cb2745-{i}",
            issue_key=f"CB-{9000 + i}",
            issue_title=f"CB-2745 Task {i}",
            order=i,
            status=task_status,
        )
        for i in range(n_tasks)
    ]
    q = AutoPilotQueue(
        id=qid,
        feature_id="feat-cb2745",
        feature_key="CB-2745",
        project_id="p-cb2745",
        project_path="/tmp/cb2745-test",
        status=status,
        tasks=tasks,
        config=QueueConfig(),
        created_at=datetime.utcnow(),
        current_index=current_index,
    )
    q.pause_reason = pause_reason
    return q


async def _persist(Sf, queue: AutoPilotQueue) -> None:
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()


# ---------------------------------------------------------------------------
# 1. pause_queue — queue in RUNNING state in DB (simulate mid-run crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2745_pause_queue_finds_db_only_running_queue(db_session_factory):
    """CB-2745: pause_queue must work on a DB-only RUNNING queue.

    Before the fix, self._queues.get() returned None and pause_queue returned
    False, causing 400 "Cannot pause — queue is not running".
    """
    Sf = db_session_factory

    # A RUNNING queue in the DB (not PAUSED — pause only works on RUNNING).
    queue = _paused_queue(
        n_tasks=3,
        status=QueueStatus.RUNNING,
        pause_reason=None,
        task_status=TaskStatus.PENDING,
        current_index=0,
    )
    queue.pause_reason = None
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()

    # Pre-condition: not in memory.
    assert svc.get_queue(queue.id) is None, (
        "Pre-condition: queue must NOT be in memory before pause_queue"
    )

    # CB-2745 fix: pause_queue now uses get_or_load_queue.
    result = await svc.pause_queue(queue.id)

    assert result is True, (
        "CB-2745: pause_queue must return True for a DB-only RUNNING queue"
    )
    # Queue must now be in memory.
    loaded = svc.get_queue(queue.id)
    assert loaded is not None, "Queue must be cached in memory after pause_queue"
    assert loaded.status == QueueStatus.PAUSED, (
        "Queue status must be PAUSED after pause_queue"
    )


# ---------------------------------------------------------------------------
# 2. resume_queue — paused/crash_recovery queue in DB (the original symptom)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2745_resume_queue_finds_db_only_paused_queue(db_session_factory):
    """CB-2745: resume_queue must NOT return False for a DB-only paused queue.

    This is the exact symptom reported: queue 99ccf3aa exists in DB as
    paused/crash_recovery with 4 pending tasks, but self._queues.get() returns
    None, so resume_queue returns False → API returns 400.
    """
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=4,
        status=QueueStatus.PAUSED,
        pause_reason="crash_recovery",
        task_status=TaskStatus.PENDING,
        current_index=0,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()

    # Pre-condition: not in memory.
    assert svc.get_queue(queue.id) is None, (
        "Pre-condition: queue must NOT be in memory before resume_queue"
    )

    result = await svc.resume_queue(queue.id)

    assert result is True, (
        "CB-2745: resume_queue must return True for a DB-only paused/crash_recovery queue — "
        "this is the exact symptom that was 400-ing: "
        "'Cannot resume — queue is not paused or does not exist'"
    )
    # Queue must now be cached in memory.
    loaded = svc.get_queue(queue.id)
    assert loaded is not None, "Queue must be cached in memory after resume_queue"
    # pause_reason cleared on successful resume
    assert loaded.pause_reason is None


@pytest.mark.asyncio
async def test_cb2745_resume_queue_waiting_reset_db_only(db_session_factory):
    """CB-2745: resume_queue also works for WAITING_RESET status (token-exhaustion path)."""
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=2,
        status=QueueStatus.WAITING_RESET,
        pause_reason="token_exhaustion",
        task_status=TaskStatus.PENDING,
        current_index=0,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    assert svc.get_queue(queue.id) is None

    result = await svc.resume_queue(queue.id)

    assert result is True, "resume_queue must work for WAITING_RESET DB-only queue"
    loaded = svc.get_queue(queue.id)
    assert loaded is not None
    assert loaded.pause_reason is None
    assert loaded.reset_time is None


@pytest.mark.asyncio
async def test_cb2745_resume_queue_returns_false_for_unknown_id(db_session_factory):
    """CB-2745: resume_queue must still return False for a genuinely unknown queue_id."""
    svc = AutoPilotQueueService()
    result = await svc.resume_queue("completely-unknown-queue-id-99999")
    assert result is False, "resume_queue must return False for unknown queue_id"


# ---------------------------------------------------------------------------
# 3. skip_current — only valid on RUNNING queues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2745_skip_current_finds_db_only_running_queue(db_session_factory):
    """CB-2745: skip_current must work on a DB-only RUNNING queue."""
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=3,
        status=QueueStatus.RUNNING,
        pause_reason=None,
        task_status=TaskStatus.PENDING,
        current_index=0,
    )
    queue.pause_reason = None
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    assert svc.get_queue(queue.id) is None

    result = await svc.skip_current(queue.id)

    assert result is True, (
        "CB-2745: skip_current must return True for a DB-only RUNNING queue"
    )
    loaded = svc.get_queue(queue.id)
    assert loaded is not None, "Queue must be cached after skip_current"
    assert loaded._skip_flag is True, "_skip_flag must be set after skip_current"


@pytest.mark.asyncio
async def test_cb2745_skip_current_returns_false_for_paused_queue(db_session_factory):
    """CB-2745: skip_current must return False when queue is PAUSED (not RUNNING)."""
    Sf = db_session_factory

    # skip_current only works on RUNNING queues, not paused ones
    queue = _paused_queue(
        n_tasks=2,
        status=QueueStatus.PAUSED,
        task_status=TaskStatus.PENDING,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    result = await svc.skip_current(queue.id)

    # Should return False because status != RUNNING, not because queue not found
    assert result is False, (
        "skip_current must return False for a PAUSED queue "
        "(but must NOT 404 — it must find the queue first)"
    )
    # The queue should still have been loaded into memory
    loaded = svc.get_queue(queue.id)
    assert loaded is not None, (
        "Queue must be cached in memory even if skip_current returned False — "
        "it found the queue but correctly refused because it's not RUNNING"
    )


# ---------------------------------------------------------------------------
# 4. abort_queue — can abort from any non-terminal state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2745_abort_queue_finds_db_only_paused_queue(db_session_factory):
    """CB-2745: abort_queue must work on a DB-only paused queue."""
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=3,
        status=QueueStatus.PAUSED,
        pause_reason="crash_recovery",
        task_status=TaskStatus.PENDING,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    assert svc.get_queue(queue.id) is None

    result = await svc.abort_queue(queue.id, action="mark_skipped")

    assert result is True, (
        "CB-2745: abort_queue must return True for a DB-only paused queue"
    )
    loaded = svc.get_queue(queue.id)
    assert loaded is not None, "Queue must be cached after abort_queue"
    assert loaded.status == QueueStatus.ABORTED, "Queue status must be ABORTED"
    # All pending tasks marked skipped
    assert all(
        t.status == TaskStatus.SKIPPED for t in loaded.tasks
    ), "All pending tasks must be SKIPPED after abort with mark_skipped"


@pytest.mark.asyncio
async def test_cb2745_abort_queue_mark_failed_action(db_session_factory):
    """CB-2745: abort_queue with mark_failed marks pending tasks as FAILED."""
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=2,
        status=QueueStatus.PAUSED,
        task_status=TaskStatus.PENDING,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    result = await svc.abort_queue(queue.id, action="mark_failed")

    assert result is True
    loaded = svc.get_queue(queue.id)
    assert loaded is not None
    assert all(t.status == TaskStatus.FAILED for t in loaded.tasks)
    assert all(t.error == "Queue aborted" for t in loaded.tasks)


@pytest.mark.asyncio
async def test_cb2745_abort_queue_returns_false_for_unknown_id(db_session_factory):
    """CB-2745: abort_queue must return False for a genuinely unknown queue_id."""
    svc = AutoPilotQueueService()
    result = await svc.abort_queue("unknown-queue-id-cb2745", action="leave")
    assert result is False


# ---------------------------------------------------------------------------
# 5. wait_for_reset — schedules auto-resume timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2745_wait_for_reset_finds_db_only_paused_queue(db_session_factory):
    """CB-2745: wait_for_reset must find and schedule for a DB-only paused queue.

    Before the fix, self._queues.get() returned None and wait_for_reset
    returned immediately without scheduling anything.
    """
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=2,
        status=QueueStatus.PAUSED,
        pause_reason="token_exhaustion",
        task_status=TaskStatus.PENDING,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    assert svc.get_queue(queue.id) is None

    # Patch _schedule_auto_resume so we don't actually wait 60+ seconds.
    scheduled_ids: list[str] = []

    def _fake_schedule(qid: str, reset_time: datetime) -> None:
        scheduled_ids.append(qid)

    svc._schedule_auto_resume = _fake_schedule  # type: ignore[method-assign]

    # wait_for_reset is async; it calls _schedule_auto_resume synchronously
    # then awaits the handle — since we replaced the handle we call it directly.
    await svc.wait_for_reset(queue.id, reset_time_str=None)

    # The queue must have been loaded from DB.
    loaded = svc.get_queue(queue.id)
    assert loaded is not None, (
        "CB-2745: wait_for_reset must load and cache the DB-only queue"
    )
    # _schedule_auto_resume was called (not short-circuited by None queue)
    assert queue.id in scheduled_ids, (
        "CB-2745: wait_for_reset must call _schedule_auto_resume after loading queue from DB"
    )


@pytest.mark.asyncio
async def test_cb2745_wait_for_reset_no_op_for_unknown_id(db_session_factory):
    """CB-2745: wait_for_reset must be a no-op (not raise) for unknown queue_id."""
    svc = AutoPilotQueueService()
    # Must not raise
    await svc.wait_for_reset("unknown-queue-id-cb2745", reset_time_str=None)
    # No queue cached
    assert svc.get_queue("unknown-queue-id-cb2745") is None


# ---------------------------------------------------------------------------
# 6. switch_model — switch provider and resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2745_switch_model_finds_db_only_paused_queue(db_session_factory):
    """CB-2745: switch_model must work on a DB-only paused queue.

    Before the fix, self._queues.get() returned None and switch_model returned
    False, causing 404 "Queue not found".
    """
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=2,
        status=QueueStatus.PAUSED,
        pause_reason="token_exhaustion",
        task_status=TaskStatus.PENDING,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    assert svc.get_queue(queue.id) is None

    result = await svc.switch_model(queue.id, provider="anthropic", model="claude-opus-4-5")

    assert result is True, (
        "CB-2745: switch_model must return True for a DB-only paused queue"
    )
    loaded = svc.get_queue(queue.id)
    assert loaded is not None, "Queue must be cached after switch_model"
    assert loaded.provider == "anthropic"
    assert loaded.model == "claude-opus-4-5"


@pytest.mark.asyncio
async def test_cb2745_switch_model_returns_false_for_unknown_id(db_session_factory):
    """CB-2745: switch_model must return False for a genuinely unknown queue_id."""
    svc = AutoPilotQueueService()
    result = await svc.switch_model("unknown-queue-id-cb2745", provider="anthropic")
    assert result is False


@pytest.mark.asyncio
async def test_cb2745_switch_model_waiting_reset_db_only(db_session_factory):
    """CB-2745: switch_model works for WAITING_RESET (token-exhaustion) DB-only queue."""
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=2,
        status=QueueStatus.WAITING_RESET,
        pause_reason="token_exhaustion",
        task_status=TaskStatus.PENDING,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    result = await svc.switch_model(queue.id, provider="local", model="llama3")

    assert result is True
    loaded = svc.get_queue(queue.id)
    assert loaded is not None
    assert loaded.provider == "local"
    assert loaded.model == "llama3"


# ---------------------------------------------------------------------------
# 7. Cross-method regression: load once, operate twice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2745_multiple_ops_on_same_db_only_queue(db_session_factory):
    """CB-2745: loading a DB-only queue caches it so subsequent ops are fast.

    Simulate: abort fails (queue is paused), then switch_model updates it —
    verifies the cache is populated after the first operation and the second
    op uses the cached object.
    """
    Sf = db_session_factory

    queue = _paused_queue(
        n_tasks=2,
        status=QueueStatus.PAUSED,
        task_status=TaskStatus.PENDING,
    )
    await _persist(Sf, queue)

    svc = AutoPilotQueueService()
    assert svc.get_queue(queue.id) is None

    # First op: abort — loads from DB and caches
    result1 = await svc.abort_queue(queue.id, action="leave")
    assert result1 is True

    # The queue is now in memory and ABORTED
    loaded = svc.get_queue(queue.id)
    assert loaded is not None
    assert loaded.status == QueueStatus.ABORTED

    # Second op: switch_model — uses cached object (no DB hit needed)
    # (switch_model calls get_or_load_queue which fast-paths on _queues)
    result2 = await svc.switch_model(queue.id, provider="local", model="test-model")
    # switch_model returns True even for ABORTED (it just updates provider/model)
    assert result2 is True
    loaded2 = svc.get_queue(queue.id)
    assert loaded2 is loaded, "Second op must use cached object, not reload from DB"
    assert loaded2.provider == "local"
