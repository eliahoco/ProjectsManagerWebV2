"""
CB-2797 — Canonical state transitions tests.

Verifies:
1. _transition writes DB before mutating in-memory status.
2. Legal (from, to) pairs all succeed end-to-end.
3. Illegal (from, to) pairs raise IllegalStateTransitionError without
   mutating in-memory status.
4. pause_queue emits a STATE_TRANSITION event.
5. No direct queue.status = QueueStatus.X assignments remain outside of
   _transition and its two intentional-exception callers in run_queue.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import List
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.autopilot import (
    AutoPilotEvent,
    AutoPilotEventType,
    AutoPilotQueueRecord,
    _ALLOWED_TRANSITIONS,
)
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
from utils.autopilot_repository import (
    IllegalStateTransitionError,
    save_queue,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine_and_session_factory(monkeypatch):
    """In-memory SQLite engine + session factory, patched into AsyncSessionLocal."""
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

    import models.database
    import services.autopilot_queue_service as svc_mod
    import utils.autopilot_repository as repo_mod
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(repo_mod, "AsyncSessionLocal", Sf)

    yield engine, Sf
    await engine.dispose()


def _make_queue(
    qid: str | None = None,
    n_tasks: int = 1,
    status: QueueStatus = QueueStatus.PENDING,
) -> AutoPilotQueue:
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
        id=qid, feature_id="feat-1", feature_key="CB-2797",
        project_id="p-test", project_path="/tmp/test",
        status=status, tasks=tasks,
        config=QueueConfig(),
        created_at=datetime.utcnow(),
    )


async def _persist_queue_with_status(Sf, queue: AutoPilotQueue) -> None:
    """Helper: persist the queue record so transition_state can find it."""
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()


# ---------------------------------------------------------------------------
# Test 1: _transition writes DB FIRST, only then updates in-memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_writes_db_then_memory(engine_and_session_factory):
    """If transition_state raises, queue.status must NOT be mutated."""
    _, Sf = engine_and_session_factory

    queue = _make_queue(status=QueueStatus.PENDING)
    await _persist_queue_with_status(Sf, queue)

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    original_status = queue.status  # PENDING

    # Patch transition_state to raise before it writes to DB.
    with patch(
        "services.autopilot_queue_service.transition_state",
        new_callable=AsyncMock,
        side_effect=IllegalStateTransitionError("injected failure"),
    ):
        with pytest.raises(IllegalStateTransitionError):
            await svc._transition(queue, QueueStatus.RUNNING, None)

    # In-memory status must NOT have changed.
    assert queue.status == original_status, (
        f"queue.status was mutated to {queue.status!r} despite DB write failing; "
        "CB-2797 requires DB-first semantics"
    )


@pytest.mark.asyncio
async def test_transition_db_exception_leaves_memory_unchanged(engine_and_session_factory):
    """If transition_state raises OperationalError, queue.status stays unchanged."""
    from sqlalchemy.exc import OperationalError

    _, Sf = engine_and_session_factory

    queue = _make_queue(status=QueueStatus.PENDING)
    await _persist_queue_with_status(Sf, queue)

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    original_status = queue.status

    with patch(
        "services.autopilot_queue_service.transition_state",
        new_callable=AsyncMock,
        side_effect=OperationalError("disk full", None, None),
    ):
        with pytest.raises(OperationalError):
            await svc._transition(queue, QueueStatus.RUNNING, None)

    assert queue.status == original_status


# ---------------------------------------------------------------------------
# Test 2: Legal paths — parametrised over the full allow-list
# ---------------------------------------------------------------------------


def _all_legal_transitions() -> List[tuple[str, str]]:
    return list(_ALLOWED_TRANSITIONS)


@pytest.mark.asyncio
@pytest.mark.parametrize("from_s,to_s", _all_legal_transitions())
async def test_transition_legal_paths_succeed(engine_and_session_factory, from_s, to_s):
    """Every allowed (from, to) pair: DB row updated + in-memory mirrors it."""
    _, Sf = engine_and_session_factory

    from_status = QueueStatus(from_s)
    to_status = QueueStatus(to_s)

    queue = _make_queue(status=from_status)
    # Write a DB record with the from_s status so transition_state can find it.
    await _persist_queue_with_status(Sf, queue)

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    reason = "test_reason" if to_status in (QueueStatus.PAUSED, QueueStatus.WAITING_RESET) else None
    await svc._transition(queue, to_status, reason)

    # In-memory updated
    assert queue.status == to_status

    # pause_reason set correctly
    if to_status in (QueueStatus.PAUSED, QueueStatus.WAITING_RESET):
        assert queue.pause_reason == reason
    else:
        assert queue.pause_reason is None

    # DB row updated
    async with Sf() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue.id)
        )
        record = result.scalar_one()
        assert record.status == to_s
        assert record.state == to_s

    # STATE_TRANSITION event emitted
    async with Sf() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AutoPilotEvent)
            .where(AutoPilotEvent.queueId == queue.id)
            .where(AutoPilotEvent.type == AutoPilotEventType.STATE_TRANSITION)
        )
        events = result.scalars().all()
        assert len(events) >= 1
        payload = json.loads(events[-1].payload)
        assert payload["from_state"] == from_s
        assert payload["to_state"] == to_s


# ---------------------------------------------------------------------------
# Test 3: Illegal paths raise without mutating in-memory
# ---------------------------------------------------------------------------


_ILLEGAL_TRANSITIONS = [
    ("completed", "running"),   # terminal → running
    ("aborted", "paused"),      # terminal → paused
    ("completed", "aborted"),   # terminal → terminal
    ("running", "pending"),     # backward
    ("pending", "completed"),   # skip intermediate
]


@pytest.mark.asyncio
@pytest.mark.parametrize("from_s,to_s", _ILLEGAL_TRANSITIONS)
async def test_transition_illegal_paths_raise(engine_and_session_factory, from_s, to_s):
    """Illegal (from, to) pairs must raise IllegalStateTransitionError without
    mutating in-memory queue.status."""
    _, Sf = engine_and_session_factory

    from_status = QueueStatus(from_s)
    to_status = QueueStatus(to_s)

    queue = _make_queue(status=from_status)
    await _persist_queue_with_status(Sf, queue)

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    original_status = queue.status

    with pytest.raises(IllegalStateTransitionError):
        await svc._transition(queue, to_status, None)

    # In-memory must be unchanged
    assert queue.status == original_status


# ---------------------------------------------------------------------------
# Test 4: pause_queue emits STATE_TRANSITION event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_queue_emits_state_transition_event(engine_and_session_factory):
    """pause_queue must persist a STATE_TRANSITION event via _transition."""
    _, Sf = engine_and_session_factory

    queue = _make_queue(status=QueueStatus.RUNNING)
    await _persist_queue_with_status(Sf, queue)

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    result = await svc.pause_queue(queue.id)
    assert result is True

    # In-memory status must be PAUSED
    assert queue.status == QueueStatus.PAUSED
    assert queue.pause_reason == "manual"

    # DB must have STATE_TRANSITION event
    async with Sf() as db:
        from sqlalchemy import select
        rows = (await db.execute(
            select(AutoPilotEvent)
            .where(AutoPilotEvent.queueId == queue.id)
            .where(AutoPilotEvent.type == AutoPilotEventType.STATE_TRANSITION)
        )).scalars().all()

        assert len(rows) >= 1, "Expected at least one STATE_TRANSITION event from pause_queue"
        payload = json.loads(rows[-1].payload)
        assert payload["to_state"] == "paused"
        assert payload["from_state"] == "running"

    # DB record status
    async with Sf() as db:
        from sqlalchemy import select
        record = (await db.execute(
            select(AutoPilotQueueRecord).where(AutoPilotQueueRecord.id == queue.id)
        )).scalar_one()
        assert record.status == "paused"


# ---------------------------------------------------------------------------
# Test 5: No direct queue.status mutations outside _transition / run_queue boot
# ---------------------------------------------------------------------------


def test_no_direct_status_mutation_remaining():
    """Read autopilot_queue_service.py and assert no raw queue.status = QueueStatus.*
    assignments exist outside _transition and the two intentional boot-path
    exception handlers (CB-2797)."""
    import pathlib

    service_path = pathlib.Path(__file__).parent.parent / "services" / "autopilot_queue_service.py"
    source = service_path.read_text()

    lines = source.splitlines()

    # Pattern: queue.status = QueueStatus.<anything>
    mutation_re = re.compile(r"queue\.status\s*=\s*QueueStatus\.")

    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        if mutation_re.search(line):
            stripped = line.strip()
            # Allowed: inside _transition body (the canonical setter)
            # Allowed: the two explicit exception handlers in run_queue start
            #          — they carry "CB-2797: direct mutation intentional" comments
            #   We detect them by checking the surrounding 3 lines for the marker.
            # Check 6 lines of context so multi-line comments preceding the
            # mutation are captured even when separated by logger lines.
            context = "\n".join(lines[max(0, lineno - 7):lineno + 1])
            is_in_transition_method = "queue.status = new_status" in stripped
            is_intentional = (
                "CB-2797: direct mutation intentional" in context
                or "CB-2797: safety fallback" in context
            )

            if not is_in_transition_method and not is_intentional:
                violations.append((lineno, line.rstrip()))

    assert violations == [], (
        "Found unguarded queue.status direct mutations (CB-2797 requires all "
        "mutations to go through _transition):\n"
        + "\n".join(f"  L{ln}: {txt}" for ln, txt in violations)
    )
