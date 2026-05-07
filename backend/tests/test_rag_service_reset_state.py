"""CB-2212: both init paths must reset `_collections` (asymmetry regression).

Before CB-2212, `_init_client_blocking` reset only `_client`/`_mode`/`_mode_detail`
but left `_collections` untouched. A future "reconnect" caller that hits this path
on a service previously running in PERSISTENT mode would have `get_collection()`
return cached objects bound to the dead PersistentClient — exactly the
half-initialised state CB-2043's reset block aimed to prevent.

These tests pin the symmetry so a future refactor cannot drift the two paths
apart again.
"""

from unittest.mock import MagicMock, patch

import chromadb

from services.rag_service import RAGService


def test_init_client_blocking_clears_stale_collections(monkeypatch):
    """_init_client_blocking must wipe `_collections` cached from a prior client."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    rag = RAGService()
    stale_handle = MagicMock(name="stale_collection_handle")
    rag._collections = {"summaries_proj_X": stale_handle}

    fake_socket = MagicMock()
    fake_client = MagicMock()
    fake_client.heartbeat = MagicMock(return_value=1)

    with patch("services.rag_service.socket.create_connection", return_value=fake_socket), \
         patch.object(chromadb, "HttpClient", return_value=fake_client):
        rag._init_client_blocking()

    assert rag._collections == {}, (
        "stale collection handles must be cleared so get_collection() cannot "
        "return objects bound to the previous client"
    )


def test_fallback_to_persistent_clears_stale_collections():
    """_fallback_to_persistent must wipe `_collections` cached from a prior client."""
    rag = RAGService()
    stale_handle = MagicMock(name="stale_collection_handle")
    rag._collections = {"summaries_proj_X": stale_handle}

    fake_persistent = MagicMock()
    with patch.object(chromadb, "PersistentClient", return_value=fake_persistent):
        rag._fallback_to_persistent()

    assert rag._collections == {}


def test_reset_state_zeroes_all_client_dependent_fields():
    """_reset_state is the single source of truth for the reset contract."""
    rag = RAGService()
    rag._client = MagicMock()
    rag._mode = "HTTP"
    rag._mode_detail = "chromadb:8000"
    rag._collections = {"a": MagicMock(), "b": MagicMock()}

    rag._reset_state()

    assert rag._client is None
    assert rag._mode is None
    assert rag._mode_detail is None
    assert rag._collections == {}


def test_init_client_blocking_failure_leaves_collections_clean(monkeypatch):
    """A failed HTTP init must NOT leave stale collection handles behind."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "CHROMA_HOST", "chromadb")
    monkeypatch.setattr(app_settings, "CHROMA_PORT", 8000)

    rag = RAGService()
    rag._collections = {"summaries_proj_X": MagicMock()}

    with patch(
        "services.rag_service.socket.create_connection",
        side_effect=OSError("nope"),
    ):
        try:
            rag._init_client_blocking()
        except ConnectionError:
            pass

    assert rag._collections == {}, (
        "even on init failure, the up-front reset must clear cached handles "
        "so the next caller cannot pull from a half-initialised cache"
    )
    # Symmetric assertion: every field _reset_state clears must remain cleared
    # on the failure path, not just _collections.
    assert rag._client is None
    assert rag._mode is None
    assert rag._mode_detail is None
