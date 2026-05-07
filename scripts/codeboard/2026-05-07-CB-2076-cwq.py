"""CB-2076 [QA] E2-5: techStack badges render from JSON array — mark COMPLETED_WAITING_QA.

Per-project + per-session helper (Rule 29). Single-shot.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


BASE = "http://localhost:8401/api"
ISSUE_ID = "ddb70fbc-41fd-4e39-ba11-2aa559b3516d"  # CB-2076

EVIDENCE = """\
QA PASS — E2-5: techStack badges render from JSON array (CB-2076)

Acceptance criterion: techStack JSON `["FastAPI", "Next.js"]` -> 2 badges visible.

Method: deterministic Vitest component test + live Chrome render of the same
code path against CB-2038 (id 94aff46e-715b-49cf-8f69-7112be5bd211).

Component under test
  frontend/components/codeboard/FeatureDocumentationView.tsx
    - parseTechStack helper (line 50-60): JSON.parse + Array.isArray guard +
      string filter + Set dedupe
    - render block (line 278-295): Section + Badge.map() with cyan border
      monospace text-[11px], one Badge per unique entry, hidden when empty

Regression artifact (added)
  frontend/tests/components/FeatureDocumentationView.test.tsx — 8 cases,
  all green:
    1. JSON `["FastAPI", "Next.js"]`        -> 2 badges (literal acceptance)
    2. duplicates                            -> deduped to ["FastAPI","Next.js"]
    3. empty array `[]`                      -> Tech Stack section hidden
    4. invalid JSON `"not-json"`             -> section hidden
    5. non-array JSON `{"foo":"bar"}`        -> section hidden
    6. mixed-type entries                    -> non-strings filtered
    7. techStack undefined                   -> section hidden
    8. techStack null                        -> section hidden
  Run: `npx vitest run tests/components/FeatureDocumentationView.test.tsx`
  Result: 8 passed (8) in 16.55s

Live Chrome render (real env)
  URL : http://localhost:3601/codeboard/features/94aff46e-.../documentation
  Tech Stack section: present
  Backend techStack JSON: 70 unique string entries
  DOM badge count under section.flex.flex-wrap: 70 (1:1 with JSON entries)
  First entries observed: ServiceMonitor, AutoPilotQueueService, RAGService,
    AutoPilotFloatingBar, AutoPilotContext, ...
  Spec subset (FastAPI, Next.js) both present in the live render.
  Screenshot: docs/research/cb-2076-techstack-badges-live.png

Audit gates
  - code-reviewer: ship-as-is. One MEDIUM (brittle parentElement.children
    selector) and two LOW findings addressed before commit (introduced
    getBadgeTexts helper using stable .flex.flex-wrap container, added
    null/undefined cases).
  - security-auditor: not run. Test file imports real types only, no fetch,
    no DOM injection, no external network. parseTechStack itself is
    JSON.parse wrapped in try/catch with Array.isArray + typeof string
    guards — no XSS surface introduced by this QA artifact.
  - tsc --noEmit: zero errors in the new test file.

Acceptance criterion satisfied (deterministic + live).
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
    print("Posting evidence comment to CB-2076...")
    request(
        "POST",
        f"/issues/{ISSUE_ID}/comments",
        {"content": EVIDENCE, "author": "AI"},
    )
    print("Flipping CB-2076 -> COMPLETED_WAITING_QA...")
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
