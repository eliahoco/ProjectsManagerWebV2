"""
Idempotent backfill script for AutoPilot persistence (CB-1951 E7.2.1).

This script is defensive — there is nothing to backfill from before
CB-1951 because the old in-memory queue state was never persisted. It
exists for one purpose: future migrations or test-data seeding can hook
in here without inventing a fresh script and risking direct DB writes.

Default behaviour (`--dry-run`) prints what WOULD change but does
nothing. Pass `--apply` to actually mutate the DB.

Refuses to overwrite existing rows. If the AutoPilot tables are already
populated, exits cleanly with no changes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

# Allow running from anywhere within the repo
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402

from models.database import AsyncSessionLocal  # noqa: E402
from models.autopilot import (  # noqa: E402
    AutoPilotQueueRecord,
    AutoPilotTaskRecord,
    AutoPilotEvent,
)


async def count_existing() -> dict:
    async with AsyncSessionLocal() as db:
        q = (await db.execute(select(AutoPilotQueueRecord))).scalars().all()
        t = (await db.execute(select(AutoPilotTaskRecord))).scalars().all()
        e = (await db.execute(select(AutoPilotEvent))).scalars().all()
    return {
        "queues": len(q),
        "tasks": len(t),
        "events": len(e),
    }


async def backfill(apply: bool) -> int:
    """Returns the number of rows that would be / were inserted."""
    counts = await count_existing()
    print(f"[backfill] Existing rows: {counts}")

    if any(counts.values()):
        print(
            "[backfill] AutoPilot tables already populated — refusing to "
            "overwrite. (This is the expected outcome on second-run.)"
        )
        return 0

    # No data to seed in the current spec. Future callers can add seed
    # rows here, gated by `apply`. Example skeleton:
    #
    # planned: list[dict] = []  # build seed rows
    # if not apply:
    #     print(f"[backfill] DRY-RUN: would insert {len(planned)} rows")
    #     return len(planned)
    # async with AsyncSessionLocal() as db:
    #     for row in planned: db.add(...)
    #     await db.commit()
    # return len(planned)

    print("[backfill] Nothing to seed for the CB-1951 baseline. Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag the script is a dry-run.",
    )
    args = parser.parse_args()
    inserted = asyncio.run(backfill(apply=args.apply))
    mode = "applied" if args.apply else "dry-run"
    print(f"[backfill] {mode}: {inserted} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
