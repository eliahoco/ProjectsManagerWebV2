"""
CB-2739 — Backfill: reset crash-recovered failed tasks back to pending.

Before CB-2738, ``rehydrate_from_db`` marked tasks that were RUNNING at crash
time as ``status='failed'`` with ``failureReason='backend_crash_recovery'``.
This caused ``on_fail: CONTINUE_MARK_FAILED`` queues to skip those tasks on
resume instead of re-running them.

This script is idempotent: it finds all AutoPilotTaskRecord rows where
  status = 'failed' AND failureReason = 'backend_crash_recovery'
and resets them to:
  status = 'pending', failureReason = NULL, sessionId = NULL, startedAt = NULL

Run once after deploying the CB-2738 fix.

Usage:
    cd backend/
    source venv/bin/activate
    python scripts/backfill_crash_to_pending.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os

# Ensure the backend package root is on sys.path so imports work when the
# script is run from the project root or the backend/ directory.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_root = os.path.dirname(_script_dir)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB path — mirrors the setting in backend/app/config.py
# ---------------------------------------------------------------------------

# The backend DATABASE_URL defaults to the frontend Prisma SQLite file.
# Match backend/app/config.py default.
_DEFAULT_DB_PATH = os.path.join(
    _backend_root, "..", "frontend", "prisma", "dev.db"
)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{os.path.abspath(_DEFAULT_DB_PATH)}",
)


async def backfill() -> int:
    """Reset all crash-recovery failed tasks to pending.

    Returns:
        Number of rows updated.
    """
    from models.autopilot import AutoPilotTaskRecord  # noqa: PLC0415

    engine = create_async_engine(DATABASE_URL, echo=False)
    Sf = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with Sf() as session:
            # Find candidate rows first so we can report them.
            result = await session.execute(
                select(AutoPilotTaskRecord)
                .where(AutoPilotTaskRecord.status == "failed")
                .where(AutoPilotTaskRecord.failureReason == "backend_crash_recovery")
            )
            rows = list(result.scalars().all())

            if not rows:
                logger.info(
                    "Backfill CB-2739: no rows match "
                    "(status='failed' AND failureReason='backend_crash_recovery'). "
                    "Nothing to do."
                )
                return 0

            logger.info(
                "Backfill CB-2739: found %d task(s) to reset. IDs: %s",
                len(rows),
                [r.id for r in rows],
            )

            # Reset each row — do this in a single UPDATE for atomicity.
            await session.execute(
                update(AutoPilotTaskRecord)
                .where(AutoPilotTaskRecord.status == "failed")
                .where(AutoPilotTaskRecord.failureReason == "backend_crash_recovery")
                .values(
                    status="pending",
                    failureReason=None,
                    sessionId=None,
                    startedAt=None,
                )
            )
            await session.commit()

            logger.info(
                "Backfill CB-2739: reset %d task(s) to status='pending'. "
                "A backend restart is not a task failure.",
                len(rows),
            )
            return len(rows)

    finally:
        await engine.dispose()


async def verify() -> None:
    """Verify no rows remain with the old crash-recovery failed pattern."""
    from models.autopilot import AutoPilotTaskRecord  # noqa: PLC0415

    engine = create_async_engine(DATABASE_URL, echo=False)
    Sf = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with Sf() as session:
            result = await session.execute(
                select(AutoPilotTaskRecord)
                .where(AutoPilotTaskRecord.status == "failed")
                .where(AutoPilotTaskRecord.failureReason == "backend_crash_recovery")
            )
            remaining = list(result.scalars().all())

        if remaining:
            logger.error(
                "Verify CB-2739: %d row(s) still have status='failed' AND "
                "failureReason='backend_crash_recovery'. IDs: %s",
                len(remaining),
                [r.id for r in remaining],
            )
            sys.exit(1)
        else:
            logger.info(
                "Verify CB-2739: PASS — zero rows match the stale crash-recovery "
                "pattern. Backfill complete."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logger.info("Starting CB-2739 backfill against DB: %s", DATABASE_URL)
    updated = asyncio.run(backfill())
    asyncio.run(verify())
    logger.info(
        "CB-2739 backfill finished. %d row(s) updated. Exiting.", updated
    )
