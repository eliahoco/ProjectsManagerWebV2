"""
Studio Chat Agent — CB-2384

Implements the Jonny orchestrator persona for the Feature Studio planning surface.
Uses the Anthropic Messages API directly (streaming, native tool-use blocks).
Multi-tenant and cost-attributed from line one.

Contract with studio_orchestrator.py (Phase 4b, parallel agent):
    from services.studio_chat_agent import StudioChatAgent, get_studio_chat_agent
    async for event in agent.run_turn(session, db):
        ...

Event dict shapes:
    {"type": "token",               "delta": str}
    {"type": "tool_call_started",   "tool_call_id": str, "tool_name": str, "input": dict}
    {"type": "tool_call_completed", "tool_call_id": str, "output": dict, "error": str|None}
    {"type": "subagent_started",    "subagent_id": str, "agent_role": str, "input": dict}
    {"type": "subagent_completed",  "subagent_id": str, "output": dict}
    {"type": "message_complete",    "message_id": str, "tokens_input": int,
                                    "tokens_output": int, "cost_usd": float, "model": str}
    {"type": "turn_complete"}
    {"type": "error",               "error": str}
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

import anthropic
from anthropic import AsyncAnthropic

from app.config import settings
from models.studio import (
    StudioAgentActivity,
    StudioArtifact,
    StudioMessage,
    StudioSession,
)
from models.agent_runtime import TenantTokenUsage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Project root — read_repo_file paths must start here.
# Read from settings so Docker / CI environments can override via PROJECT_ROOT
# env var without touching this file.
_PROJECT_ROOT: str = settings.PROJECT_ROOT

# Internal loopback URL for CodeBoard API calls.
# Read from settings so the address is consistent with the bound host/port.
# Override via BACKEND_BASE_URL env var when running behind a proxy or in Docker.
_CODEBOARD_BASE: str = settings.backend_base_url

# Model identifiers
_MODEL_OPUS = "claude-opus-4-7"
_MODEL_SONNET = "claude-sonnet-4-6"
_MODEL_HAIKU = "claude-haiku-4-5-20251001"

# Pricing in USD per million tokens (input / output)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    _MODEL_OPUS:   (15.00, 75.00),
    _MODEL_SONNET: (3.00,  15.00),
    _MODEL_HAIKU:  (0.80,  4.00),
}
_DEFAULT_PRICING = _MODEL_PRICING[_MODEL_SONNET]

# Max clarifying questions per session
_MAX_CLARIFYING_QUESTIONS = 4

# Max chars returned by read_repo_file
_MAX_FILE_CHARS = 8_000

# Max issues returned by search_codeboard
_MAX_SEARCH_RESULTS = 20

# CB-2864 — secret-redaction patterns for CodeBoard write payloads + audit logs.
# Mirrors AutoPilot redaction policy (backend/services/autopilot_queue_service.py).
import re as _re

_SECRET_PATTERNS: tuple[tuple[_re.Pattern[str], str], ...] = (
    # sk-ant-* (Anthropic) is intentionally covered by the generic sk- rule below.
    (_re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", _re.IGNORECASE), "Bearer [REDACTED]"),
    (_re.compile(r"Basic\s+[A-Za-z0-9+/=]{16,}"), "Basic [REDACTED]"),
    (_re.compile(r"sk-[A-Za-z0-9._\-]{8,}"), "sk-[REDACTED]"),
    (_re.compile(r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9._\-]+['\"]?", _re.IGNORECASE), "api_key=[REDACTED]"),
    (_re.compile(r"(secret|token|auth)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]+['\"]?", _re.IGNORECASE), r"\1=[REDACTED]"),
    (_re.compile(r"password\s*[:=]\s*\S+", _re.IGNORECASE), "password=[REDACTED]"),
    (_re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[JWT REDACTED]"),
    (_re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA[REDACTED]"),
    (_re.compile(r"\bgh[poursa]_[A-Za-z0-9]{16,}"), "gh_[REDACTED]"),
    (_re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github_pat_[REDACTED]"),
    (_re.compile(r"\b(sk|pk|rk)_live_[A-Za-z0-9]{16,}"), r"\1_live_[REDACTED]"),
    (_re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "AIza[REDACTED]"),
    (_re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "xox_[REDACTED]"),
)
_MAX_DESCRIPTION_CHARS = 8_000


def _redact_secrets(text: str) -> str:
    """Strip common secret patterns. CB-2864 review M2: NO truncation here —
    separates security scrub from size cap so this helper is safe to compose
    across paths with different length limits."""
    if not text:
        return ""
    out = text
    for pattern, replacement in _SECRET_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def _cap_description(text: str) -> str:
    """Truncate to _MAX_DESCRIPTION_CHARS without modifying content."""
    return (text or "")[:_MAX_DESCRIPTION_CHARS]

# ---------------------------------------------------------------------------
# System prompt (cached)
# ---------------------------------------------------------------------------

_JONNY_SYSTEM_PROMPT = """You are Jonny, the VP R&D planning agent for the AI Project Workspace.

Your persona: methodical, honest, and disciplined. You think before you act.
You ask exactly as many clarifying questions as necessary — no more. When you
have enough to start, you start. You do not over-explain your process; you show
your work through structured outputs.

HIERARCHY DISCIPLINE (non-negotiable)

Every feature you plan must follow this exact hierarchy:
  FEATURE → EPIC → STORY → TASK → SUBTASK

Rules that are never broken:
1. One FEATURE per conversation — the top-level container.
2. 2–8 EPICs under the FEATURE — major work areas (e.g., "Backend API", "Frontend UI").
3. 2–5 STORYs per EPIC — user-facing capabilities, written as "User can [specific action]".
4. 2–5 TASKs per STORY — implementation units, specific and implementable.
5. 0–3 SUBTASKs per TASK — only when the task has meaningful decomposition.
6. No orphan nodes. Every item has a parent except the FEATURE.
7. Every title must be unique within the session.
8. Story titles must describe user value. Task titles must describe implementation work.

CLARIFICATION RULES

Ask clarifying questions when:
- The user's feature spans multiple independent domains that would produce
  conflicting architecture choices (e.g., "build a mobile app and a desktop app")
- The feature affects existing data models and the migration strategy is unclear
- The priority/urgency is ambiguous and affects how many EPICs are worth building

Do NOT ask clarifying questions when:
- The feature is clear enough to produce at least two EPICs
- You are more than 3 questions deep without drafting anything
- The user has explicitly said "just start"

Maximum clarifying questions before drafting: 4.

MULTI-TENANT SAFETY

Your session belongs to a single tenant. You must never reference, expose, or
infer data from another tenant's sessions. The tenant context is embedded in
the session. Every tool call is automatically scoped to your session.

TOOLS AVAILABLE

1. ask_clarifying_question — Ask the user a focused question before drafting.
   Use sparingly (max 4 per session). The answer arrives in the next user turn.
2. search_codeboard — Search existing CodeBoard issues for context before drafting.
   Use before proposing structure to avoid duplicating existing work.
3. read_repo_file — Read a project file to understand existing architecture.
   Absolute paths only; max 8K chars returned.
4. query_rag — Semantic search of the project's vector knowledge base.
   Use for pattern references and prior decisions.
5. create_artifact — Render a structured artifact (markdown, mermaid, code, HTML,
   hierarchy_json) in the preview pane. Use for all substantial outputs.
6. create_codeboard_issue — File a NEW CodeBoard issue (BUG / TASK / STORY /
   EPIC / FEATURE / SUBTASK). REQUIRES explicit user confirmation BEFORE call.
   Multi-tenant scoped to the current project. Used for bug reports, fix tasks,
   feature breakdowns the user wants tracked.
7. update_codeboard_issue_status — Move an existing issue between BACKLOG /
   TODO / IN_PROGRESS / COMPLETED_WAITING_QA. REQUIRES explicit user
   confirmation BEFORE call. DONE is blocked (Rule 22 — Eli only).

BUG-REPORT INTENT (Bible Rule 28)

When the user describes anything that sounds like a defect — "X is broken",
"doesn't work", "report a bug", "open a bug", "this fails", "something's
wrong", "fix this" — your job is:
  1. Acknowledge the report (one short line).
  2. Draft the ticket inline: title + description + priority + suggested fix
     options. Use a table or short structured block — not a wall of prose.
  3. Ask explicitly: "Ready to file? Confirm and I'll create the CodeBoard
     ticket." or similar. Wait for the user's confirmation.
  4. ONLY after the user confirms ("yes", "go", "approved", "file it"),
     call create_codeboard_issue with the drafted fields.
  5. After the tool returns, surface the issue key + link in chat.

Do NOT refuse to file bugs — you HAVE the create_codeboard_issue tool. The
old refusal pattern ("I'm just the planning agent, I don't have a create
bug tool") is INCORRECT and must not be used. If you find yourself about
to refuse, call create_codeboard_issue instead.

FEATURE / PLANNING INTENT (Bible Rule 23 + 32)

When the user wants a new feature planned:
  1. Draft the full FEATURE → EPIC → STORY → TASK → SUBTASK hierarchy as a
     create_artifact(kind=hierarchy_json) — not as chat prose.
  2. Per Rule 32, every leaf task must have an assigned agent
     (python-pro, react-specialist, code-reviewer, qa-regression skill, etc).
  3. EVERY feature plan must include Code Audit + QA + Full Regression epics
     as mandatory boilerplate.
  4. Ask for approval before any create_codeboard_issue calls.
  5. After approval, file the FEATURE first, then walk top-down filing each
     EPIC with parent_id pointing at the FEATURE, then each STORY/TASK.

STATUS UPDATE INTENT

When the user asks you to update an issue's status:
  1. Confirm the intended transition. Cite Rule 22 if they ask for DONE
     (that's blocked — only Eli flips DONE).
  2. Call update_codeboard_issue_status after confirmation.

ARTIFACT DISCIPLINE

Create a mermaid artifact for system/data diagrams — not chat text.
Create a hierarchy_json artifact for the breakdown draft — not chat text.
Create a markdown artifact for long explanatory documents — not chat text.
Short (< 200 word) explanations belong in the chat, not as artifacts.

APPROVAL GATE

NEVER write to CodeBoard (create_codeboard_issue, update_codeboard_issue_status)
without explicit user confirmation in the chat. When in doubt, ask: "Ready to
file? Confirm." or "Confirm: move CB-XXXX to IN_PROGRESS?".

VISIBILITY

Before saying "I'm calling a tool", call the tool. Never claim a dispatch
happened before the tool has been called.

If a sub-agent returns an error with retryable=true, try once more. If it
fails twice, inform the user and offer to proceed with available information.

JONNY BIBLE (the 32 rules that govern your behavior — cite by number when refusing)

1. Data flow first — verify before deployment.
2. Reliability & stability — atomic writes, error isolation, circuit breakers.
3. Feature coverage top to bottom — full agile hierarchy.
4. Architecture before deployment — design before code.
5. Spawn agents as needed — orchestrate, supervise, QA each.
6. Work professional — like a VP R&D.
7. Work agile — Feature → Epic → Story → Task → Subtask.
8. Always report back — status after every sprint.
9. QA everything — nothing ships without verification.
10. Work the bible top to bottom.
11. Monitor yourself every 15 min.
12. Don't ask to keep going — just keep going.
13. Show status inline with checkboxes — never send to files.
14. Enterprise-level quality.
15. NEVER revert/rollback without risk analysis + explicit approval.
16. NEVER do experimental fixes on production.
17. Advisor-Executor: Opus advises, Sonnet/Haiku execute.
18. Pre-deploy: code-reviewer + security-auditor + debugger + Chrome UI gates.
19. Data flow preservation — map current flow, re-verify after change.
20. Agent orchestration protocol — decompose, route, QA, gate or loop.
21. User layer (preferences, API keys) NEVER auto-updated by code.
22. Nothing goes to DONE except by Eli. Code completes -> COMPLETED_WAITING_QA.
23. CodeBoard BEFORE code — present plan, get approval, push, then code.
24. Chrome visual QA on EVERY UI change.
25. Full regression test for EVERY feature.
26. CodeBoard is single source of truth — read it, fulfil it, do not improvise.
27. Durable artifacts in project dir, not /tmp.
28. ANY bug report = Rule 23 trigger — file CodeBoard FIRST.
29. Push scripts per-project + per-session, never shared /tmp/.
30. qa-regression skill is the gate to COMPLETED_WAITING_QA.
31. Design-intent comments must cite the source document + line.
32. Plans are tables, every task has an agent, every feature includes
    Code Audit + QA + Full Regression epics. No walls of bullets.
33. At the start of every new feature, ASK the user explicitly:
    "Mockup first to validate, or full planning + architecture +
    implementation?" Mockup = fast disposable visual prototype, zero
    backend, zero audits. Full = Rule 23 + 32 in force (CodeBoard tree,
    agent assignments, Code Audit + QA + Regression epics, real build).
    The two paths are not interchangeable. Default behavior was to jump
    straight to full planning — that's wrong when the user is still
    exploring an idea. Phrase the question once up front; the answer
    dictates the entire engagement.

FLEXIBILITY (Rule-aware, not rule-rigid)

You are flexible about HOW the user phrases a request — "open a bug" /
"file a ticket" / "report this" / "log this" / "track this" all mean the
same thing. You are STRICT about the rules themselves — never bypass
approval gates, never auto-flip DONE, never write outside the current
project. When refusing, cite the specific rule number ("Per Rule 22 ...").
When the user proposes a workaround that would violate a rule, explain why
the rule exists and offer the compliant path instead.
"""


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic tool schema)
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ask_clarifying_question",
        "description": (
            "Use this when the user's request is ambiguous and you need a specific "
            "answer before you can draft an architecture or breakdown. Do NOT use "
            "this more than 4 times per session without making progress — if you have "
            "enough to start, start. Each question should be targeted and answerable "
            "in 1-2 sentences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The specific question to ask the user. One question per call.",
                },
                "context": {
                    "type": "string",
                    "description": "Brief explanation of why this answer changes the architecture.",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "search_codeboard",
        "description": (
            "Search existing CodeBoard issues in a project for context. Use this before "
            "drafting a breakdown to understand what similar work has already been done "
            "or planned. Returns up to 20 matching issues."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search query.",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project ID to scope the search. Defaults to the session project.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_repo_file",
        "description": (
            "Read the content of a specific file in the project repository. Use this "
            "to understand existing architecture (e.g., read backend/models/issue.py "
            "to see the current data model before proposing schema changes). "
            "The path must be an absolute path starting with "
            f"'{_PROJECT_ROOT}'. Relative paths are rejected. "
            "Content is capped at 8,000 characters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        f"Absolute path starting with '{_PROJECT_ROOT}'. "
                        "E.g., '/Volumes/Seagate/Claude/ProjectsManagerWebV2Production/backend/models/issue.py'."
                    ),
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "query_rag",
        "description": (
            "Query the RAG vector store for semantically relevant context about this "
            "project. Use this when you need pattern references or prior decisions "
            "that may not be findable with keyword search. Returns top-k results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The semantic search query.",
                },
                "n_results": {
                    "type": "integer",
                    "description": "Number of results to return (1–20). Defaults to 5.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "create_artifact",
        "description": (
            "Render a structured artifact for display in the preview pane. Use this "
            "when you have produced content (a Mermaid diagram, a code snippet, a "
            "markdown document, a hierarchy JSON, or an HTML preview) that the user "
            "should see rendered, not just as chat text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable label for the preview pane tab.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["markdown", "mermaid", "code", "html", "hierarchy_json"],
                    "description": "The artifact content type.",
                },
                "content": {
                    "type": "string",
                    "description": "The full artifact content string.",
                },
            },
            "required": ["name", "kind", "content"],
        },
    },
    # -----------------------------------------------------------------------
    # Phase 2 write tools — CB-2864 (Studio Action Surface, 2026-05-22).
    # -----------------------------------------------------------------------
    {
        "name": "create_codeboard_issue",
        "description": (
            "File a new CodeBoard issue (BUG / TASK / STORY / EPIC / FEATURE / SUBTASK). "
            "ONLY call this AFTER the user has explicitly confirmed they want the ticket "
            "filed (e.g. user says 'approved', 'go', 'yes file it'). Multi-tenant: the "
            "issue is filed under the current session's project_id; cross-project writes "
            "are hard-blocked. If the user describes a bug ('X is broken', 'doesn't work', "
            "'report a bug', 'open a bug') you should ALWAYS draft the title + description "
            "+ priority + suggested fix options first, ask 'Ready to file? Confirm.', and "
            "only then call this tool after the user confirms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short issue title (max 200 chars)."},
                "description": {"type": "string", "description": "Markdown description — include repro steps, suggested fix options, related context."},
                "type": {
                    "type": "string",
                    "enum": ["BUG", "TASK", "STORY", "EPIC", "FEATURE", "SUBTASK"],
                    "description": "Issue type. Use BUG for defect reports, TASK for small work units.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "description": "Priority. CRITICAL only for production-down / data-loss issues.",
                },
                "parent_id": {
                    "type": "string",
                    "description": "Optional parent issue UUID for hierarchy (epic→story→task chain).",
                },
                "labels": {
                    "type": "string",
                    "description": "Optional kebab-case label string for grouping (e.g. 'studio-action-surface').",
                },
            },
            "required": ["title", "type", "priority"],
        },
    },
    {
        "name": "update_codeboard_issue_status",
        "description": (
            "Update the status of an existing CodeBoard issue. Allowed transitions: "
            "BACKLOG → TODO → IN_PROGRESS → COMPLETED_WAITING_QA. Direct flip to DONE "
            "is BLOCKED — per Bible Rule 22 only Eli promotes to DONE via manual QA. "
            "ONLY call this after the user has confirmed (e.g. 'mark CB-1234 in progress'). "
            "Multi-tenant: only issues belonging to the current session's project are "
            "writable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "CodeBoard issue key (e.g. 'CB-2864').",
                },
                "target_status": {
                    "type": "string",
                    "enum": ["BACKLOG", "TODO", "IN_PROGRESS", "COMPLETED_WAITING_QA"],
                    "description": "Target status. DONE is intentionally excluded — see tool description.",
                },
            },
            "required": ["issue_key", "target_status"],
        },
    },
    # -----------------------------------------------------------------------
    # Future tools (orchestration) — not implemented in CB-2864 Phase 1.
    # Tracked in CB-2877 (E2 Orchestration).
    # -----------------------------------------------------------------------
    # {"name": "spawn_subagent", ...},
    # {"name": "hand_to_autopilot", ...},
]


# ---------------------------------------------------------------------------
# Cost helpers
# ---------------------------------------------------------------------------

def _compute_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    """Return cost in USD for a given model and token counts."""
    input_price, output_price = _MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (tokens_input * input_price + tokens_output * output_price) / 1_000_000


# ---------------------------------------------------------------------------
# StudioChatAgent
# ---------------------------------------------------------------------------

class StudioChatAgent:
    """
    Orchestrates a single planning conversation turn for the Studio feature.

    Each call to ``run_turn`` fetches full conversation history from the DB,
    routes to the correct model, streams the Anthropic response, executes
    tool calls inline, and emits structured event dicts for the orchestrator
    to forward over SSE.
    """

    def __init__(
        self,
        db_factory: Callable,
        anthropic_client: Optional[AsyncAnthropic] = None,
    ) -> None:
        self._db_factory = db_factory
        if anthropic_client is not None:
            self.client = anthropic_client
        else:
            api_key = settings.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
            self.client = AsyncAnthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_turn(
        self,
        session: StudioSession,
        db: AsyncSession,
    ) -> AsyncIterator[dict]:
        """
        Run one assistant turn for the given session.

        Yields event dicts. The orchestrator persists messages and forwards
        events over SSE.
        """
        # 1. Token budget guard
        if session.tokensUsed >= session.tokenBudget:
            yield {"type": "error", "error": "Session token budget exceeded"}
            return

        try:
            async for event in self._run_turn_inner(session, db):
                yield event
        except asyncio.CancelledError:
            # Client disconnected — persist partial state, re-raise
            logger.warning("run_turn cancelled for session %s", session.id)
            await self._record_activity(
                db,
                session,
                verb="NOTIFY",
                source_agent="jonny",
                target_agent="system",
                payload={"kind": "cancelled"},
            )
            raise
        except anthropic.APIStatusError as exc:
            error_msg = f"Anthropic API error {exc.status_code}: {exc.message}"
            logger.error("API error in session %s: %s", session.id, error_msg)
            await self._record_activity(
                db,
                session,
                verb="NOTIFY",
                source_agent="jonny",
                target_agent="system",
                payload={"kind": "api_error", "status_code": exc.status_code},
            )
            yield {"type": "error", "error": error_msg}
        except Exception:
            # CRIT-2: log full exception server-side; never emit raw exc text over SSE.
            logger.exception("Unexpected error in run_turn for session %s", session.id)
            yield {"type": "error", "error": "An internal error occurred"}

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------

    async def _run_turn_inner(
        self,
        session: StudioSession,
        db: AsyncSession,
    ) -> AsyncIterator[dict]:
        """Core turn logic: classify → route → stream → tool loop."""
        # Load conversation history
        messages = await self._load_messages(session, db)

        # Classify user turn to select model
        last_user_content = self._last_user_text(messages)
        routed_model = await self._classify_and_route(last_user_content)
        logger.info(
            "Session %s routing to %s (last user: %.60r)",
            session.id,
            routed_model,
            last_user_content,
        )

        # Run the streaming agent loop (handles multi-turn tool calls)
        total_input_tokens = 0
        total_output_tokens = 0
        message_id = str(uuid.uuid4())
        # Final assistant text across all tool-use rounds — sent in
        # message_complete so the orchestrator can persist it to
        # StudioMessage.content (otherwise the DB row has empty content
        # and the UI shows no assistant response after refetch).
        final_assistant_text = ""

        # We keep an accumulated messages list that grows with tool results
        working_messages = list(messages)

        while True:
            # Budget check before each API call
            if (session.tokensUsed + total_input_tokens + total_output_tokens) >= session.tokenBudget:
                yield {"type": "error", "error": "Session token budget exceeded mid-turn"}
                return

            tool_calls_this_round: list[dict] = []
            text_accumulated = ""

            async with self.client.messages.stream(
                model=routed_model,
                system=[
                    {
                        "type": "text",
                        "text": _JONNY_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=working_messages,
                tools=_TOOLS,  # type: ignore[arg-type]
                max_tokens=8000,
            ) as stream:
                async for chunk in stream:
                    if chunk.type == "content_block_delta":
                        delta = chunk.delta
                        if delta.type == "text_delta":
                            text_accumulated += delta.text
                            yield {"type": "token", "delta": delta.text}
                        elif delta.type == "input_json_delta":
                            # Accumulate JSON for the current tool block
                            if tool_calls_this_round:
                                tool_calls_this_round[-1]["_input_partial"] += delta.partial_json

                    elif chunk.type == "content_block_start":
                        block = chunk.content_block
                        if block.type == "tool_use":
                            tool_calls_this_round.append({
                                "tool_call_id": block.id,
                                "tool_name": block.name,
                                "_input_partial": "",
                                "input": {},
                            })

                    elif chunk.type == "message_delta":
                        if hasattr(chunk, "usage") and chunk.usage:
                            total_output_tokens += chunk.usage.output_tokens

                    elif chunk.type == "message_start":
                        if hasattr(chunk, "message") and chunk.message.usage:
                            total_input_tokens += chunk.message.usage.input_tokens

                # Finalize tool call inputs from accumulated JSON
                import json as _json
                for tc in tool_calls_this_round:
                    raw = tc.pop("_input_partial", "")
                    try:
                        tc["input"] = _json.loads(raw) if raw else {}
                    except _json.JSONDecodeError:
                        tc["input"] = {}

            # Append this round's text to the final response. Each round
            # ends with either a final answer (text + no tool calls) or
            # an intermediate text block + tool calls. We want the full
            # concatenation persisted into StudioMessage.content.
            if text_accumulated:
                final_assistant_text += text_accumulated

            # If no tool calls, we're done
            if not tool_calls_this_round:
                break

            # Execute each tool call
            tool_results = []
            for tc in tool_calls_this_round:
                tool_name = tc["tool_name"]
                tool_call_id = tc["tool_call_id"]
                tool_input = tc["input"]

                yield {
                    "type": "tool_call_started",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "input": tool_input,
                }

                output, error = await self._dispatch_tool(
                    tool_name, tool_input, session, db
                )

                yield {
                    "type": "tool_call_completed",
                    "tool_call_id": tool_call_id,
                    "output": output,
                    "error": error,
                }

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": _json.dumps(output if error is None else {"error": error}),
                })

            # Reconstruct the assistant message for this round (text + tool_use blocks)
            assistant_content: list[dict] = []
            if text_accumulated:
                assistant_content.append({"type": "text", "text": text_accumulated})
            for tc in tool_calls_this_round:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["tool_call_id"],
                    "name": tc["tool_name"],
                    "input": tc["input"],
                })

            # Append to working messages for next round
            working_messages.append({"role": "assistant", "content": assistant_content})
            working_messages.append({"role": "user", "content": tool_results})

            # Continue the loop for the next model turn

        # Compute cost and emit message_complete
        cost_usd = _compute_cost(routed_model, total_input_tokens, total_output_tokens)

        # Roll up to TenantTokenUsage
        await self._upsert_tenant_token_usage(
            db,
            tenant_id=session.tenantId or settings.DEFAULT_TENANT_ID,
            model=routed_model,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            cost_usd=cost_usd,
        )

        # MED-1: persist token consumption back to the session so the per-session
        # budget guard works correctly across multiple turns.
        try:
            session.tokensUsed = (session.tokensUsed or 0) + total_input_tokens + total_output_tokens
            await db.commit()
        except Exception:
            logger.exception("Failed to update session.tokensUsed for session %s", session.id)
            await db.rollback()

        yield {
            "type": "message_complete",
            "message_id": message_id,
            "content": final_assistant_text,
            "tokens_input": total_input_tokens,
            "tokens_output": total_output_tokens,
            "cost_usd": cost_usd,
            "model": routed_model,
        }
        yield {"type": "turn_complete"}

    # ------------------------------------------------------------------
    # Model routing via Haiku classifier
    # ------------------------------------------------------------------

    async def _classify_and_route(self, user_text: str) -> str:
        """
        Call Haiku to classify the user turn type, then select the model.

        Classification:
            clarification → Haiku
            planning      → Opus
            revision      → Sonnet
            approval      → Haiku
            (fallback)    → Sonnet
        """
        if not user_text:
            return _MODEL_SONNET

        try:
            classifier_response = await self.client.messages.create(
                model=_MODEL_HAIKU,
                max_tokens=10,
                system=(
                    "Classify the user message as one of: clarification, planning, revision, approval. "
                    "Reply with ONE WORD only."
                ),
                messages=[{"role": "user", "content": user_text[:500]}],
            )
            classification = classifier_response.content[0].text.strip().lower()
            logger.debug("Turn classification: %r", classification)

            routing = {
                "clarification": _MODEL_HAIKU,
                "planning":      _MODEL_OPUS,
                "revision":      _MODEL_SONNET,
                "approval":      _MODEL_HAIKU,
            }
            return routing.get(classification, _MODEL_SONNET)

        except Exception as exc:
            logger.warning("Classifier call failed (%s), defaulting to Sonnet", exc)
            return _MODEL_SONNET

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    async def _load_messages(
        self, session: StudioSession, db: AsyncSession
    ) -> list[dict]:
        """
        Fetch all StudioMessage rows for this session and convert to
        the Anthropic messages format.
        """
        result = await db.execute(
            select(StudioMessage)
            .where(
                and_(
                    StudioMessage.sessionId == session.id,
                    StudioMessage.tenantId == (session.tenantId or settings.DEFAULT_TENANT_ID),
                )
            )
            .order_by(StudioMessage.sequenceNum)
        )
        rows: list[StudioMessage] = list(result.scalars().all())

        messages: list[dict] = []
        for row in rows:
            role = row.role.lower()
            if role == "user":
                role = "user"
            elif role in ("assistant", "sub_agent"):
                role = "assistant"
            elif role == "tool_result":
                role = "user"
            else:
                role = "user"

            content = row.content
            # content is stored as the Anthropic content block list (JSONB)
            if isinstance(content, list):
                messages.append({"role": role, "content": content})
            elif isinstance(content, str):
                messages.append({"role": role, "content": content})
            elif isinstance(content, dict):
                # Single content block
                messages.append({"role": role, "content": [content]})

        return messages

    @staticmethod
    def _last_user_text(messages: list[dict]) -> str:
        """Extract the text of the last user message for classification."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                    return " ".join(parts)
        return ""

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _dispatch_tool(
        self,
        tool_name: str,
        tool_input: dict,
        session: StudioSession,
        db: AsyncSession,
    ) -> tuple[dict, Optional[str]]:
        """
        Dispatch a tool call and return (output_dict, error_string | None).
        Never raises — exceptions are converted to error strings.
        """
        handlers: dict[str, Callable] = {
            "ask_clarifying_question":       self._tool_ask_clarifying_question,
            "search_codeboard":              self._tool_search_codeboard,
            "read_repo_file":                self._tool_read_repo_file,
            "query_rag":                     self._tool_query_rag,
            "create_artifact":               self._tool_create_artifact,
            # CB-2864 write tools
            "create_codeboard_issue":        self._tool_create_codeboard_issue,
            "update_codeboard_issue_status": self._tool_update_codeboard_issue_status,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return {}, f"Unknown tool: {tool_name}"

        try:
            output = await handler(tool_input, session, db)
            return output, None
        except Exception:
            # CRIT-2: log full exception server-side; return fixed string to caller.
            logger.exception("Tool %r raised unexpectedly", tool_name)
            return {}, "An internal error occurred"

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def _tool_ask_clarifying_question(
        self, inputs: dict, session: StudioSession, db: AsyncSession
    ) -> dict:
        """
        ask_clarifying_question — max 4 per session.
        Returns the question so the model can render it in chat.
        The answer arrives in the next user turn naturally.
        """
        question = inputs.get("question", "")
        context = inputs.get("context", "")

        # Count how many clarifying questions have been asked this session
        result = await db.execute(
            select(StudioAgentActivity).where(
                and_(
                    StudioAgentActivity.sessionId == session.id,
                    StudioAgentActivity.verb == "REQUEST",
                    StudioAgentActivity.sourceAgent == "jonny",
                    StudioAgentActivity.targetAgent == "user",
                )
            )
        )
        question_count = len(result.scalars().all())

        if question_count >= _MAX_CLARIFYING_QUESTIONS:
            return {
                "error": (
                    f"Maximum clarifying questions ({_MAX_CLARIFYING_QUESTIONS}) reached. "
                    "Proceed with available information."
                ),
                "retryable": False,
            }

        # Record the activity (Visibility Principle: DB row first)
        await self._record_activity(
            db,
            session,
            verb="REQUEST",
            source_agent="jonny",
            target_agent="user",
            payload={"question": question[:200], "context": context[:200]},
        )

        return {"question": question, "context": context}

    async def _tool_search_codeboard(
        self, inputs: dict, session: StudioSession, db: AsyncSession
    ) -> dict:
        """
        search_codeboard — calls GET /api/projects/{project_id}/issues?search=...
        via httpx against the loopback CodeBoard API.
        """
        query = inputs.get("query", "")
        project_id = inputs.get("project_id") or session.projectId

        if not query:
            return {"issues": [], "error": "query is required"}

        headers: dict[str, str] = {}
        internal_token = settings.INTERNAL_API_TOKEN
        if internal_token:
            headers["X-Internal-Token"] = internal_token

        # Resolve base URL at call time from settings (not the module-level
        # constant) so BACKEND_BASE_URL overrides take effect without restart.
        codeboard_base = settings.backend_base_url

        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.get(
                    f"{codeboard_base}/api/issues/{project_id}",
                    params={"search": query, "limit": _MAX_SEARCH_RESULTS},
                    headers=headers,
                )
            if response.status_code != 200:
                return {
                    "issues": [],
                    "error": f"CodeBoard API returned {response.status_code}",
                }

            data = response.json()
            # Normalize: could be a list or paginated response
            if isinstance(data, list):
                raw_issues = data
            elif isinstance(data, dict):
                raw_issues = data.get("issues", data.get("items", []))
            else:
                raw_issues = []

            issues = [
                {
                    "key": i.get("key", ""),
                    "title": i.get("title", ""),
                    "type": i.get("type", ""),
                    "status": i.get("status", ""),
                    "summary": (i.get("description") or "")[:200],
                }
                for i in raw_issues[:_MAX_SEARCH_RESULTS]
            ]
            return {"issues": issues}

        except httpx.RequestError as exc:
            logger.warning("CodeBoard search request failed: %s", exc)
            return {"issues": [], "error": f"Network error: {exc}"}

    async def _tool_read_repo_file(
        self, inputs: dict, session: StudioSession, db: AsyncSession
    ) -> dict:
        """
        read_repo_file — reads a file from the project repository.
        Absolute paths only; must start with _PROJECT_ROOT (= settings.PROJECT_ROOT).
        """
        path = inputs.get("path", "")

        # _PROJECT_ROOT is initialised from settings.PROJECT_ROOT at import time
        # so that env-var overrides are respected.  Tests can patch the module-level
        # constant directly with unittest.mock.patch.
        project_root = _PROJECT_ROOT

        # Security: reject relative paths and paths outside the project root
        if not path.startswith("/"):
            return {
                "error": (
                    "Relative paths are not allowed. Provide an absolute path starting with "
                    f"'{project_root}'."
                ),
                "retryable": False,
            }
        if not path.startswith(project_root):
            return {
                "error": (
                    f"Path must start with '{project_root}'. "
                    "Access outside the project root is not permitted."
                ),
                "retryable": False,
            }
        # Guard against path traversal
        if ".." in path:
            return {
                "error": "Path traversal sequences ('..') are not permitted.",
                "retryable": False,
            }

        # HIGH-1: resolve symlinks and re-validate to prevent escaping via symlink chains.
        real = os.path.realpath(path)
        if not real.startswith(project_root):
            return {
                "error": "Path resolves outside project root after symlink expansion.",
                "retryable": False,
            }

        try:
            with open(real, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read(_MAX_FILE_CHARS)
                truncated = len(fh.read(1)) > 0  # peek: is there more?
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            return {
                "content": content,
                "line_count": line_count,
                "truncated": truncated,
                "path": real,
            }
        except FileNotFoundError:
            return {"error": f"File not found: {path}", "retryable": False}
        except PermissionError:
            return {"error": f"Permission denied: {path}", "retryable": False}
        except OSError as exc:
            return {"error": f"OS error reading {path}: {exc}", "retryable": False}

    async def _tool_query_rag(
        self, inputs: dict, session: StudioSession, db: AsyncSession
    ) -> dict:
        """
        query_rag — delegates to the existing RAGService.search_issues.
        """
        question = inputs.get("question", "")
        n_results = min(int(inputs.get("n_results", 5)), 20)

        if not question:
            return {"results": [], "error": "question is required"}

        try:
            from services.rag_service import rag_service as _rag

            raw = await _rag.search_issues(
                project_id=session.projectId,
                query=question,
                n_results=n_results,
            )
            results = [
                {
                    "text": r.get("document", ""),
                    "score": r.get("score", 0.0),
                    "source": r.get("key", r.get("issue_id", "")),
                }
                for r in raw
            ]
            return {"results": results}

        except Exception as exc:
            logger.warning("RAG query failed: %s", exc)
            return {"results": [], "error": f"RAG error: {exc}"}

    async def _tool_create_artifact(
        self, inputs: dict, session: StudioSession, db: AsyncSession
    ) -> dict:
        """
        create_artifact — writes a StudioArtifact row and returns the artifact_id.
        """
        name = inputs.get("name", "Untitled")
        kind_raw = inputs.get("kind", "markdown").upper()
        content = inputs.get("content", "")

        # Map input enum values to the DB enum (uppercase)
        kind_map = {
            "MARKDOWN": "MARKDOWN",
            "MERMAID": "MERMAID",
            "CODE": "CODE",
            "HTML": "HTML",
            "HIERARCHY_JSON": "HIERARCHY_JSON",
        }
        kind = kind_map.get(kind_raw, "MARKDOWN")

        content_bytes = content.encode("utf-8")
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)
        artifact_id = str(uuid.uuid4())
        tenant_id = session.tenantId or settings.DEFAULT_TENANT_ID

        artifact = StudioArtifact(
            id=artifact_id,
            tenantId=tenant_id,
            sessionId=session.id,
            name=name,
            kind=kind,
            content=content[:65536],   # inline cap 64 KB
            sizeBytes=size_bytes,
            sha256=sha256,
            version=1,
        )
        db.add(artifact)
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to persist artifact: %s", exc)
            return {"error": f"Database error: {exc}", "retryable": True}

        return {"artifact_id": artifact_id, "name": name, "kind": kind}

    # ------------------------------------------------------------------
    # CodeBoard write tools (CB-2864, 2026-05-22)
    # ------------------------------------------------------------------

    async def _tool_create_codeboard_issue(
        self, inputs: dict, session: StudioSession, db: AsyncSession
    ) -> dict:
        """
        create_codeboard_issue — POST /api/projects/{project_id}/issues.

        Multi-tenant guard: scoped to session.projectId. Cross-project writes
        are hard-blocked at this layer (the model has no project_id parameter
        on the tool — it cannot specify a different project).

        Caller (Anthropic model) is required by the tool description + system
        prompt to confirm with the user BEFORE invoking. This handler does not
        re-prompt; the gate lives in the model layer.

        Audit log: every successful write emits a redacted log line with
        sessionId + projectId + new issue key.
        """
        title = (inputs.get("title") or "").strip()
        description = (inputs.get("description") or "").strip()
        type_ = (inputs.get("type") or "").strip().upper()
        priority = (inputs.get("priority") or "MEDIUM").strip().upper()
        parent_id = inputs.get("parent_id")
        labels = inputs.get("labels") or ""

        if not title:
            return {"error": "title is required", "retryable": False}
        if type_ not in {"BUG", "TASK", "STORY", "EPIC", "FEATURE", "SUBTASK"}:
            return {"error": f"invalid type '{type_}'", "retryable": False}
        if priority not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            return {"error": f"invalid priority '{priority}'", "retryable": False}

        project_id = session.projectId
        if not project_id:
            return {"error": "session has no project_id; cannot file issue", "retryable": False}

        # CB-2864 review M3+M4: redact title + labels too, not just description.
        # User-pasted curl output containing `Bearer ...` could land in any field
        # since Jonny drafts all of them from raw user input.
        safe_title = _redact_secrets(title)[:200]
        safe_labels = _redact_secrets(labels)[:120] if isinstance(labels, str) else ""
        safe_description = _cap_description(_redact_secrets(description))
        body: dict[str, Any] = {
            "title": safe_title,
            "type": type_,
            "priority": priority,
            "description": safe_description,
            "reporter": "AI-Studio-Jonny",
            "labels": safe_labels,
        }

        # CB-2864 review HIGH-2: validate parent_id belongs to the session's
        # project. Without this guard, a prompt-injected model could anchor a
        # new issue under a parent in another project, leaking cross-tenant
        # hierarchy linkage. Verify by GET — if parent's projectId mismatches
        # session.projectId, reject the write entirely.
        if parent_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as http:
                    parent_resp = await http.get(
                        f"{settings.backend_base_url}/api/issues/{parent_id}",
                        headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN}
                        if settings.INTERNAL_API_TOKEN else {},
                    )
                if parent_resp.status_code != 200:
                    return {
                        "error": f"parent_id {parent_id} not accessible (HTTP {parent_resp.status_code})",
                        "retryable": False,
                    }
                parent_pid = parent_resp.json().get("projectId")
                if parent_pid is None or parent_pid != project_id:
                    return {
                        "error": (
                            f"parent_id belongs to project {parent_pid}, not session project "
                            f"{project_id} — cross-project hierarchy is blocked by multi-tenant guard."
                        ),
                        "retryable": False,
                    }
                body["parentId"] = parent_id
            except httpx.RequestError as exc:
                return {"error": f"Parent lookup failed: {exc}", "retryable": True}

        headers: dict[str, str] = {"Content-Type": "application/json"}
        internal_token = settings.INTERNAL_API_TOKEN
        if internal_token:
            headers["X-Internal-Token"] = internal_token

        codeboard_base = settings.backend_base_url
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.post(
                    f"{codeboard_base}/api/projects/{project_id}/issues",
                    json=body,
                    headers=headers,
                )
            if response.status_code not in (200, 201):
                # CB-2864 review MED-4: redact error echo so server validation
                # messages that include offending field values don't leak secrets.
                return {
                    "error": f"CodeBoard API returned HTTP {response.status_code}: {_redact_secrets(response.text)[:200]}",
                    "retryable": response.status_code >= 500,
                }
            created = response.json()
        except httpx.RequestError as exc:
            logger.warning("create_codeboard_issue network error: %s", exc)
            return {"error": f"Network error: {exc}", "retryable": True}

        issue_key = created.get("key") or "(unknown)"
        issue_id = created.get("id")
        logger.info(
            "Studio Jonny filed CodeBoard issue session=%s project=%s key=%s type=%s",
            session.id, project_id, issue_key, type_,
        )

        # Record activity (Visibility Principle: DB row for the write).
        # CB-2864 review M4: payload stores redacted title — secrets must not
        # leak into the activity log even if they slipped past chat redaction.
        await self._record_activity(
            db,
            session,
            verb="FILE_ISSUE",
            source_agent="jonny",
            target_agent="codeboard",
            payload={
                "issue_key": issue_key,
                "issue_id": issue_id,
                "type": type_,
                "priority": priority,
                "title": safe_title,
            },
        )

        return {
            "issue_key": issue_key,
            "issue_id": issue_id,
            "title": safe_title,
            "type": type_,
            "priority": priority,
            "url": f"/codeboard?issue={issue_key}",
        }

    async def _tool_update_codeboard_issue_status(
        self, inputs: dict, session: StudioSession, db: AsyncSession
    ) -> dict:
        """
        update_codeboard_issue_status — PATCH /api/issues/{id}.

        Multi-tenant guard: GET the issue first, reject if its projectId does
        not match the session's projectId. Block direct flip to DONE per
        Bible Rule 22 (only Eli promotes to DONE).
        """
        issue_key = (inputs.get("issue_key") or "").strip().upper()
        target_status = (inputs.get("target_status") or "").strip().upper()

        if not issue_key:
            return {"error": "issue_key is required", "retryable": False}
        allowed = {"BACKLOG", "TODO", "IN_PROGRESS", "COMPLETED_WAITING_QA"}
        if target_status == "DONE":
            return {
                "error": "Direct flip to DONE is blocked by Bible Rule 22 — only Eli promotes via manual QA.",
                "retryable": False,
                "rule_cited": "Rule 22",
            }
        if target_status not in allowed:
            return {
                "error": f"invalid target_status '{target_status}'. Allowed: {sorted(allowed)}.",
                "retryable": False,
            }

        project_id = session.projectId
        if not project_id:
            return {"error": "session has no project_id", "retryable": False}

        headers: dict[str, str] = {"Content-Type": "application/json"}
        internal_token = settings.INTERNAL_API_TOKEN
        if internal_token:
            headers["X-Internal-Token"] = internal_token
        codeboard_base = settings.backend_base_url

        # 1. Resolve issue_key -> issue id + project_id (for tenant guard).
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                lookup = await http.get(
                    f"{codeboard_base}/api/projects/{project_id}/issues",
                    params={"search": issue_key, "limit": 50},
                    headers=headers,
                )
            if lookup.status_code != 200:
                return {
                    "error": f"Lookup failed: HTTP {lookup.status_code}",
                    "retryable": lookup.status_code >= 500,
                }
            lookup_data = lookup.json()
            items = (
                lookup_data if isinstance(lookup_data, list)
                else lookup_data.get("items", lookup_data.get("issues", []))
            )
            match = next((i for i in items if i.get("key", "").upper() == issue_key), None)
        except httpx.RequestError as exc:
            return {"error": f"Network error during lookup: {exc}", "retryable": True}

        if not match:
            return {
                "error": (
                    f"Issue {issue_key} not found in this project ({project_id}). "
                    "Cross-project writes are not permitted."
                ),
                "retryable": False,
            }
        # CB-2864 review M1: fail closed if API stops returning projectId.
        # Original `or project_id` fallback silently neutralised this guard.
        match_pid = match.get("projectId")
        if match_pid is None or match_pid != project_id:
            return {
                "error": "Issue belongs to a different project — write rejected by multi-tenant guard.",
                "retryable": False,
            }

        issue_id = match.get("id")
        if not issue_id:
            return {"error": "Resolved issue is missing an id", "retryable": False}

        # 2. PATCH the status.
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                patch = await http.patch(
                    f"{codeboard_base}/api/issues/{issue_id}",
                    json={"status": target_status},
                    headers=headers,
                )
            if patch.status_code not in (200, 204):
                return {
                    "error": f"PATCH failed: HTTP {patch.status_code}: {patch.text[:200]}",
                    "retryable": patch.status_code >= 500,
                }
        except httpx.RequestError as exc:
            return {"error": f"Network error during PATCH: {exc}", "retryable": True}

        logger.info(
            "Studio Jonny updated CodeBoard status session=%s project=%s key=%s -> %s",
            session.id, project_id, issue_key, target_status,
        )
        await self._record_activity(
            db,
            session,
            verb="UPDATE_STATUS",
            source_agent="jonny",
            target_agent="codeboard",
            payload={"issue_key": issue_key, "issue_id": issue_id, "target_status": target_status},
        )

        return {
            "issue_key": issue_key,
            "issue_id": issue_id,
            "previous_status": match.get("status"),
            "new_status": target_status,
        }

    # ------------------------------------------------------------------
    # Sub-agent stubs (Phase 2)
    # ------------------------------------------------------------------

    async def _spawn_subagent_stub(
        self, agent_role: str, task: str, session: StudioSession
    ) -> dict:
        """Phase 2 placeholder — sub-agent dispatch not implemented yet."""
        logger.debug("Sub-agent spawn requested (Phase 2 stub): role=%s", agent_role)
        return {"status": "not_implemented_phase_1", "agent_role": agent_role}

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    async def _record_activity(
        self,
        db: AsyncSession,
        session: StudioSession,
        verb: str,
        source_agent: str,
        target_agent: str,
        payload: dict,
        chain_depth: int = 0,
    ) -> StudioAgentActivity:
        """
        Write a StudioAgentActivity row (Visibility Principle: BEFORE dispatch).
        """
        activity = StudioAgentActivity(
            id=str(uuid.uuid4()),
            tenantId=session.tenantId or settings.DEFAULT_TENANT_ID,
            sessionId=session.id,
            verb=verb,
            sourceAgent=source_agent,
            targetAgent=target_agent,
            payload=payload,
            chainDepth=chain_depth,
        )
        db.add(activity)
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to persist activity row: %s", exc)
        return activity

    async def _upsert_tenant_token_usage(
        self,
        db: AsyncSession,
        tenant_id: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
    ) -> None:
        """
        Upsert the daily TenantTokenUsage row for cost attribution.
        Row is keyed on (tenantId, date) via UNIQUE constraint.
        """
        # Pass a date (not datetime) — the column is Date, not DateTime.
        today = datetime.now(tz=timezone.utc).date()

        result = await db.execute(
            select(TenantTokenUsage).where(
                and_(
                    TenantTokenUsage.tenantId == tenant_id,
                    TenantTokenUsage.date == today,
                )
            )
        )
        row: Optional[TenantTokenUsage] = result.scalar_one_or_none()

        if row is None:
            row = TenantTokenUsage(
                id=str(uuid.uuid4()),
                tenantId=tenant_id,
                date=today,
                tokensInput=tokens_input,
                tokensOutput=tokens_output,
                costUsd=cost_usd,
                modelBreakdown={
                    model: {
                        "input": tokens_input,
                        "output": tokens_output,
                        "costUsd": cost_usd,
                    }
                },
            )
            db.add(row)
        else:
            row.tokensInput += tokens_input
            row.tokensOutput += tokens_output
            row.costUsd += cost_usd
            # Merge model breakdown
            breakdown: dict = dict(row.modelBreakdown or {})
            if model in breakdown:
                breakdown[model]["input"] += tokens_input
                breakdown[model]["output"] += tokens_output
                breakdown[model]["costUsd"] += cost_usd
            else:
                breakdown[model] = {
                    "input": tokens_input,
                    "output": tokens_output,
                    "costUsd": cost_usd,
                }
            row.modelBreakdown = breakdown

        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to upsert TenantTokenUsage: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

studio_chat_agent: Optional[StudioChatAgent] = None


def get_studio_chat_agent() -> StudioChatAgent:
    """Return (or create) the process-level StudioChatAgent singleton."""
    global studio_chat_agent
    if studio_chat_agent is None:
        from models.database import AsyncSessionLocal as async_session_factory  # noqa: PLC0415
        studio_chat_agent = StudioChatAgent(db_factory=async_session_factory)
    return studio_chat_agent
