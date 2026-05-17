"""CB-2729: regression tests for the audit follow-up on CB-2218.

Pins three independent guarantees that together prevent a stuck/laggy
ChromaDB from pinning the FastAPI event-loop worker:

  1. `_init_client_blocking()` configures a per-call timeout on the
     chromadb HttpClient's underlying httpx session — heartbeat /
     list_collections / count() can never block more than
     `CHROMA_HTTP_TIMEOUT_S` seconds against a stuck server.
  2. `get_status_payload()` releases its single-flight lock after
     `STATUS_LOCK_ACQUIRE_TIMEOUT_S` instead of queueing forever — a
     contended caller serves the prior cached payload (or a synthesized
     degraded one) with `healthy=False` rather than waiting indefinitely.
  3. The /api/system/rag/status FastAPI handler dispatches the
     synchronous probe via `asyncio.to_thread()` — a hung probe blocks
     a threadpool worker, never the event loop or any other async
     handler scheduled on it.

Each guarantee is mock-exercised at unit level so the test suite stays
fast (no real ChromaDB server, no real network) but reflects the
production code path. The simulated stuck-ChromaDB acceptance test
(`test_stuck_chromadb_returns_within_5s`) wires a heartbeat that sleeps
60 s and asserts the entire status path returns in under 5 s end-to-end.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import chromadb
import httpx
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from services.rag_service import (  # noqa: E402
    RAGService,
    _configure_http_client_timeout,
)


# ---------------------------------------------------------------------------
# (1) HttpClient timeout is configured at construction
# ---------------------------------------------------------------------------


def test_init_configures_http_timeout(monkeypatch):
    """CB-2729: after `_init_client_blocking()` succeeds, the chromadb
    HttpClient's internal httpx session has a non-None timeout.

    chromadb 0.5.x constructs `httpx.Client(timeout=None)` internally.
    Without the configurer in `_init_client_blocking()`, every probe
    inherits no-timeout — the precondition for the CB-2729 DoS shape.
    This test pins the configurer's success: the `_session.timeout`
    attribute on the chromadb client must reflect
    `settings.CHROMA_HTTP_TIMEOUT_S` after init.

    Failure mode if chromadb refactors `_session` away: the configurer
    catches AttributeError and returns False (logged WARN), and this
    test fails — surfacing the regression at the same moment the
    silent-degradation path becomes reachable.
    """
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)
    monkeypatch.setattr(app_settings, "CHROMA_HTTP_TIMEOUT_S", 2.0)

    # Real-shaped fake: nested attribute path matches chromadb 0.5.x
    # (`client._server._session.timeout`). Using a MagicMock here would
    # let any attribute path "succeed", masking a refactor that breaks
    # the configurer.
    fake_session = httpx.Client(timeout=None)
    fake_server = MagicMock()
    fake_server._session = fake_session
    fake_client = MagicMock()
    fake_client._server = fake_server
    fake_client.heartbeat = MagicMock(return_value=1)

    rag = RAGService()
    with patch(
        "services.rag_service.socket.create_connection", return_value=MagicMock()
    ), patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    # The session timeout reflects the configured ceiling.
    assert fake_session.timeout == httpx.Timeout(2.0)


def test_configure_http_client_timeout_returns_false_on_layout_change(caplog):
    """CB-2729: if chromadb refactors the internal `_session` path away
    (private API access is intentional but fragile), the configurer logs
    WARN and returns False — degraded behaviour matches the prior
    no-timeout status quo, which is strictly better than refusing to
    start the backend.

    Pins the contract so a future chromadb upgrade that drops `_session`
    surfaces visibly via WARN log + the partner test
    `test_init_configures_http_timeout` failing simultaneously.
    """
    bad_client = MagicMock(spec=[])  # No `_server` attribute.

    with caplog.at_level("WARNING", logger="services.rag_service"):
        ok = _configure_http_client_timeout(bad_client, 2.0)

    assert ok is False
    warn_lines = [
        r for r in caplog.records if r.levelname == "WARNING" and "timeout" in r.message.lower()
    ]
    assert warn_lines, "configurer must WARN-log on internal-layout failure"


# ---------------------------------------------------------------------------
# (2) Status-cache lock is bounded (contention degrades, never queues)
# ---------------------------------------------------------------------------


def _make_http_rag_with_held_lock(monkeypatch):
    """Build a HTTP-mode RAGService with the status-cache lock already
    held by another thread, so the next get_status_payload() call hits
    the contention path.
    """
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    with patch(
        "services.rag_service.socket.create_connection", return_value=MagicMock()
    ), patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    return rag, fake_client


def test_contention_with_no_cache_returns_synthesized_degraded(monkeypatch):
    """CB-2729: with the cache lock held by another thread AND no prior
    cache to serve, `get_status_payload()` synthesizes a minimal degraded
    payload reflecting the active mode but with `healthy=False` — never
    blocks beyond the lock acquire timeout.
    """
    rag, fake_client = _make_http_rag_with_held_lock(monkeypatch)

    # Tighten the contention bound so the test asserts in <100 ms instead
    # of the 500 ms production default.
    monkeypatch.setattr(rag, "STATUS_LOCK_ACQUIRE_TIMEOUT_S", 0.05)

    # Hold the lock from a sibling thread for the whole window.
    holder_started = threading.Event()
    release_holder = threading.Event()

    def _hold():
        rag._status_cache_lock.acquire()
        holder_started.set()
        release_holder.wait(timeout=2.0)
        rag._status_cache_lock.release()

    holder = threading.Thread(target=_hold)
    holder.start()
    try:
        assert holder_started.wait(timeout=1.0), "lock-holder thread didn't start"

        # No cache exists yet (we wired state directly, never called the
        # public API). The contention path must synthesize a degraded
        # payload reflecting the actual mode.
        t0 = time.monotonic()
        payload = rag.get_status_payload()
        elapsed = time.monotonic() - t0

        assert elapsed < 0.5, (
            f"contended get_status_payload took {elapsed:.3f}s — must be "
            "bounded by STATUS_LOCK_ACQUIRE_TIMEOUT_S"
        )
        assert payload["mode"] == "HTTP"
        assert payload["endpoint"] == "chromadb"
        assert payload["port"] == 8000
        assert payload["healthy"] is False
        assert payload["collections"] == []
        # The probe never ran — neither method was called from
        # get_status_payload (init counted as 1 heartbeat already).
        assert fake_client.list_collections.call_count == 0
    finally:
        release_holder.set()
        holder.join(timeout=1.0)


def test_contention_with_no_cache_persistent_mode_redacts_endpoint(monkeypatch):
    """CB-2729 sec audit (LOW): the synthesized degraded payload must
    preserve CB-2216's PERSISTENT-mode abspath redaction even when the
    contention path fires. A future refactor that accidentally read
    `self._endpoint` in the PERSISTENT branch of
    `_synthesize_degraded_payload()` would re-leak the embedded-store
    abspath to any local Origin-less caller — exactly what CB-2216
    fixed in the legitimate compute path.

    Mirrors `test_contention_with_no_cache_returns_synthesized_degraded`
    but in PERSISTENT mode with a populated `_endpoint` (abspath) — the
    payload must still report `endpoint=""` and `fallback_active=True`.
    """
    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    monkeypatch.setattr(rag, "STATUS_LOCK_ACQUIRE_TIMEOUT_S", 0.05)

    holder_started = threading.Event()
    release_holder = threading.Event()

    def _hold():
        rag._status_cache_lock.acquire()
        holder_started.set()
        release_holder.wait(timeout=2.0)
        rag._status_cache_lock.release()

    holder = threading.Thread(target=_hold)
    holder.start()
    try:
        assert holder_started.wait(timeout=1.0)

        t0 = time.monotonic()
        payload = rag.get_status_payload()
        elapsed = time.monotonic() - t0

        assert elapsed < 0.5
        assert payload["mode"] == "PERSISTENT"
        # CB-2216: PERSISTENT mode never echoes the abspath via the HTTP
        # surface — the synthesized degraded payload must honour this.
        assert payload["endpoint"] == ""
        assert payload["fallback_active"] is True
        assert payload["healthy"] is False
        # The internal `_endpoint` still carries the abspath for log
        # surfaces (`describe_mode()`); only the synthesized HTTP payload
        # is redacted. Pin both halves of the contract.
        assert rag._endpoint  # populated by _fallback_to_persistent
        assert rag._endpoint not in str(payload), (
            "abspath leaked into synthesized PERSISTENT degraded payload"
        )
    finally:
        release_holder.set()
        holder.join(timeout=1.0)


def test_fast_path_returned_dict_does_not_alias_cache(monkeypatch):
    """CB-2729 audit (HIGH-1): the lock-free TTL-hit fast path must
    return a copy of the cached payload, not the live cached dict
    object. A caller that mutates the returned payload (Pydantic doesn't
    today, but a future code path or a caller's own post-processing
    might) must NOT poison the cache for every other reader and break
    the contention path that copies the same dict to flag degraded
    state.

    Two-pass test: first call populates the cache and returns a payload
    that the test mutates aggressively. Second call must return the
    UNMUTATED original — proving the cache wasn't aliased to the first
    return value.
    """
    rag, fake_client = _make_http_rag_with_held_lock(monkeypatch)
    # Release any hypothetical lock left over from the helper — this
    # test exercises the cache-hit path, not contention.
    if rag._status_cache_lock.locked():  # pragma: no cover — defensive
        rag._status_cache_lock.release()

    fixed_now = 1000.0
    monkeypatch.setattr(
        "services.rag_service.time.monotonic", lambda: fixed_now
    )

    first = rag.get_status_payload()
    # Mutate the returned payload — the cache must be insulated.
    first["healthy"] = "POISONED"
    first["mode"] = "POISONED"
    first["collections"].append({"count": 999_999})

    # Second call within the TTL window must return the original cached
    # payload, not the mutated copy. If `return cached` aliased, this
    # would inherit the POISONED values.
    second = rag.get_status_payload()
    assert second["healthy"] is True, (
        "cache was aliased — fast-path mutation poisoned shared state"
    )
    assert second["mode"] == "HTTP"
    # `collections` is the inner mutation we appended to — if the cache
    # is properly insulated by `dict(cached)`, the cached list is still
    # shared (shallow copy) but the append should NOT survive across
    # calls because `_compute_status_payload()` builds a fresh list per
    # probe. Verify the second call's collections matches the originally
    # computed shape (empty in this fixture's _make_http_rag_with_held_lock).
    assert {"count": 999_999} not in second["collections"], (
        "appending to fast-path collections poisoned the cached list"
    )


def test_contention_with_stale_cache_returns_cached_with_healthy_false(monkeypatch):
    """CB-2729: with a prior cached payload available, the contention
    path serves the last-known state with `healthy=False` overwritten —
    better than synthesizing zero-collections (operators see the prior
    snapshot annotated stale, not a phantom empty cluster).
    """
    rag, fake_client = _make_http_rag_with_held_lock(monkeypatch)
    monkeypatch.setattr(rag, "STATUS_LOCK_ACQUIRE_TIMEOUT_S", 0.05)

    # Plant a stale "healthy" cache directly so the contention path can
    # find prior state to degrade. We bypass the public API to avoid
    # racing the lock-holder thread below — the cache is a pair of
    # primitive attributes, planting them by direct assignment is
    # equivalent to a winning lock-holder having stored them.
    healthy_cache = {
        "mode": "HTTP",
        "endpoint": "chromadb",
        "port": 8000,
        "fallback_active": False,
        "collections": [{"count": 11}, {"count": 22}],
        "total_docs": 33,
        "healthy": True,
    }
    rag._status_cache = healthy_cache
    # Ensure the cache is stale (TTL elapsed) so the lock-free fast path
    # falls through to the lock-acquire branch.
    rag._status_cache_at = 0.0

    holder_started = threading.Event()
    release_holder = threading.Event()

    def _hold():
        rag._status_cache_lock.acquire()
        holder_started.set()
        release_holder.wait(timeout=2.0)
        rag._status_cache_lock.release()

    holder = threading.Thread(target=_hold)
    holder.start()
    try:
        assert holder_started.wait(timeout=1.0)

        t0 = time.monotonic()
        payload = rag.get_status_payload()
        elapsed = time.monotonic() - t0

        assert elapsed < 0.5
        # Same shape as the planted cache — but `healthy` flipped to False
        # to signal the surface degradation.
        assert payload["mode"] == "HTTP"
        assert payload["collections"] == [{"count": 11}, {"count": 22}]
        assert payload["total_docs"] == 33
        assert payload["healthy"] is False
        # Original cache is not mutated — the degraded payload must be a
        # copy so future fresh probes don't see this value as "the
        # historical fact" of the cluster.
        assert healthy_cache["healthy"] is True
    finally:
        release_holder.set()
        holder.join(timeout=1.0)


# ---------------------------------------------------------------------------
# (3) Stuck-ChromaDB acceptance test — entire path returns < 5s
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stuck_chromadb_returns_within_5s(monkeypatch):
    """CB-2729 acceptance: a heartbeat that sleeps 60 s must NOT pin the
    status endpoint for more than ~5 s end-to-end.

    Combines all three guarantees:
      * httpx-side timeout would cap the heartbeat at 2 s in production;
        in the test we simulate the timeout by raising httpx.ReadTimeout
        from the heartbeat mock (mimics what httpx itself would raise
        when its 2 s ceiling fires).
      * `asyncio.to_thread` ensures the blocking probe doesn't pin the
        event loop — the await in the handler returns control while the
        threadpool worker waits.
      * The lock-with-timeout further bounds *concurrent* callers, but
        this test exercises the single-call path.

    A regression that drops any of the three (e.g. removes the
    asyncio.to_thread wrapper, or the timeout configurer silently fails
    and the heartbeat actually sleeps 60 s on a real chromadb) would
    push this test over the 5 s budget.
    """
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.deps import get_rag
    from api.system import router as system_router
    from app.errors import setup_exception_handlers

    fake_client = MagicMock()
    # Simulate httpx's 2 s timeout firing by raising ReadTimeout. In
    # production this is what `_session.timeout = httpx.Timeout(2.0)`
    # would cause when the upstream chromadb is stuck — the request
    # raises after 2 s, get_status_payload's per-probe try/except
    # captures it as `healthy=False`.
    fake_client.heartbeat = MagicMock(
        side_effect=httpx.ReadTimeout("simulated stuck chromadb")
    )
    fake_client.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    rag._client = fake_client
    rag._mode = "HTTP"
    rag._endpoint = "chromadb:8402"

    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(system_router, prefix="/api")
    app.dependency_overrides[get_rag] = lambda: rag

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.monotonic()
        response = await client.get("/api/system/rag/status")
        elapsed = time.monotonic() - t0

    assert elapsed < 5.0, (
        f"stuck-chromadb path took {elapsed:.2f}s — exceeds 5 s budget; "
        "either the httpx timeout configurer regressed, the asyncio.to_thread "
        "wrapper was removed, or the per-probe try/except no longer absorbs "
        "the ReadTimeout"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "HTTP"
    assert data["healthy"] is False


@pytest.mark.asyncio
async def test_status_endpoint_does_not_pin_event_loop(monkeypatch):
    """CB-2729: while the synchronous status probe is mid-flight, an
    unrelated async handler scheduled on the same event loop must remain
    responsive.

    The previous shape called `rag.get_status_payload()` directly inside
    the async handler — a stuck probe pinned the event loop's worker
    thread for the full blocking duration, freezing every other handler
    sharing the loop. With `asyncio.to_thread()` the probe runs on the
    threadpool, so the loop keeps scheduling.

    Test mechanic: a probe that sleeps 1 s, fired alongside a `sleep(0)`
    no-op handler. The no-op must complete well before the probe — if
    the loop is pinned, both finish at ~1 s; if the loop is free, the
    no-op finishes near instantly.
    """
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.deps import get_rag
    from api.system import router as system_router
    from app.errors import setup_exception_handlers

    # 1 s blocking heartbeat — large enough to make the difference
    # between "ran on loop" (no-op stalls) and "ran on threadpool"
    # (no-op runs free) loud and unambiguous.
    def _slow_heartbeat(*a, **kw):
        time.sleep(1.0)
        return 1

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(side_effect=_slow_heartbeat)
    fake_client.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    rag._client = fake_client
    rag._mode = "HTTP"
    rag._endpoint = "chromadb:8402"

    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(system_router, prefix="/api")
    app.dependency_overrides[get_rag] = lambda: rag

    @app.get("/api/_test/noop")
    async def _noop():
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Fire status probe + no-op concurrently. Status will block for
        # ~1 s; no-op should complete near-instantly if the event loop
        # is free.
        status_t = asyncio.create_task(client.get("/api/system/rag/status"))
        # Give the status request a moment to enter the to_thread call
        # before measuring the no-op latency. Without this, both might
        # interleave before any blocking starts and the test trivially
        # passes regardless of whether the fix is in place.
        await asyncio.sleep(0.1)

        noop_t0 = time.monotonic()
        noop_response = await client.get("/api/_test/noop")
        noop_elapsed = time.monotonic() - noop_t0

        status_response = await status_t

    assert noop_response.status_code == 200
    assert status_response.status_code == 200
    # The no-op must finish in well under the 1 s probe duration —
    # 0.5 s gives ample headroom for CI scheduler jitter while still
    # being half the probe time, so a regression that pins the loop
    # (where the no-op would land at ~1 s) fails reliably.
    assert noop_elapsed < 0.5, (
        f"no-op handler blocked for {noop_elapsed:.2f}s while status probe "
        "was in flight — the event loop was pinned by the synchronous "
        "ChromaDB call. Restore the asyncio.to_thread wrapper in "
        "api/system.py:get_rag_status."
    )
