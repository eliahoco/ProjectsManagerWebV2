"""
SQLAlchemy model for the Agent Registry - tracks available AI agents and their capabilities
"""

from sqlalchemy import (
    Column, String, Integer, DateTime, Text, Index, Boolean
)
from sqlalchemy.sql import func

from models.database import Base


class AgentProfile(Base):
    """AgentProfile model - represents a registered AI agent with capabilities and matching rules"""
    __tablename__ = "AgentProfile"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "python-pro", "react-specialist"
    displayName = Column(String, nullable=False)  # e.g., "Python Pro", "React Specialist"
    description = Column(Text, nullable=True)  # What this agent specializes in
    agentPath = Column(String, nullable=False)  # Path to AGENT.md file

    # Matching criteria (stored as JSON arrays)
    capabilities = Column(Text, nullable=True)  # JSON array, e.g., ["python", "fastapi", "sqlalchemy"]
    issueTypeAffinity = Column(Text, nullable=True)  # JSON array, e.g., ["TASK", "BUG"]
    projectPatterns = Column(Text, nullable=True)  # JSON array, e.g., ["*.py", "backend/**"]

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
    )
