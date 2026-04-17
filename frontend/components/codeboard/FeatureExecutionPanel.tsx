'use client';

/**
 * Feature Execution Panel — UI-only task selection and AutoPilot launcher.
 *
 * The execution loop now lives in AutoPilotContext (providers.tsx).
 * This panel builds the queue, lets users select tasks / choose per-task
 * actions, and calls `autoPilot.startAutoPilot()`. Closing the panel
 * does NOT stop AutoPilot — execution continues in the background.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  X, Play, CheckCircle2, Circle, ChevronRight, ChevronDown,
  Loader2, AlertCircle, SkipForward, Rocket,
  ArrowRight, Clock, Zap, Eye, RotateCcw
} from 'lucide-react';
import {
  Issue,
  IssueType,
  ISSUE_TYPES,
  AutoPilotConfig,
  DEFAULT_AUTO_PILOT_CONFIG,
  ExecutionMode,
} from '@/types/codeboard';
import { useIssueDescendants } from '@/hooks/useCodeBoard';
import { useAutoPilot } from '@/contexts/AutoPilotContext';
import type { AutoPilotQueueItem } from '@/contexts/AutoPilotContext';
import { cn } from '@/lib/utils';
import { AutoPilotConfigModal } from './AutoPilotConfigModal';

interface FeatureExecutionPanelProps {
  feature: Issue;
  allIssues: Issue[];
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  onIssueClick?: (issue: Issue) => void;
}

// Get all descendant issues of a parent
function getDescendants(parentId: string, allIssues: Issue[]): Issue[] {
  const children = allIssues.filter(i => i.parentId === parentId);
  let descendants = [...children];
  for (const child of children) {
    descendants = [...descendants, ...getDescendants(child.id, allIssues)];
  }
  return descendants;
}

// Build hierarchy tree
function buildHierarchy(issues: Issue[]): Map<string | null, Issue[]> {
  const hierarchy = new Map<string | null, Issue[]>();
  for (const issue of issues) {
    const parentId = issue.parentId || null;
    if (!hierarchy.has(parentId)) {
      hierarchy.set(parentId, []);
    }
    hierarchy.get(parentId)!.push(issue);
  }
  return hierarchy;
}

// Get type order for sorting
function getTypeOrder(type: IssueType): number {
  const order: Record<IssueType, number> = {
    'FEATURE': 0, 'EPIC': 1, 'STORY': 2, 'TASK': 3, 'SUBTASK': 4, 'BUG': 3,
  };
  return order[type] ?? 5;
}

function sortByHierarchy(issues: Issue[]): Issue[] {
  return [...issues].sort((a, b) => getTypeOrder(a.type) - getTypeOrder(b.type));
}

export function FeatureExecutionPanel({
  feature,
  allIssues,
  projectId,
  isOpen,
  onClose,
  onIssueClick,
}: FeatureExecutionPanelProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set([feature.id]));
  const [showTaskActionSelector, setShowTaskActionSelector] = useState(false);
  const [taskActions, setTaskActions] = useState<Map<string, ExecutionMode | 'skip'>>(new Map());
  const [showAutoPilotModal, setShowAutoPilotModal] = useState(false);

  const autoPilot = useAutoPilot();
  const isExecuting = autoPilot.state.isActive && autoPilot.state.featureId === feature.id;

  // Fetch all descendants from the backend API
  const { data: descendants = [], isLoading: isLoadingDescendants } = useIssueDescendants(
    isOpen ? feature.id : null
  );

  // All issues under this feature
  const featureIssues = useMemo(() => [feature, ...descendants], [feature, descendants]);

  // Build hierarchy map
  const hierarchy = useMemo(() => buildHierarchy(featureIssues), [featureIssues]);

  // Calculate progress
  const progress = useMemo(() => {
    const total = featureIssues.length;
    const done = featureIssues.filter(i => i.status === 'DONE').length;
    return {
      total,
      done,
      percent: total > 0 ? Math.round((done / total) * 100) : 0,
    };
  }, [featureIssues]);

  // Items already completed
  const completedItems = useMemo(() => {
    return featureIssues.filter(i =>
      (i.type === 'TASK' || i.type === 'SUBTASK') &&
      (i.status === 'DONE' || i.status === 'COMPLETED_WAITING_QA')
    );
  }, [featureIssues]);

  // Executable items (TASKs and SUBTASKs only)
  const executableItems = useMemo(() => {
    return featureIssues.filter(i => {
      if (i.type !== 'TASK' && i.type !== 'SUBTASK') return false;
      if (i.status === 'CANCELLED') return false;
      if (showTaskActionSelector) return true;
      const action = taskActions.get(i.id);
      if (action === 'skip') return false;
      return true;
    });
  }, [featureIssues, showTaskActionSelector, taskActions]);

  // Check for completed items on open
  useEffect(() => {
    if (isOpen && !isExecuting) {
      setTaskActions(new Map());
      if (completedItems.length > 0) {
        const actions = new Map<string, ExecutionMode | 'skip'>();
        for (const item of completedItems) {
          actions.set(item.id, 'skip');
        }
        setTaskActions(actions);
        setShowTaskActionSelector(true);
      } else {
        setShowTaskActionSelector(false);
        setSelectedIds(new Set(executableItems.map(i => i.id)));
      }
    }
  }, [isOpen, completedItems.length, feature.id, isExecuting]);

  // Apply task actions → set selection
  const applyTaskActions = useCallback(() => {
    const allLeafTasks = featureIssues.filter(i =>
      (i.type === 'TASK' || i.type === 'SUBTASK') && i.status !== 'CANCELLED'
    );
    const ids = allLeafTasks
      .filter(i => taskActions.get(i.id) !== 'skip')
      .map(i => i.id);
    setSelectedIds(new Set(ids));
    setShowTaskActionSelector(false);
  }, [featureIssues, taskActions]);

  const toggleSelection = (issueId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(issueId)) next.delete(issueId);
      else next.add(issueId);
      return next;
    });
  };

  const toggleExpand = (issueId: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(issueId)) next.delete(issueId);
      else next.add(issueId);
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(executableItems.map(i => i.id)));
  const deselectAll = () => setSelectedIds(new Set());

  // Build queue and start AutoPilot (backend-driven)
  const handleStartExecution = async () => {
    const selected = executableItems.filter(i => selectedIds.has(i.id));
    if (selected.length === 0) return;

    const sorted = sortByHierarchy(selected);
    const queue: AutoPilotQueueItem[] = sorted.map((issue, index) => ({
      issue,
      status: 'pending',
      order: index,
    }));

    // Close panel first — execution continues in backend
    onClose();

    await autoPilot.startAutoPilot({
      feature,
      projectId,
      queue,
      config: DEFAULT_AUTO_PILOT_CONFIG,
      taskActions: new Map(taskActions),
    });
  };

  const handleStartAutoPilot = async (config: AutoPilotConfig) => {
    const selected = executableItems.filter(i => selectedIds.has(i.id));
    if (selected.length === 0) return;

    const sorted = sortByHierarchy(selected);
    const queue: AutoPilotQueueItem[] = sorted.map((issue, index) => ({
      issue,
      status: 'pending',
      order: index,
    }));

    // Close panel first — execution continues in backend
    onClose();

    await autoPilot.startAutoPilot({
      feature,
      projectId,
      queue,
      config,
      taskActions: new Map(taskActions),
    });
  };

  // Render issue row
  const renderIssueRow = (issue: Issue, depth: number = 0) => {
    const children = hierarchy.get(issue.id) || [];
    const hasChildren = children.length > 0;
    const isExpanded = expandedIds.has(issue.id);
    const isExecutable = issue.type === 'TASK' || issue.type === 'SUBTASK';
    const isSelected = selectedIds.has(issue.id);
    const isDone = issue.status === 'DONE';
    const isWaitingQA = issue.status === 'COMPLETED_WAITING_QA';
    const isInProgress = issue.status === 'IN_PROGRESS';

    // If AutoPilot is running for this feature, show queue status
    const queueItem = isExecuting
      ? autoPilot.state.queue.find(q => q.issue_id === issue.id)
      : undefined;

    const typeConfig = ISSUE_TYPES.find(t => t.type === issue.type);

    return (
      <div key={issue.id}>
        <div
          className={cn(
            'flex items-center gap-2 py-2 px-3 rounded-lg transition-colors',
            'hover:bg-zinc-800/50',
            isInProgress && 'bg-yellow-900/20 border-l-2 border-yellow-500',
            isWaitingQA && 'bg-orange-900/20 border-l-2 border-orange-500',
            isDone && 'opacity-60',
            queueItem?.status === 'running' && 'bg-cyan-900/30 border-l-2 border-cyan-500',
            queueItem?.status === 'completed' && 'bg-green-900/20',
            queueItem?.status === 'failed' && 'bg-red-900/20',
          )}
          style={{ paddingLeft: `${depth * 24 + 12}px` }}
        >
          {/* Expand toggle */}
          {hasChildren ? (
            <button onClick={() => toggleExpand(issue.id)} className="p-0.5 hover:bg-zinc-700 rounded">
              {isExpanded ? <ChevronDown className="w-4 h-4 text-zinc-400" /> : <ChevronRight className="w-4 h-4 text-zinc-400" />}
            </button>
          ) : (
            <div className="w-5" />
          )}

          {/* Selection checkbox (only when not executing) */}
          {isExecutable && !isExecuting ? (
            <button
              onClick={() => toggleSelection(issue.id)}
              className={cn(
                'w-5 h-5 rounded border flex items-center justify-center transition-colors',
                isSelected ? 'bg-cyan-600 border-cyan-600' : 'border-zinc-600 hover:border-zinc-400'
              )}
              disabled={isDone}
            >
              {isSelected && <CheckCircle2 className="w-3 h-3 text-white" />}
            </button>
          ) : (
            <div className="w-5 h-5 flex items-center justify-center">
              {queueItem?.status === 'running' && <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />}
              {queueItem?.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-green-400" />}
              {queueItem?.status === 'failed' && <AlertCircle className="w-4 h-4 text-red-400" />}
              {!queueItem && isDone && <CheckCircle2 className="w-4 h-4 text-green-400" />}
            </div>
          )}

          {/* Type icon */}
          <span className={cn('text-sm', typeConfig?.color)}>{typeConfig?.icon}</span>

          {/* Issue key */}
          <span className="text-xs font-mono text-zinc-500">{issue.key}</span>

          {/* Title */}
          <button
            onClick={() => onIssueClick?.(issue)}
            className="flex-1 text-left text-sm text-zinc-200 hover:text-white truncate"
          >
            {issue.title}
          </button>

          {/* Status badge */}
          <span className={cn(
            'text-xs px-2 py-0.5 rounded',
            issue.status === 'DONE' && 'bg-green-900/50 text-green-400',
            issue.status === 'COMPLETED_WAITING_QA' && 'bg-orange-900/50 text-orange-400',
            issue.status === 'IN_PROGRESS' && 'bg-yellow-900/50 text-yellow-400',
            issue.status === 'TODO' && 'bg-blue-900/50 text-blue-400',
            issue.status === 'BACKLOG' && 'bg-zinc-800 text-zinc-400',
          )}>
            {issue.status === 'COMPLETED_WAITING_QA' ? 'WAITING QA' : issue.status.replace('_', ' ')}
          </span>
        </div>

        {/* Children */}
        {hasChildren && isExpanded && (
          <div>{sortByHierarchy(children).map(child => renderIssueRow(child, depth + 1))}</div>
        )}
      </div>
    );
  };

  // Don't render if not open
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-700">
          <div className="flex items-center gap-3">
            <Rocket className="w-6 h-6 text-amber-500" />
            <div>
              <h2 className="font-semibold text-lg">Feature Implementation</h2>
              <p className="text-sm text-zinc-400">{feature.title}</p>
            </div>
            {isExecuting && (
              <span className="text-xs px-2 py-1 bg-amber-900/40 text-amber-300 rounded-full font-medium">
                AutoPilot Running
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress bar */}
        <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-zinc-300">
              Overall Progress: {progress.done}/{progress.total} items
            </span>
            <span className="text-sm font-medium text-cyan-400">{progress.percent}%</span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-600 to-green-500 transition-all duration-500"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        </div>

        {/* AutoPilot execution progress (read from context) */}
        {isExecuting && (
          <div className={cn(
            "px-6 py-3 border-b border-zinc-800",
            autoPilot.state.isPaused && autoPilot.state.lastError ? "bg-red-900/20" : "bg-cyan-900/10"
          )}>
            <div className="flex items-center gap-3">
              {autoPilot.state.isPaused ? (
                <AlertCircle className="w-5 h-5 text-yellow-400" />
              ) : (
                <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" />
              )}
              <span className={cn("text-sm", autoPilot.state.isPaused ? "text-yellow-300" : "text-cyan-300")}>
                {autoPilot.state.isPaused ? 'Paused' : 'Executing'}: {autoPilot.state.progress.completed + autoPilot.state.progress.skipped}/{autoPilot.state.progress.total}
              </span>
              {autoPilot.state.queue[autoPilot.state.currentIndex] && (
                <span className="text-sm text-zinc-400">
                  - {autoPilot.state.queue[autoPilot.state.currentIndex].issue_title}
                </span>
              )}
            </div>
            {autoPilot.state.lastError && (
              <div className="mt-2 p-2 bg-red-900/30 border border-red-600/30 rounded text-sm text-red-300">
                <strong>Error:</strong> {autoPilot.state.lastError}
              </div>
            )}
            <p className="mt-2 text-xs text-zinc-500">
              Use the floating bar (bottom-right) to pause, skip, or abort.
            </p>
          </div>
        )}

        {/* Selection controls (only when not executing) */}
        {!isExecuting && (
          <div className="flex items-center justify-between px-6 py-3 border-b border-zinc-800">
            <div className="flex items-center gap-3">
              <button onClick={selectAll} className="text-sm text-cyan-400 hover:text-cyan-300">Select All Tasks</button>
              <span className="text-zinc-600">|</span>
              <button onClick={deselectAll} className="text-sm text-zinc-400 hover:text-zinc-300">Deselect All</button>
            </div>
            <span className="text-sm text-zinc-400">{selectedIds.size} items selected</span>
          </div>
        )}

        {/* Per-task action selector for completed tasks */}
        {showTaskActionSelector && completedItems.length > 0 && !isExecuting && (
          <div className="border-b border-zinc-700 bg-amber-900/20">
            <div className="px-6 py-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertCircle className="w-5 h-5 text-amber-400" />
                <div>
                  <p className="text-sm text-amber-200">
                    {completedItems.length} task{completedItems.length > 1 ? 's' : ''} already completed — choose action per task
                  </p>
                  <p className="text-xs text-amber-400/70 mt-0.5">
                    Skip, audit existing code, or rewrite from scratch
                  </p>
                </div>
              </div>
              <button
                onClick={applyTaskActions}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-sm font-medium"
              >
                Continue
              </button>
            </div>
            {/* Task action table */}
            <div className="max-h-64 overflow-y-auto px-6 pb-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-zinc-500 text-xs">
                    <th className="text-left py-1 pr-2 font-medium">Key</th>
                    <th className="text-left py-1 pr-2 font-medium">Title</th>
                    <th className="text-left py-1 pr-2 font-medium">Status</th>
                    <th className="text-right py-1 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {completedItems.map(item => {
                    const action = taskActions.get(item.id) || 'skip';
                    return (
                      <tr key={item.id} className="border-t border-zinc-800">
                        <td className="py-1.5 pr-2 text-zinc-400 font-mono text-xs">{item.key}</td>
                        <td className="py-1.5 pr-2 text-zinc-300 truncate max-w-[200px]">{item.title}</td>
                        <td className="py-1.5 pr-2">
                          <span className={cn(
                            'text-xs px-1.5 py-0.5 rounded',
                            item.status === 'DONE' ? 'bg-green-900/50 text-green-400' : 'bg-orange-900/50 text-orange-400'
                          )}>
                            {item.status === 'DONE' ? 'Done' : 'Waiting QA'}
                          </span>
                        </td>
                        <td className="py-1.5 text-right">
                          <div className="inline-flex rounded-md overflow-hidden border border-zinc-700">
                            <button
                              onClick={() => setTaskActions(prev => new Map(prev).set(item.id, 'skip'))}
                              className={cn(
                                'px-2.5 py-1 text-xs font-medium transition-colors flex items-center gap-1',
                                action === 'skip' ? 'bg-zinc-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                              )}
                            >
                              <SkipForward className="w-3 h-3" /> Skip
                            </button>
                            <button
                              onClick={() => setTaskActions(prev => new Map(prev).set(item.id, 'audit'))}
                              className={cn(
                                'px-2.5 py-1 text-xs font-medium transition-colors flex items-center gap-1 border-l border-zinc-700',
                                action === 'audit' ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                              )}
                            >
                              <Eye className="w-3 h-3" /> Audit
                            </button>
                            <button
                              onClick={() => setTaskActions(prev => new Map(prev).set(item.id, 'rewrite'))}
                              className={cn(
                                'px-2.5 py-1 text-xs font-medium transition-colors flex items-center gap-1 border-l border-zinc-700',
                                action === 'rewrite' ? 'bg-red-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                              )}
                            >
                              <RotateCcw className="w-3 h-3" /> Rewrite
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* Apply to All shortcuts */}
            <div className="px-6 pb-3 flex items-center gap-2 text-xs text-zinc-500">
              <span>Apply to all:</span>
              <button
                onClick={() => {
                  const actions = new Map<string, ExecutionMode | 'skip'>();
                  for (const item of completedItems) actions.set(item.id, 'skip');
                  setTaskActions(actions);
                }}
                className="text-zinc-400 hover:text-white transition-colors underline"
              >
                Skip All
              </button>
              <span>/</span>
              <button
                onClick={() => {
                  const actions = new Map<string, ExecutionMode | 'skip'>();
                  for (const item of completedItems) actions.set(item.id, 'audit');
                  setTaskActions(actions);
                }}
                className="text-blue-400 hover:text-blue-300 transition-colors underline"
              >
                Audit All
              </button>
              <span>/</span>
              <button
                onClick={() => {
                  const actions = new Map<string, ExecutionMode | 'skip'>();
                  for (const item of completedItems) actions.set(item.id, 'rewrite');
                  setTaskActions(actions);
                }}
                className="text-red-400 hover:text-red-300 transition-colors underline"
              >
                Rewrite All
              </button>
            </div>
          </div>
        )}

        {/* Issue hierarchy */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoadingDescendants ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin mb-4" />
              <p className="text-zinc-400 text-sm">Loading issue hierarchy...</p>
            </div>
          ) : (
            renderIssueRow(feature)
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-700 bg-zinc-900/50">
          <div className="text-sm text-zinc-500">
            <Clock className="w-4 h-4 inline mr-1" />
            {executableItems.length} executable tasks
          </div>
          {!isExecuting ? (
            <div className="flex items-center gap-3">
              <button
                onClick={handleStartExecution}
                disabled={selectedIds.size === 0}
                className={cn(
                  'flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-colors',
                  selectedIds.size > 0
                    ? 'bg-zinc-700 hover:bg-zinc-600 text-zinc-200'
                    : 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
                )}
              >
                <Play className="w-4 h-4" />
                Manual Start
              </button>
              <button
                onClick={() => setShowAutoPilotModal(true)}
                disabled={selectedIds.size === 0}
                className={cn(
                  'flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-colors',
                  selectedIds.size > 0
                    ? 'bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white'
                    : 'bg-zinc-700 text-zinc-400 cursor-not-allowed'
                )}
              >
                <Zap className="w-5 h-5" />
                Auto Pilot
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1 bg-amber-900/30 border border-amber-600/30 rounded text-sm">
                <Zap className="w-4 h-4 text-amber-400" />
                <span className="text-amber-200">AutoPilot Active</span>
              </div>
              <span className="text-sm text-cyan-400">
                {autoPilot.state.isPaused ? 'Paused' : 'Running...'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Auto Pilot Configuration Modal */}
      <AutoPilotConfigModal
        isOpen={showAutoPilotModal}
        onClose={() => setShowAutoPilotModal(false)}
        onStart={handleStartAutoPilot}
        taskCount={selectedIds.size}
      />
    </div>
  );
}
