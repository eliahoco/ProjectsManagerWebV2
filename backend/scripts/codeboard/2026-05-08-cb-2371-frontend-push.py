"""
Push CB-2371 frontend improvement hierarchy under the existing BUG.
6 EPICs, 11 STORIEs, 19 TASKs. Wires IssueLink BLOCKS → CB-2671.
"""
from __future__ import annotations
import json, urllib.request, urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABELS_BASE = "🚀-bug,cb-2371-frontend,bug-detail-view"


def http(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} on {method} {path}: {e.read().decode()[:200]}")
        raise


def find_id(key):
    for page in range(1, 50):
        r = http("GET", f"/projects/{PROJECT_ID}/issues?page={page}&pageSize=200")
        for x in r.get("items", []):
            if x.get("key") == key:
                return x["id"]
        if page >= r.get("totalPages", 1):
            break
    return None


def create(parent_id, type_, title, desc, priority, assignee, extra_label=""):
    labels = LABELS_BASE + ("," + extra_label if extra_label else "")
    body = {
        "title": title, "description": desc, "type": type_, "priority": priority,
        "reporter": "AI", "labels": labels, "status": "BACKLOG",
        "parentId": parent_id, "assignee": assignee,
    }
    return http("POST", f"/projects/{PROJECT_ID}/issues", body)


HIERARCHY = [
    {"id": "E1", "type": "EPIC", "t": "[E1] Component Extraction — reusable building blocks", "p": "CRITICAL", "a": "react-specialist",
     "d": "Extract <HierarchyTreeSection /> + <ParentBreadcrumb /> from feature/[id]/page.tsx into reusable components. Foundation for E2.",
     "children": [
         {"id": "E1.S1", "type": "STORY", "t": "[E1.S1] Extract <HierarchyTreeSection />", "p": "CRITICAL", "a": "react-specialist",
          "d": "Pull tree+AutoPilot+bulk-actions+toggles+search out of feature/[id]/page.tsx into components/codeboard/HierarchyTreeSection.tsx",
          "children": [
              {"id": "E1.S1.T1", "type": "TASK", "t": "[E1.S1.T1] Identify logic blocks to extract", "p": "HIGH", "a": "react-specialist",
               "d": "Read frontend/app/codeboard/feature/[id]/page.tsx and map sections: tree render, AutoPilot button, All Done!, bulk actions row, EPICs/STORYs/TASKs/SUBTASKs toggle, search bar within tree, progress bar. Document findings as a comment on this task before moving to T2."},
              {"id": "E1.S1.T2", "type": "TASK", "t": "[E1.S1.T2] Define props contract", "p": "HIGH", "a": "react-specialist",
               "d": "Define props for <HierarchyTreeSection />: { issueId, projectId, viewKind?: 'feature'|'bug'|'task' }. Document in a TS interface; ensure it covers all current call sites in feature page."},
              {"id": "E1.S1.T3", "type": "TASK", "t": "[E1.S1.T3] Move logic to components/codeboard/HierarchyTreeSection.tsx", "p": "HIGH", "a": "react-specialist",
               "d": "Create the new component file. Move all identified logic (T1) inside. Adjust imports. Component must compile and unit-render in isolation."},
              {"id": "E1.S1.T4", "type": "TASK", "t": "[E1.S1.T4] Audit useFeatureLiveData for FEATURE-specific assumptions", "p": "HIGH", "a": "react-specialist",
               "d": "Hook is named useFeatureLiveData but BUG/TASK callers will use it too. Read the hook, check for type-checks against 'FEATURE'. If found, generalize (rename or fix). Backend /api/issues/{id}/descendants is type-agnostic per Eli's ticket — verify that's still true."},
          ]},
         {"id": "E1.S2", "type": "STORY", "t": "[E1.S2] Extract <ParentBreadcrumb />", "p": "HIGH", "a": "react-specialist",
          "d": "Build small breadcrumb component showing parent chain. Used on issues/[id] page when parentId is set.",
          "children": [
              {"id": "E1.S2.T1", "type": "TASK", "t": "[E1.S2.T1] Build component shell — components/codeboard/ParentBreadcrumb.tsx", "p": "HIGH", "a": "react-specialist",
               "d": "Props: { issueId }. Internal: walks parentId chain via useIssue (max 5 levels). Renders: clickable type-icon + key + title for each ancestor."},
              {"id": "E1.S2.T2", "type": "TASK", "t": "[E1.S2.T2] Recursive parent walking with infinite-loop guard", "p": "HIGH", "a": "react-specialist",
               "d": "Walk parentId via successive useIssue queries up to 5 levels. Hard cap. If a cycle is detected (visited set), stop and emit a console.warn. Test that pathological data does not lock the UI."},
              {"id": "E1.S2.T3", "type": "TASK", "t": "[E1.S2.T3] Visual styling — Linear breadcrumb pattern", "p": "MEDIUM", "a": "react-specialist",
               "d": "Match existing breadcrumb styling in the codebase. Linear-style separators. Inter Variable 510 weight. Each ancestor link clickable → navigates to its detail page."},
          ]},
     ]},
    {"id": "E2", "type": "EPIC", "t": "[E2] Page Integration", "p": "CRITICAL", "a": "react-specialist",
     "d": "Wire the new components into feature/[id] (refactor — no regression) and issues/[id] (enhance — conditional rendering).",
     "children": [
         {"id": "E2.S1", "type": "STORY", "t": "[E2.S1] Refactor feature page (no regression)", "p": "CRITICAL", "a": "react-specialist",
          "d": "Replace inline tree logic in feature/[id]/page.tsx with the extracted <HierarchyTreeSection />. Verify every existing behavior intact.",
          "children": [
              {"id": "E2.S1.T1", "type": "TASK", "t": "[E2.S1.T1] Replace inline tree with <HierarchyTreeSection />", "p": "CRITICAL", "a": "react-specialist",
               "d": "Edit frontend/app/codeboard/feature/[id]/page.tsx. Remove the now-extracted blocks. Replace with single <HierarchyTreeSection issueId={featureId} projectId={projectId} viewKind='feature' />."},
              {"id": "E2.S1.T2", "type": "TASK", "t": "[E2.S1.T2] Chrome diff before/after on CB-2384", "p": "HIGH", "a": "debugger",
               "d": "Take Chrome screenshot of /codeboard/feature/CB-2384 BEFORE refactor. After refactor, take same screenshot. Compare visually — must be byte-identical-ish (allow tiny pixel-level differences from React keys but no layout/UI changes)."},
          ]},
         {"id": "E2.S2", "type": "STORY", "t": "[E2.S2] Enhance issues page (BUG/TASK detail)", "p": "CRITICAL", "a": "react-specialist",
          "d": "Add conditional rendering of <HierarchyTreeSection /> + <ParentBreadcrumb /> on issues/[id]. Preserve existing metadata view.",
          "children": [
              {"id": "E2.S2.T1", "type": "TASK", "t": "[E2.S2.T1] Conditional <HierarchyTreeSection /> when has children", "p": "CRITICAL", "a": "react-specialist",
               "d": "In frontend/app/codeboard/issues/[id]/page.tsx, fetch descendants count via useIssues + filter. If > 0, render <HierarchyTreeSection issueId={id} projectId={projectId} viewKind={lower(issue.type)} />. Position above existing metadata."},
              {"id": "E2.S2.T2", "type": "TASK", "t": "[E2.S2.T2] Conditional <ParentBreadcrumb /> when parentId set", "p": "HIGH", "a": "react-specialist",
               "d": "If issue.parentId is set, render <ParentBreadcrumb issueId={id} /> at the very top of the page (above type+key heading)."},
              {"id": "E2.S2.T3", "type": "TASK", "t": "[E2.S2.T3] Preserve existing metadata + comments + activity (no regression)", "p": "HIGH", "a": "react-specialist",
               "d": "All existing sections on issues/[id] (description, metadata sidebar, comments thread, activity log) must remain untouched. Verify by Chrome diff before/after on a leaf BUG that has no children."},
          ]},
     ]},
    {"id": "E3", "type": "EPIC", "t": "[E3] Backend Confirmation — AutoPilot accepts non-FEATURE parents", "p": "HIGH", "a": "fullstack-developer",
     "d": "Quick smoke test: confirm POST /api/execute/queue accepts a BUG parent. If broken, file scope-creep BUG.",
     "children": [
         {"id": "E3.S1", "type": "STORY", "t": "[E3.S1] AutoPilot endpoint smoke test", "p": "HIGH", "a": "fullstack-developer",
          "d": "Confirm or deny that POST /api/execute/queue with featureId=BUG-id works.",
          "children": [
              {"id": "E3.S1.T1", "type": "TASK", "t": "[E3.S1.T1] Smoke test POST /api/execute/queue with BUG parent", "p": "HIGH", "a": "fullstack-developer",
               "d": "curl POST to start an AutoPilot queue with featureId=fb7fca2d-790c-442d-a976-446ec40d3750 (CB-2671). Verify queue enqueues successfully OR returns clear error. Document result as comment on this task."},
              {"id": "E3.S1.T2", "type": "TASK", "t": "[E3.S1.T2] If broken: file scope-creep BUG; if works: doc as comment on CB-2371", "p": "MEDIUM", "a": "fullstack-developer",
               "d": "Based on T1 result. If endpoint broken, file new BUG under CB-2371 with reproduction. If works, post a comment on CB-2371 confirming + linking the test."},
          ]},
     ]},
    {"id": "E4", "type": "EPIC", "t": "[E4] Tests — Vitest coverage", "p": "HIGH", "a": "react-specialist",
     "d": "4 vitest tests covering the new components.",
     "children": [
         {"id": "E4.S1", "type": "STORY", "t": "[E4.S1] Vitest coverage for new components + integration", "p": "HIGH", "a": "react-specialist",
          "d": "All 4 tests in frontend/__tests__/bug-detail-view.test.tsx (or similar).",
          "children": [
              {"id": "E4.S1.T1", "type": "TASK", "t": "[E4.S1.T1] Test: BUG with children → tree renders with full keys+titles", "p": "HIGH", "a": "react-specialist",
               "d": "Mock useIssue + useIssues. Render issues/[id] for a BUG with 3 mocked children. Assert all 3 child rows render with non-empty key + title. Assert AutoPilot button is present."},
              {"id": "E4.S1.T2", "type": "TASK", "t": "[E4.S1.T2] Test: BUG with parentId → breadcrumb renders correct chain", "p": "HIGH", "a": "react-specialist",
               "d": "Mock useIssue chain (BUG → FEATURE). Render issues/[id]. Assert breadcrumb contains both ancestor + current."},
              {"id": "E4.S1.T3", "type": "TASK", "t": "[E4.S1.T3] Test: AutoPilot button on BUG calls correct endpoint", "p": "MEDIUM", "a": "react-specialist",
               "d": "Mock fetch / useStartExecution. Click AutoPilot button on a BUG. Assert POST /api/execute/queue called with the BUG's id."},
              {"id": "E4.S1.T4", "type": "TASK", "t": "[E4.S1.T4] Test: leaf BUG (no children, no parent) → metadata-only view", "p": "MEDIUM", "a": "react-specialist",
               "d": "Render a BUG with no children + no parentId. Assert NO <HierarchyTreeSection /> rendered. Assert NO <ParentBreadcrumb /> rendered. Assert existing metadata sections still present."},
          ]},
     ]},
    {"id": "E5", "type": "EPIC", "t": "[E5] Audits + Chrome QA", "p": "HIGH", "a": "code-reviewer",
     "d": "code-reviewer + react-specialist audit + Chrome visual QA.",
     "children": [
         {"id": "E5.S1", "type": "STORY", "t": "[E5.S1] code-reviewer pass on full diff", "p": "HIGH", "a": "code-reviewer",
          "d": "Standard review of all modified frontend files.",
          "children": [
              {"id": "E5.S1.T1", "type": "TASK", "t": "[E5.S1.T1] code-reviewer agent on diff", "p": "HIGH", "a": "code-reviewer",
               "d": "Run code-reviewer subagent on all CB-2371 frontend changes. Focus: prop drilling, useEffect dependency lists, memo usage, TypeScript strictness. File CRITICAL/HIGH as child BUGs."},
          ]},
         {"id": "E5.S2", "type": "STORY", "t": "[E5.S2] Chrome visual QA", "p": "CRITICAL", "a": "debugger",
          "d": "Real-world end-to-end visual checks via chrome-devtools-mcp.",
          "children": [
              {"id": "E5.S2.T1", "type": "TASK", "t": "[E5.S2.T1] CB-2671 → parent breadcrumb + 9 children visible", "p": "CRITICAL", "a": "debugger",
               "d": "Navigate Chrome to /codeboard/issues/<CB-2671-id>. Take screenshot. Assert: parent breadcrumb shows CB-1951; 9 child tasks render with keys + titles + statuses."},
              {"id": "E5.S2.T2", "type": "TASK", "t": "[E5.S2.T2] Click AutoPilot on CB-2671 — queue enqueues + advances", "p": "CRITICAL", "a": "debugger",
               "d": "Click AutoPilot button. Assert: queue created (verify via /api/execute/sessions); spinner advances; first child issue moves to IN_PROGRESS."},
              {"id": "E5.S2.T3", "type": "TASK", "t": "[E5.S2.T3] Verify CB-2363 + CB-2365 (existing regression bugs) also work", "p": "HIGH", "a": "debugger",
               "d": "Navigate to CB-2363 and CB-2365 detail pages. Assert: both render their child trees correctly."},
          ]},
         {"id": "E5.S3", "type": "STORY", "t": "[E5.S3] react-specialist sanity audit", "p": "MEDIUM", "a": "react-specialist",
          "d": "React-idiomatic check: hooks usage, key props, memo correctness.",
          "children": [
              {"id": "E5.S3.T1", "type": "TASK", "t": "[E5.S3.T1] Hook + memo audit", "p": "MEDIUM", "a": "react-specialist",
               "d": "Run react-specialist subagent. Check: useEffect cleanup, useMemo dependency completeness, key={} on tree rows, no missing deps."},
          ]},
     ]},
    {"id": "E6", "type": "EPIC", "t": "[E6] Rollout — status hygiene", "p": "MEDIUM", "a": "jonny",
     "d": "Final wrap-up.",
     "children": [
         {"id": "E6.S1", "type": "STORY", "t": "[E6.S1] Status hygiene", "p": "MEDIUM", "a": "jonny",
          "d": "Mark CB-2371 → CWQ; ping Eli.",
          "children": [
              {"id": "E6.S1.T1", "type": "TASK", "t": "[E6.S1.T1] Mark CB-2371 → CWQ when E1-E5 green", "p": "MEDIUM", "a": "jonny",
               "d": "PATCH CB-2371 status=COMPLETED_WAITING_QA. Post summary comment on CB-2371."},
              {"id": "E6.S1.T2", "type": "TASK", "t": "[E6.S1.T2] Update IssueLinks + ping Eli", "p": "LOW", "a": "jonny",
               "d": "Verify IssueLink CB-2371 BLOCKS CB-2671 still present. Ping Eli with summary so he can run AutoPilot from the new BUG view."},
          ]},
     ]},
]


def push_node(node, parent_id):
    print(f"  [{node['type']}] {node['t'][:70]}", end=" ")
    r = create(parent_id, node["type"], node["t"], node["d"], node["p"], node["a"])
    key = r.get("key")
    iid = r.get("id")
    print(f"-> {key}")
    for c in node.get("children", []):
        push_node(c, iid)


def main():
    bug_id = find_id("CB-2371")
    bug_2671_id = find_id("CB-2671")
    print(f"CB-2371 (parent BUG) -> {bug_id}")
    print(f"CB-2671 (blocks)     -> {bug_2671_id}")
    print()

    # Bump priority + status
    print("Bumping CB-2371 priority -> CRITICAL, status -> IN_PROGRESS ...")
    http("PATCH", f"/issues/{bug_id}", {"priority": "CRITICAL", "status": "IN_PROGRESS"})

    # IssueLink BLOCKS
    print("Wiring IssueLink: CB-2371 BLOCKS CB-2671 ...")
    try:
        http("POST", f"/issues/{bug_id}/relations", {"toIssueId": bug_2671_id, "linkType": "BLOCKS"})
        print("  OK")
    except urllib.error.HTTPError:
        print("  (link may already exist)")
    print()

    print("Pushing hierarchy ...")
    for node in HIERARCHY:
        push_node(node, bug_id)
    print()
    print("Done.")


if __name__ == "__main__":
    main()
