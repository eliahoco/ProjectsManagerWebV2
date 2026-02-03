'use client';

/**
 * Create Issue Modal Component
 * With form validation, error feedback, and duplicate detection
 */

import { useState, useEffect, useCallback } from 'react';
import { X, AlertCircle, Search, Loader2, AlertTriangle } from 'lucide-react';
import { CreateIssueData, IssueType, IssueStatus, Priority, ISSUE_TYPES, PRIORITIES, STATUS_COLUMNS } from '@/types/codeboard';
import { useFindSimilar, type SearchResult } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';

interface FormErrors {
  title?: string;
  storyPoints?: string;
}

interface CreateIssueModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateIssueData) => void;
  defaultStatus?: IssueStatus;
  isLoading?: boolean;
  error?: string | null;
  projectId?: string;
}

export function CreateIssueModal({
  isOpen,
  onClose,
  onSubmit,
  defaultStatus = 'BACKLOG',
  isLoading,
  error,
  projectId,
}: CreateIssueModalProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<IssueType>('TASK');
  const [status, setStatus] = useState<IssueStatus>(defaultStatus);
  const [priority, setPriority] = useState<Priority>('MEDIUM');
  const [storyPoints, setStoryPoints] = useState('');
  const [assignee, setAssignee] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [similarIssues, setSimilarIssues] = useState<SearchResult[]>([]);
  const [showSimilar, setShowSimilar] = useState(false);

  // Find similar hook
  const findSimilar = useFindSimilar();

  // Reset status when defaultStatus changes
  useEffect(() => {
    setStatus(defaultStatus);
  }, [defaultStatus]);

  // Check for similar issues when title changes (debounced)
  useEffect(() => {
    if (!projectId || title.trim().length < 5) {
      setSimilarIssues([]);
      setShowSimilar(false);
      return;
    }

    const timer = setTimeout(() => {
      findSimilar.mutate(
        { projectId, title: title.trim(), description: description.trim() || undefined },
        {
          onSuccess: (data) => {
            // Only show high-confidence matches
            const matches = data.results.filter((r: SearchResult) => (r.score || 0) > 0.5);
            setSimilarIssues(matches);
            setShowSimilar(matches.length > 0);
          },
          onError: () => {
            setSimilarIssues([]);
            setShowSimilar(false);
          },
        }
      );
    }, 500);

    return () => clearTimeout(timer);
  }, [title, description, projectId]);

  // Validate form
  const validate = (): boolean => {
    const newErrors: FormErrors = {};

    // Title validation
    if (!title.trim()) {
      newErrors.title = 'Title is required';
    } else if (title.trim().length < 3) {
      newErrors.title = 'Title must be at least 3 characters';
    } else if (title.trim().length > 200) {
      newErrors.title = 'Title must be less than 200 characters';
    }

    // Story points validation
    if (storyPoints) {
      const points = parseInt(storyPoints);
      if (isNaN(points) || points < 0) {
        newErrors.storyPoints = 'Story points must be a positive number';
      } else if (points > 100) {
        newErrors.storyPoints = 'Story points cannot exceed 100';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleBlur = (field: string) => {
    setTouched({ ...touched, [field]: true });
    validate();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Mark all fields as touched
    setTouched({ title: true, storyPoints: true });

    // Validate before submit
    if (!validate()) {
      return;
    }

    onSubmit({
      title: title.trim(),
      description: description.trim() || undefined,
      type,
      status,
      priority,
      storyPoints: storyPoints ? parseInt(storyPoints) : undefined,
      assignee: assignee.trim() || undefined,
    });

    // Reset form
    resetForm();
  };

  const resetForm = () => {
    setTitle('');
    setDescription('');
    setType('TASK');
    setStatus('BACKLOG');
    setPriority('MEDIUM');
    setStoryPoints('');
    setAssignee('');
    setErrors({});
    setTouched({});
    setSimilarIssues([]);
    setShowSimilar(false);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-zinc-900 rounded-xl border border-zinc-800 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <h2 className="text-lg font-semibold">Create Issue</h2>
          <button
            onClick={handleClose}
            className="p-1 text-zinc-500 hover:text-zinc-300 rounded transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* API Error Banner */}
        {error && (
          <div className="mx-6 mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">
              Title *
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => handleBlur('title')}
              placeholder="What needs to be done?"
              className={cn(
                'w-full px-3 py-2 bg-zinc-800 border rounded-lg',
                'placeholder:text-zinc-500 focus:outline-none',
                touched.title && errors.title
                  ? 'border-red-500 focus:border-red-500'
                  : 'border-zinc-700 focus:border-cyan-500'
              )}
              autoFocus
            />
            {touched.title && errors.title && (
              <p className="mt-1 text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {errors.title}
              </p>
            )}
            {/* Similar issues indicator */}
            {findSimilar.isPending && title.trim().length >= 5 && (
              <div className="mt-1 flex items-center gap-1 text-xs text-zinc-500">
                <Loader2 className="w-3 h-3 animate-spin" />
                Checking for similar issues...
              </div>
            )}
          </div>

          {/* Similar Issues Warning */}
          {showSimilar && similarIssues.length > 0 && (
            <div className="p-3 bg-yellow-900/20 border border-yellow-700/50 rounded-lg">
              <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-2">
                <AlertTriangle className="w-4 h-4" />
                Similar issues found
              </div>
              <p className="text-xs text-zinc-400 mb-2">
                These existing issues might be related to what you&apos;re creating:
              </p>
              <ul className="space-y-1">
                {similarIssues.slice(0, 3).map((result) => (
                  <li key={result.issue_id} className="text-xs text-zinc-300 flex items-center gap-2">
                    <span className="font-mono text-yellow-500">{result.key}</span>
                    <span className="truncate flex-1">
                      {result.document?.split('\n')[0].replace(/^\[.*?\]\s*/, '') || 'Untitled'}
                    </span>
                    <span className="text-zinc-500">
                      {Math.round((result.score || 0) * 100)}% match
                    </span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => setShowSimilar(false)}
                className="mt-2 text-xs text-zinc-500 hover:text-zinc-300"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Type & Priority Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-zinc-400 mb-1">
                Type
              </label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as IssueType)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                           focus:outline-none focus:border-cyan-500"
              >
                {ISSUE_TYPES.map(t => (
                  <option key={t.type} value={t.type}>
                    {t.icon} {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-400 mb-1">
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                           focus:outline-none focus:border-cyan-500"
              >
                {PRIORITIES.map(p => (
                  <option key={p.priority} value={p.priority}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Status & Story Points Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-zinc-400 mb-1">
                Status
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as IssueStatus)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                           focus:outline-none focus:border-cyan-500"
              >
                {STATUS_COLUMNS.map(s => (
                  <option key={s.status} value={s.status}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-400 mb-1">
                Story Points
              </label>
              <input
                type="number"
                value={storyPoints}
                onChange={(e) => setStoryPoints(e.target.value)}
                onBlur={() => handleBlur('storyPoints')}
                placeholder="0"
                min="0"
                max="100"
                className={cn(
                  'w-full px-3 py-2 bg-zinc-800 border rounded-lg',
                  'placeholder:text-zinc-500 focus:outline-none',
                  touched.storyPoints && errors.storyPoints
                    ? 'border-red-500 focus:border-red-500'
                    : 'border-zinc-700 focus:border-cyan-500'
                )}
              />
              {touched.storyPoints && errors.storyPoints && (
                <p className="mt-1 text-xs text-red-400 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {errors.storyPoints}
                </p>
              )}
            </div>
          </div>

          {/* Assignee */}
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">
              Assignee
            </label>
            <input
              type="text"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              placeholder="Who will work on this?"
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                         placeholder:text-zinc-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add more details..."
              rows={4}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                         placeholder:text-zinc-500 focus:outline-none focus:border-cyan-500 resize-none"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 text-sm bg-cyan-600 hover:bg-cyan-500 disabled:bg-zinc-700
                         disabled:text-zinc-500 rounded-lg transition-colors"
            >
              {isLoading ? 'Creating...' : 'Create Issue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
