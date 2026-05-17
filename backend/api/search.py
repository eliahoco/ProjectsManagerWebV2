"""
Search API - Semantic search using RAG

CB-2667: `GET /search/{project_id}/stats` discloses a per-project
indexed-document count for any caller-supplied `project_id`. Combined
with the CB-2666 fix on `/api/projects` (full project enumeration),
this endpoint re-binds the anonymous `count` distribution that
CB-2217 made non-attributable on `/api/system/rag/status` back to a
specific `project_id` in one extra request hop. Same threat model as
CB-2666 — Origin-less callers (curl, server-to-server, malicious
local processes) bypass the `validate_origin` middleware in
`app.main` by design, and on a non-loopback bind (`ALLOW_LAN=true`)
the stats endpoint becomes a one-call enumeration of doc-count by
project.

Fix: gate the stats endpoint behind `InternalAuthDep` (the same
shared-secret gate `/api/projects` wears) and apply the 30/min per-IP
rate limit so even a bypass path (e.g., a misconfigured proxy
stripping `X-Internal-Token`) cannot enumerate the project list at
the global 200/min cap. See `app.security.require_local_or_token`
and `backend/docs/DOC_PIPELINE_RUNBOOK.md` §3.

CB-2732: the five sibling endpoints (`GET /{project_id}`,
`GET /{project_id}/similar`, `POST /{project_id}/embed/{issue_id}`,
`DELETE /{project_id}/embed/{issue_id}`, `POST /{project_id}/embed-all`)
share the SAME perimeter shape that CB-2667 closed on `/stats`:

  - The two GET routes disclose per-project semantic-search results
    (issue title/description content) for any caller-supplied
    `project_id`, which is a strictly stronger disclosure than the
    `/stats` doc-count CB-2667 closed.
  - The two `embed` mutation routes accept a caller-supplied
    `(project_id, issue_id)` pair and write into the matching
    ChromaDB collection. Without a gate this is an IDOR write +
    DoS amplifier.
  - `POST /embed-all` walks every `Issue` row with `projectId == X`
    and embeds each one synchronously inside a single request, so
    one call can pin a worker for seconds on a large project AND
    confirm a guessed CUID by a non-zero `embedded` count.

Fix: same `InternalAuthDep` + rate limit pattern. Read endpoints
keep the 30/min cap that the project-identifier perimeter uses;
the three write endpoints get a stricter 10/min cap because they
are DoS-amplifying, not just disclosure. See
`backend/docs/DOC_PIPELINE_RUNBOOK.md` §3 for the gated-endpoint
table including the stricter write cap.
"""

import logging

from fastapi import APIRouter, Query, Depends, Request
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.rate_limit import limiter
from app.security import InternalAuthDep
from services.rag_service import RAGService
from models import get_db, Issue
from api.deps import get_rag

logger = logging.getLogger(__name__)

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


@router.get(
    "/{project_id}",
    response_model=SearchResponse,
    dependencies=[InternalAuthDep],
)
@limiter.limit("30/minute")
async def search_issues(
    request: Request,
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

    CB-2732: gated by `InternalAuthDep`; rate-limited at 30/minute
    per client IP. This endpoint discloses semantic-search results
    (issue content) for any caller-supplied `project_id` — strictly
    stronger than the `/stats` doc-count CB-2667 closed.
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


@router.get(
    "/{project_id}/similar",
    dependencies=[InternalAuthDep],
)
@limiter.limit("30/minute")
async def find_similar_issues(
    request: Request,
    project_id: str,
    title: str = Query(..., description="Issue title"),
    description: Optional[str] = Query(None, description="Issue description"),
    n_results: int = Query(5, ge=1, le=20),
    rag: RAGService = Depends(get_rag),
):
    """
    Find issues similar to the given title/description.
    Useful for duplicate detection.

    CB-2732: gated by `InternalAuthDep`; rate-limited at 30/minute
    per client IP. Same disclosure shape as `/{project_id}` — issue
    content for any caller-supplied `project_id`.
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


@router.post(
    "/{project_id}/embed/{issue_id}",
    dependencies=[InternalAuthDep],
)
@limiter.limit("10/minute")
async def embed_issue(
    request: Request,
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

    CB-2732: gated by `InternalAuthDep`; rate-limited at 10/minute
    per client IP — the stricter write cap. This endpoint mutates
    the ChromaDB collection for a caller-supplied `(project_id,
    issue_id)` pair and is therefore DoS-amplifying + IDOR-write
    if exposed without a gate.
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


@router.delete(
    "/{project_id}/embed/{issue_id}",
    dependencies=[InternalAuthDep],
)
@limiter.limit("10/minute")
async def delete_embedding(
    request: Request,
    project_id: str,
    issue_id: str,
    rag: RAGService = Depends(get_rag),
):
    """Delete an issue embedding from the vector store.

    CB-2732: gated by `InternalAuthDep`; rate-limited at 10/minute
    per client IP — the stricter write cap. Destructive IDOR if
    exposed without a gate.
    """
    success = await rag.delete_issue_embedding(project_id, issue_id)
    return {"success": success, "issue_id": issue_id}


class BatchEmbedResponse(BaseModel):
    """Batch embed response schema"""
    success: bool
    total: int
    embedded: int
    failed: int
    errors: List[str] = []


@router.post(
    "/{project_id}/embed-all",
    response_model=BatchEmbedResponse,
    dependencies=[InternalAuthDep],
)
@limiter.limit("10/minute")
async def embed_all_issues(
    request: Request,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    rag: RAGService = Depends(get_rag),
):
    """
    Embed all issues for a project into the vector database.
    This indexes all issues for semantic search capabilities.

    CB-2732: gated by `InternalAuthDep`; rate-limited at 10/minute
    per client IP — the stricter write cap. This handler walks
    every `Issue` row matching `projectId == project_id` and
    embeds each one synchronously, so a single call can pin a
    worker for seconds on a large project AND confirm a guessed
    CUID by a non-zero `embedded` count.
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
                errors.append(f"{issue.key}: embed_failed")
        except Exception:
            # CB-2784: redact `str(e)` to a generic token. Raw exception
            # text can carry SQL fragments, ChromaDB internal paths, or
            # HTTP-level chromadb errors; the response body must not echo
            # any of that to the caller, even on a future bypass path
            # (CB-2732 audit M-3 proxy-collapse / multi-worker scenario).
            # Detail goes to the server log via logger.exception only.
            failed += 1
            errors.append(f"{issue.key}: embed_failed")
            logger.exception(
                "embed_failed",
                extra={"issue_key": issue.key, "project_id": project_id},
            )

    return BatchEmbedResponse(
        success=failed == 0,
        total=total,
        embedded=embedded,
        failed=failed,
        errors=errors[:10],  # Limit error messages
    )


@router.get(
    "/{project_id}/stats",
    dependencies=[InternalAuthDep],
)
@limiter.limit("30/minute")
async def get_index_stats(
    request: Request,
    project_id: str,
    rag: RAGService = Depends(get_rag),
):
    """Get statistics about the vector index for a project.

    CB-2667: gated by `InternalAuthDep`; rate-limited at 30/minute per
    client IP to bound enumeration speed on bypass paths even when the
    global 200/minute would otherwise allow a fan-out across every
    project_id returned by `/api/projects`.
    """
    try:
        collection = rag.get_collection(project_id)
        count = collection.count()
        return {
            "project_id": project_id,
            "indexed_count": count,
            "status": "ready" if count > 0 else "empty",
        }
    except Exception:
        # CB-2787: redact response `error` to a generic token; route
        # detail to logger.exception only. Mirrors CB-2784 redaction
        # on `embed_all_issues` — token-holding callers are in scope
        # by design, but on a CB-2732 bypass path one successful
        # /stats call must not leak the upstream error class.
        logger.exception("stats_failed", extra={"project_id": project_id})
        return {
            "project_id": project_id,
            "indexed_count": 0,
            "status": "error",
            "error": "stats_failed",
        }
