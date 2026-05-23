#!/usr/bin/env python3
"""Push CB-3001 Studio Workspace Surfaces plan.

10 net-new project-scoped sub-features that hang off the StudioSidebar.
Eli direction 2026-05-23 — file the plan for LATER (after CB-2914 SIE
core is signed off). Rule 32: tables, agent per task, mandatory audit + QA + regression epics.
"""
import json
import urllib.request

API = "http://localhost:8401/api"
PID = "1511e54f71dccd3fa79f67fe"
LABEL = "studio-workspace"
FEATURE_ID = "efbec42a-eab7-4ae1-8151-0f5be2747c66"
FEATURE_KEY = "CB-3001"


def post(path, body):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def issue(title, type_, priority, description, parent_id, assignee=None, est=None):
    body = {
        "title": title, "type": type_, "priority": priority,
        "description": description, "reporter": "AI",
        "labels": LABEL, "parentId": parent_id,
    }
    if assignee:
        body["assignee"] = assignee
    if est is not None:
        body["estimateMinutes"] = est
    return post(f"/projects/{PID}/issues", body)


def epic(n, title, owner, desc, est):
    return issue(f"E{n} — {title}", "EPIC", "HIGH", desc, FEATURE_ID, owner, est)


def story(parent, ident, title, owner, desc, est):
    return issue(f"{ident} — {title}", "STORY", "MEDIUM", desc, parent, owner, est)


def task(parent, ident, title, owner, est, desc=None):
    return issue(f"{ident} — {title}", "TASK", "MEDIUM", desc or title, parent, owner, est)


print(f"FEATURE: {FEATURE_KEY}")

# E0 — Shell: StudioSidebar component + conditional routing
e0 = epic(0, "StudioSidebar shell + conditional rendering", "react-specialist",
         "When pathname starts with /workspace/*/studio, replace global Sidebar with StudioSidebar. Project picker stays at top.", 240)
print(f"  {e0['key']} E0 shell")
s00 = story(e0['id'], "S0.1", "StudioSidebar component", "react-specialist", "List of 13 menu items with active-state highlighting.", 240)
for t in [
    ("T0.1.1", "StudioSidebar.tsx — list of 13 items + active route highlight", "react-specialist", 90),
    ("T0.1.2", "Conditional render in app/layout.tsx based on pathname", "react-specialist", 60),
    ("T0.1.3", "Project picker dropdown at top (reuses useTenant)", "react-specialist", 45),
    ("T0.1.4", "Theme-aware styling + a11y (focus rings, keyboard nav)", "react-specialist", 45),
]:
    task(s00['id'], *t)

# E1-E10 — Per-sub-feature epics
SUB_FEATURES = [
    (1, "Studio Dashboard", "react-specialist + python-pro",
     "Project-scoped overview — counts (sessions, artifacts, agents active), recent activity, cost rollup.",
     "/studio/dashboard"),
    (2, "Agents page", "react-specialist + python-pro",
     "List 31 agents + filter by source + search. Per row: Assign action opens new Studio chat tab with @agent pre-inserted.",
     "/studio/agents"),
    (3, "Skills page", "react-specialist + python-pro",
     "List 63 skills + filter by plugin source + search. Per row: Assign action opens new chat tab with /skill pre-inserted.",
     "/studio/skills"),
    (4, "Visualizer", "react-specialist",
     "Mermaid + hierarchy_json artifact renderer. Open artifact -> rendered in fullscreen workspace.",
     "/studio/visualizer"),
    (5, "Mockup Studio", "react-specialist + frontend-design",
     "Component mockup workspace. Generate UI mockup -> preview iframe + JSX source.",
     "/studio/mockups"),
    (6, "Workflows", "react-specialist + python-pro",
     "Project-scoped AutoPilot queue view. List queues + sessions + transitions.",
     "/studio/workflows"),
    (7, "Compare", "react-specialist",
     "Diff two artifacts (markdown / code / hierarchy_json). Side-by-side rendering.",
     "/studio/compare"),
    (8, "Artifacts", "react-specialist + python-pro",
     "List + view StudioArtifact rows. Already in DB; UI lacking. Open per-artifact view.",
     "/studio/artifacts"),
    (9, "Specs", "react-specialist + python-pro",
     "PRDs / specs storage. Markdown editor + versioning.",
     "/studio/specs"),
    (10, "Context", "react-specialist + python-pro",
     "Project context docs (architecture overview, glossary, dependencies). Plus RAG-indexed.",
     "/studio/context"),
    (11, "Memory", "react-specialist + python-pro",
     "Session memory + RAG view. Browse what the project remembers across sessions.",
     "/studio/memory"),
]

for n, name, owner, desc, route in SUB_FEATURES:
    e = epic(n, name, owner, f"{desc}\n\nRoute: `{route}`", 360)
    print(f"  {e['key']} E{n} {name}")
    s_be = story(e['id'], f"S{n}.1", "Backend route + data layer", "python-pro", "API + DB schema as needed.", 120)
    task(s_be['id'], f"T{n}.1.1", "Backend endpoint(s)", "python-pro", 60)
    task(s_be['id'], f"T{n}.1.2", "Data model / schema additions if any", "python-pro", 60)
    s_fe = story(e['id'], f"S{n}.2", f"{name} page UI", "react-specialist", "Next.js App Router page + React Query.", 180)
    task(s_fe['id'], f"T{n}.2.1", f"app/studio/{name.lower().replace(' ', '-')}/page.tsx", "react-specialist", 120)
    task(s_fe['id'], f"T{n}.2.2", "List + detail components", "react-specialist", 60)
    s_qa = story(e['id'], f"S{n}.3", "QA per sub-feature (Rule 30)", "qa-regression-skill", "Stage 1-5 qa-regression run per sub-feature.", 60)
    task(s_qa['id'], f"T{n}.3.1", "AC matrix + automated + Chrome MCP manual", "qa-regression-skill", 60)

# Mandatory boilerplate epics per Rule 32
ea = epic(12, "Code Audit Epic (MANDATORY Rule 32)", "code-reviewer",
         "code-reviewer + security-auditor on the StudioSidebar + every sub-feature diff. 0 CRITICAL / 0 HIGH gate.", 120)
print(f"  {ea['key']} E12 audit")
story(ea['id'], "S12.1", "code-reviewer on full diff", "code-reviewer", "Severity counts + CORRECTLY-IDENTIFIED strengths.", 60)
story(ea['id'], "S12.2", "security-auditor on cross-surface boundaries", "security-auditor", "Multi-tenant + access control + secret redaction.", 60)

eq = epic(13, "QA Epic — qa-regression skill (MANDATORY Rule 30+32)", "qa-regression-skill",
         "7-stage pipeline per sub-feature.", 360)
print(f"  {eq['key']} E13 QA")
for ident, title, est in [
    ("S13.1", "Stage 1-2 — AC matrix + automated", 60),
    ("S13.2", "Stage 3 — Chrome MCP manual (light + dark, 2 projects)", 120),
    ("S13.3", "Stage 4 — adjacent-flow regression sweep", 60),
    ("S13.4", "Stage 5 — destructive (corrupt state / private window / cross-tenant probe)", 60),
    ("S13.5", "Stage 7 — sign-off block to CB-3001", 60),
]:
    story(eq['id'], ident, title, "qa-regression-skill", title, est)

er = epic(14, "Full Regression Epic + 5 user-regression phases (MANDATORY Rule 32)", "qa-regression-skill",
         "Per-sub-feature + cross-feature regression.", 360)
print(f"  {er['key']} E14 regression")
for ident, title, est in [
    ("S14.1", "Existing CodeBoard / AutoPilot / CB-2814 tab persistence still works", 60),
    ("S14.2", "User-regression phase 1 — happy path end-to-end", 60),
    ("S14.3", "User-regression phase 2 — error recovery (network blip mid-action)", 60),
    ("S14.4", "User-regression phase 3 — multi-step UI-only workflow", 60),
    ("S14.5", "User-regression phase 4 — cross-project repeat", 60),
    ("S14.6", "User-regression phase 5 — stress (5+ concurrent sessions)", 60),
]:
    story(er['id'], ident, title, "qa-regression-skill", title, est)

print("\nCB-3001 plan pushed. Defer until CB-2914 SIE core signed off.")
