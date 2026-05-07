"""CB-2097 [QA] E3-4: maxPerIssue caps row count per issue — mark COMPLETED_WAITING_QA.

Per-project + per-session helper (Bible rule 29). Single-shot.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


BASE = "http://localhost:8401/api"
ISSUE_ID = "6938ade7-8660-4260-b0e7-a21da53c3c05"  # CB-2097

EVIDENCE = """\
QA PASS — E3-4: maxPerIssue caps row count per issue (CB-2097)

Acceptance criterion: 25 ExecutionSummary rows on a single issue + DocSettings.maxPerIssue=20
-> after retention pass, only newest 20 rows remain (5 oldest purged).

Coverage (two complementary verifications)

1) Automated regression — added pytest case at the literal AC values:
   tests/test_e3_full_regression.py::test_per_issue_cap_purges_25_to_20_with_default_cap
     - retentionDays pinned to 10000 so age phase cannot fire
     - 25 rows on `issue-cap-25`, strictly increasing executedAt (1-min spacing)
     - apply_retention(db) -> (purged_by_age=0, purged_by_cap=5)
     - re-query DESC: surviving ids == [r-00..r-19] (newest 20)
   Full E3 + DocSettings suite: 19 passed in 1.10s (was 18; new test is the only addition).
   No regression in the 18 pre-existing tests.

2) Live-DB trace — new operator script driving the running backend's SQLite
   through the exact apply_retention import the asyncio loop calls
   (app/main.py:200-242):
     backend/scripts/regression/2026-05-07-cb2097-live-maxperissue.py
   Sentinel issueId per run (uuid suffix), seed Project + Issue (FK target),
   pin retentionDays=10000 + maxPerIssue=20, insert 25 rows (1-min spacing),
   run apply_retention, assert exactly newest 20 survive, then full cleanup
   in finally (delete summaries -> delete issue -> delete project -> restore
   DocSettings snapshot). Every cleanup stage in its own session so a single
   failure cannot block the others. Live codeboard.db unchanged after run.
   Result: PASS — purged_by_age=0, purged_by_cap=5; surviving rows r00..r19.

Code path verified

  apply_retention(db)  [services/doc_settings_service.py:45]
    Phase 1 (age, retentionDays=10000) -> 0 purged
    Phase 2 (per-issue cap, maxPerIssue=20):
      SELECT executedAt FROM "ExecutionSummary"
        WHERE issueId = ? ORDER BY executedAt DESC
        LIMIT 1 OFFSET 20                       -- boundary row
      DELETE FROM "ExecutionSummary"
        WHERE issueId = ? AND executedAt <= ?   -- 5 rows deleted

Single-bound-parameter SQL (no NOT IN list, no SQLITE_MAX_VARIABLE_NUMBER
exposure even at maxPerIssue=1000) — the CB-2122 / CB-2124 hardening.

Audit gates

  - code-reviewer: PASS. Test ordering deterministic (zero-padded ids, DESC
    assertion pins both count and identity). Live script: sentinel uuid
    isolation, FK-correct seed/teardown order, DocSettings snapshot/restore
    in finally with per-stage isolation, no shared /tmp/ writes (Bible rule 29).
  - security-auditor: SAFE TO SHIP. No CRITICAL/HIGH/MEDIUM. All SQL via
    SQLAlchemy bound parameters, no user input, no secrets, no /tmp/ collision
    surface. One LOW (SIGKILL window between pin and finally could leave
    DocSettings pinned) — addressed via operator runbook note in script
    docstring documenting the manual restore values logged on stdout.

Evidence

  - backend/tests/test_e3_full_regression.py::test_per_issue_cap_purges_25_to_20_with_default_cap (new)
  - backend/tests/test_e3_full_regression.py::test_retention_respects_per_issue_cap (pre-existing, complementary)
  - backend/tests/test_doc_settings.py::test_apply_retention_caps_per_issue (pre-existing, service-level)
  - backend/scripts/regression/2026-05-07-cb2097-live-maxperissue.py (new)
  - docs/research/cb-2097-qa-report.md (full report)
  - pytest run: ./venv/bin/python -m pytest tests/test_e3_full_regression.py tests/test_doc_settings.py -v -> 19 passed
  - live trace: ./venv/bin/python scripts/regression/2026-05-07-cb2097-live-maxperissue.py -> PASS

Acceptance criterion satisfied (deterministic + live).
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
    print("Posting evidence comment to CB-2097...")
    request(
        "POST",
        f"/issues/{ISSUE_ID}/comments",
        {"content": EVIDENCE, "author": "AI"},
    )
    print("Flipping CB-2097 -> COMPLETED_WAITING_QA...")
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
