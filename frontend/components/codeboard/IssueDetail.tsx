'use client';

/**
 * Issue Detail Slide-over Panel
 */

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { X, Edit2, Trash2, MessageSquare, Clock, User, Calendar, GitCommit, Sparkles, ChevronRight, ChevronDown, Play, GitMerge, CheckCircle, AlertCircle, Link2, ExternalLink, Square, CheckSquare, PlayCircle, FileText, Loader2, Brain, FileCode, BookOpen } from 'lucide-react';
import { Issue, ISSUE_TYPES, PRIORITIES, STATUS_COLUMNS, IssueStatus, Priority, IssueType } from '@/types/codeboard';
import { useIssueCommits, useLinkedCommits, useIssue, useStartExecution, useGenerateDocumentation, useExecutionSummaries, CommitLink } from '@/hooks/useCodeBoard';
import { ExecuteButton } from './ExecuteButton';
import { IssueSearchBar, highlightMatch, matchesSearch } from './IssueSearchBar';
import { cn } from '@/lib/utils';

interface IssueDetailProps {
  issue: Issue | null;
  issues?: Issue[]; // All issues for parent/children lookup
  isOpen: boolean;
  onClose: () => void;
  onUpdate: (data: Partial<Issue>) => void;
  onDelete: () => void;
  projectId?: string;
  onAIBreakdown?: (issue: Issue) => void;
  onIssueClick?: (issue: Issue) => void; // Navigate to another issue
  onExecutionStart?: (sessionId: string) => void; // Open execution modal
  onBatchExecutionStart?: (sessions: { issueId: string; sessionId: string }[]) => void; // Execute multiple tasks
}

export function IssueDetail({ issue, issues = [], isOpen, onClose, onUpdate, onDelete, projectId, onAIBreakdown, onIssueClick, onExecutionStart, onBatchExecutionStart }: IssueDetailProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [selectedChildren, setSelectedChildren] = useState<Set<string>>(new Set());
  const [isExecutingBatch, setIsExecutingBatch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isAIContextOpen, setIsAIContextOpen] = useState(false);
  const [isEditingAIContext, setIsEditingAIContext] = useState(false);
  const [editAIContext, setEditAIContext] = useState('');
  const [isImplSummaryOpen, setIsImplSummaryOpen] = useState(true);

  const startExecution = useStartExecution();
  const generateDocs = useGenerateDocumentation();

  // Fetch the issue with children directly from API (independent of filters)
  const { data: issueWithChildren } = useIssue(issue?.id || null);

  // Fetch execution summaries (CB-1612) — render compact summary section if any.
  const { data: executionSummaries } = useExecutionSummaries(
    issue?.id,
    issue?.projectId,
  );
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

  // Fetch commits related to this issue (git log search)
  const { data: issueCommits } = useIssueCommits(projectId || null, issue?.key || null);

  // Fetch linked commits (from our commit linking system)
  const { data: linkedCommits } = useLinkedCommits(issue?.id || null);

  // Find parent issue from local issues array
  const parent = useMemo(() => {
    if (!issue?.parentId || !issues.length) return null;
    return issues.find(i => i.id === issue.parentId);
  }, [issue?.parentId, issues.length, issues]);

  // Get child issues - prefer API response (has all children regardless of filters)
  // Fall back to filtered issues array if API hasn't loaded yet
  const allChildren = useMemo(() => {
    // Use API response if available (includes all children regardless of search filters)
    if (issueWithChildren?.children && issueWithChildren.children.length > 0) {
      const apiChildren = issueWithChildren.children;
      // Sort: Stories first, then Tasks, then by sequence
      return [...apiChildren].sort((a, b) => {
        const typeOrder: Record<string, number> = { 'STORY': 0, 'TASK': 1, 'BUG': 1, 'SUBTASK': 2 };
        const orderA = typeOrder[a.type] ?? 99;
        const orderB = typeOrder[b.type] ?? 99;
        if (orderA !== orderB) return orderA - orderB;
        return a.sequence - b.sequence;
      });
    }

    // Fallback to local issues array
    if (!issue?.id || !issues.length) return [];
    const directChildren = issues.filter(i => i.parentId === issue.id);

    // Sort: Stories first, then Tasks, then by sequence
    return directChildren.sort((a, b) => {
      const typeOrder: Record<string, number> = { 'STORY': 0, 'TASK': 1, 'BUG': 1, 'SUBTASK': 2 };
      const orderA = typeOrder[a.type] ?? 99;
      const orderB = typeOrder[b.type] ?? 99;
      if (orderA !== orderB) return orderA - orderB;
      return a.sequence - b.sequence;
    });
  }, [issue?.id, issues.length, issues, issueWithChildren?.children]);

  // Filter children based on search query
  const children = useMemo(() => {
    if (!searchQuery.trim()) return allChildren;
    return allChildren.filter(child =>
      matchesSearch(child.title, searchQuery) ||
      matchesSearch(child.key, searchQuery) ||
      matchesSearch(child.description, searchQuery)
    );
  }, [allChildren, searchQuery]);

  // Filter linked commits based on search query
  const filteredLinkedCommits = useMemo(() => {
    if (!linkedCommits) return [];
    if (!searchQuery.trim()) return linkedCommits;
    return linkedCommits.filter(commit =>
      matchesSearch(commit.message, searchQuery) ||
      matchesSearch(commit.shortHash, searchQuery) ||
      matchesSearch(commit.author, searchQuery)
    );
  }, [linkedCommits, searchQuery]);

  // Filter issue commits based on search query
  const filteredIssueCommits = useMemo(() => {
    if (!issueCommits?.commits) return [];
    if (!searchQuery.trim()) return issueCommits.commits;
    return issueCommits.commits.filter(commit =>
      matchesSearch(commit.message, searchQuery) ||
      matchesSearch(commit.short_hash, searchQuery) ||
      matchesSearch(commit.author, searchQuery)
    );
  }, [issueCommits?.commits, searchQuery]);

  // Calculate total search results count
  const searchResultCount = useMemo(() => {
    if (!searchQuery.trim()) return 0;
    return children.length + filteredLinkedCommits.length + filteredIssueCommits.length;
  }, [searchQuery, children.length, filteredLinkedCommits.length, filteredIssueCommits.length]);

  if (!isOpen || !issue) return null;

  const issueType = ISSUE_TYPES.find(t => t.type === issue.type);
  const priority = PRIORITIES.find(p => p.priority === issue.priority);
  const status = STATUS_COLUMNS.find(s => s.status === issue.status);

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

  // Toggle selection of a child task
  const toggleChildSelection = (childId: string) => {
    setSelectedChildren(prev => {
      const next = new Set(prev);
      if (next.has(childId)) {
        next.delete(childId);
      } else {
        next.add(childId);
      }
      return next;
    });
  };

  // Select/deselect all children
  const toggleSelectAll = () => {
    if (selectedChildren.size === children.length) {
      setSelectedChildren(new Set());
    } else {
      setSelectedChildren(new Set(children.map(c => c.id)));
    }
  };

  // Execute selected children sequentially
  const handleExecuteSelected = async () => {
    if (selectedChildren.size === 0) return;

    setIsExecutingBatch(true);
    const sessions: { issueId: string; sessionId: string }[] = [];

    try {
      // Execute each selected child sequentially
      for (const childId of Array.from(selectedChildren)) {
        const result = await startExecution.mutateAsync({
          issueId: childId,
          provider: 'claude_code',
        });
        sessions.push({ issueId: childId, sessionId: result.session_id });
      }

      // Notify parent about batch execution
      if (onBatchExecutionStart && sessions.length > 0) {
        onBatchExecutionStart(sessions);
      } else if (onExecutionStart && sessions.length > 0) {
        // Fallback: just open the first session
        onExecutionStart(sessions[0].sessionId);
      }

      // Clear selection after starting execution
      setSelectedChildren(new Set());
    } catch (error) {
      console.error('Failed to execute selected tasks:', error);
    } finally {
      setIsExecutingBatch(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative w-full max-w-xl bg-zinc-900 border-l border-zinc-800 overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 bg-zinc-900 border-b border-zinc-800">
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
          </div>
          <div className="flex items-center gap-2">
            {/* Execute Button */}
            <ExecuteButton
              issue={issue}
              onExecutionStart={onExecutionStart}
              size="md"
            />
            <div className="w-px h-6 bg-zinc-700 mx-1" />
            <button
              onClick={handleStartEdit}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title="Edit"
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={onDelete}
              className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 rounded-lg transition-colors"
              title="Delete"
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/50">
          <IssueSearchBar
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search children, commits, text..."
            resultCount={searchResultCount}
            showResultCount={searchQuery.length > 0}
          />
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Parent Breadcrumb */}
          {parent && (
            <div
              className="flex items-center gap-2 p-3 bg-zinc-800/50 rounded-lg cursor-pointer hover:bg-zinc-800 transition-colors"
              onClick={() => onIssueClick?.(parent)}
            >
              <span className="text-zinc-500 text-sm">Part of:</span>
              <span className="text-base">{ISSUE_TYPES.find(t => t.type === parent.type)?.icon}</span>
              <span className="text-sm font-mono text-zinc-400">{parent.key}</span>
              <ChevronRight className="w-4 h-4 text-zinc-600" />
              <span className={cn(
                'text-sm font-medium',
                parent.type === 'EPIC' && 'text-purple-400',
                parent.type === 'STORY' && 'text-blue-400'
              )}>
                {parent.title}
              </span>
            </div>
          )}

          {/* Title */}
          {isEditing ? (
            <div className="space-y-3">
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full px-3 py-2 text-xl font-semibold bg-zinc-800 border border-zinc-700 rounded-lg
                           focus:outline-none focus:border-cyan-500"
              />
              <textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Add description..."
                rows={4}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                           focus:outline-none focus:border-cyan-500 resize-none"
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

          {/* AI Context - only for FEATURE, EPIC, STORY */}
          {(issue.type === 'FEATURE' || issue.type === 'EPIC' || issue.type === 'STORY') && (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <button
                onClick={() => setIsAIContextOpen(!isAIContextOpen)}
                className="w-full flex items-center gap-2 px-4 py-3 bg-zinc-800/50 hover:bg-zinc-800 transition-colors text-left"
              >
                <Brain className="w-4 h-4 text-purple-400 shrink-0" />
                <span className="text-sm font-medium text-zinc-300 flex-1">AI Context</span>
                {issue.aiContext && (
                  <span className="text-xs text-zinc-500 mr-2">configured</span>
                )}
                <ChevronDown className={cn(
                  'w-4 h-4 text-zinc-500 transition-transform',
                  isAIContextOpen && 'rotate-180'
                )} />
              </button>
              {isAIContextOpen && (
                <div className="px-4 py-3 border-t border-zinc-800 space-y-2">
                  <p className="text-xs text-zinc-500">
                    Provide context and instructions for AI agents working on this issue and its children.
                  </p>
                  {isEditingAIContext ? (
                    <div className="space-y-2">
                      <textarea
                        value={editAIContext}
                        onChange={(e) => setEditAIContext(e.target.value)}
                        placeholder="e.g. Use the existing auth middleware pattern. All new endpoints need unit tests. Prefer composition over inheritance..."
                        rows={5}
                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                                   focus:outline-none focus:border-purple-500 resize-none placeholder:text-zinc-600"
                        autoFocus
                        onBlur={() => {
                          if (editAIContext !== (issue.aiContext || '')) {
                            onUpdate({ aiContext: editAIContext || undefined });
                          }
                          setIsEditingAIContext(false);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') {
                            setEditAIContext(issue.aiContext || '');
                            setIsEditingAIContext(false);
                          }
                        }}
                      />
                      <p className="text-xs text-zinc-600">
                        Saves on blur. Press Esc to cancel.
                      </p>
                    </div>
                  ) : (
                    <div
                      className="min-h-[40px] px-3 py-2 bg-zinc-800/50 rounded-lg cursor-pointer hover:bg-zinc-800 transition-colors"
                      onClick={() => {
                        setEditAIContext(issue.aiContext || '');
                        setIsEditingAIContext(true);
                      }}
                    >
                      {issue.aiContext ? (
                        <p className="text-sm text-zinc-300 whitespace-pre-wrap">{issue.aiContext}</p>
                      ) : (
                        <p className="text-sm text-zinc-600 italic">Click to add AI context...</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Feature Documentation (CB-2065) — always visible for FEATURE issues */}
          {issue.type === 'FEATURE' && (
            <Link
              href={`/codeboard/features/${encodeURIComponent(issue.id)}/documentation`}
              className="flex items-center gap-2 px-4 py-3 rounded-lg border border-violet-900/40 bg-violet-950/10 hover:bg-violet-950/20 transition-colors"
            >
              <BookOpen className="w-4 h-4 text-violet-400 shrink-0" aria-hidden="true" />
              <span className="text-sm font-medium text-zinc-200 flex-1">
                Feature Documentation
              </span>
              <ChevronRight className="w-4 h-4 text-zinc-500" />
            </Link>
          )}

          {/* Implementation Summary (CB-1612) — compact view of latest ExecutionSummary */}
          {latestSummary && (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <button
                onClick={() => setIsImplSummaryOpen(!isImplSummaryOpen)}
                aria-expanded={isImplSummaryOpen}
                aria-controls="impl-summary-panel"
                className="w-full flex items-center gap-2 px-4 py-3 bg-zinc-800/50 hover:bg-zinc-800 transition-colors text-left"
              >
                <Sparkles className="w-4 h-4 text-cyan-400 shrink-0" />
                <span className="text-sm font-medium text-zinc-300 flex-1">Implementation Summary</span>
                <span className="text-xs text-zinc-500 mr-2">
                  {executionSummaries && executionSummaries.length > 1
                    ? `latest of ${executionSummaries.length}`
                    : 'latest'}
                </span>
                <ChevronDown className={cn(
                  'w-4 h-4 text-zinc-500 transition-transform',
                  isImplSummaryOpen && 'rotate-180'
                )} />
              </button>
              {isImplSummaryOpen && (
                <div id="impl-summary-panel" className="px-4 py-3 border-t border-zinc-800 space-y-3">
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
                  <div className="flex items-center gap-3">
                    <Link
                      href={`/codeboard/issues/${encodeURIComponent(issue.id)}#implementation`}
                      className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                    >
                      View Full
                      <ChevronRight className="w-3 h-3" />
                    </Link>
                    {issue.type === 'FEATURE' && (
                      <Link
                        href={`/codeboard/features/${encodeURIComponent(issue.id)}/documentation`}
                        className="inline-flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors"
                      >
                        <BookOpen className="w-3 h-3" aria-hidden="true" />
                        Documentation
                      </Link>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Properties */}
          <div className="grid grid-cols-2 gap-4">
            {/* Status */}
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Status</label>
              <select
                value={issue.status}
                onChange={(e) => handleStatusChange(e.target.value as IssueStatus)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-cyan-500"
              >
                {STATUS_COLUMNS.map(s => (
                  <option key={s.status} value={s.status}>{s.label}</option>
                ))}
              </select>
            </div>

            {/* Priority */}
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Priority</label>
              <select
                value={issue.priority}
                onChange={(e) => handlePriorityChange(e.target.value as Priority)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-cyan-500"
              >
                {PRIORITIES.map(p => (
                  <option key={p.priority} value={p.priority}>{p.label}</option>
                ))}
              </select>
            </div>

            {/* Type */}
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Type</label>
              <select
                value={issue.type}
                onChange={(e) => handleTypeChange(e.target.value as IssueType)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-cyan-500"
              >
                {ISSUE_TYPES.map(t => (
                  <option key={t.type} value={t.type}>{t.icon} {t.label}</option>
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
                  <span className={cn(
                    new Date(issue.dueDate) < new Date() ? 'text-red-500' : ''
                  )}>
                    {new Date(issue.dueDate).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Linked Commits (from commit-issue linking system) */}
          {linkedCommits && linkedCommits.length > 0 && (searchQuery ? filteredLinkedCommits.length > 0 : true) && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <Link2 className="w-4 h-4" />
                Linked Commits ({searchQuery ? `${filteredLinkedCommits.length}/${linkedCommits.length}` : linkedCommits.length})
              </h3>
              <div className="space-y-2">
                {filteredLinkedCommits.slice(0, 10).map((link) => (
                  <div
                    key={link.id}
                    className={cn(
                      "p-3 rounded-lg text-sm border-l-2",
                      link.linkType === 'FIXES' && "bg-green-900/20 border-l-green-500",
                      link.linkType === 'CLOSES' && "bg-green-900/20 border-l-green-500",
                      link.linkType === 'IMPLEMENTS' && "bg-blue-900/20 border-l-blue-500",
                      link.linkType === 'MENTIONS' && "bg-zinc-800 border-l-zinc-600"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <code className="text-xs text-cyan-500 shrink-0">{highlightMatch(link.shortHash, searchQuery)}</code>
                        <span className="text-zinc-300 truncate">{highlightMatch(link.message, searchQuery)}</span>
                      </div>
                      <span className={cn(
                        "text-xs px-1.5 py-0.5 rounded shrink-0",
                        link.linkType === 'FIXES' && "bg-green-900/40 text-green-400",
                        link.linkType === 'CLOSES' && "bg-green-900/40 text-green-400",
                        link.linkType === 'IMPLEMENTS' && "bg-blue-900/40 text-blue-400",
                        link.linkType === 'MENTIONS' && "bg-zinc-700 text-zinc-400"
                      )}>
                        {link.linkType.toLowerCase()}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-zinc-500 mt-1.5">
                      <span>{highlightMatch(link.author, searchQuery)}</span>
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

          {/* Git Commits (from git log search - fallback if no linked commits) */}
          {(!linkedCommits || linkedCommits.length === 0) && issueCommits && issueCommits.commits.length > 0 && (searchQuery ? filteredIssueCommits.length > 0 : true) && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <GitCommit className="w-4 h-4" />
                Related Commits ({searchQuery ? `${filteredIssueCommits.length}/${issueCommits.total}` : issueCommits.total})
              </h3>
              <div className="space-y-2">
                {filteredIssueCommits.slice(0, 5).map((commit) => (
                  <div
                    key={commit.hash}
                    className="p-2 bg-zinc-800 rounded-lg text-sm"
                  >
                    <div className="flex items-center gap-2">
                      <code className="text-xs text-cyan-500">{highlightMatch(commit.short_hash, searchQuery)}</code>
                      <span className="text-zinc-300 truncate">{highlightMatch(commit.message, searchQuery)}</span>
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">
                      {highlightMatch(commit.author, searchQuery)} - {new Date(commit.date).toLocaleDateString()}
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
                  {issue.type === 'EPIC' ? 'Stories' : 'Tasks'} ({searchQuery ? `${children.length}/${allChildren.length}` : children.length})
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
              {children.length === 0 && !searchQuery && (
                <p className="text-xs text-zinc-500">No {issue.type === 'EPIC' ? 'stories' : 'tasks'} yet</p>
              )}
              {children.length === 0 && searchQuery && allChildren.length > 0 && (
                <p className="text-xs text-zinc-500">No matching {issue.type === 'EPIC' ? 'stories' : 'tasks'} found</p>
              )}
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {children.map(child => {
                  const childType = ISSUE_TYPES.find(t => t.type === child.type);
                  const childStatus = STATUS_COLUMNS.find(s => s.status === child.status);
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
                      {/* Checkbox */}
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
                      {/* Clickable content */}
                      <div
                        className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer"
                        onClick={() => onIssueClick?.(child)}
                      >
                        <span className="text-base">{childType?.icon}</span>
                        <span className="text-xs font-mono text-zinc-500">{highlightMatch(child.key, searchQuery)}</span>
                        <span className="text-sm flex-1 truncate">{highlightMatch(child.title, searchQuery)}</span>
                        <span className={cn(
                          'text-xs px-2 py-0.5 rounded shrink-0',
                          child.status === 'DONE' && 'bg-green-900/30 text-green-400',
                          child.status === 'IN_PROGRESS' && 'bg-blue-900/30 text-blue-400',
                          child.status === 'BACKLOG' && 'bg-zinc-700 text-zinc-400',
                          child.status === 'TODO' && 'bg-yellow-900/30 text-yellow-400'
                        )}>
                          {childStatus?.label}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* Execute Selected Button */}
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
                    : `Execute ${selectedChildren.size} Selected ${selectedChildren.size === 1 ? 'Task' : 'Tasks'}`
                  }
                </button>
              )}
            </div>
          )}

          {/* Actions for Epic/Story */}
          {(issue.type === 'EPIC' || issue.type === 'STORY') && (
            <div className="pt-4 border-t border-zinc-800 space-y-2">
              {/* AI Breakdown Button */}
              {onAIBreakdown && (
                <button
                  onClick={() => onAIBreakdown(issue)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg transition-colors"
                >
                  <Sparkles className="w-4 h-4" />
                  AI Breakdown
                </button>
              )}

              {/* Generate Documentation Button - shown when there are child tasks */}
              {children && children.length > 0 && (
                <button
                  onClick={() => generateDocs.mutate({ issueId: issue.id })}
                  disabled={generateDocs.isPending}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  {generateDocs.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Generating Documentation...
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4" />
                      Generate Documentation
                    </>
                  )}
                </button>
              )}

              {/* Success message */}
              {generateDocs.isSuccess && (
                <p className="text-sm text-green-400 text-center">
                  Documentation generated! Check the comments section.
                </p>
              )}

              {/* Error message */}
              {generateDocs.isError && (
                <p className="text-sm text-red-400 text-center">
                  {generateDocs.error?.message || 'Failed to generate documentation'}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
