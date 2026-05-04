#!/usr/bin/env python3
"""
CB-2024 — One-time migration: convert CB-1945 fake umbrella to a real group.

Context
=======
CB-1945 was filed as a parent BUG with CB-1946 + CB-1954 as fake child TASKs
(via parentId) on 2026-04-30, before the Issue Group entity existed. Now
that EPIC 3 (Groups API) is shipped + tested, this script converts that
shoehorned hierarchy into the proper IssueGroup the feature was designed
for.

Idempotent — safe to re-run. Detects the group by title, detects existing
membership before adding, leaves parentId=null on already-detached children.

Acceptance (CB-2025 / CB-2026)
==============================
After this runs:
- An IssueGroup titled "Cascade walker hardening" exists in PMv2 project.
- CB-1945, CB-1946, CB-1954 are all members of that group.
- CB-1946.parentId and CB-1954.parentId are NULL (no longer fake children).
- Cascade walker behaviour for the legitimate CMOI-* tree is unchanged.

Run from PMv2 root:
    python3 scripts/codeboard/2026-05-05-cb-2024-migrate-cb-1945-to-group.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8401/api"
PMV2_PROJECT_ID = "1511e54f71dccd3fa79f67fe"
GROUP_TITLE = "Cascade walker hardening"
GROUP_DESCRIPTION = (
    "Umbrella for the cascade-walker concurrency + N+1 cleanup work. "
    "Originally filed as a fake parentId hierarchy under CB-1945 because "
    "the Group entity did not exist yet; migrated to a real IssueGroup "
    "by CB-2024 once EPIC 3 (Groups API) shipped under CB-1955."
)

# CB-1945 / 1946 / 1954 IDs are stable — fetched dynamically below to avoid
# encoding state that could drift if an issue is recreated.
MEMBER_KEYS = ["CB-1945", "CB-1946", "CB-1954"]


def http_get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def http_post(path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def http_patch(path: str, body: dict) -> int:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return r.status


def fetch_all_project_issues() -> list[dict]:
    items = []
    page = 1
    while True:
        d = http_get(
            f"/projects/{PMV2_PROJECT_ID}/issues?page={page}&pageSize=200"
        )
        items.extend(d["items"])
        if page >= d["totalPages"]:
            break
        page += 1
    return items


def find_existing_group() -> dict | None:
    """Idempotency check: return the matching group if title already used."""
    page = 1
    while True:
        d = http_get(
            f"/projects/{PMV2_PROJECT_ID}/groups?page={page}&pageSize=100"
        )
        for g in d["items"]:
            if g["title"] == GROUP_TITLE:
                return g
        if page >= d.get("totalPages", 1):
            break
        page += 1
    return None


def main() -> int:
    print(f"Migrating CB-1945 fake umbrella → real IssueGroup '{GROUP_TITLE}'")
    print()

    # 1. Resolve member issue IDs from keys
    print("Step 1: resolving member issue IDs by key...")
    project_issues = fetch_all_project_issues()
    by_key = {i["key"]: i for i in project_issues}
    member_ids: list[str] = []
    for k in MEMBER_KEYS:
        if k not in by_key:
            print(f"  ERROR: {k} not found in project — aborting.", file=sys.stderr)
            return 2
        member_ids.append(by_key[k]["id"])
        print(f"  {k} → {by_key[k]['id']}")
    print()

    # 2. Find or create the group
    print(f"Step 2: find-or-create IssueGroup '{GROUP_TITLE}'...")
    existing = find_existing_group()
    if existing:
        print(f"  Group already exists: {existing['id']} — skipping create.")
        group_id = existing["id"]
    else:
        status, body = http_post(
            f"/projects/{PMV2_PROJECT_ID}/groups",
            {
                "title": GROUP_TITLE,
                "description": GROUP_DESCRIPTION,
                "memberIssueIds": member_ids,
            },
        )
        if status not in (200, 201):
            print(
                f"  ERROR creating group: HTTP {status} — {json.dumps(body)[:300]}",
                file=sys.stderr,
            )
            return 3
        group_id = body["id"]
        member_count = body.get("memberCount", "?")
        print(f"  Created group {group_id} with {member_count} initial members.")
    print()

    # 3. Ensure all 3 members are present (idempotent — group existed but
    #    might be missing some members).
    print("Step 3: ensure all 3 members are in the group...")
    detail = http_get(f"/groups/{group_id}")
    current_member_issue_ids = {m["issueId"] for m in detail.get("members", [])}
    missing = [mid for mid in member_ids if mid not in current_member_issue_ids]
    if missing:
        status, body = http_post(
            f"/groups/{group_id}/members", {"issueIds": missing}
        )
        if status not in (200, 201):
            print(
                f"  ERROR adding missing members: HTTP {status} — "
                f"{json.dumps(body)[:300]}",
                file=sys.stderr,
            )
            return 4
        print(f"  Added {len(body.get('added', []))} member(s).")
    else:
        print("  All 3 members already present — no-op.")
    print()

    # 4. Detach the fake parentId chain on CB-1946 + CB-1954.
    print("Step 4: detach fake parentId on CB-1946 + CB-1954...")
    for k in ["CB-1946", "CB-1954"]:
        issue = by_key[k]
        if issue.get("parentId") is None:
            print(f"  {k}: parentId already NULL — skip.")
            continue
        status = http_patch(f"/issues/{issue['id']}", {"parentId": None})
        print(f"  {k}: parentId NULL — HTTP {status}.")
    print()

    # 5. Verify final state
    print("Step 5: verify final state...")
    final_detail = http_get(f"/groups/{group_id}")
    print(f"  Group {group_id} title='{final_detail['title']}'")
    print(f"  memberCount: {final_detail.get('memberCount', '?')}")
    for m in final_detail.get("members", []):
        # member issue summary is embedded
        i_key = m.get("issue", {}).get("key", "?")
        i_status = m.get("issue", {}).get("status", "?")
        print(f"    member: {i_key} [{i_status}]")
    project_issues_after = fetch_all_project_issues()
    by_key_after = {i["key"]: i for i in project_issues_after}
    for k in ["CB-1946", "CB-1954"]:
        pid = by_key_after[k].get("parentId")
        ok = "OK" if pid is None else f"FAIL (parentId={pid})"
        print(f"  {k} parentId NULL? {ok}")
    print()
    print("Migration complete (CB-2024).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
