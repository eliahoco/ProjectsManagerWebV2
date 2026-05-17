"""
CB-2778 regression tests — resume_queue rewinds to first pending when idx past last.

Verifies four acceptance scenarios from the CB-2778 spec:

1. Queue idx=N, M completed + K pending at end (legacy crash path)
   → resume rewinds to first pending → all pending tasks will run.
2. Queue idx=N, mixed completed + pending in middle
   → rewind to first pending → already-completed tasks in middle are NOT re-run.
3. Queue idx=N, no pending tasks at all
   → resume no-op (returns False) — existing behavior preserved.
4. Queue idx=N, single failed task at end (status==failed, not pending)
   → resume no-op (failed != pending — that's the reset-endpoint's job first).

The rewind logic lives in ``resume_queue`` (CB-2744 Part B, added in the same
autopilot_queue_service.py refactor). These tests lock in that behavior for the
specific CB-2038 crash-recovery pattern: 16 completed + 2 failed tasks,
current_index=18, where resume was silently returning False.
"""

from __future__ import annotations

import uuid

import pytest

from services.autopilot_queue_service import (
    AutoPilotQueue,
    AutoPilotQueueService,
    QueueConfig,
    QueueStatus,
    QueueTask,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_queue(
    n_tasks: int,
    status: QueueStatus = QueueStatus.PAUSED,
    qid: str | None = None,
) -> AutoPilotQueue:
    """Build an in-memory AutoPilotQueue with *n_tasks* tasks (all PENDING)."""
    qid = qid or str(uuid.uuid4())
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
        feature_id="feat-cb2778",
        feature_key="CB-2038",
        project_id="p-test",
        project_path="/tmp/test",
        status=status,
        tasks=tasks,
        config=QueueConfig(),
    )


# ---------------------------------------------------------------------------
# Test 1: Legacy crash path — completed tasks + pending tasks at end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_rewinds_to_first_pending_legacy_crash_path():
    """
    CB-2778 Scenario 1: legacy crash path.

    Queue has 18 tasks (indices 0-17). Tasks 0-15 are COMPLETED.
    Tasks 16-17 are PENDING (e.g. were never reached before crash).
    current_index = 18 (past the last index).

    resume_queue() must:
    - Detect current_index >= len(tasks) → trigger rewind scan.
    - Find pending tasks at orders 16 and 17.
    - Rewind current_index to 16 (lowest pending order).
    - Return True so the caller re-launches run_queue.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=18, status=QueueStatus.PAUSED)

    # Simulate: 16 completed, 2 pending at end, cursor past end
    for i in range(16):
        q.tasks[i].status = TaskStatus.COMPLETED
    # tasks[16] and tasks[17] remain PENDING (default from _make_queue)
    q.current_index = 18  # past last valid index (0-17)

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is True, "resume_queue must return True when pending tasks exist"
    assert q.current_index == 16, (
        f"current_index should rewind to 16 (first pending), got {q.current_index}"
    )
    # Queue should be ready to run — pause event set, bookkeeping cleared
    assert q._pause_event.is_set(), "pause event must be set after successful resume"
    assert q.pause_reason is None, "pause_reason must be cleared on resume"


# ---------------------------------------------------------------------------
# Test 2: Mixed completed + pending in middle — completed must NOT re-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_rewinds_to_first_pending_skips_completed_in_middle():
    """
    CB-2778 Scenario 2: mixed completed + pending, cursor past end.

    Queue has 8 tasks. Tasks 0, 1, 3, 5 are COMPLETED.
    Tasks 2, 4, 6, 7 are PENDING. current_index = 8 (past end).

    resume_queue() must rewind to order=2 (lowest pending).
    The run_queue loop will then run tasks 2, 4, 6, 7 — it will skip
    tasks 3 and 5 because they are already COMPLETED (loop checks status
    at execution time, not just current_index). This test only validates
    that current_index lands at the correct lowest-pending value.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=8, status=QueueStatus.PAUSED)

    q.tasks[0].status = TaskStatus.COMPLETED
    q.tasks[1].status = TaskStatus.COMPLETED
    q.tasks[2].status = TaskStatus.PENDING   # first pending
    q.tasks[3].status = TaskStatus.COMPLETED
    q.tasks[4].status = TaskStatus.PENDING
    q.tasks[5].status = TaskStatus.COMPLETED
    q.tasks[6].status = TaskStatus.PENDING
    q.tasks[7].status = TaskStatus.PENDING
    q.current_index = 8  # past end

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is True, "resume_queue must return True when pending tasks exist"
    assert q.current_index == 2, (
        f"current_index should rewind to 2 (first pending in mixed queue), got {q.current_index}"
    )
    # Verify the completed tasks are untouched
    assert q.tasks[0].status == TaskStatus.COMPLETED, "task 0 must remain COMPLETED"
    assert q.tasks[1].status == TaskStatus.COMPLETED, "task 1 must remain COMPLETED"
    assert q.tasks[3].status == TaskStatus.COMPLETED, "task 3 must remain COMPLETED"
    assert q.tasks[5].status == TaskStatus.COMPLETED, "task 5 must remain COMPLETED"


# ---------------------------------------------------------------------------
# Test 3: No pending tasks — resume must be a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_noop_when_no_pending_tasks():
    """
    CB-2778 Scenario 3: no pending tasks anywhere — resume is a no-op.

    Queue has 5 tasks, all COMPLETED. current_index = 5 (past end).
    resume_queue() must return False and leave queue status as PAUSED.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=5, status=QueueStatus.PAUSED)

    for t in q.tasks:
        t.status = TaskStatus.COMPLETED
    q.current_index = 5  # past end

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is False, "resume_queue must return False when no pending tasks exist"
    assert q.status == QueueStatus.PAUSED, "queue must remain PAUSED when resume is refused"
    assert q.current_index == 5, "current_index must not change when resume is refused"


# ---------------------------------------------------------------------------
# Test 4: Single failed task at end — resume must be a no-op (failed != pending)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_noop_when_only_failed_tasks_remain():
    """
    CB-2778 Scenario 4: only failed tasks remain — resume is a no-op.

    This is the exact CB-2038 shape: 16 completed + 2 failed, idx=18.
    The failed tasks must be reset to pending first (via the /reset endpoint,
    i.e. T2 of the CB-2775 regression). Until they are reset, resume returns
    False — there is nothing to run without risking double-execution of
    already-completed work.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=18, status=QueueStatus.PAUSED)

    # 16 completed
    for i in range(16):
        q.tasks[i].status = TaskStatus.COMPLETED
    # 2 failed (CB-2731 idx 16, CB-2732 idx 17)
    q.tasks[16].status = TaskStatus.FAILED
    q.tasks[17].status = TaskStatus.FAILED
    q.current_index = 18  # past end, mirrors the real CB-2038 queue state

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is False, (
        "resume_queue must return False when only failed tasks remain — "
        "failed tasks must be reset to pending first (T2 / /reset endpoint)"
    )
    assert q.status == QueueStatus.PAUSED, "queue must remain PAUSED after refused resume"
    # Verify failed tasks were not silently re-queued
    assert q.tasks[16].status == TaskStatus.FAILED, "task 16 must remain FAILED"
    assert q.tasks[17].status == TaskStatus.FAILED, "task 17 must remain FAILED"
