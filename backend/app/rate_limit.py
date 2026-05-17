"""Shared slowapi limiter singleton (CB-2662).

Lives outside `app.main` so individual API routers can pull the limiter for
per-route `@limiter.limit("…")` decorators without re-importing the FastAPI
app (which would create a circular import: `app.main` already imports the
api package, and api modules cannot then import `app.main`).

Only the limiter instance is exported; configuration of `app.state.limiter`
and the `RateLimitExceeded` exception handler stays in `app.main`.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Global default: 200/minute per-IP across all endpoints (CB historical).
# Per-route overrides (e.g. CB-2662 5/minute on the LLM doc-gen endpoint)
# attach via the @limiter.limit("…") decorator on individual handlers.
#
# CB-2662 deploy gates — read these BEFORE moving the backend off localhost:
#
#   1. Reverse-proxy / CDN / load-balancer in front of uvicorn:
#      `get_remote_address` reads `request.client.host` only; it does NOT
#      parse `X-Forwarded-For`. Without `--proxy-headers
#      --forwarded-allow-ips=<known-proxy-cidr>` on the uvicorn command,
#      every real client collapses into the proxy's single IP and the
#      5/min cap becomes a 5/min GLOBAL cap. A single attacker then
#      DoSes legitimate users for free. **Do NOT** swap to slowapi's
#      `get_ipaddr` — it trusts headers unconditionally and lets the
#      attacker spoof their bucket key. Fix at the uvicorn layer instead.
#
#   2. Multiple worker processes (`--workers N` or N-pod horizontal scale):
#      slowapi's default is in-memory, so each worker has its own bucket.
#      Effective cap becomes `N × 5/min`. Move to a shared store
#      (`Limiter(... storage_uri="redis://…")`) before scaling beyond
#      one process.
#
# See backend/docs/DOC_PIPELINE_RUNBOOK.md §2a for the full deploy checklist.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
