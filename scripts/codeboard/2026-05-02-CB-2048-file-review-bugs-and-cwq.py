"""
CB-2048 (T1.3.1) deliverable wrap-up:

1. File CRITICAL/MEDIUM findings from the code-reviewer pass on the E1 diff
   as new CodeBoard BUG tickets, parented under STORY CB-2047 (S1.3 audit
   + regression). LOW/NIT findings are consolidated into one polish
   ticket.

2. Update CB-2048 description with the inline findings summary.

3. Mark CB-2048 -> COMPLETED_WAITING_QA so Eli's manual QA can promote it
   to DONE per Bible Rule 22.

Per Bible Rule 29: per-project per-session script path. Per Bible Rule
22: never push to DONE from code.
"""

import json
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"

CB_2047_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"
CB_2048_ID = "4ca6f8e4-c313-4e96-bc3a-65c9a39e23cb"

LABEL = "e1-audit-cb-2048"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def patch(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------- 1. File findings as BUGs ----------

bugs = [
    {
        "title": "[CB-2048 F-1] CRITICAL: /api/system/rag/status has no Next.js proxy → card stuck at 'RAG offline'",
        "type": "BUG",
        "priority": "CRITICAL",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "react-specialist",
        "reporter": "AI",
        "description": """**Severity:** CRITICAL (defeats E1's user-visible deliverable)

**Location:** `frontend/components/service-monitor.tsx:208`

**Problem**

`RagStatusCard` calls `fetch('/api/system/rag/status')` with a relative URL. The frontend runs on Next.js at `:3601` and the FastAPI status endpoint lives at `:8401`. Every other `fetch('/api/...')` call in service-monitor.tsx has a corresponding Next.js route handler at `frontend/app/api/<path>/route.ts` that proxies to backend (`/api/projects/status`, `/api/docker/status`, `/api/watchdog/events`).

There is **no** `frontend/app/api/system/` directory and **no** rewrite in `frontend/next.config.ts` that forwards unknown `/api/*` paths to FastAPI. Verified:
- `find frontend/app/api -type d` → no `system/`
- `frontend/next.config.ts` → no `rewrites()`

Consequences:
- Browser fetch returns 404 every poll
- `failCountRef` reaches threshold after the second poll
- Badge permanently red: "RAG offline — status endpoint unreachable"
- The very surface E1 was supposed to add is silently broken

**Fix (pick one)**

Option A (recommended, mirrors existing pattern): add `frontend/app/api/system/rag/status/route.ts` that proxies to `http://localhost:8401/api/system/rag/status`, mirroring the shape of `frontend/app/api/projects/status/route.ts`.

Option B: change the fetch to the absolute backend origin (`http://localhost:8401/...`). CSP `connect-src` already permits `http://localhost:*`. Less consistent with rest of file.

**Required regression test**

Smoke test must hit through the Next.js layer (browser/3601), not just FastAPI (curl/8401). The original E1 backend tests pass while the user-facing card stays broken.

**Found in:** code-reviewer pass on CB-2048.
""",
    },
    {
        "title": "[CB-2048 F-2] MEDIUM: _init_client_blocking reset omits _collections (asymmetry vs _fallback_to_persistent)",
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "python-pro",
        "reporter": "AI",
        "description": """**Severity:** MEDIUM (latent — no current caller exposes it; future admin reconnect endpoint will)

**Location:** `backend/services/rag_service.py:79-84` vs `:114-120`

**Problem**

The new "reset before init" comment claims the up-front reset prevents the half-initialised state that motivated CB-2043. But:
- `_fallback_to_persistent` resets four fields: `_client`, `_mode`, `_mode_detail`, `_collections`
- `_init_client_blocking` resets only three (omits `_collections`)

Today the lifespan only constructs `RAGService()` once and only ever falls back, so practical impact is zero. But once anyone adds a "reconnect to chroma" admin endpoint that calls `_init_client_blocking` on a service that was running in PERSISTENT mode, `get_collection()` will return cached objects bound to the dead PersistentClient — exactly the half-initialised state the new comment promises to prevent.

**Fix**

Add `self._collections = {}` to the reset block in `_init_client_blocking` so both init paths are symmetric. Consider extracting a private `_reset_state()` helper to keep them identical going forward.

**Found in:** code-reviewer pass on CB-2048.
""",
    },
    {
        "title": "[CB-2048 F-3] MEDIUM: missing tests for half-init invariant (HTTP/PERSISTENT raise mid-init)",
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "python-pro",
        "reporter": "AI",
        "description": """**Severity:** MEDIUM (test-gap regression risk)

**Location:** `backend/tests/test_rag_service_describe_mode.py`, `backend/tests/test_rag_service_status_payload.py`

**Problem**

The new comments at `rag_service.py:79-84` and `:114-120` advertise an invariant: `_mode` cannot be `HTTP` while `_client` is `None`. No test exercises a constructor raise mid-init.

Specifically uncovered:
1. `_init_client_blocking()` raising on heartbeat after a prior successful PERSISTENT init — does `_mode` correctly drop to None?
2. `_fallback_to_persistent()` raising on `PersistentClient(...)` construction after a prior successful HTTP init — same question

A regression that re-introduces the original bug (HTTP advertised, client gone) will slip through.

**Fix**

Add two parametrised tests (one for HTTP, one for PERSISTENT) that:
1. Run the service into a healthy state in mode A
2. Patch `chromadb.HttpClient` (or `PersistentClient`) to raise
3. Call the alternate init method
4. Assert `service._mode is None and service._client is None and service.describe_mode() == "RAG mode=UNINITIALIZED"`

**Found in:** code-reviewer pass on CB-2048.
""",
    },
    {
        "title": "[CB-2048 F-4] MEDIUM: get_status_payload docstring lies about total_docs on partial failure",
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "python-pro",
        "reporter": "AI",
        "description": """**Severity:** MEDIUM (docstring/implementation drift, will mislead future readers)

**Location:** `backend/services/rag_service.py:170` (docstring) vs `backend/tests/test_rag_service_status_payload.py:155` (test asserting actual behavior)

**Problem**

Docstring: `total_docs: int (sum of per-collection counts; 0 on partial failure)`

Actual behavior: `test_status_payload_per_collection_count_failure` asserts `total_docs == 4` (sum of *successful* counts) when one of two collections raises in `count()`. The implementation accumulates only successful counts.

The implementation is correct (partial visibility > zero). The docstring is wrong and will cause a future reader to "fix" the code in the wrong direction.

**Fix**

Update docstring:
```
- total_docs: int (sum of successful per-collection counts; partial
  failure does not zero it; healthy=False signals partial failure)
```

**Found in:** code-reviewer pass on CB-2048.
""",
    },
    {
        "title": "[CB-2048 F-5..F-9] LOW: E1 polish bundle — naming, visibility-API, hint wording, fragment fragility, log spam",
        "type": "BUG",
        "priority": "LOW",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "fullstack-developer",
        "reporter": "AI",
        "description": """**Severity:** LOW / NIT (none blocking; bundled for one polish pass)

Five non-blocking findings from the CB-2048 code-reviewer pass:

---

**F-5: `host` field overloaded to mean filesystem path in PERSISTENT mode**
- `backend/api/system.py:33-39`, `backend/services/rag_service.py:167`
- Pydantic field is named `host` but in PERSISTENT mode it carries an absolute filesystem path. Frontend already pays the cost: `endpointLabel = isPersistent ? 'Path' : 'Endpoint'`.
- Fix: rename `host` → `endpoint` (and `_mode_detail` → `_endpoint`) for naming-truth, OR document the dual semantics in the Pydantic field description so OpenAPI consumers see it.

---

**F-6: no Page Visibility API gating; polls at full cadence behind hidden tabs**
- `frontend/components/service-monitor.tsx:198-203`
- 30 s `setInterval` never pauses on `document.visibilityState === 'hidden'`. Many open tabs = many parallel polls forever.
- Fix: subscribe to `visibilitychange`, skip fetch when `document.hidden`. Or migrate to React Query (project's documented standard per CLAUDE.md "State: React Query for server state") which handles visibility, retries, and exponential backoff.

---

**F-7: "silent fallback to embedded SQLite" hint will be wrong if PERSISTENT mode is intentional**
- `frontend/components/service-monitor.tsx:235`
- The hint prejudges PERSISTENT as undesired; legitimate dev/CI runs without the chromadb container.
- Fix: soften to "running on local PersistentClient (chromadb container not in use)".

---

**F-8: `RagStatusCard` duplicated across three return branches; brittle to future refactors**
- `frontend/components/service-monitor.tsx:985-998`, `:1030-1032`
- React keeps the same fiber position today, so card state survives. Any future reorder (e.g., wrapping a branch for animation) silently breaks that and triggers a remount mid-poll.
- Fix: pull `<RagStatusCard />` up so `ServiceMonitor` always returns a fragment containing it once at top level, with branches choosing what else to render alongside.

---

**F-9: heartbeat warning will fire every 30 s while chromadb is down → log spam**
- `backend/services/rag_service.py:175`
- 120 WARNING lines/hour for heartbeat + 120 for list_collections. Operators may mute and miss real issues.
- Fix: downgrade per-call WARNING to DEBUG (status endpoint already surfaces `healthy=False`), OR rate-limit to once-per-N-failures.

---

**Found in:** code-reviewer pass on CB-2048.
""",
    },
]


def main() -> None:
    created = []
    for body in bugs:
        try:
            resp = post(f"/projects/{PROJECT_ID}/issues", body)
        except urllib.error.HTTPError as exc:
            print(f"FAILED to create '{body['title'][:60]}': {exc} {exc.read()!r}")
            continue
        created.append((resp.get("key"), resp.get("id"), body["priority"]))
        print(f"created {resp.get('key')} ({body['priority']}): {body['title'][:80]}")

    # ---------- 2. Append findings summary to CB-2048 description ----------
    summary = (
        "\n\n---\n\n"
        "## Code review complete (2026-05-02)\n\n"
        "**Verdict: REQUEST-CHANGES** — 1 CRITICAL, 0 HIGH, 3 MEDIUM, 5 LOW.\n\n"
        "Findings filed as child BUGs under STORY CB-2047:\n"
    )
    for key, _id, sev in created:
        summary += f"- {key} [{sev}]\n"
    summary += (
        "\n**Reviewed scope:**\n"
        "- `backend/services/rag_service.py` (mode tracking + describe_mode + get_status_payload)\n"
        "- `backend/api/system.py` (status endpoint)\n"
        "- `backend/api/__init__.py` (system_router registration only — relations/groups out of scope)\n"
        "- `backend/app/main.py` (startup describe_mode log line only)\n"
        "- `backend/tests/test_rag_service_describe_mode.py`\n"
        "- `backend/tests/test_rag_service_status_payload.py`\n"
        "- `backend/tests/test_system_rag_status.py`\n"
        "- `frontend/components/service-monitor.tsx` (RagStatusCard additions)\n\n"
        "**What was done well:** reset-before-init pattern; layered error handling in `get_status_payload` "
        "(per-collection failure → that collection's `count: None` + `healthy=False`, rest of snapshot still renders); "
        "thorough status-payload test coverage (UNINITIALIZED / HTTP healthy / PERSISTENT healthy / heartbeat fail / "
        "list_collections fail / per-collection count fail); defensive `normalizeRagStatus` on the frontend.\n\n"
        "**Out of scope (deferred to siblings):** path-traversal on `PERSISTENT_FALLBACK_PATH` → CB-2049 "
        "(security-auditor); chroma container health → CB-2050 (regression).\n"
    )

    # fetch existing description
    with urllib.request.urlopen(f"{BASE}/issues/{CB_2048_ID}") as r:
        current = json.loads(r.read())
    new_desc = (current.get("description") or "") + summary
    patch(f"/issues/{CB_2048_ID}", {"description": new_desc})
    print(f"updated CB-2048 description ({len(summary)} chars appended)")

    # ---------- 3. Mark CB-2048 COMPLETED_WAITING_QA ----------
    patch(f"/issues/{CB_2048_ID}", {"status": "COMPLETED_WAITING_QA"})
    print("CB-2048 -> COMPLETED_WAITING_QA")


if __name__ == "__main__":
    main()
