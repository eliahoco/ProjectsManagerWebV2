"""
Feature-flag tests for AutoPilot persistence (CB-1951 E10).

Verifies that toggling ``_persistence_enabled`` correctly turns
``_persist`` and ``rehydrate_from_db`` into no-ops, restoring pre-E1
in-memory-only behaviour.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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


@pytest_asyncio.fixture
async def patched_session(monkeypatch):
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


def _make_queue():
    return AutoPilotQueue(
        id=str(uuid.uuid4()),
        feature_id="feat-1", feature_key="CB-1951",
        project_id="p-test", project_path="/tmp/test",
        status=QueueStatus.RUNNING,
        tasks=[QueueTask(
            issue_id="issue-0", issue_key="CB-1000",
            issue_title="t", order=0, status=TaskStatus.PENDING,
        )],
        config=QueueConfig(),
    )


@pytest.mark.asyncio
async def test_persist_is_noop_when_disabled(patched_session):
    """With the flag off, _persist should NOT create any DB rows."""
    Sf = patched_session
    svc = AutoPilotQueueService()
    svc._persistence_enabled = False

    q = _make_queue()
    svc._queues[q.id] = q
    await svc._persist(q, "task_started", {"issue_key": "CB-1000"})

    async with Sf() as db:
        from models.autopilot import AutoPilotQueueRecord
        from sqlalchemy import select
        rows = (await db.execute(select(AutoPilotQueueRecord))).scalars().all()
        assert len(rows) == 0


@pytest.mark.asyncio
async def test_persist_writes_when_enabled(patched_session):
    Sf = patched_session
    svc = AutoPilotQueueService()
    svc._persistence_enabled = True

    q = _make_queue()
    svc._queues[q.id] = q
    await svc._persist(q, "task_started", {"issue_key": "CB-1000"})

    async with Sf() as db:
        from models.autopilot import AutoPilotQueueRecord, AutoPilotEvent
        from sqlalchemy import select
        rows = (await db.execute(select(AutoPilotQueueRecord))).scalars().all()
        events = (await db.execute(select(AutoPilotEvent))).scalars().all()
        assert len(rows) == 1
        assert len(events) == 1


@pytest.mark.asyncio
async def test_rehydrate_is_noop_when_disabled(patched_session):
    """With the flag off, rehydrate_from_db should not query the DB
    at all and should return [] cleanly."""
    Sf = patched_session
    # Pre-populate a queue while the flag is ON
    pre_svc = AutoPilotQueueService()
    pre_svc._persistence_enabled = True
    q = _make_queue()
    pre_svc._queues[q.id] = q
    await pre_svc._persist(q, "created")

    # Fresh service with flag OFF should NOT see the persisted queue
    post_svc = AutoPilotQueueService()
    post_svc._persistence_enabled = False
    recovered = await post_svc.rehydrate_from_db()
    assert recovered == []
    assert post_svc._queues == {}


def test_get_set_persistence_enabled():
    svc = AutoPilotQueueService()
    initial = svc.get_persistence_enabled()
    svc.set_persistence_enabled(not initial)
    assert svc.get_persistence_enabled() != initial
    svc.set_persistence_enabled(initial)
    assert svc.get_persistence_enabled() == initial


def test_env_var_disables_persistence(monkeypatch):
    """AUTOPILOT_PERSISTENCE_ENABLED=false should disable at construction."""
    monkeypatch.setenv("AUTOPILOT_PERSISTENCE_ENABLED", "false")
    svc = AutoPilotQueueService()
    assert svc.get_persistence_enabled() is False


def test_env_var_default_is_enabled(monkeypatch):
    """No env var set → persistence enabled."""
    monkeypatch.delenv("AUTOPILOT_PERSISTENCE_ENABLED", raising=False)
    svc = AutoPilotQueueService()
    assert svc.get_persistence_enabled() is True


def test_env_var_accepts_various_falsy(monkeypatch):
    for v in ("0", "False", "NO", "off", "FALSE"):
        monkeypatch.setenv("AUTOPILOT_PERSISTENCE_ENABLED", v)
        svc = AutoPilotQueueService()
        assert svc.get_persistence_enabled() is False, f"failed on {v!r}"
