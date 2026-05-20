"""
Tests for services/studio_chat_agent.py — CB-2384

All tests use mocked Anthropic clients; no real API calls are made.
"""

from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# Ensure backend root is on the path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Provide a dummy API token so main.py doesn't fail its deploy-gate assert
os.environ.setdefault("INTERNAL_API_TOKEN", "pytest-internal-token-not-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key-not-real")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(
    *,
    token_budget: int = 50_000,
    tokens_used: int = 0,
    project_id: str = "proj-test",
    tenant_id: str = "default",
) -> MagicMock:
    """Build a mock StudioSession."""
    session = MagicMock()
    session.id = "session-test-id"
    session.tenantId = tenant_id
    session.projectId = project_id
    session.tokenBudget = token_budget
    session.tokensUsed = tokens_used
    return session


def _make_mock_anthropic_client(
    *,
    classifier_text: str = "planning",
    stream_events: list | None = None,
) -> MagicMock:
    """
    Build a mock AsyncAnthropic client.

    classifier_text: what the Haiku classifier returns.
    stream_events:   list of mock events from the stream (defaults to empty
                     text stream with message_start/delta/stop).
    """
    client = MagicMock()

    # --- Classifier (messages.create) ---
    classifier_response = MagicMock()
    classifier_response.content = [MagicMock(text=classifier_text)]
    client.messages.create = AsyncMock(return_value=classifier_response)

    # --- Streaming (messages.stream context manager) ---
    if stream_events is None:
        stream_events = []

    async def _aiter_events():
        for evt in stream_events:
            yield evt

    stream_cm = AsyncMock()
    stream_obj = MagicMock()
    stream_obj.__aiter__ = _aiter_events

    stream_cm.__aenter__ = AsyncMock(return_value=stream_obj)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    client.messages.stream = MagicMock(return_value=stream_cm)
    return client


def _make_db() -> AsyncMock:
    """Build a minimal async DB session mock."""
    db = AsyncMock()
    # execute returns an object whose scalars().all() returns []
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    execute_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=execute_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


async def _collect(gen: AsyncIterator[dict]) -> list[dict]:
    """Drain an async generator into a list."""
    return [item async for item in gen]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConstruct:
    def test_construct_agent_with_mock_client(self):
        """StudioChatAgent can be instantiated with an explicit mock client."""
        from services.studio_chat_agent import StudioChatAgent

        mock_client = MagicMock()
        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=mock_client)

        assert agent.client is mock_client

    def test_construct_agent_without_client_uses_env(self):
        """Without an explicit client, the agent reads ANTHROPIC_API_KEY from env."""
        from services.studio_chat_agent import StudioChatAgent
        import anthropic

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=None)
        assert isinstance(agent.client, anthropic.AsyncAnthropic)

    def test_get_studio_chat_agent_singleton(self):
        """get_studio_chat_agent returns a singleton."""
        import services.studio_chat_agent as _mod

        # Reset the singleton between tests
        _mod.studio_chat_agent = None

        a1 = _mod.get_studio_chat_agent()
        a2 = _mod.get_studio_chat_agent()
        assert a1 is a2

        # Clean up
        _mod.studio_chat_agent = None


class TestClassifierRouting:
    @pytest.mark.asyncio
    async def test_classifier_routes_clarification_to_haiku(self):
        """When classifier returns 'clarification', the routed model is Haiku."""
        from services.studio_chat_agent import StudioChatAgent, _MODEL_HAIKU

        mock_client = _make_mock_anthropic_client(classifier_text="clarification")
        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=mock_client)

        routed = await agent._classify_and_route("What does the data model look like?")
        assert routed == _MODEL_HAIKU

    @pytest.mark.asyncio
    async def test_classifier_routes_planning_to_opus(self):
        """When classifier returns 'planning', the routed model is Opus."""
        from services.studio_chat_agent import StudioChatAgent, _MODEL_OPUS

        mock_client = _make_mock_anthropic_client(classifier_text="planning")
        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=mock_client)

        routed = await agent._classify_and_route("I want to build a multi-tenant SaaS platform")
        assert routed == _MODEL_OPUS

    @pytest.mark.asyncio
    async def test_classifier_routes_revision_to_sonnet(self):
        """When classifier returns 'revision', the routed model is Sonnet."""
        from services.studio_chat_agent import StudioChatAgent, _MODEL_SONNET

        mock_client = _make_mock_anthropic_client(classifier_text="revision")
        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=mock_client)

        routed = await agent._classify_and_route("Please change the Epic title")
        assert routed == _MODEL_SONNET

    @pytest.mark.asyncio
    async def test_classifier_routes_approval_to_haiku(self):
        """When classifier returns 'approval', the routed model is Haiku."""
        from services.studio_chat_agent import StudioChatAgent, _MODEL_HAIKU

        mock_client = _make_mock_anthropic_client(classifier_text="approval")
        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=mock_client)

        routed = await agent._classify_and_route("Looks good, push it!")
        assert routed == _MODEL_HAIKU

    @pytest.mark.asyncio
    async def test_classifier_failure_falls_back_to_sonnet(self):
        """If the classifier raises, fallback is Sonnet."""
        from services.studio_chat_agent import StudioChatAgent, _MODEL_SONNET

        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=Exception("network failure"))

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=client)
        routed = await agent._classify_and_route("Tell me something")
        assert routed == _MODEL_SONNET

    @pytest.mark.asyncio
    async def test_classifier_unknown_class_falls_back_to_sonnet(self):
        """Unknown classification string → Sonnet."""
        from services.studio_chat_agent import StudioChatAgent, _MODEL_SONNET

        mock_client = _make_mock_anthropic_client(classifier_text="banana")
        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=mock_client)

        routed = await agent._classify_and_route("Some message")
        assert routed == _MODEL_SONNET


class TestTokenBudget:
    @pytest.mark.asyncio
    async def test_token_budget_blocks_when_exceeded(self):
        """
        If session.tokensUsed >= session.tokenBudget, run_turn yields an error
        event immediately and returns without calling the API.
        """
        from services.studio_chat_agent import StudioChatAgent

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock()   # should NOT be called
        mock_client.messages.stream = MagicMock()   # should NOT be called

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=mock_client)
        session = _make_session(token_budget=1000, tokens_used=1000)
        db = _make_db()

        events = await _collect(agent.run_turn(session, db))

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "token budget" in events[0]["error"].lower()

        # Classifier and streamer must NOT have been called
        mock_client.messages.create.assert_not_called()
        mock_client.messages.stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_budget_blocks_when_tokens_used_exceeds_budget(self):
        """Strictly greater than also triggers the budget guard."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(
            db_factory=MagicMock(),
            anthropic_client=MagicMock(),
        )
        session = _make_session(token_budget=100, tokens_used=150)
        db = _make_db()

        events = await _collect(agent.run_turn(session, db))

        assert any(e["type"] == "error" for e in events)


class TestReadRepoFileTool:
    @pytest.mark.asyncio
    async def test_read_repo_file_rejects_relative_path(self):
        """Relative paths must return an error embedded in the output dict."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        output, error = await agent._dispatch_tool(
            "read_repo_file",
            {"path": "backend/models/issue.py"},
            session,
            db,
        )

        # Security errors are embedded in the output dict (tool returns them, not raises).
        assert "error" in output
        err_text = output["error"].lower()
        assert "relative" in err_text or "absolute" in err_text
        assert output.get("retryable") is False

    @pytest.mark.asyncio
    async def test_read_repo_file_rejects_path_outside_project_root(self):
        """Absolute paths outside the project root are rejected with an error in output."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        output, error = await agent._dispatch_tool(
            "read_repo_file",
            {"path": "/etc/passwd"},
            session,
            db,
        )

        # The dispatch wraps tool return values: (output_dict, None) — error is in output.
        assert "error" in output
        assert output.get("retryable") is False

    @pytest.mark.asyncio
    async def test_read_repo_file_rejects_path_traversal(self):
        """Paths containing '..' are rejected with an error in the output dict."""
        from services.studio_chat_agent import StudioChatAgent, _PROJECT_ROOT

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        evil_path = _PROJECT_ROOT + "../../etc/shadow"
        output, error = await agent._dispatch_tool(
            "read_repo_file",
            {"path": evil_path},
            session,
            db,
        )

        assert "error" in output

    @pytest.mark.asyncio
    async def test_read_repo_file_rejects_symlink_pointing_outside_root(self, tmp_path):
        """HIGH-1: a symlink inside the project root that points outside must be rejected."""
        import os as _os
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        # Create a file outside the project root.
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        secret_file = outside_dir / "secret.txt"
        secret_file.write_text("super secret content")

        # Create a "project root" directory and a symlink inside it pointing outside.
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        symlink_path = project_dir / "evil_link.txt"
        _os.symlink(str(secret_file), str(symlink_path))

        # Patch PROJECT_ROOT to the project dir (with trailing slash).
        with patch(
            "services.studio_chat_agent._PROJECT_ROOT",
            str(project_dir) + "/",
        ):
            output, error = await agent._dispatch_tool(
                "read_repo_file",
                {"path": str(symlink_path)},
                session,
                db,
            )

        # The symlink resolves outside the project root — must be rejected.
        assert "error" in output
        assert output.get("retryable") is False
        assert "super secret content" not in str(output)

    @pytest.mark.asyncio
    async def test_read_repo_file_accepts_absolute_path_within_project(self, tmp_path):
        """Happy path: valid absolute path within the project root returns content."""
        from services.studio_chat_agent import StudioChatAgent, _PROJECT_ROOT

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        # Write a temp file and patch _PROJECT_ROOT to point at tmp_path
        test_file = tmp_path / "hello.py"
        test_file.write_text("print('hello world')\n")

        with patch("services.studio_chat_agent._PROJECT_ROOT", str(tmp_path) + "/"):
            output, error = await agent._dispatch_tool(
                "read_repo_file",
                {"path": str(test_file)},
                session,
                db,
            )

        assert error is None
        assert "content" in output
        assert "hello world" in output["content"]
        assert output["truncated"] is False

    @pytest.mark.asyncio
    async def test_read_repo_file_returns_truncated_flag_for_large_files(self, tmp_path):
        """Files larger than 8K chars are truncated and truncated=True is set."""
        from services.studio_chat_agent import StudioChatAgent, _MAX_FILE_CHARS

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        big_content = "x" * (_MAX_FILE_CHARS + 100)
        test_file = tmp_path / "bigfile.txt"
        test_file.write_text(big_content)

        with patch("services.studio_chat_agent._PROJECT_ROOT", str(tmp_path) + "/"):
            output, error = await agent._dispatch_tool(
                "read_repo_file",
                {"path": str(test_file)},
                session,
                db,
            )

        assert error is None
        assert output["truncated"] is True
        assert len(output["content"]) == _MAX_FILE_CHARS


class TestSearchCodeboardTool:
    @pytest.mark.asyncio
    async def test_search_codeboard_calls_api_and_returns_issues(self):
        """search_codeboard makes an HTTP GET to CodeBoard and maps the response."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        fake_response_body = [
            {
                "key": "CB-42",
                "title": "Implement auth flow",
                "type": "STORY",
                "status": "IN_PROGRESS",
                "description": "As a user I can log in with GitHub",
            }
        ]

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = fake_response_body

        mock_async_client = AsyncMock()
        mock_async_client.get = AsyncMock(return_value=mock_http_response)
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.studio_chat_agent.httpx.AsyncClient", return_value=mock_async_client):
            output, error = await agent._dispatch_tool(
                "search_codeboard",
                {"query": "auth flow", "project_id": "proj-test"},
                session,
                db,
            )

        assert error is None
        assert len(output["issues"]) == 1
        issue = output["issues"][0]
        assert issue["key"] == "CB-42"
        assert issue["title"] == "Implement auth flow"
        assert issue["type"] == "STORY"
        assert issue["status"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_search_codeboard_handles_api_error(self):
        """Non-200 CodeBoard responses are surfaced as an error field."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        mock_http_response = MagicMock()
        mock_http_response.status_code = 503
        mock_http_response.json.return_value = {}

        mock_async_client = AsyncMock()
        mock_async_client.get = AsyncMock(return_value=mock_http_response)
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.studio_chat_agent.httpx.AsyncClient", return_value=mock_async_client):
            output, error = await agent._dispatch_tool(
                "search_codeboard",
                {"query": "anything"},
                session,
                db,
            )

        # tool never raises; error is embedded in output
        assert error is None
        assert "error" in output
        assert "503" in output["error"]

    @pytest.mark.asyncio
    async def test_search_codeboard_handles_network_error(self):
        """Network errors are caught and returned as an error in the output dict."""
        import httpx as _httpx
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        mock_async_client = AsyncMock()
        mock_async_client.get = AsyncMock(
            side_effect=_httpx.ConnectError("connection refused")
        )
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.studio_chat_agent.httpx.AsyncClient", return_value=mock_async_client):
            output, error = await agent._dispatch_tool(
                "search_codeboard",
                {"query": "anything"},
                session,
                db,
            )

        assert error is None   # dispatch never raises
        assert "error" in output


class TestQueryRagTool:
    @pytest.mark.asyncio
    async def test_query_rag_calls_rag_service(self):
        """query_rag delegates to rag_service.search_issues."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        fake_rag_results = [
            {
                "key": "CB-10",
                "issue_id": "issue-10",
                "document": "Title: Auth service\nDescription: Handles login",
                "score": 0.92,
            }
        ]

        mock_rag = MagicMock()
        mock_rag.search_issues = AsyncMock(return_value=fake_rag_results)

        with patch.dict("sys.modules", {"services.rag_service": MagicMock(rag_service=mock_rag)}):
            output, error = await agent._dispatch_tool(
                "query_rag",
                {"question": "authentication"},
                session,
                db,
            )

        assert error is None
        assert "results" in output


class TestCreateArtifactTool:
    @pytest.mark.asyncio
    async def test_create_artifact_persists_row(self):
        """create_artifact writes a StudioArtifact row and returns artifact_id."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        output, error = await agent._dispatch_tool(
            "create_artifact",
            {
                "name": "Architecture Diagram",
                "kind": "mermaid",
                "content": "graph TD\n  A --> B",
            },
            session,
            db,
        )

        assert error is None
        assert "artifact_id" in output
        assert output["kind"] == "MERMAID"
        db.add.assert_called_once()
        db.commit.assert_awaited()


class TestAskClarifyingQuestionTool:
    @pytest.mark.asyncio
    async def test_ask_clarifying_question_returns_question(self):
        """Returns the question text."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        output, error = await agent._dispatch_tool(
            "ask_clarifying_question",
            {"question": "Which database engine should we target?", "context": "Affects schema design"},
            session,
            db,
        )

        assert error is None
        assert output["question"] == "Which database engine should we target?"

    @pytest.mark.asyncio
    async def test_ask_clarifying_question_enforces_limit(self):
        """After 4 questions, subsequent calls return an error output (not a raise)."""
        from services.studio_chat_agent import StudioChatAgent, _MAX_CLARIFYING_QUESTIONS
        from models.studio import StudioAgentActivity

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()
        db = _make_db()

        # Simulate that 4 questions have already been asked
        fake_activities = [MagicMock() for _ in range(_MAX_CLARIFYING_QUESTIONS)]
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = fake_activities
        db.execute = AsyncMock(return_value=execute_result)

        output, error = await agent._dispatch_tool(
            "ask_clarifying_question",
            {"question": "One more question?"},
            session,
            db,
        )

        # Tool never raises; returns error in output
        assert error is None
        assert "error" in output
        assert output.get("retryable") is False


class TestCostComputation:
    def test_compute_cost_opus(self):
        """Cost for Opus is $15/MT input + $75/MT output."""
        from services.studio_chat_agent import _compute_cost, _MODEL_OPUS

        cost = _compute_cost(_MODEL_OPUS, tokens_input=1_000_000, tokens_output=0)
        assert abs(cost - 15.00) < 0.001

        cost = _compute_cost(_MODEL_OPUS, tokens_input=0, tokens_output=1_000_000)
        assert abs(cost - 75.00) < 0.001

    def test_compute_cost_sonnet(self):
        """Cost for Sonnet is $3/MT input + $15/MT output."""
        from services.studio_chat_agent import _compute_cost, _MODEL_SONNET

        cost = _compute_cost(_MODEL_SONNET, tokens_input=1_000_000, tokens_output=1_000_000)
        assert abs(cost - 18.00) < 0.001

    def test_compute_cost_haiku(self):
        """Cost for Haiku is $0.80/MT input + $4/MT output."""
        from services.studio_chat_agent import _compute_cost, _MODEL_HAIKU

        cost = _compute_cost(_MODEL_HAIKU, tokens_input=500_000, tokens_output=500_000)
        assert abs(cost - 2.40) < 0.001

    def test_compute_cost_unknown_model_uses_default(self):
        """Unknown models fall back to Sonnet pricing without raising."""
        from services.studio_chat_agent import _compute_cost

        cost = _compute_cost("some-future-model", 1_000_000, 1_000_000)
        assert cost > 0  # just verify it doesn't crash


class TestSubAgentStub:
    @pytest.mark.asyncio
    async def test_spawn_subagent_stub_returns_not_implemented(self):
        """Phase 2 sub-agent stub returns the expected sentinel dict."""
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(db_factory=MagicMock(), anthropic_client=MagicMock())
        session = _make_session()

        result = await agent._spawn_subagent_stub("researcher", "find auth patterns", session)
        assert result["status"] == "not_implemented_phase_1"
        assert result["agent_role"] == "researcher"


class TestRunTurnBudgetGuard:
    @pytest.mark.asyncio
    async def test_run_turn_emits_error_and_stops_on_budget_exceeded(self):
        """
        run_turn must emit exactly one error event and then terminate
        when the session budget is already exhausted.
        """
        from services.studio_chat_agent import StudioChatAgent

        agent = StudioChatAgent(
            db_factory=MagicMock(),
            anthropic_client=MagicMock(),
        )
        session = _make_session(token_budget=500, tokens_used=500)
        db = _make_db()

        events = await _collect(agent.run_turn(session, db))

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1
        assert "budget" in error_events[0]["error"].lower()

        # No turn_complete should be emitted
        complete_events = [e for e in events if e["type"] == "turn_complete"]
        assert len(complete_events) == 0
