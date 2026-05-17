"""CB-2784 regression — `POST /api/search/{project_id}/embed-all` MUST
NOT echo raw exception text into the response `errors[]` array.

Severity: LOW (residual disclosure on bypass paths). Filed by the
security-auditor on the CB-2732 fix (2026-05-09).

Failure mode the test pins
--------------------------
`embed_all_issues` previously appended ``f"Error embedding {issue.key}:
{str(e)}"`` to the response. If `e` carries a SQL fragment, a ChromaDB
internal path, or an HTTP-level chromadb error, the response body leaks
it to the caller. Token-holding callers are in scope by design, but on
a future bypass path (proxy-collapse / multi-worker — CB-2732 audit
M-3) one successful `embed-all` reveals the project's issue keys AND
the upstream error class to an Origin-less attacker. The fix redacts
the per-row exception to a generic ``"embed_failed"`` token; details
go to the server log via `logger.exception` only.

Test shape
----------
Override `get_db` with a stub that yields exactly one synthetic Issue
row, and override `get_rag` so `embed_issue` raises an exception whose
text contains every leak-shaped substring we care about (SQL fragment,
filesystem path, ChromaDB collection internal, secret-pattern). Issue
the request and assert that NONE of those substrings reach
`response.errors[]`. The test also pins the redacted form
``f"{issue.key}: embed_failed"`` so a future refactor cannot re-leak by
accident.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


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
    """Concatenate every leak shape into one exception payload.

    Using a single composite message means one failing assertion below
    surfaces every leak class at once instead of N flaky one-shot tests.
    """
    return " | ".join(_LEAK_SUBSTRINGS)


def _install_embed_all_failure_stubs(request, *, embed_succeeds: bool):
    """Override `get_rag` and `get_db` so the route body runs end-to-end.

    `embed_succeeds=False` → `embed_issue` raises a leaky exception.
    `embed_succeeds=True`  → `embed_issue` returns False (the non-raise
    failure branch) so we also pin that branch's response shape.
    """
    from app.main import app
    from api.deps import get_rag
    from models import get_db

    rag_stub = MagicMock()
    if embed_succeeds:
        rag_stub.embed_issue = AsyncMock(return_value=False)
    else:
        rag_stub.embed_issue = AsyncMock(
            side_effect=Exception(_build_leaky_exception_message())
        )
    app.dependency_overrides[get_rag] = lambda: rag_stub

    issue_row = MagicMock()
    issue_row.id = "issue-1"
    issue_row.key = "CB-9999"
    issue_row.title = "synthetic"
    issue_row.description = "synthetic"
    issue_row.type = "TASK"
    issue_row.status = "TODO"
    issue_row.labels = ""
    issue_row.projectId = "test-pid"

    db_stub = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[issue_row])
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars)
    db_stub.execute = AsyncMock(return_value=execute_result)

    async def _override_db():
        yield db_stub

    app.dependency_overrides[get_db] = _override_db
    request.addfinalizer(
        lambda: app.dependency_overrides.pop(get_rag, None)
    )
    request.addfinalizer(
        lambda: app.dependency_overrides.pop(get_db, None)
    )


@pytest.mark.api
class TestEmbedAllErrorRedaction:
    """CB-2784 — `errors[]` must not echo `str(e)` substrings."""

    async def test_exception_branch_redacts_to_generic_token(
        self, async_client, monkeypatch, request
    ):
        """`embed_issue` raises → `errors[]` carries `{key}: embed_failed`,
        nothing else from the exception payload reaches the response.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
        _install_embed_all_failure_stubs(request, embed_succeeds=False)

        response = await async_client.post(
            "/api/search/test-pid/embed-all"
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["total"] == 1
        assert body["embedded"] == 0
        assert body["failed"] == 1
        assert body["success"] is False

        errors = body["errors"]
        assert errors == ["CB-9999: embed_failed"], (
            f"CB-2784 regression: errors[] shape drifted from the redacted "
            f"form. Got {errors!r}; expected exactly "
            f"['CB-9999: embed_failed']. The route must NOT echo str(e)."
        )

        joined = " ".join(errors).lower()
        for needle in _LEAK_SUBSTRINGS:
            assert needle.lower() not in joined, (
                f"CB-2784 regression: errors[] leaked exception substring "
                f"{needle!r} on the synthetic embed failure. The "
                f"`except Exception` branch in embed_all_issues must "
                f"redact `str(e)` to a generic token and route detail "
                f"to logger.exception only."
            )

    async def test_non_raise_failure_branch_also_redacted(
        self, async_client, monkeypatch, request
    ):
        """`embed_issue` returns False (no raise) → same redacted shape.

        The pre-CB-2784 code used a different format string for this
        branch (`Failed to embed {key}` vs `Error embedding {key}: {e}`).
        Pin the post-fix form to keep both branches consistent so a
        future contributor cannot accidentally re-introduce the leaky
        format on one path while patching only the other.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "")
        _install_embed_all_failure_stubs(request, embed_succeeds=True)

        response = await async_client.post(
            "/api/search/test-pid/embed-all"
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["failed"] == 1
        assert body["errors"] == ["CB-9999: embed_failed"], (
            f"CB-2784 regression: non-raise failure branch shape drifted. "
            f"Got {body['errors']!r}; expected ['CB-9999: embed_failed']. "
            f"Both failure branches MUST share the redacted form so the "
            f"redaction cannot be silently bypassed by a non-raising "
            f"chromadb error path."
        )

    def test_embed_all_source_does_not_format_str_e(self):
        """Source-level pin: the `except Exception` branch in
        `embed_all_issues` MUST NOT format the caught exception into the
        response `errors` list.

        Walks `api/search.py` AST; finds the `embed_all_issues`
        AsyncFunctionDef; finds the inner `try/except Exception as e`
        block; asserts the body does not reference the bound exception
        name in any f-string / .append() argument that escapes the
        function. Behavioural tests above pin the response shape; this
        AST pin closes the gap where a refactor changes the f-string
        verbatim but still funnels `str(e)` into `errors.append(...)`
        through an intermediate variable.
        """
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "api" / "search.py"
        tree = ast.parse(src.read_text())

        target = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AsyncFunctionDef)
                and node.name == "embed_all_issues"
            ):
                target = node
                break
        assert target is not None, (
            "CB-2784 regression: embed_all_issues handler missing from "
            "search.py — redaction cannot be enforced on a deleted route"
        )

        # Find the `except Exception as <name>` clause inside the loop.
        excs = [n for n in ast.walk(target) if isinstance(n, ast.ExceptHandler)]
        assert excs, (
            "CB-2784 regression: embed_all_issues lost its except clause"
        )

        for handler in excs:
            bound_name = handler.name  # e.g. 'e' — may be None on bare except
            for sub in ast.walk(handler):
                # Disallow bound exception name appearing inside any
                # `errors.append(...)` argument or f-string that the
                # response surfaces. logger.exception(...) is fine — it
                # writes to server logs, not the response body.
                if not isinstance(sub, ast.Call):
                    continue
                func = sub.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr == "append"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "errors"
                ):
                    continue
                src_text = ast.unparse(sub)
                if bound_name and bound_name in _identifier_tokens(src_text):
                    pytest.fail(
                        "CB-2784 regression: errors.append(...) inside "
                        "the except clause references the bound "
                        f"exception name {bound_name!r}: {src_text!r}. "
                        "Redact str(e) and route detail to "
                        "logger.exception only."
                    )
                # Also block string-coerced exception via str(...).
                if "str(" in src_text and bound_name and (
                    f"str({bound_name})" in src_text
                ):
                    pytest.fail(
                        "CB-2784 regression: errors.append uses "
                        f"str({bound_name}) — that's exactly the leak "
                        "shape this ticket closes."
                    )


def _identifier_tokens(text: str):
    """Tokenize an unparsed AST snippet into bare identifiers.

    Used by the AST pin above to detect ``errors.append(... e ...)``
    without false-matching the substring ``e`` inside other identifiers
    like ``key`` or ``embedded``.
    """
    import re
    return set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
