"""
CB-2796 (S3) — Resume endpoint contract + reset_failed_tasks.

Tests for:
  RC3a fix  — resume no longer refuses when only failed tasks remain if
              retry_failed=true is supplied.
  RC3b fix  — resume endpoint now returns 404/409 (not bare 400) with
              structured body: error, code, details.pause_reason, etc.
  New endpoint POST /queue/{id}/reset-failed-tasks.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
from utils.autopilot_repository import save_queue


# ---------------------------------------------------------------------------
# In-memory DB fixture (mirrors test_auto_resume_scheduler.py)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def patched_session(monkeypatch):
    """In-memory SQLite engine + minimal seed; patched into AsyncSessionLocal."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Sf = async_sessionmaker(engine, expire_on_commit=False)

    async with Sf() as s:
        s.add(Project(
            id="p-test",
            name="test-project",
            path="/tmp/test",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        ))
        await s.commit()

    import models.database
    import services.autopilot_queue_service as svc_mod
    monkeypatch.setattr(models.database, "AsyncSessionLocal", Sf)
    monkeypatch.setattr(svc_mod, "AsyncSessionLocal", Sf)
    yield Sf
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tasks(statuses: list[TaskStatus]) -> list[QueueTask]:
    return [
        QueueTask(
            issue_id=f"issue-{i}",
            issue_key=f"CB-{2000 + i}",
            issue_title=f"Task {i}",
            order=i,
            status=st,
        )
        for i, st in enumerate(statuses)
    ]


def _make_queue(
    *,
    statuses: list[TaskStatus] | None = None,
    queue_status: QueueStatus = QueueStatus.PAUSED,
    pause_reason: str | None = None,
    auto_resume_attempts: int = 0,
    current_index: int = 0,
) -> AutoPilotQueue:
    qid = str(uuid.uuid4())
    if statuses is None:
        statuses = [TaskStatus.PENDING]
    tasks = _make_tasks(statuses)
    q = AutoPilotQueue(
        id=qid,
        feature_id="feat-2796",
        feature_key="CB-2796",
        project_id="p-test",
        project_path="/tmp/test",
        status=queue_status,
        tasks=tasks,
        config=QueueConfig(),
    )
    q.pause_reason = pause_reason
    q.auto_resume_attempts = auto_resume_attempts
    q.current_index = current_index
    return q


# ---------------------------------------------------------------------------
# HTTP client fixture (ASGI — no live server needed)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_client():
    """Thin ASGI wrapper around the FastAPI app with internal auth token set."""
    import os
    from app.main import app
    token = os.environ.get("INTERNAL_API_TOKEN", "pytest-internal-token-not-secret")
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Internal-Token": token},
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Service-level tests — reset_failed_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_failed_tasks_marks_pending_keeps_completed(patched_session):
    """FAILED tasks become PENDING; COMPLETED tasks stay COMPLETED."""
    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.FAILED,
        TaskStatus.PENDING,
    ])
    svc._queues[q.id] = q

    result = await svc.reset_failed_tasks(q.id)

    assert result["reset_count"] == 2
    assert len(result["task_ids"]) == 2
    assert len(result["task_keys"]) == 2

    # Only tasks 1 and 2 were FAILED — check their new status
    assert q.tasks[0].status == TaskStatus.COMPLETED  # untouched
    assert q.tasks[1].status == TaskStatus.PENDING    # was FAILED
    assert q.tasks[2].status == TaskStatus.PENDING    # was FAILED
    assert q.tasks[3].status == TaskStatus.PENDING    # was already PENDING


@pytest.mark.asyncio
async def test_reset_failed_tasks_resets_error_and_timestamps(patched_session):
    """After reset: error→None, started_at→None, completed_at→None; retry_count preserved."""
    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[TaskStatus.FAILED])
    t = q.tasks[0]
    t.error = "Token exhausted"
    t.started_at = datetime.utcnow() - timedelta(minutes=5)
    t.completed_at = datetime.utcnow() - timedelta(minutes=1)
    t.retry_count = 2
    svc._queues[q.id] = q

    await svc.reset_failed_tasks(q.id)

    assert t.error is None
    assert t.started_at is None
    assert t.completed_at is None
    assert t.retry_count == 2  # preserved — informational


@pytest.mark.asyncio
async def test_reset_failed_tasks_lowers_current_index(patched_session):
    """current_index is reset to the minimum order of newly-PENDING tasks."""
    svc = AutoPilotQueueService()
    q = _make_queue(
        statuses=[TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.FAILED],
        current_index=5,  # artificially high
    )
    svc._queues[q.id] = q

    await svc.reset_failed_tasks(q.id)

    # Tasks 1 and 2 are now PENDING; min order = 1 < 5
    assert q.current_index == 1


@pytest.mark.asyncio
async def test_reset_failed_tasks_no_op_when_none_failed(patched_session):
    """Returns reset_count=0 and leaves queue unchanged when no tasks are FAILED."""
    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[TaskStatus.COMPLETED, TaskStatus.PENDING])
    svc._queues[q.id] = q

    result = await svc.reset_failed_tasks(q.id)

    assert result["reset_count"] == 0
    assert result["task_ids"] == []
    assert result["task_keys"] == []


@pytest.mark.asyncio
async def test_reset_failed_tasks_unknown_queue_returns_zero(patched_session):
    """Missing queue → returns zero-count dict (does not raise)."""
    svc = AutoPilotQueueService()

    result = await svc.reset_failed_tasks("no-such-queue-id")

    assert result["reset_count"] == 0


# ---------------------------------------------------------------------------
# Service-level tests — resume with retry_failed combo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_with_retry_failed_resets_and_allows_resume(patched_session):
    """3 FAILED + 1 PENDING: after reset_failed_tasks all 4 are PENDING, resume succeeds."""
    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[
        TaskStatus.FAILED,
        TaskStatus.FAILED,
        TaskStatus.FAILED,
        TaskStatus.PENDING,
    ])
    svc._queues[q.id] = q

    await svc.reset_failed_tasks(q.id)
    # All tasks now PENDING
    assert all(t.status == TaskStatus.PENDING for t in q.tasks)

    # resume_queue should now succeed (finds a pending task)
    success = await svc.resume_queue(q.id)
    assert success is True


@pytest.mark.asyncio
async def test_resume_without_retry_failed_does_not_reset(patched_session):
    """Calling resume_queue without prior reset leaves FAILED tasks as FAILED."""
    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[
        TaskStatus.FAILED,
        TaskStatus.FAILED,
        TaskStatus.FAILED,
    ])
    svc._queues[q.id] = q

    # Plain resume — no reset_failed_tasks call
    success = await svc.resume_queue(q.id)
    # Fails because no PENDING tasks
    assert success is False

    # FAILED tasks must still be FAILED
    assert all(t.status == TaskStatus.FAILED for t in q.tasks)


# ---------------------------------------------------------------------------
# HTTP endpoint tests (via ASGI)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_returns_404_when_queue_missing(patched_session, api_client):
    """Unknown queue_id → 404 NOT_FOUND."""
    random_id = str(uuid.uuid4())
    resp = await api_client.post(f"/api/execute/queue/{random_id}/resume")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resume_returns_409_when_all_failed_with_zero_pending(
    patched_session, api_client, monkeypatch
):
    """5 FAILED tasks, 0 PENDING → POST resume returns 409 with structured body."""
    from app.main import app
    import services.autopilot_queue_service as svc_mod

    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[TaskStatus.FAILED] * 5)
    svc._queues[q.id] = q

    # Patch the singleton so the route handler uses our test service instance.
    monkeypatch.setattr(svc_mod, "autopilot_queue_service", svc)

    # Patch the import inside the api.execution module too.
    import api.execution as exec_mod
    monkeypatch.setattr(exec_mod, "autopilot_queue_service", svc)

    resp = await api_client.post(f"/api/execute/queue/{q.id}/resume")

    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "CONFLICT"
    assert body["code"] == "QUEUE_NOT_RESUMABLE"
    assert body["details"]["failed_count"] == 5
    assert body["details"]["pending_count"] == 0
    assert "retry_failed" in body["details"]["suggestion"]


@pytest.mark.asyncio
async def test_resume_returns_409_with_breaker_details_when_tripped(
    patched_session, api_client, monkeypatch
):
    """Breaker-tripped queue (pause_reason=manual_circuit_breaker) → 409 with details."""
    import services.autopilot_queue_service as svc_mod
    import api.execution as exec_mod

    svc = AutoPilotQueueService()
    q = _make_queue(
        statuses=[TaskStatus.FAILED] * 3,
        queue_status=QueueStatus.PAUSED,
        pause_reason=svc._CIRCUIT_BREAKER_PAUSE_REASON,
        auto_resume_attempts=svc._AUTO_RESUME_MAX_ATTEMPTS,
    )
    svc._queues[q.id] = q

    monkeypatch.setattr(svc_mod, "autopilot_queue_service", svc)
    monkeypatch.setattr(exec_mod, "autopilot_queue_service", svc)

    resp = await api_client.post(f"/api/execute/queue/{q.id}/resume")

    assert resp.status_code == 409
    body = resp.json()
    details = body["details"]
    assert details["pause_reason"] == svc._CIRCUIT_BREAKER_PAUSE_REASON
    assert details["auto_resume_attempts"] >= svc._AUTO_RESUME_MAX_ATTEMPTS
    assert details["failed_count"] == 3


@pytest.mark.asyncio
async def test_reset_failed_tasks_endpoint_marks_pending_keeps_completed(
    patched_session, api_client, monkeypatch
):
    """POST /reset-failed-tasks endpoint: FAILED→PENDING, COMPLETED stays COMPLETED."""
    import services.autopilot_queue_service as svc_mod
    import api.execution as exec_mod

    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.FAILED,
    ])
    svc._queues[q.id] = q

    monkeypatch.setattr(svc_mod, "autopilot_queue_service", svc)
    monkeypatch.setattr(exec_mod, "autopilot_queue_service", svc)

    resp = await api_client.post(f"/api/execute/queue/{q.id}/reset-failed-tasks")

    assert resp.status_code == 200
    body = resp.json()
    assert body["reset_count"] == 2
    assert len(body["task_ids"]) == 2

    assert q.tasks[0].status == TaskStatus.COMPLETED  # untouched
    assert q.tasks[1].status == TaskStatus.PENDING
    assert q.tasks[2].status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_reset_failed_tasks_endpoint_returns_404_for_missing_queue(
    patched_session, api_client, monkeypatch
):
    """POST /reset-failed-tasks for unknown queue → 404."""
    import services.autopilot_queue_service as svc_mod
    import api.execution as exec_mod

    svc = AutoPilotQueueService()
    monkeypatch.setattr(svc_mod, "autopilot_queue_service", svc)
    monkeypatch.setattr(exec_mod, "autopilot_queue_service", svc)

    resp = await api_client.post(
        f"/api/execute/queue/{uuid.uuid4()}/reset-failed-tasks"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resume_with_retry_failed_true_resets_and_resumes_via_http(
    patched_session, api_client, monkeypatch
):
    """POST resume?retry_failed=true with 3 FAILED + 1 PENDING:
    all tasks become PENDING after the call, resume proceeds.
    """
    import services.autopilot_queue_service as svc_mod
    import api.execution as exec_mod

    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[
        TaskStatus.FAILED,
        TaskStatus.FAILED,
        TaskStatus.FAILED,
        TaskStatus.PENDING,
    ])
    svc._queues[q.id] = q

    monkeypatch.setattr(svc_mod, "autopilot_queue_service", svc)
    monkeypatch.setattr(exec_mod, "autopilot_queue_service", svc)

    resp = await api_client.post(
        f"/api/execute/queue/{q.id}/resume",
        params={"retry_failed": "true"},
    )

    # resume succeeds (200) — all tasks were reset to PENDING first
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True

    # All tasks are now PENDING (resume_queue sets the _pause_event so the
    # queue begins running, but in-memory state shows PENDING → not RUNNING
    # for individual tasks yet).
    assert all(t.status == TaskStatus.PENDING for t in q.tasks)


@pytest.mark.asyncio
async def test_resume_with_retry_failed_false_does_not_reset(
    patched_session, api_client, monkeypatch
):
    """POST resume?retry_failed=false does NOT reset FAILED tasks."""
    import services.autopilot_queue_service as svc_mod
    import api.execution as exec_mod

    svc = AutoPilotQueueService()
    q = _make_queue(statuses=[
        TaskStatus.FAILED,
        TaskStatus.FAILED,
        TaskStatus.FAILED,
    ])
    svc._queues[q.id] = q

    monkeypatch.setattr(svc_mod, "autopilot_queue_service", svc)
    monkeypatch.setattr(exec_mod, "autopilot_queue_service", svc)

    resp = await api_client.post(
        f"/api/execute/queue/{q.id}/resume",
        params={"retry_failed": "false"},
    )

    # Resume fails → 409 (no pending tasks)
    assert resp.status_code == 409

    # FAILED tasks remain FAILED
    assert all(t.status == TaskStatus.FAILED for t in q.tasks)
