"""
Schema migration and structure tests for database models.

Tests that focus on table creation lifecycle, index verification,
unique constraints, and relationship integrity at the database level.
"""

import pytest
from sqlalchemy import text

from models.database import Base
from models.issue import Issue, Comment, Activity, IssueLink, IssueSequence, Project
from models.qa import QATask, QATaskIssueLink, QASequence, QASettings
from models.documentation import ExecutionSummary, FeatureDocumentation
from models.git import CommitLink, GitSyncState

from tests.schema_test_utils import (
    create_test_engine,
    setup_test_db,
    teardown_test_db,
    get_index_info,
    get_table_info,
)


@pytest.fixture
async def test_engine():
    """Provide a fresh in-memory database for each test."""
    engine = create_test_engine()
    await setup_test_db(engine)
    yield engine
    await teardown_test_db(engine)
    await engine.dispose()


# ============================================
# Table creation lifecycle tests
# ============================================

@pytest.mark.unit
class TestTableCreation:
    """Verify tables can be created and dropped cleanly."""

    async def test_create_all_tables(self):
        """Base.metadata.create_all should create all tables without errors."""
        engine = create_test_engine()
        # Should not raise
        await setup_test_db(engine)
        await engine.dispose()

    async def test_drop_all_tables(self):
        """Base.metadata.drop_all should drop all tables without errors."""
        engine = create_test_engine()
        await setup_test_db(engine)
        # Should not raise
        await teardown_test_db(engine)
        await engine.dispose()

    async def test_create_idempotent(self):
        """Calling create_all twice should not raise errors."""
        engine = create_test_engine()
        await setup_test_db(engine)
        await setup_test_db(engine)  # Second call should be safe
        await engine.dispose()

    async def test_recreate_after_drop(self):
        """Tables should be recreatable after being dropped."""
        engine = create_test_engine()
        await setup_test_db(engine)
        await teardown_test_db(engine)
        await setup_test_db(engine)  # Should work again
        await engine.dispose()


# ============================================
# Index verification tests
# ============================================

@pytest.mark.unit
class TestIssueIndexes:
    """Verify Issue table indexes match expected definitions."""

    async def test_issue_projectid_index(self, test_engine):
        """Issue table should have an index on projectId."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId",) in idx_cols, "Missing index on Issue.projectId"

    async def test_issue_status_index(self, test_engine):
        """Issue table should have an index on status."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("status",) in idx_cols, "Missing index on Issue.status"

    async def test_issue_type_index(self, test_engine):
        """Issue table should have an index on type."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("type",) in idx_cols, "Missing index on Issue.type"

    async def test_issue_parentid_index(self, test_engine):
        """Issue table should have an index on parentId."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("parentId",) in idx_cols, "Missing index on Issue.parentId"

    async def test_issue_key_index(self, test_engine):
        """Issue table should have an index on key."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("key",) in idx_cols, "Missing index on Issue.key"

    async def test_issue_composite_project_status_index(self, test_engine):
        """Issue table should have composite index on (projectId, status)."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "status") in idx_cols, (
            "Missing composite index on Issue(projectId, status)"
        )

    async def test_issue_composite_project_type_index(self, test_engine):
        """Issue table should have composite index on (projectId, type)."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "type") in idx_cols, (
            "Missing composite index on Issue(projectId, type)"
        )

    async def test_issue_composite_project_type_status_index(self, test_engine):
        """Issue table should have composite index on (projectId, type, status)."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "type", "status") in idx_cols, (
            "Missing composite index on Issue(projectId, type, status)"
        )

    async def test_issue_date_indexes(self, test_engine):
        """Issue table should have indexes for date-based filtering."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("createdAt",) in idx_cols, "Missing index on Issue.createdAt"
        assert ("updatedAt",) in idx_cols, "Missing index on Issue.updatedAt"
        assert ("dueDate",) in idx_cols, "Missing index on Issue.dueDate"

    async def test_issue_composite_date_indexes(self, test_engine):
        """Issue table should have composite date indexes with projectId."""
        indexes = await get_index_info(test_engine, "Issue")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "createdAt") in idx_cols, (
            "Missing composite index on Issue(projectId, createdAt)"
        )
        assert ("projectId", "updatedAt") in idx_cols, (
            "Missing composite index on Issue(projectId, updatedAt)"
        )

    async def test_issue_unique_key(self, test_engine):
        """Issue.key should have a unique index."""
        indexes = await get_index_info(test_engine, "Issue")
        key_indexes = [idx for idx in indexes if idx["columns"] == ["key"]]
        assert any(idx["unique"] for idx in key_indexes), (
            "Issue.key should have a unique index"
        )


@pytest.mark.unit
class TestQATaskIndexes:
    """Verify QATask table indexes."""

    async def test_qa_task_projectid_index(self, test_engine):
        """QATask should have an index on projectId."""
        indexes = await get_index_info(test_engine, "QATask")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId",) in idx_cols

    async def test_qa_task_status_index(self, test_engine):
        """QATask should have an index on status."""
        indexes = await get_index_info(test_engine, "QATask")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("status",) in idx_cols

    async def test_qa_task_composite_indexes(self, test_engine):
        """QATask should have composite indexes."""
        indexes = await get_index_info(test_engine, "QATask")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "status") in idx_cols
        assert ("projectId", "lastExecutedAt") in idx_cols

    async def test_qa_task_unique_key(self, test_engine):
        """QATask.key should have a unique index."""
        indexes = await get_index_info(test_engine, "QATask")
        key_indexes = [idx for idx in indexes if idx["columns"] == ["key"]]
        assert any(idx["unique"] for idx in key_indexes)


@pytest.mark.unit
class TestActivityIndexes:
    """Verify Activity table indexes."""

    async def test_activity_issueid_index(self, test_engine):
        """Activity should have an index on issueId."""
        indexes = await get_index_info(test_engine, "Activity")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("issueId",) in idx_cols

    async def test_activity_createdat_index(self, test_engine):
        """Activity should have an index on createdAt for time-range queries."""
        indexes = await get_index_info(test_engine, "Activity")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("createdAt",) in idx_cols

    async def test_activity_composite_index(self, test_engine):
        """Activity should have composite index on (issueId, createdAt)."""
        indexes = await get_index_info(test_engine, "Activity")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("issueId", "createdAt") in idx_cols


@pytest.mark.unit
class TestCommitLinkIndexes:
    """Verify CommitLink table indexes."""

    async def test_commit_link_indexes(self, test_engine):
        """CommitLink should have expected indexes."""
        indexes = await get_index_info(test_engine, "CommitLink")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("issueId",) in idx_cols
        assert ("projectId",) in idx_cols
        assert ("commitHash",) in idx_cols
        assert ("author",) in idx_cols
        assert ("committedAt",) in idx_cols

    async def test_commit_link_composite_indexes(self, test_engine):
        """CommitLink should have composite indexes."""
        indexes = await get_index_info(test_engine, "CommitLink")
        idx_cols = {tuple(idx["columns"]) for idx in indexes}
        assert ("projectId", "author") in idx_cols
        assert ("projectId", "committedAt") in idx_cols

    async def test_commit_link_unique_constraint(self, test_engine):
        """CommitLink should have unique index on (issueId, commitHash)."""
        indexes = await get_index_info(test_engine, "CommitLink")
        unique_indexes = [
            idx for idx in indexes
            if idx["unique"] and set(idx["columns"]) == {"issueId", "commitHash"}
        ]
        assert len(unique_indexes) > 0, (
            "CommitLink should have a unique index on (issueId, commitHash)"
        )


# ============================================
# Unique constraint tests
# ============================================

@pytest.mark.unit
class TestUniqueConstraints:
    """Verify unique constraints are enforced at the database level."""

    async def test_project_name_unique(self, test_engine):
        """Project.name should be unique."""
        columns = await get_table_info(test_engine, "Project")
        indexes = await get_index_info(test_engine, "Project")
        name_indexes = [idx for idx in indexes if idx["columns"] == ["name"]]
        assert any(idx["unique"] for idx in name_indexes), (
            "Project.name should have a unique constraint"
        )

    async def test_issue_key_unique(self, test_engine):
        """Issue.key should be unique."""
        indexes = await get_index_info(test_engine, "Issue")
        key_indexes = [idx for idx in indexes if idx["columns"] == ["key"]]
        assert any(idx["unique"] for idx in key_indexes)

    async def test_qa_task_key_unique(self, test_engine):
        """QATask.key should be unique."""
        indexes = await get_index_info(test_engine, "QATask")
        key_indexes = [idx for idx in indexes if idx["columns"] == ["key"]]
        assert any(idx["unique"] for idx in key_indexes)

    async def test_issue_sequence_projectid_unique(self, test_engine):
        """IssueSequence.projectId should be unique."""
        indexes = await get_index_info(test_engine, "IssueSequence")
        pid_indexes = [idx for idx in indexes if idx["columns"] == ["projectId"]]
        assert any(idx["unique"] for idx in pid_indexes)

    async def test_qa_sequence_projectid_unique(self, test_engine):
        """QASequence.projectId should be unique."""
        indexes = await get_index_info(test_engine, "QASequence")
        pid_indexes = [idx for idx in indexes if idx["columns"] == ["projectId"]]
        assert any(idx["unique"] for idx in pid_indexes)

    async def test_qa_settings_projectid_unique(self, test_engine):
        """QASettings.projectId should be unique."""
        indexes = await get_index_info(test_engine, "QASettings")
        pid_indexes = [idx for idx in indexes if idx["columns"] == ["projectId"]]
        assert any(idx["unique"] for idx in pid_indexes)

    async def test_git_sync_state_projectid_unique(self, test_engine):
        """GitSyncState.projectId should be unique."""
        indexes = await get_index_info(test_engine, "GitSyncState")
        pid_indexes = [idx for idx in indexes if idx["columns"] == ["projectId"]]
        assert any(idx["unique"] for idx in pid_indexes)


# ============================================
# SQLAlchemy model metadata tests
# ============================================

@pytest.mark.unit
class TestModelMetadata:
    """Verify SQLAlchemy model metadata is correctly configured."""

    def test_issue_tablename(self):
        """Issue model should map to 'Issue' table."""
        assert Issue.__tablename__ == "Issue"

    def test_comment_tablename(self):
        """Comment model should map to 'Comment' table."""
        assert Comment.__tablename__ == "Comment"

    def test_activity_tablename(self):
        """Activity model should map to 'Activity' table."""
        assert Activity.__tablename__ == "Activity"

    def test_issue_link_tablename(self):
        """IssueLink model should map to 'IssueLink' table."""
        assert IssueLink.__tablename__ == "IssueLink"

    def test_qa_task_tablename(self):
        """QATask model should map to 'QATask' table."""
        assert QATask.__tablename__ == "QATask"

    def test_qa_task_issue_link_tablename(self):
        """QATaskIssueLink model should map to 'QATaskIssueLink' table."""
        assert QATaskIssueLink.__tablename__ == "QATaskIssueLink"

    def test_execution_summary_tablename(self):
        """ExecutionSummary model should map to 'ExecutionSummary' table."""
        assert ExecutionSummary.__tablename__ == "ExecutionSummary"

    def test_feature_documentation_tablename(self):
        """FeatureDocumentation model should map to 'FeatureDocumentation' table."""
        assert FeatureDocumentation.__tablename__ == "FeatureDocumentation"

    def test_commit_link_tablename(self):
        """CommitLink model should map to 'CommitLink' table."""
        assert CommitLink.__tablename__ == "CommitLink"

    def test_git_sync_state_tablename(self):
        """GitSyncState model should map to 'GitSyncState' table."""
        assert GitSyncState.__tablename__ == "GitSyncState"

    def test_issue_has_relationships(self):
        """Issue model should have expected relationships."""
        mapper = Issue.__mapper__
        rel_names = {r.key for r in mapper.relationships}
        expected = {"parent", "children", "comments", "activities", "qaTaskLinks", "executionSummaries"}
        assert expected.issubset(rel_names), (
            f"Missing relationships: {expected - rel_names}"
        )

    def test_comment_has_issue_relationship(self):
        """Comment model should have issue relationship."""
        mapper = Comment.__mapper__
        rel_names = {r.key for r in mapper.relationships}
        assert "issue" in rel_names

    def test_activity_has_issue_relationship(self):
        """Activity model should have issue relationship."""
        mapper = Activity.__mapper__
        rel_names = {r.key for r in mapper.relationships}
        assert "issue" in rel_names

    def test_qa_task_has_linked_issues(self):
        """QATask model should have linkedIssues relationship."""
        mapper = QATask.__mapper__
        rel_names = {r.key for r in mapper.relationships}
        assert "linkedIssues" in rel_names

    def test_execution_summary_has_issue(self):
        """ExecutionSummary model should have issue relationship."""
        mapper = ExecutionSummary.__mapper__
        rel_names = {r.key for r in mapper.relationships}
        assert "issue" in rel_names
