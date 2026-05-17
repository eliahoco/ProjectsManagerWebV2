'use client';

/**
 * AutoPilotFloatingBar — Persistent status bar visible on every page when AutoPilot is active.
 * Rendered in providers.tsx (always mounted). z-[70] sits above FloatingAgentStatusBar (z-60).
 *
 * Now reads from the backend-driven queue state via AutoPilotContext.
 * Shows token exhaustion states with Wait/Switch Model/Abort options.
 *
 * E5 additions:
 * - Crash-recovery banner (fetched from GET /api/execute/queue/recovery-status on mount)
 * - Countdown timer when waiting_reset + pause_reason === 'token_exhaustion' + reset_time
 * - Visual border distinction per queue state
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Loader2, Pause, Play, SkipForward, Square, ChevronDown, ChevronUp,
  CheckCircle2, AlertCircle, Clock, Timer, RefreshCw, ShieldAlert, RotateCcw,
} from 'lucide-react';
import { useAutoPilot } from '@/contexts/AutoPilotContext';
import type { AbortAction, QueueTask, RecoveredQueueInfo } from '@/contexts/AutoPilotContext';
import { cn } from '@/lib/utils';
import { AutoPilotStatusBadge } from '@/components/codeboard/AutoPilotStatusBadge';

// Direct backend URL for non-proxied endpoints.
const BACKEND_API = 'http://localhost:8401/api/execute';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatCountdown(targetIso: string): string {
  const diffMs = new Date(targetIso).getTime() - Date.now();
  if (diffMs <= 0) return '0m 0s';
  const totalSecs = Math.floor(diffMs / 1000);
  const hours = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m ${secs}s`;
}

function formatResetClock(targetIso: string): string {
  try {
    return new Date(targetIso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '—';
  }
}

// ─── Border colour derived from queue state ───────────────────────────────────

function getBorderClass(
  isTokenExhausted: boolean,
  pauseReason: string | null,
  isPaused: boolean,
): string {
  if (isTokenExhausted && pauseReason === 'crash_recovery') return 'border-red-600/60';
  if (isTokenExhausted) return 'border-amber-600/60';
  if (isPaused && pauseReason === 'manual') return 'border-zinc-500/40';
  if (isPaused) return 'border-yellow-600/40';
  return 'border-amber-600/40';
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AutoPilotFloatingBar() {
  const {
    state, pauseAutoPilot, resumeAutoPilot, skipCurrentTask,
    abortAutoPilot, waitForReset, switchModel,
    clearRecoveredQueue, setRecoveredQueues,
  } = useAutoPilot();

  const [isExpanded, setIsExpanded] = useState(false);
  const [showAbortDialog, setShowAbortDialog] = useState(false);
  const [showTokenDialog, setShowTokenDialog] = useState(false);
  const [availableModels, setAvailableModels] = useState<Array<{
    provider: string;
    label: string;
    description?: string;
    models: string[];
  }>>([]);

  // Retry state — tracks in-progress and toast message.
  const [retryingTasks, setRetryingTasks] = useState<Set<number>>(new Set());
  const [retryToast, setRetryToast] = useState<string | null>(null);
  const retryToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // CB-2796 (S3): when the resume endpoint returns 409 with failed_count > 0,
  // we store the conflict details so the UI can surface a "Retry & Resume" button
  // that calls POST resume?retry_failed=true instead of the per-task reset loop.
  const [resumeConflict, setResumeConflict] = useState<{
    failedCount: number;
    pendingCount: number;
    suggestion: string;
  } | null>(null);

  // Countdown display string — updated every second when we have a reset_time.
  const [countdown, setCountdown] = useState<string>('');
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch available models when token dialog opens
  useEffect(() => {
    if (!showTokenDialog) return;
    fetch('/api/codeboard/execute/queue/available-models')
      .then(r => r.json())
      .then(data => setAvailableModels(data.providers || []))
      .catch(() => {});
  }, [showTokenDialog]);

  // Derived values used below — safe to compute even when not active.
  const isTokenExhausted = state.isWaitingReset;
  const pauseReason = state.pauseReason;
  const resetTime = state.resetTime;

  // Auto-show token dialog when waiting_reset.
  // Must be declared before any conditional return per Rules of Hooks —
  // moving this below `if (!state.isActive) return null` causes hook-count
  // mismatches when AutoPilot toggles active/idle between renders.
  useEffect(() => {
    if (isTokenExhausted && !showTokenDialog && !showAbortDialog) {
      setShowTokenDialog(true);
    }
  }, [isTokenExhausted, showTokenDialog, showAbortDialog]);

  // Fetch recovery status on mount — shows crash-recovery banner if needed.
  useEffect(() => {
    fetch(`${BACKEND_API}/queue/recovery-status`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.recovered_count > 0 && Array.isArray(data.queues)) {
          setRecoveredQueues(data.queues as RecoveredQueueInfo[]);
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run once on mount; setRecoveredQueues is stable (useCallback)

  // Countdown timer — starts/stops based on reset_time availability.
  useEffect(() => {
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }

    if (isTokenExhausted && pauseReason === 'token_exhaustion' && resetTime) {
      // Update immediately, then every second.
      setCountdown(formatCountdown(resetTime));
      countdownIntervalRef.current = setInterval(() => {
        setCountdown(formatCountdown(resetTime));
      }, 1000);
    } else {
      setCountdown('');
    }

    return () => {
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current);
        countdownIntervalRef.current = null;
      }
    };
  }, [isTokenExhausted, pauseReason, resetTime]);

  // Show a toast message for N ms then clear it.
  const showToast = useCallback((msg: string, ms = 3000) => {
    setRetryToast(msg);
    if (retryToastTimerRef.current) clearTimeout(retryToastTimerRef.current);
    retryToastTimerRef.current = setTimeout(() => setRetryToast(null), ms);
  }, []);

  // CB-2779: Resume with optional pre-reset of failed tasks.
  // When the queue is paused and has failed tasks, resets each one first then resumes.
  const handleResumeWithRetry = useCallback(async () => {
    if (!state.queueId) return;
    // CB-2775 race fix: refetch queue from API at click time so we don't
    // miss failed tasks because state.queue is mid-flight from SSE.
    let failedTasks: QueueTask[];
    try {
      const res = await fetch(`${BACKEND_API}/queue/${state.queueId}`, {
        signal: AbortSignal.timeout(5_000),
      });
      if (res.ok) {
        const fresh = await res.json();
        failedTasks = (fresh.tasks || []).filter((t: QueueTask) => t.status === 'failed');
      } else {
        failedTasks = state.queue.filter(t => t.status === 'failed');
      }
    } catch {
      failedTasks = state.queue.filter(t => t.status === 'failed');
    }

    if (failedTasks.length === 0) {
      // No failed tasks detected client-side — attempt a plain resume and
      // detect 409 from the server (CB-2796 S3: server may see failed tasks
      // that client hasn't received yet via SSE).
      try {
        const res = await fetch(
          `${BACKEND_API}/queue/${state.queueId}/resume`,
          { method: 'POST', signal: AbortSignal.timeout(15_000) },
        );
        if (res.status === 409) {
          const body = await res.json().catch(() => ({}));
          const details = body?.details ?? {};
          const serverFailedCount: number = details.failed_count ?? 0;
          if (serverFailedCount > 0) {
            // Surface "Retry & Resume" button with server-provided context.
            setResumeConflict({
              failedCount: serverFailedCount,
              pendingCount: details.pending_count ?? 0,
              suggestion: details.suggestion ?? 'Use retry_failed=true to retry failed tasks',
            });
            return;
          }
          showToast(body?.message || 'Cannot resume — queue is not resumable.');
          return;
        }
        if (!res.ok) {
          showToast(`Resume failed: ${res.status}`);
          return;
        }
      } catch (err) {
        // Network error — fall through to context resume for retry
        await resumeAutoPilot();
        return;
      }
      // 200 OK — sync context state
      await resumeAutoPilot();
      return;
    }

    // Pre-mark all failed tasks as in-progress so buttons disable immediately.
    setRetryingTasks(new Set(failedTasks.map(t => t.order)));
    showToast(`Resetting ${failedTasks.length} failed task${failedTasks.length !== 1 ? 's' : ''}…`);

    let failedResets = 0;
    for (const task of failedTasks) {
      try {
        const res = await fetch(
          `${BACKEND_API}/queue/${state.queueId}/task/${task.order}/reset`,
          { method: 'POST', signal: AbortSignal.timeout(15_000) },
        );
        if (res.status === 409) {
          showToast('Cannot reset — queue is not paused.');
          setRetryingTasks(new Set());
          return;
        }
        if (!res.ok) failedResets++;
      } catch { failedResets++; }
      setRetryingTasks(prev => {
        const next = new Set(prev);
        next.delete(task.order);
        return next;
      });
    }

    if (failedResets > 0) {
      showToast(`${failedResets} task${failedResets !== 1 ? 's' : ''} failed to reset — check queue state before resuming.`);
      return;
    }

    // All resets succeeded — now resume
    await resumeAutoPilot();
  }, [state.queueId, state.queue, resumeAutoPilot, showToast]);

  // CB-2796 (S3): Retry & Resume — calls POST resume?retry_failed=true.
  // Used when the backend has returned a 409 with failed_count > 0, indicating
  // the server-side bulk reset is the right recovery path.
  const handleRetryAndResume = useCallback(async () => {
    if (!state.queueId) return;
    setResumeConflict(null);
    try {
      const res = await fetch(
        `${BACKEND_API}/queue/${state.queueId}/resume?retry_failed=true`,
        { method: 'POST', signal: AbortSignal.timeout(30_000) },
      );
      if (res.ok) {
        // Context state will sync via SSE; clear any stale conflict banner.
        setResumeConflict(null);
      } else {
        const body = await res.json().catch(() => ({}));
        showToast(body?.message || `Resume failed: ${res.status}`);
      }
    } catch (err) {
      showToast(`Resume failed: ${err instanceof Error ? err.message : 'Network error'}`);
    }
  }, [state.queueId, showToast]);

  // Retry a single failed task — POST to backend reset endpoint, then refetch.
  const handleRetryTask = useCallback(async (task: QueueTask) => {
    if (!state.queueId) return;
    setRetryingTasks(prev => new Set(prev).add(task.order));
    try {
      const res = await fetch(
        `${BACKEND_API}/queue/${state.queueId}/task/${task.order}/reset`,
        { method: 'POST', signal: AbortSignal.timeout(15_000) },
      );
      if (res.status === 409) {
        showToast('Pause the queue first to retry tasks.');
        return;
      }
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        showToast(`Retry failed: ${text || res.status}`);
        return;
      }
      showToast(`${task.issue_key} reset to pending.`);
    } catch (err) {
      showToast(`Retry failed: ${err instanceof Error ? err.message : 'Network error'}`);
    } finally {
      setRetryingTasks(prev => {
        const next = new Set(prev);
        next.delete(task.order);
        return next;
      });
    }
  }, [state.queueId, showToast]);

  // Bulk retry — loop over all failed tasks sequentially.
  // CB-2775: handleRetryAllFailed removed — superseded by handleResumeWithRetry
  // (header button does reset+resume) + per-task Retry buttons in the expanded list.

  if (!state.isActive) return null;

  const currentTask = state.queue[state.currentIndex];
  const { total, completed, skipped, percent } = state.progress;
  const pendingCount = state.queue.filter(q => q.status === 'pending' || q.status === 'running').length;
  const failedTasks = state.queue.filter(t => t.status === 'failed');
  const failedCount = failedTasks.length;
  // Retry is only possible when queue is not running (backend enforces 409 otherwise).
  const queueIsRunning = state.queueStatus === 'running';

  const handleAbort = async (action: AbortAction) => {
    setShowAbortDialog(false);
    await abortAutoPilot(action);
  };

  const handleWaitForReset = async () => {
    setShowTokenDialog(false);
    await waitForReset();
  };

  const handleSwitchModel = async (provider: string, model?: string) => {
    setShowTokenDialog(false);
    await switchModel(provider, model);
  };

  const handleCrashRecoveryAction = async (
    action: 'resume' | 'skip' | 'abort',
    queue: RecoveredQueueInfo,
  ) => {
    // Act first, then clear from recovery set.
    if (action === 'resume') {
      await resumeAutoPilot();
    } else if (action === 'skip') {
      await skipCurrentTask();
    } else {
      setShowAbortDialog(true);
    }
    await clearRecoveredQueue(queue.id);
  };

  const borderClass = getBorderClass(isTokenExhausted, pauseReason ?? null, state.isPaused);

  return (
    <div className={cn(
      'fixed bottom-4 right-4 z-[70] w-[420px] bg-zinc-900 border rounded-xl shadow-2xl overflow-hidden',
      borderClass,
    )}>

      {/* Crash-recovery banner — shown when backend restart detected */}
      {state.recoveredQueues.length > 0 && state.recoveredQueues.map(rq => (
        <div
          key={rq.id}
          className="px-4 py-3 bg-red-900/20 border-b border-red-600/40 flex flex-col gap-2"
        >
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-red-400 shrink-0" />
            <span className="text-sm text-red-300 font-medium flex-1">
              AutoPilot recovered after backend restart — {rq.feature_key}
            </span>
          </div>
          <p className="text-xs text-zinc-400">
            Review and choose how to proceed:
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => handleCrashRecoveryAction('resume', rq)}
              className="px-3 py-1.5 rounded bg-green-900/50 hover:bg-green-900/70 text-green-300 text-xs transition-colors"
            >
              Resume
            </button>
            <button
              onClick={() => handleCrashRecoveryAction('skip', rq)}
              className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition-colors"
            >
              Skip current task
            </button>
            <button
              onClick={() => handleCrashRecoveryAction('abort', rq)}
              className="px-3 py-1.5 rounded bg-red-900/50 hover:bg-red-900/70 text-red-300 text-xs transition-colors"
            >
              Abort
            </button>
          </div>
        </div>
      ))}

      {/* Main bar */}
      <div className="px-4 py-3 flex items-center gap-3">
        {/* Spinner / status */}
        {isTokenExhausted ? (
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
        ) : state.isPaused ? (
          <Pause className="w-4 h-4 text-yellow-400 shrink-0" />
        ) : (
          <Loader2 className="w-4 h-4 text-amber-400 animate-spin shrink-0" />
        )}

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-amber-300 font-medium text-sm truncate">
              {state.featureKey}
            </span>
            <span className="text-zinc-500 text-xs">
              {completed + skipped}/{total}
            </span>
            {/* CB-2751: Status badge — shows live queue state/reason */}
            {state.queueStatus && (
              <AutoPilotStatusBadge
                state={state.queueStatus}
                reason={pauseReason ?? undefined}
              />
            )}
          </div>
          {currentTask && (
            <p className="text-xs text-zinc-400 truncate">
              {currentTask.issue_key} — {currentTask.issue_title}
            </p>
          )}
          {currentTask?.session_info && (
            <p className="text-xs text-cyan-400/70 truncate mt-0.5">
              {currentTask.session_info.current_action}
            </p>
          )}

          {/* Countdown row — only when token_exhaustion + reset_time */}
          {isTokenExhausted && pauseReason === 'token_exhaustion' && resetTime && countdown && (
            <div className="flex items-center gap-2 mt-1">
              <Timer className="w-3 h-3 text-amber-400 shrink-0" />
              <span className="text-xs text-amber-300">
                Auto-resumes at {formatResetClock(resetTime)} ({countdown} left)
              </span>
              <button
                onClick={resumeAutoPilot}
                className="ml-auto px-2 py-0.5 rounded bg-amber-900/50 hover:bg-amber-900/70 text-amber-300 text-xs transition-colors"
              >
                Resume now
              </button>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-1 shrink-0">
          {isTokenExhausted ? (
            <button
              onClick={() => setShowTokenDialog(true)}
              className="p-1.5 rounded hover:bg-red-900/50 text-red-400"
              title="Token exhausted — choose action"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          ) : state.isPaused ? (
            <button
              onClick={handleResumeWithRetry}
              disabled={retryingTasks.size > 0}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors',
                retryingTasks.size > 0
                  ? 'text-zinc-500 cursor-not-allowed'
                  : 'hover:bg-green-900/50 text-green-400',
              )}
              title={failedCount > 0 ? `Reset ${failedCount} failed task${failedCount !== 1 ? 's' : ''} then resume` : 'Resume'}
              data-testid="resume-btn"
            >
              <Play className="w-4 h-4" />
              {failedCount > 0 ? 'Retry failed & Resume' : 'Resume'}
            </button>
          ) : (
            <button
              onClick={pauseAutoPilot}
              className="p-1.5 rounded hover:bg-yellow-900/50 text-yellow-400"
              title="Pause"
            >
              <Pause className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={skipCurrentTask}
            className="p-1.5 rounded hover:bg-zinc-700 text-zinc-400"
            title="Skip current task"
            disabled={isTokenExhausted}
          >
            <SkipForward className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowAbortDialog(true)}
            className="p-1.5 rounded hover:bg-red-900/50 text-red-400"
            title="Abort"
          >
            <Square className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsExpanded(prev => !prev)}
            className="p-1.5 rounded hover:bg-zinc-700 text-zinc-400"
            title={isExpanded ? 'Collapse' : 'Expand queue'}
          >
            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-zinc-800">
        <div
          className={cn(
            "h-full transition-all duration-500",
            isTokenExhausted
              ? "bg-gradient-to-r from-red-500 to-red-600"
              : "bg-gradient-to-r from-amber-500 to-orange-500"
          )}
          style={{ width: `${percent}%` }}
        />
      </div>

      {/* Error message */}
      {state.lastError && (
        <div className="px-4 py-2 bg-red-900/20 border-t border-red-600/30 text-xs text-red-300">
          {state.lastError}
        </div>
      )}

      {/* Retry toast */}
      {retryToast && (
        <div className="px-4 py-2 bg-zinc-800 border-t border-zinc-700 text-xs text-zinc-300">
          {retryToast}
        </div>
      )}

      {/* CB-2796 (S3): 409 conflict banner — shown when server returns 409 with
          failed_count > 0. Surfaces a "Retry & Resume" button that calls
          POST resume?retry_failed=true (server-side bulk reset + resume). */}
      {resumeConflict !== null && (
        <div className="px-4 py-3 bg-amber-900/20 border-t border-amber-600/40 flex flex-col gap-2" data-testid="resume-conflict-banner">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span className="text-xs text-amber-300 flex-1">
              {resumeConflict.failedCount} failed task{resumeConflict.failedCount !== 1 ? 's' : ''} — {resumeConflict.pendingCount} pending.
            </span>
            <button
              onClick={handleRetryAndResume}
              className="px-3 py-1.5 rounded bg-amber-900/50 hover:bg-amber-900/70 text-amber-300 text-xs font-medium transition-colors shrink-0"
              data-testid="retry-and-resume-btn"
            >
              Retry &amp; Resume
            </button>
            <button
              onClick={() => setResumeConflict(null)}
              className="p-1 rounded hover:bg-zinc-700 text-zinc-500 text-xs"
              aria-label="Dismiss"
            >
              &#x2715;
            </button>
          </div>
        </div>
      )}

      {/* Expanded queue list */}
      {isExpanded && (
        <div className="border-t border-zinc-700">
          {/* CB-2775: failed-task counter (no bulk button — "Retry failed & Resume"
              in the header already does the same job + resumes; per-task Retry buttons
              below give granular control) */}
          {failedCount > 0 && (
            <div className="px-4 py-2 bg-zinc-800/60 border-b border-zinc-700">
              <span className="text-xs text-zinc-400">
                {failedCount} failed task{failedCount !== 1 ? 's' : ''} — use header button or per-task Retry
              </span>
            </div>
          )}
          <div className="max-h-64 overflow-y-auto">
            {state.queue.map((task, idx) => (
              <QueueRow
                key={task.issue_id}
                task={task}
                isCurrent={idx === state.currentIndex}
                queueId={state.queueId ?? ''}
                queueIsRunning={queueIsRunning}
                isRetrying={retryingTasks.has(task.order)}
                onRetry={handleRetryTask}
              />
            ))}
          </div>
        </div>
      )}

      {/* Abort dialog */}
      {showAbortDialog && (
        <div className="border-t border-zinc-700 p-4 bg-zinc-850">
          <p className="text-sm text-zinc-300 mb-3">
            Stop AutoPilot? What to do with the remaining {pendingCount} task{pendingCount !== 1 ? 's' : ''}?
          </p>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleAbort('keep')}
              className="w-full text-left px-3 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm text-zinc-300 transition-colors"
            >
              Keep Current Status
              <span className="block text-xs text-zinc-500">Leave tasks as-is</span>
            </button>
            <button
              onClick={() => handleAbort('reset_todo')}
              className="w-full text-left px-3 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm text-blue-300 transition-colors"
            >
              Reset to TODO
              <span className="block text-xs text-zinc-500">Move all pending tasks back to TODO</span>
            </button>
            <button
              onClick={() => handleAbort('mark_waiting_qa')}
              className="w-full text-left px-3 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm text-orange-300 transition-colors"
            >
              Mark Waiting QA
              <span className="block text-xs text-zinc-500">Move all pending tasks to COMPLETED_WAITING_QA</span>
            </button>
          </div>
          <button
            onClick={() => setShowAbortDialog(false)}
            className="mt-2 w-full text-center text-xs text-zinc-500 hover:text-zinc-300"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Token exhaustion dialog */}
      {showTokenDialog && isTokenExhausted && (
        <div className="border-t border-red-600/30 p-4 bg-red-900/10">
          <div className="flex items-center gap-2 mb-3">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <p className="text-sm text-red-300 font-medium">Token Quota Exhausted</p>
          </div>
          <p className="text-xs text-zinc-400 mb-3">
            The execution ran out of tokens. Choose how to proceed:
          </p>
          <div className="flex flex-col gap-2">
            {/* Wait for reset */}
            <button
              onClick={handleWaitForReset}
              className="w-full text-left px-3 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm text-cyan-300 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Timer className="w-4 h-4" />
                Wait for Token Reset
              </div>
              <span className="block text-xs text-zinc-500 mt-0.5">
                {resetTime
                  ? `Auto-resume at ${formatResetClock(resetTime)} (${countdown || '…'})`
                  : 'Auto-resume when quota resets (default: ~1 hour)'}
              </span>
            </button>

            {/* Switch model */}
            {availableModels.length > 0 && (
              <div className="bg-zinc-800 rounded p-3">
                <p className="text-xs text-zinc-400 mb-2 flex items-center gap-1">
                  <RefreshCw className="w-3 h-3" /> Switch Provider/Model
                </p>
                {availableModels.map(provider => (
                  <div key={provider.provider} className="mb-2 last:mb-0">
                    {provider.models.length === 0 ? (
                      <button
                        onClick={() => handleSwitchModel(provider.provider)}
                        className="w-full text-left px-2 py-1.5 rounded hover:bg-zinc-700 text-sm text-zinc-300 transition-colors"
                      >
                        {provider.label}
                        <span className="block text-xs text-zinc-500">{provider.description}</span>
                      </button>
                    ) : (
                      <>
                        <p className="text-xs text-zinc-500 mb-1">{provider.label}</p>
                        {provider.models.map(model => (
                          <button
                            key={model}
                            onClick={() => handleSwitchModel(provider.provider, model)}
                            className="w-full text-left px-2 py-1 rounded hover:bg-zinc-700 text-xs text-zinc-300 transition-colors"
                          >
                            {model}
                          </button>
                        ))}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Abort */}
            <button
              onClick={() => { setShowTokenDialog(false); setShowAbortDialog(true); }}
              className="w-full text-left px-3 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm text-red-300 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Square className="w-4 h-4" />
                Abort AutoPilot
              </div>
              <span className="block text-xs text-zinc-500 mt-0.5">
                Stop and choose what to do with remaining tasks
              </span>
            </button>
          </div>
          <button
            onClick={() => setShowTokenDialog(false)}
            className="mt-2 w-full text-center text-xs text-zinc-500 hover:text-zinc-300"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}

interface QueueRowProps {
  task: QueueTask;
  isCurrent: boolean;
  queueId: string;
  queueIsRunning: boolean;
  isRetrying: boolean;
  onRetry: (task: QueueTask) => void;
}

function QueueRow({ task, isCurrent, queueIsRunning, isRetrying, onRetry }: QueueRowProps) {
  const isFailed = task.status === 'failed';
  const retryDisabled = queueIsRunning || isRetrying;

  return (
    <div className={cn(
      'flex items-center gap-2 px-4 py-2 text-xs',
      isCurrent && 'bg-amber-900/20',
    )}>
      {/* Status icon */}
      {task.status === 'running' && <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin shrink-0" />}
      {task.status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5 text-green-400 shrink-0" />}
      {task.status === 'failed' && !isRetrying && <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />}
      {task.status === 'failed' && isRetrying && <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin shrink-0" />}
      {task.status === 'skipped' && <SkipForward className="w-3.5 h-3.5 text-zinc-500 shrink-0" />}
      {task.status === 'pending' && <Clock className="w-3.5 h-3.5 text-zinc-500 shrink-0" />}

      <span className="font-mono text-zinc-500">{task.issue_key}</span>
      <span className="text-zinc-300 truncate flex-1">{task.issue_title}</span>

      {/* Session progress for running tasks */}
      {task.session_info && task.status === 'running' && (
        <span className="text-cyan-400/70 text-xs shrink-0">
          {task.session_info.progress_percent}%
        </span>
      )}

      {/* Per-task retry button — only for failed tasks */}
      {isFailed && (
        <button
          onClick={() => onRetry(task)}
          disabled={retryDisabled}
          title={queueIsRunning ? 'Pause queue first to retry tasks' : 'Retry this task'}
          aria-label={`Retry ${task.issue_key}`}
          data-testid={`retry-task-btn-${task.order}`}
          className={cn(
            'p-1 rounded transition-colors shrink-0',
            retryDisabled
              ? 'text-zinc-600 cursor-not-allowed'
              : 'text-amber-400 hover:bg-amber-900/40 hover:text-amber-300',
          )}
        >
          <RotateCcw className="w-3 h-3" />
        </button>
      )}

      <span className={cn(
        'text-xs shrink-0',
        task.status === 'completed' && 'text-green-500',
        task.status === 'failed' && 'text-red-500',
        task.status === 'running' && 'text-cyan-400',
        task.status === 'skipped' && 'text-zinc-500',
        task.status === 'pending' && 'text-zinc-600',
      )}>
        {task.status}
      </span>
    </div>
  );
}
