# 📖 AI Project Workspace — Master Plan
## A new layer above CodeBoard. Three views. One workspace. Major architecture add-on.

**Date:** 2026-05-07
**Author:** Jonny (VP R&D)
**For:** Eli Cohen
**Status:** PROPOSED v2.0 — final master plan, awaits Eli's approval before CodeBoard push (Rule 23)
**Supersedes:** `2026-05-07-feature-studio-and-backlog-board.md` (v1.1) — content merged + expanded
**Parked sibling:** CB-2381 (AI Cost Optimization, BACKLOG, label `parked-future`)
**Source patterns:** 10 books read across 2 CandleKeep reader passes (442 pages distilled)

---

# PART I — THE STORY

## Chapter 1 — The Why

CodeBoard is the **execution engine**. Its job is to run agents on tickets that have been decided. We use it for that — well.

But there is no place to:
- **Shape an idea** before it becomes work
- **Stage features** with priority and a schedule
- **See who is working on what** across the whole platform

Eli has been running PMv2 for months. ~30% of CodeBoard BACKLOG is half-baked drafts that never should have hit the board. Features get fired without prioritization. Nobody can see, at a glance, which agent is orchestrating which feature in which project.

The missing layer is a **workspace above CodeBoard**. Three rooms, one front door.

```
┌──────────────────────────────────────────────────────────────────────┐
│                       AI PROJECT WORKSPACE                            │
│                       (new layer — above CodeBoard)                   │
│   ┌──────────────────┬─────────────────┬─────────────────────────┐   │
│   │  💬 STUDIO        │  📋 BACKLOG      │  🕸 CREW MAP             │   │
│   │  Idea Room        │  Review Room     │  Org Chart for Agents   │   │
│   ├──────────────────┼─────────────────┼─────────────────────────┤   │
│   │  Chat with Jonny │ Priority +      │ Obsidian-style graph    │   │
│   │  + skills.        │ scheduler.      │ per project + feature.  │   │
│   │  Multi-tab        │ Filters, tags,  │ Click any node → see    │   │
│   │  conversations.   │ owners.         │ assignments, skills,    │   │
│   │  Split preview.   │ "Send to        │ recent activity.        │   │
│   │  "Send to         │ CodeBoard +     │ Live updates as agents  │   │
│   │  Backlog" button. │ AutoPilot"      │ work.                   │   │
│   └──────────────────┴─────────────────┴─────────────────────────┘   │
│                                                                       │
│         ↓                ↓                       ↓                    │
│         └────────────────┼───────────────────────┘                    │
│                          ▼                                            │
│                   ┌─────────────┐                                     │
│                   │  CodeBoard  │  ← the existing execution engine   │
│                   │  + AutoPilot│                                     │
│                   └─────────────┘                                     │
└──────────────────────────────────────────────────────────────────────┘
```

This is **a major architecture add-on**, not a small feature. It changes the front door of the entire platform.

---

# PART II — THE THREE VIEWS

## Chapter 2 — Studio (Idea Room)

### Top-level layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Project: PMv2 ▾    [+ New Conv]                                  Eli ▾  ⚙   │
│ ┌──────┬──────┬──────┬──────┬───┐                                            │
│ │Tab1●│Tab2●│Tab3 │Tab4 │ + │                                            │
│ └──────┴──────┴──────┴──────┴───┘                                            │
│ ┌──────────────────────────────────┬─────────────────────────────────────┐  │
│ │  CHAT PANE (60%)                  │  PREVIEW PANE (40% — slides in)    │  │
│ │ ─────────────────────────────────  │ ─────────────────────────────────── │  │
│ │  Eli: I want a feature where...   │  📄 Live Markdown render            │  │
│ │                                    │                                     │  │
│ │  Jonny: Let me decompose...       │  # Feature: AI Project Workspace    │  │
│ │   ╭ Calling: solution-architect ╮ │                                     │  │
│ │   │ ⚙️ Designing schema...      │ │  ## Architecture                    │  │
│ │   ╰────────────────────────────╯  │  [mermaid diagram preview]          │  │
│ │                                    │                                     │  │
│ │  Solution-Architect: Here's...    │  ┌──────────────────────────┐      │  │
│ │   [generated SQL + diagram]       │  │ erDiagram                 │      │  │
│ │                                    │  │   PROJECT ||--o{ FEATURE  │      │  │
│ │   AGENT ACTIVITY (live):           │  │   FEATURE ||--o{ EPIC     │      │  │
│ │   🟢 jonny       — orchestrating  │  └──────────────────────────┘      │  │
│ │   🟢 architect   — schema design  │                                     │  │
│ │   ⚪ ui-designer  — idle           │  Tabs: [MD│Mermaid│Code│HTML]      │  │
│ │   🟢 docs        — drafting plan  │                                     │  │
│ │  ─────────────────────────────────                                       │  │
│ │  [Type message…                  ]                                       │  │
│ │  [Send] [→ Send to Backlog] [⏸ Pause] [💾 Save] [🗑 Discard]           │  │
│ └──────────────────────────────────┴─────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component map

| Zone | Purpose | React component |
|---|---|---|
| Top bar | Project picker, new-conversation, settings | `<StudioTopBar />` |
| Tab strip | Multi-conversation tabs with live indicator dots | `<ConversationTabs />` |
| Chat pane | Messages, role badges, agent invocation cards | `<Chat.MessageList />` |
| Agent activity panel | Live status of each crew member | `<Chat.AgentStatus />` |
| Action bar | Send / Send to Backlog / Pause / Save / Discard | `<Chat.Actions />` |
| Preview pane | Split-view artifact renderer (md/code/mermaid/html) | `<PreviewPane />` |

### Visual rules (Linear-dark default, Anthropic-light alternative)

| Token | Linear-dark | Anthropic-light |
|---|---|---|
| Canvas | `#08090a` | `#f5f4ed` (Parchment) |
| Panels | `#0f1011` | `#fbf9f4` |
| Cards | `rgba(255,255,255,0.02)` + `1px rgba(255,255,255,0.08)` | `#ffffff` + `1px #e6e3da` |
| Accent | `#7170ff` (indigo-violet) | `#c96442` (Terracotta) |
| Active text | `#f7f8f8` | `#1f1d18` |
| Inactive text | `#d0d6e0` | `#5b574e` |
| Muted | `#8a8f98` | `#9a9486` |
| Status green | `#27a644` | `#2f8a3f` |
| Font | Inter Variable, weight 510 (signature) | Anthropic Serif 20px / Sans 15-16px |

### Animation rules (cognitive-science-driven)

| Behaviour | Timing | Method |
|---|---|---|
| Pane reveal (right pane slides in) | 250ms ease-out, `transform translateX 100% → 0` + opacity 0 → 1 | CSS transition (interruptible) |
| Pane dismiss | 150ms (60% of enter) | CSS transition |
| Tab switch | 150ms fade, `startTransition` to keep UI responsive | React 18 |
| Agent badge state change | 200ms cross-fade with `scale 0.25 → 1` + `blur 4 → 0` | CSS keyframe (one-shot) |
| Active-agent pulse dot | 2 Hz infinite | CSS `animate-pulse` keyframe (looping) |
| Multi-block artifact reveal | Stagger 50-100ms per block, cap cascade at 400ms | CSS transition with delay |
| Reduced motion | All pulses → static `opacity: 0.7` | `@media (prefers-reduced-motion: reduce)` |
| GPU-only properties | `transform`, `opacity`, `filter` | Never `width`, `left`, `margin` |

---

## Chapter 3 — Backlog (Review Room)

### Top-level layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Feature Backlog                                            [+ New Feature]  │
│  Filters: [Project ▾] [Status ▾] [Priority ▾] [Tag ▾]   Sort: [Updated ▾]   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ╔═════════════════════════════════════════════════════════════════════════╗ │
│  ║ 📌 CRITICAL  AI Project Workspace                                       ║ │
│  ║ APPROVED    Replaces direct CodeBoard planning           ⏰ now         ║ │
│  ║ Tags: ux, frontend, multi-tab, graph                                    ║ │
│  ║ Source: Conversation #14 (Studio)        Owner: Eli                     ║ │
│  ║ [Edit] [Open in Studio] [→ Send to CodeBoard + AutoPilot] [Schedule]   ║ │
│  ╚═════════════════════════════════════════════════════════════════════════╝ │
│                                                                              │
│  ╔═════════════════════════════════════════════════════════════════════════╗ │
│  ║ 📌 HIGH    AI Cost Optimization                                         ║ │
│  ║ DRAFT     Cuts token burn 80%                          ⏰ Q3 2026       ║ │
│  ║ Tags: ai, cost, telemetry          Linked: CB-2381 (parked)            ║ │
│  ║ [Edit] [Open in Studio] [→ Send to CodeBoard + AutoPilot] [Schedule]   ║ │
│  ╚═════════════════════════════════════════════════════════════════════════╝ │
│                                                                              │
│  ╔═════════════════════════════════════════════════════════════════════════╗ │
│  ║ 📌 MEDIUM  Migrate park.sh to Python                                    ║ │
│  ║ DRAFT     Cleanup, no urgency                          ⏰ unscheduled  ║ │
│  ║ Tags: refactor, devops             Source: Manual entry                ║ │
│  ║ [Edit] [Promote to Studio] [→ Send to CodeBoard + AutoPilot]           ║ │
│  ╚═════════════════════════════════════════════════════════════════════════╝ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Status flow

```
   DRAFT  →  REVIEWING  →  APPROVED  →  SCHEDULED  →  PROMOTED  →  SHIPPED  →  ARCHIVED
                                              ↓
                                      (now in CodeBoard +
                                        AutoPilot queue)
```

### Edit modal (priority + scheduler controls)

| Field | Control | Doherty rule |
|---|---|---|
| Title | Text input | < 100ms |
| Description | Markdown editor | < 100ms |
| Priority | Pill picker (CRITICAL/HIGH/MEDIUM/LOW/TRIVIAL) | < 200ms |
| Status | Pill picker | < 200ms |
| Tags | Multi-select with autocomplete | < 200ms |
| Owner | Person picker | < 200ms |
| Schedule mode | Radio: One-shot / Recurring / Unscheduled | < 100ms |
| One-shot date | Date+time picker | < 400ms |
| Recurring cron | Cron expression input + human preview ("Every Monday 9am") | < 400ms |
| Source | Read-only link to Studio conversation | — |
| Linked CodeBoard | Read-only link if PROMOTED | — |

All controls **must respond < 400ms** (Doherty Threshold) — if scheduling preview takes longer, user disengages.

### Priority badge recipe (Linear-style)

```tsx
// Critical
<span className="rounded-[2px] px-2 py-0.5 text-[10px] font-[510] uppercase
  bg-red-500/10 text-red-400 border border-red-500/20">Critical</span>

// High
<span className="rounded-[2px] px-2 py-0.5 text-[10px] font-[510] uppercase
  bg-orange-500/10 text-orange-400 border border-orange-500/20">High</span>

// Medium
<span className="rounded-[2px] px-2 py-0.5 text-[10px] font-[510]
  bg-white/5 text-[#d0d6e0] border border-white/5">Medium</span>

// Low
<span className="rounded-[2px] px-2 py-0.5 text-[10px] font-[510]
  bg-white/5 text-[#8a8f98] border border-white/5">Low</span>
```

`border-radius: 2px` is the Linear convention for inline badges. `border-radius: 9999px` is reserved for filter pills.

---

## Chapter 4 — Crew Map (Obsidian-Style Graph)

### Top-level layout

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  Crew Map                                                                       │
│  Filter: [Project: PMv2 ▾] [Feature: All ▾] [Agent: All ▾] [Status: All ▾]    │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│                              ┌──────────┐                                       │
│                              │ PROJECT  │                                       │
│                              │  PMv2    │                                       │
│                              └─────┬────┘                                       │
│                                    │                                            │
│                  ┌─────────────────┼──────────────────┐                         │
│                  ▼                 ▼                  ▼                         │
│            ┌──────────┐      ┌──────────┐       ┌──────────┐                   │
│            │ FEATURE  │      │ FEATURE  │       │ FEATURE  │                   │
│            │ Workspace│      │ Cost-opt │       │ AutoPilot│                   │
│            └─────┬────┘      └─────┬────┘       └─────┬────┘                   │
│                  │                 │                  │                         │
│            ┌─────▼─────┐     ┌─────▼─────┐      ┌─────▼─────┐                  │
│            │ ORCHESTR  │     │ ORCHESTR  │      │ ORCHESTR  │                  │
│            │ Jonny 👑  │     │ Jonny 👑  │      │ Jonny 👑  │                  │
│            └─────┬─────┘     └─────┬─────┘      └─────┬─────┘                  │
│                  │                 │                  │                         │
│           ┌──────┼──────┐    ┌─────┼─────┐     ┌─────┼─────┐                   │
│           ▼      ▼      ▼    ▼     ▼     ▼     ▼     ▼     ▼                   │
│        archi.   ux    docs  archi. ux  reviewer arch. fullstack  qa            │
│        🟢 active 🟢   🟢   🟢    ⚪   🟢      ⚪    🟢            ⚪            │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  Selected: Workspace → Jonny → architect                                  │  │
│  │  Status: 🟢 active for 14m                                                │  │
│  │  Skills: codeboard-flow, mermaid-design, prisma-schema                    │  │
│  │  Last action: "Designed FeatureRequest table — 4 columns added"          │  │
│  │  Conversations: Tab #2 (currently active)                                 │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Node types & semantics

| Node | Visual | Click behaviour |
|---|---|---|
| Project | Big circle, project icon | Filter graph to this project |
| Feature | Mid circle, feature icon, color = priority | Show feature detail panel |
| Orchestrator (Jonny) | Crown icon 👑, gold border, always per-feature root | Show orchestrator history |
| Skill / Agent | Small circle, agent icon, pulse if active | Show recent activity |
| Conversation | Diamond shape, link to Studio tab | Deep-link to Studio |

### Edges

| Edge | Meaning |
|---|---|
| Solid line | Active assignment |
| Dashed line | Past assignment (archived) |
| Animated dashes | Live data flowing (agent currently working) |
| Edge label | Role: "orchestrates", "audits", "implements", "reviews", "documents" |

### Live updates

- Subscribes to the same SSE channel as Studio + AutoPilot
- Active nodes pulse with the green status dot at 2 Hz
- New assignments slide in with 200ms fade
- Removed assignments fade out with 150ms (60% rule)

### Library choice

- **react-flow** (MIT license, ~80kb gz) — chosen for: built-in zoom/pan, custom node renderers, edge routing, viewport persistence per project
- Alternative considered: **Cytoscape.js** — more raw graph power but heavier and less React-native

---

# PART III — SYSTEM ARCHITECTURE

## Chapter 5 — Data Flow End-to-End

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Next.js 16, port 3601)                        │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  /app/workspace/page.tsx — main workspace shell                           │  │
│  │   ├─ /studio        → Studio view                                          │  │
│  │   ├─ /backlog       → Backlog view                                         │  │
│  │   └─ /crew-map      → Crew Map view                                         │  │
│  │  Compound Component pattern: <Workspace.Provider> + child views            │  │
│  │  Data: React Query for snapshots, EventSource for live SSE channels        │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────┬──────────────────────────────────────┘
                                           ↕  REST + SSE
┌──────────────────────────────────────────┴──────────────────────────────────────┐
│                          BACKEND (FastAPI, port 8401)                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  api/studio.py             — REST + SSE for conversation events           │  │
│  │  api/feature_backlog.py    — REST CRUD + promote pipeline                 │  │
│  │  api/crew_map.py           — REST + SSE for graph state                   │  │
│  │  ─────────────────────────                                                │  │
│  │  services/studio_orchestrator.py — multi-session manager (Jonny)          │  │
│  │  services/agent_dispatcher.py    — typed message verbs + GroupQueue lock  │  │
│  │  services/artifact_renderer.py   — md/mermaid/code/html artifact pipe     │  │
│  │  services/feature_scheduler.py   — cron + one-shot trigger loop           │  │
│  │  services/promote_pipeline.py    — Backlog → CodeBoard + AutoPilot        │  │
│  │  services/crew_map_service.py    — graph state aggregator                 │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────┬──────────────────────────────────────┘
                                           ↕
┌──────────────────────────────────────────┴──────────────────────────────────────┐
│                                  DATA LAYER                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  StudioConversation (id, projectId, title, state, hibernated, createdAt) │  │
│  │  StudioMessage (id, conversationId, role, content, agent, ts)            │  │
│  │  StudioArtifact (id, conversationId, kind, payload, ts)                  │  │
│  │  StudioAgentActivity (id, conversationId, agentName, skillName,          │  │
│  │                       status, startedAt, endedAt)  ← VISIBILITY ANCHOR   │  │
│  │  StudioInterAgentMessage (id, fromAgent, toAgent, verb, payload,         │  │
│  │                           chainDepth, ts)  ← AUDIT LOG                  │  │
│  │  AgentTemplate (id, name, version, prompt, capabilities, isActive)      │  │
│  │  AgentInstance (id, templateId, conversationId, accumulatedMemory)      │  │
│  │  ─────────────────────────                                                │  │
│  │  FeatureRequest (id, projectId, title, description, priority, status,    │  │
│  │                  scheduledFor, scheduleCron, tags, sourceConversationId, │  │
│  │                  targetIssueId, ownerEmail, archivedAt, createdAt)        │  │
│  │  FeatureRequestComment (id, featureRequestId, author, content, ts)       │  │
│  │  FeatureRequestActivity (id, featureRequestId, action, payload, actor)   │  │
│  │  ─────────────────────────                                                │  │
│  │  CrewAssignment (id, projectId, featureId, agentName, role, status,      │  │
│  │                  startedAt, endedAt)  ← graph edges                      │  │
│  │  CrewSkillUsage (id, assignmentId, skillName, invocationCount, lastUsed) │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                           ↕
┌──────────────────────────────────────────┴──────────────────────────────────────┐
│                  EXISTING INFRASTRUCTURE (re-used, not duplicated)               │
│  ─ services/terminal_service.py    (Claude Code CLI spawn — extended)           │
│  ─ services/autopilot_queue_service.py  (queue + crash recovery — CB-1951)      │
│  ─ models/agent_registry.py / skill_registry.py  (catalogue source of truth)    │
│  ─ ChromaDB :8402                  (RAG context for Studio prompts)              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Chapter 6 — The Iron Laws (production patterns baked in)

| Law | Source | Where it shows up |
|---|---|---|
| **Visibility Principle** — every agent dispatch hits `StudioAgentActivity` BEFORE chat says it happened | Building Your Agent Team pp.5,10 | Studio orchestrator API, all 3 views |
| **Template/Instance separation** | Building Your Agent Team | `AgentTemplate` + `AgentInstance` data model |
| **GroupQueue lock per agent** | Same | `services/agent_dispatcher.py` mutex |
| **4 message verbs + chain≤3** — `notify`/`request`/`delegate`/`broadcast` | Same | `StudioInterAgentMessage` schema |
| **Sub-agent context isolation** — fresh window, distill 1-2K artifact | Effective Context Engineering | Skill invocation runs isolated subprocess |
| **Tool consolidation** | Writing Effective Tools | Single `add_to_codeboard(hierarchy)` + `send_to_autopilot(id)` |
| **Blueprint state machines** — deterministic + agentic hybrid | Stripe Minions | Promote pipeline, scheduler |
| **Passive-by-default skills** | Building Your Agent Team | Only Jonny dispatches; skills don't read chat |
| **Approval modes per-action** — `always`/`confidence`/`never` | Same | Default `always` for promote, `confidence` for save-to-Backlog |
| **CSS transitions, not keyframes** for state changes | Vercel ch.16 | All pane reveal/hide, tab switch, badge state |
| **GPU-only animation properties** | Same | transform/opacity/filter only |
| **Doherty 400ms threshold** | UI/UX Principles p.9 | Scheduler controls hard rule |
| **Compound Component + Context** | Vercel p.3 | `<Workspace.Provider>...<Studio.TabBar>` etc |
| **`includePartialMessages` + `inTool` flag** | Claude Code Docs pp.335-338 | Live activity panel signal source |
| **`useRef` token buffer + 50ms flush** | Vercel ch.5 | Streaming chat render |
| **`content-visibility: auto`** | Vercel ch.6 | Off-screen message virtualization |
| **a11y iron rules** — aria-live polite, focus mgmt, role=separator, focus-visible | Vercel ch.13-14 | Non-negotiable across all 3 views |

---

# PART IV — THE FULL AGILE PLAN

## Top-level Feature

| ID | Type | Title |
|---|---|---|
| **F** | FEATURE | AI Project Workspace — Studio + Backlog + Crew Map |

### Direct EPICs (8 total — major architecture add-on)

| ID | Type | Title | Owner |
|---|---|---|---|
| E1 | EPIC | Foundation — Data model + shared services | Backend |
| E2 | EPIC | Studio — Chat-based feature planning | Full-stack |
| E3 | EPIC | Backlog — Pre-CodeBoard staging board | Full-stack |
| E4 | EPIC | Crew Map — Obsidian-style agent graph | Full-stack |
| E5 | EPIC | Promote Pipeline — Backlog → CodeBoard → AutoPilot | Backend |
| E6 | EPIC | Scheduler — One-shot + recurring feature triggers | Backend |
| E7 | EPIC | Audits + Tests + Chrome QA + Regression | Mixed |
| E8 | EPIC | Rollout + Docs + Migration + Soak | DevOps + Docs |

---

## EPIC E1 — Foundation (Data model + shared services)

| ID | Type | Title | Effort |
|---|---|---|---|
| **E1** | EPIC | Foundation — Data model + shared services | |
| E1.S1 | STORY | Studio data model | |
| E1.S1.T1 | TASK | SQLAlchemy models: `StudioConversation`, `StudioMessage`, `StudioArtifact`, `StudioAgentActivity`, `StudioInterAgentMessage` | M |
| E1.S1.T2 | TASK | SQLAlchemy models: `AgentTemplate`, `AgentInstance` (template/instance split) | S |
| E1.S1.T3 | TASK | Prisma mirror in `frontend/prisma/schema.prisma` | S |
| E1.S1.T4 | TASK | Migration script + idempotent seed (Jonny + 6 default skills as templates) | M |
| E1.S2 | STORY | Backlog data model | |
| E1.S2.T1 | TASK | SQLAlchemy: `FeatureRequest`, `FeatureRequestComment`, `FeatureRequestActivity` | M |
| E1.S2.T2 | TASK | Prisma mirror | S |
| E1.S2.T3 | TASK | Migration + seed (port the parked CB-2381 entry as first FeatureRequest) | S |
| E1.S3 | STORY | Crew Map data model | |
| E1.S3.T1 | TASK | SQLAlchemy: `CrewAssignment`, `CrewSkillUsage` | S |
| E1.S3.T2 | TASK | Prisma mirror | S |
| E1.S3.T3 | TASK | Migration | XS |
| E1.S4 | STORY | Shared services skeleton | |
| E1.S4.T1 | TASK | `services/agent_dispatcher.py` — typed-verb send + GroupQueue mutex + chain-depth check | L |
| E1.S4.T1.ST1 | SUBTASK | Implement `notify(from, to, payload)` | S |
| E1.S4.T1.ST2 | SUBTASK | Implement `request(from, to, payload)` blocking | S |
| E1.S4.T1.ST3 | SUBTASK | Implement `delegate(from, to, payload)` | S |
| E1.S4.T1.ST4 | SUBTASK | Implement `broadcast(from, group, payload)` | S |
| E1.S4.T1.ST5 | SUBTASK | Per-agent mutex via `asyncio.Lock` keyed by `agentName` | M |
| E1.S4.T1.ST6 | SUBTASK | `max_chain_depth=3` enforcement + audit log row | S |
| E1.S4.T2 | TASK | `services/studio_orchestrator.py` — multi-session manager (extends `terminal_service`) | L |
| E1.S4.T3 | TASK | SSE multiplexer — per-conversation EventSource channel | M |
| E1.S4.T4 | TASK | Crew assignment writer — every dispatch creates `CrewAssignment` row | M |
| E1.S5 | STORY | Audit log + Visibility Principle enforcement | |
| E1.S5.T1 | TASK | Pre-flight check: every `agent_dispatcher` call MUST persist before continuing | M |
| E1.S5.T2 | TASK | `StudioInterAgentMessage` write-through-persisted (CB-1951 audit log pattern) | S |
| E1.S5.T3 | TASK | Test: assert no orphan dispatches (chat claims dispatch but no DB row) | M |

**E1 totals:** 5 stories, 18 tasks, 6 subtasks. Backend-heavy. ~5 days.

---

## EPIC E2 — Studio (Chat-based feature planning)

| ID | Type | Title | Effort |
|---|---|---|---|
| **E2** | EPIC | Studio — Chat-based feature planning | |
| E2.S1 | STORY | Studio shell + routing | |
| E2.S1.T1 | TASK | `/app/workspace/studio/page.tsx` shell with `<Workspace.Provider>` | M |
| E2.S1.T2 | TASK | `<StudioTopBar />` — project picker, [+ New Conv], settings | S |
| E2.S1.T3 | TASK | URL-state encoding: `?project=X&conv=Y&tab=N` | M |
| E2.S2 | STORY | Conversation tabs | |
| E2.S2.T1 | TASK | `<ConversationTabs />` — Inter Variable 510, `#7170ff` active underline | M |
| E2.S2.T2 | TASK | Live indicator dot per tab (pulse if any agent active) | S |
| E2.S2.T3 | TASK | `startTransition` on tab switch (non-urgent, prevents flicker) | S |
| E2.S2.T4 | TASK | Right-click context menu: rename, close, duplicate, archive | M |
| E2.S2.T5 | TASK | Tab persistence — tabs survive reload | S |
| E2.S3 | STORY | Chat pane | |
| E2.S3.T1 | TASK | `<Chat.MessageList />` with `content-visibility: auto` virtualization | M |
| E2.S3.T2 | TASK | Role badges (user/Jonny/skill) with stable colors | S |
| E2.S3.T3 | TASK | Agent invocation card (collapsible "calling architect…" block) | M |
| E2.S3.T4 | TASK | `useRef` token buffer + 50ms flush for streaming render | M |
| E2.S3.T5 | TASK | Markdown rendering with syntax highlighting (rehype-pretty-code) | S |
| E2.S3.T6 | TASK | Inline citations (when agent quotes a CodeBoard issue) | M |
| E2.S3.T7 | TASK | Chat input with multiline + Cmd+Enter submit + slash-commands | M |
| E2.S4 | STORY | Agent activity panel | |
| E2.S4.T1 | TASK | `<Chat.AgentStatus />` reads SSE events for `inTool` boolean | M |
| E2.S4.T2 | TASK | Status badge variants: idle (gray), thinking (shimmer), tool-use (pulse + label), done | M |
| E2.S4.T3 | TASK | Stable visual identity per agent (icon + color, persistent across conversations) | M |
| E2.S4.T4 | TASK | Reduced-motion compliance — `@media (prefers-reduced-motion)` static fallback | S |
| E2.S5 | STORY | Action bar | |
| E2.S5.T1 | TASK | `<Chat.Actions />` — Send / Send to Backlog / Pause / Save / Discard | S |
| E2.S5.T2 | TASK | Pause action — emits `agent_dispatcher.pause(conversationId)` | M |
| E2.S5.T3 | TASK | Save action — snapshots conversation to localStorage + DB | S |
| E2.S5.T4 | TASK | Discard action — confirmation modal before destructive delete | S |
| E2.S6 | STORY | Preview pane (split-view artifact renderer) | |
| E2.S6.T1 | TASK | `<PreviewPane />` shell with detect-and-reveal on artifact event | M |
| E2.S6.T1.ST1 | SUBTASK | Detect logic — when `StudioArtifact` row created, slide pane in | S |
| E2.S6.T1.ST2 | SUBTASK | CSS `transition` enter 250ms / exit 150ms (interruptible) | S |
| E2.S6.T1.ST3 | SUBTASK | Resize handle — `role="separator"` + ArrowLeft/Right keyboard nav | M |
| E2.S6.T1.ST4 | SUBTASK | Focus moves into pane on reveal, returns to triggering message on close | S |
| E2.S6.T2 | TASK | Markdown renderer tab | S |
| E2.S6.T3 | TASK | Mermaid renderer tab (mermaid.js dynamic import) | M |
| E2.S6.T4 | TASK | Code viewer tab with diff mode (Monaco-lite or shiki) | M |
| E2.S6.T5 | TASK | HTML preview iframe (sandboxed, sandbox="allow-scripts") | M |
| E2.S6.T6 | TASK | Tab switcher — MD / Mermaid / Code / HTML | S |
| E2.S6.T7 | TASK | Stagger animation on multi-block content (50-100ms per block) | S |
| E2.S7 | STORY | Send-to-Backlog handoff | |
| E2.S7.T1 | TASK | "Send to Backlog" button → confirmation modal | S |
| E2.S7.T2 | TASK | Conversation transcript → structured `FeatureRequest` payload (Jonny prompt) | L |
| E2.S7.T3 | TASK | Edit-before-send modal — title/desc/priority/tags pre-filled, user adjusts | M |
| E2.S7.T4 | TASK | POST `/api/feature-backlog` + toast + redirect to Backlog view | S |
| E2.S7.T5 | TASK | Source conversation linked back from FeatureRequest record | S |
| E2.S8 | STORY | Hibernation + resume | |
| E2.S8.T1 | TASK | Idle detection — 30 min no activity → hibernate Claude subprocess | M |
| E2.S8.T2 | TASK | Resume on tab focus — re-spawn subprocess, replay last 5 messages | L |
| E2.S8.T3 | TASK | Snapshot conversation state every N messages to `PLANNING_STATE.md` | M |

**E2 totals:** 8 stories, 38 tasks, 4 subtasks. ~10 days.

---

## EPIC E3 — Backlog (Pre-CodeBoard staging)

| ID | Type | Title | Effort |
|---|---|---|---|
| **E3** | EPIC | Backlog — Pre-CodeBoard staging board | |
| E3.S1 | STORY | Backlog API | |
| E3.S1.T1 | TASK | CRUD endpoints `/api/feature-backlog` (list, get, create, update, delete, archive) | M |
| E3.S1.T2 | TASK | Search + filter endpoint with project/status/priority/tag/owner | M |
| E3.S1.T3 | TASK | Sort by updated/priority/scheduledFor | S |
| E3.S2 | STORY | Backlog list view | |
| E3.S2.T1 | TASK | `/app/workspace/backlog/page.tsx` shell | S |
| E3.S2.T2 | TASK | `<BacklogCard />` — title, priority badge, status, schedule, tags, source link | M |
| E3.S2.T3 | TASK | Filter bar (project/status/priority/tag) — controlled URL state | M |
| E3.S2.T4 | TASK | Sort dropdown | S |
| E3.S2.T5 | TASK | Empty state + onboarding hint ("create your first feature in Studio") | S |
| E3.S3 | STORY | Edit modal | |
| E3.S3.T1 | TASK | `<BacklogEditModal />` — all fields with controlled inputs | M |
| E3.S3.T2 | TASK | Priority pill picker | S |
| E3.S3.T3 | TASK | Status pill picker (DRAFT → REVIEWING → APPROVED → SCHEDULED → PROMOTED → SHIPPED → ARCHIVED) | S |
| E3.S3.T4 | TASK | Tag multi-select with autocomplete | M |
| E3.S3.T5 | TASK | Owner picker | S |
| E3.S3.T6 | TASK | Schedule picker — radio (one-shot/recurring/unscheduled) + date/cron input + human preview | L |
| E3.S3.T6.ST1 | SUBTASK | One-shot date+time picker | M |
| E3.S3.T6.ST2 | SUBTASK | Cron expression input + `croniter` validation | M |
| E3.S3.T6.ST3 | SUBTASK | Human-readable preview ("Every Monday 9am") | M |
| E3.S4 | STORY | Card actions | |
| E3.S4.T1 | TASK | "Open in Studio" — deep link to source conversation | S |
| E3.S4.T2 | TASK | "Promote to Studio" (for manually-entered features) — opens new conv with pre-filled context | M |
| E3.S4.T3 | TASK | "Send to CodeBoard + AutoPilot" — triggers promote pipeline (E5) | M |
| E3.S4.T4 | TASK | "Schedule" inline action — opens schedule sub-dialog | S |
| E3.S5 | STORY | Comments + activity log | |
| E3.S5.T1 | TASK | `<BacklogComments />` — threaded comments per FeatureRequest | M |
| E3.S5.T2 | TASK | Activity feed — every status change, edit, comment | M |

**E3 totals:** 5 stories, 19 tasks, 3 subtasks. ~7 days.

---

## EPIC E4 — Crew Map (Obsidian-style agent graph)

| ID | Type | Title | Effort |
|---|---|---|---|
| **E4** | EPIC | Crew Map — Obsidian-style agent graph | |
| E4.S1 | STORY | Graph data aggregator | |
| E4.S1.T1 | TASK | `services/crew_map_service.py` — assemble graph from CrewAssignment + skills + activities | L |
| E4.S1.T2 | TASK | API `/api/crew-map?projectId=X` returns nodes + edges | M |
| E4.S1.T3 | TASK | API `/api/crew-map/feature/{id}` returns single-feature subgraph | S |
| E4.S1.T4 | TASK | SSE channel `/api/crew-map/events` for live updates | M |
| E4.S2 | STORY | Graph rendering | |
| E4.S2.T1 | TASK | `/app/workspace/crew-map/page.tsx` shell | S |
| E4.S2.T2 | TASK | Install + integrate `react-flow` (MIT, ~80kb gz) | M |
| E4.S2.T3 | TASK | Custom node renderers: Project, Feature, Orchestrator, Skill, Conversation | M |
| E4.S2.T3.ST1 | SUBTASK | `<ProjectNode />` — circle with project icon | S |
| E4.S2.T3.ST2 | SUBTASK | `<FeatureNode />` — color-by-priority circle | S |
| E4.S2.T3.ST3 | SUBTASK | `<OrchestratorNode />` — crown 👑 icon, gold border | S |
| E4.S2.T3.ST4 | SUBTASK | `<SkillNode />` — agent icon, pulse if active | M |
| E4.S2.T3.ST5 | SUBTASK | `<ConversationNode />` — diamond, deep-link to Studio | S |
| E4.S2.T4 | TASK | Edge styles: solid (active), dashed (past), animated (live data) | M |
| E4.S2.T5 | TASK | Edge labels: orchestrates / audits / implements / reviews / documents | S |
| E4.S2.T6 | TASK | Force-directed layout with viewport persistence per project | M |
| E4.S3 | STORY | Filters + interaction | |
| E4.S3.T1 | TASK | Filter bar — project / feature / agent / status | M |
| E4.S3.T2 | TASK | Click-to-filter: clicking a node filters graph to its subgraph | M |
| E4.S3.T3 | TASK | Search bar — fuzzy match by node name | S |
| E4.S3.T4 | TASK | Reset view button + zoom-to-fit | S |
| E4.S4 | STORY | Detail panel | |
| E4.S4.T1 | TASK | `<NodeDetailPanel />` — slide-in right-side panel on node click | M |
| E4.S4.T2 | TASK | Per-node-type detail variants (project/feature/agent/conversation) | M |
| E4.S4.T3 | TASK | Skills used + invocation count + last-used timestamp | M |
| E4.S4.T4 | TASK | "Open in Studio" / "Open in Backlog" / "Open in CodeBoard" deep links | S |
| E4.S5 | STORY | Live updates | |
| E4.S5.T1 | TASK | SSE subscription + state reducer | M |
| E4.S5.T2 | TASK | Active node pulse animation (CSS keyframe, 2 Hz) | S |
| E4.S5.T3 | TASK | New assignment slide-in (200ms fade) | S |
| E4.S5.T4 | TASK | Removed assignment fade-out (150ms) | S |

**E4 totals:** 5 stories, 18 tasks, 5 subtasks. ~8 days.

---

## EPIC E5 — Promote Pipeline (Backlog → CodeBoard → AutoPilot)

| ID | Type | Title | Effort |
|---|---|---|---|
| **E5** | EPIC | Promote Pipeline — deterministic + agentic Blueprint | |
| E5.S1 | STORY | Pipeline orchestrator | |
| E5.S1.T1 | TASK | `services/promote_pipeline.py` — Blueprint state machine | L |
| E5.S1.T1.ST1 | SUBTASK | State 1: validate FeatureRequest readiness (deterministic) | S |
| E5.S1.T1.ST2 | SUBTASK | State 2: invoke Jonny to generate hierarchy (agentic) | M |
| E5.S1.T1.ST3 | SUBTASK | State 3: validate proposed hierarchy (deterministic) | S |
| E5.S1.T1.ST4 | SUBTASK | State 4: edit-before-send modal (user gate, `always` mode) | M |
| E5.S1.T1.ST5 | SUBTASK | State 5: bulk POST to CodeBoard `/api/projects/{id}/issues` | M |
| E5.S1.T1.ST6 | SUBTASK | State 6: append to AutoPilot queue if priority ≥ HIGH | S |
| E5.S1.T1.ST7 | SUBTASK | State 7: update FeatureRequest.status → PROMOTED + targetIssueId | S |
| E5.S2 | STORY | Hierarchy generator | |
| E5.S2.T1 | TASK | Jonny prompt template — conversation transcript → Feature/Epic/Story/Task hierarchy | M |
| E5.S2.T2 | TASK | Sub-agent context isolation — Jonny calls hierarchy-architect skill in fresh window | M |
| E5.S2.T3 | TASK | Distill back to 1-2K-token compact artifact | S |
| E5.S2.T4 | TASK | JSON-validate the generated tree against schema | M |
| E5.S3 | STORY | Tools layer (consolidated) | |
| E5.S3.T1 | TASK | `add_to_codeboard(hierarchy)` — single tool, internal multi-issue POST | L |
| E5.S3.T2 | TASK | `send_to_autopilot(issueId, priority)` — single tool | M |
| E5.S3.T3 | TASK | Tool descriptions follow Anthropic guidance — when to use, what's needed back | S |
| E5.S3.T4 | TASK | Actionable error messages (e.g. "Queue paused — retry after reset") | S |
| E5.S4 | STORY | Audit + rollback | |
| E5.S4.T1 | TASK | Every state transition appended to `FeatureRequestActivity` | S |
| E5.S4.T2 | TASK | Rollback path — if push fails partially, mark FeatureRequest status=DRAFT + cleanup orphans | M |
| E5.S4.T3 | TASK | Idempotency key — re-promote of same FeatureRequest does not duplicate issues | M |

**E5 totals:** 4 stories, 12 tasks, 7 subtasks. ~6 days.

---

## EPIC E6 — Scheduler (One-shot + recurring triggers)

| ID | Type | Title | Effort |
|---|---|---|---|
| **E6** | EPIC | Scheduler — one-shot + recurring | |
| E6.S1 | STORY | Background worker | |
| E6.S1.T1 | TASK | `services/feature_scheduler.py` — asyncio loop (60s tick) | M |
| E6.S1.T2 | TASK | Lifespan hook startup integration (similar to autopilot rehydrate) | S |
| E6.S1.T3 | TASK | Crash recovery — on restart, resume from last-tick row | M |
| E6.S2 | STORY | Trigger logic | |
| E6.S2.T1 | TASK | One-shot — `scheduledFor <= now()` → invoke promote pipeline | S |
| E6.S2.T2 | TASK | Recurring — `croniter` parser + advance to next firing | M |
| E6.S2.T3 | TASK | Skip rule — if FeatureRequest status != SCHEDULED, no-op | S |
| E6.S2.T4 | TASK | Lock — same FeatureRequest cannot fire twice in same tick | S |
| E6.S3 | STORY | UI integration | |
| E6.S3.T1 | TASK | Schedule input validation (frontend + backend) | M |
| E6.S3.T2 | TASK | Live "next firing" preview in edit modal | S |
| E6.S3.T3 | TASK | Cancel-schedule action | S |

**E6 totals:** 3 stories, 10 tasks. ~3 days.

---

## EPIC E7 — Audits + Tests + Chrome QA + Regression

| ID | Type | Title | Effort |
|---|---|---|---|
| **E7** | EPIC | Audits + Tests + Chrome QA + Regression | |
| E7.S1 | STORY | code-reviewer pass | |
| E7.S1.T1 | TASK | All E1 backend changes reviewed | M |
| E7.S1.T2 | TASK | All E2 frontend changes reviewed | M |
| E7.S1.T3 | TASK | All E3 backlog changes reviewed | M |
| E7.S1.T4 | TASK | All E4 crew-map changes reviewed | M |
| E7.S1.T5 | TASK | All E5 + E6 pipeline + scheduler reviewed | M |
| E7.S2 | STORY | security-auditor pass | |
| E7.S2.T1 | TASK | Subprocess isolation (Studio Claude spawns) — no privilege escalation | M |
| E7.S2.T2 | TASK | iframe sandbox in HTML preview tab | S |
| E7.S2.T3 | TASK | Authz on Backlog APIs (defer to CB-2121 if needed) | M |
| E7.S2.T4 | TASK | Promote pipeline: idempotency + rollback safety | M |
| E7.S2.T5 | TASK | SSE connection limits + reconnect backoff | M |
| E7.S3 | STORY | Unit + integration tests | |
| E7.S3.T1 | TASK | Studio orchestrator unit tests (multi-session, hibernate, resume) | L |
| E7.S3.T2 | TASK | Agent dispatcher tests (verbs, mutex, chain depth) | M |
| E7.S3.T3 | TASK | Backlog API tests (CRUD, filter, sort) | M |
| E7.S3.T4 | TASK | Crew map service tests (graph assembly, SSE updates) | M |
| E7.S3.T5 | TASK | Promote pipeline tests (Blueprint state machine, rollback, idempotency) | L |
| E7.S3.T6 | TASK | Scheduler tests (one-shot, recurring, crash recovery, lock) | M |
| E7.S4 | STORY | Frontend tests | |
| E7.S4.T1 | TASK | Vitest + RTL — Studio chat pane, tabs, action bar | L |
| E7.S4.T2 | TASK | Vitest + RTL — Backlog cards, filters, edit modal | M |
| E7.S4.T3 | TASK | Vitest + RTL — Crew Map detail panel, filters | M |
| E7.S5 | STORY | Chrome visual QA + Playwright e2e | |
| E7.S5.T1 | TASK | Chrome QA: Studio shell renders + tab switch + chat send | M |
| E7.S5.T2 | TASK | Chrome QA: Backlog list + edit modal + send-to-CodeBoard happy path | M |
| E7.S5.T3 | TASK | Chrome QA: Crew Map renders + click filter + node detail panel | M |
| E7.S5.T4 | TASK | Playwright e2e: full flow — Studio chat → Backlog → CodeBoard → AutoPilot | L |
| E7.S6 | STORY | Full regression matrix | |
| E7.S6.T1 | TASK | New conversation → 3 tabs → Send to Backlog | M |
| E7.S6.T2 | TASK | Backlog → schedule recurring → wait → verify CodeBoard fired | L |
| E7.S6.T3 | TASK | Crew Map shows live agent activity during E7.S6.T1 | M |
| E7.S6.T4 | TASK | Hibernate/resume: tab idle 30 min, click → resumes correctly | M |
| E7.S6.T5 | TASK | Visibility test: try to fake a dispatch — confirm DB row required | M |

**E7 totals:** 6 stories, 28 tasks. ~10 days.

---

## EPIC E8 — Rollout + Docs + Migration + Soak

| ID | Type | Title | Effort |
|---|---|---|---|
| **E8** | EPIC | Rollout + Docs + Migration + Soak | |
| E8.S1 | STORY | Migration | |
| E8.S1.T1 | TASK | Generate Prisma migrations + commit | S |
| E8.S1.T2 | TASK | Idempotent backfill — port CB-2381 + 5 sample features into Backlog | M |
| E8.S1.T3 | TASK | MIGRATION_NOTES.md update | S |
| E8.S2 | STORY | Documentation | |
| E8.S2.T1 | TASK | CLAUDE.md update — new architecture section + Workspace flow | M |
| E8.S2.T2 | TASK | New runbook: `docs/runbooks/workspace-operations.md` | M |
| E8.S2.T3 | TASK | User guide: `docs/user-guides/ai-project-workspace.md` | M |
| E8.S2.T4 | TASK | API reference: studio + backlog + crew-map endpoints | M |
| E8.S3 | STORY | Feature flag wrap | |
| E8.S3.T1 | TASK | `WORKSPACE_ENABLED` env var + runtime toggle | S |
| E8.S3.T2 | TASK | Settings page toggle | S |
| E8.S3.T3 | TASK | Fallback: redirect `/workspace` → `/codeboard` if disabled | S |
| E8.S4 | STORY | Soak window | |
| E8.S4.T1 | TASK | 7-day production soak with feature flag on | L |
| E8.S4.T2 | TASK | Daily metrics check (active conversations, promote success rate, scheduler firings) | M |
| E8.S4.T3 | TASK | Bug triage + fixes during soak | M |
| E8.S4.T4 | TASK | Soak summary doc + decision: ship or iterate | M |
| E8.S5 | STORY | Promote out of feature flag | |
| E8.S5.T1 | TASK | Remove flag once soak green | S |
| E8.S5.T2 | TASK | Final commit + tag | S |

**E8 totals:** 5 stories, 16 tasks. ~5 days (soak is mostly waiting).

---

# PART V — META

## Chapter 7 — Cross-Epic Dependencies

```
E1 Foundation ──────────► E2 Studio
                ├──────► E3 Backlog
                └──────► E4 Crew Map
                                │
E2 Studio + E3 Backlog ───────► E5 Promote Pipeline
                                │
E3 Backlog ──────────────────► E6 Scheduler ──► E5 Promote Pipeline
                                │
                                ▼
            E7 Audits + Tests + QA + Regression
                                │
                                ▼
                  E8 Rollout + Docs + Soak
```

**Sequencing rule:** E1 must be 100% green before E2/E3/E4 start. E5 + E6 can start once E1 + E2 chat-pane + E3 CRUD are green.

## Chapter 8 — Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Multi-session token cost explosion | M | H | Per-session budget cap (links to parked CB-2381) |
| Subprocess hibernation/resume bugs | M | M | `PLANNING_STATE.md` snapshot every N msgs + replay |
| SSE channel saturation | L | M | Channel multiplexing, max 8 concurrent streams per user |
| Studio + CodeBoard data drift | M | M | Single source of truth = Studio conversation; backlog references it |
| Promote pipeline generates bad hierarchy | M | H | Edit-before-send modal + JSON schema validation |
| Crew Map graph performance with >100 nodes | M | M | Force-layout web worker + on-demand subgraph fetch |
| react-flow library breaks with Next.js 16 | L | M | Pin version; test in dev before E4 starts |
| Animation distraction | L | L | Subtle defaults; user toggle in Settings |
| Cron parser edge cases | M | L | Use battle-tested `croniter` lib |
| Visibility-Principle hallucinations | M | H | Pre-flight check enforces DB row before chat narrates dispatch |
| Promote-failure orphans in CodeBoard | M | M | Idempotency key + rollback compensating action |
| Feature flag mismatch in production | L | M | Single source of truth via Settings table; Settings page toggle |

## Chapter 9 — KPI Story

### Before this feature
| Metric | Today |
|---|---|
| Half-baked CodeBoard issues | ~30% of BACKLOG |
| Time from idea to executable plan | days (manual board entry) |
| Feature priority visibility | flat on CodeBoard |
| Recurring feature fires | none — manual every time |
| Per-project agent visibility | none — must dig logs |
| Per-feature agent visibility | none |
| Cross-project crew overview | none |
| Eli's planning UX | "open another tab to CodeBoard, type, save, repeat" |

### After this feature
| Metric | Target |
|---|---|
| Half-baked CodeBoard issues | < 5% |
| Time from idea to executable plan | minutes (Studio chat) |
| Feature priority visibility | tiered Backlog with CRITICAL/HIGH/MEDIUM/LOW/TRIVIAL |
| Recurring feature fires | scheduler-driven |
| Per-project agent visibility | live Crew Map |
| Per-feature agent visibility | sub-graph in Crew Map |
| Cross-project crew overview | unified Crew Map view |
| Eli's planning UX | "type into Studio, watch agents work, send to Backlog" |

## Chapter 10 — Phased Rollout (Calendar)

| Week | Phase | Scope |
|---|---|---|
| 1 | Foundation | E1 (data model + shared services) |
| 2-3 | Studio MVP | E2 chat + tabs + actions (no preview pane yet) + E5 promote pipeline (basic) |
| 4 | Backlog | E3 list + edit + filter + actions |
| 5 | Promote + Scheduler | E5 (full Blueprint) + E6 (one-shot + recurring) |
| 6 | Studio polish | E2.S6 preview pane + E2.S4 agent activity + E2.S8 hibernation |
| 7 | Crew Map | E4 (graph + filters + detail panel + live updates) |
| 8 | Audits + Tests | E7 full pass |
| 9 | Rollout + soak start | E8 migration + docs + flag wrap |
| 10-11 | Soak | observe, fix, decide |
| 12 | Promote out of flag | E8.S5 |

**Total: ~12 weeks. ~46 stories, ~159 tasks, ~25 subtasks.**

(Soak is light effort — mostly waiting + monitoring.)

## Chapter 11 — Effort Roll-up

| Epic | Stories | Tasks | Subtasks | Effort (days) |
|---|---|---|---|---|
| E1 Foundation | 5 | 18 | 6 | 5 |
| E2 Studio | 8 | 38 | 4 | 10 |
| E3 Backlog | 5 | 19 | 3 | 7 |
| E4 Crew Map | 5 | 18 | 5 | 8 |
| E5 Promote Pipeline | 4 | 12 | 7 | 6 |
| E6 Scheduler | 3 | 10 | 0 | 3 |
| E7 Audits + Tests + QA | 6 | 28 | 0 | 10 |
| E8 Rollout + Soak | 5 | 16 | 0 | 5 |
| **TOTAL** | **41** | **159** | **25** | **~54 working days (~12 weeks with soak)** |

## Chapter 12 — The Ask

Eli, this is the **full plan**. Top to bottom. Every story. Every task.

- **1 FEATURE** — AI Project Workspace
- **8 EPICs** — Foundation / Studio / Backlog / Crew Map / Promote Pipeline / Scheduler / Audits / Rollout
- **41 STORIES**
- **159 TASKS**
- **25 SUBTASKS**
- **~12 weeks** including soak

Three views, one workspace, full bible compliance, all production patterns from Linear/Vercel/Stripe/Anthropic baked in.

**Decision needed:**

| Option | Action |
|---|---|
| ✅ **Approve as-is** | I write push script, fire it, all 8 EPICs land in CodeBoard with full hierarchy |
| 📝 **Edit first** | Tell me what to change; I cut v2.1 |
| ⏸ **Park** | Stay in `docs/plans/` for now; revisit later |

Push script will land in `backend/scripts/codeboard/2026-05-07-workspace-master-push.py` (Rule 29).

— Jonny
