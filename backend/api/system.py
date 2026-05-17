"""
System API — internal observability endpoints.

CB-2045 (T1.2.1): exposes the active RAG backend (mode, host/port,
collections + counts, total docs, healthy flag) so the Service Monitor
card (CB-2046) and on-call humans can see at a glance whether ChromaDB
is HTTP-mode against the dedicated container or has silently fallen
back to the embedded PersistentClient.

Read-only. No application-level auth: the perimeter is the bind
interface — `launch.sh` ties uvicorn to `127.0.0.1` by default and
only widens to `0.0.0.0` when `ALLOW_LAN=true` is explicitly set
(launch.sh:128-129). The `validate_origin` middleware in
`app/main.py` blocks browser fetches from origins outside
`ALLOWED_ORIGINS` but lets Origin-less requests (curl, scripts on
the same host) pass through; loopback bind is what keeps this
endpoint off the network.

CB-2217: per-collection `name` (the `project_<cuid_prefix>` string)
no longer crosses the HTTP boundary — see `RagCollectionStatus`. The
status surface still reports collection cardinality + per-collection
doc counts so the Service Monitor card can render "top collections"
without disclosing which projects exist or how their content is
distributed across CUID prefixes.
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from api.deps import RAGDep
from services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter()


class RagCollectionStatus(BaseModel):
    """Per-collection status row.

    CB-2217: `name` was previously the literal collection name
    (`project_<cuid_prefix>`), which let any local Origin-less caller
    enumerate which projects exist via the status endpoint. The field
    is removed; only `count` crosses the HTTP boundary. Internal
    callers (`get_collection`, `describe_mode`) keep using the real
    name on the service side — the redaction is payload-only.

    Rank-as-identity: rows have NO stable handle. Position in the array
    reflects sort rank for the current poll; consumers MUST NOT treat
    `collections[i]` as a persistent project pointer across polls.

    `extra="forbid"` (CB-2217 follow-up from code review) is the
    structural pin that catches a future regression where someone adds
    a name-shaped field (id/slug/label/hashed-name) without redaction
    review — Pydantic v2's default `extra="ignore"` would silently let
    such a field through `get_status_payload()` even though the model
    doesn't declare it. Forbid means the test harness fails fast at
    contract level, not just at the regex-on-serialized-JSON level.
    """

    model_config = ConfigDict(extra="forbid")

    count: Optional[int] = None


class RagStatusResponse(BaseModel):
    mode: str = Field(
        description="Active RAG backend mode: HTTP | PERSISTENT | UNINITIALIZED."
    )
    endpoint: str = Field(
        description=(
            "Backend endpoint identifier. For mode=HTTP this is the ChromaDB "
            "host (e.g., 'chromadb'). Empty string for mode=PERSISTENT and "
            "mode=UNINITIALIZED — see `fallback_active` for the PERSISTENT "
            "signal. CB-2215 (F-5): renamed from `host` to reflect dual "
            "semantics. CB-2665: flag-day rename — no back-compat alias; "
            "migration note in `docs/runbooks/2026-05-09-rag-status-host-"
            "endpoint-rename.md` explains the perimeter rationale and the "
            "`undefined` failure mode for any stale `host`-keyed consumer. "
            "CB-2216: PERSISTENT no longer echoes the abspath to avoid "
            "leaking the user-named volume layout to any local process "
            "able to curl this endpoint (Origin-less requests bypass the "
            "validate_origin middleware by design)."
        )
    )
    port: int = Field(
        description=(
            "TCP port for mode=HTTP; 0 for mode=PERSISTENT and "
            "mode=UNINITIALIZED."
        )
    )
    fallback_active: bool = Field(
        default=False,
        description=(
            "True iff mode=PERSISTENT — the embedded ChromaDB client is in "
            "use, signalling silent fallback from HTTP. Replaces the prior "
            "abspath-in-endpoint disclosure (CB-2216) so the Service Monitor "
            "card can still distinguish 'HTTP up' from 'fell back to "
            "embedded' without leaking the filesystem path."
        ),
    )
    collections: List[RagCollectionStatus]
    total_docs: int
    healthy: bool


@router.get("/system/rag/status", response_model=RagStatusResponse)
async def get_rag_status(rag: RAGService = RAGDep) -> RagStatusResponse:
    """Return the current RAG backend status snapshot.

    Never raises — `RAGService.get_status_payload()` traps every error
    from the underlying client and reflects it via `healthy=False`.

    CB-2729: the call dispatches via `asyncio.to_thread()` so the
    synchronous ChromaDB probe (`heartbeat` + `list_collections` +
    per-collection `count()`) runs on the default threadpool instead
    of pinning the event-loop worker. Without this, a stuck ChromaDB
    dependency (CLOSE_WAIT, slow-loris, half-closed TCP) would block
    every other async handler scheduled on the same worker for the
    duration of the (timeout-bounded) probe — every other status
    request, every queue/AI-execution poll, every generic API call.
    The httpx-side timeout (CB-2729 part 1, configured at HttpClient
    construction in `RAGService._init_client_blocking()`) caps the
    blocking time at ~2 s per probe; running off the loop ensures
    even that 2 s only blocks one threadpool worker, not the loop
    that schedules every other handler.

    The TTL cache + lock-with-timeout (CB-2218 + CB-2729 part 3) keep
    the steady-state cost negligible — most calls are cache hits and
    return without touching the threadpool path's blocking work.
    """
    payload = await asyncio.to_thread(rag.get_status_payload)
    return RagStatusResponse(**payload)
