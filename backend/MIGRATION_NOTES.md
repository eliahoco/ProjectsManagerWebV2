# Migration Notes — ProjectsManagerWebV2 Backend

## CB-2794 — AutoPilot `autoResumeAttempts` column (2026-05-17)

### What changed

Single column added to `AutoPilotQueueRecord` so the circuit-breaker
counter survives backend restarts. Without persistence, the counter
resets to 0 on every reboot and the breaker is silently defeated.

```sql
ALTER TABLE "AutoPilotQueueRecord"
  ADD COLUMN "autoResumeAttempts" INTEGER NOT NULL DEFAULT 0;
```

Migration file:
`frontend/prisma/migrations/20260517000001_autopilot_auto_resume_attempts/migration.sql`

### Deploy

Same pattern as CB-2748 (Prisma `migrate deploy` may balk on dev.db
because of WAL locks held by running services and absent
`_prisma_migrations` table). Run manually:

```bash
sqlite3 frontend/prisma/dev.db < frontend/prisma/migrations/20260517000001_autopilot_auto_resume_attempts/migration.sql
```

Verify:

```bash
sqlite3 frontend/prisma/dev.db "PRAGMA table_info('AutoPilotQueueRecord');" | grep autoResumeAttempts
# expected: <n>|autoResumeAttempts|INTEGER|1|0|0
```

The `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT 0` form is safe on
SQLite — existing rows backfill to `0`. Migration is NOT idempotent;
running twice errors with "duplicate column name". Wrap in a
`PRAGMA table_info` pre-check if you re-deploy.

### Caller impact

- `save_queue` (`backend/utils/autopilot_repository.py`) now writes the
  column on both INSERT and UPDATE branches.
- `_record_to_queue` (`backend/services/autopilot_queue_service.py`)
  reads it via `getattr(record, "autoResumeAttempts", 0)` so partially
  migrated environments stay safe.

## CB-2784 — embed_all_issues `errors[]` shape change (2026-05-10)

### What changed

`POST /api/search/{project_id}/embed-all` previously returned two
distinct error-string formats in the `errors[]` array:

- non-raise failure branch: `"Failed to embed {issue.key}"`
- exception branch:        `"Error embedding {issue.key}: {str(e)}"`

The exception branch leaked raw `str(e)` text (SQL fragments, ChromaDB
internal paths, HTTP-level chromadb errors) on bypass paths from the
CB-2732 audit.

Both branches now emit the SAME redacted shape:

    "{issue.key}: embed_failed"

Detail goes to the server log only via
`logger.exception("embed_failed", extra={"issue_key", "project_id"})`.

### Caller impact

None inside this repo (frontend has no string-match on the legacy
`"Failed to embed"` / `"Error embedding"` prefixes). External callers
that string-match those prefixes must update to the new shape. The
`BatchEmbedResponse` Pydantic schema is unchanged.

## CB-2748 — AutoPilot Persistence Overhaul Schema Additions (2026-05-09)

### What changed

Six new columns added to existing AutoPilot tables in `frontend/prisma/dev.db`:

**AutoPilotQueueRecord:**
- `state TEXT` — machine-readable state tag (e.g., `"paused"`, `"waiting_reset"`)
- `stateReason TEXT` — human-readable reason for current state
- `lastCheckpointAt DATETIME` — timestamp of last successful state write
- `recoveryGeneration INTEGER DEFAULT 0 NOT NULL` — increments on each crash recovery

**AutoPilotTaskRecord:**
- `lastProgressAt DATETIME` — last time progress was reported for this task
- `subprocessPid INTEGER` — PID of the Claude Code CLI subprocess (for signal-based kill)

### Migration file

`backend/scripts/codeboard/2026-05-09-cb-2748-schema-migration.py`

Idempotent: uses PRAGMA table_info to check column existence before ALTER TABLE.
Running twice produces no error.

### Deploy procedure

```bash
cd backend
DATABASE_URL="sqlite:///$(pwd)/../frontend/prisma/dev.db" \
  ./venv/bin/python scripts/codeboard/2026-05-09-cb-2748-schema-migration.py
```

**Important:** The script defaults to `backend/data/codeboard.db` which is not
the live DB. Pass `DATABASE_URL` explicitly pointing to `frontend/prisma/dev.db`.

### Schema verification

```bash
sqlite3 frontend/prisma/dev.db "PRAGMA table_info('AutoPilotQueueRecord');" | grep -E "state|reason|checkpoint|generation"
sqlite3 frontend/prisma/dev.db "PRAGMA table_info('AutoPilotTaskRecord');" | grep -E "progress|pid"
```

### Rollback

All columns are nullable or have defaults. Rollback requires only reverting the
application code — the extra columns are harmless to old code. To fully clean them:

```sql
-- SQLite does not support DROP COLUMN in older versions.
-- The safe path is to restore from a pre-migration backup.
```

---

## CB-1951 — AutoPilot Queue Persistence (2026-05-03)

### What changed

Three new tables in `frontend/prisma/dev.db` (the canonical SQLite store):

- `AutoPilotQueueRecord` — durable queue state
- `AutoPilotTaskRecord` — durable per-task state
- `AutoPilotEvent` — append-only audit log

SQLAlchemy mirrors live in `backend/models/autopilot.py`. No changes to any
existing tables. All AutoPilot queues created from this release on are
write-through persisted; backend crashes no longer lose state.

### Migration files

- Prisma: `frontend/prisma/migrations/20260503000001_autopilot_queue_persistence/migration.sql`
- Applied via raw `sqlite3` rather than full `prisma migrate dev` because the
  DB predates Prisma migration history (~10 stale tables would have been
  dropped). See [§Long-term cleanup](#long-term-cleanup) below.

### Deploy procedure

1. **Stop AutoPilot first.** If a queue is mid-run, click Abort or wait for
   it to finish. Mid-deploy crashes are recoverable (the new persistence
   handles that), but cleaner to start from a quiescent state.
2. **Backup the DBs:**
   ```sh
   cp frontend/prisma/dev.db frontend/prisma/dev.db.pre-cb1951
   cp backend/data/codeboard.db backend/data/codeboard.db.pre-cb1951 2>/dev/null || true
   ```
3. **Pull + restart backend.** The FastAPI lifespan hook auto-applies any
   missing tables via `init_db()` and runs `rehydrate_from_db()`. First
   startup logs:
   ```
   [AutoPilot] Recovered 0 queues from crash (clean startup)
   ```
4. **Verify the new tables exist:**
   ```sh
   sqlite3 frontend/prisma/dev.db ".tables" | grep AutoPilot
   # Expected: AutoPilotQueueRecord  AutoPilotTaskRecord  AutoPilotEvent
   ```
5. **Smoke test:** start a small AutoPilot queue (1-2 tasks), watch
   `AutoPilotQueueRecord` row populate within seconds.

### Rollback

If anything looks off:

1. Stop backend.
2. Restore `dev.db.pre-cb1951` over `dev.db` (and `.db-shm`/`.db-wal` are
   safe to delete — SQLite will rebuild them).
3. Revert the backend code to before the CB-1951 commits.

The old in-memory queue behaviour is preserved in a feature flag
(`AUTOPILOT_PERSISTENCE_ENABLED` — see E10). Setting that flag to `false`
disables persistence at runtime without a code rollback.

### Backfill

There is **no backfill** for queues that were running before this release
— that data wasn't persisted, so it can't be reconstructed. The backfill
script at `backend/scripts/backfill_autopilot.py` is defensive: idempotent
and refuses to overwrite existing rows. Useful only if a future migration
needs to seed test data.

---

## Long-term cleanup

The `dev.db` predates Prisma's migration history. ~10 tables exist that
the current schema doesn't declare (e.g. `CommitLink`, `IssueGroup`,
`AgentProfile`, etc. — most are still actively used; the schema just
hasn't been re-baselined). A clean fix:

1. Empty migration history: `rm -rf frontend/prisma/migrations/`
2. Generate baseline migration: `npx prisma migrate diff
   --from-empty --to-schema-datamodel frontend/prisma/schema.prisma
   --script > frontend/prisma/migrations/20250101000000_baseline/migration.sql`
3. Mark applied: `npx prisma migrate resolve --applied
   20250101000000_baseline`
4. Future migrations work normally with `npx prisma migrate dev`.

This is **out of scope for CB-1951** — listed here so the next person
who hits a Prisma migrate friction has the recipe.

### Known schema test failures (pre-existing, not caused by CB-1951)

- `tests/test_qa_sequence.py::test_no_commit_inside_helper` — outdated test
  vs the current commit semantics in `reserve_qa_key_block` (CB-1853 fix).
- `tests/test_schema_validation.py::test_no_unexpected_tables` — outdated
  expected-tables list. Touched in this release for AutoPilot tables but
  the broader hygiene is a separate cleanup.
- `tests/test_schema_validation.py::test_issue_no_extra_columns` — same
  drift on the Issue model's `aiContext` column.
