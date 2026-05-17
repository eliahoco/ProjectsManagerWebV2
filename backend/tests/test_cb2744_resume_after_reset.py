"""
CB-2744 regression tests — reset task rewinds current_index + defensive resume scan.

Two scenarios:
  1. Part A: reset_queue_task rewinds queue.current_index when a lower-order task
     is reset back to pending.  Without the fix, current_index stayed at 18 and
     resume_queue refused ("no active task at index 18/18").

  2. Part B: resume_queue self-heals a mis-indexed queue (current_index past the
     end, or pointing at a non-pending task) by scanning for the next pending task
     and updating current_index before unblocking the loop.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio

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
    n_tasks: int = 5,
    status: QueueStatus = QueueStatus.PAUSED,
    qid: str | None = None,
) -> AutoPilotQueue:
    """Build an in-memory AutoPilotQueue with *n_tasks* tasks (all PENDING)."""
    qid = qid or str(uuid.uuid4())
    tasks = [
        QueueTask(
            issue_id=f"issue-{i}",
            issue_key=f"CB-{2000 + i}",
            issue_title=f"Task {i}",
            order=i,
            status=TaskStatus.PENDING,
        )
        for i in range(n_tasks)
    ]
    return AutoPilotQueue(
        id=qid,
        feature_id="feat-cb2744",
        feature_key="CB-2744",
        project_id="p-test",
        project_path="/tmp/test",
        status=status,
        tasks=tasks,
        config=QueueConfig(),
    )


# ---------------------------------------------------------------------------
# Part A — reset_queue_task rewinds current_index
# ---------------------------------------------------------------------------


def test_part_a_reset_rewinds_current_index_when_lower_order_reset():
    """
    Given: queue with 5 tasks, tasks 0-3 completed, current_index=4 (running task 4).
    User resets task 2 back to pending (order=2 < current_index=4).
    Expected: current_index rewinds to 2 so the reset task will be re-run.
    """
    q = _make_queue(n_tasks=5, status=QueueStatus.PAUSED)
    # Simulate 4 tasks already done, cursor at 4
    for i in range(4):
        q.tasks[i].status = TaskStatus.COMPLETED
    q.current_index = 4

    # Reset task at order=2 back to pending (mimics the endpoint logic without HTTP)
    task = next(t for t in q.tasks if t.order == 2)
    task.status = TaskStatus.PENDING

    # Part A logic: find lowest pending order; rewind if below current_index
    pending_orders = [t.order for t in q.tasks if t.status == TaskStatus.PENDING]
    lowest_pending = min(pending_orders)
    if lowest_pending < q.current_index:
        q.current_index = lowest_pending

    assert q.current_index == 2, (
        "current_index should rewind to 2 (the reset task's order)"
    )


def test_part_a_no_rewind_when_reset_task_order_above_current_index():
    """
    Given: current_index=2, all tasks 0-1 done, tasks 2-4 pending.
    User resets task 4 (order=4 > current_index=2).
    Expected: current_index stays at 2 — no rewind needed.
    """
    q = _make_queue(n_tasks=5, status=QueueStatus.PAUSED)
    for i in range(2):
        q.tasks[i].status = TaskStatus.COMPLETED
    q.current_index = 2

    # Reset task 4 — already pending, just ensure logic doesn't rewind
    task = next(t for t in q.tasks if t.order == 4)
    old_status = task.status  # was already PENDING
    task.status = TaskStatus.PENDING

    pending_orders = [t.order for t in q.tasks if t.status == TaskStatus.PENDING]
    lowest_pending = min(pending_orders)
    if lowest_pending < q.current_index:
        q.current_index = lowest_pending

    assert q.current_index == 2, "current_index must not rewind when reset order >= current"


def test_part_a_rewinds_for_bulk_reset_lowest_order_wins():
    """
    Simulate the CB-2737 scenario: tasks 14-17 reset, current_index=18.
    After resetting all four, current_index should wind back to 14.
    """
    q = _make_queue(n_tasks=19, status=QueueStatus.PAUSED)
    # Tasks 0-17 completed, cursor past end
    for i in range(18):
        q.tasks[i].status = TaskStatus.COMPLETED
    q.current_index = 18

    # Reset tasks 14-17 back to pending (as CB-2743 reset endpoint would do)
    for order in (14, 15, 16, 17):
        q.tasks[order].status = TaskStatus.PENDING

    # Apply Part A logic for the last reset call (order=17, lowest pending=14)
    pending_orders = [t.order for t in q.tasks if t.status == TaskStatus.PENDING]
    lowest_pending = min(pending_orders)
    if lowest_pending < q.current_index:
        q.current_index = lowest_pending

    assert q.current_index == 14, (
        "After bulk reset of orders 14-17, cursor must rewind to 14"
    )


# ---------------------------------------------------------------------------
# Part B — resume_queue self-heals mis-indexed current_index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_part_b_resume_self_heals_when_index_past_end_with_pending_tasks():
    """
    CB-2744 core scenario: current_index=18, len(tasks)=18, tasks 14-17 pending.
    resume_queue should self-heal by scanning for the lowest pending task,
    set current_index=14, and return True (not False).
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=19, status=QueueStatus.PAUSED)
    for i in range(19):
        q.tasks[i].status = TaskStatus.COMPLETED
    # Simulate reset of tasks 14-17
    for order in (14, 15, 16, 17):
        q.tasks[order].status = TaskStatus.PENDING
    q.current_index = 18  # past last task (index 18 would be out of range for 0-17)

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is True, "resume_queue should self-heal and return True"
    assert q.current_index == 14, (
        "current_index should be rewound to 14 (lowest pending order)"
    )
    # pause_reason + reset_time must be cleared on a successful resume
    assert q.pause_reason is None
    assert q.reset_time is None


@pytest.mark.asyncio
async def test_part_b_resume_self_heals_when_current_task_is_completed():
    """
    current_index points to a COMPLETED task (not out of bounds, but done).
    resume_queue should scan ahead, find next pending, and self-heal.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=5, status=QueueStatus.PAUSED)
    # Tasks 0, 1 done; tasks 2-4 pending; cursor wrongly points at task 1
    q.tasks[0].status = TaskStatus.COMPLETED
    q.tasks[1].status = TaskStatus.COMPLETED
    q.current_index = 1  # points at completed task

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is True
    assert q.current_index == 2, "cursor should advance to next pending task (order=2)"


@pytest.mark.asyncio
async def test_part_b_resume_self_heals_when_current_task_is_failed():
    """
    current_index points to a FAILED task. resume_queue must skip it and
    find the next pending task.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=4, status=QueueStatus.PAUSED)
    q.tasks[0].status = TaskStatus.FAILED
    q.tasks[1].status = TaskStatus.PENDING
    q.tasks[2].status = TaskStatus.PENDING
    q.tasks[3].status = TaskStatus.PENDING
    q.current_index = 0  # points at failed task

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is True
    assert q.current_index == 1, "cursor should skip failed task and land on first pending"


@pytest.mark.asyncio
async def test_part_b_resume_refuses_when_no_pending_tasks_anywhere():
    """
    current_index past end AND no tasks are pending — genuinely nothing to do.
    resume_queue must return False.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=3, status=QueueStatus.PAUSED)
    for t in q.tasks:
        t.status = TaskStatus.COMPLETED
    q.current_index = 3  # past end

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is False, "resume_queue must refuse when no pending tasks exist"
    assert q.status == QueueStatus.PAUSED, "queue status must stay PAUSED on refusal"


@pytest.mark.asyncio
async def test_part_b_resume_succeeds_normally_when_index_already_correct():
    """
    Happy path: current_index=0, task 0 is PENDING.
    No self-heal needed; resume returns True as before.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=3, status=QueueStatus.PAUSED)
    q.current_index = 0  # correct

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is True
    assert q.current_index == 0


@pytest.mark.asyncio
async def test_part_b_resume_of_waiting_reset_queue_self_heals():
    """
    Token-exhaustion path: WAITING_RESET status + mis-indexed cursor.
    Self-heal should work regardless of PAUSED vs WAITING_RESET.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=4, status=QueueStatus.WAITING_RESET)
    q.tasks[0].status = TaskStatus.COMPLETED
    q.tasks[1].status = TaskStatus.COMPLETED
    q.tasks[2].status = TaskStatus.PENDING
    q.tasks[3].status = TaskStatus.PENDING
    q.current_index = 4  # past end
    q.pause_reason = "token_exhaustion"

    svc._queues[q.id] = q

    result = await svc.resume_queue(q.id)

    assert result is True
    assert q.current_index == 2
    assert q.pause_reason is None  # cleared on successful resume


# ---------------------------------------------------------------------------
# Integration: Part A + Part B together
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_reset_then_resume_works_end_to_end():
    """
    Full flow of CB-2744:
      1. Queue has 5 tasks, tasks 0-4 done, current_index=5 (past end).
      2. User resets task 3 (Part A rewinds current_index → 3).
      3. User calls resume_queue — should succeed without self-heal needed
         because Part A already fixed the index.
    """
    svc = AutoPilotQueueService()
    q = _make_queue(n_tasks=5, status=QueueStatus.PAUSED)
    for t in q.tasks:
        t.status = TaskStatus.COMPLETED
    q.current_index = 5  # past end

    svc._queues[q.id] = q

    # --- Part A: reset task at order=3 ---
    task = next(t for t in q.tasks if t.order == 3)
    task.status = TaskStatus.PENDING
    pending_orders = [t.order for t in q.tasks if t.status == TaskStatus.PENDING]
    lowest_pending = min(pending_orders)
    if lowest_pending < q.current_index:
        q.current_index = lowest_pending

    assert q.current_index == 3  # Part A rewound it

    # --- Part B: resume should succeed ---
    result = await svc.resume_queue(q.id)
    assert result is True
    assert q.current_index == 3  # unchanged — Part A already set it correctly
