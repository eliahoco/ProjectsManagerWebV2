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
"""

import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import RAGDep
from services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter()


class RagCollectionStatus(BaseModel):
    name: str
    count: Optional[int] = None


class RagStatusResponse(BaseModel):
    mode: str
    host: str
    port: int
    collections: List[RagCollectionStatus]
    total_docs: int
    healthy: bool


@router.get("/system/rag/status", response_model=RagStatusResponse)
async def get_rag_status(rag: RAGService = RAGDep) -> RagStatusResponse:
    """Return the current RAG backend status snapshot.

    Never raises — `RAGService.get_status_payload()` traps every error
    from the underlying client and reflects it via `healthy=False`.
    """
    payload = rag.get_status_payload()
    return RagStatusResponse(**payload)
