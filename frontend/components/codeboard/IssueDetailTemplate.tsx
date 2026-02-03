'use client';

/**
 * IssueDetailTemplate - Reusable page template for displaying issue details
 *
 * This template provides a consistent layout and structure for issue detail views.
 * It can be used in both full-page and embedded contexts with customizable sections.
 *
 * Part of STORY CB-21: Issue Detail View
 * Task CB-457: Create a new page template for issue detail view
 */

import { ReactNode, useState, useMemo } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Edit2,
  Trash2,
  Clock,
  User,
  Calendar,
  GitCommit,
  ChevronRight,
  Link2,
  CheckCircle,
  ExternalLink,
  MessageSquare,
  Activity,
  Tag,
  Target,
  AlertTriangle,
} from 'lucide-react';
import {
  Issue,
  ISSUE_TYPES,
  PRIORITIES,
  STATUS_COLUMNS,
  IssueStatus,
  Priority,
  IssueType,
} from '@/types/codeboard';
import { CommitLink, GitCommit as GitCommitType } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';

// ============================================
// Type Definitions
// ============================================

export interface IssueDetailTemplateProps {
  /** The issue to display */
  issue: Issue;
  /** Optional project information */
  project?: { id: string; name: string } | null;
  /** Child issues to display */
  children?: Issue[];
  /** Linked commits from the commit linking system */
  linkedCommits?: CommitLink[];
  /** Related commits from git log search */
  relatedCommits?: { commits: GitCommitType[]; total: number } | null;
  /** Parent issue information */
  parent?: Issue | null;
  /** Whether the template is in editing mode */
  isEditing?: boolean;
  /** Callback when edit mode is toggled */
  onEditToggle?: (isEditing: boolean) => void;
  /** Callback when issue data is updated */
  onUpdate?: (data: Partial<Issue>) => void;
  /** Callback when issue is deleted */
  onDelete?: () => void;
  /** Custom header actions to render */
  headerActions?: ReactNode;
  /** Custom content to render before the main content */
  beforeContent?: ReactNode;
  /** Custom content to render after the main content */
  afterContent?: ReactNode;
  /** URL to navigate back to */
  backUrl?: string;
  /** Label for back button */
  backLabel?: string;
  /** Whether to show the sidebar */
  showSidebar?: boolean;
  /** Whether to show tabs */
  showTabs?: boolean;
  /** Custom tabs configuration */
  tabs?: TabConfig[];
  /** Active tab key */
  activeTab?: string;
  /** Callback when tab changes */
  onTabChange?: (tab: string) => void;
  /** Whether to show loading state */
  isLoading?: boolean;
  /** Whether to show error state */
  error?: Error | null;
  /** Custom class names */
  className?: string;
  /** Whether this is a full-page view (adds max-width container) */
  fullPage?: boolean;
}

export interface TabConfig {
  key: string;
  label: string;
  icon?: ReactNode;
  content: ReactNode;
}

// ============================================
// Sub-Components
// ============================================

/**
 * Loading state component
 */
export function IssueDetailLoading() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-500" />
    </div>
  );
}

/**
 * Error state component
 */
export function IssueDetailError({
  message = 'Issue not found',
  description = "The issue you're looking for doesn't exist or has been deleted.",
  backUrl = '/codeboard',
  backLabel = 'Back to CodeBoard',
}: {
  message?: string;
  description?: string;
  backUrl?: string;
  backLabel?: string;
}) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-4">
      <AlertTriangle className="w-12 h-12 text-red-500" />
      <h1 className="text-xl font-semibold">{message}</h1>
      <p className="text-zinc-500">{description}</p>
      <Link
        href={backUrl}
        className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        {backLabel}
      </Link>
    </div>
  );
}

/**
 * Header component with breadcrumb and actions
 */
export function IssueDetailHeader({
  issue,
  project,
  backUrl = '/codeboard',
  backLabel = 'Back to CodeBoard',
  actions,
  onEdit,
  onDelete,
  showDefaultActions = true,
}: {
  issue: Issue;
  project?: { id: string; name: string } | null;
  backUrl?: string;
  backLabel?: string;
  actions?: ReactNode;
  onEdit?: () => void;
  onDelete?: () => void;
  showDefaultActions?: boolean;
}) {
  const issueType = ISSUE_TYPES.find((t) => t.type === issue.type);

  return (
    <div className="flex-shrink-0 border-b border-zinc-800 px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Left: Back button and breadcrumb */}
        <div className="flex items-center gap-4">
          <Link
            href={backUrl}
            className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
            title={backLabel}
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
          {actions}
          {showDefaultActions && (
            <>
              {actions && <div className="w-px h-6 bg-zinc-700 mx-1" />}
              {onEdit && (
                <button
                  onClick={onEdit}
                  className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
                  title="Edit"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
              )}
              {onDelete && (
                <button
                  onClick={onDelete}
                  className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 rounded-lg transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
              <Link
                href={backUrl}
                className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
                title="Close and return"
              >
                <ExternalLink className="w-4 h-4" />
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Title and description section with edit support
 */
export function IssueDetailTitleSection({
  issue,
  isEditing,
  editTitle,
  editDescription,
  onTitleChange,
  onDescriptionChange,
  onSave,
  onCancel,
  isSaving,
}: {
  issue: Issue;
  isEditing?: boolean;
  editTitle?: string;
  editDescription?: string;
  onTitleChange?: (value: string) => void;
  onDescriptionChange?: (value: string) => void;
  onSave?: () => void;
  onCancel?: () => void;
  isSaving?: boolean;
}) {
  if (isEditing) {
    return (
      <div className="space-y-4">
        <input
          type="text"
          value={editTitle ?? issue.title}
          onChange={(e) => onTitleChange?.(e.target.value)}
          className="w-full px-4 py-3 text-2xl font-semibold bg-zinc-800 border border-zinc-700 rounded-lg
                     focus:outline-none focus:border-cyan-500"
          autoFocus
        />
        <textarea
          value={editDescription ?? issue.description ?? ''}
          onChange={(e) => onDescriptionChange?.(e.target.value)}
          placeholder="Add description..."
          rows={6}
          className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg
                     focus:outline-none focus:border-cyan-500 resize-none"
        />
        <div className="flex gap-2">
          <button
            onClick={onSave}
            disabled={isSaving}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded-lg transition-colors"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-2 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
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
  );
}

/**
 * Tab navigation component
 */
export function IssueDetailTabs({
  tabs,
  activeTab,
  onTabChange,
}: {
  tabs: TabConfig[];
  activeTab: string;
  onTabChange: (tab: string) => void;
}) {
  return (
    <div className="border-b border-zinc-800">
      <nav className="flex gap-6">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={cn(
              'pb-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === tab.key
                ? 'border-cyan-500 text-cyan-500'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            )}
          >
            <span className="flex items-center gap-2">
              {tab.icon}
              {tab.label}
            </span>
          </button>
        ))}
      </nav>
    </div>
  );
}

/**
 * Child issues list component
 */
export function IssueDetailChildList({
  issue,
  children,
  onChildClick,
}: {
  issue: Issue;
  children: Issue[];
  onChildClick?: (child: Issue) => void;
}) {
  if (issue.type !== 'EPIC' && issue.type !== 'STORY') {
    return null;
  }

  return (
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
                onClick={(e) => {
                  if (onChildClick) {
                    e.preventDefault();
                    onChildClick(child);
                  }
                }}
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
  );
}

/**
 * Linked commits display component
 */
export function IssueDetailLinkedCommits({
  linkedCommits,
  maxDisplay = 10,
}: {
  linkedCommits: CommitLink[];
  maxDisplay?: number;
}) {
  if (!linkedCommits || linkedCommits.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
        <Link2 className="w-4 h-4" />
        Linked Commits ({linkedCommits.length})
      </h3>
      <div className="space-y-2">
        {linkedCommits.slice(0, maxDisplay).map((link) => (
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
  );
}

/**
 * Related commits display component (fallback when no linked commits)
 */
export function IssueDetailRelatedCommits({
  commits,
  total,
  maxDisplay = 5,
}: {
  commits: GitCommitType[];
  total: number;
  maxDisplay?: number;
}) {
  if (!commits || commits.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
        <GitCommit className="w-4 h-4" />
        Related Commits ({total})
      </h3>
      <div className="space-y-2">
        {commits.slice(0, maxDisplay).map((commit) => (
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
  );
}

/**
 * Sidebar status card component
 */
export function IssueDetailStatusCard({
  issue,
  onStatusChange,
  onPriorityChange,
  onTypeChange,
}: {
  issue: Issue;
  onStatusChange?: (status: IssueStatus) => void;
  onPriorityChange?: (priority: Priority) => void;
  onTypeChange?: (type: IssueType) => void;
}) {
  return (
    <div className="bg-zinc-800/50 rounded-lg p-4 space-y-4">
      {/* Status */}
      <div>
        <label className="block text-xs font-medium text-zinc-500 mb-2">Status</label>
        <select
          value={issue.status}
          onChange={(e) => onStatusChange?.(e.target.value as IssueStatus)}
          disabled={!onStatusChange}
          className={cn(
            'w-full px-3 py-2 rounded-lg text-sm font-medium',
            'bg-zinc-800 border border-zinc-700 focus:outline-none focus:border-cyan-500',
            'disabled:opacity-60 disabled:cursor-not-allowed',
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
          onChange={(e) => onPriorityChange?.(e.target.value as Priority)}
          disabled={!onPriorityChange}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                     focus:outline-none focus:border-cyan-500 disabled:opacity-60 disabled:cursor-not-allowed"
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
          onChange={(e) => onTypeChange?.(e.target.value as IssueType)}
          disabled={!onTypeChange}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                     focus:outline-none focus:border-cyan-500 disabled:opacity-60 disabled:cursor-not-allowed"
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
  );
}

/**
 * Sidebar people card component
 */
export function IssueDetailPeopleCard({ issue }: { issue: Issue }) {
  return (
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
  );
}

/**
 * Sidebar dates card component
 */
export function IssueDetailDatesCard({ issue }: { issue: Issue }) {
  return (
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
                className={cn(new Date(issue.dueDate) < new Date() && 'text-red-500')}
              >
                {new Date(issue.dueDate).toLocaleDateString()}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Sidebar labels card component
 */
export function IssueDetailLabelsCard({ issue }: { issue: Issue }) {
  if (!issue.labels || issue.labels.length === 0) {
    return null;
  }

  const labelList = typeof issue.labels === 'string'
    ? issue.labels.split(',').map(l => l.trim()).filter(Boolean)
    : issue.labels;

  if (labelList.length === 0) {
    return null;
  }

  return (
    <div className="bg-zinc-800/50 rounded-lg p-4 space-y-3">
      <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
        <Tag className="w-4 h-4" />
        Labels
      </h3>
      <div className="flex flex-wrap gap-2">
        {labelList.map((label) => (
          <span
            key={label}
            className="px-2 py-1 bg-zinc-700 text-zinc-300 rounded text-xs"
          >
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Sidebar parent issue link component
 */
export function IssueDetailParentLink({
  parentId,
  parent,
}: {
  parentId: string;
  parent?: Issue | null;
}) {
  return (
    <div className="bg-zinc-800/50 rounded-lg p-4 space-y-3">
      <h3 className="text-sm font-medium text-zinc-400">Parent Issue</h3>
      <Link
        href={`/codeboard/issues/${parentId}`}
        className="flex items-center gap-2 text-sm text-cyan-500 hover:text-cyan-400 transition-colors"
      >
        {parent && (
          <>
            <span className="text-base">
              {ISSUE_TYPES.find((t) => t.type === parent.type)?.icon}
            </span>
            <span className="font-mono text-zinc-400">{parent.key}</span>
          </>
        )}
        <ChevronRight className="w-4 h-4" />
        {parent ? parent.title : 'View Parent Issue'}
      </Link>
    </div>
  );
}

/**
 * Activity timeline component
 */
export function IssueDetailActivityTimeline({ issue }: { issue: Issue }) {
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

          {activities.map((activity) => (
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

/**
 * Comments section component (placeholder)
 */
export function IssueDetailCommentsSection({ issue }: { issue: Issue }) {
  const [newComment, setNewComment] = useState('');

  return (
    <div className="space-y-4">
      {/* Comment input */}
      <div className="space-y-3">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          rows={3}
          className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg
                     focus:outline-none focus:border-cyan-500 resize-none text-sm"
        />
        <div className="flex justify-end">
          <button
            disabled={!newComment.trim()}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed
                       rounded-lg text-sm transition-colors"
          >
            Add Comment
          </button>
        </div>
      </div>

      {/* Comments list (placeholder) */}
      <div className="text-center py-8">
        <MessageSquare className="w-12 h-12 text-zinc-600 mx-auto mb-3" />
        <p className="text-zinc-500 text-sm">No comments yet</p>
        <p className="text-zinc-600 text-xs mt-1">Be the first to add a comment</p>
      </div>
    </div>
  );
}

// ============================================
// Default Tab Configuration
// ============================================

export function getDefaultTabs(
  issue: Issue,
  children: Issue[] = [],
  linkedCommits: CommitLink[] = [],
  relatedCommits?: { commits: GitCommitType[]; total: number } | null,
  onChildClick?: (child: Issue) => void
): TabConfig[] {
  return [
    {
      key: 'details',
      label: 'Details',
      icon: <Target className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <IssueDetailChildList
            issue={issue}
            children={children}
            onChildClick={onChildClick}
          />
          <IssueDetailLinkedCommits linkedCommits={linkedCommits} />
          {(!linkedCommits || linkedCommits.length === 0) && relatedCommits && (
            <IssueDetailRelatedCommits
              commits={relatedCommits.commits}
              total={relatedCommits.total}
            />
          )}
        </div>
      ),
    },
    {
      key: 'activity',
      label: 'Activity',
      icon: <Activity className="w-4 h-4" />,
      content: <IssueDetailActivityTimeline issue={issue} />,
    },
    {
      key: 'comments',
      label: 'Comments',
      icon: <MessageSquare className="w-4 h-4" />,
      content: <IssueDetailCommentsSection issue={issue} />,
    },
  ];
}

// ============================================
// Main Template Component
// ============================================

/**
 * IssueDetailTemplate - Main reusable template for issue detail views
 *
 * This component provides a consistent layout with:
 * - Header with breadcrumb and actions
 * - Main content area with tabs (2/3 width on desktop)
 * - Sidebar with status, people, dates cards (1/3 width on desktop)
 *
 * @example
 * ```tsx
 * <IssueDetailTemplate
 *   issue={issue}
 *   project={project}
 *   children={childIssues}
 *   linkedCommits={linkedCommits}
 *   onUpdate={handleUpdate}
 *   onDelete={handleDelete}
 *   headerActions={<ExecuteButton issue={issue} />}
 * />
 * ```
 */
export function IssueDetailTemplate({
  issue,
  project,
  children: childIssues = [],
  linkedCommits = [],
  relatedCommits,
  parent,
  isEditing: externalIsEditing,
  onEditToggle,
  onUpdate,
  onDelete,
  headerActions,
  beforeContent,
  afterContent,
  backUrl = '/codeboard',
  backLabel = 'Back to CodeBoard',
  showSidebar = true,
  showTabs = true,
  tabs: customTabs,
  activeTab: externalActiveTab,
  onTabChange,
  isLoading,
  error,
  className,
  fullPage = true,
}: IssueDetailTemplateProps) {
  // Internal state for edit mode
  const [internalIsEditing, setInternalIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [internalActiveTab, setInternalActiveTab] = useState('details');

  // Use external or internal state
  const isEditing = externalIsEditing ?? internalIsEditing;
  const activeTab = externalActiveTab ?? internalActiveTab;

  // Default tabs
  const tabs = customTabs ?? getDefaultTabs(issue, childIssues, linkedCommits, relatedCommits);

  // Loading state
  if (isLoading) {
    return <IssueDetailLoading />;
  }

  // Error state
  if (error) {
    return (
      <IssueDetailError
        backUrl={backUrl}
        backLabel={backLabel}
      />
    );
  }

  const handleStartEdit = () => {
    setEditTitle(issue.title);
    setEditDescription(issue.description || '');
    if (onEditToggle) {
      onEditToggle(true);
    } else {
      setInternalIsEditing(true);
    }
  };

  const handleSaveEdit = () => {
    onUpdate?.({ title: editTitle, description: editDescription });
    if (onEditToggle) {
      onEditToggle(false);
    } else {
      setInternalIsEditing(false);
    }
  };

  const handleCancelEdit = () => {
    if (onEditToggle) {
      onEditToggle(false);
    } else {
      setInternalIsEditing(false);
    }
  };

  const handleTabChange = (tab: string) => {
    if (onTabChange) {
      onTabChange(tab);
    } else {
      setInternalActiveTab(tab);
    }
  };

  const handleStatusChange = (status: IssueStatus) => {
    onUpdate?.({ status });
  };

  const handlePriorityChange = (priority: Priority) => {
    onUpdate?.({ priority });
  };

  const handleTypeChange = (type: IssueType) => {
    onUpdate?.({ type });
  };

  const handleDelete = () => {
    if (confirm(`Delete issue ${issue.key}? This action cannot be undone.`)) {
      onDelete?.();
    }
  };

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* Header */}
      <IssueDetailHeader
        issue={issue}
        project={project}
        backUrl={backUrl}
        backLabel={backLabel}
        actions={headerActions}
        onEdit={onUpdate ? handleStartEdit : undefined}
        onDelete={onDelete ? handleDelete : undefined}
        showDefaultActions={!!onUpdate || !!onDelete}
      />

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto">
        <div className={cn(fullPage && 'max-w-5xl mx-auto', 'px-6 py-8')}>
          {beforeContent}

          <div className={cn('grid gap-8', showSidebar ? 'grid-cols-1 lg:grid-cols-3' : '')}>
            {/* Left: Main content */}
            <div className={cn('space-y-6', showSidebar && 'lg:col-span-2')}>
              {/* Title and Description */}
              <IssueDetailTitleSection
                issue={issue}
                isEditing={isEditing}
                editTitle={editTitle}
                editDescription={editDescription}
                onTitleChange={setEditTitle}
                onDescriptionChange={setEditDescription}
                onSave={handleSaveEdit}
                onCancel={handleCancelEdit}
              />

              {/* Tabs */}
              {showTabs && tabs.length > 0 && (
                <>
                  <IssueDetailTabs
                    tabs={tabs}
                    activeTab={activeTab}
                    onTabChange={handleTabChange}
                  />
                  {/* Tab Content */}
                  {tabs.find((t) => t.key === activeTab)?.content}
                </>
              )}
            </div>

            {/* Right: Sidebar */}
            {showSidebar && (
              <div className="space-y-6">
                <IssueDetailStatusCard
                  issue={issue}
                  onStatusChange={onUpdate ? handleStatusChange : undefined}
                  onPriorityChange={onUpdate ? handlePriorityChange : undefined}
                  onTypeChange={onUpdate ? handleTypeChange : undefined}
                />
                <IssueDetailPeopleCard issue={issue} />
                <IssueDetailDatesCard issue={issue} />
                <IssueDetailLabelsCard issue={issue} />
                {issue.parentId && (
                  <IssueDetailParentLink parentId={issue.parentId} parent={parent} />
                )}
              </div>
            )}
          </div>

          {afterContent}
        </div>
      </div>
    </div>
  );
}

// Export all sub-components for flexible composition
export default IssueDetailTemplate;
