# CB-2788 Architecture Audit — Auto Pilot Selection Gaps

**Date:** 2026-05-10  
**Auditor:** AI (React Specialist)  
**Mode:** READ-ONLY — no code changes  
**Feature:** CB-1955 / Bug: CB-2788  

---

## Executive Summary

Three selection-gap bugs exist in the Feature page Auto Pilot flow:

- **Gap A:** Top-right `Auto Pilot (N)` button in `feature/[id]/page.tsx` at line 577 shows `executableTasks.length` which is computed from ALL descendants with no selection awareness — it does not receive or know about the `selected` set inside `HierarchyTreeSection`.
- **Gap B:** `FeatureExecutionPanel` at line 95 calls `useIssueDescendants(feature.id)` on every open — it ignores both the `allIssues` prop passed to it AND the `selected` set from `HierarchyTreeSection`. Pre-selection is driven entirely by `completedItems` logic, not user selection.
- **Gap C:** `FeatureExecutionPanel.renderIssueRow()` renders a `button` as a checkbox only when `isExecutable && !isExecuting` (line 277) — this is a per-row checkbox, but it only toggles internal `selectedIds`, which is initialized from `descendants` (the API fetch), not from the tree's `selected` set. There is no per-row checkbox that reflects the tree's selection.

The `selected` set in `HierarchyTreeSection` is strictly local state (`useState` at line 720). It is never lifted, never passed via context, and is not shared with any parent or sibling. `FeatureExecutionPanel` has no prop for it.

---

## 1. Component Callsite Map

| File | Component Imported | Mount Point | Props Passed | Notes |
|---|---|---|---|---|
| `frontend/app/codeboard/feature/[id]/page.tsx:634` | `HierarchyTreeSection` | Main content area | `issueId={featureId}`, `projectId`, `viewKind="feature"` | `selected` state is hidden inside; page has its own `executableTasks` (line 203) that ignores HTS's `selected` |
| `frontend/app/codeboard/feature/[id]/page.tsx:693` | `FeatureExecutionPanel` | Modal overlay | `feature`, `allIssues`, `projectId`, `isOpen`, `onClose`, `onIssueClick` | No `initialSelectedIds` prop — ignores selection |
| `frontend/app/codeboard/issues/[id]/page.tsx:396` | `HierarchyTreeSection` | Details tab (conditional on `hasChildren`) | `issueId={issue.id}`, `projectId`, `viewKind` derived from `issue.type` | CB-2371 callsite |
| `frontend/app/codeboard/page.tsx:933` | `FeatureExecutionPanel` | Modal overlay | `feature={featureExecutionIssue}`, `allIssues={issues}`, `projectId`, `isOpen`, `onClose`, `onIssueClick` | Board-level callsite; `issues` is the full flat list for the project |
| `frontend/components/codeboard/IssueDetail.tsx:691` | `HierarchyTreeSection` | Details panel (if `allChildren.length > 0`) | `issueId`, `projectId`, `viewKind` | Slide-over panel callsite |
| `frontend/components/codeboard/IssueDetailModal.tsx:688` | `HierarchyTreeSection` | Modal body (if `children.length > 0`) | `issueId`, `projectId`, `viewKind` | Full-page modal callsite |
| `frontend/components/codeboard/HierarchyTreeSection.tsx:1381` | `FeatureExecutionPanel` | Inline (inside HTS render, portal-positioned) | `feature={rootIssue}`, `allIssues={issuesData.items}`, `projectId`, `isOpen`, `onClose`, `onIssueClick` | **The primary callsite for the fix** |

**Summary:** `HierarchyTreeSection` has 5 callsites (feature page, issues/[id] page, codeboard board page via IssueDetail, IssueDetail.tsx, IssueDetailModal.tsx). `FeatureExecutionPanel` has 3 callsites (HierarchyTreeSection's internal mount, feature/[id]/page.tsx, codeboard/page.tsx).

---

## 2. State Ownership Diagram

```
feature/[id]/page.tsx
│
├── selected: NOT OWNED — page has no selection state
│   (page's executableTasks at line 203 ignores selection — GAP A)
│
├── showAutoPilotPanel: useState (line 127)  ← controls page-level FEP
│
└── <HierarchyTreeSection issueId projectId viewKind="feature">
        │
        ├── selected: Set<string>  ← useState (line 720) — LOCAL ONLY
        │     ├── handleSelect sets it (line 967)
        │     ├── handleSelectAll sets it (line 984)
        │     ├── handleDeselectAll sets it (line 996)
        │     ├── handleSelectByType sets it (line 1000)
        │     └── NEVER lifted to parent, NEVER shared via context
        │
        ├── executableTasks: useMemo([tree, selected])  ← line 916
        │     "respects selection" — BUT only used inside HTS toolbar button
        │     The toolbar button (line 1232) opens showAutoPilotPanel=true
        │     which renders FeatureExecutionPanel below. COUNT IS CORRECT HERE.
        │
        ├── showAutoPilotPanel: useState (line 723)  ← HTS-level panel
        │
        └── <FeatureExecutionPanel feature=rootIssue allIssues=issuesData.items>
                │
                ├── selectedIds: Set<string>  ← useState (line 85) — LOCAL ONLY
                │     Initialized from: useIssueDescendants(feature.id) result
                │     NOT from: HierarchyTreeSection's `selected` set
                │
                ├── useIssueDescendants(feature.id)  ← API call (line 95)
                │     cache key: ['issue-descendants', feature.id]
                │     re-fetches ALL descendants regardless of selection
                │
                └── completedItems, executableItems derived from `descendants`
                      (ignores parent `selected`)

codeboard/page.tsx
│
├── selectedIds: Set<string>  ← CB-2018 board-level multi-select (line 62)
│     DIFFERENT selectedIds — for board card selection, unrelated to tree
│
└── <FeatureExecutionPanel feature=featureExecutionIssue allIssues=issues>
        Same gap — no initialSelectedIds prop
```

**Key finding:** There are TWO distinct `selected` / `selectedIds` state scopes that share the same variable name but are completely independent:

1. `HierarchyTreeSection.selected` — tree node selection (checkbox rows in tree)
2. `FeatureExecutionPanel.selectedIds` — task selection within the AutoPilot modal
3. `codeboard/page.tsx.selectedIds` — board-level card multi-select (CB-2018, unrelated)

---

## 3. Hook Dependency Graph

### HierarchyTreeSection hooks

| Hook | Key Deps | Purpose |
|---|---|---|
| `useFeatureLiveData(projectId)` | `projectId` | SSE session map + `hasActiveSessions` |
| `useIssues(projectId, {pageSize:1000, refetchInterval})` | `projectId`, `hasActiveSessions` | All issues for tree |
| `useUpdateIssue()` | — | Status mutations |
| `useIssue(issueId)` | `issueId` | Fetch root issue for passing to FEP |
| `useAutoPilot()` | — (context) | `isActive`, `featureId`, `progress`, `queueStatus` |
| `useUrlState({tab, expanded})` | URL params | Tab + expanded node IDs |
| `useState selected` | — | Tree row selection |
| `useState showAutoPilotPanel` | — | FEP open/close |
| `useMemo tree` | `[issuesData, issueId]` | Build tree from flat list |
| `useMemo executableTasks` | `[tree, selected]` | Respects selection — feeds toolbar button count |

### FeatureExecutionPanel hooks

| Hook | Key Deps | Purpose |
|---|---|---|
| `useIssueDescendants(isOpen ? feature.id : null)` | `isOpen`, `feature.id` | Fetch ALL descendants from API (always, on open) |
| `useAutoPilot()` | — (context) | Check `isActive`, `featureId`, read `queue`, call `startAutoPilot` |
| `useState selectedIds` | — | Internal task selection — initialized from `descendants` |
| `useState expandedIds` | — | Initialized to `new Set([feature.id])` |
| `useState taskActions` | — | Per-task skip/audit/rewrite |
| `useState showTaskActionSelector` | — | Shows completed-task action panel |
| `useMemo featureIssues` | `[feature, descendants]` | `[feature, ...descendants]` — the working data set |
| `useMemo hierarchy` | `[featureIssues]` | Parent→children map |
| `useMemo completedItems` | `[featureIssues]` | Items in DONE/WAITING_QA |
| `useMemo executableItems` | `[featureIssues, showTaskActionSelector, taskActions]` | Executable and not skipped |
| `useEffect` (on open) | `[isOpen, completedItems.length, feature.id, isExecuting]` | Seeds `selectedIds` from `executableItems` on open |

**Critical observation — Gap B root cause:** The `useEffect` at line 137-152 seeds `selectedIds` from `executableItems.map(i => i.id)` which comes from `descendants` (the API fetch of ALL descendants). There is no path for the tree's `selected` set to flow in.

**Gap A root cause:** `feature/[id]/page.tsx:executableTasks` (line 203-213) computes from the shallow `buildShallowTree` over all descendants, status `!== 'DONE'` only. It has zero awareness of `HierarchyTreeSection.selected`. The header Auto Pilot button at line 577 shows `executableTasks.length` — always ALL tasks.

**Gap C root cause:** `renderIssueRow` at line 277 already renders a per-row checkbox (`button` with `CheckCircle2` / empty). The visual checkbox exists, but it calls `toggleSelection(issue.id)` which updates `selectedIds` (FEP-internal), which was seeded from the API, not from the tree. So there IS a per-row checkbox — the bug is that it starts with all tasks pre-selected (from API) and ignores the tree's selection.

---

## 4. Test Coverage Map

| Test File | Tests Covering Affected Behavior | Risk if Changed |
|---|---|---|
| `frontend/__tests__/FeatureExecutionPanel.test.tsx` | 4 tests: BUG executable, auto-select, per-row checkbox, startAutoPilot call | **Must update** — test at line 138 asserts `"1 items selected"` which depends on auto-select from `mockDescendants`. Adding `initialSelectedIds` prop changes initialization path. |
| `frontend/__tests__/bug-detail-view.test.tsx` | Tests HierarchyTreeSection directly — renders child keys, titles, placeholder, Auto Pilot button. `viewKind="bug"` path. | **Must verify stays green** — tests pass `projectId` prop, no `selected` prop. If we add optional prop with fallback, these pass unchanged. |
| `frontend/tests/components/IssueDetailModal.test.tsx` | Mocks HierarchyTreeSection deps (useIssues, useFeatureLiveData, useAutoPilot, use-url-state). Tests existence of HTS inside modal. | **Stays green** — these mock away internals. Signature changes don't break mocks unless we add required props. |
| `frontend/__tests__/AutoPilotFloatingBar.test.tsx` | Tests FloatingBar retry/resume/pause via AutoPilotContext. No HTS or FEP involvement. | **Not affected** |
| `frontend/__tests__/AutoPilotStatusBadge.test.tsx` | UI-only badge component | **Not affected** |
| `frontend/__tests__/AutoPilotRecoveryBanner.test.tsx` | Recovery banner | **Not affected** |

**Critical:** The `FeatureExecutionPanel.test.tsx` test at line 138 (`"1 items selected"`) will need to account for the fact that when `initialSelectedIds` is provided and non-empty, it should seed selection from that instead of from the descendant API.

---

## 5. Cross-Feature Risk Matrix

| Cross-Feature | Owned Files | Data Path Overlap | Breakage Probability | Reason |
|---|---|---|---|---|
| **CB-1955 EPIC 5 / CB-2016** | `frontend/app/codeboard/groups/[id]/page.tsx` | None — status breakdown bar in group view | **LOW** | Completely separate route/component. No shared state with HTS or FEP. |
| **CB-2018** | `frontend/app/codeboard/page.tsx` (selectMode, selectedIds), `KanbanBoard.tsx`, `HierarchyListView.tsx`, `IssueCard.tsx`, `CreateGroupModal.tsx` | Board-level `selectedIds` is a different variable from HTS's `selected`. codeboard/page.tsx FEP callsite has `allIssues={issues}` (no selectedIds prop). | **LOW** | The board's `selectedIds` (CB-2018 per-card multi-select) lives entirely on `codeboard/page.tsx` and flows only to `KanbanBoard` / `HierarchyListView`. FEP at `codeboard/page.tsx:933` does not receive `selectedIds`. Adding `initialSelectedIds` as optional prop to FEP would need a decision: should the board's multi-select pre-seed FEP? Based on the bug description, no — this callsite is separate from the tree. Risk: LOW as long as `initialSelectedIds` is optional with fallback. |
| **CB-2371** | `frontend/app/codeboard/issues/[id]/page.tsx:396` | `HierarchyTreeSection` mount with `viewKind` derived from issue type. The `selected` state is HTS-internal. | **LOW** | This callsite does not pass any new props. If we add optional `initialSelectedIds` prop with fallback to empty `Set` (current behavior), this callsite is unaffected. The Auto Pilot button in HTS is only rendered for `viewKind="feature"` — **wait, check this.** Actually reading the code at line 1232: `{executableTasks.length > 0 || isAutoPilotRunningForThis ? (...)` — there is NO `viewKind==='feature'` guard on the toolbar button. The Auto Pilot button renders for BUG/TASK roots too. But the FEP opened from inside HTS uses `rootIssue` (any type), so it's already working for BUG/TASK roots. This is a pre-existing behavior, not introduced by our fix. |
| **CB-2737** | `frontend/components/codeboard/AutoPilotFloatingBar.tsx` | Reads `AutoPilotContext` state only. No HTS or FEP data path. | **LOW** | Retry buttons in FloatingBar call `resumeAutoPilot` / backend API. Entirely context-driven. No shared state with FEP selection. |
| **CB-2775** | Same `AutoPilotFloatingBar.tsx` | Same as CB-2737 — context-driven retry/resume | **LOW** | `handleResumeWithRetry` at line 163 reads `state.queueId` and `state.queue` from context. No FEP/HTS involvement. |
| **CB-1611** | `frontend/components/codeboard/IssueDetail.tsx`, `IssueDetailModal.tsx`, `frontend/app/codeboard/issues/[id]/page.tsx` — details tab and Implementation tab improvements | HTS is mounted in IssueDetail/IssueDetailModal when `allChildren.length > 0`. Details tab is the `activeTab === 'details'` branch in issues/[id]/page.tsx. | **LOW** | The fix only adds optional props and changes initialization of `selectedIds` inside FEP when `initialSelectedIds` prop is present. The details tab, Implementation tab, and IssueDetail components do not mount FEP. HTS's new optional prop defaults to current behavior. |

---

## 6. Precise Fix Plan

### Gap A — Top-right header button in `feature/[id]/page.tsx` shows wrong count

**Root cause:** `feature/[id]/page.tsx:executableTasks` (line 203-213) is a separate computation in the page, entirely unaware of `HierarchyTreeSection.selected`. The page also mounts its own `FeatureExecutionPanel` (line 693) from `showAutoPilotPanel`.

**The architectural truth:** There are ACTUALLY TWO separate Auto Pilot buttons that open TWO separate FEP instances:
1. The top-right header button in `feature/[id]/page.tsx:551` opens `showAutoPilotPanel` → FEP at line 693
2. The toolbar button inside `HierarchyTreeSection:1232` opens HTS's own `showAutoPilotPanel` → FEP at line 1381

This is a **redundancy problem** — users interact with the tree's checkboxes (inside HTS), but the page-level button opens a different FEP instance that ignores HTS selection.

**Fix A (minimal, backward-compat):** Lift `selected` state out of HTS into `feature/[id]/page.tsx` as a controlled prop, OR simply have the page-level FEP removed (disable/hide it) in favor of only the HTS-internal button, which already computes `executableTasks` correctly with selection.

**Before (page.tsx line 577):**
```tsx
: `Auto Pilot (${executableTasks.length})`}
```
`executableTasks` computed at line 203 — all non-DONE tasks, no selection filter.

**After option 1 (simplest — remove page-level FEP, rely on HTS button):**
Remove the `showAutoPilotPanel` state, button, and FEP render from `feature/[id]/page.tsx` entirely. The HTS toolbar button already handles this correctly. The page header button becomes redundant.

**After option 2 (prop lift):** Add `onSelectionChange?: (selected: Set<string>) => void` to `HierarchyTreeSectionProps`, call it in HTS whenever `selected` changes. Page stores `treeSelected` state and uses it to filter `executableTasks`.

**Backwards-compat:** Option 1 requires no prop changes to HTS. Option 2 adds optional callback. Both are safe.

### Gap B — FEP ignores tree selection; re-fetches ALL descendants

**Root cause:** FEP calls `useIssueDescendants(feature.id)` on open (line 95) and seeds `selectedIds` from that (line 149: `setSelectedIds(new Set(executableItems.map(i => i.id)))`).

**Fix B:** Add optional prop `initialSelectedIds?: Set<string>` to `FeatureExecutionPanelProps`. When provided and non-empty, use it to seed `selectedIds` instead of `executableItems.map(i => i.id)`.

**Before (FeatureExecutionPanel.tsx line 33-39):**
```typescript
interface FeatureExecutionPanelProps {
  feature: Issue;
  allIssues: Issue[];
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  onIssueClick?: (issue: Issue) => void;
}
```

**After:**
```typescript
interface FeatureExecutionPanelProps {
  feature: Issue;
  allIssues: Issue[];
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  onIssueClick?: (issue: Issue) => void;
  /** If provided, pre-seeds the modal's task selection instead of defaulting to all. */
  initialSelectedIds?: Set<string>;
}
```

**Before (FEP useEffect lines 137-152):**
```typescript
useEffect(() => {
  if (isOpen && !isExecuting) {
    setTaskActions(new Map());
    if (completedItems.length > 0) {
      // ... sets skip actions ...
      setShowTaskActionSelector(true);
    } else {
      setShowTaskActionSelector(false);
      setSelectedIds(new Set(executableItems.map(i => i.id)));
    }
  }
}, [isOpen, completedItems.length, feature.id, isExecuting]);
```

**After:**
```typescript
useEffect(() => {
  if (isOpen && !isExecuting) {
    setTaskActions(new Map());
    if (completedItems.length > 0) {
      // ... sets skip actions (unchanged) ...
      setShowTaskActionSelector(true);
    } else {
      setShowTaskActionSelector(false);
      // If caller passed a pre-selection, use it (filter to only executable)
      if (initialSelectedIds && initialSelectedIds.size > 0) {
        const filtered = new Set(
          executableItems.filter(i => initialSelectedIds.has(i.id)).map(i => i.id)
        );
        setSelectedIds(filtered.size > 0 ? filtered : new Set(executableItems.map(i => i.id)));
      } else {
        setSelectedIds(new Set(executableItems.map(i => i.id)));
      }
    }
  }
}, [isOpen, completedItems.length, feature.id, isExecuting, initialSelectedIds]);
```

**HTS callsite update (HierarchyTreeSection.tsx line 1381):**
```tsx
<FeatureExecutionPanel
  feature={rootIssue}
  allIssues={issuesData.items}
  projectId={projectId}
  isOpen={showAutoPilotPanel}
  onClose={() => { setShowAutoPilotPanel(false); refetch(); }}
  onIssueClick={(issue) => router.push(`/codeboard/issue/${issue.id}`)}
  initialSelectedIds={selected.size > 0 ? selected : undefined}  // NEW
/>
```

**Backwards-compat:** `initialSelectedIds` is optional. All 3 other FEP callsites (feature/[id]/page, codeboard/page, HTS with no selection) omit the prop → existing behavior unchanged.

**Note on `useIssueDescendants` and N+1:** FEP continues to call `useIssueDescendants` to get fresh data to render the hierarchy tree. This is a good pattern — the tree needs accurate server data. No N+1 risk; cache key is `['issue-descendants', feature.id]` and the result is shared across opens. The `allIssues` prop passed to FEP is currently unused for the hierarchy (FEP builds its own from `descendants`). This prop can be removed in a future cleanup; for now, leave it to avoid breaking callers.

### Gap C — Per-row checkbox already exists but is seeded incorrectly

**Finding:** The per-row checkbox in FEP DOES exist (renderIssueRow line 277-295). The issue is it starts all-selected because `selectedIds` is seeded from all `executableItems` (Gap B above). Once Gap B is fixed (initialSelectedIds), the per-row checkboxes will correctly reflect only the tree-selected tasks.

**No additional code change needed for Gap C** beyond fixing Gap B. The per-row checkbox at line 279 calls `toggleSelection(issue.id)` which mutates FEP's internal `selectedIds`, allowing user to adjust further in the modal. This is the correct UX.

**However:** The issue description says "no per-row checkbox — only Select All / Deselect All." Looking at the code: the checkbox IS rendered at line 277 (`isExecutable && !isExecuting`). For a TASK/SUBTASK/BUG with `isExecutable=true` and `!isExecuting`, a button renders with either `CheckCircle2` (selected) or empty border (not selected). It IS a checkbox. The perception of "no per-row checkbox" is likely because when all tasks are pre-selected (Gap B), the "Deselect All" is the only obvious control. The fix for Gap B (pre-seeding from tree selection) will make the per-row checkboxes more meaningful since not all will be pre-selected.

---

## 7. Pre-Implementation Checklist

- [ ] **All cross-feature risks LOW or mitigated** — See section 5; all 6 cross-features rated LOW. The key mitigation is making `initialSelectedIds` an optional prop with fallback to existing behavior.
- [ ] **Existing tests stay green — list:**
  - `frontend/__tests__/bug-detail-view.test.tsx` — no prop changes to HTS; stays green
  - `frontend/tests/components/IssueDetailModal.test.tsx` — mocks HTS internals; stays green
  - `frontend/__tests__/AutoPilotFloatingBar.test.tsx` — no overlap; stays green
  - `frontend/__tests__/AutoPilotStatusBadge.test.tsx` — no overlap; stays green
  - `frontend/__tests__/AutoPilotRecoveryBanner.test.tsx` — no overlap; stays green
  - `frontend/__tests__/FeatureExecutionPanel.test.tsx` — **needs update**: line 138 tests `"1 items selected"`. After fix, if `initialSelectedIds` is not passed (as in the test), behavior is unchanged → still 1 item selected from `executableItems`. Test stays green as long as we don't change the fallback path. Confirm: test at line 111 passes `allIssues` but not `initialSelectedIds` → falls through to existing `executableItems.map` path → still 1 item → green.
- [ ] **New tests planned:**
  1. `FeatureExecutionPanel.test.tsx` — add: "when `initialSelectedIds` is provided, only those ids are pre-selected"
  2. `FeatureExecutionPanel.test.tsx` — add: "when `initialSelectedIds` is non-empty but no matching executable items, falls back to all"
  3. `bug-detail-view.test.tsx` — add: "Auto Pilot button count matches selected tasks, not all tasks" (requires simulating select + open)
- [ ] **No backend changes needed** — all 3 gaps are frontend-only. `useIssueDescendants` endpoint stays identical; we only change when/how its result seeds `selectedIds`.
- [ ] **Bible Rule 25 regression matrix defined:**
  - HTS rendered in IssueDetailModal → no Auto Pilot button visible (viewKind implies it renders, but test confirms no FEP opened from modal)
  - HTS rendered in IssueDetail (slide-over) → same
  - HTS rendered in issues/[id]/page → same (CB-2371 path)
  - `codeboard/page.tsx` FEP instance → no `initialSelectedIds` → existing behavior, no regression
  - `feature/[id]/page.tsx` page-level FEP instance → per Fix A option 1, this instance is removed; per Fix A option 2, requires selection lift

---

## 8. Surprise Findings

**SURPRISE 1:** There are TWO independent Auto Pilot button + FEP flows on the feature page:
1. The page header button (`feature/[id]/page.tsx:551`) → `showAutoPilotPanel` → FEP at line 693
2. The HTS toolbar button (`HierarchyTreeSection.tsx:1232`) → HTS's `showAutoPilotPanel` → FEP at line 1381

Both open a FEP independently. Both display the feature. The page-level instance has Gap A (no selection). The HTS-level instance actually computes `executableTasks` correctly with selection, but passes `selected` to FEP as... nothing. So clicking the HTS toolbar button shows the correct count in the label, but still opens FEP with all tasks selected. The page-level button always shows ALL tasks.

**SURPRISE 2:** `allIssues` prop passed to `FeatureExecutionPanel` is effectively unused inside FEP. FEP builds its working data from `useIssueDescendants` API call, not from `allIssues`. The `allIssues` prop is only part of the interface signature — it is not read inside FEP (confirmed: no `allIssues` usage in FEP body after line 80's prop destructuring). This is dead prop. Safe to keep for compatibility but should be documented.

**SURPRISE 3:** The `selected` set in HTS is already selection-aware for `executableTasks` (line 921: `if (selected.size === 0 || selected.has(node.id))`). This means if user selects 3 tasks in the tree, the HTS toolbar button correctly shows `Auto Pilot (3)`. The count is RIGHT. The bug is only that when the modal opens, FEP ignores this and re-fetches all descendants. The fix is purely about threading the `selected` set into FEP's initialization.

---

## Files Modified by Fix (Minimal Surface)

| File | Change | Risk |
|---|---|---|
| `frontend/components/codeboard/FeatureExecutionPanel.tsx` | Add `initialSelectedIds?: Set<string>` to props; update useEffect seed logic | LOW — optional prop, fallback path unchanged |
| `frontend/components/codeboard/HierarchyTreeSection.tsx` | Pass `initialSelectedIds={selected.size > 0 ? selected : undefined}` to FEP at line 1383 | LOW — one prop addition at one call site |
| `frontend/app/codeboard/feature/[id]/page.tsx` | Either: (A) remove page-level FEP + button, or (B) add selection lift via callback | LOW-MED — removing redundant FEP reduces complexity; lift adds complexity |

**Recommendation for Fix A:** Option 1 (remove page-level FEP). The page-level FEP is redundant with HTS's FEP. Removing it eliminates Gap A entirely and reduces cognitive surface area. The top-right header button can be removed OR converted to just open HTS's panel (which would require a callback or ref, adding complexity). Simpler: remove the page-level button and FEP, rely on HTS toolbar as the sole entry point.
