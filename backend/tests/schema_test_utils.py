"""
Test utilities for database schema testing.

Provides an isolated in-memory SQLite database for schema tests,
avoiding any dependency on the production database.
"""

import asyncio
from typing import AsyncGenerator

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models.database import Base
# Import all models so metadata is populated
from models.issue import Issue, Comment, Activity, IssueLink, IssueSequence, Project
from models.qa import QATask, QATaskIssueLink, QASequence, QASettings
from models.documentation import ExecutionSummary, FeatureDocumentation
from models.git import CommitLink, GitSyncState


def create_test_engine() -> AsyncEngine:
    """Create an async in-memory SQLite engine for testing.

    Enables SQLite foreign key support via connection event listener,
    which is required for ON DELETE CASCADE / SET NULL to work.
    """
    from sqlalchemy import event

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


async def setup_test_db(engine: AsyncEngine) -> None:
    """Create all tables in the test database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def teardown_test_db(engine: AsyncEngine) -> None:
    """Drop all tables in the test database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def create_test_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the test engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def get_table_info(engine: AsyncEngine, table_name: str) -> dict:
    """Get column info for a table using SQLite pragma."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA table_info('{table_name}')"))
        columns = result.fetchall()
        return {
            row[1]: {
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": bool(row[3]),
                "default": row[4],
                "pk": bool(row[5]),
            }
            for row in columns
        }


async def get_index_info(engine: AsyncEngine, table_name: str) -> list[dict]:
    """Get index info for a table using SQLite pragma."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA index_list('{table_name}')"))
        indexes = []
        for row in result.fetchall():
            idx_name = row[1]
            idx_unique = bool(row[2])
            # Get columns in this index
            col_result = await conn.execute(text(f"PRAGMA index_info('{idx_name}')"))
            cols = [r[2] for r in col_result.fetchall()]
            indexes.append({
                "name": idx_name,
                "unique": idx_unique,
                "columns": cols,
            })
        return indexes


async def get_foreign_key_info(engine: AsyncEngine, table_name: str) -> list[dict]:
    """Get foreign key info for a table."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA foreign_key_list('{table_name}')"))
        return [
            {
                "id": row[0],
                "table": row[2],
                "from": row[3],
                "to": row[4],
                "on_update": row[5],
                "on_delete": row[6],
            }
            for row in result.fetchall()
        ]


# ============================================
# Sample data factories
# ============================================

def make_project(
    id: str = "test-project-1",
    name: str = "Test Project",
    path: str = "/test/project",
    status: str = "ACTIVE",
    created_at_ms: int = 1700000000000,
    updated_at_ms: int = 1700000000000,
) -> Project:
    """Create a sample Project instance."""
    return Project(
        id=id,
        name=name,
        path=path,
        status=status,
        createdAt=created_at_ms,
        updatedAt=updated_at_ms,
    )


def make_issue(
    id: str = "test-issue-1",
    project_id: str = "test-project-1",
    key: str = "CB-1",
    sequence: int = 1,
    title: str = "Test Issue",
    description: str = "A test issue",
    issue_type: str = "TASK",
    status: str = "BACKLOG",
    priority: str = "MEDIUM",
    **kwargs,
) -> Issue:
    """Create a sample Issue instance."""
    return Issue(
        id=id,
        projectId=project_id,
        key=key,
        sequence=sequence,
        title=title,
        description=description,
        type=issue_type,
        status=status,
        priority=priority,
        **kwargs,
    )


def make_comment(
    id: str = "test-comment-1",
    issue_id: str = "test-issue-1",
    author: str = "test-user",
    content: str = "Test comment content",
) -> Comment:
    """Create a sample Comment instance."""
    return Comment(id=id, issueId=issue_id, author=author, content=content)


def make_activity(
    id: str = "test-activity-1",
    issue_id: str = "test-issue-1",
    actor: str = "test-user",
    action: str = "CREATED",
    field: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> Activity:
    """Create a sample Activity instance."""
    return Activity(
        id=id,
        issueId=issue_id,
        actor=actor,
        action=action,
        field=field,
        oldValue=old_value,
        newValue=new_value,
    )


def make_qa_task(
    id: str = "test-qa-1",
    project_id: str = "test-project-1",
    key: str = "QA-001",
    sequence: int = 1,
    title: str = "Test QA Task",
    scenario: str = "1. Open app\n2. Click button\n3. Verify result",
    expected_result: str = "Button click succeeds",
    status: str = "NOT_DONE",
    qa_type: str = "AUTOMATED",
    priority: str = "MEDIUM",
    **kwargs,
) -> QATask:
    """Create a sample QATask instance."""
    return QATask(
        id=id,
        projectId=project_id,
        key=key,
        sequence=sequence,
        title=title,
        scenario=scenario,
        expectedResult=expected_result,
        status=status,
        type=qa_type,
        priority=priority,
        **kwargs,
    )


# ============================================
# All expected table names
# ============================================

ALL_TABLES = [
    "Project",
    "Port",
    "PortRange",
    "Session",
    "Setting",
    "Issue",
    "Comment",
    "Activity",
    "IssueLink",
    "IssueSequence",
    "QATask",
    "QATaskIssueLink",
    "QASequence",
    "QASettings",
    "ExecutionSummary",
    "FeatureDocumentation",
    "CommitLink",
    "GitSyncState",
]

# Tables managed by SQLAlchemy models (subset created by Base.metadata.create_all)
SQLALCHEMY_MANAGED_TABLES = [
    "Project",
    "Issue",
    "Comment",
    "Activity",
    "IssueLink",
    "IssueSequence",
    "QATask",
    "QATaskIssueLink",
    "QASequence",
    "QASettings",
    "ExecutionSummary",
    "FeatureDocumentation",
    "CommitLink",
    "GitSyncState",
]
