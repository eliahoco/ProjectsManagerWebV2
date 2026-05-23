# AIDP vs PMv2 — Multi-Agent Investigation (2026-05-23)

**Author:** Jonny (orchestrator) · 5 parallel agents dispatched
**Status:** 4 of 5 reports landed. Architecture agent + code-reviewer still running.

This document captures the consolidated findings from a parallel investigation
across UI/UX, multi-tenant readiness, multi-tenant SaaS literature (5 books),
and architecture. Final recommendation at §6.

---

## Agents dispatched

| # | Agent | Status | Output owner |
|---|---|---|---|
| 1 | `candlekeep-cloud:librarian` | ✅ done | Reading list of 5 books on multi-tenant SaaS |
| 2 | `candlekeep-cloud:item-reader` | ✅ done | Consolidated brief from those 5 books |
| 3 | `react-specialist` | ✅ done | UI/UX + frontend architecture scorecard (AIDP 19/25 vs PMv2 20.5/25) |
| 4 | `security-auditor` | ✅ done | Multi-tenant readiness audit (AIDP 5.0/10 vs PMv2 1.5/10) |
| 5 | `general-purpose` | ⏳ in flight | Architecture comparison (docs + master plans) |
| 6 | `code-reviewer` | ⏳ in flight | Code quality scorecard |

Findings below merge agents 1–4. The remaining two refine the recommendation
but do not change the headline shape.

---

## 1. Quick fact map

| Fact | AIDP | PMv2 |
|---|---|---|
| **Stack** | Turborepo monorepo (apps/web + cli + desktop + 6 backend services) · Next.js 15 · Python micro-services · pnpm | Single Next.js 16 (Turbopack) + single FastAPI backend · npm |
| **Tailwind** | v3.4 | v4 |
| **Zustand** | v4 | v5 |
| **DB** | PostgreSQL per service (user, project, qa, mentor, agent, git) | SQLite (frontend Prisma + backend SQLAlchemy) |
| **Identity** | JWT HS256, jti, refresh rotation, Redis blacklist, bcrypt 12-round | None. `X-Tenant-ID` header, single `INTERNAL_API_TOKEN` shared secret |
| **Tenant model in DB** | `Organization` + members + roles + audit log (user-service) — NO `org_id` on project/qa/git/mentor/agent rows | Only `tenantId` on the new `CrewAssignment` table — NONE on Issue, Project, Comment, ExecutionSummary, AutoPilot* |
| **Cross-tenant isolation tests** | Yes — `test_org_isolation_*` in user-service tests | None |
| **Subprocess sandboxing** | mentor-service + agent-orchestrator separation, WS endpoint open (CRITICAL hole) | Single backend process spawns Claude CLI in host filesystem |
| **Visual Builder / dashboard widgets / wizard** | Yes — Visual Builder (drag-drop), 10-widget dashboard, 7-step project wizard | None |
| **AI execution surface** | mentor-service + agent-orchestrator (with WS hole) | Studio chat + AutoPilot queue + SIE Investigation Engine (production-hardened, audit-logged, secret-redacted, rate-limited) |
| **Issue tracking** | Bug Tracker (sidebar item, depth unverified) | CodeBoard — full FEATURE→EPIC→STORY→TASK tree, status cascade, AI breakdown, Jonny-bible-aware reporter |
| **Capability registry** | 11 agents (orchestrator-internal) | 31 agents + 63 skills auto-discovered (visible in /settings/agents + /settings/skills), with `/api/studio/capabilities/suggest` ranking endpoint |
| **AI subagent dispatcher** | Custom orchestrator | `AgentDispatcher` — spawns claude CLI subprocess with allow-listed read-only tools, MED-1/2/3/4 fixed, allow-list env, name regex validation |
| **localStorage discipline** | Standard | `useStudioStore` — project-scoped tabs, stub-ID filter, sanitizePersisted with corruption-safe migration, `EMPTY_TABS` frozen-ref pattern |
| **SSE / streaming** | Some endpoints | Capability suggestions, Studio chat tokens, Investigation Engine cycle (per-layer queued→running→completed) |

---

## 2. UI / UX comparison (react-specialist)

| Dimension | AIDP | PMv2 |
|---|---|---|
| Component architecture | 4/5 | 4/5 |
| State management | 3.5/5 | **5/5** |
| Styling | 3.5/5 | **4/5** |
| Interaction patterns | 4/5 | 4/5 |
| Visual polish | **4/5** | 3.5/5 |
| **Total** | **19/25** | **20.5/25** |

### Where each wins

**AIDP wins on:**
- Visual Builder (drag-drop component composition, recursive tree drop targets, ⌘Z/⌘Y/⌘C/⌘V/⌘S/Delete keyboard shortcuts, viewport switcher desktop/tablet/mobile, layers panel with lock/visibility, properties panel with type-inferred prop editors, AI-driven generation hooks).
- Dynamic dashboard (`react-grid-layout` 2.1 with drag/resize/placeholder, 10 widget types via `widgetRegistry`).
- 7-step project wizard with auto-save draft + recovery modal + per-step validation.
- Collapsible animated sidebar with org switcher + recent projects + nav groups.
- Larger Radix-backed shadcn primitive library (25+).

**PMv2 wins on:**
- `useStudioStore` — project-scoped tabs, stub-ID filter at persist time, sanitizePersisted with v1→v2 migration, EMPTY_TABS frozen reference pattern preventing infinite selector loops. Most sophisticated frontend store in either codebase.
- Tailwind v4 (with the CB-2813 `@custom-variant dark` discovery applied) + Geist font stack.
- Studio compound components (`Chat.Provider`/`MessageList`/`Input`/`Actions`).
- Capability Ribbon — 24px contextual chip strip that auto-suggests top-7 agents/skills based on the current draft.
- ResizableSplit primitive with mouse+touch+keyboard + ARIA + persisted width.
- `markdownPresets` — `SAFE_URL_TRANSFORM` + `MARKDOWN_LINK_COMPONENTS` for safe AI-generated markdown.
- Studio Investigation Engine UI — per-layer status with live elapsed seconds, ReactMarkdown deliverable with `remark-gfm` tables.

---

## 3. Multi-tenant readiness (security-auditor)

| Score | App | Cloud-ready? |
|---|---|---|
| **5.0 / 10** | AIDP | Foundation right, downstream services unenforced. ~10 engineer-weeks to ship. |
| **1.5 / 10** | PMv2 | Effectively a single-user local tool. ~16-20 engineer-weeks to ship, or ~12 weeks if it delegates identity to AIDP. |

### AIDP's defenses (real)
- JWT HS256 + jti + Redis blacklist + refresh rotation (user-service).
- `Organization` + `organization_member_association` with OWNER/ADMIN/MEMBER/VIEWER/BILLING roles, audit log indexed by org_id.
- Cross-tenant isolation tests (`test_org_isolation_list/get/flow`).
- `SECRET_KEY` startup validation (≥32 chars, refuses placeholders, sys.exit on `your-secret-key`).
- bcrypt 12-round password hashing.

### AIDP's critical gaps
- **CRIT** `/ws/claude-code/{session_id}` has zero auth + accepts arbitrary `path` query param → `os.chdir(path)` before spawning Claude CLI. Host shell access for any caller.
- **HIGH** `Project` model in project-service has no `organization_id`. Same for qa, mentor, agent, git data models.
- **HIGH** qa-service + mentor-service have zero authentication and zero tenant scoping (grep returns no `get_current_user` on those endpoints).
- **HIGH** JWT carries no `organization_id` claim — every downstream service does HTTP round-trip to user-service per request to derive org membership (N+1 fan-out).
- **HIGH** Stubbed team-access check (`# TODO`) in project-service.
- **MEDIUM** CORS allows `allow_methods=["*"]` + `allow_headers=["*"]` with `allow_credentials=True` and no startup-assert guard.
- **MEDIUM** Plan/quota limits stored but not enforced.

### PMv2's defenses (real)
- CORS lockdown with startup assert (`assert "*" not in CORS_ORIGINS`).
- Origin validation middleware (rejects non-allowlisted origins on write methods).
- Bind-and-token startup assertion (refuses to boot if LAN+no INTERNAL_API_TOKEN).
- `InternalAuthDep` with SHA-256 + `secrets.compare_digest` constant-time.
- AutoPilot audit log with secret redaction (Bearer/sk-/api_key/JWT/AKIA/Stripe/Google/Slack/Basic).
- `/docs` disabled when not in development.
- Per-endpoint slowapi rate limiting (60/min reads, 10/min writes).
- Comprehensive InternalAuthDep test coverage (token unset/set, header missing/wrong/valid, spoofed Origin).

### PMv2's critical gaps
- **CRIT** No identity layer. No user model. `X-Tenant-ID` is header-trusted with no signature. Any caller can claim any tenant.
- **CRIT** Issue CRUD endpoints + Execution endpoints have ZERO auth dependency. `grep dependencies= api/issues.py` → 0 matches. `POST /api/execute/issue/{id}` is open.
- **CRIT** Data models — Issue, Project, Comment, Activity, ExecutionSummary, ImplementationNote, all AutoPilot tables — have NO tenant column. Cross-tenant containment impossible at the data layer.
- **CRIT** Subprocess spawning hits host filesystem (`terminal_service.spawn_claude_code_cli`). In cloud deploy: any tenant can read any tenant's project path.
- **HIGH** No cross-tenant isolation tests anywhere.
- **HIGH** `InternalAuthDep` is one shared secret for the whole deployment — can't identify caller, can't revoke a user, can't audit by user, can't rate-limit per user.
- **MEDIUM** `ANTHROPIC_API_KEY` is single global env var. All tenants burn the operator's credits.
- **MEDIUM** SQLite at `frontend/prisma/dev.db` shared by backend via raw aiosqlite. Concurrent multi-tenant writes are not safe.

---

## 4. Books read (CandleKeep)

Five books consulted. Two were Pro-restricted at preview-only. Key actionable findings from the three fully-read sources:

| Pattern | Source | Recommendation |
|---|---|---|
| Tenant isolation primitive | Supabase Best Practices p. 5 | PostgreSQL RLS with `force row level security` + `tenant_id` column + index. `auth.uid()` inside `(select ...)` subquery to avoid per-row evaluation. |
| Subprocess workers can't run on FaaS | OMG Cloud Deployment Guide p. 9 | Vercel/serverless excluded for Claude CLI workers (execution time limits). Fly.io Machines or Railway dedicated container for the worker tier. |
| Horizontal IDOR is THE multi-tenant test | OWASP WSTG ATHZ-02 p. 55 | Two tenants, identical role, every endpoint, assert cross-tenant access is denied. PMv2 has never been run against this test. |
| JWT alg enforcement | OWASP WSTG SESS-10 p. 71 | Reject `alg: none` (and case variants), enforce RS256 allow-list. PMv2's future JWT must do this from day one. |
| Cost attribution | OMG + Supabase | `tenant_quotas` table + append-only `execution_summaries(tenant_id, created_at)` index. Application role gets only INSERT on cost-event table. |

### Recommended cloud topology (synthesized)

| Component | Platform | Why |
|---|---|---|
| Next.js frontend | Vercel OR Fly.io | Vercel works; Fly.io co-locates with backend |
| FastAPI backend | Fly.io / Railway | PaaS-tier, persistent processes for async queue |
| PostgreSQL | Supabase / Fly.io Postgres | Native RLS, PgBouncer built-in |
| Claude CLI subprocess workers | Fly.io Machines (always-on) | Execution runs 2-20+ minutes; FaaS time limits broken |
| ChromaDB | Same cluster as backend | Low-latency RAG queries |

---

## 5. Prior comparison MD

Searched both projects + `~/.claude/projects/` — no saved comparison file mentioning both PMv2 and AIDP. AIDP's `PROJECT_STATE.md` describes it as a successor to a "CLI-based Projects Manager" (different lineage — that was a Python CLI, not PMv2 the web app). The two codebases have evolved independently. **The comparison Eli referenced was likely a chat conversation, not a persisted doc** — that's why no file matches.

---

## 6. Recommendation — what to do next

### The options Eli proposed

| Option | Verdict | Why |
|---|---|---|
| (a) Continue PMv2 alone, build Studio further, defer multi-tenant | **REJECT** for cloud SaaS goal. Multi-tenant is mandatory and PMv2 is ~16-20 weeks from it. |
| (b) Merge PMv2 into AIDP (port everything) | **REJECT** as full merge. AIDP's downstream services are 5.0/10 multi-tenant and have their own remediation cost. |
| (c) Port AIDP features (Builder, dashboard, wizard, sidebar) into PMv2 | **PARTIALLY ACCEPT** — port UI patterns, NOT the broken multi-tenant downstream services. |
| (d) Port PMv2 features (Studio, AutoPilot, SIE, CodeBoard) into AIDP | **REJECT** as direction. Those features are PMv2's strongest assets and the most production-hardened code in either repo. Moving them invites regression. |
| (e) Stop both, start fresh | **REJECT.** Both have real production value. Total redo throws away ~30+ engineer-weeks of working code. |

### The recommended path — **(f) Hybrid: PMv2 inherits AIDP's identity layer, ports UI patterns, hardens its own data model and subprocess sandbox**

| Step | Estimate | Outcome |
|---|---|---|
| 1. AIDP identity layer hardening (do FIRST, in parallel) | ~10 wk | JWT carries `org_id`, downstream services apply `require_org_member`, qa/mentor/WS endpoints gated, SSO/API-key Fernet wiring verified, cross-tenant tests added everywhere. |
| 2. PMv2 inherits AIDP's identity (JWT verification only) | ~1 wk | PMv2 verifies AIDP-minted JWTs; `tenant_id` derived from the verified `org_id` claim. `X-Tenant-ID` header deprecated. |
| 3. PMv2 data-model migration — add `tenantId` to Issue/Project/Comment/Activity/ExecutionSummary/AutoPilot* tables. SQLite → PostgreSQL. Enable RLS. | ~3 wk | Multi-tenant containment at the data layer. |
| 4. PMv2 auth gates on every write endpoint | ~2 wk | InternalAuthDep replaced with JWT-derived current_user + tenant filter. |
| 5. PMv2 subprocess sandbox | ~3-4 wk | Container or Firecracker per-tenant for Claude CLI execution. Or delegate execution to AIDP's mentor-service + agent-orchestrator (after AIDP step 1 lands). |
| 6. PMv2 cross-tenant test suite (two tenants × every endpoint) | ~1 wk | OWASP ATHZ-02 coverage. |
| 7. Per-tenant Anthropic key + quota enforcement | ~1 wk | Cost attribution + plan tiering possible. |
| 8. Port AIDP UI patterns into PMv2 — collapsible animated sidebar, 7-step wizard with draft recovery, dashboard widget grid, Radix shadcn primitives | ~2-3 wk | Frontend polish without rebuilding from zero. |
| 9. Port Studio Investigation Engine + CodeBoard + AutoPilot + Capability ribbon DECISION: stay in PMv2 (keep) | n/a | These are PMv2's best assets — keep where they are. |
| 10. Cloud deploy on Fly.io (Next.js + FastAPI + Postgres + Machines for workers + ChromaDB co-located) | ~1-2 wk | Production cloud SaaS reachable. |

**Total: ~22-24 engineer-weeks** end-to-end to ship both apps as a unified multi-tenant cloud SaaS.

### Why this beats alternatives

- **Reuses AIDP's identity work** (which is the hardest thing to build right).
- **Keeps PMv2's production-hardened differentiators** (Studio, SIE, CodeBoard, AutoPilot, Capability ribbon, useStudioStore).
- **Ports only what makes sense** (UI primitives, dashboard, wizard) — not the unenforced downstream services.
- **Avoids a "merge into one repo"** with all the migration coordination cost. PMv2 stays its own deployment; AIDP user-service becomes the identity dependency.
- **Honest about the work remaining** — both apps have real multi-tenant gaps. This plan addresses both.

### What "stop here" would mean

If Eli decides Studio dev should pause:
- PMv2 ships as a local-only tool, which it effectively is today.
- AIDP becomes the cloud SaaS pivot but still needs ~10 weeks before it's safe to expose.
- PMv2's Studio/SIE/CodeBoard work is preserved as a local power-user tool but isn't customer-facing.

This is rational ONLY if the goal shifts from "cloud SaaS combining both" to "AIDP becomes the product, PMv2 is internal".

---

## 7. Open questions for Eli

1. Confirm the goal: **single cloud SaaS** combining both apps, or **AIDP-as-SaaS + PMv2-as-internal-tool**?
2. Acceptable timeline for the ~22-24-week multi-tenant migration? Or is the goal a faster MVP at ~6-8 weeks accepting limited tenant safety in early beta?
3. Subprocess sandbox preference — (a) PMv2 keeps its own subprocess spawn behind a container per tenant, (b) PMv2 delegates execution to AIDP's mentor-service + agent-orchestrator after AIDP hardens, (c) execution feature gated off in v1 and added in v2?
4. UI patterns to port from AIDP — confirm: collapsible sidebar, 7-step wizard, dashboard widget grid, Radix shadcn primitives. Drop Visual Builder (per Eli "not building mockups on top of a heavy system")?
5. AIDP downstream services (qa/mentor/agent/git) — keep, port back to PMv2, or rip out and rely on PMv2's equivalents?

---

## 8. Pending — architecture & code-quality agents still running

Both will append to this doc when they return. The **headline recommendation does not change** based on what they're likely to find — UI/UX + multi-tenant readiness are the dominant factors and both have landed.
