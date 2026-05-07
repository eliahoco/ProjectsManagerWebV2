"""
Auto-resume scheduler + manual-resume hardening tests (CB-1951 E4.x).

Drives ``_schedule_auto_resume`` / ``_cancel_auto_resume`` / ``_fire_auto_resume``
and the resume-preflight guard directly. Uses small in-memory queues; relies
on monkeypatched AsyncSessionLocal for the DB-touching paths.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.database import Base
from models import Issue, Project
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
async def patched_session(monkeypatch):
    """In-memory engine + Project seed; patched into AsyncSessionLocal."""
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
    import services.autopilot_queue_service as svc_mod
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)
    yield Sf
    await engine.dispose()


def _make_queue(qid=None, n_tasks=2, status=QueueStatus.WAITING_RESET):
    qid = qid or str(uuid.uuid4())
    tasks = [
        QueueTask(
            issue_id=f"issue-{i}", issue_key=f"CB-{1000+i}",
            issue_title=f"Task {i}", order=i, status=TaskStatus.PENDING,
        )
        for i in range(n_tasks)
    ]
    q = AutoPilotQueue(
        id=qid, feature_id="feat-1", feature_key="CB-1951",
        project_id="p-test", project_path="/tmp/test",
        status=status, tasks=tasks, config=QueueConfig(),
    )
    q.pause_reason = "token_exhaustion"
    q.reset_time = datetime.utcnow() + timedelta(seconds=2)
    return q


# ---------------------------------------------------------------------------
# Schedule / fire / cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_auto_resume_arms_a_timer(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q

    # Reset 0 seconds in the future + 60s buffer → fires after ~60s. We can't
    # wait that long, so just verify the handle is registered.
    svc._schedule_auto_resume(q.id, datetime.utcnow())
    assert q.id in svc._resume_handles
    handle = svc._resume_handles[q.id]
    assert isinstance(handle, asyncio.Task)
    assert not handle.done()
    # Cancel to clean up
    svc._cancel_auto_resume(q.id)


@pytest.mark.asyncio
async def test_cancel_auto_resume_returns_true_when_handle_exists(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q
    svc._schedule_auto_resume(q.id, datetime.utcnow() + timedelta(hours=1))
    assert svc._cancel_auto_resume(q.id) is True
    assert svc._cancel_auto_resume(q.id) is False  # second call: no handle


@pytest.mark.asyncio
async def test_resume_queue_cancels_pending_timer(patched_session):
    """Manual resume should cancel any pending auto-resume timer."""
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q
    svc._schedule_auto_resume(q.id, datetime.utcnow() + timedelta(hours=1))
    assert q.id in svc._resume_handles

    svc.resume_queue(q.id)
    assert q.id not in svc._resume_handles


@pytest.mark.asyncio
async def test_abort_queue_cancels_pending_timer(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q
    svc._schedule_auto_resume(q.id, datetime.utcnow() + timedelta(hours=1))
    assert q.id in svc._resume_handles

    await svc.abort_queue(q.id)
    assert q.id not in svc._resume_handles


@pytest.mark.asyncio
async def test_fire_auto_resume_skips_if_status_changed(patched_session):
    """If user manually resumed before timer fires, the timer should not
    re-resume. Verified by calling _fire_auto_resume directly with a queue
    in RUNNING state."""
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.RUNNING)
    svc._queues[q.id] = q
    # Should be a no-op
    await svc._fire_auto_resume(q.id)
    # Status should still be RUNNING
    assert q.status == QueueStatus.RUNNING


@pytest.mark.asyncio
async def test_fire_auto_resume_no_op_for_unknown_queue(patched_session):
    svc = AutoPilotQueueService()
    # Doesn't raise
    await svc._fire_auto_resume("nonexistent-id")


# ---------------------------------------------------------------------------
# Manual resume hardening (E4.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_clears_pause_reason_and_reset_time(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.reset_time = datetime.utcnow() + timedelta(hours=1)
    svc._queues[q.id] = q

    assert svc.resume_queue(q.id) is True
    assert q.pause_reason is None
    assert q.reset_time is None


@pytest.mark.asyncio
async def test_resume_refuses_when_no_active_task(patched_session):
    """If current_index >= len(tasks) the queue has no work left."""
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=2, status=QueueStatus.PAUSED)
    q.current_index = 2  # past end
    svc._queues[q.id] = q

    assert svc.resume_queue(q.id) is False
    # Pause flag preserved — no spurious _pause_event.set()
    assert q.status == QueueStatus.PAUSED


@pytest.mark.asyncio
async def test_resume_returns_false_for_non_paused_queue(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.RUNNING)
    svc._queues[q.id] = q
    assert svc.resume_queue(q.id) is False


# ---------------------------------------------------------------------------
# Re-arm on rehydration (E4.2.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rearm_skips_crash_recovery(patched_session):
    """Queues recovered from a crash require manual resume — auto-resume
    must NOT re-arm them."""
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "crash_recovery"
    q.reset_time = datetime.utcnow() + timedelta(hours=1)
    svc._queues[q.id] = q

    rearmed = await svc.rearm_auto_resume_timers()
    assert rearmed == 0
    assert q.id not in svc._resume_handles


@pytest.mark.asyncio
async def test_rearm_token_exhaustion_arms_timer(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.reset_time = datetime.utcnow() + timedelta(hours=1)
    svc._queues[q.id] = q

    rearmed = await svc.rearm_auto_resume_timers()
    assert rearmed == 1
    assert q.id in svc._resume_handles
    svc._cancel_auto_resume(q.id)


@pytest.mark.asyncio
async def test_rearm_skips_when_no_reset_time(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.reset_time = None
    svc._queues[q.id] = q

    rearmed = await svc.rearm_auto_resume_timers()
    assert rearmed == 0


# ---------------------------------------------------------------------------
# Resume preflight (E4.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_skips_already_cwq_issue(patched_session):
    """If the issue is already COMPLETED_WAITING_QA externally, the task
    should be marked SKIPPED with no subprocess launched."""
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q

    Sf = patched_session
    async with Sf() as s:
        s.add(Issue(
            id=q.tasks[0].issue_id, projectId="p-test",
            key="CB-1000", sequence=1000, type="TASK", priority="MEDIUM",
            status="COMPLETED_WAITING_QA", title="Already done",
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    # Need to monkeypatch shutil.which("claude") so it doesn't fail E4.3.1
    import shutil
    orig = shutil.which
    shutil.which = lambda name: "/usr/local/bin/claude" if name == "claude" else orig(name)
    try:
        result = await svc._resume_preflight(q, q.tasks[0])
    finally:
        shutil.which = orig

    assert result == "skip"
    assert q.tasks[0].status == TaskStatus.SKIPPED


@pytest.mark.asyncio
async def test_preflight_skips_missing_issue(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q

    import shutil
    orig = shutil.which
    shutil.which = lambda name: "/usr/local/bin/claude" if name == "claude" else orig(name)
    try:
        result = await svc._resume_preflight(q, q.tasks[0])
    finally:
        shutil.which = orig

    assert result == "skip"
    assert q.tasks[0].status == TaskStatus.SKIPPED


@pytest.mark.asyncio
async def test_preflight_aborts_when_cli_missing(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q

    import shutil
    orig = shutil.which
    shutil.which = lambda name: None  # claude CLI not installed
    try:
        result = await svc._resume_preflight(q, q.tasks[0])
    finally:
        shutil.which = orig

    assert result == "abort"
    assert q.tasks[0].status == TaskStatus.FAILED
    assert "Claude CLI" in (q.tasks[0].error or "")


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_max_attempts(patched_session):
    """After AUTO_RESUME_MAX_ATTEMPTS consecutive auto-resumes, the queue
    must downgrade to manual and stop firing. (E4 review HIGH-1)"""
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.reset_time = datetime.utcnow()
    q.auto_resume_attempts = svc._AUTO_RESUME_MAX_ATTEMPTS  # one short of trip
    svc._queues[q.id] = q

    # Next fire pushes counter to MAX+1 → circuit-breaker trip
    await svc._fire_auto_resume(q.id)
    assert q.auto_resume_attempts == svc._AUTO_RESUME_MAX_ATTEMPTS + 1
    assert q.pause_reason == "manual"
    # Status unchanged — user must manually resume now
    assert q.status == QueueStatus.WAITING_RESET


@pytest.mark.asyncio
async def test_rearm_sanity_checks_stale_reset_time(patched_session):
    """A reset_time more than _REHYDRATION_RESET_WINDOW_HOURS in the past
    should NOT auto-resume — downgrade to manual instead. (SEC MEDIUM-2)"""
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    # 24h in the past — well outside the ±12h sanity window
    q.reset_time = datetime.utcnow() - timedelta(hours=24)
    svc._queues[q.id] = q

    rearmed = await svc.rearm_auto_resume_timers()
    assert rearmed == 0
    assert q.id not in svc._resume_handles
    assert q.pause_reason == "manual"


@pytest.mark.asyncio
async def test_rearm_sanity_checks_far_future_reset_time(patched_session):
    """A reset_time absurdly far in the future is treated as corrupt."""
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.reset_time = datetime.utcnow() + timedelta(hours=24)  # > +12h window
    svc._queues[q.id] = q

    rearmed = await svc.rearm_auto_resume_timers()
    assert rearmed == 0
    assert q.pause_reason == "manual"


@pytest.mark.asyncio
async def test_prune_old_queues_cleans_stale_resume_handles(patched_session):
    """E4 review HIGH-2: defensive — _prune_old_queues should clean up
    any orphaned handles even though _finalize_queue normally cancels."""
    svc = AutoPilotQueueService()
    # Manufacture a terminal queue with an orphan handle (simulating the
    # rare case where _finalize_queue's cancel didn't run)
    q = _make_queue(status=QueueStatus.COMPLETED)
    svc._queues[q.id] = q
    svc._schedule_auto_resume(q.id, datetime.utcnow() + timedelta(hours=1))
    assert q.id in svc._resume_handles
    # Force a prune below max_history so this queue would be removed
    svc._prune_old_queues(max_history=0)
    assert q.id not in svc._queues
    assert q.id not in svc._resume_handles


@pytest.mark.asyncio
async def test_preflight_proceeds_when_issue_active(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue()
    svc._queues[q.id] = q

    Sf = patched_session
    async with Sf() as s:
        s.add(Issue(
            id=q.tasks[0].issue_id, projectId="p-test",
            key="CB-1000", sequence=1000, type="TASK", priority="MEDIUM",
            status="TODO", title="Live task",
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    import shutil
    orig = shutil.which
    shutil.which = lambda name: "/usr/local/bin/claude" if name == "claude" else orig(name)
    try:
        result = await svc._resume_preflight(q, q.tasks[0])
    finally:
        shutil.which = orig

    assert result == "ok"
    assert q.tasks[0].status == TaskStatus.PENDING  # unchanged
