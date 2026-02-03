'use client';

/**
 * Normal QA Page - Full-featured QA execution interface
 *
 * Features:
 * - Complete QA task management
 * - Grid and list view modes
 * - Task filtering and selection
 * - Keyboard shortcuts
 * - Real-time progress tracking
 * - Generate more tasks
 * - Create bugs from failed tasks
 * - Sequential/Parallel execution modes
 */

import { useState, useMemo, useCallback, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Layout,
  ArrowLeft,
  RefreshCw,
  Zap,
  FlaskConical,
} from 'lucide-react';
import { useProjects, useIssues, useIssue } from '@/hooks/useCodeBoard';
import {
  useQATasks,
  useStreamingExecution,
  useMarkManualQAResult,
  useCreateBugFromQA,
  useGenerateQAPlan,
} from '@/hooks/useQABoard';
import { useToast } from '@/components/ui/toast';
import { NormalQAPanel, type NormalQAPriorityFilter } from '@/components/codeboard/NormalQAPanel';
import type { QATask } from '@/types/qaboard';

// Storage key for user preferences
const PREFS_KEY = 'normalqa-preferences';

// User preferences
interface NormalQAPreferences {
  executionMode: 'sequential' | 'parallel';
  maxConcurrent: number;
  priorityFilter: NormalQAPriorityFilter;
}

// Default preferences
const defaultPreferences: NormalQAPreferences = {
  executionMode: 'sequential',
  maxConcurrent: 5,
  priorityFilter: 'all',
};

// Load preferences from localStorage
function loadPreferences(): NormalQAPreferences {
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

// Save preferences to localStorage
function savePreferences(prefs: NormalQAPreferences) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore errors
  }
}

// Loading fallback for Suspense boundary
function NormalQAPageLoading() {
  return (
    <div className="h-full flex flex-col bg-zinc-950">
      <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-3">
          <Layout className="w-5 h-5 text-blue-500" />
          <h1 className="text-lg font-semibold text-white">Normal QA</h1>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
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

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-zinc-900 rounded-lg border border-zinc-700 w-full max-w-2xl max-h-[80vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-zinc-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">
            {task.key}: {task.title}
          </h2>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white text-2xl"
          >
            &times;
          </button>
        </div>
        <div className="p-4 overflow-y-auto max-h-[calc(80vh-60px)]">
          <div className="space-y-4">
            {/* Status & Info */}
            <div className="flex items-center gap-3">
              <span
                className={`px-2 py-0.5 text-xs rounded text-white ${
                  task.status === 'PASS'
                    ? 'bg-green-600'
                    : task.status === 'FAILED'
                    ? 'bg-red-600'
                    : task.status === 'IN_PROGRESS'
                    ? 'bg-blue-600'
                    : 'bg-zinc-600'
                }`}
              >
                {task.status}
              </span>
              <span
                className={`text-xs ${
                  task.priority === 'CRITICAL'
                    ? 'text-red-400'
                    : task.priority === 'HIGH'
                    ? 'text-orange-400'
                    : task.priority === 'MEDIUM'
                    ? 'text-yellow-400'
                    : 'text-zinc-400'
                }`}
              >
                {task.priority}
              </span>
              <span className="text-xs text-zinc-500">{task.type}</span>
            </div>

            {/* Scenario */}
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 mb-1">
                Test Scenario
              </h3>
              <pre className="p-3 bg-zinc-800 rounded text-sm text-zinc-200 whitespace-pre-wrap">
                {task.scenario}
              </pre>
            </div>

            {/* Expected Result */}
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 mb-1">
                Expected Result
              </h3>
              <p className="p-3 bg-zinc-800 rounded text-sm text-zinc-200">
                {task.expectedResult}
              </p>
            </div>

            {/* Actual Result */}
            {task.actualResult && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-400 mb-1">
                  Actual Result
                </h3>
                <p className="p-3 bg-zinc-800 rounded text-sm text-zinc-200">
                  {task.actualResult}
                </p>
              </div>
            )}

            {/* Linked Bug */}
            {task.bugIssueId && (
              <div>
                <h3 className="text-sm font-semibold text-zinc-400 mb-1">
                  Linked Bug
                </h3>
                <Link
                  href={`/codeboard/issue/${task.bugIssueId}`}
                  className="text-blue-400 hover:text-blue-300 text-sm"
                >
                  View Bug Issue
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function NormalQAPage() {
  return (
    <Suspense fallback={<NormalQAPageLoading />}>
      <NormalQAPageContent />
    </Suspense>
  );
}

function NormalQAPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();

  // Get project/issue from URL params
  const initialProjectId = searchParams.get('project');
  const initialIssueId = searchParams.get('issue');

  // Project state
  const { data: projects, isLoading: projectsLoading } = useProjects();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    initialProjectId
  );

  // Effective project ID - use selected or first available
  const effectiveProjectId = selectedProjectId ?? projects?.[0]?.id ?? null;

  // Issue filter (optional)
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(
    initialIssueId
  );
  const { data: issuesData } = useIssues(effectiveProjectId, { pageSize: 100 });
  const { data: selectedIssue } = useIssue(selectedIssueId || '');

  // Preferences state
  const [preferences, setPreferences] =
    useState<NormalQAPreferences>(loadPreferences);

  // Update preferences
  const updatePreferences = useCallback(
    (updates: Partial<NormalQAPreferences>) => {
      setPreferences((prev) => {
        const next = { ...prev, ...updates };
        savePreferences(next);
        return next;
      });
    },
    []
  );

  // Load tasks
  const {
    data: tasks = [],
    isLoading: tasksLoading,
    refetch: refetchTasks,
  } = useQATasks(effectiveProjectId, selectedIssueId ? { issueId: selectedIssueId } : undefined);

  // Streaming execution hook
  const streaming = useStreamingExecution();

  // Manual marking hook
  const markManual = useMarkManualQAResult();

  // Create bug hook
  const createBug = useCreateBugFromQA();

  // Generate QA plan hook
  const generatePlan = useGenerateQAPlan();

  // Task detail modal state
  const [detailTask, setDetailTask] = useState<QATask | null>(null);

  // Execution start time for progress tracking
  const [executionStartTime, setExecutionStartTime] = useState<Date | null>(
    null
  );

  // Issues for the dropdown
  const issueOptions = useMemo(() => {
    if (!issuesData?.items) return [];
    return issuesData.items.map((i) => ({
      id: i.id,
      key: i.key,
      title: i.title,
      type: i.type,
    }));
  }, [issuesData]);

  // Handle project change
  const handleProjectChange = (projectId: string | null) => {
    setSelectedProjectId(projectId);
    setSelectedIssueId(null); // Reset issue filter
    // Update URL
    const params = new URLSearchParams();
    if (projectId) params.set('project', projectId);
    router.replace(`/codeboard/qa/normal?${params.toString()}`);
  };

  // Handle issue filter change
  const handleIssueChange = (issueId: string | null) => {
    setSelectedIssueId(issueId);
    // Update URL
    const params = new URLSearchParams();
    if (effectiveProjectId) params.set('project', effectiveProjectId);
    if (issueId) params.set('issue', issueId);
    router.replace(`/codeboard/qa/normal?${params.toString()}`);
  };

  // Execute all pending tasks
  const handleExecuteAll = useCallback(async () => {
    const pendingTasks = tasks.filter(
      (t) => t.status === 'NOT_DONE' && t.type === 'AUTOMATED'
    );
    const taskIds = pendingTasks.map((t) => t.id);
    if (taskIds.length === 0) {
      toast.error('No Tasks', 'No executable tasks available');
      return;
    }

    setExecutionStartTime(new Date());

    try {
      await streaming.execute(
        taskIds,
        {
          onTaskComplete: (event) => {
            const statusText = event.status === 'PASS' ? '✓' : '✗';
            toast.info(
              `${statusText} ${event.taskKey}`,
              `${event.status} (${event.executionTime.toFixed(1)}s)`
            );
          },
          onComplete: (event) => {
            toast.success(
              'Execution Complete',
              `${event.passedTasks} passed, ${event.failedTasks} failed`
            );
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
      toast.error('Error', 'Failed to execute QA tasks');
      setExecutionStartTime(null);
    }
  }, [tasks, streaming, preferences, refetchTasks, toast]);

  // Execute selected tasks
  const handleExecuteSelected = useCallback(
    async (taskIds: string[]) => {
      // Filter to only include automated pending tasks
      const validTaskIds = taskIds.filter((id) => {
        const task = tasks.find((t) => t.id === id);
        return task && task.status === 'NOT_DONE' && task.type === 'AUTOMATED';
      });

      if (validTaskIds.length === 0) {
        toast.error('No Tasks', 'No executable tasks selected');
        return;
      }

      setExecutionStartTime(new Date());

      try {
        await streaming.execute(
          validTaskIds,
          {
            onTaskComplete: (event) => {
              const statusText = event.status === 'PASS' ? '✓' : '✗';
              toast.info(
                `${statusText} ${event.taskKey}`,
                `${event.status} (${event.executionTime.toFixed(1)}s)`
              );
            },
            onComplete: (event) => {
              toast.success(
                'Execution Complete',
                `${event.passedTasks} passed, ${event.failedTasks} failed`
              );
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
        toast.error('Error', 'Failed to execute QA tasks');
        setExecutionStartTime(null);
      }
    },
    [tasks, streaming, preferences, refetchTasks, toast]
  );

  // Execute single task
  const handleExecuteSingle = useCallback(
    async (taskId: string) => {
      const task = tasks.find((t) => t.id === taskId);
      if (!task || task.status !== 'NOT_DONE' || task.type !== 'AUTOMATED') {
        toast.error('Cannot Execute', 'Task is not executable');
        return;
      }

      try {
        await streaming.execute(
          [taskId],
          {
            onTaskComplete: (event) => {
              const statusText = event.status === 'PASS' ? '✓' : '✗';
              toast.info(
                `${statusText} ${event.taskKey}`,
                `${event.status} (${event.executionTime.toFixed(1)}s)`
              );
              refetchTasks();
            },
            onError: (event) => {
              toast.error('Execution Error', event.error);
            },
          },
          { mode: 'sequential', maxConcurrent: 1 }
        );
      } catch (error) {
        toast.error('Error', 'Failed to execute task');
      }
    },
    [tasks, streaming, refetchTasks, toast]
  );

  // Mark manual result
  const handleMarkManual = useCallback(
    async (taskId: string, status: 'PASS' | 'FAILED', result: string) => {
      try {
        await markManual.mutateAsync({ taskId, status, actualResult: result });
        toast.success('Marked', `QA task marked as ${status}`);
        refetchTasks();
      } catch (error) {
        toast.error('Error', 'Failed to mark QA result');
      }
    },
    [markManual, refetchTasks, toast]
  );

  // Create bug from failed task
  const handleCreateBug = useCallback(
    async (taskId: string) => {
      try {
        const result = await createBug.mutateAsync({ taskId });
        toast.success('Bug Created', `Created bug ${result.bugKey}`);
        refetchTasks();
      } catch (error) {
        toast.error('Error', 'Failed to create bug');
      }
    },
    [createBug, refetchTasks, toast]
  );

  // Generate more QA tasks
  const handleGenerateMore = useCallback(async () => {
    if (!selectedIssueId) {
      toast.error('No Issue Selected', 'Please select an issue to generate QA tasks');
      return;
    }

    try {
      const result = await generatePlan.mutateAsync({ issueId: selectedIssueId });
      toast.success('Generated', `Created ${result.qaTasksCreated} new QA tasks`);
      refetchTasks();
    } catch (error) {
      toast.error('Error', 'Failed to generate QA tasks');
    }
  }, [selectedIssueId, generatePlan, refetchTasks, toast]);

  // Set execution mode
  const handleSetExecutionMode = useCallback(
    (mode: 'sequential' | 'parallel') => {
      updatePreferences({ executionMode: mode });
    },
    [updatePreferences]
  );

  // Set priority filter
  const handleSetPriorityFilter = useCallback(
    (filter: NormalQAPriorityFilter) => {
      updatePreferences({ priorityFilter: filter });
    },
    [updatePreferences]
  );

  // Set max concurrent
  const handleSetMaxConcurrent = useCallback(
    (value: number) => {
      updatePreferences({ maxConcurrent: value });
    },
    [updatePreferences]
  );

  // Retry failed tasks
  const handleRetryFailed = useCallback(async () => {
    const failedTasks = tasks.filter(
      (t) => t.status === 'FAILED' && t.type === 'AUTOMATED'
    );
    const taskIds = failedTasks.map((t) => t.id);
    if (taskIds.length === 0) {
      toast.error('No Failed Tasks', 'No failed tasks to retry');
      return;
    }

    setExecutionStartTime(new Date());

    try {
      await streaming.execute(
        taskIds,
        {
          onTaskComplete: (event) => {
            const statusText = event.status === 'PASS' ? '✓' : '✗';
            toast.info(
              `${statusText} ${event.taskKey}`,
              `${event.status} (${event.executionTime.toFixed(1)}s)`
            );
          },
          onComplete: (event) => {
            toast.success(
              'Retry Complete',
              `${event.passedTasks} passed, ${event.failedTasks} failed`
            );
            setExecutionStartTime(null);
            refetchTasks();
          },
          onAborted: () => {
            toast.info('Retry Aborted', 'Retry was stopped');
            setExecutionStartTime(null);
          },
          onError: (event) => {
            toast.error('Retry Error', event.error);
            setExecutionStartTime(null);
          },
        },
        {
          mode: preferences.executionMode,
          maxConcurrent: preferences.maxConcurrent,
        }
      );
    } catch (error) {
      toast.error('Error', 'Failed to retry tasks');
      setExecutionStartTime(null);
    }
  }, [tasks, streaming, preferences, refetchTasks, toast]);

  // Calculate failed count
  const failedCount = useMemo(() => {
    return tasks.filter((t) => t.status === 'FAILED' && t.type === 'AUTOMATED').length;
  }, [tasks]);

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
              <Layout className="w-5 h-5 text-blue-500" />
              <h1 className="text-lg font-semibold text-white">Normal QA</h1>
            </div>
            {selectedIssue && (
              <div className="flex items-center gap-2 text-sm text-zinc-400">
                <span>|</span>
                <span className="font-mono">{selectedIssue.key}</span>
                <span className="truncate max-w-[200px]">{selectedIssue.title}</span>
              </div>
            )}
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

            {/* Issue filter (optional) */}
            <select
              value={selectedIssueId || ''}
              onChange={(e) => handleIssueChange(e.target.value || null)}
              className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-white text-sm min-w-[150px]"
              disabled={!effectiveProjectId}
            >
              <option value="">All Issues</option>
              {issueOptions.map((issue) => (
                <option key={issue.id} value={issue.id}>
                  {issue.key}: {issue.title.slice(0, 30)}
                  {issue.title.length > 30 ? '...' : ''}
                </option>
              ))}
            </select>

            {/* Mode quick links */}
            <div className="flex items-center gap-1 border-l border-zinc-700 pl-2 ml-1">
              <Link
                href={`/codeboard/qa/fast${effectiveProjectId ? `?project=${effectiveProjectId}` : ''}${selectedIssueId ? `&issue=${selectedIssueId}` : ''}`}
                className="flex items-center gap-1 px-2 py-1.5 text-zinc-400 hover:text-yellow-400 transition-colors text-sm"
                title="Fast QA Mode"
              >
                <Zap className="w-4 h-4" />
                Fast
              </Link>
              <Link
                href={`/codeboard/qa/extensive${effectiveProjectId ? `?project=${effectiveProjectId}` : ''}${selectedIssueId ? `&issue=${selectedIssueId}` : ''}`}
                className="flex items-center gap-1 px-2 py-1.5 text-zinc-400 hover:text-purple-400 transition-colors text-sm"
                title="Extensive QA Mode"
              >
                <FlaskConical className="w-4 h-4" />
                Extensive
              </Link>
            </div>

            {/* Refresh button */}
            <button
              onClick={() => refetchTasks()}
              disabled={isLoading}
              className="p-1.5 text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
              title="Refresh tasks"
            >
              <RefreshCw
                className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {!effectiveProjectId ? (
        <div className="flex-1 flex items-center justify-center text-zinc-500">
          Select a project to get started
        </div>
      ) : isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
        </div>
      ) : (
        <NormalQAPanel
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
          isGenerating={generatePlan.isPending}
          onExecuteAll={handleExecuteAll}
          onExecuteSelected={handleExecuteSelected}
          onExecuteSingle={handleExecuteSingle}
          onAbort={streaming.abort}
          onMarkManual={handleMarkManual}
          onCreateBug={handleCreateBug}
          onGenerateMore={handleGenerateMore}
          onSetExecutionMode={handleSetExecutionMode}
          onViewDetails={setDetailTask}
          // Normal QA options
          priorityFilter={preferences.priorityFilter}
          onSetPriorityFilter={handleSetPriorityFilter}
          onSetMaxConcurrent={handleSetMaxConcurrent}
          onRetryFailed={handleRetryFailed}
          failedCount={failedCount}
          className="flex-1"
        />
      )}

      {/* Task Detail Modal */}
      <QATaskDetailModal task={detailTask} onClose={() => setDetailTask(null)} />
    </div>
  );
}
