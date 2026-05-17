"""CB-2045: RAGService.get_status_payload() — structured snapshot for the
GET /api/system/rag/status endpoint.

Verifies:
  * UNINITIALIZED before any client init.
  * HTTP mode after a successful _init_client_blocking — host/port parsed,
    collections + counts enumerated, healthy=True.
  * PERSISTENT mode after _fallback_to_persistent — endpoint=abspath, port=0.
  * Heartbeat failure on HTTP flips healthy=False.
  * list_collections failure flips healthy=False without raising.
  * Per-collection count() failure → count=None and healthy=False.
"""

import os
from unittest.mock import MagicMock, patch

import chromadb
import pytest

from services.rag_service import PERSISTENT_FALLBACK_PATH, RAGService


def test_status_payload_uninitialized():
    rag = RAGService()
    payload = rag.get_status_payload()
    assert payload == {
        "mode": "UNINITIALIZED",
        "endpoint": "",
        "port": 0,
        "fallback_active": False,
        "collections": [],
        "total_docs": 0,
        "healthy": False,
    }


def _assert_no_collection_names(payload):
    """CB-2217: pin the contract that per-collection rows expose only
    `count` — no `name`, no `id`, no other string field that could
    re-leak the `project_<cuid_prefix>` enumeration.

    Used by every test in this module so a future refactor that
    re-introduces a name-shaped field under any key is caught no matter
    which mode-path the test exercises.
    """
    for row in payload["collections"]:
        assert "name" not in row, (
            f"CB-2217 regression: collection row leaked `name`: {row!r}"
        )
        for key, value in row.items():
            if isinstance(value, str):
                raise AssertionError(
                    "CB-2217 regression: collection row exposes string field "
                    f"{key!r}={value!r} — only numeric `count` is allowed."
                )


def test_status_payload_http_healthy(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    fake_socket = MagicMock()
    fake_socket.close = MagicMock()

    col_a = MagicMock()
    col_a.name = "project_aaaaaa"
    col_a.count = MagicMock(return_value=5)
    col_b = MagicMock()
    col_b.name = "project_bbbbbb"
    col_b.count = MagicMock(return_value=12)

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[col_a, col_b])

    rag = RAGService()
    with patch("services.rag_service.socket.create_connection", return_value=fake_socket), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    payload = rag.get_status_payload()
    assert payload["mode"] == "HTTP"
    assert payload["endpoint"] == "chromadb"
    assert payload["port"] == 8000
    assert payload["fallback_active"] is False
    # CB-2217: collection rows are anonymous — only `count` is reported.
    assert payload["collections"] == [{"count": 5}, {"count": 12}]
    _assert_no_collection_names(payload)
    assert payload["total_docs"] == 17
    assert payload["healthy"] is True


def test_status_payload_persistent_healthy():
    col = MagicMock()
    col.name = "project_xxxxxx"
    col.count = MagicMock(return_value=3)

    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[col])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    payload = rag.get_status_payload()
    assert payload["mode"] == "PERSISTENT"
    # CB-2216: PERSISTENT mode must NOT echo the abspath — embedded path is
    # internal-only filesystem layout, leaking it on an Origin-less-curl-able
    # endpoint is reconnaissance value if a sibling host service is later
    # compromised. `fallback_active` is the surface signal instead.
    assert payload["endpoint"] == ""
    assert payload["fallback_active"] is True
    # The internal `_endpoint` field still carries the abspath for log-side
    # use (`describe_mode()` startup line) — only the HTTP-exposed payload
    # is sanitized.
    assert rag._endpoint == os.path.abspath(PERSISTENT_FALLBACK_PATH)
    assert payload["port"] == 0
    # CB-2217: collection rows are anonymous — only `count` is reported.
    assert payload["collections"] == [{"count": 3}]
    _assert_no_collection_names(payload)
    assert payload["total_docs"] == 3
    assert payload["healthy"] is True


def test_status_payload_persistent_does_not_leak_abspath():
    """CB-2216 regression: PERSISTENT mode must never expose the absolute
    filesystem path of the embedded ChromaDB store via the status payload.

    The /api/system/rag/status endpoint is reachable by any Origin-less
    local caller (curl, sibling services on the host) — `validate_origin`
    in `app/main.py` intentionally lets server-to-server requests through.
    Echoing the abspath gave a future host-compromise attacker exactly
    where the embeddings live and what user-named volume backs them.

    The fix is payload-side sanitization (Option A in the ticket) so the
    same internal `_endpoint` field can keep the abspath for log surfaces
    (`describe_mode()`) without crossing the HTTP boundary. This test
    pins both halves of the contract — `endpoint` field and any nested
    string in the JSON-able payload must not contain the abspath.
    """
    import json as _json

    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    leaked = os.path.abspath(PERSISTENT_FALLBACK_PATH)
    # Internal field still has the abspath — that's intentional, log-only.
    assert rag._endpoint == leaked

    payload = rag.get_status_payload()
    assert payload["mode"] == "PERSISTENT"
    assert payload["endpoint"] == ""
    assert payload["fallback_active"] is True

    # Defence-in-depth: serialize the entire payload and assert the abspath
    # appears nowhere — guards against a future field added without
    # sanitization (e.g. someone reintroducing `host`/`path` for back-compat).
    serialized = _json.dumps(payload)
    assert leaked not in serialized, (
        f"PERSISTENT abspath leaked in payload: {serialized!r}"
    )

    # Stronger pin: regex-based negative on every known leak-prone path root.
    # Catches a future regression where someone adds a different abspath
    # (e.g. `/Users/...`, `/home/...`, `/private/var/...` macOS-resolved)
    # under a new field name the substring check above wouldn't see.
    import re as _re

    leak_pattern = _re.compile(
        r'"(?:/Volumes|/Users|/home|/root|/private/var|/tmp)/[^"]+"'
    )
    match = leak_pattern.search(serialized)
    assert match is None, (
        f"Filesystem-path-shaped value leaked in payload: {match.group(0) if match else ''!r}"
    )


def test_status_payload_does_not_enumerate_project_collection_names():
    """CB-2217 regression: per-collection `name` (the `project_<cuid_prefix>`
    string) must never cross the HTTP boundary via the status payload.

    Collections are named `project_{project_id[:8]}` — echoing them on a
    surface reachable by any Origin-less local caller (validate_origin in
    `app/main.py` intentionally lets server-to-server requests through)
    enabled project enumeration after any local foothold:
      * how many projects exist (len(collections))
      * which CUID prefixes are active (collections[].name)
      * approximately how much content each project holds (count)

    The fix is payload-side redaction: keep `count` (the Service Monitor
    card uses it for "top collections by size") but drop `name`. This
    test pins both halves of the contract:
      1. Per-collection rows must contain ONLY `count` — no string field
         that could re-leak the prefix under a renamed key.
      2. Serialized payload must not contain a `project_*` substring
         anywhere — defence-in-depth against a future additive field.
    """
    import json as _json
    import re as _re

    col_a = MagicMock()
    col_a.name = "project_abc12345"
    col_a.count = MagicMock(return_value=11)
    col_b = MagicMock()
    col_b.name = "project_def67890"
    col_b.count = MagicMock(return_value=4)

    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[col_a, col_b])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    payload = rag.get_status_payload()

    # Internal handle still carries the real names — `get_collection`
    # / `describe_mode` rely on them. Only the HTTP payload is redacted.
    # (We don't call get_collection here; this is a payload contract test.)

    # Contract (1): per-row keys are exactly {"count"}.
    for row in payload["collections"]:
        assert set(row.keys()) == {"count"}, (
            f"CB-2217: collection row exposes unexpected key(s): {row!r}"
        )

    _assert_no_collection_names(payload)

    # Contract (2): no `project_<prefix>` substring anywhere in the JSON.
    # `\w{4,}` (not `[a-z0-9]{4,}`) catches future ID schemes whose first
    # 8 chars include underscores or mixed case — code-reviewer follow-up.
    serialized = _json.dumps(payload)
    project_prefix = _re.compile(r"project_\w{4,}")
    match = project_prefix.search(serialized)
    assert match is None, (
        f"CB-2217 regression: collection-name-shaped value leaked in "
        f"payload: {match.group(0) if match else ''!r} (full payload: "
        f"{serialized!r})"
    )

    # Cardinality preserved — the card still gets per-collection counts
    # for "top collections by size", just without identifying labels.
    assert len(payload["collections"]) == 2
    assert payload["total_docs"] == 15


def test_status_payload_http_heartbeat_failure(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    fake_socket = MagicMock()
    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    with patch("services.rag_service.socket.create_connection", return_value=fake_socket), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    # After init, swap heartbeat to raise so get_status_payload sees a fault.
    fake_client.heartbeat = MagicMock(side_effect=ConnectionError("dead"))

    payload = rag.get_status_payload()
    assert payload["mode"] == "HTTP"
    assert payload["healthy"] is False


def test_status_payload_list_collections_failure_does_not_raise():
    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(side_effect=RuntimeError("boom"))

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    payload = rag.get_status_payload()
    assert payload["mode"] == "PERSISTENT"
    assert payload["collections"] == []
    assert payload["total_docs"] == 0
    assert payload["healthy"] is False


def test_status_payload_per_collection_count_failure():
    bad = MagicMock()
    bad.name = "project_broken"
    bad.count = MagicMock(side_effect=RuntimeError("count failed"))
    good = MagicMock()
    good.name = "project_ok"
    good.count = MagicMock(return_value=4)

    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[bad, good])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    payload = rag.get_status_payload()
    assert payload["mode"] == "PERSISTENT"
    # CB-2217: collection rows are anonymous — only `count` is reported.
    assert payload["collections"] == [
        {"count": None},
        {"count": 4},
    ]
    _assert_no_collection_names(payload)
    # total_docs sums only successful counts.
    assert payload["total_docs"] == 4
    assert payload["healthy"] is False


def test_status_payload_count_failure_log_uses_index_not_name(caplog):
    """CB-2669 (L-2): the per-collection count() failure DEBUG log must
    reference the loop index (`#<idx>`), not the collection name. Including
    the name in the diagnostic log re-discloses the `project_<cuid_prefix>`
    enumeration that CB-2217 banned from the HTTP status payload — anyone
    who flips the logger to DEBUG (or scrapes a captured stdout pipe)
    recovers the same string. The index is sufficient for operators to
    correlate the log line with the position-aligned `collections_payload`
    row returned to the client.
    """
    import logging

    bad = MagicMock()
    bad.name = "project_broken_secret"
    bad.count = MagicMock(side_effect=RuntimeError("count failed"))

    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[bad])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    with caplog.at_level(logging.DEBUG, logger="services.rag_service"):
        rag.get_status_payload()

    failure_lines = [
        rec.getMessage()
        for rec in caplog.records
        if "count() failed for collection" in rec.getMessage()
    ]
    assert failure_lines, "expected a count() failure DEBUG log line"
    for line in failure_lines:
        assert "project_broken_secret" not in line, (
            f"CB-2669 regression: collection name leaked into DEBUG log: {line!r}"
        )
        assert "#0" in line, (
            f"CB-2669: expected loop index `#0` in log line, got: {line!r}"
        )


# ---- CB-2215 (F-9 follow-up): state-edge log gating regression tests ----
#
# A flat WARN per status poll would have produced ~120 lines/h while
# chromadb is down (the F-9 motivation). A flat downgrade to DEBUG would
# have lost the first-failure / recovery edges that matter most in an
# outage post-mortem. The intended contract is:
#   * first failure (or healthy → unhealthy transition) → WARN
#   * subsequent failures while still unhealthy → DEBUG
#   * unhealthy → healthy transition → INFO
# These tests pin the contract for both probes (heartbeat + list_collections)
# so a future refactor cannot silently revert to spam-WARN or silent-DEBUG.

def _make_http_rag(monkeypatch, fake_client):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    rag = RAGService()
    with patch("services.rag_service.socket.create_connection", return_value=MagicMock()), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()
    return rag


def _advancing_monotonic(monkeypatch, start: float = 1000.0) -> "list[float]":
    """CB-2218: helper for edge-log tests that need each get_status_payload()
    call to bypass the TTL cache and actually probe ChromaDB.

    Returns a single-element list whose value the patched
    `services.rag_service.time.monotonic` reads — tests can mutate
    `step[0] += STATUS_CACHE_TTL_S + 1.0` between calls to force a cache
    miss without poking `_status_cache` directly. Going through the
    public time-source is cleaner than reaching into private cache state
    (which would couple these tests to the cache implementation rather
    than to the documented contract).
    """
    step = [start]
    monkeypatch.setattr(
        "services.rag_service.time.monotonic", lambda: step[0]
    )
    return step


def test_heartbeat_failure_warns_only_on_transition(monkeypatch, caplog):
    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[])

    rag = _make_http_rag(monkeypatch, fake_client)
    fake_client.heartbeat = MagicMock(side_effect=ConnectionError("dead"))

    # CB-2218: each call must actually probe — the edge-log contract this
    # test pins is per-probe, not per-call. Advance the monotonic clock
    # past STATUS_CACHE_TTL_S between every call.
    step = _advancing_monotonic(monkeypatch)

    # First failure → WARN.
    with caplog.at_level("DEBUG", logger="services.rag_service"):
        rag.get_status_payload()
    warn_records = [r for r in caplog.records if r.levelname == "WARNING" and "heartbeat" in r.message]
    assert len(warn_records) == 1, "first heartbeat failure must WARN once"
    caplog.clear()

    # Steady-state failure → DEBUG, no further WARN spam.
    with caplog.at_level("DEBUG", logger="services.rag_service"):
        step[0] += rag.STATUS_CACHE_TTL_S + 1.0
        rag.get_status_payload()
        step[0] += rag.STATUS_CACHE_TTL_S + 1.0
        rag.get_status_payload()
    warn_records = [r for r in caplog.records if r.levelname == "WARNING" and "heartbeat" in r.message]
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG" and "heartbeat still failing" in r.message]
    assert warn_records == [], "subsequent failures must not re-WARN"
    assert len(debug_records) == 2, "subsequent failures must DEBUG-log once each"


def test_heartbeat_recovery_logs_info(monkeypatch, caplog):
    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(side_effect=ConnectionError("dead"))
    fake_client.list_collections = MagicMock(return_value=[])

    # Bring up HTTP via init succeeding (init heartbeat returns 1), then
    # fail heartbeat once via get_status_payload, then recover.
    fake_client.heartbeat = MagicMock(return_value=1)
    rag = _make_http_rag(monkeypatch, fake_client)

    # CB-2218: advance the monotonic clock between calls so the recovery
    # call actually re-probes (cache from the failure call would be
    # served otherwise).
    step = _advancing_monotonic(monkeypatch)

    fake_client.heartbeat = MagicMock(side_effect=ConnectionError("dead"))
    rag.get_status_payload()  # Transitions to unhealthy.
    fake_client.heartbeat = MagicMock(return_value=1)

    step[0] += rag.STATUS_CACHE_TTL_S + 1.0
    with caplog.at_level("INFO", logger="services.rag_service"):
        rag.get_status_payload()
    info_records = [r for r in caplog.records if r.levelname == "INFO" and "heartbeat recovered" in r.message]
    assert len(info_records) == 1, "recovery from unhealthy must INFO-log exactly once"


def test_list_collections_failure_warns_only_on_transition(monkeypatch, caplog):
    fake = MagicMock()
    fake.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake):
        rag._fallback_to_persistent()

    # CB-2218: advance the monotonic clock between every probe so the
    # cache never satisfies a call — we're pinning per-probe edge-log
    # behavior, not the TTL-cache contract (covered separately).
    step = _advancing_monotonic(monkeypatch)

    # Healthy first call seeds _last_list_collections_ok=True.
    rag.get_status_payload()

    fake.list_collections = MagicMock(side_effect=RuntimeError("boom"))

    step[0] += rag.STATUS_CACHE_TTL_S + 1.0
    with caplog.at_level("DEBUG", logger="services.rag_service"):
        rag.get_status_payload()
    warn_records = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "list_collections" in r.message
    ]
    assert len(warn_records) == 1, "first list_collections failure must WARN once"
    caplog.clear()

    step[0] += rag.STATUS_CACHE_TTL_S + 1.0
    with caplog.at_level("DEBUG", logger="services.rag_service"):
        rag.get_status_payload()
    warn_records = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "list_collections" in r.message
    ]
    debug_records = [
        r for r in caplog.records
        if r.levelname == "DEBUG" and "list_collections still failing" in r.message
    ]
    assert warn_records == []
    assert len(debug_records) == 1


def test_reset_state_clears_health_edge_tracking():
    """A reconnect must treat the new client as a fresh subject — first
    failure of the new client must WARN regardless of the previous client's
    last-known health."""
    fake = MagicMock()
    fake.list_collections = MagicMock(return_value=[])
    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake):
        rag._fallback_to_persistent()

    # Force into known-failed state.
    fake.list_collections = MagicMock(side_effect=RuntimeError("boom"))
    rag.get_status_payload()
    assert rag._last_list_collections_ok is False

    # Reset (e.g., reconnect) — health-edge tracking must clear.
    rag._reset_state()
    assert rag._last_heartbeat_ok is None
    assert rag._last_list_collections_ok is None


# ---- CB-2218: TTL-cache + single-flight regression tests ----
#
# get_status_payload() is polled at 30 s by the always-mounted Service
# Monitor card. With M open tabs and N collections each uncached call
# fans out to M·(N+2) ChromaDB round-trips per window (heartbeat +
# list_collections + count() per collection). The TTL cache + threading
# lock collapse this to (N+2) per TTL regardless of tab count. These
# tests pin the contract:
#   * cache hit within TTL → no ChromaDB calls
#   * cache miss after TTL → one fresh ChromaDB pass
#   * _reset_state clears cache so reconnect surfaces fresh data
#   * concurrent callers single-flight onto one ChromaDB pass

def _http_rag_with_counters(monkeypatch):
    """Build a HTTP-mode RAGService backed by a MagicMock client with
    per-method call counters reset after init. Used by cache tests so we
    can count probes attributable to get_status_payload() alone, not the
    one heartbeat call _init_client_blocking() makes during construction.
    """
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    col_a = MagicMock()
    col_a.name = "project_aaaaaa"
    col_a.count = MagicMock(return_value=5)
    col_b = MagicMock()
    col_b.name = "project_bbbbbb"
    col_b.count = MagicMock(return_value=12)

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[col_a, col_b])

    rag = RAGService()
    with patch("services.rag_service.socket.create_connection", return_value=MagicMock()), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    # Reset counters so cache-hit assertions count only probes triggered
    # by the test's get_status_payload() calls, not the init-time
    # heartbeat that _init_client_blocking() performs.
    fake_client.heartbeat.reset_mock()
    fake_client.list_collections.reset_mock()
    col_a.count.reset_mock()
    col_b.count.reset_mock()

    return rag, fake_client, [col_a, col_b]


def test_status_payload_cached_within_ttl(monkeypatch):
    """CB-2218: calls inside the TTL window share one ChromaDB pass.

    A real Service Monitor session has M tabs polling every 30 s; in
    practice many of those polls land within the same ~10 s window due
    to render-jitter and visibility-resume bursts. The TTL cache must
    serve all of them from a single probe so ChromaDB doesn't see M·(N+2)
    redundant round-trips for what is observably the same answer.
    """
    rag, fake_client, cols = _http_rag_with_counters(monkeypatch)

    # Pin time to a fixed monotonic value so cache freshness is
    # deterministic regardless of test-runner wall-clock jitter.
    fixed_now = 1000.0
    monkeypatch.setattr(
        "services.rag_service.time.monotonic", lambda: fixed_now
    )

    first = rag.get_status_payload()
    second = rag.get_status_payload()
    third = rag.get_status_payload()

    # Each call returns the cached payload — same value across all three.
    assert first == second == third
    assert first["mode"] == "HTTP"
    assert first["total_docs"] == 17

    # Compute path ran exactly once across the three calls. Heartbeat,
    # list_collections, and per-collection count() are all attributed to
    # the cache miss on the first call; the next two calls bypassed the
    # probe entirely.
    assert fake_client.heartbeat.call_count == 1
    assert fake_client.list_collections.call_count == 1
    for c in cols:
        assert c.count.call_count == 1


def test_status_payload_recomputed_after_ttl(monkeypatch):
    """CB-2218: after the TTL elapses, the next call recomputes.

    A 10 s TTL ≪ 30 s poll cadence is the design point — every fresh
    poll cycle still gets fresh data, the cache only collapses bursts
    inside one cycle. This test pins the freshness side of the contract
    so a future TTL bump (or accidental "cache forever" regression)
    can't silently turn the status surface stale.
    """
    rag, fake_client, cols = _http_rag_with_counters(monkeypatch)

    now = [1000.0]
    monkeypatch.setattr(
        "services.rag_service.time.monotonic", lambda: now[0]
    )

    rag.get_status_payload()
    assert fake_client.heartbeat.call_count == 1

    # Advance past the TTL window. STATUS_CACHE_TTL_S is 10 s; +11 s
    # guarantees the cached entry is evicted regardless of any future
    # boundary-condition tightening.
    now[0] += rag.STATUS_CACHE_TTL_S + 1.0

    rag.get_status_payload()
    assert fake_client.heartbeat.call_count == 2, (
        "post-TTL call must recompute — got cached payload instead"
    )
    assert fake_client.list_collections.call_count == 2
    for c in cols:
        assert c.count.call_count == 2


def test_status_payload_boundary_at_exact_ttl(monkeypatch):
    """CB-2218: the TTL boundary uses strict-less-than, so exactly +TTL
    is treated as expired (recompute), and any value < TTL is fresh.

    Pins the boundary so a future refactor that flips < to <= (or vice
    versa) is caught — the difference matters under high poll-rate
    sessions where a slow probe + steady cadence can land calls on the
    boundary often enough to either leak one extra probe per window
    or starve the recompute by a tick.
    """
    rag, fake_client, _ = _http_rag_with_counters(monkeypatch)

    now = [1000.0]
    monkeypatch.setattr(
        "services.rag_service.time.monotonic", lambda: now[0]
    )

    rag.get_status_payload()  # populates cache @ now=1000.0
    assert fake_client.heartbeat.call_count == 1

    # Advance to just under TTL — still cached.
    now[0] = 1000.0 + rag.STATUS_CACHE_TTL_S - 0.001
    rag.get_status_payload()
    assert fake_client.heartbeat.call_count == 1, "just-under-TTL must be cached"

    # Advance to exactly TTL — strict-less-than means this is expired.
    now[0] = 1000.0 + rag.STATUS_CACHE_TTL_S
    rag.get_status_payload()
    assert fake_client.heartbeat.call_count == 2, "exact-TTL must recompute"


def test_reset_state_clears_status_cache(monkeypatch):
    """CB-2218: reconnect (HTTP→PERSISTENT or future runtime reattach)
    must NOT serve a stale prior-mode payload during the post-reset TTL
    window — that would mask the very mode-transition the status surface
    exists to expose, and let `fallback_active=False` linger on a client
    that has already fallen back. `_reset_state()` clears the cache so
    the next get_status_payload() probes the new client.
    """
    rag, fake_client, _ = _http_rag_with_counters(monkeypatch)

    fixed_now = 1000.0
    monkeypatch.setattr(
        "services.rag_service.time.monotonic", lambda: fixed_now
    )

    rag.get_status_payload()
    assert rag._status_cache is not None
    assert fake_client.heartbeat.call_count == 1

    # Simulate reconnect: reset wipes cache + state. (We don't bring the
    # service back online here — the assertion is that reset clears the
    # cache, not that the next probe succeeds. UNINITIALIZED is fine.)
    rag._reset_state()
    assert rag._status_cache is None
    assert rag._status_cache_at == 0.0

    # Next call hits the compute path on the now-uninitialized service —
    # returns the UNINITIALIZED snapshot rather than the stale HTTP one.
    payload = rag.get_status_payload()
    assert payload["mode"] == "UNINITIALIZED"
    assert payload["healthy"] is False


def test_status_payload_cache_singleflight(monkeypatch):
    """CB-2218: concurrent callers must serialize on the cache lock so
    only ONE thread incurs the ChromaDB pass on a cache miss; the rest
    return the cached value the winner just computed.

    This is the M-tab amplifier mitigation in its strongest form: even
    if M tabs all wake up at exactly the same monotonic instant (TTL
    just expired, visibility-resume burst, etc.), the lock collapses
    the M-fold fan-out into one probe + (M-1) cache reads.
    """
    import threading as _threading

    rag, fake_client, cols = _http_rag_with_counters(monkeypatch)

    # Slow the heartbeat just enough that all threads pile up on the
    # cache lock before the winner finishes — without this, the winner
    # might complete and store the cache before the others enter
    # get_status_payload(), and we'd be testing TTL-hit, not single-
    # flight. 50 ms is plenty for the spawn + acquire path on every
    # platform CI would run on.
    import time as _time
    original_heartbeat = fake_client.heartbeat

    def _slow_heartbeat(*a, **kw):
        _time.sleep(0.05)
        return original_heartbeat(*a, **kw)

    fake_client.heartbeat = MagicMock(side_effect=_slow_heartbeat)

    barrier = _threading.Barrier(parties=8)
    results: list = [None] * 8

    def _worker(idx: int) -> None:
        # Sync all workers so they all attempt the cache acquire at
        # essentially the same monotonic instant.
        barrier.wait()
        results[idx] = rag.get_status_payload()

    threads = [_threading.Thread(target=_worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every worker received the same payload — the winner's compute, not
    # eight independent ones. (Equality, not identity: dict literals are
    # the same object across calls because the cache stores the dict ref,
    # but assert on value to keep the test resilient to a future shallow
    # copy on read.)
    assert all(r is not None for r in results)
    expected = results[0]
    for r in results[1:]:
        assert r == expected

    # Single-flight contract: the winner ran exactly one heartbeat /
    # list_collections / count pass for all 8 workers. Without the lock
    # this would be 8.
    assert fake_client.heartbeat.call_count == 1
    assert fake_client.list_collections.call_count == 1
    for c in cols:
        assert c.count.call_count == 1
