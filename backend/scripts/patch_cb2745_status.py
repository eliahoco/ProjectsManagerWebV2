"""
CB-2745 status update script.
Patches CB-2745 → COMPLETED_WAITING_QA.
CB-2737 is NOT patched here — parent agent confirmed it will be marked CWQ only
after Chrome regression is confirmed.
"""

import urllib.request
import json


PROJECT_ID = "1511e54f71dccd3fa79f67fe"


def get_all_issues():
    items = []
    for page in range(1, 50):
        url = f"http://localhost:8401/api/projects/{PROJECT_ID}/issues?page={page}&pageSize=200"
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read())
        items.extend(d.get("items", []))
        if page >= d.get("totalPages", 1):
            break
    return items


def patch_issue(issue_id: str, body: dict) -> dict:
    url = f"http://localhost:8401/api/issues/{issue_id}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_comment(issue_id: str, text: str) -> None:
    url = f"http://localhost:8401/api/issues/{issue_id}/comments"
    body = {"content": text, "author": "AI"}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        print(f"  Warning: comment failed: {e}")


def main():
    print("Fetching all issues...")
    items = get_all_issues()
    by_key = {i.get("key"): i for i in items}

    for key in ("CB-2745", "CB-2737"):
        issue = by_key.get(key)
        if issue:
            print(f"  Found {key}: id={issue['id']} status={issue.get('status')}")
        else:
            print(f"  {key}: NOT FOUND")

    # Patch CB-2745 → COMPLETED_WAITING_QA
    cb2745 = by_key.get("CB-2745")
    if cb2745:
        print(f"\nPatching CB-2745 ({cb2745['id']}) → COMPLETED_WAITING_QA...")
        result = patch_issue(cb2745["id"], {"status": "COMPLETED_WAITING_QA"})
        print(f"  Result status: {result.get('status')}")

        # Post completion comment
        comment = (
            "CB-2745 implementation complete.\n\n"
            "**Root cause fixed:** All 6 queue-control methods now use "
            "`await self.get_or_load_queue(queue_id)` (DB fallback) instead of "
            "`self._queues.get(queue_id)` (in-memory only). "
            "When a queue is paused and the backend restarts, `_queues` is empty "
            "but the DB still has the state — the old code returned None for all 6 "
            "methods, causing silent 400/404 errors on every control operation.\n\n"
            "**Methods fixed** (all in `backend/services/autopilot_queue_service.py`):\n"
            "| Method | Old signature | New signature | Line |\n"
            "|---|---|---|---|\n"
            "| `pause_queue` | `def` (sync) | `async def` | ~1749 |\n"
            "| `resume_queue` | `def` (sync) | `async def` | ~1766 |\n"
            "| `skip_current` | `def` (sync) | `async def` | ~1879 |\n"
            "| `abort_queue` | `async def` (already) | uses `get_or_load_queue` | ~1898 |\n"
            "| `wait_for_reset` | `async def` (already) | uses `get_or_load_queue` | ~1980 |\n"
            "| `switch_model` | `def` (sync) | `async def` | ~2209 |\n\n"
            "**Internal callers updated:**\n"
            "- `_fire_auto_resume`: `self.resume_queue()` → `await self.resume_queue()`\n"
            "- `switch_model`: internal `self.resume_queue()` → `await self.resume_queue()`\n\n"
            "**API endpoints updated** (`backend/api/execution.py`):\n"
            "- All 6 endpoint call sites now `await` the service methods\n"
            "- `abort_queue` reset_todo path uses `get_or_load_queue`\n"
            "- `wait-for-reset` endpoint uses `get_or_load_queue` for 404 guard\n\n"
            "**Existing tests updated:**\n"
            "- `test_auto_resume_scheduler.py`: 4 `resume_queue` calls → `await`\n"
            "- `test_autopilot_persistence.py`: 2 `resume_queue` calls → `await`\n"
            "- `test_cb2744_resume_after_reset.py`: 7 sync `def test_` → `async def` + `@pytest.mark.asyncio`\n\n"
            "**New regression tests:** `backend/tests/test_cb2745_db_only_queue_endpoints.py`\n"
            "- 15 tests, one per endpoint path (including edge cases), all PASSING\n"
            "- Each test: persist paused queue → fresh service (empty _queues) → call method → assert success + cache\n\n"
            "**Full test suite:** 892 passed, 3 pre-existing failures (schema/QA tests, unrelated)\n\n"
            "**Live curl pending:** Backend requires manual restart to pick up code changes "
            "(uvicorn running without --reload). Once restarted, POST /queue/99ccf3aa-2e82-471f-a36c-c51abb91e63c/resume should return 200."
        )
        post_comment(cb2745["id"], comment)
        print("  Comment posted.")
    else:
        print("  CB-2745 not found — cannot patch")

    # CB-2737 is the parent BUG — NOT patching it yet per instruction:
    # "DO NOT mark CB-2737 CWQ until I confirm Chrome regression"
    print("\nCB-2737 NOT patched — awaiting parent agent Chrome regression confirmation.")


if __name__ == "__main__":
    main()
