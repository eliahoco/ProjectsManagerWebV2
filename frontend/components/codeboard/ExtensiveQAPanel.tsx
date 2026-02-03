'use client';

/**
 * ExtensiveQAPanel - Comprehensive, detailed QA testing interface
 *
 * Features:
 * - Full task details with scenario, expected result, and actual result
 * - Test coverage visualization with statistics dashboard
 * - Advanced filtering by priority, type, status, and search
 * - Execution history viewer for each task
 * - Batch operations for bulk actions
 * - Task grouping by priority or type
 * - Advanced execution controls (configurable concurrency, retry failed)
 * - Detailed progress tracking with time estimates
 * - Keyboard shortcuts for power users
 * - Responsive design with collapsible sections
 */

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  Play,
  Square,
  Plus,
  CheckCircle2,
  XCircle,
  Circle,
  Loader2,
  Filter,
  Keyboard,
  RotateCcw,
  AlertCircle,
  Bug,
  ChevronDown,
  ChevronRight,
  Clock,
  Timer,
  Zap,
  Search,
  SlidersHorizontal,
  LayoutGrid,
  List,
  History,
  Target,
  TrendingUp,
  RefreshCw,
  Eye,
  EyeOff,
  Settings,
  Maximize2,
  Minimize2,
  ArrowUpDown,
  CheckSquare,
  Square as SquareIcon,
  FileText,
  FlaskConical,
  AlertTriangle,
  Info,
} from 'lucide-react';
import type { QATask, QATaskStatus, QAPriority, QATaskType, QAExecutionRun, ExtensiveQAOptions } from '@/types/qaboard';
import { parseExecutionHistory, DEFAULT_EXTENSIVE_QA_OPTIONS } from '@/types/qaboard';
import { cn } from '@/lib/utils';
import { TestProgressTracker, MiniDonutChart } from './TestProgressTracker';
import type { TaskResult } from './TestProgressTracker';
import { ExtensiveQAOptionsPanel } from './ExtensiveQAOptionsPanel';

// Filter state type
interface FilterState {
  status: QATaskStatus | 'all';
  priority: QAPriority | 'all';
  type: QATaskType | 'all';
  search: string;
}

// Group by options
type GroupBy = 'none' | 'priority' | 'type' | 'status';

// Sort options
type SortBy = 'key' | 'priority' | 'status' | 'lastExecuted';
type SortOrder = 'asc' | 'desc';

// View mode
type ViewMode = 'detailed' | 'compact' | 'table';

export interface ExtensiveQAPanelProps {
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
  onExecuteAll: () => void;
  onExecuteSelected: (taskIds: string[]) => void;
  onExecuteSingle: (taskId: string) => void;
  onAbort: () => void;
  onMarkManual: (taskId: string, status: 'PASS' | 'FAILED', result: string) => void;
  onCreateBug: (taskId: string) => void;
  onGenerateMore: () => void;
  onSetExecutionMode: (mode: 'sequential' | 'parallel') => void;
  onSetMaxConcurrent?: (max: number) => void;
  onViewDetails: (task: QATask) => void;
  onRetryFailed?: () => void;
  // Extensive QA options
  extensiveOptions?: ExtensiveQAOptions;
  onExtensiveOptionsChange?: (options: ExtensiveQAOptions) => void;
  className?: string;
}

export function ExtensiveQAPanel({
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
  onSetMaxConcurrent,
  onViewDetails,
  onRetryFailed,
  // Extensive QA options
  extensiveOptions = DEFAULT_EXTENSIVE_QA_OPTIONS,
  onExtensiveOptionsChange,
  className,
}: ExtensiveQAPanelProps) {
  // UI State
  const [filters, setFilters] = useState<FilterState>({
    status: 'all',
    priority: 'all',
    type: 'all',
    search: '',
  });
  const [viewMode, setViewMode] = useState<ViewMode>('detailed');
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [sortBy, setSortBy] = useState<SortBy>('key');
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set());
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [showFilters, setShowFilters] = useState(true);
  const [showKeyboardHints, setShowKeyboardHints] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showExtensiveOptions, setShowExtensiveOptions] = useState(false);
  const [localMaxConcurrent, setLocalMaxConcurrent] = useState(maxConcurrent);
  const containerRef = useRef<HTMLDivElement>(null);

  // Calculate comprehensive stats
  const stats = useMemo(() => {
    const pending = tasks.filter(t => t.status === 'NOT_DONE').length;
    const passed = tasks.filter(t => t.status === 'PASS').length;
    const failed = tasks.filter(t => t.status === 'FAILED').length;
    const inProgress = tasks.filter(t => t.status === 'IN_PROGRESS').length;
    const manual = tasks.filter(t => t.type === 'MANUAL').length;
    const automated = tasks.filter(t => t.type === 'AUTOMATED').length;
    const critical = tasks.filter(t => t.priority === 'CRITICAL').length;
    const high = tasks.filter(t => t.priority === 'HIGH').length;
    const medium = tasks.filter(t => t.priority === 'MEDIUM').length;
    const low = tasks.filter(t => t.priority === 'LOW').length;
    const total = tasks.length;
    const executed = passed + failed;
    const passRate = executed > 0 ? (passed / executed) * 100 : 0;
    const coverageRate = total > 0 ? (executed / total) * 100 : 0;

    // Calculate average execution time from tasks with history
    let totalExecutionTime = 0;
    let executionCount = 0;
    tasks.forEach(t => {
      const history = parseExecutionHistory(t.executionHistory);
      if (history.length > 0) {
        const lastRun = history[history.length - 1];
        totalExecutionTime += lastRun.executionTime;
        executionCount++;
      }
    });
    const avgExecutionTime = executionCount > 0 ? totalExecutionTime / executionCount : 0;

    return {
      pending,
      passed,
      failed,
      inProgress,
      manual,
      automated,
      critical,
      high,
      medium,
      low,
      total,
      executed,
      passRate,
      coverageRate,
      avgExecutionTime,
    };
  }, [tasks]);

  // Filter tasks
  const filteredTasks = useMemo(() => {
    return tasks.filter(task => {
      // Status filter
      if (filters.status !== 'all' && task.status !== filters.status) return false;
      // Priority filter
      if (filters.priority !== 'all' && task.priority !== filters.priority) return false;
      // Type filter
      if (filters.type !== 'all' && task.type !== filters.type) return false;
      // Search filter
      if (filters.search) {
        const search = filters.search.toLowerCase();
        const matchesKey = task.key.toLowerCase().includes(search);
        const matchesTitle = task.title.toLowerCase().includes(search);
        const matchesScenario = task.scenario?.toLowerCase().includes(search);
        if (!matchesKey && !matchesTitle && !matchesScenario) return false;
      }
      return true;
    });
  }, [tasks, filters]);

  // Sort tasks
  const sortedTasks = useMemo(() => {
    const sorted = [...filteredTasks];
    sorted.sort((a, b) => {
      let comparison = 0;
      switch (sortBy) {
        case 'key':
          comparison = a.sequence - b.sequence;
          break;
        case 'priority': {
          const priorityOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
          comparison = priorityOrder[a.priority] - priorityOrder[b.priority];
          break;
        }
        case 'status': {
          const statusOrder = { IN_PROGRESS: 0, NOT_DONE: 1, FAILED: 2, PASS: 3 };
          comparison = statusOrder[a.status] - statusOrder[b.status];
          break;
        }
        case 'lastExecuted': {
          const aTime = a.lastExecutedAt ? new Date(a.lastExecutedAt).getTime() : 0;
          const bTime = b.lastExecutedAt ? new Date(b.lastExecutedAt).getTime() : 0;
          comparison = bTime - aTime;
          break;
        }
      }
      return sortOrder === 'asc' ? comparison : -comparison;
    });
    return sorted;
  }, [filteredTasks, sortBy, sortOrder]);

  // Group tasks
  const groupedTasks = useMemo(() => {
    if (groupBy === 'none') {
      return { '': sortedTasks };
    }

    const groups: Record<string, QATask[]> = {};
    sortedTasks.forEach(task => {
      let key: string;
      switch (groupBy) {
        case 'priority':
          key = task.priority;
          break;
        case 'type':
          key = task.type;
          break;
        case 'status':
          key = task.status;
          break;
        default:
          key = '';
      }
      if (!groups[key]) groups[key] = [];
      groups[key].push(task);
    });

    // Sort groups
    const sortedGroups: Record<string, QATask[]> = {};
    const groupOrder = groupBy === 'priority'
      ? ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
      : groupBy === 'status'
      ? ['IN_PROGRESS', 'NOT_DONE', 'FAILED', 'PASS']
      : groupBy === 'type'
      ? ['AUTOMATED', 'MANUAL']
      : Object.keys(groups);

    groupOrder.forEach(key => {
      if (groups[key]) {
        sortedGroups[key] = groups[key];
      }
    });

    return sortedGroups;
  }, [sortedTasks, groupBy]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Cmd/Ctrl + Enter: Execute
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

      // Escape: Abort or clear selection
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

      // R: Retry failed
      if (e.key === 'r' && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        if (!isExecuting && onRetryFailed) {
          onRetryFailed();
        }
      }

      // F: Toggle filters
      if (e.key === 'f' && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        setShowFilters(prev => !prev);
      }

      // O: Toggle extensive options
      if (e.key === 'o' && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        setShowExtensiveOptions(prev => !prev);
      }

      // 1-4: Quick status filters
      if (!e.metaKey && !e.ctrlKey && !e.shiftKey) {
        if (e.key === '1') setFilters(f => ({ ...f, status: 'all' }));
        if (e.key === '2') setFilters(f => ({ ...f, status: 'NOT_DONE' }));
        if (e.key === '3') setFilters(f => ({ ...f, status: 'PASS' }));
        if (e.key === '4') setFilters(f => ({ ...f, status: 'FAILED' }));
      }

      // Ctrl/Cmd + A: Select all
      if (e.key === 'a' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setSelectedTasks(new Set(filteredTasks.map(t => t.id)));
      }

      // ?: Toggle keyboard hints
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setShowKeyboardHints(prev => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExecuting, isGenerating, selectedTasks, filteredTasks, executionMode, onExecuteAll, onExecuteSelected, onAbort, onSetExecutionMode, onGenerateMore, onRetryFailed]);

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

  // Toggle task expansion
  const toggleTaskExpansion = useCallback((taskId: string) => {
    setExpandedTasks(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }, []);

  // Expand/collapse all
  const expandAll = useCallback(() => {
    setExpandedTasks(new Set(filteredTasks.map(t => t.id)));
  }, [filteredTasks]);

  const collapseAll = useCallback(() => {
    setExpandedTasks(new Set());
  }, []);

  // Select all in filtered list
  const selectAll = useCallback(() => {
    setSelectedTasks(new Set(filteredTasks.map(t => t.id)));
  }, [filteredTasks]);

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

  // Get failed task IDs
  const failedTaskIds = useMemo(() => {
    return tasks.filter(t => t.status === 'FAILED').map(t => t.id);
  }, [tasks]);

  // Handle retry failed
  const handleRetryFailed = useCallback(() => {
    if (failedTaskIds.length > 0) {
      onExecuteSelected(failedTaskIds);
    }
  }, [failedTaskIds, onExecuteSelected]);

  // Apply max concurrent change
  const handleMaxConcurrentChange = useCallback((value: number) => {
    setLocalMaxConcurrent(value);
    onSetMaxConcurrent?.(value);
  }, [onSetMaxConcurrent]);

  return (
    <div ref={containerRef} className={cn('flex flex-col h-full bg-zinc-950', className)}>
      {/* Header with stats dashboard */}
      <div className="border-b border-zinc-800">
        {/* Stats dashboard */}
        <div className="px-6 py-4 bg-zinc-900/50">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <FlaskConical className="w-5 h-5 text-blue-400" />
              <h2 className="text-lg font-semibold text-white">Extensive QA</h2>
            </div>
            <div className="flex items-center gap-2">
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
              <button
                onClick={() => setShowSettings(!showSettings)}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  showSettings ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
                )}
                title="Quick Settings"
              >
                <Settings className="w-4 h-4" />
              </button>
              <button
                onClick={() => setShowExtensiveOptions(!showExtensiveOptions)}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  showExtensiveOptions ? 'bg-blue-600 text-white' : 'text-zinc-500 hover:text-white'
                )}
                title="Extensive Options"
              >
                <SlidersHorizontal className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Stats cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Pass Rate */}
            <div className="p-3 bg-zinc-800/50 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-zinc-400 mb-1">Pass Rate</div>
                  <div className={cn(
                    'text-2xl font-bold',
                    stats.passRate >= 80 ? 'text-green-400' : stats.passRate >= 50 ? 'text-yellow-400' : 'text-red-400'
                  )}>
                    {stats.passRate.toFixed(0)}%
                  </div>
                </div>
                <MiniDonutChart
                  passed={stats.passed}
                  failed={stats.failed}
                  pending={stats.pending}
                  size={48}
                />
              </div>
              <div className="flex items-center gap-2 mt-2 text-xs">
                <span className="text-green-400">{stats.passed} passed</span>
                <span className="text-zinc-600">|</span>
                <span className="text-red-400">{stats.failed} failed</span>
              </div>
            </div>

            {/* Coverage */}
            <div className="p-3 bg-zinc-800/50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                <Target className="w-3 h-3 text-zinc-400" />
                <span className="text-xs text-zinc-400">Coverage</span>
              </div>
              <div className="text-2xl font-bold text-white">{stats.coverageRate.toFixed(0)}%</div>
              <div className="flex items-center gap-2 mt-2 text-xs">
                <span className="text-white">{stats.executed} executed</span>
                <span className="text-zinc-600">|</span>
                <span className="text-zinc-400">{stats.pending} pending</span>
              </div>
            </div>

            {/* Task Types */}
            <div className="p-3 bg-zinc-800/50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                <FileText className="w-3 h-3 text-zinc-400" />
                <span className="text-xs text-zinc-400">Task Types</span>
              </div>
              <div className="text-2xl font-bold text-white">{stats.total}</div>
              <div className="flex items-center gap-2 mt-2 text-xs">
                <span className="text-blue-400">{stats.automated} auto</span>
                <span className="text-zinc-600">|</span>
                <span className="text-yellow-400">{stats.manual} manual</span>
              </div>
            </div>

            {/* Priority Breakdown */}
            <div className="p-3 bg-zinc-800/50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle className="w-3 h-3 text-zinc-400" />
                <span className="text-xs text-zinc-400">Priority</span>
              </div>
              <div className="flex items-center gap-1 mt-2">
                {stats.critical > 0 && (
                  <span className="px-1.5 py-0.5 text-xs rounded bg-red-900/50 text-red-400">
                    {stats.critical} critical
                  </span>
                )}
                {stats.high > 0 && (
                  <span className="px-1.5 py-0.5 text-xs rounded bg-orange-900/50 text-orange-400">
                    {stats.high} high
                  </span>
                )}
                {stats.medium > 0 && (
                  <span className="px-1.5 py-0.5 text-xs rounded bg-yellow-900/50 text-yellow-400">
                    {stats.medium} med
                  </span>
                )}
                {stats.low > 0 && (
                  <span className="px-1.5 py-0.5 text-xs rounded bg-zinc-700 text-zinc-400">
                    {stats.low} low
                  </span>
                )}
              </div>
              {stats.avgExecutionTime > 0 && (
                <div className="flex items-center gap-1 mt-2 text-xs text-zinc-500">
                  <Clock className="w-3 h-3" />
                  <span>Avg: {stats.avgExecutionTime.toFixed(1)}s</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Settings panel */}
        {showSettings && (
          <div className="px-6 py-3 border-t border-zinc-800 bg-zinc-900/30">
            <div className="flex items-center gap-6 flex-wrap">
              {/* Execution mode */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-400">Mode:</span>
                <select
                  value={executionMode}
                  onChange={(e) => onSetExecutionMode(e.target.value as 'sequential' | 'parallel')}
                  disabled={isExecuting}
                  className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white disabled:opacity-50"
                >
                  <option value="sequential">Sequential</option>
                  <option value="parallel">Parallel</option>
                </select>
              </div>

              {/* Max concurrent (for parallel mode) */}
              {executionMode === 'parallel' && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-zinc-400">Concurrent:</span>
                  <input
                    type="number"
                    value={localMaxConcurrent}
                    onChange={(e) => handleMaxConcurrentChange(parseInt(e.target.value) || 5)}
                    min={1}
                    max={20}
                    disabled={isExecuting}
                    className="w-16 px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white disabled:opacity-50"
                  />
                </div>
              )}

              {/* View mode */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-400">View:</span>
                <div className="flex items-center border border-zinc-700 rounded overflow-hidden">
                  <button
                    onClick={() => setViewMode('detailed')}
                    className={cn(
                      'p-1.5 transition-colors',
                      viewMode === 'detailed' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
                    )}
                    title="Detailed view"
                  >
                    <FileText className="w-3 h-3" />
                  </button>
                  <button
                    onClick={() => setViewMode('compact')}
                    className={cn(
                      'p-1.5 transition-colors',
                      viewMode === 'compact' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
                    )}
                    title="Compact view"
                  >
                    <List className="w-3 h-3" />
                  </button>
                  <button
                    onClick={() => setViewMode('table')}
                    className={cn(
                      'p-1.5 transition-colors',
                      viewMode === 'table' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-white'
                    )}
                    title="Table view"
                  >
                    <LayoutGrid className="w-3 h-3" />
                  </button>
                </div>
              </div>

              {/* Group by */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-400">Group:</span>
                <select
                  value={groupBy}
                  onChange={(e) => setGroupBy(e.target.value as GroupBy)}
                  className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white"
                >
                  <option value="none">None</option>
                  <option value="priority">Priority</option>
                  <option value="type">Type</option>
                  <option value="status">Status</option>
                </select>
              </div>

              {/* Sort by */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-400">Sort:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as SortBy)}
                  className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white"
                >
                  <option value="key">Key</option>
                  <option value="priority">Priority</option>
                  <option value="status">Status</option>
                  <option value="lastExecuted">Last Executed</option>
                </select>
                <button
                  onClick={() => setSortOrder(o => o === 'asc' ? 'desc' : 'asc')}
                  className="p-1 text-zinc-400 hover:text-white transition-colors"
                  title={`Sort ${sortOrder === 'asc' ? 'descending' : 'ascending'}`}
                >
                  <ArrowUpDown className="w-3 h-3" />
                </button>
              </div>

              {/* Extensive Options Summary */}
              <div className="flex items-center gap-2 border-l border-zinc-700 pl-4">
                <span className="text-xs text-zinc-400">Profile:</span>
                <span className={cn(
                  'px-2 py-0.5 text-xs rounded font-medium',
                  extensiveOptions.executionProfile === 'smoke' && 'bg-yellow-900/50 text-yellow-400',
                  extensiveOptions.executionProfile === 'critical-path' && 'bg-orange-900/50 text-orange-400',
                  extensiveOptions.executionProfile === 'regression' && 'bg-blue-900/50 text-blue-400',
                  extensiveOptions.executionProfile === 'full-suite' && 'bg-green-900/50 text-green-400',
                  extensiveOptions.executionProfile === 'custom' && 'bg-purple-900/50 text-purple-400'
                )}>
                  {extensiveOptions.executionProfile === 'smoke' && 'Smoke'}
                  {extensiveOptions.executionProfile === 'critical-path' && 'Critical Path'}
                  {extensiveOptions.executionProfile === 'regression' && 'Regression'}
                  {extensiveOptions.executionProfile === 'full-suite' && 'Full Suite'}
                  {extensiveOptions.executionProfile === 'custom' && (extensiveOptions.customProfileName || 'Custom')}
                </span>
                <button
                  onClick={() => setShowExtensiveOptions(true)}
                  className="text-xs text-blue-400 hover:text-blue-300 underline"
                >
                  Configure
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Keyboard hints */}
        {showKeyboardHints && (
          <div className="px-6 py-2 border-t border-zinc-800 bg-zinc-900/30">
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
                <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">R</kbd>
                <span>Retry Failed</span>
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">F</kbd>
                <span>Toggle Filters</span>
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">1-4</kbd>
                <span>Status Filters</span>
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">⌘A</kbd>
                <span>Select All</span>
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1 py-0.5 bg-zinc-800 rounded text-zinc-400">O</kbd>
                <span>Extensive Options</span>
              </span>
            </div>
          </div>
        )}

        {/* Extensive Options Panel - Full featured options for comprehensive testing */}
        {showExtensiveOptions && (
          <div className="border-t border-zinc-800 bg-zinc-900/50 max-h-[60vh] overflow-y-auto">
            <div className="p-4">
              <ExtensiveQAOptionsPanel
                options={extensiveOptions}
                onOptionsChange={onExtensiveOptionsChange || (() => {})}
                isExecuting={isExecuting}
              />
            </div>
          </div>
        )}

        {/* Controls row */}
        <div className="px-6 py-3 border-t border-zinc-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {/* Filter toggle */}
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors',
                  showFilters ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:text-white'
                )}
              >
                <SlidersHorizontal className="w-3 h-3" />
                Filters
              </button>

              {/* Expand/Collapse all */}
              <button
                onClick={expandAll}
                className="p-1.5 text-zinc-400 hover:text-white transition-colors"
                title="Expand all"
              >
                <Maximize2 className="w-3 h-3" />
              </button>
              <button
                onClick={collapseAll}
                className="p-1.5 text-zinc-400 hover:text-white transition-colors"
                title="Collapse all"
              >
                <Minimize2 className="w-3 h-3" />
              </button>

              {/* Divider */}
              <div className="w-px h-4 bg-zinc-700 mx-1" />

              {/* Select All / Deselect All buttons */}
              <button
                onClick={selectAll}
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors',
                  selectedTasks.size === filteredTasks.length && filteredTasks.length > 0
                    ? 'bg-blue-600 text-white'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-700'
                )}
                title="Select all visible tasks (⌘A)"
              >
                <CheckSquare className="w-3 h-3" />
                Select All
              </button>
              <button
                onClick={clearSelection}
                disabled={selectedTasks.size === 0}
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors',
                  selectedTasks.size > 0
                    ? 'text-zinc-400 hover:text-white hover:bg-zinc-700'
                    : 'text-zinc-600 cursor-not-allowed'
                )}
                title="Deselect all tasks"
              >
                <SquareIcon className="w-3 h-3" />
                Deselect
              </button>

              {/* Selection info */}
              {selectedTasks.size > 0 && (
                <span className="text-xs text-blue-400 ml-1">
                  {selectedTasks.size} of {filteredTasks.length} selected
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* Retry failed button */}
              {stats.failed > 0 && !isExecuting && (
                <button
                  onClick={handleRetryFailed}
                  className="flex items-center gap-1 px-2 py-1 text-xs bg-orange-600 hover:bg-orange-700 text-white rounded"
                >
                  <RefreshCw className="w-3 h-3" />
                  Retry {stats.failed} Failed
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
                <div className="relative group">
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
                    {selectedTasks.size > 0 ? `Run ${selectedTasks.size} Selected` : `Execute All (${executableCount})`}
                  </button>
                  {/* Tooltip explaining why button is disabled */}
                  {executableCount === 0 && (
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg shadow-lg text-xs text-zinc-300 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                      <div className="flex items-center gap-2">
                        <Info className="w-3 h-3 text-yellow-400" />
                        <span>
                          {stats.pending === 0
                            ? 'All tasks have been executed'
                            : stats.automated === 0
                            ? 'No automated tasks available'
                            : selectedTasks.size > 0
                            ? 'Selected tasks are not pending or not automated'
                            : 'No pending automated tasks to execute'}
                        </span>
                      </div>
                      <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-zinc-800" />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Filters panel */}
        {showFilters && (
          <div className="px-6 py-3 border-t border-zinc-800 bg-zinc-900/30">
            <div className="flex items-center gap-4">
              {/* Search */}
              <div className="relative flex-1 max-w-xs">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input
                  type="text"
                  value={filters.search}
                  onChange={(e) => setFilters(f => ({ ...f, search: e.target.value }))}
                  placeholder="Search tasks..."
                  className="w-full pl-8 pr-3 py-1.5 text-sm bg-zinc-800 border border-zinc-700 rounded text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-600"
                />
              </div>

              {/* Status filter */}
              <div className="flex items-center gap-1">
                <span className="text-xs text-zinc-500 mr-1">Status:</span>
                <FilterChip
                  active={filters.status === 'all'}
                  onClick={() => setFilters(f => ({ ...f, status: 'all' }))}
                  label="All"
                />
                <FilterChip
                  active={filters.status === 'NOT_DONE'}
                  onClick={() => setFilters(f => ({ ...f, status: 'NOT_DONE' }))}
                  label="Pending"
                  color="text-zinc-400"
                />
                <FilterChip
                  active={filters.status === 'PASS'}
                  onClick={() => setFilters(f => ({ ...f, status: 'PASS' }))}
                  label="Passed"
                  color="text-green-400"
                />
                <FilterChip
                  active={filters.status === 'FAILED'}
                  onClick={() => setFilters(f => ({ ...f, status: 'FAILED' }))}
                  label="Failed"
                  color="text-red-400"
                />
              </div>

              {/* Priority filter */}
              <div className="flex items-center gap-1">
                <span className="text-xs text-zinc-500 mr-1">Priority:</span>
                <select
                  value={filters.priority}
                  onChange={(e) => setFilters(f => ({ ...f, priority: e.target.value as QAPriority | 'all' }))}
                  className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white"
                >
                  <option value="all">All</option>
                  <option value="CRITICAL">Critical</option>
                  <option value="HIGH">High</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="LOW">Low</option>
                </select>
              </div>

              {/* Type filter */}
              <div className="flex items-center gap-1">
                <span className="text-xs text-zinc-500 mr-1">Type:</span>
                <select
                  value={filters.type}
                  onChange={(e) => setFilters(f => ({ ...f, type: e.target.value as QATaskType | 'all' }))}
                  className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white"
                >
                  <option value="all">All</option>
                  <option value="AUTOMATED">Automated</option>
                  <option value="MANUAL">Manual</option>
                </select>
              </div>

              {/* Clear filters */}
              {(filters.status !== 'all' || filters.priority !== 'all' || filters.type !== 'all' || filters.search) && (
                <button
                  onClick={() => setFilters({ status: 'all', priority: 'all', type: 'all', search: '' })}
                  className="text-xs text-zinc-500 hover:text-white"
                >
                  Clear filters
                </button>
              )}
            </div>
          </div>
        )}

        {/* Progress tracker */}
        {(isExecuting || taskResults.length > 0) && (
          <div className="px-6 py-3 border-t border-zinc-800">
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
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto qa-scrollbar">
        {filteredTasks.length === 0 ? (
          <EmptyState
            hasFilters={filters.status !== 'all' || filters.priority !== 'all' || filters.type !== 'all' || !!filters.search}
            totalTasks={stats.total}
            isGenerating={isGenerating}
            onGenerateMore={onGenerateMore}
            onClearFilters={() => setFilters({ status: 'all', priority: 'all', type: 'all', search: '' })}
          />
        ) : (
          <div className="p-6">
            {Object.entries(groupedTasks).map(([group, groupTasks]) => (
              <div key={group || 'all'} className={group ? 'mb-6' : ''}>
                {/* Group header */}
                {group && (
                  <div className="flex items-center gap-2 mb-3 pb-2 border-b border-zinc-800">
                    <GroupIcon groupBy={groupBy} value={group} />
                    <span className="text-sm font-medium text-white capitalize">{group.toLowerCase().replace('_', ' ')}</span>
                    <span className="text-xs text-zinc-500">({groupTasks.length})</span>
                  </div>
                )}

                {/* Tasks */}
                <div className={cn(
                  viewMode === 'table' ? 'space-y-0' : 'space-y-3'
                )}>
                  {viewMode === 'table' && (
                    <TaskTableHeader />
                  )}
                  {groupTasks.map((task) => (
                    viewMode === 'detailed' ? (
                      <ExtensiveTaskCard
                        key={task.id}
                        task={task}
                        isSelected={selectedTasks.has(task.id)}
                        isExpanded={expandedTasks.has(task.id)}
                        isExecuting={currentTaskKey === task.key}
                        onSelect={() => toggleTaskSelection(task.id)}
                        onToggleExpand={() => toggleTaskExpansion(task.id)}
                        onExecute={() => onExecuteSingle(task.id)}
                        onMarkManual={(status, result) => onMarkManual(task.id, status, result)}
                        onCreateBug={() => onCreateBug(task.id)}
                        onViewDetails={() => onViewDetails(task)}
                      />
                    ) : viewMode === 'compact' ? (
                      <CompactTaskRow
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
                    ) : (
                      <TaskTableRow
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
                    )
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Filter chip component
function FilterChip({
  active,
  onClick,
  label,
  color,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-2 py-1 rounded text-xs transition-colors',
        active
          ? 'bg-zinc-700 text-white'
          : 'text-zinc-500 hover:text-white hover:bg-zinc-800'
      )}
    >
      <span className={color}>{label}</span>
    </button>
  );
}

// Group icon component
function GroupIcon({ groupBy, value }: { groupBy: GroupBy; value: string }) {
  switch (groupBy) {
    case 'priority':
      const priorityColors: Record<string, string> = {
        CRITICAL: 'text-red-400',
        HIGH: 'text-orange-400',
        MEDIUM: 'text-yellow-400',
        LOW: 'text-zinc-400',
      };
      return <AlertTriangle className={cn('w-4 h-4', priorityColors[value] || 'text-zinc-400')} />;
    case 'type':
      return value === 'AUTOMATED'
        ? <Zap className="w-4 h-4 text-blue-400" />
        : <FileText className="w-4 h-4 text-yellow-400" />;
    case 'status':
      if (value === 'PASS') return <CheckCircle2 className="w-4 h-4 text-green-400" />;
      if (value === 'FAILED') return <XCircle className="w-4 h-4 text-red-400" />;
      if (value === 'IN_PROGRESS') return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
      return <Circle className="w-4 h-4 text-zinc-400" />;
    default:
      return null;
  }
}

// Empty state component
function EmptyState({
  hasFilters,
  totalTasks,
  isGenerating,
  onGenerateMore,
  onClearFilters,
}: {
  hasFilters: boolean;
  totalTasks: number;
  isGenerating: boolean;
  onGenerateMore: () => void;
  onClearFilters: () => void;
}) {
  if (totalTasks === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center py-12">
        <div className="w-16 h-16 mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
          <FlaskConical className="w-8 h-8 text-zinc-500" />
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

  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-12">
      <div className="w-16 h-16 mb-4 rounded-full bg-zinc-800 flex items-center justify-center">
        <Search className="w-8 h-8 text-zinc-500" />
      </div>
      <h3 className="text-lg font-medium text-zinc-300 mb-2">No tasks match filters</h3>
      <p className="text-zinc-500 mb-4">Try adjusting your filters to see more tasks.</p>
      <button
        onClick={onClearFilters}
        className="flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg text-sm"
      >
        <RotateCcw className="w-4 h-4" />
        Clear filters
      </button>
    </div>
  );
}

// Extensive task card (detailed view)
function ExtensiveTaskCard({
  task,
  isSelected,
  isExpanded,
  isExecuting,
  onSelect,
  onToggleExpand,
  onExecute,
  onMarkManual,
  onCreateBug,
  onViewDetails,
}: {
  task: QATask;
  isSelected: boolean;
  isExpanded: boolean;
  isExecuting: boolean;
  onSelect: () => void;
  onToggleExpand: () => void;
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

  const history = parseExecutionHistory(task.executionHistory);

  const statusColors: Record<QATaskStatus, string> = {
    NOT_DONE: 'bg-zinc-600',
    IN_PROGRESS: 'bg-blue-600',
    PASS: 'bg-green-600',
    FAILED: 'bg-red-600',
  };

  const priorityColors: Record<string, string> = {
    LOW: 'text-zinc-400 bg-zinc-800',
    MEDIUM: 'text-yellow-400 bg-yellow-900/30',
    HIGH: 'text-orange-400 bg-orange-900/30',
    CRITICAL: 'text-red-400 bg-red-900/30',
  };

  return (
    <div
      className={cn(
        'rounded-lg border transition-all',
        isExecuting
          ? 'border-blue-500 ring-2 ring-blue-500/30 bg-zinc-800'
          : isSelected
          ? 'border-blue-500 bg-zinc-800'
          : 'border-zinc-700 bg-zinc-800/50 hover:bg-zinc-800'
      )}
    >
      {/* Header */}
      <div className="p-4">
        <div className="flex items-start gap-3">
          {/* Selection checkbox */}
          <button
            onClick={onSelect}
            className={cn(
              'w-5 h-5 rounded border flex items-center justify-center shrink-0 mt-0.5 transition-colors',
              isSelected
                ? 'bg-blue-600 border-blue-600'
                : 'border-zinc-600 hover:border-zinc-500'
            )}
          >
            {isSelected && <CheckCircle2 className="w-3 h-3 text-white" />}
          </button>

          {/* Expand/collapse button */}
          <button
            onClick={onToggleExpand}
            className="text-zinc-400 hover:text-white transition-colors mt-0.5"
          >
            {isExpanded ? (
              <ChevronDown className="w-5 h-5" />
            ) : (
              <ChevronRight className="w-5 h-5" />
            )}
          </button>

          {/* Main content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
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

              {/* Priority */}
              <span className={cn('text-xs px-1.5 py-0.5 rounded', priorityColors[task.priority])}>
                {task.priority}
              </span>

              {/* Type badge */}
              {isManual ? (
                <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1.5 rounded flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  Manual
                </span>
              ) : (
                <span className="text-xs bg-blue-900/50 text-blue-400 px-1.5 rounded flex items-center gap-1">
                  <Zap className="w-3 h-3" />
                  Auto
                </span>
              )}

              {/* Bug indicator */}
              {task.bugIssueId && (
                <span className="text-xs bg-red-900/50 text-red-400 px-1.5 rounded flex items-center gap-1">
                  <Bug className="w-3 h-3" />
                  Bug created
                </span>
              )}

              {/* Last executed */}
              {task.lastExecutedAt && (
                <span className="text-xs text-zinc-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {new Date(task.lastExecutedAt).toLocaleDateString()}
                </span>
              )}
            </div>

            {/* Title */}
            <h3 className="text-sm font-medium text-zinc-200">{task.title}</h3>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 shrink-0">
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
                Bug
              </button>
            )}
            <button
              onClick={onViewDetails}
              className="p-1.5 text-zinc-400 hover:text-white transition-colors"
              title="View full details"
            >
              <Eye className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Manual input */}
        {showManualInput && (
          <div className="mt-3 pt-3 border-t border-zinc-700 ml-10">
            <textarea
              value={manualResult}
              onChange={(e) => setManualResult(e.target.value)}
              placeholder="Enter actual result..."
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded text-sm text-white resize-none focus:outline-none focus:border-zinc-600"
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
              <button
                onClick={() => setShowManualInput(false)}
                className="px-3 py-1 text-xs bg-zinc-700 hover:bg-zinc-600 text-white rounded"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="border-t border-zinc-700 p-4 space-y-4 bg-zinc-900/50">
          {/* Scenario */}
          <div>
            <h4 className="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wide flex items-center gap-1">
              <FileText className="w-3 h-3" />
              Test Scenario
            </h4>
            <pre className="p-3 bg-zinc-800 rounded text-sm text-zinc-300 whitespace-pre-wrap font-mono">
              {task.scenario || 'No scenario defined'}
            </pre>
          </div>

          {/* Expected Result */}
          <div>
            <h4 className="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wide flex items-center gap-1">
              <Target className="w-3 h-3" />
              Expected Result
            </h4>
            <p className="p-3 bg-zinc-800 rounded text-sm text-zinc-300">
              {task.expectedResult || 'No expected result defined'}
            </p>
          </div>

          {/* Actual Result */}
          {task.actualResult && (
            <div>
              <h4 className="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wide flex items-center gap-1">
                {isFailed ? <XCircle className="w-3 h-3 text-red-400" /> : <CheckCircle2 className="w-3 h-3 text-green-400" />}
                Actual Result
              </h4>
              <p className={cn(
                'p-3 rounded text-sm',
                isFailed ? 'bg-red-900/20 text-red-300 border border-red-900/50' : 'bg-green-900/20 text-green-300 border border-green-900/50'
              )}>
                {task.actualResult}
              </p>
            </div>
          )}

          {/* Execution History */}
          {history.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wide flex items-center gap-1">
                <History className="w-3 h-3" />
                Execution History ({history.length} runs)
              </h4>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {history.slice().reverse().map((run, i) => (
                  <div
                    key={run.id || i}
                    className="flex items-center justify-between p-2 bg-zinc-800 rounded text-xs"
                  >
                    <span className="text-zinc-500">
                      {new Date(run.timestamp).toLocaleString()}
                    </span>
                    <span
                      className={cn(
                        'px-2 py-0.5 rounded',
                        run.status === 'PASS'
                          ? 'bg-green-900/50 text-green-400'
                          : 'bg-red-900/50 text-red-400'
                      )}
                    >
                      {run.status}
                    </span>
                    <span className="text-zinc-500">{run.executionTime.toFixed(2)}s</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Compact task row (compact view)
function CompactTaskRow({
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

  const StatusIcon = () => {
    if (isExecuting) return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
    if (task.status === 'PASS') return <CheckCircle2 className="w-4 h-4 text-green-500" />;
    if (task.status === 'FAILED') return <XCircle className="w-4 h-4 text-red-500" />;
    return <Circle className="w-4 h-4 text-zinc-500" />;
  };

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg border transition-all',
        isExecuting
          ? 'border-blue-500 ring-1 ring-blue-500/30 bg-zinc-800'
          : isSelected
          ? 'border-blue-500 bg-zinc-800'
          : 'border-zinc-700 bg-zinc-800/50 hover:bg-zinc-800'
      )}
    >
      {/* Selection */}
      <button
        onClick={onSelect}
        className={cn(
          'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
          isSelected ? 'bg-blue-600 border-blue-600' : 'border-zinc-600 hover:border-zinc-500'
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
          {isManual && <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1 rounded">Manual</span>}
          <span className="text-xs text-zinc-500">{task.priority}</span>
        </div>
        <p className="text-sm text-zinc-200 truncate">{task.title}</p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        {isPending && isAutomated && !isExecuting && (
          <button onClick={onExecute} className="p-1.5 rounded bg-green-600 hover:bg-green-700 text-white">
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
          <button onClick={onCreateBug} className="p-1.5 rounded bg-red-600 hover:bg-red-700 text-white">
            <Bug className="w-3 h-3" />
          </button>
        )}
        <button onClick={onViewDetails} className="p-1.5 text-zinc-400 hover:text-white">
          <Eye className="w-4 h-4" />
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

// Table header
function TaskTableHeader() {
  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-zinc-800 rounded-t-lg border border-zinc-700 text-xs font-medium text-zinc-400">
      <div className="w-5" /> {/* Checkbox column */}
      <div className="w-6" /> {/* Status icon column */}
      <div className="w-20">Key</div>
      <div className="flex-1">Title</div>
      <div className="w-20">Priority</div>
      <div className="w-16">Type</div>
      <div className="w-24">Status</div>
      <div className="w-20">Actions</div>
    </div>
  );
}

// Table row
function TaskTableRow({
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
  const isPending = task.status === 'NOT_DONE';
  const isFailed = task.status === 'FAILED';
  const isManual = task.type === 'MANUAL';
  const isAutomated = task.type === 'AUTOMATED';

  const statusColors: Record<QATaskStatus, string> = {
    NOT_DONE: 'bg-zinc-600 text-white',
    IN_PROGRESS: 'bg-blue-600 text-white',
    PASS: 'bg-green-600 text-white',
    FAILED: 'bg-red-600 text-white',
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
        'flex items-center gap-3 px-3 py-2 border-x border-b border-zinc-700 text-sm',
        isExecuting
          ? 'bg-blue-900/20'
          : isSelected
          ? 'bg-zinc-800'
          : 'bg-zinc-900/50 hover:bg-zinc-800/50'
      )}
    >
      {/* Checkbox */}
      <button
        onClick={onSelect}
        className={cn(
          'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
          isSelected ? 'bg-blue-600 border-blue-600' : 'border-zinc-600 hover:border-zinc-500'
        )}
      >
        {isSelected && <CheckCircle2 className="w-3 h-3 text-white" />}
      </button>

      {/* Status icon */}
      <div className="w-6">
        {isExecuting ? (
          <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
        ) : task.status === 'PASS' ? (
          <CheckCircle2 className="w-4 h-4 text-green-500" />
        ) : task.status === 'FAILED' ? (
          <XCircle className="w-4 h-4 text-red-500" />
        ) : (
          <Circle className="w-4 h-4 text-zinc-500" />
        )}
      </div>

      {/* Key */}
      <div className="w-20 font-mono text-xs text-zinc-400">{task.key}</div>

      {/* Title */}
      <div className="flex-1 truncate text-zinc-200">{task.title}</div>

      {/* Priority */}
      <div className={cn('w-20 text-xs', priorityColors[task.priority])}>{task.priority}</div>

      {/* Type */}
      <div className="w-16 text-xs">
        {isManual ? (
          <span className="text-yellow-400">Manual</span>
        ) : (
          <span className="text-blue-400">Auto</span>
        )}
      </div>

      {/* Status */}
      <div className="w-24">
        <span className={cn('px-2 py-0.5 text-xs rounded', statusColors[task.status])}>
          {task.status}
        </span>
      </div>

      {/* Actions */}
      <div className="w-20 flex items-center gap-1">
        {isPending && isAutomated && !isExecuting && (
          <button onClick={onExecute} className="p-1 rounded bg-green-600 hover:bg-green-700 text-white">
            <Play className="w-3 h-3" />
          </button>
        )}
        {isFailed && !task.bugIssueId && (
          <button onClick={onCreateBug} className="p-1 rounded bg-red-600 hover:bg-red-700 text-white">
            <Bug className="w-3 h-3" />
          </button>
        )}
        <button onClick={onViewDetails} className="p-1 text-zinc-400 hover:text-white">
          <Eye className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

export default ExtensiveQAPanel;
