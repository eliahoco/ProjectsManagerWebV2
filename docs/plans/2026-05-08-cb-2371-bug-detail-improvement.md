# 🎨 CB-2371 Frontend Improvement — BUG/TASK Detail View

**Date:** 2026-05-08
**Author:** Jonny (VP R&D)
**For:** Eli Cohen
**Status:** PROPOSED — awaits Eli's approval before push (Rule 23)
**Bug:** CB-2371 (filed 2026-05-05)
**Blocks:** CB-2671 (the AutoPilot regression bug — its 9 fix children are invisible in the BUG detail page today)

---

## Chapter 1 — Problem (Eli's words)

> "When I click on the bug, I don't see anything related to the feature or to its tasks. Only way to see everything is to look from the feature view."

**Two visible gaps in `/codeboard/issues/[id]` for BUG/TASK types:**

1. **No parent feature breadcrumb** — even though `parentId` is set, the BUG page does not display the parent relationship visually.
2. **No children tree** — child TASKs (e.g. CB-2672 through CB-2680 under CB-2671) are invisible.
3. **No Auto Pilot button** — cannot run children of a BUG.
4. **No bulk actions / progress bar** — same gap.

---

## Chapter 2 — Architecture (current vs target)

### Current

```
/codeboard/feature/[id]/page.tsx       — rich tree, Auto Pilot, bulk actions, toggles, progress bar
/codeboard/issues/[id]/page.tsx        — plain metadata, comments, activity, NO tree, NO Auto Pilot
```

### Target (after fix)

```
/codeboard/feature/[id]/page.tsx       — uses <HierarchyTreeSection />
/codeboard/issues/[id]/page.tsx        — uses <HierarchyTreeSection /> when issue has children
                                         AND <ParentBreadcrumb /> when parentId set
                                         (always shows the existing metadata + comments + activity)

shared:
  components/codeboard/HierarchyTreeSection.tsx   — extracted tree + Auto Pilot + bulk actions
  components/codeboard/ParentBreadcrumb.tsx       — small breadcrumb showing parent chain
```

**Refactor path:** extract the rich-tree logic from `feature/[id]/page.tsx` into a reusable `<HierarchyTreeSection issueId={id} />` component. Use it in both pages.

---

## Chapter 3 — Component Contract

### `<HierarchyTreeSection issueId, ... />`

**Props:**
| Prop | Type | Description |
|---|---|---|
| `issueId` | string | The issue whose descendants are rendered |
| `projectId` | string | For data-fetching context |
| `viewKind` | `'feature' \| 'bug' \| 'task'` | For minor label tweaks ("All → Waiting QA" stays generic) |
| `onChildClick?` | `(child: Issue) => void` | optional click handler (default: navigate to child detail) |

**Renders:**
- Completion progress bar (waiting QA + done counts)
- Auto Pilot button with count of executable children
- All Done / Refresh actions
- Tabs: Overview / Testing
- Search bar within tree
- Toggle: EPICs / STORYs / TASKs / SUBTASKs / BUGs
- Bulk actions: Select All / None / Expand / Collapse / All → Waiting QA / All → Done
- Hierarchical tree rendering of all descendants

**Data sources:**
- `useIssues(projectId)` — same hook feature page uses
- `useFeatureLiveData(issueId)` — already exists; should work with any issue id since backend `/api/issues/{id}/descendants` is type-agnostic

### `<ParentBreadcrumb issueId={id} />`

**Renders:**
- Walks parent chain via `useIssue(parentId)` recursively (max 5 levels)
- Renders as: `🚀 FEATURE CB-1951 / 🐛 BUG CB-2671 / 📋 you-are-here`
- Each link clickable → navigate to that issue's detail page

---

## Chapter 4 — Story Board (Agile Hierarchy)

### F: CB-2371 (existing FEATURE = parent BUG)

| ID | Type | Title | Owner |
|---|---|---|---|
| **CB-2371** | BUG | PMv2 UI: BUG and TASK detail pages don't render their child issues | (existing) |
| T1 | TASK | Extract `<HierarchyTreeSection />` from `feature/[id]/page.tsx` | react-specialist |
| T2 | TASK | Extract `<ParentBreadcrumb />` component for parent chain visualization | react-specialist |
| T3 | TASK | Wire `<HierarchyTreeSection />` into `feature/[id]/page.tsx` (replace inline) — verify zero regressions | react-specialist |
| T4 | TASK | Wire `<HierarchyTreeSection />` + `<ParentBreadcrumb />` into `issues/[id]/page.tsx` (conditional: tree when has children, breadcrumb when parentId set) | react-specialist |
| T5 | TASK | Auto Pilot button on BUG/TASK — verify backend autopilot endpoint accepts non-FEATURE parents | fullstack-developer |
| T6 | TASK | Vitest — render rich view for BUG asserting tree + Auto Pilot + parent breadcrumb visible | react-specialist |
| T7 | TASK | Chrome QA — open CB-2671 → see parent CB-1951 + 9 children + click Auto Pilot | debugger |
| T8 | TASK | code-reviewer + react-specialist 2-gate audit | code-reviewer |
| T9 | TASK | Mark CB-2371 → CWQ when T1-T8 green | jonny |

**~9 tasks, ~3 hours total. Pure frontend refactor + 1 small backend confirmation (T5).**

---

## Chapter 5 — Sequencing

```
   T1 extract tree section ─────► T3 wire feature page ────┐
                              \                            ├─► T6 tests ──► T7 Chrome QA ──► T8 audit ──► T9 CWQ
                               \─► T4 wire issues page ────┘                                      ▲
                                                                                                  │
   T2 extract breadcrumb ────────► T4 (uses both)            T5 backend confirmation ─────────────┘
```

**T1 + T2 + T5 can run in parallel.**
**T3 + T4 wait on T1 (and T2 for T4).**
**T6/T7/T8/T9 sequential after T3+T4 land.**

---

## Chapter 6 — Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Refactor breaks feature page | M | H | T3 verifies feature page still renders; full Vitest pass before T4 |
| Auto Pilot endpoint rejects non-FEATURE parent | M | M | T5 confirms backend accepts; if not, file follow-up bug + scope creep |
| Recursive parent breadcrumb infinite loops | L | L | Max-5-levels guard in component; covered by T6 test |
| Live data hook tied to feature semantics | L | M | T1 reviews `useFeatureLiveData` for FEATURE-specific assumptions; rename if needed |
| Tree fetch performance on deep BUGs | L | L | Same `useIssues` pagination as feature page; no new perf risk |

---

## Chapter 7 — KPI

**Before:**
- BUG/TASK detail page: metadata only · zero children visible · no Auto Pilot · workaround = re-parent under FEATURE

**After:**
- BUG/TASK detail page: parent breadcrumb · full children tree · Auto Pilot button · bulk actions · same as feature page · zero workaround needed

**Estimated unblocks:** CB-2671 (already CWQ but UI made it hard to monitor) + future regression bugs (CB-2363/2364/2365 cluster + any new regressions).

---

## Chapter 8 — The Ask

**Approve?** Yes/Edit/Park.

If yes → I will:
1. Bump CB-2371 priority MEDIUM → CRITICAL (it blocks visibility for CB-2671's children)
2. Mark CB-2371 → IN_PROGRESS
3. Push 9 fix TASKs under CB-2371 (T1-T9 above) with assignees pre-set
4. Add IssueLink CB-2371 BLOCKS → CB-2671 (so it's visible from CB-2671 too)
5. Dispatch react-specialist on T1+T2 in parallel (extract components)
6. After T1+T2 finish, dispatch on T3+T4
7. Then T5 (fullstack-developer for backend confirm), T6 (react-specialist tests), T7 (debugger Chrome QA), T8 (code-reviewer audit)
8. Mark CB-2371 → CWQ

— Jonny
