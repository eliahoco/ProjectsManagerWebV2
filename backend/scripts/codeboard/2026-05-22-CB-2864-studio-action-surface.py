#!/usr/bin/env python3
"""Push CB-2864 Studio Jonny Action Surface plan to CodeBoard.

Eli approved 2026-05-22. 7 epics: E1-E4 implementation + E5 audit + E6 QA + E7 regression.
"""
import json, urllib.request

API = "http://localhost:8401/api"
PID = "1511e54f71dccd3fa79f67fe"  # PMv2
LABEL = "studio-action-surface"

def post(path, body):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def create_issue(title, type_, priority, description, parent_id=None, labels=None, estimate=None, assignee=None):
    body = {
        "title": title,
        "type": type_,
        "priority": priority,
        "description": description,
        "reporter": "AI",
        "labels": labels if labels is not None else LABEL,
    }
    if parent_id:
        body["parentId"] = parent_id
    if estimate is not None:
        body["estimateMinutes"] = estimate
    if assignee:
        body["assignee"] = assignee
    return post(f"/projects/{PID}/issues", body)


# ---------------------------------------------------------------------------
# FEATURE
# ---------------------------------------------------------------------------
# FEATURE already created via curl earlier — CB-2864
FEATURE_ID = "26898b3b-96f6-413b-97ce-21d5a4898339"
FEATURE_KEY = "CB-2864"
fid = FEATURE_ID
print(f"FEATURE existing: {FEATURE_KEY} ({fid})")


# ---------------------------------------------------------------------------
# EPIC 1 — CodeBoard write tools
# ---------------------------------------------------------------------------
e1 = create_issue(
    title="E1 — CodeBoard write tools (create_codeboard_issue, update_codeboard_status)",
    type_="EPIC",
    priority="HIGH",
    parent_id=fid,
    assignee="python-pro",
    description="Add WRITE side to studio_chat_agent.py tool surface. Studio Jonny can file new tickets and update existing status (excluding direct→DONE, blocked by Rule 22).",
    estimate=720,
)
e1id = e1["id"]
print(f"  {e1['key']} (E1)")

s1_1 = create_issue("S1.1 — create_codeboard_issue tool", "STORY", "HIGH", parent_id=e1id, assignee="python-pro", description="Studio Jonny can file CB issues via tool call.", estimate=420)
for tid, title, est, assignee, desc in [
    ("T1.1.1", "Tool JSON schema (type, title, description, priority, parentId?, labels?)", 30, "python-pro", "Pydantic-style validated; matches existing /api/issues POST contract."),
    ("T1.1.2", "_tool_create_codeboard_issue handler — async POST to /api/issues/{pid}", 120, "python-pro", "Returns {issue_key, issue_id, url}."),
    ("T1.1.3", "Multi-tenant guard — project_id == session.project_id", 60, "python-pro", "Cross-project writes return tool-result error."),
    ("T1.1.4", "Approval-gate prompt — confirm before POST", 60, "llm-architect", "Tool description + system prompt require explicit user confirmation."),
    ("T1.1.5", "Audit log — sessionId + projectId + issueId + redact secrets", 30, "python-pro", "Log line present, Bearer/sk-/api_key= stripped."),
]:
    create_issue(f"{tid} — {title}", "TASK", "HIGH", parent_id=s1_1["id"], assignee=assignee, description=desc, estimate=est)

s1_2 = create_issue("S1.2 — update_codeboard_status tool", "STORY", "HIGH", parent_id=e1id, assignee="python-pro", description="Studio Jonny can flip status BACKLOG→IN_PROGRESS→CWQ. Block direct→DONE per Rule 22.", estimate=240)
for tid, title, est, assignee, desc in [
    ("T1.2.1", "Tool schema (issue_id, target_status enum)", 30, "python-pro", "Status enum validated."),
    ("T1.2.2", "Handler — PATCH /api/issues/{id}", 60, "python-pro", "200 surfaced as tool-result."),
    ("T1.2.3", "Block direct→DONE flips (Rule 22)", 30, "python-pro", "Return error citing rule."),
    ("T1.2.4", "Same multi-tenant guard as S1.1", 30, "python-pro", "Reject mismatched project."),
]:
    create_issue(f"{tid} — {title}", "TASK", "HIGH", parent_id=s1_2["id"], assignee=assignee, description=desc, estimate=est)


# ---------------------------------------------------------------------------
# EPIC 2 — Orchestration tools
# ---------------------------------------------------------------------------
e2 = create_issue(
    title="E2 — Orchestration tools (spawn_subagent, hand_to_autopilot)",
    type_="EPIC", priority="MEDIUM", parent_id=fid, assignee="python-pro",
    description="Studio Jonny can delegate to specialist agents + queue features for AutoPilot.",
    estimate=420,
)
e2id = e2["id"]
print(f"  {e2['key']} (E2)")
s2_1 = create_issue("S2.1 — spawn_subagent tool", "STORY", "MEDIUM", parent_id=e2id, assignee="python-pro", description="Studio Jonny delegates to specialist agents.", estimate=240)
for tid, title, est, assignee in [
    ("T2.1.1", "Schema (agent_type, prompt, context)", 30, "python-pro"),
    ("T2.1.2", "Handler — invoke backend agent dispatcher", 180, "ai-engineer"),
]:
    create_issue(f"{tid} — {title}", "TASK", "MEDIUM", parent_id=s2_1["id"], assignee=assignee, description=title, estimate=est)
s2_2 = create_issue("S2.2 — hand_to_autopilot tool", "STORY", "MEDIUM", parent_id=e2id, assignee="python-pro", description="Approved features queue for AutoPilot execution.", estimate=180)
for tid, title, est, assignee in [
    ("T2.2.1", "Schema (feature_issue_id, branch_strategy)", 30, "python-pro"),
    ("T2.2.2", "Handler — POST /api/autopilot/queue", 150, "python-pro"),
]:
    create_issue(f"{tid} — {title}", "TASK", "MEDIUM", parent_id=s2_2["id"], assignee=assignee, description=title, estimate=est)


# ---------------------------------------------------------------------------
# EPIC 3 — Bible binding
# ---------------------------------------------------------------------------
e3 = create_issue(
    title="E3 — Bible binding in system prompt (32 rules + flexible intent)",
    type_="EPIC", priority="HIGH", parent_id=fid, assignee="llm-architect",
    description="Embed full 32-rule bible; recognize rephrased bug-report intent; cite rule numbers in refusals.",
    estimate=240,
)
e3id = e3["id"]
print(f"  {e3['key']} (E3)")
s3_1 = create_issue("S3.1 — Embed 32-rule Bible into system prompt", "STORY", "HIGH", parent_id=e3id, assignee="llm-architect", description="Inline all 32 one-liners + tool-use → rule mapping.", estimate=240)
for tid, title, est, assignee, desc in [
    ("T3.1.1", "Inline 32-rule list verbatim", 30, "llm-architect", "From ~/.claude/skills/jonny/SKILL.md."),
    ("T3.1.2", "Flexible-intent parsing rules", 120, "llm-architect", "'X is broken' / 'open a bug' / 'report this' all trigger create_codeboard_issue path."),
    ("T3.1.3", "Refusal template cites rule number", 30, "llm-architect", "'Per Rule 22, only Eli flips DONE.'"),
    ("T3.1.4", "Approval-gate language", 60, "llm-architect", "'Ready to file CB with title X? Confirm.'"),
]:
    create_issue(f"{tid} — {title}", "TASK", "HIGH", parent_id=s3_1["id"], assignee=assignee, description=desc, estimate=est)


# ---------------------------------------------------------------------------
# EPIC 4 — Frontend tool-result rendering
# ---------------------------------------------------------------------------
e4 = create_issue(
    title="E4 — Frontend tool-result rendering (ticket link cards, status badges)",
    type_="EPIC", priority="MEDIUM", parent_id=fid, assignee="react-specialist",
    description="When Studio Jonny calls a write tool, render the result inline as a clickable card (key + title + link).",
    estimate=300,
)
e4id = e4["id"]
print(f"  {e4['key']} (E4)")
s4_1 = create_issue("S4.1 — Tool-result card components", "STORY", "MEDIUM", parent_id=e4id, assignee="react-specialist", description="Render tool-use results inline in chat list.", estimate=300)
for tid, title, est, assignee, desc in [
    ("T4.1.1", "ToolResultCard.tsx component", 120, "react-specialist", "Renders create_codeboard_issue results."),
    ("T4.1.2", "Wire into ChatMessageList.tsx", 120, "react-specialist", "Cards inline with text, theme-aware."),
    ("T4.1.3", "Status-update badge variant", 60, "react-specialist", "Compact badge for update_codeboard_status."),
]:
    create_issue(f"{tid} — {title}", "TASK", "MEDIUM", parent_id=s4_1["id"], assignee=assignee, description=desc, estimate=est)


# ---------------------------------------------------------------------------
# EPIC 5 — Code Audit (MANDATORY per Rule 32)
# ---------------------------------------------------------------------------
e5 = create_issue(
    title="E5 — Code Audit Epic (MANDATORY — Rule 32)",
    type_="EPIC", priority="HIGH", parent_id=fid, assignee="code-reviewer",
    description="0 CRITICAL / 0 HIGH; CORRECTLY-IDENTIFIED strengths surfaced.",
    estimate=120,
)
e5id = e5["id"]
print(f"  {e5['key']} (E5)")
create_issue("S5.1 — code-reviewer on diff", "STORY", "HIGH", parent_id=e5id, assignee="code-reviewer", description="Severity counts + bias-correction strengths.", estimate=60)
create_issue("S5.2 — security-auditor (multi-tenant + IDOR + secret redaction)", "STORY", "HIGH", parent_id=e5id, assignee="security-auditor", description="Confirm session.project_id sole write target; audit log redacts secrets; no IDOR.", estimate=60)


# ---------------------------------------------------------------------------
# EPIC 6 — QA Epic (MANDATORY per Rule 30 + 32)
# ---------------------------------------------------------------------------
e6 = create_issue(
    title="E6 — QA Epic — qa-regression skill (MANDATORY — Rule 30 + 32)",
    type_="EPIC", priority="HIGH", parent_id=fid, assignee="qa-regression-skill",
    description="7-stage pipeline. PASS or PASS-WITH-NITS allows CWQ flip.",
    estimate=300,
)
e6id = e6["id"]
print(f"  {e6['key']} (E6)")
for sid, title, est, assignee, desc in [
    ("S6.1", "qa-regression Stage 1 — AC matrix from bug-repro evidence", 30, "qa-regression-skill", ">=3 binary ACs derived."),
    ("S6.2", "qa-regression Stage 2 — automated tests (vitest + pytest + tsc)", 60, "general-purpose", "All green."),
    ("S6.3", "qa-regression Stage 3 — Chrome MCP manual run", 120, "qa-regression-skill", "Every AC live; light+dark; multi-project."),
    ("S6.4", "qa-regression Stage 5 — destructive (corrupt/private/network/cross-tenant)", 60, "qa-regression-skill", "All cases PASS."),
    ("S6.5", "qa-regression Stage 7 — sign-off block to CB ticket", 30, "qa-regression-skill", "Verdict comment posted."),
]:
    create_issue(f"{sid} — {title}", "STORY", "HIGH", parent_id=e6id, assignee=assignee, description=desc, estimate=est)


# ---------------------------------------------------------------------------
# EPIC 7 — Full Regression Epic (MANDATORY per Rule 32)
# ---------------------------------------------------------------------------
e7 = create_issue(
    title="E7 — Full Regression Epic (MANDATORY — Rule 32)",
    type_="EPIC", priority="HIGH", parent_id=fid, assignee="qa-regression-skill",
    description="Stage 4 adjacent-flow sweep + Stage 5 destructive cases.",
    estimate=240,
)
e7id = e7["id"]
print(f"  {e7['key']} (E7)")
for sid, title, est, assignee, desc in [
    ("S7.1", "CB-2814 Studio tab persistence — still works after prompt bloat", 30, "qa-regression-skill", "Reload + project switch."),
    ("S7.2", "useStudioStore per-project state regression", 30, "qa-regression-skill", "Open tabs A+B, send msg, reload."),
    ("S7.3", "AutoPilot queue regression (if E2 lands)", 30, "qa-regression-skill", "Queue tiny feature, verify rehydrate."),
    ("S7.4", "Audit-log redaction (Bearer/sk-/api_key=)", 30, "security-auditor", "Redacted on persistence."),
    ("S7.5", "CodeBoard read path (search_codeboard) — no regression", 30, "qa-regression-skill", "Existing read tool still works."),
    ("S7.6", "Existing chat send + draft persist", 30, "qa-regression-skill", "Send → draft cleared → msg rendered."),
    ("S7.7", "Multi-tenant tenancy header forge attempt", 60, "security-auditor", "Forged X-Tenant-ID → write rejected."),
]:
    create_issue(f"{sid} — {title}", "STORY", "HIGH", parent_id=e7id, assignee=assignee, description=desc, estimate=est)

print("\nALL EPICS PUSHED.")
print(f"FEATURE: {feature['key']}")
