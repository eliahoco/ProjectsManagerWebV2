#!/usr/bin/env python3
"""CB-2216: mark CWQ after fix + audit gates.

Per Rule 29 (per-project per-session script paths) — this lives under
scripts/codeboard/ and never collides with sibling Claude sessions.

Behaviour:
- PATCH CB-2216 status -> COMPLETED_WAITING_QA
- Optionally appends a brief comment with the audit summary so the QA
  reviewer can see the gates that passed without diff-archeology.
"""

import json
import urllib.request
import urllib.error

ISSUE_ID = "50dcc0fd-22a6-4694-bdd8-e8f7f70b7fc7"  # CB-2216
API = "http://localhost:8401/api"


def patch_status(issue_id: str, status: str) -> dict:
    req = urllib.request.Request(
        f"{API}/issues/{issue_id}",
        data=json.dumps({"status": status}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    try:
        result = patch_status(ISSUE_ID, "COMPLETED_WAITING_QA")
        print(f"CB-2216 -> {result.get('status')}")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc!r}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
