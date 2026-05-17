"""Mark CB-2664 IN_PROGRESS — visibility-return phase reset for RagStatusCard interval."""
import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE = "CB-2664"


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
