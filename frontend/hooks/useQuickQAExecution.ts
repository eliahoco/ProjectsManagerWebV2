/**
 * useQuickQAExecution - Hook for fast QA execution with smart defaults
 *
 * Features:
 * - Pre-configured execution settings
 * - Remembers last execution mode
 * - Smart task filtering
 * - Simplified API for fast QA operations
 */

import { useState, useCallback, useMemo } from 'react';
import {
  useStreamingExecution,
  useMarkManualQAResult,
  useQATasks,
} from './useQABoard';
import type { QATask, QATaskStatus, StreamingExecutionCallbacks } from '@/types/qaboard';

// Storage key for user preferences
const PREFS_KEY = 'fastqa-preferences';

// Priority filter type
export type FastQAPriorityFilter = 'all' | 'critical' | 'high' | 'medium' | 'low' | 'critical-high';

// User preferences
export interface FastQAPreferences {
  executionMode: 'sequential' | 'parallel';
  maxConcurrent: number;
  autoExpandProgress: boolean;
  showNotifications: boolean;
  // New fast QA options
  priorityFilter: FastQAPriorityFilter;
  autoRetryFailed: boolean;
  maxRetries: number;
  skipManualTasks: boolean;
  stopOnFirstFailure: boolean;
  soundEnabled: boolean;
}

// Default preferences
const defaultPreferences: FastQAPreferences = {
  executionMode: 'parallel',
  maxConcurrent: 5,
  autoExpandProgress: true,
  showNotifications: true,
  // New fast QA options defaults
  priorityFilter: 'all',
  autoRetryFailed: false,
  maxRetries: 1,
  skipManualTasks: true,
  stopOnFirstFailure: false,
  soundEnabled: false,
};

// Load preferences from localStorage
function loadPreferences(): FastQAPreferences {
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
function savePreferences(prefs: FastQAPreferences) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore errors
  }
}

export interface UseQuickQAExecutionOptions {
  projectId: string | null;
  issueId?: string | null;
  onTaskComplete?: (taskKey: string, status: QATaskStatus) => void;
  onAllComplete?: (passedCount: number, failedCount: number) => void;
  onError?: (error: string) => void;
}

export interface QuickQAExecutionState {
  // Execution state
  isExecuting: boolean;
  progress: number;
  completedTasks: number;
  totalTasks: number;
  currentTaskKey: string | null;
  currentTaskTitle: string | null;
  tasksInFlight: number;
  taskResults: Array<{ key: string; status: QATaskStatus; executionTime: number }>;
  error: string | null;

  // Preferences
  executionMode: 'sequential' | 'parallel';
  maxConcurrent: number;
  priorityFilter: FastQAPriorityFilter;
  autoRetryFailed: boolean;
  maxRetries: number;
  skipManualTasks: boolean;
  stopOnFirstFailure: boolean;
  soundEnabled: boolean;
  showNotifications: boolean;

  // Task data
  tasks: QATask[];
  pendingTasks: QATask[];
  filteredPendingTasks: QATask[];
  isLoading: boolean;
}

export interface QuickQAExecutionActions {
  // Execution actions
  executeAll: () => Promise<void>;
  executeSelected: (taskIds: string[]) => Promise<void>;
  executeSingle: (taskId: string) => Promise<void>;
  retryFailed: () => Promise<void>;
  abort: () => void;
  reset: () => void;

  // Manual task actions
  markManualPass: (taskId: string, result: string) => Promise<void>;
  markManualFail: (taskId: string, result: string) => Promise<void>;

  // Preference actions
  toggleExecutionMode: () => void;
  setMaxConcurrent: (value: number) => void;
  setPriorityFilter: (filter: FastQAPriorityFilter) => void;
  setAutoRetryFailed: (enabled: boolean) => void;
  setMaxRetries: (value: number) => void;
  setSkipManualTasks: (skip: boolean) => void;
  setStopOnFirstFailure: (stop: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setShowNotifications: (show: boolean) => void;
  updatePreferences: (updates: Partial<FastQAPreferences>) => void;

  // Refetch
  refetch: () => void;
}

export function useQuickQAExecution(
  options: UseQuickQAExecutionOptions
): QuickQAExecutionState & QuickQAExecutionActions {
  const { projectId, issueId, onTaskComplete, onAllComplete, onError } = options;

  // Preferences state
  const [preferences, setPreferences] = useState<FastQAPreferences>(loadPreferences);

  // Load tasks
  const { data: tasks = [], isLoading, refetch } = useQATasks(
    projectId,
    issueId ? { issueId } : undefined
  );

  // Streaming execution hook
  const streaming = useStreamingExecution();

  // Manual marking hook
  const markManual = useMarkManualQAResult();

  // Update preferences in state and localStorage
  const updatePreferences = useCallback((updates: Partial<FastQAPreferences>) => {
    setPreferences(prev => {
      const next = { ...prev, ...updates };
      savePreferences(next);
      return next;
    });
  }, []);

  // Filter pending automated tasks
  const pendingTasks = useMemo(() => {
    return tasks.filter(t => t.status === 'NOT_DONE' && t.type === 'AUTOMATED');
  }, [tasks]);

  // Filter pending tasks based on priority filter preference
  const filteredPendingTasks = useMemo(() => {
    let filtered = pendingTasks;

    // Apply priority filter
    switch (preferences.priorityFilter) {
      case 'critical':
        filtered = filtered.filter(t => t.priority === 'CRITICAL');
        break;
      case 'high':
        filtered = filtered.filter(t => t.priority === 'HIGH');
        break;
      case 'medium':
        filtered = filtered.filter(t => t.priority === 'MEDIUM');
        break;
      case 'low':
        filtered = filtered.filter(t => t.priority === 'LOW');
        break;
      case 'critical-high':
        filtered = filtered.filter(t => t.priority === 'CRITICAL' || t.priority === 'HIGH');
        break;
      default:
        // 'all' - no filtering
        break;
    }

    return filtered;
  }, [pendingTasks, preferences.priorityFilter]);

  // Get failed tasks for retry functionality
  const failedTasks = useMemo(() => {
    return tasks.filter(t => t.status === 'FAILED' && t.type === 'AUTOMATED');
  }, [tasks]);

  // Streaming callbacks
  const createCallbacks = useCallback((): StreamingExecutionCallbacks => ({
    onTaskComplete: (event) => {
      onTaskComplete?.(event.taskKey, event.status);
    },
    onComplete: (event) => {
      onAllComplete?.(event.passedTasks, event.failedTasks);
      // Refetch tasks to update UI
      refetch();
    },
    onError: (event) => {
      onError?.(event.error);
    },
  }), [onTaskComplete, onAllComplete, onError, refetch]);

  // Execute all pending tasks (uses filtered tasks based on priority)
  const executeAll = useCallback(async () => {
    const taskIds = filteredPendingTasks.map(t => t.id);
    if (taskIds.length === 0) return;

    try {
      await streaming.execute(taskIds, createCallbacks(), {
        mode: preferences.executionMode,
        maxConcurrent: preferences.maxConcurrent,
      });
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'Execution failed');
    }
  }, [filteredPendingTasks, streaming, createCallbacks, preferences, onError]);

  // Execute selected tasks
  const executeSelected = useCallback(async (taskIds: string[]) => {
    if (taskIds.length === 0) return;

    // Filter to only include automated pending tasks
    const validTaskIds = taskIds.filter(id => {
      const task = tasks.find(t => t.id === id);
      return task && task.status === 'NOT_DONE' && task.type === 'AUTOMATED';
    });

    if (validTaskIds.length === 0) return;

    try {
      await streaming.execute(validTaskIds, createCallbacks(), {
        mode: preferences.executionMode,
        maxConcurrent: preferences.maxConcurrent,
      });
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'Execution failed');
    }
  }, [tasks, streaming, createCallbacks, preferences, onError]);

  // Execute single task
  const executeSingle = useCallback(async (taskId: string) => {
    const task = tasks.find(t => t.id === taskId);
    if (!task || task.status !== 'NOT_DONE' || task.type !== 'AUTOMATED') return;

    try {
      await streaming.execute([taskId], createCallbacks(), {
        mode: 'sequential',
        maxConcurrent: 1,
      });
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'Execution failed');
    }
  }, [tasks, streaming, createCallbacks, onError]);

  // Retry failed tasks
  const retryFailed = useCallback(async () => {
    const taskIds = failedTasks.map(t => t.id);
    if (taskIds.length === 0) return;

    try {
      await streaming.execute(taskIds, createCallbacks(), {
        mode: preferences.executionMode,
        maxConcurrent: preferences.maxConcurrent,
      });
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'Retry failed');
    }
  }, [failedTasks, streaming, createCallbacks, preferences, onError]);

  // Mark manual task as passed
  const markManualPass = useCallback(async (taskId: string, result: string) => {
    try {
      await markManual.mutateAsync({ taskId, status: 'PASS', actualResult: result });
      refetch();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'Failed to mark task');
    }
  }, [markManual, refetch, onError]);

  // Mark manual task as failed
  const markManualFail = useCallback(async (taskId: string, result: string) => {
    try {
      await markManual.mutateAsync({ taskId, status: 'FAILED', actualResult: result });
      refetch();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'Failed to mark task');
    }
  }, [markManual, refetch, onError]);

  // Toggle execution mode
  const toggleExecutionMode = useCallback(() => {
    updatePreferences({
      executionMode: preferences.executionMode === 'sequential' ? 'parallel' : 'sequential',
    });
  }, [preferences.executionMode, updatePreferences]);

  // Set max concurrent
  const setMaxConcurrent = useCallback((value: number) => {
    updatePreferences({ maxConcurrent: Math.max(1, Math.min(10, value)) });
  }, [updatePreferences]);

  // Set priority filter
  const setPriorityFilter = useCallback((filter: FastQAPriorityFilter) => {
    updatePreferences({ priorityFilter: filter });
  }, [updatePreferences]);

  // Set auto retry failed
  const setAutoRetryFailed = useCallback((enabled: boolean) => {
    updatePreferences({ autoRetryFailed: enabled });
  }, [updatePreferences]);

  // Set max retries
  const setMaxRetries = useCallback((value: number) => {
    updatePreferences({ maxRetries: Math.max(1, Math.min(5, value)) });
  }, [updatePreferences]);

  // Set skip manual tasks
  const setSkipManualTasks = useCallback((skip: boolean) => {
    updatePreferences({ skipManualTasks: skip });
  }, [updatePreferences]);

  // Set stop on first failure
  const setStopOnFirstFailure = useCallback((stop: boolean) => {
    updatePreferences({ stopOnFirstFailure: stop });
  }, [updatePreferences]);

  // Set sound enabled
  const setSoundEnabled = useCallback((enabled: boolean) => {
    updatePreferences({ soundEnabled: enabled });
  }, [updatePreferences]);

  // Set show notifications
  const setShowNotifications = useCallback((show: boolean) => {
    updatePreferences({ showNotifications: show });
  }, [updatePreferences]);

  return {
    // Execution state
    isExecuting: streaming.isExecuting,
    progress: streaming.progress,
    completedTasks: streaming.completedTasks,
    totalTasks: streaming.totalTasks,
    currentTaskKey: streaming.currentTaskKey,
    currentTaskTitle: streaming.currentTaskTitle,
    tasksInFlight: streaming.tasksInFlight,
    taskResults: streaming.taskResults,
    error: streaming.error,

    // Preferences
    executionMode: preferences.executionMode,
    maxConcurrent: preferences.maxConcurrent,
    priorityFilter: preferences.priorityFilter,
    autoRetryFailed: preferences.autoRetryFailed,
    maxRetries: preferences.maxRetries,
    skipManualTasks: preferences.skipManualTasks,
    stopOnFirstFailure: preferences.stopOnFirstFailure,
    soundEnabled: preferences.soundEnabled,
    showNotifications: preferences.showNotifications,

    // Task data
    tasks,
    pendingTasks,
    filteredPendingTasks,
    isLoading,

    // Execution actions
    executeAll,
    executeSelected,
    executeSingle,
    retryFailed,
    abort: streaming.abort,
    reset: streaming.reset,

    // Manual task actions
    markManualPass,
    markManualFail,

    // Preference actions
    toggleExecutionMode,
    setMaxConcurrent,
    setPriorityFilter,
    setAutoRetryFailed,
    setMaxRetries,
    setSkipManualTasks,
    setStopOnFirstFailure,
    setSoundEnabled,
    setShowNotifications,
    updatePreferences,

    // Refetch
    refetch,
  };
}

export default useQuickQAExecution;
