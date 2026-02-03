'use client';

/**
 * Test Plan Evaluation UI - CB-838
 * Comprehensive component for evaluating and analyzing test plan quality and execution
 *
 * Features:
 * - Summary metrics dashboard (pass rate, coverage, total tests)
 * - Coverage analysis by area, priority, and type
 * - Execution history and trends visualization
 * - Test plan quality metrics with recommendations
 * - Interactive filtering and drill-down
 * - Customizable evaluation options (CB-849)
 */

import { useState, useMemo, useCallback } from 'react';
import {
  X,
  BarChart3,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  XCircle,
  Circle,
  AlertTriangle,
  Lightbulb,
  Target,
  Clock,
  Zap,
  Shield,
  Eye,
  Gauge,
  Accessibility,
  Puzzle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  FileText,
  AlertCircle,
  ArrowRight,
  Minus,
  Settings2,
} from 'lucide-react';
import type { QATask, QATaskStatus, QAPriority, QAExecutionRun, EvaluationOptions } from '@/types/qaboard';
import { parseExecutionHistory, DEFAULT_EVALUATION_OPTIONS } from '@/types/qaboard';
import { cn } from '@/lib/utils';
import { EvaluationOptionsPanel } from './EvaluationOptionsPanel';

// ==================== Types ====================

export interface TestPlanEvaluationProps {
  tasks: QATask[];
  passThreshold: number; // 0-1
  isOpen?: boolean;
  onClose?: () => void;
  onTaskClick?: (task: QATask) => void;
  onRerunRecommended?: (taskIds: string[]) => void;
  evaluationOptions?: EvaluationOptions;
  onEvaluationOptionsChange?: (options: EvaluationOptions) => void;
  className?: string;
}

type TestArea = 'functional' | 'ui' | 'integration' | 'performance' | 'security' | 'accessibility' | 'other';

interface AreaCoverage {
  area: TestArea;
  name: string;
  total: number;
  passed: number;
  failed: number;
  notDone: number;
  passRate: number;
  icon: React.ReactNode;
  color: string;
}

interface PriorityDistribution {
  priority: QAPriority;
  count: number;
  passed: number;
  failed: number;
  percentage: number;
}

interface TypeDistribution {
  type: 'AUTOMATED' | 'MANUAL';
  count: number;
  passed: number;
  failed: number;
  percentage: number;
}

interface QualityMetric {
  id: string;
  label: string;
  value: number;
  maxValue: number;
  status: 'good' | 'warning' | 'critical';
  description: string;
}

interface Recommendation {
  id: string;
  type: 'coverage' | 'priority' | 'flaky' | 'execution' | 'improvement';
  severity: 'info' | 'warning' | 'critical';
  title: string;
  description: string;
  action?: string;
  affectedTaskIds?: string[];
}

// ==================== Constants ====================

const TEST_AREA_CONFIG: Record<TestArea, { name: string; icon: React.ReactNode; color: string; bgColor: string }> = {
  functional: {
    name: 'Functional',
    icon: <Puzzle className="w-4 h-4" />,
    color: 'text-blue-400',
    bgColor: 'bg-blue-900/30',
  },
  ui: {
    name: 'UI/UX',
    icon: <Eye className="w-4 h-4" />,
    color: 'text-purple-400',
    bgColor: 'bg-purple-900/30',
  },
  integration: {
    name: 'Integration',
    icon: <Zap className="w-4 h-4" />,
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-900/30',
  },
  performance: {
    name: 'Performance',
    icon: <Gauge className="w-4 h-4" />,
    color: 'text-orange-400',
    bgColor: 'bg-orange-900/30',
  },
  security: {
    name: 'Security',
    icon: <Shield className="w-4 h-4" />,
    color: 'text-red-400',
    bgColor: 'bg-red-900/30',
  },
  accessibility: {
    name: 'Accessibility',
    icon: <Accessibility className="w-4 h-4" />,
    color: 'text-green-400',
    bgColor: 'bg-green-900/30',
  },
  other: {
    name: 'Other',
    icon: <FileText className="w-4 h-4" />,
    color: 'text-zinc-400',
    bgColor: 'bg-zinc-800',
  },
};

const PRIORITY_CONFIG: Record<QAPriority, { label: string; color: string; bgColor: string }> = {
  CRITICAL: { label: 'Critical', color: 'text-red-400', bgColor: 'bg-red-900/30' },
  HIGH: { label: 'High', color: 'text-orange-400', bgColor: 'bg-orange-900/30' },
  MEDIUM: { label: 'Medium', color: 'text-yellow-400', bgColor: 'bg-yellow-900/30' },
  LOW: { label: 'Low', color: 'text-zinc-400', bgColor: 'bg-zinc-800' },
};

// ==================== Helper Functions ====================

function detectTestArea(task: QATask): TestArea {
  const text = `${task.title} ${task.scenario} ${task.expectedResult}`.toLowerCase();

  if (text.includes('security') || text.includes('auth') || text.includes('permission') || text.includes('xss') || text.includes('injection')) {
    return 'security';
  }
  if (text.includes('performance') || text.includes('load') || text.includes('speed') || text.includes('latency') || text.includes('response time')) {
    return 'performance';
  }
  if (text.includes('accessibility') || text.includes('a11y') || text.includes('wcag') || text.includes('screen reader') || text.includes('keyboard navigation')) {
    return 'accessibility';
  }
  if (text.includes('ui') || text.includes('visual') || text.includes('layout') || text.includes('display') || text.includes('render') || text.includes('css')) {
    return 'ui';
  }
  if (text.includes('api') || text.includes('integration') || text.includes('endpoint') || text.includes('service') || text.includes('external')) {
    return 'integration';
  }
  if (text.includes('function') || text.includes('feature') || text.includes('behavior') || text.includes('click') || text.includes('submit')) {
    return 'functional';
  }

  return 'functional'; // Default to functional
}

function calculateExecutionTrend(tasks: QATask[]): { trend: 'up' | 'down' | 'stable'; change: number } {
  // Get all execution history entries and sort by timestamp
  const allRuns: { timestamp: Date; passed: boolean }[] = [];

  tasks.forEach(task => {
    const history = parseExecutionHistory(task.executionHistory);
    history.forEach(run => {
      allRuns.push({
        timestamp: new Date(run.timestamp),
        passed: run.status === 'PASS',
      });
    });
  });

  if (allRuns.length < 2) {
    return { trend: 'stable', change: 0 };
  }

  // Sort by timestamp
  allRuns.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());

  // Split into older half and newer half
  const midpoint = Math.floor(allRuns.length / 2);
  const olderRuns = allRuns.slice(0, midpoint);
  const newerRuns = allRuns.slice(midpoint);

  const olderPassRate = olderRuns.filter(r => r.passed).length / olderRuns.length;
  const newerPassRate = newerRuns.filter(r => r.passed).length / newerRuns.length;

  const change = (newerPassRate - olderPassRate) * 100;

  if (change > 5) return { trend: 'up', change };
  if (change < -5) return { trend: 'down', change };
  return { trend: 'stable', change };
}

function detectFlakyTests(tasks: QATask[]): QATask[] {
  return tasks.filter(task => {
    const history = parseExecutionHistory(task.executionHistory);
    if (history.length < 3) return false;

    // Check for alternating pass/fail pattern
    let flips = 0;
    for (let i = 1; i < history.length; i++) {
      if (history[i].status !== history[i - 1].status) {
        flips++;
      }
    }

    // If more than 40% of runs flip status, consider it flaky
    return flips / (history.length - 1) > 0.4;
  });
}

// ==================== Sub-components ====================

// Summary Metric Card
function MetricCard({
  label,
  value,
  suffix,
  trend,
  trendValue,
  color,
  icon,
}: {
  label: string;
  value: string | number;
  suffix?: string;
  trend?: 'up' | 'down' | 'stable';
  trendValue?: string;
  color: string;
  icon?: React.ReactNode;
}) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-zinc-500';

  return (
    <div className="p-4 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-zinc-500 uppercase tracking-wider">{label}</span>
        {icon && <span className={cn('opacity-60', color)}>{icon}</span>}
      </div>
      <div className="flex items-end gap-2">
        <span className={cn('text-2xl font-bold', color)}>
          {value}
          {suffix && <span className="text-lg font-normal">{suffix}</span>}
        </span>
        {trend && trendValue && (
          <span className={cn('flex items-center gap-0.5 text-xs mb-1', trendColor)}>
            <TrendIcon className="w-3 h-3" />
            {trendValue}
          </span>
        )}
      </div>
    </div>
  );
}

// Coverage Bar
function CoverageBar({
  area,
  onClick,
}: {
  area: AreaCoverage;
  onClick?: () => void;
}) {
  const config = TEST_AREA_CONFIG[area.area];

  return (
    <button
      onClick={onClick}
      className="w-full p-3 bg-zinc-800/30 rounded-lg hover:bg-zinc-800/50 transition-colors text-left"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={cn('p-1.5 rounded', config.bgColor, config.color)}>
            {config.icon}
          </span>
          <span className="text-sm font-medium text-zinc-200">{config.name}</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-zinc-500">{area.total} tests</span>
          <span className={cn(
            'font-medium',
            area.passRate >= 80 ? 'text-green-400' : area.passRate >= 50 ? 'text-yellow-400' : 'text-red-400'
          )}>
            {area.passRate.toFixed(0)}%
          </span>
        </div>
      </div>
      <div className="h-2 bg-zinc-700 rounded-full overflow-hidden flex">
        {area.passed > 0 && (
          <div
            className="h-full bg-green-500 transition-all"
            style={{ width: `${(area.passed / area.total) * 100}%` }}
          />
        )}
        {area.failed > 0 && (
          <div
            className="h-full bg-red-500 transition-all"
            style={{ width: `${(area.failed / area.total) * 100}%` }}
          />
        )}
        {area.notDone > 0 && (
          <div
            className="h-full bg-zinc-600 transition-all"
            style={{ width: `${(area.notDone / area.total) * 100}%` }}
          />
        )}
      </div>
      <div className="flex items-center gap-3 mt-2 text-xs text-zinc-500">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          {area.passed} passed
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          {area.failed} failed
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-zinc-600" />
          {area.notDone} pending
        </span>
      </div>
    </button>
  );
}

// Priority Distribution Chart
function PriorityChart({ distribution }: { distribution: PriorityDistribution[] }) {
  const maxCount = Math.max(...distribution.map(d => d.count), 1);

  return (
    <div className="space-y-3">
      {distribution.map(d => {
        const config = PRIORITY_CONFIG[d.priority];
        const barWidth = (d.count / maxCount) * 100;
        const passedWidth = d.count > 0 ? (d.passed / d.count) * barWidth : 0;
        const failedWidth = d.count > 0 ? (d.failed / d.count) * barWidth : 0;

        return (
          <div key={d.priority} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className={config.color}>{config.label}</span>
              <span className="text-zinc-500">{d.count} ({d.percentage.toFixed(0)}%)</span>
            </div>
            <div className="h-3 bg-zinc-700/50 rounded-full overflow-hidden flex">
              {d.passed > 0 && (
                <div
                  className="h-full bg-green-500/80 transition-all"
                  style={{ width: `${passedWidth}%` }}
                />
              )}
              {d.failed > 0 && (
                <div
                  className="h-full bg-red-500/80 transition-all"
                  style={{ width: `${failedWidth}%` }}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Type Distribution Donut
function TypeDonut({ automated, manual }: { automated: TypeDistribution; manual: TypeDistribution }) {
  const total = automated.count + manual.count;
  const automatedPercentage = total > 0 ? (automated.count / total) * 100 : 50;

  return (
    <div className="flex items-center gap-6">
      {/* Simple donut visualization */}
      <div className="relative w-24 h-24">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="#3f3f46"
            strokeWidth="3"
          />
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="#3b82f6"
            strokeWidth="3"
            strokeDasharray={`${automatedPercentage}, 100`}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold text-zinc-200">{total}</span>
        </div>
      </div>

      {/* Legend */}
      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-blue-500" />
          <span className="text-zinc-300">Automated</span>
          <span className="text-zinc-500">({automated.count})</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-zinc-600" />
          <span className="text-zinc-300">Manual</span>
          <span className="text-zinc-500">({manual.count})</span>
        </div>
      </div>
    </div>
  );
}

// Quality Score Gauge
function QualityGauge({ score, label }: { score: number; label: string }) {
  const getColor = (s: number) => {
    if (s >= 80) return 'text-green-400';
    if (s >= 60) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getStrokeColor = (s: number) => {
    if (s >= 80) return '#4ade80';
    if (s >= 60) return '#facc15';
    return '#f87171';
  };

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-20 h-20">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="#3f3f46"
            strokeWidth="2.5"
          />
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke={getStrokeColor(score)}
            strokeWidth="2.5"
            strokeDasharray={`${score}, 100`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn('text-lg font-bold', getColor(score))}>{score}</span>
        </div>
      </div>
      <span className="mt-1 text-xs text-zinc-500">{label}</span>
    </div>
  );
}

// Recommendation Card
function RecommendationCard({
  recommendation,
  onAction,
}: {
  recommendation: Recommendation;
  onAction?: () => void;
}) {
  const severityConfig = {
    info: { color: 'text-blue-400', bgColor: 'bg-blue-900/20', borderColor: 'border-blue-800/50', icon: <Lightbulb className="w-4 h-4" /> },
    warning: { color: 'text-yellow-400', bgColor: 'bg-yellow-900/20', borderColor: 'border-yellow-800/50', icon: <AlertTriangle className="w-4 h-4" /> },
    critical: { color: 'text-red-400', bgColor: 'bg-red-900/20', borderColor: 'border-red-800/50', icon: <AlertCircle className="w-4 h-4" /> },
  };

  const config = severityConfig[recommendation.severity];

  return (
    <div className={cn('p-3 rounded-lg border', config.bgColor, config.borderColor)}>
      <div className="flex items-start gap-3">
        <span className={cn('mt-0.5', config.color)}>{config.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200">{recommendation.title}</p>
          <p className="text-xs text-zinc-500 mt-0.5">{recommendation.description}</p>
          {recommendation.action && onAction && (
            <button
              onClick={onAction}
              className={cn('mt-2 text-xs flex items-center gap-1 transition-colors', config.color, 'hover:underline')}
            >
              {recommendation.action}
              <ArrowRight className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Execution History Timeline
function ExecutionTimeline({ tasks, maxItems = 10 }: { tasks: QATask[]; maxItems?: number }) {
  // Collect recent executions
  const recentExecutions = useMemo(() => {
    const executions: { task: QATask; run: QAExecutionRun }[] = [];

    tasks.forEach(task => {
      const history = parseExecutionHistory(task.executionHistory);
      history.slice(0, 3).forEach(run => {
        executions.push({ task, run });
      });
    });

    return executions
      .sort((a, b) => new Date(b.run.timestamp).getTime() - new Date(a.run.timestamp).getTime())
      .slice(0, maxItems);
  }, [tasks, maxItems]);

  if (recentExecutions.length === 0) {
    return (
      <div className="text-center py-8 text-zinc-500">
        <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">No execution history yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {recentExecutions.map(({ task, run }, index) => (
        <div
          key={`${task.id}-${run.timestamp}-${index}`}
          className="flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-800/50 transition-colors"
        >
          {run.status === 'PASS' ? (
            <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
          ) : run.status === 'FAILED' ? (
            <XCircle className="w-4 h-4 text-red-500 shrink-0" />
          ) : (
            <Circle className="w-4 h-4 text-zinc-500 shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-zinc-300 truncate">{task.key}: {task.title}</p>
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span>{new Date(run.timestamp).toLocaleString()}</span>
              <span className="text-zinc-600">|</span>
              <span>{run.executionTime.toFixed(1)}s</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ==================== Main Component ====================

export function TestPlanEvaluation({
  tasks,
  passThreshold,
  isOpen = true,
  onClose,
  onTaskClick,
  onRerunRecommended,
  evaluationOptions: externalOptions,
  onEvaluationOptionsChange,
  className,
}: TestPlanEvaluationProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['summary', 'coverage', 'quality']));
  const [selectedArea, setSelectedArea] = useState<TestArea | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  const [internalOptions, setInternalOptions] = useState<EvaluationOptions>(DEFAULT_EVALUATION_OPTIONS);

  // Use external options if provided, otherwise use internal state
  const options = externalOptions ?? internalOptions;
  const handleOptionsChange = useCallback((newOptions: EvaluationOptions) => {
    if (onEvaluationOptionsChange) {
      onEvaluationOptionsChange(newOptions);
    } else {
      setInternalOptions(newOptions);
    }
  }, [onEvaluationOptionsChange]);

  const toggleSection = useCallback((section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  }, []);

  // Calculate summary statistics
  const summary = useMemo(() => {
    const total = tasks.length;
    const passed = tasks.filter(t => t.status === 'PASS').length;
    const failed = tasks.filter(t => t.status === 'FAILED').length;
    const notDone = tasks.filter(t => t.status === 'NOT_DONE').length;
    const inProgress = tasks.filter(t => t.status === 'IN_PROGRESS').length;
    const executed = passed + failed;
    const passRate = executed > 0 ? (passed / executed) * 100 : 0;
    const completionRate = total > 0 ? (executed / total) * 100 : 0;
    const isPassingThreshold = passRate / 100 >= passThreshold;

    return {
      total,
      passed,
      failed,
      notDone,
      inProgress,
      executed,
      passRate,
      completionRate,
      isPassingThreshold,
    };
  }, [tasks, passThreshold]);

  // Calculate area coverage
  const areaCoverage = useMemo<AreaCoverage[]>(() => {
    const areaMap = new Map<TestArea, { total: number; passed: number; failed: number; notDone: number }>();

    tasks.forEach(task => {
      const area = detectTestArea(task);
      const current = areaMap.get(area) || { total: 0, passed: 0, failed: 0, notDone: 0 };
      current.total++;
      if (task.status === 'PASS') current.passed++;
      else if (task.status === 'FAILED') current.failed++;
      else current.notDone++;
      areaMap.set(area, current);
    });

    const areas: AreaCoverage[] = [];
    areaMap.forEach((stats, area) => {
      const config = TEST_AREA_CONFIG[area];
      const executed = stats.passed + stats.failed;
      areas.push({
        area,
        name: config.name,
        total: stats.total,
        passed: stats.passed,
        failed: stats.failed,
        notDone: stats.notDone,
        passRate: executed > 0 ? (stats.passed / executed) * 100 : 0,
        icon: config.icon,
        color: config.color,
      });
    });

    return areas.sort((a, b) => b.total - a.total);
  }, [tasks]);

  // Calculate priority distribution
  const priorityDistribution = useMemo<PriorityDistribution[]>(() => {
    const priorities: QAPriority[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
    const total = tasks.length;

    return priorities.map(priority => {
      const matching = tasks.filter(t => t.priority === priority);
      return {
        priority,
        count: matching.length,
        passed: matching.filter(t => t.status === 'PASS').length,
        failed: matching.filter(t => t.status === 'FAILED').length,
        percentage: total > 0 ? (matching.length / total) * 100 : 0,
      };
    });
  }, [tasks]);

  // Calculate type distribution
  const typeDistribution = useMemo(() => {
    const automated = tasks.filter(t => t.type === 'AUTOMATED');
    const manual = tasks.filter(t => t.type === 'MANUAL');
    const total = tasks.length;

    return {
      automated: {
        type: 'AUTOMATED' as const,
        count: automated.length,
        passed: automated.filter(t => t.status === 'PASS').length,
        failed: automated.filter(t => t.status === 'FAILED').length,
        percentage: total > 0 ? (automated.length / total) * 100 : 0,
      },
      manual: {
        type: 'MANUAL' as const,
        count: manual.length,
        passed: manual.filter(t => t.status === 'PASS').length,
        failed: manual.filter(t => t.status === 'FAILED').length,
        percentage: total > 0 ? (manual.length / total) * 100 : 0,
      },
    };
  }, [tasks]);

  // Calculate quality metrics
  const qualityMetrics = useMemo<QualityMetric[]>(() => {
    const metrics: QualityMetric[] = [];

    // Pass rate score
    const passRateScore = Math.min(100, summary.passRate);
    metrics.push({
      id: 'pass-rate',
      label: 'Pass Rate',
      value: passRateScore,
      maxValue: 100,
      status: passRateScore >= 80 ? 'good' : passRateScore >= 60 ? 'warning' : 'critical',
      description: `${summary.passed} of ${summary.executed} executed tests passed`,
    });

    // Completion score
    const completionScore = Math.min(100, summary.completionRate);
    metrics.push({
      id: 'completion',
      label: 'Completion',
      value: completionScore,
      maxValue: 100,
      status: completionScore >= 80 ? 'good' : completionScore >= 50 ? 'warning' : 'critical',
      description: `${summary.executed} of ${summary.total} tests executed`,
    });

    // Coverage score (based on areas covered)
    const coveredAreas = areaCoverage.filter(a => a.total > 0).length;
    const coverageScore = Math.round((coveredAreas / 6) * 100);
    metrics.push({
      id: 'coverage',
      label: 'Coverage',
      value: coverageScore,
      maxValue: 100,
      status: coverageScore >= 50 ? 'good' : coverageScore >= 33 ? 'warning' : 'critical',
      description: `${coveredAreas} of 6 test areas covered`,
    });

    // Priority balance score
    const criticalHighCount = priorityDistribution
      .filter(p => p.priority === 'CRITICAL' || p.priority === 'HIGH')
      .reduce((sum, p) => sum + p.count, 0);
    const priorityScore = tasks.length > 0 ? Math.round((criticalHighCount / tasks.length) * 100 * 2) : 0;
    const clampedPriorityScore = Math.min(100, priorityScore);
    metrics.push({
      id: 'priority',
      label: 'Priority Focus',
      value: clampedPriorityScore,
      maxValue: 100,
      status: clampedPriorityScore >= 40 ? 'good' : clampedPriorityScore >= 20 ? 'warning' : 'critical',
      description: `${criticalHighCount} critical/high priority tests`,
    });

    return metrics;
  }, [summary, areaCoverage, priorityDistribution, tasks.length]);

  // Overall quality score
  const overallScore = useMemo(() => {
    if (qualityMetrics.length === 0) return 0;
    const sum = qualityMetrics.reduce((acc, m) => acc + m.value, 0);
    return Math.round(sum / qualityMetrics.length);
  }, [qualityMetrics]);

  // Execution trend
  const trend = useMemo(() => calculateExecutionTrend(tasks), [tasks]);

  // Flaky tests
  const flakyTests = useMemo(() => detectFlakyTests(tasks), [tasks]);

  // Generate recommendations
  const recommendations = useMemo<Recommendation[]>(() => {
    const recs: Recommendation[] = [];

    // Low pass rate
    if (summary.passRate < passThreshold * 100 && summary.executed > 0) {
      recs.push({
        id: 'low-pass-rate',
        type: 'execution',
        severity: 'critical',
        title: 'Pass rate below threshold',
        description: `Current pass rate (${summary.passRate.toFixed(0)}%) is below the ${(passThreshold * 100).toFixed(0)}% threshold.`,
        action: 'View failed tests',
        affectedTaskIds: tasks.filter(t => t.status === 'FAILED').map(t => t.id),
      });
    }

    // Incomplete tests
    if (summary.completionRate < 100 && summary.notDone > 0) {
      recs.push({
        id: 'incomplete',
        type: 'execution',
        severity: summary.completionRate < 50 ? 'warning' : 'info',
        title: `${summary.notDone} tests not executed`,
        description: 'Complete all tests for comprehensive coverage assessment.',
        action: 'Run pending tests',
        affectedTaskIds: tasks.filter(t => t.status === 'NOT_DONE').map(t => t.id),
      });
    }

    // Flaky tests
    if (flakyTests.length > 0) {
      recs.push({
        id: 'flaky',
        type: 'flaky',
        severity: 'warning',
        title: `${flakyTests.length} flaky test${flakyTests.length > 1 ? 's' : ''} detected`,
        description: 'Tests with inconsistent results may indicate unstable functionality.',
        action: 'Review flaky tests',
        affectedTaskIds: flakyTests.map(t => t.id),
      });
    }

    // Coverage gaps
    const missingAreas = Object.keys(TEST_AREA_CONFIG).filter(
      area => !areaCoverage.some(c => c.area === area && c.total > 0)
    );
    if (missingAreas.length > 0 && tasks.length > 5) {
      recs.push({
        id: 'coverage-gap',
        type: 'coverage',
        severity: 'info',
        title: 'Coverage gaps detected',
        description: `No tests for: ${missingAreas.map(a => TEST_AREA_CONFIG[a as TestArea].name).join(', ')}`,
      });
    }

    // Low priority focus
    const criticalHighTests = tasks.filter(t => t.priority === 'CRITICAL' || t.priority === 'HIGH');
    if (criticalHighTests.length === 0 && tasks.length > 3) {
      recs.push({
        id: 'priority-focus',
        type: 'priority',
        severity: 'info',
        title: 'Consider adding high-priority tests',
        description: 'No critical or high priority tests in the test plan.',
      });
    }

    // Downward trend
    if (trend.trend === 'down' && Math.abs(trend.change) > 10) {
      recs.push({
        id: 'declining-trend',
        type: 'improvement',
        severity: 'warning',
        title: 'Declining pass rate trend',
        description: `Pass rate has decreased by ${Math.abs(trend.change).toFixed(0)}% over recent runs.`,
      });
    }

    return recs;
  }, [summary, passThreshold, tasks, flakyTests, areaCoverage, trend]);

  if (!isOpen) return null;

  return (
    <div className={cn('bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <BarChart3 className="w-5 h-5 text-blue-400" />
          <h2 className="text-lg font-semibold text-white">Test Plan Evaluation</h2>
          {tasks.length > 0 && (
            <span className={cn(
              'px-2 py-0.5 text-xs rounded-full',
              summary.isPassingThreshold
                ? 'bg-green-900/50 text-green-400'
                : 'bg-red-900/50 text-red-400'
            )}>
              {summary.isPassingThreshold ? 'Passing' : 'Not Passing'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowOptions(!showOptions)}
            className={cn(
              'p-1.5 rounded-lg transition-colors',
              showOptions
                ? 'text-purple-400 bg-purple-900/30 hover:bg-purple-900/50'
                : 'text-zinc-500 hover:text-white hover:bg-zinc-800'
            )}
            title="Evaluation options"
          >
            <Settings2 className="w-4 h-4" />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-500 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Options Panel - Slides out from header when active */}
      {showOptions && (
        <div className="border-b border-zinc-800 bg-zinc-900/95 max-h-[50vh] overflow-y-auto qa-scrollbar">
          <div className="p-4">
            <EvaluationOptionsPanel
              options={options}
              onOptionsChange={handleOptionsChange}
            />
          </div>
        </div>
      )}

      <div className="p-6 space-y-6 max-h-[calc(100vh-200px)] overflow-y-auto qa-scrollbar">
        {tasks.length === 0 ? (
          <div className="text-center py-12">
            <Target className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
            <h3 className="text-lg font-medium text-zinc-400 mb-2">No Test Plan Data</h3>
            <p className="text-sm text-zinc-500">Generate a test plan to see evaluation metrics.</p>
          </div>
        ) : (
          <>
            {/* Summary Section - Always shown */}
            <section>
              <button
                onClick={() => toggleSection('summary')}
                className="w-full flex items-center justify-between mb-4 group"
              >
                <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Summary</h3>
                {expandedSections.has('summary') ? (
                  <ChevronUp className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                )}
              </button>

              {expandedSections.has('summary') && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <MetricCard
                    label="Pass Rate"
                    value={summary.passRate.toFixed(0)}
                    suffix="%"
                    trend={trend.trend}
                    trendValue={trend.trend !== 'stable' ? `${Math.abs(trend.change).toFixed(0)}%` : undefined}
                    color={summary.passRate >= 80 ? 'text-green-400' : summary.passRate >= 50 ? 'text-yellow-400' : 'text-red-400'}
                    icon={<Target className="w-5 h-5" />}
                  />
                  <MetricCard
                    label="Total Tests"
                    value={summary.total}
                    color="text-blue-400"
                    icon={<FileText className="w-5 h-5" />}
                  />
                  <MetricCard
                    label="Passed"
                    value={summary.passed}
                    color="text-green-400"
                    icon={<CheckCircle2 className="w-5 h-5" />}
                  />
                  <MetricCard
                    label="Failed"
                    value={summary.failed}
                    color={summary.failed > 0 ? 'text-red-400' : 'text-zinc-400'}
                    icon={<XCircle className="w-5 h-5" />}
                  />
                </div>
              )}
            </section>

            {/* Quality Score Section - Respects options.showMetrics */}
            {options.showMetrics.length > 0 && (
              <section>
                <button
                  onClick={() => toggleSection('quality')}
                  className="w-full flex items-center justify-between mb-4 group"
                >
                  <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Quality Score</h3>
                  {expandedSections.has('quality') ? (
                    <ChevronUp className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                  )}
                </button>

                {expandedSections.has('quality') && (
                  <div className="p-4 bg-zinc-800/30 rounded-lg border border-zinc-700/50">
                    <div className="flex items-center justify-between mb-6">
                      <div>
                        <p className="text-2xl font-bold text-white">{overallScore}</p>
                        <p className="text-sm text-zinc-500">Overall Quality Score</p>
                      </div>
                      {options.metricsVisualization === 'gauge' && (
                        <div className="flex items-center gap-4">
                          {qualityMetrics
                            .filter(metric => options.showMetrics.includes(metric.id as any))
                            .map(metric => (
                              <QualityGauge
                                key={metric.id}
                                score={Math.round(metric.value)}
                                label={metric.label}
                              />
                            ))}
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-xs">
                      {qualityMetrics
                        .filter(metric => options.showMetrics.includes(metric.id as any))
                        .map(metric => (
                          <div key={metric.id} className="flex items-center justify-between p-2 bg-zinc-800/50 rounded">
                            <span className="text-zinc-400">{metric.label}</span>
                            <span className="text-zinc-500">{metric.description}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </section>
            )}

            {/* Coverage Analysis Section - Respects options */}
            {(options.showAreaCoverage || options.showPriorityDistribution || options.showTypeDistribution) && (
              <section>
                <button
                  onClick={() => toggleSection('coverage')}
                  className="w-full flex items-center justify-between mb-4 group"
                >
                  <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Coverage Analysis</h3>
                  {expandedSections.has('coverage') ? (
                    <ChevronUp className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                  )}
                </button>

                {expandedSections.has('coverage') && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* By Area */}
                    {options.showAreaCoverage && (
                      <div>
                        <h4 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">By Test Area</h4>
                        <div className="space-y-2">
                          {areaCoverage.length > 0 ? (
                            areaCoverage.map(area => (
                              <CoverageBar
                                key={area.area}
                                area={area}
                                onClick={() => setSelectedArea(selectedArea === area.area ? null : area.area)}
                              />
                            ))
                          ) : (
                            <p className="text-sm text-zinc-500 text-center py-4">No coverage data</p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* By Priority & Type */}
                    {(options.showPriorityDistribution || options.showTypeDistribution) && (
                      <div className="space-y-6">
                        {options.showPriorityDistribution && (
                          <div>
                            <h4 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">By Priority</h4>
                            <PriorityChart distribution={priorityDistribution} />
                          </div>
                        )}

                        {options.showTypeDistribution && (
                          <div>
                            <h4 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Test Type Distribution</h4>
                            <TypeDonut
                              automated={typeDistribution.automated}
                              manual={typeDistribution.manual}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            {/* Recommendations Section - Respects options */}
            {options.showRecommendations && (() => {
              // Filter recommendations based on options
              const filteredRecs = recommendations.filter(rec =>
                options.recommendationTypes.includes(rec.type as any) &&
                options.recommendationSeverities.includes(rec.severity as any)
              );
              if (filteredRecs.length === 0) return null;
              return (
                <section>
                  <button
                    onClick={() => toggleSection('recommendations')}
                    className="w-full flex items-center justify-between mb-4 group"
                  >
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Recommendations</h3>
                      <span className="px-1.5 py-0.5 text-xs bg-zinc-700 text-zinc-400 rounded">
                        {filteredRecs.length}
                      </span>
                    </div>
                    {expandedSections.has('recommendations') ? (
                      <ChevronUp className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                    )}
                  </button>

                  {expandedSections.has('recommendations') && (
                    <div className="space-y-3">
                      {filteredRecs.map(rec => (
                        <RecommendationCard
                          key={rec.id}
                          recommendation={rec}
                          onAction={rec.affectedTaskIds && onRerunRecommended
                            ? () => onRerunRecommended(rec.affectedTaskIds!)
                            : undefined
                          }
                        />
                      ))}
                    </div>
                  )}
                </section>
              );
            })()}

            {/* Execution History Section - Respects options */}
            {options.showExecutionHistory && (
              <section>
                <button
                  onClick={() => toggleSection('history')}
                  className="w-full flex items-center justify-between mb-4 group"
                >
                  <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Recent Executions</h3>
                  {expandedSections.has('history') ? (
                    <ChevronUp className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
                  )}
                </button>

                {expandedSections.has('history') && (
                  <div className="p-4 bg-zinc-800/30 rounded-lg border border-zinc-700/50">
                    <ExecutionTimeline tasks={tasks} maxItems={options.maxHistoryItems} />
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default TestPlanEvaluation;
