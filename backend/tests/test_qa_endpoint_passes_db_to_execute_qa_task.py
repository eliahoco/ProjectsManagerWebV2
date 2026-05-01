"""Regression tests for CB-1603: QA execution call chain passes db session.

CB-1603 added a `db: Optional[AsyncSession]` parameter to
`qa_service.execute_qa_task` (and to the four wrapper methods that fan it
out — sequential, sequential_stream, parallel, parallel_stream) so the
service can fetch the latest ExecutionSummary via RAG and inject
implementation context into the per-task execution prompt.

These tests lock the plumbing at every known call site:

  * api/qa.py :: execute_qa_tasks endpoint              (POST /api/qa/execute)
  * api/qa.py :: execute_qa_tasks_stream endpoint       (POST /api/qa/execute/stream)
  * api/qa.py :: execute_qa_tasks_parallel_stream       (POST /api/qa/execute/stream-parallel)

Static source-level assertions are intentional: a regression here is a
silent feature-degradation (test verdicts revert to abstract reasoning),
not a crash. The cheapest signal is a source-level lock that fires the
moment a future refactor drops the kwarg.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

import services.qa_service  # noqa: F401  ensure submodule registered

from api import qa as qa_module

qa_service_module = sys.modules["services.qa_service"]


SERVICE_METHOD_NAMES = {
    "execute_qa_task",
    "execute_qa_tasks_sequential",
    "execute_qa_tasks_sequential_stream",
    "execute_qa_tasks_parallel",
    "execute_qa_tasks_parallel_stream",
}


def _collect_service_calls(source: str) -> list[ast.Call]:
    """Return every call to one of the QA execution service methods."""
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in SERVICE_METHOD_NAMES:
            calls.append(node)
    return calls


def _has_db_kwarg(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "db":
            return True
        if kw.arg is None:  # ** unpacking — assume db may be inside
            return True
    return False


# ---------------------------------------------------------------------------
# Service signatures — guards CB-1603 contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method_name", sorted(SERVICE_METHOD_NAMES))
def test_qa_service_method_accepts_db_kwarg(method_name: str):
    method = getattr(qa_service_module.qa_service, method_name)
    sig = inspect.signature(method)
    assert "db" in sig.parameters, (
        f"qa_service.{method_name} must accept a `db` kwarg (CB-1603). "
        f"Removing it silently disables ExecutionSummary injection."
    )


# ---------------------------------------------------------------------------
# api/qa.py :: execute_qa_tasks endpoint (sequential or parallel)
# ---------------------------------------------------------------------------


def test_execute_qa_tasks_endpoint_signature_has_db_dependency():
    sig = inspect.signature(qa_module.execute_qa_tasks)
    assert "db" in sig.parameters, (
        "POST /api/qa/execute endpoint must declare "
        "`db: AsyncSession = Depends(get_db)` so the session can be threaded "
        "into qa_service execution methods (CB-1603)."
    )


def test_execute_qa_tasks_endpoint_passes_db_to_service():
    src = inspect.getsource(qa_module.execute_qa_tasks)
    calls = _collect_service_calls(src)
    assert calls, (
        "execute_qa_tasks endpoint should call one of the qa_service "
        "execution methods"
    )
    assert all(_has_db_kwarg(c) for c in calls), (
        "execute_qa_tasks endpoint must pass db=db to every qa_service "
        "execution call (CB-1603). Without it, implementation context is "
        "silently skipped during automated test execution."
    )


# ---------------------------------------------------------------------------
# api/qa.py :: execute_qa_tasks_stream endpoint (sequential SSE)
# ---------------------------------------------------------------------------


def test_execute_qa_tasks_stream_endpoint_signature_has_db_dependency():
    sig = inspect.signature(qa_module.execute_qa_tasks_stream)
    assert "db" in sig.parameters, (
        "POST /api/qa/execute/stream endpoint must declare "
        "`db: AsyncSession = Depends(get_db)` (CB-1603)."
    )


def test_execute_qa_tasks_stream_endpoint_passes_db_to_service():
    src = inspect.getsource(qa_module.execute_qa_tasks_stream)
    calls = _collect_service_calls(src)
    assert calls, "execute_qa_tasks_stream endpoint should call execute_qa_tasks_sequential_stream"
    assert all(_has_db_kwarg(c) for c in calls), (
        "execute_qa_tasks_stream endpoint must pass db=db to "
        "execute_qa_tasks_sequential_stream (CB-1603)."
    )


# ---------------------------------------------------------------------------
# api/qa.py :: execute_qa_tasks_parallel_stream endpoint
# ---------------------------------------------------------------------------


def test_execute_qa_tasks_parallel_stream_endpoint_signature_has_db_dependency():
    sig = inspect.signature(qa_module.execute_qa_tasks_parallel_stream)
    assert "db" in sig.parameters, (
        "POST /api/qa/execute/stream-parallel endpoint must declare "
        "`db: AsyncSession = Depends(get_db)` (CB-1603)."
    )


def test_execute_qa_tasks_parallel_stream_endpoint_passes_db_to_service():
    src = inspect.getsource(qa_module.execute_qa_tasks_parallel_stream)
    calls = _collect_service_calls(src)
    assert calls, (
        "execute_qa_tasks_parallel_stream endpoint should call "
        "execute_qa_tasks_parallel_stream"
    )
    assert all(_has_db_kwarg(c) for c in calls), (
        "execute_qa_tasks_parallel_stream endpoint must pass db=db to "
        "execute_qa_tasks_parallel_stream (CB-1603)."
    )


# ---------------------------------------------------------------------------
# Repo-wide sweep — locks current call sites against future drift
# ---------------------------------------------------------------------------


def test_every_known_caller_passes_db():
    """Lock current call sites. If a new file calls one of the QA execution
    service methods, add it here so the kwarg is enforced at that site too."""
    repo_root = Path(__file__).resolve().parents[2]
    rel_path = "backend/api/qa.py"
    src = (repo_root / rel_path).read_text()
    calls = _collect_service_calls(src)
    assert calls, f"{rel_path} expected to call qa_service execution methods"
    missing = [
        f"line {c.lineno} ({c.func.attr})"
        for c in calls
        if not _has_db_kwarg(c)
    ]
    assert not missing, (
        f"{rel_path}: qa_service execution calls missing `db=` kwarg at "
        f"{', '.join(missing)}. CB-1603 requires every call site to pass "
        f"the session so ExecutionSummary context flows into QA execution."
    )


# ---------------------------------------------------------------------------
# Issue context shape — must include id + projectId for RAG scoping
# ---------------------------------------------------------------------------


def test_issue_context_includes_id_and_project_id():
    """The qa.py endpoints must populate `id` and `projectId` on the
    issue_context dict; without them, qa_service.execute_qa_task cannot
    enforce cross-project isolation when fetching the ExecutionSummary
    (CB-1597 H-1 / CB-1603)."""
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / "backend/api/qa.py").read_text()
    # Every issue_context dict literal in qa.py is built from a linked_issue,
    # so the fix is to require the keys 'id' and 'projectId' wherever the
    # dict is built. Two sentinel substrings are sufficient — these strings
    # do not appear elsewhere in qa.py.
    assert src.count('"id": linked_issue.id') >= 3, (
        "Every issue_context dict in api/qa.py must include "
        '`"id": linked_issue.id` so qa_service can scope the RAG lookup '
        "(CB-1603)."
    )
    assert src.count('"projectId": linked_issue.projectId') >= 3, (
        "Every issue_context dict in api/qa.py must include "
        '`"projectId": linked_issue.projectId` so cross-project isolation '
        "is enforced when fetching the ExecutionSummary (CB-1603 / CB-1597)."
    )


# ---------------------------------------------------------------------------
# CB-1603 sec audit M-1: foreign-project linked-issue guard
# ---------------------------------------------------------------------------


def test_issue_context_skips_foreign_project_linked_issues():
    """If a QA task is linked to an Issue in a different project (allowed by
    the QATaskIssueLink model — no DB-level project-equality constraint), the
    QA execute endpoints must NOT use that Issue as the issue_context.
    Otherwise the foreign Issue's title/description/ExecutionSummary leaks
    into the prompt and back into actualResult (CB-1603 sec audit M-1).

    Lock at source level: every linked-issue path must guard with
    `linked_issue.projectId == project_id`."""
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / "backend/api/qa.py").read_text()
    # Three execute endpoints — each must guard the linked-issue branch.
    assert src.count("linked_issue.projectId == project_id") >= 3, (
        "All three QA execute endpoints in api/qa.py must guard the "
        "linked-issue branch with `linked_issue.projectId == project_id` "
        "(CB-1603 sec audit M-1) — otherwise a foreign-project link leaks "
        "ExecutionSummary content into the QA execution prompt."
    )
