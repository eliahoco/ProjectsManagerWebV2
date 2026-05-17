"""
Tests for CB-2766: InternalAuthDep gating on state-changing autopilot endpoints.

Verifies that each gated endpoint:
- Returns HTTP 401 when no X-Internal-Token header is present (when token configured).
- Returns HTTP 200/202/4xx (not 401) when valid token is presented.

We patch app.security.settings.INTERNAL_API_TOKEN to a non-empty value to
force the gate active, then verify that 401 is returned without the token and
that a non-401 response is returned with the correct token.

Note: FastAPI evaluates Depends() at request-time, so the settings patch must
be active during the request (not just at app-construction time). We use the
`override_get_token` approach: patch the token on the settings object directly.
"""

from __future__ import annotations

from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

TEST_TOKEN = "test-internal-token-secret-cb2766"


@pytest.fixture()
def gated_client() -> Generator[TestClient, None, None]:
    """
    Build a TestClient with:
    - The execution router mounted under /execute.
    - INTERNAL_API_TOKEN set to TEST_TOKEN so the gate is active.
    - autopilot_queue_service mocked out (endpoints call it).
    - DB dependency overridden with a no-op.
    """
    import app.security as sec_mod
    from app.config import settings

    # Store original and override
    original_token = settings.INTERNAL_API_TOKEN
    settings.INTERNAL_API_TOKEN = TEST_TOKEN

    try:
        with patch("services.autopilot_queue_service.autopilot_queue_service") as mock_svc:
            mock_svc.get_active_queue.return_value = None
            mock_svc.get_queue.return_value = None
            # CB-2798: get_queue_status is now async — must be AsyncMock.
            mock_svc.get_queue_status = AsyncMock(return_value=None)
            mock_svc.pause_queue = AsyncMock(return_value=False)
            mock_svc.resume_queue = AsyncMock(return_value=False)
            mock_svc.skip_current = AsyncMock(return_value=False)
            mock_svc.abort_queue = AsyncMock(return_value=False)
            mock_svc.get_or_load_queue = AsyncMock(return_value=None)
            mock_svc.get_persistence_enabled.return_value = True
            mock_svc.set_persistence_enabled.return_value = None
            mock_svc.get_recovered_queues.return_value = []
            mock_svc.get_zombie_queue_ids.return_value = set()
            mock_svc._resume_handles = {}
            mock_svc._AUTO_RESUME_MAX_ATTEMPTS = 3
            # CB-2798: clear_recovery_state is now async and returns a dict.
            mock_svc.clear_recovery_state = AsyncMock(return_value={"ok": True, "cancelled_timer": False, "transitions": []})
            mock_svc.reset_failed_tasks = AsyncMock(return_value={"queue_id": "q123", "reset_count": 0, "task_ids": [], "task_keys": []})
            mock_svc._reset_failed_tasks_locked = AsyncMock(return_value={"queue_id": "q123", "reset_count": 0, "task_ids": [], "task_keys": []})
            mock_svc._resume_locks = {}

            from api.execution import router as exec_router
            from models import get_db

            # The execution router already has prefix="/execute" so mount at root
            app = FastAPI()
            app.include_router(exec_router)

            # Override DB dependency so routes that depend on it don't fail on DB access
            async def _noop_db():
                yield MagicMock()

            app.dependency_overrides[get_db] = _noop_db

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client
    finally:
        settings.INTERNAL_API_TOKEN = original_token


def _h_none() -> dict:
    return {}


def _h_wrong() -> dict:
    return {"x-internal-token": "wrong-token"}


def _h_valid() -> dict:
    return {"x-internal-token": TEST_TOKEN}


def _assert_401_without_token(client: TestClient, method: str, path: str, **kwargs):
    """Verify no-token and wrong-token both produce 401."""
    resp = getattr(client, method)(path, headers=_h_none(), **kwargs)
    assert resp.status_code == 401, (
        f"{method.upper()} {path}: no-token expected 401, got {resp.status_code} — {resp.text}"
    )
    resp2 = getattr(client, method)(path, headers=_h_wrong(), **kwargs)
    assert resp2.status_code == 401, (
        f"{method.upper()} {path}: wrong-token expected 401, got {resp2.status_code}"
    )


def _assert_not_401_with_token(client: TestClient, method: str, path: str, **kwargs):
    """Verify valid token produces non-401."""
    resp = getattr(client, method)(path, headers=_h_valid(), **kwargs)
    assert resp.status_code != 401, (
        f"{method.upper()} {path}: valid-token expected non-401, got {resp.status_code} — {resp.text}"
    )


# ---------------------------------------------------------------------------
# Tests: 401 returned without token
# ---------------------------------------------------------------------------


def test_resume_requires_auth(gated_client):
    """POST /execute/queue/{id}/resume must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/resume")


def test_pause_requires_auth(gated_client):
    """POST /execute/queue/{id}/pause must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/pause")


def test_abort_requires_auth(gated_client):
    """POST /execute/queue/{id}/abort must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/abort", json={"action": "leave"})


def test_skip_requires_auth(gated_client):
    """POST /execute/queue/{id}/skip must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/skip")


def test_wait_for_reset_requires_auth(gated_client):
    """POST /execute/queue/{id}/wait-for-reset must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/wait-for-reset", json={})


def test_clear_recovery_requires_auth(gated_client):
    """POST /execute/queue/{id}/clear-recovery must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/clear-recovery")


def test_recovery_status_requires_auth(gated_client):
    """GET /execute/queue/recovery-status must return 401 without valid token."""
    _assert_401_without_token(gated_client, "get", "/execute/queue/recovery-status")


def test_metrics_requires_auth(gated_client):
    """GET /execute/queue/metrics must return 401 without valid token."""
    _assert_401_without_token(gated_client, "get", "/execute/queue/metrics")


def test_persistence_flag_post_requires_auth(gated_client):
    """POST /execute/queue/settings/persistence-enabled must return 401 without valid token."""
    _assert_401_without_token(
        gated_client, "post", "/execute/queue/settings/persistence-enabled",
        json={"enabled": True},
    )


def test_task_reset_requires_auth(gated_client):
    """POST /execute/queue/{id}/task/{order}/reset must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/task/0/reset")


# ---------------------------------------------------------------------------
# Tests: valid token is accepted (non-401)
# ---------------------------------------------------------------------------


def test_recovery_status_allowed_with_token(gated_client):
    """GET /execute/queue/recovery-status returns non-401 with valid token."""
    _assert_not_401_with_token(gated_client, "get", "/execute/queue/recovery-status")


def test_persistence_flag_post_allowed_with_token(gated_client):
    """POST /execute/queue/settings/persistence-enabled returns non-401 with valid token."""
    _assert_not_401_with_token(
        gated_client, "post", "/execute/queue/settings/persistence-enabled",
        json={"enabled": True},
    )


def test_abort_allowed_with_token(gated_client):
    """POST /execute/queue/{id}/abort returns non-401 with valid token."""
    # Service returns False (queue not found), so expect 404 — not 401
    _assert_not_401_with_token(gated_client, "post", "/execute/queue/q123/abort", json={"action": "leave"})


def test_skip_allowed_with_token(gated_client):
    """POST /execute/queue/{id}/skip returns non-401 with valid token."""
    _assert_not_401_with_token(gated_client, "post", "/execute/queue/q123/skip")


# CB-2793 Security Fix5: auth coverage for /reset-failed-tasks
def test_reset_failed_tasks_requires_auth(gated_client):
    """POST /execute/queue/{id}/reset-failed-tasks must return 401 without valid token."""
    _assert_401_without_token(gated_client, "post", "/execute/queue/q123/reset-failed-tasks")


def test_reset_failed_tasks_allowed_with_token(gated_client):
    """POST /execute/queue/{id}/reset-failed-tasks returns non-401 with valid token.

    Service mock returns 404 (queue not found) — which is non-401, proving the
    auth gate passed and the endpoint handler ran.
    """
    _assert_not_401_with_token(gated_client, "post", "/execute/queue/q123/reset-failed-tasks")
