'use client';

/**
 * Feature Execution Panel - Orchestrates sequential execution of a feature's tasks
 * Shows full hierarchy, allows selection, and executes items one by one
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  X, Play, Pause, CheckCircle2, Circle, ChevronRight, ChevronDown,
  Loader2, AlertCircle, SkipForward, Square, Rocket, List,
  ArrowRight, Clock, Zap, RefreshCw
} from 'lucide-react';
import {
  Issue,
  IssueType,
  ISSUE_TYPES,
  AutoPilotConfig,
  DEFAULT_AUTO_PILOT_CONFIG,
  AUTO_PILOT_FAIL_OPTIONS,
  AUTO_PILOT_SUCCESS_OPTIONS,
} from '@/types/codeboard';
import { useUpdateIssue, useStartExecution, useIssueDescendants, ExecutionSession } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';
import { AutoPilotConfigModal } from './AutoPilotConfigModal';

interface FeatureExecutionPanelProps {
  feature: Issue;
  allIssues: Issue[];
  isOpen: boolean;
  onClose: () => void;
  onExecutionStart: (session: ExecutionSession) => void;
  onIssueClick?: (issue: Issue) => void;
}

interface ExecutionQueueItem {
  issue: Issue;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  order: number;
}

// Get all descendant issues of a parent
function getDescendants(parentId: string, allIssues: Issue[]): Issue[] {
  const children = allIssues.filter(i => i.parentId === parentId);
  let descendants = [...children];
  for (const child of children) {
    descendants = [...descendants, ...getDescendants(child.id, allIssues)];
  }
  return descendants;
}

// Build hierarchy tree
function buildHierarchy(issues: Issue[]): Map<string | null, Issue[]> {
  const hierarchy = new Map<string | null, Issue[]>();

  for (const issue of issues) {
    const parentId = issue.parentId || null;
    if (!hierarchy.has(parentId)) {
      hierarchy.set(parentId, []);
    }
    hierarchy.get(parentId)!.push(issue);
  }

  return hierarchy;
}

// Get type order for sorting
function getTypeOrder(type: IssueType): number {
  const order: Record<IssueType, number> = {
    'FEATURE': 0,
    'EPIC': 1,
    'STORY': 2,
    'TASK': 3,
    'SUBTASK': 4,
    'BUG': 3,
  };
  return order[type] ?? 5;
}

// Sort issues by type hierarchy
function sortByHierarchy(issues: Issue[]): Issue[] {
  return [...issues].sort((a, b) => getTypeOrder(a.type) - getTypeOrder(b.type));
}

export function FeatureExecutionPanel({
  feature,
  allIssues,
  isOpen,
  onClose,
  onExecutionStart,
  onIssueClick,
}: FeatureExecutionPanelProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set([feature.id]));
  const [executionQueue, setExecutionQueue] = useState<ExecutionQueueItem[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [showSkipPrompt, setShowSkipPrompt] = useState(false);
  const [skipCompleted, setSkipCompleted] = useState<boolean | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  // Auto Pilot state
  const [showAutoPilotModal, setShowAutoPilotModal] = useState(false);
  const [autoPilotConfig, setAutoPilotConfig] = useState<AutoPilotConfig>(DEFAULT_AUTO_PILOT_CONFIG);
  const [retryCountMap, setRetryCountMap] = useState<Map<string, number>>(new Map());

  // Watchdog recovery state
  const [showRecoveryPrompt, setShowRecoveryPrompt] = useState(false);
  const [savedExecutionState, setSavedExecutionState] = useState<{
    sessionId: string;
    queueIndex: number;
    featureId: string;
    timestamp: number;
    queue: Array<{ issueId: string; issueKey: string; status: string; order: number }>;
  } | null>(null);

  // Ref to track stop requests - survives re-renders and can break async loops
  const stopRequestedRef = useRef(false);
  const currentSessionIdRef = useRef<string | null>(null);
  const autoPilotConfigRef = useRef<AutoPilotConfig>(DEFAULT_AUTO_PILOT_CONFIG);

  const updateIssue = useUpdateIssue();
  const startExecution = useStartExecution();

  // Fetch all descendants from the backend API (CB-813 fix)
  // This ensures we get ALL descendants regardless of any filters applied in the UI
  const { data: descendants = [], isLoading: isLoadingDescendants } = useIssueDescendants(
    isOpen ? feature.id : null
  );

  // Get all issues under this feature - combining feature with fetched descendants
  const featureIssues = useMemo(() => {
    return [feature, ...descendants];
  }, [feature, descendants]);

  // Build hierarchy map
  const hierarchy = useMemo(() => buildHierarchy(featureIssues), [featureIssues]);

  // Calculate progress
  const progress = useMemo(() => {
    const total = featureIssues.length;
    const done = featureIssues.filter(i => i.status === 'DONE').length;
    const inProgress = featureIssues.filter(i => i.status === 'IN_PROGRESS').length;
    return {
      total,
      done,
      inProgress,
      percent: total > 0 ? Math.round((done / total) * 100) : 0,
    };
  }, [featureIssues]);

  // Get items that are already completed or waiting for QA
  const completedItems = useMemo(() => {
    return featureIssues.filter(i =>
      (i.type === 'TASK' || i.type === 'SUBTASK') &&
      (i.status === 'DONE' || i.status === 'COMPLETED_WAITING_QA')
    );
  }, [featureIssues]);

  // Get executable items (TASKs and SUBTASKs only)
  const executableItems = useMemo(() => {
    return featureIssues.filter(i => {
      if (i.type !== 'TASK' && i.type !== 'SUBTASK') return false;
      if (i.status === 'CANCELLED') return false;

      // If skipCompleted is true, exclude DONE and COMPLETED_WAITING_QA
      if (skipCompleted === true) {
        return i.status !== 'DONE' && i.status !== 'COMPLETED_WAITING_QA';
      }

      // If skipCompleted is false (user chose to include), include all except CANCELLED
      // If skipCompleted is null (not decided yet), exclude DONE but include COMPLETED_WAITING_QA for now
      return i.status !== 'DONE';
    });
  }, [featureIssues, skipCompleted]);

  // Check for completed items and show prompt on open
  useEffect(() => {
    if (isOpen) {
      // Reset skip state
      setSkipCompleted(null);

      // Check if there are completed items
      if (completedItems.length > 0) {
        setShowSkipPrompt(true);
      } else {
        setShowSkipPrompt(false);
        setSelectedIds(new Set(executableItems.map(i => i.id)));
      }

      // WATCHDOG: Check for saved execution state that needs recovery
      try {
        const savedState = localStorage.getItem('autopilot_execution_state');
        if (savedState) {
          const state = JSON.parse(savedState);
          // Only offer recovery if:
          // 1. It's for this feature
          // 2. It's recent (within last hour)
          // 3. We're not already executing
          const isRecent = Date.now() - state.timestamp < 60 * 60 * 1000; // 1 hour
          const isThisFeature = state.featureId === feature.id;

          if (isRecent && isThisFeature && !isExecuting) {
            setSavedExecutionState(state);
            setShowRecoveryPrompt(true);
          } else if (!isRecent) {
            // Clear stale state
            localStorage.removeItem('autopilot_execution_state');
          }
        }
      } catch (e) {
        console.warn('Failed to check for saved execution state:', e);
      }
    }
  }, [isOpen, completedItems.length, feature.id, isExecuting]);

  // Update selection when skipCompleted changes
  // Only trigger on skipCompleted change to avoid infinite loops
  useEffect(() => {
    if (skipCompleted !== null) {
      // Get current executable items and select all
      const ids = executableItems.map(i => i.id);
      setSelectedIds(new Set(ids));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skipCompleted]); // Only depend on skipCompleted, read executableItems directly

  // Toggle selection
  const toggleSelection = (issueId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(issueId)) {
        next.delete(issueId);
      } else {
        next.add(issueId);
      }
      return next;
    });
  };

  // Toggle expand
  const toggleExpand = (issueId: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(issueId)) {
        next.delete(issueId);
      } else {
        next.add(issueId);
      }
      return next;
    });
  };

  // Select all
  const selectAll = () => {
    setSelectedIds(new Set(executableItems.map(i => i.id)));
  };

  // Deselect all
  const deselectAll = () => {
    setSelectedIds(new Set());
  };

  // Start feature execution
  const handleStartExecution = async () => {
    const selected = executableItems.filter(i => selectedIds.has(i.id));
    if (selected.length === 0) return;

    // Sort by hierarchy - execute in order
    const sorted = sortByHierarchy(selected);

    // Build execution queue
    const queue: ExecutionQueueItem[] = sorted.map((issue, index) => ({
      issue,
      status: 'pending',
      order: index,
    }));

    // Reset state
    stopRequestedRef.current = false;
    currentSessionIdRef.current = null;
    setLastError(null);
    setExecutionQueue(queue);
    setIsExecuting(true);
    setCurrentIndex(0);
    setIsPaused(false);

    // Update feature status to IN_PROGRESS
    await updateIssue.mutateAsync({
      issueId: feature.id,
      data: { status: 'IN_PROGRESS' },
    });

    // Start first task
    executeNext(queue, 0);
  };

  // Start Auto Pilot execution with config
  const handleStartAutoPilot = (config: AutoPilotConfig) => {
    // Store config in ref for use in async callbacks
    setAutoPilotConfig(config);
    autoPilotConfigRef.current = config;
    setRetryCountMap(new Map()); // Reset retry counts
    handleStartExecution();
  };

  // Handle successful task completion based on Auto Pilot config
  const handleAutoPilotSuccess = async (queue: ExecutionQueueItem[], index: number) => {
    const config = autoPilotConfigRef.current;
    const issue = queue[index].issue;

    console.log(`[AutoPilot] handleAutoPilotSuccess called for ${issue.key} (index ${index}), config.enabled=${config.enabled}, stopRequested=${stopRequestedRef.current}`);

    // Mark queue item as completed
    setExecutionQueue(prev => prev.map((q, i) =>
      i === index ? { ...q, status: 'completed' } : q
    ));

    // Apply success action based on config - wrapped in try/catch to ensure continuation
    try {
      let newStatus: 'DONE' | 'COMPLETED_WAITING_QA' | null = null;
      switch (config.onSuccess) {
        case 'MARK_DONE':
          newStatus = 'DONE';
          break;
        case 'MARK_WAITING_QA':
        case 'RUN_QA_TASK':
          newStatus = 'COMPLETED_WAITING_QA';
          break;
        case 'MOVE_NEXT':
          // Don't change status, just move to next
          newStatus = null;
          break;
      }

      if (newStatus) {
        await updateIssue.mutateAsync({
          issueId: issue.id,
          data: { status: newStatus },
        });
      }

      // Update parent statuses
      await updateParentStatuses(issue);
    } catch (error) {
      console.error(`[AutoPilot] Error updating status for ${issue.key}:`, error);
      // Don't let status update errors stop the auto-pilot continuation
    }

    // Continue to next if Auto Pilot is enabled and not stopped
    // This must run even if status updates failed above
    if (config.enabled && !stopRequestedRef.current) {
      console.log(`[AutoPilot] Scheduling next task execution (index ${index + 1})`);
      setTimeout(() => executeNext(queue, index + 1), 1000);
    } else {
      console.log(`[AutoPilot] NOT continuing: enabled=${config.enabled}, stopRequested=${stopRequestedRef.current}`);
    }
  };

  // Handle task failure based on Auto Pilot config
  const handleAutoPilotFailure = async (queue: ExecutionQueueItem[], index: number, errorMsg: string) => {
    const config = autoPilotConfigRef.current;
    const issue = queue[index].issue;

    console.log(`[AutoPilot] handleAutoPilotFailure called for ${issue.key} (index ${index}), config.enabled=${config.enabled}, onFail=${config.onFail}`);

    // If Auto Pilot is not enabled, use default behavior (pause)
    if (!config.enabled) {
      setExecutionQueue(prev => prev.map((q, i) =>
        i === index ? { ...q, status: 'failed' } : q
      ));
      try {
        await updateIssue.mutateAsync({
          issueId: issue.id,
          data: { status: 'TODO' },
        });
      } catch (error) {
        console.error(`[AutoPilot] Error updating status for ${issue.key}:`, error);
      }
      setIsPaused(true);
      setLastError(errorMsg);
      return;
    }

    // Apply fail action based on config
    switch (config.onFail) {
      case 'TERMINATE':
        setExecutionQueue(prev => prev.map((q, i) =>
          i === index ? { ...q, status: 'failed' } : q
        ));
        try {
          await updateIssue.mutateAsync({
            issueId: issue.id,
            data: { status: 'TODO' },
          });
        } catch (error) {
          console.error(`[AutoPilot] Error updating status for ${issue.key}:`, error);
        }
        stopRequestedRef.current = true;
        setIsExecuting(false);
        setLastError(`Auto Pilot terminated: ${errorMsg}`);
        break;

      case 'RETRY':
        // Check if we have retries left
        const currentRetries = retryCountMap.get(issue.id) || 0;
        if (currentRetries < config.maxRetries) {
          // Increment retry count
          setRetryCountMap(prev => new Map(prev).set(issue.id, currentRetries + 1));
          console.log(`[AutoPilot] Retrying ${issue.key} (attempt ${currentRetries + 1}/${config.maxRetries})`);
          // Retry the same task
          setTimeout(() => executeNext(queue, index), 2000);
        } else {
          // Max retries reached, mark as failed and continue
          console.log(`[AutoPilot] Max retries reached for ${issue.key}, marking as failed`);
          setExecutionQueue(prev => prev.map((q, i) =>
            i === index ? { ...q, status: 'failed' } : q
          ));
          try {
            await updateIssue.mutateAsync({
              issueId: issue.id,
              data: { status: 'TODO' },
            });
          } catch (error) {
            console.error(`[AutoPilot] Error updating status for ${issue.key}:`, error);
          }
          if (!stopRequestedRef.current) {
            console.log(`[AutoPilot] Scheduling next task after max retries (index ${index + 1})`);
            setTimeout(() => executeNext(queue, index + 1), 1000);
          }
        }
        break;

      case 'SKIP':
        // Skip without changing status
        setExecutionQueue(prev => prev.map((q, i) =>
          i === index ? { ...q, status: 'skipped' } : q
        ));
        // Keep the issue in TODO status
        try {
          await updateIssue.mutateAsync({
            issueId: issue.id,
            data: { status: 'TODO' },
          });
        } catch (error) {
          console.error(`[AutoPilot] Error updating status for ${issue.key}:`, error);
        }
        if (!stopRequestedRef.current) {
          console.log(`[AutoPilot] Scheduling next task after skip (index ${index + 1})`);
          setTimeout(() => executeNext(queue, index + 1), 1000);
        }
        break;

      case 'CONTINUE_MARK_FAILED':
      default:
        // Mark as failed and continue
        setExecutionQueue(prev => prev.map((q, i) =>
          i === index ? { ...q, status: 'failed' } : q
        ));
        try {
          await updateIssue.mutateAsync({
            issueId: issue.id,
            data: { status: 'TODO' },
          });
        } catch (error) {
          console.error(`[AutoPilot] Error updating status for ${issue.key}:`, error);
        }
        if (!stopRequestedRef.current) {
          console.log(`[AutoPilot] Scheduling next task after failure (index ${index + 1})`);
          setTimeout(() => executeNext(queue, index + 1), 1000);
        }
        break;
    }
  };

  // Execute next item in queue
  const executeNext = async (queue: ExecutionQueueItem[], index: number) => {
    console.log(`[AutoPilot] executeNext called for index ${index}, queue length ${queue.length}, stopRequested=${stopRequestedRef.current}`);

    // Check if stop was requested
    if (stopRequestedRef.current) {
      console.log(`[AutoPilot] Stop was requested, halting execution`);
      setIsExecuting(false);
      return;
    }

    if (index >= queue.length) {
      // All done
      console.log(`[AutoPilot] All tasks completed (index ${index} >= queue length ${queue.length})`);
      setIsExecuting(false);
      currentSessionIdRef.current = null;

      // Update feature status to DONE if all tasks completed
      const allCompleted = queue.every(q => q.status === 'completed');
      if (allCompleted) {
        try {
          await updateIssue.mutateAsync({
            issueId: feature.id,
            data: { status: 'DONE' },
          });
        } catch (error) {
          console.error(`[AutoPilot] Error updating feature status:`, error);
        }
      }
      return;
    }

    const item = queue[index];

    // Update queue status
    setExecutionQueue(prev => prev.map((q, i) =>
      i === index ? { ...q, status: 'running' } : q
    ));
    setCurrentIndex(index);
    setLastError(null);

    // Update issue status to IN_PROGRESS
    await updateIssue.mutateAsync({
      issueId: item.issue.id,
      data: { status: 'IN_PROGRESS' },
    });

    // CASCADE: Also set all parent EPICs/STORYs to IN_PROGRESS
    await cascadeInProgressToAncestors(item.issue);

    // Start execution
    try {
      const session = await startExecution.mutateAsync({
        issueId: item.issue.id,
        provider: 'claude_code',
      });

      // Check if the session was blocked due to another running task
      if (session.status === 'failed' && session.error?.includes('already running')) {
        console.warn('Execution blocked - another task is running:', session.error);
        setExecutionQueue(prev => prev.map((q, i) =>
          i === index ? { ...q, status: 'pending' } : q
        ));
        setIsPaused(true);
        setLastError(session.error || 'Another task is already running. Please wait for it to complete.');
        return;
      }

      // Track current session
      currentSessionIdRef.current = session.session_id;

      // Pass session to parent for monitoring
      onExecutionStart({
        ...session,
        issue_id: item.issue.id,
        issue_key: item.issue.key,
      } as ExecutionSession);

      // Poll for completion
      pollForCompletion(session.session_id, queue, index);
    } catch (error) {
      console.error('Failed to start execution:', error);
      setExecutionQueue(prev => prev.map((q, i) =>
        i === index ? { ...q, status: 'failed' } : q
      ));

      // Pause and show error - don't auto-advance
      setIsPaused(true);
      setLastError(`Failed to start execution for ${item.issue.key}: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  // Poll for execution completion with watchdog recovery
  const pollForCompletion = (sessionId: string, queue: ExecutionQueueItem[], index: number) => {
    let consecutiveNotFoundCount = 0;
    // INCREASED: More retries before declaring crash (was 3, now 10)
    // This prevents premature crashes when backend is slow or restarting
    const MAX_NOT_FOUND_RETRIES = 10;
    // Track polling for watchdog
    let lastPollTime = Date.now();

    // Save execution state to localStorage for watchdog recovery
    const saveExecutionState = () => {
      try {
        localStorage.setItem('autopilot_execution_state', JSON.stringify({
          sessionId,
          queueIndex: index,
          featureId: feature.id,
          timestamp: Date.now(),
          queue: queue.map(q => ({
            issueId: q.issue.id,
            issueKey: q.issue.key,
            status: q.status,
            order: q.order,
          })),
        }));
      } catch (e) {
        console.warn('Failed to save execution state:', e);
      }
    };

    // Clear saved state on completion
    const clearExecutionState = () => {
      try {
        localStorage.removeItem('autopilot_execution_state');
      } catch (e) {
        console.warn('Failed to clear execution state:', e);
      }
    };

    // Save initial state
    saveExecutionState();

    const poll = async () => {
      // Check if stop was requested
      if (stopRequestedRef.current) {
        clearExecutionState();
        setIsExecuting(false);
        return;
      }

      // Update last poll time
      lastPollTime = Date.now();

      try {
        const response = await fetch('/api/codeboard/execute/sessions');

        if (!response.ok) {
          throw new Error(`HTTP error: ${response.status}`);
        }

        const sessions: ExecutionSession[] = await response.json();
        const session = sessions.find(s => s.session_id === sessionId);

        // CRITICAL FIX: Distinguish between "session not found" and "session completed"
        if (!session) {
          consecutiveNotFoundCount++;
          console.warn(`Session ${sessionId} not found (attempt ${consecutiveNotFoundCount}/${MAX_NOT_FOUND_RETRIES})`);

          // Give it more retries before declaring it crashed
          if (consecutiveNotFoundCount < MAX_NOT_FOUND_RETRIES) {
            // Exponential backoff: 2s, 3s, 4s, 5s, etc.
            const backoffDelay = Math.min(2000 + (consecutiveNotFoundCount * 1000), 10000);
            setTimeout(poll, backoffDelay);
            return;
          }

          // Session is truly gone - try to recover by checking issue status
          console.warn(`Session ${sessionId} disappeared after ${MAX_NOT_FOUND_RETRIES} retries - checking issue status`);

          // Check if the issue was actually completed (backend might have cleaned up session)
          try {
            const issueResponse = await fetch(`/api/codeboard/issues/${queue[index].issue.id}`);
            if (issueResponse.ok) {
              const issueData = await issueResponse.json();
              if (issueData.status === 'COMPLETED_WAITING_QA' || issueData.status === 'DONE') {
                console.log(`Issue ${queue[index].issue.key} is ${issueData.status} - treating as success`);
                clearExecutionState();
                await handleAutoPilotSuccess(queue, index);
                return;
              }
            }
          } catch (e) {
            console.warn('Failed to check issue status:', e);
          }

          // Session is truly gone and issue not completed - treat as CRASHED
          console.error(`Session ${sessionId} disappeared - treating as crashed`);
          clearExecutionState();
          // Use Auto Pilot handler for crash/failure
          await handleAutoPilotFailure(queue, index, `Execution crashed for ${queue[index].issue.key} - session disappeared unexpectedly. Check if Claude Code process is still running.`);
          return;
        }

        // Reset not found counter since we found the session
        consecutiveNotFoundCount = 0;
        // Update saved state with progress
        saveExecutionState();

        if (session.status === 'completed') {
          // Use Auto Pilot handler for success
          console.log(`[AutoPilot] Session ${sessionId} completed, calling handleAutoPilotSuccess`);
          clearExecutionState();
          await handleAutoPilotSuccess(queue, index);
        } else if (session.status === 'failed' || session.status === 'cancelled') {
          // Use Auto Pilot handler for failure
          console.log(`[AutoPilot] Session ${sessionId} ${session.status}, calling handleAutoPilotFailure`);
          clearExecutionState();
          await handleAutoPilotFailure(queue, index, `Execution ${session.status} for ${queue[index].issue.key}`);
        } else {
          // Still running, poll again
          if (!stopRequestedRef.current) {
            setTimeout(poll, 2000);
          }
        }
      } catch (error) {
        console.error('Poll error:', error);
        // On network errors, retry with more patience
        consecutiveNotFoundCount++;
        if (consecutiveNotFoundCount >= MAX_NOT_FOUND_RETRIES) {
          // Don't clear state - allow manual recovery
          setIsPaused(true);
          setLastError(`Network error while polling: ${error instanceof Error ? error.message : 'Unknown error'}. Click Resume to retry.`);
        } else {
          // Exponential backoff for network errors
          const backoffDelay = Math.min(3000 + (consecutiveNotFoundCount * 2000), 15000);
          setTimeout(poll, backoffDelay);
        }
      }
    };

    poll();
  };

  // Update parent statuses based on children - cascades up the entire hierarchy
  const updateParentStatuses = async (issue: Issue) => {
    if (!issue.parentId) return;

    const parent = allIssues.find(i => i.id === issue.parentId);
    if (!parent) return;

    const siblings = allIssues.filter(i => i.parentId === parent.id);
    const allDone = siblings.every(s => s.status === 'DONE');
    const allCompletedOrDone = siblings.every(s =>
      s.status === 'DONE' || s.status === 'COMPLETED_WAITING_QA'
    );
    const anyInProgressOrTodo = siblings.some(s =>
      s.status === 'IN_PROGRESS' || s.status === 'TODO' ||
      s.status === 'COMPLETED_WAITING_QA' // Consider completed tasks as "in progress" for parent
    );

    if (allDone && parent.status !== 'DONE') {
      await updateIssue.mutateAsync({
        issueId: parent.id,
        data: { status: 'DONE' },
      });
      // Recursively update parent's parent
      await updateParentStatuses(parent);
    } else if (allCompletedOrDone && !allDone && parent.status !== 'COMPLETED_WAITING_QA' && parent.status !== 'DONE') {
      // If all children are completed/done, parent should be COMPLETED_WAITING_QA
      await updateIssue.mutateAsync({
        issueId: parent.id,
        data: { status: 'COMPLETED_WAITING_QA' },
      });
      await updateParentStatuses(parent);
    } else if (anyInProgressOrTodo && (parent.status === 'BACKLOG' || parent.status === 'TODO')) {
      // Set parent to IN_PROGRESS if any children are in progress or have work
      await updateIssue.mutateAsync({
        issueId: parent.id,
        data: { status: 'IN_PROGRESS' },
      });
      // Also cascade IN_PROGRESS up to grandparents
      await updateParentStatuses(parent);
    }
  };

  // Cascade IN_PROGRESS status to all ancestors when starting a task
  const cascadeInProgressToAncestors = async (issue: Issue) => {
    let currentIssue = issue;

    while (currentIssue.parentId) {
      const parent = allIssues.find(i => i.id === currentIssue.parentId);
      if (!parent) break;

      // Set parent to IN_PROGRESS if it's in BACKLOG or TODO
      if (parent.status === 'BACKLOG' || parent.status === 'TODO') {
        await updateIssue.mutateAsync({
          issueId: parent.id,
          data: { status: 'IN_PROGRESS' },
        });
      }

      currentIssue = parent;
    }
  };

  // Pause execution
  const handlePause = () => {
    setIsPaused(true);
  };

  // Resume execution
  const handleResume = () => {
    setIsPaused(false);
    setLastError(null);
    stopRequestedRef.current = false;

    // If current task failed, move to next; otherwise continue current
    const currentStatus = executionQueue[currentIndex]?.status;
    if (currentStatus === 'failed' || currentStatus === 'skipped') {
      executeNext(executionQueue, currentIndex + 1);
    } else if (currentStatus === 'running') {
      // Re-poll the current session if it was running
      if (currentSessionIdRef.current) {
        pollForCompletion(currentSessionIdRef.current, executionQueue, currentIndex);
      }
    } else {
      executeNext(executionQueue, currentIndex + 1);
    }
  };

  // Skip current
  const handleSkip = () => {
    setLastError(null);
    setExecutionQueue(prev => prev.map((q, i) =>
      i === currentIndex ? { ...q, status: 'skipped' } : q
    ));
    setIsPaused(false);
    executeNext(executionQueue, currentIndex + 1);
  };

  // Stop execution completely (pauses, keeps state)
  const handleStop = () => {
    // Set the stop flag so any running polls will exit
    stopRequestedRef.current = true;
    setIsPaused(true);
  };

  // Abort mission - stop everything and revert current task to TODO
  const handleAbortMission = async () => {
    // Set stop flag immediately
    stopRequestedRef.current = true;

    // Find the currently running task and revert to TODO
    const runningItem = executionQueue.find(q => q.status === 'running');
    if (runningItem) {
      try {
        await updateIssue.mutateAsync({
          issueId: runningItem.issue.id,
          data: { status: 'TODO' },
        });
      } catch (error) {
        console.error('Failed to revert task status:', error);
      }

      // Update queue to show it was aborted
      setExecutionQueue(prev => prev.map(q =>
        q.status === 'running' ? { ...q, status: 'failed' } : q
      ));
    }

    // Try to stop any running Claude process via API
    if (currentSessionIdRef.current) {
      try {
        await fetch(`/api/codeboard/execute/session/${currentSessionIdRef.current}/stop`, {
          method: 'POST',
        });
      } catch (error) {
        console.error('Failed to stop execution session:', error);
      }
    }

    // Reset all state
    currentSessionIdRef.current = null;
    setIsExecuting(false);
    setIsPaused(false);
    setLastError(null);
  };

  // Render issue row
  const renderIssueRow = (issue: Issue, depth: number = 0) => {
    const children = hierarchy.get(issue.id) || [];
    const hasChildren = children.length > 0;
    const isExpanded = expandedIds.has(issue.id);
    const isExecutable = issue.type === 'TASK' || issue.type === 'SUBTASK';
    const isSelected = selectedIds.has(issue.id);
    const isDone = issue.status === 'DONE';
    const isWaitingQA = issue.status === 'COMPLETED_WAITING_QA';
    const isInProgress = issue.status === 'IN_PROGRESS';
    const queueItem = executionQueue.find(q => q.issue.id === issue.id);

    const typeConfig = ISSUE_TYPES.find(t => t.type === issue.type);

    return (
      <div key={issue.id}>
        <div
          className={cn(
            'flex items-center gap-2 py-2 px-3 rounded-lg transition-colors',
            'hover:bg-zinc-800/50',
            isInProgress && 'bg-yellow-900/20 border-l-2 border-yellow-500',
            isWaitingQA && 'bg-orange-900/20 border-l-2 border-orange-500',
            isDone && 'opacity-60',
            queueItem?.status === 'running' && 'bg-cyan-900/30 border-l-2 border-cyan-500',
            queueItem?.status === 'completed' && 'bg-green-900/20',
            queueItem?.status === 'failed' && 'bg-red-900/20',
          )}
          style={{ paddingLeft: `${depth * 24 + 12}px` }}
        >
          {/* Expand toggle */}
          {hasChildren ? (
            <button
              onClick={() => toggleExpand(issue.id)}
              className="p-0.5 hover:bg-zinc-700 rounded"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-zinc-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-zinc-400" />
              )}
            </button>
          ) : (
            <div className="w-5" />
          )}

          {/* Selection checkbox (only for executable items) */}
          {isExecutable && !isExecuting ? (
            <button
              onClick={() => toggleSelection(issue.id)}
              className={cn(
                'w-5 h-5 rounded border flex items-center justify-center transition-colors',
                isSelected
                  ? 'bg-cyan-600 border-cyan-600'
                  : 'border-zinc-600 hover:border-zinc-400'
              )}
              disabled={isDone}
            >
              {isSelected && <CheckCircle2 className="w-3 h-3 text-white" />}
            </button>
          ) : (
            <div className="w-5 h-5 flex items-center justify-center">
              {queueItem?.status === 'running' && (
                <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
              )}
              {queueItem?.status === 'completed' && (
                <CheckCircle2 className="w-4 h-4 text-green-400" />
              )}
              {queueItem?.status === 'failed' && (
                <AlertCircle className="w-4 h-4 text-red-400" />
              )}
              {!queueItem && isDone && (
                <CheckCircle2 className="w-4 h-4 text-green-400" />
              )}
            </div>
          )}

          {/* Type icon */}
          <span className={cn('text-sm', typeConfig?.color)}>
            {typeConfig?.icon}
          </span>

          {/* Issue key */}
          <span className="text-xs font-mono text-zinc-500">
            {issue.key}
          </span>

          {/* Title */}
          <button
            onClick={() => onIssueClick?.(issue)}
            className="flex-1 text-left text-sm text-zinc-200 hover:text-white truncate"
          >
            {issue.title}
          </button>

          {/* Status badge */}
          <span className={cn(
            'text-xs px-2 py-0.5 rounded',
            issue.status === 'DONE' && 'bg-green-900/50 text-green-400',
            issue.status === 'COMPLETED_WAITING_QA' && 'bg-orange-900/50 text-orange-400',
            issue.status === 'IN_PROGRESS' && 'bg-yellow-900/50 text-yellow-400',
            issue.status === 'TODO' && 'bg-blue-900/50 text-blue-400',
            issue.status === 'BACKLOG' && 'bg-zinc-800 text-zinc-400',
          )}>
            {issue.status === 'COMPLETED_WAITING_QA' ? 'WAITING QA' : issue.status.replace('_', ' ')}
          </span>
        </div>

        {/* Children */}
        {hasChildren && isExpanded && (
          <div>
            {sortByHierarchy(children).map(child => renderIssueRow(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-700">
          <div className="flex items-center gap-3">
            <Rocket className="w-6 h-6 text-amber-500" />
            <div>
              <h2 className="font-semibold text-lg">Feature Implementation</h2>
              <p className="text-sm text-zinc-400">{feature.title}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress bar */}
        <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-zinc-300">
              Overall Progress: {progress.done}/{progress.total} items
            </span>
            <span className="text-sm font-medium text-cyan-400">
              {progress.percent}%
            </span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-600 to-green-500 transition-all duration-500"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        </div>

        {/* Selection controls */}
        {!isExecuting && (
          <div className="flex items-center justify-between px-6 py-3 border-b border-zinc-800">
            <div className="flex items-center gap-3">
              <button
                onClick={selectAll}
                className="text-sm text-cyan-400 hover:text-cyan-300"
              >
                Select All Tasks
              </button>
              <span className="text-zinc-600">|</span>
              <button
                onClick={deselectAll}
                className="text-sm text-zinc-400 hover:text-zinc-300"
              >
                Deselect All
              </button>
            </div>
            <span className="text-sm text-zinc-400">
              {selectedIds.size} items selected
            </span>
          </div>
        )}

        {/* Execution queue progress */}
        {isExecuting && (
          <div className={cn(
            "px-6 py-3 border-b border-zinc-800",
            isPaused && lastError ? "bg-red-900/20" : "bg-cyan-900/10"
          )}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {isPaused ? (
                  <AlertCircle className="w-5 h-5 text-yellow-400" />
                ) : (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" />
                )}
                <span className={cn("text-sm", isPaused ? "text-yellow-300" : "text-cyan-300")}>
                  {isPaused ? 'Paused' : 'Executing'}: {currentIndex + 1}/{executionQueue.length}
                </span>
                {executionQueue[currentIndex] && (
                  <span className="text-sm text-zinc-400">
                    - {executionQueue[currentIndex].issue.title}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {isPaused ? (
                  <button
                    onClick={handleResume}
                    className="flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded text-sm"
                  >
                    <Play className="w-4 h-4" />
                    {lastError ? 'Continue to Next' : 'Resume'}
                  </button>
                ) : (
                  <button
                    onClick={handlePause}
                    className="flex items-center gap-1 px-3 py-1.5 bg-yellow-600 hover:bg-yellow-500 rounded text-sm"
                  >
                    <Pause className="w-4 h-4" />
                    Pause
                  </button>
                )}
                <button
                  onClick={handleSkip}
                  className="flex items-center gap-1 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded text-sm"
                >
                  <SkipForward className="w-4 h-4" />
                  Skip
                </button>
                <button
                  onClick={handleAbortMission}
                  className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded text-sm font-medium"
                >
                  <Square className="w-4 h-4" />
                  Abort Mission
                </button>
              </div>
            </div>
            {/* Error message display */}
            {lastError && (
              <div className="mt-2 p-2 bg-red-900/30 border border-red-600/30 rounded text-sm text-red-300">
                <strong>Error:</strong> {lastError}
              </div>
            )}
            {/* Auto Pilot status indicator */}
            {autoPilotConfig.enabled && (
              <div className="mt-2 p-2 bg-amber-900/20 border border-amber-600/20 rounded text-sm">
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-400" />
                  <span className="text-amber-200 font-medium">Auto Pilot Active</span>
                  <span className="text-zinc-400">|</span>
                  <span className="text-zinc-300">
                    On Fail: <span className="text-red-300">{AUTO_PILOT_FAIL_OPTIONS.find(o => o.value === autoPilotConfig.onFail)?.label}</span>
                    {autoPilotConfig.onFail === 'RETRY' && ` (${autoPilotConfig.maxRetries}x)`}
                  </span>
                  <span className="text-zinc-400">|</span>
                  <span className="text-zinc-300">
                    On Success: <span className="text-green-300">{AUTO_PILOT_SUCCESS_OPTIONS.find(o => o.value === autoPilotConfig.onSuccess)?.label}</span>
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* WATCHDOG: Recovery prompt for interrupted execution */}
        {showRecoveryPrompt && savedExecutionState && (
          <div className="px-6 py-4 border-b border-zinc-700 bg-cyan-900/30">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <RefreshCw className="w-5 h-5 text-cyan-400" />
                <div>
                  <p className="text-sm text-cyan-200">
                    <strong>Execution Recovery Available</strong>
                  </p>
                  <p className="text-xs text-cyan-400/70 mt-0.5">
                    Auto-pilot was interrupted {Math.round((Date.now() - savedExecutionState.timestamp) / 60000)} minutes ago
                    at task {savedExecutionState.queueIndex + 1} of {savedExecutionState.queue.length}.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    // Resume execution from saved state
                    const remainingQueue = savedExecutionState.queue
                      .filter(q => q.status === 'pending' || q.status === 'running')
                      .map(q => {
                        const issue = featureIssues.find(i => i.id === q.issueId);
                        if (!issue) return null;
                        return { issue, status: 'pending' as const, order: q.order };
                      })
                      .filter(Boolean) as ExecutionQueueItem[];

                    if (remainingQueue.length > 0) {
                      setExecutionQueue(remainingQueue);
                      setIsExecuting(true);
                      setCurrentIndex(0);
                      setIsPaused(false);
                      stopRequestedRef.current = false;
                      executeNext(remainingQueue, 0);
                    }

                    setShowRecoveryPrompt(false);
                    setSavedExecutionState(null);
                  }}
                  className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-sm font-medium"
                >
                  Resume Execution
                </button>
                <button
                  onClick={() => {
                    localStorage.removeItem('autopilot_execution_state');
                    setShowRecoveryPrompt(false);
                    setSavedExecutionState(null);
                  }}
                  className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded text-sm"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Skip completed prompt */}
        {showSkipPrompt && (
          <div className="px-6 py-4 border-b border-zinc-700 bg-amber-900/20">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertCircle className="w-5 h-5 text-amber-400" />
                <div>
                  <p className="text-sm text-amber-200">
                    {completedItems.length} task{completedItems.length > 1 ? 's are' : ' is'} already completed or waiting for QA.
                  </p>
                  <p className="text-xs text-amber-400/70 mt-0.5">
                    Would you like to skip these and only execute pending tasks?
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setSkipCompleted(true);
                    setShowSkipPrompt(false);
                  }}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded text-sm font-medium"
                >
                  Yes, Skip Completed
                </button>
                <button
                  onClick={() => {
                    setSkipCompleted(false);
                    setShowSkipPrompt(false);
                  }}
                  className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded text-sm"
                >
                  No, Include All
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Issue hierarchy */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoadingDescendants ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin mb-4" />
              <p className="text-zinc-400 text-sm">Loading issue hierarchy...</p>
            </div>
          ) : (
            renderIssueRow(feature)
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-700 bg-zinc-900/50">
          <div className="text-sm text-zinc-500">
            <Clock className="w-4 h-4 inline mr-1" />
            {executableItems.length} executable tasks
          </div>
          {!isExecuting ? (
            <div className="flex items-center gap-3">
              <button
                onClick={handleStartExecution}
                disabled={selectedIds.size === 0}
                className={cn(
                  'flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-colors',
                  selectedIds.size > 0
                    ? 'bg-zinc-700 hover:bg-zinc-600 text-zinc-200'
                    : 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                )}
              >
                <Play className="w-4 h-4" />
                Manual Start
              </button>
              <button
                onClick={() => setShowAutoPilotModal(true)}
                disabled={selectedIds.size === 0}
                className={cn(
                  'flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-colors',
                  selectedIds.size > 0
                    ? 'bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white'
                    : 'bg-zinc-700 text-zinc-400 cursor-not-allowed'
                )}
              >
                <Zap className="w-5 h-5" />
                Auto Pilot
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              {autoPilotConfig.enabled && (
                <div className="flex items-center gap-2 px-3 py-1 bg-amber-900/30 border border-amber-600/30 rounded text-sm">
                  <Zap className="w-4 h-4 text-amber-400" />
                  <span className="text-amber-200">Auto Pilot</span>
                </div>
              )}
              <span className="text-sm text-cyan-400">
                {isPaused ? 'Paused' : 'Running...'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Auto Pilot Configuration Modal */}
      <AutoPilotConfigModal
        isOpen={showAutoPilotModal}
        onClose={() => setShowAutoPilotModal(false)}
        onStart={handleStartAutoPilot}
        taskCount={selectedIds.size}
      />
    </div>
  );
}
