"""
Documentation settings API (CB-2081 / T3.1.2).

Two endpoints under `/api/documentation/settings`:
  * GET  — return current config (creates default row on first call)
  * PATCH — update any subset of fields

Singleton row pattern — there is exactly one DocSettings row keyed
`global`. The service layer (`services.doc_settings_service`) owns the
upsert + transaction-friendly helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    DocSettingsResponse,
    DocSettingsUpdate,
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
    """Update a subset of DocSettings fields. Pydantic enforces bounds."""
    row = await get_or_create_settings(db)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        # No-op patch — return current row without bumping updatedAt.
        return DocSettingsResponse.model_validate(row)

    for field, value in data.items():
        setattr(row, field, value)
    row.updatedAt = datetime.utcnow()

    await db.commit()
    await db.refresh(row)
    logger.info("DocSettings updated: %s", data)
    return DocSettingsResponse.model_validate(row)
