"""CB-2212: mark COMPLETED_WAITING_QA + file security-auditor MEDIUM follow-up.

Bible Rule 22: code completes -> COMPLETED_WAITING_QA, never DONE.
Bible Rule 28/29: per-project per-session script path; never `/tmp/`.

Security audit (a3f1aa62cd7a5fbbb) flagged a latent MEDIUM:
RAGService is a process-level singleton with async callers. _reset_state()
+ subsequent client construction is not lock-guarded. Today only the lifespan
calls these paths (single-threaded), and the property-fallback path on line
65-71 of rag_service.py is a "should never happen" reentrant trigger. But
once any future code (e.g. an admin reconnect endpoint) reconnects mid-
request, two concurrent callers can race to construct duplicate
PersistentClients on the same SQLite-backed path -> potential corruption.

Fix proposal in the follow-up ticket: wrap reset+construct in a
threading.Lock (these init paths are sync, called via asyncio.to_thread).
"""

import json
import urllib.error
import urllib.request

API_BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
CB_2212_ID = "0f1eb883-7ce4-4c4e-b302-52cc66498c1c"
CB_2047_PARENT_ID = None  # resolve at runtime so we don't hardcode wrong


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read().decode()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} on {method} {path}: {exc.read().decode()[:300]}")
        raise


def find_parent_story_id() -> str | None:
    """CB-2047 is the parent story of CB-2212. Find its UUID for the follow-up."""
    page = 1
    while True:
        data = call("GET", f"/projects/{PROJECT_ID}/issues?pageSize=500&page={page}")
        for item in data.get("items", []):
            if item.get("key") == "CB-2047":
                return item["id"]
        if page >= data.get("totalPages", 1):
            return None
        page += 1


def mark_cb2212_cwq() -> None:
    print("== CB-2212: PATCH status -> COMPLETED_WAITING_QA")
    resp = call(
        "PATCH",
        f"/issues/{CB_2212_ID}",
        {
            "status": "COMPLETED_WAITING_QA",
            "implementationSummary": (
                "Extracted private `_reset_state()` helper in "
                "`backend/services/rag_service.py` that zeros `_client`, "
                "`_mode`, `_mode_detail`, `_collections`. Both "
                "`_init_client_blocking` and `_fallback_to_persistent` now "
                "call it instead of inlining the resets — fixes the "
                "asymmetry that left `_collections` cached from a dead "
                "client on the HTTP path. Added "
                "`backend/tests/test_rag_service_reset_state.py` with 4 "
                "unit tests pinning the symmetry invariant + the "
                "init-failure path. 14/14 rag_service tests pass, "
                "23/23 wider rag-touching tests pass. code-reviewer + "
                "security-auditor both cleared with no CRITICAL/HIGH; "
                "security-auditor flagged one latent MEDIUM (singleton "
                "race on future runtime reconnect) — filed as follow-up."
            ),
        },
    )
    print(f"   -> {resp.get('status')}")


def file_followup_lock_ticket(parent_id: str | None) -> None:
    print("== CB-2212 follow-up: file MEDIUM lock-guard ticket")
    body = {
        "title": (
            "[CB-2212 follow-up] MEDIUM: lock-guard RAGService _reset_state + "
            "client construct (singleton race on future runtime reconnect)"
        ),
        "description": (
            "**Source**: security-auditor pass on CB-2212.\n"
            "**Severity**: MEDIUM (latent — no current trigger; future "
            "admin reconnect endpoint will expose).\n\n"
            "## Problem\n"
            "`RAGService` is a process-level singleton consumed by async "
            "FastAPI handlers. The new `_reset_state()` helper plus the "
            "subsequent client construction in `_init_client_blocking` / "
            "`_fallback_to_persistent` are NOT guarded by a lock.\n\n"
            "Today these paths run only at lifespan startup (single-"
            "threaded) and the property-fallback at "
            "`backend/services/rag_service.py:65-71` is a 'should never "
            "happen' degraded path. So practical risk is bounded.\n\n"
            "But once any future code (e.g. an admin reconnect endpoint, "
            "the same caller CB-2212 was written to defend against) calls "
            "`_init_client_blocking` while another async caller is in the "
            "property fallback, both can race to construct duplicate "
            "`PersistentClient` instances on the same SQLite-backed path "
            "-> potential lock contention or corruption.\n\n"
            "## Fix proposal\n"
            "Wrap the reset+construct sequence in a `threading.Lock` "
            "(these are sync paths called via `asyncio.to_thread()` from "
            "the lifespan, so a thread-lock is the right primitive). "
            "Acquire at the top of `_init_client_blocking` and "
            "`_fallback_to_persistent`, release after the new client is "
            "fully assigned. The property-fallback at line 65-71 should "
            "also acquire the same lock before checking `_client is None` "
            "to close the TOCTOU window.\n\n"
            "## Bonus (LOW from same audit)\n"
            "Consider `self._collections.clear()` instead of "
            "`self._collections = {}` so any concurrent caller holding a "
            "local reference to the dict (e.g. mid-iteration in "
            "`get_status_payload`) sees a uniformly cleared view rather "
            "than reading stale handles bound to a dead client.\n\n"
            "## Acceptance\n"
            "- All three paths share a single `threading.Lock`.\n"
            "- Test reproduces the race today (two threads racing into "
            "`_init_client_blocking` create only one client).\n"
            "- No regression in startup latency (lock is uncontended at "
            "boot)."
        ),
        "type": "BUG",
        "priority": "MEDIUM",
        "labels": "rag-service-hardening,cb-2212-followup",
        "reporter": "AI",
    }
    if parent_id:
        body["parentId"] = parent_id
    resp = call("POST", f"/projects/{PROJECT_ID}/issues", body)
    print(f"   -> created {resp.get('key')} ({resp.get('id')})")


if __name__ == "__main__":
    parent = find_parent_story_id()
    print(f"Parent CB-2047 id: {parent}")
    mark_cb2212_cwq()
    file_followup_lock_ticket(parent)
    print("Done.")
