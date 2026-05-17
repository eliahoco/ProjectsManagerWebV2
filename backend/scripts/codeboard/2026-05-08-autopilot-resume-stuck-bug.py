"""
File CB-1951 regression BUG: AutoPilot resume after backend restart hangs —
task list shows empty issue_key/issue_title, queue does not advance.

Per Bible Rule 28: BUG report → file CodeBoard FIRST, before reading code.
Per Bible Rule 24: Chrome screenshot evidence captured.
Per Bible Rule 29: this script lives in backend/scripts/codeboard/.

Reporter: AI (on behalf of Eli).
Parent: CB-1951 (AutoPilot pause-resume + crash recovery — CWQ since 2026-05-04).
Severity: CRITICAL.
"""

from __future__ import annotations
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
PARENT_KEY = "CB-1951"

DESCRIPTION = """## Summary

After a backend restart, the AutoPilot crash-recovery banner correctly appears and offers Resume / Stop. Pressing **Resume** leaves the queue STUCK: the main feature toggle spins forever, the task list renders with empty rows (no key, no title, no description), one task shows "failed", the rest show "pending", and no further work happens.

This is a CRITICAL regression on **CB-1951 (AutoPilot pause-resume + crash recovery)** — the entire user-visible resume path is broken.

## Reproduction (from Eli, 2026-05-08)

1. Start an AutoPilot queue on a feature (e.g. CB-2038).
2. Let some tasks complete; let one task fail to advance current_index past pending entries.
3. Restart the FastAPI backend (kill + relaunch — the watchdog can do this).
4. Reload `/codeboard` in browser.
5. Crash-recovery alert appears: "Backend restarted. Resume / Stop?"
6. Press **Resume**.
7. **Observed:** Toggle on the feature spins forever. Task list rows are empty (no issue key, no title, no description). Queue does NOT advance. The session list is empty. No errors in the browser console.

## Live evidence (captured 2026-05-08 via `GET /api/execute/queue/recovery-status`)

```json
{
  "recovered_count": 1,
  "queues": [{
    "id": "c778e8bb-d14b-400b-924a-0be835eefc28",
    "feature_key": "CB-2038",
    "status": "paused",
    "current_index": 9,
    "tasks": [
      {"issue_id": "f7f2f95e-...", "issue_key": "", "issue_title": "", "order": 0, "status": "completed", ...},
      {"issue_id": "31577eee-...", "issue_key": "", "issue_title": "", "order": 1, "status": "completed", ...},
      ...20 tasks total...
      {"issue_id": "21846a4e-...", "issue_key": "", "issue_title": "", "order": 15, "status": "pending", ...}
    ],
    "progress": {"total": 20, "completed": 9, "skipped": 0, "failed": 1, "pending": 10, "percent": 45.0}
  }]
}
```

Smoking gun: **every task has `issue_key: ""` and `issue_title: ""` after rehydration**, even though the underlying `issue_id` (UUID) is preserved correctly. The empty strings are why the UI shows blank rows.

`GET /api/execute/sessions` returns `[]` — Resume did NOT actually start a Claude Code subprocess for the next pending task at index 9.

Screenshot: `docs/research/2026-05-08-autopilot-resume-stuck-1.png`

## Root cause hypothesis (NOT verified yet — ticket-first per Rule 28)

The persistence/rehydration logic in `services/autopilot_queue_service.py` (CB-1951 E1) appears to:
1. Persist only `issue_id` (UUID) per task, NOT `issue_key`/`issue_title`.
2. On `rehydrate_from_db()` startup hook, restore tasks with empty key/title fields.
3. The Resume endpoint then tries to act on the next pending task — but downstream code paths likely depend on `issue_key` being populated (for prompt construction, status updates, SSE events).

Without the code review, this is a hypothesis. Likely files to inspect:

- `backend/services/autopilot_queue_service.py` — `rehydrate_from_db`, `_resume_paused_queue`
- `backend/utils/autopilot_repository.py` — read/write of `AutoPilotTaskRecord`
- `backend/models/autopilot.py` — schema for `AutoPilotTaskRecord` (does it store key+title?)
- `backend/api/execution.py` — `POST /api/execute/queue/{id}/resume` handler
- `frontend/contexts/AutoPilotContext.tsx` — Resume action wiring
- `frontend/components/codeboard/AutoPilotFloatingBar.tsx` — empty-row rendering

## Acceptance criteria

1. After a real backend restart, pressing Resume on the recovery banner advances the queue from `current_index` and starts a Claude Code subprocess for the next pending task.
2. Recovered task list renders with full `issue_key` + `issue_title` populated (not empty strings).
3. The "1 failed" task continues to show its error message (already correct).
4. Pending tasks render with their issue title, not blank rows.
5. Live SSE events flow into the UI as Resume progresses.
6. Regression test added that:
   - Creates an AutoPilot queue with N tasks.
   - Persists state to DB.
   - Calls `rehydrate_from_db()` on a fresh service instance.
   - Asserts every restored task has non-empty `issue_key` and `issue_title`.
7. Chrome QA: end-to-end flow — start queue → kill backend → relaunch → reload UI → Resume → confirm queue advances within 10s.

## Severity rationale: CRITICAL

The entire user-visible crash-recovery resume path is broken. CB-1951 is in COMPLETED_WAITING_QA pending Eli's manual QA. This bug would block CB-1951 → DONE. It also blocks the user from completing CB-2038 (Documentation Surface) — the queue hosting that work is currently stuck.

## Discovered

2026-05-08 by Eli, mid-CB-2038 autopilot run. Eli reported via chat with this exact scenario: "the toggle on the main feature is turning around with nothing and no result. The list of tasks that were in this autopilot is empty. And the one which failed just shows failed, and the rest show pending with no description."

## Linked

- Parent feature: CB-1951 (will need rollback to IN_PROGRESS until this is fixed)
- Affected user-facing flow: CB-2038 (Documentation Surface) — currently stuck
- Touches CB-1951 epics: E1 (persistence), E2 (rehydrate), E5 (frontend pause/resume UX)

## Bible compliance

- **Rule 28:** ticket filed BEFORE any code read.
- **Rule 24:** Chrome evidence captured (`docs/research/2026-05-08-autopilot-resume-stuck-1.png`).
- **Rule 22:** when fixed → COMPLETED_WAITING_QA, never DONE without Eli.
- **Rule 18:** fix will pass code-reviewer + security-auditor + debugger functional + Chrome QA before CWQ.
- **Rule 27:** evidence and screenshots stored under `docs/research/`, not `/tmp/`.
"""

LABELS = "🚀-bug,cb-1951-regression,autopilot,crash-recovery,critical,resume-stuck"


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} on {method} {path}: {body_txt[:400]}")
        raise


def find_parent_id(key: str) -> str | None:
    for page in range(1, 50):
        r = http("GET", f"/projects/{PROJECT_ID}/issues?page={page}&pageSize=200")
        for x in r.get("items", []):
            if x.get("key") == key:
                return x["id"]
        if page >= r.get("totalPages", 1):
            break
    return None


def main() -> None:
    parent_id = find_parent_id(PARENT_KEY)
    if not parent_id:
        raise SystemExit(f"Parent {PARENT_KEY} not found")
    print(f"Parent {PARENT_KEY} → {parent_id}")

    body = {
        "title": "[CB-1951 regression CRITICAL] AutoPilot resume after backend restart hangs — empty issue_key/issue_title in rehydrated tasks, queue does not advance",
        "description": DESCRIPTION,
        "type": "BUG",
        "priority": "CRITICAL",
        "reporter": "AI",
        "labels": LABELS,
        "status": "BACKLOG",
        "parentId": parent_id,
    }
    result = http("POST", f"/projects/{PROJECT_ID}/issues", body)
    print(f"OK — created {result.get('key')} (id={result.get('id')})")
    print(f"Status: {result.get('status')} | Priority: {result.get('priority')}")
    print(f"Labels: {result.get('labels')}")


if __name__ == "__main__":
    main()
