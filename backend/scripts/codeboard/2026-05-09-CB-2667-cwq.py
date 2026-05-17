"""CB-2667 — file H-1 follow-up + mark CB-2667 COMPLETED_WAITING_QA.

Per Bible Rules 22/27/29: per-project per-session script lives under
backend/scripts/codeboard/. Never DONE — only Eli promotes.

What this does:
  1. Posts a CWQ summary comment on CB-2667 with the audit results.
  2. Files a HIGH follow-up under CB-2047 (S1.3 audit + regression)
     for the sibling-search-endpoint gap raised by security-auditor H-1.
  3. PATCHes CB-2667 → COMPLETED_WAITING_QA.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
CB_2667_ID = "c187ed23-5059-4298-afdf-91985e065e00"
CB_2047_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"

LABELS = "🚀-bug,cb-2217-sec-followup,cb-2666-perimeter"


def _request(url: str, payload: dict | None, method: str) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {method} {url}: {e.read().decode()[:300]}")
        raise


def add_comment(issue_id: str, content: str, author: str = "jonny") -> dict:
    return _request(
        f"{API}/issues/{issue_id}/comments",
        {"author": author, "content": content},
        "POST",
    )


def patch_issue(issue_id: str, fields: dict) -> dict:
    # Note: /api/issues/{id} (NOT /api/issues/issue/{id}). The latter is
    # only for `key`-based lookups; `{id}` accepts either UUID or key.
    return _request(f"{API}/issues/{issue_id}", fields, "PATCH")


def create_followup(parent_id: str, title: str, description: str) -> dict:
    return _request(
        f"{API}/projects/{PROJECT_ID}/issues",
        {
            "title": title[:500],
            "description": description,
            "type": "BUG",
            "status": "BACKLOG",
            "priority": "HIGH",
            "parentId": parent_id,
            "reporter": "AI",
            "assignee": "python-pro",
            "labels": LABELS,
        },
        "POST",
    )


CWQ_COMMENT = """**CB-2667 — fix landed, awaiting QA**

**Files changed**
- `backend/api/search.py:35-44, 211-242` — module docstring + new
  imports (`InternalAuthDep`, `limiter`); `dependencies=[InternalAuthDep]`
  + `@limiter.limit("30/minute")` + `request: Request` arg on
  `get_index_stats`. Mirrors the CB-2666 pattern on `/api/projects`.
- `backend/tests/test_security.py` — new `TestSearchStatsEndpointPerimeter`
  class (11 tests):
  - token unset → 200 + body shape
  - token set + missing/wrong/spoofed-Origin → 401 (gate)
  - token set + valid header → 200 + body shape
  - parametrized header-name case (lower / Title / UPPER) → 200
  - whitespace-padded token → 401
  - `Authorization: Bearer` NOT accepted → 401
  - AST-walk pin: `@router.get(... dependencies=[InternalAuthDep])`
    structurally present on `get_index_stats`
- `backend/docs/DOC_PIPELINE_RUNBOOK.md` §3 — gated-endpoint table
  extended; per-route rate-limit subsection updated; new "Frontend
  impact" subsection (`SemanticSearchPanel.tsx` direct-fetch story
  + Next.js proxy + `INTERNAL_API_TOKEN` naming discipline);
  "Token-existence side-channel" subsection (M-1 from sec-audit).

**Audit gates passed**
- Code-reviewer: 0 CRITICAL, 0 HIGH. Three LOW (test pin loose,
  test_token_unset assertion weak, helper-fragility comment) — all
  applied during the hardening pass before CWQ.
- Security-auditor: 0 CRITICAL. 1 HIGH (sibling search endpoints
  share the same threat shape) — filed as a follow-up ticket under
  CB-2047, NOT scope-creeped into this fix. 2 MEDIUM (M-1 token
  side-channel, M-2 frontend proxy guidance) — both addressed in
  runbook §3.
- Pytest: full `tests/test_security.py` → 64 passed in 1.05s.
  Pre-existing failures elsewhere (test_qa_sequence,
  test_schema_validation) confirmed by `git diff --stat HEAD` to
  be unrelated to this diff.

**Threat model recap**
Pre-fix: `GET /api/projects` (CB-2666 H-1, now gated) →
per-project_id list; `GET /api/search/{project_id}/stats` (this
ticket) → per-project doc count. Chain the two and you re-bind the
anonymous `count[]` from CB-2217 to specific project_ids in one
extra request hop.

Post-fix: stats endpoint shares the `InternalAuthDep` gate. On
loopback-bind dev (`INTERNAL_API_TOKEN=""`), pass-through preserves
the SemanticSearchPanel browser fetch. On non-loopback deploy, the
token is mandatory and the chain is broken at the same step
`/api/projects` is broken — same perimeter, same deploy-gate,
documented together in runbook §3.

**Follow-up filed**
- CB-2667-FU/H-1 (sibling-search endpoints): file-level finding
  filed under CB-2047 — `/{project_id}` (semantic search),
  `/{project_id}/similar`, `/embed/{issue_id}` (POST/DELETE),
  `/embed-all` (POST) all share the same per-project_id existence/
  data/write-amplification disclosure shape. Out of scope here;
  must close before any non-loopback deploy.

**Scope of remaining sibling tickets** (CB-2668 docs/openapi,
CB-2669 startup INFO log, CB-2729 status-cache lock) untouched.

→ COMPLETED_WAITING_QA. Eli, your call to verify.
"""


FOLLOWUP_TITLE = (
    "[CB-2667 sec audit follow-up H-1] HIGH: sibling /api/search/* endpoints "
    "share per-project_id disclosure / write-amplification shape"
)

FOLLOWUP_DESCRIPTION = """**Severity:** HIGH — a partial fix on `/stats`
(CB-2667) leaves five sibling endpoints under `backend/api/search.py`
exposed to the SAME threat model that CB-2667 closed. Until these are
gated, the CB-2666 + CB-2667 perimeter is incomplete on any non-loopback
deploy.

**Discovery:** security-auditor pass on the CB-2667 fix
(2026-05-09). H-1 is filed here rather than rolled into CB-2667 to
keep the original ticket scope-pure (single endpoint per fix).

## Affected endpoints

| Method | Path | Disclosure / Amplification |
|---|---|---|
| GET    | `/api/search/{project_id}` | per-project semantic search results (issue content disclosure) |
| GET    | `/api/search/{project_id}/similar` | per-project similar-issue results (issue content disclosure) |
| POST   | `/api/search/{project_id}/embed/{issue_id}` | mutates arbitrary collection — DoS amplification + IDOR write |
| DELETE | `/api/search/{project_id}/embed/{issue_id}` | deletes arbitrary embeddings — destructive IDOR |
| POST   | `/api/search/{project_id}/embed-all` | iterates EVERY Issue with `projectId == X` and embeds them — server-side fan-out, validates guessed CUIDs by 200-with-`embedded>0` |

## Fix recommendation

Apply the SAME pattern CB-2666 / CB-2667 established:

```python
@router.get(
    "/{project_id}",
    dependencies=[InternalAuthDep],
)
@limiter.limit("30/minute")
async def search_issues(request: Request, ...):
    ...
```

The two write endpoints (`POST /embed*`, `DELETE /embed*`,
`POST /embed-all`) deserve a STRICTER cap (suggest 10/minute) — they
are DoS-amplifying, not just disclosure. `embed-all` in particular
walks every Issue row matching `projectId` and embeds each one
synchronously, so a single request can pin the worker for seconds
on a large project.

## Runbook update needed

`backend/docs/DOC_PIPELINE_RUNBOOK.md` §3 currently lists `/stats`
as the only gated search endpoint. After this fix lands, extend
the table to cover all six routes under `/api/search/*` and note
the stricter cap on the write endpoints.

## Test parity

Mirror the `TestSearchStatsEndpointPerimeter` class — one parametrized
class per endpoint (or one shared parametrized fixture covering the
endpoint + method matrix) covering: token unset, missing header,
valid header, wrong header, Origin spoof, AST-walk source-text pin.

## Reproduction (post CB-2667, pre this fix)

With `INTERNAL_API_TOKEN=""` (default loopback dev):

```bash
# All 5 still 200 — same as before CB-2667
curl -s 'http://localhost:8401/api/search/<any-cuid>?q=foo' | head -c 200
curl -s 'http://localhost:8401/api/search/<any-cuid>/similar?title=foo' | head -c 200
```

With token set:

```bash
# /stats now 401 (CB-2667 fix), but the 5 siblings still 200 — gap.
curl -s -o /dev/null -w '%{http_code}\\n' 'http://localhost:8401/api/search/<any-cuid>/stats'
# → 401
curl -s -o /dev/null -w '%{http_code}\\n' 'http://localhost:8401/api/search/<any-cuid>?q=foo'
# → 200 (this is the gap)
```

## Threat-model linkage

CB-2217 (anonymous `count[]`) → CB-2666 H-1 (project_id list, gated)
→ CB-2667 H-2 (`/stats` per-project count, gated) → THIS (`/search/*`
sibling endpoints, ungated). Closing this finishes the perimeter
the CB-2217 redaction was supposed to provide.

_Filed by security-auditor agent during CB-2667 audit pass._
"""


def main() -> None:
    # 1. File H-1 follow-up under CB-2047 (sibling story).
    print("Filing H-1 follow-up under CB-2047...")
    followup = create_followup(
        CB_2047_ID, FOLLOWUP_TITLE, FOLLOWUP_DESCRIPTION
    )
    fu_key = followup.get("key") or followup.get("id", "(unknown)")
    print(f"  Filed {fu_key}: {FOLLOWUP_TITLE[:80]}...")

    # 2. Post CWQ summary on CB-2667.
    print("Posting CWQ summary on CB-2667...")
    add_comment(CB_2667_ID, CWQ_COMMENT)

    # 3. Mark CB-2667 → COMPLETED_WAITING_QA.
    print("Patching CB-2667 → COMPLETED_WAITING_QA...")
    result = patch_issue(CB_2667_ID, {"status": "COMPLETED_WAITING_QA"})
    print(f"  CB-2667 status: {result.get('status', '(unknown)')}")
    print("Done.")


if __name__ == "__main__":
    main()
