# CB-2094 — QA Regression Report

**Issue:** [QA] E3-1: autoGenerate toggle persists across reload
**Status (pre-QA):** IN_PROGRESS
**Status (post-QA):** COMPLETED_WAITING_QA
**Tester:** Jonny (VP R&D)
**Date:** 2026-05-07 (UTC)
**Environment:** localhost — frontend `:3601`, backend `:8401`, SQLite (`backend/data/codeboard.db`)

## Acceptance Criteria

> Manual: toggle off → reload page → still off.

## Test Procedure

| # | Action | Expected | Observed | Result |
|---|--------|----------|----------|--------|
| 1 | GET `/api/documentation/settings` (baseline) | 200 OK with `autoGenerate=true` | `{"autoGenerate":true,"retentionDays":90,"maxPerIssue":20,"updatedAt":"2026-05-02T15:37:25"}` | PASS |
| 2 | Navigate `/settings/documentation`, observe toggle | Toggle ON (`bg-cyan-600`, aria-label `Disable auto-generate`) | Matches | PASS |
| 3 | Click toggle → state flips to OFF | aria-label → `Enable auto-generate`, knob `left-1` | Matches | PASS |
| 4 | Click `Save Settings` | PATCH 200, toast `Saved`, backend `autoGenerate=false` | Backend GET returned `autoGenerate=false`, `updatedAt=2026-05-06T23:09:27` | PASS |
| 5 | Hard reload `/settings/documentation` | Toggle still OFF (no flash, no flip back) | aria-label `Enable auto-generate`, classes `bg-zinc-700`, knob `left-1` | **PASS — primary AC** |
| 6 | Second reload (cache-bust verification) | Toggle still OFF | aria-label `Enable auto-generate` | PASS |
| 7 | PATCH restore `autoGenerate=true` + reload | Toggle ON | aria-label `Disable auto-generate`, `bg-cyan-600` | PASS |

## Persistence Layer Trace

```
UI toggle click
  → React state flip (DocSettingsForm.autoGenerate)
  → handleSave() → useUpdateDocSettings.mutateAsync({ autoGenerate: false })
  → PATCH /api/documentation/settings  (api/documentation router)
  → SQLAlchemy upsert on doc_settings (key='global')
  → SQLite WAL flush
  → React Query cache replacement via setQueryData(['doc-settings'], updated)
Reload
  → useDocSettings() → GET /api/documentation/settings
  → DocSettingsForm initialised with server `autoGenerate=false`
  → Toggle renders OFF
```

End-to-end persistence chain intact. No localStorage/sessionStorage hacks — single source of truth is backend SQLite row.

## Evidence

- `cb-2094-evidence/cb-2094-01-initial-on.png` — baseline ON
- `cb-2094-evidence/cb-2094-02-after-toggle-saved.png` — toggled OFF + saved
- `cb-2094-evidence/cb-2094-03-after-reload-still-off.png` — **post-reload OFF (primary AC)**
- `cb-2094-evidence/cb-2094-04-restored-on.png` — post-restore ON

## Findings

- AC met: toggle state survives full page reload.
- Backend `updatedAt` advances on each PATCH (verified 2026-05-02T15:37 → 2026-05-06T23:09 → 2026-05-06T23:10).
- React Query cache + server fetch align — no UI lag, no flicker on reload.
- No console errors related to settings persistence (existing console errors are unrelated network noise from the queue metrics poller).

## Verdict

**PASS — CB-2094 ready for Eli's manual QA → DONE.**
