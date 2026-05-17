"""
CB-2704 Smoke Test — Verify POST /api/execute/queue accepts a BUG parent issue.

CB-2671 (id=fb7fca2d-790c-442d-a976-446ec40d3750) is a BUG with child tasks
CB-2672 through CB-2683, most at COMPLETED_WAITING_QA status.

We use CB-2671 as the "feature" (parent) and pass a single safe child task
(CB-2683, status=BACKLOG) but with execution_mode="skip" so the queue does
NOT actually invoke Claude Code CLI.  We abort immediately after confirming
the queue was created.
"""

import urllib.request
import json
import sys

BASE = "http://localhost:8401/api"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get(path):
    url = f"{BASE}{path}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def post(path, body=None, method="POST"):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else b"{}"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())

def patch(issue_id, body):
    url = f"{BASE}/api/issues/{issue_id}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read())

def post_comment(issue_id, text):
    url = f"{BASE}/issues/{issue_id}/comments"
    body = {"author": "AI", "content": text}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read())

def patch_issue_status(issue_id, status):
    url = f"{BASE}/issues/{issue_id}"
    body = {"status": status}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read())


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUG_ID    = "fb7fca2d-790c-442d-a976-446ec40d3750"   # CB-2671
BUG_KEY   = "CB-2671"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"

# CB-2683 is BACKLOG — safe to use as the single task with mode=skip
CHILD_ID   = "de29e61d-04df-4887-b76d-de9b02418025"
CHILD_KEY  = "CB-2683"
CHILD_TITLE = "CB-2683 smoke-test placeholder (skip mode)"

CB2704_ID  = "0a8feef5-a335-4a5a-9a07-780a957ecf2e"

# ---------------------------------------------------------------------------
# Step 1 — Abort any active queue first (safety)
# ---------------------------------------------------------------------------

print("=== CB-2704 Smoke Test ===\n")

print("[1] Checking for active queue ...")
active_resp = get("/execute/queue/active")
print(f"    active: {active_resp.get('active')}")

if active_resp.get("active"):
    q = active_resp["queue"]
    existing_id = q.get("id")
    existing_status = q.get("status")
    print(f"    BLOCKED: existing active queue {existing_id} (status={existing_status}) is in flight.")
    print("    Cannot run smoke test while another queue is active — abort it manually first.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 2 — POST the queue with BUG as feature_id
# ---------------------------------------------------------------------------

print("\n[2] POSTing queue with BUG parent (CB-2671) ...")

payload = {
    "feature_id":  BUG_ID,
    "feature_key": BUG_KEY,
    "project_id":  PROJECT_ID,
    "tasks": [
        {
            "issue_id":      CHILD_ID,
            "issue_key":     CHILD_KEY,
            "issue_title":   CHILD_TITLE,
            "execution_mode": "skip",
            "force": False,
        }
    ],
    "provider":    "claude_code",
    "auto_start":  False,   # do NOT start — we just want to confirm creation
}

try:
    status_code, resp = post("/execute/queue", payload)
    print(f"    HTTP status: {status_code}")
    print(f"    Response: {json.dumps(resp, indent=4)}")
    QUEUE_CREATED = True
    created_queue_id = resp.get("id") or resp.get("queue_id")
except urllib.error.HTTPError as e:
    err_body = e.read().decode()
    print(f"    HTTP ERROR {e.code}: {err_body}")
    QUEUE_CREATED = False
    created_queue_id = None

# ---------------------------------------------------------------------------
# Step 3 — Verify queue is visible in active endpoint
# ---------------------------------------------------------------------------

if QUEUE_CREATED and created_queue_id:
    print(f"\n[3] Verifying queue {created_queue_id} in /execute/queue/active ...")
    active2 = get("/execute/queue/active")
    print(f"    active: {active2.get('active')}")
    if active2.get("active"):
        q2 = active2["queue"]
        print(f"    Queue id={q2.get('id')}, status={q2.get('status')}, feature_key={q2.get('feature_key')}")

    # ---------------------------------------------------------------------------
    # Step 4 — Abort immediately (don't let it run)
    # ---------------------------------------------------------------------------
    print(f"\n[4] Aborting queue {created_queue_id} immediately ...")
    st_abort, abort2 = post(f"/execute/queue/{created_queue_id}/abort", {"action": "leave"})
    print(f"    Abort ({st_abort}): {abort2}")

# ---------------------------------------------------------------------------
# Step 5 — Post comment on CB-2704
# ---------------------------------------------------------------------------

print("\n[5] Posting result comment on CB-2704 ...")

if QUEUE_CREATED:
    comment_text = (
        "## CB-2704 Smoke Test Result — PASS\n\n"
        "**Request:** `POST /api/execute/queue` with `feature_id` set to "
        "`fb7fca2d-790c-442d-a976-446ec40d3750` (CB-2671, type=BUG)\n\n"
        f"**HTTP Status:** 200/201 — queue created successfully\n\n"
        f"**Queue ID:** `{created_queue_id}`\n\n"
        "**Conclusion:** The endpoint does NOT enforce that `feature_id` refers to "
        "a FEATURE-type issue. It validates only that the issue exists in the DB "
        "(line 949 of `backend/api/execution.py`). A BUG parent is fully accepted.\n\n"
        "Queue was aborted immediately after creation (auto_start=False, then explicit abort). "
        "No child tasks were actually executed."
    )
else:
    comment_text = (
        "## CB-2704 Smoke Test Result — FAIL\n\n"
        "**Request:** `POST /api/execute/queue` with `feature_id` set to "
        "`fb7fca2d-790c-442d-a976-446ec40d3750` (CB-2671, type=BUG)\n\n"
        "**Result:** HTTP error — endpoint rejected BUG parent.\n\n"
        "A follow-up BUG must be filed under CB-2371 to relax the type check in "
        "`backend/api/execution.py`."
    )

st_comment, comment_resp = post_comment(CB2704_ID, comment_text)
print(f"    Comment posted ({st_comment}): id={comment_resp.get('id','?')}")

# ---------------------------------------------------------------------------
# Step 6 — PATCH CB-2704 → COMPLETED_WAITING_QA
# ---------------------------------------------------------------------------

print("\n[6] Patching CB-2704 → COMPLETED_WAITING_QA ...")
st_patch, patch_resp = patch_issue_status(CB2704_ID, "COMPLETED_WAITING_QA")
print(f"    PATCH ({st_patch}): status={patch_resp.get('status','?')}")

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

print("\n=== SUMMARY ===")
if QUEUE_CREATED:
    print("RESULT: PASS — POST /execute/queue accepts BUG as parent (no type check).")
    print("CB-2705 decision: frontend can wire AutoPilot button without backend changes.")
else:
    print("RESULT: FAIL — endpoint rejected BUG parent.")
    print("CB-2705 decision: file follow-up BUG under CB-2371.")
