"""CB-2379 closeout — settings/documentation Re-run uses rewrite mode.

- PATCH CB-2379 -> COMPLETED_WAITING_QA
- Append a closeout comment summarising the fix, audit gates, and follow-ups.

Run: python backend/scripts/codeboard/2026-05-09-cb-2379-cwq.py
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
CB_2379_ID = "21846a4e-495f-41bf-b368-185d747bc185"

COMMENT = """**Fix shipped (Jonny / VP-R&D, 2026-05-09)**

`frontend/app/settings/documentation/page.tsx` — `SummaryRow.handleConfirm` now passes
`executionMode: 'rewrite'` (option 2 from the ticket, adapted to the existing backend
contract). Backend `start_execution` (`backend/api/execution.py:194-196`) intentionally
ignores the client `force` flag; only `audit`/`rewrite` modes bypass the dep-check guard.
`rewrite` also resets the issue to `TODO` server-side, so the dep-check then passes
naturally and a fresh Claude Code session is spawned end-to-end.

**Side-effect disclosure**: ConfirmDialog body now reads
"This will reset CB-XXXX to TODO and start a fresh Claude Code session."

**Cache hygiene**: invalidate `recent-execution-summaries`, `issue/<id>`, and `issues`
queries on success so the Recent Summaries row + open issue cards reflect the new TODO
status without a hard reload.

**Audits**
- code-reviewer: clean on CRITICAL/HIGH. MEDIUM "stale React Query cache" addressed
  in this commit. Two LOW nits absorbed (dialog text disclosure, test tightened).
- security-auditor: no CRITICAL/HIGH from this diff. Pre-existing MEDIUM (no authn on
  `POST /api/execute/issue/{id}`) acknowledged but predates this fix and is tracked
  separately in `backend/app/rate_limit.py`.

**Regression**: `frontend/tests/components/DocumentationSettingsRerun.test.tsx` —
asserts the mutation is called exactly once with `{ issueId, provider, executionMode:
'rewrite' }`, that the legacy `force` flag is NOT sent, and that the dialog discloses
the TODO reset. All 199 component tests pass.

**Acceptance**
- (b) Re-run on a CWQ/DONE summary now actually re-executes the issue end-to-end.
- No silent failed-session noise in GlobalAgentStatusBar.

Awaiting Eli's QA promotion to DONE.
"""


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}")
        raise


def main() -> None:
    http("PATCH", f"/issues/{CB_2379_ID}", {"status": "COMPLETED_WAITING_QA"})
    print("CB-2379 -> COMPLETED_WAITING_QA")

    http(
        "POST",
        f"/issues/{CB_2379_ID}/comments",
        {"author": "Jonny (VP-R&D)", "content": COMMENT},
    )
    print("comment appended")


if __name__ == "__main__":
    main()
