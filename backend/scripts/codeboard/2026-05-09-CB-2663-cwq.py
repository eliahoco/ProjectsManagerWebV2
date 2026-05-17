"""CB-2663 → COMPLETED_WAITING_QA + implementation summary (Rule 29)."""
import json
import urllib.request

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
ISSUE_KEY = "CB-2663"

IMPLEMENTATION_SUMMARY = """\
**Status**: COMPLETED_WAITING_QA — code review + security audit clean.

## Changes

### `backend/services/rag_service.py`
- Added `self._init_lock = threading.Lock()` (non-reentrant) on `RAGService.__init__`. Documented choice rationale: works across `asyncio.to_thread()` boundary used by lifespan; never asyncio.Lock (won't bind across threadpool).
- `_init_client_blocking()` body now wrapped in `with self._init_lock:` — reset+probe+construct sequence is atomic against any future runtime-reconnect path.
- Extracted `_construct_persistent_client_locked()` helper (caller MUST hold `_init_lock`). Lets the property-fallback in `client` reuse the construction body without re-acquiring the lock (which would deadlock — Lock is non-reentrant).
- `_fallback_to_persistent()` now acquires `_init_lock` and delegates to the helper.
- `client` property uses **double-checked locking**: outer unlocked `if _client is None` keeps the steady-state hot path lock-free; inner re-check after `with self._init_lock:` closes the TOCTOU window where two threads could each construct a duplicate `PersistentClient` on the same SQLite-backed path (the latent race CB-2663 was filed for).
- `_reset_state()` now uses `_collections.clear()` instead of rebinding to `{}` (LOW bonus from same audit) — concurrent readers holding a captured dict reference observe a uniformly-emptied view rather than an orphaned dict still bound to the dead client.
- Added lock-ordering convention comment: `_init_lock` outer, `_status_cache_lock` inner. No path holds both today; pinned to prevent future reconnect surface from inverting and deadlocking against `get_status_payload()`.

### `backend/tests/test_rag_service_init_lock.py` (NEW, 6 tests, all passing)
1. `test_init_lock_is_threading_lock` — pins behavioural contract (sync acquire, non-reentrant). Rejects `asyncio.Lock` (its acquire is a coroutine).
2. `test_construct_persistent_client_locked_runs_under_caller_lock` — pins helper-extraction contract (helper does not re-acquire).
3. `test_two_threads_racing_into_init_client_blocking_serialize_cleanly` — two-thread race + observer thread + **mutex-assertion stub** (per code-review MEDIUM-1) that fires if any two threads enter the critical section concurrently. Would fail if `with self._init_lock:` were removed.
4. `test_property_fallback_double_check_skips_duplicate_construction` — TOCTOU close: two threads racing the property fallback produce exactly ONE `PersistentClient`, both see the same client instance.
5. `test_init_lock_uncontended_at_boot` — 50ms latency budget catches regression to a slow primitive (multiprocessing/network/cross-process semaphore).
6. `test_reset_state_uses_dict_clear_not_rebind` — pins `.clear()` semantics for the LOW bonus.

### `backend/scripts/codeboard/2026-05-09-CB-2663-{in-progress,cwq}.py`
- Per-project per-session helper scripts for status transitions (Rule 29).

## Test results
- 42/42 RAG-service-related tests pass (init_lock new + reset_state + half_init_invariant + describe_mode + status_payload + persistent_fallback_path + system_rag_status).

## Audit results (both run on the diff)
- **code-reviewer**: APPROVE. No CRITICAL/HIGH. Suggested MEDIUM-1 (mutex-assertion stub for the race test), LOW-3 (reject asyncio.Lock + assert non-reentrant in lock-identity test), LOW-2 (lock-ordering doc), LOW-4 (tighten 100ms→50ms budget) — **all applied**.
- **security-auditor**: SHIPS SAFELY. No CRITICAL/HIGH. New WARN log line is constant-string (no info disclosure). Hot path through `client` property unchanged for steady-state (lock taken only on cold-start fallback). LOW/MEDIUM findings are forward-looking concerns for the still-unwritten runtime-reconnect endpoint that motivated CB-2663 in the first place — not blockers for this fix; should fold into the design review for whichever ticket builds that endpoint:
  - MEDIUM-1: future reconnect endpoint must include auth check + circuit breaker (mirrors AutoPilot's `_AUTO_RESUME_MAX_ATTEMPTS`) + failure capture.
  - LOW-1: `_compute_status_payload` reads `self._client` raw — under a runtime-reconnect surface, snapshot the `(client, mode, endpoint)` triple under `_init_lock`.
  - LOW-3: `_status_cache` invalidation in `_reset_state` should acquire `_status_cache_lock` once concurrent readers exist (today the lifespan startup serialises this; the comment at lines 196-205 documents the assumption).

## Acceptance criteria (from ticket)
- ✅ All three paths share a single `threading.Lock` (`self._init_lock`).
- ✅ Test reproduces the race today — `test_two_threads_racing_into_init_client_blocking_serialize_cleanly` includes a mutex-assertion stub that fires if concurrent entry to the critical section happens (the regression catcher); the property-fallback test verifies exactly one `PersistentClient` is constructed under contention.
- ✅ No regression in startup latency — `test_init_lock_uncontended_at_boot` pins 50 ms upper bound (uncontended `threading.Lock` acquire is microseconds).
"""


def get_id_by_key(key: str) -> str:
    with urllib.request.urlopen(
        f"{API}/projects/{PROJECT_ID}/issues?pageSize=1000", timeout=15
    ) as r:
        items = json.loads(r.read().decode("utf-8"))["items"]
    for it in items:
        if it.get("key") == key:
            return it["id"]
    raise SystemExit(f"{key} not found in first page")


def patch(issue_id: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}/issues/{issue_id}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    iid = get_id_by_key(ISSUE_KEY)
    print(f"{ISSUE_KEY} → {iid}")
    result = patch(iid, {
        "status": "COMPLETED_WAITING_QA",
        "implementationSummary": IMPLEMENTATION_SUMMARY,
    })
    print(f"status={result.get('status')}")
    print(f"implementationSummary length={len(result.get('implementationSummary') or '')}")


if __name__ == "__main__":
    main()
