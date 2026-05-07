"""CB-2370 close-out + audit-gate follow-up bugs.

Run once. Idempotent on the status-flip (PATCH is safe to repeat); the
follow-up creates DO duplicate on re-run, so guard with a manual check
or only execute once.

What this does:

1. PATCHes CB-2370 → IN_PROGRESS, then → COMPLETED_WAITING_QA, with a
   close-out comment summarising the fix scope and audit verdicts.
2. Creates three new BUGs in BACKLOG capturing the non-blocking
   findings the audit gates surfaced on the CB-2370 diff:
     - MEDIUM (sec): rate-limit /api/system/rag/status
     - LOW    (sec): redact PERSISTENT abspath in RagStatusResponse.host
     - MEDIUM (review): wrap sync chromadb client calls in
       asyncio.to_thread inside RAGService.get_status_payload()

Project: ProjectsManagerWebV2 (1511e54f71dccd3fa79f67fe)
"""

import json
import sys
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

API_BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
CB_2370_ID = "d6ec73a6-17c4-4fe6-ad78-bf72d29ec394"
CB_2365_ID = "7f8ee1e2-e5d9-45e4-aa96-01daa2cc137d"


def _request(method: str, path: str, payload=None):
    url = f"{API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib_request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} on {method} {path}: {body[:400]}", file=sys.stderr)
        return exc.code, None
    except URLError as exc:
        print(f"URLError on {method} {path}: {exc}", file=sys.stderr)
        return None, None


def patch(issue_id: str, body: dict):
    return _request("PATCH", f"/issues/{issue_id}", body)


def post_comment(issue_id: str, content: str):
    return _request("POST", f"/issues/{issue_id}/comments", {"content": content, "author": "AI"})


def create_bug(title: str, description: str, parent_id: str | None, labels: str):
    return _request(
        "POST",
        f"/projects/{PROJECT_ID}/issues",
        {
            "title": title,
            "description": description,
            "type": "BUG",
            "priority": "MEDIUM",
            "parentId": parent_id,
            "labels": labels,
            "reporter": "AI",
        },
    )


def main() -> int:
    # ---- 1. CB-2370: IN_PROGRESS → COMPLETED_WAITING_QA ----
    status, _ = patch(CB_2370_ID, {"status": "IN_PROGRESS"})
    print(f"PATCH CB-2370 IN_PROGRESS -> {status}")

    closeout = (
        "## Fix shipped\n\n"
        "Backend: `GET /api/system/rag/status` (`backend/api/system.py`) "
        "wired through `RAGService.get_status_payload()` "
        "(`backend/services/rag_service.py:162-245`). Mounted under `/api` "
        "via `backend/api/__init__.py:51`.\n\n"
        "Frontend: dedicated proxy at "
        "`frontend/app/api/system/rag/status/route.ts` forwarding to "
        "`${BACKEND_URL}/api/system/rag/status` with 15s "
        "AbortController timeout, 502 / 504 mapping, `Cache-Control: "
        "no-store`.\n\n"
        "## Verification\n\n"
        "- Backend pytest: 10/10 pass (`tests/test_system_rag_status.py` + "
        "`tests/test_rag_service_status_payload.py`).\n"
        "- Frontend vitest: 5/5 pass "
        "(`frontend/__tests__/api-system-rag-status-route.test.ts`).\n"
        "- Live curl `localhost:8401` → 200 with healthy HTTP-mode payload "
        "(`total_docs=3509`).\n"
        "- Live curl `localhost:3601` (proxy) → 200 same payload.\n"
        "- Chrome `/codeboard` mount: 0 console errors, 0 warnings, "
        "RAG badge green `RAG HTTP 3,509 docs`. "
        "Acceptance ✅ (zero [RagStatusCard] errors).\n\n"
        "## Audit gates\n\n"
        "- code-reviewer: no CRITICAL/HIGH. MEDIUM (sync chroma calls on "
        "event loop) → filed as follow-up.\n"
        "- security-auditor: no CRITICAL. HIGH was inaccurate auth claim "
        "in the docstring; fixed in this task by rewriting "
        "`backend/api/system.py:1-19` to acknowledge the loopback bind "
        "(`launch.sh:128-129` defaults `BACKEND_HOST=127.0.0.1`) as the "
        "actual perimeter and clarify the `validate_origin` middleware "
        "scope. MEDIUM (rate-limit) and LOW (PERSISTENT abspath) → filed "
        "as follow-ups."
    )
    status, _ = post_comment(CB_2370_ID, closeout)
    print(f"COMMENT CB-2370 -> {status}")

    status, _ = patch(CB_2370_ID, {"status": "COMPLETED_WAITING_QA"})
    print(f"PATCH CB-2370 COMPLETED_WAITING_QA -> {status}")

    # ---- 2. Follow-up BUGs ----
    rate_limit_desc = (
        "## Source\n\n"
        "Security audit on CB-2370 (the `/api/system/rag/status` add).\n\n"
        "## Issue (MEDIUM, A04 Insecure Design / A09)\n\n"
        "`backend/api/system.py:42-50` carries no per-route rate limit. "
        "The default global `200/minute` limit "
        "(`backend/app/main.py:26`) keys by remote address, so the Next "
        "proxy (which makes every request appear from one host) can "
        "trigger heartbeat + N×collection.count() calls against ChromaDB "
        "at unbounded frequency from a single misbehaving client.\n\n"
        "## Suggested fix\n\n"
        "Add `@limiter.limit('30/minute')` (matches the 30s poll cadence "
        "with headroom) **or** add 1-2 s server-side memoisation in the "
        "Next proxy."
    )
    status, body = create_bug(
        title="Rate-limit /api/system/rag/status to protect ChromaDB",
        description=rate_limit_desc,
        parent_id=CB_2365_ID,
        labels="rag-status,security-followup,cb-2370-audit",
    )
    print(f"CREATE follow-up rate-limit -> {status} {body and body.get('key')}")

    path_desc = (
        "## Source\n\n"
        "Security audit on CB-2370.\n\n"
        "## Issue (LOW, A02/A05 Information Disclosure)\n\n"
        "When `mode=PERSISTENT`, `RagStatusResponse.host` is the absolute "
        "filesystem path of the embedded Chroma store (e.g. "
        "`/Users/<user>/.../backend/data/chroma`). On a single-tenant "
        "local-dev tool this is acceptable, but the abspath is "
        "unnecessary detail for an observability surface.\n\n"
        "## Suggested fix\n\n"
        "In `backend/services/rag_service.py:197`, replace `host = "
        "self._mode_detail or ''` with "
        "`host = os.path.basename(self._mode_detail) if self._mode_detail "
        "else ''`. Update "
        "`backend/tests/test_rag_service_status_payload.py:87` to assert "
        "the basename instead of `os.path.abspath(...)`.\n\n"
        "## Why deferred\n\n"
        "Behavioural change to a CB-2046-shipped surface; out of scope "
        "for the narrow CB-2370 fix-task."
    )
    status, body = create_bug(
        title="Redact PERSISTENT abspath in RagStatusResponse.host",
        description=path_desc,
        parent_id=CB_2365_ID,
        labels="rag-status,security-followup,cb-2370-audit",
    )
    print(f"CREATE follow-up path-redact -> {status} {body and body.get('key')}")

    sync_desc = (
        "## Source\n\n"
        "Code review on CB-2370.\n\n"
        "## Issue (MEDIUM, async correctness)\n\n"
        "`RAGService.get_status_payload()` "
        "(`backend/services/rag_service.py:162-245`) calls "
        "`heartbeat()`, `list_collections()`, and per-collection "
        "`count()` synchronously inside the FastAPI event loop "
        "(`backend/api/system.py:43`). A wedged ChromaDB container will "
        "stall the loop for the client's internal socket timeout while "
        "every connected browser polls every 30s.\n\n"
        "## Suggested fix\n\n"
        "Wrap the chromadb calls in `await asyncio.to_thread(...)` (and "
        "make `get_status_payload` async), or convert the route handler "
        "to plain `def` so FastAPI runs it on the threadpool. Pre-existing "
        "pattern across `RAGService`, so this is a broader cleanup, not a "
        "regression of CB-2370."
    )
    status, body = create_bug(
        title="Wrap sync chromadb calls in get_status_payload to free the event loop",
        description=sync_desc,
        parent_id=None,
        labels="rag-status,review-followup,cb-2370-audit",
    )
    print(f"CREATE follow-up sync-loop -> {status} {body and body.get('key')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
