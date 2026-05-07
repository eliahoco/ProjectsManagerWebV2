"""
Push CB-1951 (AutoPilot Pause-Resume + Crash Recovery) full hierarchy to CodeBoard
+ ~72 QA tasks to QA Board.

CB-1951 already exists as a FEATURE in BACKLOG. This script:
  1. Creates 10 EPICs + ~22 STORYs + ~33 TASKs + ~24 SUBTASKs under it
  2. Creates ~72 QA tasks linked to the FEATURE
  3. Saves the full id-map to backend/docs/cb-1951/id-map.json for the QA runner

Per Bible Rule 29: stored in scripts/codeboard/, NOT /tmp/ (cross-session collision risk).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
FEATURE_ID = "03f5c3a6-2ba1-4bd3-96b1-e55a81a3b977"  # CB-1951
LABEL = "cb-1951-autopilot-pause-resume"

ID_MAP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "docs", "cb-1951", "id-map.json"
)


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} on {method} {path}: {body_txt[:500]}")
        raise


def create_issue(title: str, desc: str, type_: str, priority: str,
                 parent_id: str | None = None, assignee: str | None = None) -> dict:
    body = {
        "title": title,
        "description": desc,
        "type": type_,
        "priority": priority,
        "reporter": "AI",
        "labels": LABEL,
    }
    if parent_id:
        body["parentId"] = parent_id
    if assignee:
        body["assignee"] = assignee
    return http("POST", f"/projects/{PROJECT_ID}/issues", body)


def create_qa_task(title: str, scenario: str, expected: str,
                   type_: str = "AUTOMATED", priority: str = "MEDIUM",
                   linked_issue_ids: list[str] | None = None) -> dict:
    body = {
        "title": title,
        "scenario": scenario,
        "expectedResult": expected,
        "type": type_,
        "priority": priority,
        "linkedIssueIds": linked_issue_ids or [FEATURE_ID],
    }
    return http("POST", f"/qa/projects/{PROJECT_ID}/tasks", body)


# ---------------------------------------------------------------------------
# Full hierarchy spec
# ---------------------------------------------------------------------------
# Format per epic:
#   ("E1", title, desc, agent, priority, [
#       ("E1.1", title, desc, agent, [
#           ("E1.1.1", title, desc, agent, [subtasks])
#       ])
#   ])

HIERARCHY = [
    ("E1", "Persistent Queue State", "Foundation: durable queue+task storage with write-through persistence. Replaces in-memory _queues dict.", "python-pro", "CRITICAL", [
        ("E1.1", "Schema design (Prisma + SQLAlchemy mirrors)", "AutoPilotQueueRecord, AutoPilotTaskRecord, AutoPilotEvent models with proper indexes.", "api-designer", [
            ("E1.1.1", "Add Prisma models to schema.prisma", "3 new models after WatchdogEvent (line 452+). Run prisma migrate dev --name autopilot_queue_persistence.", "typescript-pro", [
                ("E1.1.1.s1", "Define columns + indexes for 3 models", "id, projectId, featureId, status, currentIndex, config JSON, timestamps, FK relations, indexes (projectId,status) and (queueId,sequence).", "typescript-pro"),
                ("E1.1.1.s2", "Generate + apply Prisma migration", "npx prisma migrate dev --name autopilot_queue_persistence; verify dev.db row counts match pre-migration.", "typescript-pro"),
                ("E1.1.1.s3", "Regenerate Prisma client + commit migration files", "npx prisma generate; commit migration directory.", "typescript-pro"),
            ]),
            ("E1.1.2", "Mirror SQLAlchemy ORM models in backend/models/autopilot.py", "New file. camelCase column names matching Prisma. Register in models/__init__.py. Add Pydantic schemas in models/schemas.py.", "python-pro", [
                ("E1.1.2.s1", "ORM classes for 3 models", "AutoPilotQueueRecord, AutoPilotTaskRecord, AutoPilotEvent with proper relationships.", "python-pro"),
                ("E1.1.2.s2", "Register in models/__init__.py + Pydantic schemas", "Export classes; add request/response schemas.", "python-pro"),
            ]),
        ]),
        ("E1.2", "Repository layer (utils/autopilot_repository.py)", "save_queue / load_queue / load_active_queue / record_event helpers + unit tests.", "python-pro", [
            ("E1.2.1", "Implement save/load/record functions", "5 functions with type hints. Upsert AutoPilotQueueRecord + bulk-upsert task rows. Hydrate AutoPilotQueue dataclass.", "python-pro", []),
            ("E1.2.2", "Repository unit tests", "tests/test_autopilot_repository.py — 5+ cases (roundtrip, reload, ordering, terminal filter, event log).", "python-pro", []),
        ]),
        ("E1.3", "Wire write-through persistence into queue service", "Save on every state transition in autopilot_queue_service.py.", "python-pro", [
            ("E1.3.1", "Save in create_queue (line 198)", "After _queues[queue_id] = queue → call save_queue.", "python-pro", []),
            ("E1.3.2", "Save in _execute_task (line 398)", "Save before + after each task execution.", "python-pro", []),
            ("E1.3.3", "Save in _apply_success / _apply_failure (lines 564, 603)", "Save after status update including failure reason in event log.", "python-pro", []),
            ("E1.3.4", "Save in pause_queue / resume_queue / skip_current / abort_queue (lines 876-919)", "Save on every flag flip.", "python-pro", []),
            ("E1.3.5", "Save in _finalize_queue (line 715)", "Save terminal status before pruning.", "python-pro", []),
        ]),
    ]),
    ("E2", "Crash Recovery on Startup", "Rehydrate AutoPilot state from DB on backend startup; mark stale RUNNING tasks failed; gate auto-resume behind manual user action.", "python-pro", "CRITICAL", [
        ("E2.1", "Rehydration logic in queue service", "rehydrate_from_db() method that restores non-terminal queues; marks crashed RUNNING tasks failed; sets queue PAUSED(crash_recovery).", "python-pro", [
            ("E2.1.1", "Implement rehydrate_from_db()", "Load non-terminal queue records; reconstruct AutoPilotQueue dataclasses; populate _queues + _active_queue_id.", "python-pro", []),
            ("E2.1.2", "Mark stale RUNNING tasks as failed(crash_recovery)", "On rehydration, any task with status=running gets failed + reason=backend_crash_recovery.", "python-pro", []),
            ("E2.1.3", "Set queue → PAUSED with reason=crash_recovery", "Never auto-resume from a crash — require explicit user action.", "python-pro", []),
        ]),
        ("E2.2", "FastAPI lifespan integration", "Hook rehydration into app/main.py startup; log recovered queues at INFO.", "devops-engineer", [
            ("E2.2.1", "Wire into app/main.py lifespan", "After DB session factory ready, await autopilot_queue_service.rehydrate_from_db().", "devops-engineer", []),
            ("E2.2.2", "INFO log [AutoPilot] Recovered N queues from crash", "Surface in launch.sh output for visibility.", "devops-engineer", []),
        ]),
        ("E2.3", "Recovery status endpoint + frontend banner", "GET /api/execute/queue/recovery-status returns crash_recovery queues; AutoPilotFloatingBar shows amber banner with Resume/Skip/Abort.", "api-designer", [
            ("E2.3.1", "Implement GET /api/execute/queue/recovery-status", "Returns array of queues with pauseReason=crash_recovery and their last task state.", "python-pro", []),
            ("E2.3.2", "Frontend banner in AutoPilotFloatingBar.tsx", "Poll endpoint on mount; render amber banner when crash_recovery state detected.", "react-specialist", []),
        ]),
    ]),
    ("E3", "Token-Exhaustion Detection + Auto-Pause", "Detect Anthropic rate limits / quota exhaustion; auto-pause queue to WAITING_RESET; do not retry-loop.", "debugger", "HIGH", [
        ("E3.1", "Pattern audit + extension", "Review failure logs; extend TOKEN_EXHAUSTION_PATTERNS; parse stream-json error events.", "debugger", [
            ("E3.1.1", "Scan recent backend logs for failure modes", "debugger agent reviews data/codeboard.db Activity log + last 7 days backend logs.", "debugger", []),
            ("E3.1.2", "Extend TOKEN_EXHAUSTION_PATTERNS (line 69)", "Add documented patterns; commit fixture file with raw strings.", "python-pro", []),
            ("E3.1.3", "Parse stream-json error events", "Detect type=error + message.error.type=rate_limit_error in JSON stream.", "python-pro", []),
            ("E3.1.4", "8+ fixture-based unit tests", "tests/test_token_exhaustion_detection.py with real-failure fixtures.", "python-pro", []),
        ]),
        ("E3.2", "Reset-time extraction strengthening", "extract_reset_time (line 93) returns tz-aware datetime, parses ISO + AM/PM + retry-after.", "python-pro", [
            ("E3.2.1", "Refactor extract_reset_time to return datetime", "Currently returns str — change to tz-aware datetime; update callers.", "python-pro", []),
            ("E3.2.2", "Parse 6 timestamp formats", "ISO with tz, ISO without, AM/PM with date, AM/PM without date, retry-after seconds, retry-after http-date.", "python-pro", []),
            ("E3.2.3", "tests/test_reset_time_extraction.py", "6 format cases + 2 malformed cases.", "python-pro", []),
        ]),
        ("E3.3", "Auto-pause flow wiring", "When _apply_failure detects exhaustion, set queue WAITING_RESET, do NOT retry, do NOT advance to next task.", "python-pro", [
            ("E3.3.1", "Wire is_token_exhaustion into _apply_failure (line 603)", "Branch: if exhaustion → WAITING_RESET; else → existing retry logic.", "python-pro", []),
            ("E3.3.2", "Set queue.resetTime from extracted datetime", "Persist resetTime on queue record; emit auto_paused_token_exhaustion event.", "python-pro", []),
        ]),
    ]),
    ("E4", "Resume Flow (manual + scheduled auto-resume)", "Harden manual resume; add asyncio scheduled auto-resume after resetTime+60s; preflight checks before re-running.", "python-pro", "HIGH", [
        ("E4.1", "Manual resume hardening", "resume_queue clears resetTime/pauseReason; refuses if no active task; emits manual_resume event.", "python-pro", [
            ("E4.1.1", "Clear resetTime + pauseReason on resume", "Update resume_queue (line 886).", "python-pro", []),
            ("E4.1.2", "Refuse resume if no active task selected", "Return False + log warning instead of silent succeed.", "python-pro", []),
        ]),
        ("E4.2", "Scheduled auto-resume", "asyncio.create_task with sleep until resetTime+60s buffer; cancellable on manual resume / abort.", "python-pro", [
            ("E4.2.1", "_schedule_auto_resume(queue, reset_time) helper", "Computes delay; spawns task; stores handle in _resume_handles dict.", "python-pro", []),
            ("E4.2.2", "Cancellation on manual resume / abort", "Pop + cancel handle in resume_queue + abort_queue.", "python-pro", []),
            ("E4.2.3", "Re-schedule on rehydration if reset still in future", "rehydrate_from_db re-arms timers; fires immediately if reset already passed.", "python-pro", []),
        ]),
        ("E4.3", "Resume preflight checks", "Verify Claude CLI on PATH; re-fetch issue and skip if already CWQ/DONE.", "python-pro", [
            ("E4.3.1", "Verify Claude CLI binary on PATH", "shutil.which check; mark task failed with clear reason if missing.", "python-pro", []),
            ("E4.3.2", "Re-fetch issue, skip if already terminal", "If issue.status in (COMPLETED_WAITING_QA, DONE) → mark task completed and advance.", "python-pro", []),
        ]),
    ]),
    ("E5", "Frontend Pause/Resume UX", "AutoPilotFloatingBar renders new states (WAITING_RESET countdown, crash_recovery), Resume now button, SSE-driven toasts.", "react-specialist", "HIGH", [
        ("E5.1", "Status surface for new states", "Render WAITING_RESET with live countdown; crash_recovery banner; visual distinction (amber/blue/red).", "react-specialist", [
            ("E5.1.1", "Render WAITING_RESET with countdown", "Component shows resetTime - now ticker; updates every second.", "react-specialist", []),
            ("E5.1.2", "Render crash_recovery state with action buttons", "Resume / Skip current / Abort.", "react-specialist", []),
            ("E5.1.3", "Visual distinction for each state", "amber=waiting_reset, blue=running, red=crash_recovery, gray=manual_pause.", "react-specialist", []),
        ]),
        ("E5.2", "Resume now button + optimistic UI", "Wired to resumeAutoPilot; disables during request; reverts on error.", "react-specialist", [
            ("E5.2.1", "Add Resume now button", "Beside countdown, calls AutoPilotContext.resumeAutoPilot.", "react-specialist", []),
            ("E5.2.2", "Optimistic UI + error rollback", "Set state immediately; revert + toast error if API fails.", "react-specialist", []),
        ]),
        ("E5.3", "Toast notifications via SSE", "/api/execute/queue/events stream → sonner toasts on auto-pause / auto-resume.", "react-specialist", [
            ("E5.3.1", "SSE endpoint /api/execute/queue/events", "Emits AutoPilotEvent rows as Server-Sent Events; backend.", "api-designer", []),
            ("E5.3.2", "useAutoPilotEvents hook + toast wiring", "Subscribe; surface auto-pause/resume as sonner toasts.", "react-specialist", []),
        ]),
    ]),
    ("E6", "Telemetry & Observability", "Structured logging via _log_event helper; watchdog integration; /metrics endpoint + Settings tile.", "devops-engineer", "MEDIUM", [
        ("E6.1", "Structured logging helper", "_log_event(queue, type, **fields) writes to AutoPilotEvent + stdout in one call.", "python-pro", [
            ("E6.1.1", "Implement _log_event helper", "Single source of truth for event emission.", "python-pro", []),
            ("E6.1.2", "Replace ad-hoc log calls throughout service", "Find/replace existing logger calls with _log_event.", "python-pro", []),
        ]),
        ("E6.2", "Watchdog integration", "Write WatchdogEvent rows on AutoPilot recovery / auto-pause.", "devops-engineer", [
            ("E6.2.1", "Emit WatchdogEvent on rehydration", "type=autopilot_recovery with lost-task summary in payload.", "devops-engineer", []),
            ("E6.2.2", "Emit WatchdogEvent on token-exhaust auto-pause", "type=autopilot_token_exhaust.", "devops-engineer", []),
        ]),
        ("E6.3", "Metrics endpoint + Settings tile", "GET /api/execute/queue/metrics returns counts; Settings page tile renders live.", "fullstack-developer", [
            ("E6.3.1", "Backend /api/execute/queue/metrics", "Counts by state + 24h auto-pause count + avg reset wait.", "python-pro", []),
            ("E6.3.2", "Settings page metrics tile", "Lightweight component polling endpoint every 30s.", "react-specialist", []),
        ]),
    ]),
    ("E7", "Migration & Backfill", "Document deploy procedure; ship idempotent backfill script for safety.", "devops-engineer", "MEDIUM", [
        ("E7.1", "Migration procedure doc", "MIGRATION_NOTES.md section: stop AutoPilot before deploy → migrate → restart → verify empty active set.", "devops-engineer", [
            ("E7.1.1", "Write backend/MIGRATION_NOTES.md section", "Concrete step-by-step + rollback (restore .pre-1951 backup).", "devops-engineer", []),
        ]),
        ("E7.2", "Idempotent backfill script", "backend/scripts/backfill_autopilot.py: dry-run + apply modes; safe re-run.", "devops-engineer", [
            ("E7.2.1", "Implement backfill_autopilot.py", "Refuses to overwrite existing rows; --dry-run prints what would change.", "devops-engineer", []),
        ]),
    ]),
    ("E8", "Test Suite + QA Board Push", "~60 automated tests + 12 Chrome UI tests + 12 manual matrix items, pushed to QA Board with PASS/FAIL via runner.", "python-pro", "HIGH", [
        ("E8.1", "Backend unit tests", "Repository, persistence, detection, reset extraction, scheduler.", "python-pro", [
            ("E8.1.1", "tests/test_autopilot_repository.py", "5+ cases.", "python-pro", []),
            ("E8.1.2", "tests/test_autopilot_persistence.py", "Crash → rehydrate → state correctness.", "python-pro", []),
            ("E8.1.3", "tests/test_token_exhaustion_detection.py", "8+ fixtures.", "python-pro", []),
            ("E8.1.4", "tests/test_reset_time_extraction.py", "6 formats.", "python-pro", []),
            ("E8.1.5", "tests/test_auto_resume_scheduler.py", "Scheduling + cancellation + timing.", "python-pro", []),
        ]),
        ("E8.2", "Backend integration + chaos tests", "End-to-end queue lifecycle; SIGKILL chaos; CB-1952 cascade preserved.", "python-pro", [
            ("E8.2.1", "tests/test_autopilot_e2e.py — full lifecycle", "Pause → reset → auto-resume; crash → rehydrate; cascade preserved.", "python-pro", []),
            ("E8.2.2", "Chaos tests — SIGKILL during run", "Verify state recoverable, no DB corruption.", "python-pro", []),
        ]),
        ("E8.3", "Frontend tests", "Vitest for AutoPilotFloatingBar new states + countdown + resume click.", "react-specialist", [
            ("E8.3.1", "AutoPilotFloatingBar.test.tsx", "6+ component tests for new states.", "react-specialist", []),
            ("E8.3.2", "use-autopilot-events.test.tsx", "SSE subscription tests.", "react-specialist", []),
        ]),
        ("E8.4", "QA Board push + runner", "Push ~72 QA tasks; runner orchestrator runs them and PATCHes pass/fail.", "python-pro", [
            ("E8.4.1", "Push script (this script)", "scripts/codeboard/2026-05-03-cb-1951-push.py.", "python-pro", []),
            ("E8.4.2", "Runner orchestrator", "scripts/codeboard/cb-1951-qa-runner.py — runs suites, PATCHes results.", "python-pro", []),
            ("E8.4.3", "Chrome UI test recipes (12)", "YAML recipes for mcp__claude-in-chrome__* sequences.", "react-specialist", []),
            ("E8.4.4", "Manual QA matrix execution", "12 hands-on scenarios — me + you.", "fullstack-developer", []),
        ]),
    ]),
    ("E9", "Runbook & Documentation", "AUTOPILOT_RUNBOOK.md + CLAUDE.md update.", "devops-engineer", "MEDIUM", [
        ("E9.1", "Operational runbook", "Recovery procedures, SQL inspection queries, force-resume override.", "devops-engineer", [
            ("E9.1.1", "Write backend/docs/AUTOPILOT_RUNBOOK.md", "Backend crashed during AutoPilot, queue stuck WAITING_RESET, force resume override.", "devops-engineer", []),
        ]),
        ("E9.2", "CLAUDE.md update", "Document persistence model + link to runbook.", "devops-engineer", [
            ("E9.2.1", "Update CLAUDE.md AutoPilot section", "Architecture brief + runbook link.", "devops-engineer", []),
        ]),
    ]),
    ("E10", "Feature Flag Rollout", "AUTOPILOT_PERSISTENCE_ENABLED Setting + UI toggle; soak window.", "fullstack-developer", "MEDIUM", [
        ("E10.1", "Feature flag plumbing", "Setting record + Settings page toggle; queue reads flag once at create.", "fullstack-developer", [
            ("E10.1.1", "Add AUTOPILOT_PERSISTENCE_ENABLED Setting", "Default false initially; read at queue creation; snapshot to queue.config.", "fullstack-developer", []),
            ("E10.1.2", "Settings page toggle", "Toggle + descriptive copy + warning if active queue exists.", "react-specialist", []),
        ]),
        ("E10.2", "Soak + flag removal", "24h soak with flag ON; review AutoPilotEvent log daily; remove flag after 7 clean days.", "devops-engineer", [
            ("E10.2.1", "Soak window observation log", "Daily review checklist; file follow-up tickets for anomalies.", "devops-engineer", []),
            ("E10.2.2", "Remove flag after soak", "Final commit removing flag + UI toggle.", "fullstack-developer", []),
        ]),
    ]),
]


# ---------------------------------------------------------------------------
# QA tasks spec
# ---------------------------------------------------------------------------

QA_TASKS = [
    # AUTOMATED — repository unit tests (E8.1.1)
    ("QA-A01", "AUTOMATED", "HIGH", "Repository: save_queue roundtrip",
     "Run `pytest tests/test_autopilot_repository.py::test_save_queue_roundtrip -v`",
     "Test passes; queue persisted then reloaded matches original dataclass."),
    ("QA-A02", "AUTOMATED", "HIGH", "Repository: load_active_queue filters terminal",
     "Run `pytest tests/test_autopilot_repository.py::test_load_active_queue_filters_terminal -v`",
     "Test passes; only non-terminal queues are returned."),
    ("QA-A03", "AUTOMATED", "HIGH", "Repository: bulk task ordering preserved",
     "Run `pytest tests/test_autopilot_repository.py::test_task_ordering -v`",
     "Test passes; tasks reload in original sequence order."),
    ("QA-A04", "AUTOMATED", "MEDIUM", "Repository: record_event appends to log",
     "Run `pytest tests/test_autopilot_repository.py::test_record_event -v`",
     "Test passes; events appear in AutoPilotEvent in chronological order."),
    ("QA-A05", "AUTOMATED", "MEDIUM", "Repository: idempotent re-save",
     "Run `pytest tests/test_autopilot_repository.py::test_idempotent_save -v`",
     "Test passes; saving same queue twice does not create duplicate rows."),
    # Persistence + crash (E8.1.2)
    ("QA-A06", "AUTOMATED", "CRITICAL", "Persistence: write-through on every transition",
     "Run `pytest tests/test_autopilot_persistence.py::test_write_through -v`",
     "Test passes; DB row reflects in-memory state at every checkpoint."),
    ("QA-A07", "AUTOMATED", "CRITICAL", "Persistence: rehydrate marks RUNNING failed",
     "Run `pytest tests/test_autopilot_persistence.py::test_rehydrate_marks_running_failed -v`",
     "Test passes; stale RUNNING tasks become failed(crash_recovery) on rehydration."),
    ("QA-A08", "AUTOMATED", "CRITICAL", "Persistence: crash sets queue PAUSED(crash_recovery)",
     "Run `pytest tests/test_autopilot_persistence.py::test_crash_recovery_state -v`",
     "Test passes; queue ends up PAUSED with reason=crash_recovery."),
    ("QA-A09", "AUTOMATED", "HIGH", "Persistence: cache + DB stay consistent under rapid changes",
     "Run `pytest tests/test_autopilot_persistence.py::test_concurrent_persistence -v`",
     "Test passes; rapid status flips all persist; no lost writes."),
    # Token exhaustion detection (E8.1.3)
    ("QA-A10", "AUTOMATED", "HIGH", "Detection: 'out of extra usage' triggers exhaustion",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_pattern_out_of_extra_usage -v`",
     "Test passes; is_token_exhaustion returns True."),
    ("QA-A11", "AUTOMATED", "HIGH", "Detection: 'rate limit exceeded' triggers exhaustion",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_pattern_rate_limit -v`",
     "Test passes; is_token_exhaustion returns True."),
    ("QA-A12", "AUTOMATED", "HIGH", "Detection: 'credit balance is too low' triggers exhaustion",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_pattern_credit_low -v`",
     "Test passes; is_token_exhaustion returns True."),
    ("QA-A13", "AUTOMATED", "HIGH", "Detection: stream-json rate_limit_error event",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_stream_json_rate_limit -v`",
     "Test passes; structured JSON error parsed correctly."),
    ("QA-A14", "AUTOMATED", "MEDIUM", "Detection: ordinary exit_code=0 returns False",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_clean_exit_returns_false -v`",
     "Test passes; clean exit not flagged as exhaustion."),
    ("QA-A15", "AUTOMATED", "MEDIUM", "Detection: random non-quota error returns False",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_unrelated_error_returns_false -v`",
     "Test passes; e.g. 'permission denied' not flagged as exhaustion."),
    ("QA-A16", "AUTOMATED", "MEDIUM", "Detection: case-insensitive matching",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_case_insensitive -v`",
     "Test passes; mixed case patterns still match."),
    ("QA-A17", "AUTOMATED", "MEDIUM", "Detection: pattern at start vs end of output",
     "Run `pytest tests/test_token_exhaustion_detection.py::test_pattern_position -v`",
     "Test passes; position in output does not affect detection."),
    # Reset time extraction (E8.1.4)
    ("QA-A18", "AUTOMATED", "HIGH", "Reset extraction: ISO 8601 with tz",
     "Run `pytest tests/test_reset_time_extraction.py::test_iso_with_tz -v`",
     "Test passes; tz-aware datetime returned."),
    ("QA-A19", "AUTOMATED", "HIGH", "Reset extraction: ISO 8601 without tz",
     "Run `pytest tests/test_reset_time_extraction.py::test_iso_without_tz -v`",
     "Test passes; assumed UTC, returned tz-aware."),
    ("QA-A20", "AUTOMATED", "HIGH", "Reset extraction: AM/PM with date",
     "Run `pytest tests/test_reset_time_extraction.py::test_ampm_with_date -v`",
     "Test passes; today's date used, returned tz-aware."),
    ("QA-A21", "AUTOMATED", "HIGH", "Reset extraction: AM/PM without date",
     "Run `pytest tests/test_reset_time_extraction.py::test_ampm_no_date -v`",
     "Test passes; today's date inferred."),
    ("QA-A22", "AUTOMATED", "HIGH", "Reset extraction: retry-after seconds",
     "Run `pytest tests/test_reset_time_extraction.py::test_retry_after_seconds -v`",
     "Test passes; numeric seconds added to now()."),
    ("QA-A23", "AUTOMATED", "MEDIUM", "Reset extraction: malformed input returns None",
     "Run `pytest tests/test_reset_time_extraction.py::test_malformed_returns_none -v`",
     "Test passes; bad input returns None instead of raising."),
    # Auto-resume scheduler (E8.1.5)
    ("QA-A24", "AUTOMATED", "HIGH", "Scheduler: auto-resume fires at reset+60s",
     "Run `pytest tests/test_auto_resume_scheduler.py::test_fires_at_reset_plus_60 -v`",
     "Test passes; resume fired within 100ms tolerance of expected time."),
    ("QA-A25", "AUTOMATED", "HIGH", "Scheduler: cancellation on manual resume",
     "Run `pytest tests/test_auto_resume_scheduler.py::test_cancel_on_manual_resume -v`",
     "Test passes; pending timer cancelled; no double-resume."),
    ("QA-A26", "AUTOMATED", "HIGH", "Scheduler: cancellation on abort",
     "Run `pytest tests/test_auto_resume_scheduler.py::test_cancel_on_abort -v`",
     "Test passes; pending timer cancelled when queue aborted."),
    ("QA-A27", "AUTOMATED", "HIGH", "Scheduler: re-armed on rehydration if reset still future",
     "Run `pytest tests/test_auto_resume_scheduler.py::test_re_armed_on_rehydration -v`",
     "Test passes; new timer scheduled with correct remaining delay."),
    ("QA-A28", "AUTOMATED", "MEDIUM", "Scheduler: fires immediately if reset already passed on rehydration",
     "Run `pytest tests/test_auto_resume_scheduler.py::test_immediate_if_past -v`",
     "Test passes; resume fires within 100ms when resetTime in past."),
    # E2E + cascade (E8.2)
    ("QA-A29", "AUTOMATED", "CRITICAL", "E2E: pause → reset → auto-resume happy path",
     "Run `pytest tests/test_autopilot_e2e.py::test_pause_reset_resume_happy_path -v`",
     "Test passes; full lifecycle completes without manual intervention."),
    ("QA-A30", "AUTOMATED", "CRITICAL", "E2E: crash → rehydrate → manual resume",
     "Run `pytest tests/test_autopilot_e2e.py::test_crash_rehydrate_manual_resume -v`",
     "Test passes; user resume after crash recovery completes the queue."),
    ("QA-A31", "AUTOMATED", "CRITICAL", "E2E: token-exhaust paused queue does not advance",
     "Run `pytest tests/test_autopilot_e2e.py::test_no_advance_on_exhaust -v`",
     "Test passes; tasks after the failure are untouched until resume."),
    ("QA-A32", "AUTOMATED", "CRITICAL", "E2E: resume preflight skips already-CWQ tasks",
     "Run `pytest tests/test_autopilot_e2e.py::test_skip_already_cwq -v`",
     "Test passes; tasks whose issue is already CWQ get marked completed-skip."),
    ("QA-A33", "AUTOMATED", "HIGH", "E2E: abort during WAITING_RESET cancels timer",
     "Run `pytest tests/test_autopilot_e2e.py::test_abort_cancels_timer -v`",
     "Test passes; aborting during pause does not trigger auto-resume later."),
    # Regression — CB-1952 (E8.2)
    ("QA-A34", "AUTOMATED", "CRITICAL", "Regression: CB-1952 cascade does not demote CWQ parent",
     "Run `pytest tests/test_cascade_in_progress_guard.py -v`",
     "All 4 cases pass — CWQ parent never demoted by sibling activity."),
    ("QA-A35", "AUTOMATED", "CRITICAL", "Regression: full backend pytest suite green",
     "Run `pytest -q` in backend/",
     "0 failures across the entire backend test suite."),
    # Frontend (E8.3)
    ("QA-A36", "AUTOMATED", "HIGH", "Frontend: AutoPilotFloatingBar renders WAITING_RESET",
     "Run `npm test -- AutoPilotFloatingBar.test.tsx -t WAITING_RESET`",
     "Component test passes; countdown rendered with resetTime delta."),
    ("QA-A37", "AUTOMATED", "HIGH", "Frontend: AutoPilotFloatingBar renders crash_recovery",
     "Run `npm test -- AutoPilotFloatingBar.test.tsx -t crash_recovery`",
     "Component test passes; banner + Resume/Skip/Abort buttons rendered."),
    ("QA-A38", "AUTOMATED", "HIGH", "Frontend: Resume now button calls API",
     "Run `npm test -- AutoPilotFloatingBar.test.tsx -t resume_now_button`",
     "Component test passes; clicking button invokes resumeAutoPilot mutation."),
    ("QA-A39", "AUTOMATED", "MEDIUM", "Frontend: countdown ticks every second",
     "Run `npm test -- AutoPilotFloatingBar.test.tsx -t countdown_ticks`",
     "Component test passes; advance fake timers, countdown decreases."),
    ("QA-A40", "AUTOMATED", "MEDIUM", "Frontend: SSE event triggers toast",
     "Run `npm test -- use-autopilot-events.test.tsx -t toast_on_event`",
     "Hook test passes; sonner toast triggered on auto_paused event."),
    ("QA-A41", "AUTOMATED", "MEDIUM", "Frontend: full vitest suite green",
     "Run `npm test` in frontend/",
     "0 failures across the entire frontend test suite."),

    # CHROME UI tests (MANUAL — driven by mcp__claude-in-chrome__*)
    ("QA-C01", "MANUAL", "HIGH", "Chrome: floating bar renders RUNNING state correctly",
     "1. Start AutoPilot via /codeboard (any feature)\n2. mcp__claude-in-chrome__navigate http://localhost:3601/codeboard\n3. Snapshot DOM, assert blue floating bar visible with current task title",
     "Floating bar shows blue background, current task title, pause + abort buttons; no console errors."),
    ("QA-C02", "MANUAL", "HIGH", "Chrome: floating bar renders manual PAUSED state",
     "1. Start AutoPilot, click Pause\n2. Snapshot DOM, assert gray floating bar with Resume button",
     "Floating bar shows gray background, Resume button visible; no console errors."),
    ("QA-C03", "MANUAL", "CRITICAL", "Chrome: floating bar renders WAITING_RESET with countdown",
     "1. Force queue WAITING_RESET via API (POST with resetTime=now+90s)\n2. Navigate /codeboard\n3. Snapshot, assert amber bar with countdown text\n4. Wait 5s, snapshot again\n5. Assert countdown decreased",
     "Amber banner; 'Auto-resumes at HH:MM' visible; countdown ticks down each second; Resume now button enabled."),
    ("QA-C04", "MANUAL", "CRITICAL", "Chrome: crash_recovery banner after backend restart",
     "1. Start AutoPilot, kill backend mid-task (kill -9)\n2. Wait for watchdog restart\n3. Navigate /codeboard\n4. Snapshot, assert red crash_recovery banner",
     "Red banner with 'AutoPilot recovered after backend restart' + Resume / Skip / Abort buttons."),
    ("QA-C05", "MANUAL", "HIGH", "Chrome: Resume now button click resumes queue",
     "1. Force WAITING_RESET state\n2. Click Resume now via mcp__claude-in-chrome__click\n3. Read console, assert no errors\n4. Snapshot, assert state changes to RUNNING (blue bar)",
     "Click triggers POST resume; bar transitions to blue RUNNING within 2s; no console errors."),
    ("QA-C06", "MANUAL", "MEDIUM", "Chrome: Sonner toast on auto-pause",
     "1. Start AutoPilot with mock CLI returning rate-limit error\n2. Navigate /codeboard\n3. Wait for failure event\n4. Snapshot toast container, assert 'AutoPilot paused — token exhaustion' visible",
     "Toast appears in bottom-right within 3s of auto-pause event; auto-dismisses after 5s."),
    ("QA-C07", "MANUAL", "MEDIUM", "Chrome: Sonner toast on auto-resume",
     "1. Force WAITING_RESET with resetTime=now+10s\n2. Wait 75s (reset+60s buffer)\n3. Snapshot toast, assert 'AutoPilot auto-resumed' visible",
     "Toast appears at resetTime+60s; bar transitions to RUNNING."),
    ("QA-C08", "MANUAL", "MEDIUM", "Chrome: Settings toggle for AUTOPILOT_PERSISTENCE_ENABLED",
     "1. Navigate /settings\n2. Find AutoPilot Persistence toggle\n3. Click to disable\n4. Snapshot, assert toggle UI updates\n5. POST setting check via API",
     "Toggle reflects new state; setting persisted to DB; subsequent queues respect flag."),
    ("QA-C09", "MANUAL", "MEDIUM", "Chrome: Metrics tile shows live counts",
     "1. Navigate /settings\n2. Find AutoPilot Metrics tile\n3. Snapshot tile, capture counts\n4. Trigger queue state change via API\n5. Wait 30s, snapshot again, assert counts updated",
     "Tile shows running/paused/waiting_reset/completed/aborted counts; updates within 30s of state change."),
    ("QA-C10", "MANUAL", "MEDIUM", "Chrome: Watchdog page shows recovery event",
     "1. Trigger backend crash\n2. After restart, navigate /docker (watchdog page)\n3. Snapshot events list, assert latest entry is autopilot_recovery",
     "Recovery event visible at top of list with timestamp + lost-task summary."),
    ("QA-C11", "MANUAL", "HIGH", "Chrome regression: CodeBoard back-button after AutoPilot interactions",
     "1. Open CB-1951 detail\n2. Start AutoPilot\n3. Click back\n4. Click forward\n5. Click back again\nVerify URL state persists each step (CB-1921 regression)",
     "Back/forward navigation preserves filters + project + view; matches CB-1921 baseline."),
    ("QA-C12", "MANUAL", "HIGH", "Chrome: AutoPilot survives full page reload mid-queue",
     "1. Start AutoPilot\n2. Wait for first task to begin\n3. Hard-reload page (Cmd-Shift-R)\n4. Snapshot, assert floating bar reappears with same currentIndex",
     "Floating bar reappears within 2s; current task and progress match pre-reload state."),

    # MANUAL hands-on matrix (M01-M12)
    ("QA-M01", "MANUAL", "HIGH", "Manual: persistence visible in dev.db AutoPilotQueueRecord",
     "1. Start AutoPilot\n2. SQL: SELECT * FROM AutoPilotQueueRecord ORDER BY createdAt DESC LIMIT 5\n3. Verify row exists with current queue state",
     "Latest row matches in-memory state; updatedAt within last 30s."),
    ("QA-M02", "MANUAL", "HIGH", "Manual: pause + resume cycle persists",
     "1. Start AutoPilot\n2. Pause manually\n3. SQL: verify status=paused\n4. Resume\n5. SQL: verify status=running",
     "DB rows reflect both transitions within 1s of UI action."),
    ("QA-M03", "MANUAL", "CRITICAL", "Manual: backend kill mid-task → restart → crash banner",
     "1. Start AutoPilot\n2. kill -9 $(pgrep -f 'uvicorn.*8401')\n3. Wait for watchdog restart\n4. Open /codeboard, observe banner",
     "Backend recovers; banner appears within 5s of restart with crash_recovery state."),
    ("QA-M04", "MANUAL", "CRITICAL", "Manual: Resume from crash banner re-runs current task",
     "Continuing M03: click Resume button on crash_recovery banner",
     "Current task re-launches via terminal_service; floating bar transitions to RUNNING."),
    ("QA-M05", "MANUAL", "HIGH", "Manual: simulated rate-limit triggers WAITING_RESET",
     "1. Inject mock CLI binary that exits with 'rate limit exceeded'\n2. Start AutoPilot\n3. Wait for first task to fail",
     "Queue auto-pauses with WAITING_RESET; resetTime set; no advance to next task."),
    ("QA-M06", "MANUAL", "HIGH", "Manual: scheduled auto-resume fires at +60s buffer",
     "1. Force WAITING_RESET with resetTime=now+30s\n2. Watch logs",
     "[AutoPilot] auto_resume_fired log entry appears at resetTime+60s (±5s)."),
    ("QA-M07", "MANUAL", "MEDIUM", "Manual: Resume now button overrides timer",
     "1. Force WAITING_RESET with resetTime=now+5min\n2. Click Resume now",
     "Queue resumes immediately; pending auto-resume timer cancelled (verify logs)."),
    ("QA-M08", "MANUAL", "MEDIUM", "Manual: Abort during WAITING_RESET cancels timer",
     "1. Force WAITING_RESET\n2. Click Abort\n3. Wait past resetTime+60s",
     "No auto_resume_fired log; queue final status ABORTED."),
    ("QA-M09", "MANUAL", "MEDIUM", "Manual: Settings toggle disables persistence",
     "1. Toggle AUTOPILOT_PERSISTENCE_ENABLED off\n2. Start new queue\n3. SQL: verify NO new AutoPilotQueueRecord row",
     "With flag off, queue runs in-memory only; old behavior."),
    ("QA-M10", "MANUAL", "MEDIUM", "Manual: Watchdog WatchdogEvent for autopilot_recovery",
     "After M03 recovery: SQL: SELECT * FROM WatchdogEvent WHERE type='autopilot_recovery' ORDER BY createdAt DESC LIMIT 1",
     "Row exists with timestamp matching recovery; payload includes lost-task summary."),
    ("QA-M11", "MANUAL", "MEDIUM", "Manual: Metrics endpoint counts match observed state",
     "1. curl http://localhost:8401/api/execute/queue/metrics\n2. Compare counts to manual SQL query",
     "Counts in response match SELECT status, count(*) FROM AutoPilotQueueRecord GROUP BY status."),
    ("QA-M12", "MANUAL", "CRITICAL", "Manual: CB-1952 cascade behavior unchanged after CB-1951",
     "1. Set up tree: STORY=CWQ -> TASK_A=CWQ, TASK_B=running\n2. Force TASK_B failure during AutoPilot\n3. Verify STORY stays CWQ",
     "STORY status remains COMPLETED_WAITING_QA; TASK_A unchanged; only TASK_B reverted."),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    id_map: dict = {
        "feature": {"key": "CB-1951", "id": FEATURE_ID},
        "epics": {},
        "stories": {},
        "tasks": {},
        "subtasks": {},
        "qa_tasks": {},
    }

    for epic_label, epic_title, epic_desc, epic_agent, epic_priority, stories in HIERARCHY:
        print(f"\n=== {epic_label}: {epic_title}")
        epic = create_issue(
            f"[{epic_label}] {epic_title}",
            f"{epic_desc}\n\n**Plan label:** {epic_label}\n**Primary agent:** {epic_agent}",
            "EPIC", epic_priority, parent_id=FEATURE_ID, assignee=epic_agent,
        )
        id_map["epics"][epic_label] = {"key": epic["key"], "id": epic["id"], "title": epic_title}
        print(f"   {epic['key']}  EPIC")

        for story_label, story_title, story_desc, story_agent, tasks in stories:
            story = create_issue(
                f"[{story_label}] {story_title}",
                f"{story_desc}\n\n**Plan label:** {story_label}\n**Primary agent:** {story_agent}",
                "STORY", "HIGH" if epic_priority in ("CRITICAL", "HIGH") else "MEDIUM",
                parent_id=epic["id"], assignee=story_agent,
            )
            id_map["stories"][story_label] = {"key": story["key"], "id": story["id"], "title": story_title}
            print(f"     {story['key']}  STORY  {story_label}")

            for task_spec in tasks:
                # Spec is either (label, title, desc, agent, [subtasks]) for TASK
                # or (label, title, desc, agent) for SUBTASK without children
                if len(task_spec) == 5:
                    task_label, task_title, task_desc, task_agent, subtasks = task_spec
                else:
                    task_label, task_title, task_desc, task_agent = task_spec
                    subtasks = []

                task = create_issue(
                    f"[{task_label}] {task_title}",
                    f"{task_desc}\n\n**Plan label:** {task_label}\n**Primary agent:** {task_agent}",
                    "TASK", "MEDIUM",
                    parent_id=story["id"], assignee=task_agent,
                )
                id_map["tasks"][task_label] = {"key": task["key"], "id": task["id"], "title": task_title}
                print(f"       {task['key']}  TASK   {task_label}")

                for sub in subtasks:
                    sub_label, sub_title, sub_desc, sub_agent = sub
                    subtask = create_issue(
                        f"[{sub_label}] {sub_title}",
                        f"{sub_desc}\n\n**Plan label:** {sub_label}\n**Primary agent:** {sub_agent}",
                        "SUBTASK", "MEDIUM",
                        parent_id=task["id"], assignee=sub_agent,
                    )
                    id_map["subtasks"][sub_label] = {"key": subtask["key"], "id": subtask["id"], "title": sub_title}
                    print(f"         {subtask['key']}  SUB   {sub_label}")

    # QA tasks
    print("\n=== QA Tasks")
    for label, type_, priority, title, scenario, expected in QA_TASKS:
        try:
            qa = create_qa_task(title, scenario, expected, type_, priority)
            id_map["qa_tasks"][label] = {"key": qa["key"], "id": qa["id"], "title": title, "type": type_, "priority": priority}
            print(f"   {qa['key']}  {type_:9}  {label}  {title[:60]}")
        except Exception as e:
            print(f"   FAILED {label}: {e}")
            id_map["qa_tasks"][label] = {"error": str(e)}

    # Save id-map
    os.makedirs(os.path.dirname(ID_MAP_PATH), exist_ok=True)
    with open(ID_MAP_PATH, "w") as f:
        json.dump(id_map, f, indent=2)

    print(f"\n=== Saved id-map to {ID_MAP_PATH}")
    print(f"Hierarchy: {len(id_map['epics'])} EPICs, {len(id_map['stories'])} STORIES, "
          f"{len(id_map['tasks'])} TASKS, {len(id_map['subtasks'])} SUBTASKS")
    print(f"QA tasks: {len([v for v in id_map['qa_tasks'].values() if 'error' not in v])} created, "
          f"{len([v for v in id_map['qa_tasks'].values() if 'error' in v])} errors")


if __name__ == "__main__":
    sys.exit(main())
