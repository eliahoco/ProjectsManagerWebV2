"""Mark CB-2666 (HIGH /api/projects perimeter) COMPLETED_WAITING_QA.

Per-session per-project script (Rule 29). Run from repo root or backend/.
"""

import json
import urllib.request

ISSUE_ID = "79c15de6-3cec-4914-a864-0c2fa05808ea"
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"
PAYLOAD = {"status": "COMPLETED_WAITING_QA"}

req = urllib.request.Request(
    URL,
    data=json.dumps(PAYLOAD).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PATCH",
)
with urllib.request.urlopen(req) as resp:
    body = json.loads(resp.read().decode("utf-8"))
    print("status:", resp.status)
    print("issue:", body.get("key"), "->", body.get("status"))
