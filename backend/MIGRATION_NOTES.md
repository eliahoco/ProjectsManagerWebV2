# Migration Notes — ProjectsManagerWebV2 Backend

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
