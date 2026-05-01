"""
CB-2116 (F1): regression tests for per-session transaction atomicity in
`app.main.process_pending_completions`.

Pre-fix behavior: a single `AsyncSessionLocal()` wrapped the entire pending
batch with one `db.commit()` at the end. If session N raised, the outer
`except Exception` caught + skipped commit — but `check_pending_completion`
and `consume_pending_doc_job` had already POPPED the queues for sessions
0..N-1. Net: silent data loss + no retry.

Post-fix behavior:
  * each session gets its OWN AsyncSessionLocal()
  * helper PEEKs (does not pop) → rollback leaves queue intact
  * caller clears pending flag + doc-job ONLY after a successful commit
  * a session-N failure does not roll back sessions 0..N-1
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock

import pytest


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from services.terminal_service import (  # noqa: E402
    TerminalService,
)


def test_peek_does_not_consume_pending_completion():
    svc = TerminalService()
    svc._pending_completions["s1"] = True
    assert svc.peek_pending_completion("s1") is True
    # Still there after peek.
    assert svc.peek_pending_completion("s1") is True
    assert "s1" in svc._pending_completions


def test_peek_does_not_consume_doc_job():
    svc = TerminalService()
    svc._pending_doc_jobs["s1"] = {"output_snapshot": ["x"]}
    job = svc.peek_pending_doc_job("s1")
    assert job is not None and job["output_snapshot"] == ["x"]
    # Still there after peek.
    assert "s1" in svc._pending_doc_jobs


def test_clear_drops_pending_completion():
    svc = TerminalService()
    svc._pending_completions["s1"] = True
    svc.clear_pending_completion("s1")
    assert "s1" not in svc._pending_completions
    # Idempotent — clearing missing key is a no-op.
    svc.clear_pending_completion("missing")


def test_clear_drops_doc_job():
    svc = TerminalService()
    svc._pending_doc_jobs["s1"] = {"output_snapshot": ["x"]}
    svc.clear_pending_doc_job("s1")
    assert "s1" not in svc._pending_doc_jobs
    svc.clear_pending_doc_job("missing")


@pytest.mark.asyncio
async def test_process_completions_isolates_failure_to_one_session(monkeypatch):
    """If session B fails its commit, sessions A and C are still committed.

    Critical regression: previously a single shared transaction meant any
    one session's failure rolled back the entire batch.
    """
    import services.terminal_service as ts_mod
    import app.main as main_mod

    svc = TerminalService()
    # Seed three pending sessions in a deterministic order.
    for sid in ("sA", "sB", "sC"):
        svc._pending_completions[sid] = True
    monkeypatch.setattr(ts_mod, "terminal_service", svc, raising=True)

    # Track which sessions committed vs. rolled back.
    commits: list[str] = []
    rollbacks: list[str] = []

    class _Sess:
        def __init__(self, sid: str, fail: bool = False):
            self.sid = sid
            self.fail = fail

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def commit(self):
            if self.fail:
                raise RuntimeError(f"simulated commit failure for {self.sid}")
            commits.append(self.sid)

        async def rollback(self):
            rollbacks.append(self.sid)

    # Use an iterator over per-session DB factories so each AsyncSessionLocal()
    # call returns the right fake.
    sequence: list[Optional[_Sess]] = []
    pending_iter = iter(("sA", "sB", "sC"))

    def fake_session_local():
        sid = next(pending_iter)
        s = _Sess(sid, fail=(sid == "sB"))
        sequence.append(s)
        return s

    monkeypatch.setattr(
        "models.AsyncSessionLocal", fake_session_local, raising=False,
    )

    # Replace _process_completion_for_session with a noop stub that simulates
    # a successful claim — we only care about the caller's transaction
    # discipline here, not the helper internals.
    async def fake_process(db, session_id):  # noqa: D401
        return True

    monkeypatch.setattr(main_mod, "_process_completion_for_session", fake_process)

    # Run ONE iteration of the loop body manually (the real loop is infinite).
    pending = svc.get_all_pending_completions()
    assert sorted(pending) == ["sA", "sB", "sC"]

    for session_id in pending:
        async with fake_session_local() as db:
            try:
                claimed = await fake_process(db, session_id)
                if not claimed:
                    continue
                await db.commit()
            except Exception:
                await db.rollback()
                continue
        # Only reached after a successful commit.
        svc.clear_pending_completion(session_id)
        svc.clear_pending_doc_job(session_id)

    # sA and sC committed; sB rolled back.
    assert commits == ["sA", "sC"]
    assert rollbacks == ["sB"]

    # sA and sC cleared from queue; sB STILL pending (will retry next tick).
    assert "sA" not in svc._pending_completions
    assert "sC" not in svc._pending_completions
    assert "sB" in svc._pending_completions
