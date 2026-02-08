"""
Data integrity tests for database schema changes.

Tests CRUD operations, cascading deletes, unique constraint enforcement,
nullable constraint enforcement, and relationship integrity using an
isolated in-memory database.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError

from models.issue import Issue, Comment, Activity, IssueLink, IssueSequence, Project
from models.qa import QATask, QATaskIssueLink, QASequence, QASettings
from models.documentation import ExecutionSummary, FeatureDocumentation
from models.git import CommitLink, GitSyncState

from tests.schema_test_utils import (
    create_test_engine,
    setup_test_db,
    teardown_test_db,
    create_test_session_factory,
    make_project,
    make_issue,
    make_comment,
    make_activity,
    make_qa_task,
)


@pytest.fixture
async def db_session():
    """Provide a fresh database session for each test."""
    engine = create_test_engine()
    await setup_test_db(engine)
    session_factory = create_test_session_factory(engine)

    async with session_factory() as session:
        yield session

    await teardown_test_db(engine)
    await engine.dispose()


@pytest.fixture
async def seeded_session(db_session):
    """Provide a session with a pre-seeded project and issue."""
    project = make_project()
    db_session.add(project)
    await db_session.flush()

    issue = make_issue()
    db_session.add(issue)
    await db_session.flush()

    return db_session


# ============================================
# CRUD operations tests
# ============================================

@pytest.mark.integration
class TestIssueCRUD:
    """Test CRUD operations on Issue table."""

    async def test_create_issue(self, db_session):
        """Should create an issue with all fields."""
        project = make_project()
        db_session.add(project)
        await db_session.flush()

        issue = make_issue(
            dueDate=datetime(2025, 6, 15),
            storyPoints=5,
            estimate=8.0,
            labels='["frontend", "urgent"]',
        )
        db_session.add(issue)
        await db_session.commit()

        result = await db_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        fetched = result.scalar_one()
        assert fetched.title == "Test Issue"
        assert fetched.projectId == "test-project-1"
        assert fetched.key == "CB-1"
        assert fetched.storyPoints == 5
        assert fetched.estimate == 8.0

    async def test_update_issue_status(self, seeded_session):
        """Should update an issue's status."""
        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        issue = result.scalar_one()
        issue.status = "IN_PROGRESS"
        await seeded_session.commit()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        updated = result.scalar_one()
        assert updated.status == "IN_PROGRESS"

    async def test_update_issue_dates(self, seeded_session):
        """Should update date fields on an issue."""
        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        issue = result.scalar_one()
        now = datetime.now()
        issue.startedAt = now
        issue.dueDate = now + timedelta(days=7)
        await seeded_session.commit()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        updated = result.scalar_one()
        assert updated.startedAt is not None
        assert updated.dueDate is not None

    async def test_delete_issue(self, seeded_session):
        """Should delete an issue."""
        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        issue = result.scalar_one()
        await seeded_session.delete(issue)
        await seeded_session.commit()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        assert result.scalar_one_or_none() is None


@pytest.mark.integration
class TestCommentCRUD:
    """Test CRUD operations on Comment table."""

    async def test_create_comment(self, seeded_session):
        """Should create a comment linked to an issue."""
        comment = make_comment()
        seeded_session.add(comment)
        await seeded_session.commit()

        result = await seeded_session.execute(select(Comment).where(Comment.id == "test-comment-1"))
        fetched = result.scalar_one()
        assert fetched.issueId == "test-issue-1"
        assert fetched.author == "test-user"
        assert fetched.content == "Test comment content"

    async def test_update_comment(self, seeded_session):
        """Should update a comment's content."""
        comment = make_comment()
        seeded_session.add(comment)
        await seeded_session.flush()

        comment.content = "Updated content"
        await seeded_session.commit()

        result = await seeded_session.execute(select(Comment).where(Comment.id == "test-comment-1"))
        fetched = result.scalar_one()
        assert fetched.content == "Updated content"

    async def test_delete_comment(self, seeded_session):
        """Should delete a comment."""
        comment = make_comment()
        seeded_session.add(comment)
        await seeded_session.flush()

        await seeded_session.delete(comment)
        await seeded_session.commit()

        result = await seeded_session.execute(select(Comment).where(Comment.id == "test-comment-1"))
        assert result.scalar_one_or_none() is None


@pytest.mark.integration
class TestQATaskCRUD:
    """Test CRUD operations on QATask table."""

    async def test_create_qa_task(self, seeded_session):
        """Should create a QA task."""
        qa = make_qa_task()
        seeded_session.add(qa)
        await seeded_session.commit()

        result = await seeded_session.execute(select(QATask).where(QATask.id == "test-qa-1"))
        fetched = result.scalar_one()
        assert fetched.title == "Test QA Task"
        assert fetched.status == "NOT_DONE"
        assert fetched.type == "AUTOMATED"

    async def test_update_qa_task_status(self, seeded_session):
        """Should update QA task status and result."""
        qa = make_qa_task()
        seeded_session.add(qa)
        await seeded_session.flush()

        qa.status = "PASS"
        qa.actualResult = "Test passed as expected"
        qa.lastExecutedAt = datetime.now()
        await seeded_session.commit()

        result = await seeded_session.execute(select(QATask).where(QATask.id == "test-qa-1"))
        fetched = result.scalar_one()
        assert fetched.status == "PASS"
        assert fetched.actualResult == "Test passed as expected"
        assert fetched.lastExecutedAt is not None


# ============================================
# Cascading delete tests
# ============================================

@pytest.mark.integration
class TestCascadingDeletes:
    """Test that cascading deletes work correctly."""

    async def test_delete_issue_cascades_to_comments(self, seeded_session):
        """Deleting an issue should cascade to its comments."""
        comment = make_comment()
        seeded_session.add(comment)
        await seeded_session.flush()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        issue = result.scalar_one()
        await seeded_session.delete(issue)
        await seeded_session.commit()

        result = await seeded_session.execute(select(Comment).where(Comment.issueId == "test-issue-1"))
        assert result.scalar_one_or_none() is None

    async def test_delete_issue_cascades_to_activities(self, seeded_session):
        """Deleting an issue should cascade to its activities."""
        activity = make_activity()
        seeded_session.add(activity)
        await seeded_session.flush()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        issue = result.scalar_one()
        await seeded_session.delete(issue)
        await seeded_session.commit()

        result = await seeded_session.execute(select(Activity).where(Activity.issueId == "test-issue-1"))
        assert result.scalar_one_or_none() is None

    async def test_delete_issue_cascades_to_qa_links(self, seeded_session):
        """Deleting an issue should cascade to QATaskIssueLink entries."""
        qa = make_qa_task()
        seeded_session.add(qa)
        await seeded_session.flush()

        link = QATaskIssueLink(id="link-1", qaTaskId="test-qa-1", issueId="test-issue-1")
        seeded_session.add(link)
        await seeded_session.flush()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        issue = result.scalar_one()
        await seeded_session.delete(issue)
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(QATaskIssueLink).where(QATaskIssueLink.issueId == "test-issue-1")
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_qa_task_cascades_to_links(self, seeded_session):
        """Deleting a QA task should cascade to QATaskIssueLink entries."""
        qa = make_qa_task()
        seeded_session.add(qa)
        await seeded_session.flush()

        link = QATaskIssueLink(id="link-1", qaTaskId="test-qa-1", issueId="test-issue-1")
        seeded_session.add(link)
        await seeded_session.flush()

        result = await seeded_session.execute(select(QATask).where(QATask.id == "test-qa-1"))
        qa_task = result.scalar_one()
        await seeded_session.delete(qa_task)
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(QATaskIssueLink).where(QATaskIssueLink.qaTaskId == "test-qa-1")
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_issue_cascades_to_execution_summaries(self, seeded_session):
        """Deleting an issue should cascade to its execution summaries."""
        summary = ExecutionSummary(
            id="summary-1",
            issueId="test-issue-1",
            summary="Test execution",
            executedAt=datetime.now(),
            executionTime=120.0,
            provider="claude_code",
            componentsModified='["backend"]',
            filesTouched='["test.py"]',
        )
        seeded_session.add(summary)
        await seeded_session.flush()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "test-issue-1"))
        issue = result.scalar_one()
        await seeded_session.delete(issue)
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(ExecutionSummary).where(ExecutionSummary.issueId == "test-issue-1")
        )
        assert result.scalar_one_or_none() is None


# ============================================
# Issue hierarchy tests
# ============================================

@pytest.mark.integration
class TestIssueHierarchy:
    """Test parent-child relationships on Issue table."""

    async def test_create_child_issue(self, seeded_session):
        """Should create a child issue linked to a parent."""
        child = make_issue(
            id="child-1", key="CB-2", sequence=2,
            title="Child Issue", parentId="test-issue-1",
        )
        seeded_session.add(child)
        await seeded_session.commit()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "child-1"))
        fetched = result.scalar_one()
        assert fetched.parentId == "test-issue-1"

    async def test_delete_parent_sets_child_null(self, seeded_session):
        """Deleting a parent issue should SET NULL on child's parentId."""
        child = make_issue(
            id="child-1", key="CB-2", sequence=2,
            title="Child Issue", parentId="test-issue-1",
        )
        seeded_session.add(child)
        await seeded_session.flush()

        # Use raw SQL to delete parent (bypass ORM cascade which may differ)
        await seeded_session.execute(text("DELETE FROM Issue WHERE id = 'test-issue-1'"))
        await seeded_session.commit()

        # Refresh to get updated state
        seeded_session.expire_all()
        result = await seeded_session.execute(select(Issue).where(Issue.id == "child-1"))
        child_fetched = result.scalar_one_or_none()
        if child_fetched:
            assert child_fetched.parentId is None, (
                "Child's parentId should be NULL after parent deletion"
            )

    async def test_multi_level_hierarchy(self, seeded_session):
        """Should support multi-level parent-child hierarchy."""
        # Epic -> Story -> Task
        epic = make_issue(
            id="epic-1", key="CB-10", sequence=10,
            title="Epic", issue_type="EPIC",
        )
        story = make_issue(
            id="story-1", key="CB-11", sequence=11,
            title="Story", issue_type="STORY", parentId="epic-1",
        )
        task = make_issue(
            id="task-1", key="CB-12", sequence=12,
            title="Task", issue_type="TASK", parentId="story-1",
        )
        seeded_session.add_all([epic, story, task])
        await seeded_session.commit()

        result = await seeded_session.execute(select(Issue).where(Issue.id == "task-1"))
        fetched_task = result.scalar_one()
        assert fetched_task.parentId == "story-1"

        result = await seeded_session.execute(select(Issue).where(Issue.id == "story-1"))
        fetched_story = result.scalar_one()
        assert fetched_story.parentId == "epic-1"


# ============================================
# Unique constraint enforcement tests
# ============================================

@pytest.mark.integration
class TestUniqueConstraintEnforcement:
    """Test that unique constraints are enforced at the database level."""

    async def test_duplicate_issue_key_fails(self, seeded_session):
        """Inserting a duplicate Issue.key should raise IntegrityError."""
        duplicate = make_issue(id="issue-2", key="CB-1", sequence=2, title="Duplicate Key")
        seeded_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()

    async def test_duplicate_project_name_fails(self, db_session):
        """Inserting a duplicate Project.name should raise IntegrityError."""
        p1 = make_project(id="p1", name="Same Name")
        p2 = make_project(id="p2", name="Same Name")
        db_session.add(p1)
        await db_session.flush()
        db_session.add(p2)
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_duplicate_qa_task_key_fails(self, seeded_session):
        """Inserting a duplicate QATask.key should raise IntegrityError."""
        qa1 = make_qa_task(id="qa-1", key="QA-001")
        qa2 = make_qa_task(id="qa-2", key="QA-001")
        seeded_session.add(qa1)
        await seeded_session.flush()
        seeded_session.add(qa2)
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()


# ============================================
# Nullable constraint enforcement tests
# ============================================

@pytest.mark.integration
class TestNullableConstraints:
    """Test that NOT NULL constraints are enforced."""

    async def test_issue_title_required(self, seeded_session):
        """Issue.title should not accept NULL."""
        issue = Issue(
            id="no-title", projectId="test-project-1",
            key="CB-99", sequence=99,
            title=None,  # Should fail
            type="TASK", status="BACKLOG", priority="MEDIUM",
        )
        seeded_session.add(issue)
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()

    async def test_issue_key_required(self, seeded_session):
        """Issue.key should not accept NULL."""
        issue = Issue(
            id="no-key", projectId="test-project-1",
            key=None, sequence=99,
            title="Test", type="TASK", status="BACKLOG", priority="MEDIUM",
        )
        seeded_session.add(issue)
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()

    async def test_comment_author_required(self, seeded_session):
        """Comment.author should not accept NULL."""
        comment = Comment(id="c1", issueId="test-issue-1", author=None, content="Test")
        seeded_session.add(comment)
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()

    async def test_comment_content_required(self, seeded_session):
        """Comment.content should not accept NULL."""
        comment = Comment(id="c1", issueId="test-issue-1", author="user", content=None)
        seeded_session.add(comment)
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()

    async def test_qa_task_scenario_required(self, seeded_session):
        """QATask.scenario should not accept NULL."""
        qa = QATask(
            id="qa-null", projectId="test-project-1",
            key="QA-999", sequence=999,
            title="Test", scenario=None,
            expectedResult="Pass",
            status="NOT_DONE", type="AUTOMATED", priority="MEDIUM",
        )
        seeded_session.add(qa)
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()


# ============================================
# Issue link tests
# ============================================

@pytest.mark.integration
class TestIssueLinkIntegrity:
    """Test IssueLink data integrity."""

    async def test_create_issue_link(self, seeded_session):
        """Should create a link between two issues."""
        issue2 = make_issue(id="issue-2", key="CB-2", sequence=2, title="Issue 2")
        seeded_session.add(issue2)
        await seeded_session.flush()

        link = IssueLink(
            id="link-1",
            fromIssueId="test-issue-1",
            toIssueId="issue-2",
            linkType="BLOCKS",
        )
        seeded_session.add(link)
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueLink).where(IssueLink.id == "link-1")
        )
        fetched = result.scalar_one()
        assert fetched.fromIssueId == "test-issue-1"
        assert fetched.toIssueId == "issue-2"
        assert fetched.linkType == "BLOCKS"

    async def test_delete_linked_issue_cascades(self, seeded_session):
        """Deleting a linked issue should cascade to the link."""
        issue2 = make_issue(id="issue-2", key="CB-2", sequence=2, title="Issue 2")
        seeded_session.add(issue2)
        await seeded_session.flush()

        link = IssueLink(
            id="link-1",
            fromIssueId="test-issue-1",
            toIssueId="issue-2",
            linkType="RELATES_TO",
        )
        seeded_session.add(link)
        await seeded_session.flush()

        await seeded_session.execute(text("DELETE FROM Issue WHERE id = 'test-issue-1'"))
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueLink).where(IssueLink.id == "link-1")
        )
        assert result.scalar_one_or_none() is None


# ============================================
# QA settings and sequences tests
# ============================================

@pytest.mark.integration
class TestQASettingsAndSequences:
    """Test QA settings and sequence management."""

    async def test_create_qa_settings(self, seeded_session):
        """Should create QA settings for a project."""
        settings = QASettings(
            id="settings-1",
            projectId="test-project-1",
            passThreshold=0.85,
            autoCreateBugs=True,
        )
        seeded_session.add(settings)
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(QASettings).where(QASettings.projectId == "test-project-1")
        )
        fetched = result.scalar_one()
        assert fetched.passThreshold == 0.85
        assert fetched.autoCreateBugs is True

    async def test_issue_sequence_tracking(self, seeded_session):
        """Should track issue sequence numbers per project."""
        seq = IssueSequence(
            id="seq-1", projectId="test-project-1", prefix="CB", lastNumber=5,
        )
        seeded_session.add(seq)
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueSequence).where(IssueSequence.projectId == "test-project-1")
        )
        fetched = result.scalar_one()
        assert fetched.prefix == "CB"
        assert fetched.lastNumber == 5

    async def test_qa_sequence_tracking(self, seeded_session):
        """Should track QA task sequence numbers per project."""
        seq = QASequence(
            id="qa-seq-1", projectId="test-project-1", prefix="QA", lastNumber=10,
        )
        seeded_session.add(seq)
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(QASequence).where(QASequence.projectId == "test-project-1")
        )
        fetched = result.scalar_one()
        assert fetched.prefix == "QA"
        assert fetched.lastNumber == 10
