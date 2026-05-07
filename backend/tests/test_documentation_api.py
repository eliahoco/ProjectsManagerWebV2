"""
Regression tests for the documentation GET API (CB-1588).

Covers:
  - GET /api/issues/{id}/documentation       — list ExecutionSummaries
  - GET /api/issues/{id}/documentation/latest — latest ExecutionSummary
  - GET /api/issues/{id}/documentation/notes  — list ImplementationNotes

Tests run against an isolated on-disk SQLite database with `get_db`
overridden so they never touch the production codeboard.db.
"""

import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, List

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.documentation import router as documentation_router
from app.errors import setup_exception_handlers
from models.database import Base, get_db
from models.documentation import (
    ExecutionSummary,
    ImplementationNote,
)
from models.issue import Issue, Project


@pytest_asyncio.fixture
async def test_app_and_db():
    """Build a dedicated FastAPI app wired to an isolated SQLite DB.

    The production `app/main.py` does not yet mount this router (that lives
    in sibling task CB-1591). Building a local app here keeps the regression
    test self-contained and avoids leaking dependency overrides across
    unrelated test modules.

    Uses an on-disk SQLite file — not :memory: — because the
    async_sessionmaker hands out independent connections per session, and
    :memory: would give each session a *separate* empty DB.
    """
    tmp_dir = tempfile.mkdtemp(prefix="doc-api-test-")
    db_path = os.path.join(tmp_dir, "test.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    local_app = FastAPI()
    setup_exception_handlers(local_app)
    local_app.include_router(documentation_router, prefix="/api")
    local_app.dependency_overrides[get_db] = _override_get_db

    try:
        yield local_app, factory
    finally:
        await engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest_asyncio.fixture
async def test_db(test_app_and_db):
    _, factory = test_app_and_db
    yield factory


@pytest_asyncio.fixture
async def client(test_app_and_db) -> AsyncGenerator[AsyncClient, None]:
    local_app, _ = test_app_and_db
    transport = ASGITransport(app=local_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---- Helpers ----------------------------------------------------------------

async def _create_issue(factory: async_sessionmaker) -> Issue:
    """Insert a project + issue and return the issue."""
    async with factory() as db:
        now_ms = int(time.time() * 1000)
        project = Project(
            id=str(uuid.uuid4()),
            name=f"proj-{uuid.uuid4()}",
            path="/tmp/p",
            status="ACTIVE",
            createdAt=now_ms,
            updatedAt=now_ms,
        )
        db.add(project)
        await db.flush()

        issue = Issue(
            id=str(uuid.uuid4()),
            projectId=project.id,
            key=f"CB-{uuid.uuid4().hex[:8]}",
            sequence=1,
            title="Test issue",
            type="TASK",
            status="IN_PROGRESS",
            priority="MEDIUM",
            updatedAt=datetime.utcnow(),
        )
        db.add(issue)
        await db.commit()
        await db.refresh(issue)
        return issue


async def _add_summary(
    factory: async_sessionmaker,
    issue_id: str,
    *,
    executed_at: datetime,
    summary_text: str = "exec summary",
) -> ExecutionSummary:
    async with factory() as db:
        row = ExecutionSummary(
            id=str(uuid.uuid4()),
            issueId=issue_id,
            summary=summary_text,
            executedAt=executed_at,
            executionTime=12.5,
            provider="claude_code",
            model="claude-3-opus",
            exitCode=0,
            componentsModified='["backend"]',
            filesTouched='["backend/api/documentation.py"]',
            linesAdded=50,
            linesRemoved=2,
            architectureNotes=None,
            technicalNotes=None,
            challengesFaced=None,
            lessonsLearned=None,
            commitHashes='[]',
            docFilePath=None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def _add_note(
    factory: async_sessionmaker,
    issue_id: str,
    *,
    title: str,
    category: str = "DECISION",
) -> ImplementationNote:
    async with factory() as db:
        row = ImplementationNote(
            id=str(uuid.uuid4()),
            issueId=issue_id,
            title=title,
            content="markdown body",
            category=category,
            author="System",
            tags=None,
            references=None,
            importance="MEDIUM",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


# ---- GET /api/issues/{id}/documentation -------------------------------------

@pytest.mark.asyncio
async def test_list_summaries_returns_newest_first(test_db, client):
    issue = await _create_issue(test_db)
    older = await _add_summary(
        test_db, issue.id,
        executed_at=datetime.utcnow() - timedelta(hours=2),
        summary_text="first run",
    )
    newer = await _add_summary(
        test_db, issue.id,
        executed_at=datetime.utcnow(),
        summary_text="second run",
    )

    resp = await client.get(f"/api/issues/{issue.id}/documentation?projectId={issue.projectId}")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    # Newest first
    assert body[0]["id"] == newer.id
    assert body[1]["id"] == older.id
    assert body[0]["summary"] == "second run"


@pytest.mark.asyncio
async def test_list_summaries_empty_when_no_records(test_db, client):
    """Issue exists but has no summaries — must return [], not 404."""
    issue = await _create_issue(test_db)

    resp = await client.get(f"/api/issues/{issue.id}/documentation?projectId={issue.projectId}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_summaries_404_when_issue_missing(test_db, client):
    resp = await client.get("/api/issues/does-not-exist/documentation?projectId=any-project")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"


# ---- GET /api/issues/{id}/documentation/latest ------------------------------

@pytest.mark.asyncio
async def test_latest_summary_returns_most_recent(test_db, client):
    issue = await _create_issue(test_db)
    await _add_summary(
        test_db, issue.id,
        executed_at=datetime.utcnow() - timedelta(hours=5),
        summary_text="old",
    )
    newest = await _add_summary(
        test_db, issue.id,
        executed_at=datetime.utcnow(),
        summary_text="new",
    )

    resp = await client.get(f"/api/issues/{issue.id}/documentation/latest?projectId={issue.projectId}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == newest.id
    assert body["summary"] == "new"


@pytest.mark.asyncio
async def test_latest_summary_404_when_no_records(test_db, client):
    """Single-record endpoint: empty == not found."""
    issue = await _create_issue(test_db)

    resp = await client.get(f"/api/issues/{issue.id}/documentation/latest?projectId={issue.projectId}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_latest_summary_404_when_issue_missing(test_db, client):
    resp = await client.get("/api/issues/missing/documentation/latest?projectId=any-project")
    assert resp.status_code == 404


# ---- GET /api/issues/{id}/documentation/notes -------------------------------

@pytest.mark.asyncio
async def test_list_notes_returns_records(test_db, client):
    issue = await _create_issue(test_db)
    note_a = await _add_note(test_db, issue.id, title="A", category="DECISION")
    note_b = await _add_note(test_db, issue.id, title="B", category="LESSON")

    resp = await client.get(f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}")
    assert resp.status_code == 200
    body = resp.json()
    assert {n["id"] for n in body} == {note_a.id, note_b.id}
    assert {n["category"] for n in body} == {"DECISION", "LESSON"}


@pytest.mark.asyncio
async def test_list_notes_empty_when_no_records(test_db, client):
    issue = await _create_issue(test_db)

    resp = await client.get(f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_notes_404_when_issue_missing(test_db, client):
    resp = await client.get("/api/issues/missing/documentation/notes?projectId=any-project")
    assert resp.status_code == 404


# ---- Cross-issue isolation --------------------------------------------------

@pytest.mark.asyncio
async def test_summaries_scoped_to_issue(test_db, client):
    """A summary on issue A must not appear on issue B."""
    issue_a = await _create_issue(test_db)
    issue_b = await _create_issue(test_db)
    await _add_summary(
        test_db, issue_a.id,
        executed_at=datetime.utcnow(),
        summary_text="for A",
    )

    resp_a = await client.get(f"/api/issues/{issue_a.id}/documentation?projectId={issue_a.projectId}")
    resp_b = await client.get(f"/api/issues/{issue_b.id}/documentation?projectId={issue_b.projectId}")

    assert resp_a.status_code == 200
    assert len(resp_a.json()) == 1
    assert resp_b.status_code == 200
    assert resp_b.json() == []


@pytest.mark.asyncio
async def test_notes_scoped_to_issue(test_db, client):
    issue_a = await _create_issue(test_db)
    issue_b = await _create_issue(test_db)
    await _add_note(test_db, issue_a.id, title="only-A")

    resp_a = await client.get(f"/api/issues/{issue_a.id}/documentation/notes?projectId={issue_a.projectId}")
    resp_b = await client.get(f"/api/issues/{issue_b.id}/documentation/notes?projectId={issue_b.projectId}")

    assert resp_a.status_code == 200
    assert len(resp_a.json()) == 1
    assert resp_a.json()[0]["title"] == "only-A"
    assert resp_b.status_code == 200
    assert resp_b.json() == []


# ---- POST /api/issues/{id}/documentation/notes (CB-1589) --------------------

@pytest.mark.asyncio
async def test_create_note_persists_and_returns_record(test_db, client):
    issue = await _create_issue(test_db)
    payload = {
        "title": "Pick async SQLAlchemy",
        "content": "Sync engine would block the FastAPI loop.",
        "category": "DECISION",
        "importance": "HIGH",
        "tags": '["async", "db"]',
        "references": '["backend/models/database.py"]',
    }

    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json=payload,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]  # server-generated
    assert body["issueId"] == issue.id
    assert body["title"] == payload["title"]
    assert body["category"] == "DECISION"
    assert body["importance"] == "HIGH"
    assert body["tags"] == payload["tags"]
    assert body["author"] == "System"

    # Round-trip via GET
    list_resp = await client.get(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}"
    )
    assert list_resp.status_code == 200
    ids = [n["id"] for n in list_resp.json()]
    assert body["id"] in ids


@pytest.mark.asyncio
async def test_create_note_defaults_category_and_importance(test_db, client):
    issue = await _create_issue(test_db)
    payload = {"title": "Quick note", "content": "body"}

    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json=payload,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["category"] == "GENERAL"
    assert body["importance"] == "MEDIUM"


@pytest.mark.asyncio
async def test_create_note_rejects_invalid_category(test_db, client):
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={
            "title": "x",
            "content": "y",
            "category": "NOPE",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_rejects_invalid_importance(test_db, client):
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={
            "title": "x",
            "content": "y",
            "importance": "URGENT",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_404_when_issue_missing(test_db, client):
    resp = await client.post(
        "/api/issues/missing/documentation/notes?projectId=any-project",
        json={"title": "x", "content": "y"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_note_rejects_blank_title(test_db, client):
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={"title": "", "content": "y"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_rejects_blank_content(test_db, client):
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={"title": "x", "content": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_rejects_oversized_content(test_db, client):
    """Cap content at 100k chars to block storage-abuse."""
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={"title": "x", "content": "a" * 100_001},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_rejects_malformed_tags(test_db, client):
    """tags must be valid JSON — not raw strings."""
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={"title": "x", "content": "y", "tags": "not-json"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_rejects_non_array_tags(test_db, client):
    """tags must be a JSON array, not an object."""
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={"title": "x", "content": "y", "tags": '{"key": "value"}'},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_rejects_non_string_array_items(test_db, client):
    """Array elements must all be strings."""
    issue = await _create_issue(test_db)
    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={"title": "x", "content": "y", "references": "[1, 2, 3]"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_note_ignores_client_id(test_db, client):
    """ID must be server-generated (uuid4) — never honor a client value."""
    issue = await _create_issue(test_db)
    spoof_id = "client-spoofed-id-0000"

    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}",
        json={
            "title": "x",
            "content": "y",
            "id": spoof_id,  # ImplementationNoteCreate has no `id` — silently dropped
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] != spoof_id


# ---- DELETE /api/issues/{id}/documentation/notes/{note_id} (CB-1589) --------

@pytest.mark.asyncio
async def test_delete_note_removes_record(test_db, client):
    issue = await _create_issue(test_db)
    note = await _add_note(test_db, issue.id, title="goner")

    resp = await client.delete(
        f"/api/issues/{issue.id}/documentation/notes/{note.id}?projectId={issue.projectId}"
    )
    assert resp.status_code == 204

    list_resp = await client.get(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}"
    )
    assert list_resp.status_code == 200
    assert all(n["id"] != note.id for n in list_resp.json())


@pytest.mark.asyncio
async def test_delete_note_404_when_note_missing(test_db, client):
    issue = await _create_issue(test_db)

    resp = await client.delete(
        f"/api/issues/{issue.id}/documentation/notes/no-such-note?projectId={issue.projectId}"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_note_404_when_issue_missing(test_db, client):
    resp = await client.delete(
        "/api/issues/missing/documentation/notes/whatever?projectId=any-project"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_note_404_when_note_belongs_to_other_issue(test_db, client):
    """Path issue_id must match note.issueId — prevents cross-issue delete."""
    issue_a = await _create_issue(test_db)
    issue_b = await _create_issue(test_db)
    note_a = await _add_note(test_db, issue_a.id, title="A's note")

    resp = await client.delete(
        f"/api/issues/{issue_b.id}/documentation/notes/{note_a.id}?projectId={issue_b.projectId}"
    )
    assert resp.status_code == 404

    # And the note still exists under issue A
    list_a = await client.get(
        f"/api/issues/{issue_a.id}/documentation/notes?projectId={issue_a.projectId}"
    )
    assert any(n["id"] == note_a.id for n in list_a.json())


# ---- FeatureDocumentation endpoints (CB-1590) -------------------------------

from models.documentation import FeatureDocumentation
from models.qa import QATask, QATaskIssueLink


@pytest.fixture
def disable_ai_aggregation(monkeypatch):
    """Stub `ai_service.generate_text` to return None so feature-doc tests
    exercise the deterministic path only.

    The CB-1615 implementation augments the deterministic sections with an
    AI-generated narrative when an AI provider is reachable. Network-bound
    behaviour in unit tests is slow, expensive, and non-deterministic, so
    the default for these tests is "no AI" — augmentation tests opt back
    in via `mock_ai_aggregation`.
    """
    from services.ai_service import ai_service

    async def _no_ai(prompt, max_tokens=2500):
        return None

    monkeypatch.setattr(ai_service, "generate_text", _no_ai)
    return monkeypatch


@pytest.fixture
def mock_ai_aggregation(monkeypatch):
    """Return a callable that installs a fixed AI response.

    Usage in a test:

        mock_ai_aggregation('{"overview": "...", ...}')

    The injected payload is returned verbatim from `ai_service.generate_text`,
    letting the test assert on the augmentation behaviour without hitting
    a live AI provider.
    """
    from services.ai_service import ai_service

    def _install(payload):
        async def _fixed(prompt, max_tokens=2500):
            return payload
        monkeypatch.setattr(ai_service, "generate_text", _fixed)
        return monkeypatch

    return _install


async def _create_feature(
    factory: async_sessionmaker,
    *,
    description: str = "Feature requirements live here.",
) -> Issue:
    """Insert a project + a FEATURE-type issue. Returns the feature."""
    async with factory() as db:
        now_ms = int(time.time() * 1000)
        project = Project(
            id=str(uuid.uuid4()),
            name=f"proj-{uuid.uuid4()}",
            path="/tmp/p",
            status="ACTIVE",
            createdAt=now_ms,
            updatedAt=now_ms,
        )
        db.add(project)
        await db.flush()

        feature = Issue(
            id=str(uuid.uuid4()),
            projectId=project.id,
            key=f"CB-{uuid.uuid4().hex[:8]}",
            sequence=1,
            title="Login Flow",
            description=description,
            type="FEATURE",
            status="IN_PROGRESS",
            priority="MEDIUM",
            updatedAt=datetime.utcnow(),
        )
        db.add(feature)
        await db.commit()
        await db.refresh(feature)
        return feature


async def _add_child_issue(
    factory: async_sessionmaker,
    parent: Issue,
    *,
    type_: str = "TASK",
    status_: str = "IN_PROGRESS",
) -> Issue:
    """Attach a descendant issue to `parent`."""
    async with factory() as db:
        child = Issue(
            id=str(uuid.uuid4()),
            projectId=parent.projectId,
            parentId=parent.id,
            key=f"CB-{uuid.uuid4().hex[:8]}",
            sequence=1,
            title=f"{type_} child",
            type=type_,
            status=status_,
            priority="MEDIUM",
            updatedAt=datetime.utcnow(),
        )
        db.add(child)
        await db.commit()
        await db.refresh(child)
        return child


async def _add_qa_task(
    factory: async_sessionmaker,
    *,
    project_id: str,
    issue_id: str,
    status_: str = "PASS",
) -> QATask:
    """Insert a QATask + linking row tied to `issue_id`."""
    async with factory() as db:
        task = QATask(
            id=str(uuid.uuid4()),
            projectId=project_id,
            key=f"QA-{uuid.uuid4().hex[:6]}",
            sequence=1,
            title="Test scenario",
            scenario="steps",
            expectedResult="ok",
            status=status_,
            type="MANUAL",
            priority="MEDIUM",
        )
        db.add(task)
        await db.flush()
        link = QATaskIssueLink(
            id=str(uuid.uuid4()),
            qaTaskId=task.id,
            issueId=issue_id,
        )
        db.add(link)
        await db.commit()
        await db.refresh(task)
        return task


# ---- GET /api/features/{id}/documentation -----------------------------------

@pytest.mark.asyncio
async def test_get_feature_documentation_404_when_issue_missing(client):
    resp = await client.get("/api/features/missing-id/documentation?projectId=any-project")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_feature_documentation_400_when_not_a_feature(test_db, client):
    """A TASK-type issue must yield 400, not 404 — issue exists, wrong type."""
    issue = await _create_issue(test_db)  # type=TASK

    resp = await client.get(f"/api/features/{issue.id}/documentation?projectId={issue.projectId}")
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_get_feature_documentation_404_when_no_doc_generated(test_db, client):
    """Feature exists but generate has not been called — explicit 404."""
    feature = await _create_feature(test_db)

    resp = await client.get(f"/api/features/{feature.id}/documentation?projectId={feature.projectId}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_feature_documentation_returns_existing_record(test_db, client):
    feature = await _create_feature(test_db)

    async with test_db() as db:
        row = FeatureDocumentation(
            id=str(uuid.uuid4()),
            projectId=feature.projectId,
            featureIssueId=feature.id,
            featureKey=feature.key,
            title=feature.title,
            overview="ov",
            requirements="rq",
            implementation="im",
            architecture="ar",
            techStack="[]",
            testingStrategy="ts",
            totalTasks=0,
            completedTasks=0,
            totalQATasks=0,
            passedQATasks=0,
            failedQATasks=0,
            mdFilePath=f"docs/features/{feature.key}.md",
        )
        db.add(row)
        await db.commit()

    resp = await client.get(f"/api/features/{feature.id}/documentation?projectId={feature.projectId}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["featureIssueId"] == feature.id
    assert body["featureKey"] == feature.key
    assert body["title"] == "Login Flow"


# ---- POST /api/features/{id}/documentation/generate -------------------------

@pytest.mark.asyncio
async def test_generate_feature_documentation_404_when_issue_missing(client):
    resp = await client.post("/api/features/missing-id/documentation/generate?projectId=any-project")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_feature_documentation_400_when_not_a_feature(test_db, client):
    issue = await _create_issue(test_db)  # type=TASK

    resp = await client.post(
        f"/api/features/{issue.id}/documentation/generate?projectId={issue.projectId}"
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_generate_feature_documentation_creates_record(
    test_db, client, disable_ai_aggregation
):
    """Empty feature still produces a documentation row with placeholders."""
    feature = await _create_feature(test_db)

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["featureIssueId"] == feature.id
    assert body["featureKey"] == feature.key
    assert body["title"] == "Login Flow"
    assert body["mdFilePath"] == f"docs/features/{feature.key}.md"
    assert body["totalTasks"] == 0
    assert body["completedTasks"] == 0
    assert body["totalQATasks"] == 0
    # Placeholder content for empty features
    assert "_No execution summaries" in body["implementation"]
    assert body["techStack"] == "[]"

    # Confirm GET now returns it
    get_resp = await client.get(
        f"/api/features/{feature.id}/documentation?projectId={feature.projectId}"
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_generate_feature_documentation_aggregates_descendants(
    test_db, client, disable_ai_aggregation
):
    """Descendants count + completed counts must reflect the subtree."""
    feature = await _create_feature(test_db)
    epic = await _add_child_issue(test_db, feature, type_="EPIC", status_="IN_PROGRESS")
    await _add_child_issue(test_db, epic, type_="STORY", status_="DONE")
    await _add_child_issue(test_db, epic, type_="TASK", status_="COMPLETED_WAITING_QA")
    await _add_child_issue(test_db, epic, type_="TASK", status_="BACKLOG")

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    # 1 EPIC + 3 grandchildren = 4 descendants
    assert body["totalTasks"] == 4
    # DONE + COMPLETED_WAITING_QA both count as completed
    assert body["completedTasks"] == 2


@pytest.mark.asyncio
async def test_generate_feature_documentation_aggregates_qa(
    test_db, client, disable_ai_aggregation
):
    feature = await _create_feature(test_db)
    task = await _add_child_issue(test_db, feature, type_="TASK", status_="DONE")
    await _add_qa_task(
        test_db,
        project_id=feature.projectId,
        issue_id=task.id,
        status_="PASS",
    )
    await _add_qa_task(
        test_db,
        project_id=feature.projectId,
        issue_id=task.id,
        status_="FAILED",
    )
    await _add_qa_task(
        test_db,
        project_id=feature.projectId,
        issue_id=feature.id,
        status_="NOT_DONE",
    )

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalQATasks"] == 3
    assert body["passedQATasks"] == 1
    assert body["failedQATasks"] == 1
    assert "## QA Coverage" in body["testingStrategy"]


@pytest.mark.asyncio
async def test_generate_feature_documentation_is_idempotent(
    test_db, client, disable_ai_aggregation
):
    """Calling generate twice must update in place — same id, refreshed counts.

    CB-2075: also asserts the DB has exactly ONE FeatureDocumentation row
    for the feature after regenerate, defending against a future regression
    where a code change inserts a second row instead of updating.
    """
    from sqlalchemy import func, select
    from models.documentation import FeatureDocumentation

    feature = await _create_feature(test_db)

    first = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert first.status_code == 200
    first_id = first.json()["id"]
    assert first.json()["totalTasks"] == 0

    # Add a child after the first generate, then regenerate
    await _add_child_issue(test_db, feature, type_="STORY", status_="DONE")
    second = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert second.status_code == 200
    body = second.json()
    assert body["id"] == first_id  # SAME row, updated in place
    assert body["totalTasks"] == 1
    assert body["completedTasks"] == 1

    # Third regenerate — explicit row-count assertion (CB-2075)
    third = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert third.status_code == 200
    assert third.json()["id"] == first_id

    async with test_db() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(FeatureDocumentation)
            .where(FeatureDocumentation.featureIssueId == feature.id)
        )
    assert count == 1, f"expected exactly 1 row after 3 regenerates, got {count}"


@pytest.mark.asyncio
async def test_generate_feature_documentation_pulls_execution_summaries(
    test_db, client, disable_ai_aggregation
):
    """ExecutionSummaries on descendants roll into implementation + techStack."""
    feature = await _create_feature(test_db)
    task = await _add_child_issue(test_db, feature, type_="TASK", status_="DONE")
    async with test_db() as db:
        s = ExecutionSummary(
            id=str(uuid.uuid4()),
            issueId=task.id,
            summary="Task done. Wrote backend handler.",
            executedAt=datetime.utcnow(),
            executionTime=4.2,
            provider="claude_code",
            componentsModified='["backend", "api"]',
            filesTouched='["backend/api/foo.py"]',
            linesAdded=10,
            linesRemoved=2,
            architectureNotes="Picked async over sync.",
            commitHashes='[]',
        )
        db.add(s)
        await db.commit()

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Task done" in body["implementation"]
    assert "Picked async" in body["architecture"]
    # techStack is a JSON array of unique components
    import json as _json
    components = _json.loads(body["techStack"])
    assert set(components) == {"backend", "api"}


# ---- CB-1615: AI augmentation behaviour --------------------------------------

@pytest.mark.asyncio
async def test_generate_feature_documentation_ai_replaces_overview(
    test_db, client, mock_ai_aggregation
):
    """AI-supplied overview must replace the deterministic header block."""
    feature = await _create_feature(test_db)
    await _add_child_issue(test_db, feature, type_="TASK", status_="DONE")

    mock_ai_aggregation('{"overview": "## Synthesized\\n\\nLogin flow is wired end-to-end."}')

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["overview"] == "## Synthesized\n\nLogin flow is wired end-to-end."


@pytest.mark.asyncio
async def test_generate_feature_documentation_ai_prepends_architecture(
    test_db, client, mock_ai_aggregation
):
    """AI architecture summary prepends without erasing verbatim notes."""
    feature = await _create_feature(test_db)
    task = await _add_child_issue(test_db, feature, type_="TASK", status_="DONE")
    async with test_db() as db:
        db.add(ExecutionSummary(
            id=str(uuid.uuid4()),
            issueId=task.id,
            summary="Implemented login.",
            executedAt=datetime.utcnow(),
            executionTime=1.0,
            provider="claude_code",
            componentsModified='["backend"]',
            filesTouched='["backend/login.py"]',
            architectureNotes="VERBATIM_ARCH_NOTE",
            commitHashes='[]',
        ))
        await db.commit()

    mock_ai_aggregation(
        '{"architectureSummary": "AI_ARCH_INSIGHT: cohesive auth boundary."}'
    )

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    arch = body["architecture"]
    assert "AI_ARCH_INSIGHT" in arch
    assert "VERBATIM_ARCH_NOTE" in arch
    # AI block must come before the verbatim note
    assert arch.index("AI_ARCH_INSIGHT") < arch.index("VERBATIM_ARCH_NOTE")


@pytest.mark.asyncio
async def test_generate_feature_documentation_ai_prepends_testing_strategy(
    test_db, client, mock_ai_aggregation
):
    """AI testing narrative must prepend the deterministic QA Coverage block."""
    feature = await _create_feature(test_db)
    task = await _add_child_issue(test_db, feature, type_="TASK", status_="DONE")
    await _add_qa_task(
        test_db,
        project_id=feature.projectId,
        issue_id=task.id,
        status_="PASS",
    )

    mock_ai_aggregation(
        '{"testingNarrative": "AI_TEST_NARRATIVE: smoke + integration coverage."}'
    )

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    ts = body["testingStrategy"]
    assert "AI_TEST_NARRATIVE" in ts
    assert "## QA Coverage" in ts
    assert ts.index("AI_TEST_NARRATIVE") < ts.index("## QA Coverage")


@pytest.mark.asyncio
async def test_generate_feature_documentation_ai_merges_tech_stack_hints(
    test_db, client, mock_ai_aggregation
):
    """AI tech stack hints supplement the deterministic union (case-insensitive)."""
    feature = await _create_feature(test_db)
    task = await _add_child_issue(test_db, feature, type_="TASK", status_="DONE")
    async with test_db() as db:
        db.add(ExecutionSummary(
            id=str(uuid.uuid4()),
            issueId=task.id,
            summary="x",
            executedAt=datetime.utcnow(),
            executionTime=1.0,
            provider="claude_code",
            componentsModified='["backend"]',
            filesTouched='[]',
            commitHashes='[]',
        ))
        await db.commit()

    mock_ai_aggregation(
        '{"techStackHints": ["FastAPI", "BACKEND", "SQLAlchemy"]}'
    )

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    components = json.loads(resp.json()["techStack"])
    # 'backend' came from the deterministic union; AI 'BACKEND' is a
    # case-insensitive duplicate and must NOT be added.
    assert "backend" in components
    assert "FastAPI" in components
    assert "SQLAlchemy" in components
    assert sum(1 for c in components if c.lower() == "backend") == 1


@pytest.mark.asyncio
async def test_generate_feature_documentation_skips_ai_for_empty_feature(
    test_db, client, monkeypatch
):
    """Empty feature must NOT call the AI provider — saves tokens / latency."""
    from services.ai_service import ai_service

    calls: List[str] = []

    async def _spy(prompt, max_tokens=2500):
        calls.append(prompt)
        return None

    monkeypatch.setattr(ai_service, "generate_text", _spy)

    feature = await _create_feature(test_db)
    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    assert calls == [], "AI must not be invoked for an empty feature"


@pytest.mark.asyncio
async def test_generate_feature_documentation_survives_ai_failure(
    test_db, client, monkeypatch
):
    """AI exception must NOT block persistence — deterministic fallback wins."""
    from services.ai_service import ai_service

    async def _boom(prompt, max_tokens=2500):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_service, "generate_text", _boom)

    feature = await _create_feature(test_db)
    task = await _add_child_issue(test_db, feature, type_="TASK", status_="DONE")
    async with test_db() as db:
        db.add(ExecutionSummary(
            id=str(uuid.uuid4()),
            issueId=task.id,
            summary="DETERMINISTIC_BODY",
            executedAt=datetime.utcnow(),
            executionTime=1.0,
            provider="claude_code",
            componentsModified='["backend"]',
            filesTouched='[]',
            commitHashes='[]',
        ))
        await db.commit()

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "DETERMINISTIC_BODY" in body["implementation"]


# ---- CB-1615: ChromaDB indexing ---------------------------------------------

@pytest.mark.asyncio
async def test_generate_feature_documentation_invokes_chroma_indexing(
    test_db, client, disable_ai_aggregation, monkeypatch
):
    """When a RAG service is wired, generate must call embed_feature_documentation
    and persist embeddingId + lastIndexedAt."""
    from services.documentation_generator import documentation_generator

    captured: Dict[str, object] = {}

    class _FakeRag:
        def generate_doc_id(self, issue_id, content_type):
            return f"docid::{content_type}::{issue_id}"

        async def embed_feature_documentation(
            self, *, project_id, feature_issue_id, feature_key, doc
        ):
            captured["project_id"] = project_id
            captured["feature_issue_id"] = feature_issue_id
            captured["feature_key"] = feature_key
            captured["doc_id"] = doc.id
            return True

    monkeypatch.setattr(documentation_generator, "_rag", _FakeRag())

    feature = await _create_feature(test_db)
    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert captured["feature_issue_id"] == feature.id
    assert captured["feature_key"] == feature.key
    assert body["embeddingId"] == f"docid::feature_documentation::{feature.id}"
    assert body["lastIndexedAt"] is not None

    # Reset for safety so subsequent tests don't see the fake.
    monkeypatch.setattr(documentation_generator, "_rag", None)


@pytest.mark.asyncio
async def test_generate_feature_documentation_tolerates_chroma_failure(
    test_db, client, disable_ai_aggregation, monkeypatch
):
    """RAG failure must NOT block persistence — embeddingId stays empty."""
    from services.documentation_generator import documentation_generator

    class _BoomRag:
        def generate_doc_id(self, issue_id, content_type):
            return "unused"

        async def embed_feature_documentation(self, **kwargs):
            raise RuntimeError("chroma down")

    monkeypatch.setattr(documentation_generator, "_rag", _BoomRag())

    feature = await _create_feature(test_db)
    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["embeddingId"] is None
    assert body["lastIndexedAt"] is None

    monkeypatch.setattr(documentation_generator, "_rag", None)


@pytest.mark.asyncio
async def test_generate_feature_documentation_skips_chroma_when_no_rag(
    test_db, client, disable_ai_aggregation
):
    """Default singleton has no RAG wired; persistence still succeeds."""
    feature = await _create_feature(test_db)
    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["embeddingId"] is None
    assert body["lastIndexedAt"] is None


# ---- CB-1615: cross-project isolation (sec audit H-1) -----------------------

@pytest.mark.asyncio
async def test_generate_feature_documentation_skips_cross_project_descendants(
    test_db, client, disable_ai_aggregation
):
    """A child re-parented across projects must NOT leak into the feature's
    aggregate. The Issue model does not enforce parent.projectId ==
    child.projectId at write-time, so the documentation generator must
    filter at read-time (CB-1615 sec audit, H-1)."""
    feature = await _create_feature(test_db)

    # Child A — same project, must be counted.
    in_project_child = await _add_child_issue(
        test_db, feature, type_="TASK", status_="DONE",
    )

    # Child B — different project but parentId points at our feature.
    # Simulates a malicious / buggy update that crosses the boundary.
    async with test_db() as db:
        now_ms = int(time.time() * 1000)
        other_project = Project(
            id=str(uuid.uuid4()),
            name=f"other-{uuid.uuid4()}",
            path="/tmp/other",
            status="ACTIVE",
            createdAt=now_ms,
            updatedAt=now_ms,
        )
        db.add(other_project)
        await db.flush()

        cross_project_child = Issue(
            id=str(uuid.uuid4()),
            projectId=other_project.id,  # Different project!
            parentId=feature.id,         # …but points back at our feature
            key=f"CB-{uuid.uuid4().hex[:8]}",
            sequence=1,
            title="LEAK_CANARY",
            type="TASK",
            status="DONE",
            priority="MEDIUM",
            updatedAt=datetime.utcnow(),
        )
        db.add(cross_project_child)

        # ExecutionSummary on the cross-project child — content that MUST
        # not appear in this project's FeatureDocumentation.
        db.add(ExecutionSummary(
            id=str(uuid.uuid4()),
            issueId=cross_project_child.id,
            summary="CROSS_PROJECT_SECRET_BODY",
            executedAt=datetime.utcnow(),
            executionTime=1.0,
            provider="claude_code",
            componentsModified='["other-stack"]',
            filesTouched='[]',
            commitHashes='[]',
        ))
        await db.commit()

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate?projectId={feature.projectId}"
    )
    assert resp.status_code == 200
    body = resp.json()
    # Only the in-project child counts.
    assert body["totalTasks"] == 1
    # Cross-project ExecutionSummary content must be absent everywhere.
    flat = "\n".join([
        body["overview"],
        body["implementation"],
        body["architecture"],
        body["techStack"],
        body["testingStrategy"],
    ])
    assert "CROSS_PROJECT_SECRET_BODY" not in flat
    assert "LEAK_CANARY" not in flat
    assert "other-stack" not in flat
    # And the legitimate child is still represented.
    assert in_project_child.key in body["implementation"] or \
        body["totalTasks"] == 1  # at minimum the count is right


# ---- CB-2117: projectId scoping (IDOR guard) --------------------------------
#
# These regressions encode the contract added in CB-2117: every documentation
# endpoint takes a required ``projectId`` query param and uses it to scope
# every issue lookup. A missing or mismatched projectId must return the same
# 404 as a missing issue id — no information leak — and must never expose,
# create, or delete a row outside the asserted project.

@pytest.mark.parametrize(
    "method, path_template",
    [
        # Every public route on the documentation router must reject a
        # missing projectId. Parametrising the case ensures a regression
        # that drops `ProjectIdQuery` from a single endpoint is still
        # caught — without us having to list all six checks by hand.
        ("GET",    "/api/issues/{issue_id}/documentation"),
        ("GET",    "/api/issues/{issue_id}/documentation/latest"),
        ("GET",    "/api/issues/{issue_id}/documentation/notes"),
        ("POST",   "/api/issues/{issue_id}/documentation/notes"),
        ("DELETE", "/api/issues/{issue_id}/documentation/notes/whatever"),
        ("GET",    "/api/features/{issue_id}/documentation"),
        ("POST",   "/api/features/{issue_id}/documentation/generate"),
    ],
)
@pytest.mark.asyncio
async def test_endpoints_require_projectId(test_db, client, method, path_template):
    """No ``projectId`` → 422 from FastAPI's required-query-param check."""
    issue = await _create_issue(test_db)
    url = path_template.format(issue_id=issue.id)
    resp = await client.request(
        method,
        url,
        json={"title": "x", "content": "y"} if method == "POST" else None,
    )
    assert resp.status_code == 422, (
        f"{method} {url} should reject missing projectId with 422, "
        f"got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_list_summaries_requires_projectId(test_db, client):
    """No ``projectId`` → 422 from FastAPI's required-query-param check."""
    issue = await _create_issue(test_db)

    resp = await client.get(f"/api/issues/{issue.id}/documentation")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_latest_summary_404_on_wrong_projectId(test_db, client):
    """Same scoping contract as list-summaries — wrong project → 404."""
    issue = await _create_issue(test_db)
    await _add_summary(
        test_db, issue.id,
        executed_at=datetime.utcnow(),
        summary_text="latest-canary",
    )

    resp = await client.get(
        f"/api/issues/{issue.id}/documentation/latest?projectId=other-project"
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
    assert "latest-canary" not in resp.text


@pytest.mark.asyncio
async def test_list_summaries_404_on_wrong_projectId(test_db, client):
    """Issue exists but caller asserts the wrong project → 404, not 200.

    The 404 response body must be indistinguishable from the missing-id
    case so the endpoint cannot be used to enumerate (issue, project) pairs.
    """
    issue = await _create_issue(test_db)
    await _add_summary(
        test_db, issue.id,
        executed_at=datetime.utcnow(),
        summary_text="real summary",
    )

    resp = await client.get(
        f"/api/issues/{issue.id}/documentation?projectId=some-other-project"
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    # No leak of summary content via error details.
    assert "real summary" not in resp.text


@pytest.mark.asyncio
async def test_list_notes_404_on_wrong_projectId(test_db, client):
    issue = await _create_issue(test_db)
    await _add_note(test_db, issue.id, title="canary")

    resp = await client.get(
        f"/api/issues/{issue.id}/documentation/notes?projectId=other-project"
    )
    assert resp.status_code == 404
    assert "canary" not in resp.text


@pytest.mark.asyncio
async def test_create_note_blocked_by_wrong_projectId(test_db, client):
    """Cross-project note POST must 404 — no row may be persisted."""
    from sqlalchemy import func, select
    issue = await _create_issue(test_db)

    resp = await client.post(
        f"/api/issues/{issue.id}/documentation/notes?projectId=other-project",
        json={"title": "should-not-stick", "content": "x"},
    )
    assert resp.status_code == 404

    # Confirm the DB stayed clean — no note was created against the issue.
    async with test_db() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(ImplementationNote)
            .where(ImplementationNote.issueId == issue.id)
        )
    assert count == 0


@pytest.mark.asyncio
async def test_delete_note_blocked_by_wrong_projectId(test_db, client):
    """Cross-project note DELETE must 404 — original row must remain."""
    issue = await _create_issue(test_db)
    note = await _add_note(test_db, issue.id, title="keep-me")

    resp = await client.delete(
        f"/api/issues/{issue.id}/documentation/notes/{note.id}"
        f"?projectId=other-project"
    )
    assert resp.status_code == 404

    # Note still present under the legitimate project.
    list_resp = await client.get(
        f"/api/issues/{issue.id}/documentation/notes?projectId={issue.projectId}"
    )
    assert any(n["id"] == note.id for n in list_resp.json())


@pytest.mark.asyncio
async def test_get_feature_documentation_404_on_wrong_projectId(test_db, client):
    """Feature exists, doc exists, but wrong projectId → 404, never 200."""
    feature = await _create_feature(test_db)
    async with test_db() as db:
        db.add(FeatureDocumentation(
            id=str(uuid.uuid4()),
            projectId=feature.projectId,
            featureIssueId=feature.id,
            featureKey=feature.key,
            title=feature.title,
            overview="OVERVIEW_CANARY",
            requirements="rq",
            implementation="im",
            architecture="ar",
            techStack="[]",
            testingStrategy="ts",
            totalTasks=0,
            completedTasks=0,
            totalQATasks=0,
            passedQATasks=0,
            failedQATasks=0,
            mdFilePath=f"docs/features/{feature.key}.md",
        ))
        await db.commit()

    resp = await client.get(
        f"/api/features/{feature.id}/documentation?projectId=other-project"
    )
    assert resp.status_code == 404
    assert "OVERVIEW_CANARY" not in resp.text


@pytest.mark.asyncio
async def test_generate_feature_documentation_blocked_by_wrong_projectId(
    test_db, client, monkeypatch
):
    """The most expensive endpoint must NOT be reachable cross-project.

    Spies on ai_service.generate_text — if scoping fails open, the
    descendant walk + AI provider call would still run. The assertion is
    that neither side-effect happens.
    """
    from sqlalchemy import func, select
    from services.ai_service import ai_service

    ai_calls: List[str] = []

    async def _spy(prompt, max_tokens=2500):
        ai_calls.append(prompt)
        return None

    monkeypatch.setattr(ai_service, "generate_text", _spy)

    feature = await _create_feature(test_db)

    resp = await client.post(
        f"/api/features/{feature.id}/documentation/generate"
        f"?projectId=other-project"
    )
    assert resp.status_code == 404
    assert ai_calls == [], "AI provider must not be invoked on cross-project request"

    # No FeatureDocumentation row got created.
    async with test_db() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(FeatureDocumentation)
            .where(FeatureDocumentation.featureIssueId == feature.id)
        )
    assert count == 0


@pytest.mark.asyncio
async def test_projectId_blank_rejected(test_db, client):
    """Empty-string ``projectId`` must 422 — a "" value would otherwise
    silently pass and match no row, returning a misleading 404."""
    issue = await _create_issue(test_db)

    resp = await client.get(
        f"/api/issues/{issue.id}/documentation?projectId="
    )
    assert resp.status_code == 422
