# Multi-Agent Dev Framework Survey — 2026-05-01

Survey of open-source multi-agent / mesh / swarm systems whose stated purpose is "given a request, build the thing end-to-end with a team of cooperating AI agents." Stars verified directly from GitHub on 2026-05-01. Anything older than 2025-Q3 is flagged as stale.

Scoring rubric (1–10 match against Eli's CodeBoard vision: agent mesh that talks, parallel role-based agents, full-stack generation, ticket-driven Kanban/Jira-style UI, hierarchical work breakdown, AI-execution-per-ticket).

---

## 1. TL;DR — Top 3 Closest Matches

1. **Vibe Kanban (BloopAI)** — match 9/10. Kanban board + parallel coding agents + per-task git worktrees + multi-agent (10+ CLIs) + diff review + MCP for plan-decompose-into-cards. This is the closest public analogue to CodeBoard, except it stops at "ticket → one agent" and does not push hierarchical Feature→Epic→Story→Task. Note: repo shows a sunsetting notice, so the team is moving on — this is the architecture to learn from before it freezes. ([repo](https://github.com/BloopAI/vibe-kanban))

2. **OpenAI Symphony** — match 8/10. Treats a Linear board as the control plane, spawns one autonomous agent per ticket, agents do CI/PR/walkthrough proof-of-work and only escalate when they need a human. Exactly Eli's "AI execution pipeline per ticket" pattern, but Linear-bound and Codex/Kata-only. Apache 2.0 reference implementation in Elixir. Released April 2026. ([repo](https://github.com/openai/symphony))

3. **claude-flow / Ruflo (ruvnet)** — match 8/10. By far the largest Claude-native swarm OSS (34.1k stars). Hierarchical/mesh/adaptive topologies, 100+ specialized agents, consensus protocols (Raft/Byzantine/Gossip), shared memory/RAG, multi-provider routing. No Kanban UI but the orchestration substrate is the deepest in the space. If CodeBoard is the *interface*, claude-flow is the *engine* others bolt to. ([repo](https://github.com/ruvnet/claude-flow))

Honorable mentions for "very close": **Composio Agent Orchestrator** (autonomous PR lifecycle, web dashboard), **Emdash** (24-CLI ticket-driven IDE w/ Linear+Jira+GitHub), **ClawTeam** (HKUDS — leader spawns workers with dependency chains, tmux+web kanban).

---

## 2. Ranked Table (verified 2026-05-01)

| # | Project | Stars | Activity | Match | One-liner |
|---|---------|-------|----------|-------|-----------|
| 1 | Vibe Kanban (BloopAI) | 25.7k | Apr 24 2026 (sunsetting) | 9 | Kanban + parallel agents per worktree, 10+ CLIs |
| 2 | OpenAI Symphony | ~20k | Apr 2026, fresh | 8 | Linear-board → autonomous coding agents, prove work via CI+PR |
| 3 | claude-flow / Ruflo | 34.1k | v3.6.10 Apr 30 2026 | 8 | Mesh/hierarchical Claude swarm, 100+ agents, consensus |
| 4 | Composio Agent Orchestrator | 6.7k | Mar 29 2026 | 8 | Parallel agents, autonomous CI fix + PR review loop, web UI |
| 5 | Emdash | 4.2k | v1.1.5 Apr 30 2026 | 8 | Agentic dev env, 24 CLIs, Linear/GitHub/Jira ticket integration |
| 6 | ClawTeam (HKUDS) | 5.1k | v0.2.0 Mar 23 2026 | 8 | Leader spawns worker swarm w/ dependency chains, tmux + web kanban |
| 7 | OpenHands (All-Hands-AI) | 72.4k | v1.6.0 Mar 30 2026 | 7 | Autonomous SWE agent w/ delegation, REST+SPA UI, used in production |
| 8 | MetaGPT | 67.6k | v0.8.1 Apr 2024 ⚠️stale | 7 | "Software company as agents" — PM/architect/eng SOPs, one-line→repo |
| 9 | Roo Code | 23.8k | v3.53.0 Apr 23 2026 | 7 | VS Code multi-mode (Code/Architect/Debug/Ask) |
| 10 | Microsoft Agent Framework | 10k | 1.2.2 Apr 29 2026 | 7 | Sequential/concurrent/handoff/group/Magentic-One topologies + DevUI |
| 11 | Sculptor (Imbue) | 0.15k | active beta 2026 | 7 | Containerized parallel Claudes, pairing-mode IDE sync |
| 12 | Conductor (Melty Labs) | n/a (closed-src Mac app) | 2026 | 7 | Mac dashboard for multiple parallel Claude Code agents |
| 13 | CrewAI | 50.4k | 1.14.4 Apr 30 2026 | 6 | Role-based "crews" + flows, AMP control plane |
| 14 | claude-squad (smtg-ai) | 7.2k | 1.0.17 Mar 12 2026 | 6 | Terminal multiplexer (tmux+worktrees) for N Claude/Codex/Aider |
| 15 | LangGraph | 30.9k | 1.2.0a2 Apr 30 2026 | 6 | Graph-based stateful orchestration; Studio UI via LangSmith |
| 16 | OpenManus (FoundationAgents) | 56k | v0.3 Apr 2025 ⚠️slowing | 6 | OSS Manus clone, multi-agent flow, browser+data agents |
| 17 | Agent Zero | 17.4k | v1.10 Apr 28 2026 | 6 | Hierarchical subordinate-spawning agent, web canvas UI |
| 18 | ChatDev 2.0 | 32.9k | v2.2.0 Mar 23 2026 | 6 | Zero-code multi-agent platform w/ workflow canvas, RL orchestrator |
| 19 | Kilo Code | 18.8k | v7.2.31 Apr 29 2026 | 6 | Multi-mode VS Code agent (Architect/Coder/Debugger/Orchestrator) |
| 20 | opcode (winfunc) | 21.7k | active 2026 | 6 | Tauri desktop GUI for Claude Code, custom+background agents |
| 21 | AutoGen (Microsoft) | 57.6k | py 0.7.5 Sep 30 2025 ⚠️maintenance | 5 | Original conversable-agents framework; superseded by MS Agent Framework |
| 22 | AG2 (autogen fork) | 4.5k | 0.12.1 Apr 24 2026 | 5 | AutoGen fork by original authors; swarms/group/nested chats |
| 23 | SWE-agent | 19.1k | 1.1.0 May 2025 | 4 | Single agent → fix one GH issue; SWE-bench SoTA, not multi-agent |
| 24 | Cline | 61.2k | 3.81.0 Apr 24 2026 | 4 | Single-agent VS Code extension, plan-and-act |
| 25 | Devika | 19.5k | active early-stage 2026 | 4 | OSS Devin-clone; v2 ("Opcode") teased; experimental |
| 26 | bolt.diy (StackBlitz Labs) | high | active 2026 | 4 | Open fork of bolt.new — chat→full-stack web app, single agent |
| 27 | GPT Pilot (Pythagora) | 33.8k | not maintained ⚠️ | 3 | 11-role multi-agent app generator; team moved to commercial Pythagora |
| 28 | gpt-engineer | ~55k | not maintained ⚠️ | 2 | Historical; team moved to Lovable |
| 29 | smol-developer | ~12k | not maintained ⚠️ | 2 | Historical |
| 30 | AutoGPT / BabyAGI / AgentGPT | various | experimental, stale-ish | 2 | Historical 2023 hype-cycle agents |

---

## 3. Detailed Cards

### 1. Vibe Kanban — BloopAI
- **Pitch:** Kanban board + parallel coding agents per task; the spiritual ancestor of CodeBoard.
- **Link:** https://github.com/BloopAI/vibe-kanban
- **Stars / momentum:** 25.7k / 2.6k forks. 2,070 commits. v0.1.44 Apr 24 2026. **Repo carries a sunsetting notice** — the project is being wound down; treat as "prior art frozen in late form."
- **Architecture:** Rust backend (50.3%) + TypeScript frontend (46%). Each ticket gets a workspace with its own git branch, terminal, and dev server. Multi-attempt model: same task can be run by multiple agents in parallel and diffs compared side-by-side. MCP server lets a "planning" ticket auto-decompose into child cards.
- **Comms:** No agent↔agent message bus. Coordination is via the Kanban model and the orchestrator process; agents are mostly isolated workers reading shared cards.
- **Models / agents:** Claude Code, Codex, Gemini CLI, GitHub Copilot, Amp, Cursor, OpenCode, Droid, CCR, Qwen Code (10+).
- **Builds:** Real refactors and feature work in user repos, not toys. Built-in browser w/ devtools and device emulation for review.
- **Killer feature:** "Multiple attempts per ticket" — sample the solution space across models, then merge the winner.
- **UI:** Yes — Kanban + diff review + browser preview + inline comments.
- **Maturity:** Production-grade but going dormant.
- **Match score: 9/10.** This is the public project most architecturally adjacent to CodeBoard. Differences: VK doesn't push the FEATURE→EPIC→STORY→TASK→SUBTASK hierarchy, no QA gate, no AI-driven status cascade.

### 2. OpenAI Symphony
- **Pitch:** Spec + reference implementation that turns a project-management board (Linear) into a control plane for autonomous coding agents.
- **Link:** https://github.com/openai/symphony
- **Stars / momentum:** ~20k / 1.7k. Released April 2026 (this is a mover). Apache 2.0. Elixir 95.5%.
- **Architecture:** Watches a Linear board, every task spawns an isolated agent run, agent produces "proof of work" — CI status, PR feedback, complexity analysis, walkthrough video. v1.1 added Kata CLI runtime (so Claude Code / Gemini are pluggable).
- **Comms:** Board state is the message bus. Agent → board (status, evidence). Human → board (review/approve). No direct agent↔agent chat.
- **Models:** Codex by default, Claude/Gemini via Kata.
- **Builds:** Real PRs in real repos. OpenAI claims 500% increase in landed PRs on internal pilot teams.
- **Killer feature:** Agents must justify their work to the board (CI green + walkthrough video) before a human looks. Reframes the human role from "supervisor" to "merger."
- **UI:** Linear (existing).
- **Maturity:** "Engineering preview for trusted environments" — early but from OpenAI directly, will move fast.
- **Match score: 8/10.** Eli's CodeBoard *is* this concept, except CodeBoard owns the board itself and the board has the right hierarchy. Symphony assumes you already have Linear.

### 3. claude-flow / Ruflo (ruvnet)
- **Pitch:** Largest Claude-native multi-agent orchestration platform.
- **Link:** https://github.com/ruvnet/claude-flow (renamed Ruflo in Jan 2026 to avoid Anthropic trademark, npm/CLI keep `claude-flow` name)
- **Stars / momentum:** 34.1k / 3.9k. v3.6.10 Apr 30 2026 — extremely active.
- **Architecture:** Layered — UI → orchestration (27 hooks) → swarm coordination → 100+ specialized agents → memory/learning → multi-provider routing. Topologies: hierarchical, mesh, adaptive. Consensus mechanisms: Raft, Byzantine, Gossip. Vector memory (HNSW AgentDB), WASM/Rust policy kernels, mTLS zero-trust federation. 32 native Claude Code plugins + 21 npm plugins.
- **Comms:** Real shared memory + federation protocol. Most legitimately "agent mesh" of any project here.
- **Models:** Claude (primary), GPT, Gemini, Cohere, Ollama with intelligent routing+failover.
- **Builds:** Plumbing-level; you compose the agents into apps. Not a one-shot "build me Spotify."
- **Killer feature:** Topology zoo + consensus algorithms — no other OSS framework offers Byzantine consensus over agents.
- **UI:** CLI + Claude Code plugin. No first-party Kanban dashboard.
- **Maturity:** Power-user / enterprise; complex to set up.
- **Match score: 8/10.** Engine, not interface. CodeBoard could *use* claude-flow as its execution substrate.

### 4. Composio Agent Orchestrator
- **Pitch:** Spawn parallel coding agents that own the full PR lifecycle — including fixing CI and answering review comments — without supervision.
- **Link:** https://github.com/ComposioHQ/agent-orchestrator
- **Stars / momentum:** 6.7k / 0.9k. CLI 0.2.2 Mar 29 2026. 1,163 commits.
- **Architecture:** `ao start` → orchestrator spawns workers in isolated git worktrees → workers open PRs → CI failures and review comments are routed back to the agent → human only intervenes for judgment calls. Default 5 concurrent agents.
- **Comms:** Orchestrator dispatches, agents report. PRs and CI logs are the feedback channel.
- **Models / agents:** Claude Code (default), Codex, Aider, Cursor, OpenCode.
- **Builds:** Real PRs across CI/merge-conflict/review cycles.
- **Killer feature:** Autonomous response to review comments. Closes the loop most others leave open.
- **UI:** Web dashboard at `localhost:3000` (status, agent progress, PR readiness).
- **Maturity:** Beta but production-shaped.
- **Match score: 8/10.** Strong overlap with CodeBoard's "AI runs the ticket end-to-end."

### 5. Emdash
- **Pitch:** "Agentic Development Environment" (YC W26). 24 CLI agents in parallel, ticket-driven from Linear/GitHub/Jira.
- **Link:** https://github.com/generalaction/emdash
- **Stars / momentum:** 4.2k / 387. v1.1.5 Apr 30 2026. Active.
- **Architecture:** Each task → isolated git worktree. Unified UI for diffs / tests / PR creation / CI checks / merge.
- **Comms:** No direct agent↔agent messaging; coordination via tickets and worktrees.
- **Models / agents:** 24 incl. Claude Code, Codex, Gemini, Continue, Cline, Cursor, Devin, Copilot, Goose, Kilocode, Rovo Dev.
- **Builds:** Day-to-day team coding work via tickets.
- **Killer feature:** Pass a Linear/Jira/GitHub ticket directly to an agent, review diff, PR, merge — without leaving the app. SSH/SFTP remote dev support.
- **UI:** Yes — full GUI desktop app.
- **Maturity:** Production-shaped early-stage.
- **Match score: 8/10.** Closest to CodeBoard in *workflow*: ticket → agent → diff → merge. Lacks the hierarchical breakdown CodeBoard owns.

### 6. ClawTeam (HKUDS)
- **Pitch:** "One Command → Full Automation." Leader agent self-organizes a team with dependency chains for full-stack tasks.
- **Link:** https://github.com/HKUDS/ClawTeam
- **Stars / momentum:** 5.1k / 684. v0.2.0 Mar 23 2026. 211 commits, active.
- **Architecture:** Leader spawns worker agents in isolated git worktrees + tmux windows, auto-injects coordination prompts so workers know how to message and report. Communication via point-to-point inboxes (file-based or ZeroMQ P2P). TOML team templates.
- **Comms:** Most explicit agent↔agent message bus of the OSS pack — actual P2P transport.
- **Models / agents:** Any CLI agent (Claude Code, Codex, OpenClaw, nanobot, custom scripts). Python 3.10+, tmux required.
- **Builds:** Demo: "Build a full-stack todo app with auth, DB, React" → leader creates dependency-chained tasks (REST schema, JWT, DB layer, React FE, integration tests) and spawns sub-agents for each.
- **Killer feature:** Live tiled tmux dashboard (`board attach`) showing every agent simultaneously. Plus terminal kanban + web kanban (`board serve`).
- **UI:** Terminal kanban + tmux tiled view + web UI.
- **Maturity:** Active alpha. v0.3 roadmap: Redis transport, multi-user.
- **Match score: 8/10.** The most architecturally ambitious match — only one with real agent messaging — but no hierarchy beyond leader→worker.

### 7. OpenHands (All-Hands-AI, formerly OpenDevin)
- **Pitch:** Autonomous SWE generalist agent w/ a delegation primitive.
- **Link:** https://github.com/All-Hands-AI/OpenHands
- **Stars / momentum:** 72.4k / 9.2k. v1.6.0 Mar 30 2026. 6,667 commits. Trusted by TikTok / Amazon / Netflix / Apple / NVIDIA / Google.
- **Architecture:** CodeActAgent (general coder) + BrowserAgent (web). Agents can delegate subtasks via standardized vocabulary. SDK lets you "scale to 1000s of agents in cloud." 1.4 GA on Docker 27.x / macOS Sequoia / Ubuntu 24.04.
- **Comms:** Hierarchical delegation primitives, not free-form chat.
- **Models:** Claude, GPT, any LLM via LiteLLM.
- **Builds:** Real engineering tasks in real repos at named enterprises.
- **Killer feature:** Production credibility + the SDK story (define agents in code, deploy to cloud).
- **UI:** Three: Local GUI (REST + React SPA), OpenHands Cloud, CLI.
- **Maturity:** Production.
- **Match score: 7/10.** More library-level than ticket-driven app. CodeBoard could call OpenHands SDK per ticket.

### 8. MetaGPT (FoundationAgents) ⚠️ stale core, big mindshare
- **Pitch:** "First AI software company" — one-line requirement → PRD, design, tasks, repo.
- **Link:** https://github.com/FoundationAgents/MetaGPT
- **Stars / momentum:** 67.6k / 8.6k. **Latest release v0.8.1 Apr 22, 2024 — over a year old.** Spiritual successor: MGX commercial product.
- **Architecture:** SOP-driven multi-agent (PM, architect, project manager, engineer). Code = SOP(Team).
- **Comms:** Structured message passing along SOPs.
- **Models:** Multi-provider.
- **Builds:** Toy → small-app range; "build a 2048 game" is canonical demo. Brittle on real repos.
- **Killer feature:** Cleanest articulation of "software company as agents."
- **UI:** Hugging Face Space demo. No first-party Kanban.
- **Maturity:** Foundational, no longer cutting edge. Core team's energy is on MGX (closed) and OpenManus.
- **Match score: 7/10.** Conceptual ancestor of Eli's vision but stale code.

### 9. Roo Code
- **Pitch:** "Whole dev team of AI agents in your code editor" — multi-mode VS Code agent.
- **Link:** https://github.com/RooCodeInc/Roo-Code
- **Stars / momentum:** 23.8k / 3.2k. v3.53.0 Apr 23 2026. 7,056 commits.
- **Architecture:** Single agent at a time, switched between five modes: Code / Architect / Ask / Debug / Custom. Forked from Cline.
- **Comms:** Mode-switching, not parallel agents.
- **Models:** OpenAI (GPT-5.5 via Codex), Anthropic Claude (Opus 4.7 via Vertex), MCP servers.
- **Builds:** Day-to-day editor work.
- **Killer feature:** Custom modes — define a domain-specific role.
- **UI:** Inside VS Code.
- **Maturity:** Production.
- **Match score: 7/10.** Same role-based concept as CodeBoard but inside an editor, sequential not parallel.

### 10. Microsoft Agent Framework
- **Pitch:** Successor to AutoGen + Semantic Kernel, GA April 3, 2026.
- **Link:** https://github.com/microsoft/agent-framework
- **Stars / momentum:** 10k / 1.6k. python-1.2.2 Apr 29 2026.
- **Architecture:** Graph-based workflows. Five orchestration patterns: sequential, concurrent, handoff, group chat, **Magentic-One**. Streaming, checkpointing, HITL approvals, pause/resume. A2A + MCP cross-runtime.
- **Comms:** Group-chat and handoff are the closest to "mesh."
- **Models:** Foundry/Azure AI/Azure OpenAI/OpenAI; multi-provider expanding.
- **Builds:** Plumbing; you build apps on top.
- **Killer feature:** Magentic-One pattern (orchestrator + specialists with explicit ledger).
- **UI:** DevUI for testing/debug.
- **Maturity:** Production GA.
- **Match score: 7/10.** Solid substrate; not opinionated about coding workflow.

### 11. Sculptor (Imbue)
- **Pitch:** "Missing UI for parallel coding agents."
- **Link:** https://github.com/imbue-ai/sculptor
- **Stars / momentum:** Only 148 stars / 7 forks. No releases. **But** Imbue is well-funded and the product is real.
- **Architecture:** Each Claude runs in its own Docker container. "Pairing Mode" syncs an agent's branch to the local IDE for live testing.
- **Models:** Claude today; GPT-5 next; Codex added 12/3/25.
- **UI:** Sidebar agent manager + Pairing Mode + merge UI + build logs + context meters.
- **Maturity:** Active beta.
- **Match score: 7/10.** Strong UX angle on parallel agents, weak on tickets/hierarchy.

### 12. Conductor (Melty Labs) — closed-source Mac app
- **Pitch:** Mac dashboard for multiple parallel Claude Code agents with file-claiming + priority gate to prevent race conditions.
- **Link:** https://conductor.build (Mac only, free)
- **Architecture:** Each agent gets isolated codebase copy; centralized status dashboard; file-claim system.
- **UI:** Diff-first review.
- **Maturity:** Free Mac app, popular in 2026 multi-agent benchmarks.
- **Match score: 7/10.** Closed source so excluded from "OSS prior art" but worth knowing the UI patterns.

### 13. CrewAI
- **Pitch:** Role-playing autonomous AI agents working in crews.
- **Link:** https://github.com/crewAIInc/crewAI
- **Stars / momentum:** 50.4k / 6.9k. v1.14.4 Apr 30 2026. 100k+ certified devs via learn.crewai.com.
- **Architecture:** Two layers — *Crews* (autonomous role-based teams) + *Flows* (deterministic event-driven workflow). Sequential and hierarchical processes (manager auto-assigned for delegation).
- **Comms:** Manager-mediated, role-based.
- **Models:** Multi-provider.
- **Builds:** Most demos are non-coding (research, content, trip planning, market analysis).
- **Killer feature:** Crew Control Plane (AMP) — real-time monitoring, tracing, observability dashboard.
- **UI:** AMP Suite (commercial dashboard, free trial).
- **Maturity:** Production.
- **Match score: 6/10.** Strong general agent framework, weaker as a code-generation pipeline specifically.

### 14. claude-squad (smtg-ai)
- **Pitch:** TUI to manage N parallel Claude/Codex/Aider terminal sessions with isolated worktrees.
- **Link:** https://github.com/smtg-ai/claude-squad
- **Stars / momentum:** 7.2k / 512. v1.0.17 Mar 12 2026. Go 89.1%.
- **Architecture:** tmux + git worktrees. No mesh — just N independent sessions.
- **UI:** Terminal TUI.
- **Match score: 6/10.** Lean, popular, but no orchestration intelligence.

### 15. LangGraph
- **Pitch:** Build resilient stateful agents as graphs.
- **Link:** https://github.com/langchain-ai/langgraph
- **Stars / momentum:** 30.9k / 5.3k. 1.2.0a2 Apr 30 2026. LangChain 1.0 now uses LangGraph as its agent runtime.
- **Architecture:** Each agent = graph node with own state, connected via directed edges; supervisor nodes for hierarchical control. Subgraphs.
- **Comms:** Edge transitions = handoffs; shared state in graph.
- **UI:** LangSmith Studio (visualize node states, prototype, replay).
- **Maturity:** Production. Klarna, Replit, Elastic use it.
- **Match score: 6/10.** Best-in-class substrate for stateful multi-agent. Not opinionated about coding.

### 16. OpenManus (FoundationAgents) ⚠️ slowing
- **Pitch:** OSS replica of Manus general agent.
- **Link:** https://github.com/FoundationAgents/OpenManus
- **Stars / momentum:** 56k / 9.8k. **v0.3.0 Apr 2025** — last release a year old. Originally a 3-hour prototype by MetaGPT folks.
- **Architecture:** Standard agent + DataAnalysis agent + experimental multi-agent flow.
- **Match score: 6/10.** Big stars, weak recent activity.

### 17. Agent Zero (agent0ai)
- **Pitch:** Agent that runs in its own VM and can spawn subordinate agents recursively.
- **Link:** https://github.com/agent0ai/agent-zero
- **Stars / momentum:** 17.4k / 3.6k. v1.10 Apr 28 2026. 2,018 commits.
- **Architecture:** Hierarchical — every agent can create subordinates with their own prompts/tools/sandbox.
- **UI:** "Universal Canvas" web UI w/ shared work surfaces, browser annotations, Office docs, file browser.
- **Match score: 6/10.** Hierarchy is right but not dev-specific.

### 18. ChatDev 2.0 (OpenBMB)
- **Pitch:** Zero-code multi-agent platform for "developing everything."
- **Link:** https://github.com/OpenBMB/ChatDev
- **Stars / momentum:** 32.9k / 4.1k. v2.2.0 Mar 23 2026.
- **Architecture:** v1 was CEO/CTO/Programmer SOP. v2 introduces a *learnable RL orchestrator* (NeurIPS 2025) and *MacNet* (DAGs of agents).
- **UI:** Web console — Tutorial / Workflow drag-and-drop canvas / Launch w/ live logs + HITL.
- **Builds:** Data viz, 3D (Blender), games, deep research, edu video.
- **Match score: 6/10.** Visual workflow design is interesting; less ticket-driven.

### 19. Kilo Code
- **Pitch:** Hybrid of Cline + Roo Code with Orchestrator mode coordinating Architect/Coder/Debugger.
- **Link:** https://github.com/Kilo-Org/kilocode
- **Stars / momentum:** 18.8k / 2.5k. v7.2.31 Apr 29 2026. $8M seed late 2025.
- **Architecture:** Multi-mode VS Code agent. Orchestrator mode chains the others.
- **Models:** 500+ via unified gateway (Gemini 3.1 Pro, Claude 4.6/4.7, GPT-5.4).
- **Match score: 6/10.** Sequential orchestration inside an editor.

### 20. opcode (winfunc)
- **Pitch:** Tauri desktop GUI + toolkit for Claude Code; create custom agents and run them in background.
- **Link:** https://github.com/winfunc/opcode
- **Stars / momentum:** 21.7k / 1.7k. **v0.2.0 Aug 31 2025** — release cadence has slowed but still 265 open issues / active community.
- **UI:** Visual project browser, session history, real-time CLAUDE.md editor, analytics dashboard.
- **Match score: 6/10.** Stronger as Claude Code companion than as a multi-agent mesh.

### 21. AutoGen (Microsoft) ⚠️ maintenance
- **Pitch:** Original conversable-agents framework.
- **Link:** https://github.com/microsoft/autogen
- **Stars / momentum:** 57.6k / 8.7k. python-v0.7.5 Sep 30 2025. **Repo banner: maintenance mode, use Microsoft Agent Framework.**
- **UI:** AutoGen Studio (no-code GUI prototyping; not production).
- **Match score: 5/10.** Historical, but worth reading the conversable-agent papers.

### 22. AG2 (autogen fork by original creators)
- **Pitch:** Continuation of AutoGen by Chi Wang / Qingyun Wu after they left Microsoft.
- **Link:** https://github.com/ag2ai/ag2
- **Stars / momentum:** 4.5k / 599. v0.12.1 Apr 24 2026. AG2 Beta is the v1 redesign.
- **Architecture:** Swarms / group chats / nested chats / sequential chats / custom replies. Streaming, DI, typed tools.
- **Match score: 5/10.** Library-level; not coding-pipeline-shaped.

### 23. SWE-agent (Princeton + Stanford)
- **Pitch:** SoTA single agent on SWE-bench, fixes one GitHub issue at a time.
- **Link:** https://github.com/SWE-agent/SWE-agent
- **Stars / momentum:** 19.1k / 2.1k. **1.1.0 May 2025** (a year old, but SWE-bench cycles slow).
- **Architecture:** Single agent, custom Agent-Computer Interface. Mini-SWE-Agent variant scores >74% on SWE-bench Verified in 100 lines of Python.
- **Match score: 4/10.** Single-agent — included for benchmark reference, not architectural prior art.

### 24. Cline
- **Pitch:** Autonomous coding agent in VS Code with HITL approval.
- **Link:** https://github.com/cline/cline
- **Stars / momentum:** 61.2k / 6.3k. v3.81.0 Apr 24 2026.
- **Architecture:** Single agent. Plan-then-act.
- **Models:** Most providers + local via Ollama/LM Studio.
- **Match score: 4/10.** Single-agent; ancestor of Roo and Kilo, included for context.

### 25. Devika ⚠️ early
- **Pitch:** OSS Devin clone.
- **Link:** https://github.com/stitionai/devika
- **Stars / momentum:** 19.5k / 2.6k. **No releases**, 186 commits. Devs say "v2 is Opcode."
- **Match score: 4/10.** Hyped at launch, didn't mature.

### 26. bolt.diy (StackBlitz Labs)
- **Pitch:** OSS fork of bolt.new — chat → full-stack web app, BYO API key.
- **Link:** https://github.com/stackblitz-labs/bolt.diy
- **Architecture:** Single agent driving WebContainer; not a mesh.
- **Match score: 4/10.** Closer to the *user-facing UX* of bolt.new/v0/Lovable than to a multi-agent mesh.

### 27. GPT Pilot (Pythagora) ⚠️ not maintained
- **Pitch:** 11-role multi-agent app generator (Product Owner / Spec Writer / Architect / Tech Lead / Dev / Code Monkey / Reviewer / Troubleshooter / Debugger / Tech Writer).
- **Link:** https://github.com/Pythagora-io/gpt-pilot
- **Status:** **Repo banner: not maintained anymore. Use Pythagora.ai (commercial).**
- **Match score: 3/10.** Ideologically very close to CodeBoard (11 roles!) but the OSS is dead.

### 28-30. AutoGPT / BabyAGI / AgentGPT / gpt-engineer / smol-developer
- **Status:** All historical 2023-era hype cycle. Stars high, real usage near zero. AutoGPT pivoted to "AI agent platform" (commercial). gpt-engineer team → Lovable. smol-developer not maintained.
- **Match score: 2/10.** Worth a paragraph in a history section, not a model to copy.

---

## 4. Patterns Observed

**Universal architecture choices in active 2026 projects:**

1. **Git worktree per agent** is now the standard isolation primitive. Every serious project (Vibe Kanban, Symphony, Composio AO, Emdash, ClawTeam, Sculptor, claude-squad, Cursor 2.0) uses worktrees or Docker containers per agent. **This is non-negotiable in the space now.**

2. **The board IS the message bus.** The trend — strongest in Symphony and Vibe Kanban — is that you don't build agent↔agent chat. You make tickets the source of truth, agents read+write tickets, and that emergently coordinates them. ClawTeam is the dissenting voice with real P2P (ZeroMQ), but it's the exception.

3. **Convergence on CLI agents as the unit of execution.** Vibe Kanban / Emdash / Composio AO / Conductor / Sculptor / claude-squad all wrap *external* coding CLIs (Claude Code, Codex, Cursor, Aider, Gemini CLI) rather than implementing the coder themselves. The coder is now a commodity; the orchestration around it is the product.

4. **"Proof of work" before review.** Symphony, Composio AO, and Vibe Kanban all push the agent to produce CI-green + diff + walkthrough/comment-thread *before* a human looks. The 2024 pattern of "agent asks for approval every 3 lines" is dead.

5. **Multi-attempt sampling.** Vibe Kanban (multiple attempts per ticket, compare diffs) is the freshest idea — treat code generation as sampling, not summoning. Cursor 2.0 also adopted this (8 parallel agents on one prompt).

**Where everyone fails:**

- **Hierarchical work breakdown is missing.** No project surveyed implements FEATURE→EPIC→STORY→TASK→SUBTASK as a first-class concept. Vibe Kanban's MCP planner can decompose a planning ticket into child cards, but it's flat. Symphony assumes Linear gives you the hierarchy. **This is CodeBoard's clearest architectural moat.**

- **No QA gate as a separate cycle.** Most projects ship `agent → PR → human merge`. None has an explicit `COMPLETED_WAITING_QA → DONE` state with QA agents owning the verification. CodeBoard's QA Board is genuinely uncommon.

- **Status-cascade across hierarchy is unsolved.** Eli's "completing a child cascades DONE up if all siblings are done; starting a leaf cascades IN_PROGRESS up to the container" is missing from every framework. They have flat statuses.

- **Real agent↔agent messaging is rare.** Only ClawTeam (ZeroMQ P2P) and claude-flow (federation protocol) actually have it. Most projects fake it via shared state or a supervisor pattern. The "mesh" framing in marketing is mostly aspirational.

- **Opinion on what to build is missing.** MetaGPT/ChatDev had it ("we are a software company"), the new wave is more substrate-agnostic. The interesting framing — "we have a Jira-like board and the board is alive" — is barely explored.

- **The ones that try to "build anything" hit toy ceilings.** MetaGPT, ChatDev, OpenManus, GPT Pilot all demo well on small things (2048, todo apps, landing pages) and break on production codebases. The successful 2026 projects (OpenHands, Composio AO, Symphony, Vibe Kanban) deliberately scope to *one ticket on an existing codebase* and let the human compose tickets into apps.

---

## 5. Gaps Eli's Project Could Exploit

These are concrete white-space opportunities verified to be open as of 2026-05-01:

1. **Hierarchical work breakdown as a first-class data model.** Nobody else has FEATURE→EPIC→STORY→TASK→SUBTASK natively. Most frameworks either go flat (Vibe Kanban, Symphony) or assume an external Jira/Linear (Symphony). Owning the hierarchy lets CodeBoard do things others can't:
   - AI breakdown of a Feature into Epics/Stories/Tasks before any code is written
   - Status cascades (parent IN_PROGRESS when any child is, parent DONE when all children are)
   - Automatic regression detection when a child fails (the CB-1952 commit confirms this is already implemented)

2. **QA Board as a separate execution graph.** No surveyed OSS project has a `COMPLETED_WAITING_QA` state with QA agents that own verification, and a separate kanban for QA tasks. Eli has one. This is differentiation.

3. **AI-driven breakdown loop.** `POST /api/ai/breakdown/{id}` is conceptually sharper than anyone else's flow. MetaGPT generates docs *and then* code; CodeBoard generates a *board* and then runs agents per item. The board-mediated flow is more debuggable and more rebrandable as "PM tooling for humans + AI."

4. **Floating execution status overlay.** Eli's `FloatingAgentStatusBar` (z-[60]) pattern — agent status visible during AutoPilot — is something nobody else has. Sculptor has agent sidebar; Conductor has dashboard; nobody has *contextual* execution overlays inside the planning UI itself.

5. **Multi-agent QA gate before DONE.** This is the obvious next step that none of the surveyed projects do: spawn QA agent(s) when a ticket hits `COMPLETED_WAITING_QA`, have them write+run regression tests against the diff, and only auto-promote to `DONE` if the QA passes. Symphony has "proof of work" but no parallel QA-agent verifier.

6. **Real agent↔agent communication, but scoped to ticket dependencies.** ClawTeam has P2P agent messaging but no hierarchy. Eli could implement: "TASK B depends on TASK A — when A's agent finishes, send a structured handoff message (interface contract, schema, decisions made) to B's agent before it starts." This is a feature only one other project (ClawTeam) has even attempted, and they don't tie it to ticket structure.

7. **Per-issue session isolation as the unit of execution.** Eli's `terminal_service.py` spawning Claude Code per ticket is exactly Symphony's model — but Symphony is Codex/Kata-only. Being Claude-Code-first with a multi-agent QA gate plus the hierarchical breakdown is uncopied territory.

8. **Bug-as-first-class-issue-type with auto-CodeBoard-creation.** From the project's recent commits (CB-1942 "show BUG-type issues in QA Board", CB-1944 kanban per status), bug triage is already wired into the same execution pipeline. None of the surveyed projects treat bugs and feature work as the same agent-executable primitive.

**Strategic positioning:**

The surveyed market splits into:
- **Substrates** (claude-flow, LangGraph, MS Agent Framework, AG2, CrewAI) — composable libraries.
- **Editor-bound agents** (Cline, Roo, Kilo, Cursor, Continue) — single-developer tools.
- **Parallel-agent shells** (claude-squad, Conductor, Sculptor, Vibe Kanban, Emdash, Composio AO) — N agents with coordination UI.
- **Software-company simulators** (MetaGPT, ChatDev, GPT Pilot, OpenManus) — opinionated but stuck on toys.

CodeBoard sits between (3) and (4) but with an **opinion that nobody else has shipped**: *the project board is the program*. The board's hierarchy is the program structure; agents execute against the AST that is the board; QA is a separate verifier sub-board. That framing — and the hierarchical status cascade plus QA gate — is white space.

The competitive risk is Symphony (OpenAI-backed, fresh, well-funded). It will get a hierarchy soon. Eli's window to ship the differentiator (hierarchical AI breakdown + QA Board + Claude-native execution) and own a niche is roughly the next two quarters.
