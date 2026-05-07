"""CB-2050 -> COMPLETED_WAITING_QA — E1 regression results.

Patches CB-2050 with implementationSummary capturing the regression evidence
and flips status to COMPLETED_WAITING_QA. Idempotent.
"""
import json
import urllib.request

BASE = "http://localhost:8401/api"
ISSUE_ID = "20afb26b-7482-433e-8173-4762aa8f6ebb"  # CB-2050

SUMMARY = """E1 regression PASSED (Jonny, 2026-05-02 23:48 IDT).

Steps executed:
1. `docker compose down` + `docker compose up -d chromadb` — chromadb container
   recycled cleanly; heartbeat returned within ~5s.
2. Killed stale local backend (PID 47371) which predated CB-2045 system router
   (returned 404 on /api/system/rag/status). Restarted via uvicorn.
3. Backend startup log line confirmed:
     `[startup] RAG mode=HTTP host=localhost port=8402 collections=8`
   No `_fallback_to_persistent` invocation, no PERSISTENT log.
4. Baseline `/api/system/rag/status` -> mode=HTTP, total_docs=3347,
   project_test count=0.
5. Probed embed via project-scoped script:
   `scripts/regression/2026-05-02-cb2050-embed-probe.py` — calls
   `RAGService.embed_execution_summary` (same code path AI execution uses,
   minus Claude CLI subprocess) against `project_test` collection.
6. After probe `/api/system/rag/status` -> total_docs=3348,
   project_test count=1 (delta +1).
7. Volume mtime evidence:
   - container `/chroma/chroma/chroma.sqlite3` mtime: 1777751810 -> 1777755017
     (ADVANCED — write landed in `chroma_data` volume).
   - local `backend/data/chroma/chroma.sqlite3` mtime: 1777754710 -> 1777754710
     (UNCHANGED — embedded SQLite fallback NOT touched).

Conclusion: HTTP mode active, embeds land in dedicated container volume,
silent PersistentClient fallback eliminated. Probe artifact left at
`scripts/regression/2026-05-02-cb2050-embed-probe.py` for reproducibility.

Note: regression probe used direct embed call rather than full Claude CLI
execution to avoid token/time cost; both paths share the same
`RAGService.embed_execution_summary` -> chroma HttpClient surface, so the
volume-write evidence is equivalent. Full end-to-end AI run is covered by
the QA tasks CB-2051/CB-2052/CB-2053 once those are exercised.
"""


def patch(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    result = patch(
        f"/issues/{ISSUE_ID}",
        {
            "status": "COMPLETED_WAITING_QA",
            "implementationSummary": SUMMARY,
        },
    )
    print(json.dumps({k: result.get(k) for k in ["key", "status", "updatedAt"]}, indent=2))
