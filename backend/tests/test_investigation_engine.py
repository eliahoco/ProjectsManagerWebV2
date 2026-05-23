"""Unit tests for InvestigationEngine — CB-2914 E2 + E4."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.agent_dispatcher import DispatchResult
from services.investigation_engine import (
    InvestigationEngine,
    InvestigationRequest,
    LayerStatus,
    TriggerSource,
    compose_deliverable,
)


def _make_request(**overrides) -> InvestigationRequest:
    base = dict(
        trigger_source=TriggerSource.STUDIO_CHAT_INTENT,
        description="The upload route returns 500 sometimes",
        project_id="1511e54f71dccd3fa79f67fe",
        session_id="sess-test",
    )
    base.update(overrides)
    return InvestigationRequest(**base)


def _success_dispatch(kind: str, name: str) -> DispatchResult:
    return DispatchResult(
        name=name, kind=kind, ok=True,
        output=f"findings from {name}", duration_s=0.5, cost_usd=0.001,
    )


@pytest.mark.asyncio
class TestInvestigationEngine:
    """CB-3123 fix: engine now uses per-layer invoke_agent/invoke_skill so
    progress events fire as each agent starts and finishes individually.
    Tests mock the per-call methods instead of invoke_many."""

    async def test_all_layers_succeed(self):
        async def fake_agent(name, prompt, **kwargs):
            return _success_dispatch("agent", name)

        with patch("services.investigation_engine.get_agent_dispatcher") as mock_get:
            mock_get.return_value.invoke_agent = AsyncMock(side_effect=fake_agent)
            mock_get.return_value.invoke_skill = AsyncMock(side_effect=lambda n, *a, **k: _success_dispatch("skill", n))
            engine = InvestigationEngine()
            result = await engine.run(_make_request())

        assert result.succeeded_layers == 3
        assert len(result.layer_reports) == 3
        for r in result.layer_reports:
            assert r.status == LayerStatus.COMPLETED
            assert r.confidence == 0.9
        assert "Investigation deliverable" in result.deliverable_markdown
        assert "## 1 — Storytelling" in result.deliverable_markdown
        assert "## 5 — QA + regression + user-regression" in result.deliverable_markdown

    async def test_partial_failure_tolerated(self):
        async def fake_agent(name, prompt, **kwargs):
            if name == "code-reviewer":  # second layer
                return DispatchResult(name=name, kind="agent", ok=False,
                                      output="", error="claude CLI exited 2: boom",
                                      duration_s=0.1)
            return _success_dispatch("agent", name)

        with patch("services.investigation_engine.get_agent_dispatcher") as mock_get:
            mock_get.return_value.invoke_agent = AsyncMock(side_effect=fake_agent)
            mock_get.return_value.invoke_skill = AsyncMock(side_effect=lambda n, *a, **k: _success_dispatch("skill", n))
            engine = InvestigationEngine()
            result = await engine.run(_make_request())

        assert result.succeeded_layers == 2
        assert any(r.status == LayerStatus.FAILED for r in result.layer_reports)
        assert "## 1 — Storytelling" in result.deliverable_markdown
        assert "2 returned findings" in result.deliverable_markdown
        assert "1 failed" in result.deliverable_markdown

    async def test_timeout_status_classified(self):
        async def fake_agent(name, prompt, **kwargs):
            return DispatchResult(name=name, kind="agent", ok=False,
                                  output="", error="timeout after 90s",
                                  duration_s=90.0)

        with patch("services.investigation_engine.get_agent_dispatcher") as mock_get:
            mock_get.return_value.invoke_agent = AsyncMock(side_effect=fake_agent)
            mock_get.return_value.invoke_skill = AsyncMock(side_effect=fake_agent)
            engine = InvestigationEngine()
            result = await engine.run(_make_request())

        for r in result.layer_reports:
            assert r.status == LayerStatus.TIMEOUT

    async def test_on_progress_fires_queued_running_and_completed(self):
        """CB-3123 fix: every layer emits QUEUED + RUNNING + terminal status."""
        async def fake_agent(name, prompt, **kwargs):
            return _success_dispatch("agent", name)

        events: list[tuple[str, LayerStatus]] = []

        async def progress(layer, status):
            events.append((layer, status))

        with patch("services.investigation_engine.get_agent_dispatcher") as mock_get:
            mock_get.return_value.invoke_agent = AsyncMock(side_effect=fake_agent)
            mock_get.return_value.invoke_skill = AsyncMock(side_effect=lambda n, *a, **k: _success_dispatch("skill", n))
            engine = InvestigationEngine()
            await engine.run(_make_request(), on_progress=progress)

        # 3 layers × 3 events each (QUEUED + RUNNING + COMPLETED) = 9
        assert len(events) == 9
        assert events.count(("architecture", LayerStatus.QUEUED)) == 1
        assert events.count(("architecture", LayerStatus.RUNNING)) == 1
        assert events.count(("architecture", LayerStatus.COMPLETED)) == 1

    async def test_progress_callback_exception_does_not_break_engine(self):
        async def fake_agent(name, prompt, **kwargs):
            return _success_dispatch("agent", name)

        async def bad_progress(layer, status):
            raise RuntimeError("listener crashed")

        with patch("services.investigation_engine.get_agent_dispatcher") as mock_get:
            mock_get.return_value.invoke_agent = AsyncMock(side_effect=fake_agent)
            mock_get.return_value.invoke_skill = AsyncMock(side_effect=lambda n, *a, **k: _success_dispatch("skill", n))
            engine = InvestigationEngine()
            result = await engine.run(_make_request(), on_progress=bad_progress)

        assert result.succeeded_layers == 3


class TestComposeDeliverable:
    def test_five_parts_present(self):
        req = _make_request()
        markdown = compose_deliverable(req, [])
        for header in (
            "## 1 — Storytelling",
            "## 2 — Agile resolution plan",
            "## 3 — Agents + skills involved",
            "## 4 — Owner per leaf task",
            "## 5 — QA + regression + user-regression",
        ):
            assert header in markdown

    def test_user_regression_phases_listed(self):
        req = _make_request()
        markdown = compose_deliverable(req, [])
        for phase in (
            "happy path",
            "error recovery",
            "multi-step",
            "cross-project",
            "stress",
        ):
            assert phase.lower() in markdown.lower()

    def test_description_truncated_safely(self):
        req = _make_request(description="x" * 50_000)
        markdown = compose_deliverable(req, [])
        # Storytelling truncates description to 200 chars + surrounding text.
        assert "x" * 200 in markdown
        assert "x" * 50_000 not in markdown
