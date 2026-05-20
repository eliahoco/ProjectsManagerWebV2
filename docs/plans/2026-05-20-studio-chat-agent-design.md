# Studio Chat Agent — Architecture Design
## AI Chat Planning Agent for the Feature Studio View (CB-2384)

**Date:** 2026-05-20
**Author:** LLM Architect
**Status:** DESIGN v1.0 — pending review before CodeBoard push
**Parent plan:** `2026-05-07-ai-project-workspace-master-plan.md`
**Target issue:** CB-2384 (AI Project Workspace — Studio view)

---

## 0. Context Anchor

The Feature Studio is a chat-based planning surface where a user types "I want to build X" and emerges with a reviewed, hierarchical work breakdown (FEATURE → EPIC → STORY → TASK → SUBTASK) that can be pushed to CodeBoard and handed to AutoPilot. The agent powering this surface is called Jonny — an orchestrator persona who clarifies, delegates to sub-agents (researcher, designer, breakdown-writer), produces artifacts, and drives the planning conversation to a commit-ready output.

The existing platform uses:
- `AIService` — synchronous Anthropic SDK client + Ollama fallback for JSON generation tasks
- `terminal_service` — Claude Code CLI subprocess (PTY) for code execution tasks
- `autopilot_queue_service` — sequential queue with crash recovery, token-exhaustion detection, and audit log

This design builds Jonny on top of the Anthropic Messages API (not the CLI subprocess), reuses the autopilot audit-log pattern, and introduces a new persistence model suited for cloud/Postgres deployment.

---

## 1. Conversation Architecture

### The Three Options

**Option A — Claude Code CLI subprocess (extend terminal_service)**

The existing pattern in `terminal_service.py` spawns `claude -p "..." --output-format stream-json` as a PTY subprocess. The Studio plan document (Ch. 3) initially proposed this: one Claude Code subprocess per conversation tab, streaming `stream-json` events.

Trade-offs:
- Pro: reuses battle-tested code, subprocess isolation is already implemented, `stream-json` parsing is already in place, tool-use visible through existing `inTool` parsing
- Pro: Claude Code's built-in tools (bash, read, write) are useful for repo introspection
- Con: **catastrophically wrong for multi-tenant SaaS.** PTY subprocesses are localhost-only. They cannot survive replica restarts or multi-instance deployments. Session state lives in Python process memory — if the process dies, the conversation dies. There is no clean way to share subprocess I/O across replicas.
- Con: Each active conversation tab holds a PTY subprocess open. At 50 concurrent tenants with 3 tabs each, that is 150 live processes. Process management becomes the reliability bottleneck.
- Con: Token-exhaustion recovery requires the complex crash-recovery machinery that already exists in `autopilot_queue_service.py` — correct for a task queue, overly complex for a planning chat.
- Con: Streaming Claude Code CLI output requires re-parsing `stream-json` events which has known edge cases (the existing `_EXHAUSTION_SIGNAL_RE` patterns are a maintenance burden).

**Option B — Anthropic Messages API with streaming (direct)**

Call `anthropic.messages.stream()` directly, using the Messages API's native tool-use protocol. Conversation history is maintained in the database; each user turn fetches the last N messages and sends them as the `messages` array.

Trade-offs:
- Pro: **cloud-native by design.** No subprocess, no PTY. Any replica can continue any conversation — the full context is in the database.
- Pro: Native tool-use with structured `tool_use` content blocks. No regex parsing.
- Pro: Server-Sent Events from FastAPI stream the response token-by-token to the frontend with clean reconnection semantics.
- Pro: Model routing is explicit: pick `claude-opus-4-5` for complex planning turns, `claude-sonnet-4-6` for breakdown generation and sub-agent work, `claude-haiku-3-5` for fast clarifications and cost attribution queries.
- Pro: Prompt caching is directly supported via the `cache_control` parameter — the system prompt and static planning documents can be cached for up to 5 minutes (ephemeral) or across turns via extended caching.
- Con: No access to Claude Code's built-in bash/file tools without custom tool implementations.
- Con: Requires implementing sub-agent spawning as a custom orchestration layer.

**Option C — Anthropic Managed Agents API**

Anthropic's agents framework manages the agent loop, tool-call execution, and multi-turn conversation natively.

Trade-offs:
- Pro: Reduces orchestration boilerplate; Anthropic handles the tool-call loop
- Pro: Potentially better sub-agent coordination primitives as the API matures
- Con: As of mid-2026, the Managed Agents API is not fully GA and documentation is sparse. Binding core product infrastructure to a pre-GA API is a SaaS shipment blocker.
- Con: Less control over token budgeting, prompt caching strategy, and cost attribution — all of which are non-negotiables in this design.
- Con: Multi-tenant isolation and usage metering require custom middleware regardless, eliminating the main benefit.

### Recommendation: Option B — Anthropic Messages API with streaming

Jonny runs as a persistent conversation managed by the Anthropic Messages API. Each user turn:
1. Fetches conversation history from Postgres (last N messages, within token budget)
2. Calls `anthropic.messages.stream()` with the assembled message list and tool definitions
3. Streams tokens to the frontend via SSE
4. On `tool_use` content blocks, executes the tool (which may spawn a sub-agent)
5. Appends both the assistant message and tool result to the DB before the next turn

Sub-agents (researcher, designer, breakdown-writer) are invoked as nested API calls within the tool execution path — each gets a fresh context window and returns a compact artifact that Jonny synthesizes. They are not separate subprocess sessions; they are API calls gated behind a tool definition.

This is the **Blueprint state machine** pattern from the master plan: the outer Jonny loop is an API-driven agent loop; each sub-agent invocation is a deterministic dispatch with an agentic body.

---

## 2. Persistence Model

Everything is stored write-through to Postgres. No in-memory state survives a restart. Schema is designed for multi-tenant cloud deployment (Postgres, not SQLite).

### Core Tables

```sql
-- Tenant isolation anchor
CREATE TABLE studio_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,           -- hard partition boundary
    project_id      TEXT NOT NULL,           -- FK to projects table
    title           TEXT NOT NULL DEFAULT 'New Conversation',
    state           TEXT NOT NULL DEFAULT 'active',
                    -- active | hibernated | archived | promoting
    planning_state  JSONB,                   -- structured planning progress
                    -- {phase: 'clarifying'|'drafting'|'reviewing'|'approved',
                    --  clarifications_answered: int,
                    --  hierarchy_draft: {...},
                    --  artifact_ids: [...]}
    agent_template_id UUID NOT NULL,         -- FK to agent_templates (Jonny version)
    token_budget    INTEGER NOT NULL DEFAULT 50000,  -- per-session budget
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    hibernated_at   TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ,
    CONSTRAINT fk_tenant CHECK (tenant_id != '')
);

CREATE INDEX idx_studio_sessions_tenant ON studio_sessions(tenant_id);
CREATE INDEX idx_studio_sessions_project ON studio_sessions(project_id);

-- Full conversation message log
CREATE TABLE studio_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES studio_sessions(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL,           -- denormalized for query performance
    sequence        INTEGER NOT NULL,        -- ordering within session
    role            TEXT NOT NULL,           -- user | assistant | tool_result
    content         JSONB NOT NULL,          -- Anthropic content block format
                    -- [{type: 'text', text: '...'} | {type: 'tool_use', ...} | ...]
    agent_name      TEXT,                    -- null for user, 'jonny'|'researcher'|... for assistant
    model           TEXT,                    -- which model generated this message
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cached_tokens   INTEGER,                 -- prompt cache hits
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_studio_messages_session ON studio_messages(session_id, sequence);
CREATE INDEX idx_studio_messages_tenant ON studio_messages(tenant_id, created_at);

-- Tool call executions (sub-agent invocations, CodeBoard pushes, etc.)
CREATE TABLE studio_tool_calls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES studio_sessions(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL,
    message_id      UUID REFERENCES studio_messages(id),
    tool_name       TEXT NOT NULL,
    tool_use_id     TEXT NOT NULL,           -- Anthropic tool_use block id
    input           JSONB NOT NULL,
    output          JSONB,                   -- null until completed
    status          TEXT NOT NULL DEFAULT 'pending',
                    -- pending | running | completed | failed
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER
);

CREATE INDEX idx_studio_tool_calls_session ON studio_tool_calls(session_id);

-- Sub-agent runs spawned by tool calls
CREATE TABLE studio_subagent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES studio_sessions(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL,
    tool_call_id    UUID NOT NULL REFERENCES studio_tool_calls(id),
    agent_type      TEXT NOT NULL,           -- researcher | designer | breakdown_writer | auditor
    model           TEXT NOT NULL,
    system_prompt   TEXT NOT NULL,
    input_messages  JSONB NOT NULL,          -- fresh context sent to sub-agent
    output_artifact JSONB,                   -- compact 1-2K artifact returned
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cached_tokens   INTEGER,
    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_studio_subagent_runs_session ON studio_subagent_runs(session_id);
CREATE INDEX idx_studio_subagent_runs_tool_call ON studio_subagent_runs(tool_call_id);

-- Artifacts produced (rendered in preview pane)
CREATE TABLE studio_artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES studio_sessions(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL,
    kind            TEXT NOT NULL,           -- markdown | mermaid | code | html | hierarchy_json
    label           TEXT,                    -- human-readable tab label
    payload         TEXT NOT NULL,           -- raw artifact content
    metadata        JSONB,                   -- {language, filename, version, ...}
    source_agent    TEXT,                    -- which agent produced this
    source_tool_call_id UUID REFERENCES studio_tool_calls(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by   UUID REFERENCES studio_artifacts(id)  -- versioning
);

CREATE INDEX idx_studio_artifacts_session ON studio_artifacts(session_id);

-- Hierarchy drafts (structured planning output, separate from raw artifacts)
CREATE TABLE studio_hierarchy_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES studio_sessions(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    title           TEXT NOT NULL,
    hierarchy       JSONB NOT NULL,          -- full FEATURE→EPIC→STORY→TASK→SUBTASK tree
    validation_errors JSONB,                 -- null if valid
    approved_at     TIMESTAMPTZ,
    approved_by     TEXT,                    -- user identifier
    promoted_at     TIMESTAMPTZ,
    promoted_issue_id TEXT,                  -- CodeBoard issue key after promotion
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_studio_hierarchy_drafts_session ON studio_hierarchy_drafts(session_id);

-- Agent activity log (Visibility Principle: no DB row = no dispatch)
CREATE TABLE studio_agent_activity (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES studio_sessions(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    verb            TEXT NOT NULL,           -- notify | request | delegate | broadcast
    from_agent      TEXT NOT NULL,
    to_agent        TEXT NOT NULL,
    payload_summary TEXT,                    -- <=200 chars, redacted
    chain_depth     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'dispatched',
                    -- dispatched | running | completed | failed
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_studio_agent_activity_session ON studio_agent_activity(session_id);

-- Per-tenant token usage metering (for SaaS billing)
CREATE TABLE tenant_token_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    session_id      UUID REFERENCES studio_sessions(id),
    date            DATE NOT NULL DEFAULT CURRENT_DATE,
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cached_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd_micro  BIGINT NOT NULL DEFAULT 0,  -- cost in millionths of USD
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tenant_token_usage_tenant_date ON tenant_token_usage(tenant_id, date);

-- Agent templates (versioned; source of truth for system prompts)
CREATE TABLE agent_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,           -- jonny | researcher | designer | breakdown_writer
    version         TEXT NOT NULL,           -- semver e.g. "1.2.0"
    system_prompt   TEXT NOT NULL,
    capabilities    JSONB,                   -- list of tool names this template gets
    model_default   TEXT NOT NULL,           -- which model this template uses by default
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name, version)
);

-- Per-session agent instances (accumulatedMemory, overrides)
CREATE TABLE agent_instances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES studio_sessions(id) ON DELETE CASCADE,
    template_id     UUID NOT NULL REFERENCES agent_templates(id),
    accumulated_context TEXT,               -- session-level memories Jonny has built
    overrides       JSONB,                  -- per-session model or tool overrides
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Key design decisions

- `tenant_id` is denormalized into every table that will be queried per-tenant. This avoids joins and enables row-level security policies in Postgres if needed.
- `studio_messages.content` stores the raw Anthropic content block format (JSONB). This means conversation reconstruction for replay is a simple SELECT, not a format conversion.
- `studio_tool_calls` is persisted before the tool executes (status = 'pending'). After execution, status transitions to 'completed' or 'failed'. This satisfies the Visibility Principle: the UI can show "Jonny is calling researcher" before the result arrives, and a crash mid-execution is visible as a 'pending' row.
- Token tracking is split: per-message detail in `studio_messages`, daily aggregate in `tenant_token_usage`. The aggregate table is what the billing layer reads; it is updated by an async write after each message.
- `studio_hierarchy_drafts` is separate from `studio_artifacts` because it has its own lifecycle (versioning, approval gate, promotion). An artifact is a rendered preview; a hierarchy draft is a business entity that may become CodeBoard issues.

---

## 3. Sub-Agent Spawning

### Architecture

Jonny has a tool called `spawn_subagent`. When Jonny decides a clarification question is answered and it is time to draft the architecture, it calls `spawn_subagent(agent_type='researcher', task='...')`. This is not a subprocess — it is a synchronous API call to Anthropic's Messages endpoint with a fresh context window, executed within the tool-execution handler.

The orchestration layer is `services/studio_orchestrator.py`. Its job is:

1. Receive a user turn message
2. Assemble the conversation context (messages + agent instance's accumulated context, within token budget)
3. Call Jonny's stream via Messages API
4. Handle `tool_use` blocks as they arrive in the stream
5. For `spawn_subagent` calls, execute the sub-agent synchronously (not as a separate session), persist the result to `studio_subagent_runs`, and return the compact artifact as the `tool_result` block
6. Continue the stream until Jonny's turn is complete
7. Persist the full assistant message to `studio_messages`

### Sub-agent types and their contracts

**Researcher**
- Model: `claude-sonnet-4-6` (cost-efficient, sufficient depth)
- Input: task description + search query hints
- Tools available: `search_codeboard`, `read_repo_file`, `query_rag`
- Output contract: JSONB artifact, maximum 2,000 tokens. Schema: `{summary: str, findings: [{source: str, excerpt: str}], recommended_approach: str}`
- Context isolation: gets only its task description and tool results — never sees the full Jonny conversation history

**Designer**
- Model: `claude-sonnet-4-6`
- Input: feature description + researcher findings artifact
- Tools available: none (pure generation)
- Output contract: JSONB artifact, maximum 2,000 tokens. Schema: `{mermaid_diagram: str, data_model_sketch: str, key_design_decisions: [str]}`

**Breakdown Writer**
- Model: `claude-opus-4-5` for the first draft (quality matters here), `claude-sonnet-4-6` for revisions
- Input: feature description + researcher findings + designer output
- Tools available: `validate_hierarchy_schema`
- Output contract: the full hierarchy tree as JSONB — FEATURE → EPICs → STORYs → TASKs → SUBTASKs

**Auditor** (optional, runs after breakdown writer on high-stakes sessions)
- Model: `claude-sonnet-4-6`
- Input: hierarchy draft
- Output contract: `{issues: [{level: str, message: str, path: str}], approved: bool}`

### Why not reuse autopilot_queue_service?

The AutoPilot queue is designed for sequential execution of already-decided CodeBoard tickets via the Claude Code CLI. Sub-agent spawning in Studio is different:

- Sub-agents run within a single user turn (seconds, not minutes)
- They are stateless API calls, not CLI subprocesses
- They do not need the queue's pause/resume/skip controls
- They are synchronous within the orchestrator's turn processing, not queued for later

The correct integration point with AutoPilot is at the end of the planning conversation: when the user approves the hierarchy, the `hand_to_autopilot` tool calls AutoPilot's existing `create_queue()` API. That is where the two systems connect — not at the sub-agent level.

### GroupQueue mutex

Per the iron law from the master plan, two Studio sessions cannot invoke the same sub-agent type simultaneously for the same session. This prevents Jonny from double-spawning a researcher while the first one is still running.

Implemented as an `asyncio.Lock` keyed by `(session_id, agent_type)` in the orchestrator's in-memory lock registry. Because sessions are now multi-replica-safe (state is in Postgres), the in-memory lock is only needed within a single replica. If multi-replica coordination is required (active session can migrate between replicas), upgrade to a Redis SETNX lock with a TTL of 120 seconds.

---

## 4. Streaming and Live Activity

### Protocol: SSE (Server-Sent Events), not WebSockets

SSE is the correct choice for this use case:

- The communication is unidirectional from server to client during a model turn (user sends a message, then listens for the response stream)
- SSE has native browser reconnection via `EventSource` API — if the connection drops, the browser retries automatically with `Last-Event-ID`
- SSE is compatible with HTTP/2 multiplexing — multiple SSE channels from the same origin share a single TCP connection
- The existing Studio plan already specifies SSE (`/api/studio/sessions/{id}/events`) and the platform already uses SSE in the AutoPilot and execution systems
- WebSockets would require a stateful connection upgrade, complicating load balancer configuration and adding reconnection state management

WebSockets would only be preferable if bidirectional streaming were needed (e.g., the user sending audio while the model responds). That is not this use case.

### Event stream schema

Every event on the SSE channel is a JSON object with a `type` discriminator:

```
data: {"type": "token", "delta": "Here is my", "session_id": "..."}

data: {"type": "tool_call_started", "tool_name": "spawn_subagent",
       "tool_use_id": "...", "agent_type": "researcher",
       "session_id": "...", "activity_id": "..."}

data: {"type": "tool_call_completed", "tool_use_id": "...",
       "agent_type": "researcher", "artifact_preview": "...",
       "duration_ms": 4200, "session_id": "..."}

data: {"type": "artifact_created", "artifact_id": "...",
       "kind": "mermaid", "label": "Architecture Diagram",
       "session_id": "..."}

data: {"type": "hierarchy_draft_ready", "draft_id": "...",
       "version": 1, "session_id": "..."}

data: {"type": "turn_complete", "session_id": "...",
       "input_tokens": 4200, "output_tokens": 1100,
       "cached_tokens": 3800}

data: {"type": "error", "code": "token_budget_exceeded",
       "message": "Session token budget reached", "session_id": "..."}
```

### Reconnection semantics

SSE's `Last-Event-ID` header carries the last event ID the client received. The SSE endpoint on reconnect:
1. Fetches all events for the session with `sequence > last_event_id` from `studio_messages` and `studio_agent_activity`
2. Re-emits them as a catch-up burst before resuming live streaming
3. If the model turn is still in progress (tool_call in 'pending' or 'running' state), it re-subscribes to the ongoing async generator

This means: a browser tab can close and reopen mid-turn and catch up without missing events, as long as the events are persisted (which they are — every `studio_tool_calls` row is written before the tool executes, and every `studio_agent_activity` row is written before Jonny's message claims the dispatch happened).

### Frontend rendering pattern

The frontend uses the `useRef` token buffer pattern established in the master plan: SSE `token` events are appended to `tokenBufferRef.current`, and `setInterval(50ms)` flushes to React state. This prevents 20+ re-renders per second during fast generation.

Agent activity updates use a separate state slice, not the token buffer — they need immediate render to update the AgentCrewPanel.

---

## 5. Tool Integration

Jonny receives the following tool definitions. All tools follow the Anthropic tool-use schema. Tool descriptions are written from Anthropic's guidance: describe when to use the tool, what the agent needs to provide, and what it will get back.

### Tool 1: `ask_clarifying_question`

```json
{
  "name": "ask_clarifying_question",
  "description": "Use this when the user's request is ambiguous and you need a specific answer before you can draft an architecture or breakdown. Do NOT use this more than 3 times in a row without making progress — if you have enough to start, start. Each question should be targeted and answerable in 1-2 sentences.",
  "input_schema": {
    "type": "object",
    "properties": {
      "question": {
        "type": "string",
        "description": "The specific question to ask the user. One question per call."
      },
      "context": {
        "type": "string",
        "description": "Brief explanation of why this answer changes the architecture."
      }
    },
    "required": ["question"]
  }
}
```

Output: the user's answer is provided as the next user turn in the conversation. Jonny does not call a function to get the answer — it comes in the normal conversation flow.

### Tool 2: `spawn_subagent`

```json
{
  "name": "spawn_subagent",
  "description": "Delegate a focused research, design, or breakdown task to a specialist sub-agent. The sub-agent runs in isolation and returns a compact artifact (max 2000 tokens). Use this when you need specialized knowledge you cannot reliably produce yourself (e.g., specific Postgres schema patterns, Mermaid diagram syntax). Do not spawn more than 3 sub-agents per turn.",
  "input_schema": {
    "type": "object",
    "properties": {
      "agent_type": {
        "type": "string",
        "enum": ["researcher", "designer", "breakdown_writer", "auditor"]
      },
      "task": {
        "type": "string",
        "description": "Precise task for the sub-agent. Include all context the sub-agent needs — it does not see the main conversation history."
      },
      "context_artifacts": {
        "type": "array",
        "items": {"type": "string"},
        "description": "List of artifact IDs from previous sub-agent runs that the new sub-agent should receive as input."
      }
    },
    "required": ["agent_type", "task"]
  }
}
```

Output: the compact JSONB artifact from the sub-agent, as a tool_result block.

### Tool 3: `search_codeboard`

```json
{
  "name": "search_codeboard",
  "description": "Search existing CodeBoard issues in a project for context. Use this before drafting a breakdown to understand what similar work has already been done or planned.",
  "input_schema": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "query": {"type": "string", "description": "Free-text search query."},
      "issue_types": {
        "type": "array",
        "items": {"type": "string", "enum": ["FEATURE", "EPIC", "STORY", "TASK", "SUBTASK"]},
        "description": "Filter by issue type. Omit for all types."
      },
      "limit": {"type": "integer", "default": 10}
    },
    "required": ["project_id", "query"]
  }
}
```

Output: `{issues: [{key: str, title: str, type: str, status: str, summary: str}]}`

Implementation: calls the existing `GET /api/issues/{project_id}?search=...` endpoint internally.

### Tool 4: `read_repo_file`

```json
{
  "name": "read_repo_file",
  "description": "Read the content of a specific file in the project repository. Use this to understand existing architecture (e.g., read backend/models/issue.py to see the current data model before proposing schema changes). The path must be relative to the project root.",
  "input_schema": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "file_path": {
        "type": "string",
        "description": "Relative path from the project root. E.g., 'backend/models/issue.py'."
      }
    },
    "required": ["project_id", "file_path"]
  }
}
```

Output: `{content: str, line_count: int, truncated: bool}` (content capped at 8,000 characters).

Security gate: the tool implementation validates the path against an allowlist of project roots. Path traversal attempts (`../`) are rejected with a structured error.

### Tool 5: `query_rag`

```json
{
  "name": "query_rag",
  "description": "Query the RAG vector store for semantically relevant context about this project. Use this when you need pattern references or prior decisions that may not be findable with keyword search.",
  "input_schema": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string"},
      "query": {"type": "string"},
      "top_k": {"type": "integer", "default": 5, "maximum": 20}
    },
    "required": ["project_id", "query"]
  }
}
```

Output: `{results: [{text: str, score: float, source: str}]}`

### Tool 6: `create_artifact`

```json
{
  "name": "create_artifact",
  "description": "Render a structured artifact for display in the preview pane. Use this when you have produced content (a Mermaid diagram, a code snippet, a markdown document, or an HTML preview) that the user should see rendered, not just as chat text.",
  "input_schema": {
    "type": "object",
    "properties": {
      "kind": {
        "type": "string",
        "enum": ["markdown", "mermaid", "code", "html", "hierarchy_json"]
      },
      "label": {"type": "string", "description": "Human-readable label for the preview pane tab."},
      "content": {"type": "string", "description": "The full artifact content."},
      "language": {"type": "string", "description": "Code language if kind=code (e.g., 'python', 'sql')."}
    },
    "required": ["kind", "label", "content"]
  }
}
```

Output: `{artifact_id: str, preview_url: str}`. The `artifact_id` is stored in `studio_artifacts` and the SSE channel emits an `artifact_created` event that triggers the frontend preview pane to reveal.

### Tool 7: `push_hierarchy_draft`

```json
{
  "name": "push_hierarchy_draft",
  "description": "Save the current hierarchy breakdown as a draft for user review. Call this when you have a complete FEATURE → EPIC → STORY → TASK hierarchy that you believe is ready for the user to review and approve. Do not call this until you have at least one EPIC with at least two STORYs.",
  "input_schema": {
    "type": "object",
    "properties": {
      "title": {"type": "string", "description": "Short title for this feature."},
      "hierarchy": {
        "type": "object",
        "description": "The complete hierarchy tree. Must conform to the hierarchy schema."
      }
    },
    "required": ["title", "hierarchy"]
  }
}
```

Output: `{draft_id: str, validation_errors: [], version: int}`. If `validation_errors` is non-empty, Jonny must fix them before the draft can be approved.

### Tool 8: `push_breakdown_to_codeboard`

```json
{
  "name": "push_breakdown_to_codeboard",
  "description": "Push an approved hierarchy draft to CodeBoard as real issues. Only call this AFTER the user has explicitly approved the draft (you will receive a user message saying they approve). This is a write operation — it creates issues in CodeBoard and cannot be undone easily.",
  "input_schema": {
    "type": "object",
    "properties": {
      "draft_id": {"type": "string"},
      "project_id": {"type": "string"}
    },
    "required": ["draft_id", "project_id"]
  }
}
```

Output: `{feature_issue_key: str, total_created: int, issue_keys: [str]}` or `{error: str, partial_keys: [str]}` on failure.

Implementation: calls the promote pipeline (`services/promote_pipeline.py`) which does the bulk POST to CodeBoard with idempotency key protection. The promote pipeline handles rollback if partial creation occurs.

### Tool 9: `hand_to_autopilot`

```json
{
  "name": "hand_to_autopilot",
  "description": "Submit a feature issue to the AutoPilot queue for sequential agent execution. Only call this after the feature issues exist in CodeBoard (i.e., after push_breakdown_to_codeboard succeeds). Only submit features with priority HIGH or CRITICAL unless the user explicitly requests otherwise.",
  "input_schema": {
    "type": "object",
    "properties": {
      "feature_issue_key": {"type": "string", "description": "The CodeBoard issue key, e.g. CB-2384."},
      "priority_override": {
        "type": "string",
        "enum": ["high", "normal"],
        "description": "Queue priority. Defaults to 'normal'."
      }
    },
    "required": ["feature_issue_key"]
  }
}
```

Output: `{queue_id: str, position: int}` or `{error: str}`.

---

## 6. Prompt Engineering

### Jonny System Prompt

```
You are Jonny, the VP R&D planning agent for the AI Project Workspace.

Your persona: methodical, honest, and disciplined. You think before you act.
You ask exactly as many clarifying questions as necessary — no more. When you
have enough to start, you start. You do not over-explain your process; you show
your work through structured outputs.

YOUR HIERARCHY DISCIPLINE (non-negotiable)

Every feature you plan must follow this exact hierarchy:
  FEATURE → EPIC → STORY → TASK → SUBTASK

Rules that are never broken:
1. One FEATURE per conversation — the top-level container.
2. 2–8 EPICs under the FEATURE — major work areas (e.g., "Backend API", "Frontend UI").
3. 2–5 STORYs per EPIC — user-facing capabilities, written as "User can [specific action]".
4. 2–5 TASKs per STORY — implementation units, specific and implementable.
5. 0–3 SUBTASKs per TASK — only when the task has meaningful decomposition.
6. No orphan nodes. Every item has a parent except the FEATURE.
7. Every title must be unique within the session.
8. Story titles must describe user value. Task titles must describe implementation work.

CLARIFICATION RULES

Ask clarifying questions when:
- The user's feature spans multiple independent domains that would produce
  conflicting architecture choices (e.g., "build a mobile app and a desktop app")
- The feature affects existing data models and the migration strategy is unclear
- The priority/urgency is ambiguous and affects how many EPICs are worth building

Do NOT ask clarifying questions when:
- The feature is clear enough to produce at least two EPICs
- You are more than 3 questions deep without drafting anything
- The user has explicitly said "just start"

Maximum clarifying questions before drafting: 4.

SUB-AGENT SPAWNING RULES

Dispatch the researcher when:
- You need to know what existing CodeBoard issues or repo files are relevant
- You are about to propose a data model and have not read the existing models

Dispatch the designer when:
- The feature requires a new data model, system diagram, or UI structure
- You have researcher findings and are ready to draft an architecture

Dispatch the breakdown_writer when:
- You have designer output and are ready to produce the full hierarchy tree
- You are revising a rejected draft (designer is not needed again)

Dispatch the auditor when:
- The feature has more than 4 EPICs (complexity warrants a second pass)
- The user has expressed concern about the scope

Chain depth: you may not dispatch a sub-agent that dispatches another sub-agent.
Sub-agents do not use the spawn_subagent tool. Maximum chain depth: 1.

ARTIFACT DISCIPLINE

Create a mermaid artifact for system/data diagrams — not chat text.
Create a hierarchy_json artifact for the breakdown draft — not chat text.
Create a markdown artifact for long explanatory documents — not chat text.
Short (< 200 word) explanations belong in the chat, not as artifacts.

APPROVAL GATE

Never call push_breakdown_to_codeboard unless the user has said something
equivalent to "looks good", "approve", "go ahead", or "push it". Confirmation
words in a revision request ("ok, but change X") are NOT approval.
When in doubt, ask: "Would you like me to push this to CodeBoard now?"

VISIBILITY

Before saying "I'm calling the researcher", call spawn_subagent. Never claim
a dispatch happened before the tool has been called.
```

### Few-shot examples (injected as the first assistant turn)

A condensed example exchange is injected as the first `assistant` message in the conversation history when a new session starts. It demonstrates the clarification → spawn → draft → approve flow in approximately 800 tokens (system prompt cache-eligible).

### Chain-of-thought discipline

Jonny uses extended thinking (`thinking` budget blocks) only when:
- The feature spans more than 5 EPICs (complexity justifies the cost)
- The user's initial message is fewer than 20 words and the domain is unfamiliar

Extended thinking is disabled for all sub-agent calls — sub-agents get straightforward generation.

---

## 7. Cost Controls

### Per-Tenant Token Budget

Each `studio_session` has a `token_budget` (default: 50,000 tokens). The orchestrator tracks `tokens_used` by summing `input_tokens + output_tokens` from each completed turn. When `tokens_used > token_budget * 0.9`, the orchestrator emits a `token_budget_warning` SSE event. When `tokens_used > token_budget`, it returns an error instead of making another API call and sets `session.state = 'budget_exhausted'`.

Per-tenant daily limits are enforced at the API layer (before the orchestrator runs). Default: 500,000 input tokens/day, 200,000 output tokens/day. These are configurable in a `tenant_settings` table.

### Model Routing per Task Type

| Task | Model | Rationale |
|---|---|---|
| Jonny orchestration (clarifying, planning) | `claude-opus-4-5` | Highest reasoning quality for the orchestration layer |
| Jonny orchestration (revisions, simple confirmations) | `claude-sonnet-4-6` | Cost reduction when the task is well-defined |
| Researcher sub-agent | `claude-sonnet-4-6` | Search synthesis does not need Opus |
| Designer sub-agent | `claude-sonnet-4-6` | Diagram/schema generation is well within Sonnet's capability |
| Breakdown Writer (first draft) | `claude-opus-4-5` | Hierarchy quality matters; use best model |
| Breakdown Writer (revision) | `claude-sonnet-4-6` | Revisions are constrained tasks |
| Auditor sub-agent | `claude-sonnet-4-6` | Review is mechanical; Sonnet is sufficient |
| Fast clarification response (< 3 turns in) | `claude-haiku-3-5` | < 100ms response time for snappy early interaction |

The orchestrator applies model routing via a `ModelRouter` class that reads `session.planning_state.phase` and the current turn type. The tenant can override the default model in their settings (e.g., force Sonnet-only for cost reduction).

### Prompt Caching Strategy

The Anthropic Messages API supports prompt caching via `cache_control: {type: "ephemeral"}` markers on content blocks. Cache TTL is 5 minutes (ephemeral) which is sufficient for a planning conversation where turns are 10–60 seconds apart.

Cacheable content (marked with `cache_control`):
1. The Jonny system prompt (static across all sessions). Cache hit saves ~3,000 input tokens per turn.
2. The few-shot example assistant turn (static). Cache hit saves ~800 tokens.
3. The researcher, designer, and breakdown_writer system prompts when those sub-agents are called repeatedly within a session.
4. Large static repo files fetched via `read_repo_file` (the file content is injected into the message and can be marked cacheable if it exceeds 2,000 tokens).

Estimated cache hit rate in a mature planning conversation (10+ turns): 60–75% of input tokens are cache hits. At Sonnet-4-6 pricing, cache read tokens cost ~10% of non-cached input tokens. This yields a ~55–65% reduction in input token cost for long conversations.

Cache warming: the first message to a new session pre-warms the system prompt cache with a lightweight dummy call if the tenant's session rate exceeds 5 sessions/hour (amortizes cache miss cost).

### Opus-Advisor / Sonnet-Executor Pattern

For the main Jonny turns, the orchestrator applies an adaptive pattern:
- Turn 1–2 (first interaction): `claude-haiku-3-5` — fast response, classify user intent, determine if the request needs clarification or can go straight to drafting
- Turn 3+ (planning): `claude-opus-4-5` for turns that involve decisions (which EPICs to create, how to structure stories); `claude-sonnet-4-6` for turns that are constrained (revision of a specific section, answering a factual question about the hierarchy)

The orchestrator classifies the turn type using a lightweight pre-call to Haiku (< 50 tokens output) that returns `{type: "decision" | "revision" | "factual" | "approval"}`. This classification call itself costs ~200 input tokens and < 50 output tokens — negligible compared to the savings from routing a revision away from Opus.

---

## 8. Failure Modes

### Token Budget Exhaustion (session-level)

Detection: `tokens_used > token_budget` at the start of a turn.

Recovery:
1. Orchestrator sets `session.state = 'budget_exhausted'`
2. SSE emits `{type: "error", code: "token_budget_exceeded", session_id: ...}`
3. Frontend shows an inline warning in the chat: "This planning session has reached its token limit. You can continue in a new session or request a budget increase."
4. The `studio_hierarchy_drafts` table retains the last draft — the user does not lose work.
5. No auto-resume (unlike AutoPilot token exhaustion). Planning sessions are user-driven; the user decides when to continue.

The orchestrator never makes an API call when the budget is exceeded. This prevents runaway cost from a bug that loops.

### API Token Exhaustion (Anthropic rate limit / billing)

Detection: `anthropic.APIStatusError` with status 429 or 529, or the exhaustion signal patterns from the existing `exhaustion_detector.py`.

Recovery:
1. Orchestrator sets `session.state = 'api_rate_limited'`
2. SSE emits `{type: "error", code: "api_rate_limited", retry_after_seconds: N}`
3. The orchestrator records a `studio_tool_calls` row with `status = 'failed'` and `error = redacted_error_text`
4. The session retries automatically after `retry_after_seconds` (if ≤ 300 seconds); otherwise it pauses and requires user action
5. The failing turn's assistant message is not persisted (no partial/confused state in conversation history)

### Sub-Agent Crash or Timeout

Detection: the sub-agent API call throws an exception or returns after > 30 seconds.

Recovery:
1. The `studio_subagent_runs` row transitions to `status = 'failed'` with `error` text (redacted of secrets)
2. The tool_result returned to Jonny is: `{error: "Sub-agent failed", agent_type: "...", retryable: true}`
3. Jonny's system prompt instructs it: "If a sub-agent returns an error with retryable=true, you may try once more. If it fails twice, inform the user and offer to proceed with the information you already have."
4. After two failed sub-agent attempts, Jonny degrades gracefully — it produces a lower-quality breakdown from its own knowledge rather than blocking.

The maximum sub-agent timeout is 30 seconds. This is enforced via `asyncio.wait_for` in the orchestrator. A sub-agent that exceeds this limit is cancelled, not left hanging.

### Tool Error: push_breakdown_to_codeboard fails

Detection: promote pipeline returns an error (network failure, CodeBoard API error, partial creation).

Recovery:
1. The promote pipeline's idempotency key prevents duplicate issues if the call is retried.
2. If partial creation occurred, the rollback compensating action deletes orphaned issues and returns a clean error.
3. Jonny receives `{error: "Push failed after partial creation — rolled back. Issues created: 0."}` as the tool_result.
4. Jonny informs the user: "The push to CodeBoard failed and was rolled back. Your hierarchy draft is still saved (draft_id: ...). You can try again or export the draft as JSON."
5. The `studio_hierarchy_drafts` row retains `approved_at` and remains in a promotable state.

### Tool Error: hand_to_autopilot fails

Detection: AutoPilot queue returns an error (queue paused, queue full, invalid issue key).

Recovery:
1. Jonny informs the user of the specific error: "The AutoPilot queue is currently paused (token reset in progress). Your CodeBoard issues were created successfully. I can add them to AutoPilot once the queue resumes — or you can do this manually from the CodeBoard view."
2. No rollback needed — CodeBoard issues already exist. The hand-to-autopilot step is idempotent.

### Session Hibernation Failure

Detection: the orchestrator receives a `spawn_subagent` tool call for a hibernated session that cannot be resumed (e.g., agent template version mismatch).

Recovery:
1. The orchestrator logs a `studio_agent_activity` row with `status = 'failed'`
2. The UI shows: "This conversation was started with an older version of Jonny. A new conversation tab will be opened with the current context."
3. A new session is created, and the last 5 messages and the most recent hierarchy draft are injected as the starting context.

### Visibility Principle Enforcement

If the orchestrator code path ever reaches "write an assistant message claiming dispatch happened" before the `studio_agent_activity` row is written, the test suite will catch it. The pre-flight check pattern from the master plan is: `studio_agent_activity.insert(status='dispatched')` is the FIRST database write in any dispatch path. If it fails (DB unreachable), the dispatch does not proceed and the SSE emits an error.

---

## 9. Multi-Tenant Safety Summary

| Concern | Mechanism |
|---|---|
| Conversation isolation | `tenant_id` filter on every query; no cross-tenant queries possible without explicit join on tenant_id |
| Token budget enforcement | Per-session budget enforced before every API call; per-tenant daily limit at API middleware layer |
| Sub-agent isolation | Sub-agents receive only their task description and specified artifact IDs — never the full conversation history of another tenant |
| Session persistence | All state in Postgres; sessions survive replica restarts and work across multi-instance deployments |
| Cost attribution | Every `studio_messages` row and `studio_subagent_runs` row records `tenant_id`, model, and token counts; `tenant_token_usage` is the billing rollup |
| Rate limiting | Per-tenant rate limit at the FastAPI middleware layer (before orchestrator): 10 turns/minute, 100 turns/hour |
| Secrets in tool calls | All `error` fields in `studio_tool_calls` and `studio_subagent_runs` pass through `redact_secrets()` (the existing function in `exhaustion_detector.py`) before persistence |
| Audit trail | Every agent dispatch has a `studio_agent_activity` row; no dispatch can be claimed without a database record |

---

## 10. Sequencing Recommendation

Given the master plan's E1 → E2 → E5 sequencing:

Phase 1 — Build the persistence layer first (E1). The schema in Section 2 of this document is the target schema for Postgres. For the initial SQLite development environment, the same schema applies (SQLite supports JSONB via TEXT columns with application-level serialization).

Phase 2 — Build the orchestrator skeleton (`studio_orchestrator.py`) with a stub Jonny prompt that only uses `ask_clarifying_question` and `create_artifact`. No sub-agent spawning yet. Wire up the SSE channel and verify the frontend streaming pattern works end-to-end.

Phase 3 — Add the sub-agent tools (`spawn_subagent`, `search_codeboard`, `read_repo_file`, `query_rag`). Wire up the researcher and designer sub-agents. Verify the Visibility Principle enforcement: `studio_agent_activity` row must exist before the SSE event fires.

Phase 4 — Add the hierarchy tools (`push_hierarchy_draft`, `validate_hierarchy_schema`). Integrate the breakdown_writer sub-agent. Verify the approval gate in the system prompt.

Phase 5 — Add the promotion tools (`push_breakdown_to_codeboard`, `hand_to_autopilot`). Wire up to the existing promote pipeline and AutoPilot queue.

Phase 6 — Implement cost controls: model routing, prompt caching markers, per-tenant rate limiting middleware.

Phase 7 — Failure mode testing: budget exhaustion, API rate limit simulation, sub-agent timeout, partial push rollback.

---

## 11. Open Questions for Eli's Review

1. **Postgres vs SQLite for Studio data.** This design targets Postgres as the cloud-ready persistence layer. If the initial deployment remains on SQLite, the JSONB columns degrade to TEXT with application-level JSON serialization — workable but requires explicit migration to Postgres later. Decision needed before E1 implementation starts.

2. **Tenant model.** This design assumes a `tenant_id` string on every row. The current platform does not have a formal multi-tenant model — it is single-tenant (Eli's instance). The `tenant_id` should be introduced as a placeholder field set to a constant (e.g., `"default"`) until actual multi-tenancy is needed. This avoids schema migration debt when multi-tenancy is added.

3. **Opus-4-5 for Breakdown Writer.** Using Opus for the first hierarchy draft is the highest-quality choice but also the highest cost. If cost is a concern in early testing, use Sonnet-4-6 for all roles initially and upgrade specific roles based on quality evaluation.

4. **Redis lock for multi-replica.** The in-memory `asyncio.Lock` for GroupQueue mutex is sufficient for single-replica deployment. The Redis upgrade path should be noted as a prerequisite for multi-replica deployment, not implemented speculatively.

5. **AutoPilot integration approval mode.** Per the master plan, the first N runs of `hand_to_autopilot` should require explicit user confirmation (`always` mode). This design implements that as a check in the `hand_to_autopilot` tool handler that returns a confirmation prompt before executing. The definition of N (recommend: first 10 promotions) should be configurable in tenant settings.
```
