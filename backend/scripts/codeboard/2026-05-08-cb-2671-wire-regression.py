"""
Wire CB-2671 (AutoPilot resume regression bug) into the proper regression-bug
structure used by CB-2363/CB-2364/CB-2365:

  1. IssueLink CB-2671 CAUSED_BY  CB-1951  (origin feature — bug introduced here)
  2. IssueLink CB-2671 BLOCKS     CB-2038  (affected feature — queue stuck)
  3. 9 TASK children under CB-2671 implementing the fix-plan steps

Pattern source: CB-2363/CB-2364/CB-2365 (CB-1955 regression cluster). Per
Bible Rule 28, the BUG ticket is filed before any code is read.

Reporter: AI (on behalf of Eli, 2026-05-08).
"""

from __future__ import annotations
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
BUG_KEY = "CB-2671"
ORIGIN_KEY = "CB-1951"   # The feature this regresses
BLOCKS_KEY = "CB-2038"   # The feature whose autopilot queue is stuck

LABELS = "🚀-bug,cb-1951-regression,autopilot,crash-recovery,resume-stuck"


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
        print(f"  HTTP {e.code} on {method} {path}: {body_txt[:300]}")
        raise


def find_id(key: str) -> str:
    for page in range(1, 50):
        r = http("GET", f"/projects/{PROJECT_ID}/issues?page={page}&pageSize=200")
        for x in r.get("items", []):
            if x.get("key") == key:
                return x["id"]
        if page >= r.get("totalPages", 1):
            break
    raise SystemExit(f"{key} not found")


# Fix-plan TASK children (9 tasks)
FIX_TASKS = [
    {
        "title": "[CB-2671 fix T1] Verify hypothesis — read autopilot rehydrate + repository + resume endpoint",
        "priority": "CRITICAL",
        "assignee": "python-pro",
        "desc": (
            "Read the 4-5 likely files to confirm the hypothesis that issue_key + issue_title are not persisted "
            "(or are persisted but not restored) in the AutoPilot crash-recovery path.\n\n"
            "**Files:**\n"
            "- backend/services/autopilot_queue_service.py — `rehydrate_from_db`, `_resume_paused_queue`\n"
            "- backend/utils/autopilot_repository.py — read/write of `AutoPilotTaskRecord`\n"
            "- backend/models/autopilot.py — schema for `AutoPilotTaskRecord`\n"
            "- frontend/prisma/schema.prisma — Prisma mirror of the same\n"
            "- backend/api/execution.py — `POST /api/execute/queue/{id}/resume` handler\n\n"
            "**Acceptance:** root cause documented in this task's CodeBoard comment with file:line citations + "
            "either confirmation of hypothesis or revised hypothesis if data shows otherwise.\n\n"
            "**Dispatch via Task tool:** subagent_type=`python-pro`."
        ),
    },
    {
        "title": "[CB-2671 fix T2] Schema fix — confirm/add issueKey + issueTitle on AutoPilotTaskRecord (Prisma + SQLAlchemy)",
        "priority": "CRITICAL",
        "assignee": "python-pro",
        "desc": (
            "Based on T1 findings, ensure `AutoPilotTaskRecord` has both columns. If missing, add to "
            "Prisma schema + SQLAlchemy model + generate migration.\n\n"
            "**Acceptance:** both DB schemas have non-null `issueKey` (varchar) + `issueTitle` (text). "
            "Re-runnable migration committed.\n\n"
            "**Dispatch:** subagent_type=`python-pro`."
        ),
    },
    {
        "title": "[CB-2671 fix T3] Persistence fix — write through issueKey + issueTitle on every task save",
        "priority": "CRITICAL",
        "assignee": "python-pro",
        "desc": (
            "Wherever the autopilot service creates or updates a task row (autopilot_repository.py + "
            "autopilot_queue_service.py write paths), include issueKey + issueTitle resolved from the parent "
            "Issue table at write time.\n\n"
            "**Acceptance:** unit test creates a queue with N tasks, persists, re-reads from DB — every row "
            "has non-empty key + title.\n\n"
            "**Dispatch:** subagent_type=`python-pro`."
        ),
    },
    {
        "title": "[CB-2671 fix T4] Backfill migration — populate key+title on existing AutoPilotTaskRecord rows",
        "priority": "HIGH",
        "assignee": "python-pro",
        "desc": (
            "One-time idempotent backfill: JOIN AutoPilotTaskRecord with Issue ON issue_id, "
            "set key + title where currently empty. Script under "
            "`backend/scripts/backfill_autopilot_task_keys.py`.\n\n"
            "**Acceptance:** after run, zero rows with empty key/title in AutoPilotTaskRecord. "
            "Re-run is no-op. CB-2038's stuck queue (id `c778e8bb-d14b-400b-924a-0be835eefc28`) "
            "shows full key+title on every task.\n\n"
            "**Dispatch:** subagent_type=`python-pro`."
        ),
    },
    {
        "title": "[CB-2671 fix T5] Resume endpoint defensive fallback — re-fetch from Issue if key/title missing",
        "priority": "HIGH",
        "assignee": "python-pro",
        "desc": (
            "Belt-and-braces: in `POST /api/execute/queue/{id}/resume` and the resume loop in "
            "autopilot_queue_service, if a task's key or title is empty, re-fetch from Issue table by "
            "issue_id and persist before continuing. Logs a WARNING when this fallback fires.\n\n"
            "**Acceptance:** even with a partially-broken queue (legacy data), resume completes and "
            "fills missing fields rather than stalling silently.\n\n"
            "**Dispatch:** subagent_type=`python-pro`."
        ),
    },
    {
        "title": "[CB-2671 fix T6] Regression test — assert rehydrated queue has full key+title for every task",
        "priority": "HIGH",
        "assignee": "debugger",
        "desc": (
            "New pytest in `backend/tests/test_autopilot_persistence.py` (or new file): create queue, "
            "persist, instantiate fresh service, call `rehydrate_from_db()`, assert every task in the "
            "restored queue has non-empty `issue_key` AND non-empty `issue_title`.\n\n"
            "Second test: simulate partial corruption (manually NULL out a key in DB) → resume → "
            "assert fallback re-fetches and persists the key.\n\n"
            "**Acceptance:** 2+ tests green. Both fail before T2-T5 fix, pass after.\n\n"
            "**Dispatch:** subagent_type=`debugger`."
        ),
    },
    {
        "title": "[CB-2671 fix T7] Chrome QA — full e2e: queue → kill backend → restart → reload → Resume → verify advance",
        "priority": "HIGH",
        "assignee": "debugger",
        "desc": (
            "Real-world end-to-end via chrome-devtools-mcp: start a small autopilot queue (3-5 tasks), "
            "kill backend mid-flow, relaunch, reload `/codeboard`, observe recovery banner, press "
            "Resume, capture screenshots before/after, verify queue advances within 10s and Claude "
            "subprocess starts for the next pending task.\n\n"
            "**Acceptance:** screenshots filed under `docs/research/2026-05-08-cb-2671-resume-fix-*.png`; "
            "queue progresses correctly; pending tasks render with full title.\n\n"
            "**Dispatch:** subagent_type=`debugger` (uses chrome-devtools-mcp)."
        ),
    },
    {
        "title": "[CB-2671 fix T8] code-reviewer + security-auditor pass on full diff",
        "priority": "HIGH",
        "assignee": "code-reviewer",
        "desc": (
            "Standard 2-gate audit on the entire CB-2671 diff (T2-T5 + T6 tests). Run code-reviewer "
            "first; fix any HIGH/CRITICAL inline. Then security-auditor — focus on the resume endpoint "
            "(any new input surface) and the backfill script (does it leak/expose anything in logs?).\n\n"
            "**Acceptance:** zero CRITICAL/HIGH findings; MEDIUM/LOW filed as child BUGs.\n\n"
            "**Dispatch:** subagent_type=`code-reviewer` then `security-auditor` (parallel OK)."
        ),
    },
    {
        "title": "[CB-2671 fix T9] Roll CB-1951 back to IN_PROGRESS while fix in flight; CB-2671 → CWQ when fix green",
        "priority": "MEDIUM",
        "assignee": "jonny",
        "desc": (
            "Status hygiene: while T2-T8 are in flight, CB-1951 should not be CWQ (a CRITICAL regression "
            "exists). PATCH CB-1951 status → IN_PROGRESS. When T7 + T8 are green, mark CB-2671 → "
            "COMPLETED_WAITING_QA and CB-1951 back to COMPLETED_WAITING_QA. Eli does the final DONE per "
            "Rule 22.\n\n"
            "**Acceptance:** status flow respected; activity log shows the back-and-forth.\n\n"
            "**Dispatch:** Jonny — manual via PATCH script under `backend/scripts/codeboard/`."
        ),
    },
]


def main() -> None:
    bug_id = find_id(BUG_KEY)
    origin_id = find_id(ORIGIN_KEY)
    blocks_id = find_id(BLOCKS_KEY)
    print(f"{BUG_KEY} → {bug_id}")
    print(f"{ORIGIN_KEY} (origin) → {origin_id}")
    print(f"{BLOCKS_KEY} (blocks) → {blocks_id}")
    print()

    # 1. IssueLink CAUSED_BY origin feature
    print(f"Wiring IssueLink: {BUG_KEY} CAUSED_BY {ORIGIN_KEY} ...")
    try:
        r = http(
            "POST",
            f"/issues/{bug_id}/relations",
            {"toIssueId": origin_id, "linkType": "CAUSED_BY"},
        )
        print(f"  OK link id={r.get('id')}")
    except urllib.error.HTTPError:
        print("  (link may already exist; continuing)")

    # 2. IssueLink BLOCKS affected feature
    print(f"Wiring IssueLink: {BUG_KEY} BLOCKS {BLOCKS_KEY} ...")
    try:
        r = http(
            "POST",
            f"/issues/{bug_id}/relations",
            {"toIssueId": blocks_id, "linkType": "BLOCKS"},
        )
        print(f"  OK link id={r.get('id')}")
    except urllib.error.HTTPError:
        print("  (link may already exist; continuing)")

    print()
    print(f"Creating {len(FIX_TASKS)} fix TASK children under {BUG_KEY} ...")
    for t in FIX_TASKS:
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
    print()
    print(f"Done. {BUG_KEY} now wired with: 2 IssueLinks + {len(FIX_TASKS)} fix TASKs.")


if __name__ == "__main__":
    main()
