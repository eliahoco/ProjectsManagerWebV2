# Bulletproof AutoPilot — Production Rollout Runbook

**Feature:** CB-2746 Bulletproof AutoPilot  
**Epic rollout:** CB-2755 (E9)  
**Date:** 2026-05-09  
**Status:** Ready for Eli's sign-off  

---

## Pre-Deploy Checklist

- [ ] All CB-2746 child epics (E1–E8) are COMPLETED_WAITING_QA or DONE
- [ ] Migration script confirmed idempotent (see step 3 below)
- [ ] Backend test suite: 1077 passed, 3 pre-existing stale failures (documented below)
- [ ] Frontend unit tests: 540 passed, 2 Playwright-in-Vitest misconfig failures (pre-existing)
- [ ] Backend health: `curl http://localhost:8401/health` returns `{"status":"healthy"}`
- [ ] Recovery-status enriched shape confirmed: `recoverable`, `zombie`, `auto_resume_pending` keys present
- [ ] No leftover feature-flag conditionals (BULLETPROOF_* / WORKSPACE_ENABLED) in production code
- [ ] WAL mode confirmed: `sqlite3 frontend/prisma/dev.db "PRAGMA journal_mode;"` returns `wal`

---

## Step-by-Step Deploy

### Step 1 — Backup

```bash
cp frontend/prisma/dev.db frontend/prisma/dev.db.pre-cb2746-$(date +%Y%m%d-%H%M%S)
```

The backend DB (`backend/data/codeboard.db`) is empty — all live data is in `frontend/prisma/dev.db`.

### Step 2 — Stop Backend

```bash
./stop.sh
# Or kill the FastAPI process directly:
pkill -f "uvicorn app.main:app" 2>/dev/null || true
```

### Step 3 — Run Migration (Idempotent)

The CB-2748 columns are already present in the live DB (applied via Prisma migration
at some point during development). Running the script is a no-op but confirms the schema:

```bash
cd backend
DATABASE_URL="sqlite:///$(pwd)/../frontend/prisma/dev.db" \
  ./venv/bin/python scripts/codeboard/2026-05-09-cb-2748-schema-migration.py
```

Expected output: 6 columns all reported as "already exists (skipped)".

**Note on migration script path resolution:** The script's default path resolution
targets `backend/data/codeboard.db` which is not the live DB. Always pass
`DATABASE_URL` explicitly as shown above, or the script will fail with
"no such table: AutoPilotQueueRecord".

### Step 4 — Start Backend

```bash
./launch.sh
```

Watch for clean startup log:
```
[AutoPilot] rehydrate_from_db: found N queue(s) to recover
```

If crash recovery activates, RUNNING tasks will appear as `failed(crash_recovery)` and
queues will pause with `pauseReason=crash_recovery`. This is correct behavior — see
the recovery procedure in `backend/docs/AUTOPILOT_RUNBOOK.md`.

### Step 5 — Smoke Tests

Run all in sequence:

```bash
# Health check
curl -s http://localhost:8401/health
# Expected: {"success":true,"status":"healthy","service":"ProjectsManagerWebV2 API"}

# Recovery status — must return enriched shape
curl -s http://localhost:8401/api/execute/queue/recovery-status | python3 -m json.tool | grep -E '"recoverable"|"zombie"|"auto_resume_pending"'
# Expected: all three keys present

# Metrics
curl -s http://localhost:8401/api/execute/queue/metrics
# Expected: JSON with pending/running/paused/waiting_reset/completed/aborted counts

# Full backend test suite (expect 3 pre-existing stale failures — see Known Limitations)
cd backend && PYTHONPATH=. ./venv/bin/pytest tests/ -q 2>&1 | tail -5
```

### Step 6 — Schema Verification

```bash
sqlite3 frontend/prisma/dev.db ".schema AutoPilotQueueRecord" | head -20
# Must include: state, stateReason, lastCheckpointAt, recoveryGeneration

sqlite3 frontend/prisma/dev.db ".schema AutoPilotTaskRecord" | head -15
# Must include: lastProgressAt, subprocessPid

sqlite3 frontend/prisma/dev.db "PRAGMA journal_mode;"
# Must return: wal
```

---

## 24-Hour Soak Protocol

Because the auto-resume timer fires only on token-exhaustion events (real or simulated),
the soak primarily monitors queue stability and crash recovery under normal usage.

### What to Monitor

1. **Queue state durability:** Start a multi-task AutoPilot queue. After each task
   completes, verify `AutoPilotTaskRecord.status` in the DB matches the UI state.

2. **Crash recovery:** Kill the backend mid-queue (`kill -9 <pid>`). Restart.
   Verify the queue appears in `/api/execute/queue/recovery-status` under `recoverable`
   and the UI shows a paused state with `pauseReason=crash_recovery`.

3. **Auto-resume timer:** If a task fails with a token exhaustion message, verify
   the queue transitions to `WAITING_RESET` and a `reset_time` is set. After the
   reset time passes, verify the queue auto-resumes (check metrics `autoResume24h`).

4. **Circuit breaker:** After 3 consecutive auto-resume attempts on the same queue,
   verify `pauseReason` downgrades to `manual` and the circuit breaker counter appears
   in metrics (`circuitBreakerTrips24h`).

5. **Log cleanliness:** `grep -E '(ERROR|CRITICAL|Traceback)' /tmp/backend*.log`
   should return only the known ChromaDB telemetry noise:
   ```
   chromadb.telemetry.product.posthog - ERROR - Failed to send telemetry event
   ```
   Any other ERROR/CRITICAL is a regression — file a child BUG under CB-2746.

### What Counts as a Regression

- Queue state lost across backend restart
- `recovery-status` endpoint missing `recoverable`/`zombie`/`auto_resume_pending` keys
- Token exhaustion detected but queue does NOT transition to `WAITING_RESET`
- Auto-resume fires more than 3 times without circuit breaker activating
- Any `CRITICAL` log line not attributable to ChromaDB telemetry

### Rollback Procedure

The CB-2748 schema changes are **additive only** (all new columns are nullable or
have defaults). Rollback does not require schema reversal:

1. Stop backend.
2. Restore the backup: `cp frontend/prisma/dev.db.pre-cb2746-<timestamp> frontend/prisma/dev.db`
   (also delete `.db-shm` and `.db-wal` — SQLite will rebuild them).
3. Revert code to the commit before CB-2746 work began.
4. Start backend.

If you want to keep the new schema but revert only the behavior (e.g., disable
crash recovery), set `AUTOPILOT_PERSISTENCE_ENABLED=false` in the environment
before starting the backend. This disables write-through persistence while keeping
the tables intact.

---

## Feature-Flag Audit

**Result: No BULLETPROOF_* or WORKSPACE_ENABLED flags found in production code.**

Search performed:
```bash
grep -rn "BULLETPROOF\|WORKSPACE_ENABLED" backend/ frontend/ docs/ \
  --include="*.py" --include="*.tsx" --include="*.ts" --include="*.md"
```

The only occurrences are in:
- `backend/scripts/codeboard/2026-05-07-workspace-master-data.py` — issue creation
  script (not production code)
- `backend/scripts/codeboard/2026-05-09-bulletproof-autopilot-push.py` — same
- `docs/plans/2026-05-07-ai-project-workspace-master-plan.md` — plan document

No feature-flag conditionals to remove from production code.

---

## Known Limitations (Backlog Items)

These are LOW/INFO severity items that do NOT block ship:

### Pre-Existing Stale Test Failures (3 tests)

All documented in `backend/MIGRATION_NOTES.md` under "Known schema test failures":

1. `test_qa_sequence.py::test_no_commit_inside_helper` — test asserts the QA key
   helper does NOT commit; production code was intentionally changed to commit
   immediately for concurrent-write safety (CB-1853). Test expectation is wrong,
   production behavior is correct.

2. `test_schema_validation.py::TestTableExistence::test_no_unexpected_tables` —
   `SQLALCHEMY_MANAGED_TABLES` allowlist in `schema_test_utils.py` was never updated
   to include `AgentProfile`, `AutoPilotQueueRecord`, `AutoPilotTaskRecord`,
   `AutoPilotEvent`, `DocSettings`, `ImplementationNote`, `PipelineExecution`,
   `PipelineStage`, `PipelineConfig`, `SkillProfile`, `park_events`. All are
   legitimate tables from prior epics. Fix: add them to the list + import the
   models so `Base.metadata.create_all` registers them.

3. `test_schema_validation.py::TestIssueSchema::test_issue_no_extra_columns` —
   `aiContext` column added to `Issue` model (prior epic) but not added to
   `EXPECTED_COLUMNS` dict in the test. Fix: add `"aiContext": {"notnull": False}`.

**Fix complexity:** Low. All three require only test file updates with no production
code changes. Eli must approve test file edits before they can be applied.

### Frontend E2E Playwright Tests in Vitest Run (2 test files)

`tests/regression/memory-growth.spec.ts` and `tests/regression/projects-latency.spec.ts`
use `@playwright/test` API but are picked up by the Vitest runner. They fail with
"Playwright Test did not expect test() to be called here." Run them separately via
`npx playwright test` instead. Pre-existing configuration issue.

### Migration Script Default Path

`backend/scripts/codeboard/2026-05-09-cb-2748-schema-migration.py` defaults to
`backend/data/codeboard.db` but the live DB is `frontend/prisma/dev.db` (the backend
`DATABASE_URL` points to the frontend DB). Always pass `DATABASE_URL` explicitly.
Recommend updating the script's `_resolve_db_path()` to read `app.config.settings`
at runtime for the correct default.

---

## CB-2746 Bulletproof AutoPilot — Full Feature Scope

| Epic | Description | Status |
|------|-------------|--------|
| E1 (CB-2747) | Schema & persistence foundation | CWQ |
| E2 (CB-2748) | 6-column schema overhaul (state, stateReason, lastCheckpointAt, recoveryGeneration, lastProgressAt, subprocessPid) | CWQ |
| E3 (CB-2749) | Broadened exhaustion detector (`detect_exhaustion_from_session`) | CWQ |
| E4 (CB-2750) | Circuit breaker (3 auto-resume attempts → manual) | CWQ |
| E5 (CB-2751) | Crash recovery rehydration on startup | CWQ |
| E6 (CB-2752) | Chaos test suite | CWQ |
| E7 (CB-2753) | Audit event log with redaction | CWQ |
| E8 (CB-2754) | Metrics endpoint + enriched recovery-status shape | CWQ |
| E9 (CB-2755) | Rollout gate (this runbook) | CWQ |
