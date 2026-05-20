# Studio (CB-2384) — Master Build Synthesis · 2026-05-20

Synthesis of 9 parallel design/research agents. Drives the autonomous build Eli authorised today.

Companion docs (each consumed and reconciled here):
- `docs/plans/2026-05-07-ai-project-workspace-master-plan.md` — original v2.0 spec (authoritative)
- `docs/plans/2026-05-20-studio-cloud-multitenant-architecture.md` — cloud + tenancy decisions
- `docs/plans/2026-05-20-studio-chat-agent-design.md` — chat agent architecture
- `docs/plans/2026-05-20-studio-api-contract.md` — 41 endpoint catalog
- `docs/plans/2026-05-20-studio-frontend-architecture.md` — component tree + MVP
- `docs/2026-05-19-codeboard-backlog-audit.md` — board reality check

## Mandate (immutable)

1. **Multi-tenant from day one.** Every new table carries `tenant_id`. Every new API derives tenant from a single dependency. Today single-user (`tenant_id` nullable + default tenant) — but the column and the dep land now, not in Phase 2.
2. **Cloud-deployment-ready.** Stateless handlers. No localhost hardcodes. SSE + DB-replay reconnection. Externalised secrets.
3. **SaaS-shippable later.** Per-tenant token usage rows from line one. Cost attribution per `studio_message` and `studio_subagent_run`.
4. Status flow per bible — every shippable unit → `COMPLETED_WAITING_QA`. Only Eli promotes to DONE (Rule 22).

## Architecture decisions

| Layer | Choice | Why |
|-------|--------|-----|
| Tenancy model | Shared DB + `tenant_id` column + Postgres RLS (Phase 2) | Cheapest at scale, RLS is the safety net |
| Auth (Phase 1) | `InternalAuthDep` + synthetic tenant; `MULTI_TENANT_MODE=false` flag | Doesn't break existing platform; incremental migration |
| Auth (Phase 2) | JWT at FastAPI dep, GitHub OAuth day-one | Eli already on GitHub; OIDC deferred |
| Database (Phase 1) | SQLite (existing) | No rip-up; tenant_id columns added now |
| Database (Phase 2) | Supabase Postgres + pgvector | Replaces ChromaDB, RLS-native, $25/mo |
| Chat runtime | **Anthropic Messages API direct** — NOT Claude Code CLI subprocess | Replica-portable, native tool blocks, prompt caching, cost attribution |
| Sub-agents | Nested API calls (max chain depth 1), orchestrator-workers workflow | Known sub-tasks → workflow beats open agency for cost + failure |
| Streaming | SSE + `Last-Event-ID` + DB replay catch-up | Crash-safe, multi-replica friendly |
| Frontend | Next.js 16 App Router, React Flow v12 for Crew Map, Zustand for client state | Composes with existing CodeBoard UI |
| Deployment (Phase 2) | Vercel + Fly.io + Supabase + Upstash + R2 | ~$55/mo idle, ~$1.64 infra per tenant |
| AutoPilot in cloud (Phase 2) | Fly Machines per task (~$0.01 per 30-min run) | Ephemeral gVisor isolation |

## Data model — 10 new tables (`tenant_id` on every one)

Studio: `studio_sessions`, `studio_messages`, `studio_tool_calls`, `studio_subagent_runs`, `studio_artifacts`, `studio_hierarchy_drafts`, `studio_agent_activity`
Shared: `agent_templates`, `agent_instances`, `tenant_token_usage`
Backlog: `backlog_items`, `backlog_comments`, `backlog_activity`
Crew Map: `crew_assignments`, `crew_skill_usage`

Tenancy + audit columns on every table: `id` (cuid) · `tenant_id` (string, nullable Phase 1) · `created_at` · `updated_at` · `created_by` (nullable Phase 1).

## API surface — 41 new endpoints + 3 SSE channels

Pattern: every resource route uses `get_tenant_scoped_resource(...)` FastAPI dependency. **404 (not 403) on cross-tenant** — never leak existence. `X-Tenant-ID` from trusted proxy header in Phase 2; from `settings.DEFAULT_TENANT_ID` fallback in Phase 1.

Highlights:
- Studio: `POST /api/studio/projects/{id}/sessions` · message append returns **202 + streamUrl** · SSE `/api/studio/sessions/{id}/events` with 16 event types; `agent_dispatch` fires AFTER DB row persists (Visibility Principle at protocol level)
- Backlog: ETag-conditional writes · `POST /promote` 202 + jobId · `POST /validate-schedule` must respond <100ms (Doherty)
- Crew Map: full graph + sub-graph endpoints; SSE node/edge mutations

Cursor-based message pagination (no page races during streaming). No `/v1/` prefix in Phase 1.

## Chat agent — 9 tools + model routing

Tools: `ask_clarifying_question` (max 4) · `spawn_subagent` (max 3/turn, depth 1) · `search_codeboard` · `read_repo_file` (absolute paths only, 8K cap) · `query_rag` · `create_artifact` · `push_hierarchy_draft` · `push_breakdown_to_codeboard` (explicit user approval required) · `hand_to_autopilot` (first 10 runs require confirmation).

Model routing — Haiku-4-5 (clarification + classification) · Sonnet-4-6 (researcher / designer / auditor / revisions) · Opus-4-7 (orchestrator planning + breakdown_writer first draft). A ~250-token Haiku pre-call classifies each user turn → routes the orchestrator model.

Prompt cache: 3K system + 800 few-shot ephemeral. Estimated 60-75% hit, ~55-65% input-token cost cut.

## Frontend — 4 routes, MVP slice

Routes under `/workspace/[id]/{studio,backlog,crew-map}` + shared workspace layout (switcher + tabs). Compound Component + Context for Chat. `useRef` token buffer + 50ms flush (one render per 50ms max). React Query keys prefixed `['workspace', workspaceId, ...]` for hard isolation. SSE backoff 1→30s cap.

UX language: Claude warm-parchment chat panel (`#f5f4ed`) + Cursor warm-dark artifact panel (`#26251e`). Cursor AI Timeline pattern for agent activity (semantic colors: peach/sage/blue/lavender). Linear conventions for Backlog cards + status pills. Figma chrome-monochrome for Crew Map (`#08090a`).

**MVP slice (what ships first):** Studio chat shell · token streaming · agent status panel · Backlog list + filter bar + edit modal (no scheduler) · bridge between them. NOT in MVP: PreviewPane, Crew Map, drag-reorder, cron, "Send to CodeBoard + AutoPilot", hibernation, animation polish.

## Phase staircase

| Step | What ships | Today's build covers |
|------|-----------|---------------------|
| **0 — local foundation (THIS SESSION)** | Backend models + migration + base routes; frontend `/workspace` shell + Studio chat + Backlog list; chat agent runtime (Messages API + 5 tools); SQLite; default tenant | ✅ THIS BUILD |
| 1 — cloud single-tenant | Postgres swap, JWT on Studio routes, Fly+Vercel deploy, pgvector, R2, Fly Machines for AutoPilot | later |
| 2 — closed beta | Tenant + Membership + User tables, RLS enforced, invite tokens, Redis locks | later |
| 3 — public SaaS | Self-serve signup, Stripe/Paddle billing, free tier enforcement, usage dashboard | later |

## What this session builds (Step 0 scope)

**Backend foundation (Phase 4):**
- SQLAlchemy + Prisma models for all 10 new tables, `tenant_id` nullable, default tenant constant.
- Alembic migration (or Prisma push for the frontend mirror).
- `get_tenant_scoped_resource` dependency.
- `studio_orchestrator` service skeleton.
- Base API routes — sessions CRUD + message append (202) + SSE channel scaffold + backlog CRUD.

**Frontend foundation (Phase 5):**
- `/workspace` redirect → last workspace, workspace context provider.
- `/workspace/[id]/studio` — chat shell, token streaming via SSE, agent status row stub.
- `/workspace/[id]/backlog` — list + filter bar + edit modal.
- Workspace top bar + workspace switcher (dropdown stub with default tenant).

**Chat agent runtime (Phase 6):**
- Anthropic Messages API client w/ prompt caching headers.
- 5 day-one tools: `ask_clarifying_question`, `search_codeboard`, `query_rag`, `create_artifact`, `push_hierarchy_draft` (no auto-promote until Phase 2 review).
- Visibility Principle — `studio_agent_activity` row written BEFORE dispatch surfaces in SSE.
- Per-tenant token-usage rollup.

**Quality gates (Phase 7):**
- code-reviewer + security-auditor on the full diff.
- Backend tests: tenant-scoping returns 404 (not 403); message append returns 202 + streamUrl; SSE replays on `Last-Event-ID`.
- Frontend tests: chat renders streaming tokens; Backlog filter URL persists.
- Chrome QA: load `/workspace`, screenshot, verify zero console errors.

## CodeBoard reconciliation

276 child tasks of CB-2384 are coherent and stay. Inject **E0 Multi-Tenant Foundation** epic before E1 to cover the 10 multi-tenant/cloud gaps the audit identified. CB-2121 (auth) becomes an E0 child.

## Practitioner principles (Lenny's Podcast — Krieger, Yu, Rauch, Truell, Saarinen, Ramanujam)

Locked into the build, not just nice-to-have:

- **10% rule (Yu/Linear).** First working slice = text prompt → AI plan → one "Push to Backlog" button. Nothing else needed to gut-check. This IS our MVP today.
- **Chat+artifact form (Rauch/v0).** Artifact pane must accept edits that feed back into the conversation. Not a passive display. (Day-one stub: read-only artifact pane; edit affordance Phase 1.)
- **MCP-first (Krieger/Anthropic).** Studio's push-to-backlog tool should be modelled after MCP semantics so the same primitive serves external tenants later. Today the tool calls the internal API directly; the function shape is MCP-shaped (verb + structured args + idempotency key).
- **Opinionated defaults (Saarinen/Linear).** One hierarchy (FEATURE→EPIC→STORY→TASK→SUBTASK), one agent persona ("Jonny"), one push destination (CodeBoard). NO per-tenant prompt customization, label customization, or sub-agent role config at launch.
- **Dogfood for the magic moment (Truell/Cursor).** First demo = Studio pushing a real plan back into THIS repo's CodeBoard. The audit + 276-task hierarchy work I did yesterday is the dogfood corpus.
- **B2C2B distribution (Zhao/Notion).** Generated plan = shareable landing page (Phase 2). The artifact is the viral surface.
- **Price before product (Ramanujam).** Pricing not built today, but token usage per `studio_message` + `studio_subagent_run` rows land now so per-tenant attribution is queryable from day one. Hybrid seat + overage is the target model (Phase 3).

## Out of scope today

- Crew Map graph (deferred; backend tables land for forward compatibility, frontend stub only)
- Drag-reorder Backlog
- Cron scheduler
- Promote pipeline state machine (route exists, logic stubbed)
- Hibernation / resume
- Per-tenant Claude API keys (Phase 2)
- Postgres / RLS (Phase 2)
- OAuth login (Phase 2)

Building now.
