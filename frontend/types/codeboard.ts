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

// Issue Link / Relation types (CB-1955 / CB-1971..1974)
export type LinkType =
  | 'RELATES_TO'
  | 'DUPLICATES'
  | 'IS_DUPLICATED_BY'
  | 'BLOCKS'
  | 'IS_BLOCKED_BY'
  | 'CAUSES'
  | 'CAUSED_BY';

export interface IssueSummary {
  id: string;
  key: string;
  title: string;
  // Typed as string (not IssueStatus) to mirror the backend IssueSummary
  // contract — legacy rows can carry statuses outside the enum and we
  // don't want a 500 to crash the panel render.
  status: string;
}

export interface IssueLinkResponse {
  id: string;
  fromIssueId: string;
  toIssueId: string;
  linkType: LinkType;
  createdAt: string;
  fromIssue?: IssueSummary;
  toIssue?: IssueSummary;
}

export interface IssueRelationsListResponse {
  outbound: IssueLinkResponse[];
  inbound: IssueLinkResponse[];
}

// CB-2003 — POST /issues/{id}/relations request body.
export interface IssueLinkCreatePayload {
  toIssueId: string;
  linkType: LinkType;
}

// CB-2004 / CB-1972 — POST /issues/{id}/relations/bulk request body. Same
// linkType for every target; mixed-type bulk is intentionally out of scope
// per the bulk endpoint contract.
export interface IssueLinkBulkCreatePayload {
  toIssueIds: string[];
  linkType: LinkType;
}

// One row of the `skipped` list returned by the bulk endpoint. `reason` is
// typed as a string union (NOT just a literal type) because the backend
// could grow new skip reasons in the future; the modal renders unknown
// reasons as a generic "Skipped" badge instead of a 500.
export type IssueLinkBulkSkipReason = 'DUPLICATE' | 'CYCLE' | (string & {});

export interface IssueLinkBulkSkipped {
  toIssueId: string;
  reason: IssueLinkBulkSkipReason;
}

export interface IssueLinkBulkResponse {
  created: IssueLinkResponse[];
  skipped: IssueLinkBulkSkipped[];
}

// CB-1974 — DELETE /issues/{id}/relations/{relationId} response. Backend
// guarantees `deleted` is 1 or 2 (the addressed row plus its companion
// inverse row written by the create path under the
// UNIQUE(fromIssueId, toIssueId, linkType) invariant). 404 is raised on
// rowcount=0 so a successful response never carries 0.
export interface IssueLinkDeleteResponse {
  deleted: number;
}

// Issue Group types (CB-1955 / EPIC CB-2009 — Groups frontend).
//
// Mirrors backend `models/schemas.py` IssueGroup* contract:
//   * Aggregate status (statusBreakdown / completionPercent / dominantStatus)
//     is computed on read by `compute_group_status` (CB-1958). Empty groups
//     return `{}` / 0.0 / null per the helper's contract; the page MUST
//     treat `dominantStatus: null` as a valid empty-group state, not an error.
//   * `IssueGroupMemberResponse.issue` is `IssueSummary | null`. Null only
//     surfaces if a future migration breaks the FK CASCADE on `issueId`
//     (current schema cascades), but the type stays nullable so the page
//     renders defensively rather than 500-ing on schema drift.
//   * `position` is the 1-based ordinal within the group (CB-1965). Drag
//     reorder lives in CB-2015 — this type just exposes the field so the
//     sibling task can read+write without re-shaping the contract.
export interface GroupAggregateStatus {
  statusBreakdown: Record<string, number>;
  completionPercent: number;
  // Typed as plain string (not IssueStatus) to mirror backend — legacy rows
  // can carry statuses outside the current enum and we don't want a
  // render-time crash from a Type-narrow that the API doesn't enforce.
  dominantStatus: string | null;
}

export interface IssueGroupMemberResponse {
  id: string;
  groupId: string;
  issueId: string;
  position: number;
  createdAt: string;
  issue: IssueSummary | null;
}

export interface IssueGroupResponse {
  id: string;
  projectId: string;
  title: string;
  description: string | null;
  memberCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface IssueGroupDetailResponse {
  id: string;
  projectId: string;
  title: string;
  description: string | null;
  createdAt: string;
  updatedAt: string;
  members: IssueGroupMemberResponse[];
  aggregateStatus: GroupAggregateStatus;
}

export type PaginatedGroupResponse = PaginatedResponse<IssueGroupResponse>;

// CB-2015: bulk-reorder request + response shapes for the drag-to-reorder
// PATCH /api/groups/{groupId}/members/reorder endpoint. Mirrors the Pydantic
// `IssueGroupMembersReorder` / `IssueGroupMembersReorderResponse` contract:
//   * Request: complete current membership of the group in new order. Server
//     enforces set equality with the current member set (400 with `{missing,
//     extra}` on mismatch) and rejects within-payload duplicates (422). The
//     hook layer ships the full ordered list each drag — partial reorders
//     would force the server to reconcile half-state.
//   * Response: `reordered` is the count of rows the server actually
//     re-positioned (0 on a no-op same-order PATCH). `members` is the
//     post-update full list with embedded `IssueSummary` projections,
//     ready to prime the `['issue-group', groupId]` cache without a
//     follow-up GET.
export interface IssueGroupMembersReorderPayload {
  orderedIssueIds: string[];
}

export interface IssueGroupMembersReorderResponse {
  reordered: number;
  members: IssueGroupMemberResponse[];
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
