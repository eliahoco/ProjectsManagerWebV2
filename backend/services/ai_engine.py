"""AI Engine for automated task management."""

import anthropic
from typing import Dict, Any, List
import json

from typing import Optional

from app.config import settings
from services.prompts.breakdown import BREAKDOWN_SYSTEM_PROMPT, BREAKDOWN_USER_PROMPT
from services.rag_service import RAGService


class AIEngine:
    """AI-powered features for CodeBoard."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None and settings.ANTHROPIC_API_KEY:
            self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def breakdown_feature(
        self,
        project_id: str,
        feature_title: str,
        feature_description: str,
        rag: Optional[RAGService] = None,
    ) -> Dict[str, Any]:
        """
        Break down a feature description into epics, stories, tasks, and subtasks.

        Uses project context from RAG for better understanding.

        Args:
            project_id: The project identifier.
            feature_title: Feature title.
            feature_description: Feature description.
            rag: RAGService instance for context retrieval.
        """
        if not self.client:
            raise ValueError("Anthropic API key not configured")

        # Get project context from RAG
        project_context = await rag.get_context_for_ai(
            project_id=project_id,
            query=feature_title,
            n_results=5,
        ) if rag else "No additional context available."

        # Build prompt
        user_prompt = BREAKDOWN_USER_PROMPT.format(
            feature_title=feature_title,
            feature_description=feature_description,
            project_context=project_context or "No additional context available."
        )

        # Call Claude
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=BREAKDOWN_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Parse response
        response_text = message.content[0].text

        # Extract JSON from response
        try:
            # Find JSON in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start == -1 or json_end <= json_start:
                raise ValueError("No JSON object found in response")
            json_str = response_text[json_start:json_end]
            breakdown = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Failed to parse AI response: {e}")

        return breakdown

    async def generate_qa_tasks(
        self,
        story_id: str,
        story_title: str,
        story_description: str,
        completed_tasks: List[str]
    ) -> List[Dict[str, str]]:
        """Generate QA tasks for a completed story."""
        if not self.client:
            raise ValueError("Anthropic API key not configured")

        prompt = f"""Generate QA test tasks for this completed story:

Story: {story_title}
Description: {story_description}

Completed Tasks:
{chr(10).join(f'- {t}' for t in completed_tasks)}

Generate 3-5 QA tasks covering:
1. Happy path testing
2. Edge cases
3. Error handling
4. Performance (if applicable)
5. Accessibility (if UI)

Output JSON array:
[{{"title": "...", "description": "...", "type": "QA"}}]
"""

        message = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text
        json_start = response_text.find('[')
        json_end = response_text.rfind(']') + 1
        if json_start == -1 or json_end <= json_start:
            return []
        return json.loads(response_text[json_start:json_end])


ai_engine = AIEngine()
