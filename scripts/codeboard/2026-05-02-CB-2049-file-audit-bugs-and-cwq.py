"""
CB-2049 (T1.3.2) deliverable wrap-up:

1. File MEDIUM/LOW findings from the security-auditor pass on the E1 diff
   as new CodeBoard BUG tickets, parented under STORY CB-2047 (S1.3 audit
   + regression). Mirrors CB-2048's filing pattern.

2. Append findings summary to CB-2049 description.

3. Mark CB-2049 -> COMPLETED_WAITING_QA so Eli's manual QA can promote it
   to DONE per Bible Rule 22.

Audit verdict: 0 CRITICAL / 0 HIGH / 3 MEDIUM / 2 LOW / 3 INFO. E1 safe to
ship at COMPLETED_WAITING_QA per the auditor; MEDIUMs and LOWs are
defence-in-depth follow-ups, not release blockers on a localhost-only
single-user platform.

Per Bible Rule 29: per-project per-session script path. Per Bible Rule
22: never push to DONE from code.
"""

import json
import urllib.request
import urllib.error

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"

CB_2047_ID = "c5f70d1e-9043-417a-b204-f2c653e9d743"
CB_2049_ID = "2f0cfcce-47aa-451f-a6d9-de94935cf3c6"

LABEL = "e1-audit-cb-2049"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def patch(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------- 1. File findings as BUGs ----------

bugs = [
    {
        "title": "[CB-2049 M-1] MEDIUM: /api/system/rag/status leaks absolute filesystem path in PERSISTENT mode",
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "security-auditor",
        "reporter": "AI",
        "description": """**Severity:** MEDIUM (information disclosure on an effectively-unauthenticated endpoint)

**Location:** `backend/services/rag_service.py:127`, `backend/api/system.py:42-50`, `backend/app/main.py:388-401`

**Problem**

In PERSISTENT mode, `get_status_payload()` populates the response `host` field with `os.path.abspath(PERSISTENT_FALLBACK_PATH)` — currently `/Volumes/Seagate/Claude/ProjectsManagerWebV2Production/backend/data/chroma`.

The endpoint advertises "no auth required — gated behind Origin-validation middleware". But `validate_origin` (`app/main.py:388-401`) explicitly allows requests through when the `Origin` header is **absent** (server-to-server, curl, internal services). So any local process can `curl http://localhost:8401/api/system/rag/status` and receive the absolute backend filesystem layout.

This is reconnaissance value if any other service on the host is later compromised — it tells the attacker exactly where the embeddings live and what user-named volume they're under.

**Fix (pick one)**

Option A: For unauthenticated callers, replace the absolute path with a basename or boolean flag (e.g. `host: ""` + `fallback_active: true`).
Option B: Require an internal-only loopback check on `/api/system/*` (reject when `request.client.host` not in `{127.0.0.1, ::1}` AND no Origin header), or require an `X-Internal-Token` header.

**Found in:** security-auditor pass on CB-2049.
""",
    },
    {
        "title": "[CB-2049 M-2] MEDIUM: /api/system/rag/status enables project enumeration via collection names",
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "security-auditor",
        "reporter": "AI",
        "description": """**Severity:** MEDIUM (metadata disclosure; combines with M-1)

**Location:** `backend/services/rag_service.py:249` (`get_collection`), `backend/api/system.py:42-50`

**Problem**

Collections are named `project_{project_id[:8]}` (first 8 chars of the project CUID). The status endpoint returns the full collection list with per-collection document counts. CUID prefixes are not secrets, but the endpoint discloses:
- How many projects exist
- Which CUID prefixes are active
- Approximately how much content each project holds (doc counts)

Combined with M-1's no-real-auth posture, this is metadata leakage useful for an attacker mapping the system after gaining any local foothold.

**Fix**

Either:
- Gate `/api/system/rag/status` behind the same auth surface used for `/api/projects/*` (when an auth surface lands).
- Reduce the response when called from a non-admin context (omit `collections[].name`, keep only counts + `total_docs`).

**Found in:** security-auditor pass on CB-2049.
""",
    },
    {
        "title": "[CB-2049 M-3] MEDIUM: status endpoint amplifies DoS via heartbeat + list_collections + per-col count fan-out",
        "type": "BUG",
        "priority": "MEDIUM",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "python-pro",
        "reporter": "AI",
        "description": """**Severity:** MEDIUM (DoS amplification on RAG backend; affects AI execution responsiveness)

**Location:** `backend/services/rag_service.py:202-236`, `frontend/components/service-monitor.tsx:122,228-230`

**Problem**

Each call to `get_status_payload()` performs:
1. `client.heartbeat()` (HTTP mode)
2. `client.list_collections()`
3. `col.count()` per collection (linear in N — currently 8)

`RagStatusCard` is mounted in the always-visible global `ServiceMonitor` and polls every 30 s. With M open tabs and N collections, this is `M·(N+2)` ChromaDB round-trips every 30 s.

Default FastAPI rate limit is 200/min — far above accidental hit, but ChromaDB itself has no rate limit. A noisy multi-tab session (or a forgotten dev-tools tab open overnight) could degrade RAG responsiveness for AI execution exactly when the user needs it.

**Fix (pick one)**

- Server-side cache: memoize `get_status_payload()` for ~10 s (TTL cache) so concurrent polls share one ChromaDB pass.
- Skip `col.count()` per collection when the prior payload was computed within the last poll window (return cached counts).
- Page Visibility gating on the frontend (also tracked under CB-2215 F-6) reduces but does not eliminate this.

**Found in:** security-auditor pass on CB-2049.
""",
    },
    {
        "title": "[CB-2049 L-1] LOW: chroma migration runbook tar extraction not hardened",
        "type": "BUG",
        "priority": "LOW",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "devops-engineer",
        "reporter": "AI",
        "description": """**Severity:** LOW (defence-in-depth on a one-shot operational runbook; source is trusted)

**Location:** `docs/runbooks/2026-05-02-chroma-volume-migration.md:67-71`

**Problem**

Migration step 3 pipes `tar -cf - .` from `backend/data/chroma` into `tar xf -` inside an alpine container, with no traversal-hardening flags:

```bash
tar -cf - . | docker run -i --rm \\
  -v projectsmanagerwebv2production_chroma_data:/dest \\
  alpine:3.20 sh -c 'cd /dest && rm -rf ./* ./.[!.]* 2>/dev/null;
    tar xf -'
```

Modern GNU tar strips leading `/` and refuses traversal above cwd by default, but **alpine ships BusyBox tar**, which is more permissive. A hostile tarball entry like `../etc/passwd` could in principle escape `/dest` to the throwaway container's `/etc` (volume-bounded — does NOT reach the host).

Source is the trusted local filesystem, so risk is theoretical for the already-executed run. The companion `rm -rf ./* ./.[!.]*` is correctly bounded to `/dest` (no traversal there).

No user input flows into the commands; static paths only.

**Fix**

When this runbook is reused, add hardening flags:
```bash
tar xf - -C /dest --no-same-owner --no-overwrite-dir
```
And consider `--anchored` on extraction for paranoia.

No change needed for the already-completed run.

**Found in:** security-auditor pass on CB-2049.
""",
    },
    {
        "title": "[CB-2049 L-2] LOW: PERSISTENT_FALLBACK_PATH is CWD-relative — fallback location depends on launch directory",
        "type": "BUG",
        "priority": "LOW",
        "parentId": CB_2047_ID,
        "labels": LABEL,
        "assignee": "python-pro",
        "reporter": "AI",
        "description": """**Severity:** LOW (reliability/operational; not strictly security)

**Location:** `backend/services/rag_service.py:41`

**Problem**

```python
PERSISTENT_FALLBACK_PATH = "./data/chroma"
```

The path is relative and resolves against the process working directory. If the backend is launched from anywhere other than `backend/` (e.g. systemd unit with `WorkingDirectory=/`, a sibling helper script, or a future container with a different `WORKDIR`), the fallback writes to a different disk location and previously-indexed embeddings appear missing.

Not a direct security issue, but if symlinks or a writable parent CWD ever get involved, the fallback could land in an unexpected location with unexpected permissions.

**Fix**

Anchor the path relative to `__file__` or a backend-package root constant:

```python
from pathlib import Path
PERSISTENT_FALLBACK_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "chroma"
)
```

**Found in:** security-auditor pass on CB-2049.
""",
    },
]


def main() -> None:
    created = []
    for body in bugs:
        try:
            resp = post(f"/projects/{PROJECT_ID}/issues", body)
        except urllib.error.HTTPError as exc:
            print(f"FAILED to create '{body['title'][:60]}': {exc} {exc.read()!r}")
            continue
        created.append((resp.get("key"), resp.get("id"), body["priority"]))
        print(f"created {resp.get('key')} ({body['priority']}): {body['title'][:80]}")

    # ---------- 2. Append findings summary to CB-2049 description ----------
    summary = (
        "\n\n---\n\n"
        "## Security audit complete (2026-05-02)\n\n"
        "**Verdict: SAFE TO SHIP** — 0 CRITICAL, 0 HIGH, 3 MEDIUM, 2 LOW, 3 INFO. "
        "MEDIUMs/LOWs are defence-in-depth follow-ups, not release blockers on a "
        "localhost-only single-user platform.\n\n"
        "**Audit targets covered (per CB-2049 task description):**\n"
        "1. Path-traversal risk in chroma migration → bounded; runbook flagged for "
        "future-reuse hardening (L-1).\n"
        "2. `/api/system/rag/status` data exposure → response shape correctly minimal "
        "(no documents/embeddings/metadatas/queries leak); `host` field overloaded "
        "with absolute filesystem path in PERSISTENT mode (M-1); collection-name "
        "list enables project enumeration (M-2). Confirmed via `RagStatusResponse` + "
        "`get_status_payload()` review.\n"
        "3. Endpoint authz → effectively unauthenticated for non-browser callers "
        "(Origin middleware permits no-Origin server-to-server). Acceptable for "
        "current threat model but flagged for tightening (M-1, M-2).\n\n"
        "**Findings filed as child BUGs under STORY CB-2047:**\n"
    )
    for key, _id, sev in created:
        summary += f"- {key} [{sev}]\n"
    summary += (
        "\n**INFO-level (no follow-up needed):**\n"
        "- I-1: TOCTOU during half-init not exploitable — lifespan blocks startup "
        "until init returns; `app.state.rag` only assigned after one path completes.\n"
        "- I-2: Status response shape correctly minimal — no documents, embeddings, "
        "metadatas, query results, or issue keys leak. Logger output goes to backend "
        "logs only.\n"
        "- I-3: Frontend card uses no credentials, no error leak — `fetch()` "
        "same-origin without `credentials: 'include'`; `console.error` logs only "
        "`Error.message`.\n\n"
        "**Reviewed scope:**\n"
        "- `backend/services/rag_service.py` (init/fallback/status payload/path constant)\n"
        "- `backend/api/system.py` (status endpoint + Pydantic models)\n"
        "- `backend/api/deps.py` (`RAGDep` provider)\n"
        "- `backend/api/__init__.py` (system_router registration)\n"
        "- `backend/app/main.py` (lifespan RAG init; `validate_origin` middleware authz)\n"
        "- `frontend/components/service-monitor.tsx` (`RagStatusCard` polling + render)\n"
        "- `docs/runbooks/2026-05-02-chroma-volume-migration.md` (migration commands)\n"
    )

    # fetch existing description
    with urllib.request.urlopen(f"{BASE}/issues/{CB_2049_ID}") as r:
        current = json.loads(r.read())
    new_desc = (current.get("description") or "") + summary
    patch(f"/issues/{CB_2049_ID}", {"description": new_desc})
    print(f"updated CB-2049 description ({len(summary)} chars appended)")

    # ---------- 3. Mark CB-2049 COMPLETED_WAITING_QA ----------
    patch(f"/issues/{CB_2049_ID}", {"status": "COMPLETED_WAITING_QA"})
    print("CB-2049 -> COMPLETED_WAITING_QA")


if __name__ == "__main__":
    main()
