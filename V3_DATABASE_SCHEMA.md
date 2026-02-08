# V3 Database Schema

## Overview

This document defines the database schema for the multi-agent system, including tables for agents, workflows, tasks, feedback, and learning.

---

## Database Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │    Core      │  │   Workflow   │  │   Feedback   │               │
│  │   Tables     │  │   Tables     │  │   Tables     │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         ChromaDB                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │    Agent     │  │    Code      │  │   Feedback   │               │
│  │   Memories   │  │   Patterns   │  │   Patterns   │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                          Redis                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   Message    │  │    Agent     │  │    Cache     │               │
│  │   Queues     │  │    State     │  │              │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## PostgreSQL Schema

### Core Tables

#### agents

```sql
CREATE TABLE agents (
    id VARCHAR(10) PRIMARY KEY,           -- e.g., 'O-1', 'S-1'
    name VARCHAR(100) NOT NULL,
    layer VARCHAR(20) NOT NULL,           -- orchestration, strategic, coordination, specialist, review, feedback
    type VARCHAR(50) NOT NULL,            -- specific agent type
    status VARCHAR(20) NOT NULL DEFAULT 'IDLE',

    -- Configuration
    config JSONB NOT NULL DEFAULT '{}',
    prompt_version VARCHAR(20) NOT NULL,
    max_concurrent_tasks INTEGER NOT NULL DEFAULT 1,

    -- Capabilities
    skills TEXT[] NOT NULL DEFAULT '{}',
    domains TEXT[] NOT NULL DEFAULT '{}',

    -- Tracking
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMP WITH TIME ZONE,

    -- Health
    health_status VARCHAR(20) NOT NULL DEFAULT 'HEALTHY',
    error_count INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT valid_layer CHECK (layer IN ('orchestration', 'strategic', 'coordination', 'specialist', 'review', 'feedback')),
    CONSTRAINT valid_status CHECK (status IN ('IDLE', 'BUSY', 'BLOCKED', 'ERROR', 'OFFLINE'))
);

CREATE INDEX idx_agents_layer ON agents(layer);
CREATE INDEX idx_agents_status ON agents(status);
```

#### projects

```sql
CREATE TABLE projects (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Configuration
    tech_stack TEXT[] NOT NULL DEFAULT '{}',
    repository_url VARCHAR(500),

    -- Settings
    settings JSONB NOT NULL DEFAULT '{}',

    -- Tracking
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT valid_status CHECK (status IN ('ACTIVE', 'ARCHIVED', 'DELETED'))
);

CREATE INDEX idx_projects_status ON projects(status);
```

### Workflow Tables

#### workflows

```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    type VARCHAR(20) NOT NULL,            -- SIMPLE, STANDARD, FULL
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    -- Relations
    project_id VARCHAR(50) NOT NULL REFERENCES projects(id),
    feature_request_id UUID REFERENCES feature_requests(id),

    -- Structure
    stages JSONB NOT NULL DEFAULT '[]',
    dependencies JSONB NOT NULL DEFAULT '[]',

    -- Progress
    current_stage_id VARCHAR(50),
    progress INTEGER NOT NULL DEFAULT 0,  -- 0-100

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    deadline TIMESTAMP WITH TIME ZONE,

    -- Metrics
    estimated_hours DECIMAL(10,2),
    actual_hours DECIMAL(10,2),

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',

    CONSTRAINT valid_type CHECK (type IN ('SIMPLE', 'STANDARD', 'FULL')),
    CONSTRAINT valid_status CHECK (status IN ('PENDING', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'FAILED', 'CANCELLED'))
);

CREATE INDEX idx_workflows_project ON workflows(project_id);
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_created ON workflows(created_at DESC);
```

#### workflow_stages

```sql
CREATE TABLE workflow_stages (
    id VARCHAR(50) PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    sequence INTEGER NOT NULL,

    -- Assignment
    assigned_agents TEXT[] NOT NULL DEFAULT '{}',
    required_agents TEXT[] NOT NULL DEFAULT '{}',

    -- Timing
    timeout_minutes INTEGER NOT NULL DEFAULT 60,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- I/O
    inputs JSONB NOT NULL DEFAULT '[]',
    outputs JSONB NOT NULL DEFAULT '[]',

    -- Quality
    quality_gate JSONB,

    -- Progress
    progress INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT valid_type CHECK (type IN (
        'ARCHITECTURE', 'SECURITY_REVIEW', 'DESIGN', 'BREAKDOWN',
        'IMPLEMENTATION', 'TESTING', 'CODE_REVIEW', 'SECURITY_TESTING',
        'PERFORMANCE_TESTING', 'FINAL_REVIEW', 'APPROVAL'
    )),
    CONSTRAINT valid_status CHECK (status IN (
        'PENDING', 'READY', 'IN_PROGRESS', 'REVIEW_PENDING',
        'COMPLETED', 'FAILED', 'SKIPPED'
    ))
);

CREATE INDEX idx_stages_workflow ON workflow_stages(workflow_id);
CREATE INDEX idx_stages_status ON workflow_stages(status);
```

#### feature_requests

```sql
CREATE TABLE feature_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(50) NOT NULL REFERENCES projects(id),

    -- Content
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',

    -- Requirements
    functional_requirements TEXT[] NOT NULL DEFAULT '{}',
    non_functional_requirements TEXT[] NOT NULL DEFAULT '{}',

    -- Constraints
    constraints JSONB NOT NULL DEFAULT '[]',
    deadline TIMESTAMP WITH TIME ZONE,

    -- Source
    requested_by VARCHAR(200),
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'SUBMITTED',
    workflow_id UUID REFERENCES workflows(id),

    CONSTRAINT valid_priority CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT valid_status CHECK (status IN (
        'SUBMITTED', 'ACCEPTED', 'IN_PROGRESS', 'COMPLETED', 'REJECTED', 'ON_HOLD'
    ))
);

CREATE INDEX idx_features_project ON feature_requests(project_id);
CREATE INDEX idx_features_status ON feature_requests(status);
```

### Task Tables

#### epics

```sql
CREATE TABLE epics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(20) NOT NULL UNIQUE,      -- e.g., 'CB-101'
    project_id VARCHAR(50) NOT NULL REFERENCES projects(id),
    workflow_id UUID REFERENCES workflows(id),

    -- Content
    title VARCHAR(300) NOT NULL,
    description TEXT,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'BACKLOG',
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',

    -- Tracking
    total_points INTEGER NOT NULL DEFAULT 0,
    completed_points INTEGER NOT NULL DEFAULT 0,
    progress INTEGER NOT NULL DEFAULT 0,

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    due_date TIMESTAMP WITH TIME ZONE,

    -- Estimation
    estimated_duration INTERVAL,
    actual_duration INTERVAL,

    CONSTRAINT valid_status CHECK (status IN (
        'BACKLOG', 'TODO', 'IN_PROGRESS', 'IN_REVIEW', 'DONE', 'BLOCKED', 'CANCELLED'
    ))
);

CREATE INDEX idx_epics_project ON epics(project_id);
CREATE INDEX idx_epics_status ON epics(status);
CREATE INDEX idx_epics_key ON epics(key);
```

#### stories

```sql
CREATE TABLE stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(20) NOT NULL UNIQUE,
    epic_id UUID NOT NULL REFERENCES epics(id) ON DELETE CASCADE,

    -- Content
    title VARCHAR(300) NOT NULL,          -- "User can {action} so that {benefit}"
    description TEXT,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'BACKLOG',
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    story_points INTEGER,

    -- Acceptance
    acceptance_criteria JSONB NOT NULL DEFAULT '[]',

    -- Assignment
    assigned_agent VARCHAR(10) REFERENCES agents(id),

    -- Dependencies
    depends_on UUID[] NOT NULL DEFAULT '{}',
    blocks UUID[] NOT NULL DEFAULT '{}',

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT valid_status CHECK (status IN (
        'BACKLOG', 'TODO', 'IN_PROGRESS', 'IN_REVIEW', 'DONE', 'BLOCKED', 'CANCELLED'
    ))
);

CREATE INDEX idx_stories_epic ON stories(epic_id);
CREATE INDEX idx_stories_status ON stories(status);
CREATE INDEX idx_stories_agent ON stories(assigned_agent);
```

#### tasks

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(20) NOT NULL UNIQUE,
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,

    -- Content
    title VARCHAR(300) NOT NULL,          -- "{Verb} {component} for {purpose}"
    description TEXT,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'BACKLOG',
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',

    -- Assignment
    assigned_agent VARCHAR(10) REFERENCES agents(id),
    specialist_type VARCHAR(30),

    -- Estimation
    estimated_hours DECIMAL(5,2),
    actual_hours DECIMAL(5,2),

    -- Definition of Done
    definition_of_done JSONB NOT NULL DEFAULT '[]',

    -- Dependencies
    depends_on UUID[] NOT NULL DEFAULT '{}',
    blocks UUID[] NOT NULL DEFAULT '{}',

    -- Output
    outputs JSONB NOT NULL DEFAULT '[]',

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Review
    review_status VARCHAR(20),
    review_comments JSONB,

    CONSTRAINT valid_status CHECK (status IN (
        'BACKLOG', 'TODO', 'IN_PROGRESS', 'IN_REVIEW', 'DONE', 'BLOCKED', 'CANCELLED'
    ))
);

CREATE INDEX idx_tasks_story ON tasks(story_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_agent ON tasks(assigned_agent);
```

#### subtasks

```sql
CREATE TABLE subtasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(20) NOT NULL UNIQUE,
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,

    -- Content
    title VARCHAR(300) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'TODO',

    -- Estimation
    estimated_minutes INTEGER,
    actual_minutes INTEGER,

    -- Timing
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Order
    sequence INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT valid_status CHECK (status IN ('TODO', 'DONE'))
);

CREATE INDEX idx_subtasks_task ON subtasks(task_id);
```

### Message Tables

#### messages

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id UUID NOT NULL,

    -- Routing
    from_agent VARCHAR(10) NOT NULL,
    to_agents TEXT[] NOT NULL,

    -- Type
    type VARCHAR(30) NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',

    -- Content
    payload JSONB NOT NULL,

    -- Metadata
    workflow_id UUID REFERENCES workflows(id),
    task_id UUID,

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    processed_at TIMESTAMP WITH TIME ZONE,

    -- Retry
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,

    CONSTRAINT valid_type CHECK (type IN (
        'TASK_ASSIGNMENT', 'TASK_COMPLETION', 'TASK_FAILURE', 'TASK_PROGRESS',
        'QUESTION', 'ANSWER', 'FEEDBACK', 'REVIEW_REQUEST', 'REVIEW_RESULT',
        'ESCALATION', 'STATUS_UPDATE', 'COORDINATION', 'SYSTEM'
    )),
    CONSTRAINT valid_status CHECK (status IN (
        'PENDING', 'PROCESSING', 'DELIVERED', 'FAILED', 'EXPIRED'
    ))
);

CREATE INDEX idx_messages_correlation ON messages(correlation_id);
CREATE INDEX idx_messages_from ON messages(from_agent);
CREATE INDEX idx_messages_to ON messages USING GIN(to_agents);
CREATE INDEX idx_messages_workflow ON messages(workflow_id);
CREATE INDEX idx_messages_status ON messages(status);
CREATE INDEX idx_messages_created ON messages(created_at DESC);
```

### Feedback Tables

#### quality_reports

```sql
CREATE TABLE quality_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(10) NOT NULL REFERENCES agents(id),
    task_id UUID NOT NULL REFERENCES tasks(id),

    -- Scores
    overall_score INTEGER NOT NULL,       -- 0-100
    correctness_score INTEGER NOT NULL,
    completeness_score INTEGER NOT NULL,
    quality_score INTEGER NOT NULL,
    efficiency_score INTEGER NOT NULL,

    -- Details
    issues JSONB NOT NULL DEFAULT '[]',
    positives TEXT[] NOT NULL DEFAULT '{}',
    recommendations TEXT[] NOT NULL DEFAULT '{}',

    -- Patterns
    patterns_detected JSONB NOT NULL DEFAULT '[]',

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_quality_agent ON quality_reports(agent_id);
CREATE INDEX idx_quality_task ON quality_reports(task_id);
CREATE INDEX idx_quality_created ON quality_reports(created_at DESC);
```

#### performance_metrics

```sql
CREATE TABLE performance_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(10) NOT NULL REFERENCES agents(id),
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    period_type VARCHAR(10) NOT NULL,     -- DAILY, WEEKLY, MONTHLY

    -- Task Metrics
    tasks_assigned INTEGER NOT NULL DEFAULT 0,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    tasks_failed INTEGER NOT NULL DEFAULT 0,

    -- Quality Metrics
    avg_quality_score DECIMAL(5,2),
    quality_trend VARCHAR(20),

    -- Efficiency Metrics
    avg_duration_minutes DECIMAL(10,2),
    duration_trend VARCHAR(20),

    -- Success Metrics
    first_attempt_success_rate DECIMAL(5,2),
    revision_rate DECIMAL(5,2),
    escalation_rate DECIMAL(5,2),

    -- Learning Metrics
    improvement_rate DECIMAL(5,2),
    patterns_learned INTEGER NOT NULL DEFAULT 0,
    feedback_incorporation_rate DECIMAL(5,2),

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_period CHECK (period_type IN ('DAILY', 'WEEKLY', 'MONTHLY')),
    CONSTRAINT valid_trend CHECK (quality_trend IN ('IMPROVING', 'STABLE', 'DECLINING') OR quality_trend IS NULL)
);

CREATE INDEX idx_metrics_agent ON performance_metrics(agent_id);
CREATE INDEX idx_metrics_period ON performance_metrics(period_start, period_end);
CREATE UNIQUE INDEX idx_metrics_unique ON performance_metrics(agent_id, period_start, period_type);
```

#### learning_events

```sql
CREATE TABLE learning_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(10) NOT NULL REFERENCES agents(id),

    -- Pattern
    pattern_type VARCHAR(20) NOT NULL,    -- MISTAKE, SUCCESS, INSIGHT
    pattern_name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,

    -- Frequency
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Impact
    impact_score INTEGER NOT NULL,        -- 0-100
    affected_metric VARCHAR(50),

    -- Action
    suggested_action JSONB,
    action_taken TEXT,
    action_effective BOOLEAN,
    action_taken_at TIMESTAMP WITH TIME ZONE,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',

    CONSTRAINT valid_pattern_type CHECK (pattern_type IN ('MISTAKE', 'SUCCESS', 'INSIGHT')),
    CONSTRAINT valid_status CHECK (status IN ('NEW', 'ACKNOWLEDGED', 'ACTIONED', 'RESOLVED', 'IGNORED'))
);

CREATE INDEX idx_learning_agent ON learning_events(agent_id);
CREATE INDEX idx_learning_pattern ON learning_events(pattern_type, pattern_name);
CREATE INDEX idx_learning_status ON learning_events(status);
```

#### prompt_versions

```sql
CREATE TABLE prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(10) NOT NULL REFERENCES agents(id),
    version VARCHAR(20) NOT NULL,

    -- Content
    system_prompt TEXT NOT NULL,
    task_prompts JSONB NOT NULL DEFAULT '{}',

    -- Metadata
    changes TEXT[],
    based_on_learning UUID[] REFERENCES learning_events(id),

    -- Performance
    avg_quality_score DECIMAL(5,2),
    sample_size INTEGER NOT NULL DEFAULT 0,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMP WITH TIME ZONE,
    deprecated_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT valid_status CHECK (status IN ('DRAFT', 'TESTING', 'ACTIVE', 'DEPRECATED'))
);

CREATE INDEX idx_prompts_agent ON prompt_versions(agent_id);
CREATE INDEX idx_prompts_version ON prompt_versions(agent_id, version);
CREATE INDEX idx_prompts_status ON prompt_versions(status);
```

---

## ChromaDB Collections

### agent_memories

```python
# Collection: agent_memories
# Purpose: Store agent task memories for context retrieval

collection_schema = {
    "name": "agent_memories",
    "metadata": {
        "hnsw:space": "cosine"
    }
}

document_schema = {
    "id": "string",           # UUID
    "content": "string",      # Embedded text (task + solution)
    "metadata": {
        "agent_id": "string",
        "task_id": "string",
        "task_type": "string",
        "quality_score": "number",
        "created_at": "string",
        "project_id": "string",
        "domain": "string"
    }
}
```

### code_patterns

```python
# Collection: code_patterns
# Purpose: Store successful code patterns for reuse

collection_schema = {
    "name": "code_patterns",
    "metadata": {
        "hnsw:space": "cosine"
    }
}

document_schema = {
    "id": "string",
    "content": "string",      # Pattern description + code
    "metadata": {
        "pattern_type": "string",  # component, hook, service, etc.
        "language": "string",
        "framework": "string",
        "usage_count": "number",
        "avg_quality": "number",
        "tags": ["string"]
    }
}
```

### feedback_patterns

```python
# Collection: feedback_patterns
# Purpose: Store feedback patterns for learning

collection_schema = {
    "name": "feedback_patterns",
    "metadata": {
        "hnsw:space": "cosine"
    }
}

document_schema = {
    "id": "string",
    "content": "string",      # Pattern description
    "metadata": {
        "pattern_type": "string",  # MISTAKE or SUCCESS
        "agent_id": "string",
        "frequency": "number",
        "impact": "number",
        "resolved": "boolean"
    }
}
```

---

## Redis Structures

### Message Queues

```redis
# Priority queues per agent
# Key: agent:{agent_id}:queue:{priority}
# Type: Stream

XADD agent:I-1:queue:high * message_id "uuid" payload "{json}"

# Consumer groups for processing
XGROUP CREATE agent:I-1:queue:high agent_group $ MKSTREAM
```

### Agent State

```redis
# Agent status
# Key: agent:{agent_id}:status
# Type: Hash

HSET agent:I-1:status \
    status "BUSY" \
    current_task "uuid" \
    queue_length "3" \
    last_activity "2024-01-15T10:30:00Z"

# Agent locks (for task assignment)
# Key: agent:{agent_id}:lock
# Type: String with TTL

SET agent:I-1:lock "workflow_uuid" EX 300 NX
```

### Cache

```redis
# Workflow cache
# Key: workflow:{id}
# Type: String (JSON)
# TTL: 1 hour

SET workflow:uuid "{json}" EX 3600

# Agent capabilities cache
# Key: agent:{id}:capabilities
# Type: Set

SADD agent:I-1:capabilities "component_create" "hook_create" "style_create"

# Recent tasks cache (for context)
# Key: agent:{id}:recent_tasks
# Type: List (limited to 10)

LPUSH agent:I-1:recent_tasks "{task_summary_json}"
LTRIM agent:I-1:recent_tasks 0 9
```

---

## Migrations

### Initial Migration (V1)

```sql
-- V1: Initial schema
-- Run: CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create all tables in dependency order:
-- 1. agents
-- 2. projects
-- 3. workflows, feature_requests
-- 4. workflow_stages
-- 5. epics
-- 6. stories
-- 7. tasks
-- 8. subtasks
-- 9. messages
-- 10. quality_reports, performance_metrics, learning_events, prompt_versions

-- Create all indexes
-- Create all constraints
```

### Seed Data

```sql
-- Seed agents
INSERT INTO agents (id, name, layer, type, skills, domains, prompt_version) VALUES
('O-1', 'System Orchestrator', 'orchestration', 'orchestrator',
 ARRAY['workflow_create', 'agent_assign', 'escalate'], ARRAY['all'], 'v1.0'),

('S-1', 'Solution Architect', 'strategic', 'architect',
 ARRAY['design_system', 'create_adr', 'risk_assess'], ARRAY['architecture', 'design'], 'v1.0'),

('S-2', 'Project Manager', 'strategic', 'manager',
 ARRAY['breakdown_epic', 'breakdown_story', 'dependency_map'], ARRAY['planning'], 'v1.0'),

-- ... continue for all agents
;
```

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-02-07 | Claude | Initial schema |
