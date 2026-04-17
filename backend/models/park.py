"""
ParkEvent model - records each time a project is parked (all AI stopped).
"""

import uuid

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from models.database import Base


class ParkEvent(Base):
    """Persists a record of a parking action for a project.

    When the user parks a project the frontend stops all AI sessions and
    pipelines, then POSTs the summary to ``/api/park/record``.  This model
    stores that summary so the history is queryable.
    """

    __tablename__ = "park_events"

    id: str = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: str = Column(String, nullable=False, index=True)
    parked_at: DateTime = Column(DateTime, default=func.now())
    # JSON-encoded snapshot of service states at park time
    services_snapshot: str | None = Column(Text, nullable=True)
    ai_sessions_stopped: int = Column(Integer, default=0)
    pipelines_cancelled: int = Column(Integer, default=0)
    # JSON-encoded list of step log entries
    parking_steps_log: str | None = Column(Text, nullable=True)
    # Total wall-clock time the parking sequence took, in milliseconds
    duration_ms: int | None = Column(Integer, nullable=True)
