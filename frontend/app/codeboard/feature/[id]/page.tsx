'use client';

/**
 * Feature Detail Page - Shows all issues under a FEATURE with hierarchy.
 *
 * CB-2696: The inline tree/toolbar/search/tabs block has been replaced by
 * <HierarchyTreeSection> (extracted in CB-2684/CB-2685).  This page now owns
 * only the feature-level shell:
 *   - Back button + SSE indicator + key badge + title
 *   - Overall progress bars (Completed / Done)
 *   - Manual-execute + Auto Pilot header buttons
 *   - Status-by-type summary grid
 *   - Delete feature button
 *   - Execution modal + progress bar
 *   - FeatureExecutionPanel (AutoPilot modal)
 */

import { useState, useMemo, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Zap,
  Loader2,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import {
  useIssues,
  useIssue,
  useDeleteIssue,
  useFeatureLiveData,
} from '@/hooks/useCodeBoard';
import { Issue, IssueType } from '@/types/codeboard';
import {
  FeatureExecutionPanel,
  HierarchyTreeSection,
} from '@/components/codeboard';
import { cn } from '@/lib/utils';
import { isExecutableType } from '@/lib/codeboard';
import { useAutoPilot } from '@/contexts/AutoPilotContext';

// Type colors — dark mode defaults; light mode handled by globals.css .light overrides
const TYPE_CONFIG: Record<IssueType, { color: string; icon: string }> = {
  FEATURE: { color: 'text-blue-400', icon: '🚀' },
  EPIC: { color: 'text-purple-400', icon: '⚡' },
  STORY: { color: 'text-blue-400', icon: '📖' },
  TASK: { color: 'text-green-400', icon: '✓' },
  SUBTASK: { color: 'text-gray-400', icon: '○' },
  BUG: { color: 'text-red-400', icon: '🐛' },
};

interface TreeNode extends Issue {
  children: TreeNode[];
}

function buildShallowTree(issues: Issue[], rootId: string): TreeNode[] {
  function buildNode(issue: Issue): TreeNode {
    const children = issues
      .filter((i) => i.parentId === issue.id)
      .map((child) => buildNode(child));
    return { ...issue, children };
  }
  return issues
    .filter((i) => i.parentId === rootId)
    .map((child) => buildNode(child));
}

export default function FeatureDetailPage() {
  const params = useParams();
  const router = useRouter();
  const featureId = params.id as string;

  // Back-to-board navigation — prefers browser history (preserves CodeBoard state).
  const navigateBackToBoard = useCallback(() => {
    const sameOriginReferrer =
      typeof document !== 'undefined' &&
      document.referrer &&
      (() => {
        try {
          return new URL(document.referrer).origin === window.location.origin;
        } catch {
          return false;
        }
      })();
    if (sameOriginReferrer || (typeof window !== 'undefined' && window.history.length > 1)) {
      router.back();
    } else {
      router.push('/codeboard');
    }
  }, [router]);

  // Fetch the feature issue
  const { data: feature, isLoading: featureLoading } = useIssue(featureId);

  // Live data from SSE
  const { hasActiveSessions, sseConnected } = useFeatureLiveData(feature?.projectId || null);

  // Fetch all issues for progress calculations
  const { data: issuesData, isLoading: issuesLoading, refetch } = useIssues(
    feature?.projectId || null,
    { pageSize: 1000, refetchInterval: hasActiveSessions ? 3000 : false },
  );

  const deleteIssue = useDeleteIssue();

  // Auto Pilot panel visibility
  const [showAutoPilotPanel, setShowAutoPilotPanel] = useState(false);
  const autoPilot = useAutoPilot();
  const isAutoPilotRunningForThis =
    autoPilot.state.isActive && autoPilot.state.featureId === featureId;

  // Build tree purely for progress calculations (no rendering — HierarchyTreeSection renders the tree)
  const tree = useMemo(() => {
    if (!feature || !issuesData?.items) return [] as TreeNode[];
    const allIssues = issuesData.items;
    const descendants = new Set<string>();
    function collectDescendants(parentId: string) {
      allIssues.forEach((issue) => {
        if (issue.parentId === parentId && !descendants.has(issue.id)) {
          descendants.add(issue.id);
          collectDescendants(issue.id);
        }
      });
    }
    collectDescendants(featureId);
    return buildShallowTree(
      allIssues.filter((i) => descendants.has(i.id)),
      featureId,
    );
  }, [feature, issuesData, featureId]);

  // Overall progress (TASKs + SUBTASKs + BUGs only)
  const overallProgress = useMemo(() => {
    let done = 0;
    let waitingQA = 0;
    let total = 0;
    function count(nodes: TreeNode[]) {
      for (const node of nodes) {
        if (node.type === 'TASK' || node.type === 'SUBTASK' || node.type === 'BUG') {
          total++;
          if (node.status === 'DONE') done++;
          else if (node.status === 'COMPLETED_WAITING_QA') waitingQA++;
        }
        if (node.children.length > 0) count(node.children);
      }
    }
    count(tree);
    const completed = done + waitingQA;
    return {
      done,
      waitingQA,
      completed,
      total,
      percent: total > 0 ? Math.round((completed / total) * 100) : 0,
      allDone: done === total && total > 0,
      allWaitingQA: waitingQA > 0 && done === 0 && completed === total,
    };
  }, [tree]);

  // Count by type with status breakdown (for the summary grid)
  const typeStatusCounts = useMemo(() => {
    const counts: Record<IssueType, { total: number; completed: number; done: number }> = {
      FEATURE: { total: 0, completed: 0, done: 0 },
      EPIC: { total: 0, completed: 0, done: 0 },
      STORY: { total: 0, completed: 0, done: 0 },
      TASK: { total: 0, completed: 0, done: 0 },
      SUBTASK: { total: 0, completed: 0, done: 0 },
      BUG: { total: 0, completed: 0, done: 0 },
    };
    function count(nodes: TreeNode[]) {
      for (const node of nodes) {
        counts[node.type].total++;
        if (node.status === 'COMPLETED_WAITING_QA') counts[node.type].completed++;
        if (node.status === 'DONE') counts[node.type].done++;
        count(node.children);
      }
    }
    count(tree);
    return counts;
  }, [tree]);

  // Executable tasks for header buttons
  const executableTasks = useMemo(() => {
    const tasks: Issue[] = [];
    function collect(nodes: TreeNode[]) {
      for (const node of nodes) {
        if (isExecutableType(node.type) && node.status !== 'DONE') tasks.push(node);
        collect(node.children);
      }
    }
    collect(tree);
    return tasks;
  }, [tree]);

  // ─── Delete feature ─────────────────────────────────────────────────────────

  const handleDeleteFeature = useCallback(async () => {
    if (!feature) return;
    const descendantCount = tree.reduce((acc, node) => {
      function count(n: TreeNode): number {
        return 1 + n.children.reduce((sum, child) => sum + count(child), 0);
      }
      return acc + count(node);
    }, 0);

    const message =
      descendantCount > 0
        ? `Delete "${feature.title}" and all ${descendantCount} child issues? This cannot be undone.`
        : `Delete "${feature.title}"? This cannot be undone.`;

    if (!confirm(message)) return;

    const allIssues = issuesData?.items || [];
    const descendants = allIssues.filter((i) => {
      let current = i;
      while (current.parentId) {
        if (current.parentId === featureId) return true;
        current = allIssues.find((p) => p.id === current.parentId) as Issue;
        if (!current) break;
      }
      return false;
    });

    const sortedDescendants = descendants.sort((a, b) => {
      const getDepth = (issue: Issue): number => {
        let depth = 0;
        let current = issue;
        while (current.parentId) {
          depth++;
          current = allIssues.find((p) => p.id === current.parentId) as Issue;
          if (!current) break;
        }
        return depth;
      };
      return getDepth(b) - getDepth(a);
    });

    for (const desc of sortedDescendants) {
      try {
        await deleteIssue.mutateAsync(desc.id);
      } catch (e) {
        console.error(`Failed to delete ${desc.key}:`, e);
      }
    }

    try {
      await deleteIssue.mutateAsync(featureId);
      navigateBackToBoard();
    } catch (e) {
      console.error('Failed to delete feature:', e);
      alert('Failed to delete feature');
    }
  }, [feature, tree, issuesData, featureId, deleteIssue, navigateBackToBoard]);

  // ─── Loading / error states ──────────────────────────────────────────────────

  if (featureLoading || issuesLoading) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="mx-auto animate-pulse">
          <div className="h-8 bg-zinc-700 rounded w-1/3 mb-4" />
          <div className="h-4 bg-zinc-700 rounded w-2/3 mb-8" />
          <div className="space-y-3">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="h-12 bg-zinc-700 rounded" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!feature) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="mx-auto text-center py-12">
          <h1 className="text-2xl font-bold text-zinc-100">Feature not found</h1>
          <button
            onClick={navigateBackToBoard}
            className="mt-4 text-blue-400 hover:text-blue-300"
          >
            Back to CodeBoard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-900">
      {/* Header */}
      <div className="bg-zinc-800 border-b border-zinc-700 sticky top-0 z-10">
        <div className="mx-auto px-6 py-4">
          <div className="flex items-center gap-4 mb-4">
            <button
              onClick={navigateBackToBoard}
              className="p-2 rounded-lg hover:bg-zinc-700 text-zinc-300"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm px-2 py-1 rounded-full font-medium bg-blue-900/50 text-blue-400">
                  🚀 FEATURE
                </span>
                <span className="text-sm font-mono text-zinc-400">{feature.key}</span>
                {/* SSE connection indicator */}
                <span
                  className={cn(
                    'flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full',
                    sseConnected
                      ? 'text-green-400 bg-green-900/20'
                      : hasActiveSessions
                      ? 'text-yellow-400 bg-yellow-900/20'
                      : 'text-zinc-600',
                  )}
                  title={
                    sseConnected
                      ? 'Live: SSE connected'
                      : hasActiveSessions
                      ? 'Polling fallback (SSE disconnected)'
                      : 'Idle'
                  }
                >
                  {sseConnected ? (
                    <Wifi className="w-3 h-3" />
                  ) : hasActiveSessions ? (
                    <WifiOff className="w-3 h-3" />
                  ) : null}
                  {hasActiveSessions && (sseConnected ? 'LIVE' : 'POLL')}
                </span>
              </div>
              <h1 className="text-xl font-bold text-zinc-100 mt-1">{feature.title}</h1>
            </div>

            {/* Delete Feature Button */}
            <button
              onClick={handleDeleteFeature}
              className="p-2 rounded-lg hover:bg-red-900/50 text-zinc-400 hover:text-red-400 transition-colors"
              title="Delete Feature"
            >
              <Trash2 className="w-5 h-5" />
            </button>
          </div>

          {/* Progress Overview — Two Bars */}
          <div className="flex items-center gap-6">
            <div className="flex-1 space-y-2">
              {/* Completed (Waiting QA) Bar */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-blue-400">Completed</span>
                  <span className="text-sm text-zinc-400">
                    {overallProgress.waitingQA} / {overallProgress.total}
                  </span>
                  <span className="text-xs text-zinc-500">(waiting QA)</span>
                </div>
                <div className="h-2 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-700 rounded-full transition-all duration-500"
                    style={{
                      width: `${
                        overallProgress.total > 0
                          ? (overallProgress.waitingQA / overallProgress.total) * 100
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>
              {/* Done Bar */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-green-400">Done</span>
                  <span className="text-sm text-zinc-400">
                    {overallProgress.done} / {overallProgress.total}
                  </span>
                  <span className="text-xs text-zinc-500">(verified)</span>
                </div>
                <div className="h-2 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500 rounded-full transition-all duration-500"
                    style={{
                      width: `${
                        overallProgress.total > 0
                          ? (overallProgress.done / overallProgress.total) * 100
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="text-right">
              <div className="text-lg font-bold text-blue-400">
                {overallProgress.total > 0
                  ? Math.round((overallProgress.waitingQA / overallProgress.total) * 100)
                  : 0}
                %
              </div>
              <div className="text-lg font-bold text-green-400">
                {overallProgress.total > 0
                  ? Math.round((overallProgress.done / overallProgress.total) * 100)
                  : 0}
                %
              </div>
            </div>

            {/* Execution Buttons */}
            <div className="flex items-center gap-2">
              {/* Auto Pilot Button */}
              <button
                onClick={() => setShowAutoPilotPanel(true)}
                disabled={executableTasks.length === 0}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors',
                  isAutoPilotRunningForThis
                    ? 'bg-blue-800 text-blue-200 ring-2 ring-blue-500/50'
                    : executableTasks.length === 0
                    ? 'bg-zinc-700 text-zinc-400 cursor-not-allowed'
                    : 'bg-gradient-to-r from-blue-700 to-blue-600 hover:from-blue-600 hover:to-blue-500 text-white',
                )}
                title={
                  isAutoPilotRunningForThis
                    ? 'AutoPilot is running — click to view'
                    : 'Launch Auto Pilot with full control panel'
                }
              >
                {isAutoPilotRunningForThis ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                {isAutoPilotRunningForThis
                  ? `AutoPilot ${
                      autoPilot.state.progress.completed + autoPilot.state.progress.skipped
                    }/${autoPilot.state.progress.total}`
                  : `Auto Pilot (${executableTasks.length})`}
              </button>
            </div>
          </div>

          {/* Status by Type Summary */}
          <div className="mt-4 grid grid-cols-5 gap-3">
            {(['EPIC', 'STORY', 'TASK', 'SUBTASK', 'BUG'] as IssueType[]).map((type) => {
              const counts = typeStatusCounts[type];
              if (counts.total === 0) return null;
              const tc = TYPE_CONFIG[type];
              return (
                <div
                  key={type}
                  className="p-2 rounded-lg bg-zinc-700/50 border border-zinc-600"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={cn('text-xs font-medium', tc.color)}>
                      {tc.icon} {type}s
                    </span>
                    <span className="text-xs text-zinc-400">
                      {counts.completed + counts.done}/{counts.total}
                    </span>
                  </div>
                  <div className="h-1.5 bg-zinc-600 rounded-full overflow-hidden">
                    <div className="h-full flex">
                      <div
                        className="h-full bg-green-500"
                        style={{
                          width: `${
                            counts.total > 0 ? (counts.done / counts.total) * 100 : 0
                          }%`,
                        }}
                      />
                      <div
                        className="h-full bg-blue-700"
                        style={{
                          width: `${
                            counts.total > 0 ? (counts.completed / counts.total) * 100 : 0
                          }%`,
                        }}
                      />
                    </div>
                  </div>
                  <div className="flex justify-between mt-1 text-[10px]">
                    <span className="text-blue-400">{counts.completed} waiting</span>
                    <span className="text-green-400">{counts.done} done</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Hierarchy Tree — tabs, search, toolbar, tree, testing panel */}
      <div className="mx-auto px-6 py-4">
        <HierarchyTreeSection
          issueId={featureId}
          projectId={feature.projectId}
          viewKind="feature"
        />
      </div>

      {/* Auto Pilot Panel */}
      {feature && issuesData?.items && showAutoPilotPanel && (
        <FeatureExecutionPanel
          feature={feature}
          allIssues={issuesData.items}
          projectId={feature.projectId}
          isOpen={showAutoPilotPanel}
          onClose={() => {
            setShowAutoPilotPanel(false);
            refetch();
          }}
          onIssueClick={(issue) => {
            router.push(`/codeboard/issue/${issue.id}`);
          }}
        />
      )}
    </div>
  );
}
