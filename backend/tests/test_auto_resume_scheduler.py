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
    import utils.autopilot_repository as repo_mod
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)
    # CB-2798: also patch the repository module so transition_state and
    # checkpoint write to the same in-memory DB that save_queue uses.
    monkeypatch.setattr(repo_mod, "AsyncSessionLocal", Sf)
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

    await svc.resume_queue(q.id)
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

    assert await svc.resume_queue(q.id) is True
    assert q.pause_reason is None
    assert q.reset_time is None


@pytest.mark.asyncio
async def test_resume_refuses_when_no_active_task(patched_session):
    """If current_index >= len(tasks) AND no pending tasks remain, refuse."""
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=2, status=QueueStatus.PAUSED)
    q.current_index = 2  # past end
    # Mark all tasks completed — genuinely nothing left.
    for t in q.tasks:
        t.status = TaskStatus.COMPLETED
    svc._queues[q.id] = q

    assert await svc.resume_queue(q.id) is False
    # Pause flag preserved — no spurious _pause_event.set()
    assert q.status == QueueStatus.PAUSED


@pytest.mark.asyncio
async def test_resume_returns_false_for_non_paused_queue(patched_session):
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.RUNNING)
    svc._queues[q.id] = q
    assert await svc.resume_queue(q.id) is False


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
    must downgrade to manual and stop firing. (E4 review HIGH-1)

    CB-2794 fix: the cap check now uses >= so the breaker trips exactly when
    attempts == MAX (not MAX+1).  The counter must NOT be incremented past MAX
    when the breaker fires.

    CB-2795 fix: status must transition WAITING_RESET → PAUSED and
    pause_reason must be 'manual_circuit_breaker' (not just 'manual').
    """
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.reset_time = datetime.utcnow()
    q.auto_resume_attempts = svc._AUTO_RESUME_MAX_ATTEMPTS  # already at cap
    svc._queues[q.id] = q

    # CB-2794: _fire_auto_resume pre-flight sees attempts >= MAX and trips without
    # calling resume_queue, so the counter must stay at MAX (not MAX+1).
    await svc._fire_auto_resume(q.id)
    assert q.auto_resume_attempts == svc._AUTO_RESUME_MAX_ATTEMPTS, (
        f"CB-2794: counter must not exceed MAX when breaker trips; "
        f"expected {svc._AUTO_RESUME_MAX_ATTEMPTS}, got {q.auto_resume_attempts}"
    )
    # CB-2795: status must be PAUSED (terminal-for-auto-resume), not WAITING_RESET.
    assert q.status == QueueStatus.PAUSED, (
        f"CB-2795: status must be PAUSED after breaker trips, got {q.status}"
    )
    assert q.pause_reason == svc._CIRCUIT_BREAKER_PAUSE_REASON, (
        f"CB-2795: pause_reason must be {svc._CIRCUIT_BREAKER_PAUSE_REASON!r}, "
        f"got {q.pause_reason!r}"
    )


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


# ---------------------------------------------------------------------------
# CB-2794 — increment ordering fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_increment_happens_after_cap_check(patched_session):
    """CB-2794: When auto_resume_attempts == MAX, resume_queue must trip the
    circuit breaker WITHOUT incrementing the counter past MAX.

    Before the fix: increment happened first, so the counter reached MAX+1
    before the cap check. This meant:
      - The cap was functionally MAX+1 (off-by-one — 4 attempts instead of 3).
      - The counter kept growing on each breaker trip across restarts.

    After the fix: the >= check fires before the increment, so:
      - The counter stays at MAX (3) when the breaker trips.
      - resume_queue returns False (breaker tripped).
      - pause_reason is set to "manual".
    """
    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.auto_resume_attempts = svc._AUTO_RESUME_MAX_ATTEMPTS  # == 3

    svc._queues[q.id] = q
    svc._persist_async = lambda *a, **kw: None  # suppress persistence

    result = await svc.resume_queue(q.id, _is_auto_resume=True)

    assert result is False, (
        "CB-2794: resume_queue must return False when attempts == MAX"
    )
    assert q.auto_resume_attempts == svc._AUTO_RESUME_MAX_ATTEMPTS, (
        f"CB-2794: counter must stay at MAX={svc._AUTO_RESUME_MAX_ATTEMPTS} "
        f"when breaker trips, got {q.auto_resume_attempts}"
    )
    # CB-2795: pause_reason is now 'manual_circuit_breaker' (not just 'manual')
    # and status must be PAUSED so the tick/fire predicates stop matching.
    assert q.pause_reason == svc._CIRCUIT_BREAKER_PAUSE_REASON, (
        f"CB-2795: pause_reason must be {svc._CIRCUIT_BREAKER_PAUSE_REASON!r} "
        f"after breaker trips, got {q.pause_reason!r}"
    )
    assert q.status == QueueStatus.PAUSED, (
        f"CB-2795: status must be PAUSED after breaker trips, got {q.status}"
    )


# ---------------------------------------------------------------------------
# CB-2795 — Circuit-breaker is a terminal state transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_trip_is_terminal(patched_session):
    """CB-2795: When the breaker trips via the recovery tick, status must
    transition WAITING_RESET → PAUSED and subsequent ticks must not emit
    additional events.

    Simulates 4 calls to _recovery_tick_once with attempts already at MAX.
    Asserts:
      - queue.status is PAUSED after the first tick.
      - queue.pause_reason is 'manual_circuit_breaker'.
      - Exactly ONE auto_resume_circuit_breaker_tripped event is persisted.
      - Subsequent ticks do NOT emit additional events (idempotent).
    """
    from sqlalchemy import select as sa_select
    from models.autopilot import AutoPilotEvent

    Sf = patched_session

    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    # reset_time in the past so the lookahead window includes this queue.
    q.reset_time = datetime.utcnow() - timedelta(seconds=5)
    q.auto_resume_attempts = svc._AUTO_RESUME_MAX_ATTEMPTS  # already at cap

    # Persist the queue record so transition_state can find it.
    async with Sf() as s:
        await save_queue(s, q)
        await s.commit()

    svc._queues[q.id] = q

    # Run the tick four times — simulating 4 minutes of polling at 60-second cadence.
    for _ in range(4):
        await svc._recovery_tick_once()
        # Give the event loop a turn so any ensure_future tasks settle.
        await asyncio.sleep(0)

    # In-memory status must be PAUSED immediately after the first tick.
    assert q.status == QueueStatus.PAUSED, (
        f"CB-2795: expected PAUSED, got {q.status}"
    )
    assert q.pause_reason == svc._CIRCUIT_BREAKER_PAUSE_REASON, (
        f"CB-2795: expected {svc._CIRCUIT_BREAKER_PAUSE_REASON!r}, got {q.pause_reason!r}"
    )

    # Allow any background ensure_future tasks to finish writing the event.
    await asyncio.sleep(0.05)

    # Exactly ONE circuit_breaker_tripped event must be persisted.
    async with Sf() as s:
        result = await s.execute(
            sa_select(AutoPilotEvent).where(
                AutoPilotEvent.queueId == q.id,
                AutoPilotEvent.type == "auto_resume_circuit_breaker_tripped",
            )
        )
        events = list(result.scalars().all())

    assert len(events) == 1, (
        f"CB-2795: expected exactly 1 circuit_breaker_tripped event, got {len(events)}"
    )


@pytest.mark.asyncio
async def test_circuit_breaker_trip_cancels_active_timer(patched_session):
    """CB-2795 H2 fix: exercise the self-cancel path by letting _runner call
    _fire_auto_resume from *inside* the scheduled task, which is the production
    code path. Calling _fire_auto_resume directly from the test task is a
    different task and misses the asyncio.current_task() == handle guard.

    Steps:
      1. Arm a timer set to fire in the very near future (reset_time = now-5s
         so the 60s buffer is skipped; we patch _TIMER_EXTRA_SECONDS_BUFFER=0).
      2. Wait for the _runner task to complete naturally.
      3. Assert: status PAUSED, pause_reason == _CIRCUIT_BREAKER_PAUSE_REASON,
         _resume_handles entry is gone, exactly one event persisted.
    """
    from sqlalchemy import select as sa_select
    from models.autopilot import AutoPilotEvent

    Sf = patched_session

    svc = AutoPilotQueueService()
    # Zero out the extra buffer so the timer fires almost immediately.
    svc._AUTO_RESUME_BUFFER_SECONDS = 0

    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    # reset_time in the past so delay = max(0, ...) = 0 seconds.
    q.reset_time = datetime.utcnow() - timedelta(seconds=5)
    q.auto_resume_attempts = svc._AUTO_RESUME_MAX_ATTEMPTS

    async with Sf() as s:
        await save_queue(s, q)
        await s.commit()

    svc._queues[q.id] = q

    # Arm the real timer — _runner will sleep(~0) then call _fire_auto_resume.
    svc._schedule_auto_resume(q.id, q.reset_time)
    runner_task = svc._resume_handles[q.id]
    assert runner_task is not None, "Timer task must be registered"

    # Wait for _runner to complete (it fires immediately at delay≈0).
    try:
        await asyncio.wait_for(asyncio.shield(runner_task), timeout=2.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass  # task may have been cancelled by its own self-cancel path

    # Allow any trailing async work (persist, etc.) to flush.
    await asyncio.sleep(0.1)

    # _runner's finally block (or the self-cancel pop) must have cleared the handle.
    assert q.id not in svc._resume_handles, (
        "CB-2795 H2: _resume_handles entry must be removed after _runner exits"
    )
    # In-memory mirror must be consistent.
    assert q.status == QueueStatus.PAUSED, (
        f"CB-2795 H2: expected PAUSED, got {q.status}"
    )
    assert q.pause_reason == svc._CIRCUIT_BREAKER_PAUSE_REASON, (
        f"CB-2795 H2: expected {svc._CIRCUIT_BREAKER_PAUSE_REASON!r}, got {q.pause_reason!r}"
    )
    # Exactly one circuit_breaker_tripped event persisted.
    async with Sf() as s:
        result = await s.execute(
            sa_select(AutoPilotEvent).where(
                AutoPilotEvent.queueId == q.id,
                AutoPilotEvent.type == "auto_resume_circuit_breaker_tripped",
            )
        )
        events = list(result.scalars().all())
    assert len(events) == 1, (
        f"CB-2795 H2: expected exactly 1 circuit_breaker_tripped event, got {len(events)}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_point", [
    "_fire_auto_resume",
    "_recovery_tick_once",
    "resume_queue_auto",
])
async def test_circuit_breaker_idempotent(patched_session, entry_point):
    """CB-2795 M3: Idempotency across all three entry points that can trip the
    circuit breaker:
      - _fire_auto_resume (timer path)
      - _recovery_tick_once (tick path)
      - resume_queue(_is_auto_resume=True) (manual-triggered auto path)

    For each: invoke twice; assert exactly ONE persisted event total AND
    queue.status stays PAUSED after the second invocation.

    The early-exit guards (status != WAITING_RESET, pause_reason already set)
    ensure no double-emission regardless of which path trips the breaker first.
    """
    from sqlalchemy import select as sa_select
    from models.autopilot import AutoPilotEvent

    Sf = patched_session

    svc = AutoPilotQueueService()
    q = _make_queue(status=QueueStatus.WAITING_RESET)
    q.pause_reason = "token_exhaustion"
    q.reset_time = datetime.utcnow() - timedelta(seconds=5)
    q.auto_resume_attempts = svc._AUTO_RESUME_MAX_ATTEMPTS

    # All three entry points need the queue persisted so transition_state and
    # _persist can locate the record in the in-memory SQLite DB.
    async with Sf() as s:
        await save_queue(s, q)
        await s.commit()

    svc._queues[q.id] = q

    async def invoke_once():
        if entry_point == "_fire_auto_resume":
            await svc._fire_auto_resume(q.id)
        elif entry_point == "_recovery_tick_once":
            await svc._recovery_tick_once()
        else:  # resume_queue_auto
            # _is_auto_resume=True hits the circuit-breaker branch inside
            # resume_queue; the queue record is already in DB so transition_state
            # and _persist_async can write the event.
            await svc.resume_queue(q.id, _is_auto_resume=True)

    # First invocation — must trip the breaker.
    await invoke_once()
    assert q.status == QueueStatus.PAUSED, (
        f"[{entry_point}] First trip must set PAUSED, got {q.status}"
    )

    # Second invocation — status is now PAUSED; early-exit guards must prevent
    # any additional state mutation or event emission.
    await invoke_once()
    assert q.status == QueueStatus.PAUSED, (
        f"[{entry_point}] Second trip must leave status PAUSED"
    )

    # Allow async persist tasks to flush.
    await asyncio.sleep(0.1)

    # Exactly 1 circuit_breaker_tripped event — not 2.
    async with Sf() as s:
        result = await s.execute(
            sa_select(AutoPilotEvent).where(
                AutoPilotEvent.queueId == q.id,
                AutoPilotEvent.type == "auto_resume_circuit_breaker_tripped",
            )
        )
        events = list(result.scalars().all())

    assert len(events) == 1, (
        f"CB-2795 M3 [{entry_point}]: expected 1 event, got {len(events)}"
    )
