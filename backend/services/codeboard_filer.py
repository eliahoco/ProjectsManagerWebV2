"""
CodeBoardFiler — CB-2914 E7.

After an investigation cycle completes and the user approves the
5-part deliverable, the filer walks the proposed agile plan top-down
and creates the FEATURE → EPIC → STORY → TASK tree in CodeBoard
via the existing POST /api/projects/{project_id}/issues endpoint
(internal loopback). Each node carries:

  - title (from the plan row)
  - type (FEATURE / EPIC / STORY / TASK / SUBTASK)
  - priority (from UrgencyClassifier — E6)
  - labels (from UrgencyClassifier)
  - parentId (resolved from the previously-created parent)
  - description (richer body with rationale + investigation context)
  - reporter = "AI-Studio-SIE"

The plan source is the InvestigationResult's deliverable_markdown.
For Phase 1 the filer accepts an explicit `PlanNode` tree from the
caller (the synthesizer or the UI approval flow) rather than re-parsing
markdown — keeps the contract clean and unit-testable.

Idempotency: every issue is filed with a `breakdownBatchId` tag that
the CodeBoard side already uses for grouped re-runs. Repeat invocations
with the same `batch_id` are detected and skipped at the application
layer (per-issue title+parent dedup).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings
# CB-2914 sec-audit MED-1 fix: use canonical redact_secrets (covers
# Stripe / Google / Slack / Basic / ASIA-AWS / secret-token-auth) instead
# of the local subset previously defined here.
from utils.exhaustion_detector import redact_secrets as _canonical_redact

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10.0
_MAX_TITLE = 200
_MAX_DESC = 8000
_VALID_TYPES = {"FEATURE", "EPIC", "STORY", "TASK", "SUBTASK"}
_VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


# ---------------------------------------------------------------------------
# Plan tree (input to the filer)
# ---------------------------------------------------------------------------

@dataclass
class PlanNode:
    """One node in the agile plan tree.

    `children` is filled depth-first; parent_id is resolved at file time
    (the caller doesn't need to know UUIDs in advance).
    """

    title: str
    type: str  # FEATURE / EPIC / STORY / TASK / SUBTASK
    priority: str = "MEDIUM"
    description: str = ""
    labels: str = ""
    assignee: Optional[str] = None
    children: list["PlanNode"] = field(default_factory=list)
    # Filled at file time
    created_id: Optional[str] = None
    created_key: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class FileReport:
    """What the filer produced. One row per node, in BFS order."""

    batch_id: str
    project_id: str
    created: list[dict]
    skipped: list[dict]
    errors: list[dict]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CodeBoardFiler:
    """Walks a PlanNode tree top-down and files every node in CodeBoard.

    Idempotent at the per-issue level: a node with the same (title, parent_id)
    as an existing CodeBoard issue under the same project is skipped.
    """

    def __init__(self, *, timeout_s: float = _DEFAULT_TIMEOUT):
        self.timeout_s = timeout_s

    async def file_plan(
        self,
        project_id: str,
        root: PlanNode,
        *,
        batch_id: Optional[str] = None,
        existing_titles: Optional[set[tuple[Optional[str], str]]] = None,
    ) -> FileReport:
        """File the whole tree top-down. Returns a FileReport.

        Args:
            project_id: CodeBoard project the plan belongs to.
            root: top of the plan tree (typically a FEATURE node).
            batch_id: idempotency token. Defaults to a fresh UUID.
            existing_titles: optional pre-fetched set of (parent_id, title)
                tuples already present in the project — used to skip dupes
                without an extra HTTP call. If omitted, the filer fetches
                the current project's issues once at the start.
        """
        if not project_id:
            raise ValueError("project_id required")
        if root.type not in _VALID_TYPES:
            raise ValueError(f"invalid root type {root.type!r}")
        batch_id = batch_id or str(uuid.uuid4())

        if existing_titles is None:
            existing_titles = await self._snapshot_existing_titles(project_id)

        created: list[dict] = []
        skipped: list[dict] = []
        errors: list[dict] = []

        # Walk BFS so each parent resolves before its children.
        queue: list[tuple[PlanNode, Optional[str]]] = [(root, None)]
        while queue:
            node, parent_id = queue.pop(0)
            key = (parent_id, node.title.strip().lower())
            if key in existing_titles:
                node.skipped = True
                node.skip_reason = "duplicate title under same parent"
                skipped.append({"title": node.title, "reason": node.skip_reason})
                logger.info("CodeBoardFiler: skip duplicate %r under parent=%s",
                            node.title, parent_id)
                # Children of a skipped parent are also skipped (no parent to attach).
                continue

            try:
                created_node = await self._post_issue(project_id, node, parent_id, batch_id)
            except Exception as exc:
                logger.exception("CodeBoardFiler: POST failed for %r", node.title)
                errors.append({"title": node.title, "error": str(exc)[:200]})
                continue

            node.created_id = created_node.get("id")
            node.created_key = created_node.get("key")
            existing_titles.add(key)
            created.append({
                "title": node.title,
                "key": node.created_key,
                "id": node.created_id,
                "type": node.type,
            })

            for child in node.children:
                queue.append((child, node.created_id))

        return FileReport(
            batch_id=batch_id,
            project_id=project_id,
            created=created,
            skipped=skipped,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _snapshot_existing_titles(self, project_id: str) -> set[tuple[Optional[str], str]]:
        """Pull the current project's issues once + index by (parent_id, lowercased-title)."""
        headers = self._loopback_headers()
        url = f"{settings.backend_base_url}/api/projects/{project_id}/issues?page=1&pageSize=500"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as http:
                resp = await http.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("snapshot_existing_titles: HTTP %d — proceeding with empty index",
                               resp.status_code)
                return set()
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])
        except httpx.RequestError as exc:
            logger.warning("snapshot_existing_titles: network error %s — proceeding with empty index", exc)
            return set()

        out: set[tuple[Optional[str], str]] = set()
        for i in items:
            t = (i.get("title") or "").strip().lower()
            if not t:
                continue
            out.add((i.get("parentId"), t))
        return out

    async def _post_issue(
        self,
        project_id: str,
        node: PlanNode,
        parent_id: Optional[str],
        batch_id: str,
    ) -> dict:
        # Validate
        if node.type not in _VALID_TYPES:
            raise ValueError(f"invalid type {node.type!r} on {node.title!r}")
        priority = node.priority.upper() if node.priority else "MEDIUM"
        if priority not in _VALID_PRIORITIES:
            priority = "MEDIUM"

        body: dict = {
            "title": _clean(node.title)[:_MAX_TITLE],
            "type": node.type,
            "priority": priority,
            "description": _clean(node.description)[:_MAX_DESC] if node.description else "",
            "reporter": "AI-Studio-SIE",
            "labels": _clean(node.labels)[:120] if node.labels else "",
        }
        if parent_id:
            body["parentId"] = parent_id
        if node.assignee:
            body["assignee"] = node.assignee
        # CodeBoard schema supports breakdownBatchId for grouping.
        body["breakdownBatchId"] = batch_id

        url = f"{settings.backend_base_url}/api/projects/{project_id}/issues"
        async with httpx.AsyncClient(timeout=self.timeout_s) as http:
            resp = await http.post(url, json=body, headers=self._loopback_headers())
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def _loopback_headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if settings.INTERNAL_API_TOKEN:
            h["X-Internal-Token"] = settings.INTERNAL_API_TOKEN
        return h


# ---------------------------------------------------------------------------
# Helper — delegate to the canonical scrub list to keep redaction patterns
# in lockstep with AutoPilot + Studio chat agent (sec-audit MED-1 fix).
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    if not text:
        return ""
    return _canonical_redact(text)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_filer: Optional[CodeBoardFiler] = None


def get_codeboard_filer() -> CodeBoardFiler:
    global _filer
    if _filer is None:
        _filer = CodeBoardFiler()
    return _filer
