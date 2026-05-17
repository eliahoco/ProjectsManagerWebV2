'use client';

/**
 * AutoPilotStatusBadge — Small chip showing queue state next to queue titles.
 *
 * Color coding:
 *   running       → green
 *   paused        → amber
 *   waiting_reset → blue
 *   failed/aborted → red
 *   completed     → gray
 *
 * Tooltip on hover shows {state}/{reason} friendly explanation.
 * Accessible: aria-label includes the friendly label.
 */

import { cn } from '@/lib/utils';

export interface StatusBadgeProps {
  state: string;
  reason?: string | null;
  className?: string;
}

// ─── Label helpers ────────────────────────────────────────────────────────────

export function getFriendlyLabel(state: string, reason?: string | null): string {
  const key = `${state}/${reason ?? ''}`;
  switch (key) {
    case 'waiting_reset/rate_limit_5h':    return 'Rate limit — auto-resume armed';
    case 'waiting_reset/rate_limit_weekly':return 'Weekly limit — auto-resume armed';
    case 'waiting_reset/token_exhaustion': return 'Token limit — auto-resume armed';
    case 'paused/credit_exhaustion':       return 'Credits exhausted';
    case 'paused/auth_failure':            return 'Auth failed';
    case 'paused/crash_recovery':          return 'Crash recovery';
    case 'paused/manual':                  return 'Paused';
    case 'running/zombie_detected':        return 'Zombie — stale';
    case 'running/':
    case 'running':                        return 'Running';
    case 'paused/':
    case 'paused':                         return 'Paused';
    case 'completed/':
    case 'completed':                      return 'Completed';
    case 'aborted/':
    case 'aborted':                        return 'Aborted';
    default:
      if (state === 'running')         return 'Running';
      if (state === 'paused')          return reason ? `Paused (${reason})` : 'Paused';
      if (state === 'waiting_reset')   return 'Waiting reset';
      if (state === 'completed')       return 'Completed';
      if (state === 'aborted')         return 'Aborted';
      return `${state}${reason ? `/${reason}` : ''}`;
  }
}

function getColorClass(state: string, reason?: string | null): string {
  if (state === 'running' && reason === 'zombie_detected') {
    return 'bg-red-900/40 text-red-300 ring-1 ring-red-500/40';
  }
  switch (state) {
    case 'running':       return 'bg-green-900/40 text-green-300 ring-1 ring-green-500/40';
    case 'paused':        return 'bg-amber-900/40 text-amber-300 ring-1 ring-amber-500/40';
    case 'waiting_reset': return 'bg-blue-900/40 text-blue-300 ring-1 ring-blue-500/40';
    case 'completed':     return 'bg-zinc-700/40 text-zinc-400 ring-1 ring-zinc-500/40';
    case 'aborted':       return 'bg-red-900/40 text-red-300 ring-1 ring-red-500/40';
    default:              return 'bg-zinc-700/40 text-zinc-400 ring-1 ring-zinc-500/40';
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AutoPilotStatusBadge({ state, reason, className }: StatusBadgeProps) {
  const label = getFriendlyLabel(state, reason);
  const tooltip = reason ? `${state}/${reason}` : state;

  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium leading-tight cursor-default',
        getColorClass(state, reason),
        className,
      )}
      title={tooltip}
      aria-label={`AutoPilot status: ${label}`}
      data-testid="autopilot-status-badge"
    >
      {label}
    </span>
  );
}
