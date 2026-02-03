'use client';

/**
 * FeatureTestingPanel - UI for viewing and running QA tests for a feature
 *
 * This component displays all QA tasks associated with a feature and its descendants,
 * allowing users to:
 * - View test results and pass rates
 * - Run automated tests (sequential or parallel)
 * - Mark manual tests as pass/fail
 * - Generate new QA plans
 * - Create bugs from failed tests
 */

import { useState, useMemo, useCallback } from 'react';
import {
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Bug,
  Sparkles,
  Square,
  CheckSquare,
  StopCircle,
  Zap,
  Settings2,
  RotateCcw,
  Filter,
  Eye,
  EyeOff,
  AlertTriangle,
} from 'lucide-react';
import {
  useQATasksForIssue,
  useQASummary,
  useStreamingExecution,
  useMarkManualQAResult,
  useCreateBugFromQA,
  useStreamingQAPlanGeneration,
} from '@/hooks/useQABoard';
import type { QATask, QATaskStatus, QASummary, QAPriority, QATaskType } from '@/types/qaboard';
import { getQAPriorityColor, parseExecutionHistory } from '@/types/qaboard';

// Feature Testing Options interface
interface FeatureTestingOptions {
  // Execution options
  maxConcurrent: number;
  retryFailedOnComplete: boolean;
  stopOnFirstFailure: boolean;
  // Filter options
  typeFilter: QATaskType | 'ALL';
  priorityFilter: QAPriority | 'ALL';
  // Behavior options
  autoCreateBugs: boolean;
  // View options
  hideCompleted: boolean;
  compactView: boolean;
}

const DEFAULT_OPTIONS: FeatureTestingOptions = {
  maxConcurrent: 5,
  retryFailedOnComplete: false,
  stopOnFirstFailure: false,
  typeFilter: 'ALL',
  priorityFilter: 'ALL',
  autoCreateBugs: false,
  hideCompleted: false,
  compactView: false,
};

// Helper to count active options that differ from defaults
function countActiveOptions(options: FeatureTestingOptions): number {
  let count = 0;
  if (options.maxConcurrent !== DEFAULT_OPTIONS.maxConcurrent) count++;
  if (options.retryFailedOnComplete !== DEFAULT_OPTIONS.retryFailedOnComplete) count++;
  if (options.stopOnFirstFailure !== DEFAULT_OPTIONS.stopOnFirstFailure) count++;
  if (options.typeFilter !== DEFAULT_OPTIONS.typeFilter) count++;
  if (options.priorityFilter !== DEFAULT_OPTIONS.priorityFilter) count++;
  if (options.autoCreateBugs !== DEFAULT_OPTIONS.autoCreateBugs) count++;
  if (options.hideCompleted !== DEFAULT_OPTIONS.hideCompleted) count++;
  if (options.compactView !== DEFAULT_OPTIONS.compactView) count++;
  return count;
}
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';
import { TestProgressTracker } from './TestProgressTracker';
import { QAProgressBar, ProgressBar } from './ProgressBar';

// Status configuration
const STATUS_CONFIG: Record<QATaskStatus, { icon: typeof CheckCircle2; color: string; bgColor: string; label: string }> = {
  'NOT_DONE': { icon: Clock, color: 'text-zinc-400', bgColor: 'bg-zinc-600', label: 'Not Done' },
  'IN_PROGRESS': { icon: RefreshCw, color: 'text-blue-400', bgColor: 'bg-blue-600', label: 'Running' },
  'PASS': { icon: CheckCircle2, color: 'text-green-400', bgColor: 'bg-green-600', label: 'Pass' },
  'FAILED': { icon: XCircle, color: 'text-red-400', bgColor: 'bg-red-600', label: 'Failed' },
};

interface FeatureTestingPanelProps {
  featureId: string;
  projectId: string;
}

// QA Task Card Component
function QATaskCard({
  task,
  isSelected,
  isCurrentlyExecuting,
  onSelect,
  onMarkManual,
  onCreateBug,
}: {
  task: QATask;
  isSelected: boolean;
  isCurrentlyExecuting?: boolean;
  onSelect: (id: string) => void;
  onMarkManual: (taskId: string, status: 'PASS' | 'FAILED', result: string) => void;
  onCreateBug: (taskId: string) => void;
}) {
  const [showManualInput, setShowManualInput] = useState(false);
  const [manualResult, setManualResult] = useState('');
  const [expanded, setExpanded] = useState(false);

  const statusConfig = STATUS_CONFIG[task.status];
  const StatusIcon = statusConfig.icon;
  const history = parseExecutionHistory(task.executionHistory);

  return (
    <div
      className={cn(
        'rounded-lg border transition-all',
        isCurrentlyExecuting
          ? 'border-blue-500 ring-2 ring-blue-500/30 bg-blue-900/10'
          : isSelected
          ? 'border-blue-500 bg-zinc-800'
          : 'border-zinc-700 bg-zinc-800/50 hover:bg-zinc-800'
      )}
    >
      {/* Header */}
      <div className="p-3">
        <div className="flex items-start gap-3">
          {/* Selection Checkbox */}
          <button
            onClick={() => onSelect(task.id)}
            className="mt-0.5 text-zinc-400 hover:text-blue-400"
          >
            {isSelected ? (
              <CheckSquare className="w-4 h-4 text-blue-500" />
            ) : (
              <Square className="w-4 h-4" />
            )}
          </button>

          {/* Status & Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {/* Status Badge */}
              <span
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-white',
                  isCurrentlyExecuting ? 'bg-blue-600' : statusConfig.bgColor
                )}
              >
                {isCurrentlyExecuting ? (
                  <RefreshCw className="w-3 h-3 animate-spin" />
                ) : (
                  <StatusIcon className="w-3 h-3" />
                )}
                {isCurrentlyExecuting ? 'Running' : statusConfig.label}
              </span>

              {/* Task Key */}
              <span className="text-xs font-mono text-zinc-500">{task.key}</span>

              {/* Priority */}
              <span className={cn('text-xs', getQAPriorityColor(task.priority))}>
                {task.priority}
              </span>

              {/* Type Badge */}
              {task.type === 'MANUAL' && (
                <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1.5 rounded">
                  Manual
                </span>
              )}
            </div>

            {/* Title */}
            <p className="mt-1 text-sm text-zinc-200">{task.title}</p>

            {/* Last Execution Info */}
            {task.lastExecutedAt && (
              <p className="mt-1 text-xs text-zinc-500">
                Last run: {new Date(task.lastExecutedAt).toLocaleString()}
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1 shrink-0">
            {task.status === 'FAILED' && !task.bugIssueId && (
              <button
                onClick={() => onCreateBug(task.id)}
                className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-900/30 rounded"
                title="Create Bug"
              >
                <Bug className="w-4 h-4" />
              </button>
            )}
            {task.status === 'NOT_DONE' && task.type === 'MANUAL' && (
              <button
                onClick={() => setShowManualInput(!showManualInput)}
                className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
              >
                Mark
              </button>
            )}
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-700 rounded"
              title="Show Details"
            >
              {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Manual Test Input */}
        {showManualInput && (
          <div className="mt-3 pt-3 border-t border-zinc-700">
            <textarea
              value={manualResult}
              onChange={(e) => setManualResult(e.target.value)}
              placeholder="Enter actual result..."
              rows={2}
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded text-sm text-white resize-none"
            />
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => {
                  onMarkManual(task.id, 'PASS', manualResult);
                  setShowManualInput(false);
                  setManualResult('');
                }}
                className="px-3 py-1.5 text-xs bg-green-600 hover:bg-green-700 text-white rounded"
              >
                Mark Pass
              </button>
              <button
                onClick={() => {
                  onMarkManual(task.id, 'FAILED', manualResult);
                  setShowManualInput(false);
                  setManualResult('');
                }}
                className="px-3 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white rounded"
              >
                Mark Failed
              </button>
              <button
                onClick={() => {
                  setShowManualInput(false);
                  setManualResult('');
                }}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="px-3 pb-3 pt-0 border-t border-zinc-700/50 mt-1">
          <div className="space-y-3 pt-3">
            {/* Scenario */}
            <div>
              <h4 className="text-xs font-semibold text-zinc-400 mb-1">Test Scenario</h4>
              <pre className="p-2 bg-zinc-900 rounded text-xs text-zinc-300 whitespace-pre-wrap">
                {task.scenario}
              </pre>
            </div>

            {/* Expected Result */}
            <div>
              <h4 className="text-xs font-semibold text-zinc-400 mb-1">Expected Result</h4>
              <p className="p-2 bg-zinc-900 rounded text-xs text-zinc-300">
                {task.expectedResult}
              </p>
            </div>

            {/* Actual Result */}
            {task.actualResult && (
              <div>
                <h4 className="text-xs font-semibold text-zinc-400 mb-1">Actual Result</h4>
                <p className={cn(
                  'p-2 rounded text-xs',
                  task.status === 'PASS' ? 'bg-green-900/30 text-green-300' : 'bg-red-900/30 text-red-300'
                )}>
                  {task.actualResult}
                </p>
              </div>
            )}

            {/* Execution History */}
            {history.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-zinc-400 mb-1">
                  History ({history.length} runs)
                </h4>
                <div className="space-y-1">
                  {history.slice(0, 5).map((run, i) => (
                    <div
                      key={run.id || i}
                      className="flex items-center justify-between p-1.5 bg-zinc-900 rounded text-xs"
                    >
                      <span className="text-zinc-500">
                        {new Date(run.timestamp).toLocaleString()}
                      </span>
                      <span
                        className={cn(
                          'px-1.5 py-0.5 rounded',
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
        </div>
      )}
    </div>
  );
}

// Summary Card Component
function SummaryCard({ summary }: { summary: QASummary | null }) {
  if (!summary) {
    return (
      <div className="bg-zinc-800 rounded-lg border border-zinc-700 p-4">
        <p className="text-zinc-500 text-sm">No QA tests yet</p>
      </div>
    );
  }

  const passRate = Math.round(summary.passRate * 100);
  const isHealthy = summary.isPassingThreshold;

  return (
    <div className="bg-zinc-800 rounded-lg border border-zinc-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-white flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-blue-400" />
          Test Summary
        </h3>
        <span
          className={cn(
            'px-3 py-1 rounded-full text-sm font-bold',
            isHealthy ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
          )}
        >
          {passRate}% Pass Rate
        </span>
      </div>

      {/* Progress Bar */}
      <QAProgressBar
        passed={summary.passedTasks}
        failed={summary.failedTasks}
        inProgress={summary.inProgressTasks}
        pending={summary.notDoneTasks}
        size="lg"
        className="mb-4"
      />

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-3">
        <div className="text-center">
          <div className="text-2xl font-bold text-white">{summary.totalTasks}</div>
          <div className="text-xs text-zinc-400">Total</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-green-400">{summary.passedTasks}</div>
          <div className="text-xs text-zinc-400">Passed</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-red-400">{summary.failedTasks}</div>
          <div className="text-xs text-zinc-400">Failed</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-zinc-400">{summary.notDoneTasks}</div>
          <div className="text-xs text-zinc-400">Pending</div>
        </div>
      </div>
    </div>
  );
}

// Generate QA Plan Modal
function GenerateQAPlanModal({
  isOpen,
  onClose,
  featureId,
  onGenerated,
}: {
  isOpen: boolean;
  onClose: () => void;
  featureId: string;
  onGenerated: () => void;
}) {
  const [qaLevel, setQALevel] = useState<'basic' | 'standard' | 'comprehensive'>('standard');
  const [testAreas, setTestAreas] = useState<string[]>(['functional', 'ui']);
  const [additionalNotes, setAdditionalNotes] = useState('');

  const { isGenerating, progress, message, error, generate, reset } = useStreamingQAPlanGeneration();
  const toast = useToast();

  const QA_LEVELS = [
    { value: 'basic', label: 'Basic', description: 'Quick smoke tests', tasks: '3-5' },
    { value: 'standard', label: 'Standard', description: 'Comprehensive coverage', tasks: '8-12' },
    { value: 'comprehensive', label: 'Comprehensive', description: 'Full coverage', tasks: '15-20' },
  ];

  const TEST_AREAS = [
    { value: 'functional', label: 'Functional' },
    { value: 'ui', label: 'UI/UX' },
    { value: 'integration', label: 'Integration' },
    { value: 'performance', label: 'Performance' },
    { value: 'security', label: 'Security' },
    { value: 'accessibility', label: 'Accessibility' },
  ];

  const handleGenerate = async () => {
    const customInstructions = `
## QA Configuration
- Level: ${QA_LEVELS.find(l => l.value === qaLevel)?.label}
- Test Areas: ${testAreas.join(', ')}
${additionalNotes ? `- Additional Notes: ${additionalNotes}` : ''}
    `.trim();

    try {
      await generate(
        { issueId: featureId, customInstructions },
        {
          onComplete: (result) => {
            toast.success('QA Plan Generated', `Created ${result.qaTasksCreated} tests`);
            onGenerated();
            setTimeout(() => {
              handleClose();
            }, 500);
          },
          onError: (err) => {
            toast.error('Error', err);
          },
        }
      );
    } catch {
      // Error handled in callback
    }
  };

  const handleClose = () => {
    reset();
    setQALevel('standard');
    setTestAreas(['functional', 'ui']);
    setAdditionalNotes('');
    onClose();
  };

  const toggleArea = (area: string) => {
    setTestAreas(prev =>
      prev.includes(area) ? prev.filter(a => a !== area) : [...prev, area]
    );
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-zinc-900 rounded-lg border border-zinc-700 w-full max-w-lg">
        {/* Header */}
        <div className="px-6 py-4 border-b border-zinc-700">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-yellow-400" />
              Generate QA Plan
            </h2>
            <button
              onClick={handleClose}
              className="text-zinc-400 hover:text-white text-xl"
            >
              &times;
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          {isGenerating ? (
            <div className="py-8">
              <div className="text-center mb-6">
                <div className={cn(
                  'inline-flex items-center justify-center w-16 h-16 rounded-full mb-4',
                  error ? 'bg-red-500/20' : progress >= 100 ? 'bg-green-500/20' : 'bg-blue-500/20'
                )}>
                  {error ? (
                    <XCircle className="w-8 h-8 text-red-500" />
                  ) : progress >= 100 ? (
                    <CheckCircle2 className="w-8 h-8 text-green-500" />
                  ) : (
                    <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  )}
                </div>
                <h3 className="text-white font-medium mb-2">
                  {error ? 'Generation Failed' : progress >= 100 ? 'Complete!' : 'Generating...'}
                </h3>
                <p className={cn('text-sm', error ? 'text-red-400' : 'text-zinc-400')}>
                  {error || message || 'Initializing...'}
                </p>
              </div>
              <ProgressBar
                value={error ? 100 : progress}
                variant={error ? 'error' : 'gradient-blue'}
                size="lg"
                trackClassName="bg-zinc-800"
              />
            </div>
          ) : (
            <div className="space-y-6">
              {/* QA Level */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Testing Level
                </label>
                <div className="space-y-2">
                  {QA_LEVELS.map(level => (
                    <button
                      key={level.value}
                      onClick={() => setQALevel(level.value as typeof qaLevel)}
                      className={cn(
                        'w-full p-3 rounded-lg border text-left transition-all',
                        qaLevel === level.value
                          ? 'border-blue-500 bg-blue-500/10'
                          : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-white">{level.label}</span>
                        <span className="text-xs text-zinc-500">{level.tasks} tests</span>
                      </div>
                      <p className="text-xs text-zinc-400 mt-1">{level.description}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Test Areas */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Test Areas
                </label>
                <div className="flex flex-wrap gap-2">
                  {TEST_AREAS.map(area => (
                    <button
                      key={area.value}
                      onClick={() => toggleArea(area.value)}
                      className={cn(
                        'px-3 py-1.5 rounded-lg text-sm transition-all',
                        testAreas.includes(area.value)
                          ? 'bg-blue-600 text-white'
                          : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
                      )}
                    >
                      {area.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Additional Notes */}
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  Additional Notes (optional)
                </label>
                <textarea
                  value={additionalNotes}
                  onChange={(e) => setAdditionalNotes(e.target.value)}
                  placeholder="Any specific requirements or focus areas..."
                  rows={2}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm resize-none"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {!isGenerating && (
          <div className="px-6 py-4 border-t border-zinc-700 flex justify-end gap-3">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-zinc-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleGenerate}
              disabled={testAreas.length === 0}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
            >
              Generate QA Plan
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// Feature Testing Options Panel Component
function OptionsPanel({
  options,
  onChange,
  isExecuting,
}: {
  options: FeatureTestingOptions;
  onChange: (options: FeatureTestingOptions) => void;
  isExecuting: boolean;
}) {
  const updateOption = <K extends keyof FeatureTestingOptions>(
    key: K,
    value: FeatureTestingOptions[K]
  ) => {
    onChange({ ...options, [key]: value });
  };

  return (
    <div className="bg-zinc-800/50 rounded-lg border border-zinc-700 p-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Execution Options */}
        <div>
          <h4 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4 text-yellow-400" />
            Execution Options
          </h4>
          <div className="space-y-3">
            {/* Max Concurrent */}
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">
                Max Concurrent Tasks (Parallel Mode)
              </label>
              <input
                type="range"
                min={1}
                max={20}
                value={options.maxConcurrent}
                onChange={(e) => updateOption('maxConcurrent', parseInt(e.target.value))}
                disabled={isExecuting}
                className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
              />
              <div className="flex justify-between text-xs text-zinc-500 mt-1">
                <span>1</span>
                <span className="text-blue-400 font-medium">{options.maxConcurrent}</span>
                <span>20</span>
              </div>
            </div>

            {/* Retry Failed */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.retryFailedOnComplete}
                onChange={(e) => updateOption('retryFailedOnComplete', e.target.checked)}
                disabled={isExecuting}
                className="w-4 h-4 rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 disabled:opacity-50"
              />
              <span className="text-sm text-zinc-300">
                <RotateCcw className="w-3 h-3 inline mr-1" />
                Retry failed tests after run
              </span>
            </label>

            {/* Stop on First Failure */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.stopOnFirstFailure}
                onChange={(e) => updateOption('stopOnFirstFailure', e.target.checked)}
                disabled={isExecuting}
                className="w-4 h-4 rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 disabled:opacity-50"
              />
              <span className="text-sm text-zinc-300">
                <AlertTriangle className="w-3 h-3 inline mr-1" />
                Stop on first failure
              </span>
            </label>
          </div>
        </div>

        {/* Filter Options */}
        <div>
          <h4 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
            <Filter className="w-4 h-4 text-blue-400" />
            Filter Options
          </h4>
          <div className="space-y-3">
            {/* Type Filter */}
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Test Type</label>
              <select
                value={options.typeFilter}
                onChange={(e) => updateOption('typeFilter', e.target.value as QATaskType | 'ALL')}
                className="w-full px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded text-sm text-white"
              >
                <option value="ALL">All Types</option>
                <option value="AUTOMATED">Automated Only</option>
                <option value="MANUAL">Manual Only</option>
              </select>
            </div>

            {/* Priority Filter */}
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Priority</label>
              <select
                value={options.priorityFilter}
                onChange={(e) => updateOption('priorityFilter', e.target.value as QAPriority | 'ALL')}
                className="w-full px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded text-sm text-white"
              >
                <option value="ALL">All Priorities</option>
                <option value="CRITICAL">Critical Only</option>
                <option value="HIGH">High & Above</option>
                <option value="MEDIUM">Medium & Above</option>
                <option value="LOW">Low & Above</option>
              </select>
            </div>
          </div>
        </div>

        {/* Behavior & View Options */}
        <div>
          <h4 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-purple-400" />
            Behavior & View
          </h4>
          <div className="space-y-3">
            {/* Auto Create Bugs */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.autoCreateBugs}
                onChange={(e) => updateOption('autoCreateBugs', e.target.checked)}
                disabled={isExecuting}
                className="w-4 h-4 rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 disabled:opacity-50"
              />
              <span className="text-sm text-zinc-300">
                <Bug className="w-3 h-3 inline mr-1" />
                Auto-create bugs on failure
              </span>
            </label>

            {/* Hide Completed */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.hideCompleted}
                onChange={(e) => updateOption('hideCompleted', e.target.checked)}
                className="w-4 h-4 rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
              />
              <span className="text-sm text-zinc-300">
                {options.hideCompleted ? (
                  <EyeOff className="w-3 h-3 inline mr-1" />
                ) : (
                  <Eye className="w-3 h-3 inline mr-1" />
                )}
                Hide passed/failed tests
              </span>
            </label>

            {/* Compact View */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.compactView}
                onChange={(e) => updateOption('compactView', e.target.checked)}
                className="w-4 h-4 rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
              />
              <span className="text-sm text-zinc-300">Compact view</span>
            </label>
          </div>
        </div>
      </div>

      {/* Reset Options */}
      <div className="mt-4 pt-3 border-t border-zinc-700 flex justify-end">
        <button
          onClick={() => onChange(DEFAULT_OPTIONS)}
          className="text-xs text-zinc-400 hover:text-white flex items-center gap-1"
        >
          <RotateCcw className="w-3 h-3" />
          Reset to Defaults
        </button>
      </div>
    </div>
  );
}

// Compact QA Task Card for compact view
function CompactQATaskCard({
  task,
  isSelected,
  isCurrentlyExecuting,
  onSelect,
  onMarkManual,
  onCreateBug,
}: {
  task: QATask;
  isSelected: boolean;
  isCurrentlyExecuting?: boolean;
  onSelect: (id: string) => void;
  onMarkManual: (taskId: string, status: 'PASS' | 'FAILED', result: string) => void;
  onCreateBug: (taskId: string) => void;
}) {
  const statusConfig = STATUS_CONFIG[task.status];
  const StatusIcon = statusConfig.icon;

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-3 py-2 rounded-lg border transition-all',
        isCurrentlyExecuting
          ? 'border-blue-500 bg-blue-900/20'
          : isSelected
          ? 'border-blue-500 bg-zinc-800'
          : 'border-zinc-700 bg-zinc-800/50 hover:bg-zinc-800'
      )}
    >
      {/* Selection */}
      <button
        onClick={() => onSelect(task.id)}
        className="text-zinc-400 hover:text-blue-400"
      >
        {isSelected ? (
          <CheckSquare className="w-4 h-4 text-blue-500" />
        ) : (
          <Square className="w-4 h-4" />
        )}
      </button>

      {/* Status */}
      <span
        className={cn(
          'inline-flex items-center justify-center w-6 h-6 rounded',
          isCurrentlyExecuting ? 'bg-blue-600' : statusConfig.bgColor
        )}
      >
        {isCurrentlyExecuting ? (
          <RefreshCw className="w-3 h-3 text-white animate-spin" />
        ) : (
          <StatusIcon className="w-3 h-3 text-white" />
        )}
      </span>

      {/* Key */}
      <span className="text-xs font-mono text-zinc-500 w-20 truncate">{task.key}</span>

      {/* Title */}
      <span className="flex-1 text-sm text-zinc-200 truncate">{task.title}</span>

      {/* Priority & Type */}
      <span className={cn('text-xs', getQAPriorityColor(task.priority))}>
        {task.priority}
      </span>
      {task.type === 'MANUAL' && (
        <span className="text-xs bg-yellow-900/50 text-yellow-400 px-1.5 rounded">M</span>
      )}

      {/* Actions */}
      {task.status === 'FAILED' && !task.bugIssueId && (
        <button
          onClick={() => onCreateBug(task.id)}
          className="p-1 text-red-400 hover:text-red-300 hover:bg-red-900/30 rounded"
          title="Create Bug"
        >
          <Bug className="w-3 h-3" />
        </button>
      )}
      {task.status === 'NOT_DONE' && task.type === 'MANUAL' && (
        <div className="flex gap-1">
          <button
            onClick={() => onMarkManual(task.id, 'PASS', '')}
            className="p-1 text-green-400 hover:bg-green-900/30 rounded"
            title="Mark Pass"
          >
            <CheckCircle2 className="w-3 h-3" />
          </button>
          <button
            onClick={() => onMarkManual(task.id, 'FAILED', '')}
            className="p-1 text-red-400 hover:bg-red-900/30 rounded"
            title="Mark Failed"
          >
            <XCircle className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

// Main Component
export function FeatureTestingPanel({ featureId, projectId }: FeatureTestingPanelProps) {
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set());
  const [executionMode, setExecutionMode] = useState<'sequential' | 'parallel'>('sequential');
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [statusFilter, setStatusFilter] = useState<QATaskStatus | 'ALL'>('ALL');
  const [executionStartTime, setExecutionStartTime] = useState<Date | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  const [options, setOptions] = useState<FeatureTestingOptions>(DEFAULT_OPTIONS);

  // Hooks
  const { data: qaTasks, isLoading, refetch } = useQATasksForIssue(featureId, projectId, true);
  const { data: qaSummary } = useQASummary(featureId);
  const streamingExecution = useStreamingExecution();
  const markManualQA = useMarkManualQAResult();
  const createBugFromQA = useCreateBugFromQA();
  const toast = useToast();

  // Filter tasks with advanced options
  const filteredTasks = useMemo(() => {
    if (!qaTasks) return [];

    let tasks = qaTasks;

    // Status filter
    if (statusFilter !== 'ALL') {
      tasks = tasks.filter(t => t.status === statusFilter);
    }

    // Type filter from options
    if (options.typeFilter !== 'ALL') {
      tasks = tasks.filter(t => t.type === options.typeFilter);
    }

    // Priority filter from options (includes selected priority and above)
    if (options.priorityFilter !== 'ALL') {
      const priorityOrder: QAPriority[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
      const minPriorityIndex = priorityOrder.indexOf(options.priorityFilter);
      const allowedPriorities = priorityOrder.slice(0, minPriorityIndex + 1);
      tasks = tasks.filter(t => allowedPriorities.includes(t.priority));
    }

    // Hide completed from options
    if (options.hideCompleted) {
      tasks = tasks.filter(t => t.status !== 'PASS' && t.status !== 'FAILED');
    }

    return tasks;
  }, [qaTasks, statusFilter, options.typeFilter, options.priorityFilter, options.hideCompleted]);

  // Get executable tasks
  const executableTasks = useMemo(() => {
    const tasks = selectedTasks.size > 0
      ? filteredTasks.filter(t => selectedTasks.has(t.id) && t.status === 'NOT_DONE' && t.type === 'AUTOMATED')
      : filteredTasks.filter(t => t.status === 'NOT_DONE' && t.type === 'AUTOMATED');
    return tasks;
  }, [filteredTasks, selectedTasks]);

  // Handlers
  const handleSelectTask = useCallback((id: string) => {
    setSelectedTasks(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedTasks(new Set(filteredTasks.map(t => t.id)));
  }, [filteredTasks]);

  const handleDeselectAll = useCallback(() => {
    setSelectedTasks(new Set());
  }, []);

  const handleExecute = async () => {
    if (executableTasks.length === 0) {
      toast.error('No Tasks', 'No executable tasks available');
      return;
    }

    const taskIds = executableTasks.map(t => t.id);

    // Set execution start time for progress tracking
    setExecutionStartTime(new Date());

    // Track failed tasks for potential retry
    const failedTaskIds: string[] = [];

    try {
      await streamingExecution.execute(
        taskIds,
        {
          onTaskComplete: (event) => {
            const icon = event.status === 'PASS' ? '✓' : '✗';
            toast.info(`${icon} ${event.taskKey}`, `${event.status} (${event.executionTime.toFixed(1)}s)`);

            // Track failed tests for retry
            if (event.status === 'FAILED') {
              // Find the task ID by key
              const task = executableTasks.find(t => t.key === event.taskKey);
              if (task) failedTaskIds.push(task.id);

              // Auto-create bug if option enabled
              if (options.autoCreateBugs && task && !task.bugIssueId) {
                createBugFromQA.mutate({ taskId: task.id });
              }
            }

            // Stop on first failure if option enabled
            if (options.stopOnFirstFailure && event.status === 'FAILED') {
              streamingExecution.abort();
            }
          },
          onComplete: async (event) => {
            toast.success('Execution Complete', `${event.passedTasks} passed, ${event.failedTasks} failed`);

            // Retry failed tests if option enabled and there are failures
            if (options.retryFailedOnComplete && failedTaskIds.length > 0) {
              toast.info('Retrying', `Retrying ${failedTaskIds.length} failed tests...`);
              // Reset status to NOT_DONE for retry
              await streamingExecution.execute(
                failedTaskIds,
                {
                  onComplete: (retryEvent) => {
                    toast.success('Retry Complete', `${retryEvent.passedTasks} passed, ${retryEvent.failedTasks} still failing`);
                    setExecutionStartTime(null);
                  },
                  onError: () => {
                    setExecutionStartTime(null);
                  },
                },
                {
                  mode: executionMode,
                  maxConcurrent: options.maxConcurrent,
                }
              );
            } else {
              setExecutionStartTime(null);
            }
          },
          onAborted: () => {
            toast.info('Aborted', 'Execution was stopped');
            setExecutionStartTime(null);
          },
          onError: (event) => {
            toast.error('Error', event.error);
            setExecutionStartTime(null);
          },
        },
        {
          mode: executionMode,
          maxConcurrent: options.maxConcurrent,
        }
      );
      refetch();
    } catch {
      toast.error('Error', 'Failed to execute tests');
      setExecutionStartTime(null);
    }
  };

  const handleMarkManual = async (taskId: string, status: 'PASS' | 'FAILED', result: string) => {
    try {
      await markManualQA.mutateAsync({ taskId, status, actualResult: result });
      toast.success('Marked', `Test marked as ${status}`);
      refetch();
    } catch {
      toast.error('Error', 'Failed to mark test result');
    }
  };

  const handleCreateBug = async (taskId: string) => {
    try {
      const result = await createBugFromQA.mutateAsync({ taskId });
      toast.success('Bug Created', `Created ${result.bugKey}`);
      refetch();
    } catch {
      toast.error('Error', 'Failed to create bug');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <SummaryCard summary={qaSummary || null} />

      {/* Toolbar */}
      <div className="bg-zinc-800 rounded-lg border border-zinc-700 p-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            {/* Filter */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-400">Filter:</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as QATaskStatus | 'ALL')}
                className="px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded text-sm text-white"
              >
                <option value="ALL">All ({qaTasks?.length || 0})</option>
                <option value="NOT_DONE">Pending ({qaTasks?.filter(t => t.status === 'NOT_DONE').length || 0})</option>
                <option value="PASS">Passed ({qaTasks?.filter(t => t.status === 'PASS').length || 0})</option>
                <option value="FAILED">Failed ({qaTasks?.filter(t => t.status === 'FAILED').length || 0})</option>
              </select>
            </div>

            {/* Selection */}
            <div className="flex items-center gap-2 border-l border-zinc-700 pl-4">
              <span className="text-sm text-zinc-400">Select:</span>
              <button
                onClick={handleSelectAll}
                className="text-sm text-blue-400 hover:text-blue-300"
              >
                All
              </button>
              <button
                onClick={handleDeselectAll}
                className="text-sm text-zinc-400 hover:text-white"
              >
                None
              </button>
              {selectedTasks.size > 0 && (
                <span className="text-sm text-blue-400">
                  ({selectedTasks.size} selected)
                </span>
              )}
            </div>

            {/* Execution Mode */}
            <div className="flex items-center gap-2 border-l border-zinc-700 pl-4">
              <span className="text-sm text-zinc-400">Mode:</span>
              <select
                value={executionMode}
                onChange={(e) => setExecutionMode(e.target.value as 'sequential' | 'parallel')}
                disabled={streamingExecution.isExecuting}
                className="px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded text-sm text-white disabled:opacity-50"
              >
                <option value="sequential">Sequential</option>
                <option value="parallel">Parallel ({options.maxConcurrent}x)</option>
              </select>
            </div>

            {/* Options Toggle */}
            <button
              onClick={() => setShowOptions(!showOptions)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors border-l border-zinc-700 ml-2 pl-4",
                showOptions || countActiveOptions(options) > 0
                  ? "text-blue-400"
                  : "text-zinc-400 hover:text-white"
              )}
            >
              <Settings2 className="w-4 h-4" />
              Options
              {countActiveOptions(options) > 0 && (
                <span className="inline-flex items-center justify-center w-5 h-5 text-xs bg-blue-600 text-white rounded-full">
                  {countActiveOptions(options)}
                </span>
              )}
              <ChevronDown className={cn("w-3 h-3 transition-transform", showOptions && "rotate-180")} />
            </button>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowGenerateModal(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white rounded text-sm"
            >
              <Sparkles className="w-4 h-4 text-yellow-400" />
              Generate Tests
            </button>

            {streamingExecution.isExecuting ? (
              <button
                onClick={() => streamingExecution.abort()}
                className="flex items-center gap-2 px-4 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-sm"
              >
                <StopCircle className="w-4 h-4" />
                Stop
              </button>
            ) : (
              <button
                onClick={handleExecute}
                disabled={executableTasks.length === 0}
                className="flex items-center gap-2 px-4 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {executionMode === 'parallel' ? (
                  <Zap className="w-4 h-4" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                Run Tests ({executableTasks.length})
              </button>
            )}
          </div>
        </div>

        {/* Options Panel */}
        {showOptions && (
          <div className="mt-4 pt-4 border-t border-zinc-700">
            <OptionsPanel
              options={options}
              onChange={setOptions}
              isExecuting={streamingExecution.isExecuting}
            />
          </div>
        )}

        {/* Test Progress Tracker - shows during and after execution */}
        {(streamingExecution.isExecuting || streamingExecution.taskResults.length > 0) && (
          <div className="mt-4 pt-4 border-t border-zinc-700">
            <TestProgressTracker
              isExecuting={streamingExecution.isExecuting}
              executionMode={streamingExecution.executionMode}
              progress={streamingExecution.progress}
              completedTasks={streamingExecution.completedTasks}
              totalTasks={streamingExecution.totalTasks}
              currentTaskKey={streamingExecution.currentTaskKey}
              currentTaskTitle={streamingExecution.currentTaskTitle}
              tasksInFlight={streamingExecution.tasksInFlight}
              maxConcurrent={streamingExecution.maxConcurrent}
              taskResults={streamingExecution.taskResults}
              error={streamingExecution.error}
              startTime={executionStartTime}
              defaultExpanded={false}
            />
          </div>
        )}
      </div>

      {/* Task List */}
      <div className={cn("space-y-3", options.compactView && "space-y-1")}>
        {filteredTasks.length === 0 ? (
          <div className="bg-zinc-800 rounded-lg border border-zinc-700 p-8 text-center">
            <FlaskConical className="w-12 h-12 text-zinc-600 mx-auto mb-4" />
            <p className="text-zinc-400 mb-4">
              {qaTasks && qaTasks.length > 0
                ? 'No tests match the current filters'
                : 'No QA tests found for this feature'}
            </p>
            {qaTasks && qaTasks.length > 0 ? (
              <button
                onClick={() => {
                  setStatusFilter('ALL');
                  setOptions(DEFAULT_OPTIONS);
                }}
                className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white rounded"
              >
                <RotateCcw className="w-4 h-4" />
                Reset Filters
              </button>
            ) : (
              <button
                onClick={() => setShowGenerateModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded"
              >
                <Sparkles className="w-4 h-4" />
                Generate QA Plan
              </button>
            )}
          </div>
        ) : options.compactView ? (
          // Compact view
          filteredTasks.map(task => (
            <CompactQATaskCard
              key={task.id}
              task={task}
              isSelected={selectedTasks.has(task.id)}
              isCurrentlyExecuting={streamingExecution.currentTaskKey === task.key}
              onSelect={handleSelectTask}
              onMarkManual={handleMarkManual}
              onCreateBug={handleCreateBug}
            />
          ))
        ) : (
          // Default view
          filteredTasks.map(task => (
            <QATaskCard
              key={task.id}
              task={task}
              isSelected={selectedTasks.has(task.id)}
              isCurrentlyExecuting={streamingExecution.currentTaskKey === task.key}
              onSelect={handleSelectTask}
              onMarkManual={handleMarkManual}
              onCreateBug={handleCreateBug}
            />
          ))
        )}
      </div>

      {/* Generate Modal */}
      <GenerateQAPlanModal
        isOpen={showGenerateModal}
        onClose={() => setShowGenerateModal(false)}
        featureId={featureId}
        onGenerated={() => refetch()}
      />
    </div>
  );
}
