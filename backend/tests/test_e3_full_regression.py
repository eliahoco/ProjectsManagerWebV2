"""
CB-2093 (T3.3.4) — E3 full regression for the documentation-settings surface.

End-to-end coverage of the three behaviours that gate the auto-documentation
pipeline introduced in EPIC CB-2078:

  (a) DocSettings.autoGenerate=False → completion hook skips doc-gen,
      no ExecutionSummary row is written, but issue still flips to
      COMPLETED_WAITING_QA.
  (b) DocSettings.autoGenerate=True  → completion hook invokes the
      generator, exactly one ExecutionSummary row is written.
  (c) `apply_retention` purges ExecutionSummary rows older than
      `retentionDays` (and respects the per-issue cap).

Driver: `app.main._process_completion_for_session` is the actual code path
the completion loop runs against every successful session. Exercising it
end-to-end (with a real isolated SQLite, real `DocSettings` row, real
`documentation_generator.generate_from_execution`) gives us the regression
guarantee CB-2093 asks for — gating, persistence, and retention all on the
same artifact.

Mocked surfaces (kept narrow to preserve regression value):
  * `services.ai_service.ai_service.generate_text` returns "" so the
    deterministic fallback summary is used (no model call, no network).
  * `project_path=None` so `_capture_git_changes` short-circuits with
    an empty capture (no git subprocess).
  * `documentation_generator._rag = None` so ChromaDB is not contacted.

Schema note for scenario (c): the public PATCH endpoint enforces
`retentionDays >= 1` (Pydantic). The retention helper itself accepts any
non-negative integer, so the test sets `retentionDays=1` and ages rows
to 5 days — exercises the same SQL DELETE path the operational schedule
runs every 6h, while staying within the publicly representable range.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from models.database import Base  # noqa: E402
from models.documentation import ExecutionSummary  # noqa: E402
from models.issue import Issue, Project  # noqa: E402
from services.doc_settings_service import (  # noqa: E402
    apply_retention,
    get_or_create_settings,
)
from services.terminal_service import (  # noqa: E402
    ExecutionProvider,
    ExecutionStatus,
    TerminalService,
    TerminalSession,
)


# ---------------------------------------------------------------------------
# Fixtures: isolated SQLite, fresh TerminalService, narrowly mocked AI
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def factory():
    """Yield a fresh on-disk SQLite + sessionmaker for each test."""
    tmp_dir = tempfile.mkdtemp(prefix="e3-regression-")
    db_path = os.path.join(tmp_dir, "test.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession,
        expire_on_commit=False, autocommit=False, autoflush=False,
    )

    try:
        yield sessionmaker
    finally:
        await engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def fresh_terminal_service(monkeypatch):
    """Swap the module-level singleton for an isolated TerminalService.

    `_process_completion_for_session` reads `terminal_service` from
    `services.terminal_service` at call time, so re-binding that attribute
    is the right seam. monkeypatch restores the original on teardown
    (including on test failure), so no manual restore is needed here.
    """
    svc = TerminalService()
    import services.terminal_service as ts_mod
    monkeypatch.setattr(ts_mod, "terminal_service", svc, raising=True)
    return svc


@pytest.fixture
def disable_rag(monkeypatch):
    """Make sure the doc generator's ChromaDB hook is never reached."""
    import services.documentation_generator as docgen_mod
    monkeypatch.setattr(
        docgen_mod.documentation_generator, "_rag", None, raising=False
    )
    yield


@pytest.fixture
def stub_ai(monkeypatch):
    """Force the deterministic-fallback summary path.

    `_ai_summarize` calls `ai_service.generate_text`. Returning "" makes the
    JSON parse return {} and `_fallback_summary` produce the row's body —
    no provider, no network, no flakiness.

    Note: `services/__init__.py` does `from services.ai_service import
    ai_service`, which rebinds the package attribute to the instance. So
    `import services.ai_service` resolves through the package attribute and
    yields the instance, not the module. We monkeypatch the instance method
    on the singleton via the `documentation_generator` module's already-
    imported `ai_service` name (the actual call site).
    """
    from services.ai_service import ai_service as ai_singleton
    monkeypatch.setattr(
        ai_singleton, "generate_text", AsyncMock(return_value=""),
        raising=True,
    )
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_project_and_issue(
    project_id: str = "proj-e3", issue_id: str = "issue-e3",
    issue_key: str = "CB-9999",
) -> tuple[Project, Issue]:
    import time as _time
    now_ms = int(_time.time() * 1000)
    project = Project(
        id=project_id, name="e3-regression",
        path="/tmp/e3-regression", status="ACTIVE",
        createdAt=now_ms, updatedAt=now_ms,
    )
    issue = Issue(
        id=issue_id, projectId=project_id, key=issue_key,
        sequence=1, title="E3 regression issue", type="TASK",
        status="IN_PROGRESS", priority="MEDIUM",
        updatedAt=datetime.utcnow(),
    )
    return project, issue


def _seed_session(
    svc: TerminalService, *, issue_id: str, issue_key: str,
    session_id: str | None = None,
) -> TerminalSession:
    """Park a COMPLETED session + pending-completion + doc-job in the svc."""
    sid = session_id or f"sess-{issue_id}"
    started = datetime.utcnow()
    completed = started + timedelta(seconds=2)
    session = TerminalSession(
        id=sid,
        issue_id=issue_id,
        issue_key=issue_key,
        issue_title="E3 regression session",
        project_id="proj-e3",
        provider=ExecutionProvider.CLAUDE_CODE,
        status=ExecutionStatus.COMPLETED,
        started_at=started,
        completed_at=completed,
        # None deliberately — keeps `_capture_git_changes` from shelling out.
        project_path=None,
        exit_code=0,
    )
    with svc._sessions_lock:
        svc._sessions[session.id] = session
        svc._sessions_by_issue[session.issue_id] = session.id
        svc._pending_completions[session.id] = True
        svc._pending_doc_jobs[session.id] = {
            "output_snapshot": ["regression-line-1", "regression-line-2"],
            "started_at": started,
            "completed_at": completed,
            "project_path": None,
            "issue_id": session.issue_id,
        }
    return session


async def _drive_completion(sessionmaker, session_id: str) -> None:
    """Run one full pass of the completion loop body for a session.

    Mirrors `process_pending_completions` exactly — claim, commit on success,
    clear the pending flag + doc-job afterwards.
    """
    from app.main import _process_completion_for_session
    import services.terminal_service as ts_mod

    async with sessionmaker() as db:
        claimed = await _process_completion_for_session(db, session_id)
        assert claimed is True, "completion hook did not claim the session"
        await db.commit()

    ts_mod.terminal_service.clear_pending_completion(session_id)
    ts_mod.terminal_service.clear_pending_doc_job(session_id)


# ---------------------------------------------------------------------------
# Scenario (a): toggle OFF → execution → no ExecutionSummary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_autogenerate_off_skips_summary_but_still_completes(
    factory, fresh_terminal_service, disable_rag, stub_ai,
):
    project, issue = _seed_project_and_issue()
    async with factory() as db:
        db.add(project)
        await db.flush()
        db.add(issue)
        await db.flush()

        settings = await get_or_create_settings(db)
        settings.autoGenerate = False
        await db.commit()

    session = _seed_session(
        fresh_terminal_service,
        issue_id=issue.id,
        issue_key=issue.key,
    )

    await _drive_completion(factory, session.id)

    async with factory() as db:
        rows = (await db.execute(select(ExecutionSummary))).scalars().all()
        assert rows == [], (
            f"expected NO ExecutionSummary rows when autoGenerate=False, "
            f"got {[(r.id, r.issueId) for r in rows]}"
        )

        # Primary completion path must still run — autoGenerate gates the
        # secondary doc-gen hook only.
        refreshed = (
            await db.execute(select(Issue).where(Issue.id == issue.id))
        ).scalar_one()
        assert refreshed.status == "COMPLETED_WAITING_QA"


# ---------------------------------------------------------------------------
# Scenario (b): toggle ON → execution → exactly one ExecutionSummary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_autogenerate_on_creates_one_summary(
    factory, fresh_terminal_service, disable_rag, stub_ai,
):
    project, issue = _seed_project_and_issue(
        issue_id="issue-e3-on", issue_key="CB-9998",
    )
    async with factory() as db:
        db.add(project)
        await db.flush()
        db.add(issue)
        await db.flush()

        # Default singleton has autoGenerate=True; create explicitly so
        # the assertion is unambiguous.
        settings = await get_or_create_settings(db)
        settings.autoGenerate = True
        await db.commit()

    session = _seed_session(
        fresh_terminal_service,
        issue_id=issue.id,
        issue_key=issue.key,
        session_id="sess-e3-on",
    )

    await _drive_completion(factory, session.id)

    async with factory() as db:
        rows = (
            await db.execute(
                select(ExecutionSummary)
                .where(ExecutionSummary.issueId == issue.id)
            )
        ).scalars().all()
        assert len(rows) == 1, (
            f"expected exactly 1 ExecutionSummary when autoGenerate=True, "
            f"got {len(rows)}"
        )
        row = rows[0]
        assert row.issueId == issue.id
        assert row.provider == "claude_code"
        # Fallback summary mentions the issue key — sanity-check we got
        # real content, not an empty placeholder.
        assert issue.key in (row.summary or "")

        refreshed = (
            await db.execute(select(Issue).where(Issue.id == issue.id))
        ).scalar_one()
        assert refreshed.status == "COMPLETED_WAITING_QA"


# ---------------------------------------------------------------------------
# Scenario (c): retention purges old ExecutionSummary rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retention_purges_old_rows(factory):
    """retentionDays=1 + 5-day-old rows → all old rows purged.

    Task spec literally says "retentionDays=0" — the public PATCH endpoint
    rejects 0 (Pydantic ge=1), so we use the smallest accepted bound and
    age the rows well past it. This exercises the same SQL DELETE the
    operational retention loop runs every 6h.
    """
    async with factory() as db:
        settings = await get_or_create_settings(db)
        settings.retentionDays = 1
        # Take per-issue cap out of the picture — this scenario is age-only.
        settings.maxPerIssue = 1000
        await db.flush()

        now = datetime.utcnow()
        fresh = now - timedelta(hours=2)             # < 1 day, must survive
        old = now - timedelta(days=5)                # > 1 day, must purge

        for i in range(3):
            db.add(_summary(
                f"old-{i}", "issue-A", old + timedelta(seconds=i),
            ))
        for i in range(2):
            db.add(_summary(
                f"fresh-{i}", "issue-A", fresh + timedelta(seconds=i),
            ))
        await db.flush()

        purged_age, purged_cap = await apply_retention(db)
        await db.commit()

    assert purged_age == 3, f"expected 3 rows purged by age, got {purged_age}"
    assert purged_cap == 0, (
        f"per-issue cap should not fire (only 2 fresh rows ≤ cap=1000), "
        f"got {purged_cap}"
    )

    async with factory() as db:
        remaining = (
            await db.execute(select(ExecutionSummary))
        ).scalars().all()
        assert len(remaining) == 2
        assert {r.id for r in remaining} == {"fresh-0", "fresh-1"}


@pytest.mark.asyncio
async def test_retention_purges_100d_row_with_default_90d_window(factory):
    """CB-2096 acceptance: retentionDays=90, row executedAt = now - 100d → purged.

    Mirrors the literal QA spec verbatim: 100-day-old row, default
    retentionDays=90, fresh control row aged 1d, run `apply_retention`,
    assert old row gone, fresh row survives. This is the spec the
    operations team verifies by hand every release.
    """
    async with factory() as db:
        settings = await get_or_create_settings(db)
        settings.retentionDays = 90
        # Per-issue cap out of the picture — age-only assertion.
        settings.maxPerIssue = 1000
        await db.flush()

        now = datetime.utcnow()
        row_old = _summary(
            "old-100d", "issue-cb2096", now - timedelta(days=100),
        )
        row_fresh = _summary(
            "fresh-1d", "issue-cb2096", now - timedelta(days=1),
        )
        db.add_all([row_old, row_fresh])
        await db.flush()

        purged_age, purged_cap = await apply_retention(db)
        await db.commit()

    assert purged_age == 1, f"expected 1 row purged by age, got {purged_age}"
    assert purged_cap == 0, f"per-issue cap should not fire, got {purged_cap}"

    async with factory() as db:
        remaining = (
            await db.execute(select(ExecutionSummary))
        ).scalars().all()
        ids = {r.id for r in remaining}
        assert ids == {"fresh-1d"}, (
            f"expected only fresh-1d to survive a 90-day retention window, "
            f"got {ids}"
        )


@pytest.mark.asyncio
async def test_per_issue_cap_purges_25_to_20_with_default_cap(factory):
    """CB-2097 literal AC: 25 fresh rows + maxPerIssue=20 → 5 oldest purged."""
    async with factory() as db:
        settings = await get_or_create_settings(db)
        # Long age window so ONLY the per-issue cap fires.
        settings.retentionDays = 10_000
        settings.maxPerIssue = 20
        await db.flush()

        base = datetime.utcnow() - timedelta(hours=1)
        # Newest at i=0 (base + 24min), oldest at i=24 (base) — strictly
        # increasing so order_by(executedAt DESC) is unambiguous.
        for i in range(25):
            db.add(_summary(
                f"r-{i:02d}", "issue-cap-25",
                base + timedelta(minutes=(24 - i)),
            ))
        await db.flush()

        purged_age, purged_cap = await apply_retention(db)
        await db.commit()

    assert purged_age == 0
    assert purged_cap == 5, f"expected 5 oldest purged, got {purged_cap}"

    async with factory() as db:
        rows = (
            await db.execute(
                select(ExecutionSummary)
                .where(ExecutionSummary.issueId == "issue-cap-25")
                .order_by(ExecutionSummary.executedAt.desc())
            )
        ).scalars().all()
        ids = [r.id for r in rows]
        assert len(ids) == 20, f"expected 20 survivors, got {len(ids)}"
        # Newest 20 = r-00 .. r-19 (highest executedAt values)
        assert ids == [f"r-{i:02d}" for i in range(20)], (
            f"expected r-00..r-19 (newest 20) to survive, got {ids}"
        )


@pytest.mark.asyncio
async def test_retention_respects_per_issue_cap(factory):
    """maxPerIssue=2 + 5 fresh rows for one issue → 3 purged by cap."""
    async with factory() as db:
        settings = await get_or_create_settings(db)
        # Long age window so only the per-issue cap fires.
        settings.retentionDays = 10_000
        settings.maxPerIssue = 2
        await db.flush()

        base = datetime.utcnow() - timedelta(hours=1)
        for i in range(5):
            db.add(_summary(
                f"a-{i}", "issue-cap", base + timedelta(seconds=i),
            ))
        # Different issue, untouched by the cap.
        db.add(_summary("b-0", "issue-other", base))
        await db.flush()

        purged_age, purged_cap = await apply_retention(db)
        await db.commit()

    assert purged_age == 0
    assert purged_cap == 3

    async with factory() as db:
        rows = (
            await db.execute(select(ExecutionSummary))
        ).scalars().all()
        per_issue = {}
        for r in rows:
            per_issue[r.issueId] = per_issue.get(r.issueId, 0) + 1
        assert per_issue == {"issue-cap": 2, "issue-other": 1}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summary(id_: str, issue_id: str, executed_at: datetime) -> ExecutionSummary:
    return ExecutionSummary(
        id=id_, issueId=issue_id,
        summary="regression summary", executedAt=executed_at,
        executionTime=1.0, provider="claude_code",
        componentsModified="[]", filesTouched="[]", commitHashes="[]",
    )
