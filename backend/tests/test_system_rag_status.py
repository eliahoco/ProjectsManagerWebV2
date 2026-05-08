"""CB-2045: GET /api/system/rag/status endpoint contract tests.

Wires up an isolated FastAPI app + RAGService dependency override so the
endpoint can be exercised without touching the real ChromaDB instance.

Verifies:
  * 200 + full payload shape with mode/host/port/collections/total_docs/healthy.
  * UNINITIALIZED snapshot when RAGService never connected.
  * PERSISTENT snapshot reports the abspath as endpoint and port=0.
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
        "endpoint": "",
        "port": 0,
        "fallback_active": False,
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
    rag._endpoint = "chromadb:8402"

    client = await client_factory(rag)
    response = await client.get("/api/system/rag/status")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "HTTP"
    assert data["endpoint"] == "chromadb"
    assert data["port"] == 8402
    assert data["fallback_active"] is False
    # CB-2217: collection rows are anonymous on the HTTP surface — only
    # `count` is exposed so the status endpoint cannot be used to
    # enumerate which projects exist via the `project_<cuid_prefix>`
    # collection naming.
    assert data["collections"] == [{"count": 7}]
    assert "project_aaaaaa" not in response.text
    # Defence-in-depth: regex against any `project_<prefix>` shape so a
    # different mock name in a future test edit can't bypass the
    # substring check above (code-reviewer follow-up).
    import re as _re

    leak_pattern = _re.compile(r"project_\w{4,}")
    leak_match = leak_pattern.search(response.text)
    assert leak_match is None, (
        f"CB-2217 regression: collection-name-shaped value leaked in "
        f"HTTP payload: {leak_match.group(0) if leak_match else ''!r}"
    )
    assert data["total_docs"] == 7
    assert data["healthy"] is True


async def test_endpoint_returns_persistent_payload_without_leaking_abspath(
    client_factory,
):
    """CB-2216: PERSISTENT-mode payload must surface fallback via the
    `fallback_active` boolean, not by echoing the embedded-store abspath.

    The endpoint is reachable by Origin-less local callers (curl, sibling
    services) — `validate_origin` lets server-to-server requests through
    by design. Echoing `_endpoint` (the abspath) gave a future host-
    compromise attacker the user-named volume layout. Sanitize at the
    payload boundary; keep the abspath internal for log surfaces only.
    """
    col = MagicMock()
    col.name = "project_zzzzzz"
    col.count = MagicMock(return_value=2)

    fake_client = MagicMock()
    fake_client.list_collections = MagicMock(return_value=[col])

    rag = RAGService()
    rag._client = fake_client
    rag._mode = "PERSISTENT"
    rag._endpoint = "/abs/path/to/chroma"

    client = await client_factory(rag)
    response = await client.get("/api/system/rag/status")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "PERSISTENT"
    assert data["endpoint"] == ""
    assert data["fallback_active"] is True
    assert data["port"] == 0
    # CB-2217: collection rows are anonymous — only `count` is exposed.
    assert data["collections"] == [{"count": 2}]
    assert "project_zzzzzz" not in response.text
    assert data["total_docs"] == 2
    assert data["healthy"] is True
    # Defence-in-depth: serialize the whole response and confirm the
    # abspath is not present anywhere in the JSON. Prevents a future
    # additive field from re-leaking via a different key name.
    assert "/abs/path/to/chroma" not in response.text

    # Stronger pin: regex on common leak-prone path roots (macOS, Linux,
    # /tmp, /private/var). Catches a future field that leaks a *different*
    # abspath the substring check above wouldn't see.
    import re as _re

    leak_pattern = _re.compile(
        r'"(?:/Volumes|/Users|/home|/root|/private/var|/tmp)/[^"]+"'
    )
    match = leak_pattern.search(response.text)
    assert match is None, (
        f"Filesystem-path-shaped value leaked in HTTP payload: {match.group(0) if match else ''!r}"
    )


def test_rag_collection_status_model_forbids_extra_fields():
    """CB-2217 follow-up (code-reviewer M-2): the structural pin that
    catches a future regression where someone adds a name-shaped field
    (id/slug/label/hashed-name) to `RagCollectionStatus` without
    redaction review.

    Pydantic v2's default `extra="ignore"` would silently let such a
    field through `get_status_payload()` even though the model body
    doesn't declare it. `extra="forbid"` makes the model reject it at
    validation time — this test fails the moment the discipline slips.
    """
    from pydantic import ValidationError

    from api.system import RagCollectionStatus

    # Sanity: the legitimate shape is accepted.
    RagCollectionStatus(count=5)
    RagCollectionStatus(count=None)

    # Any name-shaped field is forbidden at the model layer. The list is
    # not exhaustive — the point of `extra="forbid"` is that EVERY
    # undeclared field rejects, so we only need a small representative
    # set to pin the contract.
    for forbidden_key in ("name", "id", "slug", "label", "project_id"):
        with pytest.raises(ValidationError):
            RagCollectionStatus(**{"count": 5, forbidden_key: "anything"})


async def test_endpoint_returns_unhealthy_when_list_collections_fails(
    client_factory,
):
    fake_client = MagicMock()
    fake_client.list_collections = MagicMock(side_effect=RuntimeError("boom"))

    rag = RAGService()
    rag._client = fake_client
    rag._mode = "PERSISTENT"
    rag._endpoint = "/abs/path/to/chroma"

    client = await client_factory(rag)
    response = await client.get("/api/system/rag/status")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "PERSISTENT"
    assert data["endpoint"] == ""
    assert data["fallback_active"] is True
    assert data["collections"] == []
    assert data["total_docs"] == 0
    assert data["healthy"] is False
