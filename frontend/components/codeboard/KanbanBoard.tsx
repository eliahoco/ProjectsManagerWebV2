'use client';

/**
 * Kanban Board Component - Status columns with hierarchy grouping
 */

import { useMemo } from 'react';
import { Issue, IssueStatus, STATUS_COLUMNS, ISSUE_TYPES, SortField, SortOrder } from '@/types/codeboard';
import { IssueCard } from './IssueCard';
import { useUpdateIssue } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';
import { Plus } from 'lucide-react';

interface KanbanBoardProps {
  issues: Issue[];
  onIssueClick: (issue: Issue) => void;
  onCreateClick: (status?: IssueStatus) => void;
  onFeatureDropToTodo?: (feature: Issue) => void;
  onCascadeMove?: (feature: Issue, newStatus: IssueStatus) => void;
  focusedIssueId?: string | null;
  sortField?: SortField;
  sortOrder?: SortOrder;
}

export function KanbanBoard({ issues, onIssueClick, onCreateClick, onFeatureDropToTodo, onCascadeMove, focusedIssueId, sortField = 'sequence', sortOrder = 'asc' }: KanbanBoardProps) {
  const updateIssue = useUpdateIssue();

  // Sorting helper function
  const sortIssuesInternal = (issuesToSort: Issue[]): Issue[] => {
    const priorityOrder: Record<string, number> = { 'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3 };
    const typeOrder: Record<string, number> = { 'FEATURE': 0, 'EPIC': 1, 'STORY': 2, 'TASK': 3, 'BUG': 3, 'SUBTASK': 4 };
    const statusOrder: Record<string, number> = { 'IN_PROGRESS': 0, 'IN_REVIEW': 1, 'COMPLETED_WAITING_QA': 2, 'TODO': 3, 'BACKLOG': 4, 'DONE': 5, 'CANCELLED': 6 };

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

  // Build lookup map for parent references
  const issueMap = useMemo(() => {
    const map: Record<string, Issue> = {};
    issues.forEach(issue => {
      map[issue.id] = issue;
    });
    return map;
  }, [issues]);

  // Calculate children and descendants for each issue
  const childCountMap = useMemo(() => {
    const directChildren: Record<string, number> = {};
    const allDescendants: Record<string, number> = {};

    // First pass: count direct children
    issues.forEach(issue => {
      if (issue.parentId) {
        directChildren[issue.parentId] = (directChildren[issue.parentId] || 0) + 1;
      }
    });

    // Recursive function to count all descendants
    const countDescendants = (parentId: string, visited: Set<string> = new Set()): number => {
      if (visited.has(parentId)) return 0;
      visited.add(parentId);

      let count = 0;
      issues.forEach(issue => {
        if (issue.parentId === parentId) {
          count += 1 + countDescendants(issue.id, visited);
        }
      });
      return count;
    };

    // Calculate descendants for each issue
    issues.forEach(issue => {
      allDescendants[issue.id] = countDescendants(issue.id);
    });

    return { directChildren, allDescendants };
  }, [issues]);

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
      const issue = issueMap[issueId];

      // Handle FEATURE moves with cascade
      if (issue?.type === 'FEATURE') {
        // If moving from BACKLOG to TODO, trigger Feature Execution Panel
        if (issue.status === 'BACKLOG' && status === 'TODO' && onFeatureDropToTodo) {
          // Use cascade move if available
          if (onCascadeMove) {
            onCascadeMove(issue, status);
          } else {
            updateIssue.mutate({ issueId, data: { status } });
          }
          // Then trigger the Feature Execution Panel
          setTimeout(() => onFeatureDropToTodo(issue), 100);
          return;
        }

        // For all other FEATURE moves, use cascade move
        if (onCascadeMove) {
          onCascadeMove(issue, status);
          return;
        }
      }

      handleDrop(issueId, status);
    }
  };

  const handleDragStart = (e: React.DragEvent, issueId: string) => {
    e.dataTransfer.setData('issueId', issueId);
  };

  // CB-1944: kanban columns must reflect each issue's OWN status. A descendant
  // of a FEATURE in column X should NOT be force-claimed into column X if its
  // own status places it elsewhere — it belongs in the column matching its own
  // status, falling back to the existing orphan-rendering paths when its
  // parent isn't visible in the same column.

  // Group issues by status. Each issue lands in the column matching its own
  // status. Within a column, descendants whose parent is also in this column
  // render nested under that parent (Feature → Epic → Story → Task → Subtask);
  // descendants whose parent is in a different column render as orphans with
  // breadcrumb context.
  const getColumnIssues = (status: IssueStatus) => {
    // All issues of this status, by type, sorted
    const sameStatus = issues.filter(i => i.status === status);
    const features = sortIssuesInternal(sameStatus.filter(i => i.type === 'FEATURE'));
    const featureIds = new Set(features.map(f => f.id));

    const epics = sortIssuesInternal(sameStatus.filter(i => i.type === 'EPIC'));
    const stories = sortIssuesInternal(sameStatus.filter(i => i.type === 'STORY'));
    const tasks = sortIssuesInternal(sameStatus.filter(i => i.type === 'TASK' || i.type === 'BUG'));
    const subtasks = sortIssuesInternal(sameStatus.filter(i => i.type === 'SUBTASK'));

    // Total count = everything with this own-status, regardless of nesting.
    const uniqueNonFeature = [...epics, ...stories, ...tasks, ...subtasks];

    // Group Epics by their parent Feature (in this column)
    const epicsByFeature: Record<string, Issue[]> = {};
    const orphanEpics: Issue[] = [];

    epics.forEach(epic => {
      const parent = epic.parentId ? issueMap[epic.parentId] : undefined;
      if (parent?.type === 'FEATURE' && featureIds.has(parent.id)) {
        if (!epicsByFeature[parent.id]) epicsByFeature[parent.id] = [];
        epicsByFeature[parent.id].push(epic);
      } else {
        orphanEpics.push(epic);
      }
    });

    // Group Stories by their parent Epic (present in this column's scope)
    const epicIdSet = new Set(epics.map(e => e.id));
    const storiesByEpic: Record<string, Issue[]> = {};
    const orphanStories: Issue[] = [];

    stories.forEach(story => {
      const parent = story.parentId ? issueMap[story.parentId] : undefined;
      if (parent?.type === 'EPIC' && epicIdSet.has(parent.id)) {
        if (!storiesByEpic[parent.id]) storiesByEpic[parent.id] = [];
        storiesByEpic[parent.id].push(story);
      } else {
        orphanStories.push(story);
      }
    });

    // Group Tasks by their parent Story (present in this column's scope)
    const storyIdSet = new Set(stories.map(s => s.id));
    const tasksByStory: Record<string, Issue[]> = {};
    const orphanTasks: Issue[] = [];

    tasks.forEach(task => {
      const parent = task.parentId ? issueMap[task.parentId] : undefined;
      if (parent?.type === 'STORY' && storyIdSet.has(parent.id)) {
        if (!tasksByStory[parent.id]) tasksByStory[parent.id] = [];
        tasksByStory[parent.id].push(task);
      } else {
        orphanTasks.push(task);
      }
    });

    // Group Subtasks by their parent Task (present in this column's scope)
    const taskIdSet = new Set(tasks.map(t => t.id));
    const subtasksByTask: Record<string, Issue[]> = {};
    const orphanSubtasks: Issue[] = [];

    subtasks.forEach(subtask => {
      const parent = subtask.parentId ? issueMap[subtask.parentId] : undefined;
      if (parent?.type === 'TASK' && taskIdSet.has(parent.id)) {
        if (!subtasksByTask[parent.id]) subtasksByTask[parent.id] = [];
        subtasksByTask[parent.id].push(subtask);
      } else {
        orphanSubtasks.push(subtask);
      }
    });

    // Total count: features + all unique non-feature items in this column's scope
    const total = features.length + uniqueNonFeature.length;

    return { features, epicsByFeature, orphanEpics, epics, storiesByEpic, orphanStories, tasksByStory, orphanTasks, subtasksByTask, orphanSubtasks, total };
  };

  return (
    <div className="flex gap-4 overflow-x-auto pb-4 h-full">
      {STATUS_COLUMNS.map(column => {
        const { features, epicsByFeature, orphanEpics, epics, storiesByEpic, orphanStories, tasksByStory, orphanTasks, subtasksByTask, orphanSubtasks, total } = getColumnIssues(column.status);

        return (
          <div
            key={column.status}
            data-status={column.status}
            data-testid={`kanban-column-${column.status.toLowerCase()}`}
            className="flex flex-col w-80 flex-shrink-0"
            onDragOver={handleDragOver}
            onDrop={(e) => handleDropOnColumn(e, column.status)}
          >
            {/* Column Header */}
            <div className="flex items-center justify-between mb-3 px-1">
              <div className="flex items-center gap-2">
                <div className={cn('w-3 h-3 rounded-full', column.color)} />
                <h3 className="font-medium text-zinc-300">{column.label}</h3>
                <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded-full">
                  {total}
                </span>
              </div>
              <button
                onClick={() => onCreateClick(column.status)}
                className="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded transition-colors"
                title="Add issue"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>

            {/* Issues */}
            <div className="flex flex-col gap-2 flex-1 min-h-[200px] overflow-y-auto p-2 bg-zinc-900/50 rounded-lg border border-zinc-800">
              {/* Features with their child Epics */}
              {features.map(feature => {
                const childEpics = epicsByFeature[feature.id] || [];

                return (
                  <div key={feature.id} className="space-y-1">
                    {/* Feature */}
                    <div
                      draggable
                      onDragStart={(e) => handleDragStart(e, feature.id)}
                    >
                      <IssueCard
                        issue={feature}
                        onClick={() => onIssueClick(feature)}
                        isFocused={focusedIssueId === feature.id}
                        childCount={childCountMap.directChildren[feature.id] || 0}
                        descendantCount={childCountMap.allDescendants[feature.id] || 0}
                      />
                    </div>
                    {/* Child Epics indented under Feature */}
                    {childEpics.map(epic => {
                      const childStories = storiesByEpic[epic.id] || [];
                      return (
                        <div key={epic.id} className="ml-3 border-l-2 border-amber-600/30 pl-2 space-y-1">
                          <div
                            draggable
                            onDragStart={(e) => handleDragStart(e, epic.id)}
                          >
                            <IssueCard
                              issue={epic}
                              onClick={() => onIssueClick(epic)}
                              isFocused={focusedIssueId === epic.id}
                              childCount={childCountMap.directChildren[epic.id] || 0}
                              descendantCount={childCountMap.allDescendants[epic.id] || 0}
                            />
                          </div>
                          {/* Child Stories */}
                          {childStories.map(story => {
                            const childTasks = tasksByStory[story.id] || [];
                            return (
                              <div key={story.id} className="ml-3 border-l-2 border-purple-600/30 pl-2 space-y-1">
                                <div
                                  draggable
                                  onDragStart={(e) => handleDragStart(e, story.id)}
                                >
                                  <IssueCard
                                    issue={story}
                                    onClick={() => onIssueClick(story)}
                                    isFocused={focusedIssueId === story.id}
                                    childCount={childCountMap.directChildren[story.id] || 0}
                                    descendantCount={childCountMap.allDescendants[story.id] || 0}
                                  />
                                </div>
                                {childTasks.map(task => (
                                  <div
                                    key={task.id}
                                    className="ml-3 border-l-2 border-blue-600/30 pl-2"
                                    draggable
                                    onDragStart={(e) => handleDragStart(e, task.id)}
                                  >
                                    <IssueCard
                                      issue={task}
                                      onClick={() => onIssueClick(task)}
                                      isFocused={focusedIssueId === task.id}
                                    />
                                  </div>
                                ))}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                );
              })}

              {/* Orphan Epics (not under a Feature in this column) with their child Stories and Tasks */}
              {orphanEpics.map(epic => {
                const childStories = storiesByEpic[epic.id] || [];

                return (
                  <div key={epic.id} className="space-y-1">
                    {/* Epic */}
                    <div
                      draggable
                      onDragStart={(e) => handleDragStart(e, epic.id)}
                    >
                      <IssueCard
                        issue={epic}
                        onClick={() => onIssueClick(epic)}
                        isFocused={focusedIssueId === epic.id}
                        childCount={childCountMap.directChildren[epic.id] || 0}
                        descendantCount={childCountMap.allDescendants[epic.id] || 0}
                      />
                    </div>
                    {/* Child Stories indented under Epic */}
                    {childStories.map(story => {
                      const childTasks = tasksByStory[story.id] || [];
                      return (
                        <div key={story.id} className="ml-3 border-l-2 border-purple-600/30 pl-2 space-y-1">
                          <div
                            draggable
                            onDragStart={(e) => handleDragStart(e, story.id)}
                          >
                            <IssueCard
                              issue={story}
                              onClick={() => onIssueClick(story)}
                              isFocused={focusedIssueId === story.id}
                              childCount={childCountMap.directChildren[story.id] || 0}
                              descendantCount={childCountMap.allDescendants[story.id] || 0}
                            />
                          </div>
                          {/* Child Tasks indented under Story */}
                          {childTasks.map(task => {
                            const childSubtasks = subtasksByTask[task.id] || [];
                            return (
                              <div key={task.id} className="ml-3 border-l-2 border-blue-600/30 pl-2 space-y-1">
                                <div
                                  draggable
                                  onDragStart={(e) => handleDragStart(e, task.id)}
                                >
                                  <IssueCard
                                    issue={task}
                                    onClick={() => onIssueClick(task)}
                                    isFocused={focusedIssueId === task.id}
                                  />
                                </div>
                                {/* Child Subtasks indented under Task */}
                                {childSubtasks.map(subtask => (
                                  <div
                                    key={subtask.id}
                                    className="ml-3 border-l-2 border-cyan-600/30 pl-2"
                                    draggable
                                    onDragStart={(e) => handleDragStart(e, subtask.id)}
                                  >
                                    <IssueCard
                                      issue={subtask}
                                      onClick={() => onIssueClick(subtask)}
                                      isFocused={focusedIssueId === subtask.id}
                                    />
                                  </div>
                                ))}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                );
              })}

              {/* Orphan Stories (parent Epic is in different column) with their Tasks */}
              {orphanStories.map(story => {
                const childTasks = tasksByStory[story.id] || [];
                const parent = story.parentId ? issueMap[story.parentId] : undefined;

                return (
                  <div key={story.id} className="space-y-1">
                    <div
                      draggable
                      onDragStart={(e) => handleDragStart(e, story.id)}
                    >
                      <IssueCard
                        issue={story}
                        parent={parent?.type === 'EPIC' ? parent : undefined}
                        onClick={() => onIssueClick(story)}
                        isFocused={focusedIssueId === story.id}
                        childCount={childCountMap.directChildren[story.id] || 0}
                        descendantCount={childCountMap.allDescendants[story.id] || 0}
                      />
                    </div>
                    {/* Child tasks indented */}
                    {childTasks.map(task => {
                      const childSubtasks = subtasksByTask[task.id] || [];
                      return (
                        <div key={task.id} className="ml-3 border-l-2 border-blue-600/30 pl-2 space-y-1">
                          <div
                            draggable
                            onDragStart={(e) => handleDragStart(e, task.id)}
                          >
                            <IssueCard
                              issue={task}
                              onClick={() => onIssueClick(task)}
                              isFocused={focusedIssueId === task.id}
                            />
                          </div>
                          {childSubtasks.map(subtask => (
                            <div
                              key={subtask.id}
                              className="ml-3 border-l-2 border-cyan-600/30 pl-2"
                              draggable
                              onDragStart={(e) => handleDragStart(e, subtask.id)}
                            >
                              <IssueCard
                                issue={subtask}
                                onClick={() => onIssueClick(subtask)}
                                isFocused={focusedIssueId === subtask.id}
                              />
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                );
              })}

              {/* Orphan Tasks (parent Story is in different column) */}
              {orphanTasks.map(task => {
                const parent = task.parentId ? issueMap[task.parentId] : undefined;
                const grandparent = parent?.parentId ? issueMap[parent.parentId] : undefined;
                const childSubtasks = subtasksByTask[task.id] || [];

                // Calculate completion info for the grandparent (Epic)
                const completionInfo = grandparent ? (() => {
                  const epicDescendants = issues.filter(i => {
                    if (i.parentId === grandparent.id) return true;
                    const p = issueMap[i.parentId || ''];
                    if (p?.parentId === grandparent.id) return true;
                    const gp = issueMap[p?.parentId || ''];
                    if (gp?.parentId === grandparent.id) return true;
                    return false;
                  });
                  const done = epicDescendants.filter(i => i.status === 'DONE').length;
                  return { done, total: epicDescendants.length };
                })() : undefined;

                return (
                  <div key={task.id} className="space-y-1">
                    <div
                      draggable
                      onDragStart={(e) => handleDragStart(e, task.id)}
                    >
                      <IssueCard
                        issue={task}
                        parent={parent?.type === 'STORY' ? parent : undefined}
                        grandparent={grandparent?.type === 'EPIC' ? grandparent : undefined}
                        completionInfo={completionInfo}
                        onClick={() => onIssueClick(task)}
                        isFocused={focusedIssueId === task.id}
                      />
                    </div>
                    {childSubtasks.map(subtask => (
                      <div
                        key={subtask.id}
                        className="ml-3 border-l-2 border-cyan-600/30 pl-2"
                        draggable
                        onDragStart={(e) => handleDragStart(e, subtask.id)}
                      >
                        <IssueCard
                          issue={subtask}
                          onClick={() => onIssueClick(subtask)}
                          isFocused={focusedIssueId === subtask.id}
                        />
                      </div>
                    ))}
                  </div>
                );
              })}

              {/* Orphan Subtasks (parent Task is in different column) */}
              {orphanSubtasks.map(subtask => {
                const parent = subtask.parentId ? issueMap[subtask.parentId] : undefined;
                const grandparent = parent?.parentId ? issueMap[parent.parentId] : undefined;
                const greatGrandparent = grandparent?.parentId ? issueMap[grandparent.parentId] : undefined;

                return (
                  <div
                    key={subtask.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, subtask.id)}
                  >
                    <IssueCard
                      issue={subtask}
                      parent={parent}
                      grandparent={grandparent?.type === 'STORY' ? grandparent : (greatGrandparent?.type === 'EPIC' ? greatGrandparent : undefined)}
                      onClick={() => onIssueClick(subtask)}
                      isFocused={focusedIssueId === subtask.id}
                    />
                  </div>
                );
              })}

              {total === 0 && (
                <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm py-8">
                  No issues
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
