"""
Documentation settings API (CB-2081 / T3.1.2).

Endpoints under `/api/documentation/settings`:
  * GET   — return current config (creates default row on first call)
  * PATCH — update any subset of fields

Endpoint under `/api/documentation/summaries`:
  * GET   — latest ExecutionSummaries across all issues (CB-2087)

Singleton row pattern — there is exactly one DocSettings row keyed
`global`. The service layer (`services.doc_settings_service`) owns the
upsert + transaction-friendly helpers.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    DocSettingsResponse,
    DocSettingsUpdate,
    ExecutionSummary,
    ExecutionSummaryWithKeyResponse,
    Issue,
    get_db,
)
from services.doc_settings_service import get_or_create_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/documentation/settings",
    response_model=DocSettingsResponse,
)
async def read_doc_settings(
    db: AsyncSession = Depends(get_db),
) -> DocSettingsResponse:
    """Return the singleton DocSettings row, creating defaults if absent."""
    row = await get_or_create_settings(db)
    # The service may have inserted — commit once at the endpoint boundary.
    await db.commit()
    await db.refresh(row)
    return DocSettingsResponse.model_validate(row)


@router.patch(
    "/documentation/settings",
    response_model=DocSettingsResponse,
)
async def update_doc_settings(
    payload: DocSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> DocSettingsResponse:
    """Update a subset of DocSettings fields. Pydantic enforces bounds.

    CB-2125 (H3): the model's `onupdate=_utc_now` already maintains
    `updatedAt` on every flush that observes a changed field. We deliberately
    do NOT set `row.updatedAt` manually here because (a) it duplicates the
    onupdate trigger and (b) the empty-payload early-return below would be
    fragile if a future caller adds a side-effecting branch above it. By
    relying on onupdate exclusively, an empty PATCH never touches the row
    and `updatedAt` stays stable.
    """
    row = await get_or_create_settings(db)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        # No-op patch — commit any pending insert from get_or_create_settings,
        # but no field was changed so onupdate does not fire.
        await db.commit()
        await db.refresh(row)
        return DocSettingsResponse.model_validate(row)

    for field, value in data.items():
        setattr(row, field, value)

    await db.commit()
    await db.refresh(row)
    logger.info("DocSettings updated: %s", data)
    return DocSettingsResponse.model_validate(row)


@router.get(
    "/documentation/summaries",
    response_model=List[ExecutionSummaryWithKeyResponse],
    summary="Recent execution summaries across all issues (CB-2087)",
)
async def list_recent_summaries(
    limit: int = Query(default=20, ge=1, le=100, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> List[ExecutionSummaryWithKeyResponse]:
    """Return the most recent ExecutionSummary rows across ALL issues,
    ordered by executedAt DESC, enriched with the parent issue key.
    Single-tenant: no project filter needed.
    """
    result = await db.execute(
        select(ExecutionSummary, Issue.key)
        .outerjoin(Issue, ExecutionSummary.issueId == Issue.id)
        .order_by(ExecutionSummary.executedAt.desc())
        .limit(limit)
    )
    rows = result.all()
    out: List[ExecutionSummaryWithKeyResponse] = []
    for summary, issue_key in rows:
        item = ExecutionSummaryWithKeyResponse.model_validate(summary)
        item.issueKey = issue_key
        out.append(item)
    return out
