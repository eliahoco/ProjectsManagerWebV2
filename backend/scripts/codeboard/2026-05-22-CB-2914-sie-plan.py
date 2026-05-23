#!/usr/bin/env python3
"""Push CB-2914 Studio Investigation Engine plan to CodeBoard.

Eli approved 2026-05-22. 12 epics: E0 dispatcher → E11 user-regression.
"""
import json
import urllib.request

API = "http://localhost:8401/api"
PID = "1511e54f71dccd3fa79f67fe"
LABEL = "sie"
FEATURE_ID = "713146a5-9f05-4f06-badf-4d2afcb2eacc"
FEATURE_KEY = "CB-2914"


def post(path, body):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def issue(title, type_, priority, description, parent_id, assignee=None, estimate=None):
    body = {
        "title": title,
        "type": type_,
        "priority": priority,
        "description": description,
        "reporter": "AI",
        "labels": LABEL,
        "parentId": parent_id,
    }
    if assignee:
        body["assignee"] = assignee
    if estimate is not None:
        body["estimateMinutes"] = estimate
    return post(f"/projects/{PID}/issues", body)


def epic(num, title, assignee, desc, est):
    return issue(f"E{num} — {title}", "EPIC", "HIGH", desc, FEATURE_ID, assignee, est)


def story(parent_id, ident, title, assignee, desc, est):
    return issue(f"{ident} — {title}", "STORY", "HIGH", desc, parent_id, assignee, est)


def task(parent_id, ident, title, assignee, *args):
    """Flexible: accepts (est) or (desc, est) or (est, desc)."""
    desc = title
    est = 30
    for a in args:
        if isinstance(a, int):
            est = a
        elif isinstance(a, str):
            desc = a
    return issue(f"{ident} — {title}", "TASK", "HIGH", desc, parent_id, assignee, est)


print(f"FEATURE: {FEATURE_KEY}")

# ---- E0 — Dispatcher service (already created via earlier run, kids already pushed) ----
e0 = {"id": "cf95e9de-bd67-4403-88e5-c864325c546c", "key": "CB-2915"}
print(f"  {e0['key']} E0 (existing, kids already pushed)")

# ---- E1 — Trigger plumbing (epic + S1.1 already exist) ----
e1 = {"id": "d4e91f8a-1a8e-4f88-b6b3-7d6a8e267048", "key": "CB-2923"}  # epic
s10 = {"id": None, "key": "CB-2924"}  # S1.1 — fetch by key
# Resolve S1.1 id
_resp = urllib.request.urlopen(f"{API}/projects/{PID}/issues?page=1&pageSize=300", timeout=20)
_items = json.loads(_resp.read().decode()).get('items', [])
for _i in _items:
    if _i.get('key') == 'CB-2924': s10['id'] = _i['id']
    if _i.get('key') == 'CB-2923': e1['id'] = _i['id']
print(f"  {e1['key']} E1 (existing); S1.1={s10['key']} id={s10['id'][:6]}")
task(s10['id'], "T1.1.1", "Pydantic InvestigationRequest model", "python-pro", 30, "trigger_source, description, projectId, sessionId, evidence?")
task(s10['id'], "T1.1.2", "DB table investigation_requests + Alembic migration", "python-pro", 30, "Persistent audit row per request.")
s11 = story(e1['id'], "S1.2", "5 trigger sources", "python-pro", "Each emits identical event shape.", 180)
for t in [
    ("T1.2.1", "Studio chat intent → InvestigationRequest", "python-pro", 45),
    ("T1.2.2", "qa-regression FAIL → InvestigationRequest", "python-pro", 30),
    ("T1.2.3", "AutoPilot impl failure → InvestigationRequest", "python-pro", 30),
    ("T1.2.4", "Manual CB BUG ticket → InvestigationRequest (webhook on issue create)", "python-pro", 45),
    ("T1.2.5", "Runtime error via execution monitor → InvestigationRequest", "python-pro", 30),
]:
    task(s11['id'], *t)

# ---- E2 — Orchestrator ----
e2 = epic(2, "Investigation orchestrator", "python-pro", "Parallel asyncio.gather dispatch, 90s/agent timeout, partial results tolerated.", 240)
print(f"  {e2['key']} E2")
s20 = story(e2['id'], "S2.1", "Orchestrator core", "python-pro", "investigation_engine.py with run(request)", 180)
for t in [
    ("T2.1.1", "InvestigationEngine.run(request) -> InvestigationResult", "python-pro", 60),
    ("T2.1.2", "Parallel asyncio.gather across layer-investigators", "python-pro", 45),
    ("T2.1.3", "Per-agent 90s timeout via asyncio.wait_for", "python-pro", 30),
    ("T2.1.4", "Partial-result tolerance — failed/timeout layers marked UNAVAILABLE in result", "python-pro", 45),
]:
    task(s20['id'], *t)

# ---- E3 — Layer agents ----
e3 = epic(3, "Layer-specific investigation agents (6 layers)", "ai-engineer", "arch / code / DB / UI / runtime / security investigators. Each returns LayerReport.", 720)
print(f"  {e3['key']} E3")
for ident, title, owner, desc, est in [
    ("S3.1", "architecture-investigator (atlas + general-purpose)", "ai-engineer", "Reads master plan + Atlas index; maps cross-module impact.", 120),
    ("S3.2", "code-investigator (code-reviewer read-only)", "code-reviewer", "Greps suspect files; identifies suspect functions + lines.", 120),
    ("S3.3", "database-investigator (new — sqlite3 wrapper)", "python-pro", "Queries tables; verifies row counts, schema, recent rows.", 120),
    ("S3.4", "ui-investigator (bug-repro skill + Chrome MCP)", "python-pro", "Drives failing user flow live; captures DOM/console/network/screenshot.", 120),
    ("S3.5", "runtime-investigator (debugger agent)", "debugger", "Reads backend logs; correlates stack traces with user action.", 120),
    ("S3.6", "security-investigator (security-auditor, conditional)", "security-auditor", "Runs only if surface touches auth/data/multi-tenant/secrets.", 120),
]:
    story(e3['id'], ident, title, owner, desc, est)

# ---- E4 — Synthesizer ----
e4 = epic(4, "Synthesizer — 5-part deliverable composer", "ai-engineer", "Composes storytelling + agile plan + agent assignments + owners + QA/regression plan from LayerReports.", 300)
print(f"  {e4['key']} E4")
s40 = story(e4['id'], "S4.1", "Synthesizer core", "ai-engineer", "deliverable_composer.py", 300)
for t in [
    ("T4.1.1", "Part 1 — storytelling narrative (LLM-composed, 250 words max)", "ai-engineer", 60),
    ("T4.1.2", "Part 2 — agile plan (FEATURE→EPIC→STORY→TASK tables, Rule 32)", "ai-engineer", 90),
    ("T4.1.3", "Part 3 — agent + skill assignments table", "ai-engineer", 45),
    ("T4.1.4", "Part 4 — explicit owner per leaf task (flat summary)", "ai-engineer", 30),
    ("T4.1.5", "Part 5 — QA + regression + user-regression plan tables", "ai-engineer", 75),
]:
    task(s40['id'], *t)

# ---- E5 — Pattern C UI ----
e5 = epic(5, "Pattern C UI — capability ribbon + mentions + cycle panel", "react-specialist", "Discoverable + power-user fast + visible SIE picker.", 720)
print(f"  {e5['key']} E5")
s50 = story(e5['id'], "S5.1", "Suggest endpoint + hook", "python-pro", "GET /api/studio/capabilities/suggest + useCapabilitySuggestions React Query hook.", 180)
for t in [
    ("T5.1.1", "GET /api/studio/capabilities/suggest endpoint (server-side ranking)", "python-pro", 90),
    ("T5.1.2", "useCapabilitySuggestions React Query hook (5s stale)", "react-specialist", 45),
    ("T5.1.3", "Relevance algorithm (trigger keywords + stack hints + history + pins)", "ai-engineer", 45),
]:
    task(s50['id'], *t)
s51 = story(e5['id'], "S5.2", "Ribbon + mentions UI components", "react-specialist", "Capability ribbon, mention dropdown, mention chip, capability drawer.", 360)
for t in [
    ("T5.2.1", "CapabilityRibbon.tsx (24px, top-7 contextual, theme-aware)", "react-specialist", 120),
    ("T5.2.2", "MentionDropdown.tsx (@/ autocomplete, fuzzy search)", "react-specialist", 120),
    ("T5.2.3", "MentionChip.tsx (inline pill, kbd nav, removable)", "react-specialist", 60),
    ("T5.2.4", "CapabilityDrawer.tsx (full 94 items, categorized, pinning)", "react-specialist", 60),
]:
    task(s51['id'], *t)
s52 = story(e5['id'], "S5.3", "InvestigationCyclePanel.tsx", "react-specialist", "Replaces AgentActivityPanel when SIE cycle running. Streams per-agent progress.", 180)
for t in [
    ("T5.3.1", "Panel component + agent progress states (queued|running|completed|failed)", "react-specialist", 90),
    ("T5.3.2", "Wire to InvestigationRequest events via SSE", "react-specialist", 60),
    ("T5.3.3", "5-part deliverable artifact handoff", "react-specialist", 30),
]:
    task(s52['id'], *t)

# ---- E6 — Auto-urgency ----
e6 = epic(6, "Auto-urgency + label classifier", "ai-engineer", "Rubric+LLM hybrid. Impact + scope + surface → LOW/MED/HIGH/CRITICAL.", 180)
print(f"  {e6['key']} E6")
s60 = story(e6['id'], "S6.1", "Classifier + rubric", "ai-engineer", "urgency_classifier.py with rationale-logged scoring.", 180)
for t in [
    ("T6.1.1", "Rubric scorer (production-down, security, scope, workaround)", "ai-engineer", 60),
    ("T6.1.2", "LLM tiebreak when score in [MED, HIGH] borderline", "ai-engineer", 60),
    ("T6.1.3", "Rationale logged into deliverable + CB ticket description", "ai-engineer", 30),
    ("T6.1.4", "Label auto-pick from affected modules (e.g. studio-tabs, autopilot)", "ai-engineer", 30),
]:
    task(s60['id'], *t)

# ---- E7 — CodeBoard write integration ----
e7 = epic(7, "CodeBoard write integration", "python-pro", "After user approves deliverable, SIE walks plan top-down and files via create_codeboard_issue.", 180)
print(f"  {e7['key']} E7")
s70 = story(e7['id'], "S7.1", "Approval + push pipeline", "python-pro", "User confirms → SIE files FEATURE, then EPICs, then STORYs/TASKs in order.", 180)
for t in [
    ("T7.1.1", "Approval gate UI button + server-side check", "react-specialist", 60),
    ("T7.1.2", "Top-down filer — walks plan tree, files via create_codeboard_issue", "python-pro", 90),
    ("T7.1.3", "Idempotency — re-running same deliverable does not duplicate", "python-pro", 30),
]:
    task(s70['id'], *t)

# ---- E8 — CLI skill parity ----
e8 = epic(8, "CLI skill parity (~/.claude/skills/investigation/)", "llm-architect", "Terminal /investigate runs same orchestrator via Task tool subagents.", 180)
print(f"  {e8['key']} E8")
s80 = story(e8['id'], "S8.1", "investigation skill spec + bindings", "llm-architect", "SKILL.md + reference templates.", 180)
for t in [
    ("T8.1.1", "~/.claude/skills/investigation/SKILL.md", "llm-architect", 90),
    ("T8.1.2", "References templates (5-part deliverable + agent registry)", "llm-architect", 60),
    ("T8.1.3", "Bind to Jonny Rule 28 (replace bug-repro-only flow with SIE)", "llm-architect", 30),
]:
    task(s80['id'], *t)

# ---- E9 — Code audit (MANDATORY Rule 32) ----
e9 = epic(9, "Code Audit Epic (MANDATORY Rule 32)", "code-reviewer", "0 CRITICAL / 0 HIGH; bias-correction; strengths surfaced.", 120)
print(f"  {e9['key']} E9")
story(e9['id'], "S9.1", "code-reviewer on full diff", "code-reviewer", "Severity counts + CORRECTLY-IDENTIFIED strengths.", 60)
story(e9['id'], "S9.2", "security-auditor on dispatcher + write surface", "security-auditor", "Subprocess injection, tenant scoping, secret leakage.", 60)

# ---- E10 — QA (MANDATORY Rule 30+32) ----
e10 = epic(10, "QA Epic — qa-regression skill (MANDATORY Rule 30+32)", "qa-regression-skill", "7-stage pipeline. PASS / PASS-WITH-NITS allows CWQ flip.", 300)
print(f"  {e10['key']} E10")
for ident, title, est, desc in [
    ("S10.1", "Stage 1 — AC matrix from bug-repro evidence", 30, ">=3 binary ACs"),
    ("S10.2", "Stage 2 — automated tests (vitest + pytest + tsc)", 60, "All green"),
    ("S10.3", "Stage 3 — Chrome MCP manual run", 120, "Every AC live; light+dark; multi-project"),
    ("S10.4", "Stage 5 — destructive (cycle abort, hung agent, agent junk, network blip, cross-tenant)", 60, "All PASS"),
    ("S10.5", "Stage 7 — sign-off block to CB-2914", 30, "Verdict comment posted"),
]:
    story(e10['id'], ident, title, "qa-regression-skill", desc, est)

# ---- E11 — Full regression + user-regression ----
e11 = epic(11, "Full Regression Epic + 5 user-regression phases (MANDATORY Rule 32)", "qa-regression-skill", "Adjacent flows + scripted user journeys end-to-end.", 360)
print(f"  {e11['key']} E11")
for ident, title, est, desc in [
    ("S11.1", "Adjacent-flow smoke (Stage 4)", 30, "Existing flows unbroken"),
    ("S11.2", "Destructive cases (Stage 5)", 30, "Corrupt state / private window / network blip"),
    ("S11.3", "User-regression phase 1 — HAPPY PATH end-to-end (Chrome MCP)", 60, "Bug-report → investigation → 5-part deliverable → file → see ticket in CodeBoard"),
    ("S11.4", "User-regression phase 2 — ERROR RECOVERY (network fails mid-cycle, agent times out)", 60, "User sees graceful degradation, can retry"),
    ("S11.5", "User-regression phase 3 — MULTI-STEP WORKFLOW (only via UI, no curl)", 60, "Full feature planning completed via Studio"),
    ("S11.6", "User-regression phase 4 — CROSS-PROJECT (repeat happy path in 2nd project)", 60, "Multi-tenant boundary respected"),
    ("S11.7", "User-regression phase 5 — STRESS (many concurrent sessions, no degradation)", 60, "5+ tabs, 3+ concurrent investigations"),
]:
    story(e11['id'], ident, title, "qa-regression-skill", desc, est)

print("\nALL 12 EPICS PUSHED.")
