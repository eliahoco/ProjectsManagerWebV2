#!/usr/bin/env python3
"""Mark CB-2093 (T3.3.4 E3 full regression) COMPLETED_WAITING_QA.

Per Bible Rule 29: per-project per-session script path.
Regression artifact: backend/tests/test_e3_full_regression.py
Audit report:        docs/research/cb-2093-e3-regression-report.md
"""
import json
import urllib.request

ISSUE_ID = "c73de4d4-19c9-4564-9836-b2d198a6a912"  # CB-2093
URL = f"http://localhost:8401/api/issues/{ISSUE_ID}"

body = json.dumps({"status": "COMPLETED_WAITING_QA"}).encode()
req = urllib.request.Request(
    URL,
    data=body,
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    print(resp.status, resp.read().decode()[:300])
