# V3 Message & Data Schemas

## Overview

This document defines all message formats, API schemas, and data structures for the multi-agent system.

---

## Table of Contents

1. [Agent Messages](#agent-messages)
2. [Workflow Schemas](#workflow-schemas)
3. [Task Schemas](#task-schemas)
4. [Feedback Schemas](#feedback-schemas)
5. [API Schemas](#api-schemas)

---

## Agent Messages

### Base Message

```typescript
interface AgentMessage {
  // Identity
  id: string;                      // UUID v4
  correlationId: string;           // Links related messages

  // Routing
  from: AgentId;                   // Sender agent ID
  to: AgentId | AgentId[];         // Recipient(s)

  // Type
  type: MessageType;
  priority: Priority;

  // Content
  payload: MessagePayload;

  // Metadata
  timestamp: string;               // ISO 8601
  expiresAt?: string;              // TTL
  metadata: MessageMetadata;
}

type AgentId =
  | 'O-1'                          // Orchestrator
  | 'S-1' | 'S-2' | 'S-3' | 'S-4'  // Strategic
  | 'C-1' | 'C-2' | 'C-3' | 'C-4'  // Coordination
  | 'I-1' | 'I-2' | 'I-3' | 'I-4' | 'I-5' | 'I-6'  // Implementation
  | 'T-1' | 'T-2' | 'T-3' | 'T-4' | 'T-5' | 'T-6'  // Testing
  | 'R-1' | 'R-2' | 'R-3' | 'R-4'  // Review
  | 'F-1' | 'F-2' | 'F-3' | 'F-4'  // Feedback
  | 'HUMAN';                       // Human operator

type MessageType =
  | 'TASK_ASSIGNMENT'
  | 'TASK_COMPLETION'
  | 'TASK_FAILURE'
  | 'TASK_PROGRESS'
  | 'QUESTION'
  | 'ANSWER'
  | 'FEEDBACK'
  | 'REVIEW_REQUEST'
  | 'REVIEW_RESULT'
  | 'ESCALATION'
  | 'STATUS_UPDATE'
  | 'COORDINATION'
  | 'SYSTEM';

type Priority = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

interface MessageMetadata {
  workflowId?: string;
  taskId?: string;
  stageId?: string;
  retryCount: number;
  parentMessageId?: string;
  traceId?: string;
}
```

### Task Assignment Message

```typescript
interface TaskAssignmentMessage extends AgentMessage {
  type: 'TASK_ASSIGNMENT';
  payload: {
    task: TaskDefinition;
    context: TaskContext;
    deadline?: string;
    predecessorOutputs?: Record<string, any>;
  };
}

interface TaskDefinition {
  id: string;
  title: string;
  description: string;
  type: TaskType;
  priority: Priority;
  requirements: string[];
  definitionOfDone: string[];
  estimatedHours: number;
}

type TaskType =
  | 'ARCHITECTURE'
  | 'DESIGN'
  | 'BREAKDOWN'
  | 'IMPLEMENTATION'
  | 'TEST'
  | 'REVIEW'
  | 'DOCUMENTATION';

interface TaskContext {
  projectId: string;
  projectName: string;
  workflowId: string;
  stageId: string;
  relatedIssues: string[];
  codebaseContext?: CodebaseContext;
  architectureContext?: ArchitectureContext;
  securityContext?: SecurityContext;
}

interface CodebaseContext {
  relevantFiles: FileInfo[];
  patterns: Pattern[];
  dependencies: Dependency[];
}

interface FileInfo {
  path: string;
  content?: string;
  summary?: string;
}
```

### Task Completion Message

```typescript
interface TaskCompletionMessage extends AgentMessage {
  type: 'TASK_COMPLETION';
  payload: {
    taskId: string;
    status: 'SUCCESS' | 'PARTIAL';
    outputs: TaskOutput[];
    metrics: TaskMetrics;
    notes?: string;
  };
}

interface TaskOutput {
  type: OutputType;
  path?: string;
  content: any;
  format: string;
}

type OutputType =
  | 'CODE'
  | 'DOCUMENT'
  | 'SCHEMA'
  | 'CONFIG'
  | 'TEST'
  | 'DIAGRAM'
  | 'REPORT';

interface TaskMetrics {
  startTime: string;
  endTime: string;
  durationMinutes: number;
  tokensUsed: number;
  iterationCount: number;
  toolCallCount: number;
}
```

### Task Failure Message

```typescript
interface TaskFailureMessage extends AgentMessage {
  type: 'TASK_FAILURE';
  payload: {
    taskId: string;
    error: ErrorInfo;
    attemptsMade: number;
    partialOutput?: TaskOutput[];
    recoverable: boolean;
    suggestedAction?: SuggestedAction;
  };
}

interface ErrorInfo {
  code: string;
  message: string;
  details?: any;
  stack?: string;
}

type SuggestedAction =
  | { type: 'RETRY'; delay?: number }
  | { type: 'REASSIGN'; suggestedAgent?: AgentId }
  | { type: 'ESCALATE'; level: 'COORDINATION' | 'STRATEGIC' | 'HUMAN' }
  | { type: 'SKIP'; reason: string }
  | { type: 'ABORT'; reason: string };
```

### Question Message

```typescript
interface QuestionMessage extends AgentMessage {
  type: 'QUESTION';
  payload: {
    taskId: string;
    question: string;
    questionType: QuestionType;
    options?: string[];
    context: string;
    blocksProgress: boolean;
  };
}

type QuestionType =
  | 'CLARIFICATION'      // Need more info about requirements
  | 'DECISION'           // Need decision between options
  | 'APPROVAL'           // Need approval to proceed
  | 'TECHNICAL'          // Technical question
  | 'RESOURCE';          // Need resource/access
```

### Answer Message

```typescript
interface AnswerMessage extends AgentMessage {
  type: 'ANSWER';
  payload: {
    questionId: string;   // ID of the question message
    answer: string;
    additionalContext?: any;
  };
}
```

### Review Request Message

```typescript
interface ReviewRequestMessage extends AgentMessage {
  type: 'REVIEW_REQUEST';
  payload: {
    taskId: string;
    reviewType: ReviewType;
    artifacts: Artifact[];
    context: ReviewContext;
    urgency: Priority;
  };
}

type ReviewType =
  | 'CODE'
  | 'SECURITY'
  | 'PERFORMANCE'
  | 'ARCHITECTURE'
  | 'FINAL';

interface Artifact {
  type: OutputType;
  path: string;
  content?: string;
  diff?: string;
}

interface ReviewContext {
  requirements: string[];
  standards: string[];
  previousReviews?: ReviewResult[];
}
```

### Review Result Message

```typescript
interface ReviewResultMessage extends AgentMessage {
  type: 'REVIEW_RESULT';
  payload: {
    reviewId: string;
    taskId: string;
    status: ReviewStatus;
    comments: ReviewComment[];
    summary: string;
    qualityScore: number;          // 0-100
    blockingIssues: string[];
    suggestions: string[];
  };
}

type ReviewStatus =
  | 'APPROVED'
  | 'APPROVED_WITH_COMMENTS'
  | 'CHANGES_REQUESTED'
  | 'REJECTED';

interface ReviewComment {
  id: string;
  file?: string;
  line?: number;
  severity: CommentSeverity;
  category: CommentCategory;
  message: string;
  suggestion?: string;
  codeExample?: string;
}

type CommentSeverity = 'CRITICAL' | 'MAJOR' | 'MINOR' | 'SUGGESTION';

type CommentCategory =
  | 'FUNCTIONALITY'
  | 'SECURITY'
  | 'PERFORMANCE'
  | 'STYLE'
  | 'DOCUMENTATION'
  | 'TESTING'
  | 'ARCHITECTURE';
```

### Escalation Message

```typescript
interface EscalationMessage extends AgentMessage {
  type: 'ESCALATION';
  payload: {
    taskId: string;
    level: EscalationLevel;
    reason: string;
    context: any;
    attemptedResolutions: string[];
    suggestedResolution?: string;
    blockedItems: string[];
  };
}

type EscalationLevel =
  | 'COORDINATION'    // To Tech Lead, QA Lead, etc.
  | 'STRATEGIC'       // To Solution Architect, PM, etc.
  | 'HUMAN';          // To human operator
```

### Feedback Message

```typescript
interface FeedbackMessage extends AgentMessage {
  type: 'FEEDBACK';
  payload: {
    taskId: string;
    feedbackType: FeedbackType;
    qualityScore: QualityScore;
    dimensionScores: DimensionScores;
    issues: Issue[];
    positives: string[];
    recommendations: string[];
    learningPatterns?: LearningPattern[];
  };
}

type FeedbackType =
  | 'QUALITY_AUDIT'
  | 'PERFORMANCE_REVIEW'
  | 'LEARNING_INSIGHT';

interface QualityScore {
  overall: number;           // 0-100
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
}

interface DimensionScores {
  correctness: number;       // 0-100
  completeness: number;      // 0-100
  quality: number;           // 0-100
  efficiency: number;        // 0-100
}

interface Issue {
  severity: CommentSeverity;
  category: string;
  description: string;
  location?: string;
  recommendation: string;
}

interface LearningPattern {
  patternId: string;
  patternType: 'MISTAKE' | 'SUCCESS';
  description: string;
  frequency: number;
  suggestedPromptUpdate?: string;
}
```

---

## Workflow Schemas

### Workflow Definition

```typescript
interface WorkflowDefinition {
  id: string;
  name: string;
  description: string;
  type: WorkflowType;
  status: WorkflowStatus;

  // Timing
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  deadline?: string;

  // Structure
  stages: Stage[];
  dependencies: StageDependency[];

  // Tracking
  currentStage?: string;
  progress: WorkflowProgress;

  // Context
  projectId: string;
  featureRequest: FeatureRequest;

  // Metrics
  metrics: WorkflowMetrics;
}

type WorkflowType =
  | 'SIMPLE'           // Design → Implement → Test → Review
  | 'STANDARD'         // Architecture → Design → Implement → Test → Review → Approve
  | 'FULL';            // Full pipeline with security and performance reviews

type WorkflowStatus =
  | 'PENDING'
  | 'IN_PROGRESS'
  | 'BLOCKED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

interface Stage {
  id: string;
  name: string;
  type: StageType;
  status: StageStatus;

  // Assignment
  assignedAgents: AgentId[];
  requiredAgents: AgentId[];

  // Timing
  startedAt?: string;
  completedAt?: string;
  timeoutMinutes: number;

  // I/O
  inputs: StageInput[];
  outputs: StageOutput[];

  // Quality
  qualityGate?: QualityGate;

  // Tracking
  tasks: string[];           // Task IDs
  progress: number;          // 0-100
}

type StageType =
  | 'ARCHITECTURE'
  | 'SECURITY_REVIEW'
  | 'DESIGN'
  | 'BREAKDOWN'
  | 'IMPLEMENTATION'
  | 'TESTING'
  | 'CODE_REVIEW'
  | 'SECURITY_TESTING'
  | 'PERFORMANCE_TESTING'
  | 'FINAL_REVIEW'
  | 'APPROVAL';

type StageStatus =
  | 'PENDING'
  | 'READY'              // Dependencies met
  | 'IN_PROGRESS'
  | 'REVIEW_PENDING'
  | 'COMPLETED'
  | 'FAILED'
  | 'SKIPPED';

interface StageDependency {
  from: string;           // Stage ID
  to: string;             // Stage ID
  type: DependencyType;
}

type DependencyType =
  | 'BLOCKS'              // Must complete before
  | 'INFORMS';            // Provides input to

interface QualityGate {
  id: string;
  name: string;
  criteria: GateCriterion[];
  requiredApprovers: AgentId[];
  autoApprove: boolean;
}

interface GateCriterion {
  name: string;
  type: 'AUTOMATED' | 'MANUAL';
  check: string;
  required: boolean;
}
```

### Feature Request

```typescript
interface FeatureRequest {
  id: string;
  title: string;
  description: string;
  priority: Priority;

  // Requirements
  functionalRequirements: string[];
  nonFunctionalRequirements: string[];

  // Constraints
  constraints: Constraint[];
  deadline?: string;

  // Source
  requestedBy: string;
  requestedAt: string;

  // Tracking
  status: FeatureStatus;
  workflowId?: string;
}

interface Constraint {
  type: 'TECH_STACK' | 'TIMELINE' | 'BUDGET' | 'RESOURCE' | 'COMPATIBILITY';
  description: string;
  value?: any;
}

type FeatureStatus =
  | 'SUBMITTED'
  | 'ACCEPTED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'REJECTED'
  | 'ON_HOLD';
```

---

## Task Schemas

### Work Item Hierarchy

```typescript
interface Epic {
  id: string;
  key: string;                    // e.g., "CB-101"
  title: string;
  description: string;
  status: IssueStatus;
  priority: Priority;

  // Hierarchy
  projectId: string;
  stories: string[];              // Story IDs

  // Tracking
  totalPoints: number;
  completedPoints: number;
  progress: number;               // 0-100

  // Timing
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  dueDate?: string;

  // Estimation
  estimatedDuration: string;      // e.g., "2 weeks"
  actualDuration?: string;
}

interface Story {
  id: string;
  key: string;                    // e.g., "CB-102"
  title: string;                  // "User can {action} so that {benefit}"
  description: string;
  status: IssueStatus;
  priority: Priority;
  storyPoints: number;

  // Hierarchy
  epicId: string;
  tasks: string[];                // Task IDs

  // Acceptance
  acceptanceCriteria: AcceptanceCriterion[];

  // Dependencies
  dependsOn: string[];            // Story IDs
  blocks: string[];               // Story IDs

  // Assignment
  assignedAgent?: AgentId;

  // Timing
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
}

interface AcceptanceCriterion {
  id: string;
  given: string;
  when: string;
  then: string;
  verified: boolean;
}

interface Task {
  id: string;
  key: string;                    // e.g., "CB-103"
  title: string;                  // "{Verb} {component} for {purpose}"
  description: string;
  status: IssueStatus;
  priority: Priority;

  // Hierarchy
  storyId: string;
  subtasks: string[];             // Subtask IDs

  // Assignment
  assignedAgent: AgentId;
  specialistType: SpecialistType;

  // Estimation
  estimatedHours: number;
  actualHours?: number;

  // Definition of Done
  definitionOfDone: DoD[];

  // Dependencies
  dependsOn: string[];            // Task IDs
  blocks: string[];               // Task IDs

  // Timing
  createdAt: string;
  startedAt?: string;
  completedAt?: string;

  // Output
  outputs?: TaskOutput[];
}

interface Subtask {
  id: string;
  key: string;                    // e.g., "CB-104"
  title: string;
  status: SubtaskStatus;

  // Hierarchy
  taskId: string;

  // Estimation
  estimatedMinutes: number;
  actualMinutes?: number;

  // Timing
  completedAt?: string;
}

type SpecialistType =
  | 'FRONTEND'
  | 'BACKEND'
  | 'DATABASE'
  | 'API'
  | 'AUTH'
  | 'UI_UX'
  | 'UNIT_TEST'
  | 'INTEGRATION_TEST'
  | 'E2E_TEST'
  | 'SECURITY_TEST'
  | 'PERFORMANCE_TEST'
  | 'ACCESSIBILITY_TEST';

interface DoD {
  id: string;
  description: string;
  completed: boolean;
  verifiedBy?: AgentId;
  verifiedAt?: string;
}

type IssueStatus =
  | 'BACKLOG'
  | 'TODO'
  | 'IN_PROGRESS'
  | 'IN_REVIEW'
  | 'DONE'
  | 'BLOCKED'
  | 'CANCELLED';

type SubtaskStatus = 'TODO' | 'DONE';
```

---

## Feedback Schemas

### Agent Performance

```typescript
interface AgentPerformance {
  agentId: AgentId;
  period: Period;

  // Task Metrics
  tasksAssigned: number;
  tasksCompleted: number;
  tasksFailed: number;

  // Quality Metrics
  averageQualityScore: number;
  qualityTrend: Trend;

  // Efficiency Metrics
  averageDuration: number;        // Minutes
  durationTrend: Trend;

  // Success Metrics
  firstAttemptSuccessRate: number;
  revisionRate: number;
  escalationRate: number;

  // Learning Metrics
  improvementRate: number;
  patternsLearned: number;
  feedbackIncorporation: number;
}

interface Period {
  start: string;
  end: string;
  type: 'DAILY' | 'WEEKLY' | 'MONTHLY';
}

type Trend = 'IMPROVING' | 'STABLE' | 'DECLINING';
```

### Quality Report

```typescript
interface QualityReport {
  id: string;
  agentId: AgentId;
  taskId: string;
  timestamp: string;

  // Scores
  overallScore: number;           // 0-100

  dimensions: {
    correctness: DimensionScore;
    completeness: DimensionScore;
    quality: DimensionScore;
    efficiency: DimensionScore;
  };

  // Issues
  issues: QualityIssue[];

  // Recommendations
  recommendations: Recommendation[];

  // Patterns
  patternsDetected: PatternMatch[];
}

interface DimensionScore {
  score: number;                  // 0-100
  weight: number;                 // 0-1
  factors: ScoringFactor[];
}

interface ScoringFactor {
  name: string;
  score: number;
  notes?: string;
}

interface QualityIssue {
  id: string;
  severity: CommentSeverity;
  category: string;
  description: string;
  location?: string;
  impact: string;
  fixSuggestion: string;
}

interface Recommendation {
  type: 'PROCESS' | 'SKILL' | 'TOOL';
  description: string;
  priority: Priority;
}

interface PatternMatch {
  patternId: string;
  patternName: string;
  type: 'POSITIVE' | 'NEGATIVE';
  confidence: number;             // 0-1
}
```

### Learning Event

```typescript
interface LearningEvent {
  id: string;
  timestamp: string;

  // Source
  agentId: AgentId;
  taskId: string;

  // Pattern
  patternType: 'MISTAKE' | 'SUCCESS' | 'INSIGHT';
  patternName: string;
  description: string;

  // Frequency
  occurrenceCount: number;
  firstSeen: string;
  lastSeen: string;

  // Impact
  impactScore: number;            // 0-100
  affectedMetric: string;

  // Action
  suggestedAction: LearningAction;
  actionTaken?: string;
  actionEffective?: boolean;
}

interface LearningAction {
  type: 'PROMPT_UPDATE' | 'CHECKLIST_ADD' | 'GUIDANCE_ADD' | 'TRAINING';
  description: string;
  content?: string;
}
```

---

## API Schemas

### External API

```typescript
// POST /api/v1/workflows
interface CreateWorkflowRequest {
  feature: {
    title: string;
    description: string;
    priority?: Priority;
    requirements?: {
      functional?: string[];
      nonFunctional?: string[];
    };
    constraints?: Constraint[];
    deadline?: string;
  };
  options?: {
    workflowType?: WorkflowType;
    notifyOnComplete?: boolean;
  };
}

interface CreateWorkflowResponse {
  workflowId: string;
  status: WorkflowStatus;
  estimatedCompletion?: string;
  stages: StageSummary[];
}

// GET /api/v1/workflows/{id}
interface GetWorkflowResponse {
  workflow: WorkflowDefinition;
  currentStage: Stage;
  recentActivity: ActivityEntry[];
  blockers: Blocker[];
}

interface ActivityEntry {
  timestamp: string;
  agent: AgentId;
  action: string;
  details?: any;
}

interface Blocker {
  id: string;
  type: string;
  description: string;
  blockedSince: string;
  suggestedResolution?: string;
}

// POST /api/v1/feedback
interface SubmitFeedbackRequest {
  taskId: string;
  type: 'APPROVAL' | 'REJECTION' | 'COMMENT';
  message?: string;
  details?: any;
}

// GET /api/v1/metrics
interface GetMetricsRequest {
  period?: Period;
  agentId?: AgentId;
  metricTypes?: MetricType[];
}

interface GetMetricsResponse {
  period: Period;
  metrics: MetricValue[];
  trends: TrendData[];
}

type MetricType =
  | 'TASK_COMPLETION_RATE'
  | 'AVERAGE_QUALITY'
  | 'AVERAGE_DURATION'
  | 'ESCALATION_RATE'
  | 'FIRST_ATTEMPT_SUCCESS';

interface MetricValue {
  type: MetricType;
  value: number;
  unit: string;
  trend: Trend;
}
```

### Internal API

```typescript
// POST /internal/agents/{id}/task
interface AssignTaskRequest {
  task: TaskDefinition;
  context: TaskContext;
  deadline?: string;
  priority: Priority;
}

interface AssignTaskResponse {
  accepted: boolean;
  estimatedStart?: string;
  estimatedCompletion?: string;
  reason?: string;
}

// POST /internal/agents/{id}/message
interface SendMessageRequest {
  message: AgentMessage;
}

interface SendMessageResponse {
  delivered: boolean;
  messageId: string;
}

// GET /internal/agents/{id}/status
interface GetAgentStatusResponse {
  agentId: AgentId;
  status: AgentStatus;
  currentTask?: string;
  queueLength: number;
  lastActivity: string;
  health: HealthStatus;
}

type AgentStatus =
  | 'IDLE'
  | 'BUSY'
  | 'BLOCKED'
  | 'ERROR'
  | 'OFFLINE';

type HealthStatus =
  | 'HEALTHY'
  | 'DEGRADED'
  | 'UNHEALTHY';
```

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-02-07 | Claude | Initial schemas |
