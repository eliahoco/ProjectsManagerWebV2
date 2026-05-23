"""Unit tests for agent_dispatcher — CB-2915 (E0 of CB-2914 SIE).

Does NOT spawn real `claude` CLI subprocesses (too slow + costly for unit
tests). Mocks _run_claude and validates the wrapper logic:
  - Output parsing (single-object JSON / NDJSON / garbage)
  - Cost extraction
  - Subagent prompt composition
  - Slash-command composition
  - Timeout path returns ok=False with error set
  - Partial-result tolerance via invoke_many
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.agent_dispatcher import (
    AgentDispatcher,
    DispatchResult,
    _extract_cost,
    _parse_claude_json_output,
)


# ---------------------------------------------------------------------------
# Pure helper tests (no subprocess)
# ---------------------------------------------------------------------------

class TestParseClaudeJsonOutput:
    def test_single_object_with_result(self):
        raw = json.dumps({"type": "result", "result": "hello", "cost_usd": 0.001})
        text, meta = _parse_claude_json_output(raw)
        assert text == "hello"
        assert meta.get("cost_usd") == 0.001

    def test_ndjson_takes_last_result(self):
        raw = "\n".join([
            json.dumps({"type": "stream", "text": "intermediate"}),
            json.dumps({"type": "result", "result": "final", "usage": {"input_tokens": 10}}),
        ])
        text, meta = _parse_claude_json_output(raw)
        assert text == "final"
        assert meta.get("usage", {}).get("input_tokens") == 10

    def test_empty_input_returns_empty(self):
        assert _parse_claude_json_output("") == ("", {})
        assert _parse_claude_json_output("   ") == ("", {})

    def test_garbage_falls_back_to_raw(self):
        text, meta = _parse_claude_json_output("not json at all")
        assert "not json" in text
        assert meta == {}


class TestExtractCost:
    def test_top_level_cost(self):
        assert _extract_cost({"cost_usd": 0.42}) == 0.42

    def test_nested_in_usage(self):
        assert _extract_cost({"usage": {"cost_usd": 1.23}}) == 1.23

    def test_missing_returns_zero(self):
        assert _extract_cost({}) == 0.0
        assert _extract_cost({"usage": {}}) == 0.0

    def test_non_numeric_returns_zero(self):
        assert _extract_cost({"cost_usd": "free"}) == 0.0


# ---------------------------------------------------------------------------
# Dispatcher behavior with mocked subprocess
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAgentDispatcher:
    async def test_invoke_agent_composes_task_tool_prompt(self):
        captured: dict = {}

        async def fake_run(prompt, *, timeout, cwd=None):
            captured["prompt"] = prompt
            captured["timeout"] = timeout
            return json.dumps({"result": "review done"}), "", 0

        with patch("services.agent_dispatcher._run_claude", new=AsyncMock(side_effect=fake_run)):
            d = AgentDispatcher(default_timeout=10)
            res = await d.invoke_agent("code-reviewer", "Review src/foo.py")

        assert res.ok is True
        assert res.kind == "agent"
        assert res.output == "review done"
        # Must compose a Task-tool prompt with the subagent_type quoted.
        assert "subagent_type=" in captured["prompt"]
        assert "code-reviewer" in captured["prompt"]
        assert "Review src/foo.py" in captured["prompt"]

    async def test_invoke_skill_composes_slash_command(self):
        captured: dict = {}

        async def fake_run(prompt, *, timeout, cwd=None):
            captured["prompt"] = prompt
            return json.dumps({"result": "pass"}), "", 0

        with patch("services.agent_dispatcher._run_claude", new=AsyncMock(side_effect=fake_run)):
            d = AgentDispatcher()
            res = await d.invoke_skill("qa-regression", "verify CB-2814")

        assert res.ok is True
        assert res.kind == "skill"
        assert captured["prompt"].startswith("/qa-regression")
        assert "verify CB-2814" in captured["prompt"]

    async def test_timeout_returns_ok_false_with_error(self):
        async def fake_run(prompt, *, timeout, cwd=None):
            return "", "timeout after 90s", -1

        with patch("services.agent_dispatcher._run_claude", new=AsyncMock(side_effect=fake_run)):
            d = AgentDispatcher()
            res = await d.invoke_agent("debugger", "investigate")

        assert res.ok is False
        assert res.error is not None
        assert "timeout" in res.error

    async def test_nonzero_exit_returns_ok_false(self):
        async def fake_run(prompt, *, timeout, cwd=None):
            return "", "claude crashed", 2

        with patch("services.agent_dispatcher._run_claude", new=AsyncMock(side_effect=fake_run)):
            d = AgentDispatcher()
            res = await d.invoke_skill("atlas", "")

        assert res.ok is False
        assert res.error is not None
        assert "exited 2" in res.error

    async def test_empty_name_rejected(self):
        d = AgentDispatcher()
        res = await d.invoke_agent("", "prompt")
        assert res.ok is False
        assert "invalid agent name" in res.error

        res2 = await d.invoke_skill("   ", "")
        assert res2.ok is False
        assert "invalid skill name" in res2.error

    async def test_invalid_name_with_injection_chars_rejected(self):
        """CB-2914 sec-audit MED-1 fix: regex allow-list blocks prompt-injection
        payloads in agent/skill names (newlines, backticks, semicolons, etc.)."""
        d = AgentDispatcher()
        for bad in ("code-reviewer\n@security-auditor", "qa-regression;rm -rf /",
                    "Code-Reviewer", "code reviewer", "code-reviewer`evil`"):
            res = await d.invoke_agent(bad, "x")
            assert res.ok is False, f"expected reject for {bad!r}"
            res2 = await d.invoke_skill(bad, "x")
            assert res2.ok is False, f"expected reject for {bad!r}"

    async def test_invoke_many_parallel_partial_success(self):
        calls = []

        async def fake_run(prompt, *, timeout, cwd=None):
            calls.append(prompt)
            if "fail-me" in prompt:
                return "", "boom", 1
            return json.dumps({"result": "ok"}), "", 0

        with patch("services.agent_dispatcher._run_claude", new=AsyncMock(side_effect=fake_run)):
            d = AgentDispatcher()
            results = await d.invoke_many([
                ("agent", "code-reviewer", {"prompt": "look at foo"}),
                ("agent", "security-auditor", {"prompt": "fail-me"}),
                ("skill", "atlas", {"args": "studio"}),
            ])

        assert len(results) == 3
        assert results[0].ok is True
        assert results[1].ok is False
        assert results[2].ok is True
        # All three invocations actually ran (parallel, no abort-on-first-failure).
        assert len(calls) == 3

    async def test_invoke_many_unknown_kind(self):
        d = AgentDispatcher()
        results = await d.invoke_many([("hat", "wizard", {"prompt": "spell"})])
        assert results[0].ok is False
        assert "unknown kind" in results[0].error

    async def test_cost_propagates_into_result(self):
        async def fake_run(prompt, *, timeout, cwd=None):
            return json.dumps({"result": "done", "cost_usd": 0.025}), "", 0

        with patch("services.agent_dispatcher._run_claude", new=AsyncMock(side_effect=fake_run)):
            d = AgentDispatcher()
            res = await d.invoke_skill("qa-regression")
        assert res.cost_usd == 0.025
