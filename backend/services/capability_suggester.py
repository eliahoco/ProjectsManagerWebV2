"""
CapabilitySuggester — CB-2864 v3 / CB-2914 E5.1 + E5.1.3 (relevance algorithm).

Server-side ranking of the user's 31 agents + 63 skills against a Studio
chat session's recent context. Returns the top-N most relevant capabilities
so the CapabilityRibbon UI (E5.2.1) can render them above the textarea.

The same endpoint is consumed by the Studio Investigation Engine (E2/E3)
to auto-pick layer-investigators — keeping the user-visible picker and
the SIE's hidden picker in sync.

Ranking algorithm (per the approved E5.1.3 spec):
    score = +3 if user-message contains a trigger keyword from skill/agent metadata
            +2 if conversation hints at a stack layer (e.g. "frontend" -> react/next)
            +1 for each prior turn in this session where this capability was used
            +1 if capability is a per-project pin

Pure-Python (no LLM call) for fast, predictable suggestions. The LLM-driven
auto-urgency classifier (E6) is separate.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.studio import StudioMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stack-layer hints
# ---------------------------------------------------------------------------

# Keywords in the conversation -> agents/skills that own that stack layer.
# Mapping is intentionally conservative — overlap is fine (a capability
# can win on multiple signals; max score per capability is bounded).
_STACK_HINTS: dict[str, tuple[str, ...]] = {
    r"\b(frontend|ui|react|tsx|jsx|component)\b": (
        "react-specialist", "nextjs-developer", "frontend-design",
        "shadcn", "react-best-practices", "next-best-practices",
    ),
    r"\b(backend|api|fastapi|python|django|pydantic)\b": (
        "python-pro", "api-designer", "debugger",
    ),
    r"\b(database|db|sql|sqlite|migration|prisma|alembic)\b": (
        "python-pro", "atlas",
    ),
    r"\b(docker|colima|container|compose)\b": (
        "docker-expert", "devops-engineer",
    ),
    r"\b(deploy|deployment|ci|cd|production)\b": (
        "devops-engineer", "deployment-expert", "cloud-architect",
    ),
    r"\b(security|auth|csrf|xss|jwt|secret|injection|idor)\b": (
        "security-auditor",
    ),
    r"\b(performance|slow|lag|laggy|optimi[sz]e|bundle|lcp)\b": (
        "performance-optimizer", "react-specialist", "debug-optimize-lcp",
    ),
    r"\b(test|tests|vitest|pytest|jest|qa|regression)\b": (
        "qa-regression", "code-reviewer",
    ),
    r"\b(bug|broken|doesn'?t work|fails?|error|wrong|reproduce)\b": (
        "bug-repro", "debugger", "code-reviewer",
    ),
    r"\b(architecture|design|cross-module|data\s*flow|refactor)\b": (
        "atlas", "code-reviewer", "ai-architect",
    ),
    r"\b(typescript|types|generics|type-?safety)\b": (
        "typescript-pro", "react-specialist",
    ),
    r"\b(llm|prompt|anthropic|claude|tool[\s-]use|streaming)\b": (
        "llm-architect", "claude-api", "ai-sdk",
    ),
    r"\b(next\.?js|app\s*router|server\s*action|cache\s*components)\b": (
        "nextjs-developer", "nextjs", "next-cache-components",
    ),
    r"\b(commit|pr|review code|review the (diff|pr))\b": (
        "code-reviewer", "caveman-review", "review",
    ),
    r"\b(chrome|devtools|mcp\s*chrome)\b": (
        "chrome-devtools", "bug-repro",
    ),
    r"\b(vercel|edge|serverless)\b": (
        "deployment-expert", "vercel-cli", "vercel-functions",
    ),
}

# Compile once at import time.
_STACK_HINT_PATTERNS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(pat, re.IGNORECASE), targets)
    for pat, targets in _STACK_HINTS.items()
]


# ---------------------------------------------------------------------------
# Capability registry shape (mirrors what /api/agents + /api/skills return)
# ---------------------------------------------------------------------------

@dataclass
class Capability:
    """Normalized view used by the suggester. Built from agent+skill rows."""
    name: str          # canonical identifier ("code-reviewer", "qa-regression")
    kind: str          # "agent" | "skill"
    description: str   # one-line description for the tooltip
    source: str        # "standalone" | "plugin:<pack>"
    triggers: tuple[str, ...]  # keywords parsed from description


@dataclass
class Suggestion:
    name: str
    kind: str
    description: str
    score: float
    reasons: list[str]  # human-readable reason tags ("trigger:bug", "stack:frontend", "history", "pinned")


# ---------------------------------------------------------------------------
# Trigger keyword extraction
# ---------------------------------------------------------------------------

# Words that aren't useful as trigger keywords (too generic).
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "use", "when",
    "this", "that", "with", "from", "by", "is", "are", "be", "as", "on",
    "agent", "skill", "tool", "your", "you", "user", "uses", "claude",
    "code", "into", "across", "via", "any", "all", "their", "have",
})


def _extract_triggers(description: str, name: str) -> tuple[str, ...]:
    """Pull candidate trigger keywords from a capability's description.

    Heuristic: lowercase + tokenize on word boundaries, drop stopwords +
    short tokens, keep up to ~12 distinct terms. The name itself is always
    a trigger (case-insensitive).
    """
    seen: list[str] = [name.lower()]
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", description or ""):
        tok = raw.lower()
        if tok in _STOPWORDS or len(tok) < 4:
            continue
        if tok not in seen:
            seen.append(tok)
        if len(seen) >= 12:
            break
    return tuple(seen)


# ---------------------------------------------------------------------------
# Suggester
# ---------------------------------------------------------------------------

class CapabilitySuggester:
    """Stateless ranker. Build with the merged capability registry, call
    `suggest()` per chat turn."""

    def __init__(self, capabilities: Iterable[Capability]):
        # Keep a stable iteration order so ties resolve deterministically.
        self._caps: list[Capability] = list(capabilities)

    async def suggest(
        self,
        *,
        message: str,
        session_id: str,
        db: AsyncSession,
        pinned: Optional[Iterable[str]] = None,
        top_n: int = 7,
        history_turns: int = 10,
    ) -> list[Suggestion]:
        """Rank all capabilities against the user's latest message + session history."""
        message = message or ""
        pinned_set = {p.lower() for p in (pinned or ())}

        # Compute history-use counts (capability invocations in recent turns).
        history_counts = await self._history_counts(session_id, db, history_turns)

        scored: list[Suggestion] = []
        for cap in self._caps:
            score = 0.0
            reasons: list[str] = []

            # +3 per trigger-keyword hit.
            for trig in cap.triggers:
                if re.search(rf"\b{re.escape(trig)}\b", message, re.IGNORECASE):
                    score += 3
                    reasons.append(f"trigger:{trig}")
                    break  # cap at one trigger hit so a long description doesn't dominate

            # +2 per stack-hint match.
            for pat, targets in _STACK_HINT_PATTERNS:
                if cap.name in targets and pat.search(message):
                    score += 2
                    reasons.append(f"stack:{pat.pattern[:30]}")
                    break

            # +1 per prior use in this session.
            uses = history_counts.get(cap.name, 0)
            if uses:
                score += min(uses, 3)  # cap at +3 so a single capability can't dominate by usage
                reasons.append(f"history:{uses}")

            # +1 if pinned.
            if cap.name.lower() in pinned_set:
                score += 1
                reasons.append("pinned")

            if score > 0:
                scored.append(Suggestion(
                    name=cap.name,
                    kind=cap.kind,
                    description=cap.description,
                    score=score,
                    reasons=reasons,
                ))

        # Sort by score desc, then by capability list order (stable).
        scored.sort(key=lambda s: (-s.score, s.name))

        # If nothing scored, return the user's pinned list (or empty).
        if not scored:
            return [
                Suggestion(name=cap.name, kind=cap.kind,
                          description=cap.description, score=1.0,
                          reasons=["pinned"])
                for cap in self._caps
                if cap.name.lower() in pinned_set
            ][:top_n]

        return scored[:top_n]

    async def _history_counts(
        self,
        session_id: str,
        db: AsyncSession,
        history_turns: int,
        tenant_id: Optional[str] = None,
    ) -> dict[str, int]:
        """Count how many times each capability appeared in the session's
        recent assistant tool-use blocks. Cheap query — limited to the
        last `history_turns` rows.

        CB-2914 sec-audit HIGH-1 defense-in-depth: when a tenant_id is
        provided, the query is additionally filtered by it. The endpoint
        already enforces session ownership; this is a redundant safeguard.
        """
        if not session_id:
            return {}
        try:
            stmt = select(StudioMessage.content).where(
                StudioMessage.sessionId == session_id
            )
            if tenant_id:
                stmt = stmt.where(StudioMessage.tenantId == tenant_id)
            result = await db.execute(
                stmt.order_by(desc(StudioMessage.createdAt)).limit(history_turns)
            )
        except Exception as exc:
            logger.debug("history_counts query skipped: %s", exc)
            return {}

        counts: dict[str, int] = {}
        for (raw,) in result.all():
            if not raw:
                continue
            text = str(raw).lower()
            # Look for the canonical names of capabilities — exact matches
            # against our registered list keeps this O(n_caps * n_turns).
            for cap in self._caps:
                if cap.name.lower() in text:
                    counts[cap.name] = counts.get(cap.name, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Public factory — pulls the registry from the agent_registry + skill_registry
# services and builds a Capability list.
# ---------------------------------------------------------------------------

async def build_suggester_from_db(db: AsyncSession) -> CapabilitySuggester:
    """Hydrate a CapabilitySuggester from the live agent + skill registries."""
    from services.agent_registry_service import agent_registry_service
    from services.skill_registry_service import skill_registry_service

    agents = await agent_registry_service.get_all_agents(db, active_only=True)
    skills = await skill_registry_service.get_all_skills(db, active_only=True)

    caps: list[Capability] = []
    for a in agents:
        name = (a.name or "").strip()
        if not name:
            continue
        desc_text = (a.description or "").strip()
        caps.append(Capability(
            name=name,
            kind="agent",
            description=desc_text[:200],
            source=(a.source or "standalone"),
            triggers=_extract_triggers(desc_text, name),
        ))
    for s in skills:
        name = (s.name or "").strip()
        if not name:
            continue
        desc_text = (s.description or "").strip()
        caps.append(Capability(
            name=name,
            kind="skill",
            description=desc_text[:200],
            source=(s.source or "standalone"),
            triggers=_extract_triggers(desc_text, name),
        ))
    logger.info("CapabilitySuggester loaded %d agents + %d skills", len(agents), len(skills))
    return CapabilitySuggester(caps)
