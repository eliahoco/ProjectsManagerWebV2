"""
FastAPI dependency providers for shared application state.
"""

from fastapi import Depends, Header, Request
from typing import Optional

from services.rag_service import RAGService


def get_rag(request: Request) -> RAGService:
    """Retrieve the RAGService instance from application state.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The RAGService instance stored on app.state.rag.

    Raises:
        RuntimeError: If the lifespan failed to initialize RAGService.
    """
    rag = getattr(request.app.state, "rag", None)
    if rag is None:
        raise RuntimeError("RAGService not initialized — lifespan failed")
    return rag


RAGDep = Depends(get_rag)


def get_tenant_id(
    x_tenant_id: Optional[str] = Header(default=None),
) -> str:
    """Return the tenant identifier for the current request.

    In Phase 1 (single-user / local mode) the ``X-Tenant-ID`` header is
    absent and the function falls back to ``settings.DEFAULT_TENANT_ID``
    (``"default"``).  In Phase 2 the trusted reverse-proxy will inject the
    header and this dep becomes the single point that enforces the contract
    — no call site needs to change.

    Args:
        x_tenant_id: Optional ``X-Tenant-ID`` request header injected by
            FastAPI via ``Header(default=None)``.

    Returns:
        The tenant ID string — never ``None``.
    """
    from app.config import settings

    return x_tenant_id or settings.DEFAULT_TENANT_ID


TenantDep = Depends(get_tenant_id)
