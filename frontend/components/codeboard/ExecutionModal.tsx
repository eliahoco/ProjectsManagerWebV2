'use client';

/**
 * Execution Modal - Shows AI execution progress and output
 * Includes timeout warnings with options to continue or break down tasks
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Terminal, Bot, Loader2, CheckCircle2, XCircle, Send, StopCircle, Clock, AlertTriangle, Sparkles, Play, FileText, FileCode, TerminalSquare, Minimize2, ClipboardCheck } from 'lucide-react';
import {
  useExecutionOutput,
  useSendExecutionInput,
  useStopExecution,
  useCompleteExecution,
  useUpdateIssue,
  ExecutionSession,
} from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';
import { Issue } from '@/types/codeboard';

// Warning threshold in milliseconds (5 minutes)
const LONG_RUNNING_THRESHOLD = 5 * 60 * 1000;
// Time between warnings
const WARNING_COOLDOWN = 3 * 60 * 1000;

interface ExecutionModalProps {
  session: ExecutionSession;
  issue?: Issue;
  onClose: () => void;
  onMinimize?: () => void;
  onAIBreakdown?: (issue: Issue) => void;
  onAbortMission?: () => void;
}

export function ExecutionModal({ session, issue, onClose, onMinimize, onAIBreakdown, onAbortMission }: ExecutionModalProps) {
  const [input, setInput] = useState('');
  const [showTimeoutWarning, setShowTimeoutWarning] = useState(false);
  const [lastWarningTime, setLastWarningTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const outputRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number>(
    session.started_at ? new Date(session.started_at).getTime() : Date.now()
  );

  // Always poll for output - the hook will stop when session is not running
  const { data: outputData } = useExecutionOutput(session.session_id);
  const sendInput = useSendExecutionInput();
  const stopExecution = useStopExecution();
  const completeExecution = useCompleteExecution();
  const updateIssue = useUpdateIssue();

  // Use status from output data if available (it's more current), fallback to session prop
  const currentStatus = outputData?.status || session.status;
  const isRunning = currentStatus === 'running';
  const isCompleted = currentStatus === 'completed';
  const isFailed = currentStatus === 'failed';
  const isCancelled = currentStatus === 'cancelled';
  const isNotFound = currentStatus === 'not_found'; // Session crashed/disappeared
  const isTimedOut = currentStatus === 'failed' && outputData?.output?.some(line =>
    line.toLowerCase().includes('timeout') || line.toLowerCase().includes('timed out')
  );

  // Track elapsed time and show warnings for long-running executions
  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      const elapsed = Date.now() - startTimeRef.current;
      setElapsedTime(elapsed);

      // Check if we should show timeout warning
      if (elapsed >= LONG_RUNNING_THRESHOLD) {
        const shouldShowWarning = !lastWarningTime ||
          (Date.now() - lastWarningTime) >= WARNING_COOLDOWN;

        if (shouldShowWarning && !showTimeoutWarning) {
          setShowTimeoutWarning(true);
          setLastWarningTime(Date.now());
        }
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isRunning, lastWarningTime, showTimeoutWarning]);

  // Format elapsed time
  const formatElapsedTime = useCallback((ms: number) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    }
    if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    }
    return `${seconds}s`;
  }, []);

  // Handle dismissing timeout warning
  const handleDismissWarning = useCallback(() => {
    setShowTimeoutWarning(false);
  }, []);

  // Handle breaking down the task
  const handleBreakdown = useCallback(() => {
    setShowTimeoutWarning(false);
    if (issue && onAIBreakdown) {
      onAIBreakdown(issue);
    }
    onClose();
  }, [issue, onAIBreakdown, onClose]);

  // Auto-scroll to bottom when new output arrives
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [outputData?.output]);

  const handleSendInput = async () => {
    if (!input.trim() || !isRunning) return;

    try {
      await sendInput.mutateAsync({
        sessionId: session.session_id,
        text: input,
      });
      setInput('');
    } catch (error) {
      console.error('Failed to send input:', error);
    }
  };

  const handleStop = async () => {
    try {
      await stopExecution.mutateAsync(session.session_id);
    } catch (error) {
      console.error('Failed to stop execution:', error);
    }
  };

  const handleComplete = async () => {
    try {
      await completeExecution.mutateAsync({
        sessionId: session.session_id,
        issueId: session.issue_id,
      });
      onClose();
    } catch (error) {
      console.error('Failed to complete execution:', error);
    }
  };

  const handleMarkWaitingQA = async () => {
    if (!session.issue_id) return;
    try {
      await updateIssue.mutateAsync({
        issueId: session.issue_id,
        data: { status: 'COMPLETED_WAITING_QA' },
      });
      onClose();
    } catch (error) {
      console.error('Failed to mark as waiting for QA:', error);
    }
  };

  const handleAbortMission = async () => {
    try {
      // Stop the current execution
      await stopExecution.mutateAsync(session.session_id);
    } catch (error) {
      console.error('Failed to stop execution:', error);
    }

    // Revert issue status to TODO
    if (session.issue_id) {
      try {
        await updateIssue.mutateAsync({
          issueId: session.issue_id,
          data: { status: 'TODO' },
        });
      } catch (error) {
        console.error('Failed to revert issue status:', error);
      }
    }

    // Call parent abort handler to stop the whole queue
    if (onAbortMission) {
      onAbortMission();
    }

    onClose();
  };

  const getStatusIcon = () => {
    if (isRunning) return <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />;
    if (isCompleted) return <CheckCircle2 className="w-5 h-5 text-green-400" />;
    if (isFailed || isNotFound) return <XCircle className="w-5 h-5 text-red-400" />;
    if (isCancelled) return <StopCircle className="w-5 h-5 text-yellow-400" />;
    return <Loader2 className="w-5 h-5 text-zinc-400" />;
  };

  const getStatusText = () => {
    if (isRunning) return 'Running...';
    if (isCompleted) return 'Completed';
    if (isNotFound) return 'Session Lost';
    if (isFailed) return 'Failed';
    if (isCancelled) return 'Cancelled';
    return 'Pending';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-700">
          <div className="flex items-center gap-3">
            {session.provider === 'claude_code' ? (
              <Terminal className="w-6 h-6 text-cyan-400" />
            ) : (
              <Bot className="w-6 h-6 text-purple-400" />
            )}
            <div>
              <h2 className="font-semibold">
                {session.provider === 'claude_code' ? 'Claude Code' : 'Local AI'} Execution
              </h2>
              <p className="text-sm text-zinc-400">
                {session.issue_key}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {getStatusIcon()}
              <span className={cn(
                'text-sm font-medium',
                isRunning && 'text-blue-400',
                isCompleted && 'text-green-400',
                isFailed && 'text-red-400',
                isCancelled && 'text-yellow-400'
              )}>
                {getStatusText()}
              </span>
            </div>
            {onMinimize && isRunning && (
              <button
                onClick={onMinimize}
                className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors"
                title="Minimize to floating status"
              >
                <Minimize2 className="w-5 h-5" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Progress Section */}
        {isRunning && outputData && (
          <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50">
            {/* Progress Bar */}
            <div className="mb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-zinc-300">
                  {outputData.current_action || 'Processing...'}
                </span>
                <span className="text-sm text-zinc-400">
                  {outputData.progress_percent || 0}%
                </span>
              </div>
              <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 transition-all duration-500 ease-out"
                  style={{ width: `${outputData.progress_percent || 0}%` }}
                />
              </div>
            </div>

            {/* Stats Row */}
            <div className="flex items-center gap-4 text-xs text-zinc-500">
              {outputData.phase && (
                <span className="px-2 py-0.5 bg-zinc-800 rounded text-zinc-400 capitalize">
                  {outputData.phase.replace('_', ' ')}
                </span>
              )}
              {(outputData.files_read ?? 0) > 0 && (
                <span className="flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  {outputData.files_read} read
                </span>
              )}
              {(outputData.files_written ?? 0) > 0 && (
                <span className="flex items-center gap-1">
                  <FileCode className="w-3 h-3" />
                  {outputData.files_written} written
                </span>
              )}
              {(outputData.commands_run ?? 0) > 0 && (
                <span className="flex items-center gap-1">
                  <TerminalSquare className="w-3 h-3" />
                  {outputData.commands_run} commands
                </span>
              )}
            </div>
          </div>
        )}

        {/* Long Running Warning Banner */}
        {showTimeoutWarning && isRunning && (
          <div className="mx-4 mt-2 p-4 bg-yellow-900/30 border border-yellow-600/50 rounded-lg">
            <div className="flex items-start gap-3">
              <div className="p-1.5 bg-yellow-500/20 rounded-lg flex-shrink-0">
                <AlertTriangle className="w-5 h-5 text-yellow-500" />
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-yellow-400 mb-1">
                  Long Running Execution
                </h4>
                <p className="text-sm text-yellow-300/80 mb-3">
                  This task has been running for {formatElapsedTime(elapsedTime)}. Large tasks may take longer or time out.
                  Consider breaking it down into smaller tasks for better reliability.
                </p>
                <div className="flex flex-wrap gap-2">
                  {issue && onAIBreakdown && (
                    <button
                      onClick={handleBreakdown}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 rounded text-sm font-medium transition-colors"
                    >
                      <Sparkles className="w-4 h-4" />
                      Stop & Break Down
                    </button>
                  )}
                  <button
                    onClick={handleDismissWarning}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded text-sm transition-colors"
                  >
                    <Play className="w-4 h-4" />
                    Keep Running
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Timeout/Failed State Banner */}
        {(isTimedOut || (isFailed && elapsedTime >= LONG_RUNNING_THRESHOLD)) && (
          <div className="mx-4 mt-2 p-4 bg-red-900/30 border border-red-600/50 rounded-lg">
            <div className="flex items-start gap-3">
              <div className="p-1.5 bg-red-500/20 rounded-lg flex-shrink-0">
                <Clock className="w-5 h-5 text-red-500" />
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-red-400 mb-1">
                  Execution Timed Out or Failed
                </h4>
                <p className="text-sm text-red-300/80 mb-3">
                  This task was too large to complete. Consider breaking it down into smaller tasks that can complete faster.
                </p>
                <div className="flex flex-wrap gap-2">
                  {issue && onAIBreakdown && (
                    <button
                      onClick={handleBreakdown}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 rounded text-sm font-medium transition-colors"
                    >
                      <Sparkles className="w-4 h-4" />
                      Break Down Task
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Session Lost Banner */}
        {isNotFound && (
          <div className="mx-4 mt-2 p-4 bg-red-900/30 border border-red-600/50 rounded-lg">
            <div className="flex items-start gap-3">
              <div className="p-1.5 bg-red-500/20 rounded-lg flex-shrink-0">
                <XCircle className="w-5 h-5 text-red-500" />
              </div>
              <div className="flex-1">
                <h4 className="font-medium text-red-400 mb-1">
                  Session Lost
                </h4>
                <p className="text-sm text-red-300/80 mb-3">
                  The execution session has crashed or been terminated unexpectedly.
                  The task was not completed successfully.
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={onClose}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded text-sm transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Output */}
        <div
          ref={outputRef}
          className="flex-1 overflow-y-auto p-4 font-mono text-sm bg-zinc-950 min-h-[400px]"
        >
          {outputData?.output && outputData.output.length > 0 ? (
            outputData.output.map((line, index) => (
              <div
                key={index}
                className={cn(
                  'py-0.5',
                  line.startsWith('[ERROR]') && 'text-red-400',
                  line.startsWith('[STDERR]') && 'text-orange-400',
                  line.startsWith('[DEBUG]') && 'text-zinc-500 text-xs',
                  line.startsWith('[INFO]') && 'text-green-400',
                  line.startsWith('>') && 'text-cyan-400',
                  line.startsWith('#') && 'text-yellow-400'
                )}
              >
                {line}
              </div>
            ))
          ) : (
            <div className="text-zinc-500 text-center py-8">
              {isRunning ? 'Waiting for output...' : 'No output available'}
            </div>
          )}
        </div>

        {/* Input Area (only when running) */}
        {isRunning && (
          <div className="p-4 border-t border-zinc-700 bg-zinc-900">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendInput();
                  }
                }}
                placeholder="Send input to the execution..."
                className="flex-1 px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-cyan-500"
              />
              <button
                onClick={handleSendInput}
                disabled={!input.trim() || sendInput.isPending}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed
                           rounded-lg transition-colors flex items-center gap-2"
              >
                <Send className="w-4 h-4" />
                Send
              </button>
            </div>
          </div>
        )}

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-700 bg-zinc-900/50">
          <div className="text-sm text-zinc-500 flex items-center gap-3">
            <span>{outputData?.total_lines || 0} lines</span>
            {isRunning && (
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {formatElapsedTime(elapsedTime)}
              </span>
            )}
            {outputData?.exit_code !== undefined && (
              <span>Exit: {outputData.exit_code}</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {isRunning && (
              <>
                <button
                  onClick={handleStop}
                  disabled={stopExecution.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-yellow-600/20 text-yellow-400
                             hover:bg-yellow-600/30 border border-yellow-600/30 rounded-lg transition-colors"
                >
                  <StopCircle className="w-4 h-4" />
                  Stop Task
                </button>
                <button
                  onClick={handleAbortMission}
                  disabled={stopExecution.isPending || updateIssue.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-500
                             text-white rounded-lg transition-colors font-medium"
                >
                  <XCircle className="w-4 h-4" />
                  Abort Mission
                </button>
              </>
            )}
            {(isCompleted || isRunning) && (
              <>
                <button
                  onClick={handleMarkWaitingQA}
                  disabled={updateIssue.isPending || !session.issue_id}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-500
                             rounded-lg transition-colors"
                >
                  <ClipboardCheck className="w-4 h-4" />
                  Mark as Waiting for QA
                </button>
                <button
                  onClick={handleComplete}
                  disabled={completeExecution.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500
                             rounded-lg transition-colors"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Mark as Done
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
