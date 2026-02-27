"""
Agent Registry Service - Manages AI agent profiles and matching logic.

Scans the agents directory for available agents, registers them in the database,
and provides matching to select the best agent for a given task.
"""

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_registry import AgentProfile

logger = logging.getLogger(__name__)

# Default capability mappings inferred from agent names when AGENT.md
# frontmatter doesn't provide explicit capabilities
DEFAULT_CAPABILITIES: Dict[str, List[str]] = {
    "ai-engineer": ["ai", "ml", "machine-learning", "training", "inference"],
    "api-designer": ["api", "rest", "graphql", "openapi", "schema-design"],
    "cloud-architect": ["aws", "gcp", "azure", "cloud", "infrastructure", "terraform"],
    "code-reviewer": ["code-review", "refactoring", "best-practices", "linting"],
    "debugger": ["debugging", "profiling", "error-analysis", "stack-traces"],
    "devops-engineer": ["ci-cd", "docker", "kubernetes", "deployment", "monitoring"],
    "docker-expert": ["docker", "dockerfile", "docker-compose", "containers"],
    "fullstack-developer": ["frontend", "backend", "fullstack", "react", "node", "python"],
    "git-workflow-manager": ["git", "branching", "merge", "rebase", "workflow"],
    "llm-architect": ["llm", "prompt-engineering", "rag", "embeddings", "fine-tuning"],
    "nextjs-developer": ["nextjs", "react", "typescript", "ssr", "app-router"],
    "python-pro": ["python", "fastapi", "sqlalchemy", "pytest", "async"],
    "react-specialist": ["react", "typescript", "state-management", "performance"],
    "security-auditor": ["security", "vulnerability", "audit", "owasp", "penetration-testing"],
    "typescript-pro": ["typescript", "type-safety", "generics", "decorators"],
}

# Default issue type affinity when not explicitly provided
DEFAULT_ISSUE_TYPE_AFFINITY: Dict[str, List[str]] = {
    "debugger": ["BUG"],
    "code-reviewer": ["TASK", "SUBTASK"],
    "security-auditor": ["BUG", "TASK"],
    "devops-engineer": ["TASK", "STORY"],
    "docker-expert": ["TASK", "SUBTASK"],
}

# Default file patterns for agent matching
DEFAULT_PROJECT_PATTERNS: Dict[str, List[str]] = {
    "python-pro": ["*.py", "backend/**", "requirements.txt", "pyproject.toml"],
    "react-specialist": ["*.tsx", "*.jsx", "src/components/**"],
    "nextjs-developer": ["*.tsx", "*.ts", "app/**", "pages/**", "next.config.*"],
    "typescript-pro": ["*.ts", "*.tsx", "tsconfig.json"],
    "docker-expert": ["Dockerfile*", "docker-compose*", ".dockerignore"],
    "devops-engineer": ["*.yml", "*.yaml", ".github/**", "Makefile"],
    "api-designer": ["*.py", "*.ts", "api/**", "routes/**"],
    "fullstack-developer": ["*.py", "*.ts", "*.tsx", "backend/**", "frontend/**"],
    "security-auditor": ["*.py", "*.ts", "*.js", "*.env*"],
    "git-workflow-manager": [".github/**", ".gitignore", ".git/**"],
}


def _parse_agent_frontmatter(content: str) -> Dict[str, str]:
    """
    Parse YAML-like frontmatter from an AGENT.md file.

    Expects format:
        ---
        name: agent-name
        description: "..."
        tools: Read, Write, Edit, Bash
        model: sonnet
        ---
    """
    frontmatter: Dict[str, str] = {}
    lines = content.split("\n")

    if not lines or lines[0].strip() != "---":
        return frontmatter

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                frontmatter[key] = value

    return frontmatter


def _name_to_display_name(name: str) -> str:
    """Convert kebab-case agent name to a display name.

    Example: 'python-pro' -> 'Python Pro'
    """
    return " ".join(word.capitalize() for word in name.split("-"))


class AgentRegistryService:
    """Service for managing the agent registry."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def get_all_agents(self, db: AsyncSession, *, active_only: bool = False) -> List[AgentProfile]:
        """Return all registered agents, optionally filtered to active only."""
        stmt = select(AgentProfile).order_by(AgentProfile.priority.desc(), AgentProfile.name)
        if active_only:
            stmt = stmt.where(AgentProfile.isActive == True)  # noqa: E712
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_agent(self, db: AsyncSession, agent_id: str) -> Optional[AgentProfile]:
        """Get a single agent by ID."""
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_by_name(self, db: AsyncSession, name: str) -> Optional[AgentProfile]:
        """Get a single agent by unique name."""
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.name == name)
        )
        return result.scalar_one_or_none()

    async def register_agent(self, db: AsyncSession, data: Dict[str, Any]) -> AgentProfile:
        """Create or update an agent profile.

        If an agent with the same *name* already exists, it is updated in place.
        Otherwise a new record is created.
        """
        name = data.get("name", "")
        existing = await self.get_agent_by_name(db, name)

        if existing:
            # Update in place
            for key, value in data.items():
                if key == "id":
                    continue  # never overwrite the PK
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await db.commit()
            await db.refresh(existing)
            return existing

        # Create new
        agent = AgentProfile(
            id=str(uuid.uuid4()),
            name=data.get("name", ""),
            displayName=data.get("displayName", _name_to_display_name(data.get("name", ""))),
            description=data.get("description"),
            agentPath=data.get("agentPath", ""),
            capabilities=json.dumps(data.get("capabilities", [])) if isinstance(data.get("capabilities"), list) else data.get("capabilities"),
            issueTypeAffinity=json.dumps(data.get("issueTypeAffinity", [])) if isinstance(data.get("issueTypeAffinity"), list) else data.get("issueTypeAffinity"),
            projectPatterns=json.dumps(data.get("projectPatterns", [])) if isinstance(data.get("projectPatterns"), list) else data.get("projectPatterns"),
            isActive=data.get("isActive", True),
            priority=data.get("priority", 50),
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        return agent

    async def deactivate_agent(self, db: AsyncSession, agent_id: str) -> bool:
        """Soft-deactivate an agent by setting isActive=False."""
        result = await db.execute(
            update(AgentProfile)
            .where(AgentProfile.id == agent_id)
            .values(isActive=False)
        )
        await db.commit()
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Agent matching
    # ------------------------------------------------------------------

    async def match_agent(
        self,
        db: AsyncSession,
        *,
        issue_type: Optional[str] = None,
        file_patterns: Optional[List[str]] = None,
        project_type: Optional[str] = None,
    ) -> Optional[AgentProfile]:
        """Find the best agent for a task based on capabilities, issue type affinity,
        and file pattern matching.

        Scoring:
          - issue_type match in issueTypeAffinity:  +20
          - each file_patterns element that matches a projectPatterns glob: +10
          - project_type appears in capabilities: +15
          - base priority score is added as-is

        Returns the agent with the highest combined score, or None if no active agents exist.
        """
        agents = await self.get_all_agents(db, active_only=True)
        if not agents:
            return None

        best_agent: Optional[AgentProfile] = None
        best_score: int = -1

        for agent in agents:
            score = agent.priority  # start with base priority

            # Parse JSON fields
            try:
                affinity: List[str] = json.loads(agent.issueTypeAffinity) if agent.issueTypeAffinity else []
            except (json.JSONDecodeError, TypeError):
                affinity = []

            try:
                patterns: List[str] = json.loads(agent.projectPatterns) if agent.projectPatterns else []
            except (json.JSONDecodeError, TypeError):
                patterns = []

            try:
                caps: List[str] = json.loads(agent.capabilities) if agent.capabilities else []
            except (json.JSONDecodeError, TypeError):
                caps = []

            # Score: issue type affinity
            if issue_type and affinity:
                if issue_type.upper() in [a.upper() for a in affinity]:
                    score += 20

            # Score: file pattern matching
            if file_patterns and patterns:
                for fp in file_patterns:
                    for pat in patterns:
                        if _glob_match(fp, pat):
                            score += 10
                            break  # one match per file pattern is enough

            # Score: project type in capabilities
            if project_type and caps:
                if project_type.lower() in [c.lower() for c in caps]:
                    score += 15

            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent

    # ------------------------------------------------------------------
    # Directory scanning
    # ------------------------------------------------------------------

    async def scan_agents_directory(
        self,
        db: AsyncSession,
        directory: Optional[str] = None,
    ) -> List[AgentProfile]:
        """Scan a directory for agent folders (each containing an AGENT.md) and
        auto-register them in the database.

        Returns the list of agents that were created or updated.
        """
        if directory is None:
            directory = os.path.expanduser("~/.claude/agents")

        agents_dir = Path(directory)
        if not agents_dir.is_dir():
            logger.warning(f"Agents directory does not exist: {agents_dir}")
            return []

        registered: List[AgentProfile] = []

        for entry in sorted(agents_dir.iterdir()):
            if not entry.is_dir():
                continue

            agent_md = entry / "AGENT.md"
            if not agent_md.is_file():
                continue

            agent_name = entry.name
            try:
                content = agent_md.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not read {agent_md}: {e}")
                continue

            frontmatter = _parse_agent_frontmatter(content)

            # Build registration data from frontmatter + defaults
            data: Dict[str, Any] = {
                "name": frontmatter.get("name", agent_name),
                "displayName": _name_to_display_name(frontmatter.get("name", agent_name)),
                "description": frontmatter.get("description", ""),
                "agentPath": str(agent_md),
                "capabilities": DEFAULT_CAPABILITIES.get(agent_name, []),
                "issueTypeAffinity": DEFAULT_ISSUE_TYPE_AFFINITY.get(agent_name, ["TASK", "STORY", "BUG"]),
                "projectPatterns": DEFAULT_PROJECT_PATTERNS.get(agent_name, []),
                "isActive": True,
                "priority": 50,
            }

            agent = await self.register_agent(db, data)
            registered.append(agent)
            logger.info(f"Registered agent: {agent.name} ({agent.displayName})")

        return registered


# ------------------------------------------------------------------
# Helper: simple glob-style matching
# ------------------------------------------------------------------

def _glob_match(filepath: str, pattern: str) -> bool:
    """Check if *filepath* matches a simplified glob *pattern*.

    Supports:
      - ``*`` matches any sequence of non-``/`` characters
      - ``**`` matches any sequence of characters including ``/``
      - ``?`` matches exactly one non-``/`` character

    This is intentionally lightweight so we avoid importing ``fnmatch``
    or ``pathlib.PurePath.match`` which have slightly different semantics.
    """
    # Escape regex special chars except our glob tokens
    regex = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # ** — match anything including /
                regex += ".*"
                i += 2
                # Skip optional trailing /
                if i < len(pattern) and pattern[i] == "/":
                    i += 1
                continue
            else:
                regex += "[^/]*"
        elif c == "?":
            regex += "[^/]"
        elif c in r"\.+^${}()|[]":
            regex += "\\" + c
        else:
            regex += c
        i += 1

    return bool(re.fullmatch(regex, filepath))


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

agent_registry_service = AgentRegistryService()
