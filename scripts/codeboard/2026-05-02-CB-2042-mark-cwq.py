#!/usr/bin/env python3
"""Mark CB-2042 (chroma volume migration) COMPLETED_WAITING_QA.

Per Bible Rule 29: per-project per-session script path.
"""
import json
import urllib.request

ISSUE_ID = "241089c6-083f-4abc-8edd-7ad1536d53b3"  # CB-2042
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"

body = json.dumps({"status": "COMPLETED_WAITING_QA"}).encode()
req = urllib.request.Request(
    URL,
    data=body,
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    print(resp.status, resp.read().decode()[:200])
