'use client';

/**
 * Hierarchy List View - Tree-style backlog view showing Epic → Story → Task hierarchy
 * Similar to Jira's backlog view with expandable/collapsible sections
 */

import { useState, useMemo } from 'react';
import { Issue, IssueStatus, ISSUE_TYPES, PRIORITIES, STATUS_COLUMNS, SortField, SortOrder } from '@/types/codeboard';
import { useUpdateIssue } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';
import {
  ChevronDown,
  ChevronRight,
  Plus,
  GripVertical,
  Circle,
  CheckCircle2,
  Clock,
  AlertCircle
} from 'lucide-react';

interface SelectionAPI {
  // CB-2018 — page-level multi-select state forwarded into the list view.
  // Mirrors the shape KanbanBoard accepts. When `selectMode` is true, each
  // row renders a checkbox; clicking the row toggles selection instead of
  // opening the detail modal.
  selectMode?: boolean;
  selectedIds?: Set<string>;
  onToggleSelected?: (issueId: string) => void;
}

interface HierarchyListViewProps extends SelectionAPI {
  issues: Issue[];
  onIssueClick: (issue: Issue) => void;
  onCreateClick: (status?: IssueStatus, parentId?: string) => void;
  focusedIssueId?: string | null;
  sortField?: SortField;
  sortOrder?: SortOrder;
}

// Status icons
const STATUS_ICONS: Record<string, React.ReactNode> = {
  BACKLOG: <Circle className="w-4 h-4 text-zinc-500" />,
  TODO: <Circle className="w-4 h-4 text-yellow-500" />,
  IN_PROGRESS: <Clock className="w-4 h-4 text-blue-500" />,
  IN_REVIEW: <AlertCircle className="w-4 h-4 text-purple-500" />,
  DONE: <CheckCircle2 className="w-4 h-4 text-green-500" />,
  CANCELLED: <Circle className="w-4 h-4 text-red-500 line-through" />,
};

// Type colors for the left border
const TYPE_BORDER_COLORS: Record<string, string> = {
  EPIC: 'border-l-purple-500',
  STORY: 'border-l-blue-500',
  TASK: 'border-l-zinc-500',
  BUG: 'border-l-red-500',
  SUBTASK: 'border-l-zinc-600',
};

interface TreeNode {
  issue: Issue;
  children: TreeNode[];
  level: number;
}

export function HierarchyListView({ issues, onIssueClick, onCreateClick, focusedIssueId, sortField = 'sequence', sortOrder = 'asc', selectMode = false, selectedIds, onToggleSelected }: HierarchyListViewProps) {
  const updateIssue = useUpdateIssue();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // Sorting helper function
  const sortIssuesInternal = (issuesToSort: Issue[]): Issue[] => {
    const priorityOrder: Record<string, number> = { 'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3 };
    const typeOrder: Record<string, number> = { 'EPIC': 0, 'STORY': 1, 'TASK': 2, 'BUG': 2, 'SUBTASK': 3 };
    const statusOrder: Record<string, number> = { 'IN_PROGRESS': 0, 'IN_REVIEW': 1, 'TODO': 2, 'BACKLOG': 3, 'DONE': 4, 'CANCELLED': 5 };

    return [...issuesToSort].sort((a, b) => {
      let comparison = 0;

      switch (sortField) {
        case 'sequence':
          comparison = a.sequence - b.sequence;
          break;
        case 'priority':
          comparison = (priorityOrder[a.priority] ?? 99) - (priorityOrder[b.priority] ?? 99);
          break;
        case 'createdAt':
          comparison = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
          break;
        case 'updatedAt':
          comparison = new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime();
          break;
        case 'dueDate':
          const aDate = a.dueDate ? new Date(a.dueDate).getTime() : Infinity;
          const bDate = b.dueDate ? new Date(b.dueDate).getTime() : Infinity;
          comparison = aDate - bDate;
          break;
        case 'title':
          comparison = a.title.localeCompare(b.title);
          break;
        case 'type':
          comparison = (typeOrder[a.type] ?? 99) - (typeOrder[b.type] ?? 99);
          break;
        case 'status':
          comparison = (statusOrder[a.status] ?? 99) - (statusOrder[b.status] ?? 99);
          break;
        default:
          comparison = 0;
      }

      return sortOrder === 'asc' ? comparison : -comparison;
    });
  };

  // Build tree structure
  const tree = useMemo(() => {
    const issueMap = new Map<string, Issue>();
    const childrenMap = new Map<string, Issue[]>();

    // Index all issues
    issues.forEach(issue => {
      issueMap.set(issue.id, issue);
      if (!childrenMap.has(issue.id)) {
        childrenMap.set(issue.id, []);
      }
    });

    // Build parent-child relationships
    issues.forEach(issue => {
      if (issue.parentId && issueMap.has(issue.parentId)) {
        const siblings = childrenMap.get(issue.parentId) || [];
        siblings.push(issue);
        childrenMap.set(issue.parentId, siblings);
      }
    });

    // Build tree nodes recursively
    const buildNode = (issue: Issue, level: number): TreeNode => {
      const children = sortIssuesInternal(childrenMap.get(issue.id) || [])
        .map(child => buildNode(child, level + 1));

      return { issue, children, level };
    };

    // Get root nodes (Epics and orphans)
    const roots: TreeNode[] = [];

    // First, add all Epics
    const epics = sortIssuesInternal(issues.filter(i => i.type === 'EPIC'));

    epics.forEach(epic => {
      roots.push(buildNode(epic, 0));
    });

    // Then add orphan items (no parent, not an Epic)
    const epicIds = new Set(epics.map(e => e.id));
    const orphans = issues.filter(i => {
      if (i.type === 'EPIC') return false;
      if (!i.parentId) return true;
      // Check if parent exists
      if (!issueMap.has(i.parentId)) return true;
      // Check if parent is an Epic (already handled)
      const parent = issueMap.get(i.parentId);
      if (parent?.type === 'EPIC') return false;
      // Check if ancestor is an Epic
      let current = parent;
      while (current) {
        if (current.type === 'EPIC') return false;
        current = current.parentId ? issueMap.get(current.parentId) : undefined;
      }
      return true;
    });

    if (orphans.length > 0) {
      // Create a virtual "No Epic" node
      sortIssuesInternal(orphans).forEach(orphan => {
        roots.push(buildNode(orphan, 0));
      });
    }

    return roots;
  }, [issues, sortField, sortOrder]);

  // Auto-expand all Epics on first render
  useMemo(() => {
    if (expandedIds.size === 0) {
      const epicIds = issues
        .filter(i => i.type === 'EPIC')
        .map(i => i.id);
      setExpandedIds(new Set(epicIds));
    }
  }, [issues]);

  const toggleExpand = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleStatusChange = (issueId: string, newStatus: IssueStatus) => {
    updateIssue.mutate({
      issueId,
      data: { status: newStatus },
    });
  };

  // Flatten tree for rendering
  const flattenTree = (nodes: TreeNode[], result: TreeNode[] = []): TreeNode[] => {
    nodes.forEach(node => {
      result.push(node);
      if (expandedIds.has(node.issue.id) && node.children.length > 0) {
        flattenTree(node.children, result);
      }
    });
    return result;
  };

  const flatList = flattenTree(tree);

  // Calculate stats
  const stats = useMemo(() => {
    const byStatus: Record<string, number> = {};
    const byType: Record<string, number> = {};
    issues.forEach(i => {
      byStatus[i.status] = (byStatus[i.status] || 0) + 1;
      byType[i.type] = (byType[i.type] || 0) + 1;
    });
    return { byStatus, byType };
  }, [issues]);

  return (
    <div className="h-full flex flex-col">
      {/* Stats Bar */}
      <div className="flex-shrink-0 flex items-center gap-4 px-4 py-2 bg-zinc-800/50 border-b border-zinc-700 text-xs">
        <span className="text-zinc-400">{issues.length} items</span>
        <div className="flex items-center gap-2">
          {stats.byType['EPIC'] > 0 && (
            <span className="px-2 py-0.5 bg-purple-900/30 text-purple-400 rounded">
              {stats.byType['EPIC']} Epics
            </span>
          )}
          {stats.byType['STORY'] > 0 && (
            <span className="px-2 py-0.5 bg-blue-900/30 text-blue-400 rounded">
              {stats.byType['STORY']} Stories
            </span>
          )}
          {stats.byType['TASK'] > 0 && (
            <span className="px-2 py-0.5 bg-zinc-700 text-zinc-300 rounded">
              {stats.byType['TASK']} Tasks
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {stats.byStatus['IN_PROGRESS'] > 0 && (
            <span className="px-2 py-0.5 bg-blue-900/30 text-blue-400 rounded">
              {stats.byStatus['IN_PROGRESS']} in progress
            </span>
          )}
          {stats.byStatus['DONE'] > 0 && (
            <span className="px-2 py-0.5 bg-green-900/30 text-green-400 rounded">
              {stats.byStatus['DONE']} done
            </span>
          )}
        </div>
      </div>

      {/* Header */}
      <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-zinc-900 border-b border-zinc-700 text-xs font-medium text-zinc-400">
        <div className="w-8" /> {/* Expand toggle space */}
        <div className="flex-1">Issue</div>
        <div className="w-24 text-center">Status</div>
        <div className="w-20 text-center">Priority</div>
        <div className="w-16 text-center">Points</div>
        <div className="w-24 text-center">Assignee</div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {flatList.map(node => {
          const { issue, children, level } = node;
          const hasChildren = children.length > 0;
          const isExpanded = expandedIds.has(issue.id);
          const issueType = ISSUE_TYPES.find(t => t.type === issue.type);
          const priority = PRIORITIES.find(p => p.priority === issue.priority);
          const isHovered = hoveredId === issue.id;
          const isFocused = focusedIssueId === issue.id;

          return (
            <div
              key={issue.id}
              data-issue-id={issue.id}
              className={cn(
                'flex items-center gap-2 px-4 py-2 border-b border-zinc-800 transition-colors',
                'hover:bg-zinc-800/50 cursor-pointer',
                'border-l-4',
                TYPE_BORDER_COLORS[issue.type] || 'border-l-zinc-700',
                isHovered && 'bg-zinc-800/30',
                isFocused && 'ring-2 ring-cyan-500 ring-inset bg-cyan-950/20'
              )}
              style={{ paddingLeft: `${16 + level * 24}px` }}
              onMouseEnter={() => setHoveredId(issue.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => {
                // CB-2018 — in selectMode, row click toggles selection
                // instead of opening the detail modal.
                if (selectMode && onToggleSelected) {
                  onToggleSelected(issue.id);
                  return;
                }
                onIssueClick(issue);
              }}
            >
              {/* CB-2018 — selection checkbox (only in selectMode). Sits
                  before the expand/collapse so the row's leading visual
                  cue is the selection state when the mode is active. */}
              {selectMode && (
                <div
                  className="w-5 flex-shrink-0"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleSelected?.(issue.id);
                  }}
                >
                  <input
                    type="checkbox"
                    checked={!!selectedIds?.has(issue.id)}
                    readOnly
                    aria-label={`Select ${issue.key}`}
                    className="h-4 w-4 rounded border-zinc-600 bg-zinc-700 text-emerald-500 focus:ring-emerald-500"
                  />
                </div>
              )}

              {/* Expand/Collapse Toggle */}
              <div className="w-6 flex-shrink-0">
                {hasChildren ? (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleExpand(issue.id);
                    }}
                    className="p-0.5 text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4" />
                    ) : (
                      <ChevronRight className="w-4 h-4" />
                    )}
                  </button>
                ) : (
                  <div className="w-4" />
                )}
              </div>

              {/* Type Icon */}
              <span className="text-base flex-shrink-0" title={issue.type}>
                {issueType?.icon}
              </span>

              {/* Key */}
              <span className="text-xs font-mono text-zinc-500 flex-shrink-0 w-20">
                {issue.key}
              </span>

              {/* Title */}
              <div className="flex-1 min-w-0">
                <span className={cn(
                  'text-sm truncate block',
                  issue.type === 'EPIC' && 'font-semibold text-purple-300',
                  issue.type === 'STORY' && 'font-medium text-blue-300',
                  issue.type === 'TASK' && 'text-zinc-300',
                  issue.type === 'BUG' && 'text-red-300',
                  issue.status === 'DONE' && 'line-through text-zinc-500'
                )}>
                  {issue.title}
                </span>
              </div>

              {/* Add child button (on hover) */}
              {isHovered && (issue.type === 'EPIC' || issue.type === 'STORY') && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onCreateClick('BACKLOG', issue.id);
                  }}
                  className="p-1 text-zinc-600 hover:text-cyan-400 transition-colors"
                  title={`Add ${issue.type === 'EPIC' ? 'Story' : 'Task'} to ${issue.key}`}
                >
                  <Plus className="w-4 h-4" />
                </button>
              )}

              {/* Status Dropdown */}
              <div className="w-24 flex-shrink-0">
                <select
                  value={issue.status}
                  onChange={(e) => {
                    e.stopPropagation();
                    handleStatusChange(issue.id, e.target.value as IssueStatus);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className={cn(
                    'w-full text-xs px-2 py-1 rounded border-0 cursor-pointer',
                    'bg-zinc-800 text-zinc-300 focus:outline-none focus:ring-1 focus:ring-cyan-500',
                    issue.status === 'DONE' && 'bg-green-900/30 text-green-400',
                    issue.status === 'IN_PROGRESS' && 'bg-blue-900/30 text-blue-400',
                    issue.status === 'BACKLOG' && 'bg-zinc-800 text-zinc-400'
                  )}
                >
                  {STATUS_COLUMNS.map(col => (
                    <option key={col.status} value={col.status}>
                      {col.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Priority */}
              <div className="w-20 flex-shrink-0 text-center">
                {priority && (
                  <span className={cn('text-xs', priority.color)}>
                    {priority.priority === 'CRITICAL' && '🔥 Critical'}
                    {priority.priority === 'HIGH' && '⬆ High'}
                    {priority.priority === 'MEDIUM' && '➡ Medium'}
                    {priority.priority === 'LOW' && '⬇ Low'}
                  </span>
                )}
              </div>

              {/* Story Points */}
              <div className="w-16 flex-shrink-0 text-center">
                {issue.storyPoints && (
                  <span className="text-xs px-2 py-0.5 bg-zinc-700 rounded text-zinc-300">
                    {issue.storyPoints} pts
                  </span>
                )}
              </div>

              {/* Assignee */}
              <div className="w-24 flex-shrink-0 text-center">
                {issue.assignee && (
                  <span className="text-xs text-zinc-400 truncate block" title={issue.assignee}>
                    {issue.assignee}
                  </span>
                )}
              </div>
            </div>
          );
        })}

        {flatList.length === 0 && (
          <div className="flex items-center justify-center h-full text-zinc-500">
            No issues found
          </div>
        )}
      </div>
    </div>
  );
}
