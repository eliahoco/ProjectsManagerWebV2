"""
CB-2080..CB-2083 — DocSettings model + service + endpoints + retention.

Covers:
  * default_row defaults
  * get_or_create_settings creates singleton on first access
  * GET endpoint creates row
  * PATCH endpoint updates fields, rejects out-of-range values
  * apply_retention purges by age + per-issue cap

Uses an isolated on-disk SQLite DB (mirrors the pattern in
test_documentation_api.py) so tests never touch production codeboard.db.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from api.doc_settings import router as doc_settings_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from models.database import Base, get_db  # noqa: E402
from models.doc_settings import DocSettings, SINGLETON_KEY  # noqa: E402
from models.documentation import ExecutionSummary  # noqa: E402
from models.issue import Issue, Project  # noqa: E402
from services.doc_settings_service import (  # noqa: E402
    apply_retention,
    get_or_create_settings,
)


@pytest_asyncio.fixture
async def test_app_and_db():
    tmp_dir = tempfile.mkdtemp(prefix="doc-settings-test-")
    db_path = os.path.join(tmp_dir, "test.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession,
        expire_on_commit=False, autocommit=False, autoflush=False,
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    local_app = FastAPI()
    setup_exception_handlers(local_app)
    local_app.include_router(doc_settings_router, prefix="/api")
    local_app.dependency_overrides[get_db] = _override_get_db

    try:
        yield local_app, factory
    finally:
        await engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def factory(test_app_and_db):
    _, f = test_app_and_db
    yield f


@pytest_asyncio.fixture
async def client(test_app_and_db) -> AsyncGenerator[AsyncClient, None]:
    local_app, _ = test_app_and_db
    transport = ASGITransport(app=local_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---- model ----------------------------------------------------------------

def test_default_row_uses_documented_defaults():
    row = DocSettings.default_row()
    assert row.key == SINGLETON_KEY
    assert row.autoGenerate is True
    assert row.retentionDays == 90
    assert row.maxPerIssue == 20


# ---- service --------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_or_create_settings_creates_singleton(factory):
    async with factory() as db:
        row = await get_or_create_settings(db)
        await db.commit()
        assert row.key == SINGLETON_KEY
        assert row.autoGenerate is True

    async with factory() as db:
        # Second call returns the same row, no duplicate insert.
        row2 = await get_or_create_settings(db)
        assert row2.key == SINGLETON_KEY
        rows = (await db.execute(select(DocSettings))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_apply_retention_purges_by_age(factory):
    async with factory() as db:
        settings = await get_or_create_settings(db)
        settings.retentionDays = 10
        settings.maxPerIssue = 1000
        await db.flush()

        now = datetime.utcnow()
        fresh = now - timedelta(days=1)
        old = now - timedelta(days=20)
        for i, when in enumerate([fresh, fresh, fresh, old, old]):
            db.add(_summary(f"id-{i}", "issue-1", when))
        await db.flush()

        purged_age, purged_cap = await apply_retention(db)
        assert purged_age == 2
        assert purged_cap == 0

        remaining = (await db.execute(select(ExecutionSummary))).scalars().all()
        assert len(remaining) == 3
        await db.commit()


@pytest.mark.asyncio
async def test_apply_retention_caps_per_issue(factory):
    async with factory() as db:
        settings = await get_or_create_settings(db)
        settings.retentionDays = 10_000
        settings.maxPerIssue = 2
        await db.flush()

        base = datetime.utcnow() - timedelta(days=1)
        for i in range(4):
            db.add(_summary(f"a-{i}", "issue-A", base + timedelta(seconds=i)))
        db.add(_summary("b-0", "issue-B", base))
        await db.flush()

        purged_age, purged_cap = await apply_retention(db)
        assert purged_age == 0
        assert purged_cap == 2

        rows = (await db.execute(select(ExecutionSummary))).scalars().all()
        counts = {}
        for r in rows:
            counts[r.issueId] = counts.get(r.issueId, 0) + 1
        assert counts == {"issue-A": 2, "issue-B": 1}
        await db.commit()


@pytest.mark.asyncio
async def test_apply_retention_batches_and_yields(factory, monkeypatch):
    """CB-2123: per-issue walk commits per batch and yields to event loop.

    Drops the batch size to 5, seeds 12 issues × 3 rows with maxPerIssue=1,
    asserts: (a) total purge count is correct (each issue → 2 rows
    purged → 24 rows), (b) `db.commit` was invoked more than once during
    the pass (proves batching, not single-transaction), (c) `asyncio.sleep(0)`
    was awaited at least once between batches (proves event-loop yield).
    """
    import services.doc_settings_service as svc

    monkeypatch.setattr(svc, "_RETENTION_BATCH_SIZE", 5)

    sleep_calls: list[float] = []
    real_sleep = asyncio.sleep

    async def _tracking_sleep(delay: float):
        sleep_calls.append(delay)
        # Honor the requested delay so any stray sleep(N) elsewhere in
        # the event loop during this test isn't silently shortened.
        await real_sleep(delay)

    monkeypatch.setattr(svc.asyncio, "sleep", _tracking_sleep)

    base = datetime.utcnow() - timedelta(days=1)
    async with factory() as db:
        settings = await get_or_create_settings(db)
        settings.retentionDays = 10_000
        settings.maxPerIssue = 1
        await db.flush()
        for issue_idx in range(12):
            for row_idx in range(3):
                db.add(_summary(
                    f"i{issue_idx}-r{row_idx}",
                    f"issue-{issue_idx}",
                    base + timedelta(seconds=issue_idx * 10 + row_idx),
                ))
        await db.commit()

        commit_count_before = 0
        original_commit = db.commit

        async def _counting_commit():
            nonlocal commit_count_before
            commit_count_before += 1
            await original_commit()

        monkeypatch.setattr(db, "commit", _counting_commit)

        purged_age, purged_cap = await svc.apply_retention(db)

    assert purged_age == 0
    assert purged_cap == 12 * 2  # 12 issues × (3 rows - 1 keep) = 24
    # Phase 1 commits once + phase 2 commits floor(12/5)=2 at batch boundaries
    # + 1 final flush for the trailing 2 issues = exactly 4 commits.
    # Tight assertion (>=4 not >=3) so a regression that drops the trailing
    # flush would be caught.
    assert commit_count_before >= 4, f"expected ≥4 commits, got {commit_count_before}"
    assert any(d == 0 for d in sleep_calls), \
        f"expected asyncio.sleep(0) yields, got {sleep_calls}"


def _summary(id_: str, issue_id: str, executed_at: datetime) -> ExecutionSummary:
    return ExecutionSummary(
        id=id_, issueId=issue_id,
        summary="test summary", executedAt=executed_at,
        executionTime=1.0, provider="claude_code",
        componentsModified="[]", filesTouched="[]", commitHashes="[]",
    )


# ---- endpoints ------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_settings_creates_default(client: AsyncClient):
    resp = await client.get("/api/documentation/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == SINGLETON_KEY
    assert body["autoGenerate"] is True
    assert body["retentionDays"] == 90
    assert body["maxPerIssue"] == 20


@pytest.mark.asyncio
async def test_patch_settings_updates_fields(client: AsyncClient):
    await client.get("/api/documentation/settings")
    resp = await client.patch(
        "/api/documentation/settings",
        json={"autoGenerate": False, "retentionDays": 30, "maxPerIssue": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["autoGenerate"] is False
    assert body["retentionDays"] == 30
    assert body["maxPerIssue"] == 10
    resp2 = await client.get("/api/documentation/settings")
    assert resp2.json()["retentionDays"] == 30


@pytest.mark.asyncio
async def test_patch_rejects_out_of_range(client: AsyncClient):
    await client.get("/api/documentation/settings")
    for bad in (
        {"retentionDays": 0},
        {"retentionDays": 99_999},
        {"maxPerIssue": 0},
        {"maxPerIssue": 100_000},
    ):
        resp = await client.patch("/api/documentation/settings", json=bad)
        assert resp.status_code in (400, 422), f"expected 4xx for {bad}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_patch_empty_body_is_noop(client: AsyncClient):
    await client.get("/api/documentation/settings")
    resp = await client.patch("/api/documentation/settings", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["autoGenerate"] is True
    assert body["retentionDays"] == 90


# ---- /summaries endpoint (CB-2087) ----------------------------------------

def _project_and_issue(
    project_id: str, issue_id: str, key: str
) -> tuple[Project, Issue]:
    """Create a minimal Project + Issue pair for join tests."""
    import time as _time

    now_ms = int(_time.time() * 1000)
    proj = Project(
        id=project_id, name=f"proj-{project_id[:6]}",
        path="/tmp/p", status="ACTIVE",
        createdAt=now_ms, updatedAt=now_ms,
    )
    issue = Issue(
        id=issue_id, projectId=project_id, key=key,
        sequence=1, title="test", type="TASK",
        status="DONE", priority="MEDIUM",
        updatedAt=datetime.utcnow(),
    )
    return proj, issue


@pytest.mark.asyncio
async def test_summaries_empty(client: AsyncClient):
    resp = await client.get("/api/documentation/summaries")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_summaries_returns_rows_newest_first(
    client: AsyncClient,
    factory,
):
    base = datetime.utcnow()
    async with factory() as db:
        for i in range(3):
            db.add(_summary(f"s-{i}", "issue-X", base + timedelta(seconds=i)))
        await db.commit()

    resp = await client.get("/api/documentation/summaries")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3
    # Newest first
    executed_ats = [r["executedAt"] for r in rows]
    assert executed_ats == sorted(executed_ats, reverse=True)


@pytest.mark.asyncio
async def test_summaries_includes_issue_key(
    client: AsyncClient,
    factory,
):
    """issueKey from the Issue join is included in the response."""
    proj, issue = _project_and_issue("proj-1", "issue-1", "CB-9999")
    async with factory() as db:
        db.add(proj)
        await db.flush()
        db.add(issue)
        await db.flush()
        db.add(_summary("sum-k1", issue.id, datetime.utcnow()))
        await db.commit()

    resp = await client.get("/api/documentation/summaries")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["issueKey"] == "CB-9999"


@pytest.mark.asyncio
async def test_summaries_limit_param(client: AsyncClient, factory):
    base = datetime.utcnow()
    async with factory() as db:
        for i in range(10):
            db.add(_summary(f"t-{i}", "issue-Y", base + timedelta(seconds=i)))
        await db.commit()

    resp = await client.get("/api/documentation/summaries?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_summaries_limit_exceeds_max_returns_422(client: AsyncClient):
    resp = await client.get("/api/documentation/summaries?limit=999")
    assert resp.status_code == 422
