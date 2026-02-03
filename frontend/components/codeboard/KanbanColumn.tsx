'use client';

/**
 * Kanban Column Component - displays a status column with issues
 */

import { Issue, IssueStatus, STATUS_COLUMNS } from '@/types/codeboard';
import { IssueCard } from './IssueCard';
import { cn } from '@/lib/utils';
import { Plus } from 'lucide-react';

interface KanbanColumnProps {
  status: IssueStatus;
  issues: Issue[];
  issueMap?: Record<string, Issue>;
  onIssueClick: (issue: Issue) => void;
  onCreateClick: () => void;
  onDrop?: (issueId: string, newStatus: IssueStatus) => void;
}

export function KanbanColumn({
  status,
  issues,
  issueMap = {},
  onIssueClick,
  onCreateClick,
  onDrop,
}: KanbanColumnProps) {
  const column = STATUS_COLUMNS.find(c => c.status === status);
  const columnIssues = issues.filter(issue => issue.status === status);

  // Sort: Epics first, then Stories, then Tasks
  const sortedIssues = [...columnIssues].sort((a, b) => {
    const typeOrder: Record<string, number> = { 'EPIC': 0, 'STORY': 1, 'TASK': 2, 'SUBTASK': 3, 'BUG': 2 };
    const orderA = typeOrder[a.type] ?? 99;
    const orderB = typeOrder[b.type] ?? 99;
    if (orderA !== orderB) return orderA - orderB;
    return a.sequence - b.sequence;
  });

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.currentTarget.classList.add('bg-zinc-800/50');
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.currentTarget.classList.remove('bg-zinc-800/50');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.currentTarget.classList.remove('bg-zinc-800/50');
    const issueId = e.dataTransfer.getData('issueId');
    if (issueId && onDrop) {
      onDrop(issueId, status);
    }
  };

  const handleDragStart = (e: React.DragEvent, issueId: string) => {
    e.dataTransfer.setData('issueId', issueId);
  };

  return (
    <div
      className="flex flex-col w-80 flex-shrink-0"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Column Header */}
      <div className="flex items-center justify-between mb-3 px-1">
        <div className="flex items-center gap-2">
          <div className={cn('w-3 h-3 rounded-full', column?.color)} />
          <h3 className="font-medium text-zinc-300">{column?.label}</h3>
          <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">
            {columnIssues.length}
          </span>
        </div>
        <button
          onClick={onCreateClick}
          className="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded transition-colors"
          title="Add issue"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Issues */}
      <div className="flex flex-col gap-2 flex-1 min-h-[200px] max-h-[calc(100vh-220px)] overflow-y-auto p-2 bg-zinc-900/50 rounded-lg border border-zinc-800">
        {sortedIssues.map(issue => {
          const parent = issue.parentId ? issueMap[issue.parentId] : undefined;
          return (
            <div
              key={issue.id}
              draggable
              onDragStart={(e) => handleDragStart(e, issue.id)}
            >
              <IssueCard
                issue={issue}
                parent={parent}
                onClick={() => onIssueClick(issue)}
              />
            </div>
          );
        })}

        {columnIssues.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
            No issues
          </div>
        )}
      </div>
    </div>
  );
}
