"""
UrgencyClassifier — CB-2914 E6.

Deterministic rubric scorer that maps a bug description + investigation
evidence to a priority (LOW / MEDIUM / HIGH / CRITICAL) + a kebab-case
label set + a rationale log.

Same shape consumed by:
    - The SIE synthesizer (E4) when composing Part 2 of the deliverable
      (the priority on each row of the agile plan table).
    - The CodeBoard top-down filer (E7) when creating issues.

LLM tiebreak is intentionally deferred to a follow-up. The pure-rubric
scorer is bounded, deterministic, cheap, and unit-testable.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rubric (per the approved E5.1.3 / E6 specs)
# ---------------------------------------------------------------------------

# (regex, weight, label, rationale_tag)
_SIGNALS: tuple[tuple[re.Pattern[str], int, str, str], ...] = (
    # Impact — production / data
    (re.compile(r"\b(production|prod)\b.{0,20}\b(down|outage|broken|crash|crashed|offline|unreachable)\b", re.I),
     5, "production-down", "production-down"),
    (re.compile(r"\bdata[ -]?(loss|leak|leakage)|lost\s+(data|user|order|record)", re.I),
     4, "data-loss", "data-loss"),
    (re.compile(r"\b(corrupted|corruption|incorrect\s+(data|value|state))\b", re.I),
     3, "data-integrity", "data-integrity"),

    # Surface — security / multi-tenant
    (re.compile(r"\b(security|auth|csrf|xss|jwt|secret|injection|idor|leak)\b", re.I),
     3, "security", "security-surface"),
    (re.compile(r"\b(multi[- ]?tenant|cross[- ]?tenant|cross[- ]?project|tenant\s+leak)\b", re.I),
     3, "multi-tenant", "multi-tenant-surface"),

    # Scope — all users vs single user
    (re.compile(r"\b(all|every)\s+(users?|sessions?|tabs?|projects?)\b", re.I),
     2, "scope-all-users", "scope-all-users"),
    (re.compile(r"\b(one\s+(user|session|tab)|single\s+(user|session))\b", re.I),
     -1, "scope-single-user", "scope-single-user"),
    (re.compile(r"\b(only|just)\s+(happens|seen)\s+(on|for|with)\b", re.I),
     -1, "scope-limited", "scope-limited"),

    # Severity flavors
    (re.compile(r"\b(blocked|blocker|cannot|can'?t|unable\s+to)\b", re.I),
     2, "blocker", "blocker"),
    (re.compile(r"\b(workaround|workar|temporarily)\b", re.I),
     -1, "has-workaround", "has-workaround"),
    (re.compile(r"\b(cosmetic|polish|nit|minor|small)\b", re.I),
     -2, "cosmetic", "cosmetic"),

    # Performance
    (re.compile(r"\b(slow|laggy|lag|timeout|hang|hangs|hanging|freeze|frozen|re[- ]?render|aggressive(ly)?)\b", re.I),
     1, "performance", "performance"),

    # Stack-layer (label-only, not score-shifting)
    (re.compile(r"\b(frontend|ui|react|component|tsx?|jsx)\b", re.I),
     0, "frontend", None),
    (re.compile(r"\b(backend|api|fastapi|python|server)\b", re.I),
     0, "backend", None),
    (re.compile(r"\b(database|db|sql|sqlite|migration)\b", re.I),
     0, "database", None),
    (re.compile(r"\b(autopilot|queue|orchestrat)\b", re.I),
     0, "autopilot", None),
    (re.compile(r"\b(studio|chat|conversation|tabs?\b)", re.I),
     0, "studio", None),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class UrgencyResult:
    priority: str   # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    score: int
    labels: list[str]
    rationale: list[str]  # ordered list of (signal:weight) tags
    method: str  # "rubric" — LLM tiebreak is a future enhancement


def classify(description: str, evidence: dict | None = None) -> UrgencyResult:
    """Score a bug-report description against the rubric.

    Returns a deterministic UrgencyResult — no LLM call.
    """
    blob = description or ""
    if evidence:
        # Include evidence text but cap to keep regex passes bounded.
        blob += "\n" + str(evidence)[:2000]

    score = 0
    labels: list[str] = []
    rationale: list[str] = []
    for pat, weight, label, tag in _SIGNALS:
        if pat.search(blob):
            score += weight
            if label and label not in labels:
                labels.append(label)
            if tag:
                rationale.append(f"{tag}:{weight:+d}")

    priority = _score_to_priority(score)
    logger.debug(
        "UrgencyClassifier: priority=%s score=%d labels=%s",
        priority, score, labels,
    )
    return UrgencyResult(
        priority=priority,
        score=score,
        labels=labels,
        rationale=rationale,
        method="rubric",
    )


def _score_to_priority(score: int) -> str:
    """Map total score to a CodeBoard priority enum."""
    if score >= 7:
        return "CRITICAL"
    if score >= 4:
        return "HIGH"
    if score >= 1:
        return "MEDIUM"
    return "LOW"


def labels_to_string(labels: Iterable[str]) -> str:
    """CodeBoard's POST /issues expects `labels` as a string; canonicalize."""
    return ",".join(sorted(set(labels)))
