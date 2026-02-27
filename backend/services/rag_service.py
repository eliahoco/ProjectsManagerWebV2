"""
RAG Service - Semantic Search using ChromaDB
"""

import chromadb
from chromadb.config import Settings
from typing import List, Optional, Dict, Any
import hashlib
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class RAGService:
    """Service for RAG (Retrieval Augmented Generation) using ChromaDB"""

    def __init__(self):
        self._client = None
        self._collections: Dict[str, Any] = {}

    @property
    def client(self):
        """Lazy initialization of ChromaDB client"""
        if self._client is None:
            try:
                # Try to connect to ChromaDB server
                self._client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST,
                    port=settings.CHROMA_PORT,
                )
            except Exception:
                # Fall back to persistent local storage
                self._client = chromadb.PersistentClient(
                    path="./data/chroma",
                    settings=Settings(anonymized_telemetry=False),
                )
        return self._client

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


# Singleton instance
rag_service = RAGService()
