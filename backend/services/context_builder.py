"""
Context Builder Service — Rich prompt context for AI executions.

Hybrid prompt strategy:
  Always loaded (~3-5K tokens):
    - Parent chain (TASK → STORY → EPIC → FEATURE) with descriptions
    - Sibling issues with status summaries
    - Ancestor AI Context (free-text guidance from parents)
  From ChromaDB RAG (variable, added separately):
    - Similar past implementations
    - AI Context from non-ancestor issues

Target: ~5-8K tokens total per execution.
"""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from models.issue import Issue

logger = logging.getLogger(__name__)

# Token budget (approximate: 1 token ≈ 4 chars)
MAX_PROMPT_CHARS = 32000  # ~8K tokens


async def get_parent_chain(db: AsyncSession, issue_id: str) -> List[dict]:
    """
    Walk up the issue hierarchy and return the full parent chain.
    Returns list from immediate parent to root, e.g.:
    [STORY, EPIC, FEATURE]
    Also collects aiContext from each ancestor.
    """
    chain = []
    current_id = issue_id

    # Walk up (max 10 levels to prevent infinite loops)
    for _ in range(10):
        result = await db.execute(
            select(Issue.id, Issue.parentId, Issue.key, Issue.title, Issue.type, Issue.status, Issue.description, Issue.aiContext)
            .where(Issue.id == current_id)
        )
        row = result.first()
        if not row or not row[1]:  # no parent
            break

        parent_id = row[1]

        # Fetch parent
        parent_result = await db.execute(
            select(Issue.id, Issue.key, Issue.title, Issue.type, Issue.status, Issue.description, Issue.aiContext)
            .where(Issue.id == parent_id)
        )
        parent = parent_result.first()
        if not parent:
            break

        chain.append({
            "id": parent[0],
            "key": parent[1],
            "title": parent[2],
            "type": parent[3],
            "status": parent[4],
            "description": parent[5] or "",
            "aiContext": parent[6] or "",
        })
        current_id = parent_id

    return chain


async def get_siblings(db: AsyncSession, issue_id: str, parent_id: str) -> List[dict]:
    """
    Get sibling issues (same parent) with their key, title, type, and status.
    Excludes the current issue itself.
    """
    result = await db.execute(
        select(Issue.id, Issue.key, Issue.title, Issue.type, Issue.status)
        .where(Issue.parentId == parent_id, Issue.id != issue_id)
        .order_by(Issue.sequence)
    )
    rows = result.fetchall()
    return [
        {"key": r[1], "title": r[2], "type": r[3], "status": r[4]}
        for r in rows
    ]


def format_context_section(
    issue_key: str,
    issue_title: str,
    issue_type: str,
    issue_description: str,
    parent_chain: List[dict],
    siblings: List[dict],
) -> str:
    """
    Format the parent chain and siblings into a structured prompt section.

    Returns a string ready to be injected into the Claude Code prompt.
    """
    parts = []

    # Header
    parts.append(f"I need you to implement the following {issue_type}:")
    parts.append("")
    parts.append(f"**{issue_key}: {issue_title}**")
    parts.append("")

    # Parent chain — gives Claude the big-picture context
    if parent_chain:
        parts.append("## Hierarchy Context")
        # Show from root to leaf
        for i, ancestor in enumerate(reversed(parent_chain)):
            indent = "  " * i
            status_tag = f" [{ancestor['status']}]"
            parts.append(f"{indent}- {ancestor['type']} {ancestor['key']}: {ancestor['title']}{status_tag}")
            # Include brief description for FEATURE/EPIC (strategic context)
            if ancestor["type"] in ("FEATURE", "EPIC") and ancestor["description"]:
                desc = ancestor["description"][:300]
                if len(ancestor["description"]) > 300:
                    desc += "..."
                parts.append(f"{indent}  _{desc}_")
        # Current issue marker
        indent = "  " * len(parent_chain)
        parts.append(f"{indent}- **{issue_type} {issue_key}: {issue_title} ← YOU ARE HERE**")
        parts.append("")

    # Sibling summary — shows what's done, what's left
    if siblings:
        done = [s for s in siblings if s["status"] == "DONE"]
        waiting_qa = [s for s in siblings if s["status"] == "COMPLETED_WAITING_QA"]
        in_progress = [s for s in siblings if s["status"] == "IN_PROGRESS"]
        remaining = [s for s in siblings if s["status"] in ("BACKLOG", "TODO")]

        parts.append("## Sibling Tasks (same parent)")
        if done:
            parts.append(f"Completed ({len(done)}):")
            for s in done:
                parts.append(f"  - {s['key']}: {s['title']} [DONE]")
        if waiting_qa:
            parts.append(f"Waiting QA ({len(waiting_qa)}):")
            for s in waiting_qa:
                parts.append(f"  - {s['key']}: {s['title']} [WAITING QA]")
        if in_progress:
            parts.append(f"In Progress ({len(in_progress)}):")
            for s in in_progress:
                parts.append(f"  - {s['key']}: {s['title']} [IN PROGRESS]")
        if remaining:
            parts.append(f"Not Started ({len(remaining)}):")
            for s in remaining:
                parts.append(f"  - {s['key']}: {s['title']}")
        parts.append("")

    # Ancestor AI Context — strategic guidance from parents
    ai_contexts = [
        (a["key"], a["type"], a["aiContext"])
        for a in reversed(parent_chain)
        if a.get("aiContext")
    ]
    if ai_contexts:
        parts.append("## AI Context (from ancestors)")
        for key, atype, ctx in ai_contexts:
            parts.append(f"### From {atype} {key}:")
            parts.append(ctx.strip())
            parts.append("")

    # Description
    if issue_description:
        parts.append("## Task Description")
        parts.append(issue_description)
        parts.append("")

    parts.append("Please implement this task. When you're done, summarize what you did.")

    prompt = "\n".join(parts)

    # Token budget enforcement
    if len(prompt) > MAX_PROMPT_CHARS:
        logger.warning(
            f"Prompt for {issue_key} exceeds budget ({len(prompt)} chars). Truncating."
        )
        prompt = prompt[:MAX_PROMPT_CHARS] + "\n\n[Context truncated for token budget]"

    return prompt


async def build_execution_context(
    db: AsyncSession,
    issue_id: str,
    issue_key: str,
    issue_title: str,
    issue_type: str,
    issue_description: str,
) -> str:
    """
    Build the full rich context prompt for an AI execution.

    Combines parent chain, sibling context, and issue details
    into a structured prompt.
    """
    # Get parent chain
    parent_chain = await get_parent_chain(db, issue_id)

    # Get siblings if the issue has a parent
    siblings = []
    # Find this issue's parentId
    result = await db.execute(
        select(Issue.parentId).where(Issue.id == issue_id)
    )
    row = result.first()
    if row and row[0]:
        siblings = await get_siblings(db, issue_id, row[0])

    return format_context_section(
        issue_key=issue_key,
        issue_title=issue_title,
        issue_type=issue_type,
        issue_description=issue_description,
        parent_chain=parent_chain,
        siblings=siblings,
    )
