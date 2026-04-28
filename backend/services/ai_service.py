"""
AI Service - Multi-provider AI support (Ollama local, Claude API fallback)
"""

import asyncio
import httpx
import logging
import re
from anthropic import Anthropic
from typing import List, Optional, Dict, Any
import json

from app.config import settings
from services.rag_service import RAGService

logger = logging.getLogger(__name__)


class AIService:
    """Service for AI-powered issue management using Ollama (local) or Claude (API)"""

    def __init__(self):
        self._anthropic_client = None
        self._ollama_available = None
        self._ollama_model = "llama3"  # Default Ollama model

    @property
    def anthropic_client(self):
        """Lazy initialization of Anthropic client"""
        if self._anthropic_client is None and settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY != "your-api-key-here":
            self._anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic_client

    def set_api_key(self, api_key: str):
        """Update the Anthropic API key at runtime and reinitialize the client."""
        settings.ANTHROPIC_API_KEY = api_key
        if api_key and api_key != "your-api-key-here":
            self._anthropic_client = Anthropic(api_key=api_key)
        else:
            self._anthropic_client = None

    def get_masked_api_key(self) -> str:
        """Return the API key masked for display (show first 10 and last 4 chars)."""
        key = settings.ANTHROPIC_API_KEY
        if not key or key == "your-api-key-here":
            return ""
        if len(key) <= 14:
            return key[:4] + "..." + key[-4:]
        return key[:10] + "..." + key[-4:]

    async def get_ollama_models(self) -> list:
        """Fetch available models from Ollama."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags", timeout=3.0)
            if response.status_code == 200:
                data = response.json()
                return [
                    {
                        "name": m.get("name", ""),
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at", ""),
                    }
                    for m in data.get("models", [])
                ]
        except Exception:
            pass
        return []

    def set_ollama_model(self, model: str):
        """Set the preferred Ollama model."""
        self._ollama_model = model
        logger.info(f"Ollama model set to: {model}")

    def get_ollama_model(self) -> str:
        """Get the current Ollama model name."""
        return self._ollama_model

    async def is_ollama_available(self) -> bool:
        """Check if Ollama is running (without caching)."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False

    async def _check_ollama(self) -> bool:
        """Check if Ollama is running locally"""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags", timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                # Get full model names (including tags like :1b, :7b, etc.)
                models = [m.get("name", "") for m in data.get("models", [])]

                # Prefer larger models first (3b, 7b, 8b, etc.) over smaller ones (1b)
                # Sort by preferring larger parameter counts
                def model_priority(name: str) -> int:
                    """Higher number = better. Prefer larger models."""
                    # Extract size from model name (e.g., "llama3.2:3b" -> 3)
                    match = re.search(r':(\d+)b', name)
                    if match:
                        return int(match.group(1))
                    # Default size if not specified
                    return 7  # Assume 7b if no size tag

                # Check for preferred models (with any tag), preferring larger sizes
                preferred = ["llama3.2", "llama3", "mistral", "codellama", "deepseek-coder"]
                for pref in preferred:
                    matching = [m for m in models if m.startswith(pref)]
                    if matching:
                        # Pick the largest matching model
                        best = max(matching, key=model_priority)
                        self._ollama_model = best
                        self._ollama_available = True
                        logger.info(f"Ollama available with model: {self._ollama_model}")
                        return True
                # Use first available model if any
                if models:
                    self._ollama_model = models[0]
                    self._ollama_available = True
                    logger.info(f"Ollama available with model: {self._ollama_model}")
                    return True
            self._ollama_available = False
            return False
        except (httpx.ConnectError, httpx.TimeoutException):
            self._ollama_available = False
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking Ollama: {e}")
            self._ollama_available = False
            return False

    async def is_available(self) -> bool:
        """Check if any AI service is available (Ollama or Claude)"""
        return await self._check_ollama() or self.anthropic_client is not None

    async def get_provider(self) -> str:
        """Get current AI provider"""
        if await self._check_ollama():
            return f"ollama/{self._ollama_model}"
        elif self.anthropic_client:
            return "claude-sonnet-4-6"
        return "none"

    async def _call_ollama(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """Call Ollama API using chat endpoint for better instruction following"""
        logger.info(f"Calling Ollama with model: {self._ollama_model}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": self._ollama_model,
                        "messages": [
                            {"role": "system", "content": "You are a JSON generator. Output ONLY valid JSON, no explanations."},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "options": {
                            "num_predict": max_tokens,
                            "temperature": 0.3,
                        }
                    },
                    timeout=120.0
                )
                if response.status_code == 200:
                    data = response.json()
                    result = data.get("message", {}).get("content", "").strip()
                    logger.info(f"Ollama returned {len(result)} chars")
                    return result
                else:
                    logger.error(f"Ollama error response ({response.status_code}): {response.text[:200]}")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(f"Ollama connection failed: {e}")
        except Exception as e:
            logger.error(f"Ollama unexpected error: {e}", exc_info=True)
        return None

    async def _call_claude(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """Call Claude API (offloaded to thread to avoid blocking the event loop)."""
        if not self.anthropic_client:
            return None
        try:
            client = self.anthropic_client
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude API error: {e}", exc_info=True)
        return None

    async def _generate(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """Generate response using available AI (Ollama first, then Claude)"""
        logger.debug(f"_generate called, prompt length: {len(prompt)}")

        # Try Ollama first (local, free)
        if await self._check_ollama():
            logger.info("Trying Ollama...")
            result = await self._call_ollama(prompt, max_tokens)
            if result:
                return result
            logger.warning("Ollama returned empty result")

        # Fallback to Claude API
        logger.info("Falling back to Claude API...")
        return await self._call_claude(prompt, max_tokens)

    def _parse_text_tasks(self, content: str) -> List[Dict]:
        """Parse tasks from text/markdown format when JSON fails"""
        tasks = []
        current_task = {}

        # Field mappings (lowercase key -> output key)
        field_map = {
            'title': 'title',
            'task title': 'title',
            'task': 'title',  # Handle "**Task**: Title" format
            'type': 'type',
            'priority': 'priority',
            'description': 'description',
            'storypoints': 'storyPoints',
            'story points': 'storyPoints',
        }

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue

            # New task marker: "1. **Task**: Title" or "### Task 1" etc.
            # Check if this line starts a new task AND contains the title
            # Handles: "1. **Task**: Title", "1. Task: Title", "### Task 1"
            new_task_match = re.match(r'^(\d+\.|###?\s*)\s*\*?\*?[Tt]ask\*?\*?\s*[:.]?\s*(.+)?$', line)
            if new_task_match:
                if current_task.get('title'):
                    tasks.append(current_task)
                current_task = {'type': 'TASK', 'priority': 'MEDIUM'}
                # If title is on same line, capture it
                title_part = new_task_match.group(2)
                if title_part:
                    current_task['title'] = title_part.strip().strip('*').strip()
                continue

            # Alternative new task marker without title on same line
            if re.match(r'^(###?\s*Task\s*\d*|\*\*Task\s*\d*\*\*|[-*]\s*Task\s*\d*)$', line, re.IGNORECASE):
                if current_task.get('title'):
                    tasks.append(current_task)
                current_task = {'type': 'TASK', 'priority': 'MEDIUM'}
                continue

            # Try to parse "Key: Value" or "**Key**: Value" format (handles markdown bold)
            match = re.match(r'^[-*]?\s*\*?\*?(\w+(?:\s+\w+)?)\*?\*?\s*[:=]\s*(.+)$', line)
            if match:
                key = match.group(1).lower()
                value = match.group(2).strip().strip('"\'').strip('*')

                if key in field_map:
                    out_key = field_map[key]
                    if out_key == 'storyPoints':
                        try:
                            current_task[out_key] = int(re.search(r'\d+', value).group())
                        except (ValueError, AttributeError):
                            current_task[out_key] = 3
                    elif out_key == 'title':
                        # Only set title if not already set from task marker line
                        if not current_task.get('title'):
                            current_task[out_key] = value
                    else:
                        current_task[out_key] = value

        # Don't forget last task
        if current_task.get('title'):
            tasks.append(current_task)

        if tasks:
            logger.info(f"Parsed {len(tasks)} tasks from text format")
        return tasks

    def _extract_json_array(self, content: str) -> List[Dict]:
        """Extract JSON array from response"""
        content = content.strip()
        logger.debug(f"Extracting JSON array from: {content[:200]}...")

        # Remove markdown code blocks if present
        if "```" in content:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if match:
                content = match.group(1).strip()
                logger.debug(f"Extracted from code block: {content[:200]}...")

        # Try to complete partial JSON (model may continue from prompt)
        if content.startswith("{"):
            # Model continued from our prompt, add the opening bracket
            content = "[" + content
            logger.debug("Added opening bracket to partial JSON")

        # Ensure array is closed
        if content.startswith("[") and not content.rstrip().endswith("]"):
            # Try to close the array
            content = content.rstrip().rstrip(",") + "]"
            logger.debug("Closed JSON array")

        if content.startswith("["):
            try:
                result = json.loads(content)
                logger.info(f"Parsed JSON array with {len(result)} items")
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error: {e}")
                # Try to fix common issues
                try:
                    # Remove trailing incomplete object
                    last_complete = content.rfind("},")
                    if last_complete > 0:
                        fixed = content[:last_complete+1] + "]"
                        result = json.loads(fixed)
                        logger.info(f"Fixed partial JSON and parsed {len(result)} items")
                        return result
                except (json.JSONDecodeError, ValueError):
                    pass

        # Try to find JSON array in response
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            try:
                result = json.loads(content[start:end])
                logger.info(f"Extracted JSON array with {len(result)} items")
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"JSON extraction error: {e}")

        # Fallback: try to parse text/markdown format
        logger.debug("Trying text format parser...")
        text_result = self._parse_text_tasks(content)
        if text_result:
            return text_result

        logger.warning("No valid tasks found in AI response")
        return []

    def _extract_json_object(self, content: str) -> Dict:
        """Extract JSON object from response"""
        content = content.strip()

        # Remove markdown code blocks if present
        if "```" in content:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if match:
                content = match.group(1).strip()

        if content.startswith("{"):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
        return {}

    async def breakdown_feature(
        self,
        project_id: str,
        title: str,
        description: Optional[str] = None,
        parent_type: str = "EPIC",
        rag: Optional["RAGService"] = None,
    ) -> List[Dict[str, Any]]:
        """
        Break down a feature/epic into smaller issues.
        Returns a list of suggested child issues.

        Args:
            project_id: The project identifier.
            title: Feature title.
            description: Optional feature description.
            parent_type: The parent issue type.
            rag: RAGService instance for context retrieval.
        """
        if not await self.is_available():
            return []

        # Get context from existing issues
        context = await rag.get_context_for_ai(
            project_id, f"{title} {description or ''}"
        ) if rag else ""

        # Determine if this is a detailed specification or a brief description
        has_detailed_spec = description and len(description) > 200

        if has_detailed_spec:
            # Detailed specification - create HIERARCHICAL breakdown with FEATURE at top
            prompt = f"""Break down this feature into a complete implementation hierarchy.

=== FEATURE TO BREAK DOWN ===
Title: {title}

Specifications:
{description}
=== END ===

Generate a JSON array with these item types in hierarchy order:
1. FEATURE (1 item) - the top-level container
2. EPIC (2-4 items) - major work areas (e.g., "Epic: Backend API", "Epic: Frontend UI")
3. STORY (2-3 per epic) - user capabilities with SPECIFIC descriptions (e.g., "User can filter results by date range")
4. TASK (1-2 per story) - implementation work (e.g., "Create DateRangePicker component")
5. SUBTASK (1-2 per task) - detailed steps (e.g., "Add calendar popup with date selection")

IMPORTANT: Generate SPECIFIC, MEANINGFUL titles and descriptions based on "{title}".
DO NOT use generic placeholders like "User story" or "Implementation task".

JSON FORMAT (this shows structure only - generate real content):
[
  {{"title": "<feature name>", "type": "FEATURE", "priority": "HIGH", "description": "<what this feature does>", "storyPoints": 21, "parentTitle": null, "category": "integration"}},
  {{"title": "Epic: <area name>", "type": "EPIC", "priority": "HIGH", "description": "<epic scope>", "storyPoints": 13, "parentTitle": "<feature title>", "category": "frontend"}},
  {{"title": "User can <specific action>", "type": "STORY", "priority": "HIGH", "description": "<detailed user capability>", "storyPoints": 5, "parentTitle": "<epic title>", "category": "frontend"}},
  {{"title": "<specific implementation>", "type": "TASK", "priority": "HIGH", "description": "<what to build>", "storyPoints": 3, "parentTitle": "<story title>", "category": "frontend"}},
  {{"title": "<specific subtask>", "type": "SUBTASK", "priority": "MEDIUM", "description": "<detail>", "storyPoints": 1, "parentTitle": "<task title>", "category": "frontend"}}
]

RULES:
- parentTitle links child to parent (null only for FEATURE)
- category: frontend, backend, database, security, or testing
- Generate 25-50 items with REAL, SPECIFIC content derived from the specifications
- Every title must be unique and descriptive

Return ONLY the JSON array."""
        else:
            # Brief description - generate full hierarchy with FEATURE at top
            prompt = f"""Break down this feature into implementation items.

Feature: {title}
{f"Description: {description}" if description else ""}

Generate a JSON array with this hierarchy:
1. FEATURE (1) - top level: "{title}"
2. EPIC (1-2) - major work areas
3. STORY (1-2 per epic) - what users can do (be SPECIFIC, e.g., "User can upload CSV files")
4. TASK (2-3 per story) - implementation steps (e.g., "Create file upload component")
5. SUBTASK (1-2 per task) - detailed work

IMPORTANT: Generate SPECIFIC titles based on "{title}".
DO NOT use generic text like "User story" or "Implementation task".

JSON FORMAT (generate real content, not this placeholder text):
[
  {{"title": "{title[:50]}", "type": "FEATURE", "priority": "HIGH", "description": "<describe the feature>", "storyPoints": 13, "parentTitle": null, "category": "frontend"}},
  {{"title": "Epic: <specific area>", "type": "EPIC", "priority": "HIGH", "description": "<epic description>", "storyPoints": 8, "parentTitle": "{title[:50]}", "category": "frontend"}},
  {{"title": "User can <specific action for {title[:20]}>", "type": "STORY", "priority": "HIGH", "description": "<what user achieves>", "storyPoints": 5, "parentTitle": "<epic title>", "category": "frontend"}},
  {{"title": "<specific task for {title[:20]}>", "type": "TASK", "priority": "HIGH", "description": "<implementation detail>", "storyPoints": 3, "parentTitle": "<story title>", "category": "frontend"}},
  {{"title": "<specific subtask>", "type": "SUBTASK", "priority": "MEDIUM", "description": "<detail>", "storyPoints": 1, "parentTitle": "<task title>", "category": "frontend"}}
]

RULES:
- parentTitle links to parent (null only for FEATURE)
- category: frontend, backend, database, security, or testing
- Generate 10-20 items with SPECIFIC, UNIQUE titles

Return ONLY the JSON array."""

        try:
            # Use more tokens for detailed specs
            max_tokens = 8000 if has_detailed_spec else 4000
            content = await self._generate(prompt, max_tokens=max_tokens)
            if content:
                return self._extract_json_array(content)
            return []
        except Exception as e:
            logger.error(f"Error in feature breakdown: {e}", exc_info=True)
            return []

    async def suggest_status_update(
        self,
        issue_title: str,
        current_status: str,
        commit_message: Optional[str] = None,
        pr_title: Optional[str] = None,
    ) -> Optional[str]:
        """
        Suggest a status update based on git activity.
        Returns suggested new status or None.
        """
        if not await self.is_available():
            return None

        activity = []
        if commit_message:
            activity.append(f"Commit: {commit_message}")
        if pr_title:
            activity.append(f"PR: {pr_title}")

        if not activity:
            return None

        prompt = f"""Based on the git activity, suggest if the issue status should be updated.

Issue: {issue_title}
Current Status: {current_status}
Activity: {chr(10).join(activity)}

Possible statuses: BACKLOG, TODO, IN_PROGRESS, IN_REVIEW, DONE

If the activity suggests a status change, return ONLY the new status (e.g., "IN_PROGRESS").
If no change is needed, return "NO_CHANGE".

Common patterns:
- Commits with "WIP", "start", "begin" → IN_PROGRESS
- Commits with "fix", "implement", "add" while IN_PROGRESS → stay IN_PROGRESS
- PR opened → IN_REVIEW
- PR merged, "complete", "finish", "done" → DONE"""

        try:
            content = await self._generate(prompt, max_tokens=50)
            if content:
                suggestion = content.strip().upper()
                valid_statuses = ["BACKLOG", "TODO", "IN_PROGRESS", "IN_REVIEW", "DONE"]
                if suggestion in valid_statuses:
                    return suggestion
            return None
        except Exception as e:
            logger.error(f"Error suggesting status: {e}", exc_info=True)
            return None

    async def detect_potential_bug(
        self,
        title: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze if the issue description indicates a bug.
        Returns bug analysis with severity.
        """
        if not await self.is_available():
            return {"is_bug": False}

        prompt = f"""Analyze if this issue describes a bug or defect.

Title: {title}
{f"Description: {description}" if description else ""}

Return a JSON object with:
- is_bug: boolean - true if this describes a bug
- confidence: number 0-1 - how confident you are
- severity: LOW, MEDIUM, HIGH, or CRITICAL (if is_bug is true)
- reason: brief explanation

Return ONLY the JSON object, no other text."""

        try:
            content = await self._generate(prompt, max_tokens=200)
            if content:
                result = self._extract_json_object(content)
                if result:
                    return result
            return {"is_bug": False}
        except Exception as e:
            logger.error(f"Error detecting bug: {e}", exc_info=True)
            return {"is_bug": False}

    async def generate_qa_tasks(
        self,
        project_id: str,
        feature_title: str,
        feature_description: Optional[str] = None,
        rag: Optional["RAGService"] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate QA/testing tasks for a feature.

        Args:
            project_id: The project identifier.
            feature_title: Feature title.
            feature_description: Optional feature description.
            rag: RAGService instance for context retrieval.
        """
        if not await self.is_available():
            return []

        context = await rag.get_context_for_ai(
            project_id, f"QA testing {feature_title}"
        ) if rag else ""

        prompt = f"""Generate QA/testing tasks for this feature.

Feature: {feature_title}
{f"Description: {feature_description}" if feature_description else ""}

{context}

Generate 3-5 testing tasks. For each task provide:
- title: Clear test case title
- type: TASK
- priority: MEDIUM or HIGH
- description: What to test and expected behavior
- storyPoints: 1 or 2

Return ONLY a JSON array of tasks, no other text."""

        try:
            content = await self._generate(prompt, max_tokens=1000)
            if content:
                return self._extract_json_array(content)
            return []
        except Exception as e:
            logger.error(f"Error generating QA tasks: {e}", exc_info=True)
            return []

    async def hierarchical_breakdown_feature(
        self,
        project_id: str,
        feature_title: str,
        feature_description: str,
        rag: Optional["RAGService"] = None,
    ) -> Dict[str, Any]:
        """
        Break down a feature into a hierarchical structure:
        Epic -> Stories -> Tasks -> Subtasks

        Returns a dictionary with:
        - epic: dict with title, description
        - stories: list of stories, each with tasks and subtasks

        Args:
            project_id: The project identifier.
            feature_title: Feature title.
            feature_description: Feature description.
            rag: RAGService instance for context retrieval.
        """
        if not await self.is_available():
            raise ValueError("AI service is not available")

        # Get context from existing issues
        context = await rag.get_context_for_ai(
            project_id, f"{feature_title} {feature_description}"
        ) if rag else ""

        prompt = f"""Break down this feature into a hierarchical structure for project management.

Feature: {feature_title}
Description: {feature_description}

{context if context else ""}

Create a breakdown with:
1. One Epic (the main feature)
2. 2-4 Stories (user-facing capabilities - be SPECIFIC about what users can do)
3. For each Story, 2-4 Tasks (implementation work - describe actual code/components)
4. For each Task, 1-3 Subtasks (specific actions)

IMPORTANT: Generate SPECIFIC, MEANINGFUL titles and descriptions based on "{feature_title}".
DO NOT use generic placeholders - every item must relate to this specific feature.

Return a JSON object with this structure (replace placeholders with real content):
{{
  "epic": {{
    "title": "<specific epic name for {feature_title[:30]}>",
    "description": "<what this epic delivers>",
    "estimate_hours": 40
  }},
  "stories": [
    {{
      "title": "User can <specific capability>",
      "description": "<detailed description of user value>",
      "priority": "HIGH",
      "storyPoints": 8,
      "tasks": [
        {{
          "title": "<specific implementation task>",
          "description": "<what to build and how>",
          "priority": "MEDIUM",
          "estimate_hours": 4,
          "subtasks": ["<specific step 1>", "<specific step 2>"]
        }}
      ]
    }}
  ]
}}

Priorities: LOW, MEDIUM, HIGH, CRITICAL
Story points: 1, 2, 3, 5, 8, 13
Estimate hours should be realistic.

Return ONLY the JSON object, no other text."""

        try:
            content = await self._generate(prompt, max_tokens=3000)
            if content:
                result = self._extract_json_object(content)
                if result:
                    return result
            # Return empty structure if parsing fails
            return {
                "epic": {
                    "title": feature_title,
                    "description": feature_description,
                    "estimate_hours": 40
                },
                "stories": []
            }
        except Exception as e:
            logger.error(f"Error in hierarchical breakdown: {e}", exc_info=True)
            raise ValueError(f"Failed to generate breakdown: {e}")


# Singleton instance
ai_service = AIService()
