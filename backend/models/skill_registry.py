"""
SQLAlchemy model for the Skill Registry - tracks available skills and their metadata.

A "skill" is a SKILL.md file (analogous to AGENT.md for agents) that can be sourced
from standalone ~/.claude/skills/ directories or from plugin bundles in
~/.claude/plugins/cache/.
"""

import json
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator
from pydantic import BaseModel, ConfigDict
from typing import List, Optional

from models.database import Base


# ---------------------------------------------------------------------------
# Shared TypeDecorator (mirrored from agent_registry for JSON list columns)
# ---------------------------------------------------------------------------

class JsonList(TypeDecorator):
    """TypeDecorator that transparently serialises Python lists as JSON text in SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Serialize list → JSON string on the way into the DB."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        """Deserialize JSON string → list on the way out of the DB."""
        if value is None:
            return None
        if isinstance(value, list):
            return value
        return json.loads(value)


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class SkillProfile(Base):
    """SkillProfile model — represents a registered skill with metadata parsed from SKILL.md."""

    __tablename__ = "SkillProfile"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)  # e.g. "jonny", "atlas", "skill-creator"
    displayName = Column(String, nullable=False)  # e.g. "Jonny", "Atlas"
    description = Column(Text, nullable=True)  # From frontmatter `description:` field
    skillPath = Column(String, nullable=False)  # Absolute path to SKILL.md

    # Parsed frontmatter fields
    capabilities = Column(JsonList, nullable=True)  # JSON array, from frontmatter `capabilities:`
    contextFork = Column(Boolean, default=False, nullable=False)  # True if `context: fork`
    agentRef = Column(String, nullable=True)  # Value of `agent:` key, e.g. "atlas-indexer"

    # Source tracking
    # "standalone"            — from ~/.claude/skills/*/SKILL.md
    # "plugin:<plugin-name>"  — from ~/.claude/plugins/cache/<plugin-name>/…/skills/*/SKILL.md
    source = Column(String, default="standalone", nullable=False)

    # Status and ranking
    isActive = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=50, nullable=False)

    # Timestamps
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("SkillProfile_name_idx", "name"),
        Index("SkillProfile_isActive_idx", "isActive"),
        Index("SkillProfile_source_idx", "source"),
    )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SkillProfileCreate(BaseModel):
    """Schema for creating a new SkillProfile."""

    name: str
    displayName: Optional[str] = None
    description: Optional[str] = None
    skillPath: str
    capabilities: Optional[List[str]] = None
    contextFork: bool = False
    agentRef: Optional[str] = None
    source: str = "standalone"
    isActive: bool = True
    priority: int = 50


class SkillProfileUpdate(BaseModel):
    """Schema for partially updating a SkillProfile."""

    displayName: Optional[str] = None
    description: Optional[str] = None
    skillPath: Optional[str] = None
    capabilities: Optional[List[str]] = None
    contextFork: Optional[bool] = None
    agentRef: Optional[str] = None
    source: Optional[str] = None
    isActive: Optional[bool] = None
    priority: Optional[int] = None


class SkillProfileRead(BaseModel):
    """Schema for reading a SkillProfile (API response)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    skillPath: str
    capabilities: Optional[List[str]] = None
    contextFork: bool = False
    agentRef: Optional[str] = None
    source: str = "standalone"
    isActive: bool = True
    priority: int = 50
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
