'use client';

/**
 * Issue Detail Page - Full page view for a single issue
 * Route: /codeboard/issues/[id]
 */

import { use, useState, useMemo, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Edit2,
  Trash2,
  Clock,
  User,
  Calendar,
  GitCommit,
  Sparkles,
  ChevronRight,
  Link2,
  CheckCircle,
  ExternalLink,
  MoreHorizontal,
  MessageSquare,
  Activity,
  Tag,
  Target,
  AlertTriangle,
} from 'lucide-react';
import {
  useIssue,
  useUpdateIssue,
  useDeleteIssue,
  useIssueCommits,
  useLinkedCommits,
  useProjects,
  useExecutionSummaries,
  type ExecutionSession,
} from '@/hooks/useCodeBoard';
import { ExecuteButton } from '@/components/codeboard/ExecuteButton';
import { ExecutionModal } from '@/components/codeboard/ExecutionModal';
import { CommentsSection } from '@/components/codeboard/comments-section';
import { ImplementationTab } from '@/components/codeboard/ImplementationTab';
import {
  Issue,
  ISSUE_TYPES,
  PRIORITIES,
  STATUS_COLUMNS,
  IssueStatus,
  Priority,
  IssueType,
} from '@/types/codeboard';
import { cn } from '@/lib/utils';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function IssueDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();

  // State
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [activeExecution, setActiveExecution] = useState<ExecutionSession | null>(null);
  const [activeTab, setActiveTab] = useState<
    'details' | 'implementation' | 'activity' | 'comments'
  >('details');

  // Queries
  const { data: issue, isLoading, error } = useIssue(id);
  const { data: projects } = useProjects();
  const { data: issueCommits } = useIssueCommits(
    issue?.projectId || null,
    issue?.key || null
  );
  const { data: linkedCommits } = useLinkedCommits(issue?.id || null);
  const { data: executionSummaries } = useExecutionSummaries(
    issue?.id,
    issue?.projectId,
  );
  const hasImplementation = (executionSummaries?.length ?? 0) > 0;

  // If summaries vanish (e.g. cache invalidation) while user is on the tab,
  // fall back to Details so an orphaned tab panel never lingers.
  useEffect(() => {
    if (!hasImplementation && activeTab === 'implementation') {
      setActiveTab('details');
    }
  }, [hasImplementation, activeTab]);

  // Honor #implementation hash from slide-over "View Full" link (CB-1612).
  // Listens to hashchange so navigating between slide-over links re-applies the tab.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const apply = () => {
      if (window.location.hash === '#implementation' && hasImplementation) {
        setActiveTab('implementation');
      }
    };
    apply();
    window.addEventListener('hashchange', apply);
    return () => window.removeEventListener('hashchange', apply);
  }, [hasImplementation]);

  // Mutations
  const updateIssue = useUpdateIssue();
  const deleteIssue = useDeleteIssue();

  // Find project
  const project = useMemo(() => {
    if (!issue?.projectId || !projects) return null;
    return projects.find((p) => p.id === issue.projectId);
  }, [issue?.projectId, projects]);

  // Find parent issue from children array (parent would have this issue as a child)
  const parent = useMemo(() => {
    if (!issue?.parentId) return null;
    // The parent info might be in the issue object if API returns it
    return null; // Will be fetched separately if needed
  }, [issue?.parentId]);

  // Child issues from API response
  const children = useMemo(() => {
    if (!issue?.children) return [];
    return [...issue.children].sort((a, b) => {
      const typeOrder: Record<string, number> = { STORY: 0, TASK: 1, BUG: 1, SUBTASK: 2 };
      const orderA = typeOrder[a.type] ?? 99;
      const orderB = typeOrder[b.type] ?? 99;
      if (orderA !== orderB) return orderA - orderB;
      return a.sequence - b.sequence;
    });
  }, [issue?.children]);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-500" />
      </div>
    );
  }

  if (error || !issue) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4">
        <AlertTriangle className="w-12 h-12 text-red-500" />
        <h1 className="text-xl font-semibold">Issue not found</h1>
        <p className="text-zinc-500">The issue you're looking for doesn't exist or has been deleted.</p>
        <Link
          href="/codeboard"
          className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to CodeBoard
        </Link>
      </div>
    );
  }

  const issueType = ISSUE_TYPES.find((t) => t.type === issue.type);
  const priority = PRIORITIES.find((p) => p.priority === issue.priority);
  const status = STATUS_COLUMNS.find((s) => s.status === issue.status);

  const handleStartEdit = () => {
    setEditTitle(issue.title);
    setEditDescription(issue.description || '');
    setIsEditing(true);
  };

  const handleSaveEdit = () => {
    updateIssue.mutate(
      { issueId: issue.id, data: { title: editTitle, description: editDescription } },
      { onSuccess: () => setIsEditing(false) }
    );
  };

  const handleStatusChange = (newStatus: IssueStatus) => {
    updateIssue.mutate({ issueId: issue.id, data: { status: newStatus } });
  };

  const handlePriorityChange = (newPriority: Priority) => {
    updateIssue.mutate({ issueId: issue.id, data: { priority: newPriority } });
  };

  const handleTypeChange = (newType: IssueType) => {
    updateIssue.mutate({ issueId: issue.id, data: { type: newType } });
  };

  const handleDelete = () => {
    if (confirm(`Delete issue ${issue.key}? This action cannot be undone.`)) {
      deleteIssue.mutate(issue.id, {
        onSuccess: () => router.push('/codeboard'),
      });
    }
  };

  const handleExecutionStart = (sessionId: string) => {
    setActiveExecution({
      session_id: sessionId,
      issue_id: issue.id,
      issue_key: issue.key,
      provider: 'claude_code',
      status: 'running',
      output_lines: 0,
    });
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-zinc-800 px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Left: Back button and breadcrumb */}
          <div className="flex items-center gap-4">
            <Link
              href="/codeboard"
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title="Back to CodeBoard"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div className="flex items-center gap-2 text-sm">
              {project && (
                <>
                  <span className="text-zinc-500">{project.name}</span>
                  <ChevronRight className="w-4 h-4 text-zinc-600" />
                </>
              )}
              <span className="text-xl">{issueType?.icon}</span>
              <span className="font-mono text-cyan-500">{issue.key}</span>
            </div>
          </div>

          {/* Right: Actions */}
          <div className="flex items-center gap-2">
            <ExecuteButton issue={issue} onExecutionStart={handleExecutionStart} size="md" />
            <div className="w-px h-6 bg-zinc-700 mx-1" />
            <button
              onClick={handleStartEdit}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title="Edit"
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={handleDelete}
              className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 rounded-lg transition-colors"
              title="Delete"
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <Link
              href="/codeboard"
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title="Close and return to board"
            >
              <ExternalLink className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-8">
          <div className="grid grid-cols-3 gap-8">
            {/* Left: Main content (2/3) */}
            <div className="col-span-2 space-y-6">
              {/* Title and Description */}
              {isEditing ? (
                <div className="space-y-4">
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full px-4 py-3 text-2xl font-semibold bg-zinc-800 border border-zinc-700 rounded-lg
                               focus:outline-none focus:border-cyan-500"
                    autoFocus
                  />
                  <textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    placeholder="Add description..."
                    rows={6}
                    className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg
                               focus:outline-none focus:border-cyan-500 resize-none"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={handleSaveEdit}
                      disabled={updateIssue.isPending}
                      className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded-lg transition-colors"
                    >
                      {updateIssue.isPending ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={() => setIsEditing(false)}
                      className="px-4 py-2 text-zinc-400 hover:text-zinc-200 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <h1 className="text-2xl font-semibold">{issue.title}</h1>
                  {issue.description ? (
                    <div className="prose prose-invert prose-zinc max-w-none">
                      <p className="text-zinc-400 whitespace-pre-wrap">{issue.description}</p>
                    </div>
                  ) : (
                    <p className="text-zinc-600 italic">No description provided</p>
                  )}
                </>
              )}

              {/* Tabs */}
              <div className="border-b border-zinc-800">
                <nav className="flex gap-6">
                  <button
                    onClick={() => setActiveTab('details')}
                    className={cn(
                      'pb-3 text-sm font-medium border-b-2 transition-colors',
                      activeTab === 'details'
                        ? 'border-cyan-500 text-cyan-500'
                        : 'border-transparent text-zinc-500 hover:text-zinc-300'
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <Target className="w-4 h-4" />
                      Details
                    </span>
                  </button>
                  {hasImplementation && (
                    <button
                      onClick={() => setActiveTab('implementation')}
                      className={cn(
                        'pb-3 text-sm font-medium border-b-2 transition-colors',
                        activeTab === 'implementation'
                          ? 'border-cyan-500 text-cyan-500'
                          : 'border-transparent text-zinc-500 hover:text-zinc-300'
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4" />
                        Implementation
                      </span>
                    </button>
                  )}
                  <button
                    onClick={() => setActiveTab('activity')}
                    className={cn(
                      'pb-3 text-sm font-medium border-b-2 transition-colors',
                      activeTab === 'activity'
                        ? 'border-cyan-500 text-cyan-500'
                        : 'border-transparent text-zinc-500 hover:text-zinc-300'
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <Activity className="w-4 h-4" />
                      Activity
                    </span>
                  </button>
                  <button
                    onClick={() => setActiveTab('comments')}
                    className={cn(
                      'pb-3 text-sm font-medium border-b-2 transition-colors',
                      activeTab === 'comments'
                        ? 'border-cyan-500 text-cyan-500'
                        : 'border-transparent text-zinc-500 hover:text-zinc-300'
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4" />
                      Comments
                    </span>
                  </button>
                </nav>
              </div>

              {/* Tab Content */}
              {activeTab === 'details' && (
                <div className="space-y-6">
                  {/* Child Issues */}
                  {(issue.type === 'EPIC' || issue.type === 'STORY') && (
                    <div className="space-y-3">
                      <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Target className="w-4 h-4" />
                        {issue.type === 'EPIC' ? 'Stories & Tasks' : 'Tasks'} ({children.length})
                      </h3>
                      {children.length === 0 ? (
                        <p className="text-sm text-zinc-600 italic">
                          No {issue.type === 'EPIC' ? 'stories or tasks' : 'tasks'} yet
                        </p>
                      ) : (
                        <div className="space-y-2">
                          {children.map((child) => {
                            const childType = ISSUE_TYPES.find((t) => t.type === child.type);
                            const childStatus = STATUS_COLUMNS.find((s) => s.status === child.status);
                            return (
                              <Link
                                key={child.id}
                                href={`/codeboard/issues/${child.id}`}
                                className={cn(
                                  'flex items-center gap-3 p-3 rounded-lg transition-colors',
                                  'bg-zinc-800/50 hover:bg-zinc-800 border-l-4',
                                  child.type === 'STORY' && 'border-l-green-500',
                                  child.type === 'TASK' && 'border-l-blue-500',
                                  child.type === 'BUG' && 'border-l-red-500',
                                  child.type === 'SUBTASK' && 'border-l-cyan-500'
                                )}
                              >
                                <span className="text-base">{childType?.icon}</span>
                                <span className="text-xs font-mono text-zinc-500">{child.key}</span>
                                <span className="text-sm flex-1 truncate">{child.title}</span>
                                <span
                                  className={cn(
                                    'text-xs px-2 py-0.5 rounded',
                                    child.status === 'DONE' && 'bg-green-900/30 text-green-400',
                                    child.status === 'IN_PROGRESS' && 'bg-blue-900/30 text-blue-400',
                                    child.status === 'BACKLOG' && 'bg-zinc-700 text-zinc-400',
                                    child.status === 'TODO' && 'bg-yellow-900/30 text-yellow-400',
                                    child.status === 'IN_REVIEW' && 'bg-purple-900/30 text-purple-400'
                                  )}
                                >
                                  {childStatus?.label}
                                </span>
                              </Link>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Linked Commits */}
                  {linkedCommits && linkedCommits.length > 0 && (
                    <div className="space-y-3">
                      <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Link2 className="w-4 h-4" />
                        Linked Commits ({linkedCommits.length})
                      </h3>
                      <div className="space-y-2">
                        {linkedCommits.slice(0, 10).map((link) => (
                          <div
                            key={link.id}
                            className={cn(
                              'p-3 rounded-lg text-sm border-l-2',
                              link.linkType === 'FIXES' && 'bg-green-900/20 border-l-green-500',
                              link.linkType === 'CLOSES' && 'bg-green-900/20 border-l-green-500',
                              link.linkType === 'IMPLEMENTS' && 'bg-blue-900/20 border-l-blue-500',
                              link.linkType === 'MENTIONS' && 'bg-zinc-800 border-l-zinc-600'
                            )}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2 flex-1 min-w-0">
                                <code className="text-xs text-cyan-500 shrink-0">{link.shortHash}</code>
                                <span className="text-zinc-300 truncate">{link.message}</span>
                              </div>
                              <span
                                className={cn(
                                  'text-xs px-1.5 py-0.5 rounded shrink-0',
                                  link.linkType === 'FIXES' && 'bg-green-900/40 text-green-400',
                                  link.linkType === 'CLOSES' && 'bg-green-900/40 text-green-400',
                                  link.linkType === 'IMPLEMENTS' && 'bg-blue-900/40 text-blue-400',
                                  link.linkType === 'MENTIONS' && 'bg-zinc-700 text-zinc-400'
                                )}
                              >
                                {link.linkType.toLowerCase()}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 text-xs text-zinc-500 mt-1.5">
                              <span>{link.author}</span>
                              <span>{new Date(link.committedAt).toLocaleDateString()}</span>
                              {link.triggeredStatusChange && (
                                <span className="flex items-center gap-1 text-green-400">
                                  <CheckCircle className="w-3 h-3" />
                                  status updated
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Git Commits (fallback) */}
                  {(!linkedCommits || linkedCommits.length === 0) &&
                    issueCommits &&
                    issueCommits.commits.length > 0 && (
                      <div className="space-y-3">
                        <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                          <GitCommit className="w-4 h-4" />
                          Related Commits ({issueCommits.total})
                        </h3>
                        <div className="space-y-2">
                          {issueCommits.commits.slice(0, 5).map((commit) => (
                            <div key={commit.hash} className="p-3 bg-zinc-800 rounded-lg text-sm">
                              <div className="flex items-center gap-2">
                                <code className="text-xs text-cyan-500">{commit.short_hash}</code>
                                <span className="text-zinc-300 truncate">{commit.message}</span>
                              </div>
                              <div className="text-xs text-zinc-500 mt-1">
                                {commit.author} - {new Date(commit.date).toLocaleDateString()}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                </div>
              )}

              {activeTab === 'implementation' && (
                <div className="space-y-4">
                  <ImplementationTab issueId={issue.id} projectId={issue.projectId} />
                </div>
              )}

              {activeTab === 'activity' && (
                <div className="space-y-4">
                  <ActivityTimeline issue={issue} />
                </div>
              )}

              {activeTab === 'comments' && (
                <div className="space-y-4">
                  <CommentsSection issueId={issue.id} />
                </div>
              )}
            </div>

            {/* Right: Sidebar (1/3) */}
            <div className="space-y-6">
              {/* Status Card */}
              <div className="bg-zinc-800/50 rounded-lg p-4 space-y-4">
                {/* Status */}
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-2">Status</label>
                  <select
                    value={issue.status}
                    onChange={(e) => handleStatusChange(e.target.value as IssueStatus)}
                    className={cn(
                      'w-full px-3 py-2 rounded-lg text-sm font-medium',
                      'bg-zinc-800 border border-zinc-700 focus:outline-none focus:border-cyan-500',
                      issue.status === 'DONE' && 'border-green-600',
                      issue.status === 'IN_PROGRESS' && 'border-blue-600',
                      issue.status === 'IN_REVIEW' && 'border-purple-600'
                    )}
                  >
                    {STATUS_COLUMNS.map((s) => (
                      <option key={s.status} value={s.status}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Priority */}
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-2">Priority</label>
                  <select
                    value={issue.priority}
                    onChange={(e) => handlePriorityChange(e.target.value as Priority)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                               focus:outline-none focus:border-cyan-500"
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p.priority} value={p.priority}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Type */}
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-2">Type</label>
                  <select
                    value={issue.type}
                    onChange={(e) => handleTypeChange(e.target.value as IssueType)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                               focus:outline-none focus:border-cyan-500"
                  >
                    {ISSUE_TYPES.map((t) => (
                      <option key={t.type} value={t.type}>
                        {t.icon} {t.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Story Points */}
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-2">Story Points</label>
                  <div className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm">
                    {issue.storyPoints ?? '-'}
                  </div>
                </div>
              </div>

              {/* People Card */}
              <div className="bg-zinc-800/50 rounded-lg p-4 space-y-4">
                <h3 className="text-sm font-medium text-zinc-400">People</h3>
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <User className="w-4 h-4 text-zinc-500" />
                    <div>
                      <span className="text-xs text-zinc-500 block">Assignee</span>
                      <span className="text-sm">{issue.assignee || 'Unassigned'}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <User className="w-4 h-4 text-zinc-500" />
                    <div>
                      <span className="text-xs text-zinc-500 block">Reporter</span>
                      <span className="text-sm">{issue.reporter || 'Unknown'}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Dates Card */}
              <div className="bg-zinc-800/50 rounded-lg p-4 space-y-4">
                <h3 className="text-sm font-medium text-zinc-400">Dates</h3>
                <div className="space-y-3 text-sm">
                  <div className="flex items-center gap-3">
                    <Calendar className="w-4 h-4 text-zinc-500" />
                    <div>
                      <span className="text-xs text-zinc-500 block">Created</span>
                      <span>{new Date(issue.createdAt).toLocaleDateString()}</span>
                    </div>
                  </div>
                  {issue.startedAt && (
                    <div className="flex items-center gap-3">
                      <Clock className="w-4 h-4 text-blue-500" />
                      <div>
                        <span className="text-xs text-zinc-500 block">Started</span>
                        <span>{new Date(issue.startedAt).toLocaleDateString()}</span>
                      </div>
                    </div>
                  )}
                  {issue.completedAt && (
                    <div className="flex items-center gap-3">
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      <div>
                        <span className="text-xs text-zinc-500 block">Completed</span>
                        <span>{new Date(issue.completedAt).toLocaleDateString()}</span>
                      </div>
                    </div>
                  )}
                  {issue.dueDate && (
                    <div className="flex items-center gap-3">
                      <Calendar
                        className={cn(
                          'w-4 h-4',
                          new Date(issue.dueDate) < new Date() ? 'text-red-500' : 'text-orange-500'
                        )}
                      />
                      <div>
                        <span className="text-xs text-zinc-500 block">Due Date</span>
                        <span
                          className={cn(
                            new Date(issue.dueDate) < new Date() && 'text-red-500'
                          )}
                        >
                          {new Date(issue.dueDate).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Labels Card */}
              {issue.labels && issue.labels.length > 0 && (
                <div className="bg-zinc-800/50 rounded-lg p-4 space-y-3">
                  <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                    <Tag className="w-4 h-4" />
                    Labels
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {issue.labels.split(',').map((label) => (
                      <span
                        key={label.trim()}
                        className="px-2 py-1 bg-zinc-700 text-zinc-300 rounded text-xs"
                      >
                        {label.trim()}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Parent Issue Link */}
              {issue.parentId && (
                <div className="bg-zinc-800/50 rounded-lg p-4 space-y-3">
                  <h3 className="text-sm font-medium text-zinc-400">Parent Issue</h3>
                  <Link
                    href={`/codeboard/issues/${issue.parentId}`}
                    className="flex items-center gap-2 text-sm text-cyan-500 hover:text-cyan-400 transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                    View Parent Issue
                  </Link>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Execution Modal */}
      {activeExecution && issue && (
        <ExecutionModal
          session={activeExecution}
          issue={issue}
          onClose={() => setActiveExecution(null)}
        />
      )}
    </div>
  );
}

/**
 * Activity Timeline Component
 */
function ActivityTimeline({ issue }: { issue: Issue }) {
  // In a real implementation, this would fetch activity/history from an API
  // For now, we'll show basic activity based on available data
  const activities = useMemo(() => {
    const items: Array<{
      id: string;
      type: 'created' | 'status' | 'started' | 'completed';
      date: string;
      description: string;
    }> = [];

    items.push({
      id: 'created',
      type: 'created',
      date: issue.createdAt,
      description: `Issue ${issue.key} was created`,
    });

    if (issue.startedAt) {
      items.push({
        id: 'started',
        type: 'started',
        date: issue.startedAt,
        description: 'Work started on this issue',
      });
    }

    if (issue.completedAt) {
      items.push({
        id: 'completed',
        type: 'completed',
        date: issue.completedAt,
        description: 'Issue was marked as completed',
      });
    }

    return items.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [issue]);

  return (
    <div className="space-y-4">
      {activities.length === 0 ? (
        <p className="text-sm text-zinc-600 italic">No activity recorded</p>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-4 top-0 bottom-0 w-px bg-zinc-700" />

          {activities.map((activity, index) => (
            <div key={activity.id} className="relative pl-10 pb-4">
              {/* Timeline dot */}
              <div
                className={cn(
                  'absolute left-2.5 w-3 h-3 rounded-full border-2 border-zinc-900',
                  activity.type === 'created' && 'bg-cyan-500',
                  activity.type === 'started' && 'bg-blue-500',
                  activity.type === 'completed' && 'bg-green-500',
                  activity.type === 'status' && 'bg-yellow-500'
                )}
              />

              <div className="bg-zinc-800/50 rounded-lg p-3">
                <p className="text-sm">{activity.description}</p>
                <p className="text-xs text-zinc-500 mt-1">
                  {new Date(activity.date).toLocaleString()}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

