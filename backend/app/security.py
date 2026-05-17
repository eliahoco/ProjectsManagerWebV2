"""Internal-API authentication dependency (CB-2666).

Some read endpoints disclose project-level identifiers (CUIDs, names,
abspath) that should NOT cross the perimeter when the backend listens
on a non-loopback interface. The historical perimeter is two-layer:

  1. `launch.sh` binds uvicorn to 127.0.0.1 unless `ALLOW_LAN=true`.
  2. `validate_origin` middleware in `app.main` rejects browser-driven
     cross-origin requests.

Both layers leak when an Origin-less caller (curl, server-to-server,
malicious local process) hits an endpoint that disclosed identifiers
— see CB-2217 (collection name redaction) and CB-2216 (PERSISTENT-mode
abspath redaction) for the same threat shape on `/api/system/rag/status`.

This module adds defense-in-depth via a shared secret. When
`settings.INTERNAL_API_TOKEN` is set, callers MUST present
`X-Internal-Token: <token>` matching the configured value. Otherwise
the dependency raises HTTP 401.

Origin-only bypass deliberately omitted (CB-2666 sec audit F1):
trusting the `Origin` header on a server-side gate is meaningless
because any local process can `curl -H 'Origin: http://localhost:3601'`
and pass. The legitimate consumers of these endpoints (the Next.js
proxy and ad-hoc backend scripts) are already server-side and can
forward the token via the request header.

Token comparison uses SHA-256 hashing on both sides before
`secrets.compare_digest` so neither the contents nor the LENGTH of the
configured token are exposed via response timing — `compare_digest`
itself is constant-time only on equal-length inputs.

Reusable for sibling tickets:
  - CB-2667 — `/api/search/{project_id}/stats` per-project doc count
  - CB-2668 — `/docs` + `/openapi.json` route map
"""

import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, status

from app.config import settings


def _digest(value: str) -> bytes:
    """Fixed-length digest of `value` so length differences in the
    presented header do NOT leak via `compare_digest`'s short-circuit
    on unequal-length inputs.
    """
    return hashlib.sha256(value.encode("utf-8")).digest()


def require_local_or_token(request: Request) -> None:
    """Reject requests that lack a valid `INTERNAL_API_TOKEN` header.

    No-op when `INTERNAL_API_TOKEN` is empty (preserves dev workflow on
    loopback bind — combined with the ALLOW_LAN startup assertion in
    `app.main`, this is safe by construction).

    Raises:
        HTTPException(401): Token configured but request presents no
            valid `X-Internal-Token` header.
    """
    expected = settings.INTERNAL_API_TOKEN
    if not expected:
        return

    presented = request.headers.get("x-internal-token", "")
    if presented and secrets.compare_digest(_digest(presented), _digest(expected)):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="missing_or_invalid_internal_token",
    )


InternalAuthDep = Depends(require_local_or_token)
