'use client';

/**
 * HierarchyTreeSection
 *
 * Extracted from frontend/app/codeboard/feature/[id]/page.tsx (CB-2684 / CB-2685).
 *
 * Renders the full hierarchy tree for any root issue (FEATURE, BUG, etc.):
 *   - TreeNode + buildTree + recursive rendering
 *   - Auto Pilot button + executable-task count
 *   - All Done! / Refresh actions
 *   - Tabs: Overview / Testing
 *   - FeatureSearchBar within tree
 *   - Type-toggle selectors: EPICs / STORYs / TASKs / SUBTASKs / BUGs
 *   - Bulk actions: Select All / None / Expand / Collapse / All → Waiting QA / All → Done
 *   - Per-row inline progress bar
 *
 * NOTE (CB-2689 audit):
 *   useFeatureLiveData is NOT hardcoded to FEATURE — it only cares about
 *   `projectId` for session filtering, so it works identically for BUG or
 *   TASK roots.  The only FEATURE-specific piece was the "Auto Pilot" button
 *   label; that is now controlled by the `viewKind` prop.
 *
 * This component is purely extraction — the feature page still uses its own
 * inline code until E2 wires it in.
 */

import {
  useState,
  useMemo,
  useCallback,
  useEffect,
  useRef,
  memo,
} from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { useUrlState, enumParam, stringSetParam } from '@/hooks/use-url-state';
import {
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  Circle,
  Clock,
  XCircle,
  AlertCircle,
  Rocket,
  RefreshCw,
  Square,
  CheckSquare,
  MinusSquare,
  ClipboardCheck,
  FlaskConical,
  ListTree,
  Zap,
  Loader2,
  Search,
  Terminal,
  Play,
} from 'lucide-react';
import {
  useIssues,
  useIssue,
  useUpdateIssue,
  useStartExecution,
  useFeatureLiveData,
  type ExecutionSession,
} from '@/hooks/useCodeBoard';
import { Issue, IssueStatus, IssueType } from '@/types/codeboard';
import {
  FeatureSearchBar,
  applyFeatureSearchFilters,
  DEFAULT_FEATURE_SEARCH_FILTERS,
  FeatureTestingPanel,
  InlineTerminalPanel,
  FeatureExecutionPanel,
} from '@/components/codeboard';
import type { FeatureSearchFilters } from '@/components/codeboard';
import {
  EpicSearchBar,
  applyEpicSearchFilters,
  DEFAULT_EPIC_SEARCH_FILTERS,
  RelevanceBadge,
  highlightEpicMatch,
} from '@/components/codeboard/EpicSearchBar';
import type { EpicSearchFilters } from '@/components/codeboard/EpicSearchBar';
import { cn } from '@/lib/utils';
import { isExecutableType } from '@/lib/codeboard';
import { highlightMatch } from '@/components/codeboard/IssueSearchBar';
import { useAutoPilot } from '@/contexts/AutoPilotContext';
import { AutoPilotStatusBadge } from '@/components/codeboard/AutoPilotStatusBadge';

// ─── Props ────────────────────────────────────────────────────────────────────

export interface HierarchyTreeSectionProps {
  /** The root issue whose descendants we render. */
  issueId: string;
  /** Used for data-fetching context (project-scoped issue list + live sessions). */
  projectId: string;
  /**
   * Controls minor label tweaks in the toolbar.
   *   'feature' → shows Auto Pilot button referencing featureId
   *   'bug' / 'task' → Auto Pilot button omitted (not applicable)
   * Defaults to 'feature'.
   */
  viewKind?: 'feature' | 'bug' | 'task';
}

// ─── Internal types ───────────────────────────────────────────────────────────

interface TreeNode extends Issue {
  children: TreeNode[];
  level: number;
}

// ─── Status / type configuration ─────────────────────────────────────────────

const STATUS_CONFIG: Record<
  IssueStatus,
  {
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    bg: string;
    darkBg: string;
  }
> = {
  BACKLOG: { icon: Circle, color: 'text-gray-400', bg: 'bg-gray-100', darkBg: 'bg-gray-700' },
  TODO: { icon: Circle, color: 'text-blue-500', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30' },
  IN_PROGRESS: { icon: Clock, color: 'text-yellow-500', bg: 'bg-yellow-100', darkBg: 'bg-yellow-900/30' },
  IN_REVIEW: { icon: AlertCircle, color: 'text-purple-500', bg: 'bg-purple-100', darkBg: 'bg-purple-900/30' },
  COMPLETED_WAITING_QA: { icon: Clock, color: 'text-blue-700', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30' },
  DONE: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-100', darkBg: 'bg-green-900/30' },
  CANCELLED: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-100', darkBg: 'bg-red-900/30' },
};

const TYPE_CONFIG: Record<IssueType, { color: string; bg: string; darkBg: string; icon: string }> = {
  FEATURE: { color: 'text-blue-400', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30', icon: '🚀' },
  EPIC: { color: 'text-purple-400', bg: 'bg-purple-100', darkBg: 'bg-purple-900/30', icon: '⚡' },
  STORY: { color: 'text-blue-400', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30', icon: '📖' },
  TASK: { color: 'text-green-400', bg: 'bg-green-100', darkBg: 'bg-green-900/30', icon: '✓' },
  SUBTASK: { color: 'text-gray-400', bg: 'bg-gray-100', darkBg: 'bg-gray-700', icon: '○' },
  BUG: { color: 'text-red-400', bg: 'bg-red-100', darkBg: 'bg-red-900/30', icon: '🐛' },
};

// ─── Pure tree helpers ────────────────────────────────────────────────────────

function buildTree(issues: Issue[], rootId: string): TreeNode[] {
  function buildNode(issue: Issue, level: number): TreeNode {
    const children = issues
      .filter((i) => i.parentId === issue.id)
      .map((child) => buildNode(child, level + 1))
      .sort((a, b) => {
        const typeOrder: Record<string, number> = {
          EPIC: 0,
          STORY: 1,
          TASK: 2,
          BUG: 2,
          SUBTASK: 3,
        };
        const typeCompare = (typeOrder[a.type] ?? 99) - (typeOrder[b.type] ?? 99);
        if (typeCompare !== 0) return typeCompare;
        return a.sequence - b.sequence;
      });

    return { ...issue, children, level };
  }

  return issues
    .filter((i) => i.parentId === rootId)
    .map((child) => buildNode(child, 0))
    .sort((a, b) => a.sequence - b.sequence);
}

function calculateProgress(node: TreeNode): {
  done: number;
  waitingQA: number;
  total: number;
} {
  if (node.children.length === 0) {
    return {
      done: node.status === 'DONE' ? 1 : 0,
      waitingQA: node.status === 'COMPLETED_WAITING_QA' ? 1 : 0,
      total: 1,
    };
  }

  let done = 0;
  let waitingQA = 0;
  let total = 0;

  for (const child of node.children) {
    const p = calculateProgress(child);
    done += p.done;
    waitingQA += p.waitingQA;
    total += p.total;
  }

  return { done, waitingQA, total };
}

function collectAllDescendantIds(node: TreeNode): string[] {
  const ids: string[] = [];
  function collect(n: TreeNode) {
    for (const child of n.children) {
      ids.push(child.id);
      collect(child);
    }
  }
  collect(node);
  return ids;
}

function hasSelectedDescendants(node: TreeNode, selected: Set<string>): boolean {
  for (const child of node.children) {
    if (selected.has(child.id)) return true;
    if (hasSelectedDescendants(child, selected)) return true;
  }
  return false;
}

function allDescendantsSelected(node: TreeNode, selected: Set<string>): boolean {
  if (node.children.length === 0) return true;
  for (const child of node.children) {
    if (!selected.has(child.id)) return false;
    if (!allDescendantsSelected(child, selected)) return false;
  }
  return true;
}

// ─── TreeItem ────────────────────────────────────────────────────────────────

interface TreeItemProps {
  node: TreeNode;
  expanded: Set<string>;
  selected: Set<string>;
  onToggle: (id: string) => void;
  onSelect: (id: string, node: TreeNode) => void;
  onStatusChange: (id: string, status: IssueStatus) => void;
  onNavigate: (issue: Issue) => void;
  searchQuery?: string;
  epicSearchFilters?: Map<string, EpicSearchFilters>;
  epicSearchVisibleIds?: Map<
    string,
    { visibleIds: Set<string>; matchIds: Set<string>; scores: Map<string, number> }
  >;
  onEpicSearchToggle?: (epicId: string) => void;
  onEpicSearchChange?: (epicId: string, filters: EpicSearchFilters) => void;
  allDescendantIssues?: Array<{
    id: string;
    parentId?: string;
    title: string;
    key: string;
    description?: string;
    type: string;
    status: string;
    priority: string;
    labels?: string;
    createdAt: string;
    updatedAt: string;
    dueDate?: string;
    startedAt?: string;
    completedAt?: string;
  }>;
  activeSessionMap?: Map<string, ExecutionSession>;
  onRunningTaskClick?: (issueId: string) => void;
  onRunNow?: (node: TreeNode) => void;
}

const TreeItem = memo(function TreeItem({
  node,
  expanded,
  selected,
  onToggle,
  onSelect,
  onStatusChange,
  onNavigate,
  searchQuery,
  epicSearchFilters,
  epicSearchVisibleIds,
  onEpicSearchToggle,
  onEpicSearchChange,
  allDescendantIssues,
  activeSessionMap,
  onRunningTaskClick,
  onRunNow,
}: TreeItemProps) {
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [statusDropdownPos, setStatusDropdownPos] = useState<{
    top: number;
    left: number;
    direction: 'up' | 'down';
  }>({ top: 0, left: 0, direction: 'down' });
  const statusBtnRef = useRef<HTMLButtonElement>(null);
  const statusDropdownRef = useRef<HTMLDivElement>(null);

  // Close on outside click. Dropdown renders via Portal into document.body
  // (CB-1939: nested rendering inside the row's DOM subtree was getting
  // covered by the page background div due to stacking-context confinement;
  // portal escapes all parent stacking contexts and renders at root.)
  useEffect(() => {
    if (!showStatusDropdown) return;
    const handleOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (statusBtnRef.current?.contains(target)) return;
      if (statusDropdownRef.current?.contains(target)) return;
      setShowStatusDropdown(false);
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [showStatusDropdown]);

  const isExpanded = expanded.has(node.id);
  const isSelected = selected.has(node.id);
  const hasChildren = node.children.length > 0;
  const StatusIcon = STATUS_CONFIG[node.status].icon;
  const typeConfig = TYPE_CONFIG[node.type];
  const runningSession = activeSessionMap?.get(node.id);
  const progress = calculateProgress(node);
  const completedCount = progress.done + progress.waitingQA;
  const progressPercent =
    progress.total > 0 ? Math.round((completedCount / progress.total) * 100) : 0;
  const allWaitingQA =
    progress.waitingQA > 0 && progress.done === 0 && completedCount === progress.total;
  const allDone = progress.done === progress.total;

  // Epic search state — CB-1122
  const isEpic = node.type === 'EPIC';
  const epicFilters = isEpic ? epicSearchFilters?.get(node.id) : undefined;
  const epicSearchResult = isEpic ? epicSearchVisibleIds?.get(node.id) : undefined;
  const hasEpicSearch = !!epicFilters;

  const epicDescendantCount = useMemo(() => {
    if (!isEpic || !allDescendantIssues) return 0;
    function countDescendants(parentId: string): number {
      let count = 0;
      for (const issue of allDescendantIssues!) {
        if (issue.parentId === parentId) {
          count += 1 + countDescendants(issue.id);
        }
      }
      return count;
    }
    return countDescendants(node.id);
  }, [isEpic, allDescendantIssues, node.id]);

  const filteredChildren = useMemo(() => {
    if (!epicSearchResult || !hasEpicSearch) return node.children;
    const hasAnyFilter =
      epicFilters!.query ||
      epicFilters!.types.length > 0 ||
      epicFilters!.statuses.length > 0 ||
      epicFilters!.priorities.length > 0 ||
      (epicFilters!.dateField && (epicFilters!.dateRange.start || epicFilters!.dateRange.end));
    if (!hasAnyFilter) return node.children;

    function filterNodes(nodes: TreeNode[]): TreeNode[] {
      return nodes
        .filter((n) => epicSearchResult!.visibleIds.has(n.id))
        .map((n) => ({
          ...n,
          children: filterNodes(n.children),
        }));
    }
    return filterNodes(node.children);
  }, [node.children, epicSearchResult, hasEpicSearch, epicFilters]);

  const someDescendantsSelected = hasChildren && hasSelectedDescendants(node, selected);
  const allDescendants = hasChildren && allDescendantsSelected(node, selected);
  const isIndeterminate = someDescendantsSelected && !allDescendants && !isSelected;

  const allStatuses: IssueStatus[] = [
    'BACKLOG',
    'TODO',
    'IN_PROGRESS',
    'IN_REVIEW',
    'COMPLETED_WAITING_QA',
    'DONE',
    'CANCELLED',
  ];

  const activeSearchQuery =
    hasEpicSearch && epicFilters?.query ? epicFilters.query : searchQuery;
  const isEpicSearchQuery = !!(hasEpicSearch && epicFilters?.query);

  const relevanceScore = epicSearchResult?.scores.get(node.id) ?? 0;
  const isDirectMatch = epicSearchResult?.matchIds.has(node.id) ?? false;

  return (
    <div className="select-none">
      <div
        className={cn(
          'flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-zinc-700/50 cursor-pointer group transition-all duration-300',
          'border-l-4',
          runningSession
            ? 'border-l-cyan-400 bg-cyan-950/20 animate-pulse'
            : node.status === 'DONE'
            ? 'border-l-green-500'
            : node.status === 'COMPLETED_WAITING_QA'
            ? 'border-l-blue-700'
            : node.status === 'IN_PROGRESS'
            ? 'border-l-yellow-500'
            : node.status === 'IN_REVIEW'
            ? 'border-l-purple-500'
            : 'border-l-zinc-600',
          isSelected && 'bg-blue-900/20',
        )}
        style={{ paddingLeft: `${node.level * 24 + 12}px` }}
      >
        {/* Expand/Collapse */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(node.id);
          }}
          className={cn(
            'w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-600 text-zinc-400',
            !hasChildren && 'invisible',
          )}
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>

        {/* Selection Checkbox */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelect(node.id, node);
          }}
          className="w-5 h-5 flex items-center justify-center text-zinc-400 hover:text-blue-400"
          title={isSelected ? 'Deselect (and all children)' : 'Select (and all children)'}
        >
          {isSelected || (hasChildren && allDescendants) ? (
            <CheckSquare className="w-4 h-4 text-blue-500" />
          ) : isIndeterminate ? (
            <MinusSquare className="w-4 h-4 text-blue-400" />
          ) : (
            <Square className="w-4 h-4" />
          )}
        </button>

        {/* Type Badge */}
        <span
          className={cn(
            'text-xs px-2 py-0.5 rounded-full font-medium',
            node.type === 'EPIC'
              ? 'bg-purple-900/50 text-purple-400'
              : node.type === 'STORY'
              ? 'bg-blue-900/50 text-blue-400'
              : node.type === 'TASK'
              ? 'bg-green-900/50 text-green-400'
              : node.type === 'SUBTASK'
              ? 'bg-zinc-700 text-zinc-400'
              : node.type === 'BUG'
              ? 'bg-red-900/50 text-red-400'
              : 'bg-blue-900/50 text-blue-400',
          )}
        >
          {typeConfig.icon} {node.type}
        </span>

        {/* Issue Key */}
        <span className="text-xs font-mono text-zinc-500">{node.key}</span>

        {/* Running indicator + terminal button */}
        {runningSession && (
          <>
            <Loader2 className="w-4 h-4 text-cyan-400 animate-spin shrink-0" />
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRunningTaskClick?.(node.id);
              }}
              className="p-1 rounded hover:bg-cyan-900/50 text-cyan-400 hover:text-cyan-300 shrink-0 transition-colors"
              title="Open live terminal"
            >
              <Terminal className="w-4 h-4" />
            </button>
          </>
        )}

        {/* Title - Clickable */}
        <span
          className={cn(
            'flex-1 text-sm font-medium truncate',
            runningSession ? 'text-cyan-200 hover:text-cyan-100' : 'text-zinc-100 hover:text-blue-400',
          )}
          onClick={() => onNavigate(node)}
        >
          {activeSearchQuery
            ? isEpicSearchQuery
              ? highlightEpicMatch(node.title, activeSearchQuery)
              : highlightMatch(node.title, activeSearchQuery)
            : node.title}
        </span>

        {/* Relevance badge for epic search results — CB-1123 */}
        {hasEpicSearch && epicFilters?.query && (
          <RelevanceBadge score={relevanceScore} isDirectMatch={isDirectMatch} />
        )}

        {/* Epic Search Toggle — CB-1122/CB-1123 */}
        {isEpic && hasChildren && onEpicSearchToggle && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onEpicSearchToggle(node.id);
            }}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all',
              hasEpicSearch
                ? 'bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30'
                : 'text-zinc-500 hover:text-purple-400 hover:bg-zinc-700 border border-transparent hover:border-purple-500/30',
            )}
            title={hasEpicSearch ? 'Close epic search' : 'Search within this epic'}
          >
            <Search className="w-3.5 h-3.5" />
            {!hasEpicSearch && <span className="hidden group-hover:inline">Search</span>}
          </button>
        )}

        {/* Status Dropdown — portaled to document.body to escape stacking contexts (CB-1939) */}
        <div className="relative">
          <button
            ref={statusBtnRef}
            onClick={(e) => {
              e.stopPropagation();
              const btn = e.currentTarget as HTMLElement;
              const r = btn.getBoundingClientRect();
              const spaceBelow = window.innerHeight - r.bottom;
              const direction: 'up' | 'down' = spaceBelow < 280 ? 'up' : 'down';
              const dropdownH = 264;
              setStatusDropdownPos({
                top: direction === 'up' ? r.top - dropdownH - 4 : r.bottom + 4,
                left: r.right - 180,
                direction,
              });
              setShowStatusDropdown(!showStatusDropdown);
            }}
            className={cn(
              'flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium min-w-[140px]',
              'bg-zinc-700 border border-zinc-600 hover:border-zinc-500',
            )}
          >
            <StatusIcon className={cn('w-3.5 h-3.5', STATUS_CONFIG[node.status].color)} />
            <span className={STATUS_CONFIG[node.status].color}>
              {node.status.replace(/_/g, ' ')}
            </span>
            <ChevronDown className="w-3 h-3 ml-auto text-zinc-400" />
          </button>
        </div>

        {showStatusDropdown &&
          typeof document !== 'undefined' &&
          createPortal(
            <div
              ref={statusDropdownRef}
              className="fixed z-[9999] bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl py-1 min-w-[180px]"
              style={{ top: statusDropdownPos.top, left: statusDropdownPos.left }}
            >
              {allStatuses.map((status) => {
                const config = STATUS_CONFIG[status];
                const Icon = config.icon;
                return (
                  <button
                    key={status}
                    onClick={(e) => {
                      e.stopPropagation();
                      onStatusChange(node.id, status);
                      setShowStatusDropdown(false);
                    }}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-zinc-700 text-left',
                      node.status === status && 'bg-zinc-700',
                    )}
                  >
                    <Icon className={cn('w-4 h-4', config.color)} />
                    <span className={config.color}>{status.replace(/_/g, ' ')}</span>
                    {node.status === status && (
                      <CheckCircle2 className="w-3 h-3 ml-auto text-green-500" />
                    )}
                  </button>
                );
              })}
            </div>,
            document.body,
          )}

        {/* Progress */}
        <div className="flex items-center gap-2">
          <div className="w-20 h-2 bg-zinc-700 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500',
                allDone
                  ? 'bg-green-500'
                  : allWaitingQA
                  ? 'bg-blue-700'
                  : progressPercent === 100
                  ? 'bg-blue-700'
                  : progressPercent > 50
                  ? 'bg-blue-500'
                  : progressPercent > 0
                  ? 'bg-yellow-500'
                  : 'bg-zinc-600',
              )}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span
            className={cn(
              'text-xs w-12 text-right',
              allDone ? 'text-green-400' : allWaitingQA ? 'text-blue-400' : 'text-zinc-500',
            )}
          >
            {completedCount}/{progress.total}
          </span>
        </div>

        {/* Run Now button — CB-2791 */}
        {onRunNow && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRunNow(node);
            }}
            className="opacity-60 hover:opacity-100 p-1 rounded bg-emerald-900/30 hover:bg-emerald-900/60 text-emerald-400 hover:text-emerald-300 transition-all shrink-0"
            title={`Run ${node.key} now`}
            data-testid={`run-now-${node.id}`}
          >
            <Play className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Epic Search Bar — CB-1122 / CB-1123 */}
      {isEpic && hasEpicSearch && epicFilters && onEpicSearchChange && (
        <div
          className="border-l-4 border-l-purple-500/30 bg-purple-900/10 animate-in slide-in-from-top-1 duration-200"
          style={{ paddingLeft: `${node.level * 24 + 12}px` }}
        >
          <div className="px-3 py-2">
            <EpicSearchBar
              filters={epicFilters}
              onChange={(f) => onEpicSearchChange(node.id, f)}
              resultCount={epicSearchResult?.visibleIds.size ?? epicDescendantCount}
              totalCount={epicDescendantCount}
              matchCount={epicSearchResult?.matchIds.size}
              epicKey={node.key}
              autoFocus={true}
            />
          </div>
        </div>
      )}

      {/* Children */}
      {isExpanded && hasChildren && (
        <div>
          {filteredChildren.map((child) => (
            <TreeItem
              key={child.id}
              node={child}
              expanded={expanded}
              selected={selected}
              onToggle={onToggle}
              onSelect={onSelect}
              onStatusChange={onStatusChange}
              onNavigate={onNavigate}
              searchQuery={activeSearchQuery}
              epicSearchFilters={epicSearchFilters}
              epicSearchVisibleIds={epicSearchVisibleIds}
              onEpicSearchToggle={onEpicSearchToggle}
              onEpicSearchChange={onEpicSearchChange}
              allDescendantIssues={allDescendantIssues}
              activeSessionMap={activeSessionMap}
              onRunningTaskClick={onRunningTaskClick}
              onRunNow={onRunNow}
            />
          ))}
        </div>
      )}
    </div>
  );
});

// ─── HierarchyTreeSection ─────────────────────────────────────────────────────

export function HierarchyTreeSection({
  issueId,
  projectId,
  viewKind = 'feature',
}: HierarchyTreeSectionProps) {
  const router = useRouter();

  // Live session data
  const { activeSessionMap, hasActiveSessions } = useFeatureLiveData(projectId);

  // Fetch all issues for the project — polls every 3s when sessions are active
  const {
    data: issuesData,
    isLoading: issuesLoading,
    refetch,
  } = useIssues(projectId, {
    pageSize: 1000,
    refetchInterval: hasActiveSessions ? 3000 : false,
  });

  const updateIssue = useUpdateIssue();

  // Inline terminal state
  const [activeTerminalIssueId, setActiveTerminalIssueId] = useState<string | null>(null);
  const activeTerminalSession = activeTerminalIssueId
    ? activeSessionMap.get(activeTerminalIssueId)
    : null;

  // Search / filter state — CB-1119
  const [searchFilters, setSearchFilters] = useState<FeatureSearchFilters>(
    DEFAULT_FEATURE_SEARCH_FILTERS,
  );

  // URL-backed tab + expanded tree — survives back/refresh
  const [{ tab: activeTab, expanded }, setUrlState] = useUrlState({
    tab: enumParam('tab', ['overview', 'testing'] as const, 'overview'),
    expanded: stringSetParam('expanded'),
  });
  const setActiveTab = (v: 'overview' | 'testing') => setUrlState({ tab: v });
  // Memoised wrapper so that consumers (handleToggle etc.) get a stable ref
  // when `expanded` has not changed between renders. Must include `expanded`
  // because the functional-updater form passes it as `prev`.
  const setExpanded = useCallback(
    (next: Set<string> | ((prev: Set<string>) => Set<string>)) =>
      setUrlState({ expanded: typeof next === 'function' ? next(expanded) : next }),
    [setUrlState, expanded],
  );

  // Selection state
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Auto Pilot panel visibility — CB-2727
  const [showAutoPilotPanel, setShowAutoPilotPanel] = useState(false);

  // Run Now context — CB-2791: per-row play button
  const [runNowContext, setRunNowContext] = useState<Issue | null>(null);
  const [runNowSelected, setRunNowSelected] = useState<Set<string>>(new Set());

  // Root issue — needed to pass to FeatureExecutionPanel
  const { data: rootIssue } = useIssue(issueId);

  // Execution hook for single-task Run Now
  const startExecution = useStartExecution();

  // Auto Pilot — works for any root issue type (FEATURE, BUG, TASK)
  const autoPilot = useAutoPilot();
  const isAutoPilotRunningForThis =
    autoPilot.state.isActive &&
    autoPilot.state.featureId === issueId;

  // Epic search state — CB-1122
  const [epicSearchFilters, setEpicSearchFilters] = useState<Map<string, EpicSearchFilters>>(
    new Map(),
  );

  const handleEpicSearchToggle = useCallback((epicId: string) => {
    setEpicSearchFilters((prev) => {
      const next = new Map(prev);
      if (next.has(epicId)) {
        next.delete(epicId);
      } else {
        next.set(epicId, { ...DEFAULT_EPIC_SEARCH_FILTERS });
      }
      return next;
    });
  }, []);

  const handleEpicSearchChange = useCallback((epicId: string, filters: EpicSearchFilters) => {
    setEpicSearchFilters((prev) => {
      const next = new Map(prev);
      next.set(epicId, filters);
      return next;
    });
  }, []);

  // Build the tree
  const tree = useMemo(() => {
    if (!issuesData?.items) return [];

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

    collectDescendants(issueId);

    const relevantIssues = allIssues.filter((i) => descendants.has(i.id));
    return buildTree(relevantIssues, issueId);
  }, [issuesData, issueId]);

  // All descendants flat list — used for search filtering
  const allDescendantIssues = useMemo(() => {
    if (!issuesData?.items) return [];
    const descendants = new Set<string>();
    function collectDescendants(parentId: string) {
      issuesData!.items.forEach((issue) => {
        if (issue.parentId === parentId && !descendants.has(issue.id)) {
          descendants.add(issue.id);
          collectDescendants(issue.id);
        }
      });
    }
    collectDescendants(issueId);
    return issuesData.items.filter((i) => descendants.has(i.id));
  }, [issuesData, issueId]);

  const visibleIssueIds = useMemo(
    () => applyFeatureSearchFilters(allDescendantIssues, searchFilters),
    [allDescendantIssues, searchFilters],
  );

  // Compute epic search results for each active epic search — CB-1122
  const epicSearchVisibleIds = useMemo(() => {
    const results = new Map<
      string,
      { visibleIds: Set<string>; matchIds: Set<string>; scores: Map<string, number> }
    >();

    for (const [epicId, filters] of epicSearchFilters.entries()) {
      const epicDescendants = allDescendantIssues.filter((issue) => {
        let current = issue;
        while (current) {
          if (current.parentId === epicId) return true;
          current = allDescendantIssues.find(
            (i) => i.id === current.parentId,
          ) as typeof current;
          if (!current) break;
        }
        return false;
      });

      const result = applyEpicSearchFilters(epicDescendants, filters);
      results.set(epicId, result);
    }

    return results;
  }, [epicSearchFilters, allDescendantIssues]);

  // Auto-expand epic children when epic search is active — CB-1122
  useEffect(() => {
    for (const [epicId, filters] of epicSearchFilters.entries()) {
      const hasAnyFilter =
        filters.query ||
        filters.types.length > 0 ||
        filters.statuses.length > 0 ||
        filters.priorities.length > 0 ||
        (filters.dateField && (filters.dateRange.start || filters.dateRange.end));

      if (hasAnyFilter) {
        const searchResult = epicSearchVisibleIds.get(epicId);
        if (searchResult) {
          setExpanded((prev) => {
            const next = new Set(prev);
            next.add(epicId);
            for (const id of searchResult.visibleIds) {
              const issue = allDescendantIssues.find((i) => i.id === id);
              if (issue) {
                const hasVisibleChildren = allDescendantIssues.some(
                  (child) =>
                    child.parentId === id && searchResult.visibleIds.has(child.id),
                );
                if (hasVisibleChildren) {
                  next.add(id);
                }
              }
            }
            return next;
          });
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [epicSearchFilters, epicSearchVisibleIds, allDescendantIssues]);

  // Filter tree based on feature search — CB-1119
  const filteredTree = useMemo(() => {
    const hasAnyFilter =
      searchFilters.query ||
      searchFilters.types.length > 0 ||
      searchFilters.statuses.length > 0 ||
      searchFilters.priorities.length > 0 ||
      (searchFilters.dateField &&
        (searchFilters.dateRange.start || searchFilters.dateRange.end));

    if (!hasAnyFilter) return tree;

    function filterNodes(nodes: TreeNode[]): TreeNode[] {
      return nodes
        .filter((node) => visibleIssueIds.has(node.id))
        .map((node) => ({
          ...node,
          children: filterNodes(node.children),
        }));
    }

    return filterNodes(tree);
  }, [tree, visibleIssueIds, searchFilters]);

  // Auto-expand visible nodes when search is active — CB-1119
  useEffect(() => {
    const hasAnyFilter =
      searchFilters.query ||
      searchFilters.types.length > 0 ||
      searchFilters.statuses.length > 0 ||
      searchFilters.priorities.length > 0 ||
      (searchFilters.dateField &&
        (searchFilters.dateRange.start || searchFilters.dateRange.end));

    if (hasAnyFilter) {
      const expandIds = new Set<string>();
      function collectExpandable(nodes: TreeNode[]) {
        for (const node of nodes) {
          if (node.children.length > 0 && visibleIssueIds.has(node.id)) {
            expandIds.add(node.id);
            collectExpandable(node.children);
          }
        }
      }
      collectExpandable(tree);
      setExpanded(expandIds);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchFilters, visibleIssueIds, tree]);

  // Get all executable tasks (respects selection)
  const executableTasks = useMemo(() => {
    const tasks: Issue[] = [];
    function collectTasks(nodes: TreeNode[]) {
      for (const node of nodes) {
        if (isExecutableType(node.type) && node.status !== 'DONE') {
          if (selected.size === 0 || selected.has(node.id)) {
            tasks.push(node);
          }
        }
        collectTasks(node.children);
      }
    }
    collectTasks(tree);
    return tasks;
  }, [tree, selected]);

  // ─── Handlers ──────────────────────────────────────────────────────────────

  const handleToggle = useCallback(
    (id: string) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return next;
      });
    },
    [setExpanded],
  );

  const handleExpandAll = () => {
    const allIds = new Set<string>();
    function collect(nodes: TreeNode[]) {
      for (const node of nodes) {
        if (node.children.length > 0) {
          allIds.add(node.id);
          collect(node.children);
        }
      }
    }
    collect(tree);
    setExpanded(allIds);
  };

  const handleCollapseAll = () => {
    setExpanded(new Set());
  };

  const handleSelect = useCallback((id: string, node: TreeNode) => {
    setSelected((prev) => {
      const next = new Set(prev);
      const descendantIds = collectAllDescendantIds(node);

      if (next.has(id)) {
        next.delete(id);
        descendantIds.forEach((did) => next.delete(did));
      } else {
        next.add(id);
        descendantIds.forEach((did) => next.add(did));
      }

      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    const allIds = new Set<string>();
    function collect(nodes: TreeNode[]) {
      for (const node of nodes) {
        allIds.add(node.id);
        collect(node.children);
      }
    }
    collect(tree);
    setSelected(allIds);
  }, [tree]);

  const handleDeselectAll = useCallback(() => {
    setSelected(new Set());
  }, []);

  const handleSelectByType = useCallback(
    (type: IssueType, select: boolean) => {
      setSelected((prev) => {
        const next = new Set(prev);
        function process(nodes: TreeNode[]) {
          for (const node of nodes) {
            if (node.type === type) {
              if (select) {
                next.add(node.id);
                collectAllDescendantIds(node).forEach((did) => next.add(did));
              } else {
                next.delete(node.id);
                collectAllDescendantIds(node).forEach((did) => next.delete(did));
              }
            }
            process(node.children);
          }
        }
        process(tree);
        return next;
      });
    },
    [tree],
  );

  const handleStatusChange = useCallback(
    (id: string, status: IssueStatus) => {
      updateIssue.mutate({ issueId: id, data: { status } }, { onSuccess: () => refetch() });
    },
    [updateIssue, refetch],
  );

  const handleNavigate = useCallback(
    (issue: Issue) => {
      router.push(`/codeboard/issue/${issue.id}`);
    },
    [router],
  );

  const handleRunningTaskClick = useCallback((issueId: string) => {
    setActiveTerminalIssueId((prev) => (prev === issueId ? null : issueId));
  }, []);

  const handleMarkAllWaitingQA = useCallback(async () => {
    const allIssues = issuesData?.items || [];
    const itemsToUpdate =
      selected.size > 0
        ? allIssues.filter(
            (i) =>
              selected.has(i.id) &&
              i.status !== 'COMPLETED_WAITING_QA' &&
              i.status !== 'DONE' &&
              i.status !== 'CANCELLED',
          )
        : allIssues.filter(
            (i) =>
              isExecutableType(i.type) &&
              i.status !== 'COMPLETED_WAITING_QA' &&
              i.status !== 'DONE' &&
              i.status !== 'CANCELLED',
          );

    if (itemsToUpdate.length === 0) {
      alert('No items to mark as Waiting for QA');
      return;
    }

    if (!confirm(`Mark ${itemsToUpdate.length} items as Waiting for QA?`)) return;

    for (const item of itemsToUpdate) {
      await updateIssue.mutateAsync({ issueId: item.id, data: { status: 'COMPLETED_WAITING_QA' } });
    }
    refetch();
  }, [selected, issuesData, updateIssue, refetch]);

  const handleMarkAllDone = useCallback(async () => {
    const allIssues = issuesData?.items || [];
    const itemsToUpdate =
      selected.size > 0
        ? allIssues.filter(
            (i) =>
              selected.has(i.id) && i.status !== 'DONE' && i.status !== 'CANCELLED',
          )
        : allIssues.filter(
            (i) => isExecutableType(i.type) && i.status !== 'DONE' && i.status !== 'CANCELLED',
          );

    if (itemsToUpdate.length === 0) {
      alert('No items to mark as Done');
      return;
    }

    if (!confirm(`Mark ${itemsToUpdate.length} items as Done?`)) return;

    for (const item of itemsToUpdate) {
      await updateIssue.mutateAsync({ issueId: item.id, data: { status: 'DONE' } });
    }
    refetch();
  }, [selected, issuesData, updateIssue, refetch]);

  // ─── Run Now — CB-2791 ─────────────────────────────────────────────────────

  function getExecutableDescendantIds(node: TreeNode): string[] {
    const ids: string[] = [];
    function walk(n: TreeNode) {
      if (isExecutableType(n.type) && n.status !== 'DONE' && n.status !== 'CANCELLED') {
        ids.push(n.id);
      }
      for (const child of n.children) {
        walk(child);
      }
    }
    walk(node);
    return ids;
  }

  const handleRunNow = useCallback((node: TreeNode) => {
    const hasChildren = node.children && node.children.length > 0;
    if (isExecutableType(node.type) && !hasChildren) {
      // Single task — start immediately via autopilot infrastructure
      startExecution.mutate(
        { issueId: node.id, provider: 'claude_code' },
        {
          onSuccess: () => {
            // Toast-like feedback via page title flash — minimal, no toast lib dependency
            const orig = document.title;
            document.title = `Started ${node.key}`;
            setTimeout(() => { document.title = orig; }, 3000);
          },
        }
      );
    } else {
      // Container node — open FEP with subtree pre-selected
      const ids = new Set(getExecutableDescendantIds(node));
      setRunNowSelected(ids);
      setRunNowContext(node);
    }
  }, [startExecution]);

  // ─── Loading skeleton ───────────────────────────────────────────────────────

  if (issuesLoading) {
    return (
      <div className="animate-pulse space-y-3">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="h-12 bg-zinc-700 rounded" />
        ))}
      </div>
    );
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Tabs: Overview / Testing */}
      <div className="bg-zinc-800 border-b border-zinc-700">
        <div className="flex items-center gap-1 px-0">
          <button
            onClick={() => setActiveTab('overview')}
            className={cn(
              'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === 'overview'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200',
            )}
          >
            <ListTree className="w-4 h-4" />
            Overview
          </button>
          <button
            onClick={() => setActiveTab('testing')}
            className={cn(
              'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === 'testing'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200',
            )}
          >
            <FlaskConical className="w-4 h-4" />
            Testing
          </button>
        </div>
      </div>

      {activeTab === 'overview' ? (
        <>
          {/* Feature Search — CB-1119 */}
          <div className="bg-zinc-800/50 border-b border-zinc-700 px-0 py-3">
            <FeatureSearchBar
              filters={searchFilters}
              onChange={setSearchFilters}
              resultCount={visibleIssueIds.size}
              totalCount={allDescendantIssues.length}
            />
          </div>

          {/* Toolbar */}
          <div className="bg-zinc-800 border-b border-zinc-700">
            <div className="py-2 flex items-center gap-4 flex-wrap px-0">
              {/* Expand/Collapse */}
              <div className="flex items-center gap-2 border-r border-zinc-700 pr-4">
                <button
                  onClick={handleExpandAll}
                  className="text-sm text-zinc-400 hover:text-zinc-100"
                >
                  Expand All
                </button>
                <button
                  onClick={handleCollapseAll}
                  className="text-sm text-zinc-400 hover:text-zinc-100"
                >
                  Collapse All
                </button>
              </div>

              {/* Selection Controls */}
              <div className="flex items-center gap-2 border-r border-zinc-700 pr-4">
                <span className="text-xs text-zinc-500">Select:</span>
                <button
                  onClick={handleSelectAll}
                  className="text-sm text-blue-400 hover:text-blue-300"
                >
                  All
                </button>
                <button
                  onClick={handleDeselectAll}
                  className="text-sm text-zinc-400 hover:text-zinc-100"
                >
                  None
                </button>
              </div>

              {/* Type-specific toggles */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-500">Toggle:</span>
                <button
                  onClick={() => handleSelectByType('EPIC', !selected.size)}
                  className="text-xs px-2 py-1 rounded bg-purple-900/50 text-purple-400 hover:bg-purple-900/70"
                >
                  ⚡ EPICs
                </button>
                <button
                  onClick={() => handleSelectByType('STORY', !selected.size)}
                  className="text-xs px-2 py-1 rounded bg-blue-900/50 text-blue-400 hover:bg-blue-900/70"
                >
                  📖 STORYs
                </button>
                <button
                  onClick={() => handleSelectByType('TASK', !selected.size)}
                  className="text-xs px-2 py-1 rounded bg-green-900/50 text-green-400 hover:bg-green-900/70"
                >
                  ✓ TASKs
                </button>
                <button
                  onClick={() => handleSelectByType('SUBTASK', !selected.size)}
                  className="text-xs px-2 py-1 rounded bg-zinc-700 text-zinc-400 hover:bg-zinc-600"
                >
                  ○ SUBTASKs
                </button>
                <button
                  onClick={() => handleSelectByType('BUG', !selected.size)}
                  className="text-xs px-2 py-1 rounded bg-red-900/50 text-red-400 hover:bg-red-900/70"
                >
                  🐛 BUGs
                </button>
              </div>

              <div className="flex-1" />

              {/* Auto Pilot button — shown whenever there are children (works for FEATURE, BUG, TASK) */}
              {executableTasks.length > 0 || isAutoPilotRunningForThis ? (
                <button
                  onClick={() => setShowAutoPilotPanel(true)}
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                    isAutoPilotRunningForThis
                      ? 'bg-blue-800 text-blue-200 ring-2 ring-blue-500/50'
                      : executableTasks.length === 0
                      ? 'bg-zinc-700 text-zinc-400 cursor-not-allowed'
                      : 'bg-gradient-to-r from-blue-700 to-blue-600 hover:from-blue-600 hover:to-blue-500 text-white',
                  )}
                  disabled={executableTasks.length === 0 && !isAutoPilotRunningForThis}
                  title={
                    isAutoPilotRunningForThis
                      ? 'AutoPilot is running — click to view'
                      : `Auto Pilot (${executableTasks.length} tasks)`
                  }
                >
                  {isAutoPilotRunningForThis ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : executableTasks.length === 0 ? (
                    <CheckCircle2 className="w-4 h-4" />
                  ) : (
                    <Zap className="w-4 h-4" />
                  )}
                  {isAutoPilotRunningForThis
                    ? `AutoPilot ${
                        autoPilot.state.progress.completed +
                        autoPilot.state.progress.skipped
                      }/${autoPilot.state.progress.total}`
                    : executableTasks.length === 0
                    ? 'All Done!'
                    : `Auto Pilot (${executableTasks.length})`}
                  {/* CB-2751: Status badge inline with button label */}
                  {isAutoPilotRunningForThis && autoPilot.state.queueStatus && (
                    <AutoPilotStatusBadge
                      state={autoPilot.state.queueStatus}
                      reason={autoPilot.state.pauseReason ?? undefined}
                      className="ml-1"
                    />
                  )}
                </button>
              ) : null}

              {/* Selected count */}
              {selected.size > 0 && (
                <span className="text-sm text-blue-400">{selected.size} selected</span>
              )}

              {/* Bulk Actions */}
              <div className="flex items-center gap-2 border-l border-zinc-700 pl-4">
                <button
                  onClick={handleMarkAllWaitingQA}
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white"
                >
                  <ClipboardCheck className="w-3.5 h-3.5" />
                  {selected.size > 0 ? 'Selected → Waiting QA' : 'All → Waiting QA'}
                </button>
                <button
                  onClick={handleMarkAllDone}
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded bg-green-600 hover:bg-green-500 text-white"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {selected.size > 0 ? 'Selected → Done' : 'All → Done'}
                </button>
              </div>

              {/* Refresh */}
              <button
                onClick={() => refetch()}
                className="flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Refresh
              </button>
            </div>
          </div>

          {/* Tree View + Inline Terminal split */}
          <div
            className={cn(
              'py-4 transition-all duration-300',
              activeTerminalSession ? 'w-full' : 'w-full',
            )}
          >
            <div className="flex gap-4">
              {/* Tree panel */}
              <div
                className={cn(
                  'transition-all duration-300 min-w-0',
                  activeTerminalSession ? 'w-1/2' : 'w-full',
                )}
              >
                <div className="bg-zinc-800 rounded-lg border border-zinc-700 overflow-hidden">
                  {filteredTree.length === 0 ? (
                    <div className="p-8 text-center text-zinc-500">
                      {allDescendantIssues.length === 0
                        ? 'No issues found under this issue'
                        : 'No issues match your search criteria'}
                    </div>
                  ) : (
                    <div className="divide-y divide-zinc-700">
                      {filteredTree.map((node) => (
                        <TreeItem
                          key={node.id}
                          node={node}
                          expanded={expanded}
                          selected={selected}
                          onToggle={handleToggle}
                          onSelect={handleSelect}
                          onStatusChange={handleStatusChange}
                          onNavigate={handleNavigate}
                          searchQuery={searchFilters.query}
                          epicSearchFilters={epicSearchFilters}
                          epicSearchVisibleIds={epicSearchVisibleIds}
                          onEpicSearchToggle={handleEpicSearchToggle}
                          onEpicSearchChange={handleEpicSearchChange}
                          allDescendantIssues={allDescendantIssues}
                          activeSessionMap={activeSessionMap}
                          onRunningTaskClick={handleRunningTaskClick}
                          onRunNow={handleRunNow}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Inline terminal panel */}
              {activeTerminalSession && activeTerminalIssueId && (
                <div className="w-1/2 h-[calc(100vh-320px)] sticky top-[280px] transition-all duration-300 animate-in slide-in-from-right-4">
                  <InlineTerminalPanel
                    session={activeTerminalSession}
                    issue={issuesData?.items.find((i) => i.id === activeTerminalIssueId)}
                    onClose={() => setActiveTerminalIssueId(null)}
                  />
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        /* Testing Tab */
        <div className="py-4">
          <FeatureTestingPanel featureId={issueId} projectId={projectId} />
        </div>
      )}

      {/* Auto Pilot panel — CB-2727: opened by the toolbar button */}
      {rootIssue && issuesData?.items && showAutoPilotPanel && (
        <FeatureExecutionPanel
          feature={rootIssue}
          allIssues={issuesData.items}
          projectId={projectId}
          isOpen={showAutoPilotPanel}
          onClose={() => {
            setShowAutoPilotPanel(false);
            refetch();
          }}
          onIssueClick={(issue) => {
            router.push(`/codeboard/issue/${issue.id}`);
          }}
          initialSelectedIds={selected.size > 0 ? selected : undefined}
        />
      )}

      {/* Run Now panel — CB-2791: opened by per-row Play button on container nodes */}
      {runNowContext && issuesData?.items && (
        <FeatureExecutionPanel
          feature={runNowContext}
          allIssues={issuesData.items}
          projectId={projectId}
          isOpen={!!runNowContext}
          onClose={() => {
            setRunNowContext(null);
            setRunNowSelected(new Set());
            refetch();
          }}
          onIssueClick={(issue) => {
            router.push(`/codeboard/issue/${issue.id}`);
          }}
          initialSelectedIds={runNowSelected}
        />
      )}
    </div>
  );
}
