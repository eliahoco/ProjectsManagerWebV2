"""CB-2663: lock-guard the RAGService reset+construct sequence.

`RAGService` is a process-level singleton consumed by async FastAPI handlers
and reachable from threadpool callers via `asyncio.to_thread`. Pre-CB-2663,
`_init_client_blocking()`, `_fallback_to_persistent()`, and the property-
fallback in `client` could each construct a new ChromaDB client without
mutual exclusion. Today only the lifespan calls these paths, so contention
is zero — but a future runtime-reconnect surface (admin endpoint, watchdog
auto-recover) racing with the property-fallback would otherwise build two
`PersistentClient` instances on the same SQLite-backed path. The Python
ChromaDB SDK's PersistentClient is not safe to instantiate twice on the
same path concurrently — at best you get duplicated state, at worst the
SQLite write-ahead-log lock file gets corrupted.

These tests pin the lock contract:

  1. The fallback construction body is callable while the lock is held by
     the caller (helper-extraction contract).
  2. Two threads racing into `_init_client_blocking()` do not interleave
     their state assignments — an outside observer never witnesses a torn
     `(_client, _mode, _endpoint)` triple.
  3. The property-fallback's double-checked locking ensures that if one
     thread finishes constructing the client while another is waiting on
     the lock, the waiter observes the new client and skips construction
     entirely (so we don't leak duplicate clients on the same path).
  4. The lock is uncontended at single-threaded boot so init latency is
     unchanged.

Patching note: `mock.patch` / `patch.object` is NOT thread-safe when two
threads both `__enter__` and `__exit__` it for the same target — the
exits restore values in non-deterministic order and one thread's exit can
unpatch the other thread's still-active context. These multi-threaded
tests use `monkeypatch` (pytest fixture) instead, which patches once at
test-setup scope and tears down after both worker threads have joined.
"""

from __future__ import annotations

import threading
import time
from typing import List
from unittest.mock import MagicMock, patch

import chromadb

from services.rag_service import RAGService


def test_init_lock_is_threading_lock():
    """The lock must be `threading.Lock` so it works across the threadpool
    boundary used by `asyncio.to_thread()` in the lifespan.

    `threading.Lock()` returns an internal C type; rather than `isinstance`
    against the private `_thread.lock`, we assert the two behavioural
    contracts the design depends on:

      1. `acquire` is sync (NOT a coroutine) — an `asyncio.Lock` would
         duck-type as `acquire`/`release` but its `acquire` is a coroutine,
         which would not bind across the threadpool boundary used by
         `asyncio.to_thread()` in the lifespan.
      2. The lock is non-reentrant — re-acquiring from the same thread
         while held returns `False` for `blocking=False`. This pins the
         invariant that justifies the helper-extraction split in
         `_construct_persistent_client_locked()`; a future refactor to
         `RLock` would silently void the helper-extraction motivation.
    """
    import inspect

    rag = RAGService()
    assert not inspect.iscoroutinefunction(rag._init_lock.acquire), (
        "_init_lock.acquire is a coroutine — looks like asyncio.Lock, "
        "which won't bind across to_thread() boundaries"
    )
    # Sanity: the lock starts unlocked and acquire/release does not raise.
    assert rag._init_lock.acquire(blocking=False) is True
    # Non-reentrancy: a second non-blocking acquire from the same thread
    # while holding the lock must fail. This is the contract the helper
    # extraction in _construct_persistent_client_locked() depends on.
    assert rag._init_lock.acquire(blocking=False) is False
    rag._init_lock.release()


def test_construct_persistent_client_locked_runs_under_caller_lock():
    """The helper body must NOT itself acquire `_init_lock` — the property-
    fallback path holds the lock and calls the helper directly. If the
    helper re-acquired, the property path would deadlock."""
    rag = RAGService()

    # Hold the lock from the outside, then call the helper. With the helper
    # being lock-free internally, this completes; with a re-entrant
    # acquire it would deadlock the test thread.
    with rag._init_lock:
        with patch.object(
            chromadb, "PersistentClient", return_value=MagicMock()
        ):
            rag._construct_persistent_client_locked()

    assert rag._mode == "PERSISTENT"
    assert rag._client is not None


def test_two_threads_racing_into_init_client_blocking_serialize_cleanly(
    monkeypatch,
):
    """Two threads racing into `_init_client_blocking()` must serialize
    cleanly under `_init_lock` — no deadlock, both bodies run to
    completion sequentially, and an outside observer never witnesses a
    torn `(_client, _mode, _endpoint)` triple.

    Without the lock, an observer thread could sample
    `_mode == "HTTP"` paired with `_client is None` (T2's reset clobbered
    T1's already-assigned client) — the half-init invariant CB-2043 +
    CB-2213 pinned for sequential failure paths but which a concurrency
    regression could re-introduce.
    """
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)
    monkeypatch.setattr(
        "services.rag_service.socket.create_connection",
        lambda *a, **k: MagicMock(),
    )

    rag = RAGService()

    constructed: List[MagicMock] = []
    body_started = threading.Event()
    observer_done = threading.Event()
    # Mutex assertion: while one thread is inside `_init_client_blocking`'s
    # critical section, no other thread may enter it. If the lock is ever
    # removed from `_init_client_blocking`, T2 will reach this stub
    # concurrently with T1 and the assertion at entry will fire — that's
    # the regression detector that the torn-triple observer alone does
    # not reliably catch (per code-review MEDIUM-1).
    in_critical_section = threading.Lock()

    def slow_http_client(host, port):  # noqa: ARG001 — chromadb signature
        # `in_critical_section.acquire(blocking=False)` returns False if
        # another thread is already inside — that is the regression we
        # want to surface, NOT a hang. We do this BEFORE any sleep / wait
        # so a non-locked impl fails fast instead of deadlocking the test.
        assert in_critical_section.acquire(blocking=False), (
            "two threads inside _init_client_blocking critical section "
            "concurrently — `with self._init_lock:` was removed or broken"
        )
        try:
            # First caller stalls so the second runner is parked on the
            # lock while the observer is sampling. Subsequent callers
            # (T2 after T1 releases) run-through fast — observer_done is
            # already set.
            if not constructed:
                body_started.set()
                observer_done.wait(timeout=2)
            c = MagicMock(name=f"HttpClient#{len(constructed)}")
            c.heartbeat = MagicMock(return_value=1)
            constructed.append(c)
            return c
        finally:
            in_critical_section.release()

    monkeypatch.setattr(chromadb, "HttpClient", slow_http_client)

    torn_observations: List[tuple] = []

    def observer():
        body_started.wait(timeout=2)
        # Sample the singleton state during the construction window.
        # Under the lock, every sample is one of:
        #   - (None, None, None)          before T1 finished
        #   - (client_1, "HTTP", endpt)   T1 done, T2 parked on lock
        #   - (None, None, None)          T2 reset_state in flight
        #   - (client_2, "HTTP", endpt)   T2 done
        # A torn observation is (None, "HTTP", *) or (client, None, *).
        for _ in range(200):
            triple = (rag._client, rag._mode, rag._endpoint)
            client_set = triple[0] is not None
            mode_set = triple[1] is not None
            endpoint_set = triple[2] is not None
            if client_set != mode_set or mode_set != endpoint_set:
                torn_observations.append(triple)
            time.sleep(0.001)
        observer_done.set()

    errors: List[BaseException] = []

    def runner():
        try:
            rag._init_client_blocking()
        except BaseException as exc:  # pragma: no cover — surfaced in assert
            errors.append(exc)

    t1 = threading.Thread(target=runner)
    t2 = threading.Thread(target=runner)
    obs = threading.Thread(target=observer)
    t1.start()
    obs.start()
    # Spin t2 only after t1 has its body started so t2 definitely parks
    # on the init lock rather than racing the outer body entry.
    body_started.wait(timeout=2)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    obs.join(timeout=5)

    assert not errors, f"runner threads raised: {errors!r}"
    assert not t1.is_alive() and not t2.is_alive(), "deadlock — lock contract broke"
    assert not torn_observations, (
        f"observer saw torn (_client,_mode,_endpoint) triples — half-init "
        f"invariant violated under racing init: {torn_observations[:3]!r}"
    )

    # Both runners ran their body, so two HttpClient instances were
    # constructed (the lock serializes them but does NOT de-duplicate
    # explicit `_init_client_blocking` calls — that would be a different
    # contract; explicit reconnects are intended to rebuild).
    assert len(constructed) == 2
    assert rag._client in constructed
    assert rag._mode == "HTTP"
    assert rag._endpoint == "chromadb:8000"
    assert rag._collections == {}


def test_property_fallback_double_check_skips_duplicate_construction(
    monkeypatch,
):
    """Two threads both observing `_client is None` and contending on the
    property-fallback must not produce two `PersistentClient` instances.
    The double-checked locking inside the property closes the TOCTOU
    window: T1 acquires lock → constructs → releases; T2 acquires lock,
    re-checks `_client is None`, sees the new client, returns. Pre-
    CB-2663, both threads would have constructed on the same on-disk path.
    """
    rag = RAGService()
    assert rag._client is None  # precondition

    constructed: List[MagicMock] = []
    inside_constructor = threading.Event()
    release_constructor = threading.Event()

    def stub_persistent(*_args, **_kwargs):
        # Only stall on the very first construction so the second waiter
        # is parked on the lock during sampling. If the lock contract is
        # broken and a second construction is attempted, this stub returns
        # immediately so the test surfaces the regression cleanly via
        # `len(constructed)`.
        if not constructed:
            inside_constructor.set()
            release_constructor.wait(timeout=2)
        c = MagicMock(name=f"PersistentClient#{len(constructed)}")
        constructed.append(c)
        return c

    monkeypatch.setattr(chromadb, "PersistentClient", stub_persistent)

    errors: List[BaseException] = []
    results: List[object] = []

    def runner():
        try:
            results.append(rag.client)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    t1 = threading.Thread(target=runner)
    t2 = threading.Thread(target=runner)
    t1.start()
    # Wait until T1 is inside the constructor (lock held + about to assign)
    # before starting T2 — ensures T2 parks on the init lock.
    assert inside_constructor.wait(timeout=2), "T1 never entered constructor"
    t2.start()
    # Give T2 a moment to actually reach `_init_lock.acquire()` and park.
    time.sleep(0.05)
    release_constructor.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not errors, f"runner threads raised: {errors!r}"
    assert not t1.is_alive() and not t2.is_alive()
    assert len(constructed) == 1, (
        f"expected exactly 1 PersistentClient via double-checked locking; "
        f"got {len(constructed)} — TOCTOU window is open"
    )
    # Both threads must observe the same client object — the second
    # caller's double-check sees `_client` already set and returns it.
    assert len(results) == 2
    assert results[0] is results[1] is constructed[0]


def test_init_lock_uncontended_at_boot():
    """Acquiring the init lock during a single-threaded boot must be
    instantaneous (no startup-latency regression). Smoke-level threshold
    is generous so a slow CI box doesn't false-positive."""
    rag = RAGService()

    fake_persistent = MagicMock()
    t0 = time.monotonic()
    with patch.object(
        chromadb, "PersistentClient", return_value=fake_persistent
    ):
        rag._fallback_to_persistent()
    elapsed = time.monotonic() - t0

    # 50 ms is generous: an uncontended threading.Lock acquire is
    # microseconds. If we ever regress to a slow primitive (network lock,
    # multiprocessing.Lock, cross-process semaphore) this catches it.
    # Kept loose enough to absorb GC pauses on a busy CI runner.
    assert elapsed < 0.05, f"_fallback_to_persistent took {elapsed:.3f}s — lock too slow"
    assert rag._client is fake_persistent
    assert rag._mode == "PERSISTENT"


def test_reset_state_uses_dict_clear_not_rebind():
    """CB-2663 (LOW bonus): `_reset_state()` mutates `_collections` in place
    via `.clear()` rather than rebinding to `{}`. A reader that captured a
    reference to the dict before reset still observes a uniformly empty
    view — they don't keep iterating stale handles bound to the dead
    client."""
    rag = RAGService()
    rag._client = MagicMock()
    rag._mode = "PERSISTENT"
    rag._endpoint = "/some/path"
    rag._collections["key"] = MagicMock()

    captured_ref = rag._collections  # reader's captured dict reference
    rag._reset_state()

    # The captured dict reference must reflect the cleared state, NOT
    # point at an orphaned dict still containing the stale handle.
    assert captured_ref is rag._collections, (
        "_reset_state rebound _collections to a fresh dict; concurrent "
        "readers will keep iterating the stale (orphaned) dict"
    )
    assert captured_ref == {}
