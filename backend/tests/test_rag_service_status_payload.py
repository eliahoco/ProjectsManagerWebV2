"""CB-2045: RAGService.get_status_payload() — structured snapshot for the
GET /api/system/rag/status endpoint.

Verifies:
  * UNINITIALIZED before any client init.
  * HTTP mode after a successful _init_client_blocking — host/port parsed,
    collections + counts enumerated, healthy=True.
  * PERSISTENT mode after _fallback_to_persistent — host=abspath, port=0.
  * Heartbeat failure on HTTP flips healthy=False.
  * list_collections failure flips healthy=False without raising.
  * Per-collection count() failure → count=None and healthy=False.
"""

import os
from unittest.mock import MagicMock, patch

import chromadb
import pytest

from services.rag_service import PERSISTENT_FALLBACK_PATH, RAGService


def test_status_payload_uninitialized():
    rag = RAGService()
    payload = rag.get_status_payload()
    assert payload == {
        "mode": "UNINITIALIZED",
        "host": "",
        "port": 0,
        "collections": [],
        "total_docs": 0,
        "healthy": False,
    }


def test_status_payload_http_healthy(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    fake_socket = MagicMock()
    fake_socket.close = MagicMock()

    col_a = MagicMock()
    col_a.name = "project_aaaaaa"
    col_a.count = MagicMock(return_value=5)
    col_b = MagicMock()
    col_b.name = "project_bbbbbb"
    col_b.count = MagicMock(return_value=12)

    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[col_a, col_b])

    rag = RAGService()
    with patch("services.rag_service.socket.create_connection", return_value=fake_socket), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    payload = rag.get_status_payload()
    assert payload["mode"] == "HTTP"
    assert payload["host"] == "chromadb"
    assert payload["port"] == 8000
    assert payload["collections"] == [
        {"name": "project_aaaaaa", "count": 5},
        {"name": "project_bbbbbb", "count": 12},
    ]
    assert payload["total_docs"] == 17
    assert payload["healthy"] is True


def test_status_payload_persistent_healthy():
    col = MagicMock()
    col.name = "project_xxxxxx"
    col.count = MagicMock(return_value=3)

    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[col])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    payload = rag.get_status_payload()
    assert payload["mode"] == "PERSISTENT"
    assert payload["host"] == os.path.abspath(PERSISTENT_FALLBACK_PATH)
    assert payload["port"] == 0
    assert payload["collections"] == [{"name": "project_xxxxxx", "count": 3}]
    assert payload["total_docs"] == 3
    assert payload["healthy"] is True


def test_status_payload_http_heartbeat_failure(monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    fake_socket = MagicMock()
    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[])

    rag = RAGService()
    with patch("services.rag_service.socket.create_connection", return_value=fake_socket), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    # After init, swap heartbeat to raise so get_status_payload sees a fault.
    fake_client.heartbeat = MagicMock(side_effect=ConnectionError("dead"))

    payload = rag.get_status_payload()
    assert payload["mode"] == "HTTP"
    assert payload["healthy"] is False


def test_status_payload_list_collections_failure_does_not_raise():
    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(side_effect=RuntimeError("boom"))

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    payload = rag.get_status_payload()
    assert payload["mode"] == "PERSISTENT"
    assert payload["collections"] == []
    assert payload["total_docs"] == 0
    assert payload["healthy"] is False


def test_status_payload_per_collection_count_failure():
    bad = MagicMock()
    bad.name = "project_broken"
    bad.count = MagicMock(side_effect=RuntimeError("count failed"))
    good = MagicMock()
    good.name = "project_ok"
    good.count = MagicMock(return_value=4)

    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[bad, good])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    payload = rag.get_status_payload()
    assert payload["mode"] == "PERSISTENT"
    assert payload["collections"] == [
        {"name": "project_broken", "count": None},
        {"name": "project_ok", "count": 4},
    ]
    # total_docs sums only successful counts.
    assert payload["total_docs"] == 4
    assert payload["healthy"] is False
