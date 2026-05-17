#!/usr/bin/env python3
"""CB-2218 close-out: mark CWQ + file M-2 follow-up + comment on CB-2663.

CB-2218 is the TTL-cached single-flight wrapper around `get_status_payload()`.
Code shipped in commit 68bce26; tests pass (28/28). Code-reviewer +
security-auditor flagged two MEDIUM items:
  M-1: TOCTOU on _reset_state via runtime client property fallback —
       already covered by CB-2663 (existing follow-up). Add a comment
       on CB-2663 noting the new cache fields that must also be
       lock-guarded when CB-2663 is implemented.
  M-2: Lock-held-during-slow-probe event-loop pin — new DoS shape
       introduced by the single-flight lock. File as new MEDIUM
       follow-up under CB-2049 sibling group.

Then mark CB-2218 -> COMPLETED_WAITING_QA with the audit summary.
"""

import json
import urllib.request
import urllib.error

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
PARENT_STORY_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"  # CB-2047 (S1.3)
CB_2218_ID = "26adb60d-6ea2-4f52-903e-3c29ea0ec901"
CB_2663_KEY = "CB-2663"


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(
        f"{API}{path}", data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {body_text}") from exc


def find_by_key(key: str) -> dict | None:
    payload = req("GET", f"/projects/{PROJECT_ID}/issues?pageSize=1000&search={key}")
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    for issue in items:
        if issue.get("key") == key:
            return issue
    return None


def main() -> None:
    # Step 1: file M-2 follow-up.
    m2_body = {
        "title": (
            "[CB-2218 audit follow-up] MEDIUM: status-cache lock held during slow "
            "ChromaDB probe pins FastAPI event loop"
        ),
        "type": "BUG",
        "priority": "MEDIUM",
        "reporter": "AI",
        "assignee": "python-pro",
        "parentId": PARENT_STORY_ID,
        "labels": "documentation-surface,rag-status,follow-up,dos",
        "description": (
            "**Source**: security-auditor pass on CB-2218 (TTL-cached single-flight "
            "wrapper for `/api/system/rag/status`).\n"
            "**Severity**: MEDIUM (different DoS shape than CB-2218 fixed; latent — "
            "requires a stuck/half-closed ChromaDB connection to trigger).\n\n"
            "## Problem\n"
            "`RAGService.get_status_payload()` (rag_service.py:258-272) holds "
            "`_status_cache_lock` for the full duration of "
            "`_compute_status_payload()` to enforce single-flight on cache miss. "
            "The probe issues `client.heartbeat()` + `client.list_collections()` + "
            "`col.count()` per collection against the chromadb HTTP client, "
            "which has **no per-call timeout configured**.\n\n"
            "If ChromaDB hangs (stuck server, half-closed TCP socket in CLOSE_WAIT, "
            "slow-loris), every concurrent status request queues on the lock. The "
            "FastAPI handler at `api/system.py:106-114` calls `get_status_payload()` "
            "synchronously inside the async endpoint — no `asyncio.to_thread` — so a "
            "stuck ChromaDB pins the event-loop worker thread and blocks every other "
            "request handled by that worker.\n\n"
            "**Net result**: CB-2218 collapsed the M·(N+2) RT amplifier to (N+2) per "
            "10s, but introduced a new DoS shape where one stuck dependency stalls "
            "the entire status-endpoint queue plus any other async handlers sharing "
            "the worker.\n\n"
            "## Fix proposal\n"
            "1. Configure a request timeout on the chromadb HttpClient at construction "
            "(`_init_client_blocking()` in rag_service.py:153-188). 2 s is a safe "
            "ceiling — heartbeat / list_collections / count() should all return well "
            "below that against a healthy server.\n"
            "2. Wrap `rag.get_status_payload()` in `asyncio.to_thread(...)` at the "
            "API layer (`api/system.py:106-114`) so the synchronous probe runs off "
            "the event loop.\n"
            "3. Use `_status_cache_lock.acquire(timeout=0.5)` with a short bound; on "
            "contention, return the prior cached payload with `healthy=False` rather "
            "than queue indefinitely. (Optional belt-and-braces; (1)+(2) already "
            "remove the worst case.)\n\n"
            "## Files\n"
            "- `backend/services/rag_service.py:153-188` (HttpClient construct)\n"
            "- `backend/services/rag_service.py:258-272` (lock-held compute)\n"
            "- `backend/api/system.py:106-114` (sync call inside async handler)\n\n"
            "## Acceptance\n"
            "- `httpx.ReadTimeout` (or chromadb-equivalent) cannot block the status "
            "endpoint for more than ~2 s.\n"
            "- A simulated stuck-chromadb test (mock `client.heartbeat` to "
            "`time.sleep(60)`) returns within 5 s with `healthy=False`.\n"
            "- Concurrent unrelated FastAPI requests handled by the same worker do "
            "NOT stall while the status endpoint is hung."
        ),
    }
    created = req("POST", f"/projects/{PROJECT_ID}/issues", m2_body)
    new_key = created.get("key") or created.get("issue", {}).get("key")
    new_id = created.get("id") or created.get("issue", {}).get("id")
    print(f"[OK] filed follow-up: {new_key} (id={new_id})")

    # Step 2: comment on CB-2663 noting the new cache fields.
    cb_2663 = find_by_key(CB_2663_KEY)
    if cb_2663:
        cb_2663_id = cb_2663["id"]
        comment_body = {
            "content": (
                "**CB-2218 audit cross-link.** The CB-2218 TTL-cached single-flight "
                "wrapper added three new instance fields that must ALSO be lock-guarded "
                "when CB-2663 is implemented:\n\n"
                "- `_status_cache: Optional[Dict[str, Any]]`\n"
                "- `_status_cache_at: float`\n"
                "- `_status_cache_lock: threading.Lock`\n\n"
                "`_reset_state()` already zeroes the cache fields (rag_service.py:150-151) "
                "but does so WITHOUT acquiring `_status_cache_lock`. Today this is safe "
                "because `_reset_state()` is only invoked at lifespan startup before any "
                "concurrent reader. CB-2663's fix (lock-guard the reset+construct sequence) "
                "must therefore also lock-guard the cache field reset, OR — equivalent — "
                "use a single guard lock that covers both the client+collections reset and "
                "the cache reset, so both are atomic against an in-flight "
                "`_compute_status_payload()` reader.\n\n"
                "Audit reference: code-reviewer M-1 + security-auditor M-1 on CB-2218 "
                "(both pointed at the same TOCTOU)."
            ),
            "author": "AI",
        }
        try:
            req("POST", f"/issues/{cb_2663_id}/comments", comment_body)
            print(f"[OK] commented on {CB_2663_KEY}")
        except RuntimeError as exc:
            print(f"[WARN] comment on {CB_2663_KEY} failed: {exc}")
    else:
        print(f"[WARN] {CB_2663_KEY} not found; skipping cross-link comment")

    # Step 3: comment on CB-2218 with audit summary.
    cwq_comment = {
        "content": (
            "## CB-2218 close-out — Jonny VP-R&D pre/post checklist complete\n\n"
            "**Implementation** (commit 68bce26, already in HEAD):\n"
            "- New class constant `RAGService.STATUS_CACHE_TTL_S = 10.0`\n"
            "- New state: `_status_cache`, `_status_cache_at`, `_status_cache_lock` (`threading.Lock`)\n"
            "- `get_status_payload()` is now a TTL-gated single-flight wrapper; actual probe moved to `_compute_status_payload()`\n"
            "- `_reset_state()` clears the cache so HTTP→PERSISTENT fallback never serves stale prior-mode payload\n"
            "- `time.monotonic()` for the TTL clock (NTP/DST-immune)\n\n"
            "**Test coverage** — `backend/tests/test_rag_service_status_payload.py`, all 28 tests pass:\n"
            "- `test_status_payload_cached_within_ttl` — concurrent calls share one ChromaDB pass\n"
            "- `test_status_payload_recomputed_after_ttl` — re-probes after TTL elapses\n"
            "- `test_status_payload_boundary_at_exact_ttl` — strict-`<` boundary\n"
            "- `test_reset_state_clears_status_cache` — reconnect drops stale mode\n"
            "- `test_status_payload_cache_singleflight` — 8-thread single-flight regression\n"
            "- Plus state-edge log gating preserved across cached vs uncached calls\n\n"
            "**Net effect**: M·(N+2) ChromaDB round-trips per 30 s (M tabs, N=8 collections) "
            "collapse to (N+2) per 10 s regardless of tab count.\n\n"
            "**Audit gate — code-reviewer**: PASS with one MEDIUM (M-1: `_reset_state()` "
            "lock-discipline), one LOW (defensive-copy on cache return). M-1 is the same "
            "race already filed under CB-2663; cross-link comment added there.\n\n"
            "**Audit gate — security-auditor**: no CRITICAL / no HIGH. Two MEDIUMs:\n"
            f"- M-1: TOCTOU on `_reset_state()` via `client` property runtime fallback — "
            f"DUPLICATE of code-reviewer M-1, covered by CB-2663.\n"
            f"- M-2: Lock-held-during-slow-probe event-loop pin — new DoS shape, filed "
            f"as **{new_key}** (audit follow-up, MEDIUM, sibling under CB-2047).\n\n"
            "Info-leak surface (CB-2216 abspath redaction + CB-2217 collection-name "
            "redaction): preserved — cache stores the post-redaction shape only.\n\n"
            "Status → COMPLETED_WAITING_QA. Eli's manual QA promotes to DONE."
        ),
        "author": "AI",
    }
    try:
        req("POST", f"/issues/{CB_2218_ID}/comments", cwq_comment)
        print("[OK] commented on CB-2218 with audit summary")
    except RuntimeError as exc:
        print(f"[WARN] CB-2218 comment failed: {exc}")

    # Step 4: CB-2218 -> COMPLETED_WAITING_QA.
    transition = req(
        "PATCH",
        f"/issues/{CB_2218_ID}",
        {"status": "COMPLETED_WAITING_QA"},
    )
    final_status = (
        transition.get("status")
        or transition.get("issue", {}).get("status")
        or "?"
    )
    print(f"[OK] CB-2218 -> {final_status}")


if __name__ == "__main__":
    main()
