"""
CB-2679 (T8) — code-reviewer pass on the CB-2671 fix diff.

Posts the review comment on CB-2679, files child BUGs under CB-2671 for any
CRITICAL/HIGH findings, posts a summary comment on CB-2671, and finally
either marks CB-2679 COMPLETED_WAITING_QA (no critical/high) or leaves it
IN_PROGRESS (with HIGH+ findings escalated as child BUGs).

Per Bible Rules 22/27/29: never DONE; review-helper scripts live here under
backend/scripts/codeboard/.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
CB_2679_ID = "d485cd37-db47-479f-b12a-1083964ecdd3"
CB_2671_ID = "fb7fca2d-790c-442d-a976-446ec40d3750"

LABELS = "🚀-bug,cb-1951-regression,review-finding"


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
# severity: CRITICAL | HIGH | MEDIUM | LOW | INFO
FINDINGS: list[dict] = [
    {
        "severity": "CRITICAL",
        "title": "Auto-resume timer path does not re-launch run_queue after rehydrate (CB-2676 fix incomplete)",
        "file": "backend/services/autopilot_queue_service.py",
        "line": 1995,
        "summary": (
            "`_fire_auto_resume()` calls `self.resume_queue(queue_id)` directly. "
            "That helper only flips state and sets `_pause_event` — it does NOT "
            "re-launch `run_queue` as a tracked asyncio task. The CB-2676 "
            "re-launch logic lives ONLY in `backend/api/execution.py:1232-1246` "
            "(the manual /resume HTTP endpoint).\n\n"
            "Failure scenario: backend crashes while a queue is in WAITING_RESET; "
            "rehydrate restores the queue, `rearm_auto_resume_timers()` arms a "
            "timer; the timer fires; `_fire_auto_resume` flips `_pause_event` "
            "and bumps status — but `queue._task` is still None (lost in crash) "
            "so no subprocess ever runs. Same root cause as CB-2676; same "
            "symptom — queue appears 'resumed' but is silently dead."
        ),
        "fix": (
            "Move the re-launch logic out of the API endpoint into a helper on "
            "the service, e.g. `_ensure_run_queue_task(queue)`, and call it from "
            "(a) the API resume endpoint, (b) `_fire_auto_resume`, and "
            "(c) `switch_model` (which has the same bug — line 2084)."
        ),
    },
    {
        "severity": "HIGH",
        "title": "switch_model() shares the same dead-resume bug after rehydrate",
        "file": "backend/services/autopilot_queue_service.py",
        "line": 2084,
        "summary": (
            "`switch_model()` calls `self.resume_queue(queue_id)` for "
            "PAUSED/WAITING_RESET queues, again without ensuring a live "
            "`run_queue` coroutine. After a crash + rehydrate, a user who "
            "switches model on a paused queue will see status flip to "
            "'resumed' but no tasks will actually execute."
        ),
        "fix": "Same as the CRITICAL — share an `_ensure_run_queue_task` helper.",
    },
    {
        "severity": "MEDIUM",
        "title": "Defensive fallback silently leaves empty key/title when Issue row is missing",
        "file": "backend/services/autopilot_queue_service.py",
        "line": 1085,
        "summary": (
            "The CB-2676 fallback in `_execute_task` only logs/persists when "
            "`_fb_issue` is truthy. If the Issue row was deleted (e.g. user "
            "manually deleted the issue while the queue was paused), the "
            "fallback hits `_fb_issue is None`, falls through with empty "
            "`task.issue_key`/`task.issue_title`, and the next branch (line "
            "1132) reports `Issue  not found in database` (double-space, "
            "blank key). The user sees a confusing audit log entry.\n\n"
            "Also, the `else` branch (Issue missing) emits no warning, so "
            "operators have no signal that this happened."
        ),
        "fix": (
            "Add an `else` branch that logs a warning with task.issue_id and "
            "fails the task with a clearer message: "
            "`f'Issue id={task.issue_id} (originally {task.issue_key or \"unknown\"}) not found in database'`."
        ),
    },
    {
        "severity": "MEDIUM",
        "title": "MIGRATION_NOTES.md has no entry for CB-2671/2673/2675/2676",
        "file": "backend/MIGRATION_NOTES.md",
        "line": 0,
        "summary": (
            "The MIGRATION_NOTES doc still only covers CB-1951. The new schema "
            "columns and the two helper scripts are NOT documented:\n"
            "  - apply_autopilot_task_keys.py (schema migration)\n"
            "  - backfill_autopilot_task_keys.py (data backfill)\n\n"
            "`init_db()` uses `Base.metadata.create_all` which only adds "
            "MISSING tables — it does NOT alter existing tables. So upgrading "
            "operators MUST run apply_autopilot_task_keys.py manually, but "
            "there is no documented procedure for that. Risk of upgraders "
            "hitting OperationalError 'no such column: AutoPilotTaskRecord.issueKey' "
            "the first time `save_queue` runs."
        ),
        "fix": (
            "Add a CB-2671 section to MIGRATION_NOTES.md with: (1) reason "
            "(persistence loses key/title), (2) deploy step ordering "
            "(stop AutoPilot → run apply_autopilot_task_keys.py → run "
            "backfill_autopilot_task_keys.py → restart backend), (3) a "
            "rollback note (the columns are nullable so downgrade is safe)."
        ),
    },
    {
        "severity": "MEDIUM",
        "title": "No regression tests added for CB-2671/2673/2676 despite docstring claim",
        "file": "backend/tests/test_autopilot_persistence.py",
        "line": 11,
        "summary": (
            "The module docstring (lines 11-15) claims regression tests are "
            "added for the schema fix, the defensive fallback, and the "
            "resume re-launch. The actual file ends at line 208 with only "
            "the original CB-1951 E2 tests — no new tests exist. This is a "
            "documentation drift / unfinished T6 deliverable.\n\n"
            "Risk: future refactors silently regress the issueKey/issueTitle "
            "persistence, the defensive fallback, or the run_queue re-launch."
        ),
        "fix": (
            "Add at minimum:\n"
            "  - test that `save_queue` writes issueKey/issueTitle on insert\n"
            "  - test that `save_queue` updates them on UPDATE only when present\n"
            "  - test that `_record_to_queue` reads them with correct fallback\n"
            "  - test that the CB-2676 defensive fallback re-fetches from Issue\n"
            "  - test that the resume endpoint re-launches run_queue when "
            "    `queue._task is None`"
        ),
    },
    {
        "severity": "LOW",
        "title": "save_queue UPDATE branch is partial-write: never clears existing key/title",
        "file": "backend/utils/autopilot_repository.py",
        "line": 162,
        "summary": (
            "`if task.issue_key: existing_task.issueKey = task.issue_key`. "
            "This is correct for the backfill use-case but means a future "
            "code change that legitimately wants to clear key/title (e.g. "
            "to recover from a bad backfill) will silently no-op. Worth a "
            "comment explaining the asymmetric semantics so a future reader "
            "doesn't 'simplify' it back to unconditional assignment and "
            "regress CB-2673."
        ),
        "fix": (
            "Add an inline note: `# Conditional update — never blank out a "
            "populated DB row from an in-memory task whose fields are still "
            "empty (covers crash-recovered tasks before the T5 fallback runs).`"
        ),
    },
    {
        "severity": "LOW",
        "title": "CB-2676 fallback opens 3 sequential SQLite sessions on the slow path",
        "file": "backend/services/autopilot_queue_service.py",
        "line": 1086,
        "summary": (
            "When the fallback fires, the flow is: (a) open session, fetch "
            "issue, close; (b) `_persist` opens new session, save_queue + "
            "record_event, close; (c) main path opens new session, fetch "
            "issue AGAIN. Three connections back-to-back where one would "
            "do. Cold-path so impact is small, but it's also unnecessary "
            "DB churn during the most fragile moment of the run."
        ),
        "fix": (
            "Reuse a single session: pass the open AsyncSession into "
            "save_queue/record_event from the same async-with block, and "
            "skip the second issue fetch by hoisting the issue object."
        ),
    },
    {
        "severity": "LOW",
        "title": "Logger format-string masks 0-length issue_title vs missing title",
        "file": "backend/services/autopilot_queue_service.py",
        "line": 1102,
        "summary": (
            "`task.issue_title[:40] if task.issue_title else \"\"` reduces "
            "both 'Issue had empty title in DB' and 'fallback wrote empty "
            "title because Issue.title was None' to the same blank string. "
            "Operators reading this log line cannot tell the two cases apart."
        ),
        "fix": (
            "Log `repr(task.issue_title)[:60]` instead — repr distinguishes "
            "`''` from `None` from `'Real Title…'`."
        ),
    },
    {
        "severity": "LOW",
        "title": "Resume endpoint short-circuits with success=true for already-running queues",
        "file": "backend/api/execution.py",
        "line": 1225,
        "summary": (
            "`autopilot_queue_service.resume_queue` returns True only when "
            "status is PAUSED/WAITING_RESET — fine. But when a second "
            "near-simultaneous resume call arrives after the first has "
            "completed (queue is now RUNNING with `_task` set), the service "
            "returns False → endpoint raises 400 'Cannot resume — not "
            "paused'. That's a confusing UX: the user clicked twice and "
            "the second click looks like an error.\n\n"
            "Not a correctness bug — the queue is already running — but "
            "worth distinguishing from the genuine 'queue not found' case."
        ),
        "fix": (
            "Either: (a) detect the already-running case and return a 200 "
            "with `{\"success\": true, \"status\": \"running\", \"already\": true}`, "
            "or (b) return a more specific 409 with a message like "
            "'Queue is already running'."
        ),
    },
    {
        "severity": "LOW",
        "title": "Migration script + backfill script do not validate Prisma schema parity",
        "file": "backend/utils/apply_autopilot_task_keys.py",
        "line": 38,
        "summary": (
            "apply_autopilot_task_keys.py adds the columns directly to "
            "frontend/prisma/dev.db via raw sqlite3. Prisma's migration "
            "history is bypassed, just like CB-1951 did. That's deliberate "
            "(the README explains why), but the consequence is: a future "
            "`prisma migrate dev` would either (a) re-issue ADD COLUMN and "
            "fail because columns already exist, or (b) silently skip and "
            "leave Prisma's _prisma_migrations table out of sync.\n\n"
            "The CB-1951 MIGRATION_NOTES has a 'Long-term cleanup' note "
            "covering this for the queue tables — there's no equivalent "
            "for the new columns."
        ),
        "fix": (
            "Generate a Prisma migration stub (even if applied via raw SQL) "
            "and place it under frontend/prisma/migrations/<timestamp>_cb_2673_autopilot_task_keys/migration.sql. "
            "Add a one-line update to MIGRATION_NOTES.md cleanup section."
        ),
    },
    {
        "severity": "INFO",
        "title": "Underscore-prefixed locals in fallback block are non-pythonic",
        "file": "backend/services/autopilot_queue_service.py",
        "line": 1086,
        "summary": (
            "`_fb_db`, `_fb_result`, `_fb_issue` use leading underscores to "
            "namespace fallback-only locals. Python convention reserves "
            "leading underscore for private module/class members, not "
            "function-local variables. They're inside an `async with` so "
            "scoping is already clear."
        ),
        "fix": (
            "Rename to `fb_db`, `fb_result`, `fb_issue` (or just "
            "`db`/`result`/`issue` — there's no shadowing inside this block)."
        ),
    },
    {
        "severity": "INFO",
        "title": "Backfill script emits one INFO log line per row — noisy on large DBs",
        "file": "backend/scripts/backfill_autopilot_task_keys.py",
        "line": 81,
        "summary": (
            "Per-row 'Backfilled task <id> → issueKey=…' is fine for a 10-row "
            "DB but will spam stdout for any operator who has ever run a "
            "many-task feature. Verify-step then prints every row again."
        ),
        "fix": (
            "Demote per-row line to logger.debug; keep the summary line at "
            "INFO. Add a `--verbose` flag if per-row output is needed for "
            "debugging."
        ),
    },
    {
        "severity": "INFO",
        "title": "_record_to_queue rebuilds queue with status taken from DB but _pause_event always set",
        "file": "backend/services/autopilot_queue_service.py",
        "line": 526,
        "summary": (
            "`AutoPilotQueue.__post_init__` calls `self._pause_event.set()` "
            "unconditionally, then `_record_to_queue` constructs a queue "
            "with `status=QueueStatus.PAUSED` (or WAITING_RESET). Result: "
            "rehydrated queue has status=PAUSED but `_pause_event.is_set() "
            "is True`. This is benign in current code (only the API resume "
            "endpoint can launch run_queue post-rehydrate, and resume_queue() "
            "would set the event anyway), but is a subtle invariant violation "
            "that will confuse the next developer who tries to launch "
            "run_queue from elsewhere."
        ),
        "fix": (
            "After constructing the queue in `_record_to_queue`, if "
            "qstatus in (PAUSED, WAITING_RESET): `queue._pause_event.clear()`. "
            "Then `run_queue` can be safely launched without a prior "
            "resume_queue call (e.g. from a future test or an admin "
            "tool). Couples nicely with the CRITICAL fix above."
        ),
    },
]


def post(url: str, payload: dict, method: str = "POST") -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if not data:
                return {}
            return json.loads(data)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {method} {url}: {e.read().decode()[:300]}")
        raise


def add_comment(issue_id: str, content: str, author: str = "code-reviewer") -> dict:
    return post(
        f"{API}/issues/{issue_id}/comments",
        {"author": author, "content": content},
    )


def patch_issue(issue_id: str, fields: dict) -> dict:
    return post(f"{API}/issues/issue/{issue_id}", fields, method="PATCH")


def create_child_bug(parent_id: str, finding: dict) -> dict:
    title = f"[CB-2671 review] {finding['severity']}: {finding['title']}"
    description = (
        f"**Severity:** {finding['severity']}\n"
        f"**File:** `{finding['file']}`"
        + (f":{finding['line']}" if finding.get('line') else "")
        + "\n\n"
        f"### Summary\n{finding['summary']}\n\n"
        f"### Suggested fix\n{finding['fix']}\n\n"
        f"_Filed by code-reviewer agent during CB-2679 (T8) review pass on the CB-2671 fix._"
    )
    priority = "CRITICAL" if finding["severity"] == "CRITICAL" else "HIGH"
    return post(
        f"{API}/projects/{PROJECT_ID}/issues",
        {
            "title": title[:500],
            "description": description,
            "type": "BUG",
            "status": "BACKLOG",
            "priority": priority,
            "parentId": parent_id,
            "reporter": "AI",
            "assignee": "python-pro",
            "labels": LABELS,
        },
    )


def severity_buckets() -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {
        "CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [], "INFO": [],
    }
    for f in FINDINGS:
        buckets[f["severity"]].append(f)
    return buckets


def render_review_comment(buckets: dict[str, list[dict]]) -> str:
    lines: list[str] = []
    lines.append("**Code-reviewer pass on CB-2671 fix diff**")
    lines.append("")
    lines.append("Scope: T1-T5 by python-pro — schema migration, repo persistence,")
    lines.append("rehydration read, defensive fallback, resume endpoint relaunch.")
    lines.append("")
    lines.append(f"CRITICAL findings: {len(buckets['CRITICAL'])}")
    lines.append(f"HIGH findings: {len(buckets['HIGH'])}")
    lines.append(f"MEDIUM findings: {len(buckets['MEDIUM'])}")
    lines.append(f"LOW findings: {len(buckets['LOW'])}")
    lines.append(f"INFO: {len(buckets['INFO'])}")
    lines.append("")
    lines.append("---")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
        if not buckets[sev]:
            continue
        lines.append("")
        lines.append(f"## {sev}")
        for i, f in enumerate(buckets[sev], 1):
            lines.append("")
            loc = f["file"] + (f":{f['line']}" if f.get("line") else "")
            lines.append(f"### [{sev}-{i}] {f['title']}")
            lines.append(f"**Location:** `{loc}`")
            lines.append("")
            lines.append(f"**What's wrong:** {f['summary']}")
            lines.append("")
            lines.append(f"**Suggested fix:** {f['fix']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Note: a security-auditor agent ran in parallel on the same diff; "
        "this review focuses on correctness, race conditions, and idiomatic code."
    )
    return "\n".join(lines)


def render_parent_summary(buckets: dict[str, list[dict]], child_keys: list[str]) -> str:
    lines: list[str] = []
    lines.append("**CB-2671 — code review summary (CB-2679 / T8)**")
    lines.append("")
    lines.append(
        f"code-reviewer found {len(buckets['CRITICAL'])} CRITICAL + "
        f"{len(buckets['HIGH'])} HIGH issues that must be resolved before "
        "this fix can ship."
    )
    lines.append("")
    if buckets["CRITICAL"]:
        lines.append("## CRITICAL (filed as child BUGs)")
        for f in buckets["CRITICAL"]:
            lines.append(f"- {f['title']}")
        lines.append("")
    if buckets["HIGH"]:
        lines.append("## HIGH (filed as child BUGs)")
        for f in buckets["HIGH"]:
            lines.append(f"- {f['title']}")
        lines.append("")
    if child_keys:
        lines.append(f"Child issues filed: {', '.join(child_keys)}")
    lines.append("")
    lines.append(
        f"Plus {len(buckets['MEDIUM'])} MEDIUM, {len(buckets['LOW'])} LOW, "
        f"{len(buckets['INFO'])} INFO findings — captured in the CB-2679 "
        "review comment for the implementer."
    )
    lines.append("")
    lines.append(
        "Per the global rule: CB-2679 stays IN_PROGRESS until the "
        "CRITICAL/HIGH children are closed."
    )
    return "\n".join(lines)


def main() -> None:
    buckets = severity_buckets()

    # 1. Post the structured review comment on CB-2679
    comment = render_review_comment(buckets)
    add_comment(CB_2679_ID, comment)
    print(f"Posted review comment on CB-2679 ({len(comment)} chars).")

    has_blocking = bool(buckets["CRITICAL"]) or bool(buckets["HIGH"])
    child_keys: list[str] = []

    if has_blocking:
        # 2. File child BUGs under CB-2671 for each CRITICAL/HIGH finding
        for f in buckets["CRITICAL"] + buckets["HIGH"]:
            child = create_child_bug(CB_2671_ID, f)
            ck = child.get("key") or child.get("id", "(unknown)")
            child_keys.append(ck)
            print(f"  Filed {ck} for: {f['title']}")

        # 3. Summary comment on CB-2671
        parent_summary = render_parent_summary(buckets, child_keys)
        add_comment(CB_2671_ID, parent_summary)
        print(f"Posted summary comment on CB-2671 ({len(parent_summary)} chars).")

        # 4. Leave CB-2679 IN_PROGRESS (per the rules)
        print("CB-2679 left IN_PROGRESS due to CRITICAL/HIGH findings.")
    else:
        # No blocking findings — mark CB-2679 COMPLETED_WAITING_QA
        patch_issue(CB_2679_ID, {"status": "COMPLETED_WAITING_QA"})
        print("CB-2679 → COMPLETED_WAITING_QA (no blocking findings).")


if __name__ == "__main__":
    main()
