# Documentation Pipeline Operational Runbook

This runbook covers the FeatureDocumentation generation surface — the
endpoint and pipeline that aggregates ExecutionSummaries, descendant
counts, and QA results into a single FeatureDocumentation row per
feature, and rebuilds it on demand.

It complements:

- `backend/api/documentation.py` — public API surface
- `backend/services/documentation_generator.py` — aggregation pipeline
- `backend/docs/AUTOPILOT_RUNBOOK.md` — sister runbook for AutoPilot

---

## 1. Endpoints (FeatureDocumentation)

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/features/{issue_id}/documentation` | Read the existing row |
| `POST` | `/api/features/{issue_id}/documentation/generate` | (Re)generate the row |

Both require `?projectId=…` (CB-2117 IDOR guard). A wrong projectId returns
the same 404 as a missing issue id — the response body never leaks issue
or doc content across project boundaries.

---

## 2. Rate limiting (CB-2662)

`POST /features/{id}/documentation/generate` is the most expensive
endpoint in the documentation surface. A single call:

1. Walks the feature's descendant tree (one SQL query per level)
2. Pulls every ExecutionSummary attached to those descendants
3. Aggregates QA task counts via `QATaskIssueLink`
4. **Calls a real AI provider** (`ai_service.generate_text`) for the
   narrative augmentation step (CB-1615)
5. Writes a FeatureDocumentation row + indexes into ChromaDB

Steps 4–5 dominate latency: a single call can pin a backend request
handler for up to 30s of LLM time and the proxy/client-side timeout is
**120s** (CB-2375).

### Limits in effect

| Layer | Limit | Source |
|---|---|---|
| Global per-IP | `200/minute` | `backend/app/main.py` (slowapi default) |
| **Per-route per-IP** | **`5/minute`** | `backend/api/documentation.py:_DOC_GEN_RATE_LIMIT` (CB-2662) |
| `projectId` scoping | required | CB-2117 |

`5/minute` was chosen because real users click "Regenerate" at most
twice an hour — five calls in one minute already represents
unrealistically aggressive interactive use. Any value below the cap
indicates either a debugging session or an automated abuser, and the
correct response in both cases is to slow the caller down.

### Why this matters before any non-localhost exposure

On the public internet (or any multi-tenant deploy), a caller who knows
or guesses a valid `(projectId, issueId)` pair could otherwise sustain
the global `200/min` cap on this single endpoint. With a 120s handler
timeout per call, that's enough to:

- Burn serverless concurrency on Vercel / equivalent platforms
- Run up real AI provider token spend
- Starve other traffic of request-handler slots

The per-route 5/min cap collapses the worst-case from 200 concurrent
2-minute calls down to 5, which is comfortably absorbed by any deploy
target we ship to.

### Tuning

If product telemetry shows legitimate users hitting the 5/min cap, the
right escalation path is **not** raising the limit — it's moving to the
job-and-poll architecture below. Raising the cap re-exposes the
DoS-amplification surface the cap was added to close.

### When the limit trips

Response: `429 Too Many Requests` with body
`{"error": "Rate limit exceeded: 5 per 1 minute"}`.

Frontend should surface a "you're regenerating too quickly — try again
in a minute" message and disable the Regenerate button until the
window has passed. The 60-second window is per-IP, not per-user, so a
single shared NAT could bunch users together — track this if it shows
up in support reports.

### Test coverage

`backend/tests/test_documentation_api.py` —
`test_generate_feature_documentation_rate_limit_boundary` runs 5
successful POSTs followed by a 6th that must return 429, all inside
the same 60s window. The fixture calls `slowapi.Limiter.reset()` on
every test setup so the bucket never spills across the ~22 sibling
tests that hit the same endpoint.

---

## 2a. Deploy-gate checklist before non-localhost exposure (CB-2662)

The 5/min cap only behaves as advertised when these gates are met. **Do
NOT promote the backend to a non-localhost / non-loopback deploy until
all of them are checked off.**

### Gate 1 — Trust the right client IP

`backend/app/rate_limit.py` keys the bucket on
`get_remote_address(request)`, which reads `request.client.host`. uvicorn
populates that from `scope["client"]` — and by default, ignores the
`X-Forwarded-For` header.

Behind a reverse proxy / CDN / load-balancer, every request looks like
it came from the proxy IP. **All traffic collapses into a single
5/min bucket** and a single attacker can DoS every legitimate user.

#### Fix (do BOTH)

1. Run uvicorn with proxy headers enabled and a strict allow-list:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port 8401 \
       --proxy-headers \
       --forwarded-allow-ips="<your-proxy-cidr>"
   ```
   Examples of `<your-proxy-cidr>`:
   - Cloud Run / Vercel: ask the platform for its egress CIDR or the
     specific load-balancer IPs. Never use `*` — that lets any client
     spoof its IP via `X-Forwarded-For`.
   - Single bastion: the bastion's static IP.
   - K8s ingress: the ingress controller's service CIDR.
2. Once `--proxy-headers` is on, **keep** `key_func=get_remote_address`
   in `app/rate_limit.py`. uvicorn rewrites `scope["client"]` from the
   right-most-trusted hop in `X-Forwarded-For`, so slowapi's call to
   `request.client.host` returns the real client without slowapi
   touching the header itself.

> **Do NOT** switch `key_func` to `slowapi.util.get_ipaddr`. That helper
> trusts the `X-Forwarded-For` header unconditionally — an attacker can
> spoof their bucket key and bypass the cap entirely. The fix lives at
> the uvicorn / proxy layer, not in slowapi.

### Gate 2 — One worker, or shared rate-limit storage

slowapi's default storage is in-memory — each worker process keeps its
own buckets. Today the backend runs as a single uvicorn process
(`launch.sh`, Dockerfile), so this is fine.

Before any of these:

- `uvicorn ... --workers N` (N > 1)
- multi-pod / horizontal scale
- moving to a multi-process WSGI/ASGI server

…switch the limiter to a shared store:

```python
# backend/app/rate_limit.py
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri="redis://<host>:6379",
)
```

Otherwise the effective cap is `N × 5/min` and the cap fails open.

### Gate 3 — Side-channel awareness (informational, no fix)

The 5/min cap is enforced **before** the projectId / IDOR scoping check
runs (slowapi's wrapper executes ahead of the route body). A probing
attacker can therefore distinguish "the route is real" (429 after burning
5 calls) from "the route doesn't exist" (404), but **cannot** distinguish
valid from invalid `(projectId, issueId)` pairs once they've burned the
cap — the limit fires identically for both. Net IDOR exposure is
unchanged from CB-2117.

If a future audit demands the cap be invisible to unauthenticated probes,
the fix is to move the projectId scoping check ahead of the limiter
(e.g., a FastAPI dependency that runs before slowapi's wrapper). That is
not in scope for CB-2662.

---

## 3. INTERNAL_API_TOKEN deploy gate (CB-2666, CB-2667, CB-2732)

The project-identifier endpoints disclose CUIDs and per-project
state that, in aggregate, defeat the CB-2217 collection-name
redaction on `/api/system/rag/status`. The current set:

| Endpoint | Disclosure / amplification | Cap | Ticket |
|---|---|---|---|
| `GET /api/projects` | full project list (id + name) | 30/min | CB-2666 H-1 |
| `GET /api/projects/{id}` | per-project CUID + name | 30/min | CB-2666 |
| `POST /api/projects/{id}/initialize-sequence` | mutates sequence on arbitrary CUIDs | 30/min | CB-2666 (defense-in-depth) |
| `GET /api/search/{project_id}/stats` | per-project indexed-doc count | 30/min | CB-2667 H-2 |
| `GET /api/search/{project_id}` | per-project semantic-search results (issue content) | 30/min | CB-2732 H-1 |
| `GET /api/search/{project_id}/similar` | per-project similar-issue results (issue content) | 30/min | CB-2732 H-1 |
| `POST /api/search/{project_id}/embed/{issue_id}` | IDOR write + DoS amplification | **10/min** | CB-2732 H-1 |
| `DELETE /api/search/{project_id}/embed/{issue_id}` | destructive IDOR on arbitrary `(project_id, issue_id)` | **10/min** | CB-2732 H-1 |
| `POST /api/search/{project_id}/embed-all` | server-side fan-out (walks every Issue with `projectId == X`); confirms guessed CUIDs by non-zero `embedded` count | **10/min** | CB-2732 H-1 |

The three write endpoints carry a stricter 10/min cap (vs. the
30/min cap on the read perimeter) because they are DoS-amplifying,
not just disclosure: `embed-all` in particular pins a worker
synchronously for the duration of an N-row embed loop. The 10/min
cap bounds worst-case worker pin to ~6s/min on a project with N=O(100)
issues even on a successful gate bypass.

Before CB-2666 the projects endpoints ALSO disclosed `path` (the
abspath of every project directory) and were reachable by any
Origin-less local caller. Before CB-2667 the search-stats endpoint
returned `{project_id, indexed_count}` for any caller-supplied
project_id, so chaining `/api/projects` → per-project `/stats`
re-bound the anonymous `count` distribution from CB-2217 to specific
project_ids in one extra request hop.

The fix is two-layer:

1. **Field minimization.** `ProjectResponse` no longer serializes
   `path` (`backend/models/schemas.py`). `extra="forbid"` on the schema
   pins the contract so a future regression that re-adds a path-shaped
   field fails fast at serialization, not just at the redaction-test
   level.
2. **Internal-token gate.** `app.security.require_local_or_token`
   requires `X-Internal-Token: <value>` matching `INTERNAL_API_TOKEN`
   on every gated endpoint. There is **no** Origin-bypass branch —
   trusting the `Origin` header on a server-side gate is meaningless
   because `curl -H 'Origin: http://localhost:3601'` would defeat it
   (CB-2666 sec audit F1).

### Required setting

| Variable | Default | Required when |
|---|---|---|
| `INTERNAL_API_TOKEN` | `""` (empty) | `ALLOW_LAN=true` OR `HOST` not in `{127.0.0.1, localhost, ::1}` |

### Startup assertion

`backend/app/main.py` raises `RuntimeError` at module load if any of
the non-loopback signals is set without the token. This is the
deploy-gate equivalent of the wildcard-CORS assertion at the top of
the same file — silent misconfiguration is the failure mode CB-2666
caught and the assertion makes it loud.

### Generating + setting the token

```bash
# Generate a 256-bit token
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'

# Append to .env (or your secrets manager / k8s secret / equivalent)
echo "INTERNAL_API_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env

# Restart the backend so the new value is read by `pydantic-settings`
./stop.sh && ./launch.sh
```

The frontend Next.js proxy already runs server-side (no `Origin`
header reaches backend on its outbound fetch). When the backend is
exposed beyond loopback, the proxy MUST forward the token via a
fixed `X-Internal-Token` header in `frontend/lib/api/api-fetch.ts` (or
the per-route handlers) — backed by a secret referenced from
`process.env.INTERNAL_API_TOKEN` on the Next.js side. Until a non-
loopback deploy lands, the frontend is unaffected because it does
NOT call backend `/api/projects` directly (the Next.js
`/api/projects/route.ts` proxy talks to Prisma).

### Why the token is empty by default

Loopback bind (`HOST=127.0.0.1`) + the existing `validate_origin`
middleware is the perimeter for dev workflow. Forcing every developer
to set a per-machine secret breaks `git clone && launch.sh`. The
startup assertion only fires when the operator has already opted into
non-loopback exposure — at which point a token is non-negotiable.

### Per-route rate limit (CB-2666 sec audit F6, CB-2667, CB-2732)

Every gated endpoint in §3 carries its own `@limiter.limit("…")`
decorator on top of the global 200/min default. The cap split mirrors
the threat type:

- **30/min — read perimeter** (per IP, per route). Applies to
  `list_projects`, `get_project`, `get_index_stats`, `search_issues`,
  and `find_similar_issues`. Bounds enumeration speed even on bypass
  paths (e.g., a misconfigured proxy stripping `X-Internal-Token`).
  On `/search/{id}/stats` and the two read-search siblings the 30/min
  cap means a single client cannot fan out across more than 30
  project_ids per minute even if `/api/projects` is reachable, which
  lifts the worst-case enumeration from O(N) per minute back to a slow
  walk of the project list.
- **10/min — write perimeter** (per IP, per route). Applies to
  `embed_issue`, `delete_embedding`, and `embed_all_issues`. These
  routes are DoS-amplifying, not just disclosure: `embed-all` walks
  every Issue row matching `projectId == X` and embeds each one
  synchronously, so one call can pin a worker for seconds on a large
  project. The stricter 10/min cap bounds worst-case worker pin to
  ~6 fan-out windows per minute even on a token-holding misuse path.
- **`POST /projects/{id}/initialize-sequence`** carries the same 30/min
  read cap as the project-identifier perimeter (defense-in-depth on a
  rare-mutation path).

> **Proxy-collapse caveat (cross-link to §2a Gate 1).** All the per-route
> caps above use slowapi's default `get_remote_address`, which reads
> `request.client.host`. On a deploy with a reverse proxy / CDN /
> load-balancer in front of uvicorn, every real client collapses into
> the proxy's single IP unless uvicorn is started with
> `--proxy-headers --forwarded-allow-ips=<known-proxy-cidr>`. Without
> that, the 30/min and 10/min per-IP caps become 30/min and 10/min
> GLOBAL caps — a single attacker can pin every legitimate caller out
> of `embed-all` for 60s windows (and the read perimeter for the same
> reason). §2a Gate 1 covers this for the documentation 5/min cap; the
> same gate applies before any non-loopback deploy of the §3 routes.
> Do **not** swap to `get_ipaddr` to "fix" this — it trusts the header
> unconditionally and lets the attacker spoof their bucket key. Fix at
> the uvicorn / proxy layer, not in slowapi.

### Frontend impact (CB-2667, CB-2732)

The browser-driven flows that hit a `/api/search/*` route directly
without going through a Next.js proxy:

| Origin | Endpoint | Hook / component |
|---|---|---|
| `frontend/components/codeboard/SemanticSearchPanel.tsx` | `GET /api/search/{projectId}/stats` | inline `fetch` (CB-2667 surface) |
| `frontend/components/codeboard/SemanticSearchPanel.tsx` | `POST /api/search/{projectId}/embed-all` | inline `fetch` (re-index button) |
| `frontend/hooks/useCodeBoard.ts` | `GET /api/search/{projectId}` | `useSearchIssues` (CB-2732 surface) |
| `frontend/hooks/useCodeBoard.ts` | `GET /api/search/{projectId}/similar` | `useFindSimilarIssues` (CB-2732 surface) |

On a loopback-bind dev workflow with `INTERNAL_API_TOKEN` empty, the
gate is pass-through and all four flows keep working unchanged.

When the backend is exposed beyond loopback and a token is set, every
direct-from-browser fetch in the table above will 401. The fix is
identical to the `/api/projects` story: route the call through a
Next.js proxy handler under `frontend/app/api/**/route.ts` that
forwards a fixed `X-Internal-Token` header from
`process.env.INTERNAL_API_TOKEN` server-side. Until that deploy lands,
the SemanticSearchPanel and the two search hooks are broken on
non-loopback deploys — which is the correct failure mode (token-set
deploy without proxy forwarding is the exact misconfiguration the
gate is catching). Do NOT rename the env var to
`NEXT_PUBLIC_INTERNAL_API_TOKEN` to "fix" this — see the discipline
note below for why that publishes the secret to every shipped JS file.

#### Token-naming discipline on the Next.js side (CB-2667 M-2)

When the proxy handler is wired up, the token reference MUST be:

1. Server-side only — read from inside `app/api/**/route.ts`,
   `middleware.ts`, or `getServerSideProps`-equivalent. NEVER from
   a `'use client'` component or anywhere that compiles into the
   client bundle.
2. Variable name MUST stay `INTERNAL_API_TOKEN`, not
   `NEXT_PUBLIC_INTERNAL_API_TOKEN`. The `NEXT_PUBLIC_` prefix is
   the trigger that inlines the value into the client bundle —
   using it on this token would publish the secret in every
   shipped JS file.
3. `.env.local` (gitignored) for local dev, secrets manager / k8s
   secret in deploy. NEVER `.env.example` or any committed file.

Adding an ESLint rule that restricts `process.env.INTERNAL_API_TOKEN`
references to `app/api/**` paths is the durable backstop here, but
not a deploy-gate dependency until the proxy handler is created.

### Token-existence side-channel (informational, no fix; CB-2667 M-1)

FastAPI dependencies fire BEFORE the slowapi `@limiter.limit`
wrapper, so `InternalAuthDep` rejects with 401 before the bucket is
decremented. This is the correct posture (an unauthenticated probe
cannot drain a legitimate caller's 30/min budget), but it means the
shape of the response across N requests reveals the deploy state:

- All 401s, no 429 even after >30/min sustained → token is
  configured AND the caller has no valid token.
- 30 200s followed by 429 → token is empty (pass-through path),
  rate-limiter is the only gate.
- Mixed 200/401 with no 429 → caller has a valid token (passes the
  gate, then hits 30/min cap as 429 from inside the route body).

This is a deploy-state oracle, not a content-disclosure bug — it
reveals whether `INTERNAL_API_TOKEN` is set, but never the value.
Sibling to the CB-2662 §2a Gate 3 side-channel; do not relax the
ordering to "fix" this — collapsing the gate after the limiter
would let unauthenticated probes drain the legit-caller budget,
which is strictly worse.

### Test coverage

`backend/tests/test_security.py::TestProjectsEndpointPerimeter`:
- Field redaction — `path` absent from LIST + GET-by-id
- Token unset → endpoint passes through (preserves dev workflow)
- Token set + missing header → 401
- Token set + valid header → 200
- Token set + wrong header → 401
- Token set + spoofed Origin (no header) → 401 (F1 regression guard)
- POST `/initialize-sequence` is also gated
- Constant-time + fixed-length compare guard (F4)
- `extra="forbid"` schema pin
- Startup assertion fires when `ALLOW_LAN=true` + token unset (F2)

`backend/tests/conftest.py` sets a per-process `INTERNAL_API_TOKEN`
before importing `app.main` so the assertion never blocks pytest
collection on a developer machine that has flipped `ALLOW_LAN=true`
in `.env`.

`backend/tests/test_security.py::TestSearchStatsEndpointPerimeter`
(CB-2667):
- Token unset → endpoint passes through (preserves dev workflow)
- Token set + missing header → 401 (primary attack path)
- Token set + valid header → gate passes (route body may 500
  because rag isn't lifespan-initialized under ASGITransport, but
  that is downstream of the gate)
- Token set + wrong header → 401
- Token set + spoofed Origin (no header) → 401 (F1 invariant)
- Header-name case-insensitivity (parametrized: lower / Title /
  UPPER) — pins the Starlette/RFC 7230 normalization invariant
- Whitespace-padded token value rejected (constant-time digest
  is byte-exact, no silent normalization)
- `Authorization: Bearer <token>` NOT accepted as a fallback
  (gate is single-header; no implicit alternates)
- Source-text pin (AST walk): `@router.get(... dependencies=[
  InternalAuthDep])` is structurally present on `get_index_stats`
  — substring matching would pass even on accidental relocation
  of the marker into a comment

`backend/tests/test_security.py::TestSearchSiblingEndpointsPerimeter`
(CB-2732) — parametrized across the five sibling endpoints under
`/api/search/*` (`GET /{pid}`, `GET /{pid}/similar`, `POST /{pid}/embed/{iid}`,
`DELETE /{pid}/embed/{iid}`, `POST /{pid}/embed-all`):
- Token unset → endpoint passes through (preserves dev workflow —
  SemanticSearchPanel + `useSearchIssues` / `useFindSimilarIssues`
  hooks rely on this on a loopback-bind dev box)
- Token set + missing header → 401 (primary attack path: chained
  `/api/projects` → per-project search/embed fan-out)
- Token set + valid header → gate passes (route body returns or
  500s downstream — irrelevant to the gate; rag/db are stubbed)
- Token set + wrong header → 401
- Token set + spoofed Origin (no header) → 401 (CB-2666 F1 invariant
  — server-side gates that trust `Origin` are meaningless because
  any local process can forge it)
- Source-text pin (AST walk) per handler: `dependencies=[
  InternalAuthDep]` AND `@limiter.limit("<expected>")` are both
  structurally present, where `<expected>` is `30/minute` for the
  two GET handlers and `10/minute` for the three write handlers.
  A future regression that drops either decoration on a single
  endpoint, or that drifts the cap, fails fast at the unit-test
  level rather than at deploy.

---

## 4. Long-term plan — convert to job-and-poll

Tracked in CB-2375 (option 3, deferred). Replaces the synchronous
endpoint with:

```
POST /api/features/{id}/documentation/generate     → 202 + {"jobId": "…"}
GET  /api/features/{id}/documentation/jobs/{jobId} → 200 + {"status": "pending|ready|failed"}
```

Benefits:

- Request handlers release immediately — no 120s pin
- A worker pool caps actual provider concurrency, not request count
- Frontend polls + can show real progress
- Cancellation becomes possible (DELETE on the job)

Until that ships, the per-route 5/min rate limit is the load-bearing
defence. Do not relax it without first putting the worker pool in
place.

---

## 5. Common emergencies

| Symptom | Likely cause | Action |
|---|---|---|
| 429s on regenerate during normal use | One IP hammering the endpoint | Inspect access logs; confirm not a legitimate burst |
| 504 from the frontend proxy | LLM ran longer than the 120s timeout | See CB-2375 — adjust per-route timeout allowlist |
| Stale doc after generate | `useGenerateFeatureDoc` did not invalidate | See CB-2376 |
| Cross-project content in a doc | Descendant filter regressed | See CB-1615 sec audit, regression test in `test_generate_feature_documentation_skips_cross_project_descendants` |

---

## 6. References

- CB-1578 — original auto-doc pipeline
- CB-1588 — read-only API surface
- CB-1590 — FeatureDocumentation endpoints
- CB-1615 — AI augmentation + ChromaDB indexing
- CB-2038 — Documentation Surface umbrella feature
- CB-2117 — projectId IDOR guard
- CB-2217 — `/api/system/rag/status` collection-name redaction
- CB-2375 — proxy + client-side timeout pairing
- CB-2376 — cache invalidation on error
- **CB-2662 — per-route rate limit (this runbook §2 / §2a)**
- **CB-2666 — INTERNAL_API_TOKEN deploy gate (this runbook §3)**
- **CB-2667 — `/api/search/{id}/stats` joins the §3 gate (extends CB-2666)**
- **CB-2732 — sibling `/api/search/*` endpoints join the §3 gate; write endpoints get stricter 10/min cap (extends CB-2667)**
- **CB-2668 — `/docs` + `/redoc` + `/openapi.json` route-map gate (this runbook §3a)**

---

## 3a. Doc-surface gate (CB-2668)

FastAPI's `/docs` (Swagger), `/redoc`, and `/openapi.json` publish the
full route map by default — every path, every project_id-shaped param,
every request/response schema. Chained with CB-2666 H-1 and CB-2667 H-2,
the route map turns each isolated identifier disclosure into a guided
enumeration kit.

### Gate

`backend/app/main.py` constructs the FastAPI app with `docs_url=None`,
`redoc_url=None`, `openapi_url=None` unless `settings.is_development` is
true. The helper accepts only the canonical aliases `development` / `dev`
(case-insensitive). Production / staging / unset / typo'd ENVIRONMENT all
stay locked — fail-closed, matching the CB-2666 perimeter posture.

| ENVIRONMENT value | `/docs` | `/redoc` | `/openapi.json` |
|---|---|---|---|
| `production` (default) | 404 | 404 | 404 |
| `staging` | 404 | 404 | 404 |
| `test`, `""`, `dev-staging`, ` dev ` | 404 | 404 | 404 |
| `development` / `dev` / `DEV` / `Development` | 200 | 200 | 200 |

### Why no token-gated middle ground

A token-gated route map (the alternative the CB-2668 ticket lists) would
let an operator preserve the docs surface on non-loopback deploys behind
the same `INTERNAL_API_TOKEN` that §3 requires. Two reasons we did not:

1. The route map has no operational use that survives a deploy. Local
   dev keeps the surface; non-dev deploys don't need it.
2. Adding a third Swagger/ReDoc/OpenAPI dependency would also re-key the
   `INTERNAL_API_TOKEN` against a Swagger-loaded browser. Setting it up
   for human-driven discovery defeats the gate's purpose.

If a non-dev consumer needs the OpenAPI schema (codegen, contract test),
generate it offline from a `ENVIRONMENT=development` checkout and ship
the JSON as an artifact — never re-publish it from production.

### Test coverage

`backend/tests/test_security.py::TestDocsSurfacePerimeter`:
- `is_development` matrix (alias accepts vs typo locks)
- Production-mode 404 on all three routes
- Swagger asset path (`/docs/oauth2-redirect`) also dropped
- Reloading `app.main` under `ENVIRONMENT=development` brings back the
  three 200s — guards against a regression that hard-codes `None`
