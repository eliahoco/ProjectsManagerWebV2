#!/usr/bin/env python3
"""CB backlog audit — pull every issue, build the hierarchy, summarise.

Run by Jonny 2026-05-19 at Eli's request: full picture of what is in the
board (backlog / todo / in-progress / waiting-QA), grouped by FEATURE/EPIC,
plus a UI-vs-DB count cross-check.
"""
import json
import urllib.request
from collections import Counter, defaultdict

API = "http://localhost:8401/api"
PROJECT = "1511e54f71dccd3fa79f67fe"


def get(path):
    with urllib.request.urlopen(f"{API}{path}") as r:
        return json.loads(r.read())


def pull_all():
    first = get(f"/projects/{PROJECT}/issues?page=1")
    pages = first.get("totalPages", 1)
    items = list(first.get("items", []))
    for p in range(2, pages + 1):
        items.extend(get(f"/projects/{PROJECT}/issues?page={p}").get("items", []))
    return items, first.get("total")


def main():
    items, total = pull_all()
    print(f"DB total reported: {total}   |   issues pulled: {len(items)}")
    print()

    by_status = Counter(i.get("status") for i in items)
    by_type = Counter(i.get("type") for i in items)
    print("BY STATUS:", dict(by_status))
    print("BY TYPE:  ", dict(by_type))
    print()

    by_id = {i["id"]: i for i in items}
    children = defaultdict(list)
    for i in items:
        if i.get("parentId"):
            children[i["parentId"]].append(i)

    # Top-level FEATUREs and EPICs (the storytelling rows Eli wants)
    tops = [i for i in items if i.get("type") in ("FEATURE", "EPIC")
            and (not i.get("parentId") or i.get("parentId") not in by_id)]
    tops.sort(key=lambda x: x.get("key", ""))

    def descendants(iid):
        out = []
        stack = list(children.get(iid, []))
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(children.get(n["id"], []))
        return out

    print(f"=== {len(tops)} top-level FEATURE/EPIC items ===\n")
    rows = []
    for t in tops:
        desc = descendants(t["id"])
        st = Counter(d.get("status") for d in desc)
        row = {
            "key": t.get("key"),
            "type": t.get("type"),
            "title": t.get("title"),
            "status": t.get("status"),
            "priority": t.get("priority"),
            "children": len(desc),
            "child_status": dict(st),
            "description": (t.get("description") or "")[:600],
        }
        rows.append(row)
        print(f"{row['key']:>9} [{row['type']:7}] {row['status']:22} pri={row['priority']:8} "
              f"children={row['children']:3}  {row['title'][:80]}")
        if st:
            print(f"           child status: {dict(st)}")

    # Orphan issues (no resolvable parent, not FEATURE/EPIC)
    orphans = [i for i in items
               if i.get("type") not in ("FEATURE", "EPIC")
               and (not i.get("parentId") or i.get("parentId") not in by_id)]
    print(f"\n=== {len(orphans)} orphan TASK/STORY/BUG/SUBTASK (no resolvable parent) ===")
    o_status = Counter(o.get("status") for o in orphans)
    print("orphan status:", dict(o_status))

    # "studio" feature search
    print("\n=== items mentioning 'studio' ===")
    for i in items:
        blob = f"{i.get('title','')} {i.get('description','')}".lower()
        if "studio" in blob:
            print(f"  {i.get('key')} [{i.get('type')}] {i.get('status')}  {i.get('title','')[:80]}")

    # dump full data for the table-build step
    with open("/Volumes/Seagate/Claude/ProjectsManagerWebV2Production/scripts/codeboard/2026-05-19-backlog-dump.json", "w") as f:
        json.dump({"total": total, "pulled": len(items),
                   "by_status": dict(by_status), "by_type": dict(by_type),
                   "tops": rows, "orphan_status": dict(o_status),
                   "items": items}, f, indent=1)
    print("\nfull dump -> scripts/codeboard/2026-05-19-backlog-dump.json")


if __name__ == "__main__":
    main()
