"""
Pytest fixtures and configuration for ProjectsManagerWebV2 Backend tests.

This module provides shared fixtures for:
- FastAPI test client
- Database session management
- Mock services
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

# Import the FastAPI app
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.main import app


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client for testing FastAPI endpoints.

    Usage:
        async def test_endpoint(async_client):
            response = await async_client.get("/api/health")
            assert response.status_code == 200
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_anthropic_client():
    """
    Mock Anthropic client for AI-related tests.

    Prevents actual API calls during testing.
    """
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=MagicMock(
        content=[MagicMock(text="Mocked AI response")]
    ))
    return mock_client


@pytest.fixture
def mock_chroma_client():
    """
    Mock ChromaDB client for RAG-related tests.

    Prevents actual vector database operations during testing.
    """
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.query = MagicMock(return_value={
        "ids": [["doc1", "doc2"]],
        "documents": [["Document 1 content", "Document 2 content"]],
        "metadatas": [[{"source": "test"}, {"source": "test"}]],
        "distances": [[0.1, 0.2]]
    })
    mock_collection.add = MagicMock()
    mock_client.get_or_create_collection = MagicMock(return_value=mock_collection)
    return mock_client


@pytest.fixture
def sample_issue_data():
    """Sample issue data for testing CRUD operations."""
    return {
        "title": "Test Issue",
        "description": "This is a test issue description",
        "type": "BUG",
        "status": "BACKLOG",
        "priority": "MEDIUM",
        "projectId": "test-project-id"
    }


@pytest.fixture
def sample_project_data():
    """Sample project data for testing."""
    return {
        "id": "test-project-id",
        "name": "Test Project",
        "description": "A test project for unit testing",
        "path": "/path/to/test/project"
    }


@pytest.fixture
def sample_qa_item_data():
    """Sample QA item data for testing."""
    return {
        "title": "Test QA Item",
        "description": "Test description for QA",
        "status": "PENDING",
        "issueId": "test-issue-id"
    }


class MockResponse:
    """Helper class for mocking HTTP responses."""

    def __init__(self, json_data: dict, status_code: int = 200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def mock_http_response():
    """Factory fixture for creating mock HTTP responses."""
    def _create_response(json_data: dict, status_code: int = 200):
        return MockResponse(json_data, status_code)
    return _create_response
