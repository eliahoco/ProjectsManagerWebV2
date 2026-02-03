/**
 * QA Board Type Definitions
 */

// QA Task Status (individual task execution status)
export type QATaskStatus = 'NOT_DONE' | 'IN_PROGRESS' | 'PASS' | 'FAILED';

// QA Panel Status (aggregate status for Kanban panels)
export type QAPanelStatus = 'WAITING' | 'PASS' | 'FAILED';

// QA Task Type
export type QATaskType = 'AUTOMATED' | 'MANUAL';

// QA Priority (same as Issue priority)
export type QAPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

// QA Task interface
export interface QATask {
  id: string;
  projectId: string;
  key: string;
  sequence: number;
  title: string;
  scenario: string;
  expectedResult: string;
  actualResult?: string;
  status: QATaskStatus;
  type: QATaskType;
  priority: QAPriority;
  executionHistory?: string; // JSON string
  lastExecutedAt?: string;
  bugIssueId?: string;
  createdAt: string;
  updatedAt: string;
  linkedIssueIds?: string[];
}

// QA Execution Run (from history)
export interface QAExecutionRun {
  id: string;
  timestamp: string;
  status: QATaskStatus;
  actualResult: string;
  executionTime: number; // seconds
  error?: string;
}

// QA Summary statistics
export interface QASummary {
  totalTasks: number;
  passedTasks: number;
  failedTasks: number;
  notDoneTasks: number;
  inProgressTasks: number;
  passRate: number;
  isPassingThreshold: boolean;
}

// Project-level QA Summary statistics
export interface ProjectQASummary {
  totalIssues: number;
  issuesWithQA: number;
  issuesWaitingForQA: number;
  issuesPassed: number;
  issuesFailed: number;
  totalTasks: number;
  passedTasks: number;
  failedTasks: number;
  notDoneTasks: number;
  inProgressTasks: number;
  overallPassRate: number;
  coverageRate: number;
}

// QA Settings
export interface QASettings {
  projectId: string;
  passThreshold: number;
  autoCreateBugs: boolean;
}

// Create QA Task data
export interface CreateQATaskData {
  title: string;
  scenario: string;
  expectedResult: string;
  type: QATaskType;
  priority: QAPriority;
  linkedIssueIds?: string[];
}

// Update QA Task data
export interface UpdateQATaskData {
  title?: string;
  scenario?: string;
  expectedResult?: string;
  actualResult?: string;
  status?: QATaskStatus;
  type?: QATaskType;
  priority?: QAPriority;
}

// QA Execution Request
export interface QAExecutionRequest {
  qaTaskIds: string[];
  executionMode: 'sequential' | 'parallel';
}

// QA Execution Result
export interface QAExecutionResult {
  qaTaskId: string;
  key: string;
  status: QATaskStatus;
  actualResult?: string;
  executionTime: number;
  error?: string;
}

// QA Plan Generate Request
export interface QAPlanGenerateRequest {
  issueId: string;
  customInstructions?: string;
}

// QA Plan Generate Response
export interface QAPlanGenerateResponse {
  issueId: string;
  qaTasksCreated: number;
  qaTaskKeys: string[];
}

// QA Kanban Panel configuration (for grouping issues by QA status)
export const QA_STATUS_PANELS: { status: QAPanelStatus; label: string; color: string; description: string }[] = [
  { status: 'WAITING', label: 'Waiting for QA', color: 'bg-yellow-600', description: 'Issues with incomplete QA tasks' },
  { status: 'PASS', label: 'Passed', color: 'bg-green-600', description: 'Issues meeting pass threshold' },
  { status: 'FAILED', label: 'Failed', color: 'bg-red-600', description: 'Issues with failing QA tasks' },
];

// QA Task Status configuration
export const QA_TASK_STATUS_CONFIG: { status: QATaskStatus; label: string; color: string; bgColor: string }[] = [
  { status: 'NOT_DONE', label: 'Not Done', color: 'text-zinc-400', bgColor: 'bg-zinc-600' },
  { status: 'IN_PROGRESS', label: 'Running', color: 'text-blue-400', bgColor: 'bg-blue-600' },
  { status: 'PASS', label: 'Pass', color: 'text-green-400', bgColor: 'bg-green-600' },
  { status: 'FAILED', label: 'Failed', color: 'text-red-400', bgColor: 'bg-red-600' },
];

// QA Priority configuration
export const QA_PRIORITY_CONFIG: { priority: QAPriority; label: string; color: string; bgColor: string }[] = [
  { priority: 'LOW', label: 'Low', color: 'text-zinc-400', bgColor: 'bg-zinc-600' },
  { priority: 'MEDIUM', label: 'Medium', color: 'text-yellow-500', bgColor: 'bg-yellow-600' },
  { priority: 'HIGH', label: 'High', color: 'text-orange-500', bgColor: 'bg-orange-600' },
  { priority: 'CRITICAL', label: 'Critical', color: 'text-red-500', bgColor: 'bg-red-600' },
];

// QA Task Type configuration
export const QA_TYPE_CONFIG: { type: QATaskType; label: string; icon: string }[] = [
  { type: 'AUTOMATED', label: 'Automated', icon: 'robot' },
  { type: 'MANUAL', label: 'Manual', icon: 'user' },
];

// Issue with QA Summary (for Kanban)
export interface IssueWithQASummary {
  id: string;
  key: string;
  title: string;
  type: string;
  status: string;
  qaSummary: QASummary;
}

// QA Kanban Data
export interface QAKanbanData {
  waitingForQA: IssueWithQASummary[];
  passed: IssueWithQASummary[];
  failed: IssueWithQASummary[];
  settings: QASettings;
}

// Parse execution history from JSON string
export function parseExecutionHistory(historyJson?: string): QAExecutionRun[] {
  if (!historyJson) return [];
  try {
    const parsed = JSON.parse(historyJson);
    // Filter out summary entries
    return parsed.filter((entry: any) => !entry.summary);
  } catch {
    return [];
  }
}

// Get status badge color
export function getQAStatusColor(status: QATaskStatus): string {
  const config = QA_TASK_STATUS_CONFIG.find(c => c.status === status);
  return config?.bgColor || 'bg-zinc-600';
}

// Get status text color
export function getQAStatusTextColor(status: QATaskStatus): string {
  const config = QA_TASK_STATUS_CONFIG.find(c => c.status === status);
  return config?.color || 'text-zinc-400';
}

// Get priority color
export function getQAPriorityColor(priority: QAPriority): string {
  const config = QA_PRIORITY_CONFIG.find(c => c.priority === priority);
  return config?.color || 'text-zinc-400';
}

// Get priority background color
export function getQAPriorityBgColor(priority: QAPriority): string {
  const config = QA_PRIORITY_CONFIG.find(c => c.priority === priority);
  return config?.bgColor || 'bg-zinc-600';
}

// Get panel color by status
export function getQAPanelColor(status: QAPanelStatus): string {
  const config = QA_STATUS_PANELS.find(c => c.status === status);
  return config?.color || 'bg-zinc-600';
}

// Get panel label by status
export function getQAPanelLabel(status: QAPanelStatus): string {
  const config = QA_STATUS_PANELS.find(c => c.status === status);
  return config?.label || status;
}

// ==================== Sequential Execution Streaming Types ====================

// Execution status for tracking
export type ExecutionStatus = 'running' | 'completed' | 'aborted' | 'error';

// Streaming execution state
export interface ExecutionState {
  executionId: string;
  totalTasks: number;
  completedTasks: number;
  currentTaskIndex: number;
  currentTaskKey: string | null;
  status: ExecutionStatus;
  progress: number;
  startedAt: string;
  endedAt: string | null;
}

// SSE Event types for streaming execution
export type QAExecutionEventType =
  | 'start'
  | 'task_start'
  | 'task_complete'
  | 'complete'
  | 'aborted'
  | 'error';

// Base SSE event
export interface QAExecutionEventBase {
  event: QAExecutionEventType;
  executionId: string;
  timestamp: string;
}

// Start event
export interface QAExecutionStartEvent extends QAExecutionEventBase {
  event: 'start';
  totalTasks: number;
  maxConcurrent?: number; // For parallel execution
}

// Task start event
export interface QAExecutionTaskStartEvent extends QAExecutionEventBase {
  event: 'task_start';
  taskIndex: number;
  taskKey: string;
  taskTitle: string;
  totalTasks: number;
  progress?: number;
  tasksInFlight?: number; // For parallel execution - how many tasks currently running
}

// Task complete event
export interface QAExecutionTaskCompleteEvent extends QAExecutionEventBase {
  event: 'task_complete';
  taskIndex: number;
  taskKey: string;
  taskTitle: string;
  status: QATaskStatus;
  executionTime: number;
  error?: string;
  completedTasks: number;
  totalTasks: number;
  progress: number;
  tasksInFlight?: number; // For parallel execution - how many tasks still running
}

// Complete event
export interface QAExecutionCompleteEvent extends QAExecutionEventBase {
  event: 'complete';
  totalTasks: number;
  completedTasks: number;
  passedTasks: number;
  failedTasks: number;
  results: QAExecutionResult[];
}

// Aborted event
export interface QAExecutionAbortedEvent extends QAExecutionEventBase {
  event: 'aborted';
  completedTasks: number;
  totalTasks: number;
}

// Error event
export interface QAExecutionErrorEvent extends QAExecutionEventBase {
  event: 'error';
  error: string;
  completedTasks: number;
  totalTasks: number;
}

// Union type for all SSE events
export type QAExecutionEvent =
  | QAExecutionStartEvent
  | QAExecutionTaskStartEvent
  | QAExecutionTaskCompleteEvent
  | QAExecutionCompleteEvent
  | QAExecutionAbortedEvent
  | QAExecutionErrorEvent;

// Callback types for streaming execution
export interface StreamingExecutionCallbacks {
  onStart?: (event: QAExecutionStartEvent) => void;
  onTaskStart?: (event: QAExecutionTaskStartEvent) => void;
  onTaskComplete?: (event: QAExecutionTaskCompleteEvent) => void;
  onComplete?: (event: QAExecutionCompleteEvent) => void;
  onAborted?: (event: QAExecutionAbortedEvent) => void;
  onError?: (event: QAExecutionErrorEvent) => void;
}

// ==================== QA Evaluation Types ====================

// Coverage by test area
export interface AreaCoverage {
  area: string;
  name: string;
  total: number;
  passed: number;
  failed: number;
  notDone: number;
  passRate: number;
}

// Priority distribution
export interface PriorityDistribution {
  priority: QAPriority;
  count: number;
  passed: number;
  failed: number;
  percentage: number;
}

// Type distribution
export interface TypeDistribution {
  type: 'AUTOMATED' | 'MANUAL';
  count: number;
  passed: number;
  failed: number;
  percentage: number;
}

// Quality metric
export interface QualityMetric {
  id: string;
  label: string;
  value: number;
  maxValue: number;
  status: 'good' | 'warning' | 'critical';
  description: string;
}

// Recommendation
export interface Recommendation {
  id: string;
  type: 'coverage' | 'priority' | 'flaky' | 'execution' | 'improvement';
  severity: 'info' | 'warning' | 'critical';
  title: string;
  description: string;
  action?: string;
  affectedTaskIds?: string[];
}

// Execution trend
export interface ExecutionTrend {
  trend: 'up' | 'down' | 'stable';
  change: number;
}

// Complete evaluation response
export interface QAEvaluation {
  summary: QASummary;
  areaCoverage: AreaCoverage[];
  priorityDistribution: PriorityDistribution[];
  typeDistribution: TypeDistribution[];
  qualityMetrics: QualityMetric[];
  overallScore: number;
  recommendations: Recommendation[];
  trend: ExecutionTrend;
  flakyTestIds: string[];
}

// ==================== Test Plan Completion Types ====================

// Test plan completion status
export type TestPlanCompletionStatus = 'in_progress' | 'ready_for_completion' | 'completed' | 'archived';

// Test plan completion metadata
export interface TestPlanCompletion {
  status: TestPlanCompletionStatus;
  completedAt?: string;
  completedBy?: string;
  archivedAt?: string;
  archivedBy?: string;
  passRateAtCompletion?: number;
  totalTasksAtCompletion?: number;
  passedTasksAtCompletion?: number;
  failedTasksAtCompletion?: number;
}

// Completion metrics for UI display
export interface CompletionMetrics {
  totalTasks: number;
  executedTasks: number;
  passedTasks: number;
  failedTasks: number;
  pendingTasks: number;
  manualTasks: number;
  automatedTasks: number;
  completionRate: number;
  passRate: number;
  isPassingThreshold: boolean;
  isFullyExecuted: boolean;
  totalExecutionTime: number;
  avgExecutionTime: number;
}

// Next step action for completion UI
export interface CompletionNextStep {
  id: string;
  type: 'action' | 'recommendation' | 'warning';
  title: string;
  description: string;
  actionLabel?: string;
}

// Export format options
export type ExportFormat = 'json' | 'csv' | 'pdf';

// Test plan completion request
export interface TestPlanCompleteRequest {
  issueId: string;
  notes?: string;
}

// Test plan completion response
export interface TestPlanCompleteResponse {
  issueId: string;
  completedAt: string;
  passRate: number;
  totalTasks: number;
  passedTasks: number;
  failedTasks: number;
}

// Test results export request
export interface TestResultsExportRequest {
  issueId: string;
  format: ExportFormat;
  includeHistory?: boolean;
  includeRecommendations?: boolean;
}

// ==================== Extensive QA Options Types ====================

// Test Area categories for filtering and coverage tracking
export type TestArea =
  | 'functional'
  | 'ui'
  | 'integration'
  | 'performance'
  | 'security'
  | 'accessibility'
  | 'api'
  | 'database'
  | 'error-handling'
  | 'edge-cases';

// Test complexity levels
export type TestComplexity = 'simple' | 'moderate' | 'complex';

// Execution profile presets
export type ExecutionProfile = 'smoke' | 'regression' | 'full-suite' | 'critical-path' | 'custom';

// Target browsers for testing
export type TargetBrowser = 'chrome' | 'firefox' | 'safari' | 'edge';

// Target devices for testing
export type TargetDevice = 'desktop' | 'tablet' | 'mobile';

// Target environment
export type TargetEnvironment = 'development' | 'staging' | 'production';

// Extensive QA Options interface - advanced options for comprehensive testing
export interface ExtensiveQAOptions {
  // Execution profile settings
  executionProfile: ExecutionProfile;
  customProfileName?: string;

  // Test coverage options
  targetCoveragePercent: number;
  mandatoryTaskCount: number;
  includePriorities: QAPriority[];
  excludePriorities: QAPriority[];

  // Test depth & complexity
  maxComplexityLevel: TestComplexity;
  includeTestAreas: TestArea[];
  includeApiTests: boolean;
  includeDataIntegrityTests: boolean;
  includeErrorRecoveryTests: boolean;
  includeConcurrencyTests: boolean;
  includeStateManagementTests: boolean;

  // Environment & browser options
  targetBrowsers: TargetBrowser[];
  targetDevices: TargetDevice[];
  targetEnvironment: TargetEnvironment;
  includeResponsiveTests: boolean;
  includeLocalizationTests: boolean;
  targetLocales: string[];

  // Execution control
  testCycles: number;
  taskTimeoutSeconds: number;
  failureTolerance: number; // percentage of allowed failures before stopping
  runPrerequisites: boolean;
  runCleanup: boolean;

  // Retry & recovery options
  autoRetryFailed: boolean;
  maxRetryAttempts: number;
  retryDelaySeconds: number;
  stopOnConsecutiveFailures: number;

  // Reporting options
  generateDetailedReport: boolean;
  trackPerformanceMetrics: boolean;
  enableTrendAnalysis: boolean;
  detectFlakyTests: boolean;
  flakyTestThreshold: number; // number of state changes to mark as flaky

  // Notification options
  soundEnabled: boolean;
  browserNotifications: boolean;
  notifyOnCompletion: boolean;
  notifyOnFailure: boolean;

  // Advanced filtering
  filterByTestAreas: TestArea[];
  filterByComplexity: TestComplexity | 'all';
  filterByEstimatedDuration: 'short' | 'medium' | 'long' | 'all';
  filterByFailureRate: 'stable' | 'flaky' | 'all';
}

// Default extensive QA options
export const DEFAULT_EXTENSIVE_QA_OPTIONS: ExtensiveQAOptions = {
  executionProfile: 'full-suite',

  targetCoveragePercent: 80,
  mandatoryTaskCount: 0,
  includePriorities: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
  excludePriorities: [],

  maxComplexityLevel: 'complex',
  includeTestAreas: ['functional', 'ui', 'integration', 'api', 'error-handling'],
  includeApiTests: true,
  includeDataIntegrityTests: true,
  includeErrorRecoveryTests: true,
  includeConcurrencyTests: false,
  includeStateManagementTests: true,

  targetBrowsers: ['chrome'],
  targetDevices: ['desktop'],
  targetEnvironment: 'development',
  includeResponsiveTests: false,
  includeLocalizationTests: false,
  targetLocales: ['en'],

  testCycles: 1,
  taskTimeoutSeconds: 300,
  failureTolerance: 100,
  runPrerequisites: true,
  runCleanup: true,

  autoRetryFailed: false,
  maxRetryAttempts: 2,
  retryDelaySeconds: 5,
  stopOnConsecutiveFailures: 0,

  generateDetailedReport: true,
  trackPerformanceMetrics: true,
  enableTrendAnalysis: true,
  detectFlakyTests: true,
  flakyTestThreshold: 3,

  soundEnabled: false,
  browserNotifications: true,
  notifyOnCompletion: true,
  notifyOnFailure: true,

  filterByTestAreas: [],
  filterByComplexity: 'all',
  filterByEstimatedDuration: 'all',
  filterByFailureRate: 'all',
};

// Execution profile presets
export const EXECUTION_PROFILES: Record<ExecutionProfile, Partial<ExtensiveQAOptions>> = {
  'smoke': {
    executionProfile: 'smoke',
    targetCoveragePercent: 20,
    includePriorities: ['CRITICAL'],
    maxComplexityLevel: 'simple',
    includeTestAreas: ['functional', 'ui'],
    testCycles: 1,
    taskTimeoutSeconds: 60,
    autoRetryFailed: false,
  },
  'critical-path': {
    executionProfile: 'critical-path',
    targetCoveragePercent: 50,
    includePriorities: ['CRITICAL', 'HIGH'],
    maxComplexityLevel: 'moderate',
    includeTestAreas: ['functional', 'ui', 'api'],
    testCycles: 1,
    taskTimeoutSeconds: 120,
    autoRetryFailed: true,
    maxRetryAttempts: 1,
  },
  'regression': {
    executionProfile: 'regression',
    targetCoveragePercent: 70,
    includePriorities: ['CRITICAL', 'HIGH', 'MEDIUM'],
    maxComplexityLevel: 'moderate',
    includeTestAreas: ['functional', 'ui', 'integration', 'api', 'error-handling'],
    testCycles: 1,
    taskTimeoutSeconds: 180,
    autoRetryFailed: true,
    maxRetryAttempts: 2,
  },
  'full-suite': {
    executionProfile: 'full-suite',
    targetCoveragePercent: 100,
    includePriorities: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
    maxComplexityLevel: 'complex',
    includeTestAreas: ['functional', 'ui', 'integration', 'performance', 'security', 'accessibility', 'api', 'database', 'error-handling', 'edge-cases'],
    testCycles: 1,
    taskTimeoutSeconds: 300,
    autoRetryFailed: true,
    maxRetryAttempts: 2,
    detectFlakyTests: true,
  },
  'custom': {
    executionProfile: 'custom',
  },
};

// Test area configuration for UI display
export const TEST_AREA_CONFIG: { area: TestArea; label: string; description: string; icon: string }[] = [
  { area: 'functional', label: 'Functional', description: 'Core functionality tests', icon: 'check-circle' },
  { area: 'ui', label: 'UI/UX', description: 'User interface tests', icon: 'layout' },
  { area: 'integration', label: 'Integration', description: 'Component integration tests', icon: 'link' },
  { area: 'performance', label: 'Performance', description: 'Speed and efficiency tests', icon: 'zap' },
  { area: 'security', label: 'Security', description: 'Security vulnerability tests', icon: 'shield' },
  { area: 'accessibility', label: 'Accessibility', description: 'A11y compliance tests', icon: 'eye' },
  { area: 'api', label: 'API', description: 'API endpoint tests', icon: 'server' },
  { area: 'database', label: 'Database', description: 'Data integrity tests', icon: 'database' },
  { area: 'error-handling', label: 'Error Handling', description: 'Error and edge case tests', icon: 'alert-triangle' },
  { area: 'edge-cases', label: 'Edge Cases', description: 'Boundary condition tests', icon: 'corner-up-right' },
];

// Complexity level configuration for UI display
export const COMPLEXITY_CONFIG: { level: TestComplexity; label: string; description: string }[] = [
  { level: 'simple', label: 'Simple', description: 'Basic tests with straightforward scenarios' },
  { level: 'moderate', label: 'Moderate', description: 'Tests with some complexity and dependencies' },
  { level: 'complex', label: 'Complex', description: 'Advanced tests with multiple scenarios and edge cases' },
];

// Browser configuration for UI display
export const BROWSER_CONFIG: { browser: TargetBrowser; label: string; icon: string }[] = [
  { browser: 'chrome', label: 'Chrome', icon: 'chrome' },
  { browser: 'firefox', label: 'Firefox', icon: 'firefox' },
  { browser: 'safari', label: 'Safari', icon: 'compass' },
  { browser: 'edge', label: 'Edge', icon: 'globe' },
];

// Device configuration for UI display
export const DEVICE_CONFIG: { device: TargetDevice; label: string; icon: string }[] = [
  { device: 'desktop', label: 'Desktop', icon: 'monitor' },
  { device: 'tablet', label: 'Tablet', icon: 'tablet' },
  { device: 'mobile', label: 'Mobile', icon: 'smartphone' },
];

// Environment configuration for UI display
export const ENVIRONMENT_CONFIG: { env: TargetEnvironment; label: string; description: string }[] = [
  { env: 'development', label: 'Development', description: 'Local development environment' },
  { env: 'staging', label: 'Staging', description: 'Pre-production staging environment' },
  { env: 'production', label: 'Production', description: 'Live production environment' },
];

// Helper function to determine completion status
export function getCompletionStatus(
  tasks: { status: QATaskStatus }[],
  passThreshold: number
): TestPlanCompletionStatus {
  const total = tasks.length;
  if (total === 0) return 'in_progress';

  const passed = tasks.filter(t => t.status === 'PASS').length;
  const failed = tasks.filter(t => t.status === 'FAILED').length;
  const executed = passed + failed;
  const pending = total - executed;

  // If there are pending tasks, still in progress
  if (pending > 0) return 'in_progress';

  // All executed, check pass rate
  const passRate = passed / executed;
  if (passRate >= passThreshold) return 'ready_for_completion';

  // Fully executed but not passing threshold
  return 'in_progress';
}

// Helper function to check if plan can be marked complete
export function canMarkComplete(
  tasks: { status: QATaskStatus }[],
  passThreshold: number
): boolean {
  const total = tasks.length;
  if (total === 0) return false;

  const passed = tasks.filter(t => t.status === 'PASS').length;
  const failed = tasks.filter(t => t.status === 'FAILED').length;
  const executed = passed + failed;
  const pending = total - executed;

  // Must have no pending tasks
  if (pending > 0) return false;

  // Must meet pass threshold
  const passRate = passed / executed;
  return passRate >= passThreshold;
}

// ==================== Test Plan Evaluation Options Types ====================

// Recommendation type filter options
export type RecommendationType = 'coverage' | 'priority' | 'flaky' | 'execution' | 'improvement';

// Recommendation severity filter
export type RecommendationSeverity = 'info' | 'warning' | 'critical';

// Metric display options
export type MetricDisplayOption = 'pass-rate' | 'completion' | 'coverage' | 'priority';

// Chart visualization type
export type ChartVisualization = 'bar' | 'donut' | 'gauge' | 'none';

// Evaluation options interface
export interface EvaluationOptions {
  // Metric display preferences
  showMetrics: MetricDisplayOption[];
  metricsVisualization: ChartVisualization;

  // Quality thresholds (customizable)
  passRateGoodThreshold: number; // 0-100
  passRateWarningThreshold: number; // 0-100
  completionGoodThreshold: number; // 0-100
  completionWarningThreshold: number; // 0-100
  coverageGoodThreshold: number; // 0-100
  coverageWarningThreshold: number; // 0-100

  // Recommendation filters
  showRecommendations: boolean;
  recommendationTypes: RecommendationType[];
  recommendationSeverities: RecommendationSeverity[];

  // Coverage display options
  showAreaCoverage: boolean;
  showPriorityDistribution: boolean;
  showTypeDistribution: boolean;

  // Flaky test detection settings
  detectFlakyTests: boolean;
  flakyTestThreshold: number; // percentage of state flips

  // Trend analysis options
  showTrendAnalysis: boolean;
  trendSensitivity: number; // percentage change to trigger up/down

  // Execution history display
  showExecutionHistory: boolean;
  maxHistoryItems: number;

  // Export options
  exportFormat: ExportFormat;
  includeCharts: boolean;
  includeRecommendations: boolean;
  includeHistory: boolean;
}

// Default evaluation options
export const DEFAULT_EVALUATION_OPTIONS: EvaluationOptions = {
  // Metrics
  showMetrics: ['pass-rate', 'completion', 'coverage', 'priority'],
  metricsVisualization: 'gauge',

  // Thresholds
  passRateGoodThreshold: 80,
  passRateWarningThreshold: 60,
  completionGoodThreshold: 80,
  completionWarningThreshold: 50,
  coverageGoodThreshold: 50,
  coverageWarningThreshold: 33,

  // Recommendations
  showRecommendations: true,
  recommendationTypes: ['coverage', 'priority', 'flaky', 'execution', 'improvement'],
  recommendationSeverities: ['info', 'warning', 'critical'],

  // Coverage display
  showAreaCoverage: true,
  showPriorityDistribution: true,
  showTypeDistribution: true,

  // Flaky tests
  detectFlakyTests: true,
  flakyTestThreshold: 40,

  // Trend analysis
  showTrendAnalysis: true,
  trendSensitivity: 5,

  // History
  showExecutionHistory: true,
  maxHistoryItems: 10,

  // Export
  exportFormat: 'json',
  includeCharts: true,
  includeRecommendations: true,
  includeHistory: false,
};

// Evaluation option presets
export type EvaluationPreset = 'default' | 'minimal' | 'detailed' | 'metrics-only' | 'recommendations-only';

export const EVALUATION_PRESETS: Record<EvaluationPreset, Partial<EvaluationOptions>> = {
  'default': {},
  'minimal': {
    showMetrics: ['pass-rate', 'completion'],
    metricsVisualization: 'bar',
    showRecommendations: false,
    showAreaCoverage: false,
    showPriorityDistribution: false,
    showTypeDistribution: false,
    showTrendAnalysis: false,
    showExecutionHistory: false,
  },
  'detailed': {
    showMetrics: ['pass-rate', 'completion', 'coverage', 'priority'],
    metricsVisualization: 'gauge',
    showRecommendations: true,
    recommendationTypes: ['coverage', 'priority', 'flaky', 'execution', 'improvement'],
    recommendationSeverities: ['info', 'warning', 'critical'],
    showAreaCoverage: true,
    showPriorityDistribution: true,
    showTypeDistribution: true,
    showTrendAnalysis: true,
    showExecutionHistory: true,
    maxHistoryItems: 20,
  },
  'metrics-only': {
    showMetrics: ['pass-rate', 'completion', 'coverage', 'priority'],
    metricsVisualization: 'gauge',
    showRecommendations: false,
    showAreaCoverage: true,
    showPriorityDistribution: true,
    showTypeDistribution: true,
    showTrendAnalysis: false,
    showExecutionHistory: false,
  },
  'recommendations-only': {
    showMetrics: [],
    showRecommendations: true,
    recommendationTypes: ['coverage', 'priority', 'flaky', 'execution', 'improvement'],
    recommendationSeverities: ['info', 'warning', 'critical'],
    showAreaCoverage: false,
    showPriorityDistribution: false,
    showTypeDistribution: false,
    showTrendAnalysis: false,
    showExecutionHistory: false,
  },
};

// Metric configuration for UI display
export const METRIC_DISPLAY_CONFIG: { metric: MetricDisplayOption; label: string; description: string }[] = [
  { metric: 'pass-rate', label: 'Pass Rate', description: 'Percentage of tests that passed' },
  { metric: 'completion', label: 'Completion', description: 'Percentage of tests executed' },
  { metric: 'coverage', label: 'Coverage', description: 'Test area coverage score' },
  { metric: 'priority', label: 'Priority Focus', description: 'Critical/high priority test ratio' },
];

// Recommendation type configuration
export const RECOMMENDATION_TYPE_CONFIG: { type: RecommendationType; label: string; icon: string }[] = [
  { type: 'coverage', label: 'Coverage', icon: 'target' },
  { type: 'priority', label: 'Priority', icon: 'alert-triangle' },
  { type: 'flaky', label: 'Flaky Tests', icon: 'refresh-cw' },
  { type: 'execution', label: 'Execution', icon: 'play' },
  { type: 'improvement', label: 'Improvement', icon: 'trending-up' },
];

// Recommendation severity configuration
export const RECOMMENDATION_SEVERITY_CONFIG: { severity: RecommendationSeverity; label: string; color: string }[] = [
  { severity: 'info', label: 'Info', color: 'text-blue-400' },
  { severity: 'warning', label: 'Warning', color: 'text-yellow-400' },
  { severity: 'critical', label: 'Critical', color: 'text-red-400' },
];

// Chart visualization configuration
export const CHART_VISUALIZATION_CONFIG: { type: ChartVisualization; label: string; description: string }[] = [
  { type: 'gauge', label: 'Gauges', description: 'Circular progress indicators' },
  { type: 'bar', label: 'Bars', description: 'Horizontal bar charts' },
  { type: 'donut', label: 'Donuts', description: 'Donut/pie charts' },
  { type: 'none', label: 'Numbers Only', description: 'Text values without charts' },
];

// ==================== Test Plan Completion Options Types ====================

// Completion display preset types
export type CompletionPreset = 'default' | 'minimal' | 'detailed' | 'quick-summary' | 'report-ready';

// Completion action type
export type CompletionAction = 'mark-complete' | 'export' | 'archive' | 'rerun-failed' | 'create-bugs';

// Completion report section
export type CompletionReportSection = 'summary' | 'metrics' | 'failed-tests' | 'execution-timeline' | 'recommendations';

// Completion celebration style
export type CelebrationStyle = 'confetti' | 'simple' | 'none';

// Completion notification type
export type CompletionNotificationType = 'in-app' | 'browser' | 'sound';

// Completion options interface
export interface CompletionOptions {
  // Display presets
  preset: CompletionPreset;

  // Pass rate gauge display
  showPassRateGauge: boolean;
  gaugeSize: 'small' | 'medium' | 'large';
  showThresholdMarker: boolean;

  // Metrics display
  showMetricCards: boolean;
  metricsToShow: ('total' | 'passed' | 'failed' | 'execution-time')[];
  showTrends: boolean;

  // Progress bar options
  showProgressBar: boolean;
  progressBarStyle: 'stacked' | 'segmented' | 'simple';
  showLegend: boolean;

  // Test type breakdown
  showTestTypeBreakdown: boolean;
  showAutomatedVsManual: boolean;

  // Failed tests display
  showFailedTestsSummary: boolean;
  maxFailedTestsShown: number;
  allowBugCreation: boolean;

  // Next steps & recommendations
  showNextSteps: boolean;
  nextStepTypes: ('action' | 'recommendation' | 'warning')[];

  // Actions configuration
  enabledActions: CompletionAction[];
  showQuickActions: boolean;
  confirmBeforeComplete: boolean;
  confirmBeforeArchive: boolean;

  // Export options
  defaultExportFormat: ExportFormat;
  exportSections: CompletionReportSection[];
  includeExecutionHistory: boolean;
  includeScreenshots: boolean;

  // Celebration settings
  celebrationStyle: CelebrationStyle;
  celebrationDuration: number; // ms
  showCelebrationOnPass: boolean;

  // Notification settings
  notifyOnCompletion: boolean;
  notificationTypes: CompletionNotificationType[];
  playSoundOnComplete: boolean;

  // Auto-actions
  autoArchiveAfterDays: number; // 0 = disabled
  autoExportOnComplete: boolean;
  autoCreateBugsForFailed: boolean;

  // Thresholds (customizable from defaults)
  customPassThreshold: number | null; // null = use project default
  warningThreshold: number; // Show warning when pass rate below this
}

// Default completion options
export const DEFAULT_COMPLETION_OPTIONS: CompletionOptions = {
  // Preset
  preset: 'default',

  // Pass rate gauge
  showPassRateGauge: true,
  gaugeSize: 'large',
  showThresholdMarker: true,

  // Metrics
  showMetricCards: true,
  metricsToShow: ['total', 'passed', 'failed', 'execution-time'],
  showTrends: false,

  // Progress bar
  showProgressBar: true,
  progressBarStyle: 'stacked',
  showLegend: true,

  // Test type breakdown
  showTestTypeBreakdown: true,
  showAutomatedVsManual: true,

  // Failed tests
  showFailedTestsSummary: true,
  maxFailedTestsShown: 5,
  allowBugCreation: true,

  // Next steps
  showNextSteps: true,
  nextStepTypes: ['action', 'recommendation', 'warning'],

  // Actions
  enabledActions: ['mark-complete', 'export', 'archive', 'rerun-failed', 'create-bugs'],
  showQuickActions: true,
  confirmBeforeComplete: false,
  confirmBeforeArchive: true,

  // Export
  defaultExportFormat: 'json',
  exportSections: ['summary', 'metrics', 'failed-tests'],
  includeExecutionHistory: false,
  includeScreenshots: false,

  // Celebration
  celebrationStyle: 'simple',
  celebrationDuration: 3000,
  showCelebrationOnPass: true,

  // Notifications
  notifyOnCompletion: true,
  notificationTypes: ['in-app'],
  playSoundOnComplete: false,

  // Auto-actions
  autoArchiveAfterDays: 0,
  autoExportOnComplete: false,
  autoCreateBugsForFailed: false,

  // Thresholds
  customPassThreshold: null,
  warningThreshold: 70,
};

// Completion option presets
export const COMPLETION_PRESETS: Record<CompletionPreset, Partial<CompletionOptions>> = {
  'default': {},
  'minimal': {
    preset: 'minimal',
    showPassRateGauge: true,
    gaugeSize: 'small',
    showThresholdMarker: false,
    showMetricCards: true,
    metricsToShow: ['passed', 'failed'],
    showTrends: false,
    showProgressBar: false,
    showTestTypeBreakdown: false,
    showFailedTestsSummary: true,
    maxFailedTestsShown: 3,
    showNextSteps: false,
    celebrationStyle: 'none',
  },
  'detailed': {
    preset: 'detailed',
    showPassRateGauge: true,
    gaugeSize: 'large',
    showThresholdMarker: true,
    showMetricCards: true,
    metricsToShow: ['total', 'passed', 'failed', 'execution-time'],
    showTrends: true,
    showProgressBar: true,
    progressBarStyle: 'stacked',
    showLegend: true,
    showTestTypeBreakdown: true,
    showAutomatedVsManual: true,
    showFailedTestsSummary: true,
    maxFailedTestsShown: 10,
    showNextSteps: true,
    nextStepTypes: ['action', 'recommendation', 'warning'],
    includeExecutionHistory: true,
  },
  'quick-summary': {
    preset: 'quick-summary',
    showPassRateGauge: true,
    gaugeSize: 'medium',
    showThresholdMarker: true,
    showMetricCards: true,
    metricsToShow: ['passed', 'failed'],
    showTrends: false,
    showProgressBar: true,
    progressBarStyle: 'simple',
    showLegend: false,
    showTestTypeBreakdown: false,
    showFailedTestsSummary: false,
    showNextSteps: true,
    nextStepTypes: ['action'],
    celebrationStyle: 'simple',
  },
  'report-ready': {
    preset: 'report-ready',
    showPassRateGauge: true,
    gaugeSize: 'large',
    showThresholdMarker: true,
    showMetricCards: true,
    metricsToShow: ['total', 'passed', 'failed', 'execution-time'],
    showTrends: true,
    showProgressBar: true,
    progressBarStyle: 'stacked',
    showLegend: true,
    showTestTypeBreakdown: true,
    showAutomatedVsManual: true,
    showFailedTestsSummary: true,
    maxFailedTestsShown: 10,
    showNextSteps: true,
    nextStepTypes: ['action', 'recommendation', 'warning'],
    defaultExportFormat: 'pdf',
    exportSections: ['summary', 'metrics', 'failed-tests', 'execution-timeline', 'recommendations'],
    includeExecutionHistory: true,
    includeScreenshots: true,
    autoExportOnComplete: true,
  },
};

// Completion metrics configuration
export const COMPLETION_METRICS_CONFIG: { metric: 'total' | 'passed' | 'failed' | 'execution-time'; label: string; description: string }[] = [
  { metric: 'total', label: 'Total Tests', description: 'Total number of tests in the plan' },
  { metric: 'passed', label: 'Passed', description: 'Number of tests that passed' },
  { metric: 'failed', label: 'Failed', description: 'Number of tests that failed' },
  { metric: 'execution-time', label: 'Execution Time', description: 'Total and average execution time' },
];

// Completion actions configuration
export const COMPLETION_ACTIONS_CONFIG: { action: CompletionAction; label: string; description: string; icon: string }[] = [
  { action: 'mark-complete', label: 'Mark Complete', description: 'Mark the test plan as complete', icon: 'flag' },
  { action: 'export', label: 'Export Results', description: 'Export test results to file', icon: 'download' },
  { action: 'archive', label: 'Archive', description: 'Archive the completed test plan', icon: 'archive' },
  { action: 'rerun-failed', label: 'Re-run Failed', description: 'Re-execute failed tests', icon: 'refresh-cw' },
  { action: 'create-bugs', label: 'Create Bugs', description: 'Create bug issues for failed tests', icon: 'bug' },
];

// Report sections configuration
export const COMPLETION_REPORT_SECTIONS_CONFIG: { section: CompletionReportSection; label: string; description: string }[] = [
  { section: 'summary', label: 'Summary', description: 'High-level pass/fail summary' },
  { section: 'metrics', label: 'Metrics', description: 'Detailed metric cards' },
  { section: 'failed-tests', label: 'Failed Tests', description: 'List of failed test details' },
  { section: 'execution-timeline', label: 'Timeline', description: 'Execution timeline and history' },
  { section: 'recommendations', label: 'Recommendations', description: 'Next steps and suggestions' },
];

// Celebration styles configuration
export const CELEBRATION_STYLES_CONFIG: { style: CelebrationStyle; label: string; description: string }[] = [
  { style: 'confetti', label: 'Confetti', description: 'Celebratory confetti animation' },
  { style: 'simple', label: 'Simple', description: 'Simple success animation' },
  { style: 'none', label: 'None', description: 'No celebration animation' },
];

// Gauge size configuration
export const GAUGE_SIZE_CONFIG: { size: 'small' | 'medium' | 'large'; label: string; pixels: number }[] = [
  { size: 'small', label: 'Small', pixels: 120 },
  { size: 'medium', label: 'Medium', pixels: 160 },
  { size: 'large', label: 'Large', pixels: 200 },
];

// Progress bar style configuration
export const PROGRESS_BAR_STYLE_CONFIG: { style: 'stacked' | 'segmented' | 'simple'; label: string; description: string }[] = [
  { style: 'stacked', label: 'Stacked', description: 'Stacked bar showing passed/failed/pending' },
  { style: 'segmented', label: 'Segmented', description: 'Segmented bar with gaps' },
  { style: 'simple', label: 'Simple', description: 'Simple completion percentage' },
];
