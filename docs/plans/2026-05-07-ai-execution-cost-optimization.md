# 📖 The Story of the 11% Bug
## Feature Plan — AI Execution Cost Optimization

**Date:** 2026-05-07
**Author:** Jonny (VP R&D)
**For:** Eli Cohen
**Status:** PROPOSED — awaits Eli's approval before CodeBoard push (Rule 23)

---

## Chapter 1 — The Punch in the Face

Eli fires one bug from CodeBoard UI. **Eleven percent of the weekly quota disappears.** Other sessions sit at 0–1%. Same subscription. Same machine. Same Claude Code CLI. Different bill.

Numbers don't lie. Something inside `terminal_service.py` is burning **240× the tokens** of a normal Claude conversation per fire.

We diagnose, we fix, we measure, we never let it happen again.

---

## Chapter 2 — The Crime Scene

Four fingerprints on the murder weapon:

```
┌─────────────────────────────────────────────────────────────┐
│  CRIME SCENE — Why one bug = 11% quota                     │
├─────────────────────────────────────────────────────────────┤
│  ① alwaysThinkingEnabled: true        → 3-10× per turn     │
│  ② Default model = Opus              → 5× vs Sonnet, 25× Haiku │
│  ③ Cache wipe on feature switch      → 2-3× cold-start     │
│  ④ Mandatory 4-gate audit (Rule 18)  → 4× per change       │
│  ⑤ Claude Code 2.1.131 vs required 2.0.76 → possibly 2× dup tool_use │
│  ⑥ Zero token telemetry              → blind to runaway     │
├─────────────────────────────────────────────────────────────┤
│  MULTIPLIER STACK: 5×3×2×4 = 120× minimum                   │
│  With dup-bug: 240×                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Chapter 3 — The Plan

We build **one Feature, eight Epics, ~28 Stories, ~80 Tasks.** Every fix has audits, regression, Chrome QA, and CodeBoard tracking — bible says so.

### Architecture — Before vs After

#### BEFORE (today)
```
Eli clicks "Execute"
        ↓
terminal_service.py spawns:
        ↓
   claude -p <prompt> --output-format stream-json
        ↓
   Default model: OPUS
   alwaysThinkingEnabled: true
   Cache: WIPED on feature switch
   Subagents: 4 mandatory gates, all OPUS, all thinking
        ↓
   No usage capture
   No budget cap
   No cost telemetry
        ↓
        💸💸💸
```

#### AFTER (target)
```
Eli clicks "Execute"
        ↓
Cost Profile Selector
   ├─ size < 100 LOC + low risk  → CHEAP   profile
   ├─ 100-500 LOC OR auth        → MEDIUM  profile
   └─ > 500 LOC OR security crit → FULL    profile
        ↓
terminal_service.py spawns:
        ↓
   claude -p <prompt> --model <tiered>  --output-format stream-json
        ↓
   Tiered model: SONNET (default), Haiku for trivial, Opus only for complex
   alwaysThinkingEnabled: scoped (manual only, OFF in spawned)
   Cache: PRESERVED with feature_id tag (not wiped)
   Subagents: gate count = profile.gates (1, 2, or 4)
        ↓
   Stream-json usage parsed → ExecutionTokens table
   Per-session budget cap enforced
   SSE events publish live cost
        ↓
   Settings page: Cost Dashboard
   Per-issue tab: tokens/$/duration breakdown
        ↓
        💰 (within budget)
```

---

## Chapter 4 — The Story Board

### F: AI Execution Cost Optimization — Token Burn Mitigation
> Cut PMv2 AI execution cost by 80% without sacrificing quality. Make every fire measurable. Block runaways.

**Reporter:** AI (Jonny) | **Priority:** CRITICAL | **Label:** `ai-cost-optimization`
**Linked:** CB-1951 (AutoPilot), V3_AGENT_ARCHITECTURE.md (F-2/F-4 plan)

---

### EPIC E1 — Emergency Stop the Bleeding (TODAY)
**Goal:** Cut active token burn by 70% within 1-2 hours of approval. Zero new infrastructure. Settings + flag flips only.

| ID | Type | Title | Effort |
|---|---|---|---|
| S1.1 | STORY | Disable always-thinking in spawned sessions | |
| T1.1.1 | TASK | Read `~/.claude/settings.json`, identify `alwaysThinkingEnabled` impact on spawn vs manual | XS |
| T1.1.2 | TASK | Decide: flip global to `false`, OR override via env var in `terminal_service.py` env block | XS |
| T1.1.3 | TASK | Apply chosen approach; verify via test fire | XS |
| S1.2 | STORY | Force Sonnet model in spawned `claude -p` cmd | |
| T1.2.1 | TASK | Add `--model claude-sonnet-4-6` to `cmd` array at `terminal_service.py:747-754` | XS |
| T1.2.2 | TASK | Add settings panel toggle to override model per-project (default Sonnet) | S |
| T1.2.3 | TASK | Test fire on a low-risk task, confirm Sonnet routing in stream-json | XS |
| S1.3 | STORY | Pin Claude Code CLI version | |
| T1.3.1 | TASK | Verify if 2.1.131 has duplicate tool_use ID bug — instrument 1 fire, count ID dups | S |
| T1.3.2 | TASK | If bug present → install 2.0.76 OR find next stable; document in CLAUDE.md | M |
| T1.3.3 | TASK | Add startup version check in `terminal_service.py`; warn if mismatch | S |
| S1.4 | STORY | Audit gate floor — disable for trivial fixes | |
| T1.4.1 | TASK | Add `complexity_score` heuristic (LOC delta + path-sensitive paths) | M |
| T1.4.2 | TASK | Map score to gate count: 0-1 trivial → 1 gate; 2 medium → 2 gates; 3 high → 4 gates | S |
| T1.4.3 | TASK | Wire into prompt builder so subagent calls are conditional | M |

**E1 success criteria:**
- ✅ Test fire on CB-2363 (or equivalent BUG) burns < 2% weekly quota
- ✅ Sonnet visible in stream-json logs
- ✅ Thinking tokens absent in `usage` payload (when off)

---

### EPIC E2 — Cost Telemetry (V3-F4 Metrics Collector slice)
**Goal:** Make every fire measurable. Capture usage. Persist. Surface in UI. Detect runaways.

| ID | Type | Title |
|---|---|---|
| S2.1 | STORY | Capture token usage from stream-json `result` event |
| T2.1.1 | TASK | Extend `_process_stream_json_event` to read `event['message']['usage']` on `result` |
| T2.1.2 | TASK | Track per-session totals: `input_tokens`, `output_tokens`, `cache_read`, `cache_creation`, `thinking_tokens` |
| T2.1.3 | TASK | Compute estimated cost using model price table (per-tier rates) |
| S2.2 | STORY | Persist `ExecutionTokens` table |
| T2.2.1 | TASK | New SQLAlchemy model: `(id, sessionId, issueId, projectId, model, inputTokens, outputTokens, cacheRead, cacheCreation, thinkingTokens, totalUSD, startedAt, endedAt)` |
| T2.2.2 | TASK | Prisma mirror in `frontend/prisma/schema.prisma` |
| T2.2.3 | TASK | Migration + idempotent backfill from existing `ExecutionSummary` (where possible) |
| T2.2.4 | TASK | Repository pattern for safe write-through persistence |
| S2.3 | STORY | Capture subagent telemetry (V3-F2 slice) |
| T2.3.1 | TASK | Detect `tool_name == 'Task'` in stream-json → record `subagent_type` |
| T2.3.2 | TASK | Detect `tool_name == 'Skill'` → record `skill` arg |
| T2.3.3 | TASK | New `AgentInvocation` + `SkillInvocation` tables |
| T2.3.4 | TASK | Match start/end via `tool_use_id` ↔ `tool_result` to compute `durationMs` |
| S2.4 | STORY | Aggregations API |
| T2.4.1 | TASK | `GET /api/stats/tokens?projectId=X&since=Y` → cost rollups |
| T2.4.2 | TASK | `GET /api/stats/agents` + `/api/stats/skills` |
| T2.4.3 | TASK | `GET /api/stats/usage/by-issue/{id}` |
| T2.4.4 | TASK | SSE channel for live per-session cost updates |

**E2 success criteria:**
- ✅ Every fire writes 1 row to `ExecutionTokens` with non-null cost
- ✅ Runaway detection: per-session `totalUSD > $1.00` triggers warning event

---

### EPIC E3 — Cache Preservation
**Goal:** Stop nuking the prompt cache. Keep Anthropic + local Claude Code cache intact across feature switches.

| ID | Type | Title |
|---|---|---|
| S3.1 | STORY | Replace destructive `shutil.rmtree` with feature-tagged cache |
| T3.1.1 | TASK | Audit `terminal_service.py:731-735` cache-clear logic — what assumptions? |
| T3.1.2 | TASK | Replace with feature-scoped cache dir: `~/.claude/projects/<proj>/<feature_id>/` |
| T3.1.3 | TASK | Garbage-collect inactive feature caches > 7 days old (background task) |
| T3.1.4 | TASK | Test cache hits across feature switches via stream-json `cache_read_input_tokens` |
| S3.2 | STORY | Trim CLAUDE.md auto-loaded surface |
| T3.2.1 | TASK | Audit current CLAUDE.md (9.6K chars) — split essential vs reference |
| T3.2.2 | TASK | Move reference content (api endpoints, conventions tables) to `docs/CLAUDE-reference.md` |
| T3.2.3 | TASK | Add explicit reference link from CLAUDE.md so Claude can pull on demand |

**E3 success criteria:**
- ✅ Cold-start input tokens drop from ~22K → ~7K
- ✅ `cache_read_input_tokens` > 0 on second fire of same feature

---

### EPIC E4 — Smart Audit Gating (Rule 18 conditional)
**Goal:** Apply 4-gate audit only when warranted. Trivial fixes get 1 gate. Medium = 2. Big = full 4.

| ID | Type | Title |
|---|---|---|
| S4.1 | STORY | Complexity scoring heuristic |
| T4.1.1 | TASK | Define scoring inputs: LOC delta, file count, sensitive path match (auth/db/security/network) |
| T4.1.2 | TASK | Implement `score_change_complexity(diff_summary, file_paths)` returning 0-3 |
| T4.1.3 | TASK | Unit tests covering edge cases: pure docs (0), trivial UI (1), backend route (2), auth flow (3) |
| S4.2 | STORY | Profile-driven prompt builder |
| T4.2.1 | TASK | Define 3 profiles: CHEAP (1 gate), MEDIUM (2 gates), FULL (4 gates) |
| T4.2.2 | TASK | Generate appropriate Jonny prefix per profile (drop unused gates) |
| T4.2.3 | TASK | Persist profile choice to `ExecutionSummary` for retro analysis |
| S4.3 | STORY | Manual override + UI |
| T4.3.1 | TASK | Settings toggle: "Force FULL audit (cost ignored)" — defaults off |
| T4.3.2 | TASK | Per-issue override on execute button: drop-down (Auto/Cheap/Medium/Full) |

**E4 success criteria:**
- ✅ Test fire on a 10-line typo fix → 1 gate, < 0.5% weekly quota
- ✅ Test fire on auth middleware change → 4 gates, full coverage

---

### EPIC E5 — Model Tiering
**Goal:** Match model to job. Haiku for trivial. Sonnet default. Opus only when needed.

| ID | Type | Title |
|---|---|---|
| S5.1 | STORY | Tier mapping table |
| T5.1.1 | TASK | Build `MODEL_TIERS = {CHEAP: 'haiku-4-5', MEDIUM: 'sonnet-4-6', FULL: 'opus-4-7'}` |
| T5.1.2 | TASK | Wire to complexity score from E4 |
| T5.1.3 | TASK | Subagent inheritance — code-reviewer gets same tier as main fire (or 1 step lighter) |
| S5.2 | STORY | Cost cap |
| T5.2.1 | TASK | Add per-fire `max_usd_cap` setting (default $0.50) |
| T5.2.2 | TASK | Real-time check on stream-json `usage` events; SIGTERM if cap breached |
| T5.2.3 | TASK | Surface "session aborted: budget cap" in UI + audit log |

---

### EPIC E6 — Cost Dashboard UI
**Goal:** Make Eli see what he's spending in real time + retroactively.

| ID | Type | Title |
|---|---|---|
| S6.1 | STORY | Settings page tile: "AI Cost This Week" |
| T6.1.1 | TASK | Card with sparkline + total USD + % of weekly quota |
| T6.1.2 | TASK | Top-5 most expensive fires (issue key, cost, model, duration) |
| S6.2 | STORY | Per-issue Cost tab |
| T6.2.1 | TASK | New tab on issue detail page: "Cost & Tools" |
| T6.2.2 | TASK | Breakdown: input/output/cache/thinking tokens, USD, model, subagent calls |
| T6.2.3 | TASK | Stack chart: total cost over time per agent type |
| S6.3 | STORY | Live cost in GlobalAgentStatusBar + AutoPilotFloatingBar |
| T6.3.1 | TASK | Subscribe to SSE cost channel |
| T6.3.2 | TASK | Live ticker: "$0.12 spent so far" per active session |
| T6.3.3 | TASK | Visual warning when approaching cap |

---

### EPIC E7 — Audits + Tests + Chrome QA + Regression
**Goal:** Per Rule 18, every change passes the gate stack. Per Rule 25, full regression on every feature.

| ID | Type | Title |
|---|---|---|
| S7.1 | STORY | code-reviewer agent on all diffs |
| S7.2 | STORY | security-auditor on cache/persistence/cost-cap code (data exposure risk) |
| S7.3 | STORY | debugger functional test — fire test issue, verify cost row written |
| S7.4 | STORY | Chrome visual QA on Settings cost tile + per-issue cost tab |
| S7.5 | STORY | Full regression matrix |
| T7.5.1 | TASK | Fire trivial bug → CHEAP profile, Haiku, 1 gate, <0.3% quota |
| T7.5.2 | TASK | Fire medium task → MEDIUM profile, Sonnet, 2 gates, <1.5% quota |
| T7.5.3 | TASK | Fire complex feature → FULL profile, Opus, 4 gates, <5% quota |
| T7.5.4 | TASK | Fire with budget cap = $0.10 → SIGTERM observed, audit row written |

---

### EPIC E8 — Rollout & Documentation
**Goal:** Document in CLAUDE.md, MIGRATION_NOTES, runbook. Soak. Promote.

| ID | Type | Title |
|---|---|---|
| S8.1 | STORY | Update CLAUDE.md with new cost-aware execution flow |
| S8.2 | STORY | New runbook: `docs/runbooks/ai-cost-control.md` |
| S8.3 | STORY | Migration notes: token table backfill, cache directory restructure |
| S8.4 | STORY | Soak window — observe 1 week, gather data |
| S8.5 | STORY | Feature flag wrap (`AI_COST_OPT_ENABLED`) for safe rollback |

---

## Chapter 5 — The Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sonnet/Haiku quality drop on coding tasks | M | M | Profile escalation rule: if QA fails, retry FULL |
| Conditional audits miss real bugs | L | H | Force FULL on `priority=CRITICAL` issues regardless of LOC |
| Cache poisoning across features | L | M | Tag-based isolation per feature_id |
| Token cap kills mid-task | M | L | Graceful resume — checkpoint state, allow user override |
| Claude Code CLI version pin breaks future updates | L | L | Document upgrade test protocol |
| Telemetry table grows unbounded | M | L | Retention policy: 90 days default, configurable |

---

## Chapter 6 — The KPI Story

**Before this feature:**
- Cost per fire: ~$5-15 (estimated, no telemetry)
- Weekly quota burn: 11% per bug × N bugs/week = unsustainable
- Cost visibility: zero
- Runaway protection: zero

**After this feature (target):**
- Cost per fire: $0.20-2.00 (measured, capped)
- Weekly quota burn: 0.3-1.5% per bug
- Cost visibility: live dashboard + per-issue breakdown
- Runaway protection: hard cap, SIGTERM, audit log

**Estimated savings:** 80-90% reduction in PMv2 AI execution token cost.

---

## Chapter 7 — The Phased Rollout

### Phase A — Emergency (today, 1-2 hours)
✅ E1 only. No new tables. No UI. Just flag flips + 2-line code edits.
**Outcome:** 70% cost cut immediately. Eli safe through this week.

### Phase B — Visibility (this week, 1-2 days)
✅ E2 (telemetry capture + persist). Backend-only.
**Outcome:** Real numbers. We stop guessing.

### Phase C — Smart routing (next sprint, 3-5 days)
✅ E3 + E4 + E5 (cache, gate routing, model tiering). Backend-light, frontend-light.
**Outcome:** 80-90% cost cut sustainable.

### Phase D — Polish (sprint after, 2-3 days)
✅ E6 (dashboard UI). Frontend-medium.
**Outcome:** Eli has full visibility + control.

### Phase E — Audit & ship (1-2 days)
✅ E7 + E8. Tests, regression, runbook, soak.

---

## Chapter 8 — The Ask

Eli, this plan is honest:
- **It's big.** 8 epics, ~28 stories, ~80 tasks.
- **It pays back.** First emergency cut buys you next week's bandwidth.
- **It's bible-clean.** Audits, regression, Chrome QA, CodeBoard tracking all baked in.
- **It's V3-aligned.** E2 is exactly the F-4 Metrics Collector you authored months ago.

**Three approval levels:**

1. ✅ **Approve E1 only** — push 1 epic to CodeBoard. Emergency. No commitment to E2-E8.
2. ✅ **Approve E1 + E2** — emergency + visibility. Then we re-decide.
3. ✅ **Approve full Feature** — push all 8 epics to BACKLOG. Phased execution per chapter 7.

Default recommendation: **Option 2.** Stop the bleeding + see the numbers. Decide next steps from data, not narrative.

---

**This plan stays in `docs/plans/` (Rule 27).**
**Push script will land in `backend/scripts/codeboard/2026-05-07-ai-cost-opt-push.py` (Rule 29).**
**Status will be BACKLOG on push, not IN_PROGRESS — work starts only when Eli says go on each epic.**

— Jonny
