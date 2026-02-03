# Feature Plan: Comprehensive Documentation & RAG Knowledge System

## Overview

Build an intelligent documentation system that captures, stores, and leverages implementation knowledge across the entire project lifecycle. This enables smarter AI-driven planning, QA generation, and bug tracking through contextual awareness.

---

## Current State Analysis

### What Exists Today

| Component | Status | Details |
|-----------|--------|---------|
| Issue Description | ✅ | Basic text field for requirements |
| Comments | ✅ | Unstructured text storage |
| Activity Log | ✅ | Audit trail of changes |
| ChromaDB RAG | ✅ | Basic semantic search (title, description, type) |
| QA Tasks | ✅ | Scenario, expected/actual results, execution history |
| Bug Linking | ⚠️ | Only from QA tasks via `bugIssueId` |
| Execution Docs | ⚠️ | Generated as comment, not structured |
| MD File Export | ❌ | Read-only, no generation |

### What's Missing

1. **Structured Implementation Storage** - No dedicated fields for implementation details
2. **Enhanced RAG Context** - Missing execution results, QA outcomes, lessons learned
3. **Automatic Documentation Export** - No MD file generation per feature
4. **Smart Linking** - Limited bug/feature linking capabilities
5. **Contextual AI Generation** - Breakdown/QA doesn't leverage project knowledge

---

## Architecture Design

### 1. Database Schema Extensions

```prisma
// ========== NEW MODEL: ExecutionSummary ==========
model ExecutionSummary {
  id                  String    @id @default(cuid())
  issueId             String
  issue               Issue     @relation(fields: [issueId], references: [id], onDelete: Cascade)

  // Execution Metadata
  summary             String    // Markdown summary
  executedAt          DateTime
  executionTime       Float     // Seconds
  provider            String    // claude_code, ollama
  model               String?   // claude-3-opus, etc.
  exitCode            Int?

  // Implementation Details
  componentsModified  String    // JSON: ["frontend", "backend", "database"]
  filesTouched        String    // JSON: ["src/app.tsx", "api/route.ts"]
  linesAdded          Int?
  linesRemoved        Int?

  // Documentation
  architectureNotes   String?   // Architectural decisions made
  technicalNotes      String?   // Technical implementation notes
  challengesFaced     String?   // Challenges and how resolved
  lessonsLearned      String?   // Learnings for future reference

  // Linked Artifacts
  commitHashes        String?   // JSON array of commit hashes
  docFilePath         String?   // Path to generated MD file

  createdAt           DateTime  @default(now())
  updatedAt           DateTime  @updatedAt
}

// ========== EXTEND ISSUE MODEL ==========
model Issue {
  // ... existing fields ...

  // Implementation Documentation
  implementationSummary    String?   // Markdown: what was actually built
  technicalApproach        String?   // JSON: tech stack, patterns used
  relatedFeatureId         String?   // Link to related feature
  relatedFeature           Issue?    @relation("RelatedFeature", fields: [relatedFeatureId], references: [id])

  // Documentation References
  documentationPath        String?   // Path to MD file: /docs/features/CB-851.md

  // Enhanced Metadata
  estimatedHours           Float?    // Estimated hours
  actualHours              Float?    // Actual hours spent
  complexity               String?   // LOW, MEDIUM, HIGH, CRITICAL

  // Relations
  executionSummaries       ExecutionSummary[]
  relatedIssues            Issue[]   @relation("RelatedFeature")
}

// ========== NEW MODEL: FeatureDocumentation ==========
model FeatureDocumentation {
  id                  String    @id @default(cuid())
  projectId           String
  featureIssueId      String
  featureKey          String    // CB-851

  // Documentation Content
  title               String
  overview            String    // High-level summary
  requirements        String    // Original requirements
  implementation      String    // What was built
  architecture        String    // Architecture decisions
  techStack           String    // JSON: technologies used
  testingStrategy     String    // QA approach

  // Metrics
  totalTasks          Int
  completedTasks      Int
  totalQATasks        Int
  passedQATasks       Int
  failedQATasks       Int

  // File Reference
  mdFilePath          String    // /docs/features/CB-851.md

  // Indexing for RAG
  embeddingId         String?   // ChromaDB document ID
  lastIndexedAt       DateTime?

  createdAt           DateTime  @default(now())
  updatedAt           DateTime  @updatedAt
}

// ========== ENHANCE QA TASK MODEL ==========
model QATask {
  // ... existing fields ...

  // Enhanced Linking
  linkedFeatureId     String?   // Direct link to feature being tested
  linkedEpicId        String?
  linkedStoryId       String?
  linkedTaskId        String?

  // Context for RAG
  testContext         String?   // JSON: relevant docs, architecture notes

  // Results Context
  failureContext      String?   // JSON: what was happening when it failed
  environmentDetails  String?   // JSON: environment config during test
}
```

### 2. RAG Enhancement Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ChromaDB Collections                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │ project_{id}     │  │ project_{id}     │                 │
│  │ _issues          │  │ _documentation   │                 │
│  │ (existing)       │  │ (NEW)            │                 │
│  └──────────────────┘  └──────────────────┘                 │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │ project_{id}     │  │ project_{id}     │                 │
│  │ _qa_knowledge    │  │ _architecture    │                 │
│  │ (NEW)            │  │ (NEW)            │                 │
│  └──────────────────┘  └──────────────────┘                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘

Each collection stores:
- Issues: title, description, type, status, labels
- Documentation: implementation summaries, technical notes, lessons learned
- QA Knowledge: test scenarios, common failures, regression patterns
- Architecture: component relationships, tech decisions, patterns used
```

### 3. Documentation File Structure

```
project_root/
├── docs/
│   ├── features/
│   │   ├── CB-851_comprehensive_qa_system.md
│   │   ├── CB-502_user_authentication.md
│   │   └── index.md (auto-generated TOC)
│   │
│   ├── epics/
│   │   ├── CB-814_qa_panel_enhancements.md
│   │   └── index.md
│   │
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── frontend.md
│   │   ├── backend.md
│   │   └── database.md
│   │
│   └── qa/
│       ├── test_plans/
│       │   └── CB-851_test_plan.md
│       ├── results/
│       │   └── CB-851_qa_results.md
│       └── regression/
│           └── known_issues.md
```

---

## Implementation Plan

### Phase 1: Database Schema & Models (Backend)

**Tasks:**
1. Add new Prisma models: `ExecutionSummary`, `FeatureDocumentation`
2. Extend `Issue` model with new fields
3. Extend `QATask` model with linking fields
4. Create migrations
5. Update SQLAlchemy models for backend

**Files to modify:**
- `frontend/prisma/schema.prisma`
- `backend/models/issue.py`
- `backend/models/qa.py`

---

### Phase 2: Execution Summary Capture (Backend)

**Tasks:**
1. Create `documentation_service.py` to manage documentation
2. Modify `terminal_service.py` to capture execution metadata
3. Auto-generate execution summary after task completion
4. Store structured metadata (files touched, components, etc.)
5. Parse Claude Code output to extract insights

**New endpoints:**
```
POST /api/execute/session/{id}/summary - Generate summary from execution
GET  /api/issues/{id}/execution-history - Get all execution summaries
POST /api/issues/{id}/documentation - Create/update documentation
```

---

### Phase 3: RAG Enhancement (Backend)

**Tasks:**
1. Create new ChromaDB collections per project:
   - `{project_id}_documentation`
   - `{project_id}_qa_knowledge`
   - `{project_id}_architecture`
2. Index execution summaries into documentation collection
3. Index QA results into qa_knowledge collection
4. Create unified search across all collections
5. Add context retrieval for AI operations

**New service:**
```python
# backend/services/knowledge_service.py

class KnowledgeService:
    def index_execution_summary(project_id, issue_id, summary)
    def index_qa_result(project_id, qa_task_id, result)
    def search_relevant_context(project_id, query, types=[])
    def get_feature_context(project_id, feature_id)
    def get_implementation_patterns(project_id, component)
```

---

### Phase 4: MD File Generation (Backend)

**Tasks:**
1. Create MD templates for features, epics, stories, tasks
2. Auto-generate MD files on feature completion
3. Update index.md files automatically
4. Store file paths in database
5. Create file watching for manual edits

**Templates:**
```markdown
# Feature: {key} - {title}

## Overview
{overview}

## Requirements
{original_requirements}

## Implementation
{implementation_summary}

## Architecture
{architecture_decisions}

## Tech Stack
{technologies_used}

## Tasks Completed
{task_list}

## QA Summary
- Total Tests: {total_qa}
- Passed: {passed}
- Failed: {failed}

## Lessons Learned
{lessons}
```

---

### Phase 5: Smart AI Breakdown (Frontend + Backend)

**Tasks:**
1. Add "Link to Feature" dropdown in AI Breakdown modal
2. Fetch relevant context from RAG before generating
3. Include architecture docs in prompt
4. Show context sources to user
5. Allow user to add/remove context sources

**UI Changes to `AIBreakdownModal.tsx`:**
```tsx
// Add linking section
<div className="space-y-2">
  <label>Link to Existing Feature/Epic</label>
  <select value={linkedFeatureId} onChange={...}>
    <option value="">None</option>
    {features.map(f => <option key={f.id}>{f.key}: {f.title}</option>)}
  </select>
</div>

// Add context preview
<div className="border rounded p-3">
  <h4>Context Sources</h4>
  <ul>
    {contextSources.map(src => (
      <li key={src.id}>
        <input type="checkbox" checked={src.enabled} />
        {src.type}: {src.title}
      </li>
    ))}
  </ul>
</div>
```

**Backend Enhancement:**
```python
# ai_service.py - breakdown_feature()

async def breakdown_feature(
    title: str,
    description: str,
    project_id: str,
    linked_feature_id: str = None,  # NEW
    include_architecture: bool = True,  # NEW
    include_similar_features: bool = True,  # NEW
):
    # Gather context
    context = await knowledge_service.get_breakdown_context(
        project_id=project_id,
        linked_feature_id=linked_feature_id,
        include_architecture=include_architecture,
    )

    # Enhanced prompt with context
    prompt = f"""
    {context.architecture_summary}

    Similar features implemented:
    {context.similar_features}

    Patterns used in this project:
    {context.implementation_patterns}

    Now break down:
    Title: {title}
    Description: {description}
    """
```

---

### Phase 6: Smart QA Plan Generation (Frontend + Backend)

**Tasks:**
1. Fetch feature documentation before generating QA
2. Include execution summary context
3. Add known regression patterns
4. Link QA tasks to features/tasks
5. Generate contextual expected results

**Backend Enhancement:**
```python
# qa_service.py - generate_qa_plan()

async def generate_qa_plan(
    issue_id: str,
    project_id: str,
    include_feature_context: bool = True,  # NEW
    include_regression_patterns: bool = True,  # NEW
):
    # Gather context
    context = await knowledge_service.get_qa_context(
        project_id=project_id,
        issue_id=issue_id,
    )

    # Enhanced prompt
    prompt = f"""
    Feature Documentation:
    {context.feature_documentation}

    Implementation Details:
    {context.implementation_summary}

    Known Regression Patterns:
    {context.regression_patterns}

    Components Modified:
    {context.components}

    Generate QA plan for:
    {issue.title}
    {issue.description}
    """
```

---

### Phase 7: Enhanced Bug Creation (Frontend + Backend)

**Tasks:**
1. Add "Link to Feature" field in bug creation
2. Auto-populate from QA task context
3. Include implementation context in bug description
4. Link bugs in feature documentation
5. Track bug patterns per feature

**UI Changes to `CreateIssueModal.tsx`:**
```tsx
// For BUG type, show linking options
{issueType === 'BUG' && (
  <div className="space-y-2">
    <label>Related To</label>
    <select value={relatedFeatureId}>
      <option value="">Select feature/task</option>
      {/* Hierarchical list of features/epics/stories/tasks */}
    </select>

    <label>Reproduction Context</label>
    <textarea placeholder="Steps to reproduce from QA..." />
  </div>
)}
```

---

### Phase 8: Documentation UI (Frontend)

**Tasks:**
1. Create Documentation tab on issue detail pages
2. Show execution summaries timeline
3. Preview/edit MD files
4. Export documentation
5. Link to related docs

**New Component: `IssueDocumentation.tsx`**
```tsx
<Tabs>
  <Tab label="Overview">
    <MarkdownPreview content={issue.implementationSummary} />
  </Tab>
  <Tab label="Execution History">
    <ExecutionTimeline executions={executionSummaries} />
  </Tab>
  <Tab label="QA Results">
    <QAResultsSummary qaTaskIds={linkedQATasks} />
  </Tab>
  <Tab label="Related Docs">
    <DocumentationLinks files={relatedDocs} />
  </Tab>
</Tabs>
```

---

## Task Breakdown

### Epic: Documentation & RAG Knowledge System

#### Story 1: Database Schema Updates
- Task 1.1: Add ExecutionSummary model to Prisma
- Task 1.2: Add FeatureDocumentation model to Prisma
- Task 1.3: Extend Issue model with new fields
- Task 1.4: Extend QATask model with linking fields
- Task 1.5: Run migrations and update SQLAlchemy models

#### Story 2: Execution Summary Capture
- Task 2.1: Create DocumentationService
- Task 2.2: Capture execution metadata in terminal_service
- Task 2.3: Auto-generate summary on completion
- Task 2.4: Parse Claude output for insights
- Task 2.5: Create API endpoints

#### Story 3: RAG Knowledge Enhancement
- Task 3.1: Create new ChromaDB collections
- Task 3.2: Implement KnowledgeService
- Task 3.3: Index execution summaries
- Task 3.4: Index QA results
- Task 3.5: Implement unified context search

#### Story 4: MD File Generation
- Task 4.1: Create documentation templates
- Task 4.2: Implement MD file generator
- Task 4.3: Auto-generate on feature completion
- Task 4.4: Create index file updater
- Task 4.5: Store file paths in database

#### Story 5: Smart AI Breakdown
- Task 5.1: Add linking UI to AIBreakdownModal
- Task 5.2: Fetch RAG context for breakdown
- Task 5.3: Include architecture docs in prompt
- Task 5.4: Show context sources to user
- Task 5.5: Test contextual breakdown quality

#### Story 6: Smart QA Plan Generation
- Task 6.1: Add feature context to QA generation
- Task 6.2: Include implementation details
- Task 6.3: Add regression pattern awareness
- Task 6.4: Link QA tasks to features
- Task 6.5: Generate contextual expected results

#### Story 7: Enhanced Bug Creation
- Task 7.1: Add linking field to CreateIssueModal
- Task 7.2: Auto-populate from QA context
- Task 7.3: Include implementation context
- Task 7.4: Link bugs to features
- Task 7.5: Track bug patterns

#### Story 8: Documentation UI
- Task 8.1: Create IssueDocumentation component
- Task 8.2: Add Documentation tab to issue detail
- Task 8.3: Show execution timeline
- Task 8.4: Add MD file preview/edit
- Task 8.5: Export documentation functionality

---

## Success Metrics

1. **Documentation Coverage**: 100% of completed features have generated documentation
2. **QA Context Quality**: QA plans reference relevant implementation details
3. **Bug Linking**: 100% of bugs linked to related features/tasks
4. **AI Breakdown Quality**: Breakdown suggestions aligned with project architecture
5. **Search Relevance**: RAG searches return contextually relevant results

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Schema | 2-3 days | None |
| Phase 2: Execution Capture | 3-4 days | Phase 1 |
| Phase 3: RAG Enhancement | 4-5 days | Phase 1 |
| Phase 4: MD Generation | 2-3 days | Phase 2 |
| Phase 5: Smart Breakdown | 3-4 days | Phase 3 |
| Phase 6: Smart QA | 2-3 days | Phase 3 |
| Phase 7: Bug Creation | 2-3 days | Phase 1 |
| Phase 8: Documentation UI | 3-4 days | All |

**Total: ~25-30 days of development**

---

## Next Steps

1. Review and approve this plan
2. Create the feature in CodeBoard (CB-XXX)
3. Use AI Breakdown to generate the full hierarchy
4. Begin Phase 1 implementation
