"""CB-2043: RAGService.describe_mode() must surface the active RAG backend.

Silent fallback to the embedded SQLite store (`backend/data/chroma/`) is how
we ended up running on stale local embeddings for weeks. The startup log line
fed by `describe_mode()` makes that fallback impossible to miss going forward.

CB-2669: the PERSISTENT branch logs a hashed digest of the abspath (not the
literal path). The HTTP /api/system/rag/status payload had its abspath
redacted by CB-2216; logging the same string at INFO via main.py's
`[startup] %s` would re-disclose it off-band to anyone with read access to
logs/backend.log. These tests pin both the new hashed format AND the
absence of the literal abspath in the log line.
"""

import hashlib
import os
import re
from unittest.mock import MagicMock, patch

import chromadb
import pytest

from services.rag_service import PERSISTENT_FALLBACK_PATH, RAGService


def test_describe_mode_uninitialized_before_init():
    rag = RAGService()
    assert rag.describe_mode() == "RAG mode=UNINITIALIZED"


def test_describe_mode_http_after_successful_init(monkeypatch):
    """After _init_client_blocking succeeds, mode=HTTP with host/port/count."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    fake_socket = MagicMock()
    fake_socket.close = MagicMock()
    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(
        return_value=[MagicMock(), MagicMock(), MagicMock()]
    )

    rag = RAGService()
    with patch("services.rag_service.socket.create_connection", return_value=fake_socket), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    line = rag.describe_mode()
    assert line == "RAG mode=HTTP host=chromadb port=8000 collections=3"


def test_describe_mode_persistent_after_fallback():
    """After _fallback_to_persistent, mode=PERSISTENT logs hashed path + count.

    CB-2669: the literal abspath MUST NOT appear in the log line — it would
    re-disclose the string CB-2216 redacted from the HTTP status payload.
    """
    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[MagicMock()])

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    expected_path = os.path.abspath(PERSISTENT_FALLBACK_PATH)
    expected_hash = hashlib.blake2s(
        expected_path.encode("utf-8"), digest_size=4
    ).hexdigest()

    line = rag.describe_mode()
    assert line == (
        f"RAG mode=PERSISTENT path_hash={expected_hash} collections=1"
    )

    # Belt+suspenders: the abspath must not appear anywhere in the line,
    # not even substring-form. Guards against future format regressions
    # that re-introduce `path=<abspath>` alongside the hash.
    assert expected_path not in line
    assert "path=" not in line  # only `path_hash=` is permitted


def test_describe_mode_swallows_collection_count_failure():
    """list_collections errors must never block the startup log line."""
    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(side_effect=RuntimeError("boom"))

    rag = RAGService()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    line = rag.describe_mode()
    # CB-2669: hashed path token, not literal abspath.
    assert re.match(
        r"^RAG mode=PERSISTENT path_hash=[0-9a-f]{8} collections=\?$", line
    ), line
    expected_path = os.path.abspath(PERSISTENT_FALLBACK_PATH)
    assert expected_path not in line
