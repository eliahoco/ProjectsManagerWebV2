"""Mark CB-2732 as COMPLETED_WAITING_QA.

Per Bible Rule 22, only Eli promotes to DONE. CWQ is the auto-mark.
"""

from __future__ import annotations

import json
import sys
from urllib import request as urlrequest
from urllib.error import HTTPError

API = "http://localhost:8401/api"
ISSUE_ID = "e389341a-af67-4253-b85e-b79e1f517ce2"  # CB-2732


def main() -> int:
    payload = json.dumps({"status": "COMPLETED_WAITING_QA"}).encode("utf-8")
    req = urlrequest.Request(
        f"{API}/issues/{ISSUE_ID}",
        data=payload,
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} on PATCH: {body}") from e
    print(f"CB-2732 -> {body.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
