"""
DocSettings — singleton config for documentation pipeline (CB-2080 / T3.1.1).

Controls auto-generation of ExecutionSummaries on AI execution completion,
retention policy for old summaries, and the per-issue cap. One row, fixed
primary key (`SINGLETON_KEY`); GET creates the default row if missing.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from models.database import Base


SINGLETON_KEY = "global"


# CB-2730 (CB-2377 follow-up): tz-aware UTC. Same naive-column round-trip as
# `models.documentation._utc_now` — JSON serializer re-asserts UTC + `Z` suffix.
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocSettings(Base):
    """Documentation pipeline configuration. Singleton (key='global')."""
    __tablename__ = "DocSettings"

    key = Column(String, primary_key=True, default=SINGLETON_KEY)
    autoGenerate = Column(Boolean, nullable=False, default=True)
    retentionDays = Column(Integer, nullable=False, default=90)
    maxPerIssue = Column(Integer, nullable=False, default=20)

    createdAt = Column(
        DateTime,
        default=_utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updatedAt = Column(
        DateTime,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    @classmethod
    def default_row(cls) -> "DocSettings":
        return cls(
            key=SINGLETON_KEY,
            autoGenerate=True,
            retentionDays=90,
            maxPerIssue=20,
        )
