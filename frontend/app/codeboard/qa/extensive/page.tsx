'use client';

/**
 * Extensive QA Page - Comprehensive QA testing interface
 *
 * Features:
 * - Full task details with scenario and expected/actual results
 * - Advanced filtering and grouping
 * - Test coverage visualization
 * - Detailed execution history
 * - Batch operations
 * - Configurable execution settings
 * - Keyboard shortcuts
 */

import { useState, useMemo, useCallback, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useUrlState, optionalStringParam } from '@/hooks/use-url-state';
import {
  FlaskConical,
  ArrowLeft,
  RefreshCw,
  Zap,
  Download,
  Upload,
} from 'lucide-react';
import { useProjects, useIssues } from '@/hooks/useCodeBoard';
import {
  useQATasks,
  useStreamingExecution,
  useMarkManualQAResult,
  useGenerateQAPlan,
  useCreateBugFromQA,
} from '@/hooks/useQABoard';
import { useToast } from '@/components/ui/toast';
import { ExtensiveQAPanel } from '@/components/codeboard/ExtensiveQAPanel';
import type { QATask } from '@/types/qaboard';

// Storage key for user preferences
const PREFS_KEY = 'extensive-qa-preferences';

interface ExtensiveQAPreferences {
  executionMode: 'sequential' | 'parallel';
  maxConcurrent: number;
}

const defaultPreferences: ExtensiveQAPreferences = {
  executionMode: 'parallel',
  maxConcurrent: 5,
};

function loadPreferences(): ExtensiveQAPreferences {
  if (typeof window === 'undefined') return defaultPreferences;
  try {
    const stored = localStorage.getItem(PREFS_KEY);
    if (stored) {
      return { ...defaultPreferences, ...JSON.parse(stored) };
    }
  } catch {
    // Ignore errors
  }
  return defaultPreferences;
}

function savePreferences(prefs: ExtensiveQAPreferences) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore errors
  }
}

// Loading fallback for Suspense boundary
function ExtensiveQAPageLoading() {
  return (
    <div className="h-full flex flex-col bg-zinc-950">
      <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-3">
          <FlaskConical className="w-5 h-5 text-blue-400" />
          <h1 className="text-lg font-semibold text-white">Extensive QA</h1>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
    </div>
  );
}

export default function ExtensiveQAPage() {
  return (
    <Suspense fallback={<ExtensiveQAPageLoading />}>
      <ExtensiveQAPageContent />
    </Suspense>
  );
}

function ExtensiveQAPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();

  // URL-backed project + issue selection — survives back/refresh.
  const [urlState, setUrlState] = useUrlState({
    project: optionalStringParam('project'),
    issue: optionalStringParam('issue'),
  });

  // Project state
  const { data: projects, isLoading: projectsLoading } = useProjects();
  const selectedProjectId = urlState.project;

  // Effective project ID
  const effectiveProjectId = selectedProjectId ?? projects?.[0]?.id ?? null;

  // Issue filter (optional)
  const selectedIssueId = urlState.issue;
  const { data: issuesData } = useIssues(effectiveProjectId, { pageSize: 100 });

  // Load QA tasks
  const {
    data: tasks = [],
    isLoading: tasksLoading,
    refetch: refetchTasks,
  } = useQATasks(effectiveProjectId, selectedIssueId ? { issueId: selectedIssueId } : undefined);

  // Preferences state
  const [preferences, setPreferences] = useState<ExtensiveQAPreferences>(loadPreferences);

  // Execution hooks
  const streaming = useStreamingExecution();
  const markManual = useMarkManualQAResult();
  const generateQAPlan = useGenerateQAPlan();
  const createBugFromQA = useCreateBugFromQA();

  // Detail modal state
  const [detailTask, setDetailTask] = useState<QATask | null>(null);

  // Execution start time for progress tracking
  const [executionStartTime, setExecutionStartTime] = useState<Date | null>(null);

  // Issues for dropdown
  const issueOptions = useMemo(() => {
    if (!issuesData?.items) return [];
    return issuesData.items.map(i => ({
      id: i.id,
      key: i.key,
      title: i.title,
      type: i.type,
    }));
  }, [issuesData]);

  // Update preferences
  const updatePreferences = useCallback((updates: Partial<ExtensiveQAPreferences>) => {
    setPreferences(prev => {
      const next = { ...prev, ...updates };
      savePreferences(next);
      return next;
    });
  }, []);

  // Handle project change — URL sync is automatic via useUrlState.
  const handleProjectChange = (projectId: string | null) => {
    setUrlState({ project: projectId, issue: null });
  };

  // Handle issue filter change
  const handleIssueChange = (issueId: string | null) => {
    setUrlState({ issue: issueId });
  };

  // Execute all pending tasks
  const handleExecuteAll = useCallback(async () => {
    const pendingTasks = tasks.filter(t => t.status === 'NOT_DONE' && t.type === 'AUTOMATED');
    if (pendingTasks.length === 0) {
      toast.info('No Tasks', 'No pending automated tasks to execute');
      return;
    }

    setExecutionStartTime(new Date());

    try {
      await streaming.execute(
        pendingTasks.map(t => t.id),
        {
          onTaskComplete: (event) => {
            const icon = event.status === 'PASS' ? '✓' : '✗';
            toast.info(`${icon} ${event.taskKey}`, `${event.status} (${event.executionTime.toFixed(1)}s)`);
          },
          onComplete: (event) => {
            toast.success('Execution Complete', `${event.passedTasks} passed, ${event.failedTasks} failed`);
            setExecutionStartTime(null);
            refetchTasks();
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
          mode: preferences.executionMode,
          maxConcurrent: preferences.maxConcurrent,
        }
      );
    } catch (error) {
      toast.error('Error', 'Failed to execute tasks');
      setExecutionStartTime(null);
    }
  }, [tasks, streaming, preferences, toast, refetchTasks]);

  // Execute selected tasks
  const handleExecuteSelected = useCallback(async (taskIds: string[]) => {
    const validTasks = tasks.filter(
      t => taskIds.includes(t.id) && t.status === 'NOT_DONE' && t.type === 'AUTOMATED'
    );

    if (validTasks.length === 0) {
      toast.info('No Tasks', 'No valid tasks to execute');
      return;
    }

    setExecutionStartTime(new Date());

    try {
      await streaming.execute(
        validTasks.map(t => t.id),
        {
          onTaskComplete: (event) => {
            const icon = event.status === 'PASS' ? '✓' : '✗';
            toast.info(`${icon} ${event.taskKey}`, `${event.status} (${event.executionTime.toFixed(1)}s)`);
          },
          onComplete: (event) => {
            toast.success('Execution Complete', `${event.passedTasks} passed, ${event.failedTasks} failed`);
            setExecutionStartTime(null);
            refetchTasks();
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
          mode: preferences.executionMode,
          maxConcurrent: preferences.maxConcurrent,
        }
      );
    } catch (error) {
      toast.error('Error', 'Failed to execute tasks');
      setExecutionStartTime(null);
    }
  }, [tasks, streaming, preferences, toast, refetchTasks]);

  // Execute single task
  const handleExecuteSingle = useCallback(async (taskId: string) => {
    const task = tasks.find(t => t.id === taskId);
    if (!task || task.status !== 'NOT_DONE' || task.type !== 'AUTOMATED') {
      return;
    }

    try {
      await streaming.execute(
        [taskId],
        {
          onTaskComplete: (event) => {
            toast.info(
              event.status === 'PASS' ? '✓ Passed' : '✗ Failed',
              `${event.taskKey} (${event.executionTime.toFixed(1)}s)`
            );
            refetchTasks();
          },
          onError: (event) => {
            toast.error('Execution Error', event.error);
          },
        },
        {
          mode: 'sequential',
          maxConcurrent: 1,
        }
      );
    } catch (error) {
      toast.error('Error', 'Failed to execute task');
    }
  }, [tasks, streaming, toast, refetchTasks]);

  // Mark manual task
  const handleMarkManual = useCallback(async (taskId: string, status: 'PASS' | 'FAILED', result: string) => {
    try {
      await markManual.mutateAsync({ taskId, status, actualResult: result });
      toast.success('Marked', `Task marked as ${status}`);
      refetchTasks();
    } catch (error) {
      toast.error('Error', 'Failed to mark task');
    }
  }, [markManual, toast, refetchTasks]);

  // Create bug from failed task
  const handleCreateBug = useCallback(async (taskId: string) => {
    try {
      const result = await createBugFromQA.mutateAsync({ taskId });
      toast.success('Bug Created', `Created bug ${result.bugKey}`);
      refetchTasks();
    } catch (error) {
      toast.error('Error', 'Failed to create bug');
    }
  }, [createBugFromQA, toast, refetchTasks]);

  // Generate more QA tasks
  const handleGenerateMore = useCallback(async () => {
    if (!selectedIssueId) {
      toast.info('Select Issue', 'Please select an issue to generate QA tasks');
      return;
    }

    try {
      const result = await generateQAPlan.mutateAsync({ issueId: selectedIssueId });
      toast.success('Generated', `Created ${result.qaTasksCreated} new QA tasks`);
      refetchTasks();
    } catch (error) {
      toast.error('Error', 'Failed to generate QA tasks');
    }
  }, [selectedIssueId, generateQAPlan, toast, refetchTasks]);

  // Retry failed tasks
  const handleRetryFailed = useCallback(async () => {
    const failedTasks = tasks.filter(t => t.status === 'FAILED' && t.type === 'AUTOMATED');
    if (failedTasks.length === 0) {
      toast.info('No Failed Tasks', 'No failed tasks to retry');
      return;
    }
    handleExecuteSelected(failedTasks.map(t => t.id));
  }, [tasks, handleExecuteSelected, toast]);

  // Set execution mode
  const handleSetExecutionMode = useCallback((mode: 'sequential' | 'parallel') => {
    updatePreferences({ executionMode: mode });
  }, [updatePreferences]);

  // Set max concurrent
  const handleSetMaxConcurrent = useCallback((max: number) => {
    updatePreferences({ maxConcurrent: Math.max(1, Math.min(20, max)) });
  }, [updatePreferences]);

  const isLoading = projectsLoading || tasksLoading;

  return (
    <div className="h-full flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/codeboard/qa"
              className="p-1 text-zinc-400 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div className="flex items-center gap-2">
              <FlaskConical className="w-5 h-5 text-blue-400" />
              <h1 className="text-lg font-semibold text-white">Extensive QA</h1>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Project selector */}
            <select
              value={effectiveProjectId || ''}
              onChange={(e) => handleProjectChange(e.target.value || null)}
              className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-white text-sm min-w-[150px]"
            >
              <option value="">Select Project</option>
              {projects?.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>

            {/* Issue filter */}
            <select
              value={selectedIssueId || ''}
              onChange={(e) => handleIssueChange(e.target.value || null)}
              className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-white text-sm min-w-[200px]"
              disabled={!effectiveProjectId}
            >
              <option value="">All Issues</option>
              {issueOptions.map((issue) => (
                <option key={issue.id} value={issue.id}>
                  {issue.key}: {issue.title.length > 30 ? issue.title.slice(0, 30) + '...' : issue.title}
                </option>
              ))}
            </select>

            {/* Quick switch to Fast QA */}
            <Link
              href={`/codeboard/qa/fast${effectiveProjectId ? `?project=${effectiveProjectId}` : ''}${selectedIssueId ? `&issue=${selectedIssueId}` : ''}`}
              className="flex items-center gap-1 px-2 py-1.5 text-xs bg-yellow-600 hover:bg-yellow-700 text-white rounded transition-colors"
              title="Switch to Fast QA mode"
            >
              <Zap className="w-3 h-3" />
              Fast
            </Link>

            {/* Refresh button */}
            <button
              onClick={() => refetchTasks()}
              disabled={isLoading}
              className="p-1.5 text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
              title="Refresh tasks"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {!effectiveProjectId ? (
        <div className="flex-1 flex items-center justify-center text-zinc-500">
          <div className="text-center">
            <FlaskConical className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Select a project to get started</p>
          </div>
        </div>
      ) : isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
        </div>
      ) : (
        <ExtensiveQAPanel
          tasks={tasks}
          isExecuting={streaming.isExecuting}
          executionMode={preferences.executionMode}
          progress={streaming.progress}
          completedTasks={streaming.completedTasks}
          totalTasks={streaming.totalTasks}
          currentTaskKey={streaming.currentTaskKey}
          currentTaskTitle={streaming.currentTaskTitle}
          tasksInFlight={streaming.tasksInFlight}
          maxConcurrent={preferences.maxConcurrent}
          taskResults={streaming.taskResults}
          error={streaming.error}
          startTime={executionStartTime}
          isGenerating={generateQAPlan.isPending}
          onExecuteAll={handleExecuteAll}
          onExecuteSelected={handleExecuteSelected}
          onExecuteSingle={handleExecuteSingle}
          onAbort={streaming.abort}
          onMarkManual={handleMarkManual}
          onCreateBug={handleCreateBug}
          onGenerateMore={handleGenerateMore}
          onSetExecutionMode={handleSetExecutionMode}
          onSetMaxConcurrent={handleSetMaxConcurrent}
          onViewDetails={setDetailTask}
          onRetryFailed={handleRetryFailed}
          className="flex-1"
        />
      )}

      {/* Task Detail Modal - same as QA detail page */}
      {detailTask && (
        <TaskDetailModal
          task={detailTask}
          onClose={() => setDetailTask(null)}
        />
      )}
    </div>
  );
}

// Task detail modal component
function TaskDetailModal({
  task,
  onClose,
}: {
  task: QATask | null;
  onClose: () => void;
}) {
  if (!task) return null;

  // Parse execution history
  let history: Array<{
    id?: string;
    timestamp: string;
    status: string;
    executionTime: number;
    actualResult?: string;
  }> = [];

  try {
    if (task.executionHistory) {
      const parsed = JSON.parse(task.executionHistory);
      history = parsed.filter((entry: any) => !entry.summary);
    }
  } catch {
    // Ignore parse errors
  }

  const statusColors: Record<string, string> = {
    NOT_DONE: 'bg-zinc-600',
    IN_PROGRESS: 'bg-blue-600',
    PASS: 'bg-green-600',
    FAILED: 'bg-red-600',
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-zinc-900 rounded-lg border border-zinc-700 w-full max-w-2xl max-h-[80vh] overflow-hidden">
        <div className="p-4 border-b border-zinc-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 text-xs rounded text-white ${statusColors[task.status]}`}>
              {task.status}
            </span>
            <h2 className="text-lg font-semibold text-white">{task.key}: {task.title}</h2>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-xl">
            &times;
          </button>
        </div>
        <div className="p-4 overflow-y-auto max-h-[calc(80vh-60px)]">
          <div className="space-y-4">
            {/* Meta info */}
            <div className="flex items-center gap-4 text-xs text-zinc-400">
              <span>Priority: <span className="text-white">{task.priority}</span></span>
              <span>Type: <span className="text-white">{task.type}</span></span>
              {task.lastExecutedAt && (
                <span>Last Run: <span className="text-white">{new Date(task.lastExecutedAt).toLocaleString()}</span></span>
              )}
            </div>

            {/* Scenario */}
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 mb-1">Test Scenario</h3>
              <pre className="p-3 bg-zinc-800 rounded text-sm text-zinc-200 whitespace-pre-wrap">
                {task.scenario || 'No scenario defined'}
              </pre>
            </div>

            {/* Expected Result */}
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 mb-1">Expected Result</h3>
              <p className="p-3 bg-zinc-800 rounded text-sm text-zinc-200">
                {task.expectedResult || 'No expected result defined'}
              </p>
            </div>

            {/* Actual Result */}
            {task.actualResult && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-400 mb-1">Actual Result</h3>
                <p className={`p-3 rounded text-sm ${
                  task.status === 'FAILED'
                    ? 'bg-red-900/20 text-red-300 border border-red-900/50'
                    : 'bg-green-900/20 text-green-300 border border-green-900/50'
                }`}>
                  {task.actualResult}
                </p>
              </div>
            )}

            {/* Execution History */}
            {history.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-400 mb-1">
                  Execution History ({history.length} runs)
                </h3>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {history.slice().reverse().map((run, i) => (
                    <div
                      key={run.id || i}
                      className="p-2 bg-zinc-800 rounded text-xs flex items-center justify-between"
                    >
                      <span className="text-zinc-500">
                        {new Date(run.timestamp).toLocaleString()}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded ${
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
