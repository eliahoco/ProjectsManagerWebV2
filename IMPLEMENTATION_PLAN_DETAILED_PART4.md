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

### Task T4.2.2: Auto-embed on Issue Create

**ID:** T4.2.2
**Story:** S4.2
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Hook into the issue creation flow to automatically embed new issues in ChromaDB for semantic search capabilities.

**Technical Requirements:**
- Call embedding service after successful issue creation
- Run embedding asynchronously to not block the API response
- Handle embedding failures gracefully (log but don't fail creation)

**File: backend/api/issues.py (modification)**
```python
from services.rag import rag_service
from services.embedding import embedding_service
import asyncio

@router.post("/", response_model=IssueResponse)
async def create_issue(
    project_id: str,
    issue_data: IssueCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new issue."""
    # ... existing creation logic ...

    # Embed issue asynchronously
    asyncio.create_task(embed_issue(issue))

    return issue

async def embed_issue(issue: Issue):
    """Embed issue content for semantic search."""
    try:
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
    except Exception as e:
        logger.error(f"Failed to embed issue {issue.id}: {e}")
```

**Acceptance Criteria:**
- [ ] New issues are embedded after creation
- [ ] Embedding runs asynchronously
- [ ] Embedding failures don't break issue creation
- [ ] Metadata includes type, status, priority

**Sub-tasks:**
1. **Import embedding services** - Add dependencies
2. **Create embed_issue function** - Async wrapper
3. **Hook into create endpoint** - Call after creation
4. **Add error handling** - Graceful failure

---

### Task T4.2.3: Auto-embed on Issue Update

**ID:** T4.2.3
**Story:** S4.2
**Priority:** Medium
**Estimated Effort:** 45 minutes

**Description:**
Update the vector embeddings when issues are modified to keep search results current.

**File: backend/api/issues.py (modification)**
```python
@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: str,
    issue_data: IssueUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing issue."""
    # ... existing update logic ...

    # Re-embed issue if content changed
    if issue_data.title or issue_data.description:
        asyncio.create_task(embed_issue(updated_issue))

    return updated_issue
```

**Acceptance Criteria:**
- [ ] Updated issues are re-embedded
- [ ] Only re-embed when title or description changes
- [ ] Old embedding is replaced (upsert)

**Sub-tasks:**
1. **Check for content changes** - Title or description
2. **Call embed_issue** - Reuse create function
3. **Verify upsert behavior** - Old embedding replaced

---

### Task T4.2.4: Embed Project Context

**ID:** T4.2.4
**Story:** S4.2
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Embed project context documents (PROJECT_DESCRIPTOR.md, README.md) to provide background information for AI features.

**File: backend/services/context_embedding.py**
```python
"""Embed project context documents."""

import os
from pathlib import Path
from services.rag import rag_service
from services.embedding import embedding_service

async def embed_project_context(project_id: str, project_path: str):
    """Embed project context documents."""
    context_files = [
        "PROJECT_DESCRIPTOR.md",
        "README.md",
        "ARCHITECTURE.md",
        "docs/CONTRIBUTING.md",
    ]

    for filename in context_files:
        filepath = Path(project_path) / filename
        if filepath.exists():
            content = filepath.read_text()

            # Chunk large files
            chunks = chunk_document(content, max_size=2000)

            for i, chunk in enumerate(chunks):
                doc_id = f"context_{filename}_{i}"
                rag_service.add_document(
                    project_id=project_id,
                    doc_id=doc_id,
                    content=chunk,
                    metadata={
                        "type": "context",
                        "source": filename,
                        "chunk": i,
                    },
                    collection_type="context"
                )

def chunk_document(content: str, max_size: int = 2000) -> list[str]:
    """Split document into chunks preserving paragraph boundaries."""
    paragraphs = content.split('\n\n')
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) < max_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks
```

**Acceptance Criteria:**
- [ ] PROJECT_DESCRIPTOR.md is embedded
- [ ] README.md is embedded
- [ ] Large files are chunked properly
- [ ] Chunk metadata includes source file

**Sub-tasks:**
1. **Create context embedding function** - Find and read files
2. **Implement document chunking** - Preserve paragraphs
3. **Store in context collection** - Separate from issues
4. **Add metadata** - Source file and chunk number

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

### Task T4.3.2: Add Search UI to CodeBoard

**ID:** T4.3.2
**Story:** S4.3
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create a semantic search component for the CodeBoard UI that uses the AI-powered search endpoint to find relevant issues.

**Technical Requirements:**
- Debounced search input (300ms)
- Loading indicator during search
- Results dropdown with issue preview
- Keyboard navigation support
- AI indicator icon (sparkle) to differentiate from regular search

**File: frontend/components/codeboard/semantic-search.tsx**
```typescript
'use client';

import { useState, useEffect } from 'react';
import { Sparkles, Loader2 } from 'lucide-react';
import { useDebounce } from '@/hooks/use-debounce';
import { Input } from '@/components/ui/input';
import { searchIssues } from '@/lib/api/search';
import { IssueTypeIcon } from './issue-type-icon';
import { Badge } from '@/components/ui/badge';

interface SemanticSearchProps {
  projectId: string;
  onSelect: (issue: Issue) => void;
}

export function SemanticSearch({ projectId, onSelect }: SemanticSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);

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
      setSelectedIndex(-1);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, -1));
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      onSelect(results[selectedIndex].issue);
      setQuery('');
      setResults([]);
    } else if (e.key === 'Escape') {
      setResults([]);
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
          onKeyDown={handleKeyDown}
          className="pl-10 pr-10"
        />
        {isSearching && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
        )}
      </div>

      {results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-popover border rounded-lg shadow-lg z-50 max-h-[300px] overflow-auto">
          {results.map((result, index) => (
            <div
              key={result.issue.id}
              className={`p-3 cursor-pointer flex items-center gap-3 ${
                index === selectedIndex ? 'bg-accent' : 'hover:bg-muted'
              }`}
              onClick={() => {
                onSelect(result.issue);
                setQuery('');
                setResults([]);
              }}
            >
              <IssueTypeIcon type={result.issue.type} />
              <Badge variant="outline" className="text-xs shrink-0">
                {result.issue.key}
              </Badge>
              <span className="text-sm truncate flex-1">{result.issue.title}</span>
              <span className="text-xs text-muted-foreground">
                {(result.score * 100).toFixed(0)}% match
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Search input with AI indicator
- [ ] Debounced search (300ms)
- [ ] Results dropdown with issue details
- [ ] Keyboard navigation (up/down/enter/escape)
- [ ] Match score displayed
- [ ] Loading indicator during search

**Sub-tasks:**
1. **Create search component** - Input with sparkle icon
2. **Implement debounced search** - 300ms delay
3. **Create results dropdown** - With issue preview
4. **Add keyboard navigation** - Arrow keys and enter

---

### Task T4.3.3: Integrate with Filter Bar

**ID:** T4.3.3
**Story:** S4.3
**Priority:** Medium
**Estimated Effort:** 45 minutes

**Description:**
Integrate the semantic search with the existing filter bar, allowing users to combine AI search with traditional filters.

**File: frontend/components/codeboard/filter-bar.tsx (modification)**
```typescript
// Add semantic search toggle to filter bar

import { SemanticSearch } from './semantic-search';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface FilterBarProps {
  filters: IssueFilters;
  onFiltersChange: (filters: IssueFilters) => void;
  projectId: string;
  onIssueSelect: (issue: Issue) => void;
}

export function FilterBar({
  filters,
  onFiltersChange,
  projectId,
  onIssueSelect,
}: FilterBarProps) {
  const [searchMode, setSearchMode] = useState<'text' | 'semantic'>('text');

  return (
    <div className="flex flex-wrap items-center gap-2 p-4 border-b bg-muted/30">
      {/* Search mode toggle */}
      <Tabs value={searchMode} onValueChange={(v) => setSearchMode(v as any)}>
        <TabsList className="h-8">
          <TabsTrigger value="text" className="text-xs">Text</TabsTrigger>
          <TabsTrigger value="semantic" className="text-xs">
            <Sparkles className="h-3 w-3 mr-1" />
            AI
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {searchMode === 'text' ? (
        <SearchInput
          value={filters.search || ''}
          onChange={(search) => onFiltersChange({ ...filters, search })}
        />
      ) : (
        <SemanticSearch
          projectId={projectId}
          onSelect={onIssueSelect}
        />
      )}

      {/* Rest of filters... */}
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Toggle between text and semantic search
- [ ] Semantic search works with existing filters
- [ ] Clear visual distinction between modes
- [ ] Seamless transition between modes

**Sub-tasks:**
1. **Add search mode toggle** - Text vs AI tabs
2. **Conditionally render search** - Based on mode
3. **Pass filters to semantic search** - If applicable

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

## Story 5.2: Auto-Status Updates

**ID:** S5.2
**Epic:** E5
**Priority:** Medium
**Description:** Automatically update issue status based on development activity like commits, PR creation, and merges.

---

### Task T5.2.1: Define Status Transition Rules

**ID:** T5.2.1
**Story:** S5.2
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Define the rules for automatic status transitions based on development events. Create a configurable rule engine.

**File: backend/services/status_rules.py**
```python
"""Status transition rules based on development events."""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass

class EventType(Enum):
    COMMIT = "commit"
    PR_CREATED = "pr_created"
    PR_MERGED = "pr_merged"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    DEPLOY_SUCCESS = "deploy_success"

@dataclass
class StatusRule:
    event: EventType
    from_statuses: List[str]  # What statuses this applies to
    to_status: str
    conditions: Optional[Dict] = None  # Additional conditions

# Default rules
DEFAULT_RULES: List[StatusRule] = [
    # First commit moves to In Progress
    StatusRule(
        event=EventType.COMMIT,
        from_statuses=["BACKLOG", "TODO"],
        to_status="IN_PROGRESS"
    ),
    # PR created moves to In Review
    StatusRule(
        event=EventType.PR_CREATED,
        from_statuses=["IN_PROGRESS"],
        to_status="IN_REVIEW"
    ),
    # PR merged moves to Done
    StatusRule(
        event=EventType.PR_MERGED,
        from_statuses=["IN_PROGRESS", "IN_REVIEW"],
        to_status="DONE"
    ),
    # Test failure reopens
    StatusRule(
        event=EventType.TEST_FAILED,
        from_statuses=["IN_REVIEW", "DONE"],
        to_status="IN_PROGRESS"
    ),
]

def get_status_transition(
    event: EventType,
    current_status: str,
    rules: List[StatusRule] = DEFAULT_RULES
) -> Optional[str]:
    """Get the new status based on event and current status."""
    for rule in rules:
        if rule.event == event and current_status in rule.from_statuses:
            return rule.to_status
    return None
```

**Acceptance Criteria:**
- [ ] Rules defined for commit, PR, merge events
- [ ] Rules are configurable per project
- [ ] Status transitions respect valid state machine
- [ ] Conditions can be added to rules

**Sub-tasks:**
1. **Define EventType enum** - All supported events
2. **Create StatusRule dataclass** - Rule structure
3. **Define default rules** - Common transitions
4. **Create rule evaluation function** - Match event to transition

---

### Task T5.2.2: Create Automation Service

**ID:** T5.2.2
**Story:** S5.2
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create the service that processes events and triggers status updates based on rules.

**File: backend/services/automation_service.py**
```python
"""Automation service for event-driven status updates."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from services.status_rules import EventType, get_status_transition
from services.activity import log_activity
from models.issue import Issue

class AutomationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_event(
        self,
        event_type: EventType,
        issue_id: str,
        event_data: dict
    ) -> Optional[str]:
        """Process an event and update issue status if applicable."""
        # Get issue
        issue = await self.db.get(Issue, issue_id)
        if not issue:
            return None

        # Check for status transition
        new_status = get_status_transition(event_type, issue.status)
        if not new_status:
            return None

        # Update status
        old_status = issue.status
        issue.status = new_status

        # Log activity
        await log_activity(
            self.db,
            issue_id=issue_id,
            type="STATUS_CHANGE",
            description=f"Auto-updated: {old_status} → {new_status} (triggered by {event_type.value})",
            metadata=event_data
        )

        await self.db.commit()
        return new_status

    async def process_commit(self, commit_data: dict) -> list:
        """Process a commit and update related issues."""
        from services.git_service import extract_issue_keys

        issue_keys = extract_issue_keys(commit_data.get("message", ""))
        results = []

        for key in issue_keys:
            # Find issue by key
            issue = await self.db.query(Issue).filter(Issue.key == key).first()
            if issue:
                new_status = await self.process_event(
                    EventType.COMMIT,
                    issue.id,
                    commit_data
                )
                results.append({"issue_key": key, "new_status": new_status})

        return results
```

**Acceptance Criteria:**
- [ ] Service processes events
- [ ] Status updated based on rules
- [ ] Activity logged for changes
- [ ] Multiple issues handled per event

**Sub-tasks:**
1. **Create AutomationService class** - Event processor
2. **Implement process_event** - Single event handling
3. **Implement process_commit** - Extract keys and update
4. **Add activity logging** - Record auto-updates

---

### Task T5.2.3: Create /api/ai/update Endpoint

**ID:** T5.2.3
**Story:** S5.2
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Create the API endpoint that receives events from webhooks and triggers automation.

**File: backend/api/automation.py**
```python
"""Automation API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Dict, Any, Optional

from services.database import get_db
from services.automation_service import AutomationService
from services.status_rules import EventType

router = APIRouter(prefix="/automation", tags=["Automation"])

class EventPayload(BaseModel):
    event_type: str
    issue_id: Optional[str] = None
    issue_key: Optional[str] = None
    data: Dict[str, Any]

@router.post("/event")
async def process_event(
    payload: EventPayload,
    db: AsyncSession = Depends(get_db),
):
    """Process an automation event."""
    try:
        event = EventType(payload.event_type)
    except ValueError:
        raise HTTPException(400, f"Unknown event type: {payload.event_type}")

    service = AutomationService(db)

    if event == EventType.COMMIT:
        results = await service.process_commit(payload.data)
        return {"processed": len(results), "updates": results}

    if not payload.issue_id and not payload.issue_key:
        raise HTTPException(400, "issue_id or issue_key required")

    # Find issue ID if key provided
    issue_id = payload.issue_id
    if not issue_id and payload.issue_key:
        issue = await db.query(Issue).filter(Issue.key == payload.issue_key).first()
        if not issue:
            raise HTTPException(404, f"Issue not found: {payload.issue_key}")
        issue_id = issue.id

    new_status = await service.process_event(event, issue_id, payload.data)
    return {"issue_id": issue_id, "new_status": new_status}

@router.post("/webhook/github")
async def github_webhook(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub webhook events."""
    event_type = None
    data = {}

    # Parse GitHub event
    if "commits" in payload:
        event_type = EventType.COMMIT
        data = {"commits": payload["commits"]}
    elif "pull_request" in payload:
        action = payload.get("action")
        if action == "opened":
            event_type = EventType.PR_CREATED
        elif action == "closed" and payload["pull_request"].get("merged"):
            event_type = EventType.PR_MERGED
        data = {"pull_request": payload["pull_request"]}

    if event_type:
        service = AutomationService(db)
        # Process based on event type
        # ... implementation details

    return {"status": "processed"}
```

**Acceptance Criteria:**
- [ ] Endpoint accepts event payloads
- [ ] GitHub webhook parsing works
- [ ] Issue resolved by ID or key
- [ ] Returns update results

**Sub-tasks:**
1. **Create event endpoint** - Generic event processing
2. **Create webhook endpoint** - GitHub-specific parsing
3. **Add error handling** - Invalid events
4. **Return processing results** - What was updated

---

## Story 5.3: Bug Detection

**ID:** S5.3
**Epic:** E5
**Priority:** Medium
**Description:** Automatically create bug issues from test failures with AI-generated descriptions.

---

### Task T5.3.1: Create Bug Prompt Template

**ID:** T5.3.1
**Story:** S5.3
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Create prompt templates for AI to analyze test failures and generate bug reports.

**File: backend/services/prompts/bug_detection.py**
```python
"""Prompt templates for bug detection and reporting."""

BUG_ANALYSIS_PROMPT = """You are an expert developer analyzing a test failure.

Based on the following test failure, create a detailed bug report:

**Test Name:** {test_name}
**Error Type:** {error_type}
**Error Message:** {error_message}
**Stack Trace:**
```
{stack_trace}
```

**Test Code:**
```{language}
{test_code}
```

Create a bug report with:
1. A clear, concise title (max 100 characters)
2. A description explaining what went wrong
3. Steps to reproduce (inferred from the test)
4. Expected behavior
5. Actual behavior
6. Suggested priority (CRITICAL if it blocks main functionality, HIGH if it affects users, MEDIUM otherwise)

Respond in JSON format:
{
  "title": "Bug title",
  "description": "Detailed description...",
  "steps_to_reproduce": ["Step 1", "Step 2"],
  "expected_behavior": "What should happen",
  "actual_behavior": "What actually happens",
  "priority": "HIGH",
  "labels": ["bug", "test-failure"]
}
"""

def build_bug_prompt(
    test_name: str,
    error_type: str,
    error_message: str,
    stack_trace: str,
    test_code: str = "",
    language: str = "python"
) -> str:
    """Build the bug analysis prompt."""
    return BUG_ANALYSIS_PROMPT.format(
        test_name=test_name,
        error_type=error_type,
        error_message=error_message,
        stack_trace=stack_trace,
        test_code=test_code or "Not available",
        language=language
    )
```

**Acceptance Criteria:**
- [ ] Prompt template defined
- [ ] Includes all relevant test failure info
- [ ] Output format is JSON
- [ ] Priority inference included

**Sub-tasks:**
1. **Define prompt template** - Bug analysis structure
2. **Create prompt builder** - Fill in variables
3. **Define output format** - JSON schema

---

### Task T5.3.2: Create /api/ai/bug Endpoint

**ID:** T5.3.2
**Story:** S5.3
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create the API endpoint that receives test failure data and creates bug issues.

**File: backend/api/ai_bug.py**
```python
"""AI bug detection endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from services.database import get_db
from services.ai import ai_service
from services.prompts.bug_detection import build_bug_prompt
from models.issue import Issue
from models.schemas import IssueCreate

router = APIRouter(prefix="/ai", tags=["AI"])

class TestFailurePayload(BaseModel):
    project_id: str
    test_name: str
    error_type: str
    error_message: str
    stack_trace: str
    test_code: Optional[str] = None
    language: str = "python"

@router.post("/bug")
async def create_bug_from_failure(
    payload: TestFailurePayload,
    db: AsyncSession = Depends(get_db),
):
    """Create a bug issue from a test failure."""
    # Build prompt
    prompt = build_bug_prompt(
        test_name=payload.test_name,
        error_type=payload.error_type,
        error_message=payload.error_message,
        stack_trace=payload.stack_trace,
        test_code=payload.test_code,
        language=payload.language
    )

    # Call AI
    response = await ai_service.complete(prompt)

    # Parse response
    try:
        bug_data = json.loads(response)
    except json.JSONDecodeError:
        raise HTTPException(500, "AI returned invalid JSON")

    # Create bug issue
    issue = Issue(
        projectId=payload.project_id,
        type="BUG",
        title=bug_data["title"],
        description=format_bug_description(bug_data),
        priority=bug_data.get("priority", "MEDIUM"),
        status="BACKLOG",
        assignee="AI",
        metadata={
            "source": "test_failure",
            "test_name": payload.test_name,
            "ai_generated": True
        }
    )

    db.add(issue)
    await db.commit()
    await db.refresh(issue)

    return {"issue": issue, "ai_analysis": bug_data}

def format_bug_description(bug_data: dict) -> str:
    """Format bug data into markdown description."""
    steps = "\n".join([f"{i+1}. {s}" for i, s in enumerate(bug_data.get("steps_to_reproduce", []))])

    return f"""## Description
{bug_data.get("description", "No description")}

## Steps to Reproduce
{steps or "Not available"}

## Expected Behavior
{bug_data.get("expected_behavior", "Not specified")}

## Actual Behavior
{bug_data.get("actual_behavior", "Not specified")}

---
*This bug was automatically generated from a test failure.*
"""
```

**Acceptance Criteria:**
- [ ] Endpoint accepts test failure data
- [ ] AI analyzes failure and generates bug report
- [ ] Bug issue created with proper format
- [ ] Metadata tracks AI generation source

**Sub-tasks:**
1. **Create payload schema** - Test failure data
2. **Call AI service** - With prompt
3. **Parse AI response** - Extract bug details
4. **Create bug issue** - With formatted description

---

## Story 5.4: QA Task Generation

**ID:** S5.4
**Epic:** E5
**Priority:** Medium
**Description:** Generate QA testing tasks when features are completed.

---

### Task T5.4.1: Create QA Prompt Template

**ID:** T5.4.1
**Story:** S5.4
**Priority:** Medium
**Estimated Effort:** 1 hour

**Description:**
Create prompt templates for generating QA test cases from completed features.

**File: backend/services/prompts/qa_generation.py**
```python
"""Prompt templates for QA task generation."""

QA_GENERATION_PROMPT = """You are a QA engineer creating test cases for a completed feature.

**Feature Story:**
Title: {story_title}
Description: {story_description}

**Completed Tasks:**
{tasks_list}

**Acceptance Criteria from Story:**
{acceptance_criteria}

Generate comprehensive QA test cases covering:
1. Happy path scenarios
2. Edge cases
3. Error handling
4. Performance considerations
5. Security checks (if applicable)

Each test case should be actionable by a QA tester.

Respond in JSON format:
{
  "test_cases": [
    {
      "title": "Test case title",
      "type": "manual|automated",
      "priority": "HIGH|MEDIUM|LOW",
      "steps": ["Step 1", "Step 2"],
      "expected_result": "What should happen",
      "category": "happy_path|edge_case|error|performance|security"
    }
  ]
}
"""

def build_qa_prompt(
    story_title: str,
    story_description: str,
    tasks: list,
    acceptance_criteria: str = ""
) -> str:
    """Build the QA generation prompt."""
    tasks_list = "\n".join([f"- {t['title']}" for t in tasks])

    return QA_GENERATION_PROMPT.format(
        story_title=story_title,
        story_description=story_description,
        tasks_list=tasks_list,
        acceptance_criteria=acceptance_criteria or "Not specified"
    )
```

**Acceptance Criteria:**
- [ ] Prompt covers all test categories
- [ ] Output is structured JSON
- [ ] Test cases are actionable

**Sub-tasks:**
1. **Define prompt template** - QA test generation
2. **Include all test categories** - Happy path, edge, error, etc.
3. **Create prompt builder** - Fill variables

---

### Task T5.4.2: Create /api/ai/qa Endpoint

**ID:** T5.4.2
**Story:** S5.4
**Priority:** Medium
**Estimated Effort:** 1.5 hours

**Description:**
Create the API endpoint that generates QA tasks for a completed story.

**File: backend/api/ai_qa.py**
```python
"""AI QA task generation endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.database import get_db
from services.ai import ai_service
from services.prompts.qa_generation import build_qa_prompt
from models.issue import Issue

router = APIRouter(prefix="/ai", tags=["AI"])

@router.post("/qa/{story_id}")
async def generate_qa_tasks(
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate QA tasks for a completed story."""
    # Get story
    story = await db.get(Issue, story_id)
    if not story:
        raise HTTPException(404, "Story not found")

    if story.type != "STORY":
        raise HTTPException(400, "Can only generate QA for stories")

    # Get completed tasks
    tasks_result = await db.execute(
        select(Issue)
        .where(Issue.parentId == story_id)
        .where(Issue.status == "DONE")
    )
    tasks = [{"title": t.title, "description": t.description}
             for t in tasks_result.scalars().all()]

    if not tasks:
        raise HTTPException(400, "No completed tasks found for story")

    # Build prompt
    prompt = build_qa_prompt(
        story_title=story.title,
        story_description=story.description or "",
        tasks=tasks,
    )

    # Call AI
    response = await ai_service.complete(prompt)

    # Parse response
    try:
        qa_data = json.loads(response)
    except json.JSONDecodeError:
        raise HTTPException(500, "AI returned invalid JSON")

    # Create QA task issues
    created_tasks = []
    for test_case in qa_data.get("test_cases", []):
        qa_issue = Issue(
            projectId=story.projectId,
            type="TASK",
            title=f"[QA] {test_case['title']}",
            description=format_qa_description(test_case),
            priority=test_case.get("priority", "MEDIUM"),
            status="TODO",
            parentId=story_id,
            assignee="AI",
            metadata={
                "qa_type": test_case.get("type", "manual"),
                "qa_category": test_case.get("category"),
                "ai_generated": True
            }
        )
        db.add(qa_issue)
        created_tasks.append(qa_issue)

    await db.commit()

    return {
        "story_id": story_id,
        "qa_tasks_created": len(created_tasks),
        "tasks": [{"id": t.id, "title": t.title} for t in created_tasks]
    }

def format_qa_description(test_case: dict) -> str:
    """Format test case into markdown description."""
    steps = "\n".join([f"{i+1}. {s}" for i, s in enumerate(test_case.get("steps", []))])

    return f"""## Test Case
**Type:** {test_case.get("type", "manual")}
**Category:** {test_case.get("category", "general")}

## Steps
{steps}

## Expected Result
{test_case.get("expected_result", "Not specified")}

---
*This QA task was automatically generated.*
"""
```

**Acceptance Criteria:**
- [ ] Endpoint accepts story ID
- [ ] AI generates relevant test cases
- [ ] QA task issues created as children
- [ ] Metadata tracks AI generation

**Sub-tasks:**
1. **Get story and tasks** - Query database
2. **Call AI service** - With prompt
3. **Create QA issues** - As story children
4. **Return created tasks** - Summary response

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

**ID:** S6.2
**Epic:** E6
**Priority:** Low
**Description:** Automatically update issue status based on commit message patterns.

---

### Task T6.2.1: Define Commit Patterns

**ID:** T6.2.1
**Story:** S6.2
**Priority:** Low
**Estimated Effort:** 45 minutes

**Description:**
Define the commit message patterns that trigger automatic status updates.

**File: backend/services/git_service.py (addition)**
```python
# Commit patterns for status transitions
COMMIT_PATTERNS = {
    # Work in progress
    r'^wip\b': 'IN_PROGRESS',
    r'\[wip\]': 'IN_PROGRESS',

    # Feature work
    r'^feat(\(.+\))?:': 'IN_PROGRESS',
    r'^fix(\(.+\))?:': 'IN_PROGRESS',
    r'^refactor(\(.+\))?:': 'IN_PROGRESS',

    # Completion indicators
    r'^done\b': 'DONE',
    r'\[done\]': 'DONE',
    r'^complete\b': 'DONE',
    r'closes?\s+#?\d+': 'DONE',
    r'fixes?\s+#?\d+': 'DONE',
}

def get_status_from_commit(message: str) -> Optional[str]:
    """Get status transition based on commit message patterns."""
    message_lower = message.lower()
    for pattern, status in COMMIT_PATTERNS.items():
        if re.search(pattern, message_lower):
            return status
    return None
```

**Acceptance Criteria:**
- [ ] Patterns defined for WIP commits
- [ ] Patterns defined for conventional commits
- [ ] Patterns defined for completion indicators
- [ ] Pattern matching function works correctly

**Sub-tasks:**
1. **Define WIP patterns** - wip, [wip]
2. **Define conventional commit patterns** - feat, fix, refactor
3. **Define completion patterns** - done, closes #123
4. **Create matching function** - Return status or None

---

### Task T6.2.2: Trigger Status Updates

**ID:** T6.2.2
**Story:** S6.2
**Priority:** Low
**Estimated Effort:** 1 hour

**Description:**
Implement the webhook endpoint that processes commits and triggers status updates.

**File: backend/api/git_webhook.py**
```python
"""Git webhook for commit tracking and status updates."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List

from services.database import get_db
from services.git_service import extract_issue_keys, get_status_from_commit
from models.issue import Issue, Activity, CommitLink
from utils.cuid import generate_cuid

router = APIRouter(prefix="/webhook", tags=["Webhooks"])

class Commit(BaseModel):
    hash: str
    message: str
    author: str
    timestamp: str

class GitWebhookPayload(BaseModel):
    commits: List[Commit]
    repository: str

@router.post("/git")
async def git_webhook(
    payload: GitWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """Handle git webhook for commit tracking and status updates."""
    processed = []

    for commit in payload.commits:
        issue_keys = extract_issue_keys(commit.message)
        new_status = get_status_from_commit(commit.message)

        for key in issue_keys:
            result = await db.execute(select(Issue).where(Issue.key == key))
            issue = result.scalar()

            if not issue:
                continue

            # Create commit link
            link = CommitLink(
                id=generate_cuid(),
                issueId=issue.id,
                commitHash=commit.hash,
                commitMessage=commit.message,
                author=commit.author,
            )
            db.add(link)

            # Update status if applicable
            if new_status and issue.status != new_status:
                old_status = issue.status
                issue.status = new_status

                activity = Activity(
                    id=generate_cuid(),
                    type="STATUS_CHANGE",
                    description=f"Status changed from {old_status} to {new_status} by commit",
                    issueId=issue.id,
                    actor="git-automation",
                )
                db.add(activity)

                processed.append({
                    "issue_key": key,
                    "old_status": old_status,
                    "new_status": new_status,
                    "commit": commit.hash[:7]
                })

    await db.commit()
    return {"commits_processed": len(payload.commits), "status_updates": processed}
```

**Acceptance Criteria:**
- [ ] Webhook receives commit data
- [ ] Issue keys extracted from messages
- [ ] Commit links created
- [ ] Status updated based on patterns
- [ ] Activity logged for changes

**Sub-tasks:**
1. **Create webhook endpoint** - Accept commit payload
2. **Process each commit** - Extract keys and status
3. **Create commit links** - Track commits per issue
4. **Update status** - Based on patterns
5. **Log activity** - Record auto-updates

---

# EPIC 7: Polish & Testing

**ID:** E7
**Priority:** Low
**Status:** BACKLOG
**Description:** Add keyboard shortcuts, improve error handling, and perform end-to-end testing.

---

## Story 7.1: Keyboard Shortcuts

**ID:** S7.1
**Epic:** E7
**Priority:** Low
**Description:** Add keyboard navigation and shortcuts throughout the CodeBoard interface.

---

### Task T7.1.1: Add Board Shortcuts

**ID:** T7.1.1
**Story:** S7.1
**Priority:** Low
**Estimated Effort:** 1 hour

**Description:**
Create a keyboard shortcuts system and add shortcuts for board-level actions.

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
```

**Board-level shortcuts:**
```typescript
// In CodeBoard component
useKeyboardShortcuts({
  'n': () => setIsCreateModalOpen(true),      // New issue
  '/': () => searchInputRef.current?.focus(), // Focus search
  '?': () => setShowShortcutsHelp(true),      // Show shortcuts help
  'b': () => setViewMode('board'),            // Switch to board view
  'l': () => setViewMode('list'),             // Switch to list view
});
```

**Acceptance Criteria:**
- [ ] Hook created for keyboard shortcuts
- [ ] N opens create issue modal
- [ ] / focuses search input
- [ ] ? shows shortcuts help modal
- [ ] Shortcuts disabled in input fields

**Sub-tasks:**
1. **Create useKeyboardShortcuts hook** - Handle key events
2. **Add create shortcut (N)** - Open modal
3. **Add search shortcut (/)** - Focus search
4. **Add help shortcut (?)** - Show shortcuts

---

### Task T7.1.2: Add Issue Shortcuts

**ID:** T7.1.2
**Story:** S7.1
**Priority:** Low
**Estimated Effort:** 45 minutes

**Description:**
Add keyboard shortcuts for issue-level actions in the detail view.

**Implementation:**
```typescript
// In IssueDetail component
useKeyboardShortcuts({
  'e': () => setIsEditing(true),              // Edit issue
  'escape': () => {
    if (isEditing) {
      setIsEditing(false);
    } else {
      onClose();
    }
  },
  'cmd+enter': () => {
    if (isEditing) saveIssue();
  },
  'cmd+s': () => {
    if (isEditing) saveIssue();
  },
  'c': () => focusCommentInput(),             // Add comment
}, isOpen);
```

**Acceptance Criteria:**
- [ ] E opens edit mode
- [ ] Escape closes edit/detail
- [ ] Cmd+Enter saves changes
- [ ] C focuses comment input

**Sub-tasks:**
1. **Add edit shortcut (E)** - Enter edit mode
2. **Add close shortcut (Escape)** - Close or cancel
3. **Add save shortcut (Cmd+Enter)** - Save changes
4. **Add comment shortcut (C)** - Focus comment

---

## Story 7.2: Error Handling & Polish

**ID:** S7.2
**Epic:** E7
**Priority:** Low
**Description:** Improve user experience with loading states, error handling, and notifications.

---

### Task T7.2.1: Add Loading States

**ID:** T7.2.1
**Story:** S7.2
**Priority:** Low
**Estimated Effort:** 1 hour

**Description:**
Add skeleton loading states for all major components.

**File: frontend/components/codeboard/skeletons.tsx**
```typescript
import { Skeleton } from '@/components/ui/skeleton';

export function KanbanBoardSkeleton() {
  return (
    <div className="flex gap-4 p-4">
      {[1, 2, 3, 4, 5].map(i => (
        <div key={i} className="w-72 flex-shrink-0">
          <Skeleton className="h-8 w-24 mb-4" />
          <div className="space-y-3">
            {[1, 2, 3].map(j => (
              <Skeleton key={j} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function IssueListSkeleton() {
  return (
    <div className="space-y-2 p-4">
      <Skeleton className="h-10 w-full" />
      {[1, 2, 3, 4, 5].map(i => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

export function IssueDetailSkeleton() {
  return (
    <div className="p-6 space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-6 w-full" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
```

**Acceptance Criteria:**
- [ ] Board has skeleton loading state
- [ ] List has skeleton loading state
- [ ] Issue detail has skeleton loading state
- [ ] Skeletons match actual layout

**Sub-tasks:**
1. **Create KanbanBoardSkeleton** - Columns with cards
2. **Create IssueListSkeleton** - Table rows
3. **Create IssueDetailSkeleton** - Detail panel
4. **Use Suspense boundaries** - Automatic skeleton display

---

### Task T7.2.2: Add Error Boundaries

**ID:** T7.2.2
**Story:** S7.2
**Priority:** Low
**Estimated Effort:** 45 minutes

**Description:**
Add React error boundaries to gracefully handle component errors.

**File: frontend/components/error-boundary.tsx**
```typescript
'use client';

import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
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
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center h-full p-8 text-center">
          <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
          <h2 className="text-lg font-semibold mb-2">Something went wrong</h2>
          <p className="text-muted-foreground mb-4 max-w-md">
            {this.state.error?.message || 'An unexpected error occurred'}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={this.handleRetry}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Try Again
            </Button>
            <Button onClick={() => window.location.reload()}>
              Reload Page
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
```

**Acceptance Criteria:**
- [ ] Error boundary catches render errors
- [ ] Friendly error message displayed
- [ ] Retry button resets error state
- [ ] Reload button refreshes page

**Sub-tasks:**
1. **Create ErrorBoundary component** - Class component
2. **Add error UI** - Message and actions
3. **Add retry functionality** - Reset error state
4. **Wrap main components** - Board, detail, etc.

---

### Task T7.2.3: Add Toast Notifications

**ID:** T7.2.3
**Story:** S7.2
**Priority:** Low
**Estimated Effort:** 45 minutes

**Description:**
Add toast notifications for user feedback on actions.

**Implementation using shadcn/ui toast:**
```typescript
// In components using toasts
import { useToast } from '@/components/ui/use-toast';

function IssueActions() {
  const { toast } = useToast();

  const handleSave = async () => {
    try {
      await saveIssue();
      toast({
        title: 'Issue saved',
        description: 'Your changes have been saved successfully.',
      });
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error saving issue',
        description: error.message,
      });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteIssue();
      toast({
        title: 'Issue deleted',
        description: 'The issue has been moved to trash.',
        action: (
          <Button variant="outline" size="sm" onClick={undoDelete}>
            Undo
          </Button>
        ),
      });
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error deleting issue',
        description: error.message,
      });
    }
  };
}
```

**Acceptance Criteria:**
- [ ] Success toasts for CRUD operations
- [ ] Error toasts for failures
- [ ] Undo action for deletes
- [ ] Auto-dismiss after delay

**Sub-tasks:**
1. **Set up toast provider** - In layout
2. **Add success toasts** - Create, update, delete
3. **Add error toasts** - API failures
4. **Add undo action** - For deletions

---

## Story 7.3: Testing

**ID:** S7.3
**Epic:** E7
**Priority:** Low
**Description:** Comprehensive end-to-end testing of all CodeBoard features.

---

### Task T7.3.1: Test All CRUD Operations

**ID:** T7.3.1
**Story:** S7.3
**Priority:** Low
**Estimated Effort:** 2 hours

**Description:**
Create E2E tests for create, read, update, and delete operations.

**File: tests/e2e/crud.spec.ts**
```typescript
import { test, expect } from '@playwright/test';

test.describe('Issue CRUD Operations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/codeboard?project=test-project');
  });

  test('should create a new issue', async ({ page }) => {
    await page.click('button:has-text("Create Issue")');

    await page.fill('input[name="title"]', 'Test Issue');
    await page.fill('textarea[name="description"]', 'Test description');
    await page.selectOption('select[name="type"]', 'TASK');
    await page.selectOption('select[name="priority"]', 'HIGH');

    await page.click('button:has-text("Create")');

    // Verify toast
    await expect(page.locator('text=Issue created')).toBeVisible();

    // Verify in board
    await expect(page.locator('text=Test Issue')).toBeVisible();
  });

  test('should read issue details', async ({ page }) => {
    await page.click('[data-testid="issue-card"]:has-text("Test Issue")');

    await expect(page.locator('[data-testid="issue-detail"]')).toBeVisible();
    await expect(page.locator('text=Test description')).toBeVisible();
  });

  test('should update an issue', async ({ page }) => {
    await page.click('[data-testid="issue-card"]:has-text("Test Issue")');
    await page.click('button:has-text("Edit")');

    await page.fill('input[name="title"]', 'Updated Issue');
    await page.click('button:has-text("Save")');

    await expect(page.locator('text=Changes saved')).toBeVisible();
    await expect(page.locator('text=Updated Issue')).toBeVisible();
  });

  test('should delete an issue', async ({ page }) => {
    await page.click('[data-testid="issue-card"]:has-text("Updated Issue")');
    await page.click('button:has-text("Delete")');
    await page.click('button:has-text("Confirm")');

    await expect(page.locator('text=Issue deleted')).toBeVisible();
    await expect(page.locator('text=Updated Issue')).not.toBeVisible();
  });
});
```

**Acceptance Criteria:**
- [ ] Create test passes
- [ ] Read test passes
- [ ] Update test passes
- [ ] Delete test passes

**Sub-tasks:**
1. **Write create test** - Fill form and submit
2. **Write read test** - Open detail and verify
3. **Write update test** - Edit and save
4. **Write delete test** - Delete and confirm

---

### Task T7.3.2: Test Drag-and-Drop

**ID:** T7.3.2
**Story:** S7.3
**Priority:** Low
**Estimated Effort:** 1 hour

**Description:**
Create E2E tests for drag-and-drop status changes.

**File: tests/e2e/dnd.spec.ts**
```typescript
import { test, expect } from '@playwright/test';

test.describe('Drag and Drop', () => {
  test('should change status by dragging to new column', async ({ page }) => {
    await page.goto('/codeboard?project=test-project');

    const card = page.locator('[data-testid="issue-card"]').first();
    const targetColumn = page.locator('[data-status="IN_PROGRESS"]');

    // Get initial status
    const initialStatus = await card.getAttribute('data-status');
    expect(initialStatus).toBe('TODO');

    // Drag to In Progress
    await card.dragTo(targetColumn);

    // Verify status updated
    await expect(card).toHaveAttribute('data-status', 'IN_PROGRESS');

    // Verify activity logged
    await card.click();
    await expect(page.locator('text=Status changed')).toBeVisible();
  });

  test('should reorder within column', async ({ page }) => {
    await page.goto('/codeboard?project=test-project');

    const cards = page.locator('[data-status="TODO"] [data-testid="issue-card"]');
    const firstCard = cards.first();
    const secondCard = cards.nth(1);

    // Get initial order
    const firstKey = await firstCard.getAttribute('data-issue-key');

    // Drag first card below second
    await firstCard.dragTo(secondCard);

    // Verify order changed
    const newFirstKey = await cards.first().getAttribute('data-issue-key');
    expect(newFirstKey).not.toBe(firstKey);
  });
});
```

**Acceptance Criteria:**
- [ ] Drag to column changes status
- [ ] Activity logged for status change
- [ ] Reorder within column works
- [ ] Visual feedback during drag

**Sub-tasks:**
1. **Test column drag** - Status change
2. **Test reorder** - Within column
3. **Verify activity** - Change logged

---

### Task T7.3.3: Test AI Features

**ID:** T7.3.3
**Story:** S7.3
**Priority:** Low
**Estimated Effort:** 1.5 hours

**Description:**
Create E2E tests for AI-powered features.

**File: tests/e2e/ai-features.spec.ts**
```typescript
import { test, expect } from '@playwright/test';

test.describe('AI Features', () => {
  test('should breakdown feature into tasks', async ({ page }) => {
    await page.goto('/codeboard?project=test-project');

    // Open AI breakdown modal
    await page.click('button:has-text("AI Breakdown")');

    // Enter feature description
    await page.fill(
      'textarea[name="feature"]',
      'Add user authentication with email/password and OAuth support'
    );

    await page.click('button:has-text("Generate Tasks")');

    // Wait for AI response
    await expect(page.locator('text=Tasks generated')).toBeVisible({ timeout: 30000 });

    // Verify tasks created
    await expect(page.locator('[data-testid="issue-card"]')).toHaveCount.greaterThan(1);
  });

  test('should generate QA tasks for story', async ({ page }) => {
    await page.goto('/codeboard?project=test-project');

    // Mark story as done
    const story = page.locator('[data-type="STORY"]').first();
    await story.dragTo(page.locator('[data-status="DONE"]'));

    // Generate QA tasks
    await story.click();
    await page.click('button:has-text("Generate QA Tasks")');

    // Wait for AI response
    await expect(page.locator('text=QA tasks created')).toBeVisible({ timeout: 30000 });

    // Verify QA tasks created as children
    await expect(page.locator('[data-testid="qa-task"]')).toHaveCount.greaterThan(0);
  });

  test('should use semantic search', async ({ page }) => {
    await page.goto('/codeboard?project=test-project');

    // Switch to AI search
    await page.click('button:has-text("AI")');

    // Search with natural language
    await page.fill('input[placeholder="AI-powered search"]', 'login functionality');

    // Verify results
    await expect(page.locator('[data-testid="search-result"]')).toHaveCount.greaterThan(0);
  });
});
```

**Acceptance Criteria:**
- [ ] Feature breakdown generates tasks
- [ ] QA task generation works
- [ ] Semantic search returns results
- [ ] AI responses handled within timeout

**Sub-tasks:**
1. **Test feature breakdown** - Generate tasks
2. **Test QA generation** - Create test tasks
3. **Test semantic search** - Natural language query

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
