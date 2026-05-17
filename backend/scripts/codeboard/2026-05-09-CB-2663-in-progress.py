"""CB-2663 → IN_PROGRESS (per-project per-session script — Rule 29)."""
import json
import urllib.request

API = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
ISSUE_KEY = "CB-2663"


def get_id_by_key(key: str) -> str:
    with urllib.request.urlopen(
        f"{API}/projects/{PROJECT_ID}/issues?pageSize=1000", timeout=15
    ) as r:
        items = json.loads(r.read().decode("utf-8"))["items"]
    for it in items:
        if it.get("key") == key:
            return it["id"]
    raise SystemExit(f"{key} not found in first page")


def patch(issue_id: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}/issues/{issue_id}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    iid = get_id_by_key(ISSUE_KEY)
    print(f"{ISSUE_KEY} → {iid}")
    print(patch(iid, {"status": "IN_PROGRESS"}))


if __name__ == "__main__":
    main()
