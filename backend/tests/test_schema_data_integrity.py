"""
Data integrity tests for database schema changes.

Tests CRUD operations, cascading deletes, unique constraint enforcement,
nullable constraint enforcement, and relationship integrity using an
isolated in-memory database.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError

from models.issue import Issue, Comment, Activity, IssueLink, IssueSequence, Project
from models.grouping import IssueGroup, IssueGroupMember
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

    async def test_duplicate_issue_link_fails(self, seeded_session):
        """Duplicate (fromIssueId, toIssueId, linkType) should raise IntegrityError (CB-1959)."""
        issue2 = make_issue(id="issue-2", key="CB-2", sequence=2, title="Issue 2")
        seeded_session.add(issue2)
        await seeded_session.flush()

        seeded_session.add(IssueLink(
            id="link-a", fromIssueId="test-issue-1", toIssueId="issue-2", linkType="RELATES_TO",
        ))
        await seeded_session.flush()

        seeded_session.add(IssueLink(
            id="link-b", fromIssueId="test-issue-1", toIssueId="issue-2", linkType="RELATES_TO",
        ))
        with pytest.raises(IntegrityError):
            await seeded_session.flush()
        await seeded_session.rollback()

    async def test_different_link_type_allowed(self, seeded_session):
        """Same issue pair with a different linkType is allowed (CB-1959)."""
        issue2 = make_issue(id="issue-2", key="CB-2", sequence=2, title="Issue 2")
        seeded_session.add(issue2)
        await seeded_session.flush()

        seeded_session.add(IssueLink(
            id="link-a", fromIssueId="test-issue-1", toIssueId="issue-2", linkType="RELATES_TO",
        ))
        seeded_session.add(IssueLink(
            id="link-b", fromIssueId="test-issue-1", toIssueId="issue-2", linkType="BLOCKS",
        ))
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueLink).where(IssueLink.fromIssueId == "test-issue-1")
        )
        assert len(result.scalars().all()) == 2

    async def test_issue_link_response_projects_summaries(self, seeded_session):
        """IssueLinkResponse should embed fromIssue + toIssue summaries (CB-1960)."""
        from sqlalchemy.orm import selectinload
        from models.schemas import IssueLinkResponse, IssueSummary

        issue2 = make_issue(
            id="issue-2", key="CB-2", sequence=2, title="Second", status="IN_PROGRESS",
        )
        seeded_session.add(issue2)
        await seeded_session.flush()

        seeded_session.add(IssueLink(
            id="link-proj", fromIssueId="test-issue-1", toIssueId="issue-2", linkType="BLOCKS",
        ))
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueLink)
            .options(selectinload(IssueLink.fromIssue), selectinload(IssueLink.toIssue))
            .where(IssueLink.id == "link-proj")
        )
        link = result.scalar_one()

        projected = IssueLinkResponse.model_validate(link)
        assert projected.fromIssue == IssueSummary(
            id="test-issue-1", key="CB-1", title="Test Issue", status="BACKLOG",
        )
        assert projected.toIssue == IssueSummary(
            id="issue-2", key="CB-2", title="Second", status="IN_PROGRESS",
        )

    async def test_issue_link_response_summaries_default_none(self, seeded_session):
        """Without ORM hydration the projections must be None, never raise (CB-1960)."""
        from models.schemas import IssueLinkResponse

        issue2 = make_issue(id="issue-2", key="CB-2", sequence=2, title="Second")
        seeded_session.add(issue2)
        await seeded_session.flush()

        link = IssueLink(
            id="link-bare",
            fromIssueId="test-issue-1",
            toIssueId="issue-2",
            linkType="RELATES_TO",
            createdAt=datetime.now(timezone.utc),
        )

        projected = IssueLinkResponse.model_validate(link)
        assert projected.fromIssue is None
        assert projected.toIssue is None
        assert projected.linkType == "RELATES_TO"

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
# Issue Group schema tests (CB-1963)
# ============================================

@pytest.mark.integration
class TestIssueGroupSchemas:
    """Validate Pydantic shape of IssueGroup* schemas added in CB-1963."""

    async def test_issue_group_create_requires_title(self):
        """IssueGroupCreate must reject empty / missing title."""
        from pydantic import ValidationError
        from models.schemas import IssueGroupCreate

        with pytest.raises(ValidationError):
            IssueGroupCreate(title="")

        with pytest.raises(ValidationError):
            IssueGroupCreate.model_validate({})

        # Valid minimal payload — description and issueIds optional.
        payload = IssueGroupCreate(title="Critical login flow")
        assert payload.title == "Critical login flow"
        assert payload.description is None
        assert payload.issueIds is None

    async def test_issue_group_create_caps_initial_member_list(self):
        """`issueIds` is capped to keep create-with-members payloads bounded."""
        from pydantic import ValidationError
        from models.schemas import IssueGroupCreate

        # Just under the cap is fine.
        IssueGroupCreate(title="t", issueIds=[f"i-{n}" for n in range(500)])

        # 501 entries blows the cap.
        with pytest.raises(ValidationError):
            IssueGroupCreate(title="t", issueIds=[f"i-{n}" for n in range(501)])

    async def test_issue_group_create_dedupes_issue_ids(self):
        """Duplicate ids must be collapsed — the DB UNIQUE(groupId, issueId)
        would otherwise surface as a 500 from the service layer."""
        from models.schemas import IssueGroupCreate

        payload = IssueGroupCreate(
            title="t", issueIds=["i-1", "i-2", "i-1", "  i-2  ", "i-3"],
        )
        # `  i-2  ` is stripped → matches "i-2" → deduped.
        assert payload.issueIds == ["i-1", "i-2", "i-3"]

    async def test_issue_group_create_rejects_oversized_issue_id(self):
        """Each issueId is bounded — defends against ['x' * 1MB] payloads."""
        from pydantic import ValidationError
        from models.schemas import IssueGroupCreate

        with pytest.raises(ValidationError):
            IssueGroupCreate(title="t", issueIds=["x" * 65])

        with pytest.raises(ValidationError):
            IssueGroupCreate(title="t", issueIds=[""])

    async def test_issue_group_create_rejects_oversized_description(self):
        """description is capped at 10k chars to prevent multi-MB persistence."""
        from pydantic import ValidationError
        from models.schemas import IssueGroupCreate

        # 10k exact is fine.
        IssueGroupCreate(title="t", description="d" * 10_000)

        with pytest.raises(ValidationError):
            IssueGroupCreate(title="t", description="d" * 10_001)

    async def test_issue_group_response_from_orm(self, seeded_session):
        """IssueGroupResponse should hydrate from an ORM IssueGroup row."""
        from models.schemas import IssueGroupResponse

        group = IssueGroup(
            id="grp-1",
            projectId="test-project-1",
            title="Auth flow cluster",
            description="Login, signup, password reset",
        )
        seeded_session.add(group)
        await seeded_session.commit()

        fetched = (await seeded_session.execute(
            select(IssueGroup).where(IssueGroup.id == "grp-1")
        )).scalar_one()

        # memberCount is service-supplied (no ORM column); default 0 must
        # apply when from_attributes hydration finds no attribute.
        projected = IssueGroupResponse.model_validate(fetched)
        assert projected.id == "grp-1"
        assert projected.projectId == "test-project-1"
        assert projected.title == "Auth flow cluster"
        assert projected.description == "Login, signup, password reset"
        assert projected.memberCount == 0
        assert projected.createdAt is not None
        assert projected.updatedAt is not None

        # Service-layer pattern: setattr the count onto the row, then validate.
        # This is the production read path — locking it down so a future
        # refactor that wires func.count into the ORM is forced through this
        # test instead of silently breaking the response shape.
        setattr(fetched, "memberCount", 7)
        projected_with_count = IssueGroupResponse.model_validate(fetched)
        assert projected_with_count.memberCount == 7

    async def test_issue_group_member_response_projects_issue_summary(
        self, seeded_session,
    ):
        """IssueGroupMemberResponse should embed IssueSummary when eager-loaded."""
        from sqlalchemy.orm import selectinload
        from models.schemas import IssueGroupMemberResponse, IssueSummary

        group = IssueGroup(
            id="grp-2", projectId="test-project-1", title="Cluster", description=None,
        )
        seeded_session.add(group)
        await seeded_session.flush()

        seeded_session.add(IssueGroupMember(
            id="mem-1", groupId="grp-2", issueId="test-issue-1",
        ))
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueGroupMember)
            .options(selectinload(IssueGroupMember.issue))
            .where(IssueGroupMember.id == "mem-1")
        )
        member = result.scalar_one()

        projected = IssueGroupMemberResponse.model_validate(member)
        assert projected.id == "mem-1"
        assert projected.groupId == "grp-2"
        assert projected.issueId == "test-issue-1"
        assert projected.issue == IssueSummary(
            id="test-issue-1", key="CB-1", title="Test Issue", status="BACKLOG",
        )

    async def test_issue_group_member_response_summary_none_without_eager_load(
        self, seeded_session,
    ):
        """Without selectinload the embedded `issue` projection must default to None.

        Same contract as IssueLinkResponse (CB-1960): bare ORM rows must
        validate without raising on the `lazy='raise_on_sql'` relationship.
        """
        from models.schemas import IssueGroupMemberResponse

        member = IssueGroupMember(
            id="mem-bare",
            groupId="grp-bare",
            issueId="test-issue-1",
            createdAt=datetime.now(timezone.utc),
        )

        projected = IssueGroupMemberResponse.model_validate(member)
        assert projected.id == "mem-bare"
        assert projected.issue is None

    async def test_group_aggregate_status_defaults(self):
        """Empty groups should validate with breakdown={}, percent=0, dominant=None."""
        from models.schemas import GroupAggregateStatus

        empty = GroupAggregateStatus()
        assert empty.statusBreakdown == {}
        assert empty.completionPercent == 0.0
        assert empty.dominantStatus is None

        populated = GroupAggregateStatus(
            statusBreakdown={"DONE": 2, "IN_PROGRESS": 1, "BACKLOG": 1},
            completionPercent=50.0,
            dominantStatus="DONE",
        )
        assert populated.completionPercent == 50.0
        assert populated.dominantStatus == "DONE"

    async def test_group_aggregate_status_clamps_completion_percent(self):
        """completionPercent is bounded to [0, 100] — guard against helper bugs."""
        from pydantic import ValidationError
        from models.schemas import GroupAggregateStatus

        with pytest.raises(ValidationError):
            GroupAggregateStatus(completionPercent=-1.0)
        with pytest.raises(ValidationError):
            GroupAggregateStatus(completionPercent=100.1)

    async def test_issue_group_detail_response_carries_members_and_aggregate(self):
        """Detail response must accept members + aggregateStatus together."""
        from models.schemas import (
            IssueGroupDetailResponse,
            IssueGroupMemberResponse,
            GroupAggregateStatus,
            IssueSummary,
        )

        now = datetime.now(timezone.utc)
        detail = IssueGroupDetailResponse(
            id="grp-3",
            projectId="test-project-1",
            title="Detail cluster",
            description=None,
            createdAt=now,
            updatedAt=now,
            members=[
                IssueGroupMemberResponse(
                    id="mem-x",
                    groupId="grp-3",
                    issueId="i-x",
                    createdAt=now,
                    issue=IssueSummary(id="i-x", key="CB-9", title="X", status="DONE"),
                ),
            ],
            aggregateStatus=GroupAggregateStatus(
                statusBreakdown={"DONE": 1},
                completionPercent=100.0,
                dominantStatus="DONE",
            ),
        )
        assert len(detail.members) == 1
        assert detail.aggregateStatus.completionPercent == 100.0
        assert detail.members[0].issue.key == "CB-9"

    async def test_paginated_group_response_shape(self):
        """PaginatedGroupResponse mirrors PaginatedResponse for issues."""
        from models.schemas import PaginatedGroupResponse, IssueGroupResponse

        now = datetime.now(timezone.utc)
        page = PaginatedGroupResponse(
            items=[
                IssueGroupResponse(
                    id="grp-a",
                    projectId="test-project-1",
                    title="A",
                    memberCount=3,
                    createdAt=now,
                    updatedAt=now,
                ),
            ],
            total=1,
            page=1,
            pageSize=20,
            totalPages=1,
        )
        assert len(page.items) == 1
        assert page.items[0].memberCount == 3
        assert page.totalPages == 1


# ============================================
# CB-1965: position field + ordering on IssueGroupMember
# ============================================

@pytest.mark.integration
class TestIssueGroupMemberPosition:
    """Validate the CB-1965 position contract end-to-end through the ORM."""

    async def test_default_position_value_after_insert(self, seeded_session):
        """An IssueGroupMember inserted without an explicit position must
        land with position=0 from the DB-side default — protecting legacy
        rows and any caller that forgets to call `next_member_position`."""
        from models.grouping import IssueGroup, IssueGroupMember

        seeded_session.add(IssueGroup(
            id="grp-pos-default",
            projectId="test-project-1",
            title="Default position",
        ))
        await seeded_session.flush()

        seeded_session.add(IssueGroupMember(
            id="mem-default",
            groupId="grp-pos-default",
            issueId="test-issue-1",
        ))
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueGroupMember).where(IssueGroupMember.id == "mem-default")
        )
        member = result.scalar_one()
        assert member.position == 0

    async def test_next_member_position_helper_assigns_one_indexed_slots(
        self, seeded_session,
    ):
        """`next_member_position` must return 1 on an empty group, then 2, 3,
        … as members are added. This is the COALESCE(MAX, 0)+1 contract."""
        from models.grouping import IssueGroup, IssueGroupMember, next_member_position

        seeded_session.add(IssueGroup(
            id="grp-next",
            projectId="test-project-1",
            title="Next-slot group",
        ))
        # Make a few extra issues to attach so we don't trip the
        # IssueGroupMember UNIQUE(groupId, issueId).
        from models.issue import Issue
        for n in (2, 3, 4):
            seeded_session.add(Issue(
                id=f"issue-pos-{n}",
                projectId="test-project-1",
                key=f"CB-{1000 + n}",
                title=f"Pos issue {n}",
                type="TASK",
                status="BACKLOG",
                priority="MEDIUM",
                sequence=1000 + n,
            ))
        await seeded_session.flush()

        first = await next_member_position(seeded_session, "grp-next")
        assert first == 1, "empty group must yield position 1"

        seeded_session.add(IssueGroupMember(
            id="mem-pos-1",
            groupId="grp-next",
            issueId="test-issue-1",
            position=first,
        ))
        await seeded_session.flush()
        assert await next_member_position(seeded_session, "grp-next") == 2

        seeded_session.add(IssueGroupMember(
            id="mem-pos-2",
            groupId="grp-next",
            issueId="issue-pos-2",
            position=2,
        ))
        await seeded_session.flush()
        assert await next_member_position(seeded_session, "grp-next") == 3

    async def test_next_member_position_isolates_groups(self, seeded_session):
        """Position numbering is per-group; one group's max must not bleed
        into a sibling group's next slot."""
        from models.grouping import IssueGroup, IssueGroupMember, next_member_position

        for gid in ("grp-iso-a", "grp-iso-b"):
            seeded_session.add(IssueGroup(
                id=gid, projectId="test-project-1", title=gid,
            ))
        await seeded_session.flush()

        seeded_session.add(IssueGroupMember(
            id="mem-iso-a-1",
            groupId="grp-iso-a",
            issueId="test-issue-1",
            position=7,  # arbitrary high value
        ))
        await seeded_session.commit()

        # Group A continues from 8; group B starts at 1.
        assert await next_member_position(seeded_session, "grp-iso-a") == 8
        assert await next_member_position(seeded_session, "grp-iso-b") == 1

    async def test_relationship_orders_members_by_position(self, seeded_session):
        """`IssueGroup.members` must yield rows in ascending position order
        regardless of insert order — that's the order_by on the relationship."""
        from sqlalchemy.orm import selectinload
        from models.grouping import IssueGroup, IssueGroupMember
        from models.issue import Issue

        seeded_session.add(IssueGroup(
            id="grp-order",
            projectId="test-project-1",
            title="Ordered group",
        ))
        for n in (10, 11, 12):
            seeded_session.add(Issue(
                id=f"issue-order-{n}",
                projectId="test-project-1",
                key=f"CB-{2000 + n}",
                title=f"Order issue {n}",
                type="TASK",
                status="BACKLOG",
                priority="MEDIUM",
                sequence=2000 + n,
            ))
        await seeded_session.flush()

        # Insert OUT of position order to prove the relationship sorts.
        seeded_session.add(IssueGroupMember(
            id="mem-ord-3", groupId="grp-order", issueId="issue-order-12", position=3,
        ))
        seeded_session.add(IssueGroupMember(
            id="mem-ord-1", groupId="grp-order", issueId="issue-order-10", position=1,
        ))
        seeded_session.add(IssueGroupMember(
            id="mem-ord-2", groupId="grp-order", issueId="issue-order-11", position=2,
        ))
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueGroup)
            .options(selectinload(IssueGroup.members))
            .where(IssueGroup.id == "grp-order")
        )
        group = result.scalar_one()
        positions = [m.position for m in group.members]
        ids = [m.id for m in group.members]
        assert positions == [1, 2, 3]
        assert ids == ["mem-ord-1", "mem-ord-2", "mem-ord-3"]

    async def test_relationship_breaks_position_ties_by_id(self, seeded_session):
        """When two members share a position (the race that
        `next_member_position` documents as tolerable), the relationship's
        secondary sort on `id` must give a deterministic order — pinning
        the API contract that callers can rely on a stable read order."""
        from sqlalchemy.orm import selectinload
        from models.grouping import IssueGroup, IssueGroupMember
        from models.issue import Issue

        seeded_session.add(IssueGroup(
            id="grp-tie",
            projectId="test-project-1",
            title="Tied positions",
        ))
        for n in (20, 21):
            seeded_session.add(Issue(
                id=f"issue-tie-{n}",
                projectId="test-project-1",
                key=f"CB-{3000 + n}",
                title=f"Tie issue {n}",
                type="TASK",
                status="BACKLOG",
                priority="MEDIUM",
                sequence=3000 + n,
            ))
        await seeded_session.flush()

        # Two members SAME position; ids picked so lexicographic order is
        # the opposite of insert order — a no-secondary-sort implementation
        # would fail this assertion.
        seeded_session.add(IssueGroupMember(
            id="mem-tie-z", groupId="grp-tie", issueId="issue-tie-20", position=1,
        ))
        seeded_session.add(IssueGroupMember(
            id="mem-tie-a", groupId="grp-tie", issueId="issue-tie-21", position=1,
        ))
        await seeded_session.commit()

        result = await seeded_session.execute(
            select(IssueGroup)
            .options(selectinload(IssueGroup.members))
            .where(IssueGroup.id == "grp-tie")
        )
        group = result.scalar_one()
        assert [m.id for m in group.members] == ["mem-tie-a", "mem-tie-z"]


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
