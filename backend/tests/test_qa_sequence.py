"""Tests for the self-healing QA key sequence (CB-1853 regression fix).

The bug: `QASequence.lastNumber` could drift below `max(QATask.sequence)` for a
project, causing `get_next_qa_key` to return a duplicate key and trigger a
UNIQUE constraint failure on insert.

These tests exercise the reconciliation path added to `get_next_qa_key` so that
generation stays correct even when the counter starts out behind reality.
"""

from __future__ import annotations

import uuid
import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.database import Base
from models.qa import QATask, QASequence
from api.qa import get_next_qa_key


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


async def _seed_task(session: AsyncSession, project_id: str, sequence: int) -> None:
    session.add(
        QATask(
            id=str(uuid.uuid4()),
            projectId=project_id,
            key=f"QA-{sequence}",
            sequence=sequence,
            title=f"seeded test {sequence}",
            scenario="",
            expectedResult="",
            status="NOT_DONE",
            type="MANUAL",
            priority="MEDIUM",
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_first_call_creates_sequence_at_1(session: AsyncSession) -> None:
    key, n = await get_next_qa_key(session, "proj-a")
    assert (key, n) == ("QA-1", 1)


@pytest.mark.asyncio
async def test_drift_below_max_self_heals(session: AsyncSession) -> None:
    """QASequence.lastNumber=2 but QATasks already exist up to QA-5 — next key must be QA-6."""
    project_id = "proj-drift"
    for seq in (1, 2, 3, 4, 5):
        await _seed_task(session, project_id, seq)
    session.add(
        QASequence(
            id=str(uuid.uuid4()),
            projectId=project_id,
            prefix="QA",
            lastNumber=2,
        )
    )
    await session.flush()

    key, n = await get_next_qa_key(session, project_id)
    assert key == "QA-6"
    assert n == 6


@pytest.mark.asyncio
async def test_sequential_generation_is_monotonic(session: AsyncSession) -> None:
    keys = []
    for _ in range(5):
        k, _ = await get_next_qa_key(session, "proj-b")
        keys.append(k)
    assert keys == ["QA-1", "QA-2", "QA-3", "QA-4", "QA-5"]


@pytest.mark.asyncio
async def test_no_commit_inside_helper(session: AsyncSession) -> None:
    """The helper must NOT commit mid-loop, so callers can roll back atomically."""
    project_id = "proj-rollback"
    await get_next_qa_key(session, project_id)
    await session.rollback()

    fresh_sessionmaker = async_sessionmaker(session.bind, expire_on_commit=False)
    async with fresh_sessionmaker() as s2:
        # After rollback, no sequence row should persist.
        from sqlalchemy import select
        res = await s2.execute(
            select(QASequence).where(QASequence.projectId == project_id)
        )
        assert res.scalar_one_or_none() is None
