# `/api/system/rag/status` — `host` -> `endpoint` rename — CB-2665

**Date:** 2026-05-09
**Tickets:** CB-2215 (F-5, original rename) · CB-2665 (this changelog)
**Severity:** LOW (internal-only API)
**Decision:** Option B — flag-day rename, no back-compat alias.

## Summary

The Pydantic field on `GET /api/system/rag/status` was renamed:

| Before (≤ CB-2215 F-5) | After (current)        |
|------------------------|------------------------|
| `host: str`            | `endpoint: str`        |

The rename was applied in the same commit that updated the only known
consumer (`frontend/components/service-monitor.tsx` —
`RagStatusCard` + `normalizeRagStatus`). No deprecation alias was added
on the response model, and no migration note shipped at the time —
this runbook closes that gap.

## Why the rename

The field carries dual semantics:

- **mode=HTTP** — ChromaDB hostname (e.g., `chromadb`).
- **mode=PERSISTENT** — empty string (CB-2216 redacted the abspath
  from the payload to avoid leaking the on-disk volume layout to any
  local Origin-less caller). The `fallback_active` flag is the
  PERSISTENT signal.
- **mode=UNINITIALIZED** — empty string.

Calling the field `host` was inaccurate once the value stopped being a
hostname in two of three modes. `endpoint` is the neutral term.

## Why no back-compat alias (option B)

The endpoint perimeter is narrow enough that a flag-day rename is
acceptable:

- **Bind interface** — `launch.sh:128-129` ties uvicorn to `127.0.0.1`
  by default; `0.0.0.0` only when `ALLOW_LAN=true` is explicitly set.
- **Origin gate** — `validate_origin` middleware (`app/main.py`)
  blocks browser fetches from origins outside `ALLOWED_ORIGINS`.
  Origin-less requests (curl, scripts on the same host) pass.
- **Consumers** — exactly one in-tree consumer
  (`service-monitor.tsx`), updated in the same commit as the rename.
  No public/external consumers documented.

The conservative alternative (option A — `host: str = Field(alias=...)`
emitting both fields for one release, then drop) was rejected because:

1. The deprecation window has no external consumer to protect.
2. `extra="forbid"` on related response models (CB-2217) means we
   prefer payload precision over compatibility shims.
3. A second name on the wire would be one more shape for the
   redaction reviewer to police on every future change.

## Failure modes if a stale consumer is encountered

A pre-rename client keying on `"host"` (e.g., a stale browser tab
loaded from an old bundle, or a third-party script written against
the old OpenAPI snapshot) sees `endpoint` as `undefined`.

In the canonical client (`normalizeRagStatus` in `service-monitor.tsx`,
line 189), the coercer defaults missing `endpoint` to `''`. The
Service Monitor card renders the endpoint cell as blank in HTTP mode
(or as `embedded` when `fallback_active=true`). No exception is
thrown; the card stays functional but the endpoint field is empty.

Failure mode: cosmetic "endpoint shows blank". Fix: refresh the
browser to pull the current bundle.

## OpenAPI consumers

`/openapi.json` is published with the rename. There is no
auto-generated client SDK in this repo. If a future external client
is added, this runbook is the migration reference.

## Test coverage

- `frontend/components/service-monitor.tsx` consumes only `endpoint`
  (verified via `grep "host\|endpoint" service-monitor.tsx`).
- Backend `RagStatusResponse` field name is asserted indirectly by
  every test that constructs the model with `endpoint=...`. If a
  future commit reintroduces `host` on `RagStatusResponse`, those
  construction-time keyword-arg assertions fail.
- Note: `extra="forbid"` is set on the nested `RagCollectionStatus`
  (CB-2217 follow-up), not on `RagStatusResponse` itself. It catches
  aliased-extra regressions on the per-collection row, not on the
  outer response. A future change that reintroduces `host` to
  `RagStatusResponse` would need to be caught by tests on the outer
  shape, or by adding `extra="forbid"` to `RagStatusResponse` as a
  parallel structural pin.

## Related decisions

- CB-2215 — F-5 rename + frontend update (origin of the change).
- CB-2216 — abspath redaction in PERSISTENT mode (drove the dual
  semantics that motivated the rename).
- CB-2217 — `RagCollectionStatus.name` removal + `extra="forbid"`
  pattern (sets the precedent for payload-precision-over-compat).
- CB-2665 — this runbook (closes the missing-changelog gap).

## When to revisit

Add a back-compat alias only if:

- An external consumer ships against `/api/system/rag/status` AND
- The rename frequency on this endpoint is expected to grow.

Neither condition holds today.
