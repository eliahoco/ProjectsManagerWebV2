"""
End-to-end persistence + rehydration tests for CB-1951 E2.

Verifies:
- Crash mid-queue → next backend startup rehydrates the queue
- Stale RUNNING tasks become failed(crash_recovery) on rehydration
- Queue itself flips to paused/crash_recovery
- ``get_recovered_queues`` returns the rehydrated queue
- ``clear_recovery_state`` removes it once the user acts

CB-2671 regression tests (T6):
- Rehydrated tasks have non-empty issue_key + issue_title (CB-2673 schema fix)
- Defensive fallback re-fetches key/title from Issue table when DB row has NULL (CB-2676 T5)
- Resume re-launches run_queue coroutine when queue._task is None (CB-2676 T4)
- End-to-end: rehydrate + resume populates keys and queue becomes active
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.database import Base
from models import Project
from models.autopilot import AutoPilotTaskRecord
from models.issue import Issue
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

    # CB-2738: Task 1 (was RUNNING at crash time) must be reset to PENDING —
    # a backend restart is NOT a task failure.  ``failed`` is reserved for real
    # execution errors (subprocess non-zero exit / exception during execution).
    statuses = {t.order: (t.status, t.error) for t in rehydrated.tasks}
    assert statuses[0][0] == TaskStatus.COMPLETED
    assert statuses[1][0] == TaskStatus.PENDING
    assert statuses[1][1] is None  # no failure reason — it was just interrupted
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

    result = await svc.clear_recovery_state(q.id)
    assert result["ok"] is True
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


# ---------------------------------------------------------------------------
# CB-2671 T6 regression tests — CB-2673 schema fix + CB-2676 T4/T5 fixes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rehydrate_populates_issue_key_and_title(engine_and_session_factory):
    """CB-2671 T6-Test1: After rehydration every task must have non-empty
    issue_key AND issue_title.

    Verifies the CB-2673 fix: ``AutoPilotTaskRecord`` now persists issueKey /
    issueTitle columns and ``_record_to_queue`` reads them back.  Prior to the
    fix, all rehydrated tasks had empty strings for key and title.
    """
    _, Sf = engine_and_session_factory

    # Build a queue with 3 tasks, each with distinct key + title.
    pre_svc = AutoPilotQueueService()
    queue = _make_queue(n_tasks=3)
    # Customise keys/titles to be easily assertable.
    for i, task in enumerate(queue.tasks):
        task.issue_key = f"CB-{2000 + i}"
        task.issue_title = f"Regression title {i}"

    queue.tasks[0].status = TaskStatus.COMPLETED
    queue.tasks[1].status = TaskStatus.RUNNING   # CB-2738: reset to pending on rehydration
    queue.tasks[2].status = TaskStatus.PENDING
    queue.current_index = 1
    pre_svc._queues[queue.id] = queue

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # Simulate post-crash fresh service instance.
    post_svc = AutoPilotQueueService()
    recovered_ids = await post_svc.rehydrate_from_db()

    assert recovered_ids == [queue.id], "Expected exactly one rehydrated queue"
    rehydrated = post_svc._queues[queue.id]

    for task in rehydrated.tasks:
        assert task.issue_key, (
            f"Task order={task.order} has empty issue_key after rehydration — "
            "CB-2673 fix may not be in effect"
        )
        assert task.issue_title, (
            f"Task order={task.order} has empty issue_title after rehydration — "
            "CB-2673 fix may not be in effect"
        )

    # Verify the specific values round-tripped correctly.
    by_order = {t.order: t for t in rehydrated.tasks}
    assert by_order[0].issue_key == "CB-2000"
    assert by_order[0].issue_title == "Regression title 0"
    assert by_order[2].issue_key == "CB-2002"
    assert by_order[2].issue_title == "Regression title 2"


@pytest.mark.asyncio
async def test_defensive_fallback_refetches_null_key_title(
    engine_and_session_factory, caplog
):
    """CB-2671 T6-Test2: When a DB task row has issueKey=NULL (legacy corrupt
    data), ``_execute_task`` must re-fetch key/title from the Issue table,
    populate the task, and emit a WARNING via the standard logger.

    This exercises the CB-2676 T5 defensive fallback inside _execute_task.
    We mock the heavy I/O paths (terminal_service, context_builder, db cascade)
    so the test stays fast and deterministic.
    """
    _, Sf = engine_and_session_factory

    # Seed an Issue row so the fallback SELECT finds something.
    async with Sf() as db:
        db.add(Issue(
            id="issue-fallback-0",
            projectId="p-test",
            key="CB-9001",
            sequence=9001,
            title="Fetched from Issue table",
            type="TASK",
            status="TODO",
            priority="MEDIUM",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await db.commit()

    # Create and persist a queue with a task that references the seeded issue.
    queue = _make_queue(n_tasks=1)
    queue.tasks[0].issue_id = "issue-fallback-0"
    queue.tasks[0].issue_key = "CB-9001"
    queue.tasks[0].issue_title = "Fetched from Issue table"
    queue.status = QueueStatus.PAUSED
    queue.current_index = 0

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()
        # NULL-out the columns to simulate pre-migration legacy data.
        await db.execute(
            update(AutoPilotTaskRecord)
            .where(AutoPilotTaskRecord.queueId == queue.id)
            .values(issueKey=None, issueTitle=None)
        )
        await db.commit()

    # Rehydrate — the task will have empty key/title from the NULL DB rows.
    import models.database as _mdm
    import services.autopilot_queue_service as _svc_mod

    _orig_mdm = _mdm.AsyncSessionLocal
    _orig_svc = _svc_mod.AsyncSessionLocal
    _mdm.AsyncSessionLocal = Sf
    _svc_mod.AsyncSessionLocal = Sf

    try:
        post_svc = AutoPilotQueueService()
        await post_svc.rehydrate_from_db()
        rehydrated_q = post_svc._queues[queue.id]
        task = rehydrated_q.tasks[0]

        # Confirm the task was rehydrated with empty key/title (NULL survived).
        assert not task.issue_key, (
            "Expected empty key from NULL DB row before fallback triggers"
        )

        # Mock the parts that would need real external services.
        mock_session_obj = type("MockSession", (), {
            "session_id": "sess-fallback",
            "status": type("St", (), {"value": "completed"})(),
            "exit_code": 0,
            "output": [],
            "error": None,
        })()

        with (
            patch.object(post_svc, "_resume_preflight", new=AsyncMock(return_value="ok")),
            patch.object(post_svc, "_persist", new=AsyncMock()),
            patch("services.autopilot_queue_service.terminal_service") as mock_ts,
            patch(
                "services.autopilot_queue_service.build_execution_context",
                new=AsyncMock(return_value="ctx"),
            ),
            patch(
                "services.autopilot_queue_service.cascade_in_progress_to_parents",
                new=AsyncMock(),
            ),
            caplog.at_level("WARNING", logger="services.autopilot_queue_service"),
        ):
            mock_ts.start_execution = AsyncMock(return_value="sess-fallback")
            mock_ts.get_session = lambda _sid: mock_session_obj

            await post_svc._execute_task(rehydrated_q, task)

        # (a) Issue table was re-queried — key/title are now populated.
        assert task.issue_key == "CB-9001", (
            f"Fallback should have set issue_key='CB-9001', got {task.issue_key!r}"
        )
        assert task.issue_title == "Fetched from Issue table", (
            f"Fallback should have set issue_title, got {task.issue_title!r}"
        )

        # (b) A WARNING was logged mentioning the CB-2676 fallback.
        warning_records = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "CB-2676" in r.getMessage()
        ]
        assert warning_records, (
            "Expected a WARNING log containing 'CB-2676' from the defensive fallback"
        )

    finally:
        _mdm.AsyncSessionLocal = _orig_mdm
        _svc_mod.AsyncSessionLocal = _orig_svc


@pytest.mark.asyncio
async def test_resume_relaunches_run_queue_coroutine(engine_and_session_factory, monkeypatch):
    """CB-2671 T6-Test3: After a simulated crash (queue._task = None), the
    re-launch logic from ``api/execution.py resume_queue`` must assign a live
    asyncio.Task to ``queue._task``.

    We test the re-launch logic directly (not via HTTP) to stay fast and avoid
    needing a full ASGI transport setup with mocked services.
    """
    _, Sf = engine_and_session_factory

    # Create a PAUSED queue in recovery state.
    svc = AutoPilotQueueService()
    queue = _make_queue(n_tasks=2)
    queue.status = QueueStatus.PAUSED
    queue.pause_reason = "crash_recovery"
    queue.current_index = 0
    svc._queues[queue.id] = queue
    svc._recovered_queue_ids.add(queue.id)

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # Pre-condition: _task is None (simulates crash — coroutine was never launched
    # in this fresh service instance).
    assert queue._task is None, "Pre-condition: queue._task must be None before test"

    # Track run_queue invocations without doing real I/O.
    run_queue_calls: list[str] = []

    async def _fake_run_queue(queue_id: str) -> None:
        run_queue_calls.append(queue_id)

    monkeypatch.setattr(svc, "run_queue", _fake_run_queue)

    # Step 1: resume sets _pause_event.
    result = await svc.resume_queue(queue.id)
    assert result, "resume_queue should return True for a PAUSED queue"

    # Step 2: re-launch logic (mirrors api/execution.py resume_queue endpoint).
    from app.background import create_tracked_task

    task_missing = queue._task is None
    task_done = (not task_missing) and queue._task.done()
    if task_missing or task_done:
        queue._task = create_tracked_task(
            svc.run_queue(queue.id),
            name=f"autopilot-queue-{queue.id}",
        )

    # Let the event loop tick so the coroutine starts.
    await asyncio.sleep(0)

    # Assert queue._task is now a live asyncio.Task.
    assert queue._task is not None, "queue._task must be set after resume re-launch"
    assert isinstance(queue._task, asyncio.Task), (
        f"Expected asyncio.Task, got {type(queue._task)}"
    )

    # Wait for the stub task to finish.
    await queue._task

    # The fake coroutine should have been called at least once.
    assert len(run_queue_calls) >= 1, (
        f"run_queue was not called; calls={run_queue_calls}"
    )
    assert queue.id in run_queue_calls, (
        f"Expected queue.id={queue.id!r} in run_queue calls, got {run_queue_calls}"
    )


@pytest.mark.asyncio
async def test_end_to_end_rehydrate_resume_populates_everything(
    engine_and_session_factory, monkeypatch
):
    """CB-2671 T6-Test4: Full lifecycle — create queue, persist, simulate crash
    (fresh service instance), rehydrate, resume.

    Asserts:
    - All tasks have non-empty issue_key + issue_title after rehydration
    - Queue is paused/crash_recovery after rehydration (manual resume required)
    - resume_queue returns True
    - After re-launch, queue._task is a live asyncio.Task
    - _pause_event is set (queue unblocked)
    - No unhandled exceptions raised
    """
    _, Sf = engine_and_session_factory

    # ---- Phase 1: Pre-crash — create and persist a running queue ----
    pre_svc = AutoPilotQueueService()
    queue = _make_queue(n_tasks=3)
    queue.tasks[0].status = TaskStatus.COMPLETED
    queue.tasks[1].status = TaskStatus.RUNNING   # CB-2738: reset to pending on rehydration
    queue.tasks[2].status = TaskStatus.PENDING
    queue.current_index = 1
    queue.status = QueueStatus.RUNNING
    pre_svc._queues[queue.id] = queue

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    original_queue_id = queue.id

    # ---- Phase 2: Post-crash — fresh service instance ----
    import models.database as _mdm
    import services.autopilot_queue_service as _svc_mod

    _orig_mdm = _mdm.AsyncSessionLocal
    _orig_svc = _svc_mod.AsyncSessionLocal
    _mdm.AsyncSessionLocal = Sf
    _svc_mod.AsyncSessionLocal = Sf

    try:
        post_svc = AutoPilotQueueService()

        # Rehydrate simulates the startup lifespan hook.
        recovered_ids = await post_svc.rehydrate_from_db()
        assert original_queue_id in recovered_ids, "Queue not recovered after rehydration"

        rehydrated = post_svc._queues[original_queue_id]

        # All tasks must have populated identifiers (CB-2673 fix).
        for task in rehydrated.tasks:
            assert task.issue_key, (
                f"Task order={task.order} missing issue_key after rehydration"
            )
            assert task.issue_title, (
                f"Task order={task.order} missing issue_title after rehydration"
            )

        # Queue must be paused / crash_recovery (not auto-resumed).
        assert rehydrated.status == QueueStatus.PAUSED
        assert rehydrated.pause_reason == "crash_recovery"

        # ---- Phase 3: Resume with no-op run_queue ----
        async def _noop_run_queue(queue_id: str) -> None:
            pass

        monkeypatch.setattr(post_svc, "run_queue", _noop_run_queue)

        result = await post_svc.resume_queue(original_queue_id)
        assert result, "resume_queue should succeed on a crash_recovery queue"

        # Apply CB-2676 T4 re-launch logic.
        from app.background import create_tracked_task

        task_missing = rehydrated._task is None
        task_done = (not task_missing) and rehydrated._task.done()
        if task_missing or task_done:
            rehydrated._task = create_tracked_task(
                post_svc.run_queue(original_queue_id),
                name=f"autopilot-queue-{original_queue_id}",
            )

        # Allow the event loop to tick.
        await asyncio.sleep(0)

        # Final assertions.
        assert rehydrated._task is not None, (
            "queue._task must be a live asyncio.Task after resume + relaunch"
        )
        assert isinstance(rehydrated._task, asyncio.Task)
        assert rehydrated._pause_event.is_set(), (
            "_pause_event must be set (queue unblocked) after resume"
        )

        await rehydrated._task

    finally:
        _mdm.AsyncSessionLocal = _orig_mdm
        _svc_mod.AsyncSessionLocal = _orig_svc


# ---------------------------------------------------------------------------
# CB-2681/CB-2682 — _ensure_run_queue_task helper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_auto_resume_relaunches_run_queue(engine_and_session_factory, monkeypatch):
    """CB-2681: After token-exhaust pause + backend crash + auto-resume timer
    firing, ``_fire_auto_resume`` must ensure ``queue._task`` is a live
    asyncio.Task (not None) so execution actually resumes.

    Simulates: queue is WAITING_RESET, queue._task is None (post-rehydration),
    _fire_auto_resume fires → assert queue._task is a live coroutine.
    """
    _, Sf = engine_and_session_factory

    svc = AutoPilotQueueService()

    # Build a WAITING_RESET queue with tasks remaining (so resume_queue accepts it).
    queue = _make_queue(n_tasks=2)
    queue.status = QueueStatus.WAITING_RESET
    queue.pause_reason = "token_exhaustion"
    queue.current_index = 0
    queue._task = None  # simulates post-crash rehydration state
    svc._queues[queue.id] = queue

    # Stub out persistence so no real DB calls fire.
    monkeypatch.setattr(svc, "_persist", AsyncMock())
    monkeypatch.setattr(svc, "_persist_async", lambda *a, **kw: None)

    # Track run_queue calls without doing real I/O.
    run_queue_calls: list[str] = []

    async def _fake_run_queue(queue_id: str) -> None:
        run_queue_calls.append(queue_id)

    monkeypatch.setattr(svc, "run_queue", _fake_run_queue)

    # Fire the auto-resume (skipping the asyncio.sleep timer delay).
    await svc._fire_auto_resume(queue.id)

    # Let the event loop tick so the Task body executes.
    await asyncio.sleep(0)

    # Assertions
    assert queue._task is not None, (
        "CB-2681: queue._task must be non-None after _fire_auto_resume fires — "
        "_ensure_run_queue_task was not called or did not spawn a Task"
    )
    assert isinstance(queue._task, asyncio.Task), (
        f"Expected asyncio.Task, got {type(queue._task)}"
    )
    assert queue.id in run_queue_calls, (
        f"run_queue was not called for queue {queue.id!r}; calls={run_queue_calls}"
    )

    # Clean up the spawned task.
    if not queue._task.done():
        await queue._task


@pytest.mark.asyncio
async def test_ensure_run_queue_task_race_safe(monkeypatch):
    """CB-2681 race-safety: two concurrent callers of _ensure_run_queue_task
    must spawn exactly ONE run_queue coroutine — the ``_launching`` guard flag
    prevents the duplicate.

    We simulate the race by calling _ensure_run_queue_task twice in the same
    event-loop turn without yielding between calls (no ``await``).  Because
    asyncio is cooperative, the check-and-set is atomic from the coroutine's
    perspective, so the second call must see ``_launching=True`` and skip.
    """
    svc = AutoPilotQueueService()

    queue = _make_queue(n_tasks=1)
    queue.status = QueueStatus.PAUSED
    queue.current_index = 0
    queue._task = None
    svc._queues[queue.id] = queue

    # Count how many times create_tracked_task is called.
    spawn_count = 0
    real_tasks: list[asyncio.Task] = []

    async def _fake_run_queue(queue_id: str) -> None:  # noqa: ARG001
        pass

    monkeypatch.setattr(svc, "run_queue", _fake_run_queue)

    from app.background import create_tracked_task as _real_ctk

    def _counting_ctk(coro, name=None):
        nonlocal spawn_count
        spawn_count += 1
        t = _real_ctk(coro, name=name)
        real_tasks.append(t)
        return t

    with patch("services.autopilot_queue_service.AutoPilotQueueService._ensure_run_queue_task",
               wraps=svc._ensure_run_queue_task):
        with patch("app.background.create_tracked_task", side_effect=_counting_ctk):
            # Call twice without awaiting between — simulates concurrent resume.
            svc._ensure_run_queue_task(queue)
            svc._ensure_run_queue_task(queue)

    # Allow the spawned task to finish.
    await asyncio.sleep(0)
    for t in real_tasks:
        if not t.done():
            await t

    assert spawn_count == 1, (
        f"CB-2681 race: expected exactly 1 run_queue spawn, got {spawn_count}. "
        "The _launching guard may not be working."
    )


# ---------------------------------------------------------------------------
# CB-2734 regression — create_queue must populate issue_key + issue_title
# even when the caller passes empty strings (original CB-2671 regression).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_queue_in_memory_tasks_have_populated_keys(
    engine_and_session_factory,
):
    """CB-2734: After create_queue() is called, every in-memory task MUST have
    non-empty issue_key and issue_title — with NO save step in between.

    Before the CB-2734 fix the API endpoint forwarded whatever key/title the
    frontend sent to create_queue(); if the frontend sent "" (empty string),
    save_queue wrote NULL and the UI showed a blank list.  The fix backfills
    missing key/title from the Issue table before constructing the queue, so
    the first save_queue call always writes populated values.

    This test simulates the backfill logic (as executed by the API endpoint)
    and then verifies the in-memory AutoPilotQueue tasks are correct.
    """
    _, Sf = engine_and_session_factory

    # Seed Issue rows so the backfill lookup finds real data.
    async with Sf() as db:
        db.add(Issue(
            id="issue-cb2734-0",
            projectId="p-test",
            key="CB-2734",
            sequence=2734,
            title="Regression: create_queue populates issue_key",
            type="TASK",
            status="TODO",
            priority="MEDIUM",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        db.add(Issue(
            id="issue-cb2734-1",
            projectId="p-test",
            key="CB-2735",
            sequence=2735,
            title="Regression: second task also gets issue_key",
            type="TASK",
            status="TODO",
            priority="MEDIUM",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await db.commit()

    # Simulate the CB-2734 backfill: tasks arrive with empty key/title
    # (the pre-fix bug scenario).
    tasks_data = [
        {"issue_id": "issue-cb2734-0", "issue_key": "", "issue_title": "",
         "execution_mode": "implement", "force": False},
        {"issue_id": "issue-cb2734-1", "issue_key": "", "issue_title": "",
         "execution_mode": "implement", "force": False},
    ]

    # Apply the CB-2734 backfill (mirrors api/execution.py create_queue logic).
    from sqlalchemy import select as sa_select
    missing_issue_ids = [
        t["issue_id"]
        for t in tasks_data
        if not t.get("issue_key") or not t.get("issue_title")
    ]
    assert missing_issue_ids == ["issue-cb2734-0", "issue-cb2734-1"], (
        "Both tasks should initially have empty keys (pre-fix simulation)"
    )

    async with Sf() as db:
        from models.issue import Issue as IssueModel
        rows = await db.execute(
            sa_select(IssueModel).where(IssueModel.id.in_(missing_issue_ids))
        )
        issue_map = {i.id: i for i in rows.scalars().all()}
        for t in tasks_data:
            if not t.get("issue_key") or not t.get("issue_title"):
                issue = issue_map.get(t["issue_id"])
                if issue:
                    if not t.get("issue_key"):
                        t["issue_key"] = issue.key or ""
                    if not t.get("issue_title"):
                        t["issue_title"] = issue.title or ""

    # After backfill, verify tasks_data is now populated.
    assert tasks_data[0]["issue_key"] == "CB-2734", (
        "Backfill must populate issue_key from the Issue table"
    )
    assert tasks_data[1]["issue_key"] == "CB-2735", (
        "Backfill must populate issue_key for second task"
    )

    # Create the queue via the service (mirrors what the API endpoint does
    # after the CB-2734 backfill step).
    svc = AutoPilotQueueService()
    queue = svc.create_queue(
        feature_id="feat-cb2734",
        feature_key="CB-2734",
        project_id="p-test",
        project_path="/tmp/test",
        tasks=tasks_data,
    )

    # IMMEDIATE assertion — no save step — in-memory tasks must be populated.
    assert len(queue.tasks) == 2, "Queue must have 2 tasks"
    for task in queue.tasks:
        assert task.issue_key, (
            f"Task order={task.order} has empty issue_key immediately after "
            "create_queue() — CB-2734 backfill did not propagate"
        )
        assert task.issue_title, (
            f"Task order={task.order} has empty issue_title immediately after "
            "create_queue() — CB-2734 backfill did not propagate"
        )

    assert queue.tasks[0].issue_key == "CB-2734"
    assert queue.tasks[0].issue_title == "Regression: create_queue populates issue_key"
    assert queue.tasks[1].issue_key == "CB-2735"
    assert queue.tasks[1].issue_title == "Regression: second task also gets issue_key"


@pytest.mark.asyncio
async def test_create_queue_save_round_trip_preserves_keys(
    engine_and_session_factory,
):
    """CB-2734: After create_queue() + save_queue() + load_queue(), the
    persisted task records must have non-empty issueKey and issueTitle.

    This is the DB persistence leg of the CB-2734 regression test.
    Before the fix, NULL issueKey values in the DB caused blank UI after
    a backend restart (rehydration read NULLs → empty strings → blank list).
    """
    _, Sf = engine_and_session_factory

    # Seed Issue rows.
    async with Sf() as db:
        db.add(Issue(
            id="issue-cb2734-rt-0",
            projectId="p-test",
            key="CB-9910",
            sequence=9910,
            title="Round-trip task A",
            type="TASK",
            status="TODO",
            priority="LOW",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await db.commit()

    # Build tasks_data with pre-populated key/title (post-backfill state).
    tasks_data = [
        {"issue_id": "issue-cb2734-rt-0", "issue_key": "CB-9910",
         "issue_title": "Round-trip task A", "execution_mode": "implement",
         "force": False},
    ]

    svc = AutoPilotQueueService()
    queue = svc.create_queue(
        feature_id="feat-rt",
        feature_key="CB-9910",
        project_id="p-test",
        project_path="/tmp/test",
        tasks=tasks_data,
    )

    # Immediately populated in memory.
    assert queue.tasks[0].issue_key == "CB-9910"
    assert queue.tasks[0].issue_title == "Round-trip task A"

    # Persist to the in-memory DB.
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # Reload via rehydration and verify persistence survived the round-trip.
    import models.database as _mdm
    import services.autopilot_queue_service as _svc_mod

    _orig_mdm = _mdm.AsyncSessionLocal
    _orig_svc = _svc_mod.AsyncSessionLocal
    _mdm.AsyncSessionLocal = Sf
    _svc_mod.AsyncSessionLocal = Sf

    try:
        post_svc = AutoPilotQueueService()
        # Mark the queue as non-terminal so rehydration picks it up.
        queue.status = QueueStatus.PAUSED
        async with Sf() as db:
            await save_queue(db, queue)
            await db.commit()

        recovered_ids = await post_svc.rehydrate_from_db()
        assert queue.id in recovered_ids, "Queue should be rehydrated"

        rehydrated = post_svc._queues[queue.id]
        for task in rehydrated.tasks:
            assert task.issue_key == "CB-9910", (
                f"After save+rehydrate, task issue_key must be 'CB-9910', "
                f"got {task.issue_key!r} — DB did not persist the key (CB-2734)"
            )
            assert task.issue_title == "Round-trip task A", (
                f"After save+rehydrate, task issue_title must match, "
                f"got {task.issue_title!r}"
            )
    finally:
        _mdm.AsyncSessionLocal = _orig_mdm
        _svc_mod.AsyncSessionLocal = _orig_svc


# ---------------------------------------------------------------------------
# CB-2741 regression tests — crash-interrupted tasks reset to pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2741_crash_interrupted_task_reset_to_pending(
    engine_and_session_factory,
):
    """CB-2741 Test 1: A task in ``running`` state at crash time must be reset
    to ``pending`` (NOT ``failed``) by ``rehydrate_from_db``.

    Backend restart is not a task failure — the task was interrupted and should
    be re-run when the user resumes.  ``failed`` is reserved for real execution
    errors (subprocess non-zero exit or exception during execution).

    This test MUST fail before the CB-2738 fix and pass after.
    """
    _, Sf = engine_and_session_factory

    # ---- Pre-crash: persist a queue with one running task ----
    pre_svc = AutoPilotQueueService()
    queue = _make_queue(n_tasks=3)
    queue.tasks[0].status = TaskStatus.COMPLETED
    queue.tasks[1].status = TaskStatus.RUNNING  # interrupted by backend crash
    queue.tasks[2].status = TaskStatus.PENDING
    queue.current_index = 1
    queue.status = QueueStatus.RUNNING
    pre_svc._queues[queue.id] = queue

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # ---- Post-crash: fresh service simulating backend restart ----
    post_svc = AutoPilotQueueService()
    recovered_ids = await post_svc.rehydrate_from_db()

    assert recovered_ids == [queue.id], "Queue should be recovered after restart"
    rehydrated = post_svc._queues[queue.id]

    # Queue itself: paused / crash_recovery (manual resume required)
    assert rehydrated.status == QueueStatus.PAUSED
    assert rehydrated.pause_reason == "crash_recovery"

    by_order = {t.order: t for t in rehydrated.tasks}

    # Completed task must remain COMPLETED
    assert by_order[0].status == TaskStatus.COMPLETED, (
        "Completed task should not be touched by crash recovery"
    )

    # CB-2738 — the key assertion: interrupted task -> PENDING, not FAILED
    interrupted = by_order[1]
    assert interrupted.status == TaskStatus.PENDING, (
        f"CB-2741: interrupted task must be PENDING after rehydration, "
        f"got {interrupted.status!r}. Backend restart is NOT a task failure."
    )
    assert interrupted.error is None, (
        f"CB-2741: interrupted task must have no failureReason, "
        f"got {interrupted.error!r}"
    )
    assert interrupted.session_id is None, (
        "CB-2741: interrupted task's sessionId must be cleared on rehydration"
    )
    assert interrupted.started_at is None, (
        "CB-2741: interrupted task's startedAt must be cleared on rehydration"
    )

    # Pending task must still be PENDING
    assert by_order[2].status == TaskStatus.PENDING, (
        "Pending task should remain PENDING after crash recovery"
    )


@pytest.mark.asyncio
async def test_cb2741_real_execution_failure_stays_failed(
    engine_and_session_factory,
):
    """CB-2741 Test 2: A task that genuinely failed (status already ``failed``
    in the DB, e.g. from a non-zero subprocess exit) must remain ``failed``
    after rehydration — the crash-recovery path only touches ``running`` tasks.

    This distinguishes a real execution failure from a crash-interrupted task
    and ensures we don't accidentally clear legitimate failure reasons.
    """
    _, Sf = engine_and_session_factory

    # ---- Pre-crash: persist a queue with one genuinely-failed task ----
    pre_svc = AutoPilotQueueService()
    queue = _make_queue(n_tasks=3)
    queue.tasks[0].status = TaskStatus.COMPLETED
    # Task 1 already failed BEFORE the crash (e.g. subprocess non-zero exit).
    queue.tasks[1].status = TaskStatus.FAILED
    queue.tasks[1].error = "subprocess exited with code 1"
    queue.tasks[2].status = TaskStatus.PENDING
    # Queue was paused (e.g. on_fail=TERMINATE) before the crash.
    queue.status = QueueStatus.PAUSED
    queue.current_index = 2
    pre_svc._queues[queue.id] = queue

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # ---- Post-crash: fresh service simulating backend restart ----
    post_svc = AutoPilotQueueService()
    recovered_ids = await post_svc.rehydrate_from_db()

    assert recovered_ids == [queue.id], "Queue should be recovered after restart"
    rehydrated = post_svc._queues[queue.id]

    by_order = {t.order: t for t in rehydrated.tasks}

    # The genuinely-failed task must remain FAILED — crash recovery must not
    # touch it because its status was already ``failed`` (not ``running``)
    # at the time of the crash.
    failed_task = by_order[1]
    assert failed_task.status == TaskStatus.FAILED, (
        f"CB-2741: a task that genuinely failed before the crash must remain "
        f"FAILED after rehydration, got {failed_task.status!r}"
    )
    assert failed_task.error == "subprocess exited with code 1", (
        f"CB-2741: genuine failure reason must be preserved, "
        f"got {failed_task.error!r}"
    )


# ---------------------------------------------------------------------------
# CB-2743 regression — get_or_load_queue DB fallback for task-reset endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cb2743_get_or_load_queue_finds_db_only_paused_queue(
    engine_and_session_factory,
):
    """CB-2743 Test 1: get_or_load_queue must find a paused queue that exists
    only in the DB (not in memory) — i.e. after a backend restart where the
    user has NOT yet triggered an explicit resume/rehydration.

    Before the CB-2743 fix, get_queue() returned None for such queues and the
    reset-task endpoint responded 404.  After the fix, get_or_load_queue()
    loads the queue from DB, caches it in memory, and returns it.
    """
    _, Sf = engine_and_session_factory

    # Build a paused queue with 4 failed tasks (mirrors the real CB-2038 queue
    # that triggered the bug report: status=paused, pauseReason=crash_recovery,
    # 4 tasks with status=failed).
    queue = _make_queue(n_tasks=4)
    queue.status = QueueStatus.PAUSED
    queue.pause_reason = "crash_recovery"
    for task in queue.tasks:
        task.status = TaskStatus.FAILED
        task.error = "Process exited with code 1"

    # Persist to DB (mirrors what the backend wrote before the crash).
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # Fresh service instance — queue is NOT in memory.
    import models.database as _mdm
    import services.autopilot_queue_service as _svc_mod

    _orig_mdm = _mdm.AsyncSessionLocal
    _orig_svc = _svc_mod.AsyncSessionLocal
    _mdm.AsyncSessionLocal = Sf
    _svc_mod.AsyncSessionLocal = Sf

    try:
        svc = AutoPilotQueueService()

        # Pre-condition: queue is NOT in memory.
        assert svc.get_queue(queue.id) is None, (
            "Pre-condition failed: queue should not be in memory before get_or_load_queue"
        )

        # CB-2743: get_or_load_queue should find it in DB.
        loaded = await svc.get_or_load_queue(queue.id)

        assert loaded is not None, (
            "CB-2743: get_or_load_queue returned None for a DB-only paused queue — "
            "the reset-task endpoint would have returned 404"
        )
        assert loaded.id == queue.id
        assert loaded.status == QueueStatus.PAUSED
        assert loaded.pause_reason == "crash_recovery"
        assert len(loaded.tasks) == 4
        assert all(t.status == TaskStatus.FAILED for t in loaded.tasks)

        # The queue should now be cached in memory.
        assert svc.get_queue(queue.id) is loaded, (
            "CB-2743: get_or_load_queue must cache the loaded queue in _queues"
        )

        # A second call must return the cached instance (no new DB hit).
        loaded2 = await svc.get_or_load_queue(queue.id)
        assert loaded2 is loaded, (
            "CB-2743: second call must return the same cached object"
        )

    finally:
        _mdm.AsyncSessionLocal = _orig_mdm
        _svc_mod.AsyncSessionLocal = _orig_svc


@pytest.mark.asyncio
async def test_cb2743_task_reset_on_db_only_queue_succeeds(
    engine_and_session_factory,
):
    """CB-2743 Test 2: After get_or_load_queue loads the queue from DB, a
    task-reset operation (resetting a FAILED task to PENDING) must succeed
    and persist the change back to the DB.

    This is the direct regression for the 'Retry all failed' 404 bug:
    the queue exists in DB (paused/crash_recovery) but was NOT in memory
    after a backend restart, so reset-task returned 404 before the fix.
    """
    _, Sf = engine_and_session_factory

    # Build a paused queue with 2 failed tasks.
    queue = _make_queue(n_tasks=2)
    queue.status = QueueStatus.PAUSED
    queue.pause_reason = "crash_recovery"
    for task in queue.tasks:
        task.status = TaskStatus.FAILED
        task.error = "Process exited with code 1"

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    import models.database as _mdm
    import services.autopilot_queue_service as _svc_mod
    from utils.autopilot_repository import load_queue as _load_queue_from_db

    _orig_mdm = _mdm.AsyncSessionLocal
    _orig_svc = _svc_mod.AsyncSessionLocal
    _mdm.AsyncSessionLocal = Sf
    _svc_mod.AsyncSessionLocal = Sf

    try:
        svc = AutoPilotQueueService()

        # Load via the new helper (simulates what the endpoint now does).
        loaded = await svc.get_or_load_queue(queue.id)
        assert loaded is not None, "Queue should be loadable from DB"

        # Verify pre-condition: task 0 is FAILED.
        task0 = next(t for t in loaded.tasks if t.order == 0)
        assert task0.status == TaskStatus.FAILED, "Pre-condition: task 0 must be FAILED"

        # Simulate the reset logic from the endpoint.
        task0.status = TaskStatus.PENDING
        task0.error = None
        task0.session_id = None
        task0.started_at = None
        task0.completed_at = None

        # Persist (same as the endpoint does).
        async with Sf() as db:
            await save_queue(db, loaded)
            await db.commit()

        # Verify DB reflects the reset — load fresh from DB (no cache).
        async with Sf() as db:
            record = await _load_queue_from_db(db, queue.id)

        assert record is not None, "Queue record must still exist in DB after reset"
        task_records = sorted(record.tasks, key=lambda t: t.sequence)

        assert task_records[0].status == "pending", (
            f"CB-2743: task 0 must be 'pending' in DB after reset, "
            f"got {task_records[0].status!r}"
        )
        assert task_records[0].failureReason is None, (
            "CB-2743: task 0 failureReason must be cleared after reset"
        )

        # Task 1 must remain FAILED (untouched).
        assert task_records[1].status == "failed", (
            f"CB-2743: task 1 must remain 'failed', got {task_records[1].status!r}"
        )

    finally:
        _mdm.AsyncSessionLocal = _orig_mdm
        _svc_mod.AsyncSessionLocal = _orig_svc


@pytest.mark.asyncio
async def test_cb2743_get_or_load_queue_returns_none_for_unknown_id(
    engine_and_session_factory,
):
    """CB-2743 Test 3: get_or_load_queue must return None (not raise) when the
    queue_id does not exist in memory OR in the DB.  This preserves the 404
    response for genuinely unknown queue IDs."""
    _, Sf = engine_and_session_factory

    import models.database as _mdm
    import services.autopilot_queue_service as _svc_mod

    _orig_mdm = _mdm.AsyncSessionLocal
    _orig_svc = _svc_mod.AsyncSessionLocal
    _mdm.AsyncSessionLocal = Sf
    _svc_mod.AsyncSessionLocal = Sf

    try:
        svc = AutoPilotQueueService()
        result = await svc.get_or_load_queue("non-existent-queue-id-99999")
        assert result is None, (
            "CB-2743: get_or_load_queue must return None for an unknown queue_id"
        )
    finally:
        _mdm.AsyncSessionLocal = _orig_mdm
        _svc_mod.AsyncSessionLocal = _orig_svc

# ---------------------------------------------------------------------------
# CB-2794 — persist auto_resume_attempts across rehydration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_resume_attempts_persists_across_rehydrate(
    engine_and_session_factory,
):
    """CB-2794: auto_resume_attempts must survive a backend restart.

    Sequence:
    1. Build a WAITING_RESET queue with auto_resume_attempts=2.
    2. Persist via save_queue.
    3. Construct a fresh service instance (simulates restart).
    4. Rehydrate — assert counter is restored to 2, not reset to 0.
    """
    _, Sf = engine_and_session_factory

    queue = _make_queue(n_tasks=2)
    queue.status = QueueStatus.WAITING_RESET
    queue.pause_reason = "token_exhaustion"
    queue.auto_resume_attempts = 2

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # Switch to non-terminal status so rehydration picks it up.
    import models.database as _mdm
    import services.autopilot_queue_service as _svc_mod

    _orig_mdm = _mdm.AsyncSessionLocal
    _orig_svc = _svc_mod.AsyncSessionLocal
    _mdm.AsyncSessionLocal = Sf
    _svc_mod.AsyncSessionLocal = Sf

    try:
        post_svc = AutoPilotQueueService()
        recovered_ids = await post_svc.rehydrate_from_db()

        assert queue.id in recovered_ids, "Queue must be rehydrated"
        rehydrated = post_svc._queues[queue.id]

        assert rehydrated.auto_resume_attempts == 2, (
            f"CB-2794: auto_resume_attempts must survive restart; "
            f"expected 2, got {rehydrated.auto_resume_attempts}"
        )
    finally:
        _mdm.AsyncSessionLocal = _orig_mdm
        _svc_mod.AsyncSessionLocal = _orig_svc


def test_auto_resume_attempts_default_zero_for_legacy_rows():
    """CB-2794: _record_to_queue must return 0 for auto_resume_attempts when
    the record has no autoResumeAttempts attribute (pre-migration row).

    SQLite's NOT NULL constraint prevents us from writing NULL via an UPDATE
    on an in-memory test DB, so we exercise the guard directly by constructing
    a minimal mock record object that lacks the attribute entirely — this is
    the exact condition the getattr(..., 0) guard protects against.
    """
    import types

    # Minimal stub that mirrors the columns _record_to_queue reads
    # but intentionally omits autoResumeAttempts.
    record = types.SimpleNamespace(
        id="legacy-queue-id",
        featureId="feat-1",
        projectId="p-test",
        project_path="",
        config='{"on_success":"MARK_WAITING_QA","on_fail":"CONTINUE_MARK_FAILED",'
               '"max_retries":3,"provider":"claude_code","model":null,'
               '"project_path":"/tmp","feature_key":"CB-99"}',
        status="waiting_reset",
        tasks=[],
        currentIndex=0,
        createdAt=datetime.utcnow(),
        completedAt=None,
        pauseReason="token_exhaustion",
        resetTime=None,
        # autoResumeAttempts intentionally absent — simulates pre-migration row
    )

    rebuilt = AutoPilotQueueService._record_to_queue(record)

    assert rebuilt.auto_resume_attempts == 0, (
        f"CB-2794: missing autoResumeAttempts must default to 0, "
        f"got {rebuilt.auto_resume_attempts}"
    )
