# CB-2096 — QA Regression Report

**Issue:** [QA] E3-3: Retention purges ExecutionSummary older than retentionDays
**Status (pre-QA):** IN_PROGRESS
**Status (post-QA):** COMPLETED_WAITING_QA
**Tester:** Jonny (VP R&D)
**Date:** 2026-05-07 (UTC)
**Environment:** localhost — backend `:8401`, SQLite (`backend/data/codeboard.db`)

## Acceptance Criteria

> Manual: insert old row (executedAt = now - 100d) → set retentionDays=90 → trigger task → row gone.

## Coverage Strategy

Two complementary verifications:

1. **Automated regression** — new pytest case at the literal acceptance values
   (`test_retention_purges_100d_row_with_default_90d_window`), so the
   100-day / 90-day purge contract is permanently guarded against drift.
2. **Live-DB trace** — runs `apply_retention` against the running backend's
   SQLite (`backend/data/codeboard.db`) using the same service import the
   asyncio loop uses (`app/main.py:200-242`). Verifies the production code
   path on production data, with sentinel rows isolated by a unique issue
   id and full cleanup on exit.

## Test 1 — Automated Regression

**Location:** `backend/tests/test_e3_full_regression.py::test_retention_purges_100d_row_with_default_90d_window`

| # | Action | Expected | Observed | Result |
|---|--------|----------|----------|--------|
| 1 | Set `retentionDays=90`, `maxPerIssue=1000` (cap out of scope) | settings persisted | persisted | PASS |
| 2 | Insert row `old-100d` with `executedAt = now - 100d` | row exists | row exists | PASS |
| 3 | Insert control row `fresh-1d` with `executedAt = now - 1d` | row exists | row exists | PASS |
| 4 | Call `apply_retention(db)` | `(purged_by_age, purged_by_cap) = (1, 0)` | `(1, 0)` | PASS |
| 5 | Re-query ExecutionSummary | only `fresh-1d` survives | `{fresh-1d}` | **PASS — primary AC** |

**Run output:**
```
tests/test_e3_full_regression.py::test_retention_purges_100d_row_with_default_90d_window
DocSettings retention: purged 1 ExecutionSummary rows older than 90 days
PASSED
```

**Full E3 + DocSettings suite:** `18 passed in 0.97s` — no regression.

## Test 2 — Live-DB Trace

**Script:** `backend/scripts/regression/2026-05-07-cb2096-live-retention.py`

Drives the live `backend/data/codeboard.db` through the same `apply_retention`
import the 6h asyncio loop runs. Sentinel `Project` + `Issue` + summaries
are inserted, retention runs, results asserted, then everything is rolled
back manually (delete summaries → delete issue → delete project → restore
DocSettings). DocSettings are snapshotted at start and restored on exit, so
the live DocSettings row ends every run unchanged.

**Run output:**
```
[cb-2096] sentinel issueId = cb2096-trace-730acd61
[cb-2096] live DocSettings — retentionDays=90, maxPerIssue=20
[cb-2096] seeded sentinel project=cb2096-trace-730acd61-proj issue=cb2096-trace-730acd61-issue
[cb-2096] inserted: old (now - 100d), fresh (now - 1d)
[cb-2096] apply_retention → purged_by_age=1, purged_by_cap=0
[cb-2096] post-retention sentinel rows: {'cb2096-trace-730acd61-fresh'}
[cb-2096] PASS — 100-day-old row purged, 1-day-old row survived
[cb-2096] cleanup: removed sentinel rows + issue + project, restored retentionDays=90, maxPerIssue=20
```

| # | Live verification step | Expected | Observed | Result |
|---|------------------------|----------|----------|--------|
| 1 | Snapshot live DocSettings | retentionDays=90, maxPerIssue=20 | matches default | PASS |
| 2 | Seed sentinel Project + Issue (FK target) | both inserted | both inserted | PASS |
| 3 | Insert 100d-old + 1d-fresh ExecutionSummary | both inserted | both inserted | PASS |
| 4 | Run `apply_retention` against live DB | `(1, 0)` | `(1, 0)` | PASS |
| 5 | Re-query sentinel issueId rows | only fresh survives | `{fresh}` | **PASS — primary AC** |
| 6 | Cleanup: delete sentinel rows/issue/project, restore DocSettings | live DB returns to baseline | restored | PASS |

## Code Path Trace

```
apply_retention(db)  [services/doc_settings_service.py:45]
  ├─ get_or_create_settings(db)               → DocSettings row (retentionDays=90)
  ├─ cutoff = now - timedelta(days=90)
  ├─ DELETE FROM "ExecutionSummary"
  │       WHERE "executedAt" < cutoff          → purged_by_age = 1
  └─ per-issue cap loop (maxPerIssue=1000)     → purged_by_cap = 0

Operational schedule:
  app.main.process_doc_retention()  [app/main.py:200-242]
    ├─ asyncio.sleep(60s) on first pass
    └─ asyncio.sleep(6h) on every subsequent pass
```

The retention SQL is a parameter-bound `DELETE ... WHERE executedAt < ?`
— no string interpolation, no row-id list, no SQLITE_MAX_VARIABLE_NUMBER
exposure (the latter applies only to the per-issue cap pass, addressed
in CB-2122 / CB-2124). Same SQL exercised in test 1 (in-memory SQLite)
and test 2 (live SQLite), confirming the SQL is identical across
environments.

## Findings

- **AC met** — `executedAt < (now - retentionDays·days)` rows are deleted on
  every retention pass; younger rows are preserved. Verified on both an
  isolated test SQLite and the live `codeboard.db`.
- **No silent failures** — service logs `DocSettings retention: purged N
  ExecutionSummary rows older than D days` on any non-zero purge; the loop
  catches and logs exceptions without tightening the retry cadence
  (`app/main.py:231-242`).
- **No data leak** — sentinel rows isolated by unique issueId, full cleanup
  on exit, DocSettings snapshot/restore on every run; the live `codeboard.db`
  is unchanged after the trace.
- **No SQL injection vector** — `apply_retention` uses bound parameters via
  SQLAlchemy core; the cutoff is a Python `datetime`, the per-issue cap is
  a single LIMIT/OFFSET sub-select followed by a `<=` boundary delete.
- **No FK-orphan risk** — `ExecutionSummary.issueId` has FK to `Issue.id`,
  but retention deletes summaries (the dependent side), so no integrity
  constraint is violated.

## Evidence

- `backend/tests/test_e3_full_regression.py::test_retention_purges_100d_row_with_default_90d_window`
- `backend/scripts/regression/2026-05-07-cb2096-live-retention.py`
- pytest run: `./venv/bin/python -m pytest tests/test_e3_full_regression.py tests/test_doc_settings.py -v` → 18 passed
- live trace: `./venv/bin/python scripts/regression/2026-05-07-cb2096-live-retention.py` → PASS

## Verdict

**PASS — CB-2096 ready for Eli's manual QA → DONE.**
