"""CB-2792: systemic-failure heuristic tests.

When `detect_exhaustion_from_session()` returns None (silent claude CLI exit
on credit/quota exhaustion), the queue must NOT cascade through every task.
Instead, after N identical failures within W seconds, treat as systemic and
pause the queue with `unknown_systemic` category + auto-resume timer.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.autopilot_queue_service import (
    AutoPilotQueue,
    _is_systemic_failure,
    _normalize_error_for_systemic,
    _SYSTEMIC_FAILURE_THRESHOLD,
    _SYSTEMIC_FAILURE_WINDOW_SECONDS,
)


def _make_queue() -> AutoPilotQueue:
    """Bare queue object (heuristic only needs `recent_failures`)."""
    return AutoPilotQueue(
        id="test-queue",
        feature_id="f-1",
        feature_key="TEST-1",
        project_id="p-1",
        project_path="/tmp",
        provider="claude_code",
        tasks=[],
        config={},
    )


# ────────────────────────────────────────────────────────────────────────
# Pure heuristic logic
# ────────────────────────────────────────────────────────────────────────


def test_threshold_not_met_returns_false():
    q = _make_queue()
    err = "Process exited with code 1"
    now = datetime.utcnow()
    # Append 2 entries (under threshold of 3)
    q.recent_failures.append((now, err))
    q.recent_failures.append((now, err))
    assert _is_systemic_failure(q, err) is False


def test_three_identical_within_window_triggers():
    q = _make_queue()
    err = "Process exited with code 1"
    now = datetime.utcnow()
    q.recent_failures.append((now, err))
    q.recent_failures.append((now, err))
    q.recent_failures.append((now, err))
    assert _is_systemic_failure(q, err) is True


def test_three_different_errors_not_systemic():
    q = _make_queue()
    now = datetime.utcnow()
    q.recent_failures.append((now, "Process exited with code 1"))
    q.recent_failures.append((now, "Network unreachable"))
    q.recent_failures.append((now, "TypeError: foo"))
    # current incoming err is "Process exited with code 1" — only 1 match
    assert _is_systemic_failure(q, "Process exited with code 1") is False


def test_old_entries_trimmed():
    q = _make_queue()
    err = "Process exited with code 1"
    old = datetime.utcnow() - timedelta(seconds=_SYSTEMIC_FAILURE_WINDOW_SECONDS + 30)
    new = datetime.utcnow()
    q.recent_failures.append((old, err))
    q.recent_failures.append((old, err))
    q.recent_failures.append((new, err))
    # Only 1 entry survives the trim → not systemic
    assert _is_systemic_failure(q, err) is False
    # And the trim happened in place
    assert len(q.recent_failures) == 1


def test_normalize_strips_uuids_and_paths():
    a = "Process exited; session abc12345-1234-1234-1234-123456789012 at /var/log/foo.log"
    b = "Process exited; session deadbeef-dead-beef-dead-beefdeadbeef at /tmp/bar.log"
    assert _normalize_error_for_systemic(a) == _normalize_error_for_systemic(b)


def test_empty_error_does_not_trigger():
    q = _make_queue()
    now = datetime.utcnow()
    for _ in range(_SYSTEMIC_FAILURE_THRESHOLD):
        q.recent_failures.append((now, ""))
    assert _is_systemic_failure(q, "") is False


def test_threshold_constant_matches_design():
    """Design contract: 3 identical failures in 60s window."""
    assert _SYSTEMIC_FAILURE_THRESHOLD == 3
    assert _SYSTEMIC_FAILURE_WINDOW_SECONDS == 60.0


def test_normalised_match_across_session_ids():
    """Different session-id substrings should still match → 3 'same' failures."""
    q = _make_queue()
    now = datetime.utcnow()
    errs = [
        "Process exited with code 1 (session aaa11111-1111-1111-1111-111111111111)",
        "Process exited with code 1 (session bbb22222-2222-2222-2222-222222222222)",
        "Process exited with code 1 (session ccc33333-3333-3333-3333-333333333333)",
    ]
    for ts_err in errs:
        q.recent_failures.append((now, ts_err))
    # Incoming is yet another session
    new_err = "Process exited with code 1 (session ddd44444-4444-4444-4444-444444444444)"
    assert _is_systemic_failure(q, new_err) is True


def test_mixed_window_some_old_some_new():
    """Old entries trimmed; only the in-window ones counted."""
    q = _make_queue()
    err = "Process exited with code 1"
    old = datetime.utcnow() - timedelta(seconds=_SYSTEMIC_FAILURE_WINDOW_SECONDS + 5)
    fresh = datetime.utcnow()
    q.recent_failures.append((old, err))
    q.recent_failures.append((fresh, err))
    q.recent_failures.append((fresh, err))
    q.recent_failures.append((fresh, err))
    # 3 fresh ⇒ trigger
    assert _is_systemic_failure(q, err) is True
    assert len(q.recent_failures) == 3


@pytest.mark.asyncio
async def test_run_queue_pauses_after_3_systemic_failures(monkeypatch):
    """Integration: run_queue with mocked _execute_task that always fails.

    Simulates the exact CB-2792 scenario — 3+ tasks fail with identical
    'Process exited with code 1' and zero successes. Queue must transition
    to WAITING_RESET/unknown_systemic instead of cascading through every task.
    """
    import asyncio as _asyncio
    from services.autopilot_queue_service import (
        AutoPilotQueueService, QueueTask, QueueStatus, TaskStatus,
    )

    svc = AutoPilotQueueService()

    # Build 5 pending tasks
    tasks = [
        QueueTask(
            issue_id=f"i-{i}",
            issue_key=f"T-{i}",
            issue_title=f"Task {i}",
            order=i,
            status=TaskStatus.PENDING,
            execution_mode="implement",
        )
        for i in range(5)
    ]
    queue = AutoPilotQueue(
        id="test-q-systemic",
        feature_id="f-1",
        feature_key="TEST-FEATURE",
        project_id="p-1",
        project_path="/tmp",
        provider="claude_code",
        tasks=tasks,
        config={},
        status=QueueStatus.RUNNING,
    )
    svc._queues[queue.id] = queue

    # Stub _execute_task: always reports "failed" with identical error.
    async def _fake_execute(q, t):
        t.error = "Process exited with code 1"
        t.status = TaskStatus.FAILED
        return "failed"
    monkeypatch.setattr(svc, "_execute_task", _fake_execute)

    # Stub _persist so we don't hit DB.
    async def _noop_persist(*a, **kw): return None
    monkeypatch.setattr(svc, "_persist", _noop_persist)

    # Stub _apply_failure to short-circuit normal failure handling
    async def _fail_action(*a, **kw): return "continue"
    monkeypatch.setattr(svc, "_apply_failure", _fail_action)

    # Stub _schedule_auto_resume so we don't actually arm a timer
    monkeypatch.setattr(svc, "_schedule_auto_resume", lambda *a, **kw: None)

    # Stub transition_state — module-level import
    from services import autopilot_queue_service as mod
    async def _noop_transition(*a, **kw): return None
    monkeypatch.setattr(mod, "transition_state", _noop_transition)

    # Stub terminal_service.get_session to return None so the existing
    # detect_exhaustion_from_session path returns None.
    monkeypatch.setattr(mod.terminal_service, "get_session", lambda sid: None)

    # Run the queue loop with a short timeout — it MUST pause itself
    # before exhausting all 5 tasks.
    runner = _asyncio.create_task(svc.run_queue(queue.id))
    # Give the loop a moment to fail 3 tasks + trigger heuristic
    for _ in range(50):
        await _asyncio.sleep(0.05)
        if queue.status == QueueStatus.WAITING_RESET:
            break
    runner.cancel()
    try:
        await runner
    except _asyncio.CancelledError:
        pass

    # Acceptance: queue paused, current_index < total tasks (didn't cascade)
    assert queue.status == QueueStatus.WAITING_RESET, f"expected WAITING_RESET got {queue.status}"
    assert queue.pause_reason == "unknown_systemic"
    assert queue.current_index < len(queue.tasks), \
        f"queue cascaded through all tasks — idx={queue.current_index}/{len(queue.tasks)}"
    assert queue.reset_time is not None


def test_borderline_window_just_inside():
    """An entry just inside the window edge stays in."""
    q = _make_queue()
    err = "Process exited with code 1"
    # 1 second of slack absorbs scheduling jitter between append + check
    boundary = datetime.utcnow() - timedelta(seconds=_SYSTEMIC_FAILURE_WINDOW_SECONDS - 1)
    fresh = datetime.utcnow()
    q.recent_failures.append((boundary, err))
    q.recent_failures.append((fresh, err))
    q.recent_failures.append((fresh, err))
    assert _is_systemic_failure(q, err) is True
