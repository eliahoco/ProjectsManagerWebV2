"""
RAG Service - Semantic Search using ChromaDB
"""

import chromadb
import os
import socket
from chromadb.config import Settings
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import hashlib
import json
import logging

from app.config import settings

if TYPE_CHECKING:
    from models.documentation import ExecutionSummary, FeatureDocumentation

logger = logging.getLogger(__name__)


def _safe_json_list(value: Optional[str]) -> List[str]:
    """Decode a JSON-array TEXT column to list[str]; never raise.

    Returns [] on missing/malformed input. Logs at debug so silent
    integrity issues are still observable when DEBUG is on.
    """
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        logger.debug("Failed to decode JSON list field: %r", value[:120])
        return []
    if isinstance(decoded, list):
        return [str(item) for item in decoded if item is not None]
    logger.debug("JSON list field decoded to non-list: %s", type(decoded).__name__)
    return []


PERSISTENT_FALLBACK_PATH = "./data/chroma"


class RAGService:
    """Service for RAG (Retrieval Augmented Generation) using ChromaDB"""

    def __init__(self):
        self._client = None
        self._collections: Dict[str, Any] = {}
        # CB-2043: surface RAG mode at startup so silent fallback to the
        # embedded SQLite path can never recur. `_mode` is one of
        # {"HTTP", "PERSISTENT", None}; `_mode_detail` carries the host:port
        # or filesystem path that backs the active client.
        self._mode: Optional[str] = None
        self._mode_detail: Optional[str] = None

    @property
    def client(self):
        """Return the already-initialized ChromaDB client.

        Must be initialized at startup via _init_client_blocking() /
        _fallback_to_persistent() before the first request hits.
        If somehow still None, fall back synchronously (degraded path).
        """
        if self._client is None:
            logger.warning(
                "ChromaDB client accessed before startup init; "
                "falling back to PersistentClient synchronously"
            )
            self._fallback_to_persistent()
        return self._client

    def _reset_state(self) -> None:
        """CB-2212: zero out every field that depends on the active client.

        Both init paths (`_init_client_blocking`, `_fallback_to_persistent`)
        must reset identically — otherwise a future "reconnect" caller can
        leave `_collections` pointing at handles bound to a dead client
        (the half-initialised state CB-2043's reset block aimed to prevent).
        """
        self._client = None
        self._mode = None
        self._mode_detail = None
        self._collections = {}

    def _init_client_blocking(self) -> None:
        """Blocking: probe TCP, construct HttpClient, verify via heartbeat.

        Raises on any connectivity failure so the caller can fall back.
        Intended to be called via asyncio.to_thread() from the lifespan.
        """
        # CB-2043 (review): reset mode/client up front so a mid-init failure
        # cannot leave stale `_mode` reporting HTTP while `_client` is None
        # or still pointing at a previous backend.
        self._reset_state()

        host = settings.CHROMA_HOST
        port = settings.CHROMA_PORT

        # Fast TCP probe with 5 s timeout — avoids the 75 s macOS SYN hang
        try:
            conn = socket.create_connection((host, port), timeout=5)
            conn.close()
        except OSError as exc:
            raise ConnectionError(
                f"ChromaDB TCP probe failed ({host}:{port}): {exc}"
            ) from exc

        client = chromadb.HttpClient(host=host, port=port)

        # Heartbeat confirms the server is actually responding to HTTP
        try:
            client.heartbeat()
        except Exception as exc:
            raise ConnectionError(
                f"ChromaDB heartbeat failed ({host}:{port}): {exc}"
            ) from exc

        self._client = client
        self._mode = "HTTP"
        self._mode_detail = f"{host}:{port}"

    def _fallback_to_persistent(self) -> None:
        """Switch to a local PersistentClient (no external server needed)."""
        # CB-2043 (review): reset state so a PersistentClient(...) raise
        # cannot leave the prior HTTP `_mode` advertised next to a now-None
        # client.
        self._reset_state()

        self._client = chromadb.PersistentClient(
            path=PERSISTENT_FALLBACK_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        self._mode = "PERSISTENT"
        self._mode_detail = os.path.abspath(PERSISTENT_FALLBACK_PATH)

    def describe_mode(self) -> str:
        """CB-2043: build a one-line summary of the active RAG backend.

        Format:
          RAG mode=HTTP host=<host> port=<port> collections=<N>
          RAG mode=PERSISTENT path=<abspath> collections=<N>
          RAG mode=UNINITIALIZED

        Collection count is best-effort — a count failure must never block
        startup logging, so we fall back to "?" rather than raise.
        """
        if self._mode is None or self._client is None:
            return "RAG mode=UNINITIALIZED"

        try:
            collections = self._client.list_collections()
            count = len(collections) if collections is not None else 0
            count_str = str(count)
        except Exception as exc:
            logger.debug("list_collections failed during describe_mode: %s", exc)
            count_str = "?"

        if self._mode == "HTTP":
            host, _, port = (self._mode_detail or "").partition(":")
            return (
                f"RAG mode=HTTP host={host or '?'} port={port or '?'} "
                f"collections={count_str}"
            )
        return (
            f"RAG mode=PERSISTENT path={self._mode_detail or '?'} "
            f"collections={count_str}"
        )

    def get_status_payload(self) -> Dict[str, Any]:
        """CB-2045: structured status snapshot for /api/system/rag/status.

        Returns a dict with:
          - mode: "HTTP" | "PERSISTENT" | "UNINITIALIZED"
          - host: str (host for HTTP; abspath for PERSISTENT; "" otherwise)
          - port: int (TCP port for HTTP; 0 for PERSISTENT/UNINITIALIZED)
          - collections: list[{"name": str, "count": int|None}]
          - total_docs: int (sum of per-collection counts; 0 on partial failure)
          - healthy: bool (True iff client is up AND collection enumeration
            succeeded AND, for HTTP, heartbeat succeeded)

        Best-effort: any error during collection enumeration or per-collection
        count is captured and reflected by `healthy=False`. The endpoint must
        never raise — silent fallback or a half-broken backend is exactly what
        this surface exists to expose.
        """
        if self._mode is None or self._client is None:
            return {
                "mode": "UNINITIALIZED",
                "host": "",
                "port": 0,
                "collections": [],
                "total_docs": 0,
                "healthy": False,
            }

        if self._mode == "HTTP":
            host_part, _, port_part = (self._mode_detail or "").partition(":")
            host = host_part
            try:
                port = int(port_part) if port_part else 0
            except ValueError:
                port = 0
        else:
            host = self._mode_detail or ""
            port = 0

        healthy = True

        if self._mode == "HTTP":
            try:
                self._client.heartbeat()
            except Exception as exc:
                # Surface at WARNING — this endpoint exists precisely to
                # expose silent backend failures (CB-2043/CB-2045 motivation).
                logger.warning(
                    "RAG heartbeat failed during get_status_payload: %s", exc
                )
                healthy = False

        collections_payload: List[Dict[str, Any]] = []
        total_docs = 0
        try:
            collections = self._client.list_collections() or []
        except Exception as exc:
            logger.warning(
                "RAG list_collections failed during get_status_payload: %s", exc
            )
            collections = []
            healthy = False

        for col in collections:
            name = getattr(col, "name", None) or str(col)
            try:
                count = col.count()
                total_docs += int(count)
            except Exception as exc:
                logger.debug(
                    "count() failed for collection %s in get_status_payload: %s",
                    name, exc,
                )
                count = None
                healthy = False
            collections_payload.append({"name": name, "count": count})

        return {
            "mode": self._mode,
            "host": host,
            "port": port,
            "collections": collections_payload,
            "total_docs": total_docs,
            "healthy": healthy,
        }

    def get_collection(self, project_id: str):
        """Get or create a collection for a project"""
        collection_name = f"project_{project_id[:8]}"

        if collection_name not in self._collections:
            self._collections[collection_name] = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"project_id": project_id},
            )

        return self._collections[collection_name]

    def generate_doc_id(self, issue_id: str, content_type: str = "issue") -> str:
        """Generate a unique document ID"""
        return hashlib.md5(f"{content_type}:{issue_id}".encode()).hexdigest()

    async def embed_issue(
        self,
        project_id: str,
        issue_id: str,
        key: str,
        title: str,
        description: Optional[str] = None,
        issue_type: str = "TASK",
        status: str = "BACKLOG",
        labels: Optional[str] = None,
    ) -> bool:
        """Embed an issue into the vector store"""
        try:
            collection = self.get_collection(project_id)

            # Create document text
            doc_parts = [
                f"[{key}] {title}",
                f"Type: {issue_type}",
                f"Status: {status}",
            ]
            if description:
                doc_parts.append(f"Description: {description}")
            if labels:
                doc_parts.append(f"Labels: {labels}")

            document = "\n".join(doc_parts)
            doc_id = self.generate_doc_id(issue_id)

            # Upsert to collection
            collection.upsert(
                ids=[doc_id],
                documents=[document],
                metadatas=[{
                    "issue_id": issue_id,
                    "key": key,
                    "type": issue_type,
                    "status": status,
                }],
            )

            return True
        except Exception as e:
            print(f"Error embedding issue: {e}")
            return False

    async def delete_issue_embedding(self, project_id: str, issue_id: str) -> bool:
        """Delete an issue embedding"""
        try:
            collection = self.get_collection(project_id)
            doc_id = self.generate_doc_id(issue_id)
            collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            print(f"Error deleting embedding: {e}")
            return False

    async def search_issues(
        self,
        project_id: str,
        query: str,
        n_results: int = 10,
        filter_type: Optional[str] = None,
        filter_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar issues using semantic search"""
        try:
            collection = self.get_collection(project_id)

            # Build where filter
            where_filter = None
            if filter_type or filter_status:
                conditions = []
                if filter_type:
                    conditions.append({"type": filter_type})
                if filter_status:
                    conditions.append({"status": filter_status})

                if len(conditions) == 1:
                    where_filter = conditions[0]
                else:
                    where_filter = {"$and": conditions}

            # Query
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            # Format results
            search_results = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    search_results.append({
                        "issue_id": results["metadatas"][0][i].get("issue_id"),
                        "key": results["metadatas"][0][i].get("key"),
                        "type": results["metadatas"][0][i].get("type"),
                        "status": results["metadatas"][0][i].get("status"),
                        "document": results["documents"][0][i] if results["documents"] else None,
                        "distance": results["distances"][0][i] if results["distances"] else None,
                        "score": 1 - (results["distances"][0][i] if results["distances"] else 0),
                    })

            return search_results
        except Exception as e:
            print(f"Error searching: {e}")
            return []

    async def find_similar_issues(
        self,
        project_id: str,
        title: str,
        description: Optional[str] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find issues similar to the given title/description"""
        query = title
        if description:
            query = f"{title}\n{description}"

        return await self.search_issues(project_id, query, n_results)

    async def get_context_for_ai(
        self,
        project_id: str,
        query: str,
        n_results: int = 5,
    ) -> str:
        """Get relevant context for AI operations"""
        results = await self.search_issues(project_id, query, n_results)

        if not results:
            return "No relevant issues found."

        context_parts = ["Relevant existing issues:"]
        for r in results:
            context_parts.append(f"- [{r['key']}] ({r['type']}, {r['status']})")
            if r.get("document"):
                # Extract just the title from the document
                lines = r["document"].split("\n")
                if lines:
                    context_parts.append(f"  {lines[0]}")

        return "\n".join(context_parts)

    async def embed_ai_context(
        self,
        project_id: str,
        issue_id: str,
        issue_key: str,
        issue_type: str,
        ai_context: str,
    ) -> bool:
        """
        Embed an issue's aiContext text into ChromaDB for RAG retrieval.

        Uses a separate doc_id (content_type="ai_context") so it doesn't
        overwrite the standard issue embedding.
        """
        try:
            collection = self.get_collection(project_id)
            doc_id = self.generate_doc_id(issue_id, content_type="ai_context")

            document = f"[{issue_key}] AI Context ({issue_type}):\n{ai_context}"

            collection.upsert(
                ids=[doc_id],
                documents=[document],
                metadatas=[{
                    "issue_id": issue_id,
                    "key": issue_key,
                    "type": issue_type,
                    "context_type": "ai_context",
                }],
            )

            logger.info(f"Embedded aiContext for {issue_key} into ChromaDB")
            return True
        except Exception as e:
            logger.warning(f"Error embedding aiContext for {issue_key}: {e}")
            return False

    async def embed_execution_summary(
        self,
        project_id: str,
        issue_id: str,
        issue_key: str,
        summary: "ExecutionSummary",
    ) -> bool:
        """Index an ExecutionSummary into ChromaDB for RAG retrieval.

        Uses a stable per-issue doc_id so the latest summary for an issue
        replaces any prior one (mirrors the embed_ai_context() pattern).
        """
        try:
            doc_text = (
                f"[{issue_key}] Implementation Summary:\n"
                f"{summary.summary or ''}\n\n"
            )
            if summary.architectureNotes:
                doc_text += f"Architecture: {summary.architectureNotes}\n"
            if summary.technicalNotes:
                doc_text += f"Technical: {summary.technicalNotes}\n"
            if summary.componentsModified:
                components = _safe_json_list(summary.componentsModified)
                if components:
                    doc_text += f"Components: {', '.join(components)}\n"
            if summary.filesTouched:
                files = _safe_json_list(summary.filesTouched)
                if files:
                    # Cap files in the embedded blob to keep doc size sane
                    doc_text += f"Files: {', '.join(files[:50])}\n"

            doc_id = self.generate_doc_id(
                issue_id, content_type="execution_summary"
            )
            collection = self.get_collection(project_id)
            collection.upsert(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[{
                    "issue_id": issue_id,
                    "key": issue_key,
                    "content_type": "execution_summary",
                }],
            )
            logger.info(
                "Embedded ExecutionSummary for %s into ChromaDB", issue_key
            )
            return True
        except Exception as e:
            logger.warning(
                "Error embedding ExecutionSummary for %s: %s", issue_key, e
            )
            return False

    async def embed_feature_documentation(
        self,
        project_id: str,
        feature_issue_id: str,
        feature_key: str,
        doc: "FeatureDocumentation",
    ) -> bool:
        """Index a FeatureDocumentation row into ChromaDB for RAG retrieval.

        Uses a stable per-feature doc_id (`content_type="feature_documentation"`)
        so re-running the documentation generator replaces the prior
        embedding instead of stacking duplicates. Mirrors the
        `embed_execution_summary` integration so callers can rely on the
        same (project_id, key, content_type) metadata shape when querying.

        Returns True only when the upsert succeeded; failures are logged
        and the caller is expected to NOT update `embeddingId` / `lastIndexedAt`
        on the row.
        """
        try:
            doc_text_parts = [
                f"[{feature_key}] Feature Documentation: {doc.title or ''}".strip(),
            ]
            if doc.overview:
                doc_text_parts.append(f"Overview:\n{doc.overview}")
            if doc.architecture:
                doc_text_parts.append(f"Architecture:\n{doc.architecture}")
            if doc.testingStrategy:
                doc_text_parts.append(f"Testing Strategy:\n{doc.testingStrategy}")
            if doc.techStack:
                # techStack is JSON-encoded list[str]; flatten to a CSV
                # for the embedding text rather than embedding raw JSON.
                stack = _safe_json_list(doc.techStack)
                if stack:
                    doc_text_parts.append(
                        "Tech Stack: " + ", ".join(stack[:50])
                    )

            doc_text = "\n\n".join(doc_text_parts)

            doc_id = self.generate_doc_id(
                feature_issue_id, content_type="feature_documentation"
            )
            collection = self.get_collection(project_id)
            collection.upsert(
                ids=[doc_id],
                documents=[doc_text],
                metadatas=[{
                    "issue_id": feature_issue_id,
                    "key": feature_key,
                    "content_type": "feature_documentation",
                }],
            )
            logger.info(
                "Embedded FeatureDocumentation for %s into ChromaDB", feature_key
            )
            return True
        except Exception as e:
            logger.warning(
                "Error embedding FeatureDocumentation for %s: %s",
                feature_key, e,
            )
            return False

    async def search_execution_docs(
        self,
        project_id: str,
        query: str,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search over execution summaries for a project.

        Filters the project's collection to documents indexed by
        embed_execution_summary() (content_type == "execution_summary")
        and returns the top n_results matches in the same shape as
        search_issues() so callers can format consistently.
        """
        try:
            collection = self.get_collection(project_id)

            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"content_type": "execution_summary"},
                include=["documents", "metadatas", "distances"],
            )

            search_results: List[Dict[str, Any]] = []
            if results and results.get("ids") and results["ids"][0]:
                for i, _doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] or {}
                    distance = (
                        results["distances"][0][i]
                        if results.get("distances")
                        else None
                    )
                    search_results.append({
                        "issue_id": metadata.get("issue_id"),
                        "key": metadata.get("key"),
                        "content_type": metadata.get("content_type"),
                        "document": (
                            results["documents"][0][i]
                            if results.get("documents")
                            else None
                        ),
                        "distance": distance,
                        "score": 1 - (distance if distance is not None else 0),
                    })

            return search_results
        except Exception as e:
            logger.warning(
                "Error searching execution docs for project %s: %s",
                project_id,
                e,
            )
            return []

    async def delete_ai_context_embedding(
        self,
        project_id: str,
        issue_id: str,
    ) -> bool:
        """Delete the aiContext embedding for an issue (e.g., when cleared)."""
        try:
            collection = self.get_collection(project_id)
            doc_id = self.generate_doc_id(issue_id, content_type="ai_context")
            collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.warning(f"Error deleting aiContext embedding: {e}")
            return False

    async def get_ancestor_ai_context(
        self,
        db,
        issue_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Walk up the parent chain from issue_id and collect aiContext values
        from all ancestor issues (e.g., TASK -> STORY -> EPIC -> FEATURE).

        Returns a list of dicts ordered from nearest parent to furthest ancestor:
        [
            {"issue_id": ..., "key": ..., "type": ..., "aiContext": ...},
            ...
        ]

        The `db` parameter is an AsyncSession from SQLAlchemy.
        """
        from sqlalchemy import select
        from models import Issue

        ancestors = []
        current_id = issue_id
        visited = set()

        while current_id:
            # Prevent infinite loops in case of data corruption
            if current_id in visited:
                break
            visited.add(current_id)

            # Fetch the current issue's parentId and aiContext
            result = await db.execute(
                select(Issue.id, Issue.parentId, Issue.key, Issue.type, Issue.aiContext)
                .where(Issue.id == current_id)
            )
            row = result.one_or_none()

            if not row:
                break

            issue_id_val, parent_id, key, issue_type, ai_context = row

            # Only collect from ancestors (skip the original issue itself)
            if issue_id_val != issue_id and ai_context:
                ancestors.append({
                    "issue_id": issue_id_val,
                    "key": key,
                    "type": issue_type,
                    "aiContext": ai_context,
                })

            current_id = parent_id

        return ancestors

    async def get_full_ai_context_for_execution(
        self,
        db,
        issue_id: str,
    ) -> str:
        """
        Build a formatted string of all ancestor AI context for use during
        issue execution. Includes the issue's own aiContext plus all ancestors.

        Returns a human-readable string suitable for injecting into AI prompts.
        """
        from sqlalchemy import select
        from models import Issue

        # Get the issue's own context
        result = await db.execute(
            select(Issue.key, Issue.type, Issue.aiContext)
            .where(Issue.id == issue_id)
        )
        row = result.one_or_none()

        parts = []

        if row:
            key, issue_type, own_context = row
            if own_context:
                parts.append(f"[{key}] ({issue_type}) AI Context:\n{own_context}")

        # Get ancestor contexts (nearest parent first)
        ancestors = await self.get_ancestor_ai_context(db, issue_id)

        for ancestor in ancestors:
            parts.append(
                f"[{ancestor['key']}] ({ancestor['type']}) AI Context:\n{ancestor['aiContext']}"
            )

        if not parts:
            return ""

        return "\n\n---\n\n".join(parts)

    async def get_implementation_context_for_qa(
        self,
        db,
        project_id: str,
        issue_id: str,
    ) -> str:
        """Build a formatted implementation-context string for QA test generation.

        Loads the most recent ExecutionSummary for the issue and renders a
        markdown-style block covering summary, files, components, and notes.
        Returns "" when no execution summary exists for the issue or when
        the issue does not belong to the requested project.

        Scoping by `project_id` enforces a cross-project isolation boundary:
        callers cannot exfiltrate another project's implementation summary
        by passing a foreign issue_id (CB-1597 sec audit, H-1).

        The `db` parameter is an AsyncSession from SQLAlchemy.
        """
        from sqlalchemy import select
        from models import ExecutionSummary, Issue

        result = await db.execute(
            select(ExecutionSummary)
            .join(Issue, Issue.id == ExecutionSummary.issueId)
            .where(
                ExecutionSummary.issueId == issue_id,
                Issue.projectId == project_id,
            )
            .order_by(ExecutionSummary.executedAt.desc())
            .limit(1)
        )
        summary = result.scalar_one_or_none()

        if not summary:
            return ""

        parts = [f"## Implementation Summary\n{summary.summary}"]

        files = _safe_json_list(summary.filesTouched)
        if files:
            parts.append("## Files Modified\n" + "\n".join(f"- {f}" for f in files))

        comps = _safe_json_list(summary.componentsModified)
        if comps:
            parts.append("## Components\n" + ", ".join(comps))

        if summary.architectureNotes:
            parts.append(f"## Architecture Notes\n{summary.architectureNotes}")
        if summary.technicalNotes:
            parts.append(f"## Technical Notes\n{summary.technicalNotes}")
        if summary.challengesFaced:
            parts.append(f"## Known Challenges\n{summary.challengesFaced}")

        return "\n\n".join(parts)


# No module-level singleton — instance lives on app.state.rag (see app/main.py lifespan)
