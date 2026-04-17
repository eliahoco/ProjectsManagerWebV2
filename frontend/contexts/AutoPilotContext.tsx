'use client';

/**
 * AutoPilot Context — Thin frontend wrapper around the backend-driven queue.
 *
 * The execution loop lives entirely on the backend (autopilot_queue_service).
 * This context:
 *   1. Creates queues via POST /api/codeboard/execute/queue
 *   2. Tracks progress via SSE /api/codeboard/execute/queue/{id}/stream
 *   3. Sends control commands (pause/resume/skip/abort) via POST
 *   4. On mount, checks for an already-active queue and reattaches
 *
 * The provider lives inside QueryClientWrapper (in providers.tsx) so it never
 * unmounts during client-side navigation.
 */

import {
  createContext,
  useContext,
  useState,
  useRef,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type {
  Issue,
  AutoPilotConfig,
  ExecutionMode,
} from '@/types/codeboard';
import { DEFAULT_AUTO_PILOT_CONFIG } from '@/types/codeboard';

// ─── Types ───────────────────────────────────────────────────────────

/** A single task in the backend queue — mirrors the backend's serialized format. */
export interface QueueTask {
  issue_id: string;
  issue_key: string;
  issue_title: string;
  order: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  execution_mode: string;
  session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  retry_count: number;
  session_info: {
    phase: string;
    progress_percent: number;
    current_action: string;
    files_read: number;
    files_written: number;
    commands_run: number;
  } | null;
}

/** Full queue status as returned by the backend. */
export interface QueueStatus {
  id: string;
  feature_id: string;
  feature_key: string;
  project_id: string;
  provider: string;
  model: string | null;
  status: 'pending' | 'running' | 'paused' | 'waiting_reset' | 'completed' | 'aborted';
  current_index: number;
  tasks: QueueTask[];
  config: { on_success: string; on_fail: string; max_retries: number };
  progress: {
    total: number;
    completed: number;
    skipped: number;
    failed: number;
    pending: number;
    percent: number;
  };
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  last_error: string | null;
}

/** Legacy queue item format — still used by FeatureExecutionPanel to build the initial queue. */
export interface AutoPilotQueueItem {
  issue: Issue;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  order: number;
}

export type AbortAction = 'keep' | 'reset_todo' | 'mark_waiting_qa';

export interface AutoPilotState {
  isActive: boolean;
  isPaused: boolean;
  isWaitingReset: boolean;
  queueId: string | null;
  featureId: string | null;
  featureKey: string | null;
  featureTitle: string | null;
  projectId: string | null;
  queue: QueueTask[];
  currentIndex: number;
  progress: {
    total: number;
    completed: number;
    skipped: number;
    failed: number;
    pending: number;
    percent: number;
  };
  lastError: string | null;
  queueStatus: string | null;
}

export interface StartAutoPilotParams {
  feature: Issue;
  projectId: string;
  queue: AutoPilotQueueItem[];
  config: AutoPilotConfig;
  taskActions: Map<string, ExecutionMode | 'skip'>;
}

export interface AutoPilotContextValue {
  state: AutoPilotState;
  startAutoPilot: (params: StartAutoPilotParams) => Promise<void>;
  pauseAutoPilot: () => Promise<void>;
  resumeAutoPilot: () => Promise<void>;
  abortAutoPilot: (action: AbortAction) => Promise<void>;
  skipCurrentTask: () => Promise<void>;
  waitForReset: (resetTime?: string) => Promise<void>;
  switchModel: (provider: string, model?: string) => Promise<void>;
}

// ─── Context ─────────────────────────────────────────────────────────

const AutoPilotContext = createContext<AutoPilotContextValue | null>(null);

export function useAutoPilot() {
  const ctx = useContext(AutoPilotContext);
  if (!ctx) throw new Error('useAutoPilot must be used within AutoPilotProvider');
  return ctx;
}

// ─── Constants ───────────────────────────────────────────────────────

const API_BASE = '/api/codeboard/execute';
// Direct backend URL for SSE (Next.js proxy can't stream SSE responses)
const BACKEND_SSE_BASE = 'http://localhost:8401/api/execute';
const FETCH_TIMEOUT = 30_000;

const EMPTY_PROGRESS = { total: 0, completed: 0, skipped: 0, failed: 0, pending: 0, percent: 0 };

// ─── Provider ────────────────────────────────────────────────────────

export function AutoPilotProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // ── State ──
  const [isActive, setIsActive] = useState(false);
  const [queueId, setQueueId] = useState<string | null>(null);
  const [featureId, setFeatureId] = useState<string | null>(null);
  const [featureKey, setFeatureKey] = useState<string | null>(null);
  const [featureTitle, setFeatureTitle] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [queueTasks, setQueueTasks] = useState<QueueTask[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [progress, setProgress] = useState(EMPTY_PROGRESS);
  const [lastError, setLastError] = useState<string | null>(null);
  const [queueStatus, setQueueStatus] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [isWaitingReset, setIsWaitingReset] = useState(false);

  // Ref for SSE cleanup
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Tracks whether SSE is currently healthy — used to gate polling so that SSE
  // and polling never run simultaneously (which would cause request storms).
  const sseHealthyRef = useRef(true);

  // Refs for invalidation deduplication — track last seen status/task count
  const prevStatusRef = useRef<string | null>(null);
  const prevTaskCountRef = useRef<number>(0);

  // ── SSE / Polling for queue status ──

  const applyQueueStatus = useCallback((data: QueueStatus) => {
    setQueueTasks(data.tasks);
    setCurrentIndex(data.current_index);
    setProgress(data.progress);
    setLastError(data.last_error);
    setQueueStatus(data.status);
    setFeatureKey(data.feature_key);
    setProjectId(data.project_id);
    setFeatureId(data.feature_id);
    setIsPaused(data.status === 'paused');
    setIsWaitingReset(data.status === 'waiting_reset');

    // If terminal states, mark inactive
    if (data.status === 'completed' || data.status === 'aborted') {
      setIsActive(false);
      // Clean up SSE/polling
      // (will be handled in the effect cleanup or we do it explicitly)
    }

    // Only invalidate React Query caches on meaningful state changes, not every
    // SSE tick. Prevents request storms when SSE fires at 2s intervals with no
    // actual status change.
    const currentTaskCount = data.tasks?.length ?? 0;
    const statusChanged = data.status !== prevStatusRef.current;
    const taskCountChanged = currentTaskCount !== prevTaskCountRef.current;

    if (statusChanged || taskCountChanged) {
      queryClient.invalidateQueries({ queryKey: ['issues'] });
      queryClient.invalidateQueries({ queryKey: ['issue'] });
      queryClient.invalidateQueries({ queryKey: ['execution-sessions'] });
      prevStatusRef.current = data.status;
      prevTaskCountRef.current = currentTaskCount;
    }
  }, [queryClient]);

  const startPolling = useCallback((qId: string) => {
    // Guard: don't stack intervals if one is already running
    if (pollIntervalRef.current) return;

    const poll = async () => {
      // SSE recovered — stop polling, it's now redundant
      if (sseHealthyRef.current) {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/queue/${qId}`, {
          signal: AbortSignal.timeout(FETCH_TIMEOUT),
        });
        if (!res.ok) return;
        const data: QueueStatus = await res.json();
        applyQueueStatus(data);

        // Stop polling if done
        if (data.status === 'completed' || data.status === 'aborted') {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
        }
      } catch { /* network error — keep polling */ }
    };

    // Poll immediately, then every 2s
    poll();
    pollIntervalRef.current = setInterval(poll, 2000);
  }, [applyQueueStatus]);

  const startTracking = useCallback((qId: string) => {
    // Clean up previous tracking
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    // Try SSE first (directly to backend — Next.js proxy can't stream)
    try {
      const es = new EventSource(`${BACKEND_SSE_BASE}/queue/${qId}/stream`);

      es.onopen = () => {
        // SSE connection established — mark healthy and stop any active polling
        sseHealthyRef.current = true;
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      };

      es.onmessage = (event) => {
        try {
          const data: QueueStatus = JSON.parse(event.data);
          applyQueueStatus(data);
        } catch { /* ignore parse errors */ }
      };

      es.addEventListener('done', (event) => {
        try {
          const data: QueueStatus = JSON.parse((event as MessageEvent).data);
          applyQueueStatus(data);
        } catch { /* */ }
        es.close();
        eventSourceRef.current = null;
        sseHealthyRef.current = false;
      });

      es.addEventListener('error', () => {
        // SSE failed — mark unhealthy, fall back to polling
        sseHealthyRef.current = false;
        es.close();
        eventSourceRef.current = null;
        startPolling(qId);
        // Schedule SSE self-healing retry after 30s
        setTimeout(() => {
          if (!sseHealthyRef.current) {
            startTracking(qId);
          }
        }, 30_000);
      });

      eventSourceRef.current = es;
    } catch {
      // SSE not supported — use polling
      sseHealthyRef.current = false;
      startPolling(qId);
    }
  }, [applyQueueStatus, startPolling]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // ── Check for active queue on mount ──
  useEffect(() => {
    const checkActive = async () => {
      try {
        const res = await fetch(`${API_BASE}/queue/active`, {
          signal: AbortSignal.timeout(FETCH_TIMEOUT),
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.active && data.queue) {
          const q: QueueStatus = data.queue;
          setQueueId(q.id);
          setIsActive(true);
          applyQueueStatus(q);
          startTracking(q.id);
        }
      } catch { /* no active queue or backend unavailable */ }
    };
    checkActive();
  }, [applyQueueStatus, startTracking]);

  // ── API helpers ──

  const postQueue = async (endpoint: string, body?: object) => {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(FETCH_TIMEOUT),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  };

  // ── Public API ──

  const startAutoPilotFn = useCallback(async (params: StartAutoPilotParams) => {
    const { feature, projectId: pid, queue: q, config: cfg, taskActions: ta } = params;

    // Transform frontend queue items to backend format
    const tasks = q.map(item => {
      const action = ta.get(item.issue.id);
      let executionMode = 'implement';
      let force = false;
      if (action === 'skip') executionMode = 'skip';
      else if (action === 'audit') { executionMode = 'audit'; force = true; }
      else if (action === 'rewrite') { executionMode = 'rewrite'; force = true; }

      return {
        issue_id: item.issue.id,
        issue_key: item.issue.key,
        issue_title: item.issue.title,
        execution_mode: executionMode,
        force,
      };
    });

    // Map config
    const backendConfig: Record<string, string | number> = {
      on_success: cfg.onSuccess || 'MARK_WAITING_QA',
      on_fail: cfg.onFail || 'CONTINUE_MARK_FAILED',
      max_retries: cfg.maxRetries || 3,
    };

    try {
      const result = await postQueue(`${API_BASE}/queue`, {
        feature_id: feature.id,
        feature_key: feature.key,
        project_id: pid,
        tasks,
        config: backendConfig,
        provider: 'claude_code',
        auto_start: true,
      });

      // Set state from the returned queue status
      const qId = result.id;
      setQueueId(qId);
      setFeatureId(feature.id);
      setFeatureKey(feature.key);
      setFeatureTitle(feature.title);
      setProjectId(pid);
      setIsActive(true);
      setLastError(null);
      applyQueueStatus(result);

      // Start SSE tracking
      startTracking(qId);
    } catch (error) {
      setLastError(`Failed to start queue: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }, [applyQueueStatus, startTracking]);

  const pauseAutoPilotFn = useCallback(async () => {
    if (!queueId) return;
    try {
      await postQueue(`${API_BASE}/queue/${queueId}/pause`);
      setIsPaused(true);
    } catch (error) {
      console.error('[AutoPilot] Pause failed:', error);
    }
  }, [queueId]);

  const resumeAutoPilotFn = useCallback(async () => {
    if (!queueId) return;
    try {
      await postQueue(`${API_BASE}/queue/${queueId}/resume`);
      setIsPaused(false);
      setIsWaitingReset(false);
      setLastError(null);
    } catch (error) {
      console.error('[AutoPilot] Resume failed:', error);
    }
  }, [queueId]);

  const skipCurrentTaskFn = useCallback(async () => {
    if (!queueId) return;
    try {
      await postQueue(`${API_BASE}/queue/${queueId}/skip`);
    } catch (error) {
      console.error('[AutoPilot] Skip failed:', error);
    }
  }, [queueId]);

  const abortAutoPilotFn = useCallback(async (action: AbortAction) => {
    if (!queueId) return;

    // Map frontend action names to backend
    const backendAction = action === 'keep' ? 'leave'
      : action === 'reset_todo' ? 'reset_todo'
      : action === 'mark_waiting_qa' ? 'mark_skipped'
      : 'leave';

    try {
      await postQueue(`${API_BASE}/queue/${queueId}/abort`, { action: backendAction });

      // Clean up tracking
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }

      setIsActive(false);
      setIsPaused(false);
      setIsWaitingReset(false);
      setLastError(null);
      setQueueStatus('aborted');

      queryClient.invalidateQueries({ queryKey: ['issues'] });
      queryClient.invalidateQueries({ queryKey: ['issue'] });
    } catch (error) {
      console.error('[AutoPilot] Abort failed:', error);
    }
  }, [queueId, queryClient]);

  const waitForResetFn = useCallback(async (resetTime?: string) => {
    if (!queueId) return;
    try {
      await postQueue(`${API_BASE}/queue/${queueId}/wait-for-reset`, {
        reset_time: resetTime || null,
      });
    } catch (error) {
      console.error('[AutoPilot] Wait-for-reset failed:', error);
    }
  }, [queueId]);

  const switchModelFn = useCallback(async (provider: string, model?: string) => {
    if (!queueId) return;
    try {
      await postQueue(`${API_BASE}/queue/${queueId}/switch-model`, {
        provider,
        model: model || null,
      });
      setIsWaitingReset(false);
      setLastError(null);
    } catch (error) {
      console.error('[AutoPilot] Switch model failed:', error);
    }
  }, [queueId]);

  // ── Context value ──

  const state: AutoPilotState = {
    isActive,
    isPaused,
    isWaitingReset,
    queueId,
    featureId,
    featureKey,
    featureTitle,
    projectId,
    queue: queueTasks,
    currentIndex,
    progress,
    lastError,
    queueStatus,
  };

  return (
    <AutoPilotContext.Provider value={{
      state,
      startAutoPilot: startAutoPilotFn,
      pauseAutoPilot: pauseAutoPilotFn,
      resumeAutoPilot: resumeAutoPilotFn,
      abortAutoPilot: abortAutoPilotFn,
      skipCurrentTask: skipCurrentTaskFn,
      waitForReset: waitForResetFn,
      switchModel: switchModelFn,
    }}>
      {children}
    </AutoPilotContext.Provider>
  );
}
