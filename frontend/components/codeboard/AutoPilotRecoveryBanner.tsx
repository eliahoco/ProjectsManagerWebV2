'use client';

/**
 * AutoPilotRecoveryBanner — Universal recovery surface for ALL AutoPilot states.
 *
 * Polls GET /api/execute/queue/recovery-status on mount + every 30s +
 * re-fetches on relevant SSE events.
 *
 * Renders a banner card per recoverable or zombie queue. Each banner shows:
 *   - State-friendly label
 *   - Reason explanation
 *   - Countdown (when waiting_reset + reset_time)
 *   - Action button mapped from suggested_action
 *
 * Dismiss behaviour: per-queue dismissal key is
 *   localStorage `autopilot.banner.dismissed.<queueId>` = `<state>:<reason>`
 * Banner reappears if state/reason changes.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  AlertTriangle, Clock, RefreshCw, ShieldAlert, X, Play,
  AlertCircle, Zap, CheckCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface RecoverableEntry {
  queue_id: string;
  key: string;
  /** CB-2802: project_id is required by all scoped queue endpoints. */
  project_id: string;
  state: string;
  reason: string | null;
  reset_time?: string | null;
  attempt_count?: number;
  suggested_action: 'resume' | 'wait' | 'retry-failed' | 'force-recover' | 'abort';
}

interface RecoveryStatusPayload {
  recoverable: RecoverableEntry[];
  zombie: RecoverableEntry[];
  auto_resume_pending: Array<{ queue_id: string; key: string; state: string }>;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BACKEND_ORIGIN = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8401';
const BACKEND_API = `${BACKEND_ORIGIN}/api/execute`;
const BACKEND_EVENTS_URL = `${BACKEND_ORIGIN}/api/execute/queue/events`;
const POLL_MS = 30_000;
const LS_DISMISS_PREFIX = 'autopilot.banner.dismissed.';

// ─── Label / copy helpers ─────────────────────────────────────────────────────

export function getStateFriendlyLabel(state: string, reason: string | null): string {
  const key = `${state}/${reason ?? ''}`;
  switch (key) {
    case 'waiting_reset/rate_limit_5h':
      return 'Anthropic 5-hour limit hit — auto-resume armed';
    case 'waiting_reset/rate_limit_weekly':
      return 'Anthropic weekly limit hit — auto-resume armed';
    case 'waiting_reset/token_exhaustion':
      return 'Token quota exhausted — auto-resume armed';
    case 'paused/credit_exhaustion':
      return 'Credits exhausted — top up Anthropic balance to continue';
    case 'paused/auth_failure':
      return 'Anthropic authentication failed — check API key';
    case 'paused/crash_recovery':
      return 'Backend restarted mid-run — resume to continue';
    case 'paused/manual':
      return 'Paused by you — resume when ready';
    case 'running/zombie_detected':
      return 'Queue marked running but no live coroutine — recover to clear stale state';
    default:
      if (state === 'waiting_reset') return `Waiting for API reset (${reason ?? 'unknown'})`;
      if (state === 'paused')        return `Paused — ${reason ?? 'unknown reason'}`;
      if (state === 'running')       return `Running — ${reason ?? 'no details'}`;
      return `${state}${reason ? `/${reason}` : ''}`;
  }
}

function getReasonExplanation(state: string, reason: string | null): string {
  const key = `${state}/${reason ?? ''}`;
  switch (key) {
    case 'waiting_reset/rate_limit_5h':
      return 'Anthropic enforces a 5-hour usage window. The queue will auto-resume once the window resets.';
    case 'waiting_reset/rate_limit_weekly':
      return 'The weekly Anthropic usage limit was reached. Auto-resume is armed for when the window opens.';
    case 'waiting_reset/token_exhaustion':
      return 'The API token quota was exhausted. AutoPilot will auto-resume when the quota refreshes.';
    case 'paused/credit_exhaustion':
      return 'Your Anthropic account has no remaining credits. Top up at console.anthropic.com to continue.';
    case 'paused/auth_failure':
      return 'The Anthropic API key was rejected (401/403). Update the key in Settings and then resume.';
    case 'paused/crash_recovery':
      return 'The backend restarted while AutoPilot was executing. The queue is safe — resume to continue from where it stopped.';
    case 'paused/manual':
      return 'You paused the queue. It will wait until you click Resume.';
    case 'running/zombie_detected':
      return 'The queue record shows RUNNING but no active coroutine is executing tasks. Force-recover to reset state.';
    default:
      return '';
  }
}

// ─── Countdown helpers ────────────────────────────────────────────────────────

function formatCountdown(isoString: string): string {
  const diffMs = new Date(isoString).getTime() - Date.now();
  if (diffMs <= 0) return 'now';
  const totalSecs = Math.floor(diffMs / 1000);
  const h = Math.floor(totalSecs / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = totalSecs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatResetClock(isoString: string): string {
  try {
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '—';
  }
}

// ─── localStorage dismiss helpers ─────────────────────────────────────────────

function getDismissKey(queueId: string) {
  return `${LS_DISMISS_PREFIX}${queueId}`;
}

function getDismissedStateReason(queueId: string): string | null {
  try {
    return localStorage.getItem(getDismissKey(queueId));
  } catch {
    return null;
  }
}

function setDismissed(queueId: string, state: string, reason: string | null) {
  try {
    localStorage.setItem(getDismissKey(queueId), `${state}:${reason ?? ''}`);
  } catch { /* ignore */ }
}

function isDismissed(entry: RecoverableEntry): boolean {
  const stored = getDismissedStateReason(entry.queue_id);
  if (!stored) return false;
  return stored === `${entry.state}:${entry.reason ?? ''}`;
}

// ─── Icon helpers ─────────────────────────────────────────────────────────────

function getIcon(entry: RecoverableEntry) {
  if (entry.reason === 'zombie_detected') return <Zap className="w-4 h-4 text-red-400 shrink-0" />;
  if (entry.state === 'waiting_reset')    return <Clock className="w-4 h-4 text-blue-400 shrink-0" />;
  if (entry.reason === 'crash_recovery')  return <ShieldAlert className="w-4 h-4 text-red-400 shrink-0" />;
  if (entry.reason === 'manual')          return <CheckCircle className="w-4 h-4 text-zinc-400 shrink-0" />;
  return <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />;
}

function getBannerBorderClass(entry: RecoverableEntry): string {
  if (entry.reason === 'zombie_detected')  return 'border-red-600/40 bg-red-900/10';
  if (entry.state === 'waiting_reset')     return 'border-blue-600/40 bg-blue-900/10';
  if (entry.reason === 'crash_recovery')   return 'border-red-600/40 bg-red-900/10';
  if (entry.reason === 'manual')           return 'border-zinc-600/40 bg-zinc-800/10';
  if (entry.reason === 'credit_exhaustion' || entry.reason === 'auth_failure') {
    return 'border-red-600/40 bg-red-900/10';
  }
  return 'border-amber-600/40 bg-amber-900/10';
}

// ─── Abort confirm dialog state ───────────────────────────────────────────────

interface AbortDialogState {
  queueId: string;
  key: string;
  /** CB-2802: needed to supply ?project_id= to the abort endpoint. */
  projectId: string;
}

// ─── Per-card action error ────────────────────────────────────────────────────

interface ActionError {
  message: string;
}


// ─── Per-entry countdown component ───────────────────────────────────────────

function CountdownLine({ resetTime }: { resetTime: string }) {
  const [display, setDisplay] = useState(() => formatCountdown(resetTime));

  useEffect(() => {
    const id = setInterval(() => {
      setDisplay(formatCountdown(resetTime));
    }, 1000);
    return () => clearInterval(id);
  }, [resetTime]);

  return (
    <p className="text-xs text-blue-300 flex items-center gap-1 mt-1" data-testid="countdown-line">
      <Clock className="w-3 h-3 shrink-0" />
      Auto-resumes at {formatResetClock(resetTime)} ({display} left)
    </p>
  );
}

// ─── Single banner card ───────────────────────────────────────────────────────

interface BannerCardProps {
  entry: RecoverableEntry;
  onDismiss: (entry: RecoverableEntry) => void;
  onAction: (entry: RecoverableEntry, action: string) => Promise<void>;
  actionLoading: boolean;
  onAbortRequest: (entry: RecoverableEntry) => void;
  actionError?: ActionError | null;
}

function BannerCard({ entry, onDismiss, onAction, actionLoading, onAbortRequest, actionError }: BannerCardProps) {
  const label = getStateFriendlyLabel(entry.state, entry.reason ?? null);
  const explanation = getReasonExplanation(entry.state, entry.reason ?? null);

  const renderActionButton = () => {
    switch (entry.suggested_action) {
      case 'resume':
        return (
          <button
            onClick={() => onAction(entry, 'resume')}
            disabled={actionLoading}
            data-testid={`banner-resume-${entry.queue_id}`}
            className="px-3 py-1.5 rounded bg-green-900/50 hover:bg-green-900/70 text-green-300 text-xs font-medium transition-colors disabled:opacity-50 flex items-center gap-1.5"
            aria-label={`Resume queue ${entry.key}`}
          >
            <Play className="w-3 h-3" />
            Resume now
          </button>
        );

      case 'wait':
        return (
          <button
            disabled
            data-testid={`banner-wait-${entry.queue_id}`}
            className="px-3 py-1.5 rounded bg-blue-900/30 text-blue-400 text-xs font-medium cursor-not-allowed opacity-70 flex items-center gap-1.5"
            aria-label={`Waiting for reset — ${entry.key}`}
          >
            <Clock className="w-3 h-3" />
            {entry.reset_time
              ? `Auto-resume in ${formatCountdown(entry.reset_time)}`
              : 'Waiting for reset…'}
          </button>
        );

      case 'retry-failed':
        return (
          <button
            onClick={() => onAction(entry, 'retry-failed')}
            disabled={actionLoading}
            data-testid={`banner-retry-failed-${entry.queue_id}`}
            className="px-3 py-1.5 rounded bg-amber-900/50 hover:bg-amber-900/70 text-amber-300 text-xs font-medium transition-colors disabled:opacity-50 flex items-center gap-1.5"
            aria-label={`Retry failed tasks for ${entry.key}`}
          >
            <RefreshCw className="w-3 h-3" />
            Retry failed tasks
          </button>
        );

      case 'force-recover':
        return (
          <button
            onClick={() => onAction(entry, 'force-recover')}
            disabled={actionLoading}
            data-testid={`banner-force-recover-${entry.queue_id}`}
            className="px-3 py-1.5 rounded bg-red-900/50 hover:bg-red-900/70 text-red-300 text-xs font-medium transition-colors disabled:opacity-50 flex items-center gap-1.5"
            aria-label={`Force recover zombie queue ${entry.key}`}
          >
            <AlertCircle className="w-3 h-3" />
            Force recover
          </button>
        );

      case 'abort':
        return (
          <button
            onClick={() => onAbortRequest(entry)}
            disabled={actionLoading}
            data-testid={`banner-abort-${entry.queue_id}`}
            className="px-3 py-1.5 rounded bg-red-900/50 hover:bg-red-900/70 text-red-300 text-xs font-medium transition-colors disabled:opacity-50 flex items-center gap-1.5"
            aria-label={`Abort queue ${entry.key}`}
          >
            <X className="w-3 h-3" />
            Abort queue
          </button>
        );

      default:
        return null;
    }
  };

  return (
    <div
      className={cn(
        'relative border rounded-lg px-4 py-3 flex flex-col gap-1.5',
        getBannerBorderClass(entry),
      )}
      data-testid={`recovery-banner-${entry.queue_id}`}
      role="alert"
      aria-live="polite"
    >
      {/* Dismiss */}
      <button
        onClick={() => onDismiss(entry)}
        className="absolute top-2 right-2 p-1 rounded hover:bg-zinc-700/60 text-zinc-500 hover:text-zinc-300 transition-colors"
        aria-label={`Dismiss banner for ${entry.key}`}
        data-testid={`banner-dismiss-${entry.queue_id}`}
      >
        <X className="w-3.5 h-3.5" />
      </button>

      {/* Header row */}
      <div className="flex items-center gap-2 pr-6">
        {getIcon(entry)}
        <span className="text-sm font-medium text-zinc-100">
          {entry.key}
        </span>
        <span className="text-xs text-zinc-400">—</span>
        <span className="text-sm text-zinc-300 flex-1 min-w-0 truncate">{label}</span>
      </div>

      {/* Explanation */}
      {explanation && (
        <p className="text-xs text-zinc-400 leading-snug">{explanation}</p>
      )}

      {/* Countdown row (waiting_reset with reset_time) */}
      {entry.state === 'waiting_reset' && entry.reset_time && (
        <CountdownLine resetTime={entry.reset_time} />
      )}

      {/* Attempt count context */}
      {typeof entry.attempt_count === 'number' && entry.attempt_count > 0 && (
        <p className="text-xs text-zinc-500">
          Auto-resume attempts: {entry.attempt_count}
        </p>
      )}

      {/* Action button */}
      <div className="flex items-center gap-2 mt-0.5">
        {renderActionButton()}
      </div>

      {/* Per-action error — surfaced when action call returns a non-ok response */}
      {actionError && (
        <p
          className="text-xs text-red-400 leading-snug flex items-center gap-1"
          data-testid={`banner-action-error-${entry.queue_id}`}
          role="alert"
        >
          <AlertCircle className="w-3 h-3 shrink-0" />
          {actionError.message}
        </p>
      )}
    </div>
  );
}

// ─── Abort confirm dialog ─────────────────────────────────────────────────────

interface AbortDialogProps {
  entry: AbortDialogState;
  onConfirm: (queueId: string) => Promise<void>;
  onCancel: () => void;
  loading: boolean;
}

function AbortDialog({ entry, onConfirm, onCancel, loading }: AbortDialogProps) {
  return (
    <div
      className="border border-red-600/40 rounded-lg bg-red-900/20 px-4 py-3 flex flex-col gap-2"
      data-testid="abort-confirm-dialog"
      role="alertdialog"
      aria-modal="true"
    >
      <p className="text-sm text-red-300 font-medium">
        Abort {entry.key}?
      </p>
      <p className="text-xs text-zinc-400">
        This will stop the queue permanently. Remaining tasks will be left as-is.
      </p>
      <div className="flex items-center gap-2 mt-1">
        <button
          onClick={() => onConfirm(entry.queueId)}
          disabled={loading}
          data-testid="abort-confirm-yes"
          className="px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white text-xs font-medium transition-colors disabled:opacity-50"
        >
          Yes, abort
        </button>
        <button
          onClick={onCancel}
          data-testid="abort-confirm-cancel"
          className="px-3 py-1.5 rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-300 text-xs font-medium transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function AutoPilotRecoveryBanner() {
  const [allEntries, setAllEntries] = useState<RecoverableEntry[]>([]);
  const [dismissedKeys, setDismissedKeys] = useState<Set<string>>(new Set());
  const [actionLoading, setActionLoading] = useState<Set<string>>(new Set());
  const [actionErrors, setActionErrors] = useState<Map<string, ActionError>>(new Map());
  const [abortDialog, setAbortDialog] = useState<AbortDialogState | null>(null);
  const [abortLoading, setAbortLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch recovery status ──

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_API}/queue/recovery-status`, {
        signal: AbortSignal.timeout(15_000),
      });
      if (!res.ok) return;
      const data: RecoveryStatusPayload = await res.json();

      const combined: RecoverableEntry[] = [
        ...(data.recoverable ?? []),
        ...(data.zombie ?? []),
      ];
      setAllEntries(combined);
    } catch {
      // Backend unavailable — keep showing previous entries
    }
  }, []);

  // Poll on mount + every 30s
  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, POLL_MS);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  // Listen for SSE recovery events — triggers an immediate re-fetch
  useEffect(() => {
    const RECOVERY_EVENT_TYPES = [
      'crash_recovery_detected',
      'auto_paused',
      'auto_resume_fired',
      'auto_resume_circuit_breaker_tripped',
      'STATE_TRANSITION',
      'RECOVERY_STARTED',
      'AUTO_RESUME_FIRED',
      'TOKEN_EXHAUSTION_DETECTED',
      'ZOMBIE_DETECTED',
    ];

    let es: EventSource | null = null;
    let unmounted = false;

    try {
      es = new EventSource(BACKEND_EVENTS_URL);

      for (const evType of RECOVERY_EVENT_TYPES) {
        es.addEventListener(evType, () => {
          if (!unmounted) fetchStatus();
        });
      }

      es.onerror = () => {
        // Native reconnect handles this — no manual intervention needed
      };
    } catch {
      // SSE not supported in this env — polling-only mode is fine
    }

    return () => {
      unmounted = true;
      if (es) {
        es.close();
        es = null;
      }
    };
  }, [fetchStatus]);

  // ── Dismiss logic ──

  const handleDismiss = useCallback((entry: RecoverableEntry) => {
    setDismissed(entry.queue_id, entry.state, entry.reason ?? null);
    setDismissedKeys(prev => new Set([...prev, entry.queue_id]));
  }, []);

  // ── Action handlers ──

  const setActionError = useCallback((queueId: string, error: ActionError | null) => {
    setActionErrors(prev => {
      const next = new Map(prev);
      if (error === null) {
        next.delete(queueId);
      } else {
        next.set(queueId, error);
      }
      return next;
    });
  }, []);

  const handleAction = useCallback(async (entry: RecoverableEntry, action: string) => {
    setActionLoading(prev => new Set([...prev, entry.queue_id]));
    // Clear any previous error for this card when re-attempting.
    setActionError(entry.queue_id, null);
    try {
      let url: string;
      let method = 'POST';

      // CB-2802: all scoped queue endpoints require ?project_id=<id>.
      const pid = encodeURIComponent(entry.project_id);
      switch (action) {
        case 'resume':
          url = `${BACKEND_API}/queue/${entry.queue_id}/resume?project_id=${pid}`;
          break;
        case 'retry-failed':
          // CB-2806: Use the dedicated ?retry_failed=true param so the backend
          // bulk-resets all failed tasks then resumes — matches AutoPilotFloatingBar's
          // handleRetryAndResume pattern (POST resume?retry_failed=true).
          url = `${BACKEND_API}/queue/${entry.queue_id}/resume?retry_failed=true&project_id=${pid}`;
          break;
        case 'force-recover':
          // Force-recover: abort the zombie queue with 'leave' action.
          url = `${BACKEND_API}/queue/${entry.queue_id}/abort?project_id=${pid}`;
          break;
        default:
          return;
      }

      const body = action === 'force-recover'
        ? JSON.stringify({ action: 'leave' })
        : undefined;

      const res = await fetch(url, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body,
        signal: AbortSignal.timeout(15_000),
      });

      if (res.ok) {
        // Remove from list optimistically, then re-fetch to sync truth
        setAllEntries(prev => prev.filter(e => e.queue_id !== entry.queue_id));
        setTimeout(fetchStatus, 1000);
        return;
      }

      // Non-ok response — surface it in the banner rather than silently swallowing.
      // For 409 the backend returns { details: { failed_count, pending_count, suggestion } }.
      let errorMessage: string;
      try {
        const body = await res.json();
        const details = body?.details ?? {};
        // Prefer the backend's suggestion (matches FloatingBar's pattern),
        // then fall back to the top-level message, then a generic string.
        errorMessage =
          details.suggestion ??
          body?.message ??
          `Action failed (${res.status})`;

        // If the 409 also carries counts, prepend them for clarity.
        if (res.status === 409 && typeof details.failed_count === 'number') {
          errorMessage = `${details.failed_count} failed, ${details.pending_count ?? 0} pending — ${errorMessage}`;
        }
      } catch {
        errorMessage = `Action failed (${res.status})`;
      }

      setActionError(entry.queue_id, { message: errorMessage });
    } catch (err) {
      // CB-2806: surface network-level failures so the user gets feedback rather
      // than silent failure.
      const msg = err instanceof Error ? err.message : 'Network error';
      setActionError(entry.queue_id, { message: `Request failed: ${msg}` });
    } finally {
      setActionLoading(prev => {
        const next = new Set(prev);
        next.delete(entry.queue_id);
        return next;
      });
    }
  }, [fetchStatus, setActionError]);

  const handleAbortRequest = useCallback((entry: RecoverableEntry) => {
    setAbortDialog({ queueId: entry.queue_id, key: entry.key, projectId: entry.project_id });
  }, []);

  const handleAbortConfirm = useCallback(async (queueId: string) => {
    // CB-2802: look up projectId from abortDialog state which was set in handleAbortRequest.
    const projectId = abortDialog?.projectId ?? '';
    const pid = encodeURIComponent(projectId);
    setAbortLoading(true);
    try {
      const res = await fetch(`${BACKEND_API}/queue/${queueId}/abort?project_id=${pid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'leave' }),
        signal: AbortSignal.timeout(15_000),
      });
      if (res.ok) {
        setAllEntries(prev => prev.filter(e => e.queue_id !== queueId));
        setAbortDialog(null);
        setTimeout(fetchStatus, 1000);
      }
    } catch {
      // keep dialog open on error
    } finally {
      setAbortLoading(false);
    }
  }, [fetchStatus, abortDialog]);

  // ── Visible entries — filter dismissed (re-shows if state/reason changed) ──

  const visibleEntries = allEntries.filter(entry => !isDismissed(entry));

  if (visibleEntries.length === 0 && !abortDialog) return null;

  return (
    <div
      className="flex flex-col gap-2"
      data-testid="autopilot-recovery-banner-root"
      aria-label="AutoPilot recovery notifications"
    >
      {visibleEntries.map(entry => (
        <BannerCard
          key={entry.queue_id}
          entry={entry}
          onDismiss={handleDismiss}
          onAction={handleAction}
          actionLoading={actionLoading.has(entry.queue_id)}
          onAbortRequest={handleAbortRequest}
          actionError={actionErrors.get(entry.queue_id) ?? null}
        />
      ))}

      {abortDialog && (
        <AbortDialog
          entry={abortDialog}
          onConfirm={handleAbortConfirm}
          onCancel={() => setAbortDialog(null)}
          loading={abortLoading}
        />
      )}
    </div>
  );
}
