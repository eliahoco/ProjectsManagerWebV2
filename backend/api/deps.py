"""
FastAPI dependency providers for shared application state.
"""

from fastapi import Request, Depends
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
