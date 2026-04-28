"""
Skill Registry Service - Manages skill profiles discovered from SKILL.md files.

Scans two source roots:
  1. Standalone skills  — ~/.claude/skills/*/SKILL.md
  2. Plugin-bundled     — ~/.claude/plugins/cache/<plugin>/.../skills/*/SKILL.md

Plugin skills are labelled source="plugin:<plugin-name>" where <plugin-name> is
the directory directly under cache/ (e.g. "claude-plugins-official").
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.skill_registry import SkillProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from a SKILL.md file.

    Expects the file to begin with a fenced YAML block::

        ---
        name: skill-name
        description: "What this skill does"
        context: fork        # optional — triggers contextFork=True
        agent: atlas-indexer # optional agent reference
        capabilities:
          - python
          - fastapi
        ---

    Returns an empty dict if no valid frontmatter is found.
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}

    # Collect lines between the two "---" delimiters
    fm_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm_lines.append(line)

    if not fm_lines:
        return {}

    try:
        parsed = yaml.safe_load("\n".join(fm_lines)) or {}
        return parsed if isinstance(parsed, dict) else {}
    except yaml.YAMLError as exc:
        logger.warning("YAML parse error in frontmatter: %s", exc)
        return {}


def _name_to_display_name(name: str) -> str:
    """Convert kebab-case skill name to a human-readable display name.

    Example: ``'skill-creator'`` → ``'Skill Creator'``
    """
    return " ".join(word.capitalize() for word in name.split("-"))


def _build_skill_data(
    frontmatter: Dict[str, Any],
    skill_name: str,
    skill_path: str,
    source: str,
) -> Dict[str, Any]:
    """Build a dict of skill attributes from parsed frontmatter and path metadata."""
    raw_capabilities = frontmatter.get("capabilities")
    if isinstance(raw_capabilities, str):
        # Allow a single comma-separated string as fallback
        capabilities: Optional[List[str]] = [c.strip() for c in raw_capabilities.split(",") if c.strip()]
    elif isinstance(raw_capabilities, list):
        capabilities = [str(c) for c in raw_capabilities]
    else:
        capabilities = None

    context_value = str(frontmatter.get("context", "")).strip().lower()

    return {
        "name": str(frontmatter.get("name", skill_name)).strip(),
        "displayName": _name_to_display_name(str(frontmatter.get("name", skill_name)).strip()),
        "description": str(frontmatter.get("description", "")).strip() or None,
        "skillPath": skill_path,
        "capabilities": capabilities,
        "contextFork": context_value == "fork",
        "agentRef": str(frontmatter.get("agent", "")).strip() or None,
        "source": source,
        "isActive": True,
        "priority": int(frontmatter.get("priority", 50)),
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SkillRegistryService:
    """Service for managing the skill registry."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def get_all_skills(
        self,
        db: AsyncSession,
        *,
        active_only: bool = False,
    ) -> List[SkillProfile]:
        """Return all registered skills, optionally filtered to active-only."""
        stmt = select(SkillProfile).order_by(
            SkillProfile.priority.desc(), SkillProfile.name
        )
        if active_only:
            stmt = stmt.where(SkillProfile.isActive == True)  # noqa: E712
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_skill(
        self,
        db: AsyncSession,
        skill_id: str,
    ) -> Optional[SkillProfile]:
        """Get a single skill by primary-key ID."""
        result = await db.execute(
            select(SkillProfile).where(SkillProfile.id == skill_id)
        )
        return result.scalar_one_or_none()

    async def get_skill_by_name(
        self,
        db: AsyncSession,
        name: str,
    ) -> Optional[SkillProfile]:
        """Get a single skill by unique name."""
        result = await db.execute(
            select(SkillProfile).where(SkillProfile.name == name)
        )
        return result.scalar_one_or_none()

    async def register_skill(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
    ) -> SkillProfile:
        """Create or update a skill profile.

        If a skill with the same *name* already exists it is updated in-place
        (upsert by name).  Otherwise a new record is created.
        """
        name = data.get("name", "")
        existing = await self.get_skill_by_name(db, name)

        if existing:
            for key, value in data.items():
                if key == "id":
                    continue  # never overwrite the PK
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await db.commit()
            await db.refresh(existing)
            return existing

        skill = SkillProfile(
            id=str(uuid.uuid4()),
            name=name,
            displayName=data.get("displayName", _name_to_display_name(name)),
            description=data.get("description"),
            skillPath=data.get("skillPath", ""),
            capabilities=data.get("capabilities"),
            contextFork=data.get("contextFork", False),
            agentRef=data.get("agentRef"),
            source=data.get("source", "standalone"),
            isActive=data.get("isActive", True),
            priority=data.get("priority", 50),
        )
        db.add(skill)
        await db.commit()
        await db.refresh(skill)
        return skill

    async def delete_skill(
        self,
        db: AsyncSession,
        skill_id: str,
    ) -> bool:
        """Soft-delete a skill by setting isActive=False."""
        result = await db.execute(
            update(SkillProfile)
            .where(SkillProfile.id == skill_id)
            .values(isActive=False)
        )
        await db.commit()
        return result.rowcount > 0

    async def toggle_skill(
        self,
        db: AsyncSession,
        skill_id: str,
    ) -> Optional[SkillProfile]:
        """Toggle a skill's isActive flag.  Returns the updated record or None."""
        skill = await self.get_skill(db, skill_id)
        if not skill:
            return None
        skill.isActive = not skill.isActive
        await db.commit()
        await db.refresh(skill)
        return skill

    # ------------------------------------------------------------------
    # Directory scanning
    # ------------------------------------------------------------------

    async def scan_skills_directory(self, db: AsyncSession) -> List[SkillProfile]:
        """Walk known skill roots and upsert all discovered SKILL.md files.

        Source roots (in order):
          1. ``~/.claude/skills/*/SKILL.md``                              → source="standalone"
          2. ``~/.claude/plugins/cache/<plugin>/*/skills/*/SKILL.md``    → source="plugin:<plugin>"
          3. ``~/.claude/plugins/cache/<plugin>/<version>/skills/*/SKILL.md``
             (versioned sub-directories, e.g. ``1.0.0/``)

        Returns the list of SkillProfile records that were created or updated.
        """
        registered: List[SkillProfile] = []

        # --- 1. Standalone skills ---
        standalone_root = Path(os.path.expanduser("~/.claude/skills"))
        registered.extend(
            await self._scan_skills_root(db, standalone_root, source="standalone")
        )

        # --- 2. Plugin-bundled skills (any depth under cache) ---
        # Real layouts seen in the wild:
        #   cache/<marketplace>/<plugin>/<version>/skills/<name>/SKILL.md
        #   cache/<marketplace>/<plugin>/<version>/.claude/skills/<name>/SKILL.md
        #   cache/<marketplace>/<plugin>/<version>/claude-plugin/<plugin>/skills/<name>/SKILL.md
        #   cache/<plugin>/<plugin>/SKILL.md (e.g. caveman, candlekeep)
        # Strategy: rglob every SKILL.md and derive source from the FIRST path
        # segment under cache/ (the marketplace or plugin pack).
        plugins_cache = Path(os.path.expanduser("~/.claude/plugins/cache"))
        if plugins_cache.is_dir():
            seen_paths: set = set()
            for skill_md in plugins_cache.rglob("SKILL.md"):
                # Skip duplicates that might appear via symlinks
                resolved = skill_md.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)

                try:
                    # Defense-in-depth: skill_md must be within plugins_cache
                    # even after resolving symlinks (catches malicious link-out)
                    if not resolved.is_relative_to(plugins_cache.resolve()):
                        logger.warning("Skipping symlink escape: %s -> %s", skill_md, resolved)
                        continue
                    rel = skill_md.relative_to(plugins_cache)
                    plugin_name = rel.parts[0] if rel.parts else "unknown"
                    if plugin_name.startswith("_"):
                        continue
                    source = f"plugin:{plugin_name}"
                except (ValueError, OSError):
                    continue

                skill = await self._register_skill_from_file(db, skill_md, source=source)
                if skill:
                    registered.append(skill)

        logger.info("scan_skills_directory: registered/updated %d skill(s)", len(registered))
        return registered

    async def _scan_skills_root(
        self,
        db: AsyncSession,
        skills_root: Path,
        source: str,
    ) -> List[SkillProfile]:
        """Scan a single skills directory (skills_root/<name>/SKILL.md) and upsert each one."""
        if not skills_root.is_dir():
            logger.debug("Skills root does not exist, skipping: %s", skills_root)
            return []

        registered: List[SkillProfile] = []
        for entry in sorted(skills_root.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            skill = await self._register_skill_from_file(db, skill_md, source=source)
            if skill:
                registered.append(skill)
        return registered

    async def _register_skill_from_file(
        self,
        db: AsyncSession,
        skill_md: Path,
        source: str,
    ) -> Optional[SkillProfile]:
        """Register one SKILL.md file. Skill name comes from frontmatter or parent dir."""
        try:
            content = skill_md.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not read %s: %s", skill_md, exc)
            return None

        frontmatter = _parse_skill_frontmatter(content)
        skill_folder_name = skill_md.parent.name
        data = _build_skill_data(
            frontmatter=frontmatter,
            skill_name=skill_folder_name,
            skill_path=str(skill_md),
            source=source,
        )

        try:
            skill = await self.register_skill(db, data)
            logger.info(
                "Registered skill: %s (%s) from %s",
                skill.name,
                skill.source,
                skill.skillPath,
            )
            return skill
        except Exception as exc:
            logger.warning("Failed to register skill at %s: %s", skill_md, exc)
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

skill_registry_service = SkillRegistryService()
