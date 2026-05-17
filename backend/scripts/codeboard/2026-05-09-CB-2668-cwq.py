"""CB-2668 — flip ticket to COMPLETED_WAITING_QA + post a CWQ comment.

Rule 29 compliance: per-project, per-session path. Never write to a shared
`/tmp/` filename — sibling Claude sessions running in parallel would
overwrite each other's in-flight scripts.

CB-2668 fix summary
-------------------
FastAPI's default /docs + /redoc + /openapi.json published the full route
map (every path, every project_id-shaped param, every request/response
schema) to any Origin-less local caller. Combined with CB-2666 H-1 and
CB-2667 H-2, that route map turned isolated identifier disclosures into
a guided enumeration kit.

Fix:
  - `Settings.is_development` accepts only {"development", "dev"} (case-
    insensitive). Anything else — production / staging / unset / typos /
    padded values — returns False. Fail-closed by design.
  - `app.main` constructs FastAPI with `docs_url`, `redoc_url`,
    `openapi_url`, and (defense-in-depth) `swagger_ui_oauth2_redirect_url`
    set to None unless `settings.is_development` is True.

Audit gates (both passed, only LOW findings, all addressed before CWQ):
  - code-reviewer: README §3 → §3a cross-ref, decoupled `is_development`
    docstring from CB-2668-specific commentary, refactored test reload
    helper to a `@contextmanager` so cleanup is unconditional.
  - security-auditor: gate is fail-closed for casing / padding / unicode
    lookalikes; no side-channel re-leak (`/openapi.yaml` is not a route,
    `/docs/oauth2-redirect` is now explicitly None'd, debug=False keeps
    error pages from echoing the route map). Defense-in-depth pin on
    `swagger_ui_oauth2_redirect_url` was the one actionable suggestion.

Live regression:
  - dev .env (ENVIRONMENT=development) → /docs /redoc /openapi.json all 200.
  - temp uvicorn with ENVIRONMENT=production →
    /docs /redoc /openapi.json /docs/oauth2-redirect all 404,
    /api/health 200.

Test suite: 72/72 pass on `backend/tests/test_security.py`, including
the 8 new `TestDocsSurfacePerimeter` cases (helper matrix + production-
mode 404 across {production, staging, test, ""} + oauth2-redirect 404 +
dev-mode 200 across {development, dev}).
"""

from __future__ import annotations

import json
import urllib.request

API = "http://localhost:8401/api"
ISSUE_ID = "22ec8260-f295-4ff6-872b-43ede883c190"
ISSUE_KEY = "CB-2668"

CWQ_COMMENT = """\
# CB-2668 — COMPLETED_WAITING_QA

## Summary
Disabled FastAPI's default `/docs`, `/redoc`, `/openapi.json`, and
`/docs/oauth2-redirect` outside of development. Production / staging /
unset / typo'd `ENVIRONMENT` all lock the surface down.

## Files changed
- `backend/app/config.py` — new `Settings.is_development` property
  (case-insensitive match against `{"development", "dev"}`,
  fail-closed on every other value).
- `backend/app/main.py` — `FastAPI(...)` constructed with `docs_url`,
  `redoc_url`, `openapi_url`, and `swagger_ui_oauth2_redirect_url` set
  to None unless `settings.is_development` is True. The last URL is
  defense-in-depth — FastAPI today suppresses
  `/docs/oauth2-redirect` when `docs_url` is None, but pinning it
  explicitly survives an upstream refactor.
- `backend/tests/test_security.py` — new `TestDocsSurfacePerimeter`
  class (8 tests via parametrize): helper-alias matrix +
  production-mode 404 across {production, staging, test, ""} +
  oauth2-redirect 404 + development-mode 200 across {development,
  dev}. Reload helper restructured as `@contextmanager` so cleanup
  runs even if the import body raises.
- `backend/README.md` — flagged Swagger / ReDoc / OpenAPI as
  development-only; cross-references `DOC_PIPELINE_RUNBOOK.md` §3a.
- `backend/docs/DOC_PIPELINE_RUNBOOK.md` — added §3a covering the
  gate, the alias-acceptance table, and the rationale for choosing
  ENVIRONMENT-based gating over a token-gated middle ground.

## Audit gates
- **code-reviewer** — no CRITICAL / HIGH / MEDIUM findings. LOW
  findings (cross-ref rot, generic-property docstring, restore
  unconditional-cleanup) all addressed before this CWQ.
- **security-auditor** — no CRITICAL / HIGH / MEDIUM findings. LOW
  defense-in-depth pin on `swagger_ui_oauth2_redirect_url=None`
  applied. Confirmed gate is fail-closed against casing, padding,
  and unicode-lookalike inputs (`.lower()` does not fold fullwidth
  / Latin-extended characters to ASCII). No side-channel re-leak
  through `/openapi.yaml` (not a FastAPI route), error responses
  (debug=False), or other auto-mounted assets.

## Regression
- `pytest backend/tests/test_security.py` → **72 passed** (was 64
  before this change — 8 new `TestDocsSurfacePerimeter` cases).
- Live regression on a temp uvicorn with
  `ENVIRONMENT=production INTERNAL_API_TOKEN=temp` confirms all four
  doc routes return 404 while `/api/health` stays 200.
- Live dev backend on port 8401 still serves the three URLs as 200
  (positive path) — `.env` keeps `ENVIRONMENT=development`.

## Sibling tickets
This closes the third leg of the CB-2217 sec-audit follow-up
trio:

- CB-2666 H-1 (project enumeration via `/api/projects`) — gated
  via `INTERNAL_API_TOKEN` (CWQ).
- CB-2667 H-2 (per-project doc count via `/api/search/{id}/stats`)
  — gated via `INTERNAL_API_TOKEN` (CWQ).
- **CB-2668 M-1 (route-map publication via `/docs` etc.) — disabled
  outside development (this CWQ).**

The route map can no longer arbitrage the H-1 and H-2 disclosures
into a guided enumeration of every endpoint, schema, and parameter
shape on the backend.

## Out of scope
- Token-gated `/docs` for non-dev deploys: explicitly rejected in
  `DOC_PIPELINE_RUNBOOK.md` §3a. The route map has no operational
  use that survives a deploy; consumers that need the OpenAPI
  schema for codegen / contract tests should generate it offline
  from a `ENVIRONMENT=development` checkout and ship the JSON as a
  build artifact.
- A lint asserting `app.routes` is never serialized in any response
  body — flagged by security-auditor as a future-regression
  follow-up. Out of scope for this MEDIUM bug fix.

Ready for Eli's QA.
"""


def patch(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        method="PATCH",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    updated = patch(
        f"/issues/{ISSUE_ID}",
        {"status": "COMPLETED_WAITING_QA"},
    )
    print(
        f"PATCH /issues/{ISSUE_ID} → status={updated.get('status')!r}"
    )

    comment = post(
        f"/issues/{ISSUE_ID}/comments",
        {"content": CWQ_COMMENT, "author": "AI"},
    )
    print(
        f"POST /issues/{ISSUE_ID}/comments → id={comment.get('id')!r}"
    )


if __name__ == "__main__":
    main()
