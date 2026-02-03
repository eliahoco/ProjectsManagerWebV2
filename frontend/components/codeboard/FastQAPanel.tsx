'use client';

/**
 * FastQAPanel - A streamlined, minimal QA execution interface
 *
 * Features:
 * - Compact task list with one-click actions
 * - Quick execution of pending tasks
 * - Keyboard shortcuts for power users
 * - Real-time progress tracking
 * - Minimal UI with focus on speed
 */

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  Play,
  Square,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Filter,
  ChevronRight,
  RotateCcw,
  Settings,
  Keyboard,
  RefreshCw,
  Volume2,
  VolumeX,
  Bell,
  BellOff,
  AlertTriangle,
  Gauge,
} from 'lucide-react';
import type { QATask, QATaskStatus } from '@/types/qaboard';
import type { FastQAPriorityFilter } from '@/hooks/useQuickQAExecution';
import { cn } from '@/lib/utils';
import { QAQuickCard } from './QAQuickCard';
import { TestProgressTrackerCompact } from './TestProgressTracker';

// Filter options for quick filtering
type QuickFilter = 'all' | 'pending' | 'passed' | 'failed';

// Priority filter options for display
const PRIORITY_FILTER_OPTIONS: { value: FastQAPriorityFilter; label: string; description: string }[] = [
  { value: 'all', label: 'All', description: 'Run all priorities' },
  { value: 'critical-high', label: 'Critical & High', description: 'Critical and High priority only' },
  { value: 'critical', label: 'Critical', description: 'Critical priority only' },
  { value: 'high', label: 'High', description: 'High priority only' },
  { value: 'medium', label: 'Medium', description: 'Medium priority only' },
  { value: 'low', label: 'Low', description: 'Low priority only' },
];

export interface FastQAPanelProps {
  tasks: QATask[];
  isExecuting: boolean;
  executionMode: 'sequential' | 'parallel';
  progress: number;
  completedTasks: number;
  totalTasks: number;
  currentTaskKey: string | null;
  taskResults: Array<{ key: string; status: QATaskStatus; executionTime: number }>;
  // Execution actions
  onExecuteAll: () => void;
  onExecuteSelected: (taskIds: string[]) => void;
  onExecuteSingle: (taskId: string) => void;
  onRetryFailed?: () => void;
  onAbort: () => void;
  onMarkManual: (taskId: string, status: 'PASS' | 'FAILED', result: string) => void;
  onToggleMode: () => void;
  onClearResults?: () => void;
  // Fast QA options
  maxConcurrent?: number;
  priorityFilter?: FastQAPriorityFilter;
  autoRetryFailed?: boolean;
  stopOnFirstFailure?: boolean;
  soundEnabled?: boolean;
  showNotifications?: boolean;
  // Fast QA option setters
  onSetMaxConcurrent?: (value: number) => void;
  onSetPriorityFilter?: (filter: FastQAPriorityFilter) => void;
  onSetAutoRetryFailed?: (enabled: boolean) => void;
  onSetStopOnFirstFailure?: (stop: boolean) => void;
  onSetSoundEnabled?: (enabled: boolean) => void;
  onSetShowNotifications?: (show: boolean) => void;
  // UI options
  className?: string;
  showKeyboardHints?: boolean;
  failedCount?: number;
}

export function FastQAPanel({
  tasks,
  isExecuting,
  executionMode,
  progress,
  completedTasks,
  totalTasks,
  currentTaskKey,
  taskResults,
  onExecuteAll,
  onExecuteSelected,
  onExecuteSingle,
  onRetryFailed,
  onAbort,
  onMarkManual,
  onToggleMode,
  onClearResults,
  // Fast QA options with defaults
  maxConcurrent = 5,
  priorityFilter = 'all',
  autoRetryFailed = false,
  stopOnFirstFailure = false,
  soundEnabled = false,
  showNotifications = true,
  // Option setters
  onSetMaxConcurrent,
  onSetPriorityFilter,
  onSetAutoRetryFailed,
  onSetStopOnFirstFailure,
  onSetSoundEnabled,
  onSetShowNotifications,
  // UI options
  className,
  showKeyboardHints = true,
  failedCount = 0,
}: FastQAPanelProps) {
  const [filter, setFilter] = useState<QuickFilter>('pending');
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set());
  const [showSettings, setShowSettings] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Filter tasks based on selected filter
  const filteredTasks = useMemo(() => {
    switch (filter) {
      case 'pending':
        return tasks.filter(t => t.status === 'NOT_DONE');
      case 'passed':
        return tasks.filter(t => t.status === 'PASS');
      case 'failed':
        return tasks.filter(t => t.status === 'FAILED');
      default:
        return tasks;
    }
  }, [tasks, filter]);

  // Calculate stats
  const stats = useMemo(() => {
    const pending = tasks.filter(t => t.status === 'NOT_DONE').length;
    const passed = tasks.filter(t => t.status === 'PASS').length;
    const failed = tasks.filter(t => t.status === 'FAILED').length;
    const total = tasks.length;
    const passRate = total > 0 ? (passed / (passed + failed)) * 100 : 0;
    return { pending, passed, failed, total, passRate };
  }, [tasks]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Cmd/Ctrl + Enter: Execute all pending
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!isExecuting) {
          if (selectedTasks.size > 0) {
            onExecuteSelected(Array.from(selectedTasks));
          } else {
            onExecuteAll();
          }
        }
      }

      // Escape: Abort execution or clear selection
      if (e.key === 'Escape') {
        e.preventDefault();
        if (isExecuting) {
          onAbort();
        } else {
          setSelectedTasks(new Set());
        }
      }

      // M: Toggle execution mode
      if (e.key === 'm' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        onToggleMode();
      }

      // 1-4: Quick filters
      if (!e.metaKey && !e.ctrlKey) {
        if (e.key === '1') setFilter('all');
        if (e.key === '2') setFilter('pending');
        if (e.key === '3') setFilter('passed');
        if (e.key === '4') setFilter('failed');
      }

      // A: Select all filtered tasks
      if (e.key === 'a' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        const newSelection = new Set(filteredTasks.map(t => t.id));
        setSelectedTasks(newSelection);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExecuting, selectedTasks, filteredTasks, onExecuteAll, onExecuteSelected, onAbort, onToggleMode]);

  // Toggle task selection
  const toggleTaskSelection = useCallback((taskId: string) => {
    setSelectedTasks(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }, []);

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelectedTasks(new Set());
  }, []);

  // Get executable task count
  const executableCount = useMemo(() => {
    if (selectedTasks.size > 0) {
      return tasks.filter(t => selectedTasks.has(t.id) && t.status === 'NOT_DONE' && t.type === 'AUTOMATED').length;
    }
    return tasks.filter(t => t.status === 'NOT_DONE' && t.type === 'AUTOMATED').length;
  }, [tasks, selectedTasks]);

  return (
    <div ref={containerRef} className={cn('flex flex-col h-full bg-zinc-950', className)}>
      {/* Header - Compact with quick stats */}
      <div className="px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <Zap className="w-5 h-5 text-yellow-500" />
            <h2 className="font-semibold text-white">Fast QA</h2>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-zinc-400">{stats.total} tasks</span>
              <span className="text-zinc-600">|</span>
              <span className="text-green-500">{stats.passed} passed</span>
              <span className="text-red-500">{stats.failed} failed</span>
              <span className="text-zinc-500">{stats.pending} pending</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Execution mode toggle */}
            <button
              onClick={onToggleMode}
              disabled={isExecuting}
              className={cn(
                'px-2 py-1 text-xs rounded transition-colors',
                executionMode === 'parallel'
                  ? 'bg-purple-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:text-white'
              )}
              title={`Mode: ${executionMode} (press M to toggle)`}
            >
              {executionMode === 'parallel' ? 'Parallel' : 'Sequential'}
            </button>

            {/* Settings toggle */}
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={cn(
                'p-1 rounded transition-colors',
                showSettings ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
              )}
            >
              <Settings className="w-4 h-4" />
            </button>

            {/* Main execute button */}
            {isExecuting ? (
              <button
                onClick={onAbort}
                className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-sm font-medium"
              >
                <Square className="w-3 h-3" />
                Stop
              </button>
            ) : (
              <button
                onClick={() => {
                  if (selectedTasks.size > 0) {
                    onExecuteSelected(Array.from(selectedTasks));
                  } else {
                    onExecuteAll();
                  }
                }}
                disabled={executableCount === 0}
                className="flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Play className="w-3 h-3" />
                Run {selectedTasks.size > 0 ? selectedTasks.size : executableCount}
              </button>
            )}
          </div>
        </div>

        {/* Progress bar during execution */}
        {(isExecuting || taskResults.length > 0) && (
          <TestProgressTrackerCompact
            isExecuting={isExecuting}
            executionMode={executionMode}
            progress={progress}
            completedTasks={completedTasks}
            totalTasks={totalTasks}
            taskResults={taskResults}
            className="mb-3"
          />
        )}

        {/* Quick filters */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <FilterButton
              active={filter === 'all'}
              onClick={() => setFilter('all')}
              count={stats.total}
              label="All"
              shortcut="1"
            />
            <FilterButton
              active={filter === 'pending'}
              onClick={() => setFilter('pending')}
              count={stats.pending}
              label="Pending"
              shortcut="2"
              color="text-zinc-400"
            />
            <FilterButton
              active={filter === 'passed'}
              onClick={() => setFilter('passed')}
              count={stats.passed}
              label="Passed"
              shortcut="3"
              color="text-green-500"
            />
            <FilterButton
              active={filter === 'failed'}
              onClick={() => setFilter('failed')}
              count={stats.failed}
              label="Failed"
              shortcut="4"
              color="text-red-500"
            />
          </div>

          {/* Selection info and actions */}
          {selectedTasks.size > 0 && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-zinc-400">{selectedTasks.size} selected</span>
              <button
                onClick={clearSelection}
                className="text-zinc-500 hover:text-white"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Fast QA Options Panel (collapsible) */}
      {showSettings && (
        <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50 space-y-3">
          {/* Keyboard hints */}
          {showKeyboardHints && (
            <div className="flex items-center gap-1 text-xs text-zinc-500">
              <Keyboard className="w-3 h-3 mr-1" />
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">⌘↵</kbd>
              <span>Run</span>
              <span className="mx-2">|</span>
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">Esc</kbd>
              <span>Stop/Clear</span>
              <span className="mx-2">|</span>
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">M</kbd>
              <span>Toggle Mode</span>
              <span className="mx-2">|</span>
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">1-4</kbd>
              <span>Filter</span>
              <span className="mx-2">|</span>
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">⌘A</kbd>
              <span>Select All</span>
            </div>
          )}

          {/* Options row 1: Execution settings */}
          <div className="flex flex-wrap items-center gap-4">
            {/* Priority filter */}
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-3 h-3 text-zinc-500" />
              <span className="text-xs text-zinc-500">Priority:</span>
              <select
                value={priorityFilter}
                onChange={(e) => onSetPriorityFilter?.(e.target.value as FastQAPriorityFilter)}
                disabled={isExecuting}
                className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white disabled:opacity-50"
              >
                {PRIORITY_FILTER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Max concurrent (for parallel mode) */}
            {executionMode === 'parallel' && (
              <div className="flex items-center gap-2">
                <Gauge className="w-3 h-3 text-zinc-500" />
                <span className="text-xs text-zinc-500">Concurrent:</span>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={maxConcurrent}
                  onChange={(e) => onSetMaxConcurrent?.(parseInt(e.target.value))}
                  disabled={isExecuting}
                  className="w-16 h-1 bg-zinc-700 rounded-full appearance-none cursor-pointer disabled:opacity-50"
                />
                <span className="text-xs text-white w-4">{maxConcurrent}</span>
              </div>
            )}

            {/* Retry failed button */}
            {failedCount > 0 && !isExecuting && onRetryFailed && (
              <button
                onClick={onRetryFailed}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-orange-600 hover:bg-orange-700 text-white rounded"
              >
                <RefreshCw className="w-3 h-3" />
                Retry {failedCount} Failed
              </button>
            )}
          </div>

          {/* Options row 2: Toggles */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Stop on first failure */}
            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                checked={stopOnFirstFailure}
                onChange={(e) => onSetStopOnFirstFailure?.(e.target.checked)}
                disabled={isExecuting}
                className="w-3 h-3 rounded bg-zinc-700 border-zinc-600 text-blue-500 focus:ring-blue-500 disabled:opacity-50"
              />
              <span className="text-xs text-zinc-400 group-hover:text-white">Stop on failure</span>
            </label>

            {/* Auto retry failed */}
            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                checked={autoRetryFailed}
                onChange={(e) => onSetAutoRetryFailed?.(e.target.checked)}
                disabled={isExecuting}
                className="w-3 h-3 rounded bg-zinc-700 border-zinc-600 text-blue-500 focus:ring-blue-500 disabled:opacity-50"
              />
              <span className="text-xs text-zinc-400 group-hover:text-white">Auto-retry failed</span>
            </label>

            {/* Sound toggle */}
            <button
              onClick={() => onSetSoundEnabled?.(!soundEnabled)}
              disabled={isExecuting}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors',
                soundEnabled
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:text-white'
              )}
              title={soundEnabled ? 'Sound enabled' : 'Sound disabled'}
            >
              {soundEnabled ? <Volume2 className="w-3 h-3" /> : <VolumeX className="w-3 h-3" />}
            </button>

            {/* Notifications toggle */}
            <button
              onClick={() => onSetShowNotifications?.(!showNotifications)}
              disabled={isExecuting}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors',
                showNotifications
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:text-white'
              )}
              title={showNotifications ? 'Notifications enabled' : 'Notifications disabled'}
            >
              {showNotifications ? <Bell className="w-3 h-3" /> : <BellOff className="w-3 h-3" />}
            </button>
          </div>
        </div>
      )}

      {/* Task list */}
      <div className="flex-1 overflow-y-auto p-2">
        {filteredTasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-8">
            <div className="w-12 h-12 mb-3 rounded-full bg-zinc-800 flex items-center justify-center">
              {filter === 'pending' ? (
                <CheckCircle2 className="w-6 h-6 text-green-500" />
              ) : filter === 'failed' ? (
                <XCircle className="w-6 h-6 text-zinc-500" />
              ) : (
                <Clock className="w-6 h-6 text-zinc-500" />
              )}
            </div>
            <p className="text-zinc-400 text-sm">
              {filter === 'pending'
                ? 'All tasks completed!'
                : filter === 'failed'
                ? 'No failed tasks'
                : filter === 'passed'
                ? 'No passed tasks yet'
                : 'No tasks found'}
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {filteredTasks.map(task => (
              <QAQuickCard
                key={task.id}
                task={task}
                isSelected={selectedTasks.has(task.id)}
                isExecuting={currentTaskKey === task.key}
                onSelect={() => toggleTaskSelection(task.id)}
                onExecute={() => onExecuteSingle(task.id)}
                onMarkPass={(result) => onMarkManual(task.id, 'PASS', result)}
                onMarkFail={(result) => onMarkManual(task.id, 'FAILED', result)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer with pass rate */}
      {stats.passed + stats.failed > 0 && (
        <div className="px-4 py-2 border-t border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-500">Pass Rate</span>
            <div className="flex items-center gap-2">
              <div className="w-32 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full transition-all duration-300',
                    stats.passRate >= 80 ? 'bg-green-500' : stats.passRate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                  )}
                  style={{ width: `${stats.passRate}%` }}
                />
              </div>
              <span className={cn(
                'font-medium',
                stats.passRate >= 80 ? 'text-green-500' : stats.passRate >= 50 ? 'text-yellow-500' : 'text-red-500'
              )}>
                {stats.passRate.toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Filter button component
function FilterButton({
  active,
  onClick,
  count,
  label,
  shortcut,
  color,
}: {
  active: boolean;
  onClick: () => void;
  count: number;
  label: string;
  shortcut: string;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors',
        active
          ? 'bg-zinc-700 text-white'
          : 'text-zinc-500 hover:text-white hover:bg-zinc-800'
      )}
    >
      <span className={color}>{label}</span>
      <span className={cn(
        'px-1 py-0.5 rounded text-[10px]',
        active ? 'bg-zinc-600' : 'bg-zinc-800'
      )}>
        {count}
      </span>
    </button>
  );
}

export default FastQAPanel;
