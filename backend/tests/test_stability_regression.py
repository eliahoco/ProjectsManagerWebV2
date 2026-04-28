"""
Stability regression tests — E7.S1.T1 through E7.S1.T4.

T1: Event-loop block — 10 concurrent /api/git/*/commits calls must finish < 5s.
T2: SQLite write contention — PATCH /api/codeboard/issues/{id} must complete < 3s.
T3: /health responsiveness — must return < 500ms even during background load.
T4: embed_issue latency — fast when Chroma up; fast fallback when Chroma down.
"""

import asyncio
import time
import uuid
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app
from models import AsyncSessionLocal, Issue, Project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transport() -> ASGITransport:
    return ASGITransport(app=app)


# ---------------------------------------------------------------------------
# T1 — Event-loop block detection on /api/git/* endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_git_endpoint_no_event_loop_block_under_concurrency():
    """10 concurrent /api/git/project/{id}/commits calls must all complete < 5s.

    Verifies that git_service methods are awaited inside the route handlers
    (i.e. asyncio.create_subprocess_exec path is used, not blocking subprocess.run).
    If the event loop is blocked, elapsed time will balloon well beyond 5 s.
    """
    transport = _make_transport()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Discover a project id from the DB
        r = await client.get("/api/projects")
        assert r.status_code == 200
        projects = r.json()
        if not projects:
            pytest.skip("No projects in DB — cannot exercise git endpoint")

        project_id = projects[0]["id"]

        start = time.monotonic()
        results = await asyncio.gather(
            *[
                client.get(f"/api/git/project/{project_id}/commits")
                for _ in range(10)
            ],
            return_exceptions=True,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, (
            f"10 concurrent /api/git/.../commits calls took {elapsed:.2f}s — "
            "event loop is likely blocked (missing await on git_service coroutines)"
        )

        # At least 8/10 must return a proper HTTP response (200 or 404 acceptable)
        ok = sum(
            1
            for r in results
            if not isinstance(r, Exception) and r.status_code in (200, 404)
        )
        assert ok >= 8, (
            f"Only {ok}/10 calls returned a valid HTTP response; "
            "check that git endpoints return responses rather than raw coroutine objects"
        )


# ---------------------------------------------------------------------------
# T2 — PATCH under SQLite write contention
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_issue_patch_completes_under_write_load():
    """PATCH /api/codeboard/issues/{id} must complete < 3s under concurrent DB writes.

    A background task hammers AsyncSessionLocal with rapid INSERT/UPDATE cycles
    while we time a single PATCH request.  Validates that WAL mode + busy_timeout
    prevent the PATCH from stalling or timing out.
    """
    # Locate a real issue to PATCH, or skip
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(Issue).limit(1))
        issue = result.scalar_one_or_none()

    if issue is None:
        pytest.skip("No issues in DB — cannot exercise PATCH endpoint")

    issue_id = issue.id

    stop_flag = asyncio.Event()

    async def _write_hammer():
        """Rapidly write rows to the DB to create contention."""
        while not stop_flag.is_set():
            try:
                async with AsyncSessionLocal() as db:
                    dummy = Issue(
                        id=str(uuid.uuid4()),
                        key=f"LOAD-{uuid.uuid4().hex[:6].upper()}",
                        title="load-test dummy",
                        type="TASK",
                        status="BACKLOG",
                        priority="LOW",
                        projectId=issue.projectId,
                        createdAt=__import__("datetime").datetime.utcnow(),
                        updatedAt=__import__("datetime").datetime.utcnow(),
                    )
                    db.add(dummy)
                    await db.commit()
                    # Clean up immediately
                    await db.delete(dummy)
                    await db.commit()
            except Exception:
                pass
            await asyncio.sleep(0.01)

    hammer_task = asyncio.create_task(_write_hammer())

    try:
        transport = _make_transport()
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            start = time.monotonic()
            r = await client.patch(
                f"/api/codeboard/issues/{issue_id}",
                json={"priority": "MEDIUM"},
                # No Origin header → bypasses the origin-check middleware
            )
            elapsed = time.monotonic() - start
    finally:
        stop_flag.set()
        await hammer_task

    assert elapsed < 3.0, (
        f"PATCH /api/codeboard/issues/{{id}} took {elapsed:.2f}s under write load "
        "(expected < 3s with WAL + busy_timeout=30000)"
    )
    assert r.status_code in (200, 404, 422), (
        f"Unexpected status {r.status_code} from PATCH endpoint"
    )


# ---------------------------------------------------------------------------
# T3 — /health responsiveness under concurrent background load
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_always_responds_quickly():
    """/health must respond in < 500ms even while 20 git calls run in the background.

    This confirms /health is never queued behind a blocking git subprocess call.
    """
    transport = _make_transport()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Discover a project id — fall back to a non-existent one (404 is fine for load)
        r = await client.get("/api/projects")
        if r.status_code == 200 and r.json():
            project_id = r.json()[0]["id"]
        else:
            project_id = "nonexistent-project-id"

        # Fire 20 git calls in the background (we don't care if they fail)
        bg_task = asyncio.gather(
            *[
                client.get(f"/api/git/project/{project_id}/commits")
                for _ in range(20)
            ],
            return_exceptions=True,
        )

        # Give the background requests a moment to start
        await asyncio.sleep(0.05)

        start = time.monotonic()
        health_response = await client.get("/health")
        elapsed = time.monotonic() - start

        # Clean up background tasks
        await bg_task

    assert health_response.status_code == 200, (
        f"/health returned {health_response.status_code}"
    )
    assert elapsed < 0.5, (
        f"/health took {elapsed * 1000:.0f}ms (expected < 500ms) — "
        "event loop may be blocked by git subprocesses"
    )


# ---------------------------------------------------------------------------
# T4a — embed_issue fast when Chroma is available (mock)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_issue_fast_when_chroma_up():
    """embed_issue must return < 1s when Chroma is reachable.

    We mock the ChromaDB collection so the test is hermetic and never needs
    a real Chroma server.
    """
    from services.rag_service import RAGService

    rag = RAGService()

    # Inject a mock collection that returns immediately
    mock_collection = MagicMock()
    mock_collection.upsert = MagicMock(return_value=None)
    rag._client = MagicMock()
    rag._client.get_or_create_collection = MagicMock(return_value=mock_collection)

    start = time.monotonic()
    result = await rag.embed_issue(
        project_id="proj-001",
        issue_id=str(uuid.uuid4()),
        key="TEST-1",
        title="Stability regression test",
        description="Testing embed latency",
        issue_type="TASK",
        status="BACKLOG",
    )
    elapsed = time.monotonic() - start

    assert result is True, "embed_issue returned False — embedding failed"
    assert elapsed < 1.0, (
        f"embed_issue took {elapsed:.3f}s with mocked Chroma (expected < 1s)"
    )


# ---------------------------------------------------------------------------
# T4b — embed_issue fast fallback when Chroma is down
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_issue_fast_when_chroma_down(monkeypatch):
    """When Chroma is unreachable (port 1 = refused immediately), RAGService must
    fall back to PersistentClient within 2s — NOT hang for 75s.

    The 75s hang occurred when socket.create_connection used the OS default
    TCP timeout.  The fix added timeout=5 to the TCP probe in _init_client_blocking.
    """
    import chromadb
    from services.rag_service import RAGService
    from app.config import settings as app_settings

    # Redirect Chroma to a port that refuses connections immediately (port 1)
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 1)
    monkeypatch.setattr(app_settings, "CHROMA_HOST", "127.0.0.1")

    # Mock PersistentClient so we don't write to disk during test
    mock_persistent = MagicMock()
    mock_collection = MagicMock()
    mock_collection.upsert = MagicMock(return_value=None)
    mock_persistent.get_or_create_collection = MagicMock(return_value=mock_collection)

    with patch.object(chromadb, "PersistentClient", return_value=mock_persistent):
        rag = RAGService()

        start = time.monotonic()
        # _init_client_blocking will fail the TCP probe → caller falls back
        try:
            await asyncio.to_thread(rag._init_client_blocking)
        except ConnectionError:
            rag._fallback_to_persistent()

        elapsed_init = time.monotonic() - start

        assert elapsed_init < 2.0, (
            f"ChromaDB fallback took {elapsed_init:.2f}s (expected < 2s). "
            "TCP probe is missing a short timeout — may hang for 75s on macOS."
        )

        # After fallback, embed_issue should still work
        start = time.monotonic()
        result = await rag.embed_issue(
            project_id="proj-002",
            issue_id=str(uuid.uuid4()),
            key="TEST-2",
            title="Fallback embed test",
            issue_type="TASK",
            status="BACKLOG",
        )
        elapsed_embed = time.monotonic() - start

    assert result is True, "embed_issue returned False after fallback to PersistentClient"
    assert elapsed_embed < 1.0, (
        f"embed_issue via PersistentClient took {elapsed_embed:.3f}s (expected < 1s)"
    )
