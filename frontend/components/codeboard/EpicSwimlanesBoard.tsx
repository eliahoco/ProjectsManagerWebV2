'use client';

/**
 * Epic Swimlanes Board - Jira-like board with horizontal Epic swimlanes
 * Each swimlane shows Stories and Tasks belonging to that Epic
 */

import { useMemo } from 'react';
import { Issue, IssueStatus, STATUS_COLUMNS, ISSUE_TYPES, SortField, SortOrder } from '@/types/codeboard';
import { IssueCard } from './IssueCard';
import { useUpdateIssue } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronRight, Plus } from 'lucide-react';
import { useState } from 'react';

interface EpicSwimlanesBoardProps {
  issues: Issue[];
  onIssueClick: (issue: Issue) => void;
  onCreateClick: (status?: IssueStatus, parentId?: string) => void;
  focusedIssueId?: string | null;
  sortField?: SortField;
  sortOrder?: SortOrder;
}

// Type-specific styling for Epic headers
const EPIC_COLORS = [
  'bg-purple-600',
  'bg-blue-600',
  'bg-green-600',
  'bg-orange-600',
  'bg-pink-600',
  'bg-cyan-600',
  'bg-yellow-600',
];

export function EpicSwimlanesBoard({ issues, onIssueClick, onCreateClick, focusedIssueId, sortField = 'sequence', sortOrder = 'asc' }: EpicSwimlanesBoardProps) {
  const updateIssue = useUpdateIssue();
  const [collapsedEpics, setCollapsedEpics] = useState<Set<string>>(new Set());

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

  // Build issue map for lookups
  const issueMap = useMemo(() => {
    const map: Record<string, Issue> = {};
    issues.forEach(issue => {
      map[issue.id] = issue;
    });
    return map;
  }, [issues]);

  // Get all Epics
  const epics = useMemo(() => {
    return sortIssuesInternal(issues.filter(i => i.type === 'EPIC'));
  }, [issues, sortField, sortOrder]);

  // Get ALL descendants for an Epic (Stories, Tasks, and Subtasks)
  const getEpicChildren = (epicId: string) => {
    const descendants: Issue[] = [];
    const visited = new Set<string>();

    // Recursive function to collect all descendants
    const collectDescendants = (parentId: string) => {
      const children = issues.filter(i => i.parentId === parentId);
      children.forEach(child => {
        if (!visited.has(child.id)) {
          visited.add(child.id);
          descendants.push(child);
          collectDescendants(child.id);
        }
      });
    };

    collectDescendants(epicId);
    return descendants;
  };

  // Get issues without Epic (orphans) - items not under any Epic hierarchy
  const orphanIssues = useMemo(() => {
    const epicIds = new Set(epics.map(e => e.id));

    // Helper to check if an issue is under an Epic
    const isUnderEpic = (issue: Issue): boolean => {
      if (!issue.parentId) return false;
      if (epicIds.has(issue.parentId)) return true;
      const parent = issueMap[issue.parentId];
      if (parent) return isUnderEpic(parent);
      return false;
    };

    return issues.filter(i => {
      if (i.type === 'EPIC') return false;
      return !isUnderEpic(i);
    });
  }, [issues, epics, issueMap]);

  const toggleEpic = (epicId: string) => {
    setCollapsedEpics(prev => {
      const next = new Set(prev);
      if (next.has(epicId)) {
        next.delete(epicId);
      } else {
        next.add(epicId);
      }
      return next;
    });
  };

  const handleDrop = (issueId: string, newStatus: IssueStatus) => {
    updateIssue.mutate({
      issueId,
      data: { status: newStatus },
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDropOnColumn = (e: React.DragEvent, status: IssueStatus) => {
    e.preventDefault();
    const issueId = e.dataTransfer.getData('issueId');
    if (issueId) {
      handleDrop(issueId, status);
    }
  };

  const handleDragStart = (e: React.DragEvent, issueId: string) => {
    e.dataTransfer.setData('issueId', issueId);
  };

  // Render a swimlane for an Epic
  const renderSwimlane = (epic: Issue | null, children: Issue[], colorIndex: number) => {
    const epicId = epic?.id || 'no-epic';
    const isCollapsed = collapsedEpics.has(epicId);
    const epicColor = EPIC_COLORS[colorIndex % EPIC_COLORS.length];

    // Count children by status
    const statusCounts: Record<string, number> = {};
    STATUS_COLUMNS.forEach(col => {
      statusCounts[col.status] = children.filter(c => c.status === col.status).length;
    });

    return (
      <div key={epicId} className="mb-4">
        {/* Epic Header */}
        <div
          className={cn(
            'flex items-center gap-3 p-3 rounded-t-lg cursor-pointer',
            epic ? epicColor : 'bg-zinc-700'
          )}
          onClick={() => toggleEpic(epicId)}
        >
          {isCollapsed ? (
            <ChevronRight className="w-5 h-5 text-white/80" />
          ) : (
            <ChevronDown className="w-5 h-5 text-white/80" />
          )}

          <span className="text-lg">
            {epic ? ISSUE_TYPES.find(t => t.type === 'EPIC')?.icon : '📋'}
          </span>

          <div className="flex-1">
            <span className="font-semibold text-white">
              {epic ? `${epic.key}: ${epic.title}` : 'No Epic'}
            </span>
            <span className="ml-3 text-white/60 text-sm">
              ({children.length} items)
            </span>
          </div>

          {/* Status summary badges */}
          <div className="flex gap-2">
            {STATUS_COLUMNS.map(col => {
              const count = statusCounts[col.status];
              if (count === 0) return null;
              return (
                <span
                  key={col.status}
                  className={cn(
                    'text-xs px-2 py-0.5 rounded-full bg-black/20 text-white/80'
                  )}
                >
                  {col.label}: {count}
                </span>
              );
            })}
          </div>
        </div>

        {/* Swimlane Content (columns) */}
        {!isCollapsed && (
          <div className="flex border border-t-0 border-zinc-700 rounded-b-lg overflow-hidden">
            {STATUS_COLUMNS.map(column => {
              const columnIssues = sortIssuesInternal(
                children.filter(i => i.status === column.status)
              );

              return (
                <div
                  key={column.status}
                  data-status={column.status}
                  data-testid={`swimlane-column-${column.status.toLowerCase()}`}
                  className="flex-1 min-w-[200px] border-r border-zinc-700 last:border-r-0"
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDropOnColumn(e, column.status)}
                >
                  {/* Column Header */}
                  <div className="flex items-center justify-between px-3 py-2 bg-zinc-800/50 border-b border-zinc-700">
                    <div className="flex items-center gap-2">
                      <div className={cn('w-2 h-2 rounded-full', column.color)} />
                      <span className="text-xs font-medium text-zinc-400">{column.label}</span>
                      <span className="text-xs text-zinc-600">({columnIssues.length})</span>
                    </div>
                    {epic && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onCreateClick(column.status, epic.id);
                        }}
                        className="p-0.5 text-zinc-600 hover:text-zinc-400 transition-colors"
                        title="Add issue to this Epic"
                      >
                        <Plus className="w-3 h-3" />
                      </button>
                    )}
                  </div>

                  {/* Issues - grouped by parent Story */}
                  <div className="p-2 min-h-[100px] max-h-[300px] overflow-y-auto bg-zinc-900/30">
                    {columnIssues.length === 0 ? (
                      <div className="text-xs text-zinc-600 text-center py-4">
                        No items
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {(() => {
                          // Group issues: Stories first, then Tasks grouped by parent
                          const stories = columnIssues.filter(i => i.type === 'STORY');
                          const tasks = columnIssues.filter(i => i.type === 'TASK' || i.type === 'SUBTASK' || i.type === 'BUG');

                          // Group tasks by parent Story
                          const tasksByParent: Record<string, typeof tasks> = {};
                          const orphanTasks: typeof tasks = [];

                          tasks.forEach(task => {
                            const parent = task.parentId ? issueMap[task.parentId] : undefined;
                            if (parent?.type === 'STORY') {
                              if (!tasksByParent[parent.id]) tasksByParent[parent.id] = [];
                              tasksByParent[parent.id].push(task);
                            } else {
                              orphanTasks.push(task);
                            }
                          });

                          const elements: React.ReactNode[] = [];

                          // Render Stories with their child Tasks
                          stories.forEach(story => {
                            elements.push(
                              <div
                                key={story.id}
                                draggable
                                onDragStart={(e) => handleDragStart(e, story.id)}
                              >
                                <IssueCard
                                  issue={story}
                                  onClick={() => onIssueClick(story)}
                                  isFocused={focusedIssueId === story.id}
                                />
                              </div>
                            );

                            // Render child tasks indented
                            const childTasks = tasksByParent[story.id] || [];
                            childTasks.forEach(task => {
                              elements.push(
                                <div
                                  key={task.id}
                                  className="ml-3 border-l-2 border-blue-700/30 pl-2"
                                  draggable
                                  onDragStart={(e) => handleDragStart(e, task.id)}
                                >
                                  <IssueCard
                                    issue={task}
                                    onClick={() => onIssueClick(task)}
                                    isFocused={focusedIssueId === task.id}
                                  />
                                </div>
                              );
                            });
                          });

                          // Render orphan tasks (tasks not under a Story in this column)
                          orphanTasks.forEach(task => {
                            const parent = task.parentId ? issueMap[task.parentId] : undefined;
                            elements.push(
                              <div
                                key={task.id}
                                draggable
                                onDragStart={(e) => handleDragStart(e, task.id)}
                              >
                                <IssueCard
                                  issue={task}
                                  parent={parent?.type === 'STORY' ? parent : undefined}
                                  onClick={() => onIssueClick(task)}
                                  isFocused={focusedIssueId === task.id}
                                />
                              </div>
                            );
                          });

                          return elements;
                        })()}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full overflow-y-auto">
      {/* Column Headers (fixed) */}
      <div className="sticky top-0 z-10 flex bg-zinc-900 border-b border-zinc-700 mb-4">
        <div className="w-[250px] flex-shrink-0 p-3 font-medium text-zinc-400">
          Epic
        </div>
        {STATUS_COLUMNS.map(column => (
          <div
            key={column.status}
            className="flex-1 min-w-[200px] p-3 border-l border-zinc-700"
          >
            <div className="flex items-center gap-2">
              <div className={cn('w-3 h-3 rounded-full', column.color)} />
              <span className="font-medium text-zinc-400">{column.label}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Epic Swimlanes */}
      <div className="px-2">
        {epics.map((epic, index) => {
          const children = getEpicChildren(epic.id);
          return renderSwimlane(epic, children, index);
        })}

        {/* No Epic section */}
        {orphanIssues.length > 0 && renderSwimlane(null, orphanIssues, epics.length)}
      </div>
    </div>
  );
}
