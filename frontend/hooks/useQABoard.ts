/**
 * QA Board API Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useCallback, useRef } from 'react';
import type {
  QATask,
  QASummary,
  QASettings,
  CreateQATaskData,
  UpdateQATaskData,
  QAExecutionRequest,
  QAExecutionResult,
  QAPlanGenerateRequest,
  QAPlanGenerateResponse,
  QAKanbanData,
  QATaskStatus,
  ExecutionState,
  QAExecutionEvent,
  StreamingExecutionCallbacks,
  ProjectQASummary,
} from '@/types/qaboard';
import { apiFetch as apiFetchHttp } from '@/lib/api/api-fetch';

const API_BASE = '/api/codeboard/qa';

// Helper function for API calls
async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await apiFetchHttp(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || 'API request failed');
  }

  return res.json();
}

// ==================== QA Tasks ====================

/**
 * Get all QA tasks for a project
 */
export function useQATasks(
  projectId: string | null,
  filters?: {
    status?: string;
    priority?: string;
    issueId?: string;
  }
) {
  return useQuery<QATask[]>({
    queryKey: ['qa-tasks', projectId, filters],
    queryFn: async () => {
      if (!projectId) return [];

      const params = new URLSearchParams();
      if (filters?.status) params.append('status', filters.status);
      if (filters?.priority) params.append('priority', filters.priority);
      if (filters?.issueId) params.append('issue_id', filters.issueId);

      const query = params.toString();
      const url = `${API_BASE}/projects/${projectId}/tasks${query ? `?${query}` : ''}`;

      return apiFetch<QATask[]>(url);
    },
    enabled: !!projectId,
  });
}

/**
 * Get a single QA task by ID
 */
export function useQATask(taskId: string | null) {
  return useQuery<QATask>({
    queryKey: ['qa-task', taskId],
    queryFn: async () => {
      if (!taskId) throw new Error('Task ID required');
      return apiFetch<QATask>(`${API_BASE}/tasks/${taskId}`);
    },
    enabled: !!taskId,
  });
}

/**
 * Create a new QA task
 */
export function useCreateQATask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      data,
    }: {
      projectId: string;
      data: CreateQATaskData;
    }) => {
      return apiFetch<QATask>(`${API_BASE}/projects/${projectId}/tasks`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['qa-tasks', variables.projectId] });
    },
  });
}

/**
 * Update a QA task
 */
export function useUpdateQATask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      taskId,
      data,
    }: {
      taskId: string;
      data: UpdateQATaskData;
    }) => {
      return apiFetch<QATask>(`${API_BASE}/tasks/${taskId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['qa-task', data.id] });
    },
  });
}

/**
 * Delete a QA task
 */
export function useDeleteQATask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (taskId: string) => {
      return apiFetch<{ success: boolean }>(`${API_BASE}/tasks/${taskId}`, {
        method: 'DELETE',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
    },
  });
}

// ==================== QA Plan Generation ====================

/**
 * Generate QA plan for an issue using AI
 */
export function useGenerateQAPlan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: QAPlanGenerateRequest) => {
      return apiFetch<QAPlanGenerateResponse>(`${API_BASE}/generate`, {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['qa-kanban'] });
      queryClient.invalidateQueries({ queryKey: ['qa-summary'] });
    },
  });
}

/**
 * Event types for streaming QA plan generation
 */
export interface QAPlanGenerationEvent {
  event: 'start' | 'progress' | 'complete' | 'error';
  progress?: number;
  message?: string;
  result?: QAPlanGenerateResponse;
  error?: string;
}

/**
 * Callbacks for streaming QA plan generation
 */
export interface StreamingGenerationCallbacks {
  onStart?: () => void;
  onProgress?: (progress: number, message: string) => void;
  onComplete?: (result: QAPlanGenerateResponse) => void;
  onError?: (error: string) => void;
}

/**
 * Hook for generating QA plan with streaming progress updates
 */
export function useStreamingQAPlanGeneration() {
  const queryClient = useQueryClient();
  const abortControllerRef = useRef<AbortController | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  const generate = useCallback(
    async (
      request: QAPlanGenerateRequest,
      callbacks?: StreamingGenerationCallbacks
    ): Promise<QAPlanGenerateResponse | null> => {
      setIsGenerating(true);
      setProgress(0);
      setMessage('Initializing...');
      setError(null);

      abortControllerRef.current = new AbortController();

      try {
        const response = await fetch(`${API_BASE}/generate/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(request),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let result: QAPlanGenerateResponse | null = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete SSE messages
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event: QAPlanGenerationEvent = JSON.parse(line.slice(6));

                switch (event.event) {
                  case 'start':
                    callbacks?.onStart?.();
                    break;

                  case 'progress':
                    setProgress(event.progress || 0);
                    setMessage(event.message || '');
                    callbacks?.onProgress?.(event.progress || 0, event.message || '');
                    break;

                  case 'complete':
                    setProgress(100);
                    setMessage(event.message || 'Complete!');
                    result = event.result || null;
                    callbacks?.onComplete?.(event.result!);
                    // Invalidate queries
                    queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
                    queryClient.invalidateQueries({ queryKey: ['qa-kanban'] });
                    queryClient.invalidateQueries({ queryKey: ['qa-summary'] });
                    break;

                  case 'error':
                    setError(event.error || 'Unknown error');
                    callbacks?.onError?.(event.error || 'Unknown error');
                    break;
                }
              } catch (parseError) {
                console.error('Failed to parse SSE event:', parseError);
              }
            }
          }
        }

        setIsGenerating(false);
        return result;
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          setError('Generation cancelled');
          setIsGenerating(false);
          return null;
        }
        const errorMsg = err instanceof Error ? err.message : 'Unknown error';
        setError(errorMsg);
        callbacks?.onError?.(errorMsg);
        setIsGenerating(false);
        throw err;
      } finally {
        abortControllerRef.current = null;
      }
    },
    [queryClient]
  );

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  const reset = useCallback(() => {
    setIsGenerating(false);
    setProgress(0);
    setMessage('');
    setError(null);
  }, []);

  return {
    isGenerating,
    progress,
    message,
    error,
    generate,
    abort,
    reset,
  };
}

// ==================== QA Execution ====================

/**
 * Execute QA tasks
 */
export function useExecuteQATasks() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: QAExecutionRequest) => {
      return apiFetch<QAExecutionResult[]>(`${API_BASE}/execute`, {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['qa-kanban'] });
      queryClient.invalidateQueries({ queryKey: ['qa-summary'] });
    },
  });
}

/**
 * Mark a manual QA task result
 */
export function useMarkManualQAResult() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      taskId,
      status,
      actualResult,
    }: {
      taskId: string;
      status: 'PASS' | 'FAILED';
      actualResult: string;
    }) => {
      const params = new URLSearchParams({
        status,
        actual_result: actualResult,
      });
      return apiFetch<{ success: boolean; status: string }>(
        `${API_BASE}/tasks/${taskId}/mark-manual?${params}`,
        { method: 'POST' }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['qa-kanban'] });
      queryClient.invalidateQueries({ queryKey: ['qa-summary'] });
    },
  });
}

// ==================== QA Summary ====================

/**
 * Get QA summary for an issue
 */
export function useQASummary(issueId: string | null) {
  return useQuery<QASummary>({
    queryKey: ['qa-summary', issueId],
    queryFn: async () => {
      if (!issueId) throw new Error('Issue ID required');
      return apiFetch<QASummary>(`${API_BASE}/issues/${issueId}/summary`);
    },
    enabled: !!issueId,
  });
}

/**
 * Get comprehensive QA evaluation for an issue
 * Includes coverage analysis, quality metrics, recommendations, etc.
 */
export function useQAEvaluation(issueId: string | null, includeDescendants: boolean = false) {
  return useQuery<import('@/types/qaboard').QAEvaluation>({
    queryKey: ['qa-evaluation', issueId, includeDescendants],
    queryFn: async () => {
      if (!issueId) throw new Error('Issue ID required');
      const params = includeDescendants ? '?include_descendants=true' : '';
      return apiFetch<import('@/types/qaboard').QAEvaluation>(
        `${API_BASE}/issues/${issueId}/evaluation${params}`
      );
    },
    enabled: !!issueId,
  });
}

/**
 * Get project-level QA summary statistics
 * Aggregates QA data across all issues in a project
 */
export function useProjectQASummary(projectId: string | null) {
  const { data: kanbanData, isLoading, error, refetch } = useQAKanban(projectId);

  const summary: ProjectQASummary | null = kanbanData ? (() => {
    const allIssues = [
      ...(kanbanData.waitingForQA || []),
      ...(kanbanData.passed || []),
      ...(kanbanData.failed || []),
    ];

    // Calculate aggregate statistics
    let totalTasks = 0;
    let passedTasks = 0;
    let failedTasks = 0;
    let notDoneTasks = 0;
    let inProgressTasks = 0;

    for (const issue of allIssues) {
      if (issue.qaSummary) {
        totalTasks += issue.qaSummary.totalTasks;
        passedTasks += issue.qaSummary.passedTasks;
        failedTasks += issue.qaSummary.failedTasks;
        notDoneTasks += issue.qaSummary.notDoneTasks;
        inProgressTasks += issue.qaSummary.inProgressTasks;
      }
    }

    const issuesWithQA = allIssues.filter(i => i.qaSummary && i.qaSummary.totalTasks > 0).length;
    const overallPassRate = totalTasks > 0 ? passedTasks / totalTasks : 0;
    const coverageRate = allIssues.length > 0 ? issuesWithQA / allIssues.length : 0;

    return {
      totalIssues: allIssues.length,
      issuesWithQA,
      issuesWaitingForQA: kanbanData.waitingForQA?.length || 0,
      issuesPassed: kanbanData.passed?.length || 0,
      issuesFailed: kanbanData.failed?.length || 0,
      totalTasks,
      passedTasks,
      failedTasks,
      notDoneTasks,
      inProgressTasks,
      overallPassRate,
      coverageRate,
    };
  })() : null;

  return {
    data: summary,
    isLoading,
    error,
    refetch,
  };
}

// ==================== QA Kanban ====================

/**
 * Get QA Kanban data for a project
 */
export function useQAKanban(projectId: string | null) {
  return useQuery<QAKanbanData>({
    queryKey: ['qa-kanban', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID required');
      return apiFetch<QAKanbanData>(`${API_BASE}/projects/${projectId}/kanban`);
    },
    enabled: !!projectId,
  });
}

// ==================== QA Settings ====================

/**
 * Get QA settings for a project
 */
export function useQASettings(projectId: string | null) {
  return useQuery<QASettings>({
    queryKey: ['qa-settings', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID required');
      return apiFetch<QASettings>(`${API_BASE}/projects/${projectId}/settings`);
    },
    enabled: !!projectId,
  });
}

/**
 * Update QA settings for a project
 */
export function useUpdateQASettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      settings,
    }: {
      projectId: string;
      settings: Partial<Omit<QASettings, 'projectId'>>;
    }) => {
      return apiFetch<QASettings>(`${API_BASE}/projects/${projectId}/settings`, {
        method: 'PUT',
        body: JSON.stringify(settings),
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['qa-settings', variables.projectId] });
      queryClient.invalidateQueries({ queryKey: ['qa-kanban', variables.projectId] });
    },
  });
}

// ==================== Bug Creation ====================

/**
 * Create a bug issue from a failed QA task
 */
export function useCreateBugFromQA() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      taskId,
      additionalContext,
    }: {
      taskId: string;
      additionalContext?: string;
    }) => {
      const params = additionalContext
        ? `?additional_context=${encodeURIComponent(additionalContext)}`
        : '';
      return apiFetch<{ success: boolean; bugId: string; bugKey: string }>(
        `${API_BASE}/tasks/${taskId}/create-bug${params}`,
        { method: 'POST' }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['issues'] });
    },
  });
}

// ==================== QA Tasks for Issue ====================

/**
 * Get QA tasks linked to a specific issue
 * @param issueId - The issue ID to get QA tasks for
 * @param projectId - The project ID
 * @param includeDescendants - If true, include QA tasks from all descendant issues (useful for FEATURE/EPIC types)
 */
export function useQATasksForIssue(
  issueId: string | null,
  projectId: string | null,
  includeDescendants: boolean = false
) {
  return useQuery<QATask[]>({
    queryKey: ['qa-tasks-for-issue', issueId, projectId, includeDescendants],
    queryFn: async () => {
      if (!issueId || !projectId) return [];
      const params = new URLSearchParams({
        issue_id: issueId,
      });
      if (includeDescendants) {
        params.append('include_descendants', 'true');
      }
      return apiFetch<QATask[]>(
        `${API_BASE}/projects/${projectId}/tasks?${params.toString()}`
      );
    },
    enabled: !!issueId && !!projectId,
  });
}

// ==================== Streaming Execution (Sequential & Parallel) ====================

/**
 * State for streaming execution
 */
export interface StreamingExecutionState {
  isExecuting: boolean;
  executionId: string | null;
  executionMode: 'sequential' | 'parallel';
  currentTaskKey: string | null;
  currentTaskTitle: string | null;
  progress: number;
  completedTasks: number;
  totalTasks: number;
  tasksInFlight: number; // For parallel execution - how many tasks are currently running
  maxConcurrent: number; // For parallel execution - max concurrent tasks
  taskResults: Array<{
    key: string;
    status: QATaskStatus;
    executionTime: number;
  }>;
  error: string | null;
}

/**
 * Hook for executing QA tasks with streaming progress updates
 *
 * This hook provides real-time progress updates during both sequential and parallel
 * execution, allowing the UI to show which tasks are currently running and update
 * results as each task completes.
 *
 * For parallel execution, multiple tasks can run concurrently (up to maxConcurrent),
 * and completion events arrive as tasks finish (not in submission order).
 */
export function useStreamingExecution() {
  const queryClient = useQueryClient();
  const abortControllerRef = useRef<AbortController | null>(null);

  const [state, setState] = useState<StreamingExecutionState>({
    isExecuting: false,
    executionId: null,
    executionMode: 'sequential',
    currentTaskKey: null,
    currentTaskTitle: null,
    progress: 0,
    completedTasks: 0,
    totalTasks: 0,
    tasksInFlight: 0,
    maxConcurrent: 5,
    taskResults: [],
    error: null,
  });

  const execute = useCallback(
    async (
      qaTaskIds: string[],
      callbacks?: StreamingExecutionCallbacks,
      options?: {
        mode?: 'sequential' | 'parallel';
        maxConcurrent?: number;
      }
    ): Promise<QAExecutionResult[] | null> => {
      const mode = options?.mode || 'sequential';
      const maxConcurrent = options?.maxConcurrent || 5;

      // Reset state
      setState({
        isExecuting: true,
        executionId: null,
        executionMode: mode,
        currentTaskKey: null,
        currentTaskTitle: null,
        progress: 0,
        completedTasks: 0,
        totalTasks: qaTaskIds.length,
        tasksInFlight: 0,
        maxConcurrent,
        taskResults: [],
        error: null,
      });

      // Create abort controller
      abortControllerRef.current = new AbortController();

      // Determine endpoint based on mode
      const endpoint = mode === 'parallel'
        ? `${API_BASE}/execute/stream-parallel`
        : `${API_BASE}/execute/stream`;

      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            qaTaskIds,
            executionMode: mode,
            maxConcurrent: mode === 'parallel' ? maxConcurrent : undefined,
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let finalResults: QAExecutionResult[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete SSE messages
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event: QAExecutionEvent = JSON.parse(line.slice(6));

                switch (event.event) {
                  case 'start':
                    setState((prev) => ({
                      ...prev,
                      executionId: event.executionId,
                      totalTasks: event.totalTasks,
                      maxConcurrent: event.maxConcurrent || prev.maxConcurrent,
                    }));
                    callbacks?.onStart?.(event);
                    break;

                  case 'task_start':
                    setState((prev) => ({
                      ...prev,
                      currentTaskKey: event.taskKey,
                      currentTaskTitle: event.taskTitle,
                      progress: event.progress ?? prev.progress,
                      tasksInFlight: event.tasksInFlight ?? prev.tasksInFlight + 1,
                    }));
                    callbacks?.onTaskStart?.(event);
                    break;

                  case 'task_complete':
                    setState((prev) => {
                      // For parallel execution, currentTaskKey remains if other tasks are in flight
                      const stillRunning = mode === 'parallel' && (event.tasksInFlight ?? 0) > 0;
                      return {
                        ...prev,
                        completedTasks: event.completedTasks,
                        progress: event.progress,
                        tasksInFlight: event.tasksInFlight ?? Math.max(0, prev.tasksInFlight - 1),
                        currentTaskKey: stillRunning ? prev.currentTaskKey : null,
                        currentTaskTitle: stillRunning ? prev.currentTaskTitle : null,
                        taskResults: [
                          ...prev.taskResults,
                          {
                            key: event.taskKey,
                            status: event.status,
                            executionTime: event.executionTime,
                          },
                        ],
                      };
                    });
                    callbacks?.onTaskComplete?.(event);
                    // Invalidate queries to update task status in UI
                    queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
                    queryClient.invalidateQueries({ queryKey: ['qa-tasks-for-issue'] });
                    break;

                  case 'complete':
                    finalResults = event.results;
                    setState((prev) => ({
                      ...prev,
                      isExecuting: false,
                      progress: 100,
                      tasksInFlight: 0,
                      currentTaskKey: null,
                      currentTaskTitle: null,
                    }));
                    callbacks?.onComplete?.(event);
                    // Final invalidation
                    queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
                    queryClient.invalidateQueries({ queryKey: ['qa-tasks-for-issue'] });
                    queryClient.invalidateQueries({ queryKey: ['qa-kanban'] });
                    queryClient.invalidateQueries({ queryKey: ['qa-summary'] });
                    break;

                  case 'aborted':
                    setState((prev) => ({
                      ...prev,
                      isExecuting: false,
                      tasksInFlight: 0,
                      error: 'Execution aborted',
                    }));
                    callbacks?.onAborted?.(event);
                    queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
                    break;

                  case 'error':
                    setState((prev) => ({
                      ...prev,
                      isExecuting: false,
                      tasksInFlight: 0,
                      error: event.error,
                    }));
                    callbacks?.onError?.(event);
                    queryClient.invalidateQueries({ queryKey: ['qa-tasks'] });
                    break;
                }
              } catch (parseError) {
                console.error('Failed to parse SSE event:', parseError);
              }
            }
          }
        }

        return finalResults;
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          // Aborted by user
          setState((prev) => ({
            ...prev,
            isExecuting: false,
            tasksInFlight: 0,
            error: 'Execution aborted by user',
          }));
          return null;
        }
        setState((prev) => ({
          ...prev,
          isExecuting: false,
          tasksInFlight: 0,
          error: error instanceof Error ? error.message : 'Unknown error',
        }));
        throw error;
      } finally {
        abortControllerRef.current = null;
      }
    },
    [queryClient]
  );

  const abort = useCallback(async () => {
    // Abort the fetch request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Also request abort on the server if we have an execution ID
    if (state.executionId) {
      try {
        await apiFetchHttp(`${API_BASE}/execute/${state.executionId}/abort`, {
          method: 'POST',
        });
      } catch (error) {
        console.error('Failed to abort execution on server:', error);
      }
    }
  }, [state.executionId]);

  const reset = useCallback(() => {
    setState({
      isExecuting: false,
      executionId: null,
      executionMode: 'sequential',
      currentTaskKey: null,
      currentTaskTitle: null,
      progress: 0,
      completedTasks: 0,
      totalTasks: 0,
      tasksInFlight: 0,
      maxConcurrent: 5,
      taskResults: [],
      error: null,
    });
  }, []);

  return {
    ...state,
    execute,
    abort,
    reset,
  };
}

/**
 * Get execution status
 */
export function useExecutionStatus(executionId: string | null) {
  return useQuery<ExecutionState>({
    queryKey: ['qa-execution-status', executionId],
    queryFn: async () => {
      if (!executionId) throw new Error('Execution ID required');
      return apiFetch<ExecutionState>(`${API_BASE}/execute/${executionId}/status`);
    },
    enabled: !!executionId,
    refetchInterval: (query) => {
      // Stop polling when execution is complete
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'aborted' || status === 'error') {
        return false;
      }
      return 1000; // Poll every second while running
    },
  });
}

/**
 * List active executions
 */
export function useActiveExecutions({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery<{ executions: ExecutionState[] }>({
    queryKey: ['qa-active-executions'],
    queryFn: async () => {
      return apiFetch<{ executions: ExecutionState[] }>(`${API_BASE}/executions/active`);
    },
    enabled,
    refetchInterval: enabled ? 5000 : false,
  });
}
