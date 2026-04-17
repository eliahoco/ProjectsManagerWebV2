"""
Park API - Records parking events when a project's AI activity is stopped.

A "park" is the action of gracefully stopping all running AI sessions and
pipelines for a project.  The frontend orchestrates the stop sequence and
then calls POST /api/park/record to persist the event for auditing.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.park import ParkEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/park")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ParkRecordRequest(BaseModel):
    """Request body for recording a park event."""

    project_id: str = Field(..., min_length=1, max_length=128)
    ai_sessions_stopped: int = Field(0, ge=0)
    pipelines_cancelled: int = Field(0, ge=0)
    services_snapshot: Optional[Dict[str, Any]] = None
    parking_steps_log: Optional[List[Dict[str, Any]]] = None
    duration_ms: Optional[int] = Field(None, ge=0)


class ParkRecordResponse(BaseModel):
    """Response after a park event is persisted."""

    success: bool
    event_id: str
    project_id: str
    parked_at: str
    ai_sessions_stopped: int
    pipelines_cancelled: int
    duration_ms: Optional[int]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/record", response_model=ParkRecordResponse, status_code=201)
async def record_park_event(
    request: ParkRecordRequest,
    db: AsyncSession = Depends(get_db),
) -> ParkRecordResponse:
    """Record a parking event for a project.

    Called by the frontend after it has stopped all AI sessions and pipelines.
    Persists a ``ParkEvent`` row so the parking history is queryable.
    """
    now = datetime.utcnow()

    event = ParkEvent(
        id=str(uuid.uuid4()),
        project_id=request.project_id,
        parked_at=now,
        services_snapshot=(
            json.dumps(request.services_snapshot)
            if request.services_snapshot is not None
            else None
        ),
        ai_sessions_stopped=request.ai_sessions_stopped,
        pipelines_cancelled=request.pipelines_cancelled,
        parking_steps_log=(
            json.dumps(request.parking_steps_log)
            if request.parking_steps_log is not None
            else None
        ),
        duration_ms=request.duration_ms,
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    logger.info(
        "Park event recorded for project %s: sessions=%d, pipelines=%d, duration=%sms",
        request.project_id,
        request.ai_sessions_stopped,
        request.pipelines_cancelled,
        request.duration_ms,
    )

    return ParkRecordResponse(
        success=True,
        event_id=event.id,
        project_id=event.project_id,
        parked_at=event.parked_at.isoformat(),
        ai_sessions_stopped=event.ai_sessions_stopped,
        pipelines_cancelled=event.pipelines_cancelled,
        duration_ms=event.duration_ms,
    )
