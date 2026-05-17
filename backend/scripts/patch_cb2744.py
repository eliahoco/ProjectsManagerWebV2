"""Patch CB-2744 and CB-2737 to COMPLETED_WAITING_QA."""
import urllib.request
import json

PROJECT_ID = "1511e54f71dccd3fa79f67fe"
BASE = "http://localhost:8401/api"


def get_all_issues():
    items = []
    page = 1
    while True:
        url = f"{BASE}/projects/{PROJECT_ID}/issues?page={page}&pageSize=200"
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read())
        items.extend(d.get("items", []))
        if page >= d.get("totalPages", 1):
            break
        page += 1
    return items


def patch_issue(issue_id: str, body: dict):
    req = urllib.request.Request(
        f"{BASE}/issues/{issue_id}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main():
    print("Fetching all issues...")
    issues = get_all_issues()
    print(f"  Found {len(issues)} issues total")

    targets = {"CB-2744", "CB-2737"}
    matched = {i["key"]: i for i in issues if i.get("key") in targets}
    print(f"  Matched: {list(matched.keys())}")

    for key, issue in matched.items():
        print(f"  Patching {key} ({issue['id']}) → COMPLETED_WAITING_QA ...")
        result = patch_issue(issue["id"], {"status": "COMPLETED_WAITING_QA"})
        print(f"    → status now: {result.get('status')}")

    missing = targets - set(matched.keys())
    if missing:
        print(f"WARNING: did not find issues: {missing}")


if __name__ == "__main__":
    main()
