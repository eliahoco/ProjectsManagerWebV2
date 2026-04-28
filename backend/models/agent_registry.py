"""
SQLAlchemy model for the Agent Registry - tracks available AI agents and their capabilities
"""

import json

from sqlalchemy import (
    Column, String, Integer, DateTime, Text, Index, Boolean
)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.sql import func

from models.database import Base


class JsonList(TypeDecorator):
    """TypeDecorator that transparently serializes Python lists as JSON text in SQLite.

    Prevents ``sqlite3.ProgrammingError: type 'list' is not supported`` when
    raw list values are bound to a text column.
    """

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


class AgentProfile(Base):
    """AgentProfile model - represents a registered AI agent with capabilities and matching rules"""
    __tablename__ = "AgentProfile"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "python-pro", "react-specialist"
    displayName = Column(String, nullable=False)  # e.g., "Python Pro", "React Specialist"
    description = Column(Text, nullable=True)  # What this agent specializes in
    agentPath = Column(String, nullable=False)  # Path to AGENT.md file

    # Matching criteria (stored as JSON arrays via JsonList TypeDecorator)
    capabilities = Column(JsonList, nullable=True)  # e.g., ["python", "fastapi", "sqlalchemy"]
    issueTypeAffinity = Column(JsonList, nullable=True)  # e.g., ["TASK", "BUG"]
    projectPatterns = Column(JsonList, nullable=True)  # e.g., ["*.py", "backend/**"]

    # Source tracking
    # "standalone"            — from ~/.claude/agents/*/AGENT.md
    # "plugin:<plugin-name>"  — from ~/.claude/plugins/cache/<plugin-name>/…/agents/*.md
    source = Column(String, default="standalone", nullable=True)

    # Status and ranking
    isActive = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=50, nullable=False)  # Higher = preferred when multiple agents match

    # Timestamps
    createdAt = Column(DateTime, server_default=func.now(), nullable=False)
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("AgentProfile_name_idx", "name"),
        Index("AgentProfile_isActive_idx", "isActive"),
        Index("AgentProfile_priority_idx", "priority"),
        Index("AgentProfile_source_idx", "source"),
    )
