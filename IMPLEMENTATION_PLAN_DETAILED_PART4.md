# ProjectsManagerWebV2 - Detailed Implementation Plan (Part 4)

# EPIC 4: RAG Integration

**ID:** E4
**Priority:** Medium
**Status:** BACKLOG
**Description:** Integrate ChromaDB for vector storage and implement semantic search across issues and project context. This enables intelligent search and provides context for AI features.

---

## Story 4.1: ChromaDB Setup

### Task T4.1.1: Configure ChromaDB in docker-compose

**Description:** Add ChromaDB service to docker-compose with persistent storage on port 8501.

**docker-compose.yml addition:**
```yaml
chromadb:
  image: chromadb/chroma:latest
  container_name: pmwv2-chromadb
  ports:
    - "8501:8000"
  environment:
    - IS_PERSISTENT=TRUE
    - PERSIST_DIRECTORY=/chroma/chroma
    - ANONYMIZED_TELEMETRY=FALSE
  volumes:
    - chroma-data:/chroma/chroma
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
    interval: 30s
    timeout: 10s
    retries: 3
  networks:
    - pmwv2-network
```

**Acceptance Criteria:**
- [ ] ChromaDB starts on port 8501
- [ ] Data persisted in volume
- [ ] Health check passes

---

### Task T4.1.2: Create RAG Service Class

**File: backend/services/rag.py**
```python
"""RAG service for vector storage and retrieval."""

import chromadb
from chromadb.config import Settings
from typing import List, Optional, Dict, Any
import hashlib

from app.config import settings


class RAGService:
    """Service for managing ChromaDB collections and queries."""

    def __init__(self):
        self.client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False)
        )

    def get_collection(self, project_id: str, collection_type: str = "issues"):
        """Get or create a collection for a project."""
        collection_name = f"{project_id}_{collection_type}"
        # ChromaDB collection names must be 3-63 chars, alphanumeric with underscores
        safe_name = hashlib.md5(collection_name.encode()).hexdigest()[:32]

        return self.client.get_or_create_collection(
            name=safe_name,
            metadata={"project_id": project_id, "type": collection_type}
        )

    def add_document(
        self,
        project_id: str,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any],
        collection_type: str = "issues"
    ):
        """Add or update a document in the collection."""
        collection = self.get_collection(project_id, collection_type)

        # Upsert document
        collection.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[metadata]
        )

    def search(
        self,
        project_id: str,
        query: str,
        n_results: int = 10,
        collection_type: str = "issues",
        where: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar documents."""
        collection = self.get_collection(project_id, collection_type)

        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )

        # Format results
        documents = []
        for i, doc_id in enumerate(results["ids"][0]):
            documents.append({
                "id": doc_id,
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None
            })

        return documents

    def delete_document(self, project_id: str, doc_id: str, collection_type: str = "issues"):
        """Delete a document from the collection."""
        collection = self.get_collection(project_id, collection_type)
        collection.delete(ids=[doc_id])

    def delete_collection(self, project_id: str, collection_type: str = "issues"):
        """Delete an entire collection."""
        collection_name = f"{project_id}_{collection_type}"
        safe_name = hashlib.md5(collection_name.encode()).hexdigest()[:32]
        try:
            self.client.delete_collection(safe_name)
        except Exception:
            pass  # Collection may not exist


# Singleton instance
rag_service = RAGService()
```

**Acceptance Criteria:**
- [ ] Client connects to ChromaDB
- [ ] Collections created per project
- [ ] CRUD operations work
- [ ] Search returns ranked results

---

### Task T4.1.3: Initialize Collections per Project

**Description:** Create collections for different content types: issues, context, decisions.

**Collection Types:**
- `{project}_issues` - Issue titles and descriptions
- `{project}_context` - PROJECT_DESCRIPTOR, README
- `{project}_decisions` - Architectural decisions (future)

---

## Story 4.2: Embedding Service

### Task T4.2.1: Create Embedding Function

**File: backend/services/embedding.py**
```python
"""Embedding service for text vectorization."""

from typing import List
import chromadb.utils.embedding_functions as ef


class EmbeddingService:
    """Service for generating text embeddings."""

    def __init__(self):
        # Use default embedding function (sentence-transformers)
        self.embedding_fn = ef.DefaultEmbeddingFunction()

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        embeddings = self.embedding_fn([text])
        return embeddings[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return self.embedding_fn(texts)

    def prepare_issue_content(self, issue) -> str:
        """Prepare issue content for embedding."""
        parts = [
            f"[{issue.type}] {issue.key}: {issue.title}",
        ]
        if issue.description:
            parts.append(issue.description)
        if issue.labels:
            parts.append(f"Labels: {issue.labels}")
        return "\n".join(parts)


embedding_service = EmbeddingService()
```

---

### Task T4.2.2-4: Auto-embed on Issue Create/Update

**Integration in API endpoints:**
```python
# In issues.py after create/update

from services.rag import rag_service
from services.embedding import embedding_service

async def embed_issue(issue: Issue):
    """Embed issue content for semantic search."""
    content = embedding_service.prepare_issue_content(issue)
    rag_service.add_document(
        project_id=issue.projectId,
        doc_id=issue.id,
        content=content,
        metadata={
            "key": issue.key,
            "type": issue.type,
            "status": issue.status,
            "priority": issue.priority,
        },
        collection_type="issues"
    )
```

---

## Story 4.3: Semantic Search

### Task T4.3.1: Create Search Endpoint

**File: backend/api/search.py**
```python
"""Semantic search API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from services.database import get_db
from services.rag import rag_service
from models.schemas import IssueResponse

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/issues")
async def search_issues(
    project_id: str = Query(..., description="Project ID"),
    query: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    type_filter: Optional[List[str]] = Query(None),
    status_filter: Optional[List[str]] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Semantic search for issues using natural language.

    Uses vector similarity to find relevant issues, even if
    exact keywords don't match.
    """
    # Build filter
    where = {}
    if type_filter:
        where["type"] = {"$in": type_filter}
    if status_filter:
        where["status"] = {"$in": status_filter}

    # Search ChromaDB
    results = rag_service.search(
        project_id=project_id,
        query=query,
        n_results=limit,
        collection_type="issues",
        where=where if where else None
    )

    # Fetch full issue data
    issue_ids = [r["id"] for r in results]
    issues = await db.execute(
        select(Issue).where(Issue.id.in_(issue_ids))
    )

    # Preserve ranking order
    issue_map = {i.id: i for i in issues.scalars().all()}
    ranked_issues = [issue_map[id] for id in issue_ids if id in issue_map]

    return {
        "query": query,
        "results": [
            {
                "issue": IssueResponse(**i.__dict__, commentCount=0, childCount=0),
                "score": next((r["distance"] for r in results if r["id"] == i.id), None)
            }
            for i in ranked_issues
        ]
    }
```

---

### Task T4.3.2-3: Add Search UI to CodeBoard

**File: frontend/components/codeboard/semantic-search.tsx**
```typescript
'use client';

import { useState, useCallback } from 'react';
import { Search, Sparkles } from 'lucide-react';
import { useDebounce } from '@/hooks/use-debounce';
import { Input } from '@/components/ui/input';
import { searchIssues } from '@/lib/api/search';

export function SemanticSearch({ projectId, onSelect }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (debouncedQuery.length >= 2) {
      performSearch(debouncedQuery);
    } else {
      setResults([]);
    }
  }, [debouncedQuery]);

  const performSearch = async (q: string) => {
    setIsSearching(true);
    try {
      const data = await searchIssues(projectId, q);
      setResults(data.results);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="relative">
      <div className="relative">
        <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-purple-500" />
        <Input
          placeholder="AI-powered search..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg z-50 max-h-[300px] overflow-auto">
          {results.map((result) => (
            <div
              key={result.issue.id}
              className="p-3 hover:bg-muted cursor-pointer"
              onClick={() => onSelect(result.issue)}
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-muted-foreground">
                  {result.issue.key}
                </span>
                <span className="text-sm">{result.issue.title}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

# EPIC 5: AI Engine

**ID:** E5
**Priority:** Medium
**Status:** BACKLOG
**Description:** Implement AI-powered features including automatic feature breakdown, status updates, bug detection, and QA task generation.

---

## Story 5.1: Feature Breakdown Agent

### Task T5.1.1: Create Breakdown Prompt Template

**File: backend/services/prompts/breakdown.py**
```python
"""Prompt templates for AI feature breakdown."""

BREAKDOWN_SYSTEM_PROMPT = """You are an expert software architect and project manager.
Your task is to break down feature descriptions into actionable development tasks.

For each feature, create a hierarchical structure:
1. EPIC - The overall feature (if large enough)
2. STORY - User-facing functionality
3. TASK - Specific development work
4. SUBTASK - Detailed implementation steps

Guidelines:
- Each task should be completable in 1-4 hours
- Include clear acceptance criteria
- Consider edge cases and error handling
- Include necessary tests
- Consider UI, API, and database work

Output JSON format:
{
  "epic": {
    "title": "...",
    "description": "..."
  },
  "stories": [
    {
      "title": "...",
      "description": "...",
      "tasks": [
        {
          "title": "...",
          "description": "...",
          "subtasks": ["...", "..."],
          "estimate_hours": 2
        }
      ]
    }
  ]
}
"""

BREAKDOWN_USER_PROMPT = """Break down this feature into development tasks:

Feature: {feature_title}

Description:
{feature_description}

Project Context:
{project_context}

Please provide a comprehensive breakdown with:
- Clear, actionable tasks
- Estimated hours per task
- Subtasks for complex items
- Consider both frontend and backend work
"""
```

---

### Task T5.1.2: Implement Breakdown Service

**File: backend/services/ai_engine.py**
```python
"""AI Engine for automated task management."""

import anthropic
from typing import Dict, Any, List
import json

from app.config import settings
from services.prompts.breakdown import BREAKDOWN_SYSTEM_PROMPT, BREAKDOWN_USER_PROMPT
from services.rag import rag_service


class AIEngine:
    """AI-powered features for CodeBoard."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def breakdown_feature(
        self,
        project_id: str,
        feature_title: str,
        feature_description: str
    ) -> Dict[str, Any]:
        """
        Break down a feature description into epics, stories, tasks, and subtasks.

        Uses project context from RAG for better understanding.
        """
        # Get project context from RAG
        context_docs = rag_service.search(
            project_id=project_id,
            query=feature_title,
            n_results=5,
            collection_type="context"
        )
        project_context = "\n".join([d["content"] for d in context_docs])

        # Build prompt
        user_prompt = BREAKDOWN_USER_PROMPT.format(
            feature_title=feature_title,
            feature_description=feature_description,
            project_context=project_context or "No additional context available."
        )

        # Call Claude
        message = self.client.messages.create(
            model="claude-3-sonnet-20240229",
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
            model="claude-3-haiku-20240307",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text
        json_start = response_text.find('[')
        json_end = response_text.rfind(']') + 1
        return json.loads(response_text[json_start:json_end])


ai_engine = AIEngine()
```

---

### Task T5.1.3: Create /api/ai/breakdown Endpoint

**File: backend/api/ai.py**
```python
"""AI-powered API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional

from services.database import get_db
from services.ai_engine import ai_engine
from models.issue import Issue, IssueType, IssueStatus
from models.schemas import IssueCreate

router = APIRouter(prefix="/ai", tags=["AI"])


class BreakdownRequest(BaseModel):
    """Request body for feature breakdown."""
    project_id: str
    feature_title: str
    feature_description: str
    auto_create: bool = False  # Automatically create issues


class BreakdownResponse(BaseModel):
    """Response from feature breakdown."""
    epic: Optional[dict]
    stories: List[dict]
    total_tasks: int
    estimated_hours: float
    issues_created: List[str] = []


@router.post("/breakdown", response_model=BreakdownResponse)
async def breakdown_feature(
    request: BreakdownRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Use AI to break down a feature into epics, stories, tasks, and subtasks.

    **Options:**
    - `auto_create`: If true, automatically create all issues in the database

    **Returns:**
    - Hierarchical breakdown
    - Total task count
    - Estimated hours
    - Created issue IDs (if auto_create=true)
    """
    try:
        breakdown = await ai_engine.breakdown_feature(
            project_id=request.project_id,
            feature_title=request.feature_title,
            feature_description=request.feature_description,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Count tasks and hours
    total_tasks = 0
    estimated_hours = 0
    for story in breakdown.get("stories", []):
        for task in story.get("tasks", []):
            total_tasks += 1
            estimated_hours += task.get("estimate_hours", 2)
            total_tasks += len(task.get("subtasks", []))

    issues_created = []

    if request.auto_create:
        # Create issues in database
        epic_id = None

        # Create Epic if present
        if breakdown.get("epic"):
            epic = await create_issue_from_breakdown(
                db,
                request.project_id,
                breakdown["epic"],
                IssueType.EPIC,
                None
            )
            epic_id = epic.id
            issues_created.append(epic.key)

        # Create Stories and Tasks
        for story_data in breakdown.get("stories", []):
            story = await create_issue_from_breakdown(
                db,
                request.project_id,
                story_data,
                IssueType.STORY,
                epic_id
            )
            issues_created.append(story.key)

            for task_data in story_data.get("tasks", []):
                task = await create_issue_from_breakdown(
                    db,
                    request.project_id,
                    task_data,
                    IssueType.TASK,
                    story.id
                )
                issues_created.append(task.key)

                # Create subtasks
                for subtask_title in task_data.get("subtasks", []):
                    subtask = await create_issue_from_breakdown(
                        db,
                        request.project_id,
                        {"title": subtask_title, "description": ""},
                        IssueType.SUBTASK,
                        task.id
                    )
                    issues_created.append(subtask.key)

        await db.commit()

    return BreakdownResponse(
        epic=breakdown.get("epic"),
        stories=breakdown.get("stories", []),
        total_tasks=total_tasks,
        estimated_hours=estimated_hours,
        issues_created=issues_created,
    )


async def create_issue_from_breakdown(
    db: AsyncSession,
    project_id: str,
    data: dict,
    issue_type: IssueType,
    parent_id: Optional[str]
) -> Issue:
    """Create an issue from breakdown data."""
    issue_key = await generate_issue_key(project_id, db)

    issue = Issue(
        id=generate_cuid(),
        key=issue_key,
        projectId=project_id,
        title=data["title"],
        description=data.get("description", ""),
        type=issue_type,
        status=IssueStatus.BACKLOG,
        assignee="AI",
        parentId=parent_id,
        estimate=data.get("estimate_hours", 2) * 60 if data.get("estimate_hours") else None,
    )

    db.add(issue)
    return issue
```

---

### Task T5.1.4: Add "AI Breakdown" Button to UI

**Component:**
```typescript
'use client';

import { useState } from 'react';
import { Sparkles, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { breakdownFeature } from '@/lib/api/ai';

export function AIBreakdownButton({ projectId, onComplete }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [autoCreate, setAutoCreate] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleBreakdown = async () => {
    setIsLoading(true);
    try {
      const data = await breakdownFeature({
        project_id: projectId,
        feature_title: title,
        feature_description: description,
        auto_create: autoCreate,
      });
      setResult(data);
      if (autoCreate) {
        onComplete();
      }
    } catch (error) {
      console.error('Breakdown failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Sparkles className="h-4 w-4 mr-2 text-purple-500" />
        AI Breakdown
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>AI Feature Breakdown</DialogTitle>
            <DialogDescription>
              Describe a feature and let AI break it down into epics, stories, and tasks.
            </DialogDescription>
          </DialogHeader>

          {!result ? (
            <div className="space-y-4">
              <Input
                placeholder="Feature title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <Textarea
                placeholder="Describe the feature in detail..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={6}
              />
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={autoCreate}
                  onCheckedChange={setAutoCreate}
                />
                <span className="text-sm">Automatically create issues</span>
              </div>
              <Button
                onClick={handleBreakdown}
                disabled={!title || !description || isLoading}
                className="w-full"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Breaking down...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Generate Breakdown
                  </>
                )}
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="p-4 bg-green-50 rounded-lg">
                <p className="font-medium">Breakdown Complete!</p>
                <p className="text-sm text-muted-foreground">
                  Created {result.issues_created.length} issues
                  ({result.total_tasks} tasks, ~{result.estimated_hours}h estimated)
                </p>
              </div>
              {/* Show breakdown preview */}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
```

---

## Story 5.2-5.4: Additional AI Features

**Story 5.2: Auto-Status Updates**
- Define rules: commit → IN_PROGRESS, PR merged → DONE
- Watch for git events
- Update issues automatically

**Story 5.3: Bug Detection**
- Parse test failure output
- Generate bug issue with:
  - Error message
  - Stack trace
  - Steps to reproduce (inferred)

**Story 5.4: QA Task Generation**
- When story marked DONE
- Generate QA test tasks
- Cover edge cases and errors

---

# EPIC 6: Git Integration & Automation

**ID:** E6
**Priority:** Low
**Status:** BACKLOG
**Description:** Link commits to issues and automatically update issue status based on commit messages.

---

## Story 6.1: Commit Tracking

### Task T6.1.1: Parse Commit Messages for Issue Keys

**File: backend/services/git_service.py**
```python
"""Git integration service."""

import re
from typing import List, Optional, Tuple

# Pattern to match issue keys like PM-123, PROJ-1
ISSUE_KEY_PATTERN = re.compile(r'\b([A-Z]+-\d+)\b')


def extract_issue_keys(commit_message: str) -> List[str]:
    """Extract issue keys from a commit message."""
    return ISSUE_KEY_PATTERN.findall(commit_message)


def parse_commit_type(commit_message: str) -> Tuple[Optional[str], str]:
    """
    Parse conventional commit format.

    Returns (type, message) where type is feat/fix/chore/etc.
    """
    match = re.match(r'^(\w+)(?:\([^)]+\))?:\s*(.+)', commit_message)
    if match:
        return match.group(1).lower(), match.group(2)
    return None, commit_message


# Status transitions based on commit type
COMMIT_TYPE_STATUS = {
    'wip': 'IN_PROGRESS',
    'feat': 'IN_PROGRESS',
    'fix': 'IN_PROGRESS',
    'done': 'DONE',
    'complete': 'DONE',
}
```

---

### Task T6.1.2: Create Commit-Issue Link

**Model:**
```python
class CommitLink(Base):
    """Link between git commits and issues."""
    __tablename__ = "CommitLink"

    id = Column(String, primary_key=True)
    issueId = Column(String, ForeignKey("Issue.id", ondelete="CASCADE"))
    commitHash = Column(String, nullable=False)
    commitMessage = Column(String, nullable=False)
    author = Column(String)
    timestamp = Column(DateTime)
    createdAt = Column(DateTime, server_default=func.now())

    issue = relationship("Issue", back_populates="commits")
```

---

## Story 6.2: Auto-Status from Commits

### Task T6.2.1-2: Define and Trigger Status Updates

**Webhook endpoint:**
```python
@router.post("/webhook/git")
async def git_webhook(
    payload: GitWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle git webhook for commit tracking.

    Parses commits for issue keys and updates statuses.
    """
    for commit in payload.commits:
        issue_keys = extract_issue_keys(commit.message)
        commit_type, _ = parse_commit_type(commit.message)

        for key in issue_keys:
            # Find issue
            result = await db.execute(
                select(Issue).where(Issue.key == key)
            )
            issue = result.scalar()

            if issue:
                # Create link
                link = CommitLink(
                    id=generate_cuid(),
                    issueId=issue.id,
                    commitHash=commit.hash,
                    commitMessage=commit.message,
                    author=commit.author,
                    timestamp=commit.timestamp,
                )
                db.add(link)

                # Update status if applicable
                if commit_type in COMMIT_TYPE_STATUS:
                    new_status = COMMIT_TYPE_STATUS[commit_type]
                    if issue.status != new_status:
                        issue.status = new_status
                        # Log activity
                        activity = Activity(
                            id=generate_cuid(),
                            type=ActivityType.STATUS_CHANGED,
                            field="status",
                            oldValue=issue.status,
                            newValue=new_status,
                            issueId=issue.id,
                            actor="git",
                        )
                        db.add(activity)

    await db.commit()
    return {"processed": len(payload.commits)}
```

---

# EPIC 7: Polish & Testing

**ID:** E7
**Priority:** Low
**Status:** BACKLOG
**Description:** Add keyboard shortcuts, improve error handling, and perform end-to-end testing.

---

## Story 7.1: Keyboard Shortcuts

### Task T7.1.1-2: Add Shortcuts

**File: frontend/hooks/use-keyboard-shortcuts.ts**
```typescript
'use client';

import { useEffect, useCallback } from 'react';

type ShortcutHandler = () => void;

interface Shortcuts {
  [key: string]: ShortcutHandler;
}

export function useKeyboardShortcuts(shortcuts: Shortcuts, enabled = true) {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled) return;

      // Don't trigger in inputs
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      const key = event.key.toLowerCase();
      const withMeta = event.metaKey || event.ctrlKey;

      // Build key combo string
      let combo = key;
      if (withMeta) combo = `cmd+${key}`;
      if (event.shiftKey) combo = `shift+${combo}`;

      if (shortcuts[combo]) {
        event.preventDefault();
        shortcuts[combo]();
      }
    },
    [shortcuts, enabled]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

// Usage in CodeBoard
useKeyboardShortcuts({
  'n': () => setIsCreateModalOpen(true),      // New issue
  '/': () => searchInputRef.current?.focus(), // Focus search
  'escape': () => setSelectedIssue(null),     // Close detail
  'e': () => setIsEditing(true),              // Edit issue
  'cmd+enter': () => saveIssue(),             // Save
});
```

---

## Story 7.2: Error Handling & Polish

### Task T7.2.1-3: Loading States, Error Boundaries, Toasts

**Error Boundary:**
```typescript
'use client';

import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center h-full p-8">
          <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
          <h2 className="text-lg font-semibold mb-2">Something went wrong</h2>
          <p className="text-muted-foreground mb-4">
            {this.state.error?.message || 'An unexpected error occurred'}
          </p>
          <Button onClick={() => window.location.reload()}>
            Reload Page
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
```

---

## Story 7.3: Testing

### Task T7.3.1-3: End-to-End Tests

**Test Plan:**

1. **CRUD Operations**
   - Create issue → verify in list
   - Read issue detail → all fields present
   - Update issue → changes persist
   - Delete issue → removed from list

2. **Drag-and-Drop**
   - Drag card to new column
   - Verify status updated
   - Check activity logged

3. **AI Features**
   - Feature breakdown generates tasks
   - QA tasks created for story

**Example E2E Test:**
```typescript
// tests/e2e/codeboard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('CodeBoard', () => {
  test('should create and view an issue', async ({ page }) => {
    await page.goto('/codeboard?project=test-project');

    // Click create button
    await page.click('button:has-text("Create Issue")');

    // Fill form
    await page.fill('input[name="title"]', 'Test Issue');
    await page.fill('textarea[name="description"]', 'Test description');
    await page.selectOption('select[name="type"]', 'TASK');

    // Submit
    await page.click('button:has-text("Create")');

    // Verify in list
    await expect(page.locator('text=Test Issue')).toBeVisible();
  });

  test('should drag issue to change status', async ({ page }) => {
    await page.goto('/codeboard?project=test-project');

    // Find issue card
    const card = page.locator('[data-testid="issue-card"]').first();
    const targetColumn = page.locator('[data-status="IN_PROGRESS"]');

    // Drag and drop
    await card.dragTo(targetColumn);

    // Verify status updated
    await expect(card).toHaveAttribute('data-status', 'IN_PROGRESS');
  });
});
```

---

# Summary

This completes the detailed implementation plan across all 4 parts:

| Part | Content |
|------|---------|
| Part 1 | Epic 1: Project Setup & Infrastructure (14 tasks) |
| Part 2 | Epic 2: Database & API Foundation (16 tasks) |
| Part 3 | Epic 3: CodeBoard UI (22 tasks) |
| Part 4 | Epics 4-7: RAG, AI, Git, Polish (28 tasks) |

**Total: 80 detailed tasks with code examples, acceptance criteria, and sub-tasks.**
