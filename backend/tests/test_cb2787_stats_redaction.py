"""CB-2787 regression — `GET /api/search/{project_id}/stats` MUST NOT
echo raw exception text into the response `error` field.

Severity: MEDIUM (residual disclosure on bypass paths). Filed by the
security-auditor on the CB-2784 fix (2026-05-10). Same threat model as
CB-2784 but on the sibling endpoint `get_index_stats`.

Failure mode the test pins
--------------------------
`get_index_stats` previously returned ``"error": str(e)`` on the
``except Exception as e`` branch. If `e` carries a SQL fragment, a
ChromaDB internal path, or an HTTP-level chromadb error, the response
body leaks it to the caller. Token-holding callers are in scope by
design, but on a CB-2732 bypass path one successful `/stats` call
reveals the upstream error class to an Origin-less attacker. The fix
redacts the response `error` to a generic ``"stats_failed"`` token;
detail goes to the server log via `logger.exception` only.

Test shape
----------
Override `get_rag` so `get_collection` raises an exception whose text
contains every leak-shaped substring we care about. Issue the request
and assert that NONE of those substrings reach `body['error']`. The
test also pins the redacted form ``"stats_failed"`` and a source-level
AST pin so a refactor cannot re-leak by accident.
"""

import pytest
from unittest.mock import MagicMock


_LEAK_SUBSTRINGS = [
    # SQL surface — the most damaging leak class on the bypass path.
    "no such table",
    "sqlite_master",
    "ProgrammingError",
    "OperationalError",
    # Filesystem internals — re-discloses the CB-2216 redaction.
    "/Volumes/Seagate/Claude",
    "/var/lib/chroma",
    "chroma.sqlite3",
    # ChromaDB / HTTP-level error frames.
    "chromadb.errors",
    "InvalidCollectionException",
    "HTTP 500",
    # Secret-shaped fragments — mirrors AutoPilot audit-log redaction.
    "Bearer abc123token",
    "sk-proj-FAKEKEY",
    "api_key=FAKEKEY",
]


def _build_leaky_exception_message() -> str:
    """Concatenate every leak shape into one exception payload."""
    return " | ".join(_LEAK_SUBSTRINGS)


def _install_stats_failure_stub(request):
    """Override `get_rag` so `get_collection` raises a leaky exception."""
    from app.main import app
    from api.deps import get_rag

    rag_stub = MagicMock()
    rag_stub.get_collection = MagicMock(
        side_effect=Exception(_build_leaky_exception_message())
    )
    app.dependency_overrides[get_rag] = lambda: rag_stub
    request.addfinalizer(
        lambda: app.dependency_overrides.pop(get_rag, None)
    )


@pytest.mark.api
class TestStatsErrorRedaction:
    """CB-2787 — `body['error']` must not echo `str(e)` substrings."""

    async def test_exception_branch_redacts_to_generic_token(
        self, async_client, monkeypatch, request
    ):
        """`get_collection` raises → `error` is exactly `stats_failed`,
        nothing else from the exception payload reaches the response.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
        _install_stats_failure_stub(request)

        response = await async_client.get(
            "/api/search/test-pid/stats"
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["project_id"] == "test-pid"
        assert body["indexed_count"] == 0
        assert body["status"] == "error"
        assert body["error"] == "stats_failed", (
            f"CB-2787 regression: error field shape drifted from the "
            f"redacted form. Got {body['error']!r}; expected exactly "
            f"'stats_failed'. The route must NOT echo str(e)."
        )

        leaked = body["error"].lower()
        for needle in _LEAK_SUBSTRINGS:
            assert needle.lower() not in leaked, (
                f"CB-2787 regression: error field leaked exception "
                f"substring {needle!r} on the synthetic stats failure. "
                f"The `except Exception` branch in get_index_stats must "
                f"redact `str(e)` to a generic token and route detail "
                f"to logger.exception only."
            )

    def test_stats_source_does_not_format_str_e(self):
        """Source-level pin: the `except Exception` branch in
        `get_index_stats` MUST NOT reference the bound exception name
        in the returned dict.

        Walks `api/search.py` AST; finds `get_index_stats`; finds the
        except handler; asserts the returned dict literal does not
        reference the bound exception name. logger.exception(...) is
        fine — it writes to server logs, not the response body.
        """
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "api" / "search.py"
        tree = ast.parse(src.read_text())

        target = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AsyncFunctionDef)
                and node.name == "get_index_stats"
            ):
                target = node
                break
        assert target is not None, (
            "CB-2787 regression: get_index_stats handler missing from "
            "search.py — redaction cannot be enforced on a deleted route"
        )

        excs = [n for n in ast.walk(target) if isinstance(n, ast.ExceptHandler)]
        assert excs, (
            "CB-2787 regression: get_index_stats lost its except clause"
        )

        for handler in excs:
            bound_name = handler.name
            for sub in ast.walk(handler):
                if not isinstance(sub, ast.Return):
                    continue
                src_text = ast.unparse(sub)
                if bound_name and bound_name in _identifier_tokens(src_text):
                    pytest.fail(
                        "CB-2787 regression: return inside the except "
                        "clause references the bound exception name "
                        f"{bound_name!r}: {src_text!r}. Redact str(e) "
                        "and route detail to logger.exception only."
                    )
                if "str(" in src_text and bound_name and (
                    f"str({bound_name})" in src_text
                ):
                    pytest.fail(
                        "CB-2787 regression: return uses "
                        f"str({bound_name}) — that's exactly the leak "
                        "shape this ticket closes."
                    )


def _identifier_tokens(text: str):
    """Tokenize an unparsed AST snippet into bare identifiers."""
    import re
    return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
