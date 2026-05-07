"""
Retry QA task creation only (hierarchy already pushed). Reads QA spec from the
main push script and creates only QA tasks. Updates id-map.json with results.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error

# Re-import QA_TASKS spec from the main push script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
push_module = __import__("2026-05-03-cb-1951-push")
QA_TASKS = push_module.QA_TASKS
BASE = push_module.BASE
PROJECT_ID = push_module.PROJECT_ID
FEATURE_ID = push_module.FEATURE_ID
ID_MAP_PATH = push_module.ID_MAP_PATH


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body_txt[:300]}")
        raise


def main():
    with open(ID_MAP_PATH) as f:
        id_map = json.load(f)

    created = 0
    skipped = 0
    errors = 0

    for label, type_, priority, title, scenario, expected in QA_TASKS:
        existing = id_map["qa_tasks"].get(label)
        if existing and "error" not in existing:
            skipped += 1
            continue
        body = {
            "title": title,
            "scenario": scenario,
            "expectedResult": expected,
            "type": type_,
            "priority": priority,
            "linkedIssueIds": [FEATURE_ID],
        }
        try:
            qa = http("POST", f"/qa/projects/{PROJECT_ID}/tasks", body)
            id_map["qa_tasks"][label] = {
                "key": qa["key"], "id": qa["id"],
                "title": title, "type": type_, "priority": priority,
            }
            created += 1
            print(f"   {qa['key']}  {type_:9}  {label}  {title[:60]}")
        except Exception as e:
            id_map["qa_tasks"][label] = {"error": str(e)}
            errors += 1

    with open(ID_MAP_PATH, "w") as f:
        json.dump(id_map, f, indent=2)

    print(f"\n=== created={created}, skipped={skipped}, errors={errors}")
    print(f"Total QA tasks tracked: {len(id_map['qa_tasks'])}")


if __name__ == "__main__":
    sys.exit(main())
