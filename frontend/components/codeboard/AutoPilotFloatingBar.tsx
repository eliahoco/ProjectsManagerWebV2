'use client';

/**
 * AutoPilotFloatingBar — Persistent status bar visible on every page when AutoPilot is active.
 * Rendered in providers.tsx (always mounted). z-[70] sits above FloatingAgentStatusBar (z-60).
 *
 * Now reads from the backend-driven queue state via AutoPilotContext.
 * Shows token exhaustion states with Wait/Switch Model/Abort options.
 */

import { useState, useEffect } from 'react';
import {
  Loader2, Pause, Play, SkipForward, Square, ChevronDown, ChevronUp,
  CheckCircle2, AlertCircle, Clock, Zap, X, Timer, RefreshCw,
} from 'lucide-react';
import { useAutoPilot } from '@/contexts/AutoPilotContext';
import type { AbortAction, QueueTask } from '@/contexts/AutoPilotContext';
import { cn } from '@/lib/utils';

export function AutoPilotFloatingBar() {
  const {
    state, pauseAutoPilot, resumeAutoPilot, skipCurrentTask,
    abortAutoPilot, waitForReset, switchModel,
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

  // Fetch available models when token dialog opens
  useEffect(() => {
    if (!showTokenDialog) return;
    fetch('/api/codeboard/execute/queue/available-models')
      .then(r => r.json())
      .then(data => setAvailableModels(data.providers || []))
      .catch(() => {});
  }, [showTokenDialog]);

  if (!state.isActive) return null;

  const currentTask = state.queue[state.currentIndex];
  const { total, completed, failed, skipped, percent } = state.progress;
  const pendingCount = state.queue.filter(q => q.status === 'pending' || q.status === 'running').length;
  const isTokenExhausted = state.isWaitingReset;

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

  // Auto-show token dialog when waiting_reset
  useEffect(() => {
    if (isTokenExhausted && !showTokenDialog && !showAbortDialog) {
      setShowTokenDialog(true);
    }
  }, [isTokenExhausted]);

  return (
    <div className="fixed bottom-4 right-4 z-[70] w-[420px] bg-zinc-900 border border-amber-600/40 rounded-xl shadow-2xl overflow-hidden">
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
            {isTokenExhausted && (
              <span className="text-xs px-1.5 py-0.5 bg-red-900/50 text-red-300 rounded">
                Token Exhausted
              </span>
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
              onClick={resumeAutoPilot}
              className="p-1.5 rounded hover:bg-green-900/50 text-green-400"
              title="Resume"
            >
              <Play className="w-4 h-4" />
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

      {/* Expanded queue list */}
      {isExpanded && (
        <div className="max-h-64 overflow-y-auto border-t border-zinc-700">
          {state.queue.map((task, idx) => (
            <QueueRow key={task.issue_id} task={task} isCurrent={idx === state.currentIndex} />
          ))}
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
                Auto-resume when quota resets (default: ~1 hour)
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

function QueueRow({ task, isCurrent }: { task: QueueTask; isCurrent: boolean }) {
  return (
    <div className={cn(
      'flex items-center gap-2 px-4 py-2 text-xs',
      isCurrent && 'bg-amber-900/20',
    )}>
      {/* Status icon */}
      {task.status === 'running' && <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin shrink-0" />}
      {task.status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5 text-green-400 shrink-0" />}
      {task.status === 'failed' && <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />}
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
