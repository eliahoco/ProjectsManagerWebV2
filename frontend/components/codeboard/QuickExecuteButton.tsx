'use client';

/**
 * QuickExecuteButton - One-click execution button for fast QA
 *
 * Features:
 * - Single-click to execute all pending tasks
 * - Visual feedback during execution
 * - Progress indicator
 * - Abort capability
 */

import { useState } from 'react';
import {
  Play,
  Square,
  Loader2,
  CheckCircle2,
  XCircle,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export interface QuickExecuteButtonProps {
  pendingCount: number;
  isExecuting: boolean;
  progress?: number;
  passedCount?: number;
  failedCount?: number;
  onExecute: () => void;
  onAbort: () => void;
  variant?: 'default' | 'compact' | 'icon';
  className?: string;
}

export function QuickExecuteButton({
  pendingCount,
  isExecuting,
  progress = 0,
  passedCount = 0,
  failedCount = 0,
  onExecute,
  onAbort,
  variant = 'default',
  className,
}: QuickExecuteButtonProps) {
  const [showResults, setShowResults] = useState(false);

  // Show results for a moment after execution completes
  const hasResults = passedCount + failedCount > 0;

  if (variant === 'icon') {
    return (
      <button
        onClick={isExecuting ? onAbort : onExecute}
        disabled={!isExecuting && pendingCount === 0}
        className={cn(
          'relative p-2 rounded-lg transition-all',
          isExecuting
            ? 'bg-red-600 hover:bg-red-700 text-white'
            : pendingCount > 0
            ? 'bg-green-600 hover:bg-green-700 text-white'
            : 'bg-zinc-800 text-zinc-500 cursor-not-allowed',
          className
        )}
        title={isExecuting ? 'Stop execution' : `Run ${pendingCount} tests`}
      >
        {isExecuting ? (
          <Square className="w-4 h-4" />
        ) : (
          <Play className="w-4 h-4" />
        )}
        {pendingCount > 0 && !isExecuting && (
          <span className="absolute -top-1 -right-1 w-4 h-4 bg-yellow-500 text-black text-[10px] font-bold rounded-full flex items-center justify-center">
            {pendingCount > 9 ? '9+' : pendingCount}
          </span>
        )}
      </button>
    );
  }

  if (variant === 'compact') {
    return (
      <button
        onClick={isExecuting ? onAbort : onExecute}
        disabled={!isExecuting && pendingCount === 0}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
          isExecuting
            ? 'bg-red-600 hover:bg-red-700 text-white'
            : pendingCount > 0
            ? 'bg-green-600 hover:bg-green-700 text-white'
            : 'bg-zinc-800 text-zinc-500 cursor-not-allowed',
          className
        )}
      >
        {isExecuting ? (
          <>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>{Math.round(progress)}%</span>
          </>
        ) : (
          <>
            <Play className="w-3.5 h-3.5" />
            <span>Run {pendingCount}</span>
          </>
        )}
      </button>
    );
  }

  // Default variant with full details
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <button
        onClick={isExecuting ? onAbort : onExecute}
        disabled={!isExecuting && pendingCount === 0}
        className={cn(
          'relative flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all overflow-hidden',
          isExecuting
            ? 'bg-red-600 hover:bg-red-700 text-white'
            : pendingCount > 0
            ? 'bg-green-600 hover:bg-green-700 text-white'
            : 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
        )}
      >
        {/* Progress bar background */}
        {isExecuting && (
          <div
            className="absolute inset-0 bg-red-700 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        )}

        {/* Content */}
        <div className="relative flex items-center gap-2">
          {isExecuting ? (
            <>
              <Square className="w-4 h-4" />
              <span>Stop ({Math.round(progress)}%)</span>
            </>
          ) : (
            <>
              <Zap className="w-4 h-4" />
              <span>Quick Run</span>
              {pendingCount > 0 && (
                <span className="px-1.5 py-0.5 bg-white/20 rounded text-xs">
                  {pendingCount}
                </span>
              )}
            </>
          )}
        </div>
      </button>

      {/* Results summary */}
      {hasResults && !isExecuting && (
        <div className="flex items-center gap-2 text-sm">
          <span className="flex items-center gap-1 text-green-500">
            <CheckCircle2 className="w-3.5 h-3.5" />
            {passedCount}
          </span>
          <span className="flex items-center gap-1 text-red-500">
            <XCircle className="w-3.5 h-3.5" />
            {failedCount}
          </span>
        </div>
      )}
    </div>
  );
}

// Floating quick execute button for quick access
export function FloatingQuickExecuteButton({
  pendingCount,
  isExecuting,
  progress = 0,
  onExecute,
  onAbort,
  position = 'bottom-right',
}: QuickExecuteButtonProps & {
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
}) {
  const positionClasses = {
    'bottom-right': 'bottom-4 right-4',
    'bottom-left': 'bottom-4 left-4',
    'top-right': 'top-4 right-4',
    'top-left': 'top-4 left-4',
  };

  if (pendingCount === 0 && !isExecuting) {
    return null;
  }

  return (
    <div className={cn('fixed z-50', positionClasses[position])}>
      <button
        onClick={isExecuting ? onAbort : onExecute}
        className={cn(
          'relative flex items-center gap-2 px-4 py-3 rounded-full shadow-lg transition-all',
          'ring-2 ring-offset-2 ring-offset-zinc-950',
          isExecuting
            ? 'bg-red-600 hover:bg-red-700 text-white ring-red-500'
            : 'bg-green-600 hover:bg-green-700 text-white ring-green-500'
        )}
      >
        {isExecuting ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="font-medium">{Math.round(progress)}%</span>
          </>
        ) : (
          <>
            <Zap className="w-5 h-5" />
            <span className="font-medium">Run {pendingCount} Tests</span>
          </>
        )}
      </button>
    </div>
  );
}

export default QuickExecuteButton;
