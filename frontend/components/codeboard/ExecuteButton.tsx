'use client';

/**
 * Execute Button - Dropdown to execute issue with AI
 * Includes pre-execution task size check with breakdown recommendations
 */

import { useState, useRef, useEffect } from 'react';
import { Play, ChevronDown, Terminal, Bot, Loader2, AlertTriangle, Sparkles, X } from 'lucide-react';
import { Issue, IssueType } from '@/types/codeboard';
import { useStartExecution, useExecutionStatus } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';

interface ExecuteButtonProps {
  issue: Issue;
  onExecutionStart?: (sessionId: string) => void;
  onAIBreakdown?: (issue: Issue) => void;
  size?: 'sm' | 'md';
}

interface TaskSizeWarning {
  type: 'large_task' | 'needs_breakdown' | 'complex_description';
  message: string;
  recommendation: string;
}

// Check if task is too large or needs breakdown
function analyzeTaskSize(issue: Issue): TaskSizeWarning | null {
  const childCount = issue.children?.length || 0;
  const descLength = issue.description?.length || 0;
  const isParentType = issue.type === 'EPIC' || issue.type === 'STORY';

  // Epic/Story with no children should be broken down
  if (isParentType && childCount === 0) {
    return {
      type: 'needs_breakdown',
      message: `This ${issue.type.toLowerCase()} has no child tasks`,
      recommendation: `It's recommended to break down this ${issue.type.toLowerCase()} into smaller tasks before execution. This improves reliability and allows you to track progress on individual pieces.`,
    };
  }

  // Epic/Story with children - recommend executing children instead
  if (isParentType && childCount > 0) {
    return {
      type: 'large_task',
      message: `This ${issue.type.toLowerCase()} has ${childCount} child task${childCount > 1 ? 's' : ''}`,
      recommendation: `Consider executing the child tasks individually for better tracking and reliability. You can select specific children from the issue panel.`,
    };
  }

  // Task with very long description might be complex
  if (descLength > 2000) {
    return {
      type: 'complex_description',
      message: 'This task has a very detailed description',
      recommendation: 'Tasks with extensive descriptions may benefit from being broken into smaller subtasks. Consider using AI Breakdown to create subtasks.',
    };
  }

  return null;
}

export function ExecuteButton({ issue, onExecutionStart, onAIBreakdown, size = 'sm' }: ExecuteButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const [pendingProvider, setPendingProvider] = useState<'claude_code' | 'local_ai' | null>(null);
  const [warning, setWarning] = useState<TaskSizeWarning | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const startExecution = useStartExecution();
  const { data: executionStatus } = useExecutionStatus(issue.id);

  const isRunning = executionStatus?.status === 'running';
  const isPending = startExecution.isPending;

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Pre-execution check
  const handlePreExecute = (provider: 'claude_code' | 'local_ai') => {
    setIsOpen(false);
    const taskWarning = analyzeTaskSize(issue);

    if (taskWarning) {
      setWarning(taskWarning);
      setPendingProvider(provider);
      setShowWarning(true);
    } else {
      // No warning, proceed directly
      executeTask(provider);
    }
  };

  const executeTask = async (provider: 'claude_code' | 'local_ai') => {
    setShowWarning(false);
    setPendingProvider(null);
    try {
      const session = await startExecution.mutateAsync({
        issueId: issue.id,
        provider,
      });
      onExecutionStart?.(session.session_id);
    } catch (error) {
      console.error('Failed to start execution:', error);
    }
  };

  const handleBreakdown = () => {
    setShowWarning(false);
    setPendingProvider(null);
    setWarning(null);
    onAIBreakdown?.(issue);
  };

  const handleExecuteAnyway = () => {
    if (pendingProvider) {
      executeTask(pendingProvider);
    }
  };

  const handleCancelWarning = () => {
    setShowWarning(false);
    setPendingProvider(null);
    setWarning(null);
  };

  // If already running, show status indicator
  if (isRunning) {
    return (
      <button
        className={cn(
          'flex items-center gap-1 rounded transition-colors',
          'bg-green-600/20 text-green-400 border border-green-600/30',
          size === 'sm' ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'
        )}
        title="Execution in progress"
        onClick={(e) => {
          e.stopPropagation();
          onExecutionStart?.(executionStatus.session_id);
        }}
      >
        <Loader2 className={cn('animate-spin', size === 'sm' ? 'w-3 h-3' : 'w-4 h-4')} />
        <span>Running...</span>
      </button>
    );
  }

  return (
    <>
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
          disabled={isPending}
          className={cn(
            'flex items-center gap-1 rounded transition-colors',
            'bg-cyan-600/20 text-cyan-400 hover:bg-cyan-600/30 border border-cyan-600/30',
            size === 'sm' ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm',
            isPending && 'opacity-50 cursor-not-allowed'
          )}
          title="Execute with AI"
        >
          {isPending ? (
            <Loader2 className={cn('animate-spin', size === 'sm' ? 'w-3 h-3' : 'w-4 h-4')} />
          ) : (
            <Play className={cn(size === 'sm' ? 'w-3 h-3' : 'w-4 h-4')} />
          )}
          <span>Execute</span>
          <ChevronDown className={cn(size === 'sm' ? 'w-3 h-3' : 'w-4 h-4')} />
        </button>

        {/* Dropdown Menu */}
        {isOpen && (
          <div
            className="absolute right-0 top-full mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl overflow-hidden min-w-[200px]"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => handlePreExecute('claude_code')}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-700 transition-colors text-left"
            >
              <Terminal className="w-5 h-5 text-cyan-400" />
              <div>
                <div className="font-medium text-sm">Claude Code</div>
                <div className="text-xs text-zinc-400">Execute in terminal with Claude</div>
              </div>
            </button>
            <div className="border-t border-zinc-700" />
            <button
              onClick={() => handlePreExecute('local_ai')}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-700 transition-colors text-left"
            >
              <Bot className="w-5 h-5 text-purple-400" />
              <div>
                <div className="font-medium text-sm">Local AI Agent</div>
                <div className="text-xs text-zinc-400">Execute with Ollama locally</div>
              </div>
            </button>
          </div>
        )}
      </div>

      {/* Task Size Warning Modal */}
      {showWarning && warning && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center" onClick={(e) => e.stopPropagation()}>
          <div className="absolute inset-0 bg-black/60" onClick={handleCancelWarning} />
          <div className="relative bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl max-w-md w-full mx-4">
            {/* Header */}
            <div className="flex items-center gap-3 px-6 py-4 border-b border-zinc-700">
              <div className="p-2 bg-yellow-500/10 rounded-lg">
                <AlertTriangle className="w-6 h-6 text-yellow-500" />
              </div>
              <div>
                <h3 className="font-semibold text-lg">Large Task Warning</h3>
                <p className="text-sm text-zinc-400">{warning.message}</p>
              </div>
              <button
                onClick={handleCancelWarning}
                className="absolute top-4 right-4 p-1 text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-4">
              <p className="text-sm text-zinc-300">{warning.recommendation}</p>
            </div>

            {/* Actions */}
            <div className="flex flex-col gap-2 px-6 py-4 border-t border-zinc-700">
              {onAIBreakdown && (
                <button
                  onClick={handleBreakdown}
                  className="flex items-center justify-center gap-2 w-full px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 rounded-lg transition-colors font-medium"
                >
                  <Sparkles className="w-4 h-4" />
                  Break Down with AI
                </button>
              )}
              <button
                onClick={handleExecuteAnyway}
                disabled={isPending}
                className="flex items-center justify-center gap-2 w-full px-4 py-2.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors"
              >
                <Play className="w-4 h-4" />
                Execute Anyway
              </button>
              <button
                onClick={handleCancelWarning}
                className="w-full px-4 py-2 text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
