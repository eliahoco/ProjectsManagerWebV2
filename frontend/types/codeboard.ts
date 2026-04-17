/**
 * CodeBoard Type Definitions
 */

export type IssueType = 'FEATURE' | 'EPIC' | 'STORY' | 'TASK' | 'SUBTASK' | 'BUG';
export type IssueStatus = 'BACKLOG' | 'TODO' | 'IN_PROGRESS' | 'IN_REVIEW' | 'COMPLETED_WAITING_QA' | 'DONE' | 'CANCELLED';
export type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type Complexity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface Issue {
  id: string;
  projectId: string;
  key: string;
  sequence: number;
  title: string;
  description?: string;
  type: IssueType;
  status: IssueStatus;
  priority: Priority;
  parentId?: string;
  assignee?: string;
  reporter?: string;
  storyPoints?: number;
  estimate?: number;
  timeSpent?: number;
  dueDate?: string;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
  labels?: string;
  breakdownBatchId?: string;
  // Implementation Documentation
  implementationSummary?: string;
  technicalApproach?: string;
  documentationPath?: string;
  // Enhanced Metadata
  estimatedHours?: number;
  actualHours?: number;
  complexity?: Complexity;
  // AI Context
  aiContext?: string;
  children?: Issue[];
}

export interface Comment {
  id: string;
  issueId: string;
  author: string;
  content: string;
  createdAt: string;
  updatedAt: string;
}

export interface Activity {
  id: string;
  issueId: string;
  actor: string;
  action: string;
  field?: string;
  oldValue?: string;
  newValue?: string;
  createdAt: string;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  status: string;
  description?: string;
  type?: string;
  version?: string;
  createdAt: string;
  updatedAt: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface CreateIssueData {
  title: string;
  description?: string;
  type: IssueType;
  status?: IssueStatus;
  priority: Priority;
  parentId?: string;
  assignee?: string;
  storyPoints?: number;
  estimate?: number;
  dueDate?: string;
  labels?: string;
  breakdownBatchId?: string;
}

export interface UpdateIssueData {
  title?: string;
  description?: string;
  type?: IssueType;
  status?: IssueStatus;
  priority?: Priority;
  parentId?: string;
  assignee?: string;
  storyPoints?: number;
  estimate?: number;
  timeSpent?: number;
  dueDate?: string;
  labels?: string;
  // Implementation Documentation
  implementationSummary?: string;
  technicalApproach?: string;
  documentationPath?: string;
  // Enhanced Metadata
  estimatedHours?: number;
  actualHours?: number;
  complexity?: Complexity;
  // AI Context
  aiContext?: string;
}

// Status column configuration
export const STATUS_COLUMNS: { status: IssueStatus; label: string; color: string }[] = [
  { status: 'BACKLOG', label: 'Backlog', color: 'bg-zinc-600' },
  { status: 'TODO', label: 'To Do', color: 'bg-blue-600' },
  { status: 'IN_PROGRESS', label: 'In Progress', color: 'bg-yellow-600' },
  { status: 'IN_REVIEW', label: 'In Review', color: 'bg-purple-600' },
  { status: 'COMPLETED_WAITING_QA', label: 'Waiting QA', color: 'bg-orange-600' },
  { status: 'DONE', label: 'Done', color: 'bg-green-600' },
];

// Issue type configuration
export const ISSUE_TYPES: { type: IssueType; label: string; color: string; icon: string }[] = [
  { type: 'FEATURE', label: 'Feature', color: 'text-blue-400', icon: '🚀' },
  { type: 'EPIC', label: 'Epic', color: 'text-purple-500', icon: '⚡' },
  { type: 'STORY', label: 'Story', color: 'text-green-500', icon: '📖' },
  { type: 'TASK', label: 'Task', color: 'text-blue-500', icon: '✓' },
  { type: 'SUBTASK', label: 'Subtask', color: 'text-cyan-500', icon: '○' },
  { type: 'BUG', label: 'Bug', color: 'text-red-500', icon: '🐛' },
];

// Issue type hierarchy (parent -> allowed children)
export const ISSUE_TYPE_HIERARCHY: Record<IssueType, IssueType[]> = {
  'FEATURE': ['EPIC'],
  'EPIC': ['STORY'],
  'STORY': ['TASK'],
  'TASK': ['SUBTASK'],
  'SUBTASK': [],
  'BUG': ['SUBTASK'],
};

// Priority configuration
export const PRIORITIES: { priority: Priority; label: string; color: string }[] = [
  { priority: 'LOW', label: 'Low', color: 'text-zinc-400' },
  { priority: 'MEDIUM', label: 'Medium', color: 'text-yellow-500' },
  { priority: 'HIGH', label: 'High', color: 'text-orange-500' },
  { priority: 'CRITICAL', label: 'Critical', color: 'text-red-500' },
];

// Sort options
export type SortField = 'sequence' | 'priority' | 'createdAt' | 'updatedAt' | 'dueDate' | 'title' | 'type' | 'status';
export type SortOrder = 'asc' | 'desc';

export interface SortOption {
  field: SortField;
  label: string;
}

export const SORT_OPTIONS: SortOption[] = [
  { field: 'sequence', label: 'Manual Order' },
  { field: 'priority', label: 'Priority' },
  { field: 'createdAt', label: 'Created Date' },
  { field: 'updatedAt', label: 'Updated Date' },
  { field: 'dueDate', label: 'Due Date' },
  { field: 'title', label: 'Title' },
  { field: 'type', label: 'Type' },
  { field: 'status', label: 'Status' },
];

// Date range filter options
export type DateFilterField = 'createdAt' | 'updatedAt' | 'dueDate' | 'startedAt' | 'completedAt';

export interface DateFilterOption {
  field: DateFilterField;
  label: string;
}

export const DATE_FILTER_OPTIONS: DateFilterOption[] = [
  { field: 'createdAt', label: 'Created Date' },
  { field: 'updatedAt', label: 'Updated Date' },
  { field: 'dueDate', label: 'Due Date' },
  { field: 'startedAt', label: 'Started Date' },
  { field: 'completedAt', label: 'Completed Date' },
];

// Execution Modes — per-task action for re-run AutoPilot
export type ExecutionMode = 'implement' | 'audit' | 'rewrite';

// Auto Pilot Execution Types
export type AutoPilotFailAction =
  | 'CONTINUE_MARK_FAILED'  // Mark as failed and continue to next
  | 'RETRY'                  // Retry up to maxRetries times
  | 'SKIP'                   // Skip without status change and continue
  | 'TERMINATE';             // Stop all execution immediately

export type AutoPilotSuccessAction =
  | 'MOVE_NEXT'              // Just continue to next task (keep current status)
  | 'MARK_WAITING_QA'        // Mark as COMPLETED_WAITING_QA and continue
  | 'MARK_DONE'              // Mark as DONE and continue
  | 'RUN_QA_TASK';           // Mark as COMPLETED_WAITING_QA and trigger QA (future)

export interface AutoPilotConfig {
  enabled: boolean;
  onFail: AutoPilotFailAction;
  onSuccess: AutoPilotSuccessAction;
  maxRetries: number;         // Only used when onFail === 'RETRY'
}

export const DEFAULT_AUTO_PILOT_CONFIG: AutoPilotConfig = {
  enabled: false,
  onFail: 'CONTINUE_MARK_FAILED',
  onSuccess: 'MARK_WAITING_QA',
  maxRetries: 3,
};

export const AUTO_PILOT_FAIL_OPTIONS: { value: AutoPilotFailAction; label: string; description: string }[] = [
  { value: 'CONTINUE_MARK_FAILED', label: 'Continue & Mark Failed', description: 'Mark task as failed and proceed to next task' },
  { value: 'RETRY', label: 'Retry X Times', description: 'Retry the task up to configured number of times' },
  { value: 'SKIP', label: 'Skip', description: 'Skip task without changing status and continue' },
  { value: 'TERMINATE', label: 'Terminate', description: 'Stop all execution immediately' },
];

export const AUTO_PILOT_SUCCESS_OPTIONS: { value: AutoPilotSuccessAction; label: string; description: string }[] = [
  { value: 'MOVE_NEXT', label: 'Move to Next', description: 'Continue to next task without changing status' },
  { value: 'MARK_WAITING_QA', label: 'Mark Waiting QA', description: 'Mark as COMPLETED_WAITING_QA and continue' },
  { value: 'MARK_DONE', label: 'Mark as Done', description: 'Mark as DONE and continue' },
  { value: 'RUN_QA_TASK', label: 'Run QA Task', description: 'Mark as COMPLETED_WAITING_QA and trigger QA execution' },
];

// ============================================
// Execution Summary & Documentation Types
// ============================================

export interface ExecutionSummary {
  id: string;
  issueId: string;
  summary: string;
  executedAt: string;
  executionTime: number;
  provider: string;
  model?: string;
  exitCode?: number;
  componentsModified: string;  // JSON array
  filesTouched: string;        // JSON array
  linesAdded?: number;
  linesRemoved?: number;
  architectureNotes?: string;
  technicalNotes?: string;
  challengesFaced?: string;
  lessonsLearned?: string;
  commitHashes?: string;       // JSON array
  docFilePath?: string;
  createdAt: string;
  updatedAt: string;
}

export interface FeatureDocumentation {
  id: string;
  projectId: string;
  featureIssueId: string;
  featureKey: string;
  title: string;
  overview: string;
  requirements: string;
  implementation: string;
  architecture: string;
  techStack: string;           // JSON
  testingStrategy: string;
  totalTasks: number;
  completedTasks: number;
  totalQATasks: number;
  passedQATasks: number;
  failedQATasks: number;
  mdFilePath: string;
  embeddingId?: string;
  lastIndexedAt?: string;
  createdAt: string;
  updatedAt: string;
}
