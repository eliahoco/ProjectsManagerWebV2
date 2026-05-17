"""
CB-1951 regression: Resume button no-ops on CB-2038 (16 done + 2 failed at end,
idx 18/18). Resume tries to advance past last task, finds nothing, no-op.
Retry button on failed tasks doesn't work either. Recovery banner duplicates
the existing AutoPilotFloatingBar.

Per Eli (2026-05-09): "I didn't say don't use the agents... I just want it
to be fixed once and for all." File 1 BUG + 7 TASKs under existing CB-1951.
NO new feature. Storyboard pattern.

Bible Rule 28: file CodeBoard FIRST.
Bible Rule 29: per-project script path.
"""
from __future__ import annotations
import json, urllib.request, urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
CB_1951_ID = "03f5c3a6-2ba1-4bd3-96b1-e55a81a3b977"
LABELS = "🚀-cb-1951-regression,resume-stuck,failed-task-recovery,autopilot"


def http(m, p, b=None):
    data = json.dumps(b).encode() if b else None
    req = urllib.request.Request(
        f"{BASE}{p}", data=data,
        headers={"Content-Type": "application/json"}, method=m,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:300]}")
        raise


BUG_DESC = """## Repro

CB-2038 queue: 16 completed + 2 failed (CB-2731, CB-2732 — credit exhaustion). current_index=18/18.

1. Press Resume on AutoPilotFloatingBar → no-op (queue advances to idx 18, no task there)
2. Press Retry on failed task → broken (no UI response)
3. Recovery banner appears on left (duplicate of existing right floating bar)

## Root cause

Two gaps:
1. **`resume_queue()` advances `current_index` linearly.** When idx is past last task and pending tasks exist (because some failed earlier), it doesn't rewind to first pending. Hits end-of-queue, marks done, no-op.
2. **Retry-failed UX is split from Resume.** User must (a) reset each failed task individually, (b) then resume. Two-click flow not discoverable. UI conflates the two.

Bonus: AutoPilotRecoveryBanner (CB-2751 added) duplicates AutoPilotFloatingBar's data — both render for paused queues.

## Fix scope (7 tasks)

1. Audit `/queue/{id}/task/{order}/reset` endpoint — does it accept paused queue + failed task?
2. Wire Retry-Failed button on AutoPilotFloatingBar (per-failed-task + bulk)
3. Backend: `resume_queue()` rewinds to first pending when idx past last
4. Frontend: Resume button label = "Retry failed & Resume" when failed tasks exist
5. Regression pytest + Chrome QA on real CB-2038
6. Remove duplicate AutoPilotRecoveryBanner mount from service-monitor.tsx
7. Roll back CB-2746/2747-2755 mess (DELETED, link this BUG)

## Acceptance

- CB-2038 Resume after retry advances queue + runs CB-2731 + CB-2732
- One floating UI element (AutoPilotFloatingBar) — no duplicate banner
- Bible Rule 25 full regression green
- Eli does Chrome QA personally → DONE

## Linked

- Regresses: CB-1951 (parent feature)
- Affects: CB-2038 (stuck queue)
- Supersedes scope: CB-2746 (parallel feature, DELETED)
"""


TASKS = [
    {
        "title": "[CB-1951 regression T1] Audit /queue/{id}/task/{order}/reset endpoint — accepts paused queue + failed task?",
        "priority": "CRITICAL",
        "assignee": "python-pro",
        "desc": (
            "Read-only audit. Files:\n"
            "- backend/api/execution.py — POST /queue/{id}/task/{order}/reset handler\n"
            "- backend/services/autopilot_queue_service.py — reset_task method\n\n"
            "Confirm: does it require queue.status==paused? Does it allow task.status==failed? "
            "Does it persist reset across DB? Are there pre-conditions blocking the CB-2038 case?\n\n"
            "Output: file:line citations + answer in this task's CodeBoard comment. NO code edits."
        ),
    },
    {
        "title": "[CB-1951 regression T2] Wire Retry-Failed button on AutoPilotFloatingBar — per-failed + bulk",
        "priority": "HIGH",
        "assignee": "react-specialist",
        "desc": (
            "Files:\n"
            "- frontend/components/codeboard/AutoPilotFloatingBar.tsx — already has retry button per CB-2737, verify it actually fires\n"
            "- backend endpoint /queue/{id}/task/{order}/reset (audited in T1)\n\n"
            "Fix: on Retry click, call POST reset endpoint per failed task. Show toast on success/error. "
            "Add bulk 'Retry all failed' button when ≥2 failed tasks. Live-update via SSE event.\n\n"
            "Acceptance: click Retry on CB-2731 → task status flips to pending in <2s. Bulk button resets both CB-2731 + CB-2732."
        ),
    },
    {
        "title": "[CB-1951 regression T3] Backend resume_queue rewinds to first pending when idx past last",
        "priority": "CRITICAL",
        "assignee": "python-pro",
        "desc": (
            "File: backend/services/autopilot_queue_service.py — resume_queue() method.\n\n"
            "Current behavior: resume advances current_index linearly. When idx >= len(tasks), marks queue complete.\n\n"
            "Fix: before advancing, scan for any task with status==pending. If found at order < current_index, "
            "rewind current_index to that task's order. Then resume. Persist via existing _persist path.\n\n"
            "Edge case: completed tasks past the rewind point should NOT re-run. Only pending.\n\n"
            "Acceptance: queue with idx=18, 16 completed + 2 failed (reset to pending) → resume rewinds to "
            "idx=16 (first pending), runs CB-2731 + CB-2732 sequentially, completes."
        ),
    },
    {
        "title": "[CB-1951 regression T4] Frontend Resume button label = 'Retry failed & Resume' when failed exist",
        "priority": "HIGH",
        "assignee": "react-specialist",
        "desc": (
            "File: frontend/components/codeboard/AutoPilotFloatingBar.tsx.\n\n"
            "Current: Resume button is plain 'Resume'. Fix: when queue.tasks contains any failed task, change "
            "label to 'Retry failed & Resume'. On click: reset all failed tasks first (T2 endpoint), then call "
            "existing /queue/{id}/resume.\n\n"
            "Acceptance: CB-2038 floating bar shows 'Retry failed & Resume'. Click → 2 failed tasks reset → resume → queue runs to completion."
        ),
    },
    {
        "title": "[CB-1951 regression T5] Regression pytest + Chrome QA on real CB-2038",
        "priority": "HIGH",
        "assignee": "debugger",
        "desc": (
            "Two parts:\n\n"
            "1. Backend pytest in backend/tests/test_cb1951_resume_failed_recovery.py (or extend existing): "
            "fixture creates queue with idx=N, M completed + K failed at end → call resume → assert rewinds + "
            "runs only pending → final state completed. ≥4 tests covering: rewind logic, completed-not-rerun, "
            "single failed, multiple failed.\n\n"
            "2. Chrome QA via chrome-devtools-mcp on real CB-2038: open /codeboard, click 'Retry failed & "
            "Resume', screenshot before+during+after, verify CB-2731 + CB-2732 actually run + complete.\n\n"
            "Acceptance: 4+ tests green. Screenshots saved docs/research/cb-1951-regression-fix-*.png. "
            "Real CB-2038 queue advances 18/18 → 18/18 done."
        ),
    },
    {
        "title": "[CB-1951 regression T6] Remove duplicate AutoPilotRecoveryBanner mount",
        "priority": "MEDIUM",
        "assignee": "react-specialist",
        "desc": (
            "File: frontend/components/service-monitor.tsx.\n\n"
            "Remove the <AutoPilotRecoveryBanner /> mount. AutoPilotFloatingBar already shows the same data "
            "for paused queues (CB-2038 visible at bottom-right), so the bottom-left banner is redundant.\n\n"
            "Keep the AutoPilotRecoveryBanner.tsx component file in place (delete only the mount + import). "
            "Future: could re-mount conditionally on a state FloatingBar doesn't cover (e.g. zombie). For now "
            "remove unconditionally.\n\n"
            "Acceptance: only 1 fixed-position element related to autopilot state visible on /codeboard. "
            "Existing AutoPilotRecoveryBanner Vitest still passes (component renders independently)."
        ),
    },
    {
        "title": "[CB-1951 regression T7] Roll back CB-2746/2747-2755 — duplicate feature, no children",
        "priority": "MEDIUM",
        "assignee": "jonny",
        "desc": (
            "Bible Rule 7 violation: created 9 empty EPICs (CB-2747 through CB-2755) under parallel FEATURE "
            "CB-2746 with zero TASK/STORY children. Duplicates CB-1951's existing breakdown (CB-2274 etc).\n\n"
            "Action:\n"
            "1. Roll back CB-2746 + CB-2747-CB-2755 status → BACKLOG (not DELETED — preserve audit trail)\n"
            "2. Add label 'superseded-by-cb-1951-regression' to all 10 issues\n"
            "3. Add IssueLink CB-2746 RELATES_TO (the new BUG from this script)\n"
            "4. Real fixes shipped in CB-2756/2757/2758/2759/2760/2761/2762/2763/2764/2765/2766/2772/2773 stay "
            "CWQ — they ARE real production code that was tested and deployed.\n\n"
            "Acceptance: 10 EPICs back to BACKLOG, labelled, linked. Audit fix bugs stay CWQ."
        ),
    },
]


def main():
    print(f"Filing BUG under CB-1951 (id={CB_1951_ID})")
    bug = http("POST", f"/projects/{PROJECT_ID}/issues", {
        "title": "[REGRESSION] Resume no-ops on CB-2038 — failed tasks at end + Resume/Retry UX broken",
        "description": BUG_DESC,
        "type": "BUG",
        "priority": "CRITICAL",
        "reporter": "AI",
        "labels": LABELS,
        "status": "BACKLOG",
        "parentId": CB_1951_ID,
        "assignee": "jonny",
    })
    bug_id = bug["id"]
    print(f"  BUG → {bug['key']} (id={bug_id})")

    print(f"\nCreating {len(TASKS)} TASK children...")
    for t in TASKS:
        body = {
            "title": t["title"],
            "description": t["desc"],
            "type": "TASK",
            "priority": t["priority"],
            "reporter": "AI",
            "labels": LABELS,
            "status": "BACKLOG",
            "parentId": bug_id,
            "assignee": t["assignee"],
        }
        r = http("POST", f"/projects/{PROJECT_ID}/issues", body)
        print(f"  {r.get('key'):<10} {t['title'][:80]}")

    print(f"\nDone. BUG = {bug['key']}, {len(TASKS)} tasks.")
    print(f"Roll CB-1951 → IN_PROGRESS so dashboard shows active fix.")


if __name__ == "__main__":
    main()
