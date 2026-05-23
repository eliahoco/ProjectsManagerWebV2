"""
InvestigationEngine — CB-2914 E1 + E2 + E3 + E4 (Studio Investigation Engine).

Trigger sources (E1) fan in to a single InvestigationRequest event. The
engine (E2) dispatches layer-specific investigators (E3) in parallel via
the AgentDispatcher (E0), with a per-agent timeout + partial-result
tolerance. When all layers return (or timeout), the synthesizer (E4)
composes the 5-part deliverable.

Trigger sources implemented in this first cut:
    - StudioChatIntent (user typed a bug-shaped message)
    - ManualInvocation (E2 callable directly for tests / E3 internal use)

Layer investigators implemented in this first cut (3 of 6):
    - architecture-investigator → atlas skill + general-purpose agent
    - code-investigator → code-reviewer agent (read-only mode)
    - runtime-investigator → debugger agent

Deferred to follow-up:
    - database-investigator (S3.3) — needs sqlite3 wrapper
    - ui-investigator (S3.4) — needs bug-repro skill wiring + Chrome MCP
    - security-investigator (S3.6) — conditional, depends on surface heuristic

The deliverable contract is the 5-part artifact (E4): storytelling +
agile plan + agent assignments + owners + QA/regression plan.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from services.agent_dispatcher import (
    AgentDispatcher,
    DispatchResult,
    get_agent_dispatcher,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event model (E1)
# ---------------------------------------------------------------------------


class TriggerSource(str, Enum):
    """Each of the 5 trigger sources from CB-2914 E1.

    Phase 1 implements STUDIO_CHAT_INTENT + MANUAL_INVOCATION; the other
    three (QA_REGRESSION_FAIL, AUTOPILOT_IMPL_FAIL, RUNTIME_ERROR) are
    wired in follow-up tasks (T1.2.2 / T1.2.3 / T1.2.5).
    """

    STUDIO_CHAT_INTENT = "studio_chat_intent"
    QA_REGRESSION_FAIL = "qa_regression_fail"
    AUTOPILOT_IMPL_FAIL = "autopilot_impl_fail"
    MANUAL_CB_BUG = "manual_cb_bug"
    RUNTIME_ERROR = "runtime_error"
    MANUAL_INVOCATION = "manual_invocation"


@dataclass
class InvestigationRequest:
    """The unified event shape every trigger source emits.

    Per Rule 19 (data flow preservation): every layer-investigator sees
    this exact shape. Adding fields requires bumping the model + migration.
    """

    trigger_source: TriggerSource
    description: str  # the bug description / user message / failure summary
    project_id: str
    session_id: Optional[str] = None  # Studio session id if from chat
    tenant_id: str = "default"
    evidence: dict = field(default_factory=dict)  # repro evidence / stack traces / etc.
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Result types (E3 + E4)
# ---------------------------------------------------------------------------


class LayerStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass
class LayerReport:
    """Output from one layer-investigator."""

    layer: str  # "architecture" | "code" | "runtime" | "database" | "ui" | "security"
    investigator: str  # name of the agent/skill that produced it
    status: LayerStatus
    findings: str  # the investigator's response text
    confidence: float  # 0.0 - 1.0; LOW for failed/timeout, HIGH for clean completion
    duration_s: float
    cost_usd: float
    error: Optional[str] = None


@dataclass
class InvestigationResult:
    """Composed output of an entire investigation cycle."""

    request: InvestigationRequest
    layer_reports: list[LayerReport]
    deliverable_markdown: str  # the 5-part deliverable (E4 synthesizer output)
    started_at: datetime
    completed_at: datetime
    total_cost_usd: float

    @property
    def duration_s(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def succeeded_layers(self) -> int:
        return sum(1 for r in self.layer_reports if r.status == LayerStatus.COMPLETED)


# ---------------------------------------------------------------------------
# Layer investigator definitions (E3)
# ---------------------------------------------------------------------------


@dataclass
class LayerInvestigatorSpec:
    """Static configuration for one layer of the investigation cycle."""

    layer: str
    kind: str  # "agent" | "skill"
    name: str
    prompt_template: str  # uses {description} + {project_id}


_PHASE1_INVESTIGATORS: list[LayerInvestigatorSpec] = [
    LayerInvestigatorSpec(
        layer="architecture",
        kind="agent",
        name="general-purpose",
        prompt_template=(
            "You are the architecture-investigator for the Studio Investigation Engine. "
            "A bug or anomaly has been reported. Identify which modules / data flows / "
            "cross-component dependencies are most likely involved. Use Read + Grep on "
            "the project (project root: /Volumes/Seagate/Claude/ProjectsManagerWebV2Production). "
            "Return a structured architectural assessment: (a) suspected modules, "
            "(b) data-flow risk areas, (c) cross-module ripple impact. "
            "Be concise; max 400 words.\n\n"
            "Project: {project_id}\n\n"
            "Bug report:\n{description}\n\n"
            "Evidence (may be empty):\n{evidence}"
        ),
    ),
    LayerInvestigatorSpec(
        layer="code",
        kind="agent",
        name="code-reviewer",
        prompt_template=(
            "You are the code-investigator for the Studio Investigation Engine. "
            "A bug was reported. Search the project for the suspect code paths, "
            "identify the specific files + functions + line numbers most likely "
            "responsible. Do NOT propose fixes — only identify. Return a structured "
            "list: (a) suspect file:line locations, (b) why each is suspect, "
            "(c) confidence (high/medium/low). Max 400 words.\n\n"
            "Project root: /Volumes/Seagate/Claude/ProjectsManagerWebV2Production\n"
            "Project: {project_id}\n\n"
            "Bug report:\n{description}\n\n"
            "Evidence:\n{evidence}"
        ),
    ),
    LayerInvestigatorSpec(
        layer="runtime",
        kind="agent",
        name="debugger",
        prompt_template=(
            "You are the runtime-investigator for the Studio Investigation Engine. "
            "Analyze the bug for runtime-error signatures: stack traces, recent log "
            "patterns, error codes, race conditions, timing issues. Look at "
            "backend log files if available (e.g. /tmp/uvicorn-pmv2-restart.log). "
            "Return: (a) error signature classification, (b) likely runtime cause, "
            "(c) reproducibility hypothesis. Max 400 words.\n\n"
            "Project: {project_id}\n\n"
            "Bug report:\n{description}\n\n"
            "Evidence (stack traces / error messages if present):\n{evidence}"
        ),
    ),
]


# ---------------------------------------------------------------------------
# The orchestrator (E2)
# ---------------------------------------------------------------------------


class InvestigationEngine:
    """Drives the SIE investigation cycle.

    Stateless; each `run(request)` is independent. Thread-safe — internal
    state lives entirely on the stack.
    """

    def __init__(
        self,
        *,
        dispatcher: Optional[AgentDispatcher] = None,
        investigators: Optional[list[LayerInvestigatorSpec]] = None,
        per_agent_timeout_s: float = 90.0,
        global_timeout_s: float = 120.0,
    ):
        self.dispatcher = dispatcher or get_agent_dispatcher()
        self.investigators = investigators or _PHASE1_INVESTIGATORS
        self.per_agent_timeout_s = per_agent_timeout_s
        self.global_timeout_s = global_timeout_s

    async def run(
        self,
        request: InvestigationRequest,
        *,
        on_progress=None,  # optional async callback (layer, status) for SSE
    ) -> InvestigationResult:
        started = datetime.now(timezone.utc)
        logger.info(
            "InvestigationEngine.run starting request_id=%s trigger=%s project=%s",
            request.request_id, request.trigger_source.value, request.project_id,
        )

        # Build per-layer invocations.
        invocations = []
        for spec in self.investigators:
            prompt = spec.prompt_template.format(
                description=request.description[:4000],
                project_id=request.project_id,
                evidence=str(request.evidence)[:2000] if request.evidence else "(none)",
            )
            if spec.kind == "agent":
                invocations.append(("agent", spec.name, {"prompt": prompt}))
            else:
                invocations.append(("skill", spec.name, {"args": prompt}))

        # CB-3123 fix: emit per-layer lifecycle events. Notify QUEUED first
        # for every layer, then dispatch them in parallel with per-task
        # callbacks that fire RUNNING when the agent actually starts and
        # COMPLETED/FAILED/TIMEOUT the moment that specific agent's coroutine
        # returns — not at the all-done barrier.
        if on_progress:
            for spec in self.investigators:
                try:
                    await on_progress(spec.layer, LayerStatus.QUEUED)
                except Exception:
                    logger.exception("on_progress(QUEUED) raised; continuing")

        results: list[Optional[Any]] = [None] * len(self.investigators)
        layer_reports: list[LayerReport] = []

        async def _run_one(idx: int) -> None:
            spec = self.investigators[idx]
            if on_progress:
                try:
                    await on_progress(spec.layer, LayerStatus.RUNNING)
                except Exception:
                    logger.exception("on_progress(RUNNING) raised; continuing")
            kind, name, kwargs = invocations[idx]
            # M-1 fix: pass per-agent timeout so dispatcher honors the
            # engine's configured budget instead of falling back to its
            # own _DEFAULT_TIMEOUT_S.
            if kind == "agent":
                dr = await self.dispatcher.invoke_agent(
                    name, timeout=self.per_agent_timeout_s, **kwargs,
                )
            else:
                dr = await self.dispatcher.invoke_skill(
                    name, timeout=self.per_agent_timeout_s, **kwargs,
                )
            results[idx] = dr
            status, _conf = self._classify(dr)
            if on_progress:
                try:
                    await on_progress(spec.layer, status)
                except Exception:
                    logger.exception("on_progress(complete) raised; continuing")

        # M-1 fix: also enforce global_timeout_s. If we hit it, layers
        # whose result slot is still None get marked TIMEOUT in the
        # report-build pass below.
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *[_run_one(i) for i in range(len(self.investigators))],
                    return_exceptions=True,
                ),
                timeout=self.global_timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "InvestigationEngine global timeout %.1fs hit — partial results retained",
                self.global_timeout_s,
            )
            # Fire TIMEOUT progress events for any layer that hasn't finished.
            if on_progress:
                for idx, spec in enumerate(self.investigators):
                    if results[idx] is None:
                        try:
                            await on_progress(spec.layer, LayerStatus.TIMEOUT)
                        except Exception:
                            logger.exception("on_progress(TIMEOUT) raised; continuing")

        for spec, dr in zip(self.investigators, results):
            status, confidence = self._classify(dr) if dr else (LayerStatus.FAILED, 0.0)
            layer_reports.append(LayerReport(
                layer=spec.layer,
                investigator=spec.name,
                status=status,
                findings=(dr.output if (dr and dr.ok) else (dr.error if dr else "(no result)")) or "(no output)",
                confidence=confidence,
                duration_s=dr.duration_s if dr else 0.0,
                cost_usd=dr.cost_usd if dr else 0.0,
                error=dr.error if dr else "no result",
            ))

        # Synthesize the 5-part deliverable (E4).
        deliverable = compose_deliverable(request, layer_reports)
        completed = datetime.now(timezone.utc)
        result = InvestigationResult(
            request=request,
            layer_reports=layer_reports,
            deliverable_markdown=deliverable,
            started_at=started,
            completed_at=completed,
            total_cost_usd=sum(r.cost_usd for r in layer_reports),
        )
        logger.info(
            "InvestigationEngine.run done request_id=%s duration=%.1fs cost=$%.4f succeeded=%d/%d",
            request.request_id, result.duration_s, result.total_cost_usd,
            result.succeeded_layers, len(layer_reports),
        )
        return result

    @staticmethod
    def _classify(dr: DispatchResult) -> tuple[LayerStatus, float]:
        if dr.ok:
            return LayerStatus.COMPLETED, 0.9
        if dr.error and "timeout" in dr.error.lower():
            return LayerStatus.TIMEOUT, 0.2
        if dr.error and "global timeout" in dr.error.lower():
            return LayerStatus.TIMEOUT, 0.0
        if dr.error and ("invalid" in dr.error.lower() or "unknown" in dr.error.lower()):
            return LayerStatus.UNAVAILABLE, 0.0
        return LayerStatus.FAILED, 0.1


# ---------------------------------------------------------------------------
# Synthesizer — composes the 5-part deliverable (E4)
# ---------------------------------------------------------------------------


def compose_deliverable(
    request: InvestigationRequest,
    layer_reports: list[LayerReport],
) -> str:
    """Compose the 5-part deliverable from the investigation cycle outputs.

    Part 1 — storytelling narrative
    Part 2 — agile resolution plan (table)
    Part 3 — agents + skills involved (table)
    Part 4 — owner per leaf task
    Part 5 — QA + regression + user-regression plan
    """
    layer_status_table = "\n".join(
        f"| {r.layer} | {r.investigator} | {r.status.value} | {r.duration_s:.1f}s | ${r.cost_usd:.4f} |"
        for r in layer_reports
    )

    findings_section = "\n\n".join(
        f"### Layer: {r.layer} (investigator: {r.investigator}, status: {r.status.value})\n\n"
        f"{r.findings.strip()[:1500]}"
        for r in layer_reports
        if r.status == LayerStatus.COMPLETED
    ) or "_All layer-investigators failed or timed out._"

    # ---- Part 1 — Storytelling ----------------------------------------------
    succeeded = sum(1 for r in layer_reports if r.status == LayerStatus.COMPLETED)
    failed = len(layer_reports) - succeeded
    story = (
        f"User reported via **{request.trigger_source.value}**: "
        f"_{request.description[:200]}_\n\n"
        f"The Investigation Engine dispatched {len(layer_reports)} layer-investigators "
        f"in parallel; {succeeded} returned findings"
        + (f", {failed} failed or timed out" if failed else "") + ". "
        "The combined evidence is summarized below in the agile plan + the "
        "raw findings appendix at the bottom of this deliverable."
    )

    # ---- Part 2 — Agile resolution plan -------------------------------------
    plan = (
        "| Epic | Story | Task | Agent | Estimate |\n"
        "|---|---|---|---|---|\n"
        "| E1 — Confirm root cause | S1.1 Re-run repro after candidate fix | T1.1.1 Apply candidate fix | `python-pro` / `react-specialist` | S |\n"
        "| E1 | S1.2 Validate fix doesn't regress adjacent flows | T1.2.1 qa-regression Stage 4 sweep | `qa-regression skill` | M |\n"
        "| E2 — Audit + sign-off | S2.1 Code review the diff | T2.1.1 code-reviewer agent | `code-reviewer` | S |\n"
        "| E2 | S2.2 Security audit (conditional) | T2.2.1 security-auditor agent | `security-auditor` | S |\n"
        "| E3 — QA + regression | S3.1 qa-regression skill 7-stage pipeline | T3.1.1 Full pipeline | `qa-regression skill` | M |\n"
    )

    # ---- Part 3 — Agents + skills involved ----------------------------------
    agents_table = "| Agent / skill | Layer | Cost (this run) |\n|---|---|---|\n" + "\n".join(
        f"| `{r.investigator}` | {r.layer} | ${r.cost_usd:.4f} |"
        for r in layer_reports
    )

    # ---- Part 4 — Owner per leaf task ---------------------------------------
    owners = (
        "- T1.1.1 — apply candidate fix → `python-pro` or `react-specialist` (depending on diff)\n"
        "- T1.2.1 — regression sweep → `qa-regression skill`\n"
        "- T2.1.1 — code review → `code-reviewer`\n"
        "- T2.2.1 — security audit → `security-auditor`\n"
        "- T3.1.1 — full QA → `qa-regression skill`\n"
    )

    # ---- Part 5 — QA + regression + user-regression plan --------------------
    qa = (
        "| Phase | Tooling | Owner |\n|---|---|---|\n"
        "| qa-regression Stage 1-3 (AC matrix + automated + Chrome MCP manual) | `qa-regression skill` | `qa-regression` |\n"
        "| qa-regression Stage 4 (adjacent flow sweep) | `qa-regression skill` | `qa-regression` |\n"
        "| qa-regression Stage 5 (destructive cases) | `qa-regression skill` | `qa-regression` |\n"
        "| User-regression phase 1 — happy path end-to-end (Chrome MCP) | manual scripted journey | `qa-regression skill` |\n"
        "| User-regression phase 2 — error recovery | network kill mid-action | `qa-regression skill` |\n"
        "| User-regression phase 3 — multi-step UI-only workflow | no curl shortcuts | `qa-regression skill` |\n"
        "| User-regression phase 4 — cross-project repeat | 2nd project | `qa-regression skill` |\n"
        "| User-regression phase 5 — stress | 5+ concurrent sessions | `qa-regression skill` |\n"
    )

    return (
        f"# Investigation deliverable — `{request.request_id[:8]}`\n\n"
        f"_Trigger: {request.trigger_source.value} · "
        f"Project: `{request.project_id}` · "
        f"Started: {request.created_at.isoformat(timespec='seconds')}_\n\n"
        f"## 1 — Storytelling\n\n{story}\n\n"
        f"## 2 — Agile resolution plan\n\n{plan}\n\n"
        f"## 3 — Agents + skills involved\n\n{agents_table}\n\n"
        f"## 4 — Owner per leaf task\n\n{owners}\n\n"
        f"## 5 — QA + regression + user-regression\n\n{qa}\n\n"
        f"---\n\n## Layer status table\n\n"
        f"| Layer | Investigator | Status | Duration | Cost |\n"
        f"|---|---|---|---|---|\n{layer_status_table}\n\n"
        f"## Appendix — Raw layer findings\n\n{findings_section}\n"
    )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: Optional[InvestigationEngine] = None


def get_investigation_engine() -> InvestigationEngine:
    global _engine
    if _engine is None:
        _engine = InvestigationEngine()
    return _engine
