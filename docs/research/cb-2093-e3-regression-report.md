# CB-2093 — T3.3.4: E3 Full Regression Report

**Status:** COMPLETED_WAITING_QA
**Author:** Jonny (VP R&D)
**Date:** 2026-05-07
**Parent:** CB-2089 (S3.3) → CB-2078 (E3) → CB-2038 (Documentation Surface FEATURE)

## Scope

End-to-end regression for the E3 documentation-settings panel. Three scenarios from the task brief, all driven through the production code path (`app.main._process_completion_for_session` and `services.doc_settings_service.apply_retention`):

| # | Scenario | Production guarantee verified |
|---|----------|-------------------------------|
| a | `autoGenerate=False` → exec → no summary | Doc-gen hook is gated on `DocSettings.autoGenerate`; primary completion (status flip) still runs |
| b | `autoGenerate=True` → exec → summary    | Hook calls `documentation_generator.generate_from_execution`; exactly one `ExecutionSummary` row persists |
| c | retention purges                        | `apply_retention` deletes by `retentionDays` and respects `maxPerIssue` cap |

Spec note for (c): the public PATCH endpoint enforces `retentionDays >= 1` (Pydantic). The test sets `retentionDays=1` and ages rows to 5 days — exercises the same SQL DELETE the operational retention loop runs every 6h, while staying within the publicly representable range. A `retentionDays=0` test would only validate the model layer (which has no lower bound) and bypass the user-facing surface, so the chosen value is the right substitute.

## Artifact

`backend/tests/test_e3_full_regression.py` — 4 tests, 0.36s wall, all green.

```
tests/test_e3_full_regression.py::test_autogenerate_off_skips_summary_but_still_completes PASSED
tests/test_e3_full_regression.py::test_autogenerate_on_creates_one_summary             PASSED
tests/test_e3_full_regression.py::test_retention_purges_old_rows                       PASSED
tests/test_e3_full_regression.py::test_retention_respects_per_issue_cap                PASSED
============================== 4 passed in 0.36s ===============================
```

Production log lines emitted during the run prove the right code paths fired:

```
[AUTO-COMPLETE] Marked CB-9999 as COMPLETED_WAITING_QA after successful execution
doc-gen skipped for CB-9999 (autoGenerate=False)
Generated ExecutionSummary id=… for issue=CB-9998 (files=0, +None/-None)
DocSettings retention: purged 3 ExecutionSummary rows older than 1 days
DocSettings retention: purged 3 ExecutionSummary rows beyond per-issue cap (2)
```

## Broader regression — adjacent suites

Ran the full doc/E3 cluster to confirm the new test does not destabilise neighbours:

```
pytest tests/test_doc_settings.py \
       tests/test_completion_doc_hook.py \
       tests/test_documentation_api.py \
       tests/test_documentation_generator_parser.py \
       tests/test_documentation_generator_git_helpers.py \
       tests/test_e3_full_regression.py
============================= 129 passed in 20.93s =============================
```

## Audit gates

Both passed with no CRITICAL/HIGH findings.

**code-reviewer (MEDIUM/LOW only):**
- Acknowledged scenario (b) gate test is symmetric with (a). No false-positive risk.
- LOW: unused imports + redundant manual singleton restore. **Fixed.**
- INFO: parallel-test-safe (own tmpdir + engine per test); timezone-safe (UTC throughout); schema-safe (ORM, not raw SQL).

**security-auditor (LOW/INFO only):**
- INFO: `tempfile.mkdtemp` + `try/finally` rmtree → no leak.
- INFO: `monkeypatch.setattr` restores singletons even on test failure → no cross-suite contamination.
- INFO: production DB isolation confirmed — engine bound to ephemeral SQLite under `tempfile`, no path crosses to `frontend/prisma/dev.db` or `backend/data/codeboard.db`.
- INFO: `app.main` imports are side-effect-free (background tasks live in `lifespan`, not at import).
- LOW: naive `datetime.utcnow()` mirrors project precedent — out of scope for this regression artifact, no behavioural impact today.
- **Fixed:** dropped redundant manual singleton restore.

## Coverage of sibling QA tickets

The 3-scenario test together with the existing `test_doc_settings.py` covers the [QA] siblings under CB-2089:

- CB-2094 (toggle persists across reload) — covered by `test_doc_settings.py::test_patch_settings_updates_fields` + `test_get_settings_creates_default`.
- CB-2095 (autoGenerate=False skips next exec) — **covered here** by `test_autogenerate_off_skips_summary_but_still_completes`.
- CB-2096 (retention purges) — **covered here** by `test_retention_purges_old_rows`.
- CB-2097 (maxPerIssue caps row count) — **covered here** by `test_retention_respects_per_issue_cap`.
- CB-2098 (recent summaries DESC) — covered by `test_doc_settings.py::test_summaries_returns_rows_newest_first`.
- CB-2099 (manual re-trigger) — manual re-trigger button is a UI affordance — out of scope for backend regression; covered by Chrome QA in CB-2092.

## Files touched

- **Added:** `backend/tests/test_e3_full_regression.py` — 4 tests, ~340 lines.
- **Added:** `docs/research/cb-2093-e3-regression-report.md` (this file).
- **Added:** `scripts/codeboard/2026-05-07-CB-2093-mark-cwq.py` — per-project per-session CWQ marker (Bible Rule 29).

No production code changed.
