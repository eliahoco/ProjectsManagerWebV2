# Studio API Contract
## REST + SSE API Design for AI Project Workspace (CB-2384)

**Date:** 2026-05-20
**Author:** API Designer
**Status:** DESIGN — awaits implementation
**Covers:** Studio (chat), Backlog (staging), Crew Map (graph), integrations with CodeBoard + AutoPilot
**Base path for all new routes:** `/api/studio/...`, `/api/backlog/...`, `/api/crew-map/...`
**Versioning namespace:** `/api/v1/` prefix strategy — see Section 6

---

## Table of Contents

1. Resource Model
2. Multi-Tenant Enforcement Pattern
3. Endpoint Catalog — Studio
4. Endpoint Catalog — Backlog
5. Endpoint Catalog — Crew Map
6. Streaming (SSE) Specification
7. Integration Touchpoints (CodeBoard + AutoPilot)
8. Versioning + Backward Compatibility
9. Error Catalog
10. Rate Limit Matrix

---

## 1. Resource Model

### 1.1 Studio Resources

#### StudioSession (was "Conversation" in plan docs — renamed to avoid ambiguity)

Represents one multi-turn chat conversation tab. Maps 1:1 to a Claude Code subprocess (alive or hibernated).

```python
class StudioSession(Base):
    __tablename__ = "StudioSession"

    id: str                        # CUID, primary key
    tenantId: str                  # FK → Tenant.id  (NON-NEGOTIABLE)
    projectId: str                 # FK → Project.id (scoped within tenant)
    userId: str                    # FK → User.id — owner of the session
    title: str                     # Human-readable tab label
    state: StudioSessionState      # ACTIVE | HIBERNATED | PAUSED | ARCHIVED
    hibernatedAt: datetime | None  # set when subprocess is suspended
    resumedAt: datetime | None     # set when subprocess is re-spawned
    idempotencyKey: str | None     # client-supplied, prevents duplicate creation
    agentTemplate: str             # version tag e.g. "jonny-v2"
    tokenBudget: int               # hard cap in tokens (default 100_000)
    tokensUsed: int                # running total, updated per turn
    createdAt: datetime
    updatedAt: datetime
    archivedAt: datetime | None

    # Relationships
    messages: list[StudioMessage]
    artifacts: list[StudioArtifact]
    agentActivities: list[StudioAgentActivity]
    agentInstance: AgentInstance | None
```

Ownership: `tenantId` + `userId`. Lifecycle: ACTIVE → HIBERNATED (idle 30min) → ACTIVE (resume) → ARCHIVED (manual discard).

---

#### StudioMessage

One turn in a session. Stored persistently — never generated from memory alone (Visibility Principle).

```python
class StudioMessage(Base):
    __tablename__ = "StudioMessage"

    id: str
    tenantId: str                  # denormalized for fast tenant-scoped queries
    sessionId: str                 # FK → StudioSession.id
    role: MessageRole              # USER | ASSISTANT | AGENT | SYSTEM
    content: str                  # markdown text
    agentName: str | None         # e.g. "jonny", "architect", "ui-designer"
    agentInstanceId: str | None   # FK → AgentInstance.id
    inTool: bool                  # True when Claude is mid-tool-call
    toolName: str | None          # name of current tool (if inTool)
    isStreaming: bool              # True until final token received
    tokenCount: int               # tokens used for this message
    parentMessageId: str | None   # for branched conversations (future)
    createdAt: datetime
    updatedAt: datetime
```

Lifecycle: created at start of streaming turn, `isStreaming` flipped to False on completion.

---

#### StudioArtifact

A structured output produced during a session — markdown doc, mermaid diagram, code file, HTML preview.

```python
class StudioArtifact(Base):
    __tablename__ = "StudioArtifact"

    id: str
    tenantId: str
    sessionId: str                 # FK → StudioSession.id
    messageId: str | None         # FK → StudioMessage that produced it
    kind: ArtifactKind            # MARKDOWN | MERMAID | CODE | HTML | JSON | SQL
    title: str                    # e.g. "Feature Architecture.md"
    payload: str                  # raw content (text, up to 500 KB)
    mimeType: str                 # e.g. "text/markdown", "text/x-mermaid"
    sizeBytes: int
    etag: str                     # SHA-256 of payload, used for conditional GETs
    version: int                  # monotonic, increments on update
    isLatest: bool                # True for the head version
    createdAt: datetime
    updatedAt: datetime
```

Lifecycle: created when agent writes a file; versioned on update. `etag` enables conditional GET.

---

#### StudioAgentActivity

Write-through-persisted record of every agent dispatch. The Visibility Principle anchor — if no row exists, the dispatch did not happen.

```python
class StudioAgentActivity(Base):
    __tablename__ = "StudioAgentActivity"

    id: str
    tenantId: str
    sessionId: str                 # FK → StudioSession.id
    agentName: str                # e.g. "jonny", "architect"
    skillName: str | None
    status: AgentActivityStatus   # PENDING | RUNNING | DONE | FAILED | CANCELLED
    verb: InterAgentVerb          # NOTIFY | REQUEST | DELEGATE | BROADCAST
    chainDepth: int               # 0 = Jonny, 1 = first skill, max=3
    payload: str | None           # JSON — what was dispatched (redacted secrets)
    result: str | None            # JSON — compact 1-2K artifact returned
    startedAt: datetime
    endedAt: datetime | None
    errorText: str | None         # truncated to 8 KB, Bearer/sk- patterns redacted
    createdAt: datetime
```

Lifecycle: row written BEFORE chat narrates the dispatch. Status transitions: PENDING → RUNNING → DONE/FAILED.

---

#### StudioInterAgentMessage

Audit log of every inter-agent message. Enforces the 4 typed verbs and chain depth.

```python
class StudioInterAgentMessage(Base):
    __tablename__ = "StudioInterAgentMessage"

    id: str
    tenantId: str
    sessionId: str
    fromAgent: str
    toAgent: str                  # or group name for BROADCAST
    verb: InterAgentVerb          # NOTIFY | REQUEST | DELEGATE | BROADCAST
    payload: str                  # JSON, max 16 KB
    chainDepth: int               # enforced <= 3
    activityId: str               # FK → StudioAgentActivity.id
    createdAt: datetime
```

---

#### AgentTemplate

Versioned, git-tracked agent identity. Never per-session mutable.

```python
class AgentTemplate(Base):
    __tablename__ = "AgentTemplate"

    id: str
    tenantId: str
    name: str                     # e.g. "jonny", "architect"
    version: str                  # semver, e.g. "2.0.1"
    systemPrompt: str             # full system prompt
    capabilities: str             # JSON array of capability strings
    approvalMode: ApprovalMode    # ALWAYS | CONFIDENCE | NEVER
    isActive: bool
    isDefault: bool               # one default per name per tenant
    createdAt: datetime
    updatedAt: datetime
```

---

#### AgentInstance

Per-session accumulated memory/context. Gitignored in production. Linked to a session.

```python
class AgentInstance(Base):
    __tablename__ = "AgentInstance"

    id: str
    tenantId: str
    templateId: str               # FK → AgentTemplate.id
    sessionId: str                # FK → StudioSession.id (unique)
    agentName: str                # denormalized
    accumulatedMemory: str | None # JSON blob, up to 32 KB
    lastActiveAt: datetime
    createdAt: datetime
    updatedAt: datetime
```

---

### 1.2 Backlog Resources

#### BacklogItem (the plan docs call this FeatureRequest)

A feature draft in the staging area, between ideation and CodeBoard execution.

```python
class BacklogItem(Base):
    __tablename__ = "BacklogItem"

    id: str
    tenantId: str                  # NON-NEGOTIABLE scope
    projectId: str
    title: str
    description: str | None       # markdown
    priority: Priority            # CRITICAL | HIGH | MEDIUM | LOW | TRIVIAL
    status: BacklogStatus         # DRAFT | REVIEWING | APPROVED | SCHEDULED | PROMOTED | SHIPPED | ARCHIVED
    tags: str                     # JSON array of tag strings
    ownerEmail: str | None
    sourceSessionId: str | None   # FK → StudioSession.id (if from Studio)
    sourceType: str               # "STUDIO" | "MANUAL"
    targetIssueId: str | None     # FK → Issue.id (set on PROMOTE)
    scheduledFor: datetime | None # one-shot trigger time
    scheduleCron: str | None      # cron expression for recurring
    scheduleTimezone: str         # IANA tz, default "UTC"
    idempotencyKey: str | None    # prevents duplicate promote
    archivedAt: datetime | None
    createdAt: datetime
    updatedAt: datetime

    # Relationships
    comments: list[BacklogComment]
    activities: list[BacklogActivity]
```

Status lifecycle: `DRAFT → REVIEWING → APPROVED → SCHEDULED → PROMOTED → SHIPPED → ARCHIVED`

---

#### BacklogComment

```python
class BacklogComment(Base):
    __tablename__ = "BacklogComment"

    id: str
    tenantId: str
    backlogItemId: str            # FK → BacklogItem.id
    author: str
    content: str                  # markdown
    createdAt: datetime
    updatedAt: datetime
```

---

#### BacklogActivity

Append-only audit trail. Every status change, edit, promote, schedule action.

```python
class BacklogActivity(Base):
    __tablename__ = "BacklogActivity"

    id: str
    tenantId: str
    backlogItemId: str
    action: str                   # e.g. "STATUS_CHANGED", "PROMOTED", "SCHEDULED"
    payload: str | None           # JSON diff or context
    actor: str                    # user email or "system" or "scheduler"
    createdAt: datetime
```

---

### 1.3 Crew Map Resources

#### CrewAssignment

One agent-to-feature assignment. These are the graph edges.

```python
class CrewAssignment(Base):
    __tablename__ = "CrewAssignment"

    id: str
    tenantId: str
    projectId: str
    featureId: str | None         # FK → Issue.id (FEATURE type) — null means project-level
    agentName: str                # e.g. "jonny", "architect"
    role: str                     # "orchestrates" | "implements" | "audits" | "reviews" | "documents"
    status: AssignmentStatus      # ACTIVE | PAST | CANCELLED
    sessionId: str | None         # FK → StudioSession.id that spawned this assignment
    startedAt: datetime
    endedAt: datetime | None
    createdAt: datetime
```

---

#### CrewSkillUsage

Aggregated per-assignment skill invocation counts.

```python
class CrewSkillUsage(Base):
    __tablename__ = "CrewSkillUsage"

    id: str
    tenantId: str
    assignmentId: str             # FK → CrewAssignment.id
    skillName: str
    invocationCount: int
    lastUsedAt: datetime
    createdAt: datetime
    updatedAt: datetime
```

---

### 1.4 Enum Definitions

```python
class StudioSessionState(str, Enum):
    ACTIVE = "ACTIVE"
    HIBERNATED = "HIBERNATED"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"

class MessageRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"

class ArtifactKind(str, Enum):
    MARKDOWN = "MARKDOWN"
    MERMAID = "MERMAID"
    CODE = "CODE"
    HTML = "HTML"
    JSON = "JSON"
    SQL = "SQL"

class AgentActivityStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class InterAgentVerb(str, Enum):
    NOTIFY = "NOTIFY"
    REQUEST = "REQUEST"
    DELEGATE = "DELEGATE"
    BROADCAST = "BROADCAST"

class ApprovalMode(str, Enum):
    ALWAYS = "ALWAYS"          # human confirms before action
    CONFIDENCE = "CONFIDENCE"  # agent self-decides if confident
    NEVER = "NEVER"            # full autonomy (use sparingly)

class BacklogStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PROMOTED = "PROMOTED"
    SHIPPED = "SHIPPED"
    ARCHIVED = "ARCHIVED"

class Priority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    TRIVIAL = "TRIVIAL"

class AssignmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAST = "PAST"
    CANCELLED = "CANCELLED"
```

---

## 2. Multi-Tenant Enforcement Pattern

### 2.1 The Dependency

Every new Studio/Backlog/Crew Map endpoint MUST use `get_tenant_scoped_resource`. This is the single, mandatory gate — no bare resource lookups by ID allowed.

```python
# backend/api/deps.py  (add alongside existing get_rag, get_db)

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import get_db
from models.tenant import Tenant  # new model
from app.security import require_local_or_token
import logging

logger = logging.getLogger(__name__)


async def get_tenant_id(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Derive tenantId from the authenticated request.

    Resolution order:
    1. X-Tenant-ID header (set by Next.js proxy after session validation)
    2. JWT sub claim (future: when OAuth 2.0 is fully wired)
    3. If single-tenant deployment (MULTI_TENANT=false in settings),
       return the default system tenant ID.

    Never reads tenantId from a request body or query param — always
    from a trusted header or token so callers cannot self-elevate.
    """
    # Phase 1: header-based (current deployment model)
    tenant_id = request.headers.get("x-tenant-id")
    if tenant_id:
        return tenant_id

    # Phase 2: single-tenant fallback (dev + current production)
    if not settings.MULTI_TENANT:
        return settings.DEFAULT_TENANT_ID  # new config key, e.g. "system"

    raise HTTPException(
        status_code=401,
        detail="tenant_id_required",
    )


async def get_tenant_scoped_resource(
    resource_id: str,
    tenant_id: str,
    model_class,
    db: AsyncSession,
    id_column_name: str = "id",
) -> Any:
    """
    Fetch a resource by ID, enforcing tenant scope.

    Returns 404 (NOT 403) when the resource exists under a different
    tenant — avoids revealing the existence of cross-tenant resources
    to probing clients. This is the non-negotiable multi-tenant rule.

    Usage example:
        session = await get_tenant_scoped_resource(
            resource_id=session_id,
            tenant_id=tenant_id,
            model_class=StudioSession,
            db=db,
        )
    """
    id_col = getattr(model_class, id_column_name)
    result = await db.execute(
        select(model_class).where(
            id_col == resource_id,
            model_class.tenantId == tenant_id,
        )
    )
    resource = result.scalar_one_or_none()

    if resource is None:
        # Deliberately 404 — do not reveal whether the resource exists
        # under a different tenant (avoids tenant enumeration attacks)
        raise HTTPException(status_code=404, detail=f"Resource not found")

    return resource
```

### 2.2 Application Pattern

Every route handler that accepts a resource ID looks like this:

```python
@router.get("/studio/sessions/{session_id}")
async def get_session(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    session = await get_tenant_scoped_resource(
        resource_id=session_id,
        tenant_id=tenant_id,
        model_class=StudioSession,
        db=db,
    )
    return StudioSessionResponse.model_validate(session)
```

List endpoints always filter by `tenantId` in the WHERE clause — never fetch all then filter in Python.

### 2.3 Project Scope Check

For routes that are project-scoped (most Studio + Backlog endpoints), an additional check ensures the project belongs to the tenant:

```python
async def verify_project_in_tenant(
    project_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> Project:
    """Returns 404 if project doesn't exist or belongs to another tenant."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.tenantId == tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
```

---

## 3. Endpoint Catalog — Studio

Router prefix: `/api/studio` (registered in `api/__init__.py` as `studio_router`)

### 3.1 Session Management

---

#### POST /api/studio/projects/{project_id}/sessions

Create a new Studio session (conversation tab).

**Request body:**
```python
class CreateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    agentTemplate: str = "jonny-v2"  # must exist in AgentTemplate
    tokenBudget: int = Field(100_000, ge=1_000, le=500_000)
    idempotencyKey: str | None = None  # client UUID; duplicate returns 200 + existing session
```

**Response — 201 Created:**
```python
class StudioSessionResponse(BaseModel):
    id: str
    tenantId: str
    projectId: str
    userId: str
    title: str
    state: StudioSessionState
    agentTemplate: str
    tokenBudget: int
    tokensUsed: int
    createdAt: str  # ISO 8601 Z suffix
    updatedAt: str

    model_config = ConfigDict(from_attributes=True)
```

**Idempotency:** If `idempotencyKey` matches an existing non-ARCHIVED session for this tenant+project+user, return 200 with the existing session rather than creating a duplicate.

**Error codes:**
- 400 `VALIDATION_ERROR` — invalid title, budget out of range
- 404 `NOT_FOUND` — project_id not found in tenant
- 409 `CONFLICT` — agentTemplate version not found
- 429 `RATE_LIMITED` — max 20 active sessions per tenant

**Rate limit:** 20 creates/hour per tenant, max 8 concurrent ACTIVE sessions per tenant (mirrors "max 8 concurrent streams" risk mitigation from plan docs).

---

#### GET /api/studio/projects/{project_id}/sessions

List sessions for a project, scoped to the calling user's tenant.

**Query params:**
```
state: StudioSessionState | None       # filter by state
page: int = 1
pageSize: int = 50 (max 200)
sortBy: "createdAt" | "updatedAt" | "title" = "updatedAt"
sortOrder: "asc" | "desc" = "desc"
```

**Response — 200:**
```python
class PaginatedSessionsResponse(BaseModel):
    items: list[StudioSessionResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int
```

**Error codes:**
- 404 — project not found in tenant

---

#### GET /api/studio/sessions/{session_id}

Get a single session by ID.

**Response — 200:** `StudioSessionResponse`

**Error codes:**
- 404 — session not found or wrong tenant (never 403)

---

#### PATCH /api/studio/sessions/{session_id}

Update session metadata (title, state transitions, token budget).

**Request body:**
```python
class UpdateSessionRequest(BaseModel):
    title: str | None = None
    state: StudioSessionState | None = None  # only PAUSED, ARCHIVED allowed (cannot force ACTIVE)
    tokenBudget: int | None = Field(None, ge=1_000, le=500_000)
```

**State transition rules enforced server-side:**
- `ACTIVE → PAUSED`: always allowed
- `PAUSED → ACTIVE`: allowed (triggers subprocess resume)
- `ACTIVE → ARCHIVED`: allowed (terminates subprocess, soft-deletes)
- `HIBERNATED → ARCHIVED`: allowed
- `ARCHIVED → *`: blocked (409)

**Response — 200:** `StudioSessionResponse`

**Headers:** `ETag: <session_version_hash>` on response; client should send `If-Match` on subsequent PATCH.

**Error codes:**
- 400 — invalid state transition
- 404 — session not found
- 409 — invalid state transition or ETag mismatch (`If-Match` sent and stale)
- 422 — validation error

---

#### DELETE /api/studio/sessions/{session_id}

Archive and terminate session. Soft delete — data retained for 30 days.

**Response — 204 No Content**

**Error codes:**
- 404 — session not found or wrong tenant

---

### 3.2 Message Operations

---

#### GET /api/studio/sessions/{session_id}/messages

List all messages in a session in chronological order.

**Query params:**
```
limit: int = 100 (max 500)
before: str | None   # message ID cursor — returns messages before this ID
after: str | None    # message ID cursor — returns messages after this ID
```

**Response — 200:**
```python
class MessageListResponse(BaseModel):
    items: list[StudioMessageResponse]
    hasMore: bool
    nextCursor: str | None
    prevCursor: str | None
```

```python
class StudioMessageResponse(BaseModel):
    id: str
    sessionId: str
    role: MessageRole
    content: str
    agentName: str | None
    inTool: bool
    toolName: str | None
    isStreaming: bool
    tokenCount: int
    createdAt: str
    updatedAt: str
```

Cursor-based pagination is used (not page-based) because message lists are append-only and page-based has races during streaming. Client stores `nextCursor` and sends `after=<cursor>` to poll for new messages.

---

#### POST /api/studio/sessions/{session_id}/messages

Append a user message and trigger AI response. The AI response is delivered via SSE (Section 6).

**Request body:**
```python
class AppendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=32_000)
    role: Literal[MessageRole.USER] = MessageRole.USER
    # User can include slash commands: /pause, /save, /discard
```

**Response — 202 Accepted** (immediate, before AI responds):
```python
class AppendMessageAccepted(BaseModel):
    userMessageId: str          # the persisted user message ID
    sessionId: str
    streamUrl: str              # SSE endpoint to subscribe to: /api/studio/sessions/{id}/events
    estimatedLatencyMs: int     # hint for UI (typically 500-2000)
```

**Idempotency:** Client should include `Idempotency-Key: <uuid>` header. Duplicate submission within 60s returns the same 202 response without re-triggering the AI.

**Error codes:**
- 400 — content too long or session ARCHIVED/HIBERNATED without resume
- 404 — session not found
- 429 — rate limit (5 messages/min per session during streaming)
- 503 — subprocess backend unavailable

**Rate limit:** 5 user messages/minute per session (prevents runaway inference during streaming).

---

### 3.3 Artifact Operations

---

#### GET /api/studio/sessions/{session_id}/artifacts

List artifacts for a session.

**Query params:**
```
kind: ArtifactKind | None
latestOnly: bool = True   # if False, returns all versions
```

**Response — 200:**
```python
class ArtifactListResponse(BaseModel):
    items: list[StudioArtifactResponse]
    total: int
```

```python
class StudioArtifactResponse(BaseModel):
    id: str
    sessionId: str
    messageId: str | None
    kind: ArtifactKind
    title: str
    mimeType: str
    sizeBytes: int
    etag: str
    version: int
    isLatest: bool
    payloadUrl: str            # /api/studio/artifacts/{id}/content
    createdAt: str
    updatedAt: str
    # payload NOT inline — too large for list responses
```

---

#### GET /api/studio/artifacts/{artifact_id}

Get artifact metadata (no payload).

**Response — 200:** `StudioArtifactResponse`

**Headers:** `ETag: <artifact.etag>`

**Error codes:**
- 404 — artifact not found or wrong tenant

---

#### GET /api/studio/artifacts/{artifact_id}/content

Get artifact raw content. Supports conditional GET.

**Request headers:**
- `If-None-Match: <etag>` — returns 304 Not Modified if unchanged

**Response — 200:**
- `Content-Type: <artifact.mimeType>`
- `ETag: <artifact.etag>`
- `Cache-Control: private, max-age=300`
- Body: raw artifact content (text)

**Response — 304 Not Modified** (if ETag matches)

**Error codes:**
- 404 — artifact not found or wrong tenant
- 413 — artifact exceeds 500 KB (should never happen; this is a guard)

---

#### POST /api/studio/sessions/{session_id}/artifacts

Manually upload an artifact (user-provided file for preview pane, not AI-generated).

**Request body:** `multipart/form-data`
```
kind: ArtifactKind
title: str
file: binary  (max 500 KB)
```

**Response — 201:** `StudioArtifactResponse`

**Error codes:**
- 400 — unsupported kind, missing title
- 413 — file exceeds 500 KB
- 415 — unsupported media type

---

### 3.4 Agent Activity

---

#### GET /api/studio/sessions/{session_id}/agent-activity

List agent activity records for a session (the Visibility Principle audit log).

**Query params:**
```
status: AgentActivityStatus | None
agentName: str | None
limit: int = 50
```

**Response — 200:**
```python
class AgentActivityListResponse(BaseModel):
    items: list[StudioAgentActivityResponse]
    total: int
```

```python
class StudioAgentActivityResponse(BaseModel):
    id: str
    sessionId: str
    agentName: str
    skillName: str | None
    status: AgentActivityStatus
    verb: InterAgentVerb
    chainDepth: int
    startedAt: str
    endedAt: str | None
    errorText: str | None
    createdAt: str
```

---

### 3.5 Send-to-Backlog

---

#### POST /api/studio/sessions/{session_id}/send-to-backlog

Extracts a structured FeatureRequest from the session transcript and creates a BacklogItem. This is an atomic action — the AI generation and BacklogItem creation are transactional.

**Request body:**
```python
class SendToBacklogRequest(BaseModel):
    # Optional overrides — if omitted, AI infers from conversation
    title: str | None = None
    description: str | None = None
    priority: Priority | None = None
    tags: list[str] = []
    idempotencyKey: str         # required — prevents double-submit from UI
```

**Approval mode:** `CONFIDENCE` (AI self-decides the extraction; user edits in Backlog if needed). The frontend shows an edit-before-send modal for user confirmation before calling this endpoint.

**Response — 201:**
```python
class SendToBacklogResponse(BaseModel):
    backlogItemId: str
    backlogItemTitle: str
    backlogItemStatus: BacklogStatus  # always DRAFT on creation
    sessionId: str
    redirectUrl: str  # /workspace/backlog/{backlogItemId}
```

**Error codes:**
- 400 — session has no messages to extract from
- 404 — session not found
- 409 — idempotencyKey already used (return existing backlog item ID in details)
- 422 — AI extraction failed (malformed response)
- 503 — AI backend unavailable

**Rate limit:** 10 per hour per session.

---

### 3.6 Hibernate / Resume

These are handled via `PATCH /api/studio/sessions/{session_id}` with `state` transitions. The subprocess management is opaque to the API consumer — the orchestrator handles it internally.

However, the frontend can explicitly request hibernation/resume to implement "tab focus" behavior:

---

#### POST /api/studio/sessions/{session_id}/hibernate

Request immediate session hibernation (subprocess suspension). Idempotent.

**Response — 200:**
```python
class HibernateResponse(BaseModel):
    sessionId: str
    state: Literal["HIBERNATED"]
    hibernatedAt: str
    snapshotMessageCount: int   # messages snapshotted to DB
```

---

#### POST /api/studio/sessions/{session_id}/resume

Resume a hibernated session. Triggers subprocess re-spawn and context replay.

**Response — 200:**
```python
class ResumeResponse(BaseModel):
    sessionId: str
    state: Literal["ACTIVE"]
    resumedAt: str
    replayedMessageCount: int
    streamUrl: str
```

**Error codes:**
- 404 — session not found
- 409 — session not in HIBERNATED state
- 503 — subprocess pool exhausted (max concurrent sessions reached)

---

## 4. Endpoint Catalog — Backlog

Router prefix: `/api/backlog`

### 4.1 BacklogItem CRUD

---

#### POST /api/backlog/projects/{project_id}/items

Create a new BacklogItem manually (without Studio).

**Request body:**
```python
class CreateBacklogItemRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    tags: list[str] = []
    ownerEmail: str | None = None
    scheduledFor: datetime | None = None
    scheduleCron: str | None = None
    scheduleTimezone: str = "UTC"
    sourceSessionId: str | None = None    # if originated from Studio
    idempotencyKey: str | None = None
```

**Validation:**
- `scheduledFor` and `scheduleCron` are mutually exclusive
- `scheduleCron` validated against croniter regex + parsed for human preview
- `scheduleTimezone` must be a valid IANA timezone string
- `tags` max 20 items, each max 50 chars

**Response — 201:**
```python
class BacklogItemResponse(BaseModel):
    id: str
    tenantId: str
    projectId: str
    title: str
    description: str | None
    priority: Priority
    status: BacklogStatus
    tags: list[str]
    ownerEmail: str | None
    sourceSessionId: str | None
    sourceType: str
    targetIssueId: str | None
    scheduledFor: str | None
    scheduleCron: str | None
    scheduleTimezone: str
    nextFiringAt: str | None      # computed from scheduleCron + timezone
    humanScheduleDescription: str | None   # "Every Monday at 9am UTC"
    archivedAt: str | None
    createdAt: str
    updatedAt: str

    model_config = ConfigDict(from_attributes=True)
```

**Error codes:**
- 400 — validation errors, invalid cron expression, invalid timezone
- 404 — project not found in tenant
- 409 — idempotencyKey already used

---

#### GET /api/backlog/projects/{project_id}/items

List BacklogItems with filtering, sorting, and pagination.

**Query params:**
```
status: BacklogStatus | None
priority: Priority | None
tags: str | None            # comma-separated tag filter (OR)
ownerEmail: str | None
search: str | None          # searches title + description
scheduledOnly: bool = False # filter to items with scheduledFor or scheduleCron
sortBy: "updatedAt" | "priority" | "scheduledFor" | "createdAt" | "title" = "updatedAt"
sortOrder: "asc" | "desc" = "desc"
page: int = 1
pageSize: int = 50 (max 200)
```

Priority sort order: CRITICAL(0) → HIGH(1) → MEDIUM(2) → LOW(3) → TRIVIAL(4).

**Response — 200:**
```python
class PaginatedBacklogItemsResponse(BaseModel):
    items: list[BacklogItemResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int
```

---

#### GET /api/backlog/items/{item_id}

Get a single BacklogItem.

**Response — 200:** `BacklogItemResponse`

**Error codes:**
- 404 — item not found or wrong tenant

---

#### PATCH /api/backlog/items/{item_id}

Update a BacklogItem.

**Request headers:** `If-Match: <etag>` (optional; if provided, 409 on stale)

**Request body:**
```python
class UpdateBacklogItemRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: Priority | None = None
    status: BacklogStatus | None = None
    tags: list[str] | None = None
    ownerEmail: str | None = None
    scheduledFor: datetime | None = None
    scheduleCron: str | None = None
    scheduleTimezone: str | None = None
```

**Status transition enforcement:**
- `PROMOTED` → any: blocked (409). Promoted items are read-only.
- `ARCHIVED` → any: blocked (409).
- All other transitions allowed.

**Response — 200:** `BacklogItemResponse`

**Headers:** `ETag: <updated_etag>`

**Error codes:**
- 400 — invalid cron, invalid timezone, status conflict
- 404 — item not found
- 409 — invalid state transition, ETag mismatch

---

#### DELETE /api/backlog/items/{item_id}

Soft-delete (sets `archivedAt`, status → `ARCHIVED`). Items in `PROMOTED` status cannot be deleted.

**Response — 204 No Content**

**Error codes:**
- 404 — item not found
- 409 — item is PROMOTED (cannot archive a promoted item)

---

### 4.2 Comments + Activity

---

#### POST /api/backlog/items/{item_id}/comments

```python
class CreateBacklogCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000)
    author: str
```

**Response — 201:**
```python
class BacklogCommentResponse(BaseModel):
    id: str
    backlogItemId: str
    author: str
    content: str
    createdAt: str
    updatedAt: str
```

---

#### GET /api/backlog/items/{item_id}/comments

Returns comments in reverse-chronological order.

**Response — 200:** `list[BacklogCommentResponse]`

---

#### GET /api/backlog/items/{item_id}/activity

Returns the full append-only activity log.

**Response — 200:**
```python
class BacklogActivityResponse(BaseModel):
    id: str
    backlogItemId: str
    action: str
    payload: dict | None
    actor: str
    createdAt: str
```

---

### 4.3 Promote to CodeBoard + AutoPilot

This is the high-value integration endpoint. Approval mode: `ALWAYS` (user must explicitly call this after editing).

---

#### POST /api/backlog/items/{item_id}/promote

Promote a BacklogItem to CodeBoard + AutoPilot. Runs the Blueprint state machine (deterministic dispatch → agentic hierarchy generation → deterministic push).

**Request body:**
```python
class PromoteRequest(BaseModel):
    # The hierarchy is optionally provided pre-built from the edit-before-send modal.
    # If absent, the server generates it via the Jonny prompt.
    hierarchy: HierarchyProposal | None = None
    queueIfHighPriority: bool = True   # append to AutoPilot if priority >= HIGH
    idempotencyKey: str               # REQUIRED — prevents double-promote
```

```python
class HierarchyProposal(BaseModel):
    feature: HierarchyNode

class HierarchyNode(BaseModel):
    title: str
    description: str | None
    type: str  # FEATURE | EPIC | STORY | TASK | SUBTASK
    priority: str
    assignee: str | None
    children: list[HierarchyNode] = []
```

**Idempotency:** If `idempotencyKey` matches an existing promotion, return 200 with the existing result. The `BacklogItem.idempotencyKey` column stores this. Prevents duplicate CodeBoard issue trees if the user double-clicks.

**Response — 202 Accepted** (promote is async; pipeline runs in background):
```python
class PromoteAccepted(BaseModel):
    backlogItemId: str
    promoteJobId: str        # poll for status
    statusUrl: str           # /api/backlog/promote-jobs/{promoteJobId}
    estimatedDurationSecs: int  # hint: typically 10-30 seconds
```

**Error codes:**
- 400 — item is DRAFT (must be APPROVED or SCHEDULED first)
- 404 — item not found
- 409 — item already PROMOTED (idempotencyKey mismatch means double-promote)
- 422 — invalid hierarchy proposal (fails JSON schema validation)
- 503 — CodeBoard API unavailable

---

#### GET /api/backlog/promote-jobs/{job_id}

Poll promote job status.

**Response — 200:**
```python
class PromoteJobResponse(BaseModel):
    id: str
    backlogItemId: str
    status: str  # "RUNNING" | "DONE" | "FAILED" | "ROLLED_BACK"
    stage: str   # "validating" | "generating_hierarchy" | "pushing_codeboard" | "queuing_autopilot" | "finalizing"
    createdIssueKeys: list[str]   # populated incrementally as issues created
    featureIssueId: str | None    # the root FEATURE issue ID in CodeBoard
    autopilotQueueId: str | None  # the queue entry ID
    error: str | None
    startedAt: str
    completedAt: str | None
```

**SSE alternative:** Subscribe to `/api/backlog/items/{item_id}/events` to receive real-time promote pipeline progress (see Section 6).

---

### 4.4 Schedule Validation

---

#### POST /api/backlog/validate-schedule

Validate and preview a schedule expression without creating/updating an item. Used by the frontend edit modal for instant feedback.

**Request body:**
```python
class ValidateScheduleRequest(BaseModel):
    scheduledFor: datetime | None = None
    scheduleCron: str | None = None
    scheduleTimezone: str = "UTC"
```

**Response — 200:**
```python
class ValidateScheduleResponse(BaseModel):
    valid: bool
    humanDescription: str | None   # "Every Monday at 9am UTC"
    nextFiringAt: str | None       # ISO 8601 Z — next trigger time
    nextFiveFirings: list[str]     # for recurring: next 5 trigger times
    errors: list[str]              # empty if valid
```

**Response must return in < 100ms** (Doherty Threshold rule from plan docs). Croniter parsing is synchronous and fast.

---

## 5. Endpoint Catalog — Crew Map

Router prefix: `/api/crew-map`

### 5.1 Graph Data

---

#### GET /api/crew-map/projects/{project_id}/graph

Fetch the full graph for a project. Returns nodes + edges. Optimized for react-flow consumption.

**Query params:**
```
featureId: str | None      # sub-graph for one feature
agentName: str | None      # filter to nodes involving this agent
status: AssignmentStatus | None = "ACTIVE"
includeConversationNodes: bool = True
```

**Response — 200:**
```python
class CrewMapGraphResponse(BaseModel):
    projectId: str
    nodes: list[CrewMapNode]
    edges: list[CrewMapEdge]
    generatedAt: str          # ISO timestamp — for cache freshness
    etag: str                 # hash of full graph state

class CrewMapNode(BaseModel):
    id: str                   # stable ID for react-flow
    type: CrewMapNodeType     # PROJECT | FEATURE | ORCHESTRATOR | SKILL | CONVERSATION
    label: str
    status: str | None        # ACTIVE | IDLE | PAST
    metadata: dict            # type-specific detail (see below)

class CrewMapEdge(BaseModel):
    id: str
    source: str               # node id
    target: str               # node id
    label: str                # "orchestrates" | "implements" | "audits" | "reviews" | "documents"
    status: AssignmentStatus  # determines visual style: solid=ACTIVE, dashed=PAST
    animated: bool            # True when agent is currently mid-task (live data flowing)

class CrewMapNodeType(str, Enum):
    PROJECT = "PROJECT"
    FEATURE = "FEATURE"
    ORCHESTRATOR = "ORCHESTRATOR"
    SKILL = "SKILL"
    CONVERSATION = "CONVERSATION"
```

**Node metadata by type:**
```
PROJECT node metadata:
  { "name": str, "issueCount": int }

FEATURE node metadata:
  { "issueId": str, "priority": str, "status": str }

ORCHESTRATOR node metadata:
  { "agentName": str, "templateVersion": str, "isActive": bool }

SKILL node metadata:
  { "agentName": str, "isActive": bool, "currentActivity": str | None, "invocationCount": int }

CONVERSATION node metadata:
  { "sessionId": str, "sessionTitle": str, "deepLinkUrl": str }
```

**Cache strategy:** Clients should send `If-None-Match: <etag>` on subsequent requests. Graph is recomputed from `CrewAssignment` + `StudioAgentActivity` tables — typically fast (<200ms for < 100 nodes). For > 100 nodes, a 5-second background cache is applied.

**Error codes:**
- 404 — project not found in tenant

---

#### GET /api/crew-map/features/{feature_issue_id}/graph

Fetch sub-graph for a single feature. Always includes: the feature node, its orchestrator, all skill nodes assigned to it, and linked conversation nodes.

**Response — 200:** Same `CrewMapGraphResponse` shape, scoped to the feature.

---

#### GET /api/crew-map/assignments

List `CrewAssignment` records (the raw graph edges) with filtering.

**Query params:**
```
projectId: str | None
featureId: str | None
agentName: str | None
status: AssignmentStatus | None
page: int = 1
pageSize: int = 100
```

**Response — 200:**
```python
class CrewAssignmentResponse(BaseModel):
    id: str
    tenantId: str
    projectId: str
    featureId: str | None
    agentName: str
    role: str
    status: AssignmentStatus
    sessionId: str | None
    startedAt: str
    endedAt: str | None
    createdAt: str
```

---

#### GET /api/crew-map/assignments/{assignment_id}

Get one assignment with its skill usage breakdown.

**Response — 200:**
```python
class CrewAssignmentDetailResponse(CrewAssignmentResponse):
    skillUsage: list[CrewSkillUsageResponse]
    recentActivities: list[StudioAgentActivityResponse]  # last 10

class CrewSkillUsageResponse(BaseModel):
    skillName: str
    invocationCount: int
    lastUsedAt: str
```

---

### 5.2 Crew Map Search

---

#### GET /api/crew-map/search

Fuzzy search across agent names, feature titles, and session titles within a tenant.

**Query params:**
```
q: str = Field(..., min_length=1)
projectId: str | None
limit: int = 20
```

**Response — 200:**
```python
class CrewMapSearchResponse(BaseModel):
    results: list[CrewMapSearchResult]

class CrewMapSearchResult(BaseModel):
    nodeId: str
    nodeType: CrewMapNodeType
    label: str
    score: float
    projectId: str
    metadata: dict
```

---

## 6. Streaming (SSE) Specification

All SSE endpoints produce `text/event-stream` responses. The FastAPI handler uses `StreamingResponse` with an `async_generator` — identical pattern to existing `execution.py` streaming.

### 6.1 SSE Connection Pattern

```python
# Standard SSE response pattern (replicating execution.py style)
@router.get("/studio/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    _auth = InternalAuthDep,
):
    session = await get_tenant_scoped_resource(session_id, tenant_id, StudioSession, db)

    async def event_generator():
        # Send a ping on connect
        yield "event: connected\ndata: {\"sessionId\": \"" + session_id + "\"}\n\n"

        async for event in studio_orchestrator.subscribe(session_id):
            yield f"event: {event.type}\ndata: {event.json()}\n\n"

            if event.type in ("session_error", "session_done"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        }
    )
```

### 6.2 Studio Session Events — /api/studio/sessions/{session_id}/events

SSE channel for a live Studio chat session. The frontend `EventSource` subscribes here.

| Event Type | When | Payload |
|---|---|---|
| `connected` | On subscribe | `{ sessionId, state }` |
| `token_delta` | Each streaming token | `{ messageId, delta, tokenIndex }` |
| `message_start` | AI starts responding | `{ messageId, role, agentName }` |
| `message_done` | AI response complete | `{ messageId, tokenCount, isStreaming: false }` |
| `tool_start` | Agent begins tool call | `{ messageId, toolName, agentName, inTool: true }` |
| `tool_done` | Tool call completes | `{ messageId, toolName, result: "summary", inTool: false }` |
| `agent_dispatch` | Jonny dispatches a skill | `{ activityId, fromAgent, toAgent, verb, chainDepth }` — AFTER DB row persisted |
| `agent_status` | Skill status update | `{ activityId, agentName, status, currentAction }` |
| `artifact_created` | Agent writes a file | `{ artifactId, kind, title, sessionId }` |
| `artifact_updated` | Agent updates a file | `{ artifactId, version, etag }` |
| `session_paused` | Session paused | `{ sessionId, reason }` |
| `session_hibernated` | Idle timeout or explicit | `{ sessionId, snapshotCount }` |
| `session_error` | Fatal error | `{ sessionId, error, code }` |
| `session_done` | All agents idle, awaiting input | `{ sessionId, tokensUsed, tokensRemaining }` |
| `ping` | Every 30s | `{ ts }` — client reconnects if ping missed x2 |

**Payload schemas:**
```python
class TokenDeltaEvent(BaseModel):
    messageId: str
    delta: str         # partial token text
    tokenIndex: int

class AgentDispatchEvent(BaseModel):
    activityId: str    # FK → StudioAgentActivity.id — MUST be persisted before this fires
    fromAgent: str
    toAgent: str
    verb: InterAgentVerb
    chainDepth: int
    sessionId: str

class ArtifactCreatedEvent(BaseModel):
    artifactId: str
    kind: ArtifactKind
    title: str
    sessionId: str
    previewUrl: str    # /api/studio/artifacts/{id}/content
```

**Client reconnect:** EventSource reconnects automatically. The server should replay unacknowledged events using `Last-Event-ID` header — store last 100 events in a sliding ring buffer keyed by `session_id`.

### 6.3 Backlog Item Events — /api/backlog/items/{item_id}/events

SSE channel for Backlog lifecycle events (primarily: promote pipeline progress).

| Event Type | When | Payload |
|---|---|---|
| `connected` | On subscribe | `{ itemId, status }` |
| `promote_stage` | Pipeline stage advance | `{ stage, completedStages, totalStages }` |
| `promote_issue_created` | CodeBoard issue created | `{ issueKey, issueId, issueType, parentKey }` |
| `promote_queued` | AutoPilot queue entry added | `{ queueId, issueId }` |
| `promote_done` | Promote complete | `{ featureIssueId, allIssueKeys, autopilotQueueId }` |
| `promote_failed` | Promote failed (with rollback) | `{ stage, error, rolledBack, orphanCount }` |
| `status_changed` | Item status changed | `{ oldStatus, newStatus, actor }` |
| `scheduled_fired` | Scheduler triggered promote | `{ scheduledFor, triggeredAt }` |
| `ping` | Every 30s | `{ ts }` |

### 6.4 Crew Map Events — /api/crew-map/projects/{project_id}/events

SSE channel for live Crew Map graph updates. Frontend subscribes once per project view.

| Event Type | When | Payload |
|---|---|---|
| `connected` | On subscribe | `{ projectId, nodeCount, edgeCount }` |
| `node_added` | New assignment/session created | `{ node: CrewMapNode }` |
| `node_updated` | Agent status changed | `{ nodeId, changes: dict }` |
| `node_removed` | Assignment ended | `{ nodeId }` |
| `edge_added` | New assignment relationship | `{ edge: CrewMapEdge }` |
| `edge_updated` | Assignment status changed | `{ edgeId, status, animated }` |
| `edge_removed` | Assignment ended | `{ edgeId }` |
| `agent_active` | Agent begins tool use in any session | `{ nodeId, agentName, toolName, sessionId }` |
| `agent_idle` | Agent completes tool use | `{ nodeId, agentName }` |
| `ping` | Every 30s | `{ ts }` |

**Broadcast mechanism:** `studio_orchestrator.py` and `agent_dispatcher.py` both publish to a project-level event bus (asyncio `Queue` per project). `crew_map_service.py` subscribes and translates into Crew Map events.

### 6.5 SSE Connection Limits

- Max 8 concurrent SSE connections per tenant (across all three channels)
- Client must send `Last-Event-ID` on reconnect — server replays last 100 events
- Server sends `ping` every 30 seconds; client reconnects if no ping for 60 seconds
- HTTP/2 multiplexing recommended (each SSE connection is one HTTP/2 stream)

---

## 7. Integration Touchpoints

### 7.1 Backlog → CodeBoard

The promote pipeline calls existing CodeBoard issue endpoints. The exact call sequence:

**Step 1: Create the FEATURE issue**
```
POST /api/projects/{codeboard_project_id}/issues
Content-Type: application/json

{
  "title": "<feature_title>",
  "description": "<feature_description_with_context>",
  "type": "FEATURE",
  "status": "BACKLOG",
  "priority": "<mapped_priority>",
  "reporter": "AI",
  "labels": "[\"studio-promoted\", \"<backlog-item-id>\"]"
}
```

Response: `IssueResponse` — capture `featureIssueId = response.id`.

**Step 2: Create EPICs under the FEATURE**
```
POST /api/projects/{codeboard_project_id}/issues

{
  "title": "<epic_title>",
  "type": "EPIC",
  "status": "BACKLOG",
  "parentId": "<featureIssueId>",
  "priority": "<priority>",
  "reporter": "AI"
}
```

**Step 3: Create STORYs, TASKs, SUBTASKs recursively**
Same pattern, linking `parentId` at each level.

**Priority mapping (Backlog → CodeBoard):**
```
CRITICAL → CRITICAL
HIGH     → HIGH
MEDIUM   → MEDIUM
LOW      → LOW
TRIVIAL  → LOW  (CodeBoard has no TRIVIAL)
```

**Idempotency:** Before creating, check if a FEATURE issue with `labels` containing the `BacklogItem.id` already exists. If yes, return it without creating duplicates. This guards against partial-failure + retry scenarios.

**Rollback on partial failure:** If issue creation fails mid-tree (e.g., network error after creating FEATURE but before EPICs), a compensation action runs: mark all created issues with `status=CANCELLED`, append rollback event to `BacklogActivity`, leave `BacklogItem.status=APPROVED` for retry. Do NOT silently leave orphan issues.

---

### 7.2 Backlog → AutoPilot Queue

After CodeBoard issues are created, if `queueIfHighPriority=True` and `priority >= HIGH`:

```
POST /api/execute/queue
Content-Type: application/json

{
  "issueId": "<featureIssueId>",
  "mode": "implement",
  "priority": "HIGH",
  "metadata": {
    "sourceBacklogItemId": "<backlog_item_id>",
    "promotedAt": "<iso_timestamp>"
  }
}
```

This calls the existing AutoPilot queue endpoint (CB-1951). The promote pipeline stores the returned `queueId` in `BacklogActivity` for traceability.

**If the AutoPilot queue is currently WAITING_RESET or PAUSED:** the promote pipeline still succeeds (CodeBoard issues are created), but `autopilotQueueId` in the response will be null and a `BacklogActivity` row is appended: `{ "action": "AUTOPILOT_QUEUE_SKIPPED", "reason": "queue_paused", "retryAfter": "<iso>" }`. The user can manually trigger queuing from the Backlog card.

---

### 7.3 Chat Agent Reading CodeBoard Issues

When a Studio session's Jonny agent needs to read existing CodeBoard issues for context (e.g., "what issues exist for project X?"), it uses the existing search endpoint via the `add_to_codeboard` consolidated tool:

**RAG search (semantic):**
```
POST /api/search/{project_id}/semantic
{
  "query": "<natural_language_query>",
  "limit": 10
}
```

**Keyword issue search:**
```
GET /api/projects/{project_id}/issues?search=<query>&pageSize=20
```

These are internal calls from `studio_orchestrator.py`, not exposed as new endpoints. The agent receives a distilled 1-2K artifact from the RAG results, not the raw API response (sub-agent context isolation principle).

---

### 7.4 Chat Agent Triggering RAG Search

The `studio_orchestrator.py` calls `rag_service.semantic_search()` directly (service-to-service), not through the HTTP API. This avoids an extra HTTP hop and re-uses the existing `RAGService` class.

```python
# In studio_orchestrator.py
from services.rag_service import RAGService

async def _rag_context_for_session(
    session: StudioSession,
    query: str,
    rag: RAGService,
) -> str:
    """Fetch relevant CodeBoard context for a chat turn."""
    results = await rag.semantic_search(
        project_id=session.projectId,
        query=query,
        limit=10,
    )
    # Distill to 1-2K token artifact
    return _distill_rag_results(results)
```

---

### 7.5 Agent Activity → Crew Map

Every `StudioAgentActivity` row creation and status update publishes a crew map event. This is implemented as a SQLAlchemy after_flush event hook in `crew_map_service.py`:

```python
# In crew_map_service.py
async def on_agent_activity_change(activity: StudioAgentActivity) -> None:
    """Publish crew map edge update when agent activity changes."""
    event = CrewMapEdgeUpdatedEvent(
        edgeId=activity.id,
        status="ACTIVE" if activity.status == "RUNNING" else "PAST",
        animated=activity.status == "RUNNING",
    )
    await project_event_bus.publish(activity.session.projectId, event)
```

---

## 8. Versioning + Backward Compatibility

### 8.1 Namespace

All new Studio/Backlog/Crew Map routes live under their resource-specific prefixes:
- `/api/studio/...`
- `/api/backlog/...`
- `/api/crew-map/...`

These are distinct from the existing `/api/issues`, `/api/execute`, `/api/qa` namespaces. No versioning prefix (`/api/v1/`) is added in Phase 1 — the existing convention in this codebase uses no version prefix (see current `api/__init__.py`). A version prefix is reserved for when a breaking change occurs.

### 8.2 Breaking Change Policy

A change is "breaking" if it:
- Removes or renames a field from a response
- Changes the type of an existing field
- Removes an endpoint
- Changes an HTTP method on an existing endpoint
- Narrows accepted input (e.g., reducing max length)

**Breaking change procedure:**
1. Add the new shape alongside the old (additive, non-breaking) for one release
2. Mark old field/endpoint deprecated in OpenAPI: `deprecated: true` + `x-sunset-date`
3. Sunset after 60 days minimum (one sprint cycle for clients to adapt)
4. Never remove without a sunset date in the changelog

### 8.3 Non-breaking Additions (always allowed without version bump)

- New optional request fields (ignored by old clients)
- New response fields (ignored by old clients using strong types)
- New query parameters with defaults
- New SSE event types (old clients ignore unknown events)
- New error codes in the `ErrorCode` enum

### 8.4 Version Prefix Trigger

If a breaking change cannot be avoided, introduce `/api/v2/studio/...` alongside `/api/studio/...` (which implicitly becomes `v1`). Route both through the same router tree using FastAPI's `prefix` parameter. The v1 routes stay alive for 90 days after v2 launch.

### 8.5 Deprecation Headers

All deprecated endpoints should return:
```
Deprecation: true
Sunset: <RFC 7231 HTTP-date>
Link: </api/v2/studio/sessions>; rel="successor-version"
```

---

## 9. Error Catalog

All errors follow the existing `ErrorResponse` shape from `app/errors.py`:
```json
{
  "success": false,
  "error": "ERROR_CODE",
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": { "resource": "...", "field": "..." }
}
```

New error codes added to `ErrorCode` enum:

| Code | HTTP | When |
|---|---|---|
| `SESSION_LIMIT_EXCEEDED` | 429 | More than 8 concurrent ACTIVE sessions |
| `SESSION_NOT_RESUMABLE` | 409 | Session is ARCHIVED, cannot resume |
| `SUBPROCESS_UNAVAILABLE` | 503 | Claude subprocess pool exhausted |
| `TOKEN_BUDGET_EXCEEDED` | 402 | Session has consumed its token budget |
| `AGENT_MUTEX_LOCKED` | 409 | A skill is already active under GroupQueue lock |
| `CHAIN_DEPTH_EXCEEDED` | 400 | Inter-agent message chain > 3 |
| `PROMOTE_ALREADY_RUNNING` | 409 | Promote job already in progress for this item |
| `PROMOTE_ITEM_NOT_READY` | 400 | Item must be APPROVED before promoting |
| `IDEMPOTENCY_CONFLICT` | 409 | Idempotency key reused with different payload |
| `INVALID_CRON_EXPRESSION` | 400 | Cron string failed croniter parse |
| `INVALID_TIMEZONE` | 400 | Timezone not in IANA database |
| `ARTIFACT_TOO_LARGE` | 413 | Artifact > 500 KB |
| `GRAPH_COMPUTATION_TIMEOUT` | 503 | Crew map graph exceeded compute budget |

**Tenant-scoped 404 (non-negotiable):**

Cross-tenant resource access always returns 404, never 403. The error code is `NOT_FOUND` — identical to a genuinely missing resource. This prevents tenant enumeration via error code discrimination.

---

## 10. Rate Limit Matrix

Rate limits use the existing `app/rate_limit.py` (slowapi/AIOHTTP limiter). New limits:

| Endpoint Group | Limit | Window | Key |
|---|---|---|---|
| `POST /api/studio/projects/*/sessions` | 20 | 1 hour | tenant_id |
| `POST /api/studio/sessions/*/messages` | 5 | 1 minute | session_id |
| `POST /api/studio/sessions/*/send-to-backlog` | 10 | 1 hour | session_id |
| `POST /api/studio/sessions/*/artifacts` | 30 | 1 hour | session_id |
| `POST /api/backlog/projects/*/items` | 100 | 1 hour | tenant_id |
| `POST /api/backlog/items/*/promote` | 10 | 1 hour | tenant_id |
| `GET /api/crew-map/projects/*/graph` | 60 | 1 minute | tenant_id |
| SSE connections (total) | 8 concurrent | — | tenant_id |

Rate limit responses return:
```
HTTP 429 Too Many Requests
Retry-After: <seconds>
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: 0
X-RateLimit-Reset: <unix_timestamp>
```

---

## 11. OpenAPI Tags and Router Registration

Add to `backend/api/__init__.py`:

```python
from api.studio import router as studio_router
from api.backlog import router as backlog_router
from api.crew_map import router as crew_map_router

router.include_router(studio_router, tags=["studio"])
router.include_router(backlog_router, tags=["backlog"])
router.include_router(crew_map_router, tags=["crew-map"])
```

Router prefixes in each file:
```python
# api/studio.py
router = APIRouter(prefix="/studio")

# api/backlog.py
router = APIRouter(prefix="/backlog")

# api/crew_map.py
router = APIRouter(prefix="/crew-map")
```

---

## 12. Authentication Notes

Current deployment uses `InternalAuthDep` (shared secret via `X-Internal-Token` header). All new Studio/Backlog/Crew Map endpoints that read or write project data should include `InternalAuthDep` as a dependency — same as the pattern in `execution.py`.

SSE endpoints specifically must require auth before opening the stream to prevent token leakage via connection timing.

The `get_tenant_id` dependency reads `X-Tenant-ID` set by the Next.js proxy (trusted server-to-server). In the current single-tenant deployment, `settings.DEFAULT_TENANT_ID` is returned when the header is absent, keeping dev workflow intact.

---

## 13. Implementation File Map

New files to create:

```
backend/
├── api/
│   ├── studio.py           # Section 3 endpoints
│   ├── backlog.py          # Section 4 endpoints
│   └── crew_map.py         # Section 5 endpoints
├── models/
│   ├── studio.py           # StudioSession, StudioMessage, StudioArtifact,
│   │                       # StudioAgentActivity, StudioInterAgentMessage,
│   │                       # AgentTemplate, AgentInstance
│   ├── backlog.py          # BacklogItem, BacklogComment, BacklogActivity
│   └── crew_map.py         # CrewAssignment, CrewSkillUsage
├── services/
│   ├── studio_orchestrator.py  # multi-session manager (extends terminal_service)
│   ├── agent_dispatcher.py     # typed verbs + GroupQueue mutex + chain-depth
│   ├── promote_pipeline.py     # Blueprint state machine
│   ├── crew_map_service.py     # graph aggregator + SSE publisher
│   └── feature_scheduler.py   # cron + one-shot scheduler loop
└── api/
    └── deps.py             # add get_tenant_id + get_tenant_scoped_resource
```

Existing files modified:
```
backend/api/__init__.py     # register 3 new routers
backend/api/deps.py         # add get_tenant_id, get_tenant_scoped_resource
backend/app/errors.py       # add new ErrorCode values (Section 9)
backend/app/config.py       # add MULTI_TENANT, DEFAULT_TENANT_ID settings
```

---

*End of Studio API Contract — 2026-05-20*
