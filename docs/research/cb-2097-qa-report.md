# CB-2097 — QA Regression Report

**Issue:** [QA] E3-4: maxPerIssue caps row count per issue
**Status (pre-QA):** IN_PROGRESS
**Status (post-QA):** COMPLETED_WAITING_QA
**Tester:** Jonny (VP R&D)
**Date:** 2026-05-07 (UTC)
**Environment:** localhost — backend `:8401`, SQLite (`backend/data/codeboard.db`)

## Acceptance Criteria

> Manual: create 25 summaries on one issue → set maxPerIssue=20 → trigger task → only newest 20 remain.

## Coverage Strategy

Two complementary verifications:

1. **Automated regression** — new pytest case at the literal acceptance values
   (`test_per_issue_cap_purges_25_to_20_with_default_cap`), so the
   25-rows / cap-20 contract is permanently guarded against drift.
2. **Live-DB trace** — runs `apply_retention` against the running backend's
   SQLite (`backend/data/codeboard.db`) using the same service import the
   asyncio loop uses (`app/main.py:200-242`). Verifies the production code
   path on production data, with sentinel rows isolated by a unique issue
   id and full cleanup on exit.

## Test 1 — Automated Regression

**Location:** `backend/tests/test_e3_full_regression.py::test_per_issue_cap_purges_25_to_20_with_default_cap`

| # | Action | Expected | Observed | Result |
|---|--------|----------|----------|--------|
| 1 | Set `retentionDays=10000` (age phase out of scope), `maxPerIssue=20` | settings persisted | persisted | PASS |
| 2 | Insert 25 rows on `issue-cap-25` with strictly-increasing `executedAt` (1-min spacing, newest = `r-00`, oldest = `r-24`) | 25 rows present | 25 rows present | PASS |
| 3 | Call `apply_retention(db)` | `(purged_by_age, purged_by_cap) = (0, 5)` | `(0, 5)` | PASS |
| 4 | Re-query rows ordered DESC | exactly `r-00..r-19` (newest 20) survive | `r-00..r-19` | **PASS — primary AC** |

**Run output:**
```
tests/test_e3_full_regression.py::test_per_issue_cap_purges_25_to_20_with_default_cap PASSED
```

**Full E3 + DocSettings suite:** `19 passed in 1.10s` — no regression
(previously 18 passed; the new literal-AC test is the only addition).

## Test 2 — Live-DB Trace

**Script:** `backend/scripts/regression/2026-05-07-cb2097-live-maxperissue.py`

Drives the live `backend/data/codeboard.db` through the same `apply_retention`
import the 6h asyncio loop runs. Sentinel `Project` + `Issue` + 25 summaries
are inserted, retention runs, results asserted, then everything is rolled
back manually (delete summaries → delete issue → delete project → restore
DocSettings). DocSettings are snapshotted at start and restored on exit, so
the live DocSettings row ends every run unchanged. `retentionDays` is pinned
to 10000 for the duration of the run so the per-age phase cannot fire and
mask a per-issue cap regression.

**Run output:**
```
[cb-2097] sentinel issueId = cb2097-trace-28bc52de-issue
[cb-2097] live DocSettings — retentionDays=90, maxPerIssue=20
[cb-2097] seeded sentinel project=cb2097-trace-28bc52de-proj issue=cb2097-trace-28bc52de-issue
[cb-2097] pinned DocSettings — retentionDays=10000, maxPerIssue=20
[cb-2097] inserted 25 sentinel summaries (1-min spacing)
[cb-2097] pre-condition ok — 25 sentinel rows present
[cb-2097] apply_retention → purged_by_age=0, purged_by_cap=5
[cb-2097] post-retention sentinel row count: 20
[cb-2097] surviving newest: ['cb2097-trace-28bc52de-r00', 'cb2097-trace-28bc52de-r01', 'cb2097-trace-28bc52de-r02'] ... oldest: ['cb2097-trace-28bc52de-r17', 'cb2097-trace-28bc52de-r18', 'cb2097-trace-28bc52de-r19']
[cb-2097] PASS — newest 20 rows survived, oldest 5 purged by per-issue cap
[cb-2097] cleanup ok: delete sentinel summaries
[cb-2097] cleanup ok: delete sentinel issue
[cb-2097] cleanup ok: delete sentinel project
[cb-2097] cleanup ok: restore DocSettings
[cb-2097] cleanup done — DocSettings target: retentionDays=90, maxPerIssue=20
```

| # | Live verification step | Expected | Observed | Result |
|---|------------------------|----------|----------|--------|
| 1 | Snapshot live DocSettings | retentionDays=90, maxPerIssue=20 | matches default | PASS |
| 2 | Seed sentinel Project + Issue (FK target) | both inserted | both inserted | PASS |
| 3 | Pin retentionDays=10000, maxPerIssue=20 | settings persisted | persisted | PASS |
| 4 | Insert 25 sentinel summaries (1-min spacing) | 25 rows present | 25 rows present | PASS |
| 5 | Run `apply_retention` against live DB | `(0, 5)` | `(0, 5)` | PASS |
| 6 | Re-query sentinel issueId rows DESC | exactly newest 20 (`r00..r19`) survive | `r00..r19` | **PASS — primary AC** |
| 7 | Cleanup: delete sentinel rows/issue/project, restore DocSettings | live DB returns to baseline | restored to retentionDays=90, maxPerIssue=20 | PASS |

## Code Path Trace

```
apply_retention(db)  [services/doc_settings_service.py:45]
  ├─ get_or_create_settings(db)               → DocSettings row (maxPerIssue=20)
  ├─ Phase 1: age purge (retentionDays=10000) → purged_by_age = 0
  └─ Phase 2: per-issue cap loop
       └─ for each distinct issueId (sentinel only):
            ├─ SELECT executedAt FROM "ExecutionSummary"
            │    WHERE issueId = ?
            │    ORDER BY executedAt DESC
            │    LIMIT 1 OFFSET 20                  → boundary row (r-19)
            └─ DELETE FROM "ExecutionSummary"
                 WHERE issueId = ?
                 AND executedAt <= ?                → purged_by_cap = 5

Operational schedule:
  app.main.process_doc_retention()  [app/main.py:200-242]
    ├─ asyncio.sleep(60s) on first pass
    └─ asyncio.sleep(6h) on every subsequent pass
```

The per-issue cap pass uses **single-bound-parameter** SQL (one
`LIMIT/OFFSET` sub-select to find the boundary `executedAt`, then
one `DELETE ... WHERE executedAt <= ?`) — no row-id list, no
`NOT IN (...)`, so SQLITE_MAX_VARIABLE_NUMBER cannot be tripped even
at the upper bound (`maxPerIssue=1000`). This is the CB-2122 (M1) /
CB-2124 (H2) hardening; same SQL exercised in test 1 (in-memory SQLite)
and test 2 (live SQLite), confirming the SQL is identical across
environments.

## Findings

- **AC met** — with `maxPerIssue=20`, inserting 25 rows on a single issue
  and running `apply_retention` purges exactly the 5 oldest rows; the
  newest 20 (by `executedAt DESC`) survive. Verified on both an isolated
  test SQLite and the live `codeboard.db`.
- **No silent failures** — service logs `DocSettings retention: purged N
  ExecutionSummary rows beyond per-issue cap (M)` on any non-zero cap
  purge; the loop catches and logs exceptions without tightening the
  retry cadence (`app/main.py:231-242`).
- **No data leak** — sentinel rows isolated by unique issueId, full cleanup
  on exit, DocSettings snapshot/restore on every run; the live `codeboard.db`
  is unchanged after the trace.
- **No SQL injection vector** — `apply_retention` uses bound parameters via
  SQLAlchemy core; the per-issue cap is a single LIMIT/OFFSET sub-select
  followed by a `<=` boundary delete (no string interpolation, no client-side
  row-id list).
- **No FK-orphan risk** — `ExecutionSummary.issueId` has FK to `Issue.id`,
  but retention deletes summaries (the dependent side), so no integrity
  constraint is violated.
- **Per-issue isolation preserved** — pre-existing test
  `test_retention_respects_per_issue_cap` already proves the cap fires
  per-issue independently (one issue at cap=2 with 5 rows purges 3, while
  a sibling issue with 1 row is untouched). Combined with the new literal-AC
  test, both shapes (single high-volume issue and multi-issue mix) are guarded.

## Evidence

- `backend/tests/test_e3_full_regression.py::test_per_issue_cap_purges_25_to_20_with_default_cap` (new)
- `backend/tests/test_e3_full_regression.py::test_retention_respects_per_issue_cap` (pre-existing)
- `backend/tests/test_doc_settings.py::test_apply_retention_caps_per_issue` (pre-existing)
- `backend/scripts/regression/2026-05-07-cb2097-live-maxperissue.py` (new)
- pytest run: `./venv/bin/python -m pytest tests/test_e3_full_regression.py tests/test_doc_settings.py -v` → 19 passed
- live trace: `./venv/bin/python scripts/regression/2026-05-07-cb2097-live-maxperissue.py` → PASS

## Verdict

**PASS — CB-2097 ready for Eli's manual QA → DONE.**
