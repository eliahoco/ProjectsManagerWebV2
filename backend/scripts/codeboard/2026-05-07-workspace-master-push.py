"""
Push the AI Project Workspace master plan to CodeBoard.

Hierarchy (production-grade, no mockups):
- 1 FEATURE
- 8 EPICS  (E1 Foundation, E2 Studio, E3 Backlog, E4 Crew Map,
            E5 Promote Pipeline, E6 Scheduler, E7 Audits + Full Regression QA,
            E8 Rollout + Soak)
- 41 STORIES
- 203 TASKS
- 25 SUBTASKS
= 278 issues total.

Every task has a self-contained brief: file paths, acceptance criteria,
assignee subagent, references to dependencies. AutoPilot fires each via
PMv2's full instruction stack (Jonny SKILL + Atlas + CandleKeep + 16
specialist subagents + context_builder).

Source plan: docs/plans/2026-05-07-ai-project-workspace-master-plan.md
Bible compliance: Rule 23 (CodeBoard FIRST), Rule 27 (durable plan),
Rule 29 (per-project per-session script path).
Reporter: AI. Default status: BACKLOG. Eli explicitly approved 2026-05-07.

Output: backend/docs/workspace/id-map.json — full key/id map for downstream
work (audit runner, soak monitor, promote-pipeline tests).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
LABELS_BASE = "🚀-workspace-v1"

ID_MAP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "docs", "workspace", "id-map.json",
)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def http(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code} on {method} {path}: {body_txt[:300]}")
        raise


def create_issue(
    title: str,
    description: str,
    type_: str,
    priority: str,
    parent_id: str | None = None,
    assignee: str | None = None,
    extra_labels: str = "",
) -> dict:
    labels = LABELS_BASE
    if extra_labels:
        labels = f"{LABELS_BASE},{extra_labels}"
    body: dict = {
        "title": title,
        "description": description,
        "type": type_,
        "priority": priority,
        "reporter": "AI",
        "labels": labels,
        "status": "BACKLOG",
    }
    if parent_id:
        body["parentId"] = parent_id
    if assignee:
        body["assignee"] = assignee
    result = http("POST", f"/projects/{PROJECT_ID}/issues", body)
    return result


# ---------------------------------------------------------------------------
# Rich descriptions — common templates
# ---------------------------------------------------------------------------

WORKSPACE_PREAMBLE = """
**Parent feature:** AI Project Workspace — major architecture add-on layered above CodeBoard.
Three views: Studio (chat planning) · Backlog (staging) · Crew Map (Obsidian-style agent graph).
Source plan: `docs/plans/2026-05-07-ai-project-workspace-master-plan.md`.

**Bible compliance required:** Rules 1-29 apply. Specifically:
- Rule 18: 4-gate audit (code-reviewer + security-auditor + debugger functional + Chrome QA) before CWQ
- Rule 22: status flows BACKLOG → IN_PROGRESS → COMPLETED_WAITING_QA. Never DONE without Eli.
- Rule 23: any scope change → file CodeBoard ticket BEFORE writing code.
- Rule 24: any UI change → Chrome screenshot + visual inspection (DOM queries are NOT sufficient).
- Rule 25: full regression — create → save → read → run → verify end-to-end.

**Production patterns baked in (from CandleKeep reading):**
- Visibility Principle: every agent dispatch hits `StudioAgentActivity` BEFORE chat narrates it.
- Template/Instance separation: versioned identity vs per-conversation memory.
- GroupQueue mutex: one execution per agent across all tabs.
- 4 typed message verbs (notify/request/delegate/broadcast) + max_chain_depth=3.
- Sub-agent context isolation: skills run fresh window, return 1-2K artifact.
- Tool consolidation: `add_to_codeboard(hierarchy)`, `send_to_autopilot(id)` — single tools, not granular CRUD.
- Blueprint state machines: deterministic + agentic hybrid for promote pipeline.
- Linear-dark default (#08090a/#0f1011/#7170ff) with Anthropic-light alternative.
- Inter Variable weight 510 for tab labels + badges.
- CSS transitions (interruptible) over keyframes for state changes.
- Doherty 400ms responsiveness for scheduler controls.
- Compound Component + Context for Chat shell.
- aria-live=polite for streaming text, role=separator for pane resize handle.

**Linked artifacts:**
- Parked sibling: CB-2381 (AI Cost Optimization, will become ExecutionTokens dependency).
- Bible: ~/.claude/skills/jonny/SKILL.md.
- Atlas: ~/.claude/skills/atlas/.
- CandleKeep readings (10 books): library + marketplace, see plan ch.11.

**No mockups.** Production code. State of the art. Eli's words: "super super super professional, perfectionist state of the art."
""".strip()


def std_desc(body: str, *, files: list[str] | None = None,
             accept: list[str] | None = None,
             dispatch: str | None = None,
             refs: list[str] | None = None) -> str:
    """Build a rich, self-contained task brief."""
    out = [body.strip(), ""]
    if files:
        out.append("**Files / paths:**")
        for f in files:
            out.append(f"- `{f}`")
        out.append("")
    if accept:
        out.append("**Acceptance criteria:**")
        for a in accept:
            out.append(f"- {a}")
        out.append("")
    if dispatch:
        out.append(f"**Dispatch via Task tool:** subagent_type=`{dispatch}`")
        out.append("")
    if refs:
        out.append("**Dependencies / references:**")
        for r in refs:
            out.append(f"- {r}")
        out.append("")
    out.append("---")
    out.append(WORKSPACE_PREAMBLE)
    return "\n".join(out)


def review_desc(epic_label: str, scope: str, files_glob: str) -> str:
    return std_desc(
        f"Run code-reviewer agent on the full {epic_label} diff. Scope: {scope}.",
        files=[files_glob],
        accept=[
            "Zero CRITICAL findings.",
            "Zero HIGH findings (or all fixed inline before CWQ).",
            "MEDIUM/LOW findings filed as child BUGs under the epic with kebab-case label `cb-WORKSPACE-review-followup`.",
            "Reviewer pass appended as comment on this task's CodeBoard issue.",
        ],
        dispatch="code-reviewer",
    )


def security_desc(scope: str, files: list[str]) -> str:
    return std_desc(
        f"Run security-auditor agent on: {scope}.",
        files=files,
        accept=[
            "Zero CRITICAL/HIGH findings.",
            "MEDIUM/LOW findings filed as child BUGs.",
            "Auditor pass appended as comment.",
        ],
        dispatch="security-auditor",
    )


def qa_desc(scenario: str, expected: str, dispatcher: str = "debugger") -> str:
    return std_desc(
        f"**Scenario:** {scenario}\n\n**Expected outcome:** {expected}",
        accept=[
            "Test executed end-to-end (no mocks where production state matters).",
            "Result documented in CodeBoard comment with timestamps + screenshots if UI.",
            "Pass → CWQ. Fail → file follow-up BUG and leave this task IN_PROGRESS.",
        ],
        dispatch=dispatcher,
    )


# ---------------------------------------------------------------------------
# HIERARCHY — 1 FEATURE → 8 EPICS → 41 STORIES → 203 TASKS → 25 SUBTASKS
# ---------------------------------------------------------------------------

# For brevity in this script, each item dict has the keys:
#   id    — local identifier (e.g. "E1.S2.T1") used only inside this script
#   t     — title
#   d     — description (rich, self-contained brief)
#   p     — priority (CRITICAL/HIGH/MEDIUM/LOW/TRIVIAL)
#   a     — assignee subagent name (used by AutoPilot via Task tool)
#   l     — extra labels (kebab-case, comma-separated; LABELS_BASE auto-prepended)
#   children — list of child item dicts of the next type below


FEATURE = {
    "id": "F",
    "t": "AI Project Workspace — Studio + Backlog + Crew Map",
    "d": (
        "**Major architecture add-on.** New layer above CodeBoard with three views:\n"
        "1. **Studio** — chat-based feature planning, multi-tab persistent Claude Code sessions, live agent activity panel, split-view artifact preview.\n"
        "2. **Backlog** — pre-CodeBoard staging board with priority + scheduler, 'Send to CodeBoard + AutoPilot' action.\n"
        "3. **Crew Map** — Obsidian-style graph showing orchestrator + skills + assignments per project + per feature.\n\n"
        "**Vision:** Today CodeBoard is the execution engine but is misused as planning. ~30% of BACKLOG is half-baked drafts. "
        "This feature moves planning into a dedicated Studio room, stages features in a Backlog room, and makes the whole crew "
        "visible in a Crew Map. CodeBoard becomes pure execution.\n\n"
        "**Three views, one workspace.** All bound to the same project picker. All share the same data layer. "
        "All built with production-grade Linear-style aesthetics (dark default, Anthropic-light alternative).\n\n"
        "**Eli explicit approval (2026-05-07):** 'super super super professional, perfectionist state of the art. "
        "I trust you. Go and do your work with your colleagues.'\n\n"
        "**Hierarchy:** 1 FEATURE / 8 EPICs / 41 STORIES / 203 TASKS / 25 SUBTASKS = 278 issues.\n"
        "**Estimated:** ~12 weeks including 7-day soak.\n"
        "**Sequencing:** E1 → (E2 || E3 || E4) → (E5 || E6) → E7 → E8.\n\n"
        + WORKSPACE_PREAMBLE
    ),
    "p": "CRITICAL",
    "a": "Eli",
    "l": "feature,studio,backlog,crew-map,architecture-major-addon",
    "children": [],  # populated below
}


# =========================================================================
# E1 — Foundation
# =========================================================================
E1 = {
    "id": "E1",
    "t": "[E1] Foundation — Data model + shared services",
    "d": std_desc(
        "Build the data layer and shared backend services that all three views depend on. "
        "Studio, Backlog, and Crew Map all read/write through this foundation. "
        "Includes: SQLAlchemy + Prisma models for conversations/messages/artifacts/agent-activity/inter-agent-messages, "
        "FeatureRequest data model, CrewAssignment data model, agent_dispatcher service with typed verbs + GroupQueue mutex + chain-depth check, "
        "studio_orchestrator multi-session manager, SSE multiplexer, audit log + Visibility Principle enforcement.",
        accept=[
            "All migrations applied successfully against backend/data/codeboard.db AND frontend/prisma/dev.db.",
            "agent_dispatcher passes its full test suite (verbs, mutex, chain depth, audit log).",
            "Visibility Principle enforced: pre-flight check rejects any dispatch attempt that bypasses the audit log.",
            "studio_orchestrator can spawn + hibernate + resume a Claude Code subprocess.",
        ],
        dispatch="python-pro",
        refs=[
            "Existing infra to extend: services/terminal_service.py (CLI spawn), services/autopilot_queue_service.py (CB-1951 audit pattern), models/agent_registry.py + skill_registry.py (catalogue).",
            "Reading: V3_AGENT_ARCHITECTURE.md §F-2/F-4, V3_DATABASE_SCHEMA.md, CB-1951 journal at backend/docs/cb-1951/journal.md.",
        ],
    ),
    "p": "CRITICAL",
    "a": "python-pro",
    "l": "epic,foundation,backend,data-model,e1",
    "children": [
        # ----- E1.S1 Studio data model -----
        {
            "id": "E1.S1", "t": "[E1.S1] Studio data model", "p": "CRITICAL", "a": "python-pro",
            "l": "story,backend,data-model,studio,e1",
            "d": std_desc(
                "Define and migrate the SQLAlchemy + Prisma models that back the Studio view: conversations, "
                "messages, artifacts, live agent activity, inter-agent messages, plus the agent template/instance split.",
                accept=[
                    "All models exist on both sides (SQLAlchemy in backend/models/, Prisma in frontend/prisma/schema.prisma).",
                    "Migrations idempotent (re-run does not fail).",
                    "Foreign keys enforce referential integrity.",
                    "Indexes on hot lookup columns (projectId, conversationId, agentName, ts).",
                ],
                dispatch="python-pro",
            ),
            "children": [
                {"id": "E1.S1.T1", "t": "[E1.S1.T1] SQLAlchemy: StudioConversation/Message/Artifact/AgentActivity/InterAgentMessage",
                 "p": "CRITICAL", "a": "python-pro", "l": "task,backend,sqlalchemy,e1",
                 "d": std_desc(
                     "Add 5 SQLAlchemy 2.0 async ORM classes in backend/models/studio.py. "
                     "Match V3_DATABASE_SCHEMA.md table shape where applicable. Use `func.now()` server defaults for timestamps. "
                     "Use cascading deletes from Conversation → Message/Artifact/AgentActivity. "
                     "Each model includes id (CUID), createdAt, updatedAt.",
                     files=[
                         "backend/models/studio.py (NEW)",
                         "backend/models/__init__.py (re-export)",
                         "backend/models/database.py (Base import only)",
                     ],
                     accept=[
                         "StudioConversation: id, projectId (FK), title, state (enum: active/hibernated/archived), createdAt, updatedAt.",
                         "StudioMessage: id, conversationId (FK), role (enum: user/jonny/skill/system), content TEXT, agentName nullable, ts.",
                         "StudioArtifact: id, conversationId (FK), kind (enum: markdown/mermaid/code/html), payload TEXT, ts.",
                         "StudioAgentActivity: id, conversationId (FK), agentName, skillName nullable, status (enum: idle/dispatched/thinking/tool_use/done/error), startedAt, endedAt nullable.",
                         "StudioInterAgentMessage: id, conversationId (FK), fromAgent, toAgent, verb (enum: notify/request/delegate/broadcast), payload JSON, chainDepth INT, ts.",
                         "Indexes: (conversationId, ts) on Message+AgentActivity+InterAgentMessage; (projectId) on Conversation.",
                     ],
                     dispatch="python-pro",
                     refs=["Pattern reference: backend/models/autopilot.py (CB-1951 mirror)."],
                 )},
                {"id": "E1.S1.T2", "t": "[E1.S1.T2] SQLAlchemy: AgentTemplate + AgentInstance (template/instance split)",
                 "p": "HIGH", "a": "python-pro", "l": "task,backend,sqlalchemy,e1",
                 "d": std_desc(
                     "Add 2 SQLAlchemy classes implementing the production-validated template/instance separation "
                     "(per Building Your Agent Team). AgentTemplate is versioned, git-tracked-style identity. "
                     "AgentInstance is per-conversation accumulated memory.",
                     files=[
                         "backend/models/studio.py (extend)",
                     ],
                     accept=[
                         "AgentTemplate: id, name UNIQUE, version, prompt TEXT, capabilities JSON, isActive BOOLEAN, createdAt, updatedAt.",
                         "AgentInstance: id, templateId (FK→AgentTemplate.id), conversationId (FK→StudioConversation.id), accumulatedMemory TEXT, lastActiveAt, createdAt.",
                         "UNIQUE(templateId, conversationId) — one instance per conversation per template.",
                     ],
                     dispatch="python-pro",
                 )},
                {"id": "E1.S1.T3", "t": "[E1.S1.T3] Prisma mirror — Studio models",
                 "p": "HIGH", "a": "typescript-pro", "l": "task,frontend,prisma,e1",
                 "d": std_desc(
                     "Mirror all 7 Studio models into frontend/prisma/schema.prisma so Next.js can read them via Prisma Client.",
                     files=["frontend/prisma/schema.prisma"],
                     accept=[
                         "Models match SQLAlchemy shape (camelCase fields).",
                         "Relations declared with @relation directives.",
                         "Indexes mirrored (@@index([conversationId, ts])).",
                         "Enums declared (ConversationState, MessageRole, ArtifactKind, AgentActivityStatus, InterAgentVerb).",
                         "`prisma generate` succeeds without errors.",
                     ],
                     dispatch="typescript-pro",
                 )},
                {"id": "E1.S1.T4", "t": "[E1.S1.T4] Migration script + idempotent seed (Jonny + 6 default skills as templates)",
                 "p": "HIGH", "a": "python-pro", "l": "task,backend,migration,e1",
                 "d": std_desc(
                     "Write Alembic-style migration in backend/utils/ that adds the new tables AND seeds AgentTemplate "
                     "with: jonny, atlas, candlekeep, code-reviewer, security-auditor, debugger, chrome-devtools-mcp. "
                     "Seed must be idempotent (re-run does not duplicate).",
                     files=[
                         "backend/utils/apply_studio_tables.py (NEW)",
                         "backend/scripts/seed_agent_templates.py (NEW)",
                     ],
                     accept=[
                         "Tables created on backend/data/codeboard.db.",
                         "7 AgentTemplate rows seeded with version=1, isActive=true.",
                         "Re-run produces no duplicate rows + no errors.",
                         "Frontend Prisma migration applied to frontend/prisma/dev.db.",
                     ],
                     dispatch="python-pro",
                     refs=["Pattern: backend/scripts/backfill_autopilot.py."],
                 )},
            ],
        },
        # ----- E1.S2 Backlog data model -----
        {
            "id": "E1.S2", "t": "[E1.S2] Backlog data model", "p": "CRITICAL", "a": "python-pro",
            "l": "story,backend,data-model,backlog,e1",
            "d": std_desc(
                "Define and migrate the FeatureRequest + Comment + Activity models that back the Backlog view.",
                accept=[
                    "Models on both sides (SQLAlchemy + Prisma).",
                    "Status flow constrained: DRAFT → REVIEWING → APPROVED → SCHEDULED → PROMOTED → SHIPPED → ARCHIVED.",
                    "Schedule fields: scheduledFor (one-shot ISO timestamp) + scheduleCron (string, validated by croniter).",
                    "sourceConversationId nullable FK to StudioConversation.",
                    "targetIssueId nullable string (CodeBoard issue key after promote).",
                ],
                dispatch="python-pro",
            ),
            "children": [
                {"id": "E1.S2.T1", "t": "[E1.S2.T1] SQLAlchemy: FeatureRequest + Comment + Activity",
                 "p": "CRITICAL", "a": "python-pro", "l": "task,backend,sqlalchemy,e1",
                 "d": std_desc(
                     "Add 3 SQLAlchemy classes in backend/models/feature_request.py.",
                     files=["backend/models/feature_request.py (NEW)", "backend/models/__init__.py"],
                     accept=[
                         "FeatureRequest: id, projectId (FK), title, description TEXT, priority enum, status enum, "
                         "scheduledFor DateTime nullable, scheduleCron VARCHAR nullable, tags JSON, sourceConversationId nullable, "
                         "targetIssueId nullable, ownerEmail nullable, archivedAt nullable, createdAt, updatedAt.",
                         "FeatureRequestComment: id, featureRequestId (FK), author, content, createdAt.",
                         "FeatureRequestActivity: id, featureRequestId (FK), action, payload JSON, actor, ts.",
                         "Indexes on (projectId, status), (scheduledFor), (status, scheduleCron).",
                     ],
                     dispatch="python-pro",
                 )},
                {"id": "E1.S2.T2", "t": "[E1.S2.T2] Prisma mirror — Backlog models",
                 "p": "HIGH", "a": "typescript-pro", "l": "task,frontend,prisma,e1",
                 "d": std_desc(
                     "Mirror FeatureRequest + Comment + Activity into Prisma schema.",
                     files=["frontend/prisma/schema.prisma"],
                     accept=["3 models declared with relations + indexes; prisma generate succeeds."],
                     dispatch="typescript-pro",
                 )},
                {"id": "E1.S2.T3", "t": "[E1.S2.T3] Migration + seed (port CB-2381 as first FeatureRequest)",
                 "p": "HIGH", "a": "python-pro", "l": "task,backend,migration,e1",
                 "d": std_desc(
                     "Apply migrations to both DBs. Backfill: read CB-2381 from CodeBoard API, "
                     "create one FeatureRequest row in BACKLOG status with priority=HIGH, "
                     "tags=['ai','cost','telemetry','parked'], targetIssueId='CB-2381'.",
                     files=["backend/utils/apply_feature_request_tables.py (NEW)"],
                     accept=[
                         "Tables created.",
                         "CB-2381 backfilled as 1 FeatureRequest with sourceConversationId=null, targetIssueId='CB-2381', status='DRAFT', tags includes 'parked-future'.",
                         "Re-run idempotent.",
                     ],
                     dispatch="python-pro",
                 )},
            ],
        },
        # ----- E1.S3 Crew Map data model -----
        {
            "id": "E1.S3", "t": "[E1.S3] Crew Map data model", "p": "HIGH", "a": "python-pro",
            "l": "story,backend,data-model,crew-map,e1",
            "d": std_desc(
                "Define CrewAssignment + CrewSkillUsage tables that back the Crew Map graph.",
                accept=["Models present on both sides; indexes on (projectId, featureId, agentName)."],
                dispatch="python-pro",
            ),
            "children": [
                {"id": "E1.S3.T1", "t": "[E1.S3.T1] SQLAlchemy: CrewAssignment + CrewSkillUsage",
                 "p": "HIGH", "a": "python-pro", "l": "task,backend,sqlalchemy,e1",
                 "d": std_desc(
                     "Add 2 models in backend/models/crew_map.py.",
                     files=["backend/models/crew_map.py (NEW)"],
                     accept=[
                         "CrewAssignment: id, projectId (FK), featureId nullable (FK to Issue.id where type=FEATURE), agentName, role (enum: orchestrates/audits/implements/reviews/documents), status (enum: active/past), startedAt, endedAt nullable.",
                         "CrewSkillUsage: id, assignmentId (FK), skillName, invocationCount INT default 0, lastUsed DateTime.",
                         "Indexes on (projectId, status), (featureId), (agentName, status).",
                     ],
                     dispatch="python-pro",
                 )},
                {"id": "E1.S3.T2", "t": "[E1.S3.T2] Prisma mirror — Crew Map models",
                 "p": "HIGH", "a": "typescript-pro", "l": "task,frontend,prisma,e1",
                 "d": std_desc("Mirror CrewAssignment + CrewSkillUsage into Prisma.",
                     files=["frontend/prisma/schema.prisma"], accept=["prisma generate ok."],
                     dispatch="typescript-pro"),
                },
                {"id": "E1.S3.T3", "t": "[E1.S3.T3] Migration",
                 "p": "MEDIUM", "a": "python-pro", "l": "task,backend,migration,e1",
                 "d": std_desc("Apply migrations to both DBs.",
                     files=["backend/utils/apply_crew_map_tables.py (NEW)"],
                     accept=["Tables exist; idempotent re-run."],
                     dispatch="python-pro"),
                },
            ],
        },
        # ----- E1.S4 Shared services skeleton -----
        {
            "id": "E1.S4", "t": "[E1.S4] Shared services skeleton (agent_dispatcher + studio_orchestrator + SSE)",
            "p": "CRITICAL", "a": "python-pro",
            "l": "story,backend,services,e1",
            "d": std_desc(
                "Build the shared backend services that Studio + Crew Map + Promote Pipeline all depend on. "
                "Includes the iron-law agent_dispatcher (4 verbs + mutex + chain limit + audit), studio_orchestrator "
                "(multi-session Claude Code spawn manager extending terminal_service), SSE multiplexer for live events, "
                "and the CrewAssignment writer.",
                accept=[
                    "agent_dispatcher tests pass.",
                    "studio_orchestrator can spawn + hibernate + resume.",
                    "SSE per-conversation channel multiplexes correctly.",
                    "Every dispatch creates one CrewAssignment row.",
                ],
                dispatch="python-pro",
            ),
            "children": [
                {"id": "E1.S4.T1", "t": "[E1.S4.T1] services/agent_dispatcher.py — typed verbs + GroupQueue mutex + chain-depth",
                 "p": "CRITICAL", "a": "python-pro", "l": "task,backend,services,e1",
                 "d": std_desc(
                     "Build the dispatcher that ALL inter-agent messages must flow through. Iron law: every call hits the audit log "
                     "BEFORE the chat narrates the action (Visibility Principle). Implements 4 typed verbs and enforces max_chain_depth=3 + per-agent mutex.",
                     files=["backend/services/agent_dispatcher.py (NEW)", "backend/tests/test_agent_dispatcher.py (NEW)"],
                     accept=[
                         "Module exposes: notify(), request(), delegate(), broadcast(), get_chain_depth(), is_locked().",
                         "Per-agent asyncio.Lock keyed by agentName.",
                         "Pre-flight write to StudioInterAgentMessage BEFORE any subprocess work begins.",
                         "Reject with explicit error if chain_depth>=3.",
                         "Reject if target agent is locked by another conversation.",
                         "Audit row payload size capped at 8KB (CB-1951 pattern).",
                         "Sanitized payload — strip Bearer/sk-/api_key= patterns (CB-1951 pattern).",
                     ],
                     dispatch="python-pro",
                     refs=["Pattern source: services/autopilot_queue_service.py CB-1951 audit log redactor."],
                 ),
                 "children": [
                     {"id": "E1.S4.T1.ST1", "t": "[E1.S4.T1.ST1] notify(from, to, payload)",
                      "p": "CRITICAL", "a": "python-pro", "l": "subtask,backend,e1",
                      "d": std_desc("One-directional information share, no reply expected. Returns immediately after audit row written.",
                          accept=["Audit row written; no blocking; returns dispatch_id."], dispatch="python-pro")},
                     {"id": "E1.S4.T1.ST2", "t": "[E1.S4.T1.ST2] request(from, to, payload) — blocking",
                      "p": "CRITICAL", "a": "python-pro", "l": "subtask,backend,e1",
                      "d": std_desc("Question requiring an answer; blocks until target replies or timeout (default 60s).",
                          accept=["Returns reply payload or raises TimeoutError; audit pair (request+reply) recorded."], dispatch="python-pro")},
                     {"id": "E1.S4.T1.ST3", "t": "[E1.S4.T1.ST3] delegate(from, to, payload)",
                      "p": "CRITICAL", "a": "python-pro", "l": "subtask,backend,e1",
                      "d": std_desc("Task handoff; sender is done. Returns dispatch_id; target picks up async.",
                          accept=["Audit row written; target's queue receives dispatch."], dispatch="python-pro")},
                     {"id": "E1.S4.T1.ST4", "t": "[E1.S4.T1.ST4] broadcast(from, group, payload)",
                      "p": "HIGH", "a": "python-pro", "l": "subtask,backend,e1",
                      "d": std_desc("Notify a group of agents simultaneously. Group resolved from agent_registry by tag.",
                          accept=["One audit row per recipient; chain_depth=1."], dispatch="python-pro")},
                     {"id": "E1.S4.T1.ST5", "t": "[E1.S4.T1.ST5] Per-agent mutex via asyncio.Lock",
                      "p": "CRITICAL", "a": "python-pro", "l": "subtask,backend,e1",
                      "d": std_desc("GroupQueue lock keyed by agentName. Two tabs cannot invoke same skill simultaneously.",
                          accept=["Concurrent dispatch test: second call blocks until first releases."], dispatch="python-pro")},
                     {"id": "E1.S4.T1.ST6", "t": "[E1.S4.T1.ST6] max_chain_depth=3 enforcement + audit log row",
                      "p": "HIGH", "a": "python-pro", "l": "subtask,backend,e1",
                      "d": std_desc("Reject 4th-level dispatch with ChainDepthExceeded error. Audit log records the rejection.",
                          accept=["chain_depth=3 dispatch succeeds; chain_depth=4 raises and writes rejection audit row."], dispatch="python-pro")},
                 ],
                },
                {"id": "E1.S4.T2", "t": "[E1.S4.T2] services/studio_orchestrator.py — multi-session manager",
                 "p": "CRITICAL", "a": "python-pro", "l": "task,backend,services,e1",
                 "d": std_desc(
                     "Extend the existing terminal_service patterns to manage multiple persistent Claude Code subprocesses, "
                     "one per StudioConversation tab. Track active sessions in memory, persist to DB, support hibernate/resume.",
                     files=["backend/services/studio_orchestrator.py (NEW)"],
                     accept=[
                         "spawn_session(conversationId) starts a Claude Code subprocess with the right cwd, env, and prompt.",
                         "hibernate_session(conversationId) snapshots state and SIGTERMs the subprocess.",
                         "resume_session(conversationId) re-spawns and replays last 5 messages as context.",
                         "List of active sessions per project.",
                         "Maximum 8 concurrent sessions per user (configurable).",
                     ],
                     dispatch="python-pro",
                     refs=["Pattern source: backend/services/terminal_service.py (existing single-session model + JONNY_PREFIX)."],
                 )},
                {"id": "E1.S4.T3", "t": "[E1.S4.T3] SSE multiplexer — per-conversation EventSource channel",
                 "p": "HIGH", "a": "python-pro", "l": "task,backend,services,e1",
                 "d": std_desc(
                     "Multiplex stream-json events from each Studio subprocess into a per-conversation SSE channel. "
                     "Frontend subscribes via /api/studio/sessions/{conversationId}/events. Reconnect-friendly with last-event-id.",
                     files=["backend/api/studio.py (NEW partial)"],
                     accept=[
                         "Each conversation has its own SSE stream.",
                         "Reconnect with Last-Event-ID resumes from last seen event.",
                         "Heartbeat every 15s.",
                         "Channel closes cleanly on conversation hibernate/archive.",
                     ],
                     dispatch="python-pro",
                 )},
                {"id": "E1.S4.T4", "t": "[E1.S4.T4] Crew assignment writer — every dispatch creates CrewAssignment row",
                 "p": "HIGH", "a": "python-pro", "l": "task,backend,services,e1",
                 "d": std_desc(
                     "When agent_dispatcher.delegate() fires, write a CrewAssignment row with role inferred from the calling context "
                     "(orchestrates if Jonny→Skill, audits if reviewer/auditor agent, implements if specialist). "
                     "Mark status=active; flip to past when StudioAgentActivity for that agent reports done.",
                     files=["backend/services/agent_dispatcher.py (extend)"],
                     accept=[
                         "Every successful delegate call writes one CrewAssignment.",
                         "Role correctly inferred from agentName (code-reviewer→audits, python-pro/react-specialist→implements, etc.).",
                         "Crew Map view sees the new assignment within 2s of dispatch.",
                     ],
                     dispatch="python-pro",
                 )},
            ],
        },
        # ----- E1.S5 Audit log + Visibility enforcement -----
        {
            "id": "E1.S5", "t": "[E1.S5] Audit log + Visibility Principle enforcement",
            "p": "CRITICAL", "a": "python-pro",
            "l": "story,backend,security,visibility,e1",
            "d": std_desc(
                "Iron-law enforcement: every agent dispatch hits the audit log BEFORE the chat narrates it. "
                "Without this, agents can hallucinate dispatches that never happened (the 'agent shaming' anti-pattern).",
                dispatch="python-pro",
            ),
            "children": [
                {"id": "E1.S5.T1", "t": "[E1.S5.T1] Pre-flight check: dispatcher MUST persist before continuing",
                 "p": "CRITICAL", "a": "python-pro", "l": "task,backend,security,visibility,e1",
                 "d": std_desc(
                     "Wrap agent_dispatcher entrypoints with a decorator that writes the audit row in a transaction "
                     "BEFORE any subprocess spawn or message return. If the audit write fails, the dispatch fails — never both ways.",
                     files=["backend/services/agent_dispatcher.py"],
                     accept=[
                         "Decorator @audit_first applied to notify/request/delegate/broadcast.",
                         "Test: simulate DB failure at audit write — confirm dispatch is rejected, no subprocess spawn.",
                         "Test: simulate subprocess failure after audit write — audit row remains (for post-mortem).",
                     ],
                     dispatch="python-pro",
                 )},
                {"id": "E1.S5.T2", "t": "[E1.S5.T2] StudioInterAgentMessage write-through-persisted",
                 "p": "HIGH", "a": "python-pro", "l": "task,backend,e1",
                 "d": std_desc(
                     "Every InterAgentMessage written goes through the same write-through pattern as CB-1951 AutoPilotEvent: "
                     "synchronous DB write, no in-memory buffering, atomic commit per row.",
                     files=["backend/services/agent_dispatcher.py"],
                     accept=["No buffer; each call commits.", "Crash mid-flow leaves consistent DB state."],
                     dispatch="python-pro",
                 )},
                {"id": "E1.S5.T3", "t": "[E1.S5.T3] Test: assert no orphan dispatches",
                 "p": "HIGH", "a": "debugger", "l": "task,backend,test,e1",
                 "d": std_desc(
                     "Write a regression test that simulates an agent claiming a dispatch happened by directly calling the chat-message "
                     "writer without going through agent_dispatcher. The test must FAIL (i.e. the chat must reject the orphan claim).",
                     files=["backend/tests/test_visibility_principle.py (NEW)"],
                     accept=[
                         "Test attempts to write a chat message with agent invocation but no matching InterAgentMessage row.",
                         "Test asserts the chat layer rejects (or flags) the orphan claim.",
                         "Test green when implementation is correct.",
                     ],
                     dispatch="debugger",
                 )},
            ],
        },
    ],
}

# =========================================================================
# E2 — Studio (chat-based feature planning)  — full hierarchy below
# =========================================================================
# (Hierarchy data continues for E2..E8. The full data is loaded from the
# auxiliary module workspace_master_data.py to keep this file readable.)

# We import the rest of the hierarchy from a sibling data module for sanity.
# If the data module is missing, we fail fast with a clear error.
DATA_MODULE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "2026-05-07-workspace-master-data.py",
)
if not os.path.exists(DATA_MODULE):
    print(
        "ERROR: 2026-05-07-workspace-master-data.py not found alongside this script.\n"
        "       This script expects the rest of the hierarchy (E2..E8) to live there.\n"
        f"       Expected path: {DATA_MODULE}"
    )
    sys.exit(2)

# Load the data module (sibling file with hierarchy continuation)
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("workspace_master_data", DATA_MODULE)
data_mod = importlib.util.module_from_spec(spec)  # type: ignore
data_mod.__dict__["std_desc"] = std_desc
data_mod.__dict__["review_desc"] = review_desc
data_mod.__dict__["security_desc"] = security_desc
data_mod.__dict__["qa_desc"] = qa_desc
data_mod.__dict__["WORKSPACE_PREAMBLE"] = WORKSPACE_PREAMBLE
spec.loader.exec_module(data_mod)  # type: ignore

E2 = data_mod.E2
E3 = data_mod.E3
E4 = data_mod.E4
E5 = data_mod.E5
E6 = data_mod.E6
E7 = data_mod.E7
E8 = data_mod.E8

FEATURE["children"] = [E1, E2, E3, E4, E5, E6, E7, E8]


# ---------------------------------------------------------------------------
# Push driver
# ---------------------------------------------------------------------------

def walk_and_create(node: dict, parent_id: str | None, type_: str, id_map: dict, indent: int = 0) -> None:
    """Recursively create FEATURE → EPIC → STORY → TASK → SUBTASK in CodeBoard."""
    title = node["t"]
    desc = node["d"]
    priority = node.get("p", "MEDIUM")
    assignee = node.get("a")
    extra_labels = node.get("l", "")

    print(f"{'  ' * indent}→ Creating [{type_}] {node['id']}: {title[:60]}...", end=" ")
    try:
        result = create_issue(
            title=title,
            description=desc,
            type_=type_,
            priority=priority,
            parent_id=parent_id,
            assignee=assignee,
            extra_labels=extra_labels,
        )
        key = result["key"]
        iid = result["id"]
        id_map[node["id"]] = {"key": key, "id": iid, "title": title, "type": type_}
        print(f"OK {key}")
    except Exception as e:
        print(f"FAIL: {e}")
        id_map[node["id"]] = {"key": None, "id": None, "error": str(e), "title": title, "type": type_}
        return

    # Recurse — determine the next type level
    next_type_map = {
        "FEATURE": "EPIC",
        "EPIC": "STORY",
        "STORY": "TASK",
        "TASK": "SUBTASK",
    }
    children = node.get("children", []) or []
    next_type = next_type_map.get(type_)
    if not next_type or not children:
        return
    for child in children:
        walk_and_create(child, iid, next_type, id_map, indent + 1)
        time.sleep(0.05)  # gentle pacing — server-side rate limit safety


def main() -> None:
    print("=" * 80)
    print("AI Project Workspace — Master Push Script")
    print(f"Project: {PROJECT_ID}")
    print(f"Hierarchy: 1 FEATURE / 8 EPICs / 41 STORIES / 203 TASKS / 25 SUBTASKS")
    print("=" * 80)
    print()

    id_map: dict = {}
    walk_and_create(FEATURE, None, "FEATURE", id_map, 0)

    # Save id-map
    os.makedirs(os.path.dirname(ID_MAP_PATH), exist_ok=True)
    with open(ID_MAP_PATH, "w") as f:
        json.dump(id_map, f, indent=2, default=str)
    print()
    print(f"id-map saved to {ID_MAP_PATH}")

    # Summary
    total = len(id_map)
    failed = [k for k, v in id_map.items() if v.get("error")]
    print()
    print("=" * 80)
    print(f"Total created: {total - len(failed)} / {total}")
    if failed:
        print(f"Failed: {len(failed)}")
        for k in failed[:10]:
            print(f"  - {k}: {id_map[k].get('error', '')[:120]}")
    else:
        print("All OK ✓")
    print("=" * 80)


if __name__ == "__main__":
    main()
