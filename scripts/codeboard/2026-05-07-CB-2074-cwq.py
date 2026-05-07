"""CB-2074 [QA] E2-3: Generate creates row + 6 sections populate — mark COMPLETED_WAITING_QA.

Per-project + per-session helper (Rule 29). Single-shot.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


BASE = "http://localhost:8401/api"
ISSUE_ID = "cfe7f7e5-5295-418c-b706-1b423972b41d"  # CB-2074

EVIDENCE = """\
QA PASS — E2-3: Generate creates row + 6 sections populate (CB-2074)

Method: backend row probe + live Chrome render + full-page screenshot.
Target FEATURE: CB-2038 (id 94aff46e-715b-49cf-8f69-7112be5bd211).

Backend (GET /api/features/.../documentation):
  embeddingId    : f6e011d460598184e3d8951747516f13
  lastIndexedAt  : 2026-05-06T22:14:06.024676
  totalTasks/completed/QA: 96 / 59 / 48
  Section sizes (no placeholders remain):
    overview        :  2,155 chars
    requirements    :    855 chars
    implementation  : 15,938 chars  (11 execution runs)
    architecture    :  7,177 chars
    techStack       :  2,223 chars  (parsed: 70 JSON entries)
    testingStrategy :  6,283 chars

Frontend (Chrome via Playwright @ localhost:3601):
  Page: /codeboard/features/{id}/documentation
  All six section H3s present in DOM:
    Tech Stack, Overview, Requirements, Implementation, Architecture, Testing Strategy
  Indexed badge: "Indexed 3h ago"
  Progress card: 96 / 59 / 48 / 0 / 0 (matches backend)
  Total rendered text: 34,239 chars

All six acceptance bullets ("non-empty content per section") pass.

Evidence:
  - docs/research/cb-2074-qa-report.md (full QA report with DOM inventory)
  - docs/research/cb-2074-qa-fullpage.png (fresh full-page screenshot)

Cross-refs: BUG-A (proxy 504 on Regenerate) and BUG-B (no auto-refetch after
504) discovered in CB-2071 are filed separately and do not block this task —
the persisted row exists, sections render on a normal page load.
"""


def request(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"HTTP {resp.status}: {body}")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}")


def main() -> None:
    print("Posting evidence comment to CB-2074...")
    request(
        "POST",
        f"/issues/{ISSUE_ID}/comments",
        {"content": EVIDENCE, "author": "AI"},
    )
    print("Flipping CB-2074 -> COMPLETED_WAITING_QA...")
    request(
        "PATCH",
        f"/issues/{ISSUE_ID}",
        {"status": "COMPLETED_WAITING_QA"},
    )
    time.sleep(0.2)
    final = request("GET", f"/issues/{ISSUE_ID}")
    print(f"  status: {final.get('status')}")
    print(f"  key:    {final.get('key')}")


if __name__ == "__main__":
    main()
