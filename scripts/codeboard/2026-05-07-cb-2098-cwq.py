"""CB-2098 [QA] E3-5: Recent summaries list shows latest 20 ordered DESC.

QA verification PASS — flip to COMPLETED_WAITING_QA.
Per-project + per-session helper (Rule 29). Single-shot.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


BASE = "http://localhost:8401/api"
ISSUE_ID = "b46794dc-a205-4bd9-aa7f-a5a84b01fafe"  # CB-2098

EVIDENCE = """\
QA PASS — E3-5 recent summaries list (CB-2098)

Acceptance: open settings → recent list → newest-first, count <=20.

Code audit:
  backend/api/doc_settings.py:96-116
    GET /api/documentation/summaries
    - limit: int = Query(default=20, ge=1, le=100)
    - select(ExecutionSummary, Issue.key)
        .outerjoin(Issue, ExecutionSummary.issueId == Issue.id)
        .order_by(ExecutionSummary.executedAt.desc())
        .limit(limit)
  frontend/hooks/useCodeBoard.ts:1412
    useRecentExecutionSummaries(limit = 20) — passes limit to ?limit=N
  frontend/app/settings/documentation/page.tsx:400
    useRecentExecutionSummaries(20) — render in API order, no client re-sort

Live regression (curl http://localhost:8401):
  GET /api/documentation/summaries          → 200, 20 rows, DESC verified
  GET /api/documentation/summaries?limit=5  → 200, 5 rows
  GET /api/documentation/summaries?limit=200 → 422 (Pydantic le=100 enforced)
  Top 3 timestamps:    2026-05-06T23:28:59, 23:22:07, 23:14:12
  Bottom 3 timestamps: 2026-05-06T14:40:47, 2026-05-02T20:44:34, 20:36:54
  All 20 rows enriched with issueKey.

Visual QA (Chrome 1440x900, /settings/documentation):
  ✅ Header "Recent Execution Summaries" + "latest 20 across all issues"
  ✅ Table renders 20 rows (newest first)
  ✅ Top: 5/6/26, 11:28 PM CB-2097
  ✅ Bottom: 5/2/26, 8:36 PM CB-2048
  ✅ Each row: timestamp · issue link · provider · exit · files · +/- lines · Re-run

Evidence:
  docs/research/cb-2098-recent-summaries-list.png (full-page screenshot)
  docs/research/cb-2098-qa-report.md (full QA report)

Verdict: PASS. Backend ORDER + LIMIT correct, frontend hook + render preserve them.
"""


def request(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"HTTP {resp.status}: {body}")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}")


def main() -> None:
    print("Posting evidence comment to CB-2098...")
    request(
        "POST",
        f"/issues/{ISSUE_ID}/comments",
        {"content": EVIDENCE, "author": "AI"},
    )
    print("Flipping CB-2098 -> COMPLETED_WAITING_QA...")
    request(
        "PATCH",
        f"/issues/{ISSUE_ID}",
        {"status": "COMPLETED_WAITING_QA"},
    )
    time.sleep(0.2)
    final = request("GET", f"/issues/{ISSUE_ID}")
    print(f"  status: {final.get('status')}")
    print(f"  key:    {final.get('key')}")


if __name__ == "__main__":
    main()
