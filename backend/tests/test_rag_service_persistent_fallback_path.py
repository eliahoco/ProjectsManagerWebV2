"""CB-2220 regression: PERSISTENT_FALLBACK_PATH must be anchored to the
backend/ package root, not the process working directory.

Before the fix, the constant was the literal string ``"./data/chroma"`` which
``chromadb.PersistentClient`` resolves against ``os.getcwd()``. A backend
launched from anywhere other than ``backend/`` (systemd unit with
``WorkingDirectory=/``, sibling helper script, future container with a
different ``WORKDIR``) would write the embedded SQLite fallback to a
different disk location, making prior embeddings appear missing. If symlinks
or a writable parent CWD were ever involved, the fallback could land in an
unexpected location with unexpected permissions.
"""

import importlib
import os
from pathlib import Path


def test_persistent_fallback_path_is_absolute():
    """The fallback path must be absolute so PersistentClient cannot follow CWD."""
    from services.rag_service import PERSISTENT_FALLBACK_PATH

    assert os.path.isabs(PERSISTENT_FALLBACK_PATH), (
        f"PERSISTENT_FALLBACK_PATH={PERSISTENT_FALLBACK_PATH!r} must be absolute"
    )


def test_persistent_fallback_path_anchored_to_backend_data_chroma():
    """The fallback path must resolve to <repo>/backend/data/chroma."""
    from services.rag_service import PERSISTENT_FALLBACK_PATH

    # services/rag_service.py -> services/ -> backend/
    backend_root = Path(__file__).resolve().parent.parent
    expected = backend_root / "data" / "chroma"
    assert PERSISTENT_FALLBACK_PATH == str(expected), (
        f"expected {expected!s}, got {PERSISTENT_FALLBACK_PATH!r}"
    )


def test_persistent_fallback_path_is_cwd_invariant(monkeypatch, tmp_path):
    """Re-importing the module from a different CWD must not change the path."""
    from services import rag_service as original

    snapshot = original.PERSISTENT_FALLBACK_PATH

    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(original)

    assert reloaded.PERSISTENT_FALLBACK_PATH == snapshot, (
        "PERSISTENT_FALLBACK_PATH changed when CWD changed — still CWD-relative. "
        f"snapshot={snapshot!r}, after_reload={reloaded.PERSISTENT_FALLBACK_PATH!r}"
    )


def test_persistent_fallback_path_abspath_is_idempotent():
    """Existing call sites use ``os.path.abspath(PERSISTENT_FALLBACK_PATH)``;
    that must be a no-op now that the constant is already absolute, so
    surrounding code (``rag_service._fallback_to_persistent`` and existing
    tests in ``test_rag_service_status_payload.py``) keeps working."""
    from services.rag_service import PERSISTENT_FALLBACK_PATH

    assert os.path.abspath(PERSISTENT_FALLBACK_PATH) == PERSISTENT_FALLBACK_PATH
