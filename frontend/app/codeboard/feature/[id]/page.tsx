'use client';

/**
 * Feature Detail Page - Shows all issues under a FEATURE with hierarchy
 */

import { useState, useMemo, useCallback, useEffect, memo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, ChevronRight, ChevronDown, CheckCircle2, Circle, Clock, XCircle, AlertCircle, Rocket, RefreshCw, Square, CheckSquare, MinusSquare, ClipboardCheck, Trash2, FlaskConical, ListTree, Zap, Search, Loader2, PanelRightClose, Wifi, WifiOff, Terminal } from 'lucide-react';
import { useIssues, useIssue, useUpdateIssue, useDeleteIssue, useStartExecution, useFeatureLiveData, type ExecutionSession } from '@/hooks/useCodeBoard';
import { Issue, IssueStatus, IssueType } from '@/types/codeboard';
import { ExecutionModal, FeatureTestingPanel, FeatureExecutionPanel, FeatureSearchBar, applyFeatureSearchFilters, DEFAULT_FEATURE_SEARCH_FILTERS, InlineTerminalPanel } from '@/components/codeboard';
import type { FeatureSearchFilters } from '@/components/codeboard';
import { EpicSearchBar, applyEpicSearchFilters, DEFAULT_EPIC_SEARCH_FILTERS, RelevanceBadge, highlightEpicMatch } from '@/components/codeboard/EpicSearchBar';
import type { EpicSearchFilters } from '@/components/codeboard/EpicSearchBar';
import { cn } from '@/lib/utils';
import { highlightMatch } from '@/components/codeboard/IssueSearchBar';
import { useAutoPilot } from '@/contexts/AutoPilotContext';

// Status icons and colors — dark mode defaults; light mode handled by globals.css .light overrides
const STATUS_CONFIG: Record<IssueStatus, { icon: React.ComponentType<{ className?: string }>; color: string; bg: string; darkBg: string }> = {
  'BACKLOG': { icon: Circle, color: 'text-gray-400', bg: 'bg-gray-100', darkBg: 'bg-gray-700' },
  'TODO': { icon: Circle, color: 'text-blue-500', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30' },
  'IN_PROGRESS': { icon: Clock, color: 'text-yellow-500', bg: 'bg-yellow-100', darkBg: 'bg-yellow-900/30' },
  'IN_REVIEW': { icon: AlertCircle, color: 'text-purple-500', bg: 'bg-purple-100', darkBg: 'bg-purple-900/30' },
  'COMPLETED_WAITING_QA': { icon: Clock, color: 'text-blue-700', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30' },
  'DONE': { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-100', darkBg: 'bg-green-900/30' },
  'CANCELLED': { icon: XCircle, color: 'text-red-500', bg: 'bg-red-100', darkBg: 'bg-red-900/30' },
};

// Type colors — dark mode defaults; light mode handled by globals.css .light overrides
const TYPE_CONFIG: Record<IssueType, { color: string; bg: string; darkBg: string; icon: string }> = {
  'FEATURE': { color: 'text-blue-400', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30', icon: '🚀' },
  'EPIC': { color: 'text-purple-400', bg: 'bg-purple-100', darkBg: 'bg-purple-900/30', icon: '⚡' },
  'STORY': { color: 'text-blue-400', bg: 'bg-blue-100', darkBg: 'bg-blue-900/30', icon: '📖' },
  'TASK': { color: 'text-green-400', bg: 'bg-green-100', darkBg: 'bg-green-900/30', icon: '✓' },
  'SUBTASK': { color: 'text-gray-400', bg: 'bg-gray-100', darkBg: 'bg-gray-700', icon: '○' },
  'BUG': { color: 'text-red-400', bg: 'bg-red-100', darkBg: 'bg-red-900/30', icon: '🐛' },
};

interface TreeNode extends Issue {
  children: TreeNode[];
  level: number;
}

function buildTree(issues: Issue[], rootId: string): TreeNode[] {
  const issueMap = new Map<string, Issue>();
  issues.forEach(issue => issueMap.set(issue.id, issue));

  function buildNode(issue: Issue, level: number): TreeNode {
    const children = issues
      .filter(i => i.parentId === issue.id)
      .map(child => buildNode(child, level + 1))
      .sort((a, b) => {
        // Sort by type hierarchy, then by sequence
        const typeOrder: Record<string, number> = { 'EPIC': 0, 'STORY': 1, 'TASK': 2, 'BUG': 2, 'SUBTASK': 3 };
        const typeCompare = (typeOrder[a.type] ?? 99) - (typeOrder[b.type] ?? 99);
        if (typeCompare !== 0) return typeCompare;
        return a.sequence - b.sequence;
      });

    return { ...issue, children, level };
  }

  // Find direct children of the root (FEATURE)
  const rootChildren = issues
    .filter(i => i.parentId === rootId)
    .map(child => buildNode(child, 0))
    .sort((a, b) => a.sequence - b.sequence);

  return rootChildren;
}

function calculateProgress(node: TreeNode): { done: number; waitingQA: number; total: number } {
  if (node.children.length === 0) {
    const isDone = node.status === 'DONE';
    const isWaitingQA = node.status === 'COMPLETED_WAITING_QA';
    return {
      done: isDone ? 1 : 0,
      waitingQA: isWaitingQA ? 1 : 0,
      total: 1
    };
  }

  let done = 0;
  let waitingQA = 0;
  let total = 0;

  for (const child of node.children) {
    const childProgress = calculateProgress(child);
    done += childProgress.done;
    waitingQA += childProgress.waitingQA;
    total += childProgress.total;
  }

  return { done, waitingQA, total };
}

// Helper to collect all descendant IDs from a node
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

// Check if any descendants are selected
function hasSelectedDescendants(node: TreeNode, selected: Set<string>): boolean {
  for (const child of node.children) {
    if (selected.has(child.id)) return true;
    if (hasSelectedDescendants(child, selected)) return true;
  }
  return false;
}

// Check if all descendants are selected
function allDescendantsSelected(node: TreeNode, selected: Set<string>): boolean {
  if (node.children.length === 0) return true;
  for (const child of node.children) {
    if (!selected.has(child.id)) return false;
    if (!allDescendantsSelected(child, selected)) return false;
  }
  return true;
}

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
  epicSearchVisibleIds?: Map<string, { visibleIds: Set<string>; matchIds: Set<string>; scores: Map<string, number> }>;
  onEpicSearchToggle?: (epicId: string) => void;
  onEpicSearchChange?: (epicId: string, filters: EpicSearchFilters) => void;
  allDescendantIssues?: Array<{ id: string; parentId?: string; title: string; key: string; description?: string; type: string; status: string; priority: string; labels?: string; createdAt: string; updatedAt: string; dueDate?: string; startedAt?: string; completedAt?: string }>;
  activeSessionMap?: Map<string, ExecutionSession>;
  onRunningTaskClick?: (issueId: string) => void;
}

const TreeItem = memo(function TreeItem({ node, expanded, selected, onToggle, onSelect, onStatusChange, onNavigate, searchQuery, epicSearchFilters, epicSearchVisibleIds, onEpicSearchToggle, onEpicSearchChange, allDescendantIssues, activeSessionMap, onRunningTaskClick }: TreeItemProps) {
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const isExpanded = expanded.has(node.id);
  const isSelected = selected.has(node.id);
  const hasChildren = node.children.length > 0;
  const StatusIcon = STATUS_CONFIG[node.status].icon;
  const typeConfig = TYPE_CONFIG[node.type];
  const runningSession = activeSessionMap?.get(node.id);
  const progress = calculateProgress(node);
  const completedCount = progress.done + progress.waitingQA;
  const progressPercent = progress.total > 0 ? Math.round((completedCount / progress.total) * 100) : 0;
  const allWaitingQA = progress.waitingQA > 0 && progress.done === 0 && completedCount === progress.total;
  const allDone = progress.done === progress.total;

  // Epic search state - CB-1122
  const isEpic = node.type === 'EPIC';
  const epicFilters = isEpic ? epicSearchFilters?.get(node.id) : undefined;
  const epicSearchResult = isEpic ? epicSearchVisibleIds?.get(node.id) : undefined;
  const hasEpicSearch = !!epicFilters;

  // Count descendants of this epic for search result display
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

  // Filter children based on epic search - CB-1122
  const filteredChildren = useMemo(() => {
    if (!epicSearchResult || !hasEpicSearch) return node.children;
    const hasAnyFilter = epicFilters!.query ||
      epicFilters!.types.length > 0 ||
      epicFilters!.statuses.length > 0 ||
      epicFilters!.priorities.length > 0 ||
      (epicFilters!.dateField && (epicFilters!.dateRange.start || epicFilters!.dateRange.end));
    if (!hasAnyFilter) return node.children;

    function filterNodes(nodes: TreeNode[]): TreeNode[] {
      return nodes
        .filter(n => epicSearchResult!.visibleIds.has(n.id))
        .map(n => ({
          ...n,
          children: filterNodes(n.children),
        }));
    }
    return filterNodes(node.children);
  }, [node.children, epicSearchResult, hasEpicSearch, epicFilters]);

  // Determine checkbox state: checked, unchecked, or indeterminate
  const someDescendantsSelected = hasChildren && hasSelectedDescendants(node, selected);
  const allDescendants = hasChildren && allDescendantsSelected(node, selected);
  const isIndeterminate = someDescendantsSelected && !allDescendants && !isSelected;

  const allStatuses: IssueStatus[] = ['BACKLOG', 'TODO', 'IN_PROGRESS', 'IN_REVIEW', 'COMPLETED_WAITING_QA', 'DONE', 'CANCELLED'];

  // Get the active search query for highlighting - use epic search query if active, otherwise parent search
  const activeSearchQuery = (hasEpicSearch && epicFilters?.query) ? epicFilters.query : searchQuery;
  const isEpicSearchQuery = !!(hasEpicSearch && epicFilters?.query);

  // Relevance score for this item (from epic search)
  const relevanceScore = epicSearchResult?.scores.get(node.id) ?? 0;
  const isDirectMatch = epicSearchResult?.matchIds.has(node.id) ?? false;

  return (
    <div className="select-none">
      <div
        className={cn(
          "flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-zinc-700/50 cursor-pointer group transition-all duration-300",
          "border-l-4",
          runningSession ? 'border-l-cyan-400 bg-cyan-950/20 animate-pulse' :
          node.status === 'DONE' ? 'border-l-green-500' :
          node.status === 'COMPLETED_WAITING_QA' ? 'border-l-blue-700' :
          node.status === 'IN_PROGRESS' ? 'border-l-yellow-500' :
          node.status === 'IN_REVIEW' ? 'border-l-purple-500' :
          'border-l-zinc-600',
          isSelected && 'bg-blue-900/20'
        )}
        style={{ paddingLeft: `${(node.level * 24) + 12}px` }}
      >
        {/* Expand/Collapse */}
        <button
          onClick={(e) => { e.stopPropagation(); onToggle(node.id); }}
          className={cn(
            "w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-600 text-zinc-400",
            !hasChildren && "invisible"
          )}
        >
          {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>

        {/* Selection Checkbox */}
        <button
          onClick={(e) => { e.stopPropagation(); onSelect(node.id, node); }}
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
        <span className={cn(
          "text-xs px-2 py-0.5 rounded-full font-medium",
          node.type === 'EPIC' ? 'bg-purple-900/50 text-purple-400' :
          node.type === 'STORY' ? 'bg-blue-900/50 text-blue-400' :
          node.type === 'TASK' ? 'bg-green-900/50 text-green-400' :
          node.type === 'SUBTASK' ? 'bg-zinc-700 text-zinc-400' :
          node.type === 'BUG' ? 'bg-red-900/50 text-red-400' :
          'bg-blue-900/50 text-blue-400'
        )}>
          {typeConfig.icon} {node.type}
        </span>

        {/* Issue Key */}
        <span className="text-xs font-mono text-zinc-500">{node.key}</span>

        {/* Running indicator + terminal button */}
        {runningSession && (
          <>
            <Loader2 className="w-4 h-4 text-cyan-400 animate-spin shrink-0" />
            <button
              onClick={(e) => { e.stopPropagation(); onRunningTaskClick?.(node.id); }}
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
            "flex-1 text-sm font-medium truncate",
            runningSession ? "text-cyan-200 hover:text-cyan-100" : "text-zinc-100 hover:text-blue-400"
          )}
          onClick={() => onNavigate(node)}
        >
          {activeSearchQuery
            ? (isEpicSearchQuery ? highlightEpicMatch(node.title, activeSearchQuery) : highlightMatch(node.title, activeSearchQuery))
            : node.title
          }
        </span>

        {/* Relevance badge for epic search results - CB-1123 */}
        {hasEpicSearch && epicFilters?.query && (
          <RelevanceBadge score={relevanceScore} isDirectMatch={isDirectMatch} />
        )}

        {/* Epic Search Toggle - CB-1122/CB-1123 */}
        {isEpic && hasChildren && onEpicSearchToggle && (
          <button
            onClick={(e) => { e.stopPropagation(); onEpicSearchToggle(node.id); }}
            className={cn(
              "flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all",
              hasEpicSearch
                ? "bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30"
                : "text-zinc-500 hover:text-purple-400 hover:bg-zinc-700 border border-transparent hover:border-purple-500/30"
            )}
            title={hasEpicSearch ? 'Close epic search' : 'Search within this epic'}
          >
            <Search className="w-3.5 h-3.5" />
            {!hasEpicSearch && <span className="hidden group-hover:inline">Search</span>}
          </button>
        )}

        {/* Status Dropdown */}
        <div className="relative">
          <button
            onClick={(e) => { e.stopPropagation(); setShowStatusDropdown(!showStatusDropdown); }}
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium min-w-[140px]",
              "bg-zinc-700 border border-zinc-600 hover:border-zinc-500"
            )}
          >
            <StatusIcon className={cn("w-3.5 h-3.5", STATUS_CONFIG[node.status].color)} />
            <span className={STATUS_CONFIG[node.status].color}>
              {node.status.replace(/_/g, ' ')}
            </span>
            <ChevronDown className="w-3 h-3 ml-auto text-zinc-400" />
          </button>

          {showStatusDropdown && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={(e) => { e.stopPropagation(); setShowStatusDropdown(false); }}
              />
              <div className="absolute right-0 top-full mt-1 z-20 bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl py-1 min-w-[180px]">
                {allStatuses.map(status => {
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
                        "w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-zinc-700 text-left",
                        node.status === status && "bg-zinc-700"
                      )}
                    >
                      <Icon className={cn("w-4 h-4", config.color)} />
                      <span className={config.color}>{status.replace(/_/g, ' ')}</span>
                      {node.status === status && <CheckCircle2 className="w-3 h-3 ml-auto text-green-500" />}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Progress */}
        <div className="flex items-center gap-2">
          <div className="w-20 h-2 bg-zinc-700 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                allDone ? 'bg-green-500' :
                allWaitingQA ? 'bg-blue-700' :
                progressPercent === 100 ? 'bg-blue-700' :
                progressPercent > 50 ? 'bg-blue-500' :
                progressPercent > 0 ? 'bg-yellow-500' : 'bg-zinc-600'
              )}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className={cn(
            "text-xs w-12 text-right",
            allDone ? 'text-green-400' :
            allWaitingQA ? 'text-blue-400' :
            'text-zinc-500'
          )}>
            {completedCount}/{progress.total}
          </span>
        </div>
      </div>

      {/* Epic Search Bar - CB-1122 / CB-1123 */}
      {isEpic && hasEpicSearch && epicFilters && onEpicSearchChange && (
        <div
          className="border-l-4 border-l-purple-500/30 bg-purple-900/10 animate-in slide-in-from-top-1 duration-200"
          style={{ paddingLeft: `${(node.level * 24) + 12}px` }}
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
          {filteredChildren.map(child => (
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
            />
          ))}
        </div>
      )}
    </div>
  );
});

export default function FeatureDetailPage() {
  const params = useParams();
  const router = useRouter();
  const featureId = params.id as string;

  // Fetch the feature issue
  const { data: feature, isLoading: featureLoading } = useIssue(featureId);

  // Live data from SSE
  const { activeSessionMap, hasActiveSessions, sseConnected } = useFeatureLiveData(feature?.projectId || null);

  // Fetch all issues for the project — polls every 3s when sessions are active
  const { data: issuesData, isLoading: issuesLoading, refetch } = useIssues(
    feature?.projectId || null,
    { pageSize: 1000, refetchInterval: hasActiveSessions ? 3000 : false }
  );

  // Inline terminal state
  const [activeTerminalIssueId, setActiveTerminalIssueId] = useState<string | null>(null);
  const activeTerminalSession = activeTerminalIssueId ? activeSessionMap.get(activeTerminalIssueId) : null;

  const updateIssue = useUpdateIssue();
  const deleteIssue = useDeleteIssue();
  const startExecution = useStartExecution();

  // Search/filter state - CB-1119
  const [searchFilters, setSearchFilters] = useState<FeatureSearchFilters>(DEFAULT_FEATURE_SEARCH_FILTERS);

  // State for active tab
  const [activeTab, setActiveTab] = useState<'overview' | 'testing'>('overview');

  // State for expanded nodes
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // State for selected nodes (for execution)
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // State for execution
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentExecutionIssue, setCurrentExecutionIssue] = useState<Issue | null>(null);
  const [activeExecution, setActiveExecution] = useState<ExecutionSession | null>(null);
  const [executionQueue, setExecutionQueue] = useState<Issue[]>([]);
  const [executionIndex, setExecutionIndex] = useState(0);

  // Auto Pilot Panel state
  const [showAutoPilotPanel, setShowAutoPilotPanel] = useState(false);
  const autoPilot = useAutoPilot();
  const isAutoPilotRunningForThis = autoPilot.state.isActive && autoPilot.state.featureId === featureId;

  // Epic search state - CB-1122
  const [epicSearchFilters, setEpicSearchFilters] = useState<Map<string, EpicSearchFilters>>(new Map());

  const handleEpicSearchToggle = useCallback((epicId: string) => {
    setEpicSearchFilters(prev => {
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
    setEpicSearchFilters(prev => {
      const next = new Map(prev);
      next.set(epicId, filters);
      return next;
    });
  }, []);

  // Build the tree
  const tree = useMemo(() => {
    if (!feature || !issuesData?.items) return [];

    // Get all descendants of this feature
    const allIssues = issuesData.items;
    const descendants = new Set<string>();

    function collectDescendants(parentId: string) {
      allIssues.forEach(issue => {
        if (issue.parentId === parentId && !descendants.has(issue.id)) {
          descendants.add(issue.id);
          collectDescendants(issue.id);
        }
      });
    }

    collectDescendants(featureId);

    const relevantIssues = allIssues.filter(i => descendants.has(i.id));
    return buildTree(relevantIssues, featureId);
  }, [feature, issuesData, featureId]);

  // Apply search filters to get visible issue IDs - CB-1119
  const allDescendantIssues = useMemo(() => {
    if (!issuesData?.items) return [];
    const descendants = new Set<string>();
    function collectDescendants(parentId: string) {
      issuesData!.items.forEach(issue => {
        if (issue.parentId === parentId && !descendants.has(issue.id)) {
          descendants.add(issue.id);
          collectDescendants(issue.id);
        }
      });
    }
    collectDescendants(featureId);
    return issuesData.items.filter(i => descendants.has(i.id));
  }, [issuesData, featureId]);

  const visibleIssueIds = useMemo(() => {
    return applyFeatureSearchFilters(allDescendantIssues, searchFilters);
  }, [allDescendantIssues, searchFilters]);

  // Compute epic search results for each active epic search - CB-1122
  const epicSearchVisibleIds = useMemo(() => {
    const results = new Map<string, { visibleIds: Set<string>; matchIds: Set<string>; scores: Map<string, number> }>();

    for (const [epicId, filters] of epicSearchFilters.entries()) {
      // Get descendants of this specific epic
      const epicDescendants = allDescendantIssues.filter(issue => {
        // Check if this issue is a descendant of the epic
        let current = issue;
        while (current) {
          if (current.parentId === epicId) return true;
          current = allDescendantIssues.find(i => i.id === current.parentId) as typeof current;
          if (!current) break;
        }
        return false;
      });

      const result = applyEpicSearchFilters(epicDescendants, filters);
      results.set(epicId, result);
    }

    return results;
  }, [epicSearchFilters, allDescendantIssues]);

  // Auto-expand epic children when epic search is active - CB-1122
  useEffect(() => {
    for (const [epicId, filters] of epicSearchFilters.entries()) {
      const hasAnyFilter = filters.query ||
        filters.types.length > 0 ||
        filters.statuses.length > 0 ||
        filters.priorities.length > 0 ||
        (filters.dateField && (filters.dateRange.start || filters.dateRange.end));

      if (hasAnyFilter) {
        const searchResult = epicSearchVisibleIds.get(epicId);
        if (searchResult) {
          setExpanded(prev => {
            const next = new Set(prev);
            next.add(epicId); // Expand the epic itself
            // Expand all visible parent nodes within the epic
            for (const id of searchResult.visibleIds) {
              const issue = allDescendantIssues.find(i => i.id === id);
              if (issue) {
                // Check if this issue has children in the visible set
                const hasVisibleChildren = allDescendantIssues.some(
                  child => child.parentId === id && searchResult.visibleIds.has(child.id)
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
  }, [epicSearchFilters, epicSearchVisibleIds, allDescendantIssues]);

  // Filter tree nodes based on search - CB-1119
  const filteredTree = useMemo(() => {
    const hasAnyFilter = searchFilters.query ||
      searchFilters.types.length > 0 ||
      searchFilters.statuses.length > 0 ||
      searchFilters.priorities.length > 0 ||
      (searchFilters.dateField && (searchFilters.dateRange.start || searchFilters.dateRange.end));

    if (!hasAnyFilter) return tree;

    function filterNodes(nodes: TreeNode[]): TreeNode[] {
      return nodes
        .filter(node => visibleIssueIds.has(node.id))
        .map(node => ({
          ...node,
          children: filterNodes(node.children),
        }));
    }

    return filterNodes(tree);
  }, [tree, visibleIssueIds, searchFilters]);

  // Calculate overall progress - only counts TASKs and SUBTASKs (actual work items)
  // EPICs and STORYs are containers, not executable work
  const overallProgress = useMemo(() => {
    let done = 0;
    let waitingQA = 0;
    let total = 0;

    function count(nodes: TreeNode[]) {
      for (const node of nodes) {
        // Only count TASKs and SUBTASKs (actual executable work items)
        if (node.type === 'TASK' || node.type === 'SUBTASK' || node.type === 'BUG') {
          total++;
          if (node.status === 'DONE') done++;
          else if (node.status === 'COMPLETED_WAITING_QA') waitingQA++;
        }
        // Always recurse into children
        if (node.children.length > 0) {
          count(node.children);
        }
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
      allWaitingQA: waitingQA > 0 && done === 0 && completed === total
    };
  }, [tree]);

  // Count by status
  const statusCounts = useMemo(() => {
    const counts: Record<IssueStatus, number> = {
      'BACKLOG': 0, 'TODO': 0, 'IN_PROGRESS': 0, 'IN_REVIEW': 0, 'COMPLETED_WAITING_QA': 0, 'DONE': 0, 'CANCELLED': 0
    };

    function count(nodes: TreeNode[]) {
      for (const node of nodes) {
        counts[node.status]++;
        count(node.children);
      }
    }

    count(tree);
    return counts;
  }, [tree]);

  // Count by type with status breakdown
  const typeStatusCounts = useMemo(() => {
    const types: IssueType[] = ['EPIC', 'STORY', 'TASK', 'SUBTASK', 'BUG'];
    const counts: Record<IssueType, { total: number; completed: number; done: number }> = {
      'FEATURE': { total: 0, completed: 0, done: 0 },
      'EPIC': { total: 0, completed: 0, done: 0 },
      'STORY': { total: 0, completed: 0, done: 0 },
      'TASK': { total: 0, completed: 0, done: 0 },
      'SUBTASK': { total: 0, completed: 0, done: 0 },
      'BUG': { total: 0, completed: 0, done: 0 },
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

  // Auto-expand all visible nodes when search is active - CB-1119
  useEffect(() => {
    const hasAnyFilter = searchFilters.query ||
      searchFilters.types.length > 0 ||
      searchFilters.statuses.length > 0 ||
      searchFilters.priorities.length > 0 ||
      (searchFilters.dateField && (searchFilters.dateRange.start || searchFilters.dateRange.end));

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
  }, [searchFilters, visibleIssueIds, tree]);

  // Handlers
  const handleToggle = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

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

  // Selection handlers with cascading
  const handleSelect = useCallback((id: string, node: TreeNode) => {
    setSelected(prev => {
      const next = new Set(prev);
      const descendantIds = collectAllDescendantIds(node);

      if (next.has(id)) {
        // Deselect this node and all descendants
        next.delete(id);
        descendantIds.forEach(did => next.delete(did));
      } else {
        // Select this node and all descendants
        next.add(id);
        descendantIds.forEach(did => next.add(did));
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

  // Select/Deselect by type
  const handleSelectByType = useCallback((type: IssueType, select: boolean) => {
    setSelected(prev => {
      const next = new Set(prev);
      function process(nodes: TreeNode[]) {
        for (const node of nodes) {
          if (node.type === type) {
            if (select) {
              // Select this node and all its descendants
              next.add(node.id);
              const descendantIds = collectAllDescendantIds(node);
              descendantIds.forEach(did => next.add(did));
            } else {
              // Deselect this node and all its descendants
              next.delete(node.id);
              const descendantIds = collectAllDescendantIds(node);
              descendantIds.forEach(did => next.delete(did));
            }
          }
          process(node.children);
        }
      }
      process(tree);
      return next;
    });
  }, [tree]);

  const handleStatusChange = (id: string, status: IssueStatus) => {
    updateIssue.mutate({ issueId: id, data: { status } }, {
      onSuccess: () => refetch()
    });
  };

  const handleNavigate = (issue: Issue) => {
    router.push(`/codeboard/issue/${issue.id}`);
  };

  const handleRunningTaskClick = useCallback((issueId: string) => {
    setActiveTerminalIssueId(prev => prev === issueId ? null : issueId);
  }, []);

  // Get all executable tasks (TASKs and SUBTASKs that are not DONE)
  // If items are selected, only include selected items
  const getExecutableTasks = useMemo(() => {
    const tasks: Issue[] = [];

    function collectTasks(nodes: TreeNode[]) {
      for (const node of nodes) {
        // Only collect TASKs and SUBTASKs that are not done
        if ((node.type === 'TASK' || node.type === 'SUBTASK') && node.status !== 'DONE') {
          // If we have selections, only include selected items
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

  // Start executing the feature
  const handleStartExecution = () => {
    const tasks = getExecutableTasks;
    if (tasks.length === 0) {
      alert('No tasks to execute. All tasks are already done!');
      return;
    }

    setExecutionQueue(tasks);
    setExecutionIndex(0);
    setIsExecuting(true);
    executeTask(tasks[0]);
  };

  // Execute a single task
  const executeTask = (task: Issue) => {
    setCurrentExecutionIssue(task);

    // Update task status to IN_PROGRESS
    updateIssue.mutate({ issueId: task.id, data: { status: 'IN_PROGRESS' } });

    // Start the execution
    startExecution.mutate(
      { issueId: task.id, provider: 'claude_code' },
      {
        onSuccess: (session) => {
          setActiveExecution(session);
        },
        onError: (error) => {
          console.error('Failed to start execution:', error);
          // Move to next task on error
          handleExecutionComplete();
        },
      }
    );
  };

  // Handle when a task execution completes
  const handleExecutionComplete = () => {
    // Mark current task as DONE
    if (currentExecutionIssue) {
      updateIssue.mutate({ issueId: currentExecutionIssue.id, data: { status: 'DONE' } });
    }

    // Move to next task
    const nextIndex = executionIndex + 1;
    if (nextIndex < executionQueue.length) {
      setExecutionIndex(nextIndex);
      executeTask(executionQueue[nextIndex]);
    } else {
      // All tasks done
      setIsExecuting(false);
      setCurrentExecutionIssue(null);
      setActiveExecution(null);
      setExecutionQueue([]);
      setExecutionIndex(0);
      refetch(); // Refresh the data
    }
  };

  // Skip current task
  const handleSkipTask = () => {
    handleExecutionComplete();
  };

  // Stop execution
  const handleStopExecution = () => {
    setIsExecuting(false);
    setCurrentExecutionIssue(null);
    setActiveExecution(null);
    setExecutionQueue([]);
    setExecutionIndex(0);
    refetch();
  };

  // Abort mission - stop everything and revert current task to TODO
  const handleAbortMission = async () => {
    // Revert current task to TODO if there is one
    if (currentExecutionIssue) {
      try {
        await updateIssue.mutateAsync({
          issueId: currentExecutionIssue.id,
          data: { status: 'TODO' },
        });
      } catch (error) {
        console.error('Failed to revert task status:', error);
      }
    }

    // Stop everything
    setIsExecuting(false);
    setCurrentExecutionIssue(null);
    setActiveExecution(null);
    setExecutionQueue([]);
    setExecutionIndex(0);
    refetch();
  };

  // Bulk mark as Done
  const handleMarkAllDone = useCallback(async () => {
    const allIssues = issuesData?.items || [];
    const itemsToUpdate = selected.size > 0
      ? allIssues.filter(i => selected.has(i.id) && i.status !== 'DONE' && i.status !== 'CANCELLED')
      : allIssues.filter(i => (i.type === 'TASK' || i.type === 'SUBTASK') && i.status !== 'DONE' && i.status !== 'CANCELLED');

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

  // Delete feature and all descendants
  const handleDeleteFeature = useCallback(async () => {
    if (!feature) return;

    const descendantCount = tree.reduce((acc, node) => {
      function count(n: TreeNode): number {
        return 1 + n.children.reduce((sum, child) => sum + count(child), 0);
      }
      return acc + count(node);
    }, 0);

    const message = descendantCount > 0
      ? `Delete "${feature.title}" and all ${descendantCount} child issues? This cannot be undone.`
      : `Delete "${feature.title}"? This cannot be undone.`;

    if (!confirm(message)) return;

    // Delete all descendants first (bottom-up)
    const allIssues = issuesData?.items || [];
    const descendants = allIssues.filter(i => {
      let current = i;
      while (current.parentId) {
        if (current.parentId === featureId) return true;
        current = allIssues.find(p => p.id === current.parentId) as Issue;
        if (!current) break;
      }
      return false;
    });

    // Sort by depth (deepest first) to delete children before parents
    const sortedDescendants = descendants.sort((a, b) => {
      const getDepth = (issue: Issue): number => {
        let depth = 0;
        let current = issue;
        while (current.parentId) {
          depth++;
          current = allIssues.find(p => p.id === current.parentId) as Issue;
          if (!current) break;
        }
        return depth;
      };
      return getDepth(b) - getDepth(a);
    });

    // Delete descendants
    for (const desc of sortedDescendants) {
      try {
        await deleteIssue.mutateAsync(desc.id);
      } catch (e) {
        console.error(`Failed to delete ${desc.key}:`, e);
      }
    }

    // Delete the feature itself
    try {
      await deleteIssue.mutateAsync(featureId);
      router.push('/codeboard');
    } catch (e) {
      console.error('Failed to delete feature:', e);
      alert('Failed to delete feature');
    }
  }, [feature, tree, issuesData, featureId, deleteIssue, router]);

  // Bulk mark as Waiting for QA
  const handleMarkAllWaitingQA = useCallback(async () => {
    const allIssues = issuesData?.items || [];
    const itemsToUpdate = selected.size > 0
      ? allIssues.filter(i => selected.has(i.id) && i.status !== 'COMPLETED_WAITING_QA' && i.status !== 'DONE' && i.status !== 'CANCELLED')
      : allIssues.filter(i => (i.type === 'TASK' || i.type === 'SUBTASK') && i.status !== 'COMPLETED_WAITING_QA' && i.status !== 'DONE' && i.status !== 'CANCELLED');

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

  if (featureLoading || issuesLoading) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="max-w-6xl mx-auto">
          <div className="animate-pulse">
            <div className="h-8 bg-zinc-700 rounded w-1/3 mb-4" />
            <div className="h-4 bg-zinc-700 rounded w-2/3 mb-8" />
            <div className="space-y-3">
              {[...Array(10)].map((_, i) => (
                <div key={i} className="h-12 bg-zinc-700 rounded" />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!feature) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="max-w-6xl mx-auto text-center py-12">
          <h1 className="text-2xl font-bold text-zinc-100">Feature not found</h1>
          <button
            onClick={() => router.push('/codeboard')}
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
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center gap-4 mb-4">
            <button
              onClick={() => router.push('/codeboard')}
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
                    "flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full",
                    sseConnected ? "text-green-400 bg-green-900/20" : hasActiveSessions ? "text-yellow-400 bg-yellow-900/20" : "text-zinc-600"
                  )}
                  title={sseConnected ? 'Live: SSE connected' : hasActiveSessions ? 'Polling fallback (SSE disconnected)' : 'Idle'}
                >
                  {sseConnected ? <Wifi className="w-3 h-3" /> : hasActiveSessions ? <WifiOff className="w-3 h-3" /> : null}
                  {hasActiveSessions && (sseConnected ? 'LIVE' : 'POLL')}
                </span>
              </div>
              <h1 className="text-xl font-bold text-zinc-100 mt-1">
                {feature.title}
              </h1>
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

          {/* Progress Overview - Two Bars */}
          <div className="flex items-center gap-6">
            <div className="flex-1 space-y-2">
              {/* Completed (Waiting QA) Bar */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-blue-400">Completed</span>
                  <span className="text-sm text-zinc-400">{overallProgress.waitingQA} / {overallProgress.total}</span>
                  <span className="text-xs text-zinc-500">(waiting QA)</span>
                </div>
                <div className="h-2 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-700 rounded-full transition-all duration-500"
                    style={{ width: `${overallProgress.total > 0 ? (overallProgress.waitingQA / overallProgress.total) * 100 : 0}%` }}
                  />
                </div>
              </div>
              {/* Done Bar */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-green-400">Done</span>
                  <span className="text-sm text-zinc-400">{overallProgress.done} / {overallProgress.total}</span>
                  <span className="text-xs text-zinc-500">(verified)</span>
                </div>
                <div className="h-2 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500 rounded-full transition-all duration-500"
                    style={{ width: `${overallProgress.total > 0 ? (overallProgress.done / overallProgress.total) * 100 : 0}%` }}
                  />
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-lg font-bold text-blue-400">
                {overallProgress.total > 0 ? Math.round((overallProgress.waitingQA / overallProgress.total) * 100) : 0}%
              </div>
              <div className="text-lg font-bold text-green-400">
                {overallProgress.total > 0 ? Math.round((overallProgress.done / overallProgress.total) * 100) : 0}%
              </div>
            </div>

            {/* Execution Buttons */}
            <div className="flex items-center gap-2">
              {/* Execute Feature Button */}
              <button
                onClick={handleStartExecution}
                disabled={isExecuting || getExecutableTasks.length === 0}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors",
                  isExecuting
                    ? "bg-yellow-500 text-white cursor-wait"
                    : getExecutableTasks.length === 0
                    ? "bg-green-500 text-white cursor-default"
                    : "bg-zinc-700 hover:bg-zinc-600 text-white"
                )}
              >
                {isExecuting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Executing {executionIndex + 1}/{executionQueue.length}
                  </>
                ) : getExecutableTasks.length === 0 ? (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    All Done!
                  </>
                ) : (
                  <>
                    <Rocket className="w-4 h-4" />
                    Manual
                  </>
                )}
              </button>

              {/* Auto Pilot Button */}
              <button
                onClick={() => setShowAutoPilotPanel(true)}
                disabled={isExecuting || getExecutableTasks.length === 0}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors",
                  isAutoPilotRunningForThis
                    ? "bg-blue-800 text-blue-200 ring-2 ring-blue-500/50"
                    : isExecuting || getExecutableTasks.length === 0
                      ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
                      : "bg-gradient-to-r from-blue-700 to-blue-600 hover:from-blue-600 hover:to-blue-500 text-white"
                )}
                title={isAutoPilotRunningForThis ? "AutoPilot is running — click to view" : "Launch Auto Pilot with full control panel"}
              >
                {isAutoPilotRunningForThis ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                {isAutoPilotRunningForThis
                  ? `AutoPilot ${autoPilot.state.progress.completed + autoPilot.state.progress.skipped}/${autoPilot.state.progress.total}`
                  : `Auto Pilot (${getExecutableTasks.length})`
                }
              </button>
            </div>
          </div>

          {/* Status by Type Summary */}
          <div className="mt-4 grid grid-cols-5 gap-3">
            {(['EPIC', 'STORY', 'TASK', 'SUBTASK', 'BUG'] as IssueType[]).map(type => {
              const counts = typeStatusCounts[type];
              if (counts.total === 0) return null;
              const typeConfig = TYPE_CONFIG[type];
              return (
                <div key={type} className="p-2 rounded-lg bg-zinc-700/50 border border-zinc-600">
                  <div className="flex items-center justify-between mb-1">
                    <span className={cn("text-xs font-medium", typeConfig.color)}>
                      {typeConfig.icon} {type}s
                    </span>
                    <span className="text-xs text-zinc-400">{counts.completed + counts.done}/{counts.total}</span>
                  </div>
                  <div className="h-1.5 bg-zinc-600 rounded-full overflow-hidden">
                    <div className="h-full flex">
                      <div className="h-full bg-green-500" style={{ width: `${counts.total > 0 ? (counts.done / counts.total) * 100 : 0}%` }} />
                      <div className="h-full bg-blue-700" style={{ width: `${counts.total > 0 ? (counts.completed / counts.total) * 100 : 0}%` }} />
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

      {/* Tabs */}
      <div className="bg-zinc-800 border-b border-zinc-700">
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab('overview')}
              className={cn(
                "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors",
                activeTab === 'overview'
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              )}
            >
              <ListTree className="w-4 h-4" />
              Overview
            </button>
            <button
              onClick={() => setActiveTab('testing')}
              className={cn(
                "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors",
                activeTab === 'testing'
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              )}
            >
              <FlaskConical className="w-4 h-4" />
              Testing
            </button>
          </div>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' ? (
        <>
          {/* Feature Search - CB-1119 */}
          <div className="bg-zinc-800/50 border-b border-zinc-700">
            <div className="max-w-6xl mx-auto px-6 py-3">
              <FeatureSearchBar
                filters={searchFilters}
                onChange={setSearchFilters}
                resultCount={visibleIssueIds.size}
                totalCount={allDescendantIssues.length}
              />
            </div>
          </div>

          {/* Toolbar */}
          <div className="bg-zinc-800 border-b border-zinc-700">
            <div className="max-w-6xl mx-auto px-6 py-2 flex items-center gap-4 flex-wrap">
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

              {/* Type-specific selection */}
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
              </div>

              <div className="flex-1" />

              {/* Selected count */}
              {selected.size > 0 && (
                <span className="text-sm text-blue-400">
                  {selected.size} selected
                </span>
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

              <button
                onClick={() => refetch()}
                className="text-sm text-zinc-400 hover:text-zinc-100"
              >
                Refresh
              </button>
            </div>
          </div>

          {/* Tree View + Inline Terminal Split */}
          <div className={cn(
            "mx-auto px-6 py-4 transition-all duration-300",
            activeTerminalSession ? "max-w-[1600px]" : "max-w-6xl"
          )}>
            <div className="flex gap-4">
              {/* Tree panel */}
              <div className={cn(
                "transition-all duration-300 min-w-0",
                activeTerminalSession ? "w-1/2" : "w-full"
              )}>
                <div className="bg-zinc-800 rounded-lg border border-zinc-700 overflow-hidden">
                  {filteredTree.length === 0 ? (
                    <div className="p-8 text-center text-zinc-500">
                      {allDescendantIssues.length === 0
                        ? 'No issues found under this feature'
                        : 'No issues match your search criteria'}
                    </div>
                  ) : (
                    <div className="divide-y divide-zinc-700">
                      {filteredTree.map(node => (
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
                    issue={issuesData?.items.find(i => i.id === activeTerminalIssueId)}
                    onClose={() => setActiveTerminalIssueId(null)}
                  />
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        /* Testing Tab */
        <div className="max-w-6xl mx-auto px-6 py-4">
          <FeatureTestingPanel
            featureId={featureId}
            projectId={feature.projectId}
          />
        </div>
      )}

      {/* Execution Modal */}
      {activeExecution && currentExecutionIssue && (
        <ExecutionModal
          session={activeExecution}
          issue={currentExecutionIssue}
          onClose={() => {
            handleExecutionComplete();
          }}
          onAbortMission={handleAbortMission}
        />
      )}

      {/* Execution Progress Bar */}
      {isExecuting && (
        <div className="fixed bottom-0 left-0 right-0 bg-zinc-800 border-t border-zinc-700 p-4 shadow-lg">
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-zinc-300">
                    Executing: {currentExecutionIssue?.key} - {currentExecutionIssue?.title}
                  </span>
                  <span className="text-sm text-zinc-400">
                    {executionIndex + 1} of {executionQueue.length}
                  </span>
                </div>
                <div className="h-2 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all"
                    style={{ width: `${((executionIndex + 1) / executionQueue.length) * 100}%` }}
                  />
                </div>
              </div>
              <button
                onClick={handleSkipTask}
                className="px-3 py-1.5 text-sm bg-yellow-500 text-white rounded-lg hover:bg-yellow-600"
              >
                Skip
              </button>
              <button
                onClick={handleStopExecution}
                className="px-3 py-1.5 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600"
              >
                Stop
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Auto Pilot Panel — execution runs in AutoPilotContext (providers.tsx) */}
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
