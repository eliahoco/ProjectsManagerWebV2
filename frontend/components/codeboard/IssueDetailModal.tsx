'use client';

/**
 * Issue Detail Modal Component
 * A centered modal that displays detailed information about an issue
 */

import { useState, useMemo, useCallback } from 'react';
import Link from 'next/link';
import {
  X,
  Edit2,
  Trash2,
  User,
  Calendar,
  Clock,
  GitCommit,
  Link2,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  Sparkles,
  Square,
  CheckSquare,
  PlayCircle,
  Copy,
  FileCode,
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
import {
  useIssue,
  useIssueCommits,
  useLinkedCommits,
  useStartExecution,
  useExecutionSummaries,
} from '@/hooks/useCodeBoard';
import { ExecuteButton } from './ExecuteButton';
import { ShortcutBadge } from './KeyboardShortcutsHelp';
import { cn } from '@/lib/utils';
import { useKeyboardShortcuts, SHORTCUTS, formatShortcut, type ShortcutHandler } from '@/hooks/use-keyboard-shortcuts';
import { useToast } from '@/components/ui/toast';

interface IssueDetailModalProps {
  issue: Issue | null;
  issues?: Issue[];
  isOpen: boolean;
  onClose: () => void;
  onUpdate: (data: Partial<Issue>) => void;
  onDelete: () => void;
  projectId?: string;
  onAIBreakdown?: (issue: Issue) => void;
  onIssueClick?: (issue: Issue) => void;
  onExecutionStart?: (sessionId: string) => void;
  onBatchExecutionStart?: (sessions: { issueId: string; sessionId: string }[]) => void;
}

export function IssueDetailModal({
  issue,
  issues = [],
  isOpen,
  onClose,
  onUpdate,
  onDelete,
  projectId,
  onAIBreakdown,
  onIssueClick,
  onExecutionStart,
  onBatchExecutionStart,
}: IssueDetailModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [selectedChildren, setSelectedChildren] = useState<Set<string>>(new Set());
  const [isExecutingBatch, setIsExecutingBatch] = useState(false);
  const [isImplSummaryOpen, setIsImplSummaryOpen] = useState(true);

  const startExecution = useStartExecution();
  const toast = useToast();

  // Fetch the issue with children directly from API
  const { data: issueWithChildren } = useIssue(issue?.id || null);

  // Fetch execution summaries (CB-1612).
  const { data: executionSummaries } = useExecutionSummaries(issue?.id);
  const latestSummary = executionSummaries?.[0];
  const implFiles = useMemo(() => {
    if (!latestSummary?.filesTouched) return [] as string[];
    try {
      const parsed = JSON.parse(latestSummary.filesTouched);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((p): p is string => typeof p === 'string');
    } catch {
      return [];
    }
  }, [latestSummary?.filesTouched]);

  // Copy issue key to clipboard
  const copyIssueKey = useCallback(() => {
    if (issue?.key) {
      navigator.clipboard.writeText(issue.key);
      toast.success('Copied', `Issue key ${issue.key} copied to clipboard`);
    }
  }, [issue?.key, toast]);

  // Keyboard shortcuts for issue detail modal
  const modalShortcuts = useMemo<ShortcutHandler[]>(() => {
    if (!isOpen || !issue) return [];

    return [
      // Edit issue
      {
        ...SHORTCUTS.EDIT_ISSUE,
        handler: () => {
          if (!isEditing) handleStartEdit();
        },
      },
      // Delete issue
      {
        ...SHORTCUTS.DELETE_ISSUE,
        handler: () => {
          onDelete();
        },
      },
      // Execute issue
      {
        ...SHORTCUTS.EXECUTE_ISSUE,
        handler: () => {
          // Trigger execution via the ExecuteButton
          const executeBtn = document.querySelector('[data-execute-button]') as HTMLButtonElement;
          executeBtn?.click();
        },
      },
      // Copy issue key
      {
        ...SHORTCUTS.COPY_ISSUE_KEY,
        handler: copyIssueKey,
      },
      // Status shortcuts
      {
        ...SHORTCUTS.STATUS_BACKLOG,
        handler: () => handleStatusChange('BACKLOG'),
      },
      {
        ...SHORTCUTS.STATUS_TODO,
        handler: () => handleStatusChange('TODO'),
      },
      {
        ...SHORTCUTS.STATUS_IN_PROGRESS,
        handler: () => handleStatusChange('IN_PROGRESS'),
      },
      {
        ...SHORTCUTS.STATUS_IN_REVIEW,
        handler: () => handleStatusChange('IN_REVIEW'),
      },
      {
        ...SHORTCUTS.STATUS_DONE,
        handler: () => handleStatusChange('DONE'),
      },
    ];
  }, [isOpen, issue, isEditing, copyIssueKey]);

  useKeyboardShortcuts(modalShortcuts, { enabled: isOpen && !isEditing });

  // Fetch commits related to this issue
  const { data: issueCommits } = useIssueCommits(projectId || null, issue?.key || null);

  // Fetch linked commits
  const { data: linkedCommits } = useLinkedCommits(issue?.id || null);

  // Find parent issue
  const parent = useMemo(() => {
    if (!issue?.parentId || !issues.length) return null;
    return issues.find((i) => i.id === issue.parentId);
  }, [issue?.parentId, issues]);

  // Get child issues
  const children = useMemo(() => {
    if (issueWithChildren?.children && issueWithChildren.children.length > 0) {
      const apiChildren = issueWithChildren.children;
      return [...apiChildren].sort((a, b) => {
        const typeOrder: Record<string, number> = { STORY: 0, TASK: 1, BUG: 1, SUBTASK: 2 };
        const orderA = typeOrder[a.type] ?? 99;
        const orderB = typeOrder[b.type] ?? 99;
        if (orderA !== orderB) return orderA - orderB;
        return a.sequence - b.sequence;
      });
    }

    if (!issue?.id || !issues.length) return [];
    const directChildren = issues.filter((i) => i.parentId === issue.id);

    return directChildren.sort((a, b) => {
      const typeOrder: Record<string, number> = { STORY: 0, TASK: 1, BUG: 1, SUBTASK: 2 };
      const orderA = typeOrder[a.type] ?? 99;
      const orderB = typeOrder[b.type] ?? 99;
      if (orderA !== orderB) return orderA - orderB;
      return a.sequence - b.sequence;
    });
  }, [issue?.id, issues, issueWithChildren?.children]);

  if (!isOpen || !issue) return null;

  const issueType = ISSUE_TYPES.find((t) => t.type === issue.type);
  const status = STATUS_COLUMNS.find((s) => s.status === issue.status);

  const handleStartEdit = () => {
    setEditTitle(issue.title);
    setEditDescription(issue.description || '');
    setIsEditing(true);
  };

  const handleSaveEdit = () => {
    onUpdate({
      title: editTitle,
      description: editDescription,
    });
    setIsEditing(false);
  };

  const handleStatusChange = (newStatus: IssueStatus) => {
    onUpdate({ status: newStatus });
  };

  const handlePriorityChange = (newPriority: Priority) => {
    onUpdate({ priority: newPriority });
  };

  const handleTypeChange = (newType: IssueType) => {
    onUpdate({ type: newType });
  };

  const toggleChildSelection = (childId: string) => {
    setSelectedChildren((prev) => {
      const next = new Set(prev);
      if (next.has(childId)) {
        next.delete(childId);
      } else {
        next.add(childId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedChildren.size === children.length) {
      setSelectedChildren(new Set());
    } else {
      setSelectedChildren(new Set(children.map((c) => c.id)));
    }
  };

  const handleExecuteSelected = async () => {
    if (selectedChildren.size === 0) return;

    setIsExecutingBatch(true);
    const sessions: { issueId: string; sessionId: string }[] = [];

    try {
      for (const childId of Array.from(selectedChildren)) {
        const result = await startExecution.mutateAsync({
          issueId: childId,
          provider: 'claude_code',
        });
        sessions.push({ issueId: childId, sessionId: result.session_id });
      }

      if (onBatchExecutionStart && sessions.length > 0) {
        onBatchExecutionStart(sessions);
      } else if (onExecutionStart && sessions.length > 0) {
        onExecutionStart(sessions[0].sessionId);
      }

      setSelectedChildren(new Set());
    } catch (error) {
      console.error('Failed to execute selected tasks:', error);
    } finally {
      setIsExecutingBatch(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-2xl mx-4 max-h-[90vh] bg-zinc-900 rounded-xl border border-zinc-800 shadow-xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-xl">{issueType?.icon}</span>
            <Link
              href={`/codeboard/issues/${issue.id}`}
              className="text-sm font-mono text-zinc-500 hover:text-cyan-400 transition-colors flex items-center gap-1"
              title="Open full detail page"
            >
              {issue.key}
              <ExternalLink className="w-3 h-3" />
            </Link>
            <span
              className={cn(
                'text-xs px-2 py-0.5 rounded',
                status?.color,
                'text-white'
              )}
            >
              {status?.label}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ExecuteButton issue={issue} onExecutionStart={onExecutionStart} size="md" data-execute-button />
            <div className="w-px h-6 bg-zinc-700 mx-1" />
            <button
              onClick={copyIssueKey}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Copy issue key (${formatShortcut(SHORTCUTS.COPY_ISSUE_KEY)})`}
            >
              <Copy className="w-4 h-4" />
            </button>
            <button
              onClick={handleStartEdit}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Edit (${formatShortcut(SHORTCUTS.EDIT_ISSUE)})`}
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={onDelete}
              className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Delete (${formatShortcut(SHORTCUTS.DELETE_ISSUE)})`}
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Close (${formatShortcut(SHORTCUTS.ESCAPE)})`}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content - Scrollable */}
        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          {/* Parent Breadcrumb */}
          {parent && (
            <div
              className="flex items-center gap-2 p-3 bg-zinc-800/50 rounded-lg cursor-pointer hover:bg-zinc-800 transition-colors"
              onClick={() => onIssueClick?.(parent)}
            >
              <span className="text-zinc-500 text-sm">Part of:</span>
              <span className="text-base">
                {ISSUE_TYPES.find((t) => t.type === parent.type)?.icon}
              </span>
              <span className="text-sm font-mono text-zinc-400">{parent.key}</span>
              <ChevronRight className="w-4 h-4 text-zinc-600" />
              <span
                className={cn(
                  'text-sm font-medium',
                  parent.type === 'EPIC' && 'text-purple-400',
                  parent.type === 'STORY' && 'text-blue-400'
                )}
              >
                {parent.title}
              </span>
            </div>
          )}

          {/* Title & Description */}
          {isEditing ? (
            <div className="space-y-3">
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full px-3 py-2 text-xl font-semibold bg-zinc-800 border border-zinc-700 rounded-lg focus:outline-none focus:border-cyan-500"
              />
              <textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Add description..."
                rows={4}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg focus:outline-none focus:border-cyan-500 resize-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleSaveEdit}
                  className="px-3 py-1.5 text-sm bg-cyan-600 hover:bg-cyan-500 rounded-lg"
                >
                  Save
                </button>
                <button
                  onClick={() => setIsEditing(false)}
                  className="px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <h1 className="text-xl font-semibold">{issue.title}</h1>
              {issue.description && (
                <p className="text-zinc-400 whitespace-pre-wrap">{issue.description}</p>
              )}
            </>
          )}

          {/* Implementation Summary (CB-1612) — compact view of latest ExecutionSummary */}
          {latestSummary && (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <button
                onClick={() => setIsImplSummaryOpen(!isImplSummaryOpen)}
                aria-expanded={isImplSummaryOpen}
                aria-controls="impl-summary-modal-panel"
                className="w-full flex items-center gap-2 px-4 py-3 bg-zinc-800/50 hover:bg-zinc-800 transition-colors text-left"
              >
                <Sparkles className="w-4 h-4 text-cyan-400 shrink-0" />
                <span className="text-sm font-medium text-zinc-300 flex-1">Implementation Summary</span>
                <span className="text-xs text-zinc-500 mr-2">
                  {executionSummaries && executionSummaries.length > 1
                    ? `latest of ${executionSummaries.length}`
                    : 'latest'}
                </span>
                <ChevronDown
                  className={cn(
                    'w-4 h-4 text-zinc-500 transition-transform',
                    isImplSummaryOpen && 'rotate-180'
                  )}
                />
              </button>
              {isImplSummaryOpen && (
                <div id="impl-summary-modal-panel" className="px-4 py-3 border-t border-zinc-800 space-y-3">
                  {latestSummary.summary && (
                    <p className="text-sm text-zinc-300 whitespace-pre-wrap">
                      {latestSummary.summary.length > 200
                        ? `${latestSummary.summary.slice(0, 200).trimEnd()}…`
                        : latestSummary.summary}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono">
                      <FileCode className="w-3 h-3" aria-hidden="true" />
                      {implFiles.length} file{implFiles.length === 1 ? '' : 's'}
                    </span>
                    {typeof latestSummary.linesAdded === 'number' && latestSummary.linesAdded > 0 && (
                      <span className="px-1.5 py-0.5 rounded bg-green-900/40 text-green-400 font-mono">
                        +{latestSummary.linesAdded}
                      </span>
                    )}
                    {typeof latestSummary.linesRemoved === 'number' && latestSummary.linesRemoved > 0 && (
                      <span className="px-1.5 py-0.5 rounded bg-red-900/40 text-red-400 font-mono">
                        -{latestSummary.linesRemoved}
                      </span>
                    )}
                  </div>
                  <Link
                    href={`/codeboard/issues/${encodeURIComponent(issue.id)}#implementation`}
                    className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    View Full
                    <ChevronRight className="w-3 h-3" />
                  </Link>
                </div>
              )}
            </div>
          )}

          {/* Properties Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Status */}
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Status</label>
              <select
                value={issue.status}
                onChange={(e) => handleStatusChange(e.target.value as IssueStatus)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500"
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
              <label className="block text-xs font-medium text-zinc-500 mb-1">Priority</label>
              <select
                value={issue.priority}
                onChange={(e) => handlePriorityChange(e.target.value as Priority)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500"
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
              <label className="block text-xs font-medium text-zinc-500 mb-1">Type</label>
              <select
                value={issue.type}
                onChange={(e) => handleTypeChange(e.target.value as IssueType)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500"
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
              <label className="block text-xs font-medium text-zinc-500 mb-1">Story Points</label>
              <div className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm">
                {issue.storyPoints ?? '-'}
              </div>
            </div>
          </div>

          {/* People */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-zinc-400">People</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-zinc-500" />
                <span className="text-zinc-500">Assignee:</span>
                <span>{issue.assignee || 'Unassigned'}</span>
              </div>
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-zinc-500" />
                <span className="text-zinc-500">Reporter:</span>
                <span>{issue.reporter || 'Unknown'}</span>
              </div>
            </div>
          </div>

          {/* Dates */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-zinc-400">Dates</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-zinc-500" />
                <span className="text-zinc-500">Created:</span>
                <span>{new Date(issue.createdAt).toLocaleDateString()}</span>
              </div>
              {issue.startedAt && (
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-zinc-500" />
                  <span className="text-zinc-500">Started:</span>
                  <span>{new Date(issue.startedAt).toLocaleDateString()}</span>
                </div>
              )}
              {issue.completedAt && (
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-green-500" />
                  <span className="text-zinc-500">Completed:</span>
                  <span>{new Date(issue.completedAt).toLocaleDateString()}</span>
                </div>
              )}
              {issue.dueDate && (
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-orange-500" />
                  <span className="text-zinc-500">Due:</span>
                  <span
                    className={cn(new Date(issue.dueDate) < new Date() ? 'text-red-500' : '')}
                  >
                    {new Date(issue.dueDate).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Linked Commits */}
          {linkedCommits && linkedCommits.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <Link2 className="w-4 h-4" />
                Linked Commits ({linkedCommits.length})
              </h3>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
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

          {/* Git Commits (fallback if no linked commits) */}
          {(!linkedCommits || linkedCommits.length === 0) &&
            issueCommits &&
            issueCommits.commits.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                  <GitCommit className="w-4 h-4" />
                  Related Commits ({issueCommits.total})
                </h3>
                <div className="space-y-2 max-h-[200px] overflow-y-auto">
                  {issueCommits.commits.slice(0, 5).map((commit) => (
                    <div key={commit.hash} className="p-2 bg-zinc-800 rounded-lg text-sm">
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

          {/* Child Issues */}
          {(issue.type === 'EPIC' || issue.type === 'STORY') && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-zinc-400">
                  {issue.type === 'EPIC' ? 'Stories' : 'Tasks'} ({children.length})
                </h3>
                {children.length > 0 && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={toggleSelectAll}
                      className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                    >
                      {selectedChildren.size === children.length ? (
                        <CheckSquare className="w-4 h-4 text-cyan-400" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                      {selectedChildren.size === children.length ? 'Deselect All' : 'Select All'}
                    </button>
                  </div>
                )}
              </div>
              {children.length === 0 && (
                <p className="text-xs text-zinc-500">
                  No {issue.type === 'EPIC' ? 'stories' : 'tasks'} yet
                </p>
              )}
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {children.map((child) => {
                  const childType = ISSUE_TYPES.find((t) => t.type === child.type);
                  const childStatus = STATUS_COLUMNS.find((s) => s.status === child.status);
                  const isSelected = selectedChildren.has(child.id);
                  return (
                    <div
                      key={child.id}
                      className={cn(
                        'flex items-center gap-3 p-3 rounded-lg transition-colors',
                        'bg-zinc-800/50 hover:bg-zinc-800 border-l-4',
                        child.type === 'STORY' && 'border-l-blue-500',
                        child.type === 'TASK' && 'border-l-zinc-500',
                        child.type === 'BUG' && 'border-l-red-500',
                        child.type === 'SUBTASK' && 'border-l-zinc-600',
                        isSelected && 'ring-1 ring-cyan-500/50 bg-cyan-900/10'
                      )}
                    >
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleChildSelection(child.id);
                        }}
                        className="shrink-0 text-zinc-400 hover:text-cyan-400 transition-colors"
                      >
                        {isSelected ? (
                          <CheckSquare className="w-5 h-5 text-cyan-400" />
                        ) : (
                          <Square className="w-5 h-5" />
                        )}
                      </button>
                      <div
                        className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer"
                        onClick={() => onIssueClick?.(child)}
                      >
                        <span className="text-base">{childType?.icon}</span>
                        <span className="text-xs font-mono text-zinc-500">{child.key}</span>
                        <span className="text-sm flex-1 truncate">{child.title}</span>
                        <span
                          className={cn(
                            'text-xs px-2 py-0.5 rounded shrink-0',
                            child.status === 'DONE' && 'bg-green-900/30 text-green-400',
                            child.status === 'IN_PROGRESS' && 'bg-blue-900/30 text-blue-400',
                            child.status === 'BACKLOG' && 'bg-zinc-700 text-zinc-400',
                            child.status === 'TODO' && 'bg-yellow-900/30 text-yellow-400'
                          )}
                        >
                          {childStatus?.label}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
              {selectedChildren.size > 0 && (
                <button
                  onClick={handleExecuteSelected}
                  disabled={isExecutingBatch}
                  className={cn(
                    'w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg transition-colors',
                    'bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed'
                  )}
                >
                  <PlayCircle className="w-4 h-4" />
                  {isExecutingBatch
                    ? 'Starting Execution...'
                    : `Execute ${selectedChildren.size} Selected ${selectedChildren.size === 1 ? 'Task' : 'Tasks'}`}
                </button>
              )}
            </div>
          )}

          {/* AI Breakdown Action */}
          {(issue.type === 'EPIC' || issue.type === 'STORY') && onAIBreakdown && (
            <div className="pt-4 border-t border-zinc-800">
              <button
                onClick={() => onAIBreakdown(issue)}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg transition-colors"
              >
                <Sparkles className="w-4 h-4" />
                AI Breakdown
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
