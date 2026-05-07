# CB-2071 — E2 Full Regression Report

**Task**: T2.4.4: open FEATURE → Generate → verify all 6 sections + Chroma indexed
**Run date**: 2026-05-07
**Tested by**: Jonny (orchestrator) via Playwright + direct backend/chroma probes
**Target FEATURE**: CB-2038 (id `94aff46e-715b-49cf-8f69-7112be5bd211`, project `1511e54f71dccd3fa79f67fe`)

## Summary

PASS — All six markdown sections render, metrics are correct, persistence
holds across reload, and the FeatureDocumentation row is indexed into
ChromaDB. **One real product bug surfaced** during regression and is filed
as a follow-up (see below).

## Pre-state (before Generate)

```
GET /api/features/{id}/documentation
  overview: 2155 chars (auto-derived from issue description, OK)
  requirements: 855 chars
  implementation: "_No execution summaries recorded under this feature yet._"
  architecture: "_No architectural notes captured._"
  techStack: "[]"  (empty JSON array)
  testingStrategy: "_No QA tasks linked under this feature yet._"
  totalTasks: 86 / completed: 34
  totalQATasks: 0 / passedQA: 0 / failedQA: 0
  embeddingId: null
  lastIndexedAt: null
```

UI badge: "Not indexed in ChromaDB". Tech Stack section hidden
(`techItems.length === 0` ⇒ component returns null per
`FeatureDocumentationView.tsx:278`).

Screenshot: `docs/research/cb-2071-before-generate.png`

## Generate trigger

UI Regenerate click triggered POST through Next.js proxy
`/api/codeboard/features/{id}/documentation/generate`. Proxy has a
**15 s `AbortController` timeout** at
`frontend/app/api/codeboard/[...path]/route.ts:48`. LLM aggregation took
**~33 s** (verified via direct backend probe), so the UI received a 504
"Gateway timeout" and the mutation hook surfaced an error toast.

Backend completed successfully despite the proxy abort — direct probe:

```
POST http://localhost:8401/api/features/94aff46e-…/documentation/generate
  → 200 in 32.9 s
```

## Post-state (after Generate, verified end-to-end)

Direct backend response (parsed):

| Field            | Pre        | Post                                  |
|------------------|------------|---------------------------------------|
| overview         | 2,155      | 2,155 (refreshed)                     |
| requirements     | 855        | 855 (refreshed)                       |
| implementation   | placeholder| **15,938** chars (11 execution runs)  |
| architecture     | placeholder| **7,177** chars                       |
| techStack        | `[]`       | **2,223** chars (~50 components)      |
| testingStrategy  | placeholder| **6,283** chars                       |
| totalTasks       | 86         | **96**                                |
| completedTasks   | 34         | **59**                                |
| totalQATasks     | 0          | **48**                                |
| embeddingId      | null       | `f6e011d460598184e3d8951747516f13`    |
| lastIndexedAt    | null       | `2026-05-06T22:14:06.024676`          |

`embeddingId` matches `md5("feature_documentation:" + issue_id)` — i.e.
the stable per-feature `doc_id` from
`rag_service.RAGService.generate_doc_id` (line 259-261).

## ChromaDB verification

`backend/services/rag_service.py:541-553` upserts to the per-project
collection (`project_<projectId[:8]>`) with metadata
`content_type="feature_documentation"`. There is **no separate
`feature_documentation` collection** — task description's wording is
loose; implementation uses metadata-tagged docs inside the project
collection. Verified against running ChromaDB HTTP server (port 8402):

```
POST /api/v2/.../collections/{project_1511e54f-id}/get
body: {"ids":["f6e011d460598184e3d8951747516f13"]}

→ 1 hit
  metadata: { content_type: "feature_documentation",
              issue_id:  "94aff46e-715b-49cf-8f69-7112be5bd211",
              key:       "CB-2038" }
  document len: 17,466 chars
  preview: "[CB-2038] Feature Documentation: Documentation Surface — make
            documentation feature visible, controllable, and properly stored
            \n\nOverview:\n…"
```

(Note: the embedded SQLite at `backend/data/chroma/chroma.sqlite3` is
**stale** — it was used during the embedded-fallback period documented
in CLAUDE.md. The running backend is in HTTP mode against the on-disk
ChromaDB volume on port 8402, as confirmed via
`/api/system/rag/status` → `mode: "HTTP"`. Anyone debugging Chroma must
hit the HTTP endpoint, not the file.)

## UI verification (after manual reload)

Page snapshot via Playwright `evaluate` — H3 headings in DOM order:

1. Progress (metrics card)
2. Tech Stack ← previously hidden, now rendered (50+ badges)
3. Overview
4. Requirements
5. Implementation (each execution run is a nested h3)
6. Architecture
7. Testing Strategy

Indexed-status strip toggled from "Not indexed in ChromaDB" → "Indexed 3h ago".
Metrics card shows 96 / 59 / 48 / 0 / 0 (matches backend payload).

Screenshot: `docs/research/cb-2071-after-generate.png`

## Sibling QA acceptance hits

This regression also satisfies acceptance for the following [QA] tasks
on the same parent story (CB-2067):

- CB-2073 (E2-2: empty state shows when no row exists) — verified
  separately on a fresh feature (page renders `EmptyState` when hook
  returns null per `app/codeboard/features/[id]/documentation/page.tsx:120-122`).
- CB-2074 (E2-3: Generate creates row + 6 sections populate) — **PASS**.
- CB-2075 (E2-4: Regenerate updates, no duplicate) — **PASS** (Chroma
  upsert by stable `doc_id` ⇒ exactly one row; backend re-uses the same
  DB row by `feature_issue_id` upsert).
- CB-2076 (E2-5: techStack badges render from JSON array) — **PASS**.
- CB-2077 (E2-6: last-indexed timestamp updates after regenerate) —
  **PASS** ("Indexed 3h ago" badge replaces "Not indexed").

## Bugs found during regression

### BUG-A: Generate UI surfaces 504 because proxy timeout < LLM latency

- **Severity**: HIGH (renders the Generate button effectively broken
  in the UI even though the backend works).
- **Where**: `frontend/app/api/codeboard/[...path]/route.ts:48` —
  hard-coded `setTimeout(() => controller.abort(), 15000)`.
- **Repro**: open any FEATURE with non-trivial task graph, click
  Regenerate, watch network tab — 504 after 15 s, while backend keeps
  working and finishes in ~30–35 s.
- **Fix options**:
  1. Lift the proxy timeout for `/features/*/documentation/generate`
     to 120 s (route-specific allowlist).
  2. Switch the endpoint to SSE / streaming so the proxy hands bytes
     through (this proxy already does that path on `text/event-stream`).
  3. Convert the endpoint to a job-and-poll pattern (POST → 202 +
     job_id, GET /status → ready / pending).
- **Recommended**: option 1 (smallest surface, unblocks UX
  immediately); revisit (3) when other long-running endpoints land.

### BUG-B: useFeatureDocumentation does not auto-refetch after a 504 error

- **Severity**: MEDIUM (cosmetic — once BUG-A is fixed, this becomes
  a noop, but worth tracking separately).
- **Where**: `frontend/hooks/useCodeBoard.ts` (mutation for
  `useGenerateFeatureDoc` — no `onError` retry / no reconciliation
  with the server state via `queryClient.invalidateQueries` on a 504).
- **Effect**: even though the backend has populated the row, the user
  must hard-reload to see it. With BUG-A fixed this disappears, but
  defence-in-depth would invalidate the GET cache on any non-2xx
  generate response so the UI eventually self-heals.

Both filed in CodeBoard alongside this report.

## Files / artefacts

- `docs/research/cb-2071-before-generate.png`
- `docs/research/cb-2071-after-generate.png`
- `docs/research/cb-2071-regression-report.md` (this file)
- Push script: `scripts/codeboard/2026-05-07-CB-2071-cwq.py`
