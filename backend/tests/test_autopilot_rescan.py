"""
Tests for CB-2382: audit-rescan pass in AutoPilot queue.

Verifies that _rescan_subtree_for_new_tasks:
- Picks up new BACKLOG BUG/TASK issues spawned after the queue started.
- Is idempotent (second call appends 0 tasks).
- Ignores issues created before the queue started.
- Emits a 'task_appended' AutoPilotEvent with the correct payload.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select

from models.database import Base
from models.issue import Issue
from models import Project
from models.autopilot import AutoPilotEvent
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
async def engine_and_session_factory(monkeypatch):
    """In-memory SQLite + monkeypatched AsyncSessionLocal."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Sf = async_sessionmaker(engine, expire_on_commit=False)

    # Seed a project so FK constraints pass.
    async with Sf() as s:
        s.add(Project(
            id="p-rescan",
            name="rescan-test-project",
            path="/tmp/rescan-test",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    import models.database
    import services.autopilot_queue_service as svc_mod
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)

    yield engine, Sf
    await engine.dispose()


def _new_id() -> str:
    return str(uuid.uuid4())


def _make_queue(feature_id: str, started_at: datetime | None = None) -> AutoPilotQueue:
    """Build a minimal running queue with one pre-existing TASK."""
    task = QueueTask(
        issue_id=_new_id(),
        issue_key="CB-100",
        issue_title="Original task",
        order=0,
        status=TaskStatus.PENDING,
    )
    q = AutoPilotQueue(
        id=_new_id(),
        feature_id=feature_id,
        feature_key="CB-FEAT",
        project_id="p-rescan",
        project_path="/tmp/rescan-test",
        status=QueueStatus.RUNNING,
        tasks=[task],
        config=QueueConfig(),
        created_at=datetime.utcnow(),
    )
    q.started_at = started_at or datetime.utcnow()
    return q


async def _seed_issue(
    Sf,
    *,
    issue_id: str,
    parent_id: str,
    issue_type: str = "BUG",
    status: str = "BACKLOG",
    created_at: datetime | None = None,
    key: str | None = None,
    reporter: str = "AI",
) -> None:
    """Insert a minimal Issue row."""
    async with Sf() as s:
        s.add(Issue(
            id=issue_id,
            projectId="p-rescan",
            key=key or f"CB-{issue_id[:6]}",
            sequence=1,
            title=f"Auto-created {issue_type}",
            type=issue_type,
            status=status,
            reporter=reporter,
            parentId=parent_id,
            createdAt=created_at or datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()


# ---------------------------------------------------------------------------
# Test 1: rescan appends a new BACKLOG BUG spawned after queue started
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_appends_new_backlog_bug_during_run(engine_and_session_factory):
    """A BACKLOG BUG created after started_at should be appended to queue.tasks."""
    _, Sf = engine_and_session_factory

    # Seed the feature root so the BFS walk has something to find.
    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT",
            sequence=0,
            title="Feature root",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    queue = _make_queue(feature_id=feature_id, started_at=datetime.utcnow() - timedelta(seconds=10))

    # Persist initial queue so save_queue can upsert cleanly.
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    bug_id = _new_id()
    await _seed_issue(
        Sf,
        issue_id=bug_id,
        parent_id=feature_id,
        issue_type="BUG",
        status="BACKLOG",
        # created 5s after the queue started → should be picked up
        created_at=datetime.utcnow(),
    )

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    n = await svc._rescan_subtree_for_new_tasks(queue)

    assert n == 1, f"Expected 1 appended task, got {n}"
    assert len(queue.tasks) == 2, f"queue.tasks should be 2, is {len(queue.tasks)}"
    appended_task = queue.tasks[1]
    assert appended_task.issue_id == bug_id
    assert appended_task.order == 1
    assert appended_task.execution_mode == "implement"


# ---------------------------------------------------------------------------
# Test 2: idempotency — second rescan call appends 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_is_idempotent(engine_and_session_factory):
    """Running the rescan twice should not append the same issue twice."""
    _, Sf = engine_and_session_factory

    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT2",
            sequence=0,
            title="Feature root 2",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    queue = _make_queue(feature_id=feature_id, started_at=datetime.utcnow() - timedelta(seconds=10))

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    bug_id = _new_id()
    await _seed_issue(
        Sf,
        issue_id=bug_id,
        parent_id=feature_id,
        issue_type="BUG",
        status="BACKLOG",
        created_at=datetime.utcnow(),
    )

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    # First call — should append 1
    n_first = await svc._rescan_subtree_for_new_tasks(queue)
    assert n_first == 1

    # Second call — same issue already in _appended_ids, should append 0
    n_second = await svc._rescan_subtree_for_new_tasks(queue)
    assert n_second == 0, f"Expected 0 on second rescan, got {n_second}"
    assert len(queue.tasks) == 2, "No extra tasks should have been added"


# ---------------------------------------------------------------------------
# Test 3: issues created before queue.started_at are ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_ignores_pre_start_backlog_bugs(engine_and_session_factory):
    """A BACKLOG BUG that predates queue.started_at must NOT be appended."""
    _, Sf = engine_and_session_factory

    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT3",
            sequence=0,
            title="Feature root 3",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    # Queue started 60 seconds ago
    queue = _make_queue(
        feature_id=feature_id,
        started_at=datetime.utcnow() - timedelta(seconds=60),
    )

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    old_bug_id = _new_id()
    # Bug created 90s ago — i.e. BEFORE the queue started
    await _seed_issue(
        Sf,
        issue_id=old_bug_id,
        parent_id=feature_id,
        issue_type="BUG",
        status="BACKLOG",
        created_at=datetime.utcnow() - timedelta(seconds=90),
    )

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    n = await svc._rescan_subtree_for_new_tasks(queue)

    assert n == 0, f"Pre-start BUG should not be appended, got n={n}"
    assert len(queue.tasks) == 1


# ---------------------------------------------------------------------------
# Test 4: task_appended event is emitted with correct payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_emits_task_appended_event(engine_and_session_factory):
    """After appending a task, an AutoPilotEvent with type='task_appended' must exist."""
    _, Sf = engine_and_session_factory

    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT4",
            sequence=0,
            title="Feature root 4",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    queue = _make_queue(feature_id=feature_id, started_at=datetime.utcnow() - timedelta(seconds=5))

    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    bug_id = _new_id()
    bug_key = f"CB-{bug_id[:4].upper()}"
    await _seed_issue(
        Sf,
        issue_id=bug_id,
        parent_id=feature_id,
        issue_type="BUG",
        status="BACKLOG",
        created_at=datetime.utcnow(),
        key=bug_key,
    )

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    n = await svc._rescan_subtree_for_new_tasks(queue)
    assert n == 1

    # Query the audit log for the emitted event
    import json
    async with Sf() as db:
        result = await db.execute(
            select(AutoPilotEvent).where(
                AutoPilotEvent.queueId == queue.id,
                AutoPilotEvent.type == "task_appended",
            )
        )
        events = result.scalars().all()

    assert len(events) == 1, f"Expected 1 task_appended event, got {len(events)}"
    payload = json.loads(events[0].payload)
    assert payload["issueId"] == bug_id
    assert payload["issueKey"] == bug_key
    assert payload["source"] == "audit_rescan"
    assert "sequence" in payload


# ---------------------------------------------------------------------------
# Test 5: per-run cap (_RESCAN_MAX_APPENDS_PER_RUN = 25)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_respects_per_run_cap(engine_and_session_factory):
    """After 25 total appends the queue is capped; a rescan_cap_exceeded event is written."""
    import json as _json
    from services.autopilot_queue_service import _RESCAN_MAX_APPENDS_PER_RUN

    _, Sf = engine_and_session_factory

    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT5",
            sequence=0,
            title="Feature root 5",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    queue = _make_queue(feature_id=feature_id, started_at=datetime.utcnow() - timedelta(seconds=10))
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # Insert 30 eligible BUGs (more than the cap of 25)
    for i in range(30):
        bid = _new_id()
        async with Sf() as s:
            s.add(Issue(
                id=bid,
                projectId="p-rescan",
                key=f"CB-CAP{i}",
                sequence=i + 1,
                title=f"Cap bug {i}",
                type="BUG",
                status="BACKLOG",
                reporter="AI",
                parentId=feature_id,
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            ))
            await s.commit()

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    # Drive rescan until it returns 0 (cap hit)
    total = 0
    for _ in range(20):
        n = await svc._rescan_subtree_for_new_tasks(queue)
        total += n
        if n == 0:
            break

    assert queue._appended_count == _RESCAN_MAX_APPENDS_PER_RUN, (
        f"Expected _appended_count=={_RESCAN_MAX_APPENDS_PER_RUN}, got {queue._appended_count}"
    )

    # A rescan_cap_exceeded event must have been written
    async with Sf() as db:
        result = await db.execute(
            select(AutoPilotEvent).where(
                AutoPilotEvent.queueId == queue.id,
                AutoPilotEvent.type == "rescan_cap_exceeded",
            )
        )
        events = result.scalars().all()
    assert len(events) >= 1, "Expected at least one rescan_cap_exceeded event"
    payload = _json.loads(events[0].payload)
    assert payload["total_appended"] == _RESCAN_MAX_APPENDS_PER_RUN
    assert payload["max"] == _RESCAN_MAX_APPENDS_PER_RUN


# ---------------------------------------------------------------------------
# Test 6: per-iteration cap (_RESCAN_MAX_APPENDS_PER_ITERATION = 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_respects_per_iteration_cap(engine_and_session_factory):
    """A single rescan call appends at most _RESCAN_MAX_APPENDS_PER_ITERATION issues."""
    from services.autopilot_queue_service import _RESCAN_MAX_APPENDS_PER_ITERATION

    _, Sf = engine_and_session_factory

    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT6",
            sequence=0,
            title="Feature root 6",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    queue = _make_queue(feature_id=feature_id, started_at=datetime.utcnow() - timedelta(seconds=10))
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    # Insert exactly 10 eligible BUGs — more than the per-iteration cap of 5
    for i in range(10):
        bid = _new_id()
        async with Sf() as s:
            s.add(Issue(
                id=bid,
                projectId="p-rescan",
                key=f"CB-ITER{i}",
                sequence=i + 1,
                title=f"Iter bug {i}",
                type="BUG",
                status="BACKLOG",
                reporter="AI",
                parentId=feature_id,
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            ))
            await s.commit()

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    n = await svc._rescan_subtree_for_new_tasks(queue)

    assert n == _RESCAN_MAX_APPENDS_PER_ITERATION, (
        f"Expected {_RESCAN_MAX_APPENDS_PER_ITERATION} appended, got {n}"
    )


# ---------------------------------------------------------------------------
# Test 7: trusted-reporter filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_filters_by_trusted_reporter(engine_and_session_factory):
    """Only issues with reporter in _TRUSTED_REPORTERS should be appended."""
    _, Sf = engine_and_session_factory

    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT7",
            sequence=0,
            title="Feature root 7",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    queue = _make_queue(feature_id=feature_id, started_at=datetime.utcnow() - timedelta(seconds=10))
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    trusted_id = _new_id()
    untrusted_id = _new_id()

    async with Sf() as s:
        # Trusted reporter — should be appended
        s.add(Issue(
            id=trusted_id,
            projectId="p-rescan",
            key="CB-TRUST",
            sequence=1,
            title="Trusted bug",
            type="BUG",
            status="BACKLOG",
            reporter="AI",
            parentId=feature_id,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        # Untrusted reporter — must NOT be appended
        s.add(Issue(
            id=untrusted_id,
            projectId="p-rescan",
            key="CB-EXTERN",
            sequence=2,
            title="External bug",
            type="BUG",
            status="BACKLOG",
            reporter="external",
            parentId=feature_id,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    n = await svc._rescan_subtree_for_new_tasks(queue)

    assert n == 1, f"Expected 1 appended (trusted only), got {n}"
    appended_issue_ids = {t.issue_id for t in queue.tasks} - {queue.tasks[0].issue_id}
    assert trusted_id in appended_issue_ids
    assert untrusted_id not in appended_issue_ids


# ---------------------------------------------------------------------------
# Test 8: BFS depth limit (_RESCAN_MAX_DEPTH = 10)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rescan_respects_max_depth(engine_and_session_factory):
    """A BUG nested deeper than _RESCAN_MAX_DEPTH levels must NOT be appended."""
    from services.autopilot_queue_service import _RESCAN_MAX_DEPTH

    _, Sf = engine_and_session_factory

    # Build chain: FEATURE → S1 → S2 → … → S11 (11 levels below feature)
    # BUG hangs off S11, which is at depth 11 — beyond the cap of 10.
    feature_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=feature_id,
            projectId="p-rescan",
            key="CB-FEAT8",
            sequence=0,
            title="Feature root 8",
            type="FEATURE",
            status="IN_PROGRESS",
            parentId=None,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    parent_id = feature_id
    for depth_i in range(1, _RESCAN_MAX_DEPTH + 2):  # S1..S11
        story_id = _new_id()
        async with Sf() as s:
            s.add(Issue(
                id=story_id,
                projectId="p-rescan",
                key=f"CB-S{depth_i}",
                sequence=depth_i,
                title=f"Story depth {depth_i}",
                type="STORY",
                status="IN_PROGRESS",
                reporter="AI",
                parentId=parent_id,
                createdAt=datetime.utcnow(),
                updatedAt=datetime.utcnow(),
            ))
            await s.commit()
        parent_id = story_id  # S11 is the deepest

    # BUG attached to S11 (depth 12 from feature)
    deep_bug_id = _new_id()
    async with Sf() as s:
        s.add(Issue(
            id=deep_bug_id,
            projectId="p-rescan",
            key="CB-DEEPBUG",
            sequence=99,
            title="Deep bug beyond max depth",
            type="BUG",
            status="BACKLOG",
            reporter="AI",
            parentId=parent_id,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    queue = _make_queue(feature_id=feature_id, started_at=datetime.utcnow() - timedelta(seconds=10))
    async with Sf() as db:
        await save_queue(db, queue)
        await db.commit()

    svc = AutoPilotQueueService()
    svc._queues[queue.id] = queue

    n = await svc._rescan_subtree_for_new_tasks(queue)

    assert n == 0, f"BUG beyond max depth should NOT be appended, got n={n}"
    assert len(queue.tasks) == 1, "Queue should still have only the original task"
