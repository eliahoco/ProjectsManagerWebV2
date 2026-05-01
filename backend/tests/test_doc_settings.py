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
