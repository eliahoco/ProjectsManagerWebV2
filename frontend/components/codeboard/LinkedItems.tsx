'use client';

/**
 * LinkedItems Component - displays parent/children hierarchy and related issues
 */

import { Issue, ISSUE_TYPES, STATUS_COLUMNS } from '@/types/codeboard';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Plus, ArrowUp, ArrowDown, Link2 } from 'lucide-react';

interface LinkedItemsProps {
  issue: Issue;
  issues?: Issue[]; // All issues for parent lookup
  onIssueClick?: (issue: Issue) => void;
  onLinkIssue?: () => void;
}

export function LinkedItems({ issue, issues = [], onIssueClick, onLinkIssue }: LinkedItemsProps) {
  // Find parent issue
  const parent = issue.parentId
    ? issues.find(i => i.id === issue.parentId)
    : null;

  // Get children from issue object
  const children = issue.children || [];

  // Check if we have any linked content to show
  const hasContent = parent || children.length > 0;

  return (
    <div className="space-y-6">
      {/* Parent */}
      {parent && (
        <div>
          <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
            <ArrowUp className="h-4 w-4" />
            Parent
          </h4>
          <LinkedIssueCard issue={parent} onClick={() => onIssueClick?.(parent)} />
        </div>
      )}

      {/* Children */}
      {children.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
            <ArrowDown className="h-4 w-4" />
            Child Issues ({children.length})
          </h4>
          <div className="space-y-2">
            {children.map(child => (
              <LinkedIssueCard
                key={child.id}
                issue={child}
                onClick={() => onIssueClick?.(child)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Related Issues - placeholder for future IssueLink implementation */}
      {/* When IssueLink data is available, render related issues here */}

      {/* Empty state */}
      {!hasContent && (
        <p className="text-sm text-zinc-500 text-center py-4">
          No linked issues yet
        </p>
      )}

      {/* Link Issue Button */}
      <Button
        variant="outline"
        size="sm"
        className="w-full"
        onClick={onLinkIssue}
      >
        <Plus className="h-4 w-4 mr-2" />
        Link Issue
      </Button>
    </div>
  );
}

interface LinkedIssueCardProps {
  issue: Issue;
  onClick?: () => void;
}

function LinkedIssueCard({ issue, onClick }: LinkedIssueCardProps) {
  const issueType = ISSUE_TYPES.find(t => t.type === issue.type);
  const status = STATUS_COLUMNS.find(s => s.status === issue.status);

  // Type-specific border colors
  const borderColor = {
    FEATURE: 'border-l-amber-500',
    EPIC: 'border-l-purple-500',
    STORY: 'border-l-blue-500',
    TASK: 'border-l-zinc-500',
    BUG: 'border-l-red-500',
    SUBTASK: 'border-l-zinc-600',
  }[issue.type] || 'border-l-zinc-500';

  // Type badge styles
  const badgeStyle = {
    FEATURE: 'bg-amber-600 text-amber-100',
    EPIC: 'bg-purple-600 text-purple-100',
    STORY: 'bg-blue-600 text-blue-100',
    TASK: 'bg-zinc-600 text-zinc-100',
    BUG: 'bg-red-600 text-red-100',
    SUBTASK: 'bg-zinc-700 text-zinc-300',
  }[issue.type] || 'bg-zinc-600 text-zinc-100';

  // Status badge styles
  const statusStyle = cn(
    'text-xs px-2 py-0.5 rounded shrink-0',
    issue.status === 'DONE' && 'bg-green-900/30 text-green-400',
    issue.status === 'IN_PROGRESS' && 'bg-blue-900/30 text-blue-400',
    issue.status === 'IN_REVIEW' && 'bg-purple-900/30 text-purple-400',
    issue.status === 'BACKLOG' && 'bg-zinc-700 text-zinc-400',
    issue.status === 'TODO' && 'bg-yellow-900/30 text-yellow-400',
    issue.status === 'CANCELLED' && 'bg-red-900/30 text-red-400'
  );

  return (
    <div
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 p-3 rounded-lg border-l-4 cursor-pointer transition-colors',
        'bg-zinc-800/50 hover:bg-zinc-800',
        borderColor
      )}
    >
      {/* Type Icon */}
      <span className="text-base shrink-0">{issueType?.icon}</span>

      {/* Key Badge */}
      <span className={cn('text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0', badgeStyle)}>
        {issue.key}
      </span>

      {/* Title */}
      <span className="text-sm truncate flex-1 text-zinc-200">{issue.title}</span>

      {/* Status Badge */}
      <span className={statusStyle}>
        {status?.label || issue.status}
      </span>
    </div>
  );
}

export { LinkedIssueCard };
