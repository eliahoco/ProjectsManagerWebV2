'use client';

/**
 * Global Agent Status Bar - Shows all active/queued/recent executions
 * Sits between the CodeBoard header and content area, always visible when agents are running
 */

import { useState, useMemo } from 'react';
import {
  Bot, ChevronDown, ChevronUp, Loader2, CheckCircle, XCircle,
  AlertCircle, Pause, Square, Clock, Terminal, Maximize2, X
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useExecutionSessions, type ExecutionSession } from '@/hooks/useCodeBoard';

/**
 * Connection indicator dot - shows SSE (green) vs polling fallback (yellow)
 */
function ConnectionIndicator({ connected }: { connected?: boolean }) {
  return (
    <span
      className={cn(
        'inline-block w-1.5 h-1.5 rounded-full flex-shrink-0',
        connected ? 'bg-green-400' : 'bg-yellow-400 animate-pulse'
      )}
      title={connected ? 'Live (SSE connected)' : 'Polling fallback (SSE disconnected)'}
    />
  );
}

interface GlobalAgentStatusBarProps {
  projectId?: string;
  onSessionClick?: (session: ExecutionSession) => void;
  onStopAll?: () => void;
}

function getPhaseLabel(phase?: string): string {
  if (!phase) return '';
  const labels: Record<string, string> = {
    'INITIALIZING': 'Initializing',
    'READING_FILES': 'Reading files',
    'ANALYZING': 'Analyzing',
    'PLANNING': 'Planning',
    'WRITING_CODE': 'Writing code',
    'RUNNING_COMMANDS': 'Running commands',
    'TESTING': 'Testing',
    'FINALIZING': 'Finalizing',
    'COMPLETED': 'Done',
    // Pipeline stages
    'IMPLEMENT': 'Implementing',
    'VERIFY': 'Verifying UI',
    'FIX': 'Fixing issues',
    'RE_VERIFY': 'Re-verifying',
  };
  return labels[phase] || phase;
}

function getPipelineStageColor(stage?: string): string {
  switch (stage) {
    case 'IMPLEMENT': return 'text-cyan-400';
    case 'VERIFY': return 'text-amber-400';
    case 'FIX': return 'text-orange-400';
    case 'RE_VERIFY': return 'text-amber-400';
    default: return 'text-zinc-400';
  }
}

function getStatusIcon(status: string, size: string = 'w-4 h-4') {
  switch (status) {
    case 'running':
      return <Loader2 className={cn(size, 'animate-spin text-cyan-400')} />;
    case 'completed':
      return <CheckCircle className={cn(size, 'text-green-400')} />;
    case 'failed':
      return <XCircle className={cn(size, 'text-red-400')} />;
    case 'cancelled':
      return <AlertCircle className={cn(size, 'text-yellow-400')} />;
    case 'pending':
      return <Clock className={cn(size, 'text-zinc-400')} />;
    default:
      return <Bot className={cn(size, 'text-zinc-400')} />;
  }
}

function getProviderLabel(provider: string): string {
  switch (provider) {
    case 'claude_code': return 'Claude Code';
    case 'local_ai': return 'Local AI';
    default: return provider;
  }
}

function getProviderColor(provider: string): string {
  switch (provider) {
    case 'claude_code': return 'text-orange-400 bg-orange-500/10 border-orange-500/30';
    case 'local_ai': return 'text-violet-400 bg-violet-500/10 border-violet-500/30';
    default: return 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30';
  }
}

function getProgressColor(status: string): string {
  switch (status) {
    case 'running': return 'bg-cyan-500';
    case 'completed': return 'bg-green-500';
    case 'failed': return 'bg-red-500';
    default: return 'bg-zinc-500';
  }
}

function formatElapsed(startedAt?: string): string {
  if (!startedAt) return '';
  const start = new Date(startedAt).getTime();
  const elapsed = Math.floor((Date.now() - start) / 1000);
  if (elapsed < 60) return `${elapsed}s`;
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return `${mins}m ${secs}s`;
}

function SessionRow({
  session,
  onClick
}: {
  session: ExecutionSession;
  onClick?: () => void;
}) {
  const progress = session.progress_percent || 0;

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors cursor-pointer',
        'hover:bg-zinc-700/50',
        session.status === 'running' && 'bg-zinc-800/50',
      )}
      onClick={onClick}
    >
      {/* Status icon */}
      {getStatusIcon(session.status)}

      {/* Issue key */}
      <span className="font-mono text-xs font-medium text-zinc-200 w-16 flex-shrink-0">
        {session.issue_key}
      </span>

      {/* Agent/Provider badge */}
      <span className={cn(
        'text-[10px] font-medium px-1.5 py-0.5 rounded border flex-shrink-0',
        getProviderColor(session.provider)
      )}>
        {getProviderLabel(session.provider)}
      </span>

      {/* Progress bar */}
      <div className="flex-1 max-w-[200px]">
        <div className="h-1.5 bg-zinc-700 rounded-full overflow-hidden">
          <div
            className={cn('h-full rounded-full transition-all duration-500', getProgressColor(session.status))}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Progress % */}
      <span className="text-xs font-mono text-zinc-400 w-10 text-right">
        {progress}%
      </span>

      {/* Pipeline stage badge */}
      {session.pipeline_stage && (
        <span className={cn(
          'text-[10px] font-medium px-1.5 py-0.5 rounded border flex-shrink-0',
          session.pipeline_stage === 'VERIFY' || session.pipeline_stage === 'RE_VERIFY'
            ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
            : session.pipeline_stage === 'FIX'
            ? 'text-orange-400 bg-orange-500/10 border-orange-500/30'
            : 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30'
        )}>
          {getPhaseLabel(session.pipeline_stage)}
          {(session.retry_count ?? 0) > 0 && ` (retry ${session.retry_count}/${session.max_retries ?? 3})`}
        </span>
      )}

      {/* Phase */}
      <span className="text-xs text-zinc-500 w-28 truncate">
        {session.status === 'running'
          ? getPhaseLabel(session.phase) || session.current_action || 'Running...'
          : session.status === 'completed' ? 'Completed'
          : session.status === 'failed' ? (session.error?.slice(0, 30) || 'Failed')
          : session.status}
      </span>

      {/* Elapsed time */}
      <span className="text-xs font-mono text-zinc-500 w-12 text-right">
        {formatElapsed(session.started_at)}
      </span>

      {/* Expand button */}
      <button
        className="p-1 rounded hover:bg-zinc-600 transition-colors"
        title="View terminal output"
        onClick={(e) => { e.stopPropagation(); onClick?.(); }}
      >
        <Terminal className="w-3 h-3 text-zinc-400" />
      </button>
    </div>
  );
}

/**
 * Shared hook to categorize sessions
 */
function useCategorizedSessions(sessions?: ExecutionSession[]) {
  return useMemo(() => {
    if (!sessions?.length) return { running: [], completed: [], failed: [], queued: [], totalActive: 0 };
    const running = sessions.filter(s => s.status === 'running');
    const queued = sessions.filter(s => s.status === 'pending');
    return {
      running,
      completed: sessions.filter(s => s.status === 'completed'),
      failed: sessions.filter(s => s.status === 'failed'),
      queued,
      totalActive: running.length + queued.length,
    };
  }, [sessions]);
}

/**
 * Summary badges (running, queued, done, failed counts)
 */
function StatusBadges({ running, queued, completed, failed }: {
  running: ExecutionSession[];
  queued: ExecutionSession[];
  completed: ExecutionSession[];
  failed: ExecutionSession[];
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {running.length > 0 && (
        <span className="flex items-center gap-1 px-2 py-0.5 bg-cyan-500/10 border border-cyan-500/30 rounded-full text-cyan-400">
          <Loader2 className="w-3 h-3 animate-spin" />
          {running.length} running
        </span>
      )}
      {queued.length > 0 && (
        <span className="flex items-center gap-1 px-2 py-0.5 bg-zinc-700 rounded-full text-zinc-400">
          <Clock className="w-3 h-3" />
          {queued.length} queued
        </span>
      )}
      {completed.length > 0 && (
        <span className="flex items-center gap-1 px-2 py-0.5 bg-green-500/10 border border-green-500/30 rounded-full text-green-400">
          <CheckCircle className="w-3 h-3" />
          {completed.length} done
        </span>
      )}
      {failed.length > 0 && (
        <span className="flex items-center gap-1 px-2 py-0.5 bg-red-500/10 border border-red-500/30 rounded-full text-red-400">
          <XCircle className="w-3 h-3" />
          {failed.length} failed
        </span>
      )}
    </div>
  );
}

/**
 * Inline status bar — sits between CodeBoard header and content
 */
export function GlobalAgentStatusBar({ projectId, onSessionClick, onStopAll }: GlobalAgentStatusBarProps) {
  const { data: allSessions, connected: sseConnected } = useExecutionSessions();
  const [isExpanded, setIsExpanded] = useState(true);

  // Filter sessions by project if projectId is provided
  const sessions = useMemo(() => {
    if (!allSessions?.length) return undefined;
    if (!projectId) return allSessions;
    return allSessions.filter(s => !s.project_id || s.project_id === projectId);
  }, [allSessions, projectId]);

  const { running, completed, failed, queued, totalActive } = useCategorizedSessions(sessions);

  // Don't render if no sessions at all
  if (!sessions?.length) return null;

  return (
    <div className="flex-shrink-0 border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
      {/* Compact summary bar */}
      <div
        className="flex items-center justify-between px-6 py-2 cursor-pointer hover:bg-zinc-800/30 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Bot className={cn('w-4 h-4', running.length > 0 ? 'text-cyan-400' : 'text-zinc-500')} />
            <span className="text-sm font-medium text-zinc-300">
              Agent Status
            </span>
            <ConnectionIndicator connected={sseConnected} />
          </div>

          <StatusBadges running={running} queued={queued} completed={completed} failed={failed} />

          {/* Running task quick preview */}
          {running.length > 0 && !isExpanded && (
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <span className="text-zinc-600">|</span>
              <span className="font-mono text-cyan-400">{running[0].issue_key}</span>
              <span className={cn('text-[10px] px-1 rounded border', getProviderColor(running[0].provider))}>
                {getProviderLabel(running[0].provider)}
              </span>
              <div className="w-20 h-1 bg-zinc-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-cyan-500 rounded-full transition-all duration-500"
                  style={{ width: `${running[0].progress_percent || 0}%` }}
                />
              </div>
              <span className="text-zinc-500">{running[0].progress_percent || 0}%</span>
              <span className="text-zinc-500 truncate max-w-[150px]">
                {getPhaseLabel(running[0].phase)}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Stop all button */}
          {totalActive > 0 && onStopAll && (
            <button
              onClick={(e) => { e.stopPropagation(); onStopAll(); }}
              className="flex items-center gap-1 px-2 py-1 text-xs text-red-400 hover:bg-red-500/10 rounded transition-colors"
              title="Stop all executions"
            >
              <Square className="w-3 h-3" />
              Stop All
            </button>
          )}

          {/* Expand/collapse */}
          {isExpanded
            ? <ChevronUp className="w-4 h-4 text-zinc-500" />
            : <ChevronDown className="w-4 h-4 text-zinc-500" />
          }
        </div>
      </div>

      {/* Expanded session list */}
      {isExpanded && sessions.length > 0 && (
        <div className="px-4 pb-3 space-y-1 max-h-[200px] overflow-y-auto">
          {running.map(session => (
            <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
          ))}
          {queued.map(session => (
            <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
          ))}
          {completed.slice(0, 3).map(session => (
            <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
          ))}
          {failed.map(session => (
            <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Floating status bar — fixed at top of screen, visible above modals (z-[60] > AutoPilot z-50)
 * Shows when agents are active and a full-screen modal is open
 */
export function FloatingAgentStatusBar({ projectId, onSessionClick, onStopAll }: GlobalAgentStatusBarProps) {
  const { data: allSessions, connected: sseConnected } = useExecutionSessions();
  const [isExpanded, setIsExpanded] = useState(false);

  const sessions = useMemo(() => {
    if (!allSessions?.length) return undefined;
    if (!projectId) return allSessions;
    return allSessions.filter(s => !s.project_id || s.project_id === projectId);
  }, [allSessions, projectId]);

  const { running, completed, failed, queued, totalActive } = useCategorizedSessions(sessions);

  // Only show if there are active sessions
  if (!totalActive && !completed.length && !failed.length) return null;
  if (!sessions?.length) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[60] pointer-events-none">
      <div className="pointer-events-auto mx-auto max-w-4xl mt-2 rounded-xl border border-zinc-700 bg-zinc-900/95 backdrop-blur-md shadow-2xl shadow-black/50">
        {/* Compact summary */}
        <div
          className="flex items-center justify-between px-4 py-2 cursor-pointer hover:bg-zinc-800/30 transition-colors rounded-xl"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-3">
            <Bot className={cn('w-4 h-4', running.length > 0 ? 'text-cyan-400' : 'text-zinc-500')} />
            <span className="text-xs font-medium text-zinc-300">Agents</span>
            <ConnectionIndicator connected={sseConnected} />
            <StatusBadges running={running} queued={queued} completed={completed} failed={failed} />

            {/* Inline preview of first running task */}
            {running.length > 0 && !isExpanded && (
              <div className="flex items-center gap-2 text-xs text-zinc-400 ml-1">
                <span className="text-zinc-600">|</span>
                <span className="font-mono text-cyan-400">{running[0].issue_key}</span>
                <span className={cn('text-[10px] px-1 rounded border', getProviderColor(running[0].provider))}>
                  {getProviderLabel(running[0].provider)}
                </span>
                <div className="w-16 h-1 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-cyan-500 rounded-full transition-all duration-500"
                    style={{ width: `${running[0].progress_percent || 0}%` }}
                  />
                </div>
                <span className="text-zinc-500">{running[0].progress_percent || 0}%</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {totalActive > 0 && onStopAll && (
              <button
                onClick={(e) => { e.stopPropagation(); onStopAll(); }}
                className="flex items-center gap-1 px-2 py-0.5 text-xs text-red-400 hover:bg-red-500/10 rounded transition-colors"
              >
                <Square className="w-3 h-3" />
                Stop All
              </button>
            )}
            {isExpanded
              ? <ChevronUp className="w-3 h-3 text-zinc-500" />
              : <ChevronDown className="w-3 h-3 text-zinc-500" />
            }
          </div>
        </div>

        {/* Expanded rows */}
        {isExpanded && (
          <div className="px-3 pb-2 space-y-1 max-h-[180px] overflow-y-auto border-t border-zinc-800">
            {running.map(session => (
              <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
            ))}
            {queued.map(session => (
              <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
            ))}
            {completed.slice(0, 3).map(session => (
              <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
            ))}
            {failed.map(session => (
              <SessionRow key={session.session_id} session={session} onClick={() => onSessionClick?.(session)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
