'use client';

/**
 * NormalQAPanel - Full-featured QA testing interface for single issues
 *
 * Features:
 * - Grid layout of QA task cards
 * - Task filtering (All/Pending/Passed/Failed)
 * - Task selection for batch operations
 * - Keyboard shortcuts support
 * - Real-time execution progress
 * - Summary statistics
 * - Generate more tasks
 * - Sequential/Parallel execution modes
 */

import { useState, useMemo, useCallback, useEffect } from 'react';
import {
  Play,
  Square,
  Plus,
  CheckCircle2,
  XCircle,
  Circle,
  Loader2,
  Filter,
  Grid,
  List,
  Keyboard,
  RotateCcw,
  AlertCircle,
  Bug,
  Settings,
  RefreshCw,
  AlertTriangle,
  Gauge,
} from 'lucide-react';
import type { QATask, QATaskStatus } from '@/types/qaboard';
import { cn } from '@/lib/utils';
import { TestProgressTracker, TestProgressTrackerCompact } from './TestProgressTracker';

// Filter options
type TaskFilter = 'all' | 'pending' | 'passed' | 'failed' | 'manual';

// View mode
type ViewMode = 'grid' | 'list';

// Priority filter options
export type NormalQAPriorityFilter = 'all' | 'critical-high' | 'critical' | 'high' | 'medium' | 'low';

const PRIORITY_FILTER_OPTIONS: { value: NormalQAPriorityFilter; label: string; description: string }[] = [
  { value: 'all', label: 'All Priorities', description: 'Include all priority levels' },
  { value: 'critical-high', label: 'Critical & High', description: 'Critical and High priority only' },
  { value: 'critical', label: 'Critical Only', description: 'Critical priority only' },
  { value: 'high', label: 'High Only', description: 'High priority only' },
  { value: 'medium', label: 'Medium Only', description: 'Medium priority only' },
  { value: 'low', label: 'Low Only', description: 'Low priority only' },
];

// Task result for progress tracking
export interface TaskResult {
  key: string;
  status: QATaskStatus;
  executionTime: number;
}

export interface NormalQAPanelProps {
  tasks: QATask[];
  isExecuting: boolean;
  executionMode: 'sequential' | 'parallel';
  progress: number;
  completedTasks: number;
  totalTasks: number;
  currentTaskKey: string | null;
  currentTaskTitle?: string | null;
  tasksInFlight?: number;
  maxConcurrent?: number;
  taskResults: TaskResult[];
  error?: string | null;
  startTime?: Date | null;
  isGenerating?: boolean;
  // Execution actions
  onExecuteAll: () => void;
  onExecuteSelected: (taskIds: string[]) => void;
  onExecuteSingle: (taskId: string) => void;
  onAbort: () => void;
  onMarkManual: (taskId: string, status: 'PASS' | 'FAILED', result: string) => void;
  onCreateBug: (taskId: string) => void;
  onGenerateMore: () => void;
  onSetExecutionMode: (mode: 'sequential' | 'parallel') => void;
  onViewDetails: (task: QATask) => void;
  // Normal QA options
  priorityFilter?: NormalQAPriorityFilter;
  onSetPriorityFilter?: (filter: NormalQAPriorityFilter) => void;
  onSetMaxConcurrent?: (value: number) => void;
  onRetryFailed?: () => void;
  failedCount?: number;
  className?: string;
}

export function NormalQAPanel({
  tasks,
  isExecuting,
  executionMode,
  progress,
  completedTasks,
  totalTasks,
  currentTaskKey,
  currentTaskTitle,
  tasksInFlight,
  maxConcurrent = 5,
  taskResults,
  error,
  startTime,
  isGenerating = false,
  onExecuteAll,
  onExecuteSelected,
  onExecuteSingle,
  onAbort,
  onMarkManual,
  onCreateBug,
  onGenerateMore,
  onSetExecutionMode,
  onViewDetails,
  // Normal QA options
  priorityFilter = 'all',
  onSetPriorityFilter,
  onSetMaxConcurrent,
  onRetryFailed,
  failedCount = 0,
  className,
}: NormalQAPanelProps) {
  const [filter, setFilter] = useState<TaskFilter>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set());
  const [showKeyboardHints, setShowKeyboardHints] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // Filter tasks based on selected filter
  const filteredTasks = useMemo(() => {
    switch (filter) {
      case 'pending':
        return tasks.filter(t => t.status === 'NOT_DONE');
      case 'passed':
        return tasks.filter(t => t.status === 'PASS');
      case 'failed':
        return tasks.filter(t => t.status === 'FAILED');
      case 'manual':
        return tasks.filter(t => t.type === 'MANUAL');
      default:
        return tasks;
    }
  }, [tasks, filter]);

  // Calculate stats
  const stats = useMemo(() => {
    const pending = tasks.filter(t => t.status === 'NOT_DONE').length;
    const passed = tasks.filter(t => t.status === 'PASS').length;
    const failed = tasks.filter(t => t.status === 'FAILED').length;
    const manual = tasks.filter(t => t.type === 'MANUAL').length;
    const automated = tasks.filter(t => t.type === 'AUTOMATED').length;
    const total = tasks.length;
    const executed = passed + failed;
    const passRate = executed > 0 ? (passed / executed) * 100 : 0;
    return { pending, passed, failed, manual, automated, total, executed, passRate };
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
      if (e.key === 'm' && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        onSetExecutionMode(executionMode === 'sequential' ? 'parallel' : 'sequential');
      }

      // G: Generate more tasks
      if (e.key === 'g' && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        if (!isGenerating && !isExecuting) {
          onGenerateMore();
        }
      }

      // V: Toggle view mode
      if (e.key === 'v' && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        setViewMode(prev => prev === 'grid' ? 'list' : 'grid');
      }

      // 1-5: Quick filters
      if (!e.metaKey && !e.ctrlKey) {
        if (e.key === '1') setFilter('all');
        if (e.key === '2') setFilter('pending');
        if (e.key === '3') setFilter('passed');
        if (e.key === '4') setFilter('failed');
        if (e.key === '5') setFilter('manual');
      }

      // Ctrl/Cmd + A: Select all filtered tasks
      if (e.key === 'a' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        const newSelection = new Set(filteredTasks.map(t => t.id));
        setSelectedTasks(newSelection);
      }

      // ?: Toggle keyboard hints
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setShowKeyboardHints(prev => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExecuting, isGenerating, selectedTasks, filteredTasks, executionMode, onExecuteAll, onExecuteSelected, onAbort, onSetExecutionMode, onGenerateMore]);

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
    <div className={cn('flex flex-col h-full bg-zinc-950', className)}>
      {/* Header with controls */}
      <div className="px-6 py-3 border-b border-zinc-800">
        {/* Main controls row */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-4">
            <h2 className="font-semibold text-white">QA Tasks</h2>

            {/* Quick stats */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-zinc-400">{stats.total} total</span>
              <span className="text-zinc-600">|</span>
              <span className="text-green-500">{stats.passed} passed</span>
              <span className="text-red-500">{stats.failed} failed</span>
              <span className="text-zinc-500">{stats.pending} pending</span>
              {stats.executed > 0 && (
                <>
                  <span className="text-zinc-600">|</span>
                  <span className={cn(
                    'font-medium',
                    stats.passRate >= 80 ? 'text-green-500' : stats.passRate >= 50 ? 'text-yellow-500' : 'text-red-500'
                  )}>
                    {stats.passRate.toFixed(0)}% pass rate
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Execution mode selector */}
            <select
              value={executionMode}
              onChange={(e) => onSetExecutionMode(e.target.value as 'sequential' | 'parallel')}
              disabled={isExecuting}
              className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white disabled:opacity-50"
            >
              <option value="sequential">Sequential</option>
              <option value="parallel">Parallel</option>
            </select>

            {/* View mode toggle */}
            <div className="flex items-center border border-zinc-700 rounded overflow-hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={cn(
                  'p-1.5 transition-colors',
                  viewMode === 'grid' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
                )}
                title="Grid view (V)"
              >
                <Grid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={cn(
                  'p-1.5 transition-colors',
                  viewMode === 'list' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
                )}
                title="List view (V)"
              >
                <List className="w-4 h-4" />
              </button>
            </div>

            {/* Settings toggle */}
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={cn(
                'p-1.5 rounded transition-colors',
                showSettings ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
              )}
              title="Settings"
            >
              <Settings className="w-4 h-4" />
            </button>

            {/* Keyboard hints toggle */}
            <button
              onClick={() => setShowKeyboardHints(!showKeyboardHints)}
              className={cn(
                'p-1.5 rounded transition-colors',
                showKeyboardHints ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
              )}
              title="Keyboard shortcuts (?)"
            >
              <Keyboard className="w-4 h-4" />
            </button>

            {/* Retry failed button */}
            {failedCount > 0 && !isExecuting && onRetryFailed && (
              <button
                onClick={onRetryFailed}
                className="flex items-center gap-1 px-2 py-1.5 bg-orange-600 hover:bg-orange-700 text-white rounded text-sm"
              >
                <RefreshCw className="w-3 h-3" />
                Retry {failedCount}
              </button>
            )}

            {/* Generate more button */}
            <button
              onClick={onGenerateMore}
              disabled={isGenerating || isExecuting}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm disabled:opacity-50"
            >
              {isGenerating ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Plus className="w-3 h-3" />
              )}
              Generate More
            </button>

            {/* Execute/Abort button */}
            {isExecuting ? (
              <button
                onClick={onAbort}
                className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-sm font-medium"
              >
                <Square className="w-3 h-3" />
                Abort
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
                className="flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-sm font-medium disabled:opacity-50"
              >
                <Play className="w-3 h-3" />
                {selectedTasks.size > 0 ? `Run ${selectedTasks.size} Selected` : `Execute All (${executableCount})`}
              </button>
            )}
          </div>
        </div>

        {/* Progress tracker */}
        {(isExecuting || taskResults.length > 0) && (
          <div className="mb-3">
            <TestProgressTracker
              isExecuting={isExecuting}
              executionMode={executionMode}
              progress={progress}
              completedTasks={completedTasks}
              totalTasks={totalTasks}
              currentTaskKey={currentTaskKey}
              currentTaskTitle={currentTaskTitle ?? null}
              tasksInFlight={tasksInFlight}
              maxConcurrent={maxConcurrent}
              taskResults={taskResults}
              error={error}
              startTime={startTime}
              defaultExpanded={true}
            />
          </div>
        )}

        {/* Filter row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Filter className="w-3 h-3 text-zinc-500 mr-1" />
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
            <FilterButton
              active={filter === 'manual'}
              onClick={() => setFilter('manual')}
              count={stats.manual}
              label="Manual"
              shortcut="5"
              color="text-yellow-500"
            />
          </div>

          {/* Selection info and actions */}
          {selectedTasks.size > 0 && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-zinc-400">{selectedTasks.size} selected</span>
              <button
                onClick={clearSelection}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Keyboard hints panel */}
      {showKeyboardHints && (
        <div className="px-6 py-2 border-b border-zinc-800 bg-zinc-900/50">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-500">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">⌘↵</kbd>
              <span>Run</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">Esc</kbd>
              <span>Stop/Clear</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">M</kbd>
              <span>Toggle Mode</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">G</kbd>
              <span>Generate</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">V</kbd>
              <span>Toggle View</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">1-5</kbd>
              <span>Filters</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">⌘A</kbd>
              <span>Select All</span>
            </span>
          </div>
        </div>
      )}

      {/* Settings panel (collapsible) */}
      {showSettings && (
        <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50">
          <div className="flex flex-wrap items-center gap-4">
            {/* Priority filter */}
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-3 h-3 text-zinc-500" />
              <span className="text-xs text-zinc-500">Priority:</span>
              <select
                value={priorityFilter}
                onChange={(e) => onSetPriorityFilter?.(e.target.value as NormalQAPriorityFilter)}
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
                  className="w-20 h-1 bg-zinc-700 rounded-full appearance-none cursor-pointer disabled:opacity-50"
                />
                <span className="text-xs text-white w-4">{maxConcurrent}</span>
              </div>
            )}

            {/* Stats summary */}
            <div className="flex items-center gap-2 text-xs text-zinc-500 border-l border-zinc-700 pl-4 ml-2">
              <span>Manual: {stats.manual}</span>
              <span className="text-zinc-600">|</span>
              <span>Auto: {stats.automated}</span>
            </div>
          </div>
        </div>
      )}

      {/* Task grid/list */}
      <div className="flex-1 overflow-y-auto p-6 qa-scrollbar">
        {filteredTasks.length === 0 ? (
          <EmptyState
            filter={filter}
            totalTasks={stats.total}
            isGenerating={isGenerating}
            onGenerateMore={onGenerateMore}
          />
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredTasks.map((task) => (
              <QATaskCard
                key={task.id}
                task={task}
                isSelected={selectedTasks.has(task.id)}
                isExecuting={currentTaskKey === task.key}
                onSelect={() => toggleTaskSelection(task.id)}
                onExecute={() => onExecuteSingle(task.id)}
                onMarkManual={(status, result) => onMarkManual(task.id, status, result)}
                onCreateBug={() => onCreateBug(task.id)}
                onViewDetails={() => onViewDetails(task)}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredTasks.map((task) => (
              <QATaskRow
                key={task.id}
                task={task}
                isSelected={selectedTasks.has(task.id)}
                isExecuting={currentTaskKey === task.key}
                onSelect={() => toggleTaskSelection(task.id)}
                onExecute={() => onExecuteSingle(task.id)}
                onMarkManual={(status, result) => onMarkManual(task.id, status, result)}
                onCreateBug={() => onCreateBug(task.id)}
                onViewDetails={() => onViewDetails(task)}
              />
            ))}
          </div>
        )}
      </div>
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

// Empty state component
function EmptyState({
  filter,
  totalTasks,
  isGenerating,
  onGenerateMore,
}: {
  filter: TaskFilter;
  totalTasks: number;
  isGenerating: boolean;
  onGenerateMore: () => void;
}) {
  if (totalTasks === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center">
        <div className="w-16 h-16 mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-zinc-500" />
        </div>
        <h3 className="text-lg font-medium text-zinc-300 mb-2">No QA Tasks Yet</h3>
        <p className="text-zinc-500 mb-4 max-w-md">
          Generate a QA plan to create test tasks for this issue. The AI will analyze the issue and create relevant test scenarios.
        </p>
        <button
          onClick={onGenerateMore}
          disabled={isGenerating}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
        >
          {isGenerating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
          {isGenerating ? 'Generating...' : 'Generate QA Plan'}
        </button>
      </div>
    );
  }

  const messages: Record<TaskFilter, { icon: React.ReactNode; title: string; description: string }> = {
    all: {
      icon: <Circle className="w-8 h-8 text-zinc-500" />,
      title: 'No tasks found',
      description: 'There are no QA tasks matching the current filter.',
    },
    pending: {
      icon: <CheckCircle2 className="w-8 h-8 text-green-500" />,
      title: 'All tasks completed!',
      description: 'Great work! All QA tasks have been executed.',
    },
    passed: {
      icon: <Circle className="w-8 h-8 text-zinc-500" />,
      title: 'No passed tasks',
      description: 'No tasks have passed yet. Run some tests to see results here.',
    },
    failed: {
      icon: <CheckCircle2 className="w-8 h-8 text-green-500" />,
      title: 'No failed tasks',
      description: 'Great news! No tasks have failed.',
    },
    manual: {
      icon: <Circle className="w-8 h-8 text-zinc-500" />,
      title: 'No manual tasks',
      description: 'There are no manual test tasks for this issue.',
    },
  };

  const message = messages[filter];

  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-12">
      <div className="w-16 h-16 mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
        {message.icon}
      </div>
      <h3 className="text-lg font-medium text-zinc-300 mb-2">{message.title}</h3>
      <p className="text-zinc-500 max-w-md">{message.description}</p>
    </div>
  );
}

// QA Task Card component (grid view)
function QATaskCard({
  task,
  isSelected,
  isExecuting,
  onSelect,
  onExecute,
  onMarkManual,
  onCreateBug,
  onViewDetails,
}: {
  task: QATask;
  isSelected: boolean;
  isExecuting: boolean;
  onSelect: () => void;
  onExecute: () => void;
  onMarkManual: (status: 'PASS' | 'FAILED', result: string) => void;
  onCreateBug: () => void;
  onViewDetails: () => void;
}) {
  const [showManualInput, setShowManualInput] = useState(false);
  const [manualResult, setManualResult] = useState('');

  const isPending = task.status === 'NOT_DONE';
  const isPassed = task.status === 'PASS';
  const isFailed = task.status === 'FAILED';
  const isManual = task.type === 'MANUAL';
  const isAutomated = task.type === 'AUTOMATED';

  const statusColors: Record<QATaskStatus, string> = {
    NOT_DONE: 'bg-zinc-600',
    IN_PROGRESS: 'bg-blue-600',
    PASS: 'bg-green-600',
    FAILED: 'bg-red-600',
  };

  const priorityColors: Record<string, string> = {
    LOW: 'text-zinc-400',
    MEDIUM: 'text-yellow-400',
    HIGH: 'text-orange-400',
    CRITICAL: 'text-red-400',
  };

  return (
    <div
      className={cn(
        'p-4 bg-zinc-800 rounded-lg border transition-all',
        isExecuting
          ? 'border-blue-500 ring-2 ring-blue-500/30'
          : isSelected
          ? 'border-blue-500'
          : 'border-zinc-700 hover:border-zinc-600'
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          {/* Selection checkbox */}
          <button
            onClick={onSelect}
            className={cn(
              'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
              isSelected
                ? 'bg-blue-600 border-blue-600'
                : 'border-zinc-600 hover:border-zinc-500'
            )}
          >
            {isSelected && <CheckCircle2 className="w-3 h-3 text-white" />}
          </button>

          {/* Status badge */}
          {isExecuting ? (
            <span className="px-2 py-0.5 text-xs rounded text-white bg-blue-600 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              RUNNING
            </span>
          ) : (
            <span className={cn('px-2 py-0.5 text-xs rounded text-white', statusColors[task.status])}>
              {task.status}
            </span>
          )}

          {/* Task key */}
          <span className="text-xs text-zinc-500 font-mono">{task.key}</span>
        </div>

        {/* Priority and type */}
        <div className="flex items-center gap-1">
          <span className={cn('text-xs', priorityColors[task.priority] || 'text-zinc-400')}>
            {task.priority}
          </span>
          {isManual && (
            <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1.5 rounded">
              Manual
            </span>
          )}
        </div>
      </div>

      {/* Title */}
      <p className="text-sm text-zinc-200 mb-3">{task.title}</p>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {isPending && isAutomated && !isExecuting && (
          <button
            onClick={onExecute}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded"
          >
            <Play className="w-3 h-3" />
            Run
          </button>
        )}
        {isPending && isManual && (
          <button
            onClick={() => setShowManualInput(!showManualInput)}
            className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
          >
            Mark
          </button>
        )}
        {isFailed && !task.bugIssueId && (
          <button
            onClick={onCreateBug}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
          >
            <Bug className="w-3 h-3" />
            Create Bug
          </button>
        )}
        <button
          onClick={onViewDetails}
          className="px-2 py-1 text-xs text-zinc-400 hover:text-white transition-colors"
        >
          Details
        </button>
      </div>

      {/* Manual input */}
      {showManualInput && (
        <div className="mt-3 pt-3 border-t border-zinc-700">
          <textarea
            value={manualResult}
            onChange={(e) => setManualResult(e.target.value)}
            placeholder="Enter actual result..."
            rows={2}
            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-sm text-white resize-none focus:outline-none focus:border-zinc-600"
          />
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => {
                onMarkManual('PASS', manualResult);
                setShowManualInput(false);
                setManualResult('');
              }}
              className="px-3 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded"
            >
              Mark Pass
            </button>
            <button
              onClick={() => {
                onMarkManual('FAILED', manualResult);
                setShowManualInput(false);
                setManualResult('');
              }}
              className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
            >
              Mark Failed
            </button>
          </div>
        </div>
      )}

      {/* Actual result */}
      {task.actualResult && (
        <div className="mt-2 p-2 bg-zinc-900 rounded text-xs text-zinc-400">
          <strong>Result:</strong> {task.actualResult}
        </div>
      )}
    </div>
  );
}

// QA Task Row component (list view)
function QATaskRow({
  task,
  isSelected,
  isExecuting,
  onSelect,
  onExecute,
  onMarkManual,
  onCreateBug,
  onViewDetails,
}: {
  task: QATask;
  isSelected: boolean;
  isExecuting: boolean;
  onSelect: () => void;
  onExecute: () => void;
  onMarkManual: (status: 'PASS' | 'FAILED', result: string) => void;
  onCreateBug: () => void;
  onViewDetails: () => void;
}) {
  const [showManualInput, setShowManualInput] = useState(false);
  const [manualResult, setManualResult] = useState('');

  const isPending = task.status === 'NOT_DONE';
  const isFailed = task.status === 'FAILED';
  const isManual = task.type === 'MANUAL';
  const isAutomated = task.type === 'AUTOMATED';

  // Status icon
  const StatusIcon = () => {
    if (isExecuting) {
      return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
    }
    if (task.status === 'PASS') {
      return <CheckCircle2 className="w-4 h-4 text-green-500" />;
    }
    if (task.status === 'FAILED') {
      return <XCircle className="w-4 h-4 text-red-500" />;
    }
    return <Circle className="w-4 h-4 text-zinc-500" />;
  };

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 bg-zinc-800 rounded-lg border transition-all',
        isExecuting
          ? 'border-blue-500 ring-1 ring-blue-500/30'
          : isSelected
          ? 'border-blue-500'
          : 'border-zinc-700 hover:border-zinc-600'
      )}
    >
      {/* Selection checkbox */}
      <button
        onClick={onSelect}
        className={cn(
          'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
          isSelected
            ? 'bg-blue-600 border-blue-600'
            : 'border-zinc-600 hover:border-zinc-500'
        )}
      >
        {isSelected && <CheckCircle2 className="w-3 h-3 text-white" />}
      </button>

      {/* Status icon */}
      <StatusIcon />

      {/* Task info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-500">{task.key}</span>
          {isManual && (
            <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1 rounded">Manual</span>
          )}
          <span className="text-xs text-zinc-500">{task.priority}</span>
        </div>
        <p className="text-sm text-zinc-200 truncate">{task.title}</p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        {isPending && isAutomated && !isExecuting && (
          <button
            onClick={onExecute}
            className="p-1.5 rounded bg-green-600 hover:bg-green-700 text-white transition-colors"
            title="Run test"
          >
            <Play className="w-3 h-3" />
          </button>
        )}
        {isPending && isManual && (
          <button
            onClick={() => setShowManualInput(!showManualInput)}
            className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
          >
            Mark
          </button>
        )}
        {isFailed && !task.bugIssueId && (
          <button
            onClick={onCreateBug}
            className="p-1.5 rounded bg-red-600 hover:bg-red-700 text-white transition-colors"
            title="Create bug"
          >
            <Bug className="w-3 h-3" />
          </button>
        )}
        <button
          onClick={onViewDetails}
          className="p-1.5 text-zinc-400 hover:text-white transition-colors"
          title="View details"
        >
          <AlertCircle className="w-4 h-4" />
        </button>
      </div>

      {/* Manual input popup */}
      {showManualInput && (
        <div className="absolute right-0 top-full mt-1 z-10 p-3 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl w-72">
          <textarea
            value={manualResult}
            onChange={(e) => setManualResult(e.target.value)}
            placeholder="Enter actual result..."
            rows={2}
            className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-sm text-white resize-none focus:outline-none focus:border-zinc-600"
            autoFocus
          />
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => {
                onMarkManual('PASS', manualResult);
                setShowManualInput(false);
                setManualResult('');
              }}
              className="flex-1 px-2 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded"
            >
              Pass
            </button>
            <button
              onClick={() => {
                onMarkManual('FAILED', manualResult);
                setShowManualInput(false);
                setManualResult('');
              }}
              className="flex-1 px-2 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
            >
              Fail
            </button>
            <button
              onClick={() => setShowManualInput(false)}
              className="px-2 py-1 text-xs bg-zinc-700 hover:bg-zinc-600 text-white rounded"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default NormalQAPanel;
