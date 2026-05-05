#!/usr/bin/env python3
"""
CB-2032 — End-to-end API regression for CB-1955 (Issue Correlation & Grouping).

Substitutes Chrome MCP regression (CB-2033..CB-2037) with API-driven smoke
tests when the browser extension is disconnected. Verifies the full
backend + integration logic that the Chrome tests would have exercised:

  CB-2033 — create-group flow                  → here, via POST /groups
  CB-2034 — relation lifecycle                 → here, POST/GET/DELETE /relations
  CB-2035 — cycle prevention                   → here, BLOCKS A→B + B→A → 409
  CB-2036 — aggregate status updates           → here, member status flip → fresh GET
  CB-2037 — cascade-up still works (CB-1941)   → here, child CWQ → parent CWQ

UI visual checks (drag-to-reorder, modal layout, kanban segmented bar
render) are NOT covered — those need Chrome MCP or a manual pass.

Idempotent: cleans up after itself. Safe to re-run. Aborts on first
unexpected response.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8401/api"
PMV2_PROJECT_ID = "1511e54f71dccd3fa79f67fe"


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None


def assert_eq(actual, expected, msg: str):
    if actual != expected:
        print(f"  FAIL: {msg}: expected {expected!r}, got {actual!r}", file=sys.stderr)
        sys.exit(1)
    print(f"  PASS: {msg}")


def assert_in(value, container, msg: str):
    if value not in container:
        print(f"  FAIL: {msg}: {value!r} not in {container!r}", file=sys.stderr)
        sys.exit(1)
    print(f"  PASS: {msg}")


# ----------------------------------------------------------------------------
# Setup — create 4 disposable issues we'll use as test fixtures
# ----------------------------------------------------------------------------

print("=" * 60)
print("CB-2032 regression: CB-1955 Issue Correlation & Grouping")
print("=" * 60)
print()
print("Step 0: create 4 disposable test issues...")
test_issues = []
for i in range(4):
    status, body = http(
        "POST",
        f"/projects/{PMV2_PROJECT_ID}/issues",
        {
            "type": "TASK",
            "title": f"CB-2032 regression fixture {i+1} (auto-cleanup)",
            "priority": "LOW",
            "reporter": "AI",
            "labels": "cb-2032-regression-fixture",
            "status": "BACKLOG",
        },
    )
    assert_eq(status, 201, f"create fixture {i+1}")
    test_issues.append(body)
    print(f"    fixture {i+1}: {body['key']} ({body['id']})")
fixture_ids = [i["id"] for i in test_issues]
print()


# ----------------------------------------------------------------------------
# CB-2033 — create-group flow
# ----------------------------------------------------------------------------
print("CB-2033 — create-group flow:")
status, group = http(
    "POST",
    f"/projects/{PMV2_PROJECT_ID}/groups",
    {
        "title": "CB-2032 regression group",
        "description": "Auto-created by regression script — safe to delete.",
        "issueIds": fixture_ids[:3],  # first 3 of 4 (backend schema is `issueIds`)
    },
)
assert_eq(status, 201, "POST /groups returns 201")
group_id = group["id"]
print(f"  Created group {group_id}")
# POST response shape may not inline memberCount — fetch detail to confirm
status, detail0 = http("GET", f"/groups/{group_id}")
assert_eq(status, 200, "GET group detail")
assert_eq(len(detail0.get("members", [])), 3, "members list has 3 entries")
print()


# ----------------------------------------------------------------------------
# CB-2034 — relation lifecycle
# ----------------------------------------------------------------------------
print("CB-2034 — relation lifecycle:")
# Create RELATES_TO relation between fixture 1 and fixture 2
status, link = http(
    "POST",
    f"/issues/{fixture_ids[0]}/relations",
    {"toIssueId": fixture_ids[1], "linkType": "RELATES_TO"},
)
assert_eq(status, 201, "POST /relations returns 201")
relation_id = link["id"]
assert_eq(link["fromIssueId"], fixture_ids[0], "fromIssueId matches source")
assert_eq(link["toIssueId"], fixture_ids[1], "toIssueId matches target")
assert_eq(link["linkType"], "RELATES_TO", "linkType matches")

# GET relations on source
status, body = http("GET", f"/issues/{fixture_ids[0]}/relations")
assert_eq(status, 200, "GET /relations returns 200")
out_targets = [r["toIssueId"] for r in body["outbound"]]
assert_in(fixture_ids[1], out_targets, "fixture 2 in outbound from fixture 1")

# RELATES_TO is symmetric — companion row should make fixture 2 see fixture 1 too
status, body = http("GET", f"/issues/{fixture_ids[1]}/relations")
assert_eq(status, 200, "GET fixture 2 relations returns 200")
all_related = [r["toIssueId"] for r in body["outbound"]] + [
    r["fromIssueId"] for r in body["inbound"]
]
assert_in(fixture_ids[0], all_related, "fixture 1 visible from fixture 2 (symmetric)")

# DELETE the relation (auto-deletes companion)
status, body = http("DELETE", f"/issues/{fixture_ids[0]}/relations/{relation_id}")
assert_in(status, (200, 204), "DELETE /relations succeeds")
print(f"  DELETE response: status={status}, body={body}")

# Confirm gone from both sides
status, body = http("GET", f"/issues/{fixture_ids[0]}/relations")
assert_eq(len(body["outbound"]), 0, "outbound empty after DELETE")
status, body = http("GET", f"/issues/{fixture_ids[1]}/relations")
assert_eq(len(body["outbound"]) + len(body["inbound"]), 0, "fixture 2 also clean (companion removed)")
print()


# ----------------------------------------------------------------------------
# CB-2035 — cycle prevention
# ----------------------------------------------------------------------------
print("CB-2035 — cycle prevention:")
# A BLOCKS B
status, link1 = http(
    "POST",
    f"/issues/{fixture_ids[0]}/relations",
    {"toIssueId": fixture_ids[1], "linkType": "BLOCKS"},
)
assert_eq(status, 201, "A BLOCKS B creates")

# B BLOCKS A — should fail with cycle
status, body = http(
    "POST",
    f"/issues/{fixture_ids[1]}/relations",
    {"toIssueId": fixture_ids[0], "linkType": "BLOCKS"},
)
assert_eq(status, 409, "B BLOCKS A returns 409 (cycle)")
assert_eq(body.get("code"), "CYCLE_DETECTED", "code = CYCLE_DETECTED")
print(f"  Cycle response: code={body.get('code')}, message={body.get('message')[:60]}")

# Cleanup the BLOCKS relation
http("DELETE", f"/issues/{fixture_ids[0]}/relations/{link1['id']}")
print()


# ----------------------------------------------------------------------------
# CB-2036 — aggregate status updates
# ----------------------------------------------------------------------------
print("CB-2036 — aggregate status updates:")
# All 3 members are at BACKLOG (just created). aggregate completion should be 0%.
status, detail = http("GET", f"/groups/{group_id}")
assert_eq(status, 200, "GET /groups/{id}")
agg = detail["aggregateStatus"]
print(f"  Initial aggregate: dominantStatus={agg['dominantStatus']}, percent={agg['completionPercent']}")
assert_eq(int(agg["completionPercent"]), 0, "completionPercent = 0 (all BACKLOG)")

# Flip fixture 1 to CWQ
status, _ = http("PATCH", f"/issues/{fixture_ids[0]}", {"status": "COMPLETED_WAITING_QA"})
assert_eq(status, 200, "PATCH fixture 1 → CWQ")

# Re-fetch — completion should reflect 1/3 done
status, detail = http("GET", f"/groups/{group_id}")
agg = detail["aggregateStatus"]
print(f"  After 1 CWQ: dominantStatus={agg['dominantStatus']}, percent={agg['completionPercent']}")
# CWQ is in the "complete" set per backend logic; verify breakdown reflects it
breakdown = agg["statusBreakdown"]
assert_eq(breakdown.get("COMPLETED_WAITING_QA", 0), 1, "1 member at CWQ in breakdown")
assert_eq(breakdown.get("BACKLOG", 0), 2, "2 members still at BACKLOG")
print()


# ----------------------------------------------------------------------------
# CB-2037 — cascade-up still works (CB-1941 regression check)
# ----------------------------------------------------------------------------
print("CB-2037 — cascade-up still works (CB-1941 regression check):")
# Use a fresh STORY+TASK pair (cascade only walks parentId chain, not group membership)
status, story = http(
    "POST",
    f"/projects/{PMV2_PROJECT_ID}/issues",
    {
        "type": "STORY",
        "title": "CB-2032 cascade-test STORY (auto-cleanup)",
        "priority": "LOW",
        "reporter": "AI",
        "labels": "cb-2032-regression-fixture",
        "status": "BACKLOG",
    },
)
assert_eq(status, 201, "create STORY")
story_id = story["id"]

status, task = http(
    "POST",
    f"/projects/{PMV2_PROJECT_ID}/issues",
    {
        "type": "TASK",
        "title": "CB-2032 cascade-test TASK (auto-cleanup)",
        "priority": "LOW",
        "reporter": "AI",
        "labels": "cb-2032-regression-fixture",
        "status": "BACKLOG",
        "parentId": story_id,
    },
)
assert_eq(status, 201, "create TASK under STORY")
task_id = task["id"]

# Flip TASK → CWQ (only child) → STORY should cascade to CWQ
status, _ = http("PATCH", f"/issues/{task_id}", {"status": "COMPLETED_WAITING_QA"})
assert_eq(status, 200, "PATCH TASK → CWQ")
time.sleep(0.5)  # cascade is sync but give the DB a moment for safety
status, fresh_story = http("GET", f"/issues/{story_id}")
assert_eq(fresh_story["status"], "COMPLETED_WAITING_QA", "STORY auto-cascaded to CWQ")
print(f"  STORY cascaded ✓ updatedAt={fresh_story['updatedAt']}")

# Reverse: TASK → BACKLOG should cascade STORY back to IN_PROGRESS (CB-1943)
status, _ = http("PATCH", f"/issues/{task_id}", {"status": "BACKLOG"})
time.sleep(0.5)
status, fresh_story = http("GET", f"/issues/{story_id}")
assert_eq(fresh_story["status"], "IN_PROGRESS", "STORY auto-reverted to IN_PROGRESS (CB-1943)")
print(f"  STORY reverted ✓ updatedAt={fresh_story['updatedAt']}")
print()


# ----------------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------------
print("Cleanup: removing test fixtures...")
http("DELETE", f"/groups/{group_id}")
print(f"  Deleted group {group_id}")
for iid in fixture_ids + [story_id, task_id]:
    s, _ = http("DELETE", f"/issues/{iid}")
    print(f"  Deleted issue {iid}: HTTP {s}")
print()

print("=" * 60)
print("CB-2032 regression PASSED — backend feature integration verified.")
print("UI visual checks (modal layout, kanban segmented bar, drag-reorder)")
print("still need a manual or Chrome-MCP pass.")
print("=" * 60)
