#!/usr/bin/env python3
"""
Document this session's CB-1955 regressions + follow-ups in CodeBoard.

Per Eli's directive (2026-05-05):
  * Always plan first, document after.
  * Regression tickets must be grouped under an EPIC describing the
    regression — not standalone.
  * Each ticket includes what changed, what was fixed, files touched,
    commits, acceptance criteria, root cause, links to evidence.

Structure:
  EPIC (NEW)  — Issue Correlation & Grouping: implementation regressions
                + post-mortem
    ├── BUG   — SCard wrapper React anti-pattern (HIGH)
    ├── BUG   — IssueGroupCreate schema missing extra="forbid" (MED)
    ├── BUG   — RagStatusCard floods console with 404s (LOW)
    ├── TASK  — Re-implement kanban-card multi-select via Context (LOW)
    ├── TASK  — Playwright smoke: replace networkidle (LOW)
    └── TASK  — SSE endpoints failing during smoke (LOW)

Plus comment-updates on existing tickets:
  CB-2018, CB-2032, CB-2033, CB-2034, CB-2035, CB-2036, CB-2037,
  CB-2009 (EPIC 5), CB-2336.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8401/api"
PMV2_PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "cb-1955-regression-postmortem"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def patch(iid: str, payload: dict) -> int:
    req = urllib.request.Request(
        f"{BASE}/issues/{iid}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def comment(iid: str, body: str) -> int:
    req = urllib.request.Request(
        f"{BASE}/issues/{iid}/comments",
        data=json.dumps({"content": body, "author": "Jonny"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def fetch_all_issues() -> dict:
    items = []
    page = 1
    while True:
        d = json.load(urllib.request.urlopen(
            f"{BASE}/projects/{PMV2_PROJECT_ID}/issues?page={page}&pageSize=200"
        ))
        items.extend(d["items"])
        if page >= d["totalPages"]:
            break
        page += 1
    return {i["key"]: i for i in items}


def create(*, type_: str, title: str, description: str, priority: str,
           parent_id: str | None = None, extra_labels: str = "") -> dict:
    payload = {
        "type": type_,
        "title": title,
        "description": description,
        "priority": priority,
        "reporter": "AI",
        "labels": LABEL + (f",{extra_labels}" if extra_labels else ""),
        "status": "BACKLOG",
    }
    if parent_id:
        payload["parentId"] = parent_id
    r = post(f"/projects/{PMV2_PROJECT_ID}/issues", payload)
    print(f"  CREATED {r['key']:8s} [{type_:5s}] [{priority:6s}] — {title[:65]}")
    return r


# ============================================================
# 1. EPIC — umbrella for the regression post-mortem
# ============================================================
print("=" * 60)
print("Step 1: create regression EPIC")
print("=" * 60)
epic = create(
    type_="EPIC",
    priority="HIGH",
    title="EPIC — CB-1955 implementation regressions + post-mortem",
    description="""**Umbrella for regressions and follow-ups discovered during the CB-1955 (Issue Correlation & Grouping) implementation cycle on 2026-05-05.**

## Why this EPIC exists

Per Eli's directive on 2026-05-05: regression tickets must group under an EPIC describing the regression context, not be filed standalone. This EPIC scopes the post-mortem of one specific cycle.

## What happened (summary)

During the EPIC 5 (Frontend Groups view) implementation:
- A SCard wrapper component (CB-2018) was defined inside the `KanbanBoard` function body. New component identity per render → React unmounted/remounted all ~1800 issue cards on every state change → browser hung. A sloppy mass-replace also turned the wrapper into a recursive self-call. Reverted in commit `e3c2684`.
- The `IssueGroupCreate` Pydantic schema was missing `extra="forbid"`. Modal+hook were sending `memberIssueIds` (correct frontend convention) but the backend schema field is `issueIds` — silent field-name drop. Groups created via the modal had zero members. Caught during regression in commit `287e51c`.
- Console errors (RagStatusCard 404s flooding) and network failures (SSE endpoints) were observed during the playwright smoke test — pre-existing, surfaced now.
- Multi-select on kanban-card view is currently inert (only LIST view works) following the SCard revert.

## How verification was done

Chrome MCP transport was stuck in this Code session — could not drive a real browser. Substituted with:
1. **API-driven regression** (`scripts/codeboard/2026-05-05-cb-2032-regression-cb1955.py`) — covers CB-2032..CB-2037 backend equivalents. All 5 scenarios PASS.
2. **Playwright smoke** (`scripts/codeboard/2026-05-05-cb-1955-playwright-smoke.js`) — drives a real headless Chromium against the dev server. Verified all CB-1955 UI components mount and render correctly: "+ New Group" button, multi-select toggle, Create Group Modal (title + body + member search), 210 list-view checkboxes, segmented status bar with `aria-label="3 Backlog"`.

## Process learnings

1. Never define a React component inside another component's function body — new identity per render destroys child reconciliation.
2. Schemas at API boundaries should always have `extra="forbid"` to fail loud on field-name typos rather than silently dropping data.
3. Playwright `networkidle` doesn't work for apps with always-on SSE streams.
4. Bible Rule 23 violated: implementation shipped before presenting plan to Eli. Documented for future reference.

## Children

See child BUGs and TASKs for individual scope, fix status, and acceptance criteria. All filed today as part of this post-mortem.""",
)
EPIC = epic["id"]
print()


# ============================================================
# 2. BUG — SCard wrapper React anti-pattern (HIGH)
# ============================================================
print("Step 2: file regression BUGs + follow-up TASKs")
b1 = create(
    type_="BUG",
    priority="HIGH",
    parent_id=EPIC,
    extra_labels="frontend,react,regression",
    title="SCard wrapper inside KanbanBoard hung the browser (CB-2018 regression)",
    description="""## Symptom

Opening `/codeboard?project=<any>` after CB-2018 commit `1363507` made the entire CodeBoard page unresponsive. Browser tab pegged CPU, eventually triggered "page unresponsive" dialog.

## Root cause

In `frontend/components/codeboard/KanbanBoard.tsx`, the CB-2018 commit defined a `SCard` wrapper component INSIDE the `KanbanBoard` function body:

```tsx
export function KanbanBoard(props) {
  // BAD — new component identity per render:
  const SCard = (props) => (
    <IssueCard {...props} selectMode={selectMode} ... />
  );
  // ... 14 <SCard /> usages ...
}
```

Two compounding problems:

1. **New component identity per render** — every time KanbanBoard re-rendered (which happens on every selection state change), `SCard` was a fresh function reference. React saw it as a new component type and unmounted + remounted the entire issue tree. With ~1800 issues open in PMv2, the browser locked up.

2. **Mass-replace caught the inner reference** — the `<IssueCard ...` → `<SCard ...` replace_all also caught the wrapper's internal `<IssueCard>` reference, turning the wrapper into a recursive self-call. Stack overflow on first render attempt.

## What was fixed

Commit `e3c2684` — reverted the SCard wrapper. All `<SCard>` references in KanbanBoard.tsx restored to `<IssueCard>`. KanbanBoard.tsx still accepts the `selectMode`/`selectedIds`/`onToggleSelected` props in its signature so the page-level wiring stays in place for the LIST view to consume — but the kanban-card variant is currently inert.

## Files touched

- `frontend/components/codeboard/KanbanBoard.tsx` (revert)

## Verification

- Playwright smoke (`scripts/codeboard/2026-05-05-cb-1955-playwright-smoke.js`) confirmed `/codeboard` loads after revert and all 14 IssueCard renders work correctly.
- LIST view multi-select (HierarchyListView, owns its own checkboxes inline) confirmed working — 210 checkboxes rendered when selectMode toggled on.

## Status

FIXED in commit `e3c2684`.

## Side-effect / follow-up

Kanban-card multi-select is no longer functional. Filed as separate TASK (sibling under this EPIC) to re-implement using React Context or a stable helper-function pattern (NOT a wrapper component defined inside the parent function body — that's the anti-pattern this bug documents).

## Lesson

Never define a React component inside another component's function body. Lift the component definition to module scope, or use Context/render props. If you need to inject parent props into many children, use a helper function that returns props (not JSX) and spread it: `<IssueCard {...rowProps(issue.id)} />`.""",
)
print()

# ============================================================
# 3. BUG — IssueGroupCreate schema missing extra="forbid"
# ============================================================
b2 = create(
    type_="BUG",
    priority="MEDIUM",
    parent_id=EPIC,
    extra_labels="backend,schema,security-hardening",
    title="IssueGroupCreate schema silently drops unknown fields (memberIssueIds vs issueIds)",
    description="""## Symptom

Every group created via the new "+ New Group" modal had zero members despite the user selecting multiple issues in the picker. POST `/api/projects/{id}/groups` returned `201 Created` with `memberCount: 0`. No backend error, no frontend error.

## Root cause

The `IssueGroupCreate` Pydantic schema in `backend/models/schemas.py` accepts:

```python
class IssueGroupCreate(BaseModel):
    title: str
    description: Optional[str]
    issueIds: Optional[List[str]]   # backend field name
```

But `frontend/components/codeboard/CreateGroupModal.tsx` and `frontend/hooks/useGroups.ts` were sending:

```ts
{ title, description, memberIssueIds: [...] }   // wrong field name
```

The schema does NOT have `model_config = {"extra": "forbid"}`, so Pydantic silently dropped `memberIssueIds` instead of returning a 422. Backend created the group with no members.

This worked end-to-end through TypeScript compile-time checks (frontend defined its own type, backend defined its own schema, neither enforced the relationship). Only running the actual call surfaced the mismatch.

## What was fixed

Commit `287e51c`:
- `frontend/hooks/useGroups.ts` — `CreateGroupPayload.memberIssueIds` → `issueIds`
- `frontend/components/codeboard/CreateGroupModal.tsx` — payload key changed
- `scripts/codeboard/2026-05-05-cb-2032-regression-cb1955.py` — same rename in the regression script

## What still needs fixing (this ticket's scope)

Add `model_config = {"extra": "forbid"}` to `IssueGroupCreate` (and audit all other `*Create` / `*Update` schemas in `backend/models/schemas.py` for the same hardening). Future field-name typos must surface as `422 VALIDATION_ERROR` at the API boundary instead of silently dropping data.

## Files involved

- `backend/models/schemas.py` — `IssueGroupCreate` (around line 367)
- Optional sweep: any other Pydantic input schema for the API

## Acceptance

- `POST /api/projects/{id}/groups` with body `{"title": "x", "memberIssueIds": ["a"]}` returns `422 VALIDATION_ERROR` (not `201`).
- All existing tests still pass.
- Add a regression test: send unknown field, expect 422.

## Lesson

Pydantic's default `extra="ignore"` is an unsafe default for API input schemas. The repo's existing schemas should be audited for this — at minimum every `*Create` / `*Update` shape that receives user input.""",
)
print()

# ============================================================
# 4. BUG — RagStatusCard 404 flood
# ============================================================
b3 = create(
    type_="BUG",
    priority="LOW",
    parent_id=EPIC,
    extra_labels="frontend,console-noise,pre-existing",
    title="RagStatusCard floods console with 404s on every codeboard mount",
    description="""## Symptom

Opening any CodeBoard page in the browser produces 5+ `[RagStatusCard] fetch failed: HTTP 404` console errors. Surfaced during the playwright smoke test on 2026-05-05.

## Root cause

`RagStatusCard` polls `/api/system/rag/status` on a timer. The endpoint does not exist (returns 404). Was caught earlier as a network failure in dev tooling but never silenced.

## Status

NOT MY REGRESSION — pre-existing on 2026-05-05 before any of my CB-1955 work landed. Filing here per Eli's directive that issues surfaced during a regression cycle should be tracked even if they're not caused by it.

## Files involved

- `frontend/components/RagStatusCard.tsx` (or wherever it lives)
- `backend/api/system.py` — endpoint either needs to be implemented or the poller needs to be removed

## Acceptance

Either:
(a) Implement `/api/system/rag/status` to return RAG service health (likely a real feature), OR
(b) Remove the RagStatusCard polling (if RAG status is no longer needed)

Console should be clean of `[RagStatusCard]` errors after the fix.""",
)
print()

# ============================================================
# 5. TASK — Re-implement kanban-card multi-select via Context
# ============================================================
t1 = create(
    type_="TASK",
    priority="LOW",
    parent_id=EPIC,
    extra_labels="frontend,follow-up,multi-select",
    title="Re-implement kanban-card multi-select via React Context (replaces SCard approach)",
    description="""## Context

CB-2018 originally specified per-card checkbox + multi-select on both LIST view AND KANBAN view. The LIST view ships and works (HierarchyListView owns inline checkboxes — 210 confirmed via playwright smoke). The KANBAN view variant was attempted via a `SCard` wrapper component defined inside KanbanBoard's function body. That approach was a React anti-pattern (see sibling BUG: SCard wrapper hung the browser) and had to be reverted.

KanbanBoard.tsx still accepts `selectMode`/`selectedIds`/`onToggleSelected` props in its signature — the wiring is intact at the page level — but the props are not currently consumed by IssueCard renders inside the kanban.

## Scope

Re-implement kanban-card multi-select using one of:

**Option A — React Context** (recommended):
- Create `SelectionContext` in `frontend/contexts/SelectionContext.tsx`
- Provider wraps the CodeBoard page (page.tsx)
- IssueCard reads `useSelection()` directly when in selectMode
- No prop threading through KanbanBoard at all
- Stable identity guaranteed

**Option B — Stable helper function**:
- Define `cardSelProps = useMemo(() => (id) => ({...}), [...deps])` in KanbanBoard
- Spread `{...cardSelProps(issue.id)}` on each `<IssueCard>` site
- Avoids the wrapper-component anti-pattern entirely

## Files

- `frontend/components/codeboard/KanbanBoard.tsx`
- `frontend/components/codeboard/IssueCard.tsx` (already accepts the props from CB-2018 commit)
- New: `frontend/contexts/SelectionContext.tsx` (if Option A)

## Acceptance

- Playwright smoke or manual test: enable selectMode, switch to kanban view, verify checkboxes appear on each card and toggle correctly
- ~1800 issues open + selectMode toggle does NOT hang the browser
- "Group selected (N)" button on toolbar reflects selection from kanban view

## Replaces

CB-2336 (filed 2026-05-04 as the original "deferred CB-2018 follow-up"). That ticket pre-dates this regression context. Either close CB-2336 with a link here or merge.""",
)
print()

# ============================================================
# 6. TASK — Playwright smoke networkidle fix
# ============================================================
t2 = create(
    type_="TASK",
    priority="LOW",
    parent_id=EPIC,
    extra_labels="dev-tooling,test-infra",
    title="Playwright smoke script: replace `networkidle` with `domcontentloaded`",
    description="""## Context

`scripts/codeboard/2026-05-05-cb-1955-playwright-smoke.js` uses `waitUntil: 'networkidle'` for `page.goto`. PMv2 has always-on SSE streams (`/api/execute/sessions/stream`, `/api/execute/queue/events`) that keep the network "busy" forever, so `networkidle` never fires.

Result: every `page.goto` times out at 90s. Assertions still run (page is interactive long before the timeout) but the script's exit timing is wrong and any CI integration would falsely fail.

## What needs to change

In `scripts/codeboard/2026-05-05-cb-1955-playwright-smoke.js`:

```js
// before:
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });

// after:
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('[data-testid="codeboard-ready"]'); // or similar
```

`domcontentloaded` fires when the HTML is parsed; for client-rendered React, follow with an explicit `waitForSelector` on a known mounted element. The CodeBoard page already has stable selectors like `button:has-text("New Group")` — those are good post-mount markers.

## Files

- `scripts/codeboard/2026-05-05-cb-1955-playwright-smoke.js`

## Acceptance

- Script completes in <30s end-to-end (vs current 3+ min due to repeated 90s timeouts)
- No false-positive timeouts; explicit "page is ready" assertions instead""",
)
print()

# ============================================================
# 7. TASK — SSE endpoints failing
# ============================================================
t3 = create(
    type_="TASK",
    priority="LOW",
    parent_id=EPIC,
    extra_labels="backend,sse,investigation",
    title="Investigate SSE endpoints returning ERR_ABORTED during smoke",
    description="""## Context

Playwright smoke (2026-05-05) reported network failures:
- `GET http://localhost:8401/api/execute/sessions/stream` — `net::ERR_ABORTED`
- `GET http://localhost:8401/api/execute/queue/events` — `net::ERR_ABORTED`

Browsers showing `ERR_ABORTED` for SSE endpoints can be normal (client navigated away mid-stream, browser cancelled the long-lived connection) but worth confirming.

## What to investigate

1. Is `ERR_ABORTED` here intentional (SSE always cancels on navigation) or a real backend issue (endpoint never returned headers, browser timed out)?
2. Tail backend log during a fresh codeboard load and capture what those endpoints return.
3. If intentional: filter from the playwright smoke output so signal isn't lost in noise.
4. If a real bug: fix the endpoint to either keep the connection alive or return a clean close.

## Acceptance

- Documented behavior of both endpoints with evidence (backend log + browser network tab capture).
- Either silence the noise in the smoke script OR file a downstream bug.""",
)
print()

# ============================================================
# 8. Update existing tickets with comments
# ============================================================
print("Step 3: update existing tickets with detailed comments")

by_key = fetch_all_issues()

# CB-2018 — honest scope
if "CB-2018" in by_key:
    body = f"""## 2026-05-05 update — honest scope after the SCard regression

**LIST view**: shipped + verified. Playwright smoke confirmed 210 checkboxes render in HierarchyListView when selectMode is toggled on. Page-level state (`selectMode`/`selectedIds`/`onToggleSelected`) flows correctly from CodeBoardPage → HierarchyListView.

**KANBAN view**: temporarily INERT. Original implementation used a `SCard` wrapper component defined inside `KanbanBoard.tsx`'s function body — React anti-pattern that hung the browser by remounting all 1800 cards on every render. Reverted in commit `e3c2684`. Filed as bug under regression EPIC `{epic['key']}`.

**Follow-up**: kanban-card multi-select to be re-implemented via React Context or stable helper-function pattern. Filed as TASK `{t1['key']}` under regression EPIC `{epic['key']}`. (Replaces CB-2336.)

This ticket stays at CWQ for the LIST scope. Eli to bless to DONE once visually confirmed."""
    s = comment(by_key["CB-2018"]["id"], body)
    print(f"  CB-2018 comment: {s}")

# CB-2032
if "CB-2032" in by_key:
    body = f"""## 2026-05-05 update — verification via API regression

Chrome MCP transport was stuck in this Code session. Could not drive a real browser via MCP for the original Chrome regression scope.

**Substituted with API-driven regression script**: `scripts/codeboard/2026-05-05-cb-2032-regression-cb1955.py` (committed as `287e51c`).

Covers all 5 child Chrome scenarios end-to-end against the live backend:

| Test | Scenario | Result |
|---|---|---|
| CB-2033 | Create-group flow with members | PASS — 3 members confirmed in detail |
| CB-2034 | Relation lifecycle (POST → GET symmetric → DELETE pair) | PASS — `{{deleted: 2}}` confirms companion auto-removed |
| CB-2035 | Cycle prevention (BLOCKS A→B then B→A) | PASS — `409 CYCLE_DETECTED` |
| CB-2036 | Aggregate status updates (1/3 → CWQ) | PASS — 33.33% completion, breakdown reflects mix |
| CB-2037 | Cascade-up + cascade-down (CB-1941/1943 still works) | PASS both directions |

**Subsequent UI verification via Playwright** (`scripts/codeboard/2026-05-05-cb-1955-playwright-smoke.js`):
- "+ New Group" toolbar button visible
- Create Group Modal opens correctly (title, body, member search inputs all present)
- LIST view multi-select renders 210 checkboxes
- Group detail page loads with segmented status bar (`aria-label="3 Backlog"`)

**What's NOT covered**: literal Chrome MCP-driven user interactions. Eli to do a final manual click-through for visual regression sign-off."""
    s = comment(by_key["CB-2032"]["id"], body)
    print(f"  CB-2032 comment: {s}")

# CB-2033..CB-2037 individual comments
for k in ["CB-2033", "CB-2034", "CB-2035", "CB-2036", "CB-2037"]:
    if k not in by_key:
        continue
    body = f"""## 2026-05-05 — verified via API substitute

This Chrome regression task was verified via the API-driven substitute script (`scripts/codeboard/2026-05-05-cb-2032-regression-cb1955.py`, commit `287e51c`) because Chrome MCP transport was unavailable in the implementing session.

Result: **PASS** — see parent CB-2032 for the full assertion table.

If a literal Chrome-driven verification is required as a separate gate, file as a follow-up. Otherwise this is satisfied."""
    s = comment(by_key[k]["id"], body)
    print(f"  {k} comment: {s}")

# CB-2009 — process post-mortem
if "CB-2009" in by_key:
    body = f"""## 2026-05-05 process post-mortem

**Bible Rule 23 violation** — implementation work for CB-2016 / CB-2017 / CB-2018 / CB-2019 shipped without presenting a plan to Eli first. Items were moved IN_PROGRESS → CWQ without a pre-flight plan review. Acknowledged.

**What went wrong:**
1. CB-2018 SCard wrapper anti-pattern crashed CodeBoard for ~10 minutes before being caught + reverted. Filed as BUG under regression EPIC `{epic['key']}`.
2. CB-2017/2019 CreateGroupModal silently dropped members (field-name mismatch with backend schema). Caught only during regression + fixed in commit `287e51c`. Filed as BUG under regression EPIC `{epic['key']}`.

**Lesson**: ALWAYS plan first, even when the breakdown is already in CodeBoard. Pre-flight is not just for new features — it's for any non-trivial implementation work."""
    s = comment(by_key["CB-2009"]["id"], body)
    print(f"  CB-2009 comment: {s}")

# CB-2336
if "CB-2336" in by_key:
    body = f"""## 2026-05-05 — superseded by `{t1['key']}`

This ticket was filed pre-regression as the original deferred follow-up for CB-2018's kanban-card multi-select. The CB-2018 implementation attempt (SCard wrapper) failed due to a React anti-pattern (see BUG `{b1['key']}` under regression EPIC `{epic['key']}`).

The proper re-implementation work is now tracked under TASK `{t1['key']}` (re-implement via React Context or stable helper). Closing this ticket as superseded.

If you'd rather keep this ticket as the active one and close the new one, swap the relationship — they describe the same work, just from different points in time."""
    s = comment(by_key["CB-2336"]["id"], body)
    print(f"  CB-2336 comment: {s}")

print()
print("=" * 60)
print(f"Done. Regression EPIC: {epic['key']}")
print(f"  Children: {b1['key']}, {b2['key']}, {b3['key']}, {t1['key']}, {t2['key']}, {t3['key']}")
print(f"  Updated existing: CB-2018, CB-2032, CB-2033, CB-2034, CB-2035,")
print(f"                    CB-2036, CB-2037, CB-2009, CB-2336")
print("=" * 60)
