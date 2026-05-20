# Studio Cloud + Multi-Tenant Architecture
## AI Project Workspace — SaaS-Ready Design

**Date:** 2026-05-20
**Author:** Cloud Architect (AI)
**For:** Eli Cohen / ProjectsManagerWebV2Production
**Status:** PROPOSED — design document, awaits approval before implementation tickets
**Applies to:** AI Project Workspace (Studio + Backlog + Crew Map) — the new layer above CodeBoard
**Companion plan:** `docs/plans/2026-05-07-ai-project-workspace-master-plan.md`

---

## Framing: What "Cloud-Ready" Means for This Platform

The current platform is an intentionally single-user, single-machine system. It runs FastAPI + Next.js with SQLite (two databases: `backend/data/codeboard.db` via SQLAlchemy async, and `frontend/prisma/dev.db` via Prisma), ChromaDB on port 8402, and Claude Code CLI subprocesses spawned by `terminal_service.py`. All of this is designed to run on one box, hardcoded to loopback addresses, with no user identity beyond `InternalAuthDep` (a single machine-to-machine shared secret).

The Studio feature must be designed so that none of the existing CodeBoard machinery breaks, the system can ship to a second user on day one of SaaS launch, and the full target is reachable without a rewrite — only migrations and configuration changes.

The six questions below are answered in dependency order: tenancy model first, because every other decision flows from it.

---

## 1. Tenancy Model

### Decision: Shared Database with `tenant_id` Column on Every Table (Option A)

**Rejected alternatives:**

- **Schema-per-tenant (Option B):** PostgreSQL supports this and it gives clean DDL isolation, but it makes cross-tenant analytics impossible, complicates migration rollouts (you must migrate N schemas, not one), and at SaaS scale you quickly hit PostgreSQL's 10,000-connection ceiling when each tenant needs its own connection pool. It is the right choice only when tenants have regulatory requirements for physical DDL isolation (HIPAA, FedRAMP), which is not the starting requirement here.

- **Database-per-tenant (Option C):** Strong isolation, simple backup-per-tenant story, but operationally expensive: each tenant database needs its own compute/storage billing unit, connection pool, and migration job. At 1,000 tenants, you are managing 1,000 Postgres instances. This is appropriate only for enterprise on-premise deployments or GDPR jurisdictions requiring data residency by customer contract.

**Why Option A is correct for SaaS-scale economics here:**

The Studio feature's dominant cost is LLM token spend, not database rows. A shared PostgreSQL database with `tenant_id` columns delivers:

- One connection pool (PgBouncer or asyncpg's built-in pool), shared across all tenants — cost-efficient at startup
- One migration run per release instead of N
- Row-level security (RLS) in PostgreSQL enforces the isolation guarantee at the database engine layer, independent of application code — this is the key hard-isolation mechanism
- Cross-tenant aggregate metrics (token burn, feature throughput) are trivially queryable for platform analytics
- The blast radius of a bug is bounded: an application bug that forgets `WHERE tenant_id = ?` will be caught by RLS before data crosses tenant lines, provided RLS is configured correctly

**The isolation mechanism is PostgreSQL Row-Level Security, not application-layer filtering alone.** Application filtering is a first defense; RLS is the backstop.

### Tenant Data Model

Every table that holds tenant-owned data gains a `tenant_id` column. The `Tenant` and `TenantMembership` tables are new platform-level tables that sit outside the application data schema.

```
Tenant
  id              CUID  PK
  slug            TEXT  UNIQUE  -- URL slug, e.g. "acme-corp"
  displayName     TEXT
  plan            ENUM(free, pro, enterprise)
  createdAt       TIMESTAMP
  settings        JSONB         -- per-tenant feature flags, token budgets

TenantMembership
  id              CUID  PK
  tenantId        CUID  FK -> Tenant.id
  userId          CUID  FK -> User.id
  role            ENUM(owner, admin, member, viewer)
  createdAt       TIMESTAMP

User
  id              CUID  PK
  email           TEXT  UNIQUE
  displayName     TEXT
  hashedPassword  TEXT          -- only if using local credential auth
  externalId      TEXT          -- sub claim from OIDC provider
  provider        TEXT          -- "github", "google", "local"
  createdAt       TIMESTAMP
```

All existing tables — `Issue`, `Project`, `AutoPilotQueueRecord`, `StudioConversation`, `FeatureRequest`, `CrewAssignment`, etc. — gain:

```
tenant_id   TEXT  NOT NULL   REFERENCES Tenant(id)
```

This column is the partition key for RLS policies.

### PostgreSQL RLS Configuration

```sql
-- Enable RLS on every tenant-partitioned table
ALTER TABLE "Issue" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Project" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "StudioConversation" ENABLE ROW LEVEL SECURITY;
-- ... repeat for all tenant-partitioned tables

-- Create a policy that reads the tenant from a session-level setting
-- set by the FastAPI dependency before any query runs
CREATE POLICY tenant_isolation ON "Issue"
  USING (tenant_id = current_setting('app.current_tenant_id'));
```

The FastAPI database session factory sets `SET LOCAL app.current_tenant_id = '<tenant_id>'` at the start of every transaction. This means even if application code omits `WHERE tenant_id = ?`, PostgreSQL rejects the row at the storage layer.

The backend service account (the PostgreSQL user that FastAPI connects as) must NOT be a superuser — superusers bypass RLS. Use a `BYPASSRLS` grant only for the migration/admin role, never for the runtime application role.

### Migration Path from SQLite

The migration has four phases. Each phase is independently deployable and non-breaking to the running single-user instance.

**Phase 0 — Dual-database period (today to MVP launch):**
SQLite continues to serve the single-user instance. No migration yet. The Studio feature is built and tested against SQLite locally, using the `tenant_id` columns but with a single hardcoded tenant (`SINGLE_TENANT_ID = "local-dev"`). All new Studio tables include `tenant_id` from the first migration.

**Phase 1 — PostgreSQL introduction (before first external user):**
Provision a PostgreSQL 16 instance (target: Supabase or Neon, see Section 4). Generate Alembic migrations from the current SQLAlchemy models. The `DATABASE_URL` env var switches from `sqlite+aiosqlite://` to `postgresql+asyncpg://`. The `engine` instantiation in `database.py` already supports this by design: `create_async_engine(settings.DATABASE_URL, ...)` is database-agnostic. Remove the SQLite-specific `PRAGMA` event listener and the `aiosqlite` connect args. The Prisma schema on the frontend switches from `provider = "sqlite"` to `provider = "postgresql"` and runs `prisma migrate deploy`.

**Phase 2 — Single-tenant seeding:**
Run a one-time migration script that:
1. Creates a `Tenant` record for the existing user (slug = "eli-local", plan = "pro")
2. Creates a `User` record from `ownerEmail` fields
3. Backfills `tenant_id` on all existing rows
4. Enables RLS policies

**Phase 3 — Multi-tenant open (SaaS launch):**
Add the auth layer (Section 2), the identity API, and tenant provisioning endpoints. RLS is already enforced. Onboard the first external tenant.

---

## 2. Identity and Auth

### Current State

`InternalAuthDep` is a single shared `INTERNAL_API_TOKEN` checked against `X-Internal-Token` header. It is a machine-to-machine perimeter control, not a user identity system. CB-2121 (Backend Auth Layer + Project Scoping) is the open ticket for proper per-user identity — it is unimplemented as of today.

There is no JWT, no session cookie, no user object in request context, and no RBAC anywhere in the codebase. Every request is trusted if it originates from the localhost origin or carries the internal token.

### Target: JWT-Based Tenant-Scoped Identity at the FastAPI Dependency Layer

The auth strategy is a stateless signed JWT. This is the correct choice for a SaaS platform because:

- Stateless — no session store to scale or replicate across instances
- Self-describing — the tenant claim lives inside the token, eliminating a database lookup per request to establish tenant context
- Standard — OIDC providers (GitHub, Google, Auth0) issue compatible tokens
- Container-friendly — any replica can verify the token with the public key

**Token structure:**

```json
{
  "sub": "user_cuid_here",
  "tenant_id": "tenant_cuid_here",
  "tenant_slug": "acme-corp",
  "role": "member",
  "email": "user@example.com",
  "iat": 1716192000,
  "exp": 1716195600,
  "iss": "https://auth.projectsmanager.io",
  "aud": "projectsmanager-api"
}

```

Short expiry (1 hour) with a refresh token stored in an httpOnly cookie. Access token delivered in the response body, stored in memory (not localStorage — mitigates XSS exfiltration). Refresh token is httpOnly, SameSite=Strict, Secure — survives page reload without being accessible to JavaScript.

**Where the auth layer sits:**

The auth layer is a FastAPI dependency, NOT a gateway. This keeps the architecture simple for an early-stage SaaS and avoids adding an API gateway until traffic justifies it. The dependency is composable alongside the existing `InternalAuthDep`.

```python
# backend/app/auth.py (new file)

class TenantContext(BaseModel):
    user_id: str
    tenant_id: str
    tenant_slug: str
    role: str
    email: str

async def get_tenant_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """
    Extracts and validates the JWT from the Authorization header.
    Sets app.current_tenant_id on the database session for RLS.
    Raises HTTP 401 on missing/invalid/expired token.
    Raises HTTP 403 on valid token but insufficient role.
    """
    token = _extract_bearer(request)
    claims = _verify_jwt(token, settings.JWT_PUBLIC_KEY)
    # Set RLS context on the database session
    await db.execute(
        text("SET LOCAL app.current_tenant_id = :tid"),
        {"tid": claims["tenant_id"]}
    )
    return TenantContext(**claims)

TenantDep = Depends(get_tenant_context)
```

All Studio, Backlog, and Crew Map API routers receive `TenantDep`. Existing CodeBoard routers retain `InternalAuthDep` during the migration period and migrate to `TenantDep` as part of CB-2121 resolution.

**Backward compatibility strategy for CB-2121:**

`InternalAuthDep` and `TenantDep` are mutually exclusive resolution paths in a new `UnifiedAuthDep` that checks:

1. If `MULTI_TENANT_MODE=false` (env var, default during migration): use `InternalAuthDep` path, inject a synthetic `TenantContext` with the single-tenant seed values. No behavioral change to existing endpoints.
2. If `MULTI_TENANT_MODE=true`: require JWT, enforce `TenantDep` on all routes.

This flag allows the existing CodeBoard to keep running while the auth layer is built around it.

**JWT signing key management:**

- Development: symmetric HS256 with a local `JWT_SECRET` env var
- Production: asymmetric RS256 with a private key in the cloud provider's secrets manager (AWS Secrets Manager / Doppler / Infisical). The public key is available to all replicas at startup via a JWKS endpoint. Key rotation is handled by the secrets manager without redeploying.

**Auth flows:**

- Social login (GitHub OAuth2): user redirects to `/auth/github`, backend exchanges code for GitHub access token, creates/upserts `User` record, issues the platform JWT. Recommended as the day-one auth method because Eli already uses GitHub heavily.
- Magic link email (Resend or Postmark): fallback for users without GitHub. The Next.js `/api/auth/magic-link` route sends a signed link; clicking it hits the FastAPI backend and issues the JWT.
- OIDC (Google, Auth0): wired in Phase 2 for enterprise tenants.

**Token delivery to the frontend:**

The Next.js frontend stores the access token in memory (React context / Zustand store). The `fetch()` calls in all existing hooks (`useCodeBoard.ts`, etc.) add `Authorization: Bearer <token>` headers. The refresh token in an httpOnly cookie is automatically sent by the browser on every request to the same origin; the backend `/auth/refresh` endpoint issues a new access token.

---

## 3. State Externalisation

This is the most consequential section. Every component that holds state locally must be evaluated: what breaks if the process restarts, what breaks if there are two replicas, and what the cloud target is.

### 3a. Primary Database: SQLite → PostgreSQL (Supabase or Neon)

**Current state:** Two SQLite files (`backend/data/codeboard.db` and `frontend/prisma/dev.db`). The backend and frontend both read/write these files from the local filesystem. The `database.py` uses `aiosqlite` with WAL mode and a 30-second busy timeout to manage concurrent writes.

**Why SQLite cannot stay for multi-tenant cloud:**

- Single writer lock: WAL mode helps reads but writes still serialize. At 10 concurrent tenants running AutoPilot queues, write contention is immediate.
- File-local: two replicas of the FastAPI backend would each need their own file, or share a network file system — NFS for a database is an anti-pattern.
- No RLS: SQLite has no row-level security mechanism.

**Cloud target:** PostgreSQL 16 on Supabase (recommended) or Neon.

Supabase is the recommended choice because:
- Managed PostgreSQL with built-in RLS enforcement UI and key management
- Supabase Auth can replace or supplement the custom JWT layer in Phase 2, reducing code owned
- pgvector extension is available — relevant for replacing or supplementing ChromaDB (see 3c)
- Connection pooling via PgBouncer is built in
- Free tier covers the MVP period; Pro at $25/month covers early SaaS

Neon is the alternative if serverless cold-start economics matter more than the Auth integration.

**Migration effort:** The SQLAlchemy models are database-agnostic. Swapping `sqlite+aiosqlite://` for `postgresql+asyncpg://` in `DATABASE_URL` is the only code change required. The Prisma schema requires a provider swap and `prisma migrate deploy` against the new database. One-time data migration via `pg_dump`-equivalent or a Python migration script that reads from SQLite and bulk-inserts into PostgreSQL.

**Blast radius:** High if done incorrectly. Low if done with the dual-database period (Phase 0 above). The key risk is the Prisma schema: Prisma generates slightly different migration SQL for PostgreSQL versus SQLite, and some column types differ (`TEXT` maps cleanly, but `BOOLEAN` and `DATETIME` have subtle differences). A migration rehearsal against a staging PostgreSQL before switching production is mandatory.

### 3b. In-Memory Session State: terminal_service → Persistent Queue Table (already partly done)

**Current state:** `terminal_service.py` stores active Claude Code CLI sessions in `_sessions: dict[str, TerminalSession]` in process memory, protected by `_sessions_lock`. The AutoPilot queue service (`autopilot_queue_service.py`) already addresses this for the queue layer: CB-1951 implemented write-through persistence to `AutoPilotQueueRecord` / `AutoPilotTaskRecord` / `AutoPilotEvent` tables, with `rehydrate_from_db()` on startup.

**What is not yet externalized:** The in-memory session dictionary in `terminal_service.py` itself — individual session state (status, progress, token counts, current subprocess PID) is rebuilt from DB on startup by the rehydrate path, but the running subprocess is not transferable between replicas.

**Cloud target for single-replica (MVP):** No change required. The existing rehydrate pattern already handles process restart. The blast radius of a process crash is bounded: the queue pauses, the user sees the crash recovery banner, and resumes manually — exactly as today.

**Cloud target for multi-replica (Phase 2):** This is the hard problem. Claude Code CLI subprocesses cannot migrate between hosts. The solution is a dedicated Execution Worker service (see Section 4, AutoPilot compute). The main API replicas become stateless request handlers; execution tasks are dispatched via a queue (Redis Streams or a dedicated PostgreSQL table acting as a queue) to a pool of Execution Workers. Each worker owns the subprocess for its lifetime. Session state is written to PostgreSQL after each status change, so any replica can display the current status by reading the database.

**The Studio conversation subprocess** has the same problem as AutoPilot. A Studio tab's Claude Code subprocess runs on one machine. In the cloud, each Studio conversation must be "sticky" to one Execution Worker for its duration, or the conversation must be mediated by a persistent queue that routes messages to the correct worker. The recommended pattern is sticky routing via a consistent hash of `conversationId` to an Execution Worker ID, held in Redis. When the worker restarts, the conversation is orphaned and must be resumed from the last persisted snapshot (`PLANNING_STATE.md` snapshots, as planned in E2.S8).

### 3c. ChromaDB → pgvector (Recommended) or Managed Vector Service

**Current state:** ChromaDB running on port 8402 as a separate container. The `rag_service.py` probes it at startup and falls back to a local `PersistentClient` using `backend/data/chroma/chroma.sqlite3`. The RAG pipeline indexes `ExecutionSummary` embeddings and serves them to `documentation_generator` and `qa_service`.

**The cloud problem:** The local ChromaDB container stores its data on a volume (`chroma_data` in `docker-compose.yml`). A cloud container restart without a persistent volume drops all indexed data. A managed ChromaDB service (ChromaDB Cloud) exists but is expensive and adds a third third-party service contract.

**Recommended cloud target: pgvector on the same Supabase PostgreSQL instance.**

pgvector is a PostgreSQL extension that provides vector similarity search with `<->` (L2), `<#>` (inner product), and `<=>` (cosine) operators. If the platform is already on Supabase, pgvector is available at no additional cost. The `rag_service.py` abstraction layer (already in place with the fallback pattern) can be replaced with a pgvector implementation without touching call sites. Supabase enables pgvector with a single SQL command.

The trade-off: pgvector's HNSW index is not as fast as ChromaDB's HNSW for pure vector workloads at millions of embeddings. For this platform at SaaS scale (thousands of execution summaries per tenant, not billions), pgvector performance is more than sufficient. The operational simplification of eliminating a separate service outweighs the marginal performance difference.

**Alternative if vector-only service is preferred:** Pinecone Serverless (pay-per-query, no idle cost) or Weaviate Cloud. Both require an API client swap in `rag_service.py` and per-tenant namespace/collection isolation.

**Migration:** Existing ChromaDB embeddings can be exported via the ChromaDB Python client and re-inserted into pgvector. This is a one-time script. Namespace isolation in pgvector is achieved by including `tenant_id` as a metadata filter column alongside the vector column — same RLS policy applies.

### 3d. Local Filesystem Artifacts → Object Storage

**Current state:** Claude Code CLI subprocesses write files to the local filesystem (project working directories). `StudioArtifact` rows store the `payload` as text (markdown, mermaid, code) directly in the database. The `shell.ts` and `terminal_service.py` reference local paths.

**What must move:** For cloud, file artifacts (generated code, diagrams, plan documents) that are large or binary must move to object storage. Small text artifacts (under 64KB) can stay as database columns. Large artifacts and project working directories must move to S3-compatible storage.

**Cloud target:** AWS S3 (if on AWS) or Cloudflare R2 (if on Fly/Render — R2 is S3-compatible, no egress fees, cheaper at this scale).

**Artifact storage strategy:**

- Small text artifacts (markdown, mermaid, code snippets): stored in `StudioArtifact.payload` column as today. Threshold: 64KB. No change required.
- Large artifacts (generated full files, ZIP archives, HTML previews): stored in S3/R2, `StudioArtifact.storageKey` column holds the object key. Served via a pre-signed URL with a 15-minute expiry. The FastAPI `GET /api/studio/artifacts/{id}/download` endpoint generates the pre-signed URL.
- Project working directories for Execution Workers: each worker gets an ephemeral volume (Fly.io machine volume, or EBS-attached EFS). For the Studio feature, the working directory is the Studio conversation's scratch space, not a git repository — it is created fresh per conversation and archived to S3 on hibernation.

**Blast radius:** Low initially. Text artifacts stay in the database. Object storage is additive, not a replacement for existing functionality.

### 3e. AutoPilot Subprocess Execution: Local Claude CLI → Cloud Execution Sandbox

This is the highest-complexity state externalisation and the most critical for multi-tenant safety.

**Current state:** `terminal_service.py` spawns `claude -p ... --output-format stream-json` as a local subprocess. The subprocess runs with the same OS user permissions as the FastAPI backend. It has access to the full local filesystem, including other tenants' project directories (in a single-user system, there are no other tenants, so this is not a risk today). The AutoPilot queue sequences these subprocesses one at a time per queue.

**The cloud multi-tenant problem:** In a SaaS context, one tenant's Claude Code subprocess must not be able to read files or environment variables belonging to another tenant's subprocess. Process-level isolation on a shared host is insufficient — even with `chroot` or Unix user isolation, a kernel vulnerability or misconfiguration could cross tenant boundaries. The correct primitive is container-level isolation: each subprocess execution runs in its own container.

**Recommended cloud target: Fly.io Machines API (recommended) or AWS Fargate (for AWS-native deployments).**

The Fly.io Machines API is recommended because:
- A Machine is a single-tenant ephemeral micro-VM (gVisor-isolated) that starts in under 1 second
- The API is a simple HTTP call: `POST /v1/apps/{app}/machines` with the container image and command
- Machines auto-destroy when the process exits — no cleanup code required
- Fly.io's private networking (WireGuard mesh) allows the Execution Worker to stream output back to the FastAPI backend via a private address
- Pricing: ~$0.0000064/second per vCPU — a 30-minute Claude Code session on 1 vCPU costs about $0.01 in compute

**Execution flow (cloud):**

```
User triggers "Start AutoPilot" on Issue CB-1234
  → FastAPI backend enqueues AutoPilotTask to PostgreSQL task table
  → Execution Dispatcher service (long-running) polls the task table (or listens via LISTEN/NOTIFY)
  → Dispatcher calls Fly Machines API: POST /v1/apps/pmv2-executor/machines
      body: { image: "ghcr.io/pmv2/executor:latest", cmd: ["claude", "-p", ...], env: { ISSUE_ID: "..." } }
  → Fly starts a new Machine with the executor container
  → Executor runs claude CLI, streams output via stdout
  → Executor sends stream-json events back to the Dispatcher via HTTP POST to a private callback URL
  → Dispatcher forwards events to the FastAPI SSE channel for the frontend
  → Machine exits when claude completes; Fly destroys it
  → Dispatcher marks AutoPilotTask COMPLETED, updates issue status
```

The executor container image is built from the existing `terminal_service.py` logic, packaged as a standalone Python process that accepts an issue ID and project context, runs Claude Code CLI, and POSTs structured events to the callback URL.

**Alternative: AWS Fargate** follows the same pattern but uses ECS task definitions. Fargate tasks start in 10-30 seconds, which is acceptable for AutoPilot queue items but too slow for interactive Studio conversations.

**For interactive Studio conversations** (which require low-latency subprocess start for the first message), the recommended approach is a pool of warm Fly Machines that are paused between conversations and resumed when a user sends a message. Fly Machines support `suspend`/`resume` — a suspended machine retains its memory state and resumes in under 100ms. This is the cloud equivalent of the local subprocess hibernation pattern (E2.S8).

---

## 4. Deployment Topology

### Recommended Cloud Stack

This stack is chosen for simplicity (fewest distinct services for the MVP), cost-efficiency at early SaaS scale, and the ability to replace any component independently as the platform grows.

```
Service           Provider              Tier/SKU                    Monthly Cost (est.)
─────────────────────────────────────────────────────────────────────────────────────
Frontend (Next.js) Vercel               Pro ($20/mo, 1 seat)         $20
Backend (FastAPI)  Fly.io               shared-cpu-2x, 512MB RAM     $7-14
PostgreSQL         Supabase             Pro ($25/mo)                 $25
Vector DB          pgvector on Supabase (included in Pro)            $0
ChromaDB           retired              (replaced by pgvector)       $0
Execution Workers  Fly.io Machines API  pay-per-second               $0-50 (usage)
Redis              Upstash              pay-per-request              $0-5
Object Storage     Cloudflare R2        $0.015/GB/mo                 $0-2
Auth               self-hosted JWT      (in FastAPI backend)         $0
CDN/Edge           Vercel Edge Network  (included in Vercel Pro)     $0
─────────────────────────────────────────────────────────────────────────────────────
Total (idle/light)                                                   ~$55/month
Total (active SaaS, 10 tenants)                                      ~$100-150/month
```

### Why These Providers

**Vercel for Next.js:**
The existing frontend uses Turbopack (Next.js 16.1.2 with App Router). Vercel is the native deployment target for this stack. Edge functions, ISR, and the existing React Query + SSE pattern work without modification. The `NEXT_PUBLIC_API_URL` env var points to the Fly.io backend. The only code change is replacing hardcoded `http://localhost:8401` URLs with `process.env.NEXT_PUBLIC_API_URL`.

SSE (Server-Sent Events) for Studio's live agent activity and Crew Map live updates works on Vercel via Edge Streaming — responses must set `Content-Type: text/event-stream` and the Next.js API route must use `ReadableStream`. The existing SSE channels in the FastAPI backend are not affected; the Next.js frontend proxies them through `app/api/sse/[...path]/route.ts` if needed for CORS, or connects directly to the FastAPI backend URL.

**Fly.io for FastAPI backend:**
The existing FastAPI app is already containerized (`docker-compose.yml`). Fly.io accepts a Dockerfile directly. The `fly.toml` configuration sets:
- `internal_port = 8401`
- `[env]` section for all configuration (replacing `.env` file)
- `[mounts]` for no local storage (stateless — all state in PostgreSQL and object storage)
- `[services.concurrency]` soft limit of 25 concurrent connections per machine, to match asyncpg pool size

The `validate_origin` middleware in `main.py` must be updated to accept the Vercel deployment URL. `CORS_ORIGINS` becomes an env var list: `["https://app.projectsmanager.io", "https://app-git-*.vercel.app"]` (the glob for Vercel preview deployments).

The `HOST` and `ALLOW_LAN` settings become irrelevant in Fly's network model — Fly handles the public/private network boundary. The `INTERNAL_API_TOKEN` check on `InternalAuthDep` is replaced by `TenantDep` for Studio routes.

**Fly.io Machines for AutoPilot Execution Workers:**
As described in Section 3e. The Machines API is called from the FastAPI backend (or a separate Dispatcher service) directly. No separate orchestration layer (Kubernetes, ECS) is needed at this scale.

**Supabase for PostgreSQL + pgvector:**
One PostgreSQL instance serves both the SQLAlchemy backend and the Prisma frontend client. Connection string format for both:
- SQLAlchemy: `postgresql+asyncpg://postgres:[password]@db.[project].supabase.co:5432/postgres`
- Prisma: `postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres`

Supabase also provides the realtime WebSocket layer as an optional enhancement — if SSE proves problematic through Vercel's edge network, Supabase Realtime can replace the FastAPI SSE channels.

**Upstash Redis:**
Used for:
1. Rate limiting (existing `slowapi` rate limiter can use Redis as the backend instead of local memory, enabling rate limiting across replicas)
2. Execution Worker sticky routing (conversationId → Machine ID mapping)
3. Distributed lock for the AutoPilot queue's `_AUTO_RESUME_MAX_ATTEMPTS` circuit breaker (currently in-memory; needs to be shared across replicas)
4. SSE event fan-out: when an Execution Worker on Machine A updates task status, it publishes to a Redis channel; all FastAPI replicas subscribed to that channel can push the SSE event to connected clients

Upstash is chosen over ElastiCache/Upstash Redis Cloud alternatives because it is serverless (no idle cost), has a free tier, and the HTTP-based client works from serverless environments.

**Cloudflare R2 for object storage:**
Artifact storage as described in Section 3d. R2 is S3-compatible, zero egress fees to Cloudflare's network, and $0.015/GB/month storage. The `boto3` client (with custom endpoint URL) or the `cloudflare` Python SDK works from the FastAPI backend.

### Network Topology

```
Internet
    │
    ├──► Vercel Edge Network
    │        Next.js App (SSR + static)
    │        ↕ HTTPS to Fly.io backend (API calls + SSE)
    │
    ├──► Fly.io Private Network (WireGuard mesh — private to Fly)
    │        FastAPI Backend Machines (2 replicas min)
    │        ↕ asyncpg to Supabase PostgreSQL (external, TLS)
    │        ↕ HTTP to Upstash Redis (external, TLS)
    │        ↕ HTTP to Cloudflare R2 (external, TLS)
    │        ↕ Fly Machines API (internal) → Execution Worker Machines
    │
    └──► Execution Worker Machines (ephemeral, per-task)
             claude CLI subprocess
             ↕ private HTTP callback to FastAPI backend
             ↕ read project context from R2 or database
```

All inter-service communication over public internet uses TLS. The Fly private network is used only for the FastAPI-to-ExecutionWorker callback path, keeping that traffic off the public internet.

---

## 5. Cost and Scale Economics

### Per-Tenant Cost Breakdown

The dominant cost in this platform is LLM tokens, not infrastructure. Infrastructure costs are nearly fixed until very high tenant counts. Token cost is variable and directly proportional to feature usage.

**Infrastructure cost per tenant (shared, at 50 tenants):**

```
Component             Monthly Total   Per-Tenant (50 tenants)
────────────────────────────────────────────────────────────────
Vercel Pro            $20             $0.40
Fly.io backend        $30             $0.60
Supabase Pro          $25             $0.50
Upstash Redis         $5              $0.10
Cloudflare R2         $2              $0.04
────────────────────────────────────────────────────────────────
Infrastructure total  $82             $1.64/tenant/month
```

**Token cost per tenant (the real cost):**

A Studio conversation that plans a feature with Jonny orchestrating three skills for 30 minutes might consume:
- Input tokens: ~50,000 (conversation context, code context from RAG, skill prompts)
- Output tokens: ~15,000 (Jonny's responses, skill artifacts)

At Claude Sonnet 4.5 pricing (~$3/M input, ~$15/M output):
- Per conversation: (50,000 / 1,000,000 * $3) + (15,000 / 1,000,000 * $15) = $0.15 + $0.225 = $0.375

An active tenant planning two features per week: ~$3/month in tokens.

An active AutoPilot queue running 20 tasks per week (each task ~20K tokens combined):
- ~$1.20/month in tokens.

**Total active tenant cost: ~$5-7/month in tokens + $1.64 infrastructure = ~$7-9/month.**

**Minimum viable SaaS price point:** $29/month per tenant delivers a comfortable margin at this cost structure. A free tier capped at 10,000 tokens/month (roughly 2-3 Studio conversations) is operationally safe.

**Where the costs scale:**
- Token costs scale linearly with usage — the parked CB-2381 AI Cost Optimization plan (token budgets, caching, context compression) becomes financially important above 100 active tenants.
- Execution Worker compute scales linearly with concurrent AutoPilot runs — at 50 tenants each running 3 concurrent tasks, 150 Fly Machines at ~$0.01 each = $1.50/day = $45/month added.
- PostgreSQL is the least cost-sensitive component — Supabase Pro handles thousands of tenants on a single instance.

---

## 6. Day-One MVP Slice vs Full Target

### The Staircase

```
STEP 0 — TODAY (single-user, local)
  SQLite + local subprocess + no auth + loopback only
  Studio/Backlog/Crew Map built and tested locally
  tenant_id columns present but single hardcoded value
  Database: SQLite
  Execution: local claude CLI
  Auth: InternalAuthDep (shared secret)

STEP 1 — CLOUD-READY SINGLE-TENANT (MVP)
  Deploy existing app to Vercel + Fly.io + Supabase
  Switch DATABASE_URL to PostgreSQL
  Replace ChromaDB with pgvector
  Add JWT auth (GitHub OAuth2 as the only provider)
  Single tenant, single user (Eli on cloud)
  No external users yet
  Execution: Fly Machines for AutoPilot (one-at-a-time, as today)
  Studio conversations: still sticky to one Fly machine (no pool yet)
  Object storage: R2 for large artifacts
  Estimated timeline: 2-3 weeks after Studio feature ships locally

STEP 2 — MULTI-TENANT SOFT LAUNCH (Closed Beta)
  Tenant + TenantMembership + User tables added
  RLS enabled on all tables
  Tenant provisioning API (POST /api/tenants)
  Invite-only onboarding (manual invite token)
  Token budget enforcement per tenant (Tenant.settings.token_budget)
  Upstash Redis for distributed rate limiting and circuit breaker
  Warm Machine pool for Studio conversations (suspend/resume)
  Target: 5-10 beta tenants
  Estimated timeline: 6-8 weeks after MVP

STEP 3 — PUBLIC SAAS LAUNCH
  Self-serve signup and Stripe billing integration
  Magic link email auth (Resend) alongside GitHub OAuth2
  Per-tenant usage dashboard (token burn, feature throughput)
  Free tier token cap enforced
  Documentation for tenant onboarding
  SLA monitoring (uptime, P99 API latency)
  Estimated timeline: 12-16 weeks after MVP
```

### What the MVP Slice Is (Step 1 in concrete terms)

The smallest cloud-ready multi-tenant slice that ships first is not about adding external tenants — it is about making the existing single-user platform cloud-deployable so that the infrastructure is in place before the first external user arrives. Specifically:

1. **PostgreSQL swap** — DATABASE_URL points to Supabase. All existing tests pass against PostgreSQL. Prisma and SQLAlchemy both work.
2. **JWT auth for Studio routes only** — New routes (`/api/studio/*`, `/api/feature-backlog/*`, `/api/crew-map/*`) require a JWT. Existing CodeBoard routes continue using `InternalAuthDep` (the `MULTI_TENANT_MODE=false` path). GitHub OAuth2 is the only sign-in method.
3. **`tenant_id` column on all new tables** — `StudioConversation`, `FeatureRequest`, `CrewAssignment`, and all other Studio tables include `tenant_id` from day one of their creation. No backfill of existing tables yet.
4. **Fly.io deployment** — FastAPI backend runs on Fly.io with two replicas. `CORS_ORIGINS` updated to accept the Vercel domain.
5. **Vercel deployment** — Next.js frontend deployed to Vercel. `NEXT_PUBLIC_API_URL` env var points to the Fly backend.
6. **pgvector replacing ChromaDB** — `rag_service.py` pgvector implementation. ChromaDB container retired.
7. **R2 for large artifacts** — Artifacts over 64KB stored in Cloudflare R2. Smaller artifacts in the database.

Steps 2 and 3 are additive: they add tables, endpoints, and services without touching the existing CodeBoard machinery.

---

## Appendix A — Environment Variable Map (Cloud)

The following env vars replace `.env` file configuration in the cloud deployment. They are set via Fly.io secrets and Vercel environment variables respectively.

**FastAPI backend (Fly.io secrets):**

```
DATABASE_URL                    postgresql+asyncpg://postgres:***@db.***.supabase.co:5432/postgres
REDIS_URL                       rediss://***@***.upstash.io:6380
CHROMA_HOST                     retired
ANTHROPIC_API_KEY               sk-ant-***
JWT_PUBLIC_KEY                  -----BEGIN PUBLIC KEY-----\n...
JWT_SECRET                      (HS256 secret for development only)
JWT_ALGORITHM                   RS256
JWT_AUDIENCE                    projectsmanager-api
JWT_ISSUER                      https://auth.projectsmanager.io
GITHUB_CLIENT_ID                ***
GITHUB_CLIENT_SECRET            ***
INTERNAL_API_TOKEN              *** (kept for backward compat with CodeBoard routes)
CORS_ORIGINS                    ["https://app.projectsmanager.io","https://app-git-*.vercel.app"]
ENVIRONMENT                     production
MULTI_TENANT_MODE               false (Step 1) → true (Step 2+)
R2_ACCOUNT_ID                   ***
R2_ACCESS_KEY_ID                ***
R2_SECRET_ACCESS_KEY            ***
R2_BUCKET_NAME                  pmv2-artifacts
FLY_API_TOKEN                   *** (for dispatching Execution Worker machines)
FLY_APP_NAME                    pmv2-executor
```

**Next.js frontend (Vercel environment variables):**

```
NEXT_PUBLIC_API_URL             https://api.projectsmanager.io
NEXT_PUBLIC_APP_URL             https://app.projectsmanager.io
NEXT_PUBLIC_GITHUB_CLIENT_ID    ***
DATABASE_URL                    postgresql://postgres:***@db.***.supabase.co:5432/postgres
                                (Prisma reads this; only used server-side in API routes)
```

---

## Appendix B — What Does Not Change

The following components are explicitly NOT changed by this architecture. They continue to work as designed.

| Component | Current State | Cloud Status |
|---|---|---|
| AutoPilot crash recovery + rehydrate | `rehydrate_from_db()` on startup | Unchanged — PostgreSQL makes this more reliable |
| AutoPilot token-exhaustion circuit breaker | In-memory `_AUTO_RESUME_MAX_ATTEMPTS` | Moves to Redis for multi-replica safety (Step 2) |
| Status cascade (IN_PROGRESS, COMPLETED_WAITING_QA, DONE) | Existing `execution.py` logic | Unchanged |
| CodeBoard issue hierarchy (FEATURE → EPIC → STORY → TASK → SUBTASK) | Unchanged | Unchanged |
| `InternalAuthDep` | Shared secret for machine-to-machine calls | Retained alongside JWT (MULTI_TENANT_MODE flag) |
| CB-2121 (Backend Auth + Project Scoping) | Deferred | This document defines its target shape; implementation follows the Step 2 timeline |
| `validate_origin` middleware | Loopback guard | Updated to accept Vercel domain in ALLOWED_ORIGINS |
| SSE channels (GlobalAgentStatusBar, AutoPilot events) | EventSource polling | Unchanged in structure; Redis Pub/Sub added as fan-out layer in Step 2 |
| Docker Compose (local dev) | Three services | Retained for local development; PostgreSQL container added to replace SQLite in local dev |
| `WORKSPACE_ENABLED` feature flag (E8.S3) | Env var toggle | Works identically in cloud; set per Fly.io secret |

---

## Appendix C — Decisions Not Made Here (Deferred)

The following architectural decisions are explicitly deferred to avoid over-engineering before validation:

- **OIDC / SSO for enterprise tenants** — not needed until the first enterprise contract. Auth0 or WorkOS can be wired into the JWT layer later without structural changes.
- **Multi-region deployment** — Fly.io supports multi-region at the app level. The database (Supabase) would need read replicas per region. Deferred until P99 latency from a specific region becomes a problem.
- **Kafka / event streaming** — Redis Pub/Sub is sufficient for the SSE fan-out use case at this scale. Event streaming (Kafka, Redpanda) is a future consideration if audit log volume exceeds Redis capacity.
- **Kubernetes** — unnecessary overhead for this stack at early SaaS scale. Fly.io's Machine API provides the container orchestration needed.
- **Tenant-level encryption at rest** — PostgreSQL + Supabase provides encryption at rest for all data. Column-level encryption per tenant (e.g., encrypting `StudioMessage.content` with a per-tenant key) is a Phase 3+ consideration for HIPAA/SOC2 compliance tiers.
- **CB-2381 (AI Cost Optimization)** — the parked token budget plan. Becomes urgent at Step 3 when free-tier tenants can generate unbounded token spend. The `Tenant.settings.token_budget` column is stubbed in Step 1 but not enforced until Step 2.

---

*Document ends. Next step: present to Eli for approval, then create CodeBoard tickets for the Phase 1 infrastructure work (PostgreSQL migration, JWT auth, Fly.io deployment, pgvector migration) as a separate epic — E0 Infrastructure — before E1-E8 of the master plan execute.*
