"""CB-2213: half-init invariant — `_mode` cannot be HTTP/PERSISTENT while
`_client is None`.

Both init paths (`_init_client_blocking`, `_fallback_to_persistent`) call
`_reset_state()` up front before constructing the new client. The invariant
they pin: if construction (or heartbeat) raises mid-flight, the service must
end up FULLY uninitialised — `_mode is None`, `_client is None`,
`_endpoint is None`, `_collections == {}` — so no caller can read a stale
mode advertised next to a dead/None client.

Pre-CB-2043, the original bug was exactly that: HTTP advertised, client None.
The reset block at the top of each init path closed it; these parametrised
tests pin the closure so a future refactor that forgets the up-front reset
(or drifts only one path) cannot silently re-introduce the gap.

Both scenarios exercise the cross-mode failure path explicitly called out in
the CB-2213 spec:
  - successful PERSISTENT init, then `_init_client_blocking` raises
  - successful HTTP init, then `_fallback_to_persistent` raises
"""

from unittest.mock import MagicMock, patch

import chromadb
import pytest

from app.config import settings as app_settings
from services.rag_service import RAGService


def _bring_up_persistent(rag: RAGService) -> None:
    """Drive the service into a healthy PERSISTENT state."""
    fake_persistent = MagicMock()
    fake_persistent.list_collections = MagicMock(return_value=[])
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()
    assert rag._mode == "PERSISTENT"
    assert rag._client is fake_persistent


def _bring_up_http(rag: RAGService, monkeypatch) -> None:
    """Drive the service into a healthy HTTP state."""
    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    fake_socket = MagicMock()
    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)
    fake_client.list_collections = MagicMock(return_value=[])
    with patch("services.rag_service.socket.create_connection", return_value=fake_socket), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()
    assert rag._mode == "HTTP"
    assert rag._client is fake_client


def _assert_uninitialised(rag: RAGService) -> None:
    """Pin the half-init invariant. If any of these regress, the original
    'mode advertised next to a None client' bug is back."""
    assert rag._mode is None
    assert rag._client is None
    assert rag._endpoint is None
    assert rag._collections == {}
    assert rag.describe_mode() == "RAG mode=UNINITIALIZED"


@pytest.mark.parametrize(
    "scenario",
    [
        "http_init_raises_after_persistent",
        "persistent_init_raises_after_http",
    ],
)
def test_half_init_failure_leaves_service_uninitialised(scenario, monkeypatch):
    rag = RAGService()
    sentinel_handle = MagicMock(name="stale_handle")

    if scenario == "http_init_raises_after_persistent":
        # Mode A: PERSISTENT (healthy)
        _bring_up_persistent(rag)
        # Seed _collections so we can also confirm it was wiped by the
        # up-front reset, not left dangling.
        rag._collections["sentinel"] = sentinel_handle

        # Now the alternate init: _init_client_blocking. Patch HttpClient
        # heartbeat to raise mid-init (TCP probe succeeds, construction
        # succeeds, heartbeat fails — the exact partial-failure window
        # CB-2043's reset block was added to defend).
        monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
        monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

        fake_socket = MagicMock()
        broken_http = MagicMock()
        broken_http.heartbeat = MagicMock(
            side_effect=RuntimeError("heartbeat exploded")
        )
        # _init_client_blocking wraps heartbeat failures in ConnectionError —
        # that wrapping is part of the public contract (lifespan code branches
        # on ConnectionError to fall back), so we pin the class explicitly.
        with patch("services.rag_service.socket.create_connection",
                   return_value=fake_socket), \
             patch.object(chromadb, "HttpClient", return_value=broken_http):
            with pytest.raises(ConnectionError):
                rag._init_client_blocking()

    else:
        # Mode A: HTTP (healthy)
        _bring_up_http(rag, monkeypatch)
        rag._collections["sentinel"] = sentinel_handle

        # Now the alternate init: _fallback_to_persistent. Patch
        # PersistentClient construction to raise — this is the constructor
        # raise mid-init scenario the CB-2213 spec calls out explicitly.
        # The production code does NOT wrap PersistentClient errors, so we
        # match on the broad `Exception` to avoid pinning the test to today's
        # exception class — a future "wrap in ConnectionError" refactor must
        # not silently break this regression test.
        with patch.object(
            chromadb,
            "PersistentClient",
            side_effect=RuntimeError("PersistentClient construct exploded"),
        ):
            with pytest.raises(Exception):
                rag._fallback_to_persistent()

    _assert_uninitialised(rag)
    assert "sentinel" not in rag._collections
