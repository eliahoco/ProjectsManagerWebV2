# Studio Workspace — Full Architecture (2026-05-23)

**Status:** Draft for Eli review · supersedes CB-3001 (Studio Workspace Surfaces)
**Author:** Jonny (with code-reviewer + security-auditor + react-specialist review pending)
**Scope:** Replace global Sidebar when on `/workspace/*/studio` with a project-scoped
StudioSidebar. Add 14 sidebar items. Convert chat into a mode-aware surface.
Kill the right-rail Investigation panel; the SIE becomes a tool inside the chat.

---

## 0. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Global Layout (always)                                                       │
│ ┌──── ProjectSwitcher ─────┐                                                  │
│ │  current: PMv2           │     Sidebar (mode-switched by pathname)           │
│ └──────────────────────────┘                                                  │
│                                                                               │
│   pathname starts with /workspace/*/studio  →  render StudioSidebar           │
│   else                                       →  render GlobalSidebar          │
│                                                                               │
│ ┌─ StudioSidebar (14 items) ─────────┐ ┌─ <Outlet> renders /studio/* route ─┐│
│ │ Dashboard                          │ │                                    ││
│ │ Chat (mode-aware)                  │ │   /studio                          ││
│ │ Modes (mode registry CRUD)         │ │   /studio/dashboard                ││
│ │ Agents                             │ │   /studio/agents                   ││
│ │ Skills                             │ │   /studio/skills                   ││
│ │ Story Board → /codeboard           │ │   /studio/modes                    ││
│ │ Visualizer                         │ │   /studio/visualizer               ││
│ │ Mockup Studio                      │ │   /studio/mockups                  ││
│ │ Workflows                          │ │   /studio/workflows                ││
│ │ Compare                            │ │   /studio/compare                  ││
│ │ Artifacts                          │ │   /studio/artifacts                ││
│ │ Specs                              │ │   /studio/specs                    ││
│ │ Context                            │ │   /studio/context                  ││
│ │ Memory                             │ │   /studio/memory                   ││
│ └────────────────────────────────────┘ └────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

Every Studio surface inherits:
- **TenantContext** — `workspaceId`, `tenantId`, `projectId`. Switches when the
  ProjectSwitcher changes. All API calls send these as headers.
- **TanStack Query** keys prefixed with `workspaceId + projectId` so workspace
  switches don't leak data.
- **CB-2814 store invariant** — `useStudioStore` per-project tab state +
  partialize stub-id filter + `studio-state-v2` localStorage shape preserved.

---

## 1. Cross-cutting concerns (Rule 19 data-flow preservation)

| Concern | Decision |
|---|---|
| **Multi-tenant boundary** | Every new endpoint takes `TenantDep` + calls `studio_orchestrator.get_session(tenant_id, session_id, db)` before any data read/write. Pattern from `/api/studio/sessions/{id}/investigate` HIGH-1 fix. |
| **Project scoping** | Frontend reads `projectId` from `useTenant()`. Backend filters every query by `projectId == session.projectId`. Cross-project ops require explicit user confirmation. |
| **Secret redaction** | All user-supplied strings flowing to persistence/log pass through `utils.exhaustion_detector.redact_secrets` (canonical scrub list — Bearer/sk-/api_key/password/JWT/AKIA/Stripe/Slack/Basic/etc). |
| **Cost attribution** | Every model call (chat turn, SIE invocation, mode-driven tool call) flows through `_compute_cost` and persists to `TenantTokenUsage`. Per-tenant + per-mode rollup queryable. |
| **Auth on writes** | `InternalAuthDep` on all write endpoints when LAN-exposed. Loopback bind keeps this safe today. |
| **Approval gates** | Writes (file CB issue, push artifact, change mode default model) require explicit user confirmation in chat OR a "Confirm" UI button. Pattern from CB-2864. |
| **Audit log** | `StudioAgentActivity` row per tool call (verb + source + target + payload). Already in DB. |
| **Idempotency** | Long-running operations carry `batch_id` / `request_id`. Investigation Engine + CodeBoard filer both have it. |
| **Rate limits** | `@limiter.limit(...)` on every new write endpoint, keyed by session_id (60/min reads, 10/min writes). |
| **Markdown safety** | All AI-generated content rendered via `ReactMarkdown` + `SAFE_URL_TRANSFORM` + `MARKDOWN_LINK_COMPONENTS`. No `rehype-raw`. |

---

## 2. Mode-aware Chat — the central rewire

### 2.1 Concept

Today: a new conversation is a blank chat. The same `studio_chat_agent` system prompt + tool set applies to everything (CB-2864 v1 made it write-capable).

Tomorrow: a new conversation opens with a **ModePicker**. The user picks a mode (or adds a new one). The selection:

1. Sets the session's `mode_id` (persisted to DB column).
2. Switches the system prompt for that session to the mode's prompt.
3. Restricts the agent's tool allow-list to the mode's tool subset.
4. Sets the default model (Opus/Sonnet/Haiku) for that session.
5. Names the tab `{project-slug}-{mode-slug}-{auto-title}`.

Modes are user-editable rows in a `studio_modes` DB table. Three are seeded as built-ins (Bug Reporter, Feature Planner, Continue Existing Feature). The user can add/edit/delete from `/studio/modes`.

### 2.2 Data model

```sql
CREATE TABLE studio_modes (
  id                TEXT PRIMARY KEY,           -- CUID
  tenantId          TEXT NOT NULL,              -- multi-tenant scope
  projectId         TEXT NULLABLE,              -- NULL = workspace-level mode; non-null = project-scoped
  slug              TEXT NOT NULL,              -- kebab-case, unique per (tenantId, projectId)
  name              TEXT NOT NULL,              -- display name
  description       TEXT,                       -- one-line description
  icon              TEXT,                       -- emoji or lucide icon name
  systemPrompt      TEXT NOT NULL,              -- the mode's system prompt
  toolAllowList     TEXT NOT NULL,              -- JSON array of tool names; "*" = all
  defaultModel      TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
  tabTitlePattern   TEXT NOT NULL DEFAULT '{project}-{mode}-{title}',
  isBuiltin         INTEGER NOT NULL DEFAULT 0, -- 0/1
  isActive          INTEGER NOT NULL DEFAULT 1,
  createdBy         TEXT,                       -- userId
  createdAt         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updatedAt         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(tenantId, projectId, slug)
);

-- Extend StudioSession
ALTER TABLE studio_sessions ADD COLUMN modeId TEXT REFERENCES studio_modes(id);
```

### 2.3 Seeded built-in modes

| Slug | Name | System-prompt focus | Tools allowed | Default model |
|---|---|---|---|---|
| `bug` | Report a bug | Reproduce, investigate, file ticket. Pulls Bible Rule 28 + qa-regression hooks. | `ask_clarifying_question`, `search_codeboard`, `read_repo_file`, `start_investigation`, `create_codeboard_issue`, `chrome_repro` | `claude-opus-4-7` |
| `feature` | Discuss new feature | Full FEATURE→EPIC→STORY→TASK→SUBTASK breakdown. Rule 7+23+32 hooks. Mandatory Code Audit + QA + Regression epics auto-appended. | `ask_clarifying_question`, `search_codeboard`, `read_repo_file`, `query_rag`, `create_artifact`, `propose_breakdown`, `create_codeboard_issue` | `claude-opus-4-7` |
| `continue` | Continue existing feature | Loads existing FEATURE context from CodeBoard, reads its tree, proposes next steps. | `search_codeboard`, `read_repo_file`, `query_rag`, `update_codeboard_issue_status`, `hand_to_autopilot` | `claude-sonnet-4-6` |

User can edit any of these (with "Restore default" option per row).

### 2.4 API contract

```
GET    /api/studio/modes                      → list modes visible to current tenant+project
POST   /api/studio/modes                      → create a custom mode
GET    /api/studio/modes/{id}                 → read one
PATCH  /api/studio/modes/{id}                 → edit
DELETE /api/studio/modes/{id}                 → soft-delete (only non-builtin OR overrides)
POST   /api/studio/modes/{id}/restore-default → only for built-ins; reverts edits

POST   /api/studio/sessions                   → existing endpoint, NOW accepts mode_id (required)
PATCH  /api/studio/sessions/{id}              → existing, accepts mode_id (switch mode)
```

All gated by `InternalAuthDep` + `TenantDep` + 60/min rate limit per session_id.

### 2.5 Per-turn tool gating

`studio_chat_agent.run_turn(session, db)`:

1. Load `session.mode_id` → look up `studio_modes` row.
2. Use mode's `systemPrompt` instead of the static `_JONNY_SYSTEM_PROMPT`.
3. Compute the effective tool list:
   - If `toolAllowList == "*"` → all 7 current Studio tools + investigation tool.
   - Else: intersection of mode's list + the 7 implemented tools (security guard: model can't enable tools the dispatcher doesn't recognize).
4. Pass to Anthropic Messages API with `tools=effective_tools` and `system=mode.systemPrompt`.
5. Use `mode.defaultModel` unless the session explicitly overrides.

### 2.6 User stories

| As a … | I want … | So that … |
|---|---|---|
| Developer reporting a bug | A focused mode that knows Rule 28 + auto-files CodeBoard | I don't have to remember the discipline each time |
| Product manager | A feature-planning mode that builds the full tree + audit/QA epics | I get Rule 32-compliant tickets without writing the boilerplate |
| Team lead extending the workflow | An admin page where I add a "Postmortem" mode with my prompt + tool subset | We don't need a code change per workflow |
| Engineer mid-implementation | A "Continue existing feature" mode that loads the CB tree | The agent isn't re-asking what we've already decided |

---

## 3. Per-sidebar-item architecture

Each sub-feature below: user stories → data model → APIs → components → integration → edge cases.

### 3.1 Dashboard

| Aspect | Detail |
|---|---|
| **User stories** | (a) PM/dev sees one-glance health of the project: open CB issues by status, active Studio sessions, AutoPilot queue depth, cost-MTD, recent activity. (b) Click any tile → drill into the related sidebar item. |
| **Data model** | No new tables. Aggregates from `Issue`, `StudioSession`, `AutoPilotQueueRecord`, `TenantTokenUsage`, `StudioAgentActivity`. |
| **APIs** | `GET /api/studio/dashboard?project_id=...` — single rollup endpoint. Returns `{issue_counts_by_status, active_sessions, queue_depth, cost_mtd, recent_activity[20]}`. |
| **Components** | `app/studio/dashboard/page.tsx`. Six tiles + recent-activity feed. React Query stale 30s. |
| **Edge cases** | Empty project (no issues yet) → empty-state tile with "Create first issue" CTA. Backend down → individual tiles show error state, don't collapse the page. |
| **Multi-tenant** | Endpoint takes `TenantDep`. All counts scoped to `(tenantId, projectId)`. |

### 3.2 Chat (mode-aware) — covered in §2 above

### 3.3 Modes (registry editor)

| Aspect | Detail |
|---|---|
| **User stories** | (a) User views built-in + custom modes. (b) Clicks Add Mode, fills name/description/prompt/tool-picker/model. (c) Edits a mode. (d) Deletes a custom mode. (e) Restores a built-in mode to default. |
| **Data model** | `studio_modes` table (§2.2). |
| **APIs** | §2.4. |
| **Components** | `app/studio/modes/page.tsx` — list view. `ModeEditorDialog.tsx` — modal with form. `ToolPicker.tsx` — multi-select over 31 agents + 63 skills + 7 Studio tools (search + categorize by source). |
| **Edge cases** | Slug collision → API returns 409, UI shows "slug already used". Deleting a mode in active use → API returns 409 + lists session_ids using it. User must switch them first. |
| **Multi-tenant** | Modes scoped to tenantId. Project-scoped modes only visible inside that project. Workspace-level modes visible to all projects of the workspace. |

### 3.4 Agents page

| Aspect | Detail |
|---|---|
| **User stories** | (a) Browse 31 agents grouped by source (standalone/plugins). (b) Search/filter. (c) Click an agent → details panel with description + Assign action. (d) Assign opens new Studio chat tab with `@agent` pre-inserted in current project. |
| **Data model** | Reuses `agent_registry_service.get_all_agents` (already exposes `/api/agents`). |
| **APIs** | Existing `GET /api/agents`. NEW: `GET /api/studio/agents/{name}/details` for the side panel. |
| **Components** | `app/studio/agents/page.tsx`. `AgentList.tsx`, `AgentDetailDrawer.tsx`. |
| **Edge cases** | Agent disabled in project settings → Assign disabled with tooltip. Agent name with special chars → ToolPicker validates against `_NAME_RE`. |

### 3.5 Skills page — same shape as Agents page, over 63 skills.

### 3.6 Story Board

| Aspect | Detail |
|---|---|
| **Decision** | Sidebar item links to existing `/codeboard` route — no new build. Pre-filtered to current project. |
| **Edge case** | If user switches project via ProjectSwitcher while on /codeboard, URL updates to reflect. |

### 3.7 Visualizer

| Aspect | Detail |
|---|---|
| **User stories** | (a) Renders `StudioArtifact` rows of kind `mermaid` or `hierarchy_json` in a full-page canvas. (b) Pan/zoom. (c) Export PNG/SVG. |
| **Data model** | Existing `StudioArtifact` table. |
| **APIs** | `GET /api/studio/projects/{pid}/artifacts?kind=mermaid,hierarchy_json` (existing). NEW: `POST /api/studio/artifacts/{id}/export?format=png|svg`. |
| **Components** | `app/studio/visualizer/page.tsx`. Mermaid via `mermaid.js` CDN (loaded lazy). Hierarchy via custom tree renderer. |
| **Edge cases** | Malformed mermaid → render error inline, don't crash. Very large hierarchy (1000+ nodes) → virtualized list. |

### 3.8 Mockup Studio

| Aspect | Detail |
|---|---|
| **User stories** | (a) User describes a UI element ("login form with email + Google SSO"). (b) Agent generates React/Tailwind JSX. (c) Live preview in iframe. (d) Source code shown in editor. (e) Save to artifacts. |
| **Data model** | `StudioArtifact` rows with `kind="mockup"` and `content` = JSX source. |
| **APIs** | `POST /api/studio/mockups/generate` → invokes `frontend-design` skill via `AgentDispatcher`. Returns artifact_id. |
| **Components** | `app/studio/mockups/page.tsx`. Two-pane: prompt + JSX editor on left, sandbox iframe on right. `MonacoEditor.tsx` for source. |
| **Edge cases** | iframe sandboxing: `sandbox="allow-scripts"` (no `allow-same-origin`) — JSX runs but can't read parent. Mockup uses inline Tailwind + React via CDN; no build step required. |
| **Security** | XSS prevented by sandbox + `Content-Security-Policy` `default-src 'none'; script-src https://esm.sh https://cdn.tailwindcss.com`. |

### 3.9 Workflows

| Aspect | Detail |
|---|---|
| **User stories** | (a) See AutoPilot queue for current project. (b) Inspect each queue's tasks/events/audit log. (c) Trigger force-recover when stuck. |
| **Data model** | Existing `AutoPilotQueueRecord`, `AutoPilotTaskRecord`, `AutoPilotEvent`. |
| **APIs** | Existing `GET /api/execute/queue` + `GET /api/execute/queue/{id}/events`. NEW project-scoped filter. |
| **Components** | `app/studio/workflows/page.tsx`. Queue list + drill-down. Recovery panel (force-recover button with confirm modal). |
| **Edge cases** | Force-recover requires double-confirm. Recovery action audit-logged. |

### 3.10 Compare

| Aspect | Detail |
|---|---|
| **User stories** | (a) Pick two artifacts of same kind. (b) Side-by-side diff (markdown/code/hierarchy). (c) Used for spec revisions, mockup iterations, etc. |
| **Components** | `app/studio/compare/page.tsx`. `react-diff-viewer-continued` for text. Custom hierarchy diff for JSON trees. |

### 3.11 Artifacts

| Aspect | Detail |
|---|---|
| **User stories** | (a) Browse all `StudioArtifact` rows for the project. (b) Filter by kind/session/date. (c) Open in canonical viewer (Visualizer for diagrams, Specs for markdown, Mockup Studio for JSX). (d) Pin to project. |
| **Data model** | Add `pinned: bool` column to `StudioArtifact`. |
| **APIs** | Existing list. NEW `PATCH /api/studio/artifacts/{id}/pin`. |
| **Components** | `app/studio/artifacts/page.tsx`. Table + filters. |

### 3.12 Specs

| Aspect | Detail |
|---|---|
| **User stories** | (a) Write/edit project PRDs and specs in markdown. (b) Versioned (every save = new revision). (c) Link to issues. |
| **Data model** | New table `studio_specs (id, projectId, tenantId, title, slug, content, version, parent_revision_id, created_by, created_at)`. Versioning is append-only + a `currentVersion` pointer per slug. |
| **APIs** | `GET/POST/PATCH /api/studio/specs[/...]`. Diff endpoint for two revisions. |
| **Components** | `app/studio/specs/page.tsx` — list. `app/studio/specs/[slug]/page.tsx` — editor (Monaco/markdown + preview). |

### 3.13 Context

| Aspect | Detail |
|---|---|
| **User stories** | (a) Project-level reference docs (architecture overview, glossary, dependencies). (b) Auto-indexed into RAG so chat agents can `query_rag` them. |
| **Data model** | New table `studio_context_docs (id, projectId, tenantId, slug, content, indexed_at)`. Hook to `rag_service.index_doc` on save. |
| **APIs** | Same shape as Specs. `POST /api/studio/context/{id}/reindex` to force RAG refresh. |

### 3.14 Memory

| Aspect | Detail |
|---|---|
| **User stories** | (a) Browse what the project remembers across sessions — i.e. RAG-indexed content. (b) See top-K results for a search query. (c) Delete embeddings the user no longer wants the agent referencing. |
| **Data model** | Reads from ChromaDB via `rag_service.search`. NEW endpoint to forget specific docs. |
| **APIs** | `GET /api/studio/memory?q=...` → top-K. `DELETE /api/studio/memory/{doc_id}` → ChromaDB delete. |

---

## 4. SIE migration — right rail → in-chat tool

### Today (CB-2914)

- Right rail mounts `InvestigationCyclePanel` when a session is active.
- User types into the panel's own textarea + clicks Investigate.
- SSE streams layer status into the panel.
- 5-part deliverable renders in the same panel.

### Tomorrow

- `InvestigationCyclePanel` + `ResizableSplit` + `investigationPanelWidthPx` REMOVED.
- The `bug` mode's system prompt instructs the agent to:
  1. Ask 1-3 clarifying questions if needed (`ask_clarifying_question`).
  2. Call `start_investigation` tool with the bug description + evidence.
  3. The tool dispatcher fires the SIE engine. As each layer transitions, an `agent_activity` row is recorded — the chat surface streams these as inline assistant messages with a compact "Layer X: running…" UX.
  4. When the engine returns, the deliverable markdown is sent as a single assistant message (ReactMarkdown + remark-gfm + SAFE_URL_TRANSFORM).
  5. Agent proposes the CB ticket → user `approve` → agent calls `create_codeboard_issue` → reports the key.
- The `start_investigation` tool is one of the 7 Studio tools (registered in `_TOOLS` in `studio_chat_agent.py`). Multi-tenant scoped via `session.projectId`.
- The `/api/studio/sessions/{id}/investigate` endpoint is REMOVED (no longer needed — agent invokes the engine in-process via the tool handler).

### Why this is better

- Single surface for the user. No context switching between chat and side panel.
- Conversational: agent can interleave clarifying questions, partial findings, and follow-up runs naturally.
- Reuses the existing chat persistence (CB-2814) + audit log + cost tracking.
- Lower frontend surface area: no `ResizableSplit`, no `InvestigationCyclePanel`, no extra SSE consumer.

---

## 5. Migration ordering (hard deps)

| Step | Depends on | Risk |
|---|---|---|
| 1. Build StudioSidebar shell + route conditional | nothing | low |
| 2. Build Mode registry table + CRUD API + seed 3 built-ins | (1) | medium — schema change |
| 3. Build ModePicker + per-turn system prompt + tool gating | (2) + studio_chat_agent | high — touches every chat turn |
| 4. Update tab title format `{project}-{mode}-{title}` | (3) | low |
| 5. Wire SIE as `start_investigation` tool | (3) | medium — refactor engine entry |
| 6. Render layer status + deliverable as inline chat messages | (5) | medium — chat message rendering for tool results |
| 7. Kill `InvestigationCyclePanel` + `ResizableSplit` | (6) verified | low |
| 8. Build `/studio/dashboard` | (1) | low |
| 9. Build `/studio/agents` + `/studio/skills` (read-only) | (1) | low |
| 10. Build `/studio/modes` editor (CRUD UI for table from step 2) | (2) | medium |
| 11. Build `/studio/visualizer` | (1) + existing artifacts API | medium — mermaid dependency |
| 12. Build `/studio/mockups` | (1) + frontend-design skill | high — iframe sandbox, security |
| 13. Build `/studio/workflows` | (1) + existing AutoPilot API | low |
| 14. Build `/studio/compare` | (1) + react-diff-viewer | low |
| 15. Build `/studio/artifacts` + pin endpoint | (1) | low |
| 16. Build `/studio/specs` (new table + editor) | (1) + new schema | medium |
| 17. Build `/studio/context` (new table + RAG integration) | (1) + rag_service | medium |
| 18. Build `/studio/memory` (RAG query + forget) | (17) | medium |
| 19. **MANDATORY** Code Audit Epic | all above | gate |
| 20. **MANDATORY** QA Epic — qa-regression skill | (19) | gate |
| 21. **MANDATORY** Full Regression + 5 user-regression phases | (20) | gate |

This is 21 epics. CB-2914 SIE + CB-3001 sidebar plan + this re-architecture
together = a real multi-week feature, not a one-day push.

---

## 6. Open questions before push

| # | Question |
|---|---|
| 1 | Confirm mode is **single per tab** (switching mode = new tab)? Or switchable mid-conversation with audit-trail? |
| 2 | Per-mode default model — Opus for `bug` + `feature`, Sonnet for `continue` — agreed? Or always Opus? |
| 3 | Workspace-level modes vs project-scoped modes — both supported? Or project-only for v1? |
| 4 | `/studio/mockups` — generate JSX or only renders artifacts other modes produced? Building a generator requires `frontend-design` skill in-the-loop. |
| 5 | `/studio/memory` — should "forget" be physical delete from ChromaDB or soft-mark `forgotten=true`? |
| 6 | Update CB-3001 in place (preferred — keeps ticket history) or file new CB-3128 superseding? |
| 7 | Build order: kill right rail FIRST (clean slate) or build sidebar + modes IN PARALLEL with right rail still alive? |
| 8 | When does this start? After current QA, or now? |

---

## 7. What this document is missing (to be filled after Eli answers)

- Exact wireframes for each new page (need design pass via `frontend-design` skill).
- Token-budget per mode (Opus is expensive — what's the cap before throttling kicks in?).
- Onboarding flow for new users (mode picker for first conversation may be confusing — need a walkthrough?).
- Migration script for existing `StudioSession` rows (set `modeId` to default = "feature" or NULL = "free chat" mode?).
- Backwards compat with any external API consumers of `/api/studio/sessions/{id}/investigate` — that endpoint is removed.

---

## 8. Next steps

1. **Eli reviews this doc** + answers §6 questions.
2. I update CB-3001 (or file new) with the 21-epic plan derived from §5.
3. Per Rule 32: each epic gets Stories + Tasks tables with agent assignments. Mandatory Code Audit + QA + Regression epics at the end.
4. Push to CodeBoard. Start step 1 of §5.

**No code lands until §6 is answered and the CodeBoard plan is approved.**
