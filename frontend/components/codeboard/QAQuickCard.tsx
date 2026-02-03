'use client';

/**
 * QAQuickCard - Compact QA task card for fast QA UI
 *
 * Features:
 * - Minimal design with essential info only
 * - One-click execution
 * - Quick pass/fail marking for manual tests
 * - Selection support for batch operations
 * - Visual execution state indicator
 */

import { useState } from 'react';
import {
  Play,
  CheckCircle2,
  XCircle,
  Circle,
  Loader2,
  ChevronRight,
  User,
  Bot,
} from 'lucide-react';
import type { QATask, QATaskStatus } from '@/types/qaboard';
import { cn } from '@/lib/utils';

export interface QAQuickCardProps {
  task: QATask;
  isSelected: boolean;
  isExecuting: boolean;
  onSelect: () => void;
  onExecute: () => void;
  onMarkPass: (result: string) => void;
  onMarkFail: (result: string) => void;
}

export function QAQuickCard({
  task,
  isSelected,
  isExecuting,
  onSelect,
  onExecute,
  onMarkPass,
  onMarkFail,
}: QAQuickCardProps) {
  const [showQuickMark, setShowQuickMark] = useState(false);
  const [quickResult, setQuickResult] = useState('');

  const isPending = task.status === 'NOT_DONE';
  const isPassed = task.status === 'PASS';
  const isFailed = task.status === 'FAILED';
  const isManual = task.type === 'MANUAL';
  const isAutomated = task.type === 'AUTOMATED';

  // Status icon component
  const StatusIcon = () => {
    if (isExecuting) {
      return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
    }
    if (isPassed) {
      return <CheckCircle2 className="w-4 h-4 text-green-500" />;
    }
    if (isFailed) {
      return <XCircle className="w-4 h-4 text-red-500" />;
    }
    return <Circle className="w-4 h-4 text-zinc-500" />;
  };

  // Handle quick mark submission
  const handleQuickMark = (status: 'PASS' | 'FAILED') => {
    if (status === 'PASS') {
      onMarkPass(quickResult || 'Marked as passed');
    } else {
      onMarkFail(quickResult || 'Marked as failed');
    }
    setShowQuickMark(false);
    setQuickResult('');
  };

  return (
    <div
      className={cn(
        'group relative flex items-center gap-2 p-2 rounded-lg border transition-all cursor-pointer',
        isExecuting
          ? 'bg-blue-950/30 border-blue-600 ring-1 ring-blue-500/30'
          : isSelected
          ? 'bg-zinc-800 border-blue-500'
          : 'bg-zinc-900 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-800/50'
      )}
      onClick={onSelect}
    >
      {/* Selection checkbox */}
      <div
        className={cn(
          'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
          isSelected
            ? 'bg-blue-600 border-blue-600'
            : 'border-zinc-600 group-hover:border-zinc-500'
        )}
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
      >
        {isSelected && <CheckCircle2 className="w-3 h-3 text-white" />}
      </div>

      {/* Status icon */}
      <StatusIcon />

      {/* Task info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-500">{task.key}</span>
          {isManual && (
            <span className="flex items-center gap-0.5 text-[10px] text-yellow-500">
              <User className="w-3 h-3" />
              Manual
            </span>
          )}
          {isAutomated && (
            <span className="flex items-center gap-0.5 text-[10px] text-blue-400">
              <Bot className="w-3 h-3" />
            </span>
          )}
        </div>
        <p className="text-sm text-zinc-200 truncate">{task.title}</p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
        {isPending && isAutomated && !isExecuting && (
          <button
            onClick={onExecute}
            className="p-1.5 rounded bg-green-600 hover:bg-green-700 text-white transition-colors"
            title="Run test"
          >
            <Play className="w-3 h-3" />
          </button>
        )}

        {isPending && isManual && !showQuickMark && (
          <button
            onClick={() => setShowQuickMark(true)}
            className="px-2 py-1 rounded bg-zinc-700 hover:bg-zinc-600 text-xs text-white transition-colors"
          >
            Mark
          </button>
        )}

        {isExecuting && (
          <span className="px-2 py-1 text-xs text-blue-400 bg-blue-950/50 rounded">
            Running...
          </span>
        )}

        {!isPending && !isExecuting && task.lastExecutedAt && (
          <span className="text-[10px] text-zinc-500">
            {new Date(task.lastExecutedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}

        <ChevronRight className="w-4 h-4 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>

      {/* Quick mark panel (for manual tests) */}
      {showQuickMark && (
        <div
          className="absolute right-0 top-full mt-1 z-10 p-2 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl w-64"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="text"
            value={quickResult}
            onChange={(e) => setQuickResult(e.target.value)}
            placeholder="Result notes (optional)"
            className="w-full px-2 py-1 mb-2 text-xs bg-zinc-900 border border-zinc-700 rounded text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-600"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.shiftKey) {
                handleQuickMark('FAILED');
              } else if (e.key === 'Enter') {
                handleQuickMark('PASS');
              } else if (e.key === 'Escape') {
                setShowQuickMark(false);
              }
            }}
          />
          <div className="flex gap-1">
            <button
              onClick={() => handleQuickMark('PASS')}
              className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-xs transition-colors"
            >
              <CheckCircle2 className="w-3 h-3" />
              Pass
            </button>
            <button
              onClick={() => handleQuickMark('FAILED')}
              className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-xs transition-colors"
            >
              <XCircle className="w-3 h-3" />
              Fail
            </button>
            <button
              onClick={() => setShowQuickMark(false)}
              className="px-2 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white rounded text-xs transition-colors"
            >
              Cancel
            </button>
          </div>
          <p className="mt-1 text-[10px] text-zinc-500">
            Press Enter for Pass, Shift+Enter for Fail
          </p>
        </div>
      )}
    </div>
  );
}

export default QAQuickCard;
