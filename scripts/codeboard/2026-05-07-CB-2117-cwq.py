"""CB-2117 [BUG] F2 documentation router IDOR — mark COMPLETED_WAITING_QA.

Per-project + per-session helper (Bible rule 29). Single-shot.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


BASE = "http://localhost:8401/api"
ISSUE_ID = "f7f2f95e-e334-4f11-95b6-89b98e9cf8e8"  # CB-2117

EVIDENCE = """\
CB-2117 implemented — Option 2 (projectId scoping) on documentation router.

Scope (per ticket recommendation)

  Closed cross-project IDOR by adding a required `projectId` query param to
  every endpoint and scoping the issue lookup to (id, projectId). Full
  per-user authz + rate-limit are deferred to Option 3 — residual risks
  documented below for the follow-up ticket.

Code

  backend/api/documentation.py
    - New module-level `ProjectIdQuery` constant (Query(..., alias='projectId',
      min_length=1, max_length=128, description=...)).
    - `_ensure_issue_exists(db, issue_id, project_id)` now does
      WHERE Issue.id == ? AND Issue.projectId == ?  -> NotFoundError on miss.
    - `_load_feature_issue(db, issue_id, project_id)` likewise; the FEATURE
      type-check still raises 400 with key/type, but only for issues already
      in the asserted project (no cross-project leak).
    - All 6 endpoints (3 GETs + POST/DELETE notes + GET feature + POST
      generate) declare the new required query param.

  backend/models/schemas.py
    - Updated docstring on `ImplementationNoteCreate` (lines 1157-1175):
      removed the dangling "endpoint is unauthenticated" lament, replaced
      with a CB-2117 reference + scope note.

Frontend (threading projectId through hooks + components)

  frontend/hooks/useCodeBoard.ts
    - `useExecutionSummaries(issueId, projectId)`,
      `useImplementationNotes(issueId, projectId)`,
      `useFeatureDocumentation(issueId, projectId)` — disabled until both ids
      present; query keys include projectId so cache invalidation is precise.
    - `useCreateImplementationNote` + `useGenerateFeatureDocumentation`
      mutate args now require `projectId`.
    - Internal `_docPath(path, projectId)` helper centralises the
      `?projectId=encodeURIComponent(...)` append (defends against HPP).

  frontend/components/codeboard/ImplementationTab.tsx
    - Added `projectId` prop on `ImplementationTabProps`,
      `AddNoteFormProps`, `NotesSectionProps`. Both `<NotesSection>`
      callsites pass it through.
    - Early-return guard now requires both `issueId` AND `projectId`.

  frontend/components/codeboard/GenerateFeatureDocButton.tsx
    - New `projectId` prop. `disabled={!canGenerate}` (= !projectId ||
      isPending). Handler early-returns when projectId is missing.

  frontend/components/codeboard/IssueDetail.tsx
  frontend/components/codeboard/IssueDetailModal.tsx
  frontend/app/codeboard/issues/[id]/page.tsx
  frontend/app/codeboard/features/[id]/documentation/page.tsx
    - Threaded `issue.projectId` into every documentation hook call and
      into `<ImplementationTab>` / `<GenerateFeatureDocButton>` props.
      `EmptyState` and `PageShell` accept `projectId: string | undefined`
      so loading/error shells render without it; the button stays disabled
      until the issue resolves.

Tests

  backend/tests/test_documentation_api.py
    - Every existing test URL appends `?projectId=...` (issue.projectId
      for known cases, "any-project" for missing-id assertions).
    - New CB-2117 block (search "CB-2117: projectId scoping"):
        * test_endpoints_require_projectId (parametrised over all 7
          method+path pairs — catches the regression where someone drops
          ProjectIdQuery from a single endpoint)
        * test_list_summaries_404_on_wrong_projectId (no canary leak)
        * test_latest_summary_404_on_wrong_projectId
        * test_list_notes_404_on_wrong_projectId
        * test_create_note_blocked_by_wrong_projectId (DB row-count
          asserts no row was persisted)
        * test_delete_note_blocked_by_wrong_projectId (original row
          remains)
        * test_get_feature_documentation_404_on_wrong_projectId
        * test_generate_feature_documentation_blocked_by_wrong_projectId
          (spies on ai_service.generate_text — asserts AI provider is NOT
          invoked when scoping rejects the request, and no FeatureDocumentation
          row is created)
        * test_projectId_blank_rejected (?projectId= -> 422)

  Suite results
    backend/tests/test_documentation_api.py     -> 64 passed
    documentation suite (5 files)               -> 133 passed
    backend/tests/ wide sweep                   -> 781 passed,
      2 pre-existing failures unrelated to CB-2117
      (test_qa_sequence::test_no_commit_inside_helper +
       test_schema_validation aiContext drift). Confirmed those exist on
      baseline by stashing the CB-2117 diff and running them.
    frontend npx tsc --noEmit                   -> clean (only pre-existing
      CpuTicks issue in app/api/docker/metrics/route.ts, untouched).

Audit gates

  code-reviewer: PASS — no CRITICAL/HIGH. Confirmed:
    - both helpers consistently scope on (id, projectId)
    - 404 timing/body/headers identical for "wrong project" vs "missing id"
      (same indexed PK lookup + one extra equality predicate on
      Issue_projectId_idx)
    - downstream descendant walk in documentation_generator was already
      project-scoped (CB-1615 H-1) — no cross-project leakage in the
      generated FeatureDocumentation body, and the spy test asserts the
      AI provider is NOT invoked when scoping rejects the request.
  Two MEDIUM gaps the reviewer flagged in the test layer were closed in
  this same diff (parametrised require-projectId test covering all 7
  routes; latest-summary wrong-projectId test).

  security-auditor: SAFE TO SHIP — no CRITICAL/HIGH introduced. Confirmed:
    - SQLAlchemy parameterises the projectId equality, no SQLi reachable
    - encodeURIComponent + single-typed-string hook arg blocks HTTP
      Parameter Pollution
    - empty-string projectId rejected at validator (min_length=1)
  LOW (residual, by design — out of CB-2117 Option 2 scope, file under
  Option 3 follow-up):
    1. _load_feature_issue 400 echoes issue.key + issue.type (not an
       IDOR escalation — caller already proved access to that project,
       but turns "wrong type" into a key-enumeration oracle within the
       project).
    2. min_length=1, max_length=128 is loose vs actual CUID format
       (25 chars). Tightening to a regex pattern is defensible; not
       security-critical because the value never escapes the bound
       parameter.
  HIGH (residual, by design — explicitly deferred to Option 3):
    - No per-user authz: a caller who learns ANY valid (issueId, projectId)
      pair through any side channel can still abuse the endpoint.
    - No rate-limit on POST /features/{id}/documentation/generate
      (descendant walk + LLM completion).
    - No rate-limit on POST /issues/{id}/documentation/notes
      (100 KB content per request still reachable for one valid pair).

Code path verified

  All 6 endpoints funnel through `_ensure_issue_exists` or
  `_load_feature_issue` BEFORE any other DB read. Service layer
  `_collect_feature_descendants` already scopes on
  `Issue.projectId == feature.projectId` (CB-1615 H-1 hardening), so
  the FeatureDocumentation body cannot expose cross-project rows even if
  scoping were ever bypassed. The new spy test asserts the AI provider
  is never called when scoping rejects the request.

Mitigation that didn't ship in CB-2117

  Rate-limiting (slowapi or token-bucket) and a `Depends(get_current_user)`
  layer require platform-wide design and were explicitly excluded from
  Option 2. These should be filed as a fresh ticket under FEATURE
  CB-2038 with the residual HIGH risks above as the motivation.

Acceptance criterion

  - Cross-project lookup by guessed issue id returns 404 (not 200).
  - 404 body for wrong-projectId is byte-equivalent to 404 for missing id
    (no canary content leak).
  - Cross-project POST creates no row; cross-project DELETE removes no
    row; cross-project generate invokes no AI call.
  - All existing documentation regressions still pass with projectId
    threaded through.
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
    print("Posting evidence comment to CB-2117...")
    request(
        "POST",
        f"/issues/{ISSUE_ID}/comments",
        {"content": EVIDENCE, "author": "AI"},
    )
    print("Flipping CB-2117 -> COMPLETED_WAITING_QA...")
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
