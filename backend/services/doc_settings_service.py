"""
DocSettings service (CB-2080 / T3.1.1, CB-2083 / T3.1.4).

Provides:
  * `get_or_create_settings(db)` — load the singleton row, creating defaults
    on first access.
  * `apply_retention(db)` — delete ExecutionSummary rows older than
    `retentionDays`, then per-issue cap newest-first to `maxPerIssue`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Tuple

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.doc_settings import DocSettings, SINGLETON_KEY
from models.documentation import ExecutionSummary

logger = logging.getLogger(__name__)


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

    Caller owns the transaction. Logs a single line per non-zero phase
    so operators can see retention activity in the loop.
    """
    settings = await get_or_create_settings(db)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=settings.retentionDays)

    # Phase 1: by age.
    age_result = await db.execute(
        delete(ExecutionSummary)
        .where(ExecutionSummary.executedAt < cutoff)
    )
    purged_by_age = int(age_result.rowcount or 0)

    # Phase 2: per-issue cap. Walk distinct issueIds, delete tail beyond
    # the cap. Uses a windowed query to avoid loading every row in memory.
    issue_rows = await db.execute(
        select(ExecutionSummary.issueId).distinct()
    )
    issue_ids = [r[0] for r in issue_rows.all() if r[0]]
    purged_by_cap = 0
    for issue_id in issue_ids:
        survivors = await db.execute(
            select(ExecutionSummary.id)
            .where(ExecutionSummary.issueId == issue_id)
            .order_by(ExecutionSummary.executedAt.desc())
            .limit(settings.maxPerIssue)
        )
        keep_ids = {row[0] for row in survivors.all()}
        if not keep_ids:
            continue
        cap_result = await db.execute(
            delete(ExecutionSummary)
            .where(ExecutionSummary.issueId == issue_id)
            .where(ExecutionSummary.id.notin_(keep_ids))
        )
        purged_by_cap += int(cap_result.rowcount or 0)

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
