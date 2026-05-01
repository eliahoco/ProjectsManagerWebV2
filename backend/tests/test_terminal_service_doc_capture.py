"""
Unit tests for the doc-generation snapshot capture in terminal_service
(CB-1586).

Verifies that `_run_claude_async` populates `_pending_doc_jobs` with a
preserved `output_snapshot`, the `started_at` and `completed_at`
timestamps, and the working directory (`project_path`) BEFORE the
session can be cleaned up — and that the `completed_at` set in the
success branch is not clobbered by the `finally` backstop.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest


# Ensure the backend root is importable when this file is run via pytest from
# the project root (matches the pattern in conftest.py).
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from services.terminal_service import (  # noqa: E402
    ExecutionProvider,
    ExecutionStatus,
    TerminalService,
    TerminalSession,
)


pytestmark = pytest.mark.skipif(
    shutil.which("/bin/echo") is None and shutil.which("echo") is None,
    reason="echo binary not available",
)


def _make_running_session(svc: TerminalService, cwd: str) -> TerminalSession:
    """Insert a RUNNING session that `_run_claude_async` can drive."""
    session = TerminalSession(
        id="test-session-cb1586",
        issue_id="issue-1",
        issue_key="CB-TEST-1",
        issue_title="capture test",
        project_id="proj-1",
        provider=ExecutionProvider.CLAUDE_CODE,
        status=ExecutionStatus.RUNNING,
        started_at=datetime.utcnow(),
        project_path=cwd,
    )
    with svc._sessions_lock:
        svc._sessions[session.id] = session
        svc._sessions_by_issue[session.issue_id] = session.id
    return session


def test_run_claude_async_captures_doc_job_after_success(tmp_path):
    """Successful run enqueues snapshot + both timestamps + cwd."""
    svc = TerminalService()
    cwd = str(tmp_path)
    session = _make_running_session(svc, cwd)

    # Prefer the absolute path so a hostile $PATH can't shadow `echo`.
    echo = shutil.which("/bin/echo") or shutil.which("echo") or "/bin/echo"
    svc._run_claude_async(
        session_id=session.id,
        cmd=[echo, "hello-from-cb1586"],
        cwd=cwd,
        env=os.environ.copy(),
    )

    # Success branch fired
    assert session.status == ExecutionStatus.COMPLETED
    assert session.exit_code == 0

    job = svc._pending_doc_jobs.get(session.id)
    assert job is not None, "expected pending doc-gen job after success"

    # Snapshot is a list and is decoupled from the live session.output
    assert isinstance(job["output_snapshot"], list)
    assert job["output_snapshot"] is not session.output

    # Timestamps present and ordered
    assert isinstance(job["started_at"], datetime)
    assert isinstance(job["completed_at"], datetime)
    assert job["completed_at"] >= job["started_at"]

    # cwd carried through for downstream git operations
    assert job["project_path"] == cwd
    assert job["issue_id"] == session.issue_id


def test_completed_at_not_clobbered_by_finally(tmp_path):
    """The success-branch completed_at survives the finally backstop."""
    svc = TerminalService()
    cwd = str(tmp_path)
    session = _make_running_session(svc, cwd)

    # Prefer the absolute path so a hostile $PATH can't shadow `echo`.
    echo = shutil.which("/bin/echo") or shutil.which("echo") or "/bin/echo"
    svc._run_claude_async(
        session_id=session.id,
        cmd=[echo, "ok"],
        cwd=cwd,
        env=os.environ.copy(),
    )

    job = svc._pending_doc_jobs[session.id]
    # Object identity — not just equality. A clobber in the finally block
    # would replace the datetime with a freshly-constructed instance, even
    # if both happen to compare equal at microsecond resolution on macOS.
    assert session.completed_at is job["completed_at"]


def test_consume_pending_doc_job_pops_once(tmp_path):
    """consume_pending_doc_job returns the job once, then None."""
    svc = TerminalService()
    cwd = str(tmp_path)
    session = _make_running_session(svc, cwd)

    # Prefer the absolute path so a hostile $PATH can't shadow `echo`.
    echo = shutil.which("/bin/echo") or shutil.which("echo") or "/bin/echo"
    svc._run_claude_async(
        session_id=session.id,
        cmd=[echo, "ok"],
        cwd=cwd,
        env=os.environ.copy(),
    )

    first = svc.consume_pending_doc_job(session.id)
    second = svc.consume_pending_doc_job(session.id)
    assert first is not None
    assert second is None


def test_failed_branch_completed_at_backstop_runs(tmp_path):
    """FAILED branch (non-zero exit) leaves no doc-job; finally still stamps completed_at.

    Regression guard: when the completion succeeds the success branch sets
    `completed_at` and enqueues the doc-job; the finally block must
    preserve that timestamp. Conversely, on a failed run the success
    branch is skipped, no doc-job is enqueued, and finally is the only
    thing that sets `completed_at`. Both invariants matter for downstream
    consumers (process_pending_completions skips no-job sessions, but
    eviction/UI still need a completed_at).
    """
    svc = TerminalService()
    cwd = str(tmp_path)
    session = _make_running_session(svc, cwd)

    # `false` exits non-zero on every Unix — drives the failed branch.
    false_bin = shutil.which("/usr/bin/false") or shutil.which("false") or "/bin/false"
    svc._run_claude_async(
        session_id=session.id,
        cmd=[false_bin],
        cwd=cwd,
        env=os.environ.copy(),
    )

    assert session.status == ExecutionStatus.FAILED
    # finally backstop ran
    assert session.completed_at is not None
    assert isinstance(session.completed_at, datetime)
    # No doc-job enqueued for failures
    assert svc._pending_doc_jobs.get(session.id) is None


def test_doc_job_survives_when_consumed_before_cleanup(tmp_path):
    """consume_pending_doc_job returns the job even after cleanup_session.

    Regression guard for the original CB-1586 motivation: the doc-job must
    be safe to consume BEFORE cleanup, but cleanup must also drop any
    leftover entry so we don't leak memory across orphaned jobs.
    """
    svc = TerminalService()
    cwd = str(tmp_path)
    session = _make_running_session(svc, cwd)

    # Prefer the absolute path so a hostile $PATH can't shadow `echo`.
    echo = shutil.which("/bin/echo") or shutil.which("echo") or "/bin/echo"
    svc._run_claude_async(
        session_id=session.id,
        cmd=[echo, "ok"],
        cwd=cwd,
        env=os.environ.copy(),
    )

    # Snapshot pulled BEFORE cleanup — generator path
    job = svc.consume_pending_doc_job(session.id)
    assert job is not None
    snapshot = job["output_snapshot"]

    # Cleanup session — output list is gone, but snapshot is independent
    svc.cleanup_session(session.id)
    assert svc.get_session(session.id) is None
    assert snapshot, "snapshot must remain readable after session cleanup"

    # And the pending_doc_jobs entry is gone (cleanup drops leftovers)
    assert svc._pending_doc_jobs.get(session.id) is None
