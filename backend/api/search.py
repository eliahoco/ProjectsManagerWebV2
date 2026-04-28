"""
Search API - Semantic search using RAG
"""

from fastapi import APIRouter, Query, Depends, Request
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.rag_service import RAGService
from models import get_db, Issue
from api.deps import get_rag

router = APIRouter(prefix="/search")


class SearchResult(BaseModel):
    """Search result schema"""
    issue_id: Optional[str] = None
    key: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    document: Optional[str] = None
    score: Optional[float] = None


class SearchResponse(BaseModel):
    """Search response schema"""
    results: List[SearchResult]
    query: str
    total: int


@router.get("/{project_id}", response_model=SearchResponse)
async def search_issues(
    project_id: str,
    q: str = Query(..., min_length=1, description="Search query"),
    n_results: int = Query(10, ge=1, le=50, description="Number of results"),
    type: Optional[str] = Query(None, description="Filter by issue type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    rag: RAGService = Depends(get_rag),
):
    """
    Semantic search for issues in a project.
    Uses ChromaDB vector embeddings for similarity search.
    """
    results = await rag.search_issues(
        project_id=project_id,
        query=q,
        n_results=n_results,
        filter_type=type,
        filter_status=status,
    )

    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        query=q,
        total=len(results),
    )


@router.get("/{project_id}/similar")
async def find_similar_issues(
    project_id: str,
    title: str = Query(..., description="Issue title"),
    description: Optional[str] = Query(None, description="Issue description"),
    n_results: int = Query(5, ge=1, le=20),
    rag: RAGService = Depends(get_rag),
):
    """
    Find issues similar to the given title/description.
    Useful for duplicate detection.
    """
    results = await rag.find_similar_issues(
        project_id=project_id,
        title=title,
        description=description,
        n_results=n_results,
    )

    return {
        "results": results,
        "query": {"title": title, "description": description},
        "total": len(results),
    }


@router.post("/{project_id}/embed/{issue_id}")
async def embed_issue(
    project_id: str,
    issue_id: str,
    key: str = Query(...),
    title: str = Query(...),
    description: Optional[str] = Query(None),
    issue_type: str = Query("TASK"),
    status: str = Query("BACKLOG"),
    labels: Optional[str] = Query(None),
    rag: RAGService = Depends(get_rag),
):
    """
    Manually embed or re-embed an issue.
    Usually called automatically when issues are created/updated.
    """
    success = await rag.embed_issue(
        project_id=project_id,
        issue_id=issue_id,
        key=key,
        title=title,
        description=description,
        issue_type=issue_type,
        status=status,
        labels=labels,
    )

    return {"success": success, "issue_id": issue_id}


@router.delete("/{project_id}/embed/{issue_id}")
async def delete_embedding(
    project_id: str,
    issue_id: str,
    rag: RAGService = Depends(get_rag),
):
    """Delete an issue embedding from the vector store."""
    success = await rag.delete_issue_embedding(project_id, issue_id)
    return {"success": success, "issue_id": issue_id}


class BatchEmbedResponse(BaseModel):
    """Batch embed response schema"""
    success: bool
    total: int
    embedded: int
    failed: int
    errors: List[str] = []


@router.post("/{project_id}/embed-all", response_model=BatchEmbedResponse)
async def embed_all_issues(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    rag: RAGService = Depends(get_rag),
):
    """
    Embed all issues for a project into the vector database.
    This indexes all issues for semantic search capabilities.
    """
    # Fetch all issues for the project
    result = await db.execute(
        select(Issue).where(Issue.projectId == project_id)
    )
    issues = result.scalars().all()

    total = len(issues)
    embedded = 0
    failed = 0
    errors = []

    for issue in issues:
        try:
            success = await rag.embed_issue(
                project_id=project_id,
                issue_id=issue.id,
                key=issue.key,
                title=issue.title,
                description=issue.description,
                issue_type=issue.type,
                status=issue.status,
                labels=issue.labels,
            )
            if success:
                embedded += 1
            else:
                failed += 1
                errors.append(f"Failed to embed {issue.key}")
        except Exception as e:
            failed += 1
            errors.append(f"Error embedding {issue.key}: {str(e)}")

    return BatchEmbedResponse(
        success=failed == 0,
        total=total,
        embedded=embedded,
        failed=failed,
        errors=errors[:10],  # Limit error messages
    )


@router.get("/{project_id}/stats")
async def get_index_stats(
    project_id: str,
    rag: RAGService = Depends(get_rag),
):
    """
    Get statistics about the vector index for a project.
    """
    try:
        collection = rag.get_collection(project_id)
        count = collection.count()
        return {
            "project_id": project_id,
            "indexed_count": count,
            "status": "ready" if count > 0 else "empty",
        }
    except Exception as e:
        return {
            "project_id": project_id,
            "indexed_count": 0,
            "status": "error",
            "error": str(e),
        }
