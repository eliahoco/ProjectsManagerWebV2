#!/usr/bin/env python3
"""CB-2814 agile-plan push — 6 EPICs, 13 STORIES, 30 TASKs under the BUG.

Filed under bug parent CB-2814 (c81b7394-afe0-4ca2-9d35-1a3b3051a045).
Run from anywhere; reads no env. Idempotent-by-key labels handled out-of-band.
"""
import json
import urllib.request

API = "http://localhost:8401/api"
PROJECT = "1511e54f71dccd3fa79f67fe"
ROOT = "c81b7394-afe0-4ca2-9d35-1a3b3051a045"  # CB-2814
LABEL = "cb-2814-fix"

# Effort scale (minutes)
XS, S, M, L, XL = 30, 120, 240, 480, 960

# Each entry: (label, type, priority, title, description, effort_minutes, agent)
# Children listed under their parent via nested structure.
TREE = [
    # ── EPIC 4 ── qa-regression skill (build first) ──────────────────────
    {
        "type": "EPIC", "priority": "HIGH",
        "title": "E4 — qa-regression skill (new)",
        "description": (
            "Build ~/.claude/skills/qa-regression/SKILL.md + reference templates. "
            "Encodes the 7-stage QA + regression pipeline so every fix runs the "
            "same gate before status flips to COMPLETED_WAITING_QA.\n\n"
            "Modeled on guycoful/validate-skill (MIT) pattern, adapted for Jonny's "
            "bible. User-level skill — not in repo."
        ),
        "effort": M, "agent": "general-purpose",
        "children": [
            {"type": "STORY", "priority": "HIGH", "title": "S4.1 — Skill body",
             "description": "Core SKILL.md plus templates. Self-contained — no project bindings yet (those live in PROJECT/CLAUDE.md per Rule 31).",
             "effort": M, "agent": "general-purpose",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T4.1.1 — Write ~/.claude/skills/qa-regression/SKILL.md",
                  "description": "Frontmatter (name, description, triggers). 7-stage pipeline body. Output contract.",
                  "effort": S, "agent": "general-purpose"},
                 {"type": "TASK", "priority": "MEDIUM", "title": "T4.1.2 — Reference templates",
                  "description": "templates/ac-matrix.md, regression-matrix.md, destructive-tests.md, signoff-block.md.",
                  "effort": S, "agent": "general-purpose"},
                 {"type": "TASK", "priority": "LOW", "title": "T4.1.3 — Credit guycoful/validate-skill",
                  "description": "MIT-license credit + acknowledgement in SKILL.md header.",
                  "effort": XS, "agent": "general-purpose"},
             ]},
            {"type": "STORY", "priority": "MEDIUM", "title": "S4.2 — Self-integration test",
             "description": "Dry-run the skill on a synthetic AC checklist to confirm shape.",
             "effort": S, "agent": "general-purpose",
             "children": [
                 {"type": "TASK", "priority": "MEDIUM", "title": "T4.2.1 — Synthetic dry-run",
                  "description": "Invoke skill against a 3-AC sample; verify output structure.",
                  "effort": S, "agent": "general-purpose"},
             ]},
        ],
    },

    # ── EPIC 6 ── Bible + project-bible propagation ───────────────────────
    {
        "type": "EPIC", "priority": "HIGH",
        "title": "E6 — Bible Rules 30+31 + PROJECT/CLAUDE.md propagation",
        "description": (
            "Two new immutable rules on Jonny + propagate to PMv2's CLAUDE.md:\n"
            "Rule 30 — qa-regression skill invocation gate before CWQ flip.\n"
            "Rule 31 — design-intent comments must cite doc+line (else removed)."
        ),
        "effort": M, "agent": "general-purpose",
        "children": [
            {"type": "TASK", "priority": "HIGH", "title": "T6.1 — Jonny SKILL.md +Rule 30",
             "description": "Add Rule 30: After any code fix, invoke qa-regression skill BEFORE CWQ flip.",
             "effort": XS, "agent": "general-purpose"},
            {"type": "TASK", "priority": "HIGH", "title": "T6.2 — Jonny SKILL.md +Rule 31",
             "description": "Add Rule 31: Design-intent comments must cite doc+line; otherwise removed.",
             "effort": XS, "agent": "general-purpose"},
            {"type": "TASK", "priority": "MEDIUM", "title": "T6.3 — bible-extended.md rationale",
             "description": "Expand Rules 30+31 with rationale + examples (CB-2814 case study for Rule 31).",
             "effort": S, "agent": "general-purpose"},
            {"type": "TASK", "priority": "HIGH", "title": "T6.4 — PROJECT/CLAUDE.md QA Pipeline section",
             "description": "Add QA Pipeline section binding qa-regression skill to PMv2's test commands + dev URLs.",
             "effort": S, "agent": "general-purpose"},
            {"type": "TASK", "priority": "MEDIUM", "title": "T6.5 — PROJECT/CLAUDE.md Design-Intent Comments note",
             "description": "Add note pointing at docs/plans/ as the citation source. Reference CB-2814 root cause.",
             "effort": XS, "agent": "general-purpose"},
        ],
    },

    # ── EPIC 1 ── Store refactor + persistence ────────────────────────────
    {
        "type": "EPIC", "priority": "HIGH",
        "title": "E1 — useStudioStore refactor + persistence",
        "description": (
            "Reshape state: tabs+activeTabId per-project; drafts+sendCounters stay flat "
            "(CUIDs globally unique). Persist all four. Migrate key v1→v2. Remove the "
            "false 'intentional per architecture doc' comment."
        ),
        "effort": M, "agent": "react-specialist",
        "children": [
            {"type": "STORY", "priority": "HIGH", "title": "S1.1 — State shape",
             "description": "Per-project maps for tabs + activeTabId; drafts+sendCounters flat.",
             "effort": S, "agent": "react-specialist",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T1.1.1 — Add tabsByProject + activeTabIdByProject",
                  "description": "Record<string, TabState[]> and Record<string, string|null> on store state.",
                  "effort": S, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "HIGH", "title": "T1.1.2 — Actions take projectId first arg",
                  "description": "openTab/closeTab/setActiveTab/updateTab.",
                  "effort": S, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "LOW", "title": "T1.1.3 — Keep drafts + sendCounters flat",
                  "description": "SessionIds are CUIDs — no project key needed.",
                  "effort": XS, "agent": "react-specialist"},
             ]},
            {"type": "STORY", "priority": "HIGH", "title": "S1.2 — Persistence config",
             "description": "Rename key, expand partialize, add version+migrate.",
             "effort": S, "agent": "react-specialist",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T1.2.1 — Rename studio-panel-v1 → studio-state-v2",
                  "description": "Old key has only panelRatio; safe to drop.",
                  "effort": XS, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "HIGH", "title": "T1.2.2 — partialize: 5 fields",
                  "description": "panelRatio + tabsByProject + activeTabIdByProject + drafts + sendCounters.",
                  "effort": XS, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "HIGH", "title": "T1.2.3 — version:2 + migrate() corruption guard",
                  "description": "Drop v1 cleanly; fall back to empty state on shape mismatch; never crash.",
                  "effort": S, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "MEDIUM", "title": "T1.2.4 — Remove false comment; cite E2.S2.T5",
                  "description": "Replace 'intentional per architecture doc' with citation to master plan E2.S2.T5.",
                  "effort": XS, "agent": "react-specialist"},
             ]},
        ],
    },

    # ── EPIC 2 ── Hydration + stale cleanup ───────────────────────────────
    {
        "type": "EPIC", "priority": "HIGH",
        "title": "E2 — Hydration + stale-tab cleanup",
        "description": "On mount, reconcile persisted tab ids against backend session list. Prune missing.",
        "effort": M, "agent": "react-specialist",
        "children": [
            {"type": "STORY", "priority": "HIGH", "title": "S2.1 — Backend session reconciliation",
             "description": "New hook + mount-point.",
             "effort": S, "agent": "react-specialist",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T2.1.1 — useStudioTabsHydration(projectId)",
                  "description": "Fetch sessions, diff, prune stale tabs via closeTab.",
                  "effort": S, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "MEDIUM", "title": "T2.1.2 — Mount in StudioPage.tsx",
                  "description": "Idempotent — runs once on mount + on projectId change.",
                  "effort": XS, "agent": "react-specialist"},
             ]},
            {"type": "STORY", "priority": "MEDIUM", "title": "S2.2 — Stub-ID guard",
             "description": "Reject stub-* IDs from persisted state; defense-in-depth on hydrate.",
             "effort": S, "agent": "react-specialist",
             "children": [
                 {"type": "TASK", "priority": "MEDIUM", "title": "T2.2.1 — partialize strips stub-*",
                  "description": "Filter tabsByProject entries whose id startsWith('stub-').",
                  "effort": XS, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "LOW", "title": "T2.2.2 — migrate() also drops stub-*",
                  "description": "Defense-in-depth on rehydration.",
                  "effort": XS, "agent": "react-specialist"},
             ]},
        ],
    },

    # ── EPIC 3 ── Consumer migration ──────────────────────────────────────
    {
        "type": "EPIC", "priority": "HIGH",
        "title": "E3 — Consumer migration (4 files)",
        "description": "Update all useStudioStore consumers to pass projectId.",
        "effort": S, "agent": "react-specialist",
        "children": [
            {"type": "TASK", "priority": "HIGH", "title": "T3.1 — StudioPage.tsx scoped reads",
             "description": "Read tabs/activeTabId from useTenant().projectId.",
             "effort": XS, "agent": "react-specialist"},
            {"type": "TASK", "priority": "HIGH", "title": "T3.2 — ConversationTabBar.tsx scoped reads",
             "description": "Same.",
             "effort": XS, "agent": "react-specialist"},
            {"type": "TASK", "priority": "LOW", "title": "T3.3 — Chat.tsx unchanged",
             "description": "drafts/sendCounters stay flat. Verify no regression.",
             "effort": XS, "agent": "react-specialist"},
            {"type": "TASK", "priority": "MEDIUM", "title": "T3.4 — __tests__/StudioPage.test.tsx mock update",
             "description": "Update Zustand mock to new shape.",
             "effort": XS, "agent": "react-specialist"},
        ],
    },

    # ── EPIC 5 ── Verify CB-2814 via the new skill ────────────────────────
    {
        "type": "EPIC", "priority": "HIGH",
        "title": "E5 — Verify CB-2814 via qa-regression skill",
        "description": "Run the new skill end-to-end on this very fix. 11 ACs + automated + destructive + audits + sign-off.",
        "effort": L, "agent": "general-purpose",
        "children": [
            {"type": "STORY", "priority": "HIGH", "title": "S5.1 — Automated tests",
             "description": "vitest unit + integration.",
             "effort": M, "agent": "react-specialist",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T5.1.1 — useStudioStore.test.ts",
                  "description": "Per-project isolation, MAX_TABS per project, corrupt-localStorage fallback, stub-ID rejection.",
                  "effort": M, "agent": "react-specialist"},
                 {"type": "TASK", "priority": "MEDIUM", "title": "T5.1.2 — ConversationTabBar.test.tsx",
                  "description": "Scoped render; project-switch swap.",
                  "effort": S, "agent": "react-specialist"},
             ]},
            {"type": "STORY", "priority": "HIGH", "title": "S5.2 — Manual AC matrix (11 ACs)",
             "description": "Chrome MCP — drive each AC, screenshot evidence.",
             "effort": M, "agent": "general-purpose",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T5.2.1 — Execute 11 ACs dark+light",
                  "description": "AC-1..AC-11 from QA plan. Evidence per AC.",
                  "effort": M, "agent": "general-purpose"},
             ]},
            {"type": "STORY", "priority": "MEDIUM", "title": "S5.3 — Destructive tests",
             "description": "Corrupt localStorage / private window / mid-stream refresh.",
             "effort": S, "agent": "general-purpose",
             "children": [
                 {"type": "TASK", "priority": "MEDIUM", "title": "T5.3.1 — Destructive trio",
                  "description": "Each must not crash; expected fallback observed.",
                  "effort": S, "agent": "general-purpose"},
             ]},
            {"type": "STORY", "priority": "HIGH", "title": "S5.4 — Audit gates",
             "description": "code-reviewer + security-auditor on diff.",
             "effort": S, "agent": "general-purpose",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T5.4.1 — code-reviewer agent",
                  "description": "Full diff review; verdict PASS/PASS-WITH-NITS/FAIL.",
                  "effort": S, "agent": "code-reviewer"},
                 {"type": "TASK", "priority": "MEDIUM", "title": "T5.4.2 — security-auditor",
                  "description": "localStorage scope; verify drafts/sendCounters don't leak PII; CUIDs non-secret.",
                  "effort": S, "agent": "security-auditor"},
             ]},
            {"type": "STORY", "priority": "HIGH", "title": "S5.5 — Sign-off + commit",
             "description": "Skill emits verdict; mark CB-2814 → CWQ; commit.",
             "effort": S, "agent": "general-purpose",
             "children": [
                 {"type": "TASK", "priority": "HIGH", "title": "T5.5.1 — qa-regression sign-off block emitted",
                  "description": "PASS/PASS-WITH-NITS/FAIL with file:line evidence per AC.",
                  "effort": XS, "agent": "general-purpose"},
                 {"type": "TASK", "priority": "HIGH", "title": "T5.5.2 — Mark CB-2814 CWQ + git commit",
                  "description": "Status flip + commit message referencing E1-E6.",
                  "effort": XS, "agent": "general-purpose"},
             ]},
        ],
    },
]


def post(path, payload):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def push(node, parent_id, depth=0):
    payload = {
        "title": node["title"],
        "description": node["description"],
        "type": node["type"],
        "priority": node["priority"],
        "parentId": parent_id,
        "labels": LABEL,
        "reporter": "AI",
        "estimate": node.get("effort"),
        "assignee": node.get("agent"),
    }
    issue = post(f"/projects/{PROJECT}/issues", payload)
    key = issue.get("key", "?")
    iid = issue.get("id")
    indent = "  " * depth
    print(f"{indent}{key}  [{node['type']}]  {node['title'][:70]}")
    for child in node.get("children", []):
        push(child, iid, depth + 1)
    return iid


def main():
    print("Pushing CB-2814 agile plan — 6 EPICs under bug parent...\n")
    for epic in TREE:
        push(epic, ROOT)
    print("\nDone.")


if __name__ == "__main__":
    main()
