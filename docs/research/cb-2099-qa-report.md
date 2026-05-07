# CB-2099 — QA E3-6: Manual re-trigger button starts exec

**Date:** 2026-05-07
**Tester:** Jonny (VP R&D)
**Result:** ✅ PASS

## Acceptance Criterion

> Manual: click re-trigger → confirm → exec session appears in GlobalAgentStatusBar.

## Test Path

| Layer | Location | Verified |
|-------|----------|----------|
| UI button | `frontend/app/settings/documentation/page.tsx:381` | ✅ visible on row hover |
| Confirm dialog | `frontend/app/settings/documentation/page.tsx:254` | ✅ renders with issueKey + Cancel/Start |
| Mutation | `useStartExecution` in `frontend/hooks/useCodeBoard.ts:796` | ✅ POST `/api/execute/issue/{id}` |
| Backend | `POST /api/execute/issue/{id}` | ✅ creates session row |
| Live channel | `useExecutionSessions` (SSE + 2s poll fallback) | ✅ SSE connected |
| Bar render | `GlobalAgentStatusBar` — `frontend/app/codeboard/page.tsx:764` | ✅ failed-state row visible |

## Steps Executed

1. Browser navigate `/settings/documentation` → Recent summaries table renders 20 rows (DESC).
2. Hover row CB-2370 → Re-run button becomes visible (`opacity-0 group-hover:opacity-100`).
3. Click **Re-run** → `ConfirmDialog` opens: *"Re-trigger execution? This will start a new Claude Code session for CB-2370."* — `Cancel` + `Start`.
   - Screenshot: `cb-2099-confirm-dialog.png`
4. Click **Start** → mutation fires.
5. `GET /api/execute/sessions` shows new entry:
   ```
   CB-2370  failed  a92b97c8  started_at=2026-05-07T06:39:33
   error: "Dependency check failed: CB-2370 has status COMPLETED_WAITING_QA. Must be one of BACKLOG, IN_PROGRESS, TODO to execute."
   ```
   Session **was created**, then back-end refused execution because the picked sample issue happened to be in CWQ. Wiring is correct; the rejection is a downstream guardrail, not a bug in CB-2099.
6. Navigate `/codeboard?project=1511e54f71dccd3fa79f67fe` (CB-2370's project).
7. **GlobalAgentStatusBar** renders:
   - `1 running` (CB-2099 — sibling autopilot)
   - `1 done` (CB-2098)
   - `1 failed` (**CB-2370 — this test session**)
   - SSE indicator green ("Live (SSE connected)")
   - Screenshot: `cb-2099-globalagentstatusbar-shows-retrigger-session.png`

## Verdict

Manual re-trigger button starts an execution session and the session appears in `GlobalAgentStatusBar`. **Acceptance met.**

## Side Findings (non-blocking)

### Hydration warning — `<dialog>` rendered as nested `<div>` inside `<tbody>`

Console emits:

```
<%s> cannot contain a nested %s.
See this log for the ancestor stack trace. tbody <div>
```

Cause: `SummaryRow` returns `<>{confirming && <ConfirmDialog/>}<tr>…</tr></>` — the dialog `<div>` becomes a `<tbody>` direct child during render, which React flags as invalid HTML and a hydration risk. Filed separately as **CB-2378**.

### Re-run UX gap — completed/CWQ issues fast-fail

Clicking Re-run on a row whose underlying issue is in `COMPLETED_WAITING_QA` or `DONE` always produces a `Dependency check failed` failed-session. The summary list mostly shows CWQ-state issues (since they just executed), so the button often fast-fails when used. Suggestion: either pre-disable Re-run for non-eligible statuses, send `force=true` from the dialog, or surface the dep-check rejection in a toast instead of a failed session row. Filed separately as **CB-2379**.

## Artifacts

- `docs/research/cb-2099-confirm-dialog.png`
- `docs/research/cb-2099-globalagentstatusbar-shows-retrigger-session.png`
- This report

## Audit Gates

- code-reviewer: not required for QA-only task (no code change in this run).
- security-auditor: not required for QA-only task (no code change in this run).
- regression-test: this report **is** the regression evidence for E3-6.
