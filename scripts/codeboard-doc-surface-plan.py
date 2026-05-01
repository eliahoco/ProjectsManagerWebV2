"""
Push the "Documentation Surface" feature plan to CodeBoard.

Hierarchy (76 items total):
  1 FEATURE
  4 EPICS
  12 STORIES
  36 TASKS
  23 QA verification tasks (filed as TASK type with [QA] prefix + qa-verification label)

Run:
  python3 scripts/codeboard-doc-surface-plan.py

Idempotency: NOT idempotent. Re-running creates duplicates. Run once.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

BASE = "http://localhost:8401/api"
PROJECT_ID = "1511e54f71dccd3fa79f67fe"
LABEL = "documentation-surface"


def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            if resp.status not in (200, 201):
                raise RuntimeError(f"HTTP {resp.status} on {path}: {body}")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} on {path}: {body}") from e


def create(
    title: str,
    description: str,
    issue_type: str,
    priority: str,
    parent_id: Optional[str] = None,
    assignee: Optional[str] = None,
    extra_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    labels = [LABEL]
    if extra_labels:
        labels.extend(extra_labels)
    payload: Dict[str, Any] = {
        "title": title,
        "description": description,
        "type": issue_type,
        "priority": priority,
        "reporter": "AI",
        "labels": ",".join(labels),
    }
    if parent_id:
        payload["parentId"] = parent_id
    if assignee:
        payload["assignee"] = assignee
    result = _post(f"/projects/{PROJECT_ID}/issues", payload)
    print(f"  [{result.get('key')}] {issue_type:8s} {title[:80]}")
    return result


# ----------------------------------------------------------------------------
# FEATURE
# ----------------------------------------------------------------------------

print("\n=== FEATURE ===")
feature = create(
    title="Documentation Surface — make documentation feature visible, controllable, and properly stored",
    description=(
        "Bring the auto-documentation feature (CB-1578) to user surface.\n\n"
        "**Current state**: ExecutionSummary + FeatureDocumentation + ImplementationNote pipelines all run "
        "automatically on AI execution completion. Backend complete. ChromaDB silently fell back to "
        "embedded SQLite (`backend/data/chroma/chroma.sqlite3`, 17MB) because the Docker container is not "
        "running. FeatureDocumentation endpoints exist but have NO frontend. There is no settings UI to "
        "toggle, configure retention, or inspect generated artifacts. Existing implementation lives in an "
        "uncommitted working tree.\n\n"
        "**This feature delivers**:\n"
        "1. Restore ChromaDB container + observability surface\n"
        "2. Build FeatureDocumentation frontend (page + tab + generate UI)\n"
        "3. Settings panel for autoGenerate / retention / max-per-issue + recent summaries list\n"
        "4. Audit + commit existing WIP through proper gates"
    ),
    issue_type="FEATURE",
    priority="HIGH",
)
F_ID = feature["id"]


# ----------------------------------------------------------------------------
# EPIC 1: ChromaDB container restoration + observability
# ----------------------------------------------------------------------------

print("\n=== EPIC 1: ChromaDB container restoration + observability ===")
e1 = create(
    title="E1: ChromaDB container restoration + observability",
    description=(
        "Bring the chromadb Docker container back online so embeddings land in the dedicated container "
        "volume (`chroma_data`) instead of the embedded SQLite fallback. Add a status surface so silent "
        "fallback is impossible going forward."
    ),
    issue_type="EPIC",
    priority="HIGH",
    parent_id=F_ID,
)

# Story 1.1
s1_1 = create(
    "S1.1: Bring chroma container back, verify connection",
    "Restart chromadb service, verify HTTP heartbeat, migrate existing embedded data into the container volume.",
    "STORY", "HIGH", parent_id=e1["id"],
)
create("T1.1.1: Run docker compose up chromadb, verify port 8402 reachable + heartbeat",
       "Start chromadb service via docker-compose. Verify `curl http://localhost:8402/api/v2/heartbeat` returns 200. Confirm backend rag_service connects via HTTP mode (not PERSISTENT fallback).",
       "TASK", "HIGH", parent_id=s1_1["id"], assignee="docker-expert")
create("T1.1.2: Migrate backend/data/chroma/* to container volume chroma_data",
       "Copy existing collections (7 UUID dirs + chroma.sqlite3, 17MB) from local fallback path into the container's `/chroma/chroma` mount. Verify collection counts match before/after. If migration is unsafe, document why and accept fresh start.",
       "TASK", "HIGH", parent_id=s1_1["id"], assignee="python-pro")
create("T1.1.3: Add startup log line surfacing RAG mode (HTTP vs PERSISTENT)",
       "In `app/main.py` lifespan + `services/rag_service.py`: log `RAG mode=HTTP host=chromadb port=8000 collections=N` or `RAG mode=PERSISTENT path=... collections=N`. Currently fallback is silent, which is how we ended up with embedded sqlite chroma without realizing it.",
       "TASK", "HIGH", parent_id=s1_1["id"], assignee="python-pro")

# Story 1.2
s1_2 = create(
    "S1.2: RAG health surface",
    "Expose RAG/Chroma mode + collection metadata to frontend so silent fallback is visible.",
    "STORY", "MEDIUM", parent_id=e1["id"],
)
create("T1.2.1: Endpoint GET /api/system/rag/status",
       "Returns `{mode: 'HTTP'|'PERSISTENT', host: str, port: int, collections: [{name, count}], total_docs: int, healthy: bool}`. Read-only. No auth required (already internal).",
       "TASK", "MEDIUM", parent_id=s1_2["id"], assignee="api-designer")
create("T1.2.2: Service Monitor card showing RAG mode + collection count",
       "Add card to `frontend/components/service-monitor.tsx`. Show: mode badge (green if HTTP, amber if PERSISTENT), total docs, top 3 collections by count. Polls every 30s.",
       "TASK", "MEDIUM", parent_id=s1_2["id"], assignee="react-specialist")

# Story 1.3
s1_3 = create(
    "S1.3: E1 audit + regression",
    "Audit gates + full regression for Epic 1. Blocks E1 → COMPLETED_WAITING_QA.",
    "STORY", "HIGH", parent_id=e1["id"],
)
create("T1.3.1: code-reviewer on E1 diff (chroma migration + status endpoint + monitor card)",
       "Review for atomicity of migration, error handling, mode-switching correctness, status endpoint shape, frontend polling efficiency.",
       "TASK", "HIGH", parent_id=s1_3["id"], assignee="code-reviewer")
create("T1.3.2: security-auditor on E1 (path-traversal in migration + endpoint authz)",
       "Audit path-traversal risk in chroma migration script. Verify `/api/system/rag/status` doesn't leak collection contents (only counts).",
       "TASK", "HIGH", parent_id=s1_3["id"], assignee="security-auditor")
create("T1.3.3: E1 regression — restart backend, verify HTTP mode, embed lands in container volume",
       "Steps: `docker compose down && up`. Tail backend log → confirm `RAG mode=HTTP`. Trigger 1 AI execution on test issue. Verify new ExecutionSummary embedded into container volume `chroma_data` (NOT local sqlite path). Verify collection count incremented.",
       "TASK", "HIGH", parent_id=s1_3["id"], assignee="debugger")
create("[QA] E1-1: Chroma container UP, heartbeat passes, port 8402 reachable",
       "Manual verification: `curl http://localhost:8402/api/v2/heartbeat` returns 200. `docker ps | grep chroma` shows running container.",
       "TASK", "HIGH", parent_id=s1_3["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E1-2: /api/system/rag/status returns mode=HTTP after compose up",
       "Manual verification: `curl http://localhost:8401/api/system/rag/status` shows `mode: 'HTTP'`. Backend log on startup includes `RAG mode=HTTP`.",
       "TASK", "HIGH", parent_id=s1_3["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E1-3: Service Monitor card renders RAG mode + collection count",
       "Manual verification: open frontend → service monitor → RAG card visible with green HTTP badge + non-zero total docs.",
       "TASK", "MEDIUM", parent_id=s1_3["id"], assignee="qa", extra_labels=["qa-verification"])


# ----------------------------------------------------------------------------
# EPIC 2: FeatureDocumentation Frontend
# ----------------------------------------------------------------------------

print("\n=== EPIC 2: FeatureDocumentation Frontend ===")
e2 = create(
    "E2: FeatureDocumentation Frontend",
    "Build the missing UI for FeatureDocumentation. Backend endpoints (GET / POST generate) already exist at `/api/features/{id}/documentation` but have NO frontend. Make them reachable + render the 6 markdown sections + metrics.",
    "EPIC", "HIGH", parent_id=F_ID,
)

# Story 2.1
s2_1 = create(
    "S2.1: Hooks + types",
    "React Query hooks + TypeScript types for FeatureDocumentation API.",
    "STORY", "HIGH", parent_id=e2["id"],
)
create("T2.1.1: useFeatureDocumentation(issueId) — GET wrapper",
       "Hook in `frontend/hooks/useCodeBoard.ts`. Calls `GET /api/features/{id}/documentation`. Returns `FeatureDocumentationData | null`. 404 → null (un-generated).",
       "TASK", "HIGH", parent_id=s2_1["id"], assignee="react-specialist")
create("T2.1.2: useGenerateFeatureDocumentation() — POST mutation",
       "Mutation hook calling `POST /api/features/{id}/documentation/generate`. On success → invalidate `useFeatureDocumentation` query. Includes loading + error state.",
       "TASK", "HIGH", parent_id=s2_1["id"], assignee="react-specialist")
create("T2.1.3: TS types FeatureDocumentationData + response shape",
       "Add to `frontend/types/`. Mirrors `FeatureDocumentationResponse` from backend Pydantic model. Includes overview, requirements, implementation, architecture, techStack (JSON string), testingStrategy, metrics, mdFilePath, embeddingId, lastIndexedAt.",
       "TASK", "MEDIUM", parent_id=s2_1["id"], assignee="typescript-pro")

# Story 2.2
s2_2 = create(
    "S2.2: Page + view components",
    "Standalone page + view component rendering all 6 markdown sections + metrics card.",
    "STORY", "HIGH", parent_id=e2["id"],
)
create("T2.2.1: app/codeboard/features/[id]/documentation/page.tsx",
       "Next.js App Router page. Loads issue, validates type=FEATURE, renders FeatureDocumentationView. Handles 400 (not a feature) + 404 (no docs yet) states.",
       "TASK", "HIGH", parent_id=s2_2["id"], assignee="nextjs-developer")
create("T2.2.2: FeatureDocumentationView component — render 6 sections + metrics",
       "Component renders: overview (markdown), requirements (markdown), implementation (markdown), architecture (markdown), techStack (parse JSON → badges), testingStrategy (markdown). Metrics card: totalTasks/completedTasks/totalQATasks/passedQATasks/failedQATasks. Reuse `PROSE_CLASSES` + `SAFE_URL_TRANSFORM` from ImplementationTab.",
       "TASK", "HIGH", parent_id=s2_2["id"], assignee="react-specialist")
create("T2.2.3: Generate / Regenerate button → POST + loading + toast",
       "Sticky button in page header. Calls `useGenerateFeatureDocumentation`. Shows spinner during generation (can take 5–30s). Toast on success/failure. Disabled while pending.",
       "TASK", "HIGH", parent_id=s2_2["id"], assignee="react-specialist")
create("T2.2.4: Last-indexed timestamp badge + Chroma-indexed indicator",
       "Show `lastIndexedAt` formatted as `Indexed 2m ago` + green dot if `embeddingId` present, amber dot if null.",
       "TASK", "MEDIUM", parent_id=s2_2["id"], assignee="react-specialist")

# Story 2.3
s2_3 = create(
    "S2.3: Entry points (tab + empty state)",
    "Wire the new page into IssueDetail flows so users can reach it.",
    "STORY", "HIGH", parent_id=e2["id"],
)
create("T2.3.1: Documentation tab on FEATURE-type issues in IssueDetail + IssueDetailModal",
       "Add new tab next to existing `#implementation` tab. Visible ONLY when `issue.type === 'FEATURE'`. Tab content = inline FeatureDocumentationView OR link to standalone page.",
       "TASK", "HIGH", parent_id=s2_3["id"], assignee="react-specialist")
create("T2.3.2: Empty state with Generate Documentation CTA when 404",
       "When useFeatureDocumentation returns null: render centered empty state card with `Sparkles` icon + 'No documentation generated yet' + Generate button.",
       "TASK", "MEDIUM", parent_id=s2_3["id"], assignee="react-specialist")

# Story 2.4
s2_4 = create(
    "S2.4: E2 audit + regression + Chrome QA",
    "Audit gates + Chrome visual QA + full regression for Epic 2.",
    "STORY", "HIGH", parent_id=e2["id"],
)
create("T2.4.1: code-reviewer on E2 diff (hooks + page + view + tab integration)",
       "Review React Query usage, type safety, FEATURE-type gating, error boundary placement, memoization where needed.",
       "TASK", "HIGH", parent_id=s2_4["id"], assignee="code-reviewer")
create("T2.4.2: security-auditor on E2 — markdown XSS + JSON.parse defense + URL transform",
       "Verify all 6 markdown sections use `SAFE_URL_TRANSFORM`. Verify `techStack` JSON.parse wrapped in try/catch with array-type guard. Verify no dangerouslySetInnerHTML.",
       "TASK", "HIGH", parent_id=s2_4["id"], assignee="security-auditor")
create("T2.4.3: Chrome visual QA — empty + populated states + FEATURE-only gating",
       "Open non-FEATURE issue → confirm tab hidden. Open FEATURE issue → empty state screenshot. Click Generate → spinner → populated screenshot. Save screenshots to `docs/research/cb-doc-surface/`.",
       "TASK", "HIGH", parent_id=s2_4["id"], assignee="general-purpose")
create("T2.4.4: E2 full regression — open FEATURE → Generate → verify all 6 sections + Chroma indexed",
       "End-to-end: open FEATURE issue → Documentation tab → click Generate → wait for response → verify all 6 sections render + metrics correct → reload → data persists → query Chroma → confirm `feature_documentation` collection has new entry.",
       "TASK", "HIGH", parent_id=s2_4["id"], assignee="debugger")
create("[QA] E2-1: Documentation tab visible only on FEATURE-type issues",
       "Manual: open EPIC, STORY, TASK, BUG → tab hidden. Open FEATURE → tab visible.",
       "TASK", "HIGH", parent_id=s2_4["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E2-2: Empty state shows when no FeatureDocumentation row exists",
       "Manual: pick FEATURE without prior generation → empty state with Generate CTA visible.",
       "TASK", "HIGH", parent_id=s2_4["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E2-3: Generate button creates row + all 6 sections populate",
       "Manual: click Generate → wait → overview/requirements/implementation/architecture/techStack/testingStrategy all render with non-empty content (or descriptive placeholder per generator).",
       "TASK", "HIGH", parent_id=s2_4["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E2-4: Regenerate updates row, doesn't duplicate",
       "Manual: click Generate twice → DB has only ONE FeatureDocumentation row for that featureIssueId.",
       "TASK", "MEDIUM", parent_id=s2_4["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E2-5: techStack badges render from JSON array",
       "Manual: techStack JSON `[\"FastAPI\", \"Next.js\"]` → 2 badges visible.",
       "TASK", "MEDIUM", parent_id=s2_4["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E2-6: Last-indexed timestamp updates after regenerate",
       "Manual: note timestamp → regenerate → timestamp newer.",
       "TASK", "MEDIUM", parent_id=s2_4["id"], assignee="qa", extra_labels=["qa-verification"])


# ----------------------------------------------------------------------------
# EPIC 3: Documentation Settings Panel
# ----------------------------------------------------------------------------

print("\n=== EPIC 3: Documentation Settings Panel ===")
e3 = create(
    "E3: Documentation Settings Panel",
    "Add user control over the auto-documentation feature. Today it's auto-on with no toggle, retention, or visibility. This epic adds a settings page + retention task.",
    "EPIC", "MEDIUM", parent_id=F_ID,
)

# Story 3.1
s3_1 = create(
    "S3.1: Backend settings + retention",
    "DocSettings model + GET/PATCH endpoint + autoGenerate gate + retention background task.",
    "STORY", "MEDIUM", parent_id=e3["id"],
)
create("T3.1.1: DocSettings model — autoGenerate / retentionDays / maxPerIssue",
       "New SQLAlchemy model + Pydantic schemas. Singleton row pattern (single global config). Defaults: autoGenerate=true, retentionDays=90, maxPerIssue=20.",
       "TASK", "MEDIUM", parent_id=s3_1["id"], assignee="python-pro")
create("T3.1.2: GET / PATCH /api/documentation/settings",
       "Two endpoints. GET returns current config (creates default row if missing). PATCH updates fields. Pydantic validates retentionDays >= 1, maxPerIssue >= 1.",
       "TASK", "MEDIUM", parent_id=s3_1["id"], assignee="api-designer")
create("T3.1.3: Honor autoGenerate=false in _process_completion_for_session",
       "In `app/main.py`: read DocSettings before invoking `documentation_generator.generate_from_execution`. If `autoGenerate=false` → skip + log `doc-gen skipped (autoGenerate=false)`. Issue still flips to COMPLETED_WAITING_QA.",
       "TASK", "MEDIUM", parent_id=s3_1["id"], assignee="python-pro")
create("T3.1.4: Background retention task — purge ExecutionSummary by retentionDays + maxPerIssue cap",
       "Async task running every 6h. Deletes ExecutionSummary rows older than `retentionDays`. Then per-issue: keep newest `maxPerIssue` rows, delete rest. Also removes orphaned Chroma embeddings via RAGService.delete_embedding.",
       "TASK", "MEDIUM", parent_id=s3_1["id"], assignee="python-pro")

# Story 3.2
s3_2 = create(
    "S3.2: Settings UI",
    "Settings page exposing the new endpoints + recent summaries list.",
    "STORY", "MEDIUM", parent_id=e3["id"],
)
create("T3.2.1: app/settings/documentation/page.tsx",
       "Next.js page under existing settings section. Loads DocSettings via React Query.",
       "TASK", "MEDIUM", parent_id=s3_2["id"], assignee="nextjs-developer")
create("T3.2.2: Toggle (autoGenerate) + retentionDays input + maxPerIssue input",
       "Form with optimistic UI. Save button persists via PATCH. Disabled state during pending. Toast on success.",
       "TASK", "MEDIUM", parent_id=s3_2["id"], assignee="react-specialist")
create("T3.2.3: Recent ExecutionSummaries list (latest 20 across project)",
       "Read-only list. Columns: timestamp, issue key (linked), provider, exit code, files touched count, +/- badges. Click → navigate to issue Implementation tab. Backed by new `GET /api/documentation/summaries?limit=20` endpoint (sub-task of T3.1.2 if needed, otherwise reuse existing endpoints).",
       "TASK", "MEDIUM", parent_id=s3_2["id"], assignee="react-specialist")
create("T3.2.4: Manual re-trigger button per row",
       "Calls existing `POST /api/execute/issue/{id}` to re-run AI on issue. Confirms via dialog. Toast on success.",
       "TASK", "LOW", parent_id=s3_2["id"], assignee="react-specialist")

# Story 3.3
s3_3 = create(
    "S3.3: E3 audit + regression + Chrome QA",
    "Audit gates + Chrome visual QA + full regression for Epic 3.",
    "STORY", "HIGH", parent_id=e3["id"],
)
create("T3.3.1: code-reviewer on E3 diff (model + endpoints + retention task + UI)",
       "Review singleton-row pattern, retention task SQL safety, integer bounds, UI optimistic update correctness.",
       "TASK", "HIGH", parent_id=s3_3["id"], assignee="code-reviewer")
create("T3.3.2: security-auditor on E3 — PATCH validation + retention SQL safety",
       "Verify Pydantic bounds prevent negative retentionDays. Verify retention task uses parameterized queries. Verify PATCH endpoint authz consistent with rest of API.",
       "TASK", "HIGH", parent_id=s3_3["id"], assignee="security-auditor")
create("T3.3.3: Chrome visual QA — settings page + toggle + recent list",
       "Screenshot: settings page initial, toggle off state, recent summaries populated. Verify keyboard nav.",
       "TASK", "HIGH", parent_id=s3_3["id"], assignee="general-purpose")
create("T3.3.4: E3 full regression — toggle off → exec → no summary; toggle on → exec → summary; retention purges",
       "End-to-end: (a) toggle autoGenerate off, run exec, verify NO ExecutionSummary row. (b) toggle on, run exec, verify summary created. (c) set retentionDays=0, trigger retention task, verify old rows deleted.",
       "TASK", "HIGH", parent_id=s3_3["id"], assignee="debugger")
create("[QA] E3-1: autoGenerate toggle persists across reload",
       "Manual: toggle off → reload page → still off.",
       "TASK", "HIGH", parent_id=s3_3["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E3-2: autoGenerate=false skips doc-gen hook on next exec",
       "Manual: toggle off → run AI exec on test issue → no new ExecutionSummary row in DB.",
       "TASK", "HIGH", parent_id=s3_3["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E3-3: Retention purges ExecutionSummary older than retentionDays",
       "Manual: insert old row (executedAt = now - 100d) → set retentionDays=90 → trigger task → row gone.",
       "TASK", "HIGH", parent_id=s3_3["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E3-4: maxPerIssue caps row count per issue",
       "Manual: create 25 summaries on one issue → set maxPerIssue=20 → trigger task → only newest 20 remain.",
       "TASK", "MEDIUM", parent_id=s3_3["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E3-5: Recent summaries list shows latest 20 ordered DESC",
       "Manual: open settings → recent list → verify order newest-first, count <=20.",
       "TASK", "MEDIUM", parent_id=s3_3["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E3-6: Manual re-trigger button starts exec",
       "Manual: click re-trigger → confirm → exec session appears in GlobalAgentStatusBar.",
       "TASK", "MEDIUM", parent_id=s3_3["id"], assignee="qa", extra_labels=["qa-verification"])


# ----------------------------------------------------------------------------
# EPIC 4: Audits + WIP commit
# ----------------------------------------------------------------------------

print("\n=== EPIC 4: Audits + WIP commit ===")
e4 = create(
    "E4: Audits + WIP commit (existing uncommitted documentation feature code)",
    "The doc generator + QA service refactor + ImplementationTab UI all live in working tree uncommitted. This epic audits and commits it in logical slices BEFORE we add E1/E2/E3 on top.",
    "EPIC", "CRITICAL", parent_id=F_ID,
)

# Story 4.1
s4_1 = create(
    "S4.1: Audits on existing WIP",
    "Run all 4 gates (code review, security, Chrome, regression) on already-written documentation code.",
    "STORY", "CRITICAL", parent_id=e4["id"],
)
create("T4.1.1: code-reviewer on documentation_generator.py + api/documentation.py + ImplementationTab + hooks",
       "Comprehensive review of the uncommitted WIP. Files: backend/services/documentation_generator.py, backend/api/documentation.py, backend/models/documentation.py, frontend/components/codeboard/ImplementationTab.tsx, frontend/hooks/useCodeBoard.ts (modified sections).",
       "TASK", "CRITICAL", parent_id=s4_1["id"], assignee="code-reviewer")
create("T4.1.2: security-auditor — git subprocess + prompt injection + path validation + RAG cross-project",
       "Audit: git subprocess hardening (env scrubbing, --end-of-options, SHA regex), prompt injection sentinels, file-path traversal, RAG cross-project leakage (CB-1615 audit mentions H-1 hardening already in code, verify).",
       "TASK", "CRITICAL", parent_id=s4_1["id"], assignee="security-auditor")
create("T4.1.3: Chrome visual QA — ImplementationTab empty + populated + add note flow",
       "Screenshots: open issue → Implementation tab empty state, then with summary, then add note flow. Save to `docs/research/cb-doc-surface/wip-screenshots/`.",
       "TASK", "HIGH", parent_id=s4_1["id"], assignee="general-purpose")
create("T4.1.4: Full regression on existing WIP — exec → ExecutionSummary → tab render → Chroma embed",
       "End-to-end: trigger AI exec on throwaway test issue → wait for completion → verify ExecutionSummary row in DB → open Implementation tab → verify render → query Chroma → verify execution_summary collection has entry.",
       "TASK", "HIGH", parent_id=s4_1["id"], assignee="debugger")

# Story 4.2
s4_2 = create(
    "S4.2: Commit existing WIP in logical slices",
    "Once audits pass, commit the WIP in clean logical slices. Cleanup loose screenshots from repo root.",
    "STORY", "HIGH", parent_id=e4["id"],
)
create("T4.2.1: Commit slice 1 — backend doc generator (services/documentation_generator.py + api/documentation.py + models/documentation.py + tests)",
       "Files: backend/services/documentation_generator.py, backend/api/documentation.py, backend/models/documentation.py, backend/models/__init__.py, backend/api/__init__.py, all new test_documentation_*.py. Single commit. Subject: 'feat(docs): execution summary + feature documentation generator'.",
       "TASK", "HIGH", parent_id=s4_2["id"], assignee="git-workflow-manager")
create("T4.2.2: Commit slice 2 — QA + RAG + terminal hooks (qa_service.py + rag_service.py + terminal_service.py + tests)",
       "Files: backend/services/qa_service.py, backend/services/rag_service.py, backend/services/terminal_service.py, backend/services/ai_service.py (if modified), backend/api/qa.py, backend/api/issues.py, backend/app/main.py, backend/models/schemas.py, all new test_qa_*.py, test_rag_service_*.py, test_terminal_service_doc_capture.py.",
       "TASK", "HIGH", parent_id=s4_2["id"], assignee="git-workflow-manager")
create("T4.2.3: Commit slice 3 — frontend (IssueDetail + IssueDetailModal + ImplementationTab + useCodeBoard)",
       "Files: frontend/components/codeboard/IssueDetail.tsx, frontend/components/codeboard/IssueDetailModal.tsx, frontend/components/codeboard/ImplementationTab.tsx (new), frontend/components/codeboard/index.ts, frontend/hooks/useCodeBoard.ts, frontend/app/codeboard/issues/[id]/page.tsx.",
       "TASK", "HIGH", parent_id=s4_2["id"], assignee="git-workflow-manager")
create("T4.2.4: Cleanup — move loose cb-1612-*.png + watchdog-*.png to docs/research/ or delete",
       "Files in repo root: cb-1612-kanban.png, cb-1612-modal-empty.png, cb-1612-modal-populated.png, cb-1612-slideover.png, cb-1612-standalone.png, cb-1612-view-full.png, watchdog-auto-restarting.png, watchdog-buttons-visible.png, watchdog-toggle-switch.png. Move to `docs/research/cb-1612/` and `docs/research/watchdog/` or delete if no longer needed. Final commit.",
       "TASK", "MEDIUM", parent_id=s4_2["id"], assignee="general-purpose")
create("[QA] E4-1: Existing ImplementationTab renders ExecutionSummary on real issue",
       "Manual: pick issue with prior exec → Implementation tab → all sections render correctly.",
       "TASK", "HIGH", parent_id=s4_2["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E4-2: Add ImplementationNote → persists → renders",
       "Manual: open Implementation tab → Add Note → fill form → Save → note appears in list → reload → still there.",
       "TASK", "HIGH", parent_id=s4_2["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E4-3: Delete ImplementationNote → 204 → list refreshes",
       "Manual: delete note → list refreshes without it → reload → confirmed gone.",
       "TASK", "MEDIUM", parent_id=s4_2["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E4-4: git status clean after E4.2 commit slices",
       "Manual: run `git status` after T4.2.1-3 → no uncommitted documentation-feature files. Working tree only contains files unrelated to this feature.",
       "TASK", "HIGH", parent_id=s4_2["id"], assignee="qa", extra_labels=["qa-verification"])
create("[QA] E4-5: Loose screenshots gone from repo root",
       "Manual: `ls /Volumes/Seagate/Claude/ProjectsManagerWebV2Production/*.png` returns nothing.",
       "TASK", "MEDIUM", parent_id=s4_2["id"], assignee="qa", extra_labels=["qa-verification"])


# ----------------------------------------------------------------------------
# Set FEATURE → IN_PROGRESS, E4 + S4.1 → IN_PROGRESS (we start there)
# ----------------------------------------------------------------------------

def patch(issue_id: str, payload: Dict[str, Any]) -> None:
    req = urllib.request.Request(
        f"{BASE}/issues/issue/{issue_id}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"PATCH failed: HTTP {resp.status}")


print("\n=== Promoting starting work to IN_PROGRESS ===")
patch(F_ID, {"status": "IN_PROGRESS"})
print(f"  FEATURE {feature['key']} → IN_PROGRESS")
patch(e4["id"], {"status": "IN_PROGRESS"})
print(f"  EPIC {e4['key']} → IN_PROGRESS")
patch(s4_1["id"], {"status": "IN_PROGRESS"})
print(f"  STORY {s4_1['key']} → IN_PROGRESS")

print("\n=== DONE ===")
print(f"FEATURE: {feature['key']}")
print(f"  E1: {e1['key']}")
print(f"  E2: {e2['key']}")
print(f"  E3: {e3['key']}")
print(f"  E4: {e4['key']} (IN_PROGRESS)")
print(f"  Starting story: {s4_1['key']} (IN_PROGRESS)")
