"""File CB-2732 sec-audit / code-review follow-up bugs under STORY CB-2047.

Output: 4 sibling BUG tickets capturing the LOW + INFO findings the
audit recommended as out-of-scope-of-CB-2732 follow-ups.

Per Bible Rule 29: per-project per-session path, not /tmp/.
"""

from __future__ import annotations

import json
import sys
from urllib import request as urlrequest
from urllib.error import HTTPError

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
PARENT_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"  # CB-2047 (STORY)
LABELS = "cb-2732-followup,security,internal-token-gate"

# (key_suffix-for-prints, payload)
TICKETS: list[tuple[str, dict]] = [
    (
        "L-1",
        {
            "title": (
                "[CB-2732 audit follow-up L-1] LOW: search.py file-level invariant "
                "test — every router-decorated handler must carry InternalAuthDep + "
                "@limiter.limit"
            ),
            "type": "BUG",
            "priority": "LOW",
            "parentId": PARENT_ID,
            "labels": LABELS,
            "assignee": "python-pro",
            "reporter": "AI",
            "description": (
                "**Severity:** LOW — discovered by security-auditor on the "
                "CB-2732 fix (2026-05-09).\n\n"
                "## Gap\n\n"
                "`backend/tests/test_security.py::TestSearchSiblingEndpointsPerimeter"
                "::test_handler_carries_internal_auth_dep` AST-pins the FIVE "
                "named CB-2732 handlers + the `/stats` handler from CB-2667. The "
                "parametrize list `_SEARCH_SIBLING_ENDPOINTS` is hard-coded, so "
                "if a future ticket adds a SIXTH endpoint to `backend/api/search.py` "
                "(e.g. `POST /{project_id}/reindex-since`) and forgets the gate, "
                "no test fails.\n\n"
                "## Fix\n\n"
                "Add a separate file-level invariant test that walks every "
                "`FunctionDef` / `AsyncFunctionDef` in `search.py` decorated by "
                "`@router.<verb>(...)` and asserts each one:\n\n"
                "1. carries `dependencies=[...]` with `InternalAuthDep` in the kwarg\n"
                "2. carries a `@limiter.limit(...)` decorator with a known cap\n"
                "3. has `@router.<verb>` ABOVE `@limiter.limit` in source "
                "(decorator-order invariant from CB-2732 sec audit M-1)\n\n"
                "This generalises the per-handler AST check to a per-file "
                "invariant. Same pattern should arguably apply to "
                "`backend/api/projects.py` (CB-2666 perimeter) — extend the "
                "test or extract a helper if so.\n\n"
                "## Threat-model linkage\n\n"
                "CB-2732 closed the perimeter on the FIVE current sibling "
                "endpoints. This follow-up makes the closure structural — a "
                "file-level invariant a new endpoint cannot bypass without "
                "deliberately defeating the test.\n\n"
                "_Filed by Jonny during CB-2732 implementation pass._"
            ),
        },
    ),
    (
        "L-2",
        {
            "title": (
                "[CB-2732 audit follow-up L-2] LOW: embed_all_issues errors[] "
                "leaks raw exception strings — redact str(e) to a generic token"
            ),
            "type": "BUG",
            "priority": "LOW",
            "parentId": PARENT_ID,
            "labels": LABELS,
            "assignee": "python-pro",
            "reporter": "AI",
            "description": (
                "**Severity:** LOW — discovered by security-auditor on the "
                "CB-2732 fix (2026-05-09). Residual disclosure on bypass paths.\n\n"
                "## Disclosure\n\n"
                "`backend/api/search.py:276-279` and `:286` (`embed_all_issues`) "
                "return up to 10 entries in `errors[]` of the form:\n\n"
                "```python\n"
                'errors.append(f"Error embedding {issue.key}: {str(e)}")\n'
                "```\n\n"
                "If `e` carries a SQL error string, ChromaDB internal path, "
                "or HTTP-level chromadb error, the response body leaks more "
                "than the issue key. Token-holding callers are in-scope by "
                "design, but on a future bypass path (proxy-collapse / multi-"
                "worker scenario from CB-2732 audit M-3), an attacker who lands "
                "one successful `embed-all` call learns the project's issue "
                "keys via `errors[]` even when the bucket is otherwise capped.\n\n"
                "## Fix\n\n"
                "Redact `str(e)` to a generic `\"embed_failed\"` token; keep "
                "`issue.key` (caller already supplied it via `(project_id, "
                "issue_id)` in legitimate use). Mirror the redaction pattern "
                "the AutoPilot audit log uses (`Bearer/sk-/api_key=` strip).\n\n"
                "Suggested form:\n\n"
                "```python\n"
                "except Exception as e:\n"
                "    failed += 1\n"
                "    errors.append(f\"{issue.key}: embed_failed\")\n"
                "    logger.exception(\"embed_failed\", extra={\"issue_key\": issue.key})\n"
                "```\n\n"
                "## Test parity\n\n"
                "Add a regression test asserting `errors[]` entries do not "
                "contain `str(e)`-derived substrings (e.g. SQL error patterns, "
                "filesystem paths) on a synthetic embed failure.\n\n"
                "_Filed by Jonny during CB-2732 implementation pass._"
            ),
        },
    ),
    (
        "L-3",
        {
            "title": (
                "[CB-2732 audit follow-up L-3] LOW: rag_service.embed_issue / "
                "delete_issue_embedding use print() for errors — convert to "
                "logger.exception"
            ),
            "type": "BUG",
            "priority": "LOW",
            "parentId": PARENT_ID,
            "labels": LABELS,
            "assignee": "python-pro",
            "reporter": "AI",
            "description": (
                "**Severity:** LOW — discovered by security-auditor on the "
                "CB-2732 fix (2026-05-09). Pre-existing pattern, but the new "
                "CB-2732 write endpoints (`POST /embed/{iid}`, `POST /embed-all`, "
                "`DELETE /embed/{iid}`) are now the user-facing entry points "
                "that drive these prints under attacker control.\n\n"
                "## Issue\n\n"
                "`backend/services/rag_service.py:902, :913` use:\n\n"
                "```python\n"
                'print(f"Error embedding issue: {e}")\n'
                "```\n\n"
                "Raw exception text → stdout, captured by any log shipper "
                "without the redaction logic the structured logger provides. "
                "Violates project convention (`CLAUDE.md`): \"Logging: Python "
                "`logging` module (no print statements).\"\n\n"
                "## Fix\n\n"
                "Convert `print(...)` → `logger.exception(...)` so any future "
                "log-redaction layer (Bearer/sk-/api_key= patterns the "
                "AutoPilot audit log already strips) catches accidental token "
                "spillage in the exception message.\n\n"
                "Sweep the entire `rag_service.py` module for other `print()` "
                "instances while in there.\n\n"
                "_Filed by Jonny during CB-2732 implementation pass._"
            ),
        },
    ),
    (
        "I-5",
        {
            "title": (
                "[CB-2732 audit follow-up I-5] MEDIUM: /api/search/* gates are "
                "auth-only, not project-scoped — token-holder can still walk "
                "any project_id (CB-2117-style follow-up)"
            ),
            "type": "BUG",
            "priority": "MEDIUM",
            "parentId": PARENT_ID,
            "labels": LABELS,
            "assignee": "security-auditor",
            "reporter": "AI",
            "description": (
                "**Severity:** MEDIUM — flagged by security-auditor during the "
                "CB-2732 audit pass (2026-05-09). Out of CB-2732 stated scope "
                "(gate is auth-only by design, matching CB-2666 / CB-2667 "
                "perimeter posture); filed as a follow-up for the multi-tenant "
                "story.\n\n"
                "## Issue\n\n"
                "`InternalAuthDep` checks `X-Internal-Token` presence + "
                "correctness. It does NOT verify the caller-supplied "
                "`project_id` is one the caller is authorised to read or "
                "mutate. After CB-2732 a token-holding caller can still:\n\n"
                "- `GET /api/search/<any-cuid>?q=...` and learn semantic-search "
                "  results for any project the operator owns\n"
                "- `POST /api/search/<any-cuid>/embed-all` and confirm a "
                "  guessed CUID by the non-zero `embedded` count, while pinning "
                "  a worker for the duration of the fan-out\n"
                "- `DELETE /api/search/<any-cuid>/embed/<any-iid>` and destroy "
                "  embeddings on a project they do not own\n\n"
                "The runbook docstring at the top of `search.py` claims "
                "`embed-all` \"confirms a guessed CUID by non-zero `embedded` "
                "count\" — that claim still holds AFTER the gate for any "
                "token-holding client. The gate closes the **anonymous** "
                "perimeter; project-scoped authorisation is a separate layer.\n\n"
                "## Fix recommendation\n\n"
                "Same shape as CB-2117 (projectId IDOR guard on issue "
                "endpoints): add a project-scope check that resolves the "
                "caller to a Project row and verifies the supplied "
                "`project_id` matches a project the caller owns. The check "
                "runs INSIDE the route body or as a second `Depends(...)` "
                "after `InternalAuthDep`.\n\n"
                "Note: the current deploy model is single-tenant (Eli is the "
                "operator and owns every project), so this is not exploitable "
                "today. The follow-up exists for when the perimeter expands "
                "(team / multi-tenant deploy).\n\n"
                "## Test parity\n\n"
                "After the fix lands, extend `TestSearchSiblingEndpointsPerimeter` "
                "(or add a sibling class) covering: token valid + project_id "
                "owned by caller → 200; token valid + project_id owned by "
                "another caller → 403.\n\n"
                "## Threat-model linkage\n\n"
                "CB-2117 (issue-endpoint projectId IDOR) → CB-2666 (project "
                "list gate) → CB-2667 (`/stats` gate) → CB-2732 (sibling "
                "search gates) → THIS (project-scoped authorisation on the "
                "search router for multi-tenant). Closing this finishes the "
                "authorisation perimeter the gate-only fixes built on.\n\n"
                "_Filed by Jonny during CB-2732 implementation pass._"
            ),
        },
    ),
]


def post(payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        f"{API}/projects/{PROJECT_ID}/issues",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} on POST: {body}") from e


def main() -> int:
    created: list[tuple[str, str]] = []
    for tag, payload in TICKETS:
        result = post(payload)
        key = result.get("key", "?")
        created.append((tag, key))
        print(f"[{tag}] created {key}: {payload['title'][:80]}")

    print("\nSummary:")
    for tag, key in created:
        print(f"  {tag} -> {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
