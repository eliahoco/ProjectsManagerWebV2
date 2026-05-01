"""
CB-1585: regression tests for the documentation-generation hook in the
async completion loop (`app.main._process_completion_for_session`).

Covers:
  * pending-completion flag is consumed
  * issue is flipped to COMPLETED_WAITING_QA when not already terminal
  * `documentation_generator.generate_from_execution` is invoked with
    the captured doc-job (snapshot, timestamps, project_path) and the
    same db session — so the summary row and status update land in the
    same transaction
  * a doc-gen failure is swallowed (best-effort enrichment, never the
    primary completion path)
  * if no doc-job is queued (e.g. failed run), the hook is a no-op
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from services.terminal_service import (  # noqa: E402
    ExecutionProvider,
    ExecutionStatus,
    TerminalService,
    TerminalSession,
    terminal_service as _global_terminal_service,
)


def _seed_completed_session(svc: TerminalService, *, issue_id: str) -> TerminalSession:
    session = TerminalSession(
        id=f"sess-{issue_id}",
        issue_id=issue_id,
        issue_key="CB-9999",
        issue_title="hook integration",
        project_id="proj-1",
        provider=ExecutionProvider.CLAUDE_CODE,
        status=ExecutionStatus.COMPLETED,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        project_path="/tmp/fake-proj",
        exit_code=0,
    )
    with svc._sessions_lock:
        svc._sessions[session.id] = session
        svc._sessions_by_issue[session.issue_id] = session.id
        svc._pending_completions[session.id] = True
        svc._pending_doc_jobs[session.id] = {
            "output_snapshot": ["line-1", "line-2"],
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "project_path": "/tmp/from-doc-job",
            "issue_id": session.issue_id,
        }
    return session


class _FakeDB:
    """Minimal stand-in for AsyncSession — only exposes `execute`."""

    def __init__(self, issue):
        self._issue = issue
        self.executed = []

    async def execute(self, stmt):  # noqa: D401 — match AsyncSession API
        self.executed.append(stmt)
        scalar = SimpleNamespace(
            scalar_one_or_none=lambda: self._issue,
        )
        return scalar


def _patch_terminal_service(monkeypatch, svc: TerminalService) -> None:
    """Point `app.main` at our isolated TerminalService instance."""
    import app.main as main_mod
    import services.terminal_service as ts_mod

    monkeypatch.setattr(ts_mod, "terminal_service", svc, raising=True)
    # Also patch any already-imported alias inside main_mod (the helper
    # imports lazily, but this guards against future caching).
    if hasattr(main_mod, "terminal_service"):
        monkeypatch.setattr(main_mod, "terminal_service", svc, raising=False)


@pytest.mark.asyncio
async def test_hook_invokes_generate_from_execution(monkeypatch):
    svc = TerminalService()
    session = _seed_completed_session(svc, issue_id="issue-1")
    issue = SimpleNamespace(
        id="issue-1",
        key="CB-9999",
        status="IN_PROGRESS",
        updatedAt=None,
    )
    _patch_terminal_service(monkeypatch, svc)

    captured = {}

    async def fake_generate(*, session, issue, project_path, db):
        captured["session"] = session
        captured["issue"] = issue
        captured["project_path"] = project_path
        captured["db"] = db
        return None

    import services.documentation_generator as docgen_mod
    monkeypatch.setattr(
        docgen_mod.documentation_generator,
        "generate_from_execution",
        AsyncMock(side_effect=fake_generate),
        raising=True,
    )

    from app.main import _process_completion_for_session

    db = _FakeDB(issue)
    handled = await _process_completion_for_session(db, session.id)

    assert handled is True
    # status flipped
    assert issue.status == "COMPLETED_WAITING_QA"
    assert isinstance(issue.updatedAt, datetime)
    # hook called with the captured doc-job's project_path
    assert captured["session"] is session
    assert captured["issue"] is issue
    assert captured["project_path"] == "/tmp/from-doc-job"
    assert captured["db"] is db
    # CB-2116 (F1): the helper now PEEKs, leaving the queue intact so a
    # rollback by the caller can replay on the next loop tick. The caller
    # (`process_pending_completions`) is responsible for calling
    # `clear_pending_completion` + `clear_pending_doc_job` AFTER a successful
    # commit. So inside the helper they MUST still be present.
    with svc._sessions_lock:
        assert session.id in svc._pending_completions
        assert session.id in svc._pending_doc_jobs


@pytest.mark.asyncio
async def test_hook_falls_back_to_session_project_path(monkeypatch):
    svc = TerminalService()
    session = _seed_completed_session(svc, issue_id="issue-2")
    # Wipe project_path on the doc job so the fallback path is exercised.
    with svc._sessions_lock:
        svc._pending_doc_jobs[session.id]["project_path"] = None
    issue = SimpleNamespace(
        id="issue-2",
        key="CB-9999",
        status="IN_PROGRESS",
        updatedAt=None,
    )
    _patch_terminal_service(monkeypatch, svc)

    captured = {}

    async def fake_generate(*, session, issue, project_path, db):
        captured["project_path"] = project_path

    import services.documentation_generator as docgen_mod
    monkeypatch.setattr(
        docgen_mod.documentation_generator,
        "generate_from_execution",
        AsyncMock(side_effect=fake_generate),
        raising=True,
    )

    from app.main import _process_completion_for_session

    await _process_completion_for_session(_FakeDB(issue), session.id)
    assert captured["project_path"] == session.project_path


@pytest.mark.asyncio
async def test_hook_swallows_doc_gen_failure(monkeypatch):
    svc = TerminalService()
    session = _seed_completed_session(svc, issue_id="issue-3")
    issue = SimpleNamespace(
        id="issue-3",
        key="CB-9999",
        status="IN_PROGRESS",
        updatedAt=None,
    )
    _patch_terminal_service(monkeypatch, svc)

    async def boom(**kwargs):
        raise RuntimeError("simulated doc-gen failure")

    import services.documentation_generator as docgen_mod
    monkeypatch.setattr(
        docgen_mod.documentation_generator,
        "generate_from_execution",
        AsyncMock(side_effect=boom),
        raising=True,
    )

    from app.main import _process_completion_for_session

    # Must NOT raise
    handled = await _process_completion_for_session(_FakeDB(issue), session.id)
    assert handled is True
    # Issue status still updated despite doc-gen failure
    assert issue.status == "COMPLETED_WAITING_QA"


@pytest.mark.asyncio
async def test_hook_logs_warning_when_issue_missing(monkeypatch, caplog):
    """Doc job present but issue row vanished — log a warning, no call."""
    import logging as _logging

    svc = TerminalService()
    session = _seed_completed_session(svc, issue_id="issue-missing")
    _patch_terminal_service(monkeypatch, svc)

    mock_gen = AsyncMock()
    import services.documentation_generator as docgen_mod
    monkeypatch.setattr(
        docgen_mod.documentation_generator,
        "generate_from_execution",
        mock_gen,
        raising=True,
    )

    from app.main import _process_completion_for_session

    # _FakeDB(None) returns None for the issue lookup
    with caplog.at_level(_logging.WARNING, logger="app.main"):
        handled = await _process_completion_for_session(_FakeDB(None), session.id)

    assert handled is True
    mock_gen.assert_not_called()
    assert any(
        "Discarding pending doc-gen job" in r.getMessage()
        for r in caplog.records
    ), "expected warning when issue row missing"


@pytest.mark.asyncio
async def test_hook_skips_when_no_doc_job_present(monkeypatch):
    """Failed runs leave no doc-job — hook must be a no-op (no call)."""
    svc = TerminalService()
    session = _seed_completed_session(svc, issue_id="issue-4")
    # Drop the doc job to simulate a failed-run path that never enqueued.
    with svc._sessions_lock:
        svc._pending_doc_jobs.pop(session.id, None)
    issue = SimpleNamespace(
        id="issue-4",
        key="CB-9999",
        status="IN_PROGRESS",
        updatedAt=None,
    )
    _patch_terminal_service(monkeypatch, svc)

    mock_gen = AsyncMock()
    import services.documentation_generator as docgen_mod
    monkeypatch.setattr(
        docgen_mod.documentation_generator,
        "generate_from_execution",
        mock_gen,
        raising=True,
    )

    from app.main import _process_completion_for_session

    handled = await _process_completion_for_session(_FakeDB(issue), session.id)
    assert handled is True
    # Status still flipped, but no doc-gen call
    assert issue.status == "COMPLETED_WAITING_QA"
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_hook_returns_false_when_no_pending_flag(monkeypatch):
    """Stale session_id with no pending flag is a graceful no-op."""
    svc = TerminalService()
    _patch_terminal_service(monkeypatch, svc)

    from app.main import _process_completion_for_session

    handled = await _process_completion_for_session(_FakeDB(None), "missing-sess")
    assert handled is False


@pytest.mark.asyncio
async def test_hook_keeps_done_status_unchanged(monkeypatch):
    """Issue already DONE / COMPLETED_WAITING_QA is not re-flipped."""
    svc = TerminalService()
    session = _seed_completed_session(svc, issue_id="issue-5")
    issue = SimpleNamespace(
        id="issue-5",
        key="CB-9999",
        status="DONE",
        updatedAt=None,
    )
    _patch_terminal_service(monkeypatch, svc)

    import services.documentation_generator as docgen_mod
    monkeypatch.setattr(
        docgen_mod.documentation_generator,
        "generate_from_execution",
        AsyncMock(return_value=None),
        raising=True,
    )

    from app.main import _process_completion_for_session

    handled = await _process_completion_for_session(_FakeDB(issue), session.id)
    assert handled is True
    assert issue.status == "DONE"
    assert issue.updatedAt is None


# Restore the global terminal_service singleton after each test to avoid
# leaking patched state into unrelated suites that import it.
@pytest.fixture(autouse=True)
def _restore_global_terminal_service():
    yield
    import services.terminal_service as ts_mod
    ts_mod.terminal_service = _global_terminal_service
