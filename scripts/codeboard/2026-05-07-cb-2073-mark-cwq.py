"""CB-2073 [QA] E2-2: empty-state visual verification — mark COMPLETED_WAITING_QA.

Per-project + per-session helper (Rule 29). Single-shot.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


BASE = "http://localhost:8401/api"
ISSUE_ID = "4ab22d27-adf9-4e40-b678-957a985bb77b"  # CB-2073

EVIDENCE = """\
QA PASS — E2-2 empty-state verification (CB-2073)

Test FEATURE: CB-2128 "Issue Correlation & Grouping" (BACKLOG, no prior generation).
Backend probe: GET /api/features/4920efaa-7f60-430b-aa16-5cb5a6ee589b/documentation
  → 404 NOT_FOUND { resource: 'FeatureDocumentation', identifier: 'feature=CB-2128' }
  Confirms zero FeatureDocumentation row for this FEATURE.

Frontend (Chrome, viewport 1440x900) at /codeboard/features/{id}/documentation:
  ✅ Sparkles icon rendered
  ✅ Heading "No documentation generated yet"
  ✅ Subtitle "Click Generate to build documentation from execution history,
     tasks, and QA results for this feature."
  ✅ "Generate Documentation" CTA visible in empty-state card (centered)
  ✅ "Generate Documentation" CTA also visible in page header (top-right)
  ✅ FEATURE-only gate passed — header shows "CB-2128 Issue Correlation & Grouping"
  ✅ No error card (docError path) rendered — 404 correctly translated to null doc

Console errors observed (non-blocking, out of scope):
  - 404 on the documentation endpoint — EXPECTED, signals empty state
  - 500 on /api/projects/status — unrelated service-monitor poll, file under separate ticket if persistent

Evidence: docs/research/cb-2073-empty-state.png (full-page screenshot)
Component code paths verified:
  frontend/app/codeboard/features/[id]/documentation/page.tsx (EmptyState component, lines 185-201)
  frontend/components/codeboard/GenerateFeatureDocButton.tsx (CTA)
  backend/api/documentation.py:262 (404 when row missing — frontend hook converts to null)
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
    print("Posting evidence comment to CB-2073...")
    request(
        "POST",
        f"/issues/{ISSUE_ID}/comments",
        {"content": EVIDENCE, "author": "AI"},
    )
    print("Flipping CB-2073 → COMPLETED_WAITING_QA...")
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
