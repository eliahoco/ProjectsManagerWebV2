# 📖 The Story of Feature Studio + Feature Backlog Board
## Two Features That Decide Where the Work Begins

**Date:** 2026-05-07
**Author:** Jonny (VP R&D)
**For:** Eli Cohen
**Status:** PROPOSED v1.1 — awaits Eli's approval before CodeBoard push (Rule 23)
**CandleKeep:** 10 books read across 2 reader passes — citations inline + at end

---

## Chapter 1 — The Crooked Workflow Today

Eli has an idea. He opens CodeBoard. He clicks "Create Issue". He types a title. He picks Feature/Epic/Story. He clicks save. And another. And another. Now the idea is **live** — visible to every agent, every autopilot run, every metric — before it has been shaped, debated, or even fully written down.

Half the issues in BACKLOG are **half-baked drafts** that should never have hit the board.

The CodeBoard is the **execution layer**. Its job is to track work that has already been decided. Right now we're using it as the **planning layer** too — and the two layers fight each other.

**There are two missing rooms in the house:**

```
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│  IDEA STAGE          │    │  REVIEW STAGE        │    │  EXECUTION STAGE     │
│  (where Eli thinks)  │ →  │  (where Eli decides) │ →  │  (where agents work) │
├──────────────────────┤    ├──────────────────────┤    ├──────────────────────┤
│  ❓ NO ROOM           │    │  ❓ NO ROOM           │    │  ✅ CodeBoard         │
│  TODAY               │    │  TODAY               │    │                      │
└──────────────────────┘    └──────────────────────┘    └──────────────────────┘
        ↓                            ↓                            ↓
   We need this              We need this              We have this
   = Feature Studio         = Feature Backlog         = CodeBoard
```

Eli wants to build the two missing rooms. This plan is how.

---

## Chapter 2 — The Two New Rooms

### 🎨 Feature Studio — the Idea Room
Where Eli, Jonny, and the agent crew **shape** a feature in conversation. Multiple parallel conversations across multiple projects. Live visibility into who's thinking and what they're producing. Split view when artifacts appear. One button to graduate the conversation into a Feature Backlog entry.

### 📋 Feature Backlog Board — the Review Room
A staging area between Idea and CodeBoard. Every feature shaped in Studio lands here as a draft. Eli prioritizes, schedules, refines, drops, or promotes. When a feature is ready, one action sends it to CodeBoard + AutoPilot — and it disappears from Backlog into the execution stream.

---

## Chapter 3 — Feature Studio Architecture

### Top-level layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Feature Studio                                                              │
│  ┌────────────────────┐                                              ┌───┐   │
│  │ Project: PMv2 ▾    │  [+ New Conversation]              Eli  ▾   │ ⚙ │   │
│  └────────────────────┘                                              └───┘   │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐                   │
│  │ Tab 1: ● │ Tab 2: ● │ Tab 3:   │ Tab 4:   │  +       │                   │
│  │ Backlog  │ Cost-opt │ Chat UI  │ Roadmap  │          │                   │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘                   │
│ ┌────────────────────────────────────────────┬─────────────────────────────┐ │
│ │  CHAT PANE (left, ~60%)                    │  PREVIEW PANE (right, ~40%) │ │
│ │ ──────────────────────────────────────────  │ ─────────────────────────── │ │
│ │  Eli: I want a feature where...             │  📄 README.md (live render) │ │
│ │                                             │                             │ │
│ │  Jonny: Let me decompose...                 │  # Feature Studio           │ │
│ │   ╭ Calling: solution-architect ─╮          │                             │ │
│ │   │ ⚙️ Designing schema...        │          │  ## Architecture            │ │
│ │   ╰────────────────────────────╯          │   [diagram preview]          │ │
│ │                                             │                             │ │
│ │  Solution-Architect: Here's the data model │  ┌────────────┐             │ │
│ │   [generated SQL + diagram]                │  │            │             │ │
│ │                                             │  │  Mermaid   │             │ │
│ │  ──────────────────────────────             │  │  diagram   │             │ │
│ │   AGENT ACTIVITY (live):                   │  │  rendered  │             │ │
│ │   🟢 jonny       — orchestrating            │  │            │             │ │
│ │   🟢 architect   — schema design            │  └────────────┘             │ │
│ │   ⚪ ui-designer  — idle                    │                             │ │
│ │   🟢 docs        — drafting plan             │  [Tab: Mermaid │ MD │ Code]│ │
│ │  ──────────────────────────────             │                             │ │
│ │  [Type message…                  ]          │                             │ │
│ │  [Send] [→ Send to Backlog] [⏸ Pause]      │                             │ │
│ └────────────────────────────────────────────┴─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component breakdown

| Zone | Purpose | React component |
|---|---|---|
| Top bar | Project picker, new conversation, settings | `<StudioTopBar />` |
| Tab strip | Conversation tabs with live indicator dots | `<ConversationTabs />` |
| Chat pane | Messages, agent invocation cards, action buttons | `<ChatPane />` |
| Agent activity panel | Live status of each agent/skill in the room | `<AgentCrewPanel />` |
| Preview pane | Split-view artifact renderer (md/code/mermaid/html) | `<PreviewPane />` |
| Action bar | Send / Send to Backlog / Pause / Save / Discard | `<ChatActions />` |

### Architecture — backend

```
┌────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 16 / 3601)                                  │
│  ──────────────────────────────────────────────────────────── │
│  /app/studio/page.tsx                                          │
│   └─ React Query → /api/studio/conversations                   │
│   └─ EventSource → /api/studio/sessions/{id}/events  ←─ SSE    │
└────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI / 8401)                                      │
│  ──────────────────────────────────────────────────────────── │
│  api/studio.py — REST + SSE endpoints                          │
│  services/studio_orchestrator.py — multi-session manager       │
│   ├─ Spawn `claude -p ... --output-format stream-json`         │
│   │   per conversation tab (reuse terminal_service patterns)   │
│   ├─ Per-session worktree via session_pool                     │
│   ├─ Multiplex stream-json events into per-session SSE channel │
│   └─ Track active agents/skills per session in memory + DB     │
└────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────────────────────────────────────────────────────┐
│  Data Layer                                                    │
│  ──────────────────────────────────────────────────────────── │
│  StudioConversation (id, projectId, title, state, createdAt) │
│  StudioMessage (id, conversationId, role, content, agent)    │
│  StudioArtifact (id, conversationId, kind, payload, ts)       │
│  StudioAgentActivity (id, conversationId, agentName,         │
│                       skillName, status, startedAt, endedAt) │
└────────────────────────────────────────────────────────────────┘
```

**Key mechanic:** every conversation tab maps 1:1 to a persistent Claude Code subprocess that stays alive for the life of the tab (hibernates after N minutes idle). The subprocess streams `stream-json` events; the orchestrator parses them into:
- Chat messages → `StudioMessage`
- Tool calls → live `StudioAgentActivity` updates
- File writes → `StudioArtifact` rendered in preview pane
- Subagent invocations → "agent X is working" cards in chat pane

### Animation philosophy
**Subtle, not distracting.** Active agent badges pulse at 2 Hz with a soft glow. New messages slide in 200ms. Preview pane reveals/hides with a 280ms ease-in-out. No bouncing, no spinning wheels — agent thinking is a soft shimmer.

---

## Chapter 4 — Feature Backlog Board Architecture

### Top-level layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Feature Backlog                                            [+ New Feature]  │
│  Filters: [Project ▾] [Status ▾] [Priority ▾] [Tag ▾]   Sort: [Updated ▾]   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ╔═════════════════════════════════════════════════════════════════════════╗ │
│  ║ 📌 HIGH    AI Cost Optimization                                         ║ │
│  ║ DRAFT     Cuts token burn 80%                          ⏰ Q3 2026       ║ │
│  ║ Tags: ai, cost, telemetry          From: Conversation #12 (Studio)     ║ │
│  ║ [Edit] [Open in Studio] [→ Send to CodeBoard + AutoPilot] [Schedule]   ║ │
│  ╚═════════════════════════════════════════════════════════════════════════╝ │
│                                                                              │
│  ╔═════════════════════════════════════════════════════════════════════════╗ │
│  ║ 📌 CRITICAL Feature Studio Chat Window                                  ║ │
│  ║ APPROVED   Replaces direct CodeBoard planning           ⏰ now          ║ │
│  ║ Tags: ux, frontend, multi-tab     From: Conversation #14 (Studio)     ║ │
│  ║ [Edit] [Open in Studio] [→ Send to CodeBoard + AutoPilot] [Schedule]   ║ │
│  ╚═════════════════════════════════════════════════════════════════════════╝ │
│                                                                              │
│  ╔═════════════════════════════════════════════════════════════════════════╗ │
│  ║ 📌 MEDIUM  Migrate park.sh to Python                                   ║ │
│  ║ DRAFT     Cleanup, no urgency                          ⏰ unscheduled  ║ │
│  ║ Tags: refactor, devops             From: Manual entry                  ║ │
│  ║ [Edit] [Promote to Studio] [→ Send to CodeBoard + AutoPilot]           ║ │
│  ╚═════════════════════════════════════════════════════════════════════════╝ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Status flow
```
   DRAFT  →  REVIEWING  →  APPROVED  →  SCHEDULED  →  PROMOTED
                                                ↓
                                            (now in CodeBoard +
                                              AutoPilot queue)
                                                ↓
                                             SHIPPED
                                                ↓
                                             ARCHIVED
```

### Data model

| Table | Columns |
|---|---|
| `FeatureRequest` | id, projectId, title, description, priority, status, scheduledFor, scheduleCron, tags, sourceConversationId, targetIssueId, ownerEmail, createdAt, updatedAt, archivedAt |
| `FeatureRequestComment` | id, featureRequestId, author, content, createdAt |
| `FeatureRequestActivity` | id, featureRequestId, action, payload, actor, ts |

### "Send to CodeBoard + AutoPilot" action
1. Read the source conversation transcript + structured plan
2. Generate Feature → Epic → Story → Task hierarchy via Jonny prompt
3. Create CodeBoard issues (POST `/api/projects/{id}/issues`)
4. Set status `IN_PROGRESS` on the FEATURE if scheduledFor=now
5. Append to AutoPilot queue (POST `/api/execute/queue`)
6. Update FeatureRequest.status → PROMOTED, set targetIssueId

### Scheduler
- One-shot: `scheduledFor = ISO timestamp`
- Recurring: `scheduleCron = "0 9 * * MON"` (cron expression)
- Background worker (`services/feature_scheduler.py`) wakes every 60s, polls SCHEDULED entries with `scheduledFor <= now`, fires the promote-to-CodeBoard action

---

## Chapter 5 — Story Board (Agile Hierarchy)

### Feature 1: Feature Studio — Chat-based Feature Planning

| ID | Type | Title |
|---|---|---|
| **F1** | FEATURE | Feature Studio — Chat-Based Feature Planning Interface |
| F1.E1 | EPIC | Backend Conversation Orchestrator |
| F1.E1.S1 | STORY | StudioConversation + StudioMessage data model |
| F1.E1.S2 | STORY | Multi-session Claude Code spawn manager (extend `terminal_service`) |
| F1.E1.S3 | STORY | Stream-json → SSE multiplexer per session |
| F1.E1.S4 | STORY | Persistent session hibernation + resume |
| F1.E1.S5 | STORY | Per-session token usage capture (links to AI Cost Optimization E2) |
| F1.E2 | EPIC | Frontend — Studio Layout & Chat |
| F1.E2.S1 | STORY | `/app/studio/page.tsx` shell with project picker + new-conversation CTA |
| F1.E2.S2 | STORY | Conversation tab strip with live indicator dots |
| F1.E2.S3 | STORY | Chat pane (messages, role badges, agent invocation cards) |
| F1.E2.S4 | STORY | Action bar (Send, Send to Backlog, Pause, Save, Discard) |
| F1.E3 | EPIC | Live Agent Activity Panel |
| F1.E3.S1 | STORY | `<AgentCrewPanel />` component |
| F1.E3.S2 | STORY | SSE subscription + state reducer for agent activity |
| F1.E3.S3 | STORY | Animation system (pulse, shimmer, fade) — Tailwind + framer-motion |
| F1.E4 | EPIC | Split-View Preview Pane |
| F1.E4.S1 | STORY | `<PreviewPane />` shell with detect-and-reveal logic |
| F1.E4.S2 | STORY | Markdown renderer with syntax highlighting |
| F1.E4.S3 | STORY | Mermaid + diagram renderer |
| F1.E4.S4 | STORY | Code viewer with diff mode |
| F1.E4.S5 | STORY | HTML preview iframe (sandboxed) for UI/UX previews |
| F1.E5 | EPIC | Send-to-Backlog Bridge |
| F1.E5.S1 | STORY | Conversation transcript → structured FeatureRequest payload |
| F1.E5.S2 | STORY | Confirmation modal + edit-before-send |
| F1.E5.S3 | STORY | POST to `/api/feature-backlog` + redirect/toast |
| F1.E6 | EPIC | Audits + Tests + Chrome QA |
| F1.E7 | EPIC | Rollout + Docs + Soak |

**~24 stories, ~70 tasks, ~30-40 subtasks**

### Feature 2: Feature Backlog Board

| ID | Type | Title |
|---|---|---|
| **F2** | FEATURE | Feature Backlog Board — Pre-CodeBoard Staging |
| F2.E1 | EPIC | Data Model |
| F2.E1.S1 | STORY | `FeatureRequest` + `FeatureRequestComment` + `FeatureRequestActivity` SQLAlchemy + Prisma |
| F2.E1.S2 | STORY | Migration + idempotent seed (import from Studio sample) |
| F2.E2 | EPIC | API Layer |
| F2.E2.S1 | STORY | CRUD endpoints `/api/feature-backlog` |
| F2.E2.S2 | STORY | "Promote to CodeBoard + AutoPilot" action endpoint |
| F2.E2.S3 | STORY | Filtering, sorting, tag search |
| F2.E3 | EPIC | Frontend Page |
| F2.E3.S1 | STORY | `/app/feature-backlog/page.tsx` list view with cards |
| F2.E3.S2 | STORY | Filter bar + search + sort dropdown |
| F2.E3.S3 | STORY | Card component with priority badge + schedule indicator |
| F2.E3.S4 | STORY | Edit modal (title, description, priority, tags, schedule) |
| F2.E3.S5 | STORY | "Open in Studio" action (deep link back to source conversation) |
| F2.E4 | EPIC | Scheduler |
| F2.E4.S1 | STORY | Background `feature_scheduler.py` worker (asyncio loop) |
| F2.E4.S2 | STORY | Cron expression parser + validator |
| F2.E4.S3 | STORY | One-shot trigger on `scheduledFor <= now` |
| F2.E4.S4 | STORY | Promote-to-CodeBoard pipeline |
| F2.E5 | EPIC | Promote Pipeline |
| F2.E5.S1 | STORY | Conversation transcript → Feature/Epic/Story/Task generator (Jonny prompt) |
| F2.E5.S2 | STORY | Bulk POST to CodeBoard + commit on success |
| F2.E5.S3 | STORY | Append to AutoPilot queue if priority >= HIGH |
| F2.E5.S4 | STORY | Status transition: SCHEDULED → PROMOTED + audit row |
| F2.E6 | EPIC | Audits + Tests + Chrome QA |
| F2.E7 | EPIC | Rollout + Docs |

**~22 stories, ~65 tasks, ~25-30 subtasks**

---

## Chapter 6 — Cross-Feature Dependencies

```
   F1 Feature Studio ─────►  F2 Feature Backlog ─────► CodeBoard / AutoPilot
   (creates conversations)   (stages drafts)         (executes work)

   Both F1 + F2 inherit the future ExecutionTokens table from CB-2381
   (parked AI Cost Optimization plan) once that ships.
```

**Sequencing recommendation:**
1. **F2 first** (Feature Backlog Board) — fewer moving parts, gives a destination for F1
2. **F1 second** (Feature Studio) — now has Backlog to "Send to" out of the box
3. Each feature follows the bible: CodeBoard tickets → audits → regression → CWQ → Eli's manual QA → DONE

---

## Chapter 7 — The KPI Story

| Metric | Today | After F1+F2 |
|---|---|---|
| Half-baked CodeBoard issues | ~30% of BACKLOG | <5% |
| Time from idea to executable plan | days (manual) | minutes (Studio chat) |
| Feature priority visibility | flat in CodeBoard | tiered in Backlog Board |
| Recurring feature fires | none | scheduler |
| Eli's planning UX | "open another tab to CodeBoard" | "type into Studio" |

---

## Chapter 8 — Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Multi-session token cost explosion | M | H | Per-session budget cap (links to CB-2381 future fix) |
| Subprocess hibernation / resume bugs | M | M | Snapshot conversation state every N msgs |
| SSE channel saturation on many tabs | L | M | Channel multiplexing, max 8 concurrent streams |
| Studio + CodeBoard data drift | M | M | Single source of truth = Studio conversation; backlog references it |
| Promote-to-CodeBoard generates bad hierarchy | M | H | Edit-before-send modal; require human confirm |
| Animation distraction | L | L | Subtle defaults; user can disable |
| Cron parser edge cases | M | L | Use battle-tested `croniter` lib |

---

## Chapter 9 — Phased Rollout

### Phase A — Feature Backlog Board (1.5 weeks)
F2.E1 → F2.E2 → F2.E3 → F2.E4 → F2.E5 → F2.E6 → F2.E7

### Phase B — Feature Studio MVP (2 weeks)
F1.E1 → F1.E2 (chat only, no split view yet) → F1.E5 (send to backlog) → F1.E6 → F1.E7

### Phase C — Feature Studio polish (1 week)
F1.E3 (agent activity) → F1.E4 (split-view preview)

**Total: ~4.5 weeks. ~46 stories, ~135 tasks, ~55 subtasks.**

---

## Chapter 10 — The Ask

Eli, this plan covers BOTH features end-to-end:

✅ Architecture diagrams (top-level layouts + backend + data model)
✅ Component breakdowns
✅ Full agile hierarchy (FEATURE → EPIC → STORY → TASK → SUBTASK)
✅ Animation philosophy
✅ Cross-feature dependencies
✅ Risk register
✅ KPI targets
✅ Phased rollout

**Three approval levels:**

1. ✅ **Approve the storytelling + arch** — I refine with CandleKeep findings, present v1.1, you approve, I push F1 + F2 to CodeBoard
2. ✅ **Approve and push immediately** — I run the push script now with the current hierarchy. Refinement happens via CodeBoard edits later
3. ✅ **Approve only F2 (Feature Backlog Board)** — start with the simpler one, defer F1 for next sprint

Default recommendation: **Option 1.** CandleKeep readers are still in flight — they'll bring concrete patterns from Linear, Vercel, Claude Code chat UX, and multi-agent orchestration that will sharpen the design materially before we commit to a hierarchy.

---

**Plan stays in `docs/plans/` (Rule 27).**
**Push script will land in `backend/scripts/codeboard/2026-05-07-feature-studio-and-backlog-push.py` (Rule 29).**
**Cost-optimization plan is parked as CB-2381 (BACKLOG, label `parked-future`).**

— Jonny

---

## Chapter 11 — CandleKeep Findings (v1.1 merge)

### Production-validated patterns to bake in

#### From Reader 1 — Agent Orchestration (6 books)

**The Visibility Principle (iron law).** *Building Your Agent Team*, pp. 5 & 10:
> "I caught an agent once claiming it had communicated with another agent through an 'internal channel' that did not exist. It hallucinated the entire interaction… Every message, every agent-to-agent notification, every response goes through Discord where I can see it, scroll back through it, and audit it."

→ **F1.E1 — every Jonny→skill dispatch MUST hit `StudioAgentActivity` row before the chat says it happened. No trust on Jonny's claim. No internal channels.**

**Template / Instance separation.** Each agent gets two halves: `template/` (git-tracked, versioned: identity, capabilities, domain knowledge) and `instance/` (gitignored, per-session: accumulated memory, logs).
→ **F1 data model adds `agentTemplate` (versioned) + `agentInstance` (per-conversation) split. Kills config drift on Studio crew.**

**GroupQueue lock per agent.** One execution at a time per agent across all tabs — folder-lock or DB-lock equivalent.
→ **F1.E1.S2 — add per-skill mutex in `studio_orchestrator.py`. Two tabs cannot invoke `architect` simultaneously.**

**Four typed inter-agent message primitives.** `notify` / `request` / `delegate` / `broadcast`, with `max_chain_depth=3` to prevent runaway delegation.
→ **F1.E1.S3 — orchestrator API uses these 4 verbs only. Chain depth enforced structurally.**

**Sub-agent context isolation.** Each skill gets a fresh, clean context window and returns a 1-2K-token compact artifact. Jonny's planning context never bloats with tool transcripts.
→ **F1.E5 transcript-to-CodeBoard pipeline: skills run isolated, return distilled artifacts, Jonny synthesizes.**

**Tool consolidation, not decomposition.** *Writing Effective Tools for Agents*:
> "Multiple API calls can be wrapped into single, higher-level operations."

→ **F1.E5.S1 — single `add_to_codeboard(hierarchy)` tool, NOT five granular CRUD tools. Same for `send_to_autopilot(issue_id, priority)`.**

**Blueprint state machines (deterministic + agentic hybrid).** *Stripe Minions*:
> "A given node can run either deterministic code or an agent loop focused on a task."

→ **F2.E5 promote pipeline: dispatch + collect + push are deterministic; per-skill task is agentic. NOT pure agent loop.**

**Passive-by-default skills.** Skills do NOT auto-fire on chat keywords — only Jonny dispatches.
→ **F1.E2 chat input only sends to Jonny; skills never read chat directly.**

**Approval modes per-action.** `confidence` (skill self-decides), `always` (human approves), `never` (full autonomy). Start `always`, loosen as trust builds.
→ **F2.E5 send-to-AutoPilot: first N runs in `always` mode (confirmation modal). Reversible actions (`add_to_codeboard`) can run `confidence` mode.**

#### From Reader 2 — UI/UX & Frontend (4 books)

**Linear-native dark palette (the visual reference).** *Awesome Design.md*, p. 24:
- Canvas: `#08090a` (deepest dark)
- Panels: `#0f1011`
- Card surfaces: `rgba(255,255,255,0.02)` translucent + `1px solid rgba(255,255,255,0.08)` border
- Single chromatic accent: `#7170ff` (indigo-violet)
- Status green: `#27a644` / `#10b981`
- Text active: `#f7f8f8` | inactive: `#d0d6e0` | muted: `#8a8f98`

**Inter Variable weight 510 — the signature.** *Awesome Design.md*, p. 24:
> "510 is the signature weight: between regular 400 and medium 500 — subtly bolded feel without the heaviness of traditional medium or semibold."

→ **All Studio tab labels + agent badges + priority pills use Inter Variable, weight 510, 13-14px.**

**Asymmetric animation timing.** *UI/UX Design Principles for AI Agents*, p. 10:
- Enter: 250ms `translateX(100% → 0)` ease-out
- Exit: 150ms (~60% of enter) — get out of the way fast

→ **Split-view artifact pane reveal/hide uses these exact timings.**

**CSS `transition` (NOT `@keyframes`) for state-change animations.** *Vercel Frontend Engineering Guidelines*, ch. 16. Transitions are interruptible — if user dismisses mid-open, animation picks up from current position. Keyframes reset jarringly.

→ **All split-pane + tab-switch + badge state transitions use CSS `transition`, not keyframes. Reserved keyframes only for one-shot looping animations (the green pulse dot).**

**GPU-only animation properties.** Animate only `transform` + `opacity` + `filter`. Never `width` / `left` / `margin` (triggers layout = jank).

→ **Codified in F1.E3 + F1.E4 design rules.**

**Stagger 50-100ms, cap cascade ≤400ms.** Sequential reveal of artifact sub-blocks reads as composition, not chaos.

**Doherty Threshold = 400ms.** *UI/UX Design Principles*, p. 9:
> "Maintain system response below 400ms to keep users in flow state."

→ **F2.E4 scheduler controls (date pickers, drag-reorder, priority dropdowns) must respond < 400ms. Hard rule.**

**Compound Component + Context pattern.** *Vercel Frontend Engineering Guidelines*, p. 3:
> "Avoid boolean prop proliferation… use composition: `<Composer.Frame>`, `<Composer.Input>`, `<Composer.Footer>`, `<Composer.Submit>`"

→ **Studio chat shipped as `<Chat.Provider>` + `<Chat.TabBar>` + `<Chat.MessageList>` + `<Chat.AgentStatus>` + `<Chat.Input>`. State in context, not props.**

**Streaming UI = `includePartialMessages: true` + `inTool` boolean.** *Claude Code Official Docs*, pp. 335-338. Drives live activity indicator without complex state machines.

→ **F1.E3.S2 — agent activity panel reads `inTool` from stream-json events; toggle "Using ToolName…" badge accordingly.**

**`useRef` token accumulation (not `useState`).** *Vercel Frontend Engineering Guidelines*, ch. 5. Streaming SSE deltas updated via `tokenBufferRef.current += delta.text`, flushed to state every 50ms via `setInterval`. Prevents 20+ re-renders per second.

→ **F1.E2.S3 chat pane uses ref-buffered streaming pattern.**

**`content-visibility: auto`** on message list items — virtualizes off-screen messages without a virtual scroll library.

**Accessibility iron rules (non-negotiable):**
- `<div role="status" aria-live="polite">` on streaming text container (not assertive — assertive is for errors only)
- Focus moves into artifact pane on reveal, returns to triggering message on close
- Resize handle is `role="separator"` + keyboard ArrowLeft/ArrowRight operable
- `:focus-visible` outlines (keyboard only, not mouse) — `2px solid #7170ff` offset 2px
- Reduced-motion media query disables all `animate-pulse` to static opacity
- Content usable at 200% zoom — split pane collapses to single column

**Linear priority badge recipe:**
```tsx
// Critical
<span className="rounded-[2px] px-2 py-0.5 text-[10px] font-[510] uppercase
  bg-red-500/10 text-red-400 border border-red-500/20">Critical</span>

// Medium
<span className="rounded-[2px] px-2 py-0.5 text-[10px] font-[510]
  bg-white/5 text-[#d0d6e0] border border-white/5">Medium</span>
```

**Tabular numerals on schedule timestamps:** `font-feature-settings: "tnum"` keeps countdown timers + dates optically aligned across rows. *Awesome Design.md*, p. 47 (Stripe).

**Anthropic light-mode alternative** — for users who prefer Parchment over Linear-dark:
- Surface: `#f5f4ed` (Parchment)
- Headlines: Anthropic Serif 20px weight 500
- Body: Anthropic Sans 15-16px
- Accent: Terracotta `#c96442`

→ **Theme switcher in Settings: Linear-dark (default) | Anthropic-light.**

---

### Updated decision log (v1.0 → v1.1)

| Decision | v1.0 | v1.1 (post-CandleKeep) |
|---|---|---|
| Agent template/instance | implicit | **explicit split**, mirror Building Your Agent Team |
| Per-skill execution lock | not specified | **GroupQueue mutex** in orchestrator |
| Inter-agent message types | implicit | **4 verbs**: notify/request/delegate/broadcast + chain≤3 |
| Visibility | "DB record per dispatch" | **iron rule** — no record = didn't happen |
| Tool granularity | "many small tools" | **consolidated**: `add_to_codeboard(hierarchy)`, `send_to_autopilot(id)` |
| Promote pipeline | agent loop | **Blueprint** (deterministic dispatch + agentic per-skill) |
| Skill triggers | reactive | **passive-by-default**, only Jonny dispatches |
| Approval default | not specified | **`always` mode** for first N runs of send-to-AutoPilot |
| Color palette | not specified | **Linear-dark** default, Anthropic-light alternative |
| Font weight | "Tailwind defaults" | **Inter Variable 510** signature |
| Animation engine | framer-motion | **CSS transitions** (interruptible), keyframes reserved for one-shot loops |
| Pane reveal timing | "smooth" | **enter 250ms / exit 150ms** asymmetric |
| Streaming pattern | SSE | **`includePartialMessages` + `inTool` flag + ref-buffered render** |
| Component pattern | "shadcn-style" | **Compound Component + Context provider** |
| Scheduler responsiveness | not specified | **<400ms Doherty Threshold** hard rule |
| Accessibility | "WCAG AA" | **explicit iron rules** (focus mgmt, separator role, aria-live polite) |

---

## Citation Block

```
┌─ CandleKeep ──────────────────────────────────────────────────────────────────┐
│ Read: Building Your Agent Team — A Practitioner's Guide to Multi-Agent AI    │
│       Building Effective Agents                                               │
│       Effective Context Engineering for AI Agents                             │
│       Writing Effective Tools for Agents                                      │
│       Stripe Minions — Unattended Coding Agents at Scale                      │
│       How Anthropic Teams Use Claude Code                                     │
│       UI/UX Design Principles for AI Agents                                   │
│       Awesome Design.md (Claude/Linear/Stripe/Vercel sections)                │
│       Vercel Frontend Engineering Guidelines                                  │
│       Claude Code: Official Docs (Streaming chapters)                         │
│ Learned: visibility principle (no DB record = hallucination) ·                │
│          template/instance separation · 4 inter-agent message verbs ·         │
│          tool consolidation over decomposition · Blueprint hybrid state       │
│          machines · Inter Variable weight 510 · CSS transitions over          │
│          keyframes (interruptible) · Doherty 400ms threshold ·                │
│          Linear dark palette + Anthropic light alternative ·                  │
│          ref-buffered SSE accumulation · aria-live polite + role=separator    │
│ How it helped: design grounded in production-validated patterns from          │
│                Stripe (1,300+ PRs/wk), Anthropic (10 internal teams), and     │
│                Linear/Vercel design systems — not invented from scratch       │
│                                                                                │
│ Worth remembering: "I caught an agent once claiming it had communicated      │
│ with another agent through an 'internal channel' that did not exist. It      │
│ hallucinated the entire interaction… Every message goes through a visible    │
│ medium where I can see it, scroll back, and audit it."                        │
│ — Building Your Agent Team, pp. 5 & 10                                        │
└────────────────────────────────────────────────────────────────────────────────┘
```

