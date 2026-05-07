"""CB-2375 close-out:

1. Mark CB-2375 -> COMPLETED_WAITING_QA with implementationSummary.
2. File a follow-up MEDIUM-severity bug under EPIC CB-2054 capturing the
   security-auditor M1 finding (per-route rate limit on the LLM
   `/features/{id}/documentation/generate` endpoint before any non-localhost
   exposure).

Per-project per-session script per Bible Rule 29.
Run: python3 scripts/codeboard/2026-05-07-CB-2375-cwq-and-followup.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
CB_2375_ID = "05c3b400-644b-433f-a4ff-d196b7754fc8"
CB_2054_PARENT_ID = None  # resolved at runtime


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{API}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} on {method} {url}\n{body_text}") from exc


def _resolve_cb_2054_id() -> str:
    page = 1
    while True:
        resp = _request(
            "GET",
            f"/projects/{PROJECT_ID}/issues?pageSize=200&page={page}",
        )
        for issue in resp.get("items", []):
            if issue.get("key") == "CB-2054":
                return issue["id"]
        if page >= resp.get("totalPages", 1):
            break
        page += 1
    raise SystemExit("CB-2054 not found")


CB_2375_SUMMARY = """
## Fix shipped — CB-2375 (Documentation Generate UI 504)

### Root cause
Two stacked client-side timeouts shorter than the LLM aggregation:
1. Next.js proxy `frontend/app/api/codeboard/[...path]/route.ts` aborted ALL
   POST/PUT/PATCH at **15 s**.
2. Frontend `lib/api/api-fetch.ts` aborted via `AbortController` at **30 s**
   (the JSON `apiFetch` wrapper at `lib/api/api-client.ts` accepted only
   `RequestInit`, so callers couldn't override).

`POST /api/features/{id}/documentation/generate` runs an LLM aggregation
across execution summaries / implementation notes / QA tasks and routinely
takes 30–35 s, so the UI surfaced 504 while the backend completed and
ChromaDB indexed successfully.

### Fix (Option 1 from the ticket — per-route timeout allowlist)
- **NEW** `frontend/app/api/codeboard/[...path]/timeouts.ts` — per-route
  timeout config with `getTimeoutMs(pathStr, method)` helper. Default 15 s.
  First-match-wins. Currently one entry:
  `POST /features/{id}/documentation/generate` → 120_000 ms.
- `frontend/app/api/codeboard/[...path]/route.ts` — imports `getTimeoutMs`,
  replaces all five hard-coded `15000` literals, includes `timeoutMs` in 504
  error JSON for ops debugging. `buildUrl` now returns `{ url, pathStr }`.
- `frontend/lib/api/api-client.ts` — widened `apiFetch<T>` options type from
  `RequestInit` to `ApiFetchInit` so callers can pass per-request `timeout`
  (additive, type-safe).
- `frontend/hooks/useCodeBoard.ts:useGenerateFeatureDocumentation` — passes
  `timeout: 120_000` to match the proxy override end-to-end.
- **NEW** `frontend/__tests__/api-codeboard-proxy-timeouts.test.ts` — 9
  vitest cases: default fallback, empty path, POST override hit, GET on same
  path NOT bumped, PUT/PATCH/DELETE on same path NOT bumped, sibling
  `/features` paths NOT bumped, unrelated `/documentation` paths NOT bumped,
  regex anchoring (no prefix forgery), `TIMEOUT_OVERRIDES` shape check.

### Verification
- `npx vitest run __tests__/api-codeboard-proxy-timeouts.test.ts` — 9/9 pass.
- `npx tsc --noEmit` — clean for changed files (one pre-existing unrelated
  error in `app/api/docker/metrics/route.ts`).
- Direct backend probe: 200 in 37.7 s.
- Proxy curl through :3601: 200 in 33.9 s (was 504 at 15 s pre-fix).
- Playwright Chrome regression: clicked **Regenerate** on CB-2038's
  documentation page — single POST, status 200, page rendered "Indexed in
  ChromaDB" + "Last updated" with no 504 toast.
- Code-reviewer agent: no CRITICAL/HIGH; one MEDIUM nit on AbortError
  source disambiguation (followed up only, not blocking).
- Security-auditor agent: no CRITICAL/HIGH; M1 (per-route rate limit on
  LLM endpoint before non-localhost exposure) filed as a separate ticket
  under EPIC CB-2054.

### Why NOT options 2/3 from the ticket
SSE streaming (option 2) would fix the symptom but invert the contract —
a JSON endpoint becomes a stream surface, callers (`useGenerateFeatureDoc`
+ tests) would all need to change, and the proxy already passes streaming
through. Job-and-poll (option 3) is the right long-term shape but is a
multi-epic refactor; out of scope for a HIGH bug blocking E2 acceptance.
The allowlist is the smallest correct surface.
""".strip()


CB_FOLLOWUP_TITLE = (
    "Add per-route rate limit to /features/{id}/documentation/generate "
    "before any non-localhost exposure"
)
CB_FOLLOWUP_DESCRIPTION = """
**Source**: Security audit during CB-2375 (per-route timeout allowlist).
Severity in audit: **MEDIUM** (DoS amplification on the LLM endpoint).

## Risk
After CB-2375, the proxy + client-side timeout for
`POST /features/{id}/documentation/generate` is 120 s. Backend protection
today is:
- **slowapi global** `200/min` per-IP (`backend/app/main.py:26`)
- **`projectId` scoping** (CB-2117 IDOR fix)

That's enough for current local/single-tenant deployment, but on the
public internet (or any multi-tenant deploy) a single attacker who knows
or guesses a valid `projectId`+`issueId` pair can sustain ~200 concurrent
calls/min, each pinning a Next.js route handler for up to 2 minutes plus
a real backend AI provider call (token cost). On serverless/Vercel each
in-flight request burns concurrency.

## Fix (recommended)
1. Add a per-route slowapi limit, e.g. `@limiter.limit("5/minute")` on
   `POST /api/features/{issue_id}/documentation/generate` in
   `backend/api/documentation.py:319`. Tune to whatever cap matches
   observed legitimate user behaviour (real users click Regenerate
   maybe twice an hour).
2. Long-term: convert the endpoint to job-and-poll
   (POST → 202 + jobId, GET /status → ready / pending) so request handlers
   release immediately and a worker pool caps actual concurrency. This is
   option 3 from CB-2375 and was deliberately deferred.

## Acceptance
- New per-route limit enforced on `POST /features/{id}/documentation/generate`
  with a clear 429 response when exceeded.
- pytest covers the limit boundary (5 successes + 1 throttled in <60 s).
- Documentation runbook (`backend/docs/AUTOPILOT_RUNBOOK.md` or a new
  doc-pipeline runbook) references the limit and the long-term plan.

## Severity
MEDIUM — not blocking CB-2054 acceptance on local/single-tenant. Must be
resolved BEFORE any public/multi-tenant exposure.

## Evidence
See CB-2375 close-out comment for the security audit transcript and the
proxy + client-side timeout pairing this ticket protects against abuse of.
""".strip()


def main() -> None:
    cb_2054_id = _resolve_cb_2054_id()
    print(f"CB-2054 id: {cb_2054_id}")

    print(f"Marking CB-2375 ({CB_2375_ID}) -> COMPLETED_WAITING_QA …")
    _request(
        "PATCH",
        f"/issues/{CB_2375_ID}",
        {
            "status": "COMPLETED_WAITING_QA",
            "implementationSummary": CB_2375_SUMMARY,
        },
    )
    print("  ok")

    print("Filing follow-up bug under CB-2054 …")
    created = _request(
        "POST",
        f"/projects/{PROJECT_ID}/issues",
        {
            "title": CB_FOLLOWUP_TITLE,
            "description": CB_FOLLOWUP_DESCRIPTION,
            "type": "BUG",
            "priority": "MEDIUM",
            "parentId": cb_2054_id,
            "labels": "documentation-surface,security-followup,cb-2375",
            "reporter": "AI",
            "assignee": "security-auditor",
        },
    )
    print(f"  created: {created.get('key')} ({created.get('id')})")


if __name__ == "__main__":
    sys.exit(main() or 0)
