"""
CB-2740 — Mark as COMPLETED_WAITING_QA and post summary comment on CB-2737.
"""
import urllib.request
import json


def patch(key, body):
    items = []
    for page in range(1, 50):
        with urllib.request.urlopen(
            f'http://localhost:8401/api/projects/1511e54f71dccd3fa79f67fe/issues?page={page}&pageSize=200',
            timeout=30,
        ) as r:
            d = json.loads(r.read())
        items.extend(d.get('items', []))
        if page >= d.get('totalPages', 1):
            break
    x = next((i for i in items if i.get('key') == key), None)
    if x:
        req = urllib.request.Request(
            f'http://localhost:8401/api/issues/{x["id"]}',
            data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'},
            method='PATCH',
        )
        urllib.request.urlopen(req, timeout=15).read()
        print(f'PATCH {key} -> {body}')
        return x['id']
    else:
        print(f'ERROR: {key} not found')
        return None


def post_comment(issue_id, body_text):
    payload = json.dumps({'content': body_text}).encode()
    req = urllib.request.Request(
        f'http://localhost:8401/api/issues/{issue_id}/comments',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    urllib.request.urlopen(req, timeout=15).read()
    print(f'Comment posted on {issue_id}')


# 1. Mark CB-2740 as COMPLETED_WAITING_QA
patch('CB-2740', {'status': 'COMPLETED_WAITING_QA'})

# 2. Post summary comment on parent BUG CB-2737
bug_id = patch.__globals__['patch']('CB-2737', {})  # just lookup

items = []
for page in range(1, 50):
    with urllib.request.urlopen(
        f'http://localhost:8401/api/projects/1511e54f71dccd3fa79f67fe/issues?page={page}&pageSize=200',
        timeout=30,
    ) as r:
        d = json.loads(r.read())
    items.extend(d.get('items', []))
    if page >= d.get('totalPages', 1):
        break

bug = next((i for i in items if i.get('key') == 'CB-2737'), None)
if bug:
    summary = """CB-2740 COMPLETE — Retry UI for failed AutoPilot tasks shipped.

## What was built

**Per-task Retry button (AutoPilotFloatingBar.tsx)**
- Each task row with `status === 'failed'` now renders a RotateCcw icon button
- Click POSTs to `POST /api/execute/queue/{queueId}/task/{order}/reset`
- Button shows spinner while in-flight; toast confirms success/error
- While `queueStatus === 'running'`, button is disabled with tooltip "Pause queue first to retry tasks"

**Bulk Retry header (expanded view)**
- When expanded view has failed tasks, a "Retry all failed (N)" button appears above the task list
- Loops sequentially over all failed tasks, updates progress via toast
- Disabled + styled gray when queue is running; active amber when paused

**Disabled state**
- Backend returns 409 when queue is running — frontend shows toast "Pause the queue first to retry tasks"
- Button disabled attribute set + cursor-not-allowed styling when queueIsRunning

**Tests — 6 new tests added to AutoPilotFloatingBar.test.tsx**
- Shows retry button for failed task in expanded queue
- POST fires to correct endpoint on click
- Toast shown after success
- Button disabled when queueStatus is running
- Bulk "Retry all failed (N)" button visible with failed tasks
- Bulk button absent when no failed tasks

**Screenshots**
- docs/research/2026-05-09-cb-2740-retry-button-*.png (5 screenshots)

All 484 Vitest tests pass. Zero regressions."""
    post_comment(bug['id'], summary)
