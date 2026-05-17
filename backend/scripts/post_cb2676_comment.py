"""Post T5 comment on CB-2676 and mark COMPLETED_WAITING_QA."""
import urllib.request
import json

def comment(iid, content):
    req = urllib.request.Request(
        f'http://localhost:8401/api/issues/{iid}/comments',
        data=json.dumps({'content': content, 'author': 'AI'}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    urllib.request.urlopen(req, timeout=15).read()

def patch_status(iid, status):
    req = urllib.request.Request(
        f'http://localhost:8401/api/issues/{iid}',
        data=json.dumps({'status': status}).encode(),
        headers={'Content-Type': 'application/json'}, method='PATCH',
    )
    urllib.request.urlopen(req, timeout=15).read()

CB_2676 = '306b4caf-7536-4dd9-bfa4-f4c1f263d371'

body = """## T5 Resume Defensive Fallback + run_queue re-launch -- CB-2676

Two fixes applied:

---

### Fix A -- Defensive issueKey/issueTitle fallback in _execute_task

**File:** backend/services/autopilot_queue_service.py, inserted before task.status = TaskStatus.RUNNING

When task.issue_key or task.issue_title is empty:
1. Opens an async DB session and fetches the Issue record by task.issue_id
2. Populates the empty fields on the in-memory QueueTask
3. Emits logging.warning() with [AutoPilot] CB-2676 fallback: prefix to detect future drift
4. Calls _persist() with event type task_key_backfill to write the populated values back
5. Wrapped in try/except -- any DB error logs and continues (never crashes the queue)

---

### Fix B -- Re-launch run_queue coroutine on resume after crash recovery (CRITICAL)

**File:** backend/api/execution.py, POST /queue/{queue_id}/resume endpoint

Root cause: after a backend crash, the run_queue asyncio coroutine is gone (queue._task is None).
resume_queue() only called queue._pause_event.set() -- no coroutine was waiting on it.

Fix detects queue._task is None or done, then:
  queue._task = create_tracked_task(
      autopilot_queue_service.run_queue(queue_id),
      name=f"autopilot-queue-{queue_id}",
  )

After this fix, when the user presses Resume after crash recovery:
1. resume_queue() clears pause bookkeeping and sets _pause_event
2. API endpoint detects queue._task is None (crash-recovery case)
3. Launches a new run_queue asyncio task
4. run_queue sets status=RUNNING, enters the while loop
5. _pause_event is already set so it skips the pause gate immediately
6. Calls _execute_task(queue.tasks[current_index]) -- Claude Code subprocess starts
7. GET /api/execute/sessions now returns the active session

This explains the observed symptom: sessions=[] after Resume because no subprocess was ever spawned.

---

### Syntax verification

All 4 modified files passed ast.parse() check (syntax clean).
"""

comment(CB_2676, body)
patch_status(CB_2676, 'COMPLETED_WAITING_QA')
print('T5 done')
