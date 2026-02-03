'use client';

/**
 * TestProgressTracker - Comprehensive test execution progress tracking UI
 *
 * Features:
 * - Real-time progress bar with percentage
 * - Time tracking (elapsed, estimated remaining, tasks per minute)
 * - Task-by-task timeline with status and timing
 * - Current task indicator with animation
 * - Pass/fail summary that updates in real-time
 * - Collapsible detailed view
 * - Summary donut chart visualization
 * - Filter/search capability for task timeline
 * - Clear/reset results functionality
 * - Execution history summary
 */

import { useState, useMemo, useEffect, useRef } from 'react';
import {
  Clock,
  Timer,
  Zap,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  Loader2,
  Activity,
  TrendingUp,
  Search,
  RotateCcw,
  PieChart,
} from 'lucide-react';
import type { QATaskStatus } from '@/types/qaboard';
import { cn } from '@/lib/utils';

// Task result from execution
export interface TaskResult {
  key: string;
  title?: string;
  status: QATaskStatus;
  executionTime: number; // seconds
}

// Progress tracking display options
export interface ProgressTrackingOptions {
  // Auto-scroll to latest result in timeline (default: true)
  autoScroll?: boolean;
  // Show time statistics panel (elapsed, remaining, avg, speed) (default: true)
  showTimeStats?: boolean;
  // Show execution summary when complete (default: true)
  showExecutionSummary?: boolean;
  // Timeline max height in pixels (default: 200)
  timelineMaxHeight?: number;
  // Compact header mode - minimal header without donut chart (default: false)
  compactHeader?: boolean;
  // Show task titles in timeline items (default: true)
  showTaskTitles?: boolean;
  // Animation for progress bar pulse (default: true when executing)
  animateProgress?: boolean;
  // Show search/filter controls in timeline (default: true)
  showTimelineFilters?: boolean;
}

// Props for the TestProgressTracker component
export interface TestProgressTrackerProps {
  // Execution state
  isExecuting: boolean;
  executionMode: 'sequential' | 'parallel';

  // Progress info
  progress: number; // 0-100
  completedTasks: number;
  totalTasks: number;

  // Current execution state (for sequential mode)
  currentTaskKey: string | null;
  currentTaskTitle: string | null;

  // Parallel mode specific
  tasksInFlight?: number;
  maxConcurrent?: number;

  // Results accumulated during execution
  taskResults: TaskResult[];

  // Optional: error message
  error?: string | null;

  // Execution start time (for timing calculations)
  startTime?: Date | null;

  // Styling
  className?: string;

  // Show expanded view by default
  defaultExpanded?: boolean;

  // Optional: callback to clear/reset results
  onClearResults?: () => void;

  // Show summary chart in header
  showSummaryChart?: boolean;

  // Progress tracking display options
  trackingOptions?: ProgressTrackingOptions;
}

// Format duration in seconds to readable string
function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins < 60) {
    return `${mins}m ${secs}s`;
  }
  const hours = Math.floor(mins / 60);
  const remainingMins = mins % 60;
  return `${hours}h ${remainingMins}m`;
}

// Mini donut chart for pass/fail visualization
function MiniDonutChart({
  passed,
  failed,
  pending,
  size = 40,
  className,
}: {
  passed: number;
  failed: number;
  pending: number;
  size?: number;
  className?: string;
}) {
  const total = passed + failed + pending;
  if (total === 0) return null;

  const strokeWidth = 4;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  // Calculate stroke dasharray for each segment
  const passedPct = passed / total;
  const failedPct = failed / total;
  const pendingPct = pending / total;

  const passedDash = passedPct * circumference;
  const failedDash = failedPct * circumference;
  const pendingDash = pendingPct * circumference;

  // Calculate offsets - segments start where the previous one ends
  const passedOffset = 0;
  const failedOffset = -passedDash;
  const pendingOffset = -(passedDash + failedDash);

  return (
    <div className={cn('relative', className)} style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        className="transform -rotate-90"
      >
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-zinc-700"
        />
        {/* Pending segment */}
        {pending > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeDasharray={`${pendingDash} ${circumference - pendingDash}`}
            strokeDashoffset={pendingOffset}
            className="text-zinc-500 transition-all duration-300"
          />
        )}
        {/* Failed segment */}
        {failed > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeDasharray={`${failedDash} ${circumference - failedDash}`}
            strokeDashoffset={failedOffset}
            className="text-red-500 transition-all duration-300"
          />
        )}
        {/* Passed segment */}
        {passed > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeDasharray={`${passedDash} ${circumference - passedDash}`}
            strokeDashoffset={passedOffset}
            className="text-green-500 transition-all duration-300"
          />
        )}
      </svg>
      {/* Center text showing pass rate */}
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-[9px] font-bold text-white">
          {total > 0 ? Math.round((passed / total) * 100) : 0}%
        </span>
      </div>
    </div>
  );
}

// Filter type for timeline
type TimelineFilter = 'all' | 'passed' | 'failed';

// Task timeline item component
function TaskTimelineItem({
  result,
  index,
  isLatest,
  showTitle = true,
}: {
  result: TaskResult;
  index: number;
  isLatest: boolean;
  showTitle?: boolean;
}) {
  const isPassed = result.status === 'PASS';

  return (
    <div
      className={cn(
        'flex items-center gap-3 py-2 px-3 rounded-lg transition-all',
        isLatest && 'bg-zinc-800/50 ring-1 ring-zinc-700'
      )}
    >
      {/* Status icon */}
      <div
        className={cn(
          'flex items-center justify-center w-6 h-6 rounded-full shrink-0',
          isPassed ? 'bg-green-500/20' : 'bg-red-500/20'
        )}
      >
        {isPassed ? (
          <CheckCircle2 className="w-4 h-4 text-green-400" />
        ) : (
          <XCircle className="w-4 h-4 text-red-400" />
        )}
      </div>

      {/* Task info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-400">#{index + 1}</span>
          <span className="text-sm font-medium text-zinc-200 truncate">
            {result.key}
          </span>
        </div>
        {showTitle && result.title && (
          <p className="text-xs text-zinc-500 truncate mt-0.5">{result.title}</p>
        )}
      </div>

      {/* Execution time */}
      <div className="text-xs text-zinc-500 shrink-0">
        {result.executionTime.toFixed(2)}s
      </div>
    </div>
  );
}

// Default tracking options
const defaultTrackingOptions: Required<ProgressTrackingOptions> = {
  autoScroll: true,
  showTimeStats: true,
  showExecutionSummary: true,
  timelineMaxHeight: 200,
  compactHeader: false,
  showTaskTitles: true,
  animateProgress: true,
  showTimelineFilters: true,
};

// Main TestProgressTracker component
export function TestProgressTracker({
  isExecuting,
  executionMode,
  progress,
  completedTasks,
  totalTasks,
  currentTaskKey,
  currentTaskTitle,
  tasksInFlight = 0,
  maxConcurrent = 5,
  taskResults,
  error,
  startTime,
  className,
  defaultExpanded = false,
  onClearResults,
  showSummaryChart = true,
  trackingOptions,
}: TestProgressTrackerProps) {
  // Merge tracking options with defaults
  const options: Required<ProgressTrackingOptions> = {
    ...defaultTrackingOptions,
    ...trackingOptions,
  };

  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  // Calculate statistics
  const stats = useMemo(() => {
    const passedCount = taskResults.filter(r => r.status === 'PASS').length;
    const failedCount = taskResults.filter(r => r.status === 'FAILED').length;
    const totalExecutionTime = taskResults.reduce((sum, r) => sum + r.executionTime, 0);
    const avgExecutionTime = taskResults.length > 0 ? totalExecutionTime / taskResults.length : 0;

    // Tasks per minute (based on completed tasks and elapsed time)
    const tasksPerMinute = elapsedTime > 0 ? (completedTasks / elapsedTime) * 60 : 0;

    // Estimated remaining time (based on average execution time)
    const remainingTasks = totalTasks - completedTasks;
    const estimatedRemaining = avgExecutionTime * remainingTasks;

    // Pending count (not yet executed)
    const pendingCount = totalTasks - passedCount - failedCount;

    return {
      passedCount,
      failedCount,
      pendingCount,
      totalExecutionTime,
      avgExecutionTime,
      tasksPerMinute,
      estimatedRemaining,
    };
  }, [taskResults, completedTasks, totalTasks, elapsedTime]);

  // Filter timeline results
  const filteredResults = useMemo(() => {
    let results = taskResults;

    // Apply status filter
    if (timelineFilter === 'passed') {
      results = results.filter(r => r.status === 'PASS');
    } else if (timelineFilter === 'failed') {
      results = results.filter(r => r.status === 'FAILED');
    }

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      results = results.filter(r =>
        r.key.toLowerCase().includes(query) ||
        (r.title && r.title.toLowerCase().includes(query))
      );
    }

    return results;
  }, [taskResults, timelineFilter, searchQuery]);

  // Timer for elapsed time
  useEffect(() => {
    if (isExecuting && startTime) {
      // Update elapsed time every 100ms for smooth display
      timerRef.current = setInterval(() => {
        setElapsedTime((Date.now() - startTime.getTime()) / 1000);
      }, 100);

      return () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
        }
      };
    } else if (!isExecuting && timerRef.current) {
      clearInterval(timerRef.current);
    }
  }, [isExecuting, startTime]);

  // Auto-scroll timeline to latest result
  useEffect(() => {
    if (options.autoScroll && timelineRef.current && taskResults.length > 0) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [taskResults.length, options.autoScroll]);

  // Don't render if not executing and no results
  if (!isExecuting && taskResults.length === 0) {
    return null;
  }

  const isParallel = executionMode === 'parallel';

  return (
    <div className={cn('rounded-lg border border-zinc-700 overflow-hidden', className)}>
      {/* Header - Always visible */}
      <div className="bg-zinc-800 px-4 py-3">
        {/* Top row: Progress info */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            {/* Summary donut chart - hidden in compact mode */}
            {!options.compactHeader && showSummaryChart && taskResults.length > 0 && (
              <MiniDonutChart
                passed={stats.passedCount}
                failed={stats.failedCount}
                pending={stats.pendingCount}
                size={36}
              />
            )}

            {/* Execution status indicator */}
            {isExecuting ? (
              <div className="flex items-center gap-2">
                <Loader2 className={cn(
                  'w-4 h-4 animate-spin',
                  isParallel ? 'text-purple-400' : 'text-blue-400'
                )} />
                <span className={cn(
                  'text-sm font-medium',
                  isParallel ? 'text-purple-400' : 'text-blue-400'
                )}>
                  {isParallel ? 'Parallel Execution' : 'Sequential Execution'}
                </span>
              </div>
            ) : error ? (
              <div className="flex items-center gap-2">
                <XCircle className="w-4 h-4 text-red-400" />
                <span className="text-sm font-medium text-red-400">Error</span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-400" />
                <span className="text-sm font-medium text-green-400">Complete</span>
              </div>
            )}
          </div>

          {/* Progress percentage and actions */}
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-white">
              {Math.round(progress)}%
            </span>

            {/* Clear results button - only show when not executing and has results */}
            {!isExecuting && taskResults.length > 0 && onClearResults && (
              <button
                onClick={onClearResults}
                className="text-zinc-500 hover:text-zinc-300 transition-colors p-1"
                title="Clear results"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            )}

            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-zinc-400 hover:text-white transition-colors p-1"
            >
              {isExpanded ? (
                <ChevronUp className="w-5 h-5" />
              ) : (
                <ChevronDown className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-2 bg-zinc-700 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full transition-all duration-300 ease-out',
              isParallel
                ? 'bg-gradient-to-r from-purple-600 to-purple-400'
                : 'bg-gradient-to-r from-blue-600 to-blue-400',
              isExecuting && options.animateProgress && 'animate-pulse'
            )}
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Stats row */}
        <div className="flex items-center justify-between mt-3 text-xs">
          {/* Left: Task counts and current task */}
          <div className="flex items-center gap-4">
            {/* Task counter */}
            <span className="text-zinc-400">
              <span className="text-white font-medium">{completedTasks}</span>
              <span className="mx-1">/</span>
              <span>{totalTasks}</span>
              <span className="ml-1">tasks</span>
            </span>

            {/* Current task or parallel info */}
            {isExecuting && (
              isParallel ? (
                <span className="text-purple-400">
                  <Activity className="w-3 h-3 inline mr-1" />
                  {tasksInFlight} running (max {maxConcurrent})
                </span>
              ) : currentTaskKey && (
                <span className="text-blue-400 truncate max-w-[200px]">
                  Running: <span className="font-mono">{currentTaskKey}</span>
                </span>
              )
            )}
          </div>

          {/* Right: Pass/Fail counts */}
          <div className="flex items-center gap-3">
            <span className="text-green-400">
              <CheckCircle2 className="w-3 h-3 inline mr-1" />
              {stats.passedCount}
            </span>
            <span className="text-red-400">
              <XCircle className="w-3 h-3 inline mr-1" />
              {stats.failedCount}
            </span>
          </div>
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="bg-zinc-900 border-t border-zinc-700">
          {/* Time statistics */}
          {options.showTimeStats && (
          <div className="grid grid-cols-4 gap-4 p-4 border-b border-zinc-800">
            {/* Elapsed time */}
            <div className="text-center">
              <div className="flex items-center justify-center gap-1 text-zinc-400 mb-1">
                <Clock className="w-3 h-3" />
                <span className="text-xs">Elapsed</span>
              </div>
              <div className="text-sm font-mono text-white">
                {formatDuration(elapsedTime)}
              </div>
            </div>

            {/* Estimated remaining */}
            <div className="text-center">
              <div className="flex items-center justify-center gap-1 text-zinc-400 mb-1">
                <Timer className="w-3 h-3" />
                <span className="text-xs">Remaining</span>
              </div>
              <div className="text-sm font-mono text-white">
                {isExecuting && stats.estimatedRemaining > 0
                  ? formatDuration(stats.estimatedRemaining)
                  : '--'}
              </div>
            </div>

            {/* Average time per task */}
            <div className="text-center">
              <div className="flex items-center justify-center gap-1 text-zinc-400 mb-1">
                <TrendingUp className="w-3 h-3" />
                <span className="text-xs">Avg Time</span>
              </div>
              <div className="text-sm font-mono text-white">
                {stats.avgExecutionTime > 0
                  ? `${stats.avgExecutionTime.toFixed(2)}s`
                  : '--'}
              </div>
            </div>

            {/* Speed (tasks per minute) */}
            <div className="text-center">
              <div className="flex items-center justify-center gap-1 text-zinc-400 mb-1">
                <Zap className="w-3 h-3" />
                <span className="text-xs">Speed</span>
              </div>
              <div className="text-sm font-mono text-white">
                {stats.tasksPerMinute > 0
                  ? `${stats.tasksPerMinute.toFixed(1)}/min`
                  : '--'}
              </div>
            </div>
          </div>
          )}

          {/* Execution Summary - shows when not executing and has results */}
          {options.showExecutionSummary && !isExecuting && taskResults.length > 0 && (
            <div className="p-4 border-b border-zinc-800">
              <h4 className="text-xs font-semibold text-zinc-400 mb-3 uppercase tracking-wide flex items-center gap-2">
                <PieChart className="w-3 h-3" />
                Execution Summary
              </h4>
              <div className="grid grid-cols-2 gap-4">
                {/* Pass rate gauge */}
                <div className="flex items-center gap-4 p-3 bg-zinc-800/50 rounded-lg">
                  <MiniDonutChart
                    passed={stats.passedCount}
                    failed={stats.failedCount}
                    pending={0}
                    size={48}
                  />
                  <div>
                    <div className="text-2xl font-bold text-white">
                      {taskResults.length > 0
                        ? Math.round((stats.passedCount / taskResults.length) * 100)
                        : 0}%
                    </div>
                    <div className="text-xs text-zinc-400">Pass Rate</div>
                  </div>
                </div>

                {/* Result breakdown */}
                <div className="p-3 bg-zinc-800/50 rounded-lg">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-green-400 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        Passed
                      </span>
                      <span className="text-sm font-medium text-white">{stats.passedCount}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-red-400 flex items-center gap-1">
                        <XCircle className="w-3 h-3" />
                        Failed
                      </span>
                      <span className="text-sm font-medium text-white">{stats.failedCount}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-zinc-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Total Time
                      </span>
                      <span className="text-sm font-medium text-white">
                        {formatDuration(stats.totalExecutionTime)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Task timeline */}
          {taskResults.length > 0 && (
            <div className="p-4">
              {/* Timeline header with filters */}
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">
                  Task Timeline ({filteredResults.length}/{taskResults.length})
                </h4>

                {options.showTimelineFilters && (
                <div className="flex items-center gap-2">
                  {/* Search input */}
                  <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-500" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search..."
                      className="w-32 pl-7 pr-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-600"
                    />
                  </div>

                  {/* Status filter */}
                  <div className="flex items-center gap-1 bg-zinc-800 rounded p-0.5">
                    <button
                      onClick={() => setTimelineFilter('all')}
                      className={cn(
                        'px-2 py-0.5 text-xs rounded transition-colors',
                        timelineFilter === 'all'
                          ? 'bg-zinc-700 text-white'
                          : 'text-zinc-400 hover:text-white'
                      )}
                    >
                      All
                    </button>
                    <button
                      onClick={() => setTimelineFilter('passed')}
                      className={cn(
                        'px-2 py-0.5 text-xs rounded transition-colors',
                        timelineFilter === 'passed'
                          ? 'bg-green-600 text-white'
                          : 'text-green-400 hover:text-green-300'
                      )}
                    >
                      Pass
                    </button>
                    <button
                      onClick={() => setTimelineFilter('failed')}
                      className={cn(
                        'px-2 py-0.5 text-xs rounded transition-colors',
                        timelineFilter === 'failed'
                          ? 'bg-red-600 text-white'
                          : 'text-red-400 hover:text-red-300'
                      )}
                    >
                      Fail
                    </button>
                  </div>
                </div>
                )}
              </div>

              {/* Timeline list */}
              <div
                ref={timelineRef}
                className="overflow-y-auto space-y-1 pr-2 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent"
                style={{ maxHeight: `${options.timelineMaxHeight}px` }}
              >
                {filteredResults.length === 0 ? (
                  <div className="py-4 text-center text-xs text-zinc-500">
                    No tasks match the current filter
                  </div>
                ) : (
                  filteredResults.map((result, index) => (
                    <TaskTimelineItem
                      key={`${result.key}-${index}`}
                      result={result}
                      index={taskResults.indexOf(result)}
                      isLatest={result === taskResults[taskResults.length - 1]}
                      showTitle={options.showTaskTitles}
                    />
                  ))
                )}
              </div>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="p-4 border-t border-zinc-800">
              <div className="p-3 bg-red-900/20 border border-red-900/50 rounded-lg">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Compact version for inline use
export function TestProgressTrackerCompact({
  isExecuting,
  executionMode,
  progress,
  completedTasks,
  totalTasks,
  taskResults,
  className,
}: Pick<
  TestProgressTrackerProps,
  'isExecuting' | 'executionMode' | 'progress' | 'completedTasks' | 'totalTasks' | 'taskResults' | 'className'
>) {
  const passedCount = taskResults.filter(r => r.status === 'PASS').length;
  const failedCount = taskResults.filter(r => r.status === 'FAILED').length;
  const isParallel = executionMode === 'parallel';

  return (
    <div className={cn('space-y-2', className)}>
      {/* Progress bar with percentage */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 bg-zinc-700 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full transition-all duration-300',
              isParallel ? 'bg-purple-500' : 'bg-blue-500'
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-sm font-medium text-white w-12 text-right">
          {Math.round(progress)}%
        </span>
      </div>

      {/* Stats */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-400">
          {completedTasks}/{totalTasks} tasks
        </span>
        <div className="flex items-center gap-2">
          <span className="text-green-400">{passedCount} passed</span>
          <span className="text-red-400">{failedCount} failed</span>
        </div>
      </div>
    </div>
  );
}

// Export MiniDonutChart for reuse
export { MiniDonutChart };
export type { TimelineFilter };

export default TestProgressTracker;
