"""CB-2784 wrap-up — file audit follow-up bug for get_index_stats
str(e) leak (security-auditor finding, out of scope for CB-2784) and
mark CB-2784 itself COMPLETED_WAITING_QA.

Rule 29 (Jonny bible): per-project per-session helper, NOT
/tmp/codeboard-plan.py. Eli runs parallel sessions across projects
that share /tmp.
"""
import json
import urllib.request

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"  # ProjectsManagerWebV2Production
PARENT_STORY_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"  # CB-2047
CB_2784_ID = "ac2fa57c-6683-4429-9ae4-da8805152483"


def request(method: str, path: str, body: dict | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method, headers=headers
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> None:
    # 1. File the audit follow-up bug.
    follow_up_title = (
        "[CB-2784 audit follow-up M-1] MEDIUM: /api/search/{project_id}/stats "
        "(get_index_stats) still echoes str(e) on exception — same "
        "disclosure shape CB-2784 closed for embed_all_issues"
    )
    follow_up_description = (
        "**Severity:** MEDIUM — found by security-auditor on the CB-2784 fix "
        "(2026-05-10). Same threat model as CB-2784 but on the sibling "
        "endpoint `/api/search/{project_id}/stats`.\n\n"
        "## Disclosure\n\n"
        "`backend/api/search.py:329-335` (`get_index_stats`) still returns:\n\n"
        "```python\n"
        "except Exception as e:\n"
        "    return {\n"
        "        \"project_id\": project_id,\n"
        "        \"indexed_count\": 0,\n"
        "        \"status\": \"error\",\n"
        "        \"error\": str(e),\n"
        "    }\n"
        "```\n\n"
        "Token-holding callers are in scope by design (`InternalAuthDep` + "
        "30/min cap), but on a CB-2732 bypass path an attacker who lands one "
        "successful `/stats` call learns the upstream error class — same "
        "CB-2784 leak shape.\n\n"
        "## Fix\n\n"
        "Mirror CB-2784: redact the response `error` field to a generic "
        "`stats_failed` token; keep `project_id` (path param). Route detail "
        "to `logger.exception` only.\n\n"
        "Suggested form:\n\n"
        "```python\n"
        "except Exception:\n"
        "    logger.exception(\"stats_failed\", extra={\"project_id\": project_id})\n"
        "    return {\n"
        "        \"project_id\": project_id,\n"
        "        \"indexed_count\": 0,\n"
        "        \"status\": \"error\",\n"
        "        \"error\": \"stats_failed\",\n"
        "    }\n"
        "```\n\n"
        "## Test parity\n\n"
        "Add a behavioural test (mirror "
        "`test_cb2784_embed_all_redaction.py`) asserting `body['error']` does "
        "not contain `str(e)`-derived substrings on a synthetic "
        "`rag.get_collection(...)` failure.\n\n"
        "_Filed by Jonny during CB-2784 implementation pass._"
    )
    payload = {
        "title": follow_up_title,
        "description": follow_up_description,
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": PARENT_STORY_ID,
        "labels": "cb-2732-audit-followup,disclosure,search-api",
        "reporter": "AI",
        "assignee": "python-pro",
    }
    created = request("POST", f"/projects/{PROJECT_ID}/issues", payload)
    print(f"Filed audit follow-up: {created.get('key')} ({created.get('id')})")

    # 2. Mark CB-2784 COMPLETED_WAITING_QA.
    updated = request(
        "PATCH",
        f"/issues/{CB_2784_ID}",
        {"status": "COMPLETED_WAITING_QA"},
    )
    print(
        f"CB-2784 status -> "
        f"{updated.get('status') or updated.get('data', {}).get('status')}"
    )


if __name__ == "__main__":
    main()
