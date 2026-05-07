"""
DocSettings service (CB-2080 / T3.1.1, CB-2083 / T3.1.4).

Provides:
  * `get_or_create_settings(db)` — load the singleton row, creating defaults
    on first access.
  * `apply_retention(db)` — delete ExecutionSummary rows older than
    `retentionDays`, then per-issue cap newest-first to `maxPerIssue`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Tuple

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.doc_settings import DocSettings, SINGLETON_KEY
from models.documentation import ExecutionSummary

logger = logging.getLogger(__name__)

# CB-2123 (M2): commit phase-2 work in slices of this many issues so a
# retention pass on a 50k-issue DB does not hold a single SQLite write
# transaction (and the disk lock with it) for the entire scan. Empirically
# 100 issues = ~200 small statements per batch — short enough to release
# the lock between batches, large enough to avoid commit overhead
# dominating the scan.
_RETENTION_BATCH_SIZE = 100


async def get_or_create_settings(db: AsyncSession) -> DocSettings:
    """Return the singleton DocSettings row, inserting defaults if missing.

    Caller owns the transaction. This function calls `db.flush()` so the new
    row is queryable immediately, but never commits.
    """
    result = await db.execute(
        select(DocSettings).where(DocSettings.key == SINGLETON_KEY)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    row = DocSettings.default_row()
    db.add(row)
    await db.flush()
    return row


async def apply_retention(db: AsyncSession) -> Tuple[int, int]:
    """Apply retention policy. Returns (purged_by_age, purged_by_per_issue_cap).

    Two-phase pass:
      1. Delete every ExecutionSummary with `executedAt` older than
         `retentionDays` days ago.
      2. Per-issue: keep newest `maxPerIssue` rows (by executedAt DESC),
         delete the rest.

    CB-2123 (M2): the per-issue walk commits every `_RETENTION_BATCH_SIZE`
    issues and yields to the event loop so a retention pass on a large DB
    does not hold the SQLite write lock for its full duration. This means
    the function commits internally — caller's transaction is split into
    multiple committed slices. A failure mid-pass leaves earlier batches
    persisted (acceptable: retention is idempotent, and partial cleanup
    beats fully blocking the API on a disk lock). Caller may still issue
    a final `db.commit()`; on a clean-pass it's a no-op.

    WARNING: this function commits internally. Do NOT call inside an
    explicit `async with db.begin():` block — the inner commit will
    surprise the outer transaction manager.

    Logs a single line per non-zero phase so operators can see retention
    activity in the loop.
    """
    settings = await get_or_create_settings(db)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=settings.retentionDays)

    # Phase 1: by age. Single statement; commit immediately so the write
    # lock for phase 1 is released before phase 2's longer walk begins.
    age_result = await db.execute(
        delete(ExecutionSummary)
        .where(ExecutionSummary.executedAt < cutoff)
    )
    purged_by_age = int(age_result.rowcount or 0)
    await db.commit()
    await asyncio.sleep(0)

    # Phase 2: per-issue cap. Walk distinct issueIds, delete every row older
    # than the maxPerIssue-th newest. CB-2122 (M1) / CB-2124 (H2): pull the
    # `executedAt` of the boundary row only, then delete everything strictly
    # older than that timestamp — uses a single bound parameter instead of
    # an N-element `NOT IN (...)` list, so we cannot trip
    # SQLITE_MAX_VARIABLE_NUMBER even when maxPerIssue is at the upper
    # bound (1000) on legacy SQLite builds (default 999 vars).
    #
    # CB-2123 (M2): commit + yield every `_RETENTION_BATCH_SIZE` issues so
    # a 50k-issue scan releases the SQLite write lock periodically and lets
    # interleaved API requests make progress.
    issue_rows = await db.execute(
        select(ExecutionSummary.issueId).distinct()
    )
    issue_ids = [r[0] for r in issue_rows.all() if r[0]]
    purged_by_cap = 0
    pending_in_batch = 0
    for issue_id in issue_ids:
        boundary = await db.execute(
            select(ExecutionSummary.executedAt)
            .where(ExecutionSummary.issueId == issue_id)
            .order_by(ExecutionSummary.executedAt.desc())
            .limit(1)
            .offset(settings.maxPerIssue)
        )
        oldest_keep = boundary.scalar_one_or_none()
        if oldest_keep is None:
            # Fewer rows than the cap — nothing to purge for this issue.
            # Still count toward the batch budget: the boundary SELECT
            # already hit the lock, so we want to yield by issue count
            # not by delete count.
            pending_in_batch += 1
        else:
            cap_result = await db.execute(
                delete(ExecutionSummary)
                .where(ExecutionSummary.issueId == issue_id)
                .where(ExecutionSummary.executedAt <= oldest_keep)
            )
            purged_by_cap += int(cap_result.rowcount or 0)
            pending_in_batch += 1

        if pending_in_batch >= _RETENTION_BATCH_SIZE:
            await db.commit()
            await asyncio.sleep(0)
            pending_in_batch = 0

    if pending_in_batch:
        await db.commit()
        await asyncio.sleep(0)

    if purged_by_age:
        logger.info(
            "DocSettings retention: purged %d ExecutionSummary rows older than %d days",
            purged_by_age, settings.retentionDays,
        )
    if purged_by_cap:
        logger.info(
            "DocSettings retention: purged %d ExecutionSummary rows beyond per-issue cap (%d)",
            purged_by_cap, settings.maxPerIssue,
        )
    return purged_by_age, purged_by_cap
