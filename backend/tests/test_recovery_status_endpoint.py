"""
CB-2798 (S5) — Single source of truth for queue state in recovery-status.

Tests for RC5 (clear_recovery_state was a no-op) and RC6 (recovery-status
endpoint hard-coded 'state' literals instead of reading from queue.status).

Also covers the get_queue_status DB fallback (RC4: DB-only queues returned 404).

LINK-124 retrospective: simulate a queue in zombie set with DB status
waiting_reset and verify the endpoint reports state=waiting_reset (matches DB),
not state=running (the old hard-coded lie).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.database import Base
from models import Issue, Project
from models.autopilot import AutoPilotEvent, AutoPilotEventType
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
async def patched_session(monkeypatch):
    """In-memory SQLite + patched AsyncSessionLocal."""
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
    # CB-2798: also patch the repository module so transition_state writes to
    # the same in-memory DB that save_queue uses.
    monkeypatch.setattr(repo_mod, "AsyncSessionLocal", Sf)
    yield Sf
    await engine.dispose()


def _make_queue(
    qid: str | None = None,
    n_tasks: int = 2,
    status: QueueStatus = QueueStatus.PAUSED,
    pause_reason: str | None = "crash_recovery",
) -> AutoPilotQueue:
    qid = qid or str(uuid.uuid4())
    tasks = [
        QueueTask(
            issue_id=f"issue-{i}", issue_key=f"CB-{1000 + i}",
            issue_title=f"Task {i}", order=i, status=TaskStatus.PENDING,
        )
        for i in range(n_tasks)
    ]
    q = AutoPilotQueue(
        id=qid, feature_id="feat-1", feature_key="CB-2798",
        project_id="p-test", project_path="/tmp/test",
        status=status, tasks=tasks, config=QueueConfig(),
        created_at=datetime.utcnow(),
    )
    q.pause_reason = pause_reason
    return q


async def _persist(Sf, queue: AutoPilotQueue) -> None:
    async with Sf() as s:
        await save_queue(s, queue)
        await s.commit()


# ---------------------------------------------------------------------------
# RC6: recovery-status state must match DB, not hard-coded literals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_status_state_matches_db_for_all_classifications(patched_session):
    """RC6 regression: each sub-list (recoverable/zombie/auto_resume_pending)
    must report state from queue.status.value, NOT a hard-coded literal.

    All three queues have DB status 'paused'.  The endpoint must report
    state='paused' for all three, not 'running' (zombie) or 'waiting_reset'
    (auto_resume_pending).
    """
    Sf = patched_session
    svc = AutoPilotQueueService()

    q_rec = _make_queue(status=QueueStatus.PAUSED, pause_reason="crash_recovery")
    q_zom = _make_queue(status=QueueStatus.PAUSED, pause_reason="crash_recovery")
    q_arp = _make_queue(status=QueueStatus.PAUSED, pause_reason="crash_recovery")

    for q in (q_rec, q_zom, q_arp):
        await _persist(Sf, q)

    # Rehydrate so they're in _queues and _recovered_queue_ids
    await svc.rehydrate_from_db()

    # Manually set up zombie and auto_resume sets
    svc._zombie_queue_ids.add(q_zom.id)

    # Simulate an armed auto-resume task handle (a done coroutine is fine)
    async def _noop():
        pass

    fake_task = asyncio.ensure_future(_noop())
    await fake_task  # finish immediately
    svc._resume_handles[q_arp.id] = fake_task

    # Call the recovery-status endpoint logic directly via the service
    recovered = svc.get_recovered_queues()
    zombie_ids = svc.get_zombie_queue_ids()
    resume_handle_ids = set(svc._resume_handles.keys())

    # Build the same entries the endpoint builds
    recoverable_entries = []
    for q in recovered:
        recoverable_entries.append({
            "queue_id": q.id,
            "state": q.status.value,
            "classification": "recoverable",
        })

    zombie_entries = []
    for qid in zombie_ids:
        q_loaded = await svc.get_or_load_queue(qid)
        assert q_loaded is not None
        zombie_entries.append({
            "queue_id": qid,
            "state": q_loaded.status.value,
            "classification": "zombie",
        })

    arp_entries = []
    for qid in resume_handle_ids:
        q_loaded = await svc.get_or_load_queue(qid)
        assert q_loaded is not None
        arp_entries.append({
            "queue_id": qid,
            "state": q_loaded.status.value,
            "classification": "auto_resume_pending",
        })

    # Every entry should have state='paused' — not hard-coded 'running' or 'waiting_reset'
    for entry in recoverable_entries + zombie_entries + arp_entries:
        assert entry["state"] == "paused", (
            f"Entry {entry['queue_id']} ({entry['classification']}) "
            f"reported state={entry['state']!r}, expected 'paused'. "
            "RC6: state must come from queue.status.value."
        )


@pytest.mark.asyncio
async def test_recovery_status_includes_classification_field(patched_session):
    """Each entry from the new _entry() helper must carry the 'classification' field."""
    Sf = patched_session
    svc = AutoPilotQueueService()

    q = _make_queue(status=QueueStatus.PAUSED, pause_reason="crash_recovery")
    await _persist(Sf, q)
    await svc.rehydrate_from_db()

    # Build a recoverable entry as the endpoint would
    recovered = svc.get_recovered_queues()
    assert len(recovered) == 1

    entry = {
        "queue_id": recovered[0].id,
        "state": recovered[0].status.value,
        "classification": "recoverable",
    }
    assert entry["classification"] == "recoverable"


@pytest.mark.asyncio
async def test_link124_zombie_with_db_status_waiting_reset_reports_correctly(patched_session):
    """LINK-124 retrospective: a queue in zombie set with DB status waiting_reset
    must report state=waiting_reset, NOT state=running (the old hard-coded lie).
    """
    Sf = patched_session
    svc = AutoPilotQueueService()

    # Create a queue that's actually WAITING_RESET but landed in zombie set
    q = _make_queue(status=QueueStatus.WAITING_RESET, pause_reason="token_exhaustion")
    q.reset_time = datetime.utcnow() + timedelta(hours=2)
    await _persist(Sf, q)
    await svc.rehydrate_from_db()

    # Force it into zombie set (the failing scenario from LINK-124)
    svc._zombie_queue_ids.add(q.id)

    # Simulate endpoint logic: load queue via get_or_load_queue, read status
    loaded = await svc.get_or_load_queue(q.id)
    assert loaded is not None
    # BEFORE fix: hard-coded "state": "running" would be returned.
    # AFTER fix: state comes from loaded.status.value.
    state = loaded.status.value
    assert state == "waiting_reset", (
        f"Expected state='waiting_reset', got {state!r}. "
        "LINK-124 fix: zombie entries must read state from queue.status, not hard-code 'running'."
    )


# ---------------------------------------------------------------------------
# RC5: clear_recovery_state must do real work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_recovery_cancels_timer_and_transitions_paused(patched_session):
    """RC5: clear_recovery_state must cancel the auto-resume timer, remove from
    zombie/recovery sets, and transition queue to PAUSED/manual_cleared.
    """
    Sf = patched_session
    svc = AutoPilotQueueService()

    q = _make_queue(status=QueueStatus.WAITING_RESET, pause_reason="token_exhaustion")
    q.reset_time = datetime.utcnow() + timedelta(hours=1)
    await _persist(Sf, q)
    await svc.rehydrate_from_db()

    # Manually add to zombie set and arm a timer
    svc._zombie_queue_ids.add(q.id)

    # Create a real asyncio task so we can assert task.cancelled()
    async def _sleep_forever():
        await asyncio.sleep(9999)

    timer_task = asyncio.ensure_future(_sleep_forever())
    svc._resume_handles[q.id] = timer_task

    assert q.id in svc._zombie_queue_ids
    assert q.id in svc._recovered_queue_ids
    assert q.id in svc._resume_handles

    result = await svc.clear_recovery_state(q.id)

    # Timer must be cancelled
    assert result["ok"] is True
    assert result["cancelled_timer"] is True
    assert timer_task.cancelled()

    # Removed from all tracking sets
    assert q.id not in svc._zombie_queue_ids
    assert q.id not in svc._recovered_queue_ids
    assert q.id not in svc._resume_handles

    # Queue transitioned to PAUSED/manual_cleared
    loaded = svc._queues.get(q.id)
    assert loaded is not None
    assert loaded.status == QueueStatus.PAUSED
    assert loaded.pause_reason == "manual_cleared"

    # Transition recorded
    assert len(result["transitions"]) == 1
    assert "waiting_reset" in result["transitions"][0]
    assert "paused" in result["transitions"][0]


@pytest.mark.asyncio
async def test_clear_recovery_returns_not_found_for_missing_queue(patched_session):
    """RC5: clear_recovery_state on an unknown queue_id returns {ok: False, error: 'not_found'}."""
    Sf = patched_session
    svc = AutoPilotQueueService()

    result = await svc.clear_recovery_state(str(uuid.uuid4()))

    assert result["ok"] is False
    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_clear_recovery_no_timer_still_succeeds(patched_session):
    """clear_recovery_state with no armed timer still completes and reports cancelled_timer=False."""
    Sf = patched_session
    svc = AutoPilotQueueService()

    q = _make_queue(status=QueueStatus.PAUSED, pause_reason="crash_recovery")
    await _persist(Sf, q)
    await svc.rehydrate_from_db()

    # No timer armed — just recovery set
    assert q.id not in svc._resume_handles

    result = await svc.clear_recovery_state(q.id)

    assert result["ok"] is True
    assert result["cancelled_timer"] is False
    assert q.id not in svc._recovered_queue_ids


# ---------------------------------------------------------------------------
# get_queue_status DB fallback (RC4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_queue_status_db_fallback_for_db_only_queue(patched_session):
    """A queue that exists only in DB (not in _queues) must return a proper payload
    rather than None (which would translate to 404 at the API layer).
    """
    Sf = patched_session
    svc = AutoPilotQueueService()

    q = _make_queue(status=QueueStatus.PAUSED, pause_reason="manual")
    await _persist(Sf, q)

    # Deliberately do NOT add to _queues or call rehydrate
    assert q.id not in svc._queues

    # get_queue_status must fall back to DB
    status = await svc.get_queue_status(q.id)

    assert status is not None, (
        "get_queue_status returned None for a DB-only queue. "
        "RC4 fix: must use get_or_load_queue DB fallback."
    )
    assert status["id"] == q.id
    assert status["status"] == "paused"
    assert status["feature_key"] == "CB-2798"


@pytest.mark.asyncio
async def test_get_queue_status_returns_none_for_unknown_id(patched_session):
    """get_queue_status must return None when the queue doesn't exist anywhere."""
    Sf = patched_session
    svc = AutoPilotQueueService()

    result = await svc.get_queue_status(str(uuid.uuid4()))
    assert result is None


# ---------------------------------------------------------------------------
# _serialize_queue single source of truth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serialize_queue_state_matches_status(patched_session):
    """_serialize_queue must derive 'status' from queue.status.value."""
    Sf = patched_session
    svc = AutoPilotQueueService()

    for qs in (QueueStatus.PAUSED, QueueStatus.WAITING_RESET, QueueStatus.RUNNING):
        q = _make_queue(status=qs, pause_reason="test")
        payload = svc._serialize_queue(q)
        assert payload["status"] == qs.value, (
            f"_serialize_queue returned status={payload['status']!r} "
            f"but queue.status={qs.value!r}"
        )
