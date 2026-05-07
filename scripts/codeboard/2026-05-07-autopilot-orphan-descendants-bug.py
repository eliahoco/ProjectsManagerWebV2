"""
File BUG: AutoPilot does not enqueue audit-spawned descendants of active feature.

Context: when running AutoPilot on a FEATURE, audit gates (code-reviewer +
security-auditor) spawn new BUG issues under the feature's subtree mid-run.
Those BUGs land in BACKLOG and are NOT pulled into the running queue, so the
feature can never reach DONE/CWQ — parent EPICs/STORIEs stay IN_PROGRESS
because their newly-filed BUG children are still BACKLOG.

Real-world impact: CB-2038 "Documentation Surface" autopilot run (queue
e37d1972-89ca-40c7-acba-8db1af33935b) completed all 21 enqueued tasks but
left 16 audit-spawned BACKLOG BUGs and 4 IN_PROGRESS containers behind.

Parent: CB-639 (Auto Pilot Execution feature).
"""
import json, urllib.request, sys

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
PARENT_ID = "ap-feature-001"  # CB-639 Auto Pilot Execution

TITLE = (
    "AutoPilot does not enqueue audit-spawned descendants — feature can never "
    "reach completion when code-review/security-audit gates file new BUGs mid-run"
)

DESCRIPTION = """## Bug

When AutoPilot runs on a FEATURE, code-reviewer and security-auditor agents
file new BUG issues under that feature's subtree as they discover findings.
Those BUGs land in `BACKLOG` and are **not pulled into the running queue**.

Result: the feature never reaches a clean state. Parent EPICs/STORIEs stay
`IN_PROGRESS` because their newly-filed BUG children are still `BACKLOG`,
and the cascade-up rule correctly refuses to close them.

## Reproduction (real run)

- **Queue**: `e37d1972-89ca-40c7-acba-8db1af33935b`
- **Feature**: CB-2038 "Documentation Surface"
- **Started**: 2026-05-06 22:02:13
- **Finalized**: 2026-05-07 07:09:11 (after one token-exhaustion auto-resume)
- **Tasks enqueued**: 21 (all reached `COMPLETED_WAITING_QA`)
- **Subtree state after run**:
  - 82 `COMPLETED_WAITING_QA` (the 21 + cascading completions)
  - 16 `BACKLOG` audit-spawned BUGs:
    CB-2117, CB-2123, CB-2212, CB-2213, CB-2214, CB-2215, CB-2216, CB-2217,
    CB-2218, CB-2219, CB-2220, CB-2375, CB-2376, CB-2377, CB-2378, CB-2379
  - 4 `IN_PROGRESS` containers (cannot close due to BACKLOG children):
    CB-2039 (E1 epic), CB-2047 (S1.3 story),
    CB-2054 (E2 epic), CB-2067 (S2.4 story)

The queue is `completed` and the UI bar is gone, so from a user's POV the
feature looks "stuck" with no autopilot anywhere to advance it.

## Root cause

`autopilot_queue_service.py` builds the task list **once** at queue start
from the feature's descendants snapshot. It does not re-scan the subtree
between tasks, so any BUG filed by an audit gate during execution never
enters the pipeline. Audit-spawned tickets become orphans relative to the
queue that caused them.

## Suggested fix

Two viable approaches:

### Option A — re-scan subtree before each task (preferred)
Before pulling the next task off the queue, walk the active feature's
descendant tree for any `BACKLOG` BUG (or `BACKLOG` TASK) created **after**
queue start. Append to the end of the queue with proper `sequence` and
`AutoPilotTaskRecord` rows. Emit a `task_appended` event for the audit log.

Trade-off: simple, deterministic, plays nice with crash recovery (the
appended tasks already live in the DB).

### Option B — fold audit findings into a follow-up queue
On queue `finalized`, if the feature subtree still has open `BACKLOG` BUGs
or `IN_PROGRESS` containers, auto-create a follow-up AutoPilot queue
seeded with those BUGs. Mark the original queue as `completed-with-followup`.

Trade-off: keeps the original queue's task list immutable (cleaner audit
trail), but adds a second queue and another startup hop.

**Recommendation**: Option A. Lower friction, fewer states, matches user
expectation that "AutoPilot finishes the feature".

## Acceptance criteria

- [ ] Re-scan logic added to `autopilot_queue_service.py` (between tasks).
- [ ] Newly-filed `BACKLOG` BUGs inside the active feature's subtree get
      appended to the queue with `sequence = max(seq) + 1`.
- [ ] `AutoPilotTaskRecord` rows persisted for appended tasks (crash-safe).
- [ ] `task_appended` audit event emitted with payload `{issueId, key, source}`.
- [ ] Re-scan respects `max_retries` (don't append the same issue twice in
      one run).
- [ ] Unit test: feature with 5 enqueued tasks, audit gate files 2 BUGs
      mid-run, queue completes 7 tasks total.
- [ ] Regression: re-run CB-2038 after fix lands and verify the 16
      remaining BUGs get enqueued + driven to `COMPLETED_WAITING_QA`.

## Related

- Source: `backend/services/autopilot_queue_service.py`
- Persistence: `backend/utils/autopilot_repository.py`,
  `backend/models/autopilot.py`
- Mirror: `frontend/prisma/schema.prisma` (AutoPilotTaskRecord)
- Runbook: `backend/docs/AUTOPILOT_RUNBOOK.md` (update after fix)
- Lineage: CB-1951 (pause/resume), CB-1640 (background execution),
  CB-1617 (chain-to-next-task fix)
"""


def call(method, path, body=None):
    headers = {"Content-Type": "application/json"} if body else {}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main():
    body = {
        "title": TITLE,
        "description": DESCRIPTION,
        "type": "BUG",
        "priority": "HIGH",
        "parentId": PARENT_ID,
        "labels": "autopilot,orphan-descendants,blocks-cb-2038",
        "assignee": "python-pro",
        "reporter": "AI",
    }
    issue = call("POST", f"/projects/{PROJECT_ID}/issues", body)
    issue_id = issue["id"]
    issue_key = issue["key"]
    print(f"Created {issue_key} (id={issue_id})")

    # Mark IN_PROGRESS so the execution path is tracked correctly
    call("PATCH", f"/issues/{issue_id}", {"status": "IN_PROGRESS"})
    print(f"  → status=IN_PROGRESS")

    # Kick off AI execution
    exec_resp = call("POST", f"/execute/issue/{issue_id}", {})
    print(f"  → execution: {json.dumps(exec_resp)[:200]}")

    return issue_key, issue_id


if __name__ == "__main__":
    try:
        key, _id = main()
        print(f"\nDONE — file: {key} executing now")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)
