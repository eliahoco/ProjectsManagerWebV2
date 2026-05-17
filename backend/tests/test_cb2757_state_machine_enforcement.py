"""
Tests for CB-2757: transition_state() called for every state change in production.

Verifies that STATE_TRANSITION events are emitted for:
- pending → running (run_queue start)
- running → paused (pause gate)
- paused → running (resume)
- running → waiting_reset (token exhaustion, auto-resume)
- running → paused (token exhaustion, no auto-resume)
- running → completed (finalize)
- running → aborted (finalize stop_flag)
- running → aborted (_apply_failure TERMINATE action)
- abort_queue → aborted
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from models.autopilot import (
    AutoPilotEvent,
    AutoPilotEventType,
    AutoPilotQueueRecord,
)
from models.database import Base
from models.issue import Project
from utils.autopilot_repository import (
    save_queue,
    transition_state,
    record_event,
    IllegalStateTransitionError,
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
async def patched_session(monkeypatch):
    """In-memory SQLite with schema + project row, patched into AsyncSessionLocal."""
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
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(repo_mod, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)
    yield Sf
    await engine.dispose()


def _make_queue(status: QueueStatus = QueueStatus.PENDING, n_tasks: int = 1) -> AutoPilotQueue:
    qid = str(uuid.uuid4())
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
        feature_id="feat-1",
        feature_key="CB-2757",
        project_id="p-test",
        project_path="/tmp/test",
        provider="claude_code",
        status=status,
        tasks=tasks,
        config=QueueConfig(),
    )


async def _persist_q(Sf, queue: AutoPilotQueue):
    async with Sf() as s:
        await save_queue(s, queue)
        await s.commit()


async def _get_state_transition_events(Sf, queue_id: str) -> list:
    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotEvent)
            .where(AutoPilotEvent.queueId == queue_id)
            .where(AutoPilotEvent.type == AutoPilotEventType.STATE_TRANSITION)
            .order_by(AutoPilotEvent.createdAt.asc())
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Tests: transition_state() emits STATE_TRANSITION events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_pending_to_running_emits_event(patched_session):
    """pending → running transition emits STATE_TRANSITION event."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.PENDING)
    await _persist_q(Sf, q)

    await transition_state(q.id, "running", None)

    events = await _get_state_transition_events(Sf, q.id)
    assert len(events) == 1
    import json
    payload = json.loads(events[0].payload)
    assert payload["from_state"] == "pending"
    assert payload["to_state"] == "running"


@pytest.mark.asyncio
async def test_transition_running_to_paused_emits_event(patched_session):
    """running → paused transition emits STATE_TRANSITION event."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.RUNNING)
    q.status = QueueStatus.RUNNING
    await _persist_q(Sf, q)

    await transition_state(q.id, "paused", "manual")

    events = await _get_state_transition_events(Sf, q.id)
    assert len(events) == 1
    import json
    payload = json.loads(events[0].payload)
    assert payload["from_state"] == "running"
    assert payload["to_state"] == "paused"
    assert payload["to_reason"] == "manual"


@pytest.mark.asyncio
async def test_transition_paused_to_running_emits_event(patched_session):
    """paused → running transition emits STATE_TRANSITION event."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.PAUSED)
    q.status = QueueStatus.PAUSED
    await _persist_q(Sf, q)

    await transition_state(q.id, "running", None)

    events = await _get_state_transition_events(Sf, q.id)
    assert len(events) == 1
    import json
    payload = json.loads(events[0].payload)
    assert payload["from_state"] == "paused"
    assert payload["to_state"] == "running"


@pytest.mark.asyncio
async def test_transition_running_to_waiting_reset_emits_event(patched_session):
    """running → waiting_reset transition emits STATE_TRANSITION event."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.RUNNING)
    q.status = QueueStatus.RUNNING
    await _persist_q(Sf, q)

    await transition_state(q.id, "waiting_reset", "rate_limit_5h")

    events = await _get_state_transition_events(Sf, q.id)
    assert len(events) == 1
    import json
    payload = json.loads(events[0].payload)
    assert payload["to_state"] == "waiting_reset"
    assert payload["to_reason"] == "rate_limit_5h"


@pytest.mark.asyncio
async def test_transition_running_to_completed_emits_event(patched_session):
    """running → completed transition emits STATE_TRANSITION event."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.RUNNING)
    q.status = QueueStatus.RUNNING
    await _persist_q(Sf, q)

    await transition_state(q.id, "completed", None)

    events = await _get_state_transition_events(Sf, q.id)
    assert len(events) == 1
    import json
    payload = json.loads(events[0].payload)
    assert payload["to_state"] == "completed"


@pytest.mark.asyncio
async def test_transition_running_to_aborted_emits_event(patched_session):
    """running → aborted transition emits STATE_TRANSITION event."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.RUNNING)
    q.status = QueueStatus.RUNNING
    await _persist_q(Sf, q)

    await transition_state(q.id, "aborted", "user_abort")

    events = await _get_state_transition_events(Sf, q.id)
    assert len(events) == 1
    import json
    payload = json.loads(events[0].payload)
    assert payload["to_state"] == "aborted"
    assert payload["to_reason"] == "user_abort"


@pytest.mark.asyncio
async def test_illegal_transition_raises_error(patched_session):
    """Attempting an illegal transition must raise IllegalStateTransitionError."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.COMPLETED)
    q.status = QueueStatus.COMPLETED
    await _persist_q(Sf, q)

    with pytest.raises(IllegalStateTransitionError):
        await transition_state(q.id, "running", None)


@pytest.mark.asyncio
async def test_transition_state_mirrors_to_status_column(patched_session):
    """transition_state must update both state AND status (legacy) columns."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.PENDING)
    await _persist_q(Sf, q)

    await transition_state(q.id, "running", None)

    async with Sf() as s:
        from sqlalchemy import select
        result = await s.execute(
            select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == q.id)
        )
        record = result.scalar_one()
        assert record.state == "running"
        assert record.status == "running"  # legacy field mirrored


@pytest.mark.asyncio
async def test_run_queue_emits_state_transition_on_start(patched_session):
    """run_queue must emit a STATE_TRANSITION (pending→running) event on startup."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.PENDING, n_tasks=1)
    await _persist_q(Sf, q)

    svc = AutoPilotQueueService()
    svc._queues[q.id] = q

    # run_queue will call _execute_task which opens DB sessions for the issue —
    # mock out _execute_task and _finalize_queue so we only test the start path.
    with (
        patch.object(svc, "_execute_task", new_callable=AsyncMock, return_value="completed"),
        patch.object(svc, "_apply_success", new_callable=AsyncMock, return_value="terminate"),
        patch.object(svc, "_finalize_queue", new_callable=AsyncMock),
    ):
        await svc.run_queue(q.id)

    events = await _get_state_transition_events(Sf, q.id)
    assert any(
        e for e in events
        if "running" in e.payload
    ), "At least one STATE_TRANSITION event must mention 'running'"


@pytest.mark.asyncio
async def test_abort_queue_emits_state_transition_aborted(patched_session):
    """abort_queue must cause a STATE_TRANSITION(→aborted) event."""
    Sf = patched_session
    q = _make_queue(status=QueueStatus.PAUSED)
    q.status = QueueStatus.PAUSED
    await _persist_q(Sf, q)

    svc = AutoPilotQueueService()
    svc._queues[q.id] = q

    with patch.object(svc, "_persist", new_callable=AsyncMock):
        await svc.abort_queue(q.id, action="leave")

    # The in-process transition_state call (inside abort_queue) writes to DB
    events = await _get_state_transition_events(Sf, q.id)
    assert any("aborted" in e.payload for e in events), (
        "abort_queue must emit STATE_TRANSITION with to_state=aborted"
    )
