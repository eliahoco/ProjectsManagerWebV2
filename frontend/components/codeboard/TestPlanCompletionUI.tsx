'use client';

/**
 * Test Plan Completion UI - CB-839
 * Component for displaying test plan completion status and final results
 *
 * Features:
 * - Completion status banner with pass/fail indicator
 * - Final summary metrics (pass rate, completion rate, coverage)
 * - Large visual pass rate display
 * - Completion actions (mark complete, export results, archive)
 * - Next steps recommendations based on results
 * - Execution timeline summary
 * - Celebratory animation for passing tests
 * - Configurable options panel (CB-850)
 */

import { useState, useMemo, useCallback } from 'react';
import {
  CheckCircle2,
  XCircle,
  Trophy,
  Download,
  Archive,
  RefreshCw,
  ChevronRight,
  Clock,
  Target,
  AlertTriangle,
  PartyPopper,
  FileText,
  TrendingUp,
  TrendingDown,
  Minus,
  Shield,
  Zap,
  Flag,
  ArrowRight,
  Settings2,
  X,
} from 'lucide-react';
import type { QATask, CompletionOptions } from '@/types/qaboard';
import { DEFAULT_COMPLETION_OPTIONS, GAUGE_SIZE_CONFIG } from '@/types/qaboard';
import { cn } from '@/lib/utils';
import { CompletionOptionsPanel } from './CompletionOptionsPanel';

// ==================== Types ====================

export interface TestPlanCompletionUIProps {
  tasks: QATask[];
  passThreshold: number; // 0-1
  isComplete?: boolean;
  completedAt?: string;
  completedBy?: string;
  onMarkComplete?: () => void;
  onExportResults?: (format: 'json' | 'csv' | 'pdf') => void;
  onArchive?: () => void;
  onRerunFailed?: () => void;
  onViewTask?: (task: QATask) => void;
  onCreateBugs?: (taskIds: string[]) => void;
  className?: string;
  // Completion options (CB-850)
  options?: CompletionOptions;
  onOptionsChange?: (options: CompletionOptions) => void;
  showOptionsPanel?: boolean;
}

interface CompletionMetrics {
  totalTasks: number;
  executedTasks: number;
  passedTasks: number;
  failedTasks: number;
  pendingTasks: number;
  manualTasks: number;
  automatedTasks: number;
  completionRate: number;
  passRate: number;
  isPassingThreshold: boolean;
  isFullyExecuted: boolean;
  totalExecutionTime: number;
  avgExecutionTime: number;
}

interface NextStep {
  id: string;
  type: 'action' | 'recommendation' | 'warning';
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

// ==================== Helper Functions ====================

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

function parseExecutionHistory(historyJson?: string): { executionTime: number }[] {
  if (!historyJson) return [];
  try {
    const parsed = JSON.parse(historyJson);
    return parsed.filter((entry: { summary?: boolean }) => !entry.summary);
  } catch {
    return [];
  }
}

// ==================== Sub-components ====================

// Large circular progress gauge for pass rate
function PassRateGauge({
  passRate,
  isPassingThreshold,
  passThreshold,
  size = 200,
}: {
  passRate: number;
  isPassingThreshold: boolean;
  passThreshold: number;
  size?: number;
}) {
  const strokeWidth = 12;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const passRateDash = (passRate / 100) * circumference;

  const getColor = () => {
    if (passRate >= 90) return { stroke: '#22c55e', text: 'text-green-400', bg: 'from-green-500/20' };
    if (passRate >= passThreshold * 100) return { stroke: '#eab308', text: 'text-yellow-400', bg: 'from-yellow-500/20' };
    return { stroke: '#ef4444', text: 'text-red-400', bg: 'from-red-500/20' };
  };

  const colors = getColor();

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      {/* Background glow */}
      <div
        className={cn(
          'absolute inset-0 rounded-full bg-gradient-radial to-transparent opacity-50',
          colors.bg
        )}
      />

      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#3f3f46"
          strokeWidth={strokeWidth}
        />

        {/* Threshold marker */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#ffffff20"
          strokeWidth={strokeWidth}
          strokeDasharray={`2 ${circumference - 2}`}
          strokeDashoffset={-((passThreshold * circumference) - 1)}
        />

        {/* Pass rate arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colors.stroke}
          strokeWidth={strokeWidth}
          strokeDasharray={`${passRateDash} ${circumference - passRateDash}`}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>

      {/* Center content */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn('text-5xl font-bold', colors.text)}>
          {passRate.toFixed(0)}
        </span>
        <span className="text-xl text-zinc-400">%</span>
        <span className="text-sm text-zinc-500 mt-1">Pass Rate</span>
        {isPassingThreshold ? (
          <span className="flex items-center gap-1 text-xs text-green-400 mt-2">
            <CheckCircle2 className="w-3 h-3" />
            Meets threshold
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-red-400 mt-2">
            <XCircle className="w-3 h-3" />
            Below {(passThreshold * 100).toFixed(0)}%
          </span>
        )}
      </div>
    </div>
  );
}

// Metric stat card
function MetricCard({
  label,
  value,
  subvalue,
  icon,
  color,
  trend,
}: {
  label: string;
  value: string | number;
  subvalue?: string;
  icon: React.ReactNode;
  color: string;
  trend?: 'up' | 'down' | 'stable';
}) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-zinc-500';

  return (
    <div className="p-4 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
      <div className="flex items-center justify-between mb-2">
        <span className={cn('opacity-70', color)}>{icon}</span>
        {trend && <TrendIcon className={cn('w-4 h-4', trendColor)} />}
      </div>
      <div className={cn('text-2xl font-bold', color)}>{value}</div>
      <div className="text-xs text-zinc-500">{label}</div>
      {subvalue && <div className="text-xs text-zinc-600 mt-1">{subvalue}</div>}
    </div>
  );
}

// Completion progress bar
function CompletionProgressBar({
  completionRate,
  passedCount,
  failedCount,
  pendingCount,
  showLegend = true,
}: {
  completionRate: number;
  passedCount: number;
  failedCount: number;
  pendingCount: number;
  showLegend?: boolean;
}) {
  const total = passedCount + failedCount + pendingCount;

  return (
    <div className="space-y-3">
      {/* Progress bar */}
      <div className="h-4 bg-zinc-800 rounded-full overflow-hidden flex">
        {passedCount > 0 && (
          <div
            className="h-full bg-green-500 transition-all duration-500"
            style={{ width: `${(passedCount / total) * 100}%` }}
          />
        )}
        {failedCount > 0 && (
          <div
            className="h-full bg-red-500 transition-all duration-500"
            style={{ width: `${(failedCount / total) * 100}%` }}
          />
        )}
        {pendingCount > 0 && (
          <div
            className="h-full bg-zinc-600 transition-all duration-500"
            style={{ width: `${(pendingCount / total) * 100}%` }}
          />
        )}
      </div>

      {/* Legend */}
      {showLegend && (
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full bg-green-500" />
              <span className="text-zinc-300">{passedCount} Passed</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full bg-red-500" />
              <span className="text-zinc-300">{failedCount} Failed</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full bg-zinc-600" />
              <span className="text-zinc-300">{pendingCount} Pending</span>
            </span>
          </div>
          <span className="text-zinc-400">
            {completionRate.toFixed(0)}% Complete
          </span>
        </div>
      )}
    </div>
  );
}

// Next step card
function NextStepCard({ step }: { step: NextStep }) {
  const typeConfig = {
    action: {
      icon: <ArrowRight className="w-4 h-4" />,
      color: 'text-blue-400',
      bgColor: 'bg-blue-900/20',
      borderColor: 'border-blue-800/50',
    },
    recommendation: {
      icon: <Target className="w-4 h-4" />,
      color: 'text-green-400',
      bgColor: 'bg-green-900/20',
      borderColor: 'border-green-800/50',
    },
    warning: {
      icon: <AlertTriangle className="w-4 h-4" />,
      color: 'text-yellow-400',
      bgColor: 'bg-yellow-900/20',
      borderColor: 'border-yellow-800/50',
    },
  };

  const config = typeConfig[step.type];

  return (
    <div className={cn('p-4 rounded-lg border', config.bgColor, config.borderColor)}>
      <div className="flex items-start gap-3">
        <span className={cn('mt-0.5', config.color)}>{config.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200">{step.title}</p>
          <p className="text-xs text-zinc-500 mt-0.5">{step.description}</p>
          {step.action && (
            <button
              onClick={step.action.onClick}
              className={cn(
                'mt-2 text-xs font-medium flex items-center gap-1 transition-colors hover:underline',
                config.color
              )}
            >
              {step.action.label}
              <ChevronRight className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Export dropdown menu
function ExportMenu({
  onExport,
  defaultFormat = 'json',
}: {
  onExport: (format: 'json' | 'csv' | 'pdf') => void;
  defaultFormat?: 'json' | 'csv' | 'pdf';
}) {
  const [isOpen, setIsOpen] = useState(false);

  // Order formats with default first
  const formats: ('json' | 'csv' | 'pdf')[] = ['json', 'csv', 'pdf'];
  const orderedFormats = [defaultFormat, ...formats.filter(f => f !== defaultFormat)];

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg transition-colors"
      >
        <Download className="w-4 h-4" />
        Export Results
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute top-full left-0 mt-1 z-20 w-48 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl overflow-hidden">
            {orderedFormats.map((format) => (
              <button
                key={format}
                onClick={() => { onExport(format); setIsOpen(false); }}
                className={cn(
                  'w-full flex items-center gap-2 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 transition-colors',
                  format === defaultFormat && 'bg-zinc-700/50'
                )}
              >
                <FileText className="w-4 h-4" />
                Export as {format.toUpperCase()}
                {format === defaultFormat && (
                  <span className="text-xs text-zinc-500 ml-auto">(default)</span>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// Failed tests summary
function FailedTestsSummary({
  tasks,
  onViewTask,
  onCreateBugs,
  maxShown = 5,
}: {
  tasks: QATask[];
  onViewTask?: (task: QATask) => void;
  onCreateBugs?: (taskIds: string[]) => void;
  maxShown?: number;
}) {
  const failedTasks = tasks.filter(t => t.status === 'FAILED');

  if (failedTasks.length === 0) return null;

  const tasksWithoutBugs = failedTasks.filter(t => !t.bugIssueId);

  return (
    <div className="p-4 bg-red-900/10 border border-red-900/30 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-red-400 flex items-center gap-2">
          <XCircle className="w-4 h-4" />
          {failedTasks.length} Failed Test{failedTasks.length > 1 ? 's' : ''}
        </h4>
        {onCreateBugs && tasksWithoutBugs.length > 0 && (
          <button
            onClick={() => onCreateBugs(tasksWithoutBugs.map(t => t.id))}
            className="text-xs text-red-400 hover:text-red-300 transition-colors"
          >
            Create bugs for all ({tasksWithoutBugs.length})
          </button>
        )}
      </div>

      <div className="space-y-2 max-h-40 overflow-y-auto">
        {failedTasks.slice(0, maxShown).map(task => (
          <button
            key={task.id}
            onClick={() => onViewTask?.(task)}
            className="w-full flex items-center gap-2 p-2 bg-zinc-900/50 rounded hover:bg-zinc-900 transition-colors text-left"
          >
            <XCircle className="w-3 h-3 text-red-500 shrink-0" />
            <span className="text-xs font-mono text-zinc-500">{task.key}</span>
            <span className="text-sm text-zinc-300 truncate flex-1">{task.title}</span>
            {task.bugIssueId && (
              <span className="text-xs bg-red-900/50 text-red-400 px-1.5 rounded">Bug Created</span>
            )}
          </button>
        ))}
        {failedTasks.length > maxShown && (
          <p className="text-xs text-zinc-500 text-center py-1">
            +{failedTasks.length - maxShown} more failed tests
          </p>
        )}
      </div>
    </div>
  );
}

// ==================== Main Component ====================

export function TestPlanCompletionUI({
  tasks,
  passThreshold,
  isComplete = false,
  completedAt,
  completedBy,
  onMarkComplete,
  onExportResults,
  onArchive,
  onRerunFailed,
  onViewTask,
  onCreateBugs,
  className,
  options: externalOptions,
  onOptionsChange,
  showOptionsPanel: initialShowOptionsPanel = false,
}: TestPlanCompletionUIProps) {
  const [showCelebration, setShowCelebration] = useState(false);
  const [showOptionsPanel, setShowOptionsPanel] = useState(initialShowOptionsPanel);
  const [internalOptions, setInternalOptions] = useState<CompletionOptions>(DEFAULT_COMPLETION_OPTIONS);

  // Use external options if provided, otherwise use internal state
  const options = externalOptions ?? internalOptions;
  const handleOptionsChange = useCallback((newOptions: CompletionOptions) => {
    if (onOptionsChange) {
      onOptionsChange(newOptions);
    } else {
      setInternalOptions(newOptions);
    }
  }, [onOptionsChange]);

  // Get effective pass threshold (use custom if set, otherwise use prop)
  const effectivePassThreshold = options.customPassThreshold !== null
    ? options.customPassThreshold / 100
    : passThreshold;

  // Get gauge size in pixels
  const gaugeSize = GAUGE_SIZE_CONFIG.find(c => c.size === options.gaugeSize)?.pixels ?? 180;

  // Calculate completion metrics
  const metrics = useMemo<CompletionMetrics>(() => {
    const totalTasks = tasks.length;
    const passedTasks = tasks.filter(t => t.status === 'PASS').length;
    const failedTasks = tasks.filter(t => t.status === 'FAILED').length;
    const pendingTasks = tasks.filter(t => t.status === 'NOT_DONE' || t.status === 'IN_PROGRESS').length;
    const executedTasks = passedTasks + failedTasks;
    const manualTasks = tasks.filter(t => t.type === 'MANUAL').length;
    const automatedTasks = tasks.filter(t => t.type === 'AUTOMATED').length;

    const completionRate = totalTasks > 0 ? (executedTasks / totalTasks) * 100 : 0;
    const passRate = executedTasks > 0 ? (passedTasks / executedTasks) * 100 : 0;
    const isPassingThreshold = passRate / 100 >= effectivePassThreshold;
    const isFullyExecuted = pendingTasks === 0;

    // Calculate execution time from history
    let totalExecutionTime = 0;
    tasks.forEach(task => {
      const history = parseExecutionHistory(task.executionHistory);
      if (history.length > 0) {
        totalExecutionTime += history[history.length - 1].executionTime || 0;
      }
    });
    const avgExecutionTime = executedTasks > 0 ? totalExecutionTime / executedTasks : 0;

    return {
      totalTasks,
      executedTasks,
      passedTasks,
      failedTasks,
      pendingTasks,
      manualTasks,
      automatedTasks,
      completionRate,
      passRate,
      isPassingThreshold,
      isFullyExecuted,
      totalExecutionTime,
      avgExecutionTime,
    };
  }, [tasks, effectivePassThreshold]);

  // Generate next steps based on current state
  const nextSteps = useMemo<NextStep[]>(() => {
    if (!options.showNextSteps) return [];

    const steps: NextStep[] = [];
    const allowedTypes = options.nextStepTypes;

    // Pending tests (warning)
    if (metrics.pendingTasks > 0 && allowedTypes.includes('warning')) {
      steps.push({
        id: 'pending',
        type: 'warning',
        title: `${metrics.pendingTasks} tests not yet executed`,
        description: 'Complete all test execution before marking the plan as complete.',
      });
    }

    // Failed tests (action)
    if (metrics.failedTasks > 0 && onRerunFailed && allowedTypes.includes('action') && options.enabledActions.includes('rerun-failed')) {
      steps.push({
        id: 'rerun-failed',
        type: 'action',
        title: `${metrics.failedTasks} failed tests need attention`,
        description: 'Review and re-run failed tests or create bug reports.',
        action: {
          label: 'Re-run Failed Tests',
          onClick: onRerunFailed,
        },
      });
    }

    // Below threshold (warning)
    if (!metrics.isPassingThreshold && metrics.executedTasks > 0 && allowedTypes.includes('warning')) {
      steps.push({
        id: 'below-threshold',
        type: 'warning',
        title: 'Pass rate below threshold',
        description: `Current pass rate (${metrics.passRate.toFixed(0)}%) is below the required ${(effectivePassThreshold * 100).toFixed(0)}%.`,
      });
    }

    // Below warning threshold (warning)
    if (metrics.passRate < options.warningThreshold && metrics.executedTasks > 0 && allowedTypes.includes('warning') && metrics.isPassingThreshold) {
      steps.push({
        id: 'warning-threshold',
        type: 'warning',
        title: 'Pass rate is close to threshold',
        description: `Current pass rate (${metrics.passRate.toFixed(0)}%) is approaching the warning level.`,
      });
    }

    // Ready to complete (recommendation)
    if (metrics.isFullyExecuted && metrics.isPassingThreshold && !isComplete && onMarkComplete && allowedTypes.includes('recommendation') && options.enabledActions.includes('mark-complete')) {
      steps.push({
        id: 'ready-complete',
        type: 'recommendation',
        title: 'Test plan is ready for completion',
        description: 'All tests have been executed and the pass threshold has been met.',
        action: {
          label: 'Mark as Complete',
          onClick: onMarkComplete,
        },
      });
    }

    // Export results (recommendation)
    if (metrics.isFullyExecuted && onExportResults && allowedTypes.includes('recommendation') && options.enabledActions.includes('export')) {
      steps.push({
        id: 'export',
        type: 'recommendation',
        title: 'Export test results',
        description: 'Generate a report of your test execution for documentation.',
      });
    }

    return steps;
  }, [metrics, effectivePassThreshold, isComplete, onMarkComplete, onRerunFailed, onExportResults, options]);

  // Handle marking complete with celebration
  const handleMarkComplete = useCallback(() => {
    if (metrics.isPassingThreshold && options.showCelebrationOnPass && options.celebrationStyle !== 'none') {
      setShowCelebration(true);
      setTimeout(() => setShowCelebration(false), options.celebrationDuration);
    }
    onMarkComplete?.();
  }, [metrics.isPassingThreshold, onMarkComplete, options]);

  // Don't render if no tasks
  if (tasks.length === 0) {
    return null;
  }

  return (
    <div className={cn('relative', className)}>
      {/* Celebration overlay */}
      {showCelebration && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-zinc-900/80 rounded-lg animate-fade-in">
          <div className="text-center">
            <PartyPopper className="w-16 h-16 text-yellow-400 mx-auto mb-4 animate-bounce" />
            <h3 className="text-2xl font-bold text-white mb-2">Test Plan Complete!</h3>
            <p className="text-zinc-400">All tests passed the threshold.</p>
          </div>
        </div>
      )}

      {/* Options Panel Overlay */}
      {showOptionsPanel && (
        <div className="absolute inset-0 z-40 bg-zinc-900/95 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
            <h3 className="text-sm font-medium text-white">Completion Options</h3>
            <button
              onClick={() => setShowOptionsPanel(false)}
              className="p-1 text-zinc-400 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="p-4 overflow-y-auto max-h-[calc(100%-48px)]">
            <CompletionOptionsPanel
              options={options}
              onOptionsChange={handleOptionsChange}
            />
          </div>
        </div>
      )}

      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        {/* Header */}
        <div className={cn(
          'px-6 py-4 border-b border-zinc-800',
          isComplete
            ? 'bg-gradient-to-r from-green-900/30 to-transparent'
            : metrics.isPassingThreshold
            ? 'bg-gradient-to-r from-blue-900/30 to-transparent'
            : 'bg-gradient-to-r from-yellow-900/30 to-transparent'
        )}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {isComplete ? (
                <Trophy className="w-6 h-6 text-green-400" />
              ) : metrics.isPassingThreshold ? (
                <CheckCircle2 className="w-6 h-6 text-blue-400" />
              ) : (
                <Target className="w-6 h-6 text-yellow-400" />
              )}
              <div>
                <h2 className="text-lg font-semibold text-white">
                  {isComplete ? 'Test Plan Completed' : 'Test Plan Completion'}
                </h2>
                {isComplete && completedAt && (
                  <p className="text-sm text-zinc-500">
                    Completed {new Date(completedAt).toLocaleDateString()}{' '}
                    {completedBy && `by ${completedBy}`}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Options toggle button */}
              <button
                onClick={() => setShowOptionsPanel(!showOptionsPanel)}
                className={cn(
                  'p-2 rounded-lg transition-colors',
                  showOptionsPanel
                    ? 'bg-green-600 text-white'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
                )}
                title="Completion Options"
              >
                <Settings2 className="w-4 h-4" />
              </button>

              {/* Status badge */}
              <div className={cn(
                'px-3 py-1 rounded-full text-sm font-medium',
                isComplete
                  ? 'bg-green-900/50 text-green-400'
                  : metrics.isFullyExecuted
                  ? metrics.isPassingThreshold
                    ? 'bg-blue-900/50 text-blue-400'
                    : 'bg-red-900/50 text-red-400'
                  : 'bg-yellow-900/50 text-yellow-400'
              )}>
                {isComplete
                  ? 'Completed'
                  : metrics.isFullyExecuted
                  ? metrics.isPassingThreshold
                    ? 'Passing'
                    : 'Not Passing'
                  : 'In Progress'}
              </div>
            </div>
          </div>
        </div>

        {/* Main content */}
        <div className="p-6 space-y-6">
          {/* Pass rate and metrics row */}
          <div className="flex gap-8">
            {/* Pass rate gauge */}
            {options.showPassRateGauge && (
              <div className="shrink-0">
                <PassRateGauge
                  passRate={metrics.passRate}
                  isPassingThreshold={metrics.isPassingThreshold}
                  passThreshold={effectivePassThreshold}
                  size={gaugeSize}
                />
              </div>
            )}

            {/* Metric cards */}
            {options.showMetricCards && (
              <div className={cn('flex-1 grid gap-4', options.showPassRateGauge ? 'grid-cols-2 lg:grid-cols-4' : 'grid-cols-2 lg:grid-cols-4')}>
                {options.metricsToShow.includes('total') && (
                  <MetricCard
                    label="Total Tests"
                    value={metrics.totalTasks}
                    icon={<FileText className="w-5 h-5" />}
                    color="text-blue-400"
                    trend={options.showTrends ? undefined : undefined}
                  />
                )}
                {options.metricsToShow.includes('passed') && (
                  <MetricCard
                    label="Passed"
                    value={metrics.passedTasks}
                    subvalue={`${metrics.passedTasks} of ${metrics.executedTasks} executed`}
                    icon={<CheckCircle2 className="w-5 h-5" />}
                    color="text-green-400"
                    trend={options.showTrends ? undefined : undefined}
                  />
                )}
                {options.metricsToShow.includes('failed') && (
                  <MetricCard
                    label="Failed"
                    value={metrics.failedTasks}
                    icon={<XCircle className="w-5 h-5" />}
                    color={metrics.failedTasks > 0 ? 'text-red-400' : 'text-zinc-400'}
                    trend={options.showTrends ? undefined : undefined}
                  />
                )}
                {options.metricsToShow.includes('execution-time') && (
                  <MetricCard
                    label="Execution Time"
                    value={formatDuration(metrics.totalExecutionTime)}
                    subvalue={`~${metrics.avgExecutionTime.toFixed(1)}s avg per test`}
                    icon={<Clock className="w-5 h-5" />}
                    color="text-purple-400"
                    trend={options.showTrends ? undefined : undefined}
                  />
                )}
              </div>
            )}
          </div>

          {/* Completion progress bar */}
          {options.showProgressBar && (
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                Completion Progress
              </h3>
              <CompletionProgressBar
                completionRate={metrics.completionRate}
                passedCount={metrics.passedTasks}
                failedCount={metrics.failedTasks}
                pendingCount={metrics.pendingTasks}
                showLegend={options.showLegend}
              />
            </div>
          )}

          {/* Test type breakdown */}
          {options.showTestTypeBreakdown && options.showAutomatedVsManual && (
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-zinc-800/30 rounded-lg border border-zinc-700/50">
                <div className="flex items-center gap-2 mb-2">
                  <Zap className="w-4 h-4 text-blue-400" />
                  <span className="text-sm font-medium text-zinc-200">Automated Tests</span>
                </div>
                <div className="text-2xl font-bold text-blue-400">{metrics.automatedTasks}</div>
                <div className="text-xs text-zinc-500">
                  {metrics.totalTasks > 0 ? ((metrics.automatedTasks / metrics.totalTasks) * 100).toFixed(0) : 0}% of total
                </div>
              </div>
              <div className="p-4 bg-zinc-800/30 rounded-lg border border-zinc-700/50">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-4 h-4 text-yellow-400" />
                  <span className="text-sm font-medium text-zinc-200">Manual Tests</span>
                </div>
                <div className="text-2xl font-bold text-yellow-400">{metrics.manualTasks}</div>
                <div className="text-xs text-zinc-500">
                  {metrics.totalTasks > 0 ? ((metrics.manualTasks / metrics.totalTasks) * 100).toFixed(0) : 0}% of total
                </div>
              </div>
            </div>
          )}

          {/* Failed tests summary */}
          {options.showFailedTestsSummary && (
            <FailedTestsSummary
              tasks={tasks}
              onViewTask={onViewTask}
              onCreateBugs={options.allowBugCreation ? onCreateBugs : undefined}
              maxShown={options.maxFailedTestsShown}
            />
          )}

          {/* Next steps */}
          {options.showNextSteps && nextSteps.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                Next Steps
              </h3>
              <div className="space-y-3">
                {nextSteps.map(step => (
                  <NextStepCard key={step.id} step={step} />
                ))}
              </div>
            </div>
          )}

          {/* Action buttons */}
          {options.showQuickActions && (
            <div className="flex items-center gap-3 pt-4 border-t border-zinc-800">
              {!isComplete && onMarkComplete && metrics.isFullyExecuted && options.enabledActions.includes('mark-complete') && (
                <button
                  onClick={handleMarkComplete}
                  disabled={!metrics.isPassingThreshold}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors',
                    metrics.isPassingThreshold
                      ? 'bg-green-600 hover:bg-green-700 text-white'
                      : 'bg-zinc-700 text-zinc-400 cursor-not-allowed'
                  )}
                >
                  <Flag className="w-4 h-4" />
                  Mark Complete
                </button>
              )}

              {onExportResults && options.enabledActions.includes('export') && (
                <ExportMenu onExport={onExportResults} defaultFormat={options.defaultExportFormat} />
              )}

              {onRerunFailed && metrics.failedTasks > 0 && options.enabledActions.includes('rerun-failed') && (
                <button
                  onClick={onRerunFailed}
                  className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                  Re-run Failed ({metrics.failedTasks})
                </button>
              )}

              {onArchive && isComplete && options.enabledActions.includes('archive') && (
                <button
                  onClick={onArchive}
                  className="flex items-center gap-2 px-4 py-2 text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  <Archive className="w-4 h-4" />
                  Archive
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default TestPlanCompletionUI;
