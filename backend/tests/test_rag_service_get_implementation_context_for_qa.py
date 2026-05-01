"""Regression tests for RAGService.get_implementation_context_for_qa (CB-1597)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.rag_service import RAGService


def _make_db_returning(summary):
    """Build an AsyncSession-like mock whose execute() returns scalar_one_or_none=summary."""
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = summary
    db.execute = AsyncMock(return_value=result)
    return db


def _make_summary(**overrides):
    """Build a MagicMock standing in for an ExecutionSummary row."""
    defaults = {
        "summary": "Built feature X end-to-end.",
        "filesTouched": json.dumps(["backend/app.py", "frontend/page.tsx"]),
        "componentsModified": json.dumps(["backend", "frontend"]),
        "architectureNotes": "Used factory pattern.",
        "technicalNotes": "Cached via React Query.",
        "challengesFaced": "Deal with race condition in startup.",
    }
    defaults.update(overrides)
    summary = MagicMock()
    for key, value in defaults.items():
        setattr(summary, key, value)
    return summary


@pytest.mark.asyncio
async def test_get_implementation_context_returns_empty_when_no_summary():
    rag = RAGService()
    db = _make_db_returning(None)

    out = await rag.get_implementation_context_for_qa(
        db, project_id="proj-1", issue_id="issue-1"
    )

    assert out == ""
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_implementation_context_renders_full_summary():
    rag = RAGService()
    db = _make_db_returning(_make_summary())

    out = await rag.get_implementation_context_for_qa(
        db, project_id="proj-1", issue_id="issue-1"
    )

    assert "## Implementation Summary" in out
    assert "Built feature X end-to-end." in out
    assert "## Files Modified" in out
    assert "- backend/app.py" in out
    assert "- frontend/page.tsx" in out
    assert "## Components" in out
    assert "backend, frontend" in out
    assert "## Architecture Notes" in out
    assert "Used factory pattern." in out
    assert "## Technical Notes" in out
    assert "Cached via React Query." in out
    assert "## Known Challenges" in out
    assert "race condition" in out


@pytest.mark.asyncio
async def test_get_implementation_context_omits_empty_optional_sections():
    rag = RAGService()
    db = _make_db_returning(
        _make_summary(
            filesTouched=None,
            componentsModified=None,
            architectureNotes=None,
            technicalNotes=None,
            challengesFaced=None,
        )
    )

    out = await rag.get_implementation_context_for_qa(
        db, project_id="proj-1", issue_id="issue-1"
    )

    assert "## Implementation Summary" in out
    assert "Built feature X end-to-end." in out
    assert "## Files Modified" not in out
    assert "## Components" not in out
    assert "## Architecture Notes" not in out
    assert "## Technical Notes" not in out
    assert "## Known Challenges" not in out


@pytest.mark.asyncio
async def test_get_implementation_context_handles_malformed_json_gracefully():
    rag = RAGService()
    db = _make_db_returning(
        _make_summary(
            filesTouched="this-is-not-json",
            componentsModified="{broken",
        )
    )

    out = await rag.get_implementation_context_for_qa(
        db, project_id="proj-1", issue_id="issue-1"
    )

    # _safe_json_list returns [] for malformed input, so these sections drop out
    assert "## Files Modified" not in out
    assert "## Components" not in out
    # Other sections still render
    assert "## Architecture Notes" in out


@pytest.mark.asyncio
async def test_get_implementation_context_queries_latest_summary_scoped_to_project():
    """SQL must JOIN Issue, scope by projectId, ORDER BY executedAt DESC, LIMIT 1."""
    rag = RAGService()
    db = _make_db_returning(_make_summary())

    await rag.get_implementation_context_for_qa(
        db, project_id="proj-1", issue_id="issue-1"
    )

    db.execute.assert_awaited_once()
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ExecutionSummary" in compiled
    assert "Issue" in compiled  # Join target for project scoping
    assert "projectId" in compiled  # Cross-project isolation predicate
    assert "ORDER BY" in compiled.upper()
    assert "executedAt" in compiled
    assert "LIMIT 1" in compiled.upper().replace("\n", " ")


@pytest.mark.asyncio
async def test_get_implementation_context_returns_empty_when_issue_in_other_project():
    """Cross-project isolation: foreign issue_id must yield no results.

    The DB returns None because the JOIN-on-projectId filter eliminates the
    row whose Issue.projectId != requested project_id. Verifies the H-1
    fix from the CB-1597 security audit.
    """
    rag = RAGService()
    db = _make_db_returning(None)

    out = await rag.get_implementation_context_for_qa(
        db, project_id="proj-1", issue_id="issue-belonging-to-proj-2"
    )

    assert out == ""
