"""
Schema validation tests for database models.

Validates that SQLAlchemy models match the expected Prisma schema structure,
ensuring parity between the frontend ORM (Prisma) and the backend ORM (SQLAlchemy).
"""

import pytest
from sqlalchemy import inspect

from models.database import Base
from models.issue import Issue, Comment, Activity, IssueLink, IssueSequence, Project
from models.qa import QATask, QATaskIssueLink, QASequence, QASettings
from models.documentation import ExecutionSummary, FeatureDocumentation
from models.git import CommitLink, GitSyncState

from tests.schema_test_utils import (
    create_test_engine,
    setup_test_db,
    teardown_test_db,
    get_table_info,
    get_index_info,
    get_foreign_key_info,
    SQLALCHEMY_MANAGED_TABLES,
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
# Table existence tests
# ============================================

@pytest.mark.unit
class TestTableExistence:
    """Verify all expected tables are created by SQLAlchemy models."""

    async def test_all_managed_tables_exist(self, test_engine):
        """All SQLAlchemy-managed tables should be created."""
        async with test_engine.connect() as conn:
            def _get_table_names(connection):
                insp = inspect(connection)
                return insp.get_table_names()
            table_names = await conn.run_sync(_get_table_names)

        for table in SQLALCHEMY_MANAGED_TABLES:
            assert table in table_names, f"Table '{table}' not found in database"

    async def test_no_unexpected_tables(self, test_engine):
        """Only expected tables should be created."""
        async with test_engine.connect() as conn:
            def _get_table_names(connection):
                insp = inspect(connection)
                return insp.get_table_names()
            table_names = await conn.run_sync(_get_table_names)

        for table in table_names:
            assert table in SQLALCHEMY_MANAGED_TABLES, (
                f"Unexpected table '{table}' found in database"
            )


# ============================================
# Issue table schema validation
# ============================================

@pytest.mark.unit
class TestIssueSchema:
    """Validate the Issue table schema matches Prisma definition."""

    EXPECTED_COLUMNS = {
        "id": {"notnull": False, "pk": True},  # SQLite PKs show notnull=False
        "projectId": {"notnull": True},
        "key": {"notnull": True},
        "sequence": {"notnull": True},
        "title": {"notnull": True},
        "description": {"notnull": False},
        "type": {"notnull": True},
        "status": {"notnull": True},
        "priority": {"notnull": True},
        "parentId": {"notnull": False},
        "assignee": {"notnull": False},
        "reporter": {"notnull": False},
        "storyPoints": {"notnull": False},
        "estimate": {"notnull": False},
        "timeSpent": {"notnull": False},
        "dueDate": {"notnull": False},
        "startedAt": {"notnull": False},
        "completedAt": {"notnull": False},
        "createdAt": {"notnull": True},
        "updatedAt": {"notnull": True},
        "labels": {"notnull": False},
        "breakdownBatchId": {"notnull": False},
        "implementationSummary": {"notnull": False},
        "technicalApproach": {"notnull": False},
        "documentationPath": {"notnull": False},
        "estimatedHours": {"notnull": False},
        "actualHours": {"notnull": False},
        "complexity": {"notnull": False},
        "aiContext": {"notnull": False},
    }

    async def test_issue_table_columns(self, test_engine):
        """Issue table should have all expected columns."""
        columns = await get_table_info(test_engine, "Issue")
        for col_name in self.EXPECTED_COLUMNS:
            assert col_name in columns, f"Column '{col_name}' missing from Issue table"

    async def test_issue_column_nullability(self, test_engine):
        """Issue columns should have correct nullability constraints."""
        columns = await get_table_info(test_engine, "Issue")
        for col_name, expected in self.EXPECTED_COLUMNS.items():
            if col_name in columns and "notnull" in expected and not expected.get("pk"):
                assert columns[col_name]["notnull"] == expected["notnull"], (
                    f"Issue.{col_name} notnull mismatch: "
                    f"expected {expected['notnull']}, got {columns[col_name]['notnull']}"
                )

    async def test_issue_primary_key(self, test_engine):
        """Issue table should have 'id' as primary key."""
        columns = await get_table_info(test_engine, "Issue")
        assert columns["id"]["pk"], "Issue.id should be the primary key"

    async def test_issue_no_extra_columns(self, test_engine):
        """Issue table should not have unexpected columns."""
        columns = await get_table_info(test_engine, "Issue")
        for col_name in columns:
            assert col_name in self.EXPECTED_COLUMNS, (
                f"Unexpected column '{col_name}' in Issue table"
            )

    async def test_issue_foreign_keys(self, test_engine):
        """Issue table should have correct foreign keys."""
        fks = await get_foreign_key_info(test_engine, "Issue")
        fk_map = {fk["from"]: fk for fk in fks}

        assert "projectId" in fk_map, "Issue.projectId should be a foreign key"
        assert fk_map["projectId"]["table"] == "Project"
        assert fk_map["projectId"]["on_delete"] == "CASCADE"

        assert "parentId" in fk_map, "Issue.parentId should be a foreign key"
        assert fk_map["parentId"]["table"] == "Issue"
        assert fk_map["parentId"]["on_delete"] == "SET NULL"


# ============================================
# Comment table schema validation
# ============================================

@pytest.mark.unit
class TestCommentSchema:
    """Validate the Comment table schema."""

    async def test_comment_columns(self, test_engine):
        """Comment table should have all expected columns."""
        columns = await get_table_info(test_engine, "Comment")
        expected = ["id", "issueId", "author", "content", "createdAt", "updatedAt"]
        for col in expected:
            assert col in columns, f"Column '{col}' missing from Comment table"

    async def test_comment_foreign_key(self, test_engine):
        """Comment.issueId should reference Issue with CASCADE delete."""
        fks = await get_foreign_key_info(test_engine, "Comment")
        fk_map = {fk["from"]: fk for fk in fks}
        assert "issueId" in fk_map
        assert fk_map["issueId"]["table"] == "Issue"
        assert fk_map["issueId"]["on_delete"] == "CASCADE"

    async def test_comment_required_fields(self, test_engine):
        """Comment author and content should be required."""
        columns = await get_table_info(test_engine, "Comment")
        assert columns["author"]["notnull"], "Comment.author should be NOT NULL"
        assert columns["content"]["notnull"], "Comment.content should be NOT NULL"


# ============================================
# Activity table schema validation
# ============================================

@pytest.mark.unit
class TestActivitySchema:
    """Validate the Activity table schema."""

    async def test_activity_columns(self, test_engine):
        """Activity table should have all expected columns."""
        columns = await get_table_info(test_engine, "Activity")
        expected = ["id", "issueId", "actor", "action", "field", "oldValue", "newValue", "createdAt"]
        for col in expected:
            assert col in columns, f"Column '{col}' missing from Activity table"

    async def test_activity_nullable_fields(self, test_engine):
        """Activity field, oldValue, newValue should be nullable."""
        columns = await get_table_info(test_engine, "Activity")
        assert not columns["field"]["notnull"], "Activity.field should be nullable"
        assert not columns["oldValue"]["notnull"], "Activity.oldValue should be nullable"
        assert not columns["newValue"]["notnull"], "Activity.newValue should be nullable"

    async def test_activity_required_fields(self, test_engine):
        """Activity actor and action should be required."""
        columns = await get_table_info(test_engine, "Activity")
        assert columns["actor"]["notnull"], "Activity.actor should be NOT NULL"
        assert columns["action"]["notnull"], "Activity.action should be NOT NULL"


# ============================================
# IssueLink table schema validation
# ============================================

@pytest.mark.unit
class TestIssueLinkSchema:
    """Validate the IssueLink table schema."""

    async def test_issue_link_columns(self, test_engine):
        """IssueLink table should have all expected columns."""
        columns = await get_table_info(test_engine, "IssueLink")
        expected = ["id", "fromIssueId", "toIssueId", "linkType", "createdAt"]
        for col in expected:
            assert col in columns, f"Column '{col}' missing from IssueLink table"

    async def test_issue_link_foreign_keys(self, test_engine):
        """IssueLink should have two foreign keys to Issue, both CASCADE."""
        fks = await get_foreign_key_info(test_engine, "IssueLink")
        fk_map = {fk["from"]: fk for fk in fks}
        assert "fromIssueId" in fk_map
        assert fk_map["fromIssueId"]["table"] == "Issue"
        assert fk_map["fromIssueId"]["on_delete"] == "CASCADE"
        assert "toIssueId" in fk_map
        assert fk_map["toIssueId"]["table"] == "Issue"
        assert fk_map["toIssueId"]["on_delete"] == "CASCADE"


# ============================================
# QATask table schema validation
# ============================================

@pytest.mark.unit
class TestQATaskSchema:
    """Validate the QATask table schema."""

    EXPECTED_COLUMNS = [
        "id", "projectId", "key", "sequence", "title", "scenario",
        "expectedResult", "actualResult", "status", "type", "priority",
        "executionHistory", "lastExecutedAt", "createdAt", "updatedAt",
        "bugIssueId", "linkedFeatureId", "linkedEpicId", "linkedStoryId",
        "linkedTaskId", "testContext", "failureContext", "environmentDetails",
    ]

    async def test_qa_task_columns(self, test_engine):
        """QATask table should have all expected columns."""
        columns = await get_table_info(test_engine, "QATask")
        for col in self.EXPECTED_COLUMNS:
            assert col in columns, f"Column '{col}' missing from QATask table"

    async def test_qa_task_required_fields(self, test_engine):
        """QATask required fields should be NOT NULL."""
        columns = await get_table_info(test_engine, "QATask")
        required = ["projectId", "title", "scenario", "expectedResult", "status", "type", "priority"]
        for col in required:
            assert columns[col]["notnull"], f"QATask.{col} should be NOT NULL"

    async def test_qa_task_nullable_fields(self, test_engine):
        """QATask optional fields should be nullable."""
        columns = await get_table_info(test_engine, "QATask")
        nullable = [
            "actualResult", "executionHistory", "lastExecutedAt",
            "bugIssueId", "linkedFeatureId", "linkedEpicId", "linkedStoryId",
            "linkedTaskId", "testContext", "failureContext", "environmentDetails",
        ]
        for col in nullable:
            assert not columns[col]["notnull"], f"QATask.{col} should be nullable"


# ============================================
# QATaskIssueLink table schema validation
# ============================================

@pytest.mark.unit
class TestQATaskIssueLinkSchema:
    """Validate the QATaskIssueLink table schema."""

    async def test_qa_link_columns(self, test_engine):
        """QATaskIssueLink should have expected columns."""
        columns = await get_table_info(test_engine, "QATaskIssueLink")
        for col in ["id", "qaTaskId", "issueId", "createdAt"]:
            assert col in columns

    async def test_qa_link_foreign_keys(self, test_engine):
        """QATaskIssueLink should reference both QATask and Issue with CASCADE."""
        fks = await get_foreign_key_info(test_engine, "QATaskIssueLink")
        fk_map = {fk["from"]: fk for fk in fks}
        assert "qaTaskId" in fk_map
        assert fk_map["qaTaskId"]["table"] == "QATask"
        assert fk_map["qaTaskId"]["on_delete"] == "CASCADE"
        assert "issueId" in fk_map
        assert fk_map["issueId"]["table"] == "Issue"
        assert fk_map["issueId"]["on_delete"] == "CASCADE"


# ============================================
# ExecutionSummary table schema validation
# ============================================

@pytest.mark.unit
class TestExecutionSummarySchema:
    """Validate the ExecutionSummary table schema."""

    async def test_execution_summary_columns(self, test_engine):
        """ExecutionSummary should have all expected columns."""
        columns = await get_table_info(test_engine, "ExecutionSummary")
        expected = [
            "id", "issueId", "summary", "executedAt", "executionTime",
            "provider", "model", "exitCode", "componentsModified", "filesTouched",
            "linesAdded", "linesRemoved", "architectureNotes", "technicalNotes",
            "challengesFaced", "lessonsLearned", "commitHashes", "docFilePath",
            "createdAt", "updatedAt",
        ]
        for col in expected:
            assert col in columns, f"Column '{col}' missing from ExecutionSummary"

    async def test_execution_summary_foreign_key(self, test_engine):
        """ExecutionSummary.issueId should reference Issue with CASCADE."""
        fks = await get_foreign_key_info(test_engine, "ExecutionSummary")
        fk_map = {fk["from"]: fk for fk in fks}
        assert "issueId" in fk_map
        assert fk_map["issueId"]["table"] == "Issue"
        assert fk_map["issueId"]["on_delete"] == "CASCADE"


# ============================================
# FeatureDocumentation table schema validation
# ============================================

@pytest.mark.unit
class TestFeatureDocumentationSchema:
    """Validate the FeatureDocumentation table schema."""

    async def test_feature_doc_columns(self, test_engine):
        """FeatureDocumentation should have all expected columns."""
        columns = await get_table_info(test_engine, "FeatureDocumentation")
        expected = [
            "id", "projectId", "featureIssueId", "featureKey", "title",
            "overview", "requirements", "implementation", "architecture",
            "techStack", "testingStrategy", "totalTasks", "completedTasks",
            "totalQATasks", "passedQATasks", "failedQATasks", "mdFilePath",
            "embeddingId", "lastIndexedAt", "createdAt", "updatedAt",
        ]
        for col in expected:
            assert col in columns, f"Column '{col}' missing from FeatureDocumentation"

    async def test_feature_doc_required_fields(self, test_engine):
        """FeatureDocumentation required fields should be NOT NULL."""
        columns = await get_table_info(test_engine, "FeatureDocumentation")
        required = [
            "projectId", "featureIssueId", "featureKey", "title",
            "overview", "requirements", "implementation", "architecture",
            "techStack", "testingStrategy", "totalTasks", "completedTasks",
            "totalQATasks", "passedQATasks", "failedQATasks", "mdFilePath",
        ]
        for col in required:
            assert columns[col]["notnull"], f"FeatureDocumentation.{col} should be NOT NULL"


# ============================================
# CommitLink table schema validation
# ============================================

@pytest.mark.unit
class TestCommitLinkSchema:
    """Validate the CommitLink table schema."""

    async def test_commit_link_columns(self, test_engine):
        """CommitLink should have all expected columns."""
        columns = await get_table_info(test_engine, "CommitLink")
        expected = [
            "id", "issueId", "projectId", "commitHash", "shortHash",
            "message", "author", "authorEmail", "committedAt",
            "linkType", "autoLinked", "triggeredStatusChange", "createdAt",
        ]
        for col in expected:
            assert col in columns, f"Column '{col}' missing from CommitLink"

    async def test_commit_link_foreign_keys(self, test_engine):
        """CommitLink should have foreign keys to Issue and Project."""
        fks = await get_foreign_key_info(test_engine, "CommitLink")
        fk_map = {fk["from"]: fk for fk in fks}
        assert "issueId" in fk_map
        assert fk_map["issueId"]["table"] == "Issue"
        assert fk_map["issueId"]["on_delete"] == "CASCADE"
        assert "projectId" in fk_map
        assert fk_map["projectId"]["table"] == "Project"
        assert fk_map["projectId"]["on_delete"] == "CASCADE"


# ============================================
# GitSyncState table schema validation
# ============================================

@pytest.mark.unit
class TestGitSyncStateSchema:
    """Validate the GitSyncState table schema."""

    async def test_git_sync_state_columns(self, test_engine):
        """GitSyncState should have all expected columns."""
        columns = await get_table_info(test_engine, "GitSyncState")
        expected = [
            "id", "projectId", "lastSyncedCommitHash", "lastSyncedAt",
            "totalCommitsLinked", "totalStatusUpdates",
            "autoSyncEnabled", "autoStatusUpdateEnabled",
            "createdAt", "updatedAt",
        ]
        for col in expected:
            assert col in columns, f"Column '{col}' missing from GitSyncState"

    async def test_git_sync_state_foreign_key(self, test_engine):
        """GitSyncState.projectId should reference Project."""
        fks = await get_foreign_key_info(test_engine, "GitSyncState")
        fk_map = {fk["from"]: fk for fk in fks}
        assert "projectId" in fk_map
        assert fk_map["projectId"]["table"] == "Project"
        assert fk_map["projectId"]["on_delete"] == "CASCADE"


# ============================================
# Pydantic schema validation tests
# ============================================

@pytest.mark.unit
class TestPydanticSchemaValidation:
    """Validate Pydantic schemas enforce correct constraints."""

    def test_issue_create_requires_title(self):
        """IssueCreate should require a title."""
        from models.schemas import IssueCreate
        with pytest.raises(Exception):
            IssueCreate()

    def test_issue_create_rejects_empty_title(self):
        """IssueCreate should reject empty title."""
        from models.schemas import IssueCreate
        with pytest.raises(Exception):
            IssueCreate(title="")

    def test_issue_create_rejects_long_title(self):
        """IssueCreate should reject titles > 500 chars."""
        from models.schemas import IssueCreate
        with pytest.raises(Exception):
            IssueCreate(title="x" * 501)

    def test_issue_create_defaults(self):
        """IssueCreate should have correct defaults."""
        from models.schemas import IssueCreate, IssueType, IssueStatus, Priority
        issue = IssueCreate(title="Test")
        assert issue.type == IssueType.TASK
        assert issue.status == IssueStatus.BACKLOG
        assert issue.priority == Priority.MEDIUM

    def test_issue_update_all_optional(self):
        """IssueUpdate should allow all fields to be optional."""
        from models.schemas import IssueUpdate
        update = IssueUpdate()
        assert update.title is None
        assert update.status is None

    def test_issue_update_rejects_negative_estimate(self):
        """IssueUpdate should reject negative estimate values."""
        from models.schemas import IssueUpdate
        with pytest.raises(Exception):
            IssueUpdate(estimate=-1.0)

    def test_issue_update_rejects_negative_story_points(self):
        """IssueUpdate should reject negative story points."""
        from models.schemas import IssueUpdate
        with pytest.raises(Exception):
            IssueUpdate(storyPoints=-1)

    def test_qa_task_create_requires_fields(self):
        """QATaskCreate should require title, scenario, expectedResult."""
        from models.schemas import QATaskCreate
        with pytest.raises(Exception):
            QATaskCreate()

    def test_qa_task_create_defaults(self):
        """QATaskCreate should have correct defaults."""
        from models.schemas import QATaskCreate, QATaskType, QAPriority
        qa = QATaskCreate(
            title="Test", scenario="Step 1", expectedResult="Pass"
        )
        assert qa.type == QATaskType.AUTOMATED
        assert qa.priority == QAPriority.MEDIUM
        assert qa.linkedIssueIds == []

    def test_qa_settings_threshold_range(self):
        """QASettingsUpdate should enforce passThreshold in [0, 1]."""
        from models.schemas import QASettingsUpdate
        with pytest.raises(Exception):
            QASettingsUpdate(passThreshold=1.5)
        with pytest.raises(Exception):
            QASettingsUpdate(passThreshold=-0.1)

    def test_enum_values_match(self):
        """Enum values should match expected constants."""
        from models.schemas import IssueType, IssueStatus, Priority, QATaskStatus

        assert set(IssueType) == {
            IssueType.FEATURE, IssueType.EPIC, IssueType.STORY,
            IssueType.TASK, IssueType.SUBTASK, IssueType.BUG,
        }
        assert set(IssueStatus) == {
            IssueStatus.BACKLOG, IssueStatus.TODO, IssueStatus.IN_PROGRESS,
            IssueStatus.IN_REVIEW, IssueStatus.COMPLETED_WAITING_QA,
            IssueStatus.DONE, IssueStatus.CANCELLED,
        }
        assert set(Priority) == {
            Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.CRITICAL,
        }
        assert set(QATaskStatus) == {
            QATaskStatus.NOT_DONE, QATaskStatus.IN_PROGRESS,
            QATaskStatus.PASS, QATaskStatus.FAILED,
        }
