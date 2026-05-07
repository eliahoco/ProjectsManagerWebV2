"""CB-2211 → COMPLETED_WAITING_QA + audit comment (Rule 29)."""
import json
import urllib.request

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
ISSUE_KEY = "CB-2211"

COMMENT = """**CB-2211 fix shipped — pre/post checklist completed.**

**Implementation**
- Added `frontend/app/api/system/rag/status/route.ts` (GET-only proxy) that forwards to FastAPI at `${BACKEND_URL || 'http://localhost:8401'}/api/system/rag/status`.
- Mirrors the existing `/api/codeboard/[...path]/route.ts` pattern: 15s `AbortController` timeout, 502 on connection failure, 504 on `AbortError`, JSON-or-passthrough body.
- `RagStatusCard` (service-monitor.tsx:208) now receives valid responses every poll instead of 404.

**Defense-in-depth applied (security-auditor MEDIUM/LOW findings)**
- `export const dynamic = 'force-dynamic'` — Next 16 cannot statically optimize a live infra heartbeat.
- Sanitized error log: `console.error('[rag-status proxy] upstream error:', message)` — avoids leaking resolved hostname/IP from raw `Error` objects.
- `Cache-Control: no-store` on every response branch (success, 502, 504, passthrough, empty-body) — prevents collection-name leaks via shared caches.
- Switched request header from `Content-Type: application/json` (meaningless on GET) to `Accept: application/json`.

**Findings deferred (already tracked elsewhere or low-impact polish)**
- Backend endpoint hardening (path leak / project enumeration / DoS amplification) — covered by sibling tickets CB-2216, CB-2217, CB-2218.
- Non-JSON passthrough clamp — defense-in-depth only; backend always returns JSON. Logged as future polish, not blocking.
- BACKEND_URL protocol allowlist — env is operator-controlled; would only catch typos. Out of scope.

**Regression test (vitest)**
- `frontend/__tests__/api-system-rag-status-route.test.ts` — 5 tests pinning: forwards URL + Accept header + AbortSignal, returns 502 on ECONNREFUSED, 504 on AbortError, status passthrough on non-2xx, empty-body passthrough. All assert `Cache-Control: no-store`. **5/5 passing.**

**End-to-end smoke**
- `curl http://localhost:3601/api/system/rag/status` (through Next.js layer) → HTTP 200, `cache-control: no-store`, payload byte-identical to direct backend call (`mode=HTTP`, `total_docs=3508`, 8 collections).
- The card at service-monitor.tsx:208 now resolves on every poll. The original "RAG offline" loop is broken.

**Audits**
- `code-reviewer` agent: zero CRITICAL/HIGH (one HIGH was a false positive about test setup — green run proves `tests/setup.ts:53` already mocks `fetch` globally). MEDIUMs on `force-dynamic` + query-string forwarding addressed.
- `security-auditor` agent: zero CRITICAL/HIGH. SSRF/open-redirect surface closed by hardcoded path. MEDIUMs on log sanitization + Cache-Control addressed.

**Files**
- `frontend/app/api/system/rag/status/route.ts` (new)
- `frontend/__tests__/api-system-rag-status-route.test.ts` (new)

Status → `COMPLETED_WAITING_QA` for Eli's manual QA pass.
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


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    iid = get_id_by_key(ISSUE_KEY)
    print(f"{ISSUE_KEY} → {iid}")
    print("Posting comment ...")
    post(f"/issues/{iid}/comments", {"content": COMMENT, "author": "AI"})
    print("Setting status COMPLETED_WAITING_QA ...")
    print(patch(iid, {"status": "COMPLETED_WAITING_QA"}))


if __name__ == "__main__":
    main()
