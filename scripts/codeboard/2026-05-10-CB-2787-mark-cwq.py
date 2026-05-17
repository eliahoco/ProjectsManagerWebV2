"""CB-2787 — mark COMPLETED_WAITING_QA after fix + tests + audits.

Per Rule 29: per-project per-session script path (no /tmp/ collisions).
"""

import json
import urllib.request

ISSUE_ID = "b9d7fc10-f570-40b6-980a-0b5912b99bbc"
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"

payload = {"status": "COMPLETED_WAITING_QA"}
req = urllib.request.Request(
    URL,
    method="PATCH",
    headers={"Content-Type": "application/json"},
    data=json.dumps(payload).encode(),
)
with urllib.request.urlopen(req) as resp:
    body = resp.read().decode()
    print("status:", resp.status)
    print(body[:500])
