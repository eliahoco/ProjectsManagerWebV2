"""
RAG Service - Semantic Search using ChromaDB
"""

import chromadb
import os
import socket
import threading
import time
from chromadb.config import Settings
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import hashlib
import json
import logging

try:
    import httpx  # CB-2729: used to coerce a per-call timeout onto the
    # chromadb HttpClient's internal httpx session (chromadb 0.5.x
    # constructs `httpx.Client(timeout=None)`). httpx is a transitive dep
    # via chromadb itself, but we import defensively so a future chromadb
    # release that drops/replaces httpx degrades gracefully (the
    # configurer below logs + skips instead of crashing init).
    _HTTPX_TIMEOUT_AVAILABLE = True
except ImportError:  # pragma: no cover — httpx is required by chromadb
    httpx = None  # type: ignore[assignment]
    _HTTPX_TIMEOUT_AVAILABLE = False

from app.config import settings

if TYPE_CHECKING:
    from models.documentation import ExecutionSummary, FeatureDocumentation

logger = logging.getLogger(__name__)


def _safe_json_list(value: Optional[str]) -> List[str]:
    """Decode a JSON-array TEXT column to list[str]; never raise.

    Returns [] on missing/malformed input. Logs at debug so silent
    integrity issues are still observable when DEBUG is on.
    """
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        logger.debug("Failed to decode JSON list field: %r", value[:120])
        return []
    if isinstance(decoded, list):
        return [str(item) for item in decoded if item is not None]
    logger.debug("JSON list field decoded to non-list: %s", type(decoded).__name__)
    return []


def _configure_http_client_timeout(
    client: Any, timeout_s: float
) -> bool:
    """CB-2729: coerce a per-call timeout onto the chromadb HttpClient's
    underlying httpx session.

    chromadb 0.5.x's `chromadb.api.fastapi.FastAPI.__init__` builds
    `self._session = httpx.Client(timeout=None)` and never reconfigures
    it — every heartbeat / list_collections / count() inherits the
    no-timeout default. When the chromadb server hangs (stuck container,
    CLOSE_WAIT socket, slow-loris), those calls block the caller's
    thread indefinitely. The /api/system/rag/status endpoint hits all
    three on every cache miss, so a single stuck dependency would
    otherwise pin the FastAPI worker thread that handles the request.

    The fix mutates `client._server._session.timeout` post-construction
    (the only hook chromadb exposes — there is no public `timeout=`
    kwarg on `chromadb.HttpClient` as of 0.5.23). Private attribute
    access is intentional and load-bearing: the alternative is reaching
    into chromadb's Settings (which only exposes per-operation timeouts
    for query/sysdb/logservice — heartbeat is none of those) or running
    our own httpx pool against the chromadb HTTP API directly. Both are
    significantly more invasive.

    Returns True on success, False if the internal layout changed or
    httpx isn't importable. Failures log at WARNING (operators should
    notice the regression) but never raise — we'd rather have a
    timeout-less client than refuse to start the backend.

    The defensive try/except is paired with a regression test
    (`test_init_configures_http_timeout`) that asserts the timeout
    landed on the session — if chromadb refactors `_session` away, the
    test fails loudly at the same time as this returns False, so the
    silent-degradation path is never reached in practice.
    """
    if not _HTTPX_TIMEOUT_AVAILABLE:
        logger.warning(
            "Cannot configure ChromaDB HTTP timeout — httpx not importable; "
            "status-endpoint probes have no per-call timeout (CB-2729)"
        )
        return False
    try:
        # `client._server` is the chromadb FastAPI instance; `_session` is
        # its httpx.Client. Setting `.timeout` here propagates to every
        # subsequent `_session.request(...)` call (heartbeat / list /
        # count all flow through that single method).
        client._server._session.timeout = httpx.Timeout(timeout_s)
        return True
    except AttributeError as exc:
        logger.warning(
            "Could not configure ChromaDB HTTP timeout — chromadb internal "
            "layout changed (%s); status-endpoint probes have no per-call "
            "timeout (CB-2729)", exc,
        )
        return False


# CB-2220: anchor to backend/ package root, not process CWD. A relative
# "./data/chroma" silently moved with `os.getcwd()` — systemd unit with a
# non-backend WorkingDirectory or a sibling helper script would write the
# embedded SQLite fallback to a different disk location, making prior
# embeddings appear missing.  Path(__file__).resolve() also collapses any
# parent symlinks so the fallback can never land in a writable parent CWD
# with unexpected permissions.
PERSISTENT_FALLBACK_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "chroma"
)


class RAGService:
    """Service for RAG (Retrieval Augmented Generation) using ChromaDB"""

    # CB-2729: bound on `_status_cache_lock.acquire()` blocking when a
    # caller misses the TTL cache. (1)+(2) of the CB-2729 fix already
    # remove the worst-case event-loop pin (httpx timeout + asyncio.to_thread),
    # but a short acquire bound is the belt-and-braces guarantee that
    # status callers can never stack indefinitely on a slow probe even
    # if the timeout configurer fails or chromadb internal layout changes
    # mid-deploy. 0.5 s ≪ httpx 2 s ceiling ⇒ a healthy probe always
    # completes before contention timeout fires; 0.5 s ≫ TCP-on-loopback
    # round-trip ⇒ no false-positive contention drops in steady-state.
    STATUS_LOCK_ACQUIRE_TIMEOUT_S: float = 0.5

    # CB-2218: TTL window for the status-payload cache (seconds).
    # The /api/system/rag/status endpoint is polled at 30 s by the always-
    # mounted Service Monitor card; with M open tabs and N collections each
    # uncached call fans out to M·(N+2) ChromaDB round-trips per 30 s window
    # (heartbeat + list_collections + count() per collection). ChromaDB has
    # no rate limit of its own, so a noisy multi-tab session could degrade
    # RAG responsiveness for AI execution exactly when it's needed.
    # 10 s ≪ poll cadence ⇒ each fresh poll cycle still gets a fresh probe;
    # 10 s > render-jitter ⇒ M concurrent tabs in the same window collapse
    # to a single ChromaDB pass. Combined with the threading.Lock-based
    # single-flight in `get_status_payload()`, the worst-case RT cost
    # becomes (N+2) per 10 s regardless of tab count.
    STATUS_CACHE_TTL_S: float = 10.0

    def __init__(self):
        self._client = None
        self._collections: Dict[str, Any] = {}
        # CB-2043: surface RAG mode at startup so silent fallback to the
        # embedded SQLite path can never recur. `_mode` is one of
        # {"HTTP", "PERSISTENT", None}; `_endpoint` carries the host:port
        # or filesystem path that backs the active client.
        # CB-2215 (F-5): renamed from `_mode_detail` for naming-truth — this
        # field is the endpoint identifier (host:port or abspath), not a
        # generic "detail" string.
        self._mode: Optional[str] = None
        self._endpoint: Optional[str] = None
        # CB-2215 (F-9 follow-up from code-reviewer + security-auditor):
        # state-edge log gating for the status-endpoint probes. The endpoint
        # is polled every 30s — flat WARN per failure spammed ~120 lines/h
        # while chromadb was down (F-9 motivation), but a flat downgrade to
        # DEBUG also lost the first-failure signal that's the most useful
        # log line in an outage post-mortem (and the recovery edge that
        # confirms a restore worked). Track the last-observed health per
        # probe so we WARN once on transition healthy→unhealthy, INFO once
        # on unhealthy→healthy, and DEBUG for steady-state.
        # Initial value None → first observed state never WARNs spuriously
        # for a fresh service.
        self._last_heartbeat_ok: Optional[bool] = None
        self._last_list_collections_ok: Optional[bool] = None
        # CB-2218: cached status payload + monotonic timestamp it was
        # computed at. Lock is `threading.Lock` (not `asyncio.Lock`) because
        # the underlying ChromaDB client is sync — FastAPI runs the async
        # endpoint in the event loop but `_compute_status_payload()` itself
        # is synchronous and can be reached from threadpool callers (tests,
        # `describe_mode()`, future sync entry points). A threading lock
        # gives correct mutual exclusion in either case without any
        # event-loop-vs-thread asymmetry. Held for the duration of the
        # compute so concurrent callers single-flight onto one ChromaDB
        # pass instead of stampeding the cache miss.
        self._status_cache: Optional[Dict[str, Any]] = None
        self._status_cache_at: float = 0.0
        self._status_cache_lock = threading.Lock()
        # CB-2663: serialize the reset+construct sequence shared by
        # `_init_client_blocking()`, `_fallback_to_persistent()`, and the
        # property-fallback in `client`. RAGService is a process-level
        # singleton hung off `app.state.rag` and reached from async FastAPI
        # handlers via `asyncio.to_thread()`; today only the lifespan calls
        # the init paths so contention is zero, but a future runtime-
        # reconnect surface (e.g. admin endpoint) racing with the property
        # fallback would otherwise construct two clients on the same
        # SQLite-backed PersistentClient path — undefined behaviour up to
        # and including DB lock-file corruption. A `threading.Lock` (NOT
        # `asyncio.Lock`) is the right primitive because every caller
        # of these methods is sync and crosses the event-loop boundary
        # via `to_thread`; an asyncio lock would simply not bind across
        # the threadpool. The lock is only ever held during the short
        # reset+construct window (microseconds at boot, dominated by the
        # ChromaDB heartbeat timeout in degraded paths), so it is
        # uncontended in the steady-state hot path that goes through
        # `client` after `_client` is set.
        #
        # Lock-ordering convention (see CB-2663 audit, code-review LOW-2 +
        # security LOW-3): if a future caller ever needs to hold both
        # `_init_lock` and `_status_cache_lock` at the same time, ALWAYS
        # acquire `_init_lock` first, then `_status_cache_lock`. Today no
        # path holds both — the init paths write `_status_cache = None`
        # under `_init_lock` without acquiring `_status_cache_lock` (see
        # `_reset_state` docstring for the startup-only justification) —
        # but pinning the order here prevents a future runtime-reconnect
        # surface from inverting it and deadlocking against
        # `get_status_payload()`.
        self._init_lock = threading.Lock()

    @property
    def client(self):
        """Return the already-initialized ChromaDB client.

        Must be initialized at startup via _init_client_blocking() /
        _fallback_to_persistent() before the first request hits.
        If somehow still None, fall back synchronously (degraded path).

        CB-2663: the `_client is None` check + fallback construction now
        runs under `_init_lock` with double-checked locking. The outer
        unlocked check keeps the steady-state hot path (`_client` already
        set) lock-free; the inner re-check after acquire closes the TOCTOU
        window where two threads could both observe `_client is None` and
        each construct a duplicate `PersistentClient` on the same SQLite
        path — the latent race CB-2663 was filed for.
        """
        if self._client is None:
            with self._init_lock:
                if self._client is None:
                    logger.warning(
                        "ChromaDB client accessed before startup init; "
                        "falling back to PersistentClient synchronously"
                    )
                    self._construct_persistent_client_locked()
        return self._client

    def _reset_state(self) -> None:
        """CB-2212: zero out every field that depends on the active client.

        Both init paths (`_init_client_blocking`, `_fallback_to_persistent`)
        must reset identically — otherwise a future "reconnect" caller can
        leave `_collections` pointing at handles bound to a dead client
        (the half-initialised state CB-2043's reset block aimed to prevent).

        CB-2663 contract: callers in the init paths hold `_init_lock`. This
        method itself does NOT acquire the lock — it is the inner reset
        primitive shared by `_init_client_blocking`,
        `_fallback_to_persistent`, and the property-fallback in `client`,
        all of which acquire `_init_lock` first. Tests that drive
        `_reset_state()` directly to assert the reset contract are
        single-threaded and exempt.
        """
        self._client = None
        self._mode = None
        self._endpoint = None
        # CB-2663 (LOW bonus from same audit): mutate the existing dict in
        # place rather than rebinding to a fresh `{}`. A concurrent reader
        # mid-iteration over `_collections` (e.g. a snapshotting helper that
        # captured `dict(rag._collections).items()` outside the lock) sees a
        # uniformly emptied view rather than a frozen reference to a now-
        # detached dict still bound to handles of the dead client. The
        # primary lock-guard above already prevents *new* writers from
        # racing; `.clear()` reduces blast radius if a future caller leaks
        # an unsynchronised read of the dict.
        self._collections.clear()
        # Reset health-edge tracking too — a reconnect should treat the new
        # client as a fresh subject. Without this, a healthy old client →
        # reset → degraded new client would silently log DEBUG instead of
        # WARN on the first failure of the new client.
        self._last_heartbeat_ok = None
        self._last_list_collections_ok = None
        # CB-2218: clear the status cache on every state reset. A reconnect
        # (HTTP→PERSISTENT fallback or future runtime reattach) must NOT
        # serve a stale prior-mode payload during the post-reset TTL window
        # — that would mask the very mode-transition the status surface
        # exists to expose, and let "fallback_active=False" linger on a
        # client that has already fallen back.
        #
        # CB-2729 sec audit (MEDIUM): we do not take `_status_cache_lock`
        # here even though `_fallback_to_persistent()` is reachable post-
        # startup via the property fallback in `client` (rag_service.py
        # `client` getter). Two reasons that combination is safe today:
        #
        #   1. The property fallback only fires on the very first
        #      `client` access — after init, `_client` is non-None and
        #      the unlocked check skips the lock entirely, so the
        #      runtime path that actually calls `_reset_state()` is
        #      bounded to the first request hitting a service whose
        #      lifespan startup failed. After that first reset the
        #      property fallback never reaches `_reset_state()` again.
        #   2. The TTL fast-path read in `get_status_payload()` reads
        #      `_status_cache` and `_status_cache_at` as two atomic
        #      attribute reads. Across a reset that happens between
        #      those reads, the four torn-pair outcomes are:
        #        (old_cache, old_at) — TTL math identical to before
        #          the reset; serves stale at most once before the next
        #          poll catches up.
        #        (None, old_at)     — `cached is None` short-circuits;
        #          lock acquired, recomputes against the new client.
        #        (old_cache, 0.0)   — `now - 0.0` is huge, TTL gate
        #          fails; lock acquired, recomputes.
        #        (None, 0.0)        — `cached is None` short-circuits;
        #          lock acquired, recomputes.
        #      None of the four returns a payload from the wrong mode;
        #      worst case is one redundant pre-reset stale read on the
        #      caller that lost the race, then convergence on the next
        #      poll. Adding a lock acquisition here would serialize
        #      cache reset against in-flight cache reads, which would
        #      defeat the point of the lock-free fast path that
        #      CB-2729 introduced for the loop-pin fix.
        #
        # If a future runtime-reconnect surface (e.g. an admin endpoint
        # that calls `_init_client_blocking()` mid-flight) is added, the
        # convention pinned in `_init_lock`'s docstring requires the
        # caller to acquire `_init_lock` first and then `_status_cache_lock`
        # before mutating cache state — that gives the strict-consistency
        # guarantee the current "torn-read is safe-by-arithmetic" relies on.
        self._status_cache = None
        self._status_cache_at = 0.0

    def _init_client_blocking(self) -> None:
        """Blocking: probe TCP, construct HttpClient, verify via heartbeat.

        Raises on any connectivity failure so the caller can fall back.
        Intended to be called via asyncio.to_thread() from the lifespan.

        CB-2663: the entire reset+probe+construct sequence runs under
        `_init_lock` so a future runtime-reconnect caller racing with
        the property-fallback in `client` cannot construct duplicate
        clients on the same backing store. Lock is uncontended at boot
        (single lifespan caller) so there is no startup-latency cost.
        On failure the lock is released by `with`-block unwind and
        `_reset_state()` has already cleared `_client`/`_mode`/`_endpoint`,
        so the next caller sees a clean slate.
        """
        with self._init_lock:
            # CB-2043 (review): reset mode/client up front so a mid-init
            # failure cannot leave stale `_mode` reporting HTTP while
            # `_client` is None or still pointing at a previous backend.
            self._reset_state()

            host = settings.CHROMA_HOST
            port = settings.CHROMA_PORT

            # Fast TCP probe with 5 s timeout — avoids the 75 s macOS SYN hang
            try:
                conn = socket.create_connection((host, port), timeout=5)
                conn.close()
            except OSError as exc:
                raise ConnectionError(
                    f"ChromaDB TCP probe failed ({host}:{port}): {exc}"
                ) from exc

            client = chromadb.HttpClient(host=host, port=port)

            # CB-2729: configure a per-call HTTP timeout on the chromadb
            # HttpClient before the first probe. chromadb 0.5.x constructs
            # `_session = httpx.Client(timeout=None)` internally, so any
            # subsequent heartbeat / list_collections / count() blocks
            # indefinitely if the server hangs (CLOSE_WAIT, slow-loris,
            # half-closed TCP). Without this, `get_status_payload()` could
            # pin its worker thread for the full TCP keepalive interval —
            # CB-2729's audit-finding DoS shape. Failure to configure the
            # timeout (chromadb internals changed, httpx unavailable) is
            # logged but non-fatal: degraded behaviour matches the prior
            # status quo, which is strictly better than refusing to start.
            _configure_http_client_timeout(
                client, settings.CHROMA_HTTP_TIMEOUT_S
            )

            # Heartbeat confirms the server is actually responding to HTTP
            try:
                client.heartbeat()
            except Exception as exc:
                raise ConnectionError(
                    f"ChromaDB heartbeat failed ({host}:{port}): {exc}"
                ) from exc

            self._client = client
            self._mode = "HTTP"
            self._endpoint = f"{host}:{port}"

    def _construct_persistent_client_locked(self) -> None:
        """CB-2663: reset+construct PersistentClient. Caller MUST hold `_init_lock`.

        Extracted from `_fallback_to_persistent` so the property-fallback in
        `client` can call the construction body while already holding the
        lock (Python's `threading.Lock` is non-reentrant — having the public
        `_fallback_to_persistent` method also acquire the lock would
        otherwise deadlock the property-fallback path). All assignments to
        `_client`/`_mode`/`_endpoint`/`_collections` happen here under the
        lock, so any concurrent reader either sees the prior fully-
        consistent state or the new one — never a torn mix.
        """
        # CB-2043 (review): reset state so a PersistentClient(...) raise
        # cannot leave the prior HTTP `_mode` advertised next to a now-None
        # client.
        self._reset_state()

        self._client = chromadb.PersistentClient(
            path=PERSISTENT_FALLBACK_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        self._mode = "PERSISTENT"
        self._endpoint = os.path.abspath(PERSISTENT_FALLBACK_PATH)

    def _fallback_to_persistent(self) -> None:
        """Switch to a local PersistentClient (no external server needed).

        CB-2663: acquires `_init_lock` then delegates to
        `_construct_persistent_client_locked()`. See that helper for the
        rationale on the lock split.
        """
        with self._init_lock:
            self._construct_persistent_client_locked()

    def describe_mode(self) -> str:
        """CB-2043: build a one-line summary of the active RAG backend.

        Format:
          RAG mode=HTTP host=<host> port=<port> collections=<N>
          RAG mode=PERSISTENT path_hash=<8-hex> collections=<N>
          RAG mode=UNINITIALIZED

        Collection count is best-effort — a count failure must never block
        startup logging, so we fall back to "?" rather than raise.

        CB-2669: the PERSISTENT branch logs a stable blake2s digest of the
        abspath instead of the path itself. CB-2216 redacted this abspath
        from /api/system/rag/status because the endpoint is reachable by
        any local Origin-less caller; logging the literal path here at
        INFO via main.py's `[startup] %s` would re-disclose the same
        string to anyone with read access to logs/backend.log, journald,
        or a captured stdout pipe — defeating the CB-2216 redaction
        off-band. The 4-byte digest preserves boot-log diagnostic value
        (operators can still compare `path_hash` across boots to confirm
        the fallback location is stable across restarts) without
        revealing the underlying filesystem layout.
        """
        if self._mode is None or self._client is None:
            return "RAG mode=UNINITIALIZED"

        try:
            collections = self._client.list_collections()
            count = len(collections) if collections is not None else 0
            count_str = str(count)
        except Exception as exc:
            logger.debug("list_collections failed during describe_mode: %s", exc)
            count_str = "?"

        if self._mode == "HTTP":
            host, _, port = (self._endpoint or "").partition(":")
            return (
                f"RAG mode=HTTP host={host or '?'} port={port or '?'} "
                f"collections={count_str}"
            )
        endpoint = self._endpoint
        if endpoint:
            path_hash = hashlib.blake2s(
                endpoint.encode("utf-8"), digest_size=4
            ).hexdigest()
        else:
            # CB-2669 (code-review M-1): reaching this branch means
            # `_mode == "PERSISTENT"` and `_client` is set but `_endpoint`
            # is empty — a half-init state that CB-2213's invariant tests
            # are supposed to make impossible. Emit a WARN so a future
            # refactor that breaks the invariant produces a loud signal
            # instead of a silent `path_hash=?` lie.
            logger.warning(
                "describe_mode: PERSISTENT mode with empty _endpoint — "
                "half-init invariant broken (CB-2213/CB-2669)"
            )
            path_hash = "?"
        return (
            f"RAG mode=PERSISTENT path_hash={path_hash} "
            f"collections={count_str}"
        )

    @staticmethod
    def _clone_status_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """CB-2729 audit (HIGH-1): caller-safe copy of a status payload.

        Used by every return path in `get_status_payload()` so callers
        can never mutate (`payload["collections"].append(...)`,
        `payload["healthy"] = False`, …) into the shared cache. Shallow-
        copies the outer dict and the inner `collections` list, plus
        each per-collection row dict — that's all the mutation surface
        the payload carries. Other top-level fields are immutable
        primitives (str, int, bool) so the outer `dict()` is enough.

        Cheaper than `copy.deepcopy()` (microseconds vs. tens of
        microseconds on the typical 8-collection payload) and tighter:
        deepcopy would also copy inner dict values, but those are all
        primitives so there's nothing left to share.
        """
        clone: Dict[str, Any] = dict(payload)
        if "collections" in clone:
            clone["collections"] = [dict(row) for row in clone["collections"]]
        return clone

    def _synthesize_degraded_payload(self) -> Dict[str, Any]:
        """CB-2729: minimal payload for the contention-no-cache path.

        Used when `_status_cache_lock.acquire()` times out AND no prior
        cache exists to serve. Reflects the configured mode (so the
        Service Monitor card still shows HTTP vs PERSISTENT correctly)
        but reports `healthy=False` and zero collections — every probe
        is skipped because another caller is mid-compute on the lock.

        Mirrors the field shape of `_compute_status_payload()` so callers
        can treat the result interchangeably; the only signal the
        contention path leaks is `healthy=False`. CB-2216 path-redaction
        is preserved (PERSISTENT mode reports `endpoint=""`,
        `fallback_active=True`).

        Reads `_mode` / `_endpoint` without the cache lock — those are
        primitive attributes in CPython so single-attribute reads are
        atomic at the bytecode level. Worst case is a torn read across
        a concurrent reset (mode says HTTP, endpoint says ""); the
        downstream consumer still sees `healthy=False` and the next
        cache-miss call (TTL window 10s) will resolve to consistent state.
        """
        if self._mode is None or self._client is None:
            return {
                "mode": "UNINITIALIZED",
                "endpoint": "",
                "port": 0,
                "fallback_active": False,
                "collections": [],
                "total_docs": 0,
                "healthy": False,
            }
        if self._mode == "HTTP":
            host_part, _, port_part = (self._endpoint or "").partition(":")
            try:
                port = int(port_part) if port_part else 0
            except ValueError:
                port = 0
            return {
                "mode": "HTTP",
                "endpoint": host_part,
                "port": port,
                "fallback_active": False,
                "collections": [],
                "total_docs": 0,
                "healthy": False,
            }
        # PERSISTENT — endpoint redacted per CB-2216 contract.
        return {
            "mode": "PERSISTENT",
            "endpoint": "",
            "port": 0,
            "fallback_active": True,
            "collections": [],
            "total_docs": 0,
            "healthy": False,
        }

    def get_status_payload(self) -> Dict[str, Any]:
        """CB-2045: structured status snapshot for /api/system/rag/status.

        CB-2218: TTL-cached single-flight wrapper around the actual probe.
        Returns the cached payload if it was computed within the last
        `STATUS_CACHE_TTL_S` seconds (10 s); otherwise acquires the cache
        lock, recomputes once, and returns the fresh result. Concurrent
        callers that miss the TTL serialize on the lock so M open tabs
        share a single ChromaDB pass per window — the M·(N+2) RT amplifier
        described on the ticket collapses to (N+2) per TTL.

        Cache rationale + TTL choice are documented on
        `STATUS_CACHE_TTL_S`. State-edge logging (WARN-once-on-transition
        for heartbeat / list_collections failures) is preserved
        unchanged: it fires on actual probes, so a cache hit is silent
        (no probe → no new outcome → no log line), and the first probe
        after expiry still detects healthy⇄unhealthy transitions.

        CB-2729: lock acquisition is bounded by
        `STATUS_LOCK_ACQUIRE_TIMEOUT_S` (0.5 s). Steady-state: every
        probe completes well under the bound (httpx 2 s ceiling +
        ChromaDB-on-loopback ≪ 100 ms), so contention is unobservable.
        Failure mode: a stuck ChromaDB stalls the lock holder for the
        full httpx timeout (2 s); concurrent callers that arrive during
        that window time out on the lock and serve the prior cached
        payload with `healthy=False` overwritten — better than queueing
        indefinitely and worse than blowing the cache, so the Service
        Monitor card still renders meaningful state during the outage.
        Combined with the `asyncio.to_thread` wrapper in `api/system.py`
        and the per-call httpx timeout in `_init_client_blocking()`,
        this caps the worst-case status-endpoint latency at ~2.5 s
        regardless of dependency health, and prevents one stuck dep
        from pinning the entire FastAPI worker thread.

        See `_compute_status_payload()` for the per-probe contract +
        full payload shape, `_synthesize_degraded_payload()` for the
        contention-with-no-cache fallback shape.
        """
        # Lock-free fast path: TTL hit. Reading `_status_cache` and
        # `_status_cache_at` outside the lock is safe in CPython
        # because individual attribute reads are atomic; a stale
        # snapshot (cache value from one moment, timestamp from another)
        # at worst causes a redundant lock acquire on the next call,
        # never a torn payload. The lock is only ever needed to
        # serialize the compute on a cache miss.
        #
        # CB-2729 audit follow-up (HIGH-1): every return path returns
        # `dict(cached)` rather than the live cached dict object. The
        # cached payload is shared state — handing the same reference
        # back to many callers means a single misbehaving caller
        # (`payload["collections"].sort()`, `payload["healthy"] = False`,
        # …) can poison the cache for every other reader and break the
        # contention path that copies the same dict to flag degraded
        # state. Today no caller mutates (the FastAPI handler just
        # splats it into a Pydantic model), but the asymmetry vs. the
        # contention path's `dict(stale)` copy was flagged as a latent
        # leak. Shallow copy is sufficient — the inner `collections`
        # list contains plain dicts that the cache itself never re-uses
        # across compute cycles (a fresh list is built on each
        # `_compute_status_payload()` pass), so deep copying would only
        # add cost without preventing a realistic mutation pattern.
        now = time.monotonic()
        cached = self._status_cache
        cached_at = self._status_cache_at
        if (
            cached is not None
            and (now - cached_at) < self.STATUS_CACHE_TTL_S
        ):
            return self._clone_status_payload(cached)

        acquired = self._status_cache_lock.acquire(
            timeout=self.STATUS_LOCK_ACQUIRE_TIMEOUT_S
        )
        if not acquired:
            # CB-2729: contention bound exceeded — a prior caller is
            # still inside `_compute_status_payload()`. Serve last-known
            # state with healthy=False so the surface degrades visibly
            # rather than blocking the worker thread. The next request
            # in this TTL window will either find the cache populated
            # (winner finished) or hit this same path again — either way
            # the bound is preserved per call.
            stale = self._status_cache
            if stale is not None:
                degraded = self._clone_status_payload(stale)
                degraded["healthy"] = False
                return degraded
            return self._synthesize_degraded_payload()

        try:
            # Re-check TTL after acquire — the prior lock-holder may have
            # already populated the cache while we were waiting.
            now = time.monotonic()
            cached = self._status_cache
            if (
                cached is not None
                and (now - self._status_cache_at) < self.STATUS_CACHE_TTL_S
            ):
                # CB-2729 audit (HIGH-1): copy on the way out, same
                # rationale as the lock-free fast path — caller-side
                # mutation must never poison the cached dict or its
                # `collections` sub-list.
                return self._clone_status_payload(cached)
            payload = self._compute_status_payload()
            # Store + timestamp inside the lock so a concurrent caller
            # waiting on the lock sees a consistent (cache, timestamp)
            # pair when it acquires.
            self._status_cache = payload
            self._status_cache_at = now
            # Fresh compute → return a copy too so the cached object
            # and the returned object are independent from this call
            # forward. (The first caller of a fresh probe used to share
            # the dict with the cache; this asymmetry vs. subsequent
            # cache-hit callers is the one HIGH-1 explicitly named.)
            return self._clone_status_payload(payload)
        finally:
            self._status_cache_lock.release()

    def _compute_status_payload(self) -> Dict[str, Any]:
        """Actual ChromaDB probe — heartbeat + list_collections + per-col count.

        Public callers go through `get_status_payload()` so the result is
        TTL-cached (CB-2218). Direct callers must hold a sensible lock
        themselves if they care about avoiding redundant probes.

        Returns a dict with:
          - mode: "HTTP" | "PERSISTENT" | "UNINITIALIZED"
          - endpoint: str (host for HTTP; "" for PERSISTENT/UNINITIALIZED)
          - port: int (TCP port for HTTP; 0 for PERSISTENT/UNINITIALIZED)
          - fallback_active: bool (True iff mode=PERSISTENT — the embedded
            client is in use, signalling silent fallback from HTTP)
          - collections: list[{"count": int|None}]  (CB-2217: `name` removed)
          - total_docs: int (sum of successful per-collection counts; partial
            failure does not zero it; healthy=False signals partial failure)
          - healthy: bool (True iff client is up AND collection enumeration
            succeeded AND, for HTTP, heartbeat succeeded)

        Best-effort: any error during collection enumeration or per-collection
        count is captured and reflected by `healthy=False`. The endpoint must
        never raise — silent fallback or a half-broken backend is exactly what
        this surface exists to expose.

        CB-2215 (F-5): renamed `host` payload key to `endpoint` to reflect
        the dual semantics (host:port vs filesystem path).
        CB-2215 (F-9): heartbeat / list_collections failures use state-edge
        log gating — WARN once on transition healthy→unhealthy, INFO once
        on unhealthy→healthy, DEBUG for steady-state. A 30s poll cadence
        would otherwise produce ~120 WARN/hour while chromadb is down,
        drowning genuinely actionable warnings; a flat downgrade to DEBUG
        loses the first-failure / recovery edges that are the most useful
        signals in an outage post-mortem.
        CB-2216: PERSISTENT mode no longer leaks the absolute filesystem
        path — `endpoint` is "" and `fallback_active=True` is the surface
        signal. The full abspath stays on `_endpoint` for internal logging
        (`describe_mode()`, lifespan startup line) but never crosses the
        HTTP boundary, since the status endpoint is reachable by any local
        process via Origin-less curl (validate_origin in app/main.py
        intentionally allows server-to-server callers through). The user-
        named volume path was reconnaissance value if any sibling service
        on the host is later compromised.
        CB-2217: per-collection `name` (the `project_<cuid_prefix>` string)
        no longer crosses the HTTP boundary either. Collections are named
        `project_{project_id[:8]}`; echoing them on this surface let any
        local foothold enumerate which projects exist + which CUID prefixes
        are active + (combined with `count`) approximately how much content
        each project holds. The doc-count distribution is preserved because
        the Service Monitor card uses it to render "top collections by
        size" — but the array is now anonymous, so neither rank nor count
        can be back-mapped to a project. The real collection name is still
        used internally (`get_collection`, `describe_mode`); only the HTTP
        payload is redacted.
        """
        if self._mode is None or self._client is None:
            return {
                "mode": "UNINITIALIZED",
                "endpoint": "",
                "port": 0,
                "fallback_active": False,
                "collections": [],
                "total_docs": 0,
                "healthy": False,
            }

        fallback_active = self._mode == "PERSISTENT"

        if self._mode == "HTTP":
            host_part, _, port_part = (self._endpoint or "").partition(":")
            endpoint = host_part
            try:
                port = int(port_part) if port_part else 0
            except ValueError:
                port = 0
        else:
            # CB-2216: do NOT echo `self._endpoint` (abspath) — see docstring.
            endpoint = ""
            port = 0

        healthy = True

        if self._mode == "HTTP":
            try:
                self._client.heartbeat()
                heartbeat_ok = True
            except Exception as exc:
                heartbeat_ok = False
                if self._last_heartbeat_ok is not False:
                    # First failure (or transition from healthy) — make it
                    # loud so the outage edge is visible in `tail -f`.
                    logger.warning(
                        "RAG heartbeat failed during get_status_payload: %s", exc
                    )
                else:
                    logger.debug(
                        "RAG heartbeat still failing during get_status_payload: %s",
                        exc,
                    )
                healthy = False
            if heartbeat_ok and self._last_heartbeat_ok is False:
                logger.info("RAG heartbeat recovered")
            self._last_heartbeat_ok = heartbeat_ok

        collections_payload: List[Dict[str, Any]] = []
        total_docs = 0
        try:
            collections = self._client.list_collections() or []
            list_ok = True
        except Exception as exc:
            list_ok = False
            if self._last_list_collections_ok is not False:
                logger.warning(
                    "RAG list_collections failed during get_status_payload: %s", exc
                )
            else:
                logger.debug(
                    "RAG list_collections still failing during get_status_payload: %s",
                    exc,
                )
            collections = []
            healthy = False
        if list_ok and self._last_list_collections_ok is False:
            logger.info("RAG list_collections recovered")
        self._last_list_collections_ok = list_ok

        for idx, col in enumerate(collections):
            try:
                count = col.count()
                total_docs += int(count)
            except Exception as exc:
                # CB-2669: log the loop index, not the collection name.
                # CB-2217 forbids the name from the HTTP payload because
                # `project_<cuid_prefix>` enumerates projects; including the
                # name in a DEBUG log re-discloses the same string off-band
                # to anyone who flips the logger to DEBUG (or scrapes a
                # captured stdout pipe). The index is sufficient to
                # correlate the log line with the position-aligned
                # `collections_payload` entry returned to the operator.
                logger.debug(
                    "count() failed for collection #%d in get_status_payload: %s",
                    idx, exc,
                )
                count = None
                healthy = False
            collections_payload.append({"count": count})

        return {
            "mode": self._mode,
            "endpoint": endpoint,
            "port": port,
            "fallback_active": fallback_active,
            "collections": collections_payload,
            "total_docs": total_docs,
            "healthy": healthy,
        }

    def get_collection(self, project_id: str):
        """Get or create a collection for a project"""
        collection_name = f"project_{project_id[:8]}"

        if collection_name not in self._collections:
            self._collections[collection_name] = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"project_id": project_id},
            )

        return self._collections[collection_name]

    def generate_doc_id(self, issue_id: str, content_type: str = "issue") -> str:
        """Generate a unique document ID"""
        return hashlib.md5(f"{content_type}:{issue_id}".encode()).hexdigest()

    async def embed_issue(
        self,
        project_id: str,
        issue_id: str,
        key: str,
        title: str,
        description: Optional[str] = None,
        issue_type: str = "TASK",
        status: str = "BACKLOG",
        labels: Optional[str] = None,
    ) -> bool:
        """Embed an issue into the vector store"""
        try:
            collection = self.get_collection(project_id)

            # Create document text
            doc_parts = [
                f"[{key}] {title}",
                f"Type: {issue_type}",
                f"Status: {status}",
            ]
            if description:
                doc_parts.append(f"Description: {description}")
            if labels:
                doc_parts.append(f"Labels: {labels}")

            document = "\n".join(doc_parts)
            doc_id = self.generate_doc_id(issue_id)

            # Upsert to collection
            collection.upsert(
                ids=[doc_id],
                documents=[document],
                metadatas=[{
                    "issue_id": issue_id,
                    "key": key,
                    "type": issue_type,
                    "status": status,
                }],
            )

            return True
        except Exception as e:
            print(f"Error embedding issue: {e}")
            return False

    async def delete_issue_embedding(self, project_id: str, issue_id: str) -> bool:
        """Delete an issue embedding"""
        try:
            collection = self.get_collection(project_id)
            doc_id = self.generate_doc_id(issue_id)
            collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            print(f"Error deleting embedding: {e}")
            return False

    async def search_issues(
        self,
        project_id: str,
        query: str,
        n_results: int = 10,
        filter_type: Optional[str] = None,
        filter_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar issues using semantic search"""
        try:
            collection = self.get_collection(project_id)

            # Build where filter
            where_filter = None
            if filter_type or filter_status:
                conditions = []
                if filter_type:
                    conditions.append({"type": filter_type})
                if filter_status:
                    conditions.append({"status": filter_status})

                if len(conditions) == 1:
                    where_filter = conditions[0]
                else:
                    where_filter = {"$and": conditions}

            # Query
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            # Format results
            search_results = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    search_results.append({
                        "issue_id": results["metadatas"][0][i].get("issue_id"),
                        "key": results["metadatas"][0][i].get("key"),
                        "type": results["metadatas"][0][i].get("type"),
                        "status": results["metadatas"][0][i].get("status"),
                        "document": results["documents"][0][i] if results["documents"] else None,
                        "distance": results["distances"][0][i] if results["distances"] else None,
                        "score": 1 - (results["distances"][0][i] if results["distances"] else 0),
                    })

            return search_results
        except Exception as e:
            print(f"Error searching: {e}")
            return []

    async def find_similar_issues(
        self,
        project_id: str,
        title: str,
        description: Optional[str] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find issues similar to the given title/description"""
        query = title
        if description:
            query = f"{title}\n{description}"

        return await self.search_issues(project_id, query, n_results)

    async def get_context_for_ai(
        self,
        project_id: str,
        query: str,
        n_results: int = 5,
    ) -> str:
        """Get relevant context for AI operations"""
        results = await self.search_issues(project_id, query, n_results)

        if not results:
            return "No relevant issues found."

        context_parts = ["Relevant existing issues:"]
        for r in results:
            context_parts.append(f"- [{r['key']}] ({r['type']}, {r['status']})")
            if r.get("document"):
                # Extract just the title from the document
                lines = r["document"].split("\n")
                if lines:
                    context_parts.append(f"  {lines[0]}")

        return "\n".join(context_parts)

    async def embed_ai_context(
        self,
        project_id: str,
        issue_id: str,
        issue_key: str,
        issue_type: str,
        ai_context: str,
    ) -> bool:
        """
        Embed an issue's aiContext text into ChromaDB for RAG retrieval.

        Uses a separate doc_id (content_type="ai_context") so it doesn't
        overwrite the standard issue embedding.
        """
        try:
            collection = self.get_collection(project_id)
            doc_id = self.generate_doc_id(issue_id, content_type="ai_context")

            document = f"[{issue_key}] AI Context ({issue_type}):\n{ai_context}"

            collection.upsert(
                ids=[doc_id],
                documents=[document],
                metadatas=[{
                    "issue_id": issue_id,
                    "key": issue_key,
                    "type": issue_type,
                    "context_type": "ai_context",
                }],
            )

            logger.info(f"Embedded aiContext for {issue_key} into ChromaDB")
            return True
        except Exception as e:
            logger.warning(f"Error embedding aiContext for {issue_key}: {e}")
            return False

    async def embed_execution_summary(
        self,
        project_id: str,
        issue_id: str,
        issue_key: str,
        summary: "ExecutionSummary",
    ) -> bool:
        """Index an ExecutionSummary into ChromaDB for RAG retrieval.

        Uses a stable per-issue doc_id so the latest summary for an issue
        replaces any prior one (mirrors the embed_ai_context() pattern).
        """
        try:
            doc_text = (
                f"[{issue_key}] Implementation Summary:\n"
                f"{summary.summary or ''}\n\n"
            )
            if summary.architectureNotes:
                doc_text += f"Architecture: {summary.architectureNotes}\n"
            if summary.technicalNotes:
                doc_text += f"Technical: {summary.technicalNotes}\n"
            if summary.componentsModified:
                components = _safe_json_list(summary.componentsModified)
                if components:
                    doc_text += f"Components: {', '.join(components)}\n"
            if summary.filesTouched:
                files = _safe_json_list(summary.filesTouched)
                if files:
                    # Cap files in the embedded blob to keep doc size sane
                    doc_text += f"Files: {', '.join(files[:50])}\n"

            doc_id = self.generate_doc_id(
                issue_id, content_type="execution_summary"
            )
            collection = self.get_collection(project_id)
            collection.upsert(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[{
                    "issue_id": issue_id,
                    "key": issue_key,
                    "content_type": "execution_summary",
                }],
            )
            logger.info(
                "Embedded ExecutionSummary for %s into ChromaDB", issue_key
            )
            return True
        except Exception as e:
            logger.warning(
                "Error embedding ExecutionSummary for %s: %s", issue_key, e
            )
            return False

    async def embed_feature_documentation(
        self,
        project_id: str,
        feature_issue_id: str,
        feature_key: str,
        doc: "FeatureDocumentation",
    ) -> bool:
        """Index a FeatureDocumentation row into ChromaDB for RAG retrieval.

        Uses a stable per-feature doc_id (`content_type="feature_documentation"`)
        so re-running the documentation generator replaces the prior
        embedding instead of stacking duplicates. Mirrors the
        `embed_execution_summary` integration so callers can rely on the
        same (project_id, key, content_type) metadata shape when querying.

        Returns True only when the upsert succeeded; failures are logged
        and the caller is expected to NOT update `embeddingId` / `lastIndexedAt`
        on the row.
        """
        try:
            doc_text_parts = [
                f"[{feature_key}] Feature Documentation: {doc.title or ''}".strip(),
            ]
            if doc.overview:
                doc_text_parts.append(f"Overview:\n{doc.overview}")
            if doc.architecture:
                doc_text_parts.append(f"Architecture:\n{doc.architecture}")
            if doc.testingStrategy:
                doc_text_parts.append(f"Testing Strategy:\n{doc.testingStrategy}")
            if doc.techStack:
                # techStack is JSON-encoded list[str]; flatten to a CSV
                # for the embedding text rather than embedding raw JSON.
                stack = _safe_json_list(doc.techStack)
                if stack:
                    doc_text_parts.append(
                        "Tech Stack: " + ", ".join(stack[:50])
                    )

            doc_text = "\n\n".join(doc_text_parts)

            doc_id = self.generate_doc_id(
                feature_issue_id, content_type="feature_documentation"
            )
            collection = self.get_collection(project_id)
            collection.upsert(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[{
                    "issue_id": feature_issue_id,
                    "key": feature_key,
                    "content_type": "feature_documentation",
                }],
            )
            logger.info(
                "Embedded FeatureDocumentation for %s into ChromaDB", feature_key
            )
            return True
        except Exception as e:
            logger.warning(
                "Error embedding FeatureDocumentation for %s: %s",
                feature_key, e,
            )
            return False

    async def search_execution_docs(
        self,
        project_id: str,
        query: str,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search over execution summaries for a project.

        Filters the project's collection to documents indexed by
        embed_execution_summary() (content_type == "execution_summary")
        and returns the top n_results matches in the same shape as
        search_issues() so callers can format consistently.
        """
        try:
            collection = self.get_collection(project_id)

            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"content_type": "execution_summary"},
                include=["documents", "metadatas", "distances"],
            )

            search_results: List[Dict[str, Any]] = []
            if results and results.get("ids") and results["ids"][0]:
                for i, _doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] or {}
                    distance = (
                        results["distances"][0][i]
                        if results.get("distances")
                        else None
                    )
                    search_results.append({
                        "issue_id": metadata.get("issue_id"),
                        "key": metadata.get("key"),
                        "content_type": metadata.get("content_type"),
                        "document": (
                            results["documents"][0][i]
                            if results.get("documents")
                            else None
                        ),
                        "distance": distance,
                        "score": 1 - (distance if distance is not None else 0),
                    })

            return search_results
        except Exception as e:
            logger.warning(
                "Error searching execution docs for project %s: %s",
                project_id,
                e,
            )
            return []

    async def delete_ai_context_embedding(
        self,
        project_id: str,
        issue_id: str,
    ) -> bool:
        """Delete the aiContext embedding for an issue (e.g., when cleared)."""
        try:
            collection = self.get_collection(project_id)
            doc_id = self.generate_doc_id(issue_id, content_type="ai_context")
            collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.warning(f"Error deleting aiContext embedding: {e}")
            return False

    async def get_ancestor_ai_context(
        self,
        db,
        issue_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Walk up the parent chain from issue_id and collect aiContext values
        from all ancestor issues (e.g., TASK -> STORY -> EPIC -> FEATURE).

        Returns a list of dicts ordered from nearest parent to furthest ancestor:
        [
            {"issue_id": ..., "key": ..., "type": ..., "aiContext": ...},
            ...
        ]

        The `db` parameter is an AsyncSession from SQLAlchemy.
        """
        from sqlalchemy import select
        from models import Issue

        ancestors = []
        current_id = issue_id
        visited = set()

        while current_id:
            # Prevent infinite loops in case of data corruption
            if current_id in visited:
                break
            visited.add(current_id)

            # Fetch the current issue's parentId and aiContext
            result = await db.execute(
                select(Issue.id, Issue.parentId, Issue.key, Issue.type, Issue.aiContext)
                .where(Issue.id == current_id)
            )
            row = result.one_or_none()

            if not row:
                break

            issue_id_val, parent_id, key, issue_type, ai_context = row

            # Only collect from ancestors (skip the original issue itself)
            if issue_id_val != issue_id and ai_context:
                ancestors.append({
                    "issue_id": issue_id_val,
                    "key": key,
                    "type": issue_type,
                    "aiContext": ai_context,
                })

            current_id = parent_id

        return ancestors

    async def get_full_ai_context_for_execution(
        self,
        db,
        issue_id: str,
    ) -> str:
        """
        Build a formatted string of all ancestor AI context for use during
        issue execution. Includes the issue's own aiContext plus all ancestors.

        Returns a human-readable string suitable for injecting into AI prompts.
        """
        from sqlalchemy import select
        from models import Issue

        # Get the issue's own context
        result = await db.execute(
            select(Issue.key, Issue.type, Issue.aiContext)
            .where(Issue.id == issue_id)
        )
        row = result.one_or_none()

        parts = []

        if row:
            key, issue_type, own_context = row
            if own_context:
                parts.append(f"[{key}] ({issue_type}) AI Context:\n{own_context}")

        # Get ancestor contexts (nearest parent first)
        ancestors = await self.get_ancestor_ai_context(db, issue_id)

        for ancestor in ancestors:
            parts.append(
                f"[{ancestor['key']}] ({ancestor['type']}) AI Context:\n{ancestor['aiContext']}"
            )

        if not parts:
            return ""

        return "\n\n---\n\n".join(parts)

    async def get_implementation_context_for_qa(
        self,
        db,
        project_id: str,
        issue_id: str,
    ) -> str:
        """Build a formatted implementation-context string for QA test generation.

        Loads the most recent ExecutionSummary for the issue and renders a
        markdown-style block covering summary, files, components, and notes.
        Returns "" when no execution summary exists for the issue or when
        the issue does not belong to the requested project.

        Scoping by `project_id` enforces a cross-project isolation boundary:
        callers cannot exfiltrate another project's implementation summary
        by passing a foreign issue_id (CB-1597 sec audit, H-1).

        The `db` parameter is an AsyncSession from SQLAlchemy.
        """
        from sqlalchemy import select
        from models import ExecutionSummary, Issue

        result = await db.execute(
            select(ExecutionSummary)
            .join(Issue, Issue.id == ExecutionSummary.issueId)
            .where(
                ExecutionSummary.issueId == issue_id,
                Issue.projectId == project_id,
            )
            .order_by(ExecutionSummary.executedAt.desc())
            .limit(1)
        )
        summary = result.scalar_one_or_none()

        if not summary:
            return ""

        parts = [f"## Implementation Summary\n{summary.summary}"]

        files = _safe_json_list(summary.filesTouched)
        if files:
            parts.append("## Files Modified\n" + "\n".join(f"- {f}" for f in files))

        comps = _safe_json_list(summary.componentsModified)
        if comps:
            parts.append("## Components\n" + ", ".join(comps))

        if summary.architectureNotes:
            parts.append(f"## Architecture Notes\n{summary.architectureNotes}")
        if summary.technicalNotes:
            parts.append(f"## Technical Notes\n{summary.technicalNotes}")
        if summary.challengesFaced:
            parts.append(f"## Known Challenges\n{summary.challengesFaced}")

        return "\n\n".join(parts)


# No module-level singleton — instance lives on app.state.rag (see app/main.py lifespan)
