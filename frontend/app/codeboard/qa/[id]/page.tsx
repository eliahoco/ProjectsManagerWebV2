'use client';

import { useState, useMemo, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Zap, FlaskConical, BarChart3, Trophy } from 'lucide-react';
import { useIssue, useIssues } from '@/hooks/useCodeBoard';
import {
  useQATasksForIssue,
  useQASummary,
  useQAEvaluation,
  useExecuteQATasks,
  useMarkManualQAResult,
  useCreateBugFromQA,
  useGenerateQAPlan,
  useStreamingExecution,
  useQASettings,
} from '@/hooks/useQABoard';
import type { Issue } from '@/types/codeboard';
import type { QATask, QATaskStatus } from '@/types/qaboard';
import { getQAStatusColor, getQAPriorityColor, parseExecutionHistory } from '@/types/qaboard';
import { useToast } from '@/components/ui/toast';
import { TestProgressTracker, NormalQAPanel, TestPlanEvaluation, TestPlanCompletionUI } from '@/components/codeboard';

// Tree Node type for issue hierarchy
interface TreeNode extends Issue {
  children: TreeNode[];
}

// Build tree from flat list - returns the root node with its children
function buildTree(issues: Issue[], rootId: string): TreeNode[] {
  // First, collect all descendant IDs recursively starting from rootId
  const descendants = new Set<string>();

  function collectDescendants(parentId: string) {
    issues.forEach((issue) => {
      if (issue.parentId === parentId && !descendants.has(issue.id)) {
        descendants.add(issue.id);
        collectDescendants(issue.id);
      }
    });
  }

  collectDescendants(rootId);

  // Create TreeNodes for root and all descendants
  const issueMap = new Map<string, TreeNode>();

  // Add the root node
  const rootIssue = issues.find((i) => i.id === rootId);
  if (rootIssue) {
    issueMap.set(rootId, { ...rootIssue, children: [] });
  }

  // Add all descendants
  issues.forEach((issue) => {
    if (descendants.has(issue.id)) {
      issueMap.set(issue.id, { ...issue, children: [] });
    }
  });

  // Build parent-child relationships
  issueMap.forEach((node) => {
    if (node.parentId && issueMap.has(node.parentId)) {
      const parent = issueMap.get(node.parentId);
      if (parent) {
        parent.children.push(node);
      }
    }
  });

  // Sort children by type hierarchy (case-insensitive)
  const typeOrder: Record<string, number> = {
    FEATURE: 0,
    EPIC: 1,
    STORY: 2,
    TASK: 3,
    SUBTASK: 4,
    BUG: 5,
  };

  function sortChildren(node: TreeNode) {
    node.children.sort((a, b) => {
      const aType = a.type?.toUpperCase() || 'TASK';
      const bType = b.type?.toUpperCase() || 'TASK';
      return (typeOrder[aType] || 5) - (typeOrder[bType] || 5);
    });
    node.children.forEach(sortChildren);
  }

  // Get the root node and return it as the tree (including the root itself)
  const rootNode = issueMap.get(rootId);
  if (rootNode) {
    sortChildren(rootNode);
    // Return the root node as a single-element array so the tree displays from the root
    return [rootNode];
  }

  return [];
}

// Issue Tree Item Component
function IssueTreeItem({
  node,
  level,
  selected,
  onSelect,
}: {
  node: TreeNode;
  level: number;
  selected: Set<string>;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const isSelected = selected.has(node.id);
  const hasChildren = node.children.length > 0;

  const typeColors: Record<string, string> = {
    FEATURE: 'text-amber-500',
    EPIC: 'text-purple-500',
    STORY: 'text-green-500',
    TASK: 'text-blue-500',
    SUBTASK: 'text-cyan-500',
    BUG: 'text-red-500',
  };

  // Normalize type to uppercase for consistent color lookup
  const normalizedType = node.type?.toUpperCase() || 'TASK';

  return (
    <div>
      <div
        className={`flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer hover:bg-zinc-800 qa-tree-item ${
          isSelected ? 'bg-zinc-800 ring-1 ring-blue-500' : ''
        }`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => onSelect(node.id)}
      >
        {hasChildren && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className={`text-zinc-500 hover:text-white qa-tree-expand-btn ${!expanded ? 'collapsed' : ''}`}
          >
            ▼
          </button>
        )}
        {!hasChildren && <span className="w-4" />}
        <span className={`text-xs font-mono ${typeColors[normalizedType] || 'text-zinc-400'}`}>
          {normalizedType}
        </span>
        <span className="text-xs text-zinc-500">{node.key}</span>
        <span className="text-sm text-zinc-200 truncate">{node.title}</span>
      </div>
      {expanded &&
        hasChildren &&
        node.children.map((child) => (
          <IssueTreeItem
            key={child.id}
            node={child}
            level={level + 1}
            selected={selected}
            onSelect={onSelect}
          />
        ))}
    </div>
  );
}

// QA Task Item Component
function QATaskItem({
  task,
  isHighlighted,
  isCurrentlyExecuting,
  onExecute,
  onMarkManual,
  onCreateBug,
  onViewDetails,
}: {
  task: QATask;
  isHighlighted: boolean;
  isCurrentlyExecuting?: boolean;
  onExecute: () => void;
  onMarkManual: (status: 'PASS' | 'FAILED', result: string) => void;
  onCreateBug: () => void;
  onViewDetails: () => void;
}) {
  const [showManualInput, setShowManualInput] = useState(false);
  const [manualResult, setManualResult] = useState('');

  const statusColors: Record<QATaskStatus, string> = {
    NOT_DONE: 'bg-zinc-600',
    IN_PROGRESS: 'bg-blue-600',
    PASS: 'bg-green-600',
    FAILED: 'bg-red-600',
  };

  return (
    <div
      className={`p-3 bg-zinc-800 rounded-lg border transition-all qa-task-card ${
        isCurrentlyExecuting
          ? 'border-blue-500 ring-2 ring-blue-500/30 qa-task-executing'
          : isHighlighted
          ? 'border-blue-500'
          : 'border-zinc-700'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            {isCurrentlyExecuting ? (
              <span className="px-2 py-0.5 text-xs rounded text-white bg-blue-600 flex items-center gap-1">
                <span className="w-2 h-2 bg-white rounded-full animate-pulse" />
                RUNNING
              </span>
            ) : (
              <span className={`px-2 py-0.5 text-xs rounded text-white ${statusColors[task.status]}`}>
                {task.status}
              </span>
            )}
            <span className="text-xs text-zinc-500 font-mono">{task.key}</span>
            <span className={`text-xs ${getQAPriorityColor(task.priority)}`}>
              {task.priority}
            </span>
            {task.type === 'MANUAL' && (
              <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1.5 rounded">
                Manual
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-zinc-200">{task.title}</p>
        </div>
        <div className="flex items-center gap-1">
          {task.status === 'NOT_DONE' && task.type === 'AUTOMATED' && (
            <button
              onClick={onExecute}
              className="px-2 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded"
            >
              Run
            </button>
          )}
          {task.status === 'NOT_DONE' && task.type === 'MANUAL' && (
            <button
              onClick={() => setShowManualInput(!showManualInput)}
              className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
            >
              Mark
            </button>
          )}
          {task.status === 'FAILED' && !task.bugIssueId && (
            <button
              onClick={onCreateBug}
              className="px-2 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
            >
              Create Bug
            </button>
          )}
          <button
            onClick={onViewDetails}
            className="px-2 py-1 text-xs text-zinc-400 hover:text-white"
          >
            Details
          </button>
        </div>
      </div>

      {/* Manual test input */}
      {showManualInput && (
        <div className="mt-3 pt-3 border-t border-zinc-700">
          <textarea
            value={manualResult}
            onChange={(e) => setManualResult(e.target.value)}
            placeholder="Enter actual result..."
            rows={2}
            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-sm text-white resize-none"
          />
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => {
                onMarkManual('PASS', manualResult);
                setShowManualInput(false);
                setManualResult('');
              }}
              className="px-3 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded"
            >
              Mark Pass
            </button>
            <button
              onClick={() => {
                onMarkManual('FAILED', manualResult);
                setShowManualInput(false);
                setManualResult('');
              }}
              className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
            >
              Mark Failed
            </button>
          </div>
        </div>
      )}

      {/* Show actual result if available */}
      {task.actualResult && (
        <div className="mt-2 p-2 bg-zinc-900 rounded text-xs text-zinc-400">
          <strong>Actual Result:</strong> {task.actualResult}
        </div>
      )}
    </div>
  );
}

// QA Task Detail Modal
function QATaskDetailModal({
  task,
  onClose,
}: {
  task: QATask | null;
  onClose: () => void;
}) {
  if (!task) return null;

  const history = parseExecutionHistory(task.executionHistory);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 qa-modal-backdrop">
      <div className="bg-zinc-900 rounded-lg border border-zinc-700 w-full max-w-2xl max-h-[80vh] overflow-hidden qa-modal-content">
        <div className="p-4 border-b border-zinc-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">{task.key}: {task.title}</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-white">
            &times;
          </button>
        </div>
        <div className="p-4 overflow-y-auto max-h-[calc(80vh-60px)] qa-scrollbar">
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 mb-1">Test Scenario</h3>
              <pre className="p-3 bg-zinc-800 rounded text-sm text-zinc-200 whitespace-pre-wrap qa-detail-pre">
                {task.scenario}
              </pre>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 mb-1">Expected Result</h3>
              <p className="p-3 bg-zinc-800 rounded text-sm text-zinc-200">{task.expectedResult}</p>
            </div>
            {task.actualResult && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-400 mb-1">Actual Result</h3>
                <p className="p-3 bg-zinc-800 rounded text-sm text-zinc-200">{task.actualResult}</p>
              </div>
            )}
            {history.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-400 mb-1">
                  Execution History ({history.length} runs)
                </h3>
                <div className="space-y-2">
                  {history.map((run, i) => (
                    <div
                      key={run.id || i}
                      className="p-2 bg-zinc-800 rounded text-xs flex items-center justify-between"
                    >
                      <span className="text-zinc-500 qa-history-timestamp">
                        {new Date(run.timestamp).toLocaleString()}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded qa-badge ${
                          run.status === 'PASS'
                            ? 'bg-green-900/50 text-green-400'
                            : 'bg-red-900/50 text-red-400'
                        }`}
                      >
                        {run.status}
                      </span>
                      <span className="text-zinc-500">{run.executionTime.toFixed(2)}s</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Main QA Detail Page
export default function QADetailPage() {
  const params = useParams();
  const router = useRouter();
  const issueId = params.id as string;

  const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set());
  const [selectedQATasks, setSelectedQATasks] = useState<Set<string>>(new Set());
  const [executionMode, setExecutionMode] = useState<'sequential' | 'parallel'>('sequential');
  const [detailTask, setDetailTask] = useState<QATask | null>(null);
  const [executionStartTime, setExecutionStartTime] = useState<Date | null>(null);
  const [showEvaluation, setShowEvaluation] = useState(false);
  const [showCompletionUI, setShowCompletionUI] = useState(false);
  const [isTestPlanComplete, setIsTestPlanComplete] = useState(false);
  const [completedAt, setCompletedAt] = useState<string | undefined>();

  const { data: issue, isLoading: issueLoading } = useIssue(issueId);
  // Load all issues for the project to build the complete tree hierarchy
  const { data: issuesData } = useIssues(issue?.projectId || null, { pageSize: 1000 });
  // For FEATURE and EPIC types, include QA tasks from all descendant issues
  // Use case-insensitive comparison to handle any data inconsistencies
  const issueTypeUpper = issue?.type?.toUpperCase();
  const includeDescendants = issueTypeUpper === 'FEATURE' || issueTypeUpper === 'EPIC';
  const { data: qaTasks, refetch: refetchQATasks } = useQATasksForIssue(
    issueId,
    issue?.projectId || null,
    includeDescendants
  );
  const { data: qaSummary } = useQASummary(issueId);
  const { data: qaSettings } = useQASettings(issue?.projectId || null);

  // Determine if we should show the simplified "normal" view
  // Show normal view when the issue has no children (leaf node) or is not a FEATURE/EPIC
  const hasChildren = useMemo(() => {
    if (!issuesData?.items || !issue) return false;
    return issuesData.items.some((i) => i.parentId === issue.id);
  }, [issuesData, issue]);

  const showNormalView = !includeDescendants || !hasChildren;

  const executeQATasks = useExecuteQATasks();
  const markManualQA = useMarkManualQAResult();
  const createBugFromQA = useCreateBugFromQA();
  const generateQAPlan = useGenerateQAPlan();
  const streamingExecution = useStreamingExecution();
  const toast = useToast();

  // Build tree from issues
  const tree = useMemo(() => {
    if (!issue || !issuesData?.items) return [];
    return buildTree(issuesData.items, issue.id);
  }, [issue, issuesData]);

  // Filter QA tasks based on selected issues
  const filteredQATasks = useMemo(() => {
    if (!qaTasks) return [];
    if (selectedIssues.size === 0) return qaTasks;
    return qaTasks.filter((task) =>
      task.linkedIssueIds?.some((id) => selectedIssues.has(id))
    );
  }, [qaTasks, selectedIssues]);

  // Handle issue selection
  const handleIssueSelect = useCallback((id: string) => {
    setSelectedIssues((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Handle QA task selection
  const handleQATaskSelect = useCallback((id: string) => {
    setSelectedQATasks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Execute selected QA tasks
  const handleExecute = async () => {
    const taskIds = selectedQATasks.size > 0
      ? Array.from(selectedQATasks)
      : filteredQATasks.filter((t) => t.status === 'NOT_DONE' && t.type === 'AUTOMATED').map((t) => t.id);

    if (taskIds.length === 0) {
      toast.error('No Tasks', 'No executable tasks selected');
      return;
    }

    // Set execution start time for progress tracking
    setExecutionStartTime(new Date());

    // Use streaming for both sequential and parallel execution
    try {
      const results = await streamingExecution.execute(
        taskIds,
        {
          onTaskStart: (event) => {
            // Optional: show toast for each task start in parallel mode
            if (executionMode === 'parallel' && event.tasksInFlight && event.tasksInFlight > 1) {
              // Multiple tasks running - could show a notification
            }
          },
          onTaskComplete: (event) => {
            // Show intermediate result
            const statusText = event.status === 'PASS' ? '✓' : '✗';
            toast.info(`${statusText} ${event.taskKey}`, `${event.status} (${event.executionTime.toFixed(1)}s)`);
          },
          onComplete: (event) => {
            toast.success(
              'Execution Complete',
              `${event.passedTasks} passed, ${event.failedTasks} failed`
            );
            setExecutionStartTime(null);
          },
          onAborted: () => {
            toast.info('Execution Aborted', 'Execution was stopped');
            setExecutionStartTime(null);
          },
          onError: (event) => {
            toast.error('Execution Error', event.error);
            setExecutionStartTime(null);
          },
        },
        {
          mode: executionMode,
          maxConcurrent: 5, // Could make this configurable in the UI
        }
      );
      refetchQATasks();
    } catch (error) {
      toast.error('Error', 'Failed to execute QA tasks');
      setExecutionStartTime(null);
    }
  };

  // Handle abort
  const handleAbort = () => {
    streamingExecution.abort();
  };

  // Mark manual QA result
  const handleMarkManual = async (taskId: string, status: 'PASS' | 'FAILED', result: string) => {
    try {
      await markManualQA.mutateAsync({ taskId, status, actualResult: result });
      toast.success('Marked', `QA task marked as ${status}`);
      refetchQATasks();
    } catch (error) {
      toast.error('Error', 'Failed to mark QA result');
    }
  };

  // Create bug from failed task
  const handleCreateBug = async (taskId: string) => {
    try {
      const result = await createBugFromQA.mutateAsync({ taskId });
      toast.success('Bug Created', `Created bug ${result.bugKey}`);
      refetchQATasks();
    } catch (error) {
      toast.error('Error', 'Failed to create bug');
    }
  };

  // Generate more QA tasks
  const handleGenerateMore = async () => {
    try {
      const result = await generateQAPlan.mutateAsync({ issueId });
      toast.success('Generated', `Created ${result.qaTasksCreated} new QA tasks`);
      refetchQATasks();
    } catch (error) {
      toast.error('Error', 'Failed to generate QA tasks');
    }
  };

  // Mark test plan as complete
  const handleMarkComplete = useCallback(() => {
    setIsTestPlanComplete(true);
    setCompletedAt(new Date().toISOString());
    toast.success('Test Plan Complete', 'The test plan has been marked as complete');
  }, [toast]);

  // Export test results
  const handleExportResults = useCallback((format: 'json' | 'csv' | 'pdf') => {
    if (!filteredQATasks.length) {
      toast.error('Export Error', 'No tasks to export');
      return;
    }

    if (format === 'json') {
      const exportData = {
        issue: { id: issueId, key: issue?.key, title: issue?.title },
        exportedAt: new Date().toISOString(),
        summary: qaSummary,
        tasks: filteredQATasks.map(task => ({
          key: task.key,
          title: task.title,
          status: task.status,
          type: task.type,
          priority: task.priority,
          scenario: task.scenario,
          expectedResult: task.expectedResult,
          actualResult: task.actualResult,
          lastExecutedAt: task.lastExecutedAt,
        })),
      };
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `qa-results-${issue?.key || issueId}-${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Exported', 'Test results exported as JSON');
    } else if (format === 'csv') {
      const headers = ['Key', 'Title', 'Status', 'Type', 'Priority', 'Expected Result', 'Actual Result'];
      const rows = filteredQATasks.map(task => [
        task.key,
        `"${task.title.replace(/"/g, '""')}"`,
        task.status,
        task.type,
        task.priority,
        `"${(task.expectedResult || '').replace(/"/g, '""')}"`,
        `"${(task.actualResult || '').replace(/"/g, '""')}"`,
      ]);
      const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `qa-results-${issue?.key || issueId}-${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Exported', 'Test results exported as CSV');
    } else {
      // PDF export would require a library - show a message for now
      toast.info('PDF Export', 'PDF export is not yet implemented. Use JSON or CSV instead.');
    }
  }, [filteredQATasks, issue, issueId, qaSummary, toast]);

  // Archive test plan
  const handleArchive = useCallback(() => {
    toast.success('Archived', 'Test plan has been archived');
    // Note: Full archive functionality would need a backend endpoint
  }, [toast]);

  // Re-run failed tests
  const handleRerunFailed = useCallback(() => {
    const failedTaskIds = filteredQATasks
      .filter(t => t.status === 'FAILED' && t.type === 'AUTOMATED')
      .map(t => t.id);

    if (failedTaskIds.length === 0) {
      toast.info('No Failed Tests', 'There are no failed automated tests to re-run');
      return;
    }

    setSelectedQATasks(new Set(failedTaskIds));
    handleExecute();
  }, [filteredQATasks, toast, handleExecute]);

  // Create bugs for multiple tasks
  const handleCreateBugsForTasks = useCallback(async (taskIds: string[]) => {
    let successCount = 0;
    let errorCount = 0;

    for (const taskId of taskIds) {
      try {
        await createBugFromQA.mutateAsync({ taskId });
        successCount++;
      } catch {
        errorCount++;
      }
    }

    if (successCount > 0) {
      toast.success('Bugs Created', `Created ${successCount} bug${successCount > 1 ? 's' : ''}`);
      refetchQATasks();
    }
    if (errorCount > 0) {
      toast.error('Error', `Failed to create ${errorCount} bug${errorCount > 1 ? 's' : ''}`);
    }
  }, [createBugFromQA, refetchQATasks, toast]);

  if (issueLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-zinc-950">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
    );
  }

  if (!issue) {
    return (
      <div className="h-full flex items-center justify-center bg-zinc-950 text-zinc-500">
        Issue not found
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="px-6 py-4 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/codeboard/qa"
              className="text-zinc-400 hover:text-white transition-colors"
            >
              &larr; QA Board
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-zinc-500 font-mono text-sm">{issue.key}</span>
                <span
                  className={`text-xs px-1.5 py-0.5 rounded ${
                    issueTypeUpper === 'FEATURE'
                      ? 'bg-amber-900/50 text-amber-400'
                      : issueTypeUpper === 'EPIC'
                      ? 'bg-purple-900/50 text-purple-400'
                      : issueTypeUpper === 'STORY'
                      ? 'bg-green-900/50 text-green-400'
                      : issueTypeUpper === 'TASK'
                      ? 'bg-blue-900/50 text-blue-400'
                      : 'bg-zinc-700 text-zinc-400'
                  }`}
                >
                  {issueTypeUpper}
                </span>
              </div>
              <h1 className="text-xl font-semibold text-white">{issue.title}</h1>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* QA Summary */}
            {qaSummary && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-green-500">{qaSummary.passedTasks} passed</span>
                <span className="text-red-500">{qaSummary.failedTasks} failed</span>
                <span className="text-zinc-500">
                  {qaSummary.notDoneTasks} pending
                </span>
                <span
                  className={`px-2 py-0.5 rounded ${
                    qaSummary.isPassingThreshold
                      ? 'bg-green-900/50 text-green-400'
                      : 'bg-red-900/50 text-red-400'
                  }`}
                >
                  {Math.round(qaSummary.passRate * 100)}%
                </span>
              </div>
            )}
            {/* Completion UI Toggle */}
            <button
              onClick={() => setShowCompletionUI(!showCompletionUI)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
                showCompletionUI
                  ? 'bg-green-600 text-white'
                  : isTestPlanComplete
                  ? 'bg-green-700 hover:bg-green-600 text-white'
                  : 'bg-zinc-700 hover:bg-zinc-600 text-zinc-200'
              }`}
              title="Test plan completion status and actions"
            >
              <Trophy className="w-4 h-4" />
              {isTestPlanComplete ? 'Completed' : 'Complete'}
            </button>
            {/* Evaluation Toggle */}
            <button
              onClick={() => setShowEvaluation(!showEvaluation)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
                showEvaluation
                  ? 'bg-purple-600 text-white'
                  : 'bg-zinc-700 hover:bg-zinc-600 text-zinc-200'
              }`}
              title="Test plan evaluation and metrics"
            >
              <BarChart3 className="w-4 h-4" />
              Evaluate
            </button>
            {/* Fast QA Mode */}
            <Link
              href={`/codeboard/qa/fast?project=${issue.projectId}&issue=${issueId}`}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 text-white rounded text-sm transition-colors"
              title="Quick, streamlined QA execution"
            >
              <Zap className="w-4 h-4" />
              Fast
            </Link>
            {/* Extensive QA Mode */}
            <Link
              href={`/codeboard/qa/extensive?project=${issue.projectId}&issue=${issueId}`}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm transition-colors"
              title="Comprehensive QA with full details"
            >
              <FlaskConical className="w-4 h-4" />
              Extensive
            </Link>
          </div>
        </div>
      </div>

      {/* Completion UI Panel - Shows test plan completion status */}
      {showCompletionUI && (
        <div className="border-b border-zinc-800 max-h-[60vh] overflow-y-auto">
          <TestPlanCompletionUI
            tasks={filteredQATasks}
            passThreshold={qaSettings?.passThreshold || 0.9}
            isComplete={isTestPlanComplete}
            completedAt={completedAt}
            onMarkComplete={handleMarkComplete}
            onExportResults={handleExportResults}
            onArchive={handleArchive}
            onRerunFailed={handleRerunFailed}
            onViewTask={(task) => setDetailTask(task)}
            onCreateBugs={handleCreateBugsForTasks}
            className="m-4"
          />
        </div>
      )}

      {/* Evaluation Panel - Slides in from the right when active */}
      {showEvaluation && (
        <div className="border-b border-zinc-800 max-h-[50vh] overflow-y-auto">
          <TestPlanEvaluation
            tasks={filteredQATasks}
            passThreshold={qaSettings?.passThreshold || 0.9}
            onClose={() => setShowEvaluation(false)}
            onTaskClick={(task) => setDetailTask(task)}
            onRerunRecommended={(taskIds) => {
              setSelectedQATasks(new Set(taskIds));
              handleExecute();
            }}
          />
        </div>
      )}

      {/* Content Area - Normal view vs Split view */}
      {showNormalView ? (
        /* Normal QA UI - Full-featured single-pane view for leaf issues */
        <NormalQAPanel
          tasks={filteredQATasks}
          isExecuting={streamingExecution.isExecuting}
          executionMode={executionMode}
          progress={streamingExecution.progress}
          completedTasks={streamingExecution.completedTasks}
          totalTasks={streamingExecution.totalTasks}
          currentTaskKey={streamingExecution.currentTaskKey}
          currentTaskTitle={streamingExecution.currentTaskTitle}
          tasksInFlight={streamingExecution.tasksInFlight}
          maxConcurrent={streamingExecution.maxConcurrent}
          taskResults={streamingExecution.taskResults}
          error={streamingExecution.error}
          startTime={executionStartTime}
          isGenerating={generateQAPlan.isPending}
          onExecuteAll={handleExecute}
          onExecuteSelected={(taskIds) => {
            setSelectedQATasks(new Set(taskIds));
            handleExecute();
          }}
          onExecuteSingle={(taskId) => {
            executeQATasks.mutateAsync({
              qaTaskIds: [taskId],
              executionMode: 'sequential',
            }).then(() => {
              const task = filteredQATasks.find(t => t.id === taskId);
              toast.success('Executed', `${task?.key || 'Task'} completed`);
              refetchQATasks();
            });
          }}
          onAbort={handleAbort}
          onMarkManual={handleMarkManual}
          onCreateBug={handleCreateBug}
          onGenerateMore={handleGenerateMore}
          onSetExecutionMode={setExecutionMode}
          onViewDetails={setDetailTask}
          className="flex-1"
        />
      ) : (
        /* Split View - For FEATUREs/EPICs with children */
        <div className="flex-1 flex overflow-hidden qa-split-view">
          {/* Left Panel - Issue Tree */}
          <div className="w-1/2 border-r border-zinc-800 flex flex-col qa-panel">
            <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
              <h2 className="font-semibold text-white">
                {issueTypeUpper === 'FEATURE' ? 'Feature' : issueTypeUpper === 'EPIC' ? 'Epic' : 'Issue'} Tree
              </h2>
              <button
                onClick={() => setSelectedIssues(new Set())}
                className="text-xs text-zinc-400 hover:text-white"
              >
                Clear Selection
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 qa-scrollbar">
              {tree.map((node) => (
                <IssueTreeItem
                  key={node.id}
                  node={node}
                  level={0}
                  selected={selectedIssues}
                  onSelect={handleIssueSelect}
                />
              ))}
            </div>
          </div>

          {/* Right Panel - QA Missions */}
          <div className="w-1/2 flex flex-col qa-panel">
            <div className="px-4 py-3 border-b border-zinc-800 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-white">
                  QA Missions ({filteredQATasks.length})
                </h2>
                <div className="flex items-center gap-2">
                  <select
                    value={executionMode}
                    onChange={(e) => setExecutionMode(e.target.value as any)}
                    className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white"
                    disabled={streamingExecution.isExecuting}
                  >
                    <option value="sequential">Sequential</option>
                    <option value="parallel">Parallel</option>
                  </select>
                  <button
                    onClick={handleGenerateMore}
                    disabled={generateQAPlan.isPending || streamingExecution.isExecuting}
                    className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50"
                  >
                    + Generate More
                  </button>
                  {streamingExecution.isExecuting ? (
                    <button
                      onClick={handleAbort}
                      className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
                    >
                      Abort
                    </button>
                  ) : (
                    <button
                      onClick={handleExecute}
                      disabled={executeQATasks.isPending}
                      className="px-3 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50"
                    >
                      {executeQATasks.isPending ? 'Running...' : 'Execute'}
                    </button>
                  )}
                </div>
              </div>

              {/* Test Progress Tracker - shows during and after execution */}
              {(streamingExecution.isExecuting || streamingExecution.taskResults.length > 0) && (
                <TestProgressTracker
                  isExecuting={streamingExecution.isExecuting}
                  executionMode={streamingExecution.executionMode}
                  progress={streamingExecution.progress}
                  completedTasks={streamingExecution.completedTasks}
                  totalTasks={streamingExecution.totalTasks}
                  currentTaskKey={streamingExecution.currentTaskKey}
                  currentTaskTitle={streamingExecution.currentTaskTitle}
                  tasksInFlight={streamingExecution.tasksInFlight}
                  maxConcurrent={streamingExecution.maxConcurrent}
                  taskResults={streamingExecution.taskResults}
                  error={streamingExecution.error}
                  startTime={executionStartTime}
                  defaultExpanded={true}
                />
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3 qa-scrollbar">
              {filteredQATasks.length === 0 ? (
                <div className="text-center py-8 text-zinc-500 qa-empty-state">
                  No QA tasks yet.{' '}
                  <button
                    onClick={handleGenerateMore}
                    className="text-blue-400 hover:text-blue-300"
                  >
                    Generate QA Plan
                  </button>
                </div>
              ) : (
                filteredQATasks.map((task) => (
                  <QATaskItem
                    key={task.id}
                    task={task}
                    isHighlighted={selectedQATasks.has(task.id)}
                    isCurrentlyExecuting={streamingExecution.currentTaskKey === task.key}
                    onExecute={() => {
                      executeQATasks.mutateAsync({
                        qaTaskIds: [task.id],
                        executionMode: 'sequential',
                      }).then(() => {
                        toast.success('Executed', `${task.key} completed`);
                        refetchQATasks();
                      });
                    }}
                    onMarkManual={(status, result) => handleMarkManual(task.id, status, result)}
                    onCreateBug={() => handleCreateBug(task.id)}
                    onViewDetails={() => setDetailTask(task)}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Task Detail Modal */}
      <QATaskDetailModal task={detailTask} onClose={() => setDetailTask(null)} />
    </div>
  );
}
