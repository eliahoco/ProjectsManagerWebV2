"""Regression tests for CB-1601: QA generation call chain passes db session.

CB-1600 added a `db: Optional[AsyncSession]` parameter to
`qa_service.generate_qa_plan` so the service can fetch the latest
ExecutionSummary via RAG and inject implementation context into the prompt.

CB-1601 ensures every caller passes that session, otherwise the impl-context
section silently disappears and QA tests revert to abstract-requirements-only
generation. These tests lock the plumbing at every known call site:

  * api/qa.py :: generate_qa_plan endpoint            (POST /api/qa/generate)
  * api/qa.py :: generate_qa_plan_stream endpoint     (POST /api/qa/generate/stream)
  * api/issues.py :: trigger_qa_generation background task

Static source-level assertions are intentional: full integration tests for
the same plumbing would need a real DB plus mocked AI plus FastAPI DI
wiring, which is heavier than the value provided. A regression here is a
silent feature-degradation, not a crash, so the cheapest signal is a
source-level lock that fires the moment a future refactor drops the kwarg.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import sys

import services.qa_service  # noqa: F401  ensure submodule registered in sys.modules

from api import issues as issues_module
from api import qa as qa_module

# `services/__init__.py` re-exports the `qa_service` singleton, which shadows
# the submodule attribute on the `services` package. Pull the actual module
# from sys.modules so we can read its bound singleton without ambiguity.
qa_service_module = sys.modules["services.qa_service"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_generate_qa_plan_calls(source: str) -> list[ast.Call]:
    """Return every `qa_service.generate_qa_plan(...)` call node in `source`."""
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match attribute calls like `qa_service.generate_qa_plan(...)` or
        # `<anything>.generate_qa_plan(...)` — name match is the load-bearing part.
        if isinstance(func, ast.Attribute) and func.attr == "generate_qa_plan":
            calls.append(node)
    return calls


def _has_db_kwarg(call: ast.Call) -> bool:
    """True if `db=...` is explicit, OR if call uses `**unpack` (kw.arg is None).

    `**ctx` is treated as ambiguous-pass rather than missing-kwarg: the call
    `qa_service.generate_qa_plan(**ctx)` may or may not include `db` depending
    on `ctx` at runtime, and flagging it as missing would be a false positive
    for legitimate dispatch patterns.
    """
    for kw in call.keywords:
        if kw.arg == "db":
            return True
        if kw.arg is None:  # ** unpacking — assume db may be inside
            return True
    return False


# ---------------------------------------------------------------------------
# Service signature — guards CB-1600 contract
# ---------------------------------------------------------------------------


def test_generate_qa_plan_service_accepts_db_kwarg():
    """The service signature must keep `db` as a kwarg or callers break."""
    sig = inspect.signature(qa_service_module.qa_service.generate_qa_plan)
    assert "db" in sig.parameters, (
        "qa_service.generate_qa_plan must accept a `db` kwarg (CB-1600). "
        "Removing it silently disables ExecutionSummary injection at every caller."
    )


# ---------------------------------------------------------------------------
# api/qa.py :: generate_qa_plan endpoint
# ---------------------------------------------------------------------------


def test_generate_qa_plan_endpoint_signature_has_db_dependency():
    sig = inspect.signature(qa_module.generate_qa_plan)
    assert "db" in sig.parameters, (
        "POST /api/qa/generate endpoint must declare `db: AsyncSession = Depends(get_db)` "
        "so the session can be threaded into qa_service.generate_qa_plan (CB-1601)."
    )


def test_generate_qa_plan_endpoint_passes_db_to_service():
    src = inspect.getsource(qa_module.generate_qa_plan)
    calls = _collect_generate_qa_plan_calls(src)
    assert calls, "generate_qa_plan endpoint should call qa_service.generate_qa_plan"
    assert all(_has_db_kwarg(c) for c in calls), (
        "generate_qa_plan endpoint must pass db=db to qa_service.generate_qa_plan (CB-1601). "
        "Without it, RAG-backed implementation context is silently skipped."
    )


# ---------------------------------------------------------------------------
# api/qa.py :: generate_qa_plan_stream endpoint
# ---------------------------------------------------------------------------


def test_generate_qa_plan_stream_endpoint_signature_has_db_dependency():
    sig = inspect.signature(qa_module.generate_qa_plan_stream)
    assert "db" in sig.parameters, (
        "POST /api/qa/generate/stream endpoint must declare `db: AsyncSession = Depends(get_db)` "
        "so the session can be threaded into qa_service.generate_qa_plan (CB-1601)."
    )


def test_generate_qa_plan_stream_endpoint_passes_db_to_service():
    src = inspect.getsource(qa_module.generate_qa_plan_stream)
    calls = _collect_generate_qa_plan_calls(src)
    assert calls, "generate_qa_plan_stream endpoint should call qa_service.generate_qa_plan"
    assert all(_has_db_kwarg(c) for c in calls), (
        "generate_qa_plan_stream endpoint must pass db=db to qa_service.generate_qa_plan (CB-1601)."
    )


# ---------------------------------------------------------------------------
# api/issues.py :: trigger_qa_generation background task
# ---------------------------------------------------------------------------


def test_trigger_qa_generation_passes_db_to_service():
    src = inspect.getsource(issues_module.trigger_qa_generation)
    calls = _collect_generate_qa_plan_calls(src)
    assert calls, "trigger_qa_generation should call qa_service.generate_qa_plan"
    assert all(_has_db_kwarg(c) for c in calls), (
        "trigger_qa_generation must pass db=db to qa_service.generate_qa_plan (CB-1601). "
        "Background task uses its own AsyncSessionLocal session — must still thread it through."
    )


# ---------------------------------------------------------------------------
# Repo-wide sweep — catches new call sites added in future
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path",
    [
        "backend/api/qa.py",
        "backend/api/issues.py",
    ],
)
def test_every_known_caller_passes_db(rel_path: str):
    """Lock current call sites. If a new file starts calling generate_qa_plan,
    add it here so the kwarg is enforced at that site too."""
    repo_root = Path(__file__).resolve().parents[2]
    file_path = repo_root / rel_path
    src = file_path.read_text()
    calls = _collect_generate_qa_plan_calls(src)
    assert calls, f"{rel_path} expected to call generate_qa_plan"
    missing = [
        f"line {c.lineno}" for c in calls if not _has_db_kwarg(c)
    ]
    assert not missing, (
        f"{rel_path}: generate_qa_plan calls missing `db=` kwarg at "
        f"{', '.join(missing)}. CB-1601 requires every call site to pass "
        f"the session so ExecutionSummary context flows into QA generation."
    )
