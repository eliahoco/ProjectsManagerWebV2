"""Mark CB-2665 IN_PROGRESS — document host->endpoint rename runbook."""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE = "CB-2665"


def patch(payload: dict) -> None:
    req = urllib.request.Request(
        f"{API}/issues/issue/{ISSUE}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.status, resp.read().decode("utf-8")[:200])


if __name__ == "__main__":
    patch({"status": "IN_PROGRESS"})
