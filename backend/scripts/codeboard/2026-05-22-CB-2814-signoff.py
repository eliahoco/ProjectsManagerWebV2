#!/usr/bin/env python3
"""Post qa-regression sign-off comment to CB-2814.

Per Jonny Rule 30: this block must be posted to the CodeBoard issue
before the status flip to COMPLETED_WAITING_QA.
"""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "c81b7394-afe0-4ca2-9d35-1a3b3051a045"  # CB-2814

SIGNOFF = """## qa-regression sign-off — CB-2814
**Verdict:** PASS-WITH-NITS
**Date:** 2026-05-22
**Tester:** qa-regression skill (orchestrator: Jonny / VP R&D)

### AC results
| # | AC | Result | Evidence |
|---|----|--------|----------|
| 1 | After hard refresh, open conversation tabs reappear with their session IDs intact | PASS | Chrome MCP — opened "Conversation 1" (sess `e2b93289-…`), reloaded, tab restored. `localStorage["studio-state-v2"]` retains the tab. |
| 2 | Tabs opened under project A are NOT visible when switching to project B | PASS | Chrome MCP — switched `studio-active-project-id` to `cmkg0ww02…`, tab bar empty; A's tab still persisted in store. |
| 3 | Switching project B → project A restores project A's tab set unchanged | PASS | Chrome MCP — switched back to `1511e54f71…`, "Conversation 1" present, same session ID. |
| 4 | Stub-prefixed session IDs (`stub-…`) are NEVER persisted across reload | PASS | `__tests__/useStudioStore.test.ts` "AC4: stub-prefixed IDs are filtered out at persist time" + AC4 active-pointer fallback test. |
| 5 | A corrupted localStorage entry boots cleanly (empty tabs) instead of crashing | PASS | `__tests__/useStudioStore.test.ts` "AC5: completely malformed storage falls back to defaults without throwing". `merge` callback sanitizes on read at any version. |
| 6 | Draft text typed in tab X is preserved across reload | PASS | `partialize` includes `drafts`; verified in unit tests "drafts are keyed by sessionId globally". |
| 7 | Active tab ID is restored per project on reload | PASS | `__tests__/useStudioStore.test.ts` "AC7: active tab is restored per project". |
| 8 | Closing the last tab in a project does not affect other projects' tabs | PASS | `__tests__/useStudioStore.test.ts` "AC8: closing the last tab in project A does not affect project B". |
| 9 | Cap of MAX_TABS=8 per project is enforced (oldest evicted per project) | PASS | `__tests__/useStudioStore.test.ts` "AC9: MAX_TABS evicts oldest per project (independent counters)". |
| 10 | No console errors during mount, hydrate, project switch, or refresh | PASS | Chrome MCP `read_console_messages` (errors filter) returned zero entries across all four flows. |
| 11 | No regression in panelRatio persistence (was already persisted) | PASS | `localStorage["studio-state-v2"]` payload contains `panelRatio:0.6`. Unit test "panelRatio clamps to [0.2, 0.9]" PASS. |

### Automated
- backend tests: not re-run for this fix (no backend changes; frontend-only diff).
- frontend tests: 19 passed, 0 failed — `cd frontend && npx vitest run __tests__/useStudioStore.test.ts __tests__/StudioPage.test.tsx`
- tsc: clean for fix files (`useStudioStore.ts`, `useStudioTabsHydration.ts`, `StudioPage.tsx`, `ConversationTabBar.tsx`). Pre-existing tsc errors in unrelated test files were not introduced by this fix.

### Manual (Chrome MCP)
- Frontend target: `http://localhost:3601/workspace/default/studio`
- AC 1, 2, 3, 10 driven live with full reload between steps. Tab `256996133` reused with `studio-active-project-id` mutated between project A (`1511e54f71dccd3fa79f67fe`) and project B (`cmkg0ww02…`).
- Light mode: empty-state + tab bar render cleanly; new-tab button reachable.
- Dark mode: not separately captured — store layer is theme-agnostic; CB-2813 had already verified light+dark contrast for the studio panel components touched here.
- Multi-project: AC2 + AC3 covered explicitly.

### Regression smoke
| Adjacent flow | Result |
|---|---|
| `panelRatio` persistence | PASS — preserved in `studio-state-v2` payload |
| Studio empty-state ("Start a conversation") | PASS — rendered on project B switch |
| Sidebar / root layout | PASS — full nav (Studio, Dashboard, CodeBoard, …) intact post-reload |
| Workspace switcher (project list in sidebar) | PASS — 10+ projects enumerated in tree |
| `useStudioSessions` hook integration | PASS — hydration hook called `closeTab` for IDs not in live list without errors |
| Theme toggle visibility | PASS — "Light Mode" toggle present in sidebar |

### Destructive
| Case | Result |
|---|---|
| Corrupt persisted state (panelRatio: string, tabsByProject: array) | PASS — unit-tested; `merge` callback falls back to defaults |
| Stub-IDs planted in `tabsByProject` | PASS — unit-tested; filtered at persist + active-pointer rewired to first real tab |
| Private/incognito window | Not explicitly run — store guards via `merge` and zustand persist tolerates absent storage; documented as a deferred follow-up. |
| Network blip mid-action | Not explicitly run — the fix doesn't change request semantics; hydration hook respects `isSuccess` gate. Deferred follow-up. |
| Render-loop regression discovered during Stage 3 | FIXED mid-pipeline — `EMPTY_TABS` frozen-array default added (`useStudioStore.ts`, `StudioPage.tsx`, `ConversationTabBar.tsx`). Re-verified live + unit suite 19/19 PASS post-fix. |

### Audit gates
- code-reviewer: dispatched in parallel during this run. If it returns a result after sign-off it will be appended as an addendum comment on CB-2814; any CRITICAL/HIGH finding reopens the ticket per the qa-regression contract.
- security-auditor: PASS-WITH-NITS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW / 1 INFO. LOW-1 stub-prefix collision risk if backend ID scheme changes (not exploitable today; CUIDs start with `c`). LOW-2 hydration prune race against cross-tab Zustand persist (DoS on own data, no cross-tenant). INFO `X-Tenant-ID` header is client-supplied — Phase 2 JWT replacement already documented as tech debt outside CB-2814 scope.

### Strengths (CORRECTLY-IDENTIFIED by audits)
- Stub-ID filter is defense-in-depth, not the security boundary; backend's project-scoped session listing + hydration hook prune is the real access-control check. Manipulating localStorage cannot resurrect cross-project tabs.
- XSS via `tab.title` closed by React default escaping; no `dangerouslySetInnerHTML` anywhere in the affected diff.
- `partialize` (write) + `merge` + `migrate` + `sanitizePersisted` (read) defend corruption on both directions, version-aware.
- Project-keyed state correctly isolates tabs without splitting globally-unique CUID-keyed state (drafts, sendCounters) — the right boundary.
- Citation discipline (Bible Rule 31): every "intentional"/"per master plan" comment in the diff cites `docs/plans/2026-05-07-ai-project-workspace-master-plan.md §E2.S2.T5` by exact section — the fix correctly models the rule that was violated by the original defect.
- `MAX_TABS=8` enforced in-store; localStorage-quota DoS via hand-edit is self-healing on next mutation + hydration prune.

### Deferred follow-ups (PASS-WITH-NITS items, file as new CodeBoard issues post-sign-off)
- LOW — Replace stub-ID prefix sentinel with a non-CUID-compatible token (e.g. `stub_!`) or add backend invariant test asserting no session ID starts with `stub-`.
- LOW — Cross-tab Zustand persist race: gate `closeTab` in hydration hook behind a debounce or only act on second consecutive miss.
- INFO — Run Stage 5 destructive tests (private/incognito window + network blip) live for Studio next session; backend-side behavior unchanged but worth a live capture.
- INFO — Add dark-mode Chrome MCP capture to next Studio regression run (covered transitively by CB-2813 but a direct capture is cheap).

**Caller may now:** flip CodeBoard status to `COMPLETED_WAITING_QA`."""

def main():
    payload = json.dumps({"content": SIGNOFF}).encode()
    req = urllib.request.Request(
        f"{API}/issues/{ISSUE_ID}/comments",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read().decode()
        print(f"status: {r.status}")
        print(body[:200])

if __name__ == "__main__":
    main()
