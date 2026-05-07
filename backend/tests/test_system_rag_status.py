"""CB-2045: GET /api/system/rag/status endpoint contract tests.

Wires up an isolated FastAPI app + RAGService dependency override so the
endpoint can be exercised without touching the real ChromaDB instance.

Verifies:
  * 200 + full payload shape with mode/host/port/collections/total_docs/healthy.
  * UNINITIALIZED snapshot when RAGService never connected.
  * PERSISTENT snapshot reports the abspath as host and port=0.
  * Endpoint never raises 5xx even when the underlying client misbehaves —
    `healthy=False` is the surface, not an exception.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from api.deps import get_rag  # noqa: E402
from api.system import router as system_router  # noqa: E402
from app.errors import setup_exception_handlers  # noqa: E402
from services.rag_service import RAGService  # noqa: E402


def _make_app(rag: RAGService) -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(system_router, prefix="/api")
    app.dependency_overrides[get_rag] = lambda: rag
    return app


@pytest_asyncio.fixture
async def client_factory():
    clients: list[AsyncClient] = []

    async def _make(rag: RAGService) -> AsyncClient:
        app = _make_app(rag)
        transport = ASGITransport(app=app)
        c = AsyncClient(transport=transport, base_url="http://test")
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()


async def test_endpoint_returns_uninitialized_payload_when_client_missing(
    client_factory,
):
    rag = RAGService()
    client = await client_factory(rag)

    response = await client.get("/api/system/rag/status")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "mode": "UNINITIALIZED",
        "host": "",
        "port": 0,
        "collections": [],
        "total_docs": 0,
        "healthy": False,
    }


async def test_endpoint_returns_http_payload_with_collection_counts(
    client_factory,
):
    """Manually wire HTTP-mode state on the service — no real ChromaDB call."""
    col = MagicMock()
    col.name = "project_aaaaaa"
    col.count = MagicMock(return_value=7)

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[col])

    rag = RAGService()
    rag._client = fake_client
    rag._mode = "HTTP"
    rag._mode_detail = "chromadb:8402"

    client = await client_factory(rag)
    response = await client.get("/api/system/rag/status")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "HTTP"
    assert data["host"] == "chromadb"
    assert data["port"] == 8402
    assert data["collections"] == [{"name": "project_aaaaaa", "count": 7}]
    assert data["total_docs"] == 7
    assert data["healthy"] is True


async def test_endpoint_returns_persistent_payload_with_abspath_host(
    client_factory,
):
    col = MagicMock()
    col.name = "project_zzzzzz"
    col.count = MagicMock(return_value=2)

    fake_client = MagicMock()
    fake_client.list_collections = MagicMock(return_value=[col])

    rag = RAGService()
    rag._client = fake_client
    rag._mode = "PERSISTENT"
    rag._mode_detail = "/abs/path/to/chroma"

    client = await client_factory(rag)
    response = await client.get("/api/system/rag/status")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "PERSISTENT"
    assert data["host"] == "/abs/path/to/chroma"
    assert data["port"] == 0
    assert data["total_docs"] == 2
    assert data["healthy"] is True


async def test_endpoint_returns_unhealthy_when_list_collections_fails(
    client_factory,
):
    fake_client = MagicMock()
    fake_client.list_collections = MagicMock(side_effect=RuntimeError("boom"))

    rag = RAGService()
    rag._client = fake_client
    rag._mode = "PERSISTENT"
    rag._mode_detail = "/abs/path/to/chroma"

    client = await client_factory(rag)
    response = await client.get("/api/system/rag/status")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "PERSISTENT"
    assert data["collections"] == []
    assert data["total_docs"] == 0
    assert data["healthy"] is False
