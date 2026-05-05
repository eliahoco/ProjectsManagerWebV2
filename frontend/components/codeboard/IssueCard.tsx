'use client';

/**
 * Issue Card Component - displays a single issue in the Kanban board
 */

import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { Issue, ISSUE_TYPES, PRIORITIES } from '@/types/codeboard';
import { cn } from '@/lib/utils';

interface IssueCardProps {
  issue: Issue;
  parent?: Issue;
  grandparent?: Issue;  // Epic when showing a Task under a Story
  completionInfo?: { done: number; total: number };  // For showing x% completion
  childCount?: number;  // Number of direct children
  descendantCount?: number;  // Total descendants (children, grandchildren, etc.)
  onClick?: () => void;
  isDragging?: boolean;
  showDetailLink?: boolean;  // Show link to full detail page
  isFocused?: boolean;  // Keyboard navigation focus
  // CB-2018 — multi-select mode. When `selectMode` is true, a checkbox renders
  // in the card header. Toggling the checkbox calls `onToggleSelected(issue.id)`
  // and stops the click from propagating into `onClick` (which would open
  // the detail modal). `isSelected` controls the checkbox visual state.
  selectMode?: boolean;
  isSelected?: boolean;
  onToggleSelected?: (issueId: string) => void;
}

// Type-specific styling
const TYPE_STYLES: Record<string, { bg: string; border: string; badge: string }> = {
  FEATURE: {
    bg: 'bg-blue-950/40',
    border: 'border-blue-700/60 hover:border-blue-600 border-2',
    badge: 'bg-blue-800 text-white',
  },
  EPIC: {
    bg: 'bg-purple-950/30',
    border: 'border-purple-700/50 hover:border-purple-600',
    badge: 'bg-purple-600 text-purple-100',
  },
  STORY: {
    bg: 'bg-blue-950/30',
    border: 'border-blue-700/50 hover:border-blue-600',
    badge: 'bg-blue-600 text-blue-100',
  },
  TASK: {
    bg: 'bg-zinc-800',
    border: 'border-zinc-700 hover:border-zinc-600',
    badge: 'bg-zinc-600 text-zinc-100',
  },
  BUG: {
    bg: 'bg-red-950/30',
    border: 'border-red-700/50 hover:border-red-600',
    badge: 'bg-red-600 text-red-100',
  },
  SUBTASK: {
    bg: 'bg-zinc-800/50',
    border: 'border-zinc-700/50 hover:border-zinc-600',
    badge: 'bg-zinc-700 text-zinc-300',
  },
};

export function IssueCard({ issue, parent, grandparent, completionInfo, childCount, descendantCount, onClick, isDragging, showDetailLink = true, isFocused = false, selectMode = false, isSelected = false, onToggleSelected }: IssueCardProps) {
  const issueType = ISSUE_TYPES.find(t => t.type === issue.type);
  const priority = PRIORITIES.find(p => p.priority === issue.priority);
  const typeStyle = TYPE_STYLES[issue.type] || TYPE_STYLES.TASK;
  const isDone = issue.status === 'DONE';
  const completionPercent = completionInfo
    ? Math.round((completionInfo.done / completionInfo.total) * 100)
    : null;

  // CB-2018 — in select mode, a card click toggles selection instead of
  // opening the detail modal. The checkbox itself also calls toggle (for
  // discoverability — keyboard users tab into the checkbox).
  const handleCardClick = (e: React.MouseEvent) => {
    if (selectMode && onToggleSelected) {
      e.preventDefault();
      e.stopPropagation();
      onToggleSelected(issue.id);
      return;
    }
    onClick?.();
  };

  return (
    <div
      data-testid="issue-card"
      data-issue-id={issue.id}
      data-issue-key={issue.key}
      data-status={issue.status}
      onClick={handleCardClick}
      className={cn(
        'p-3 rounded-lg border cursor-pointer transition-all',
        typeStyle.bg,
        typeStyle.border,
        isDragging && 'opacity-50 rotate-2 scale-105',
        isDone && 'opacity-90',
        isFocused && 'ring-2 ring-cyan-500 ring-offset-1 ring-offset-zinc-900',
        selectMode && isSelected && 'ring-2 ring-emerald-500 ring-offset-1 ring-offset-zinc-900'
      )}
    >
      {/* CB-2018 — selection checkbox (render only in selectMode). Sits at
          the top so it's always reachable regardless of card size. The
          `pointer-events-auto` + `stopPropagation` lets the box receive
          clicks even though the card itself owns the outer click handler. */}
      {selectMode && (
        <div
          className="mb-2 flex items-center"
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelected?.(issue.id);
          }}
        >
          <input
            type="checkbox"
            checked={isSelected}
            readOnly
            tabIndex={0}
            aria-label={`Select ${issue.key}`}
            className="h-4 w-4 rounded border-zinc-600 bg-zinc-700 text-emerald-500 focus:ring-emerald-500"
          />
          <span className="ml-2 text-[10px] text-zinc-500">
            {isSelected ? 'Selected' : 'Click to select'}
          </span>
        </div>
      )}

      {/* Hierarchy Context (Epic → Story) - grayed out for DONE items */}
      {(grandparent || parent) && (
        <div className={cn(
          'flex flex-col gap-0.5 mb-2 text-xs',
          isDone ? 'text-zinc-600' : 'text-zinc-500'
        )}>
          {grandparent && (
            <div className="flex items-center gap-1">
              <span className="opacity-50">{ISSUE_TYPES.find(t => t.type === grandparent.type)?.icon}</span>
              <span className="truncate opacity-70">{grandparent.key}</span>
              {completionPercent !== null && (
                <span className="ml-auto text-[10px] px-1.5 py-0.5 bg-green-900/30 text-green-500 rounded">
                  {completionPercent}%
                </span>
              )}
            </div>
          )}
          {parent && (
            <div className="flex items-center gap-1 pl-2">
              <span className="opacity-50">↳</span>
              <span className="opacity-50">{ISSUE_TYPES.find(t => t.type === parent.type)?.icon}</span>
              <span className="truncate opacity-70">{parent.key}: {parent.title}</span>
            </div>
          )}
        </div>
      )}

      {/* Type Badge + Key + Priority + Detail Link */}
      <div className="flex items-center gap-2 mb-2">
        <span className={cn('text-[10px] font-semibold px-1.5 py-0.5 rounded', typeStyle.badge)}>
          {issue.type}
        </span>
        <span className="text-xs font-mono text-zinc-500">{issue.key}</span>
        <div className="flex items-center gap-1 ml-auto">
          {showDetailLink && (
            <Link
              href={`/codeboard/issues/${issue.id}`}
              onClick={(e) => e.stopPropagation()}
              className="p-1 text-zinc-600 hover:text-cyan-400 rounded transition-colors"
              title="Open full detail view"
            >
              <ExternalLink className="w-3 h-3" />
            </Link>
          )}
          {priority && (
            <span className={cn('text-xs', priority.color)}>
              {priority.priority === 'CRITICAL' && '🔥'}
              {priority.priority === 'HIGH' && '⬆'}
              {priority.priority === 'MEDIUM' && '➡'}
              {priority.priority === 'LOW' && '⬇'}
            </span>
          )}
        </div>
      </div>

      {/* Title */}
      <h4 className="text-sm font-medium text-zinc-200 line-clamp-2 mb-2">
        {issue.title}
      </h4>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <div className="flex items-center gap-2">
          {issue.storyPoints && (
            <span className="px-1.5 py-0.5 bg-zinc-700/50 rounded">
              {issue.storyPoints} pts
            </span>
          )}
          {/* Child/Descendant count for parent types */}
          {(issue.type === 'FEATURE' || issue.type === 'EPIC' || issue.type === 'STORY') && descendantCount !== undefined && descendantCount > 0 && (
            <span className={cn(
              'px-1.5 py-0.5 rounded text-[10px] font-medium',
              issue.type === 'FEATURE' ? 'bg-blue-900/50 text-blue-400' :
              issue.type === 'EPIC' ? 'bg-purple-900/50 text-purple-400' :
              'bg-blue-900/50 text-blue-400'
            )} title={`${childCount || 0} direct children, ${descendantCount} total descendants`}>
              📦 {descendantCount}
            </span>
          )}
          {issue.assignee && (
            <span className="truncate max-w-[80px]" title={issue.assignee}>
              👤 {issue.assignee}
            </span>
          )}
        </div>
        {issue.dueDate && (
          <span className={cn(
            new Date(issue.dueDate) < new Date() ? 'text-red-500' : ''
          )}>
            📅 {new Date(issue.dueDate).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}
