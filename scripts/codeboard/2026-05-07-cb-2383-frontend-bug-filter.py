"""
CB-2383 — File BUG: AutoPilot frontend queue construction excludes BUG-type
issues from the executable list, so child BUGs filed under a feature can
never enter a queue and are unreachable from the UI.

This is the seeding-side counterpart to CB-2382 (which fixed the rescan
during run). Together they fully restore the contract: BUGs in a feature
subtree get executed by AutoPilot.

Parent: CB-639 (Auto Pilot Execution feature).
"""
import json, urllib.request, sys

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
PARENT_ID = "ap-feature-001"  # CB-639

TITLE = (
    "AutoPilot UI excludes BUG-type issues from executable queue — "
    "child BUGs under a feature unreachable, no way to start them"
)

DESCRIPTION = """## Bug

The AutoPilot frontend hardcodes the executable-type predicate as
`type === 'TASK' || type === 'SUBTASK'`. `BUG`-type issues that live in
the feature subtree are silently filtered out of:

- `executableItems` in `FeatureExecutionPanel.tsx:124-127` — the queue
  source-of-truth that gets shipped to `POST /api/execute/queue`
- `allLeafTasks` in `FeatureExecutionPanel.tsx:155-156` — the
  "auto-select-all leaves" helper
- `isExecutable` in `FeatureExecutionPanel.tsx:238` — the per-row
  "▶ Run" button visibility flag (no button rendered → no manual single-run)
- `executableItems` in `FeatureSelector.tsx:111-117` — the feature card's
  done/in-progress/todo counters
- `feature/[id]/page.tsx:1041, 1124` — feature page executable lists

This hardcoding has already been partially fixed in the **board** views:
- `KanbanBoard.tsx:204` includes `'BUG'`.
- `EpicSwimlanesBoard.tsx:282` includes `'BUG'`.
- `feature/[id]/page.tsx:718` includes `'BUG'`.

The AutoPilot path was missed.

## Real-world impact

Feature CB-2038 "Documentation Surface" has 16 `BACKLOG` BUGs in its subtree
(filed by code-reviewer + security-auditor agents during prior runs):

```
CB-2117, CB-2123, CB-2212, CB-2213, CB-2214, CB-2215, CB-2216, CB-2217,
CB-2218, CB-2219, CB-2220, CB-2375, CB-2376, CB-2377, CB-2378, CB-2379
```

Most are under STORY CB-2047 (S1.3: E1 audit + regression). They are:

- Visible in the issue tree
- Not visible in the AutoPilot panel
- Not selectable
- Have no `▶ Run` button on their detail row
- Not counted in feature progress

Result: the feature is stuck — child BUGs cannot be advanced, parent
EPICs/STORIEs cascade-block at `IN_PROGRESS`, feature never reaches DONE.

## Reproduction

1. Open `/codeboard/feature/[CB-2038-id]`
2. Click "Run AutoPilot"
3. Observe `FeatureExecutionPanel` task list — no BUGs present
4. Observe per-row `▶ Run` button on a BUG (e.g. CB-2117) — absent
5. Submit queue — backend receives 0 BUGs in `tasks[]`

## Suggested fix

### 1. Centralise the predicate
Create `frontend/lib/codeboard.ts` (or extend an existing helper) with:

```ts
export type ExecutableType = 'TASK' | 'SUBTASK' | 'BUG';
export const EXECUTABLE_TYPES: readonly ExecutableType[] = ['TASK', 'SUBTASK', 'BUG'] as const;
export function isExecutableType(t: IssueType): t is ExecutableType {
  return EXECUTABLE_TYPES.includes(t as ExecutableType);
}
```

### 2. Replace every hardcoded `type === 'TASK' || type === 'SUBTASK'`
in the AutoPilot path with `isExecutableType(i.type)`. Specifically:

- `FeatureExecutionPanel.tsx` lines 117-118, 125-126, 155-156, 238
- `FeatureSelector.tsx` line 111
- `feature/[id]/page.tsx` lines 1041, 1124 (and 924 if AutoPilot-related)

Leave the type-styling sites (kanban swimlane border colours, etc.)
alone — they are visual, not gating. This change is gating only.

### 3. Backend already accepts BUG-type tasks
Verified: `backend/api/execution.py` `POST /execute/queue` validates
`Issue.id` exists but does not gate on `type`. CB-2382 also extended the
mid-run rescan to include BUGs. So the backend is ready; this is purely
a frontend exclusion.

## Acceptance criteria

- [ ] `isExecutableType()` helper added in `frontend/lib/codeboard.ts`.
- [ ] All five AutoPilot-path call sites replaced with the helper.
- [ ] Per-row `▶ Run` button renders for BUGs in `FeatureExecutionPanel`.
- [ ] Selecting a BUG and starting the queue ships it through to the
      backend and executes Claude Code CLI on it.
- [ ] Vitest unit covering the helper + at least one component
      integration test (BUG row appears in the panel for a feature with
      a child BUG).
- [ ] Manual regression: open CB-2038, click Run AutoPilot, verify the
      16 listed BUGs above appear in the executable list, queue starts
      and processes them to `COMPLETED_WAITING_QA`.

## Related

- CB-2382 (sibling): mid-run rescan now picks up BUGs filed *during*
  execution. CB-2383 fixes the seeding side. The two together restore
  the contract: BUGs in a feature subtree get auto-executed.
- CB-639 (parent): Auto Pilot Execution feature.
- Same-tree blockers: CB-2039, CB-2047, CB-2054, CB-2067 stay
  `IN_PROGRESS` until their child BUGs reach `COMPLETED_WAITING_QA`.
"""


def call(method, path, body=None):
    headers = {"Content-Type": "application/json"} if body else {}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main():
    body = {
        "title": TITLE,
        "description": DESCRIPTION,
        "type": "BUG",
        "priority": "HIGH",
        "parentId": PARENT_ID,
        "labels": "autopilot,frontend,blocks-cb-2038,executable-filter",
        "assignee": "react-specialist",
        "reporter": "AI",
    }
    issue = call("POST", f"/projects/{PROJECT_ID}/issues", body)
    print(f"Created {issue['key']} (id={issue['id']})")
    call("PATCH", f"/issues/{issue['id']}", {"status": "IN_PROGRESS"})
    print(f"  → status=IN_PROGRESS")
    return issue["key"], issue["id"]


if __name__ == "__main__":
    try:
        key, _id = main()
        print(f"\nDONE — file: {key} ready for fix")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)
