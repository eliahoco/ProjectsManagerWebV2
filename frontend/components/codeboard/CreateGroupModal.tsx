'use client';

/**
 * CreateGroupModal — title + description + multi-select member picker.
 *
 * Implements CB-2017 (STORY 5.3 — Create group from selection) +
 * CB-2019 (TASK — 'Group selected' action: opens Create-group modal with
 * memberIssueIds). Pre-row-checkbox UX (CB-2018) is intentionally deferred
 * — the picker-inside-modal approach covers the user goal of "create a
 * group with multiple issues" without requiring deep changes to
 * KanbanBoard / HierarchyListView. Cards-with-checkboxes can be added
 * later as a separate workflow on top of this modal.
 *
 * Submit shape: POST /api/projects/{projectId}/groups with
 * `{ title, description?, memberIssueIds }`. Backend cross-project rule
 * (CB-1980) is enforced in `useCreateGroup`; failure surfaces inline.
 *
 * Closes on backdrop click, ESC, X button, or after successful create.
 * Form state is reset between opens so reopening doesn't carry stale
 * picks across sessions.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Search, X } from 'lucide-react';
import type { Issue } from '@/types/codeboard';
import { useIssues } from '@/hooks/useCodeBoard';
import { useCreateGroup } from '@/hooks/useGroups';
import { cn } from '@/lib/utils';

interface CreateGroupModalProps {
  /** Whether the modal is open. Caller controls. */
  isOpen: boolean;
  /** Close handler — called on backdrop click, ESC, X button, or after success. */
  onClose: () => void;
  /** Project the new group will live in. Picker results are scoped to this project. */
  projectId: string;
  /** Optional initial member ids — for future "create from selection" entry points. */
  initialMemberIds?: string[];
  /** Optional success callback — fires after the group is created with the new group id. */
  onSuccess?: (groupId: string) => void;
}

const TITLE_MAX = 200;
const DESCRIPTION_MAX = 5000;

export function CreateGroupModal({
  isOpen,
  onClose,
  projectId,
  initialMemberIds,
  onSuccess,
}: CreateGroupModalProps) {
  // Form state. Reset on close so reopening starts clean rather than
  // carrying stale state from a prior session.
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(initialMemberIds ?? []),
  );
  const [error, setError] = useState<string | null>(null);
  const titleInputRef = useRef<HTMLInputElement | null>(null);

  const createGroup = useCreateGroup(projectId);

  // Reset form whenever the modal toggles open. Use the modal-open flag as
  // a transition trigger — no useReducer needed for this size.
  useEffect(() => {
    if (isOpen) {
      setTitle('');
      setDescription('');
      setSearch('');
      setSelected(new Set(initialMemberIds ?? []));
      setError(null);
      // Defer focus so the modal mount completes first.
      setTimeout(() => titleInputRef.current?.focus(), 0);
    }
    // initialMemberIds intentionally not in deps — we want a stable reset
    // per open, not a re-reset every parent re-render that hands a new
    // array reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // ESC closes. Backdrop click also closes (handled inline below). Both
  // skip when the create mutation is in flight so the user can't lose a
  // half-submitted form.
  useEffect(() => {
    if (!isOpen) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !createGroup.isPending) onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose, createGroup.isPending]);

  // Picker results scoped to project + filtered by search. The hook
  // returns paginated issues; cap page size large enough for typical
  // projects but rely on substring filter for practical narrowing.
  const { data: issuesData } = useIssues(projectId, { pageSize: 500 });
  const allIssues = issuesData?.items ?? [];

  const filteredIssues = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return allIssues;
    return allIssues.filter(
      (i) =>
        i.key.toLowerCase().includes(q) ||
        i.title.toLowerCase().includes(q),
    );
  }, [allIssues, search]);

  const toggleSelected = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);

      const trimmedTitle = title.trim();
      if (!trimmedTitle) {
        setError('Title is required.');
        return;
      }
      if (trimmedTitle.length > TITLE_MAX) {
        setError(`Title must be ${TITLE_MAX} characters or fewer.`);
        return;
      }
      if (description.length > DESCRIPTION_MAX) {
        setError(`Description must be ${DESCRIPTION_MAX} characters or fewer.`);
        return;
      }

      try {
        const created = await createGroup.mutateAsync({
          title: trimmedTitle,
          description: description.trim() || undefined,
          memberIssueIds: Array.from(selected),
        });
        onSuccess?.(created.id);
        onClose();
      } catch (err) {
        // Surface backend message inline. APIError carries `.message`; raw
        // Error fallbacks render generic copy so the user isn't left
        // staring at a frozen form.
        const msg =
          err instanceof Error ? err.message : 'Failed to create group.';
        setError(msg);
      }
    },
    [title, description, selected, createGroup, onSuccess, onClose],
  );

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-group-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        // Backdrop click closes; clicks inside the modal don't bubble.
        if (e.target === e.currentTarget && !createGroup.isPending) {
          onClose();
        }
      }}
    >
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg bg-zinc-900 shadow-xl ring-1 ring-zinc-800">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-zinc-800 px-6 py-4">
          <h2
            id="create-group-title"
            className="text-lg font-semibold text-zinc-100"
          >
            Create issue group
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={createGroup.isPending}
            aria-label="Close"
            className="text-zinc-400 hover:text-zinc-100 disabled:opacity-50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-hidden">
          {/* Body */}
          <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
            <div>
              <label
                htmlFor="group-title"
                className="block text-sm font-medium text-zinc-300"
              >
                Title <span className="text-red-400">*</span>
              </label>
              <input
                ref={titleInputRef}
                id="group-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={TITLE_MAX}
                required
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
                placeholder="e.g. Cascade walker hardening"
              />
            </div>

            <div>
              <label
                htmlFor="group-description"
                className="block text-sm font-medium text-zinc-300"
              >
                Description
              </label>
              <textarea
                id="group-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={DESCRIPTION_MAX}
                rows={3}
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
                placeholder="Optional context for the group's purpose."
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label
                  htmlFor="group-member-search"
                  className="block text-sm font-medium text-zinc-300"
                >
                  Members
                </label>
                <span className="text-xs text-zinc-500">
                  {selected.size} selected
                </span>
              </div>
              <div className="relative">
                <Search
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500"
                  aria-hidden="true"
                />
                <input
                  id="group-member-search"
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by key or title…"
                  className="w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 pl-9 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div className="mt-2 max-h-56 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950">
                {filteredIssues.length === 0 ? (
                  <div className="px-3 py-4 text-center text-sm text-zinc-500">
                    No issues match this search.
                  </div>
                ) : (
                  <ul className="divide-y divide-zinc-800">
                    {filteredIssues.slice(0, 100).map((issue: Issue) => {
                      const isSel = selected.has(issue.id);
                      return (
                        <li key={issue.id}>
                          <button
                            type="button"
                            onClick={() => toggleSelected(issue.id)}
                            className={cn(
                              'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-800/60',
                              isSel && 'bg-blue-900/30',
                            )}
                          >
                            <input
                              type="checkbox"
                              readOnly
                              checked={isSel}
                              tabIndex={-1}
                              className="pointer-events-none h-4 w-4 rounded border-zinc-600 bg-zinc-700"
                              aria-label={`Toggle ${issue.key}`}
                            />
                            <span className="font-mono text-xs text-zinc-400">
                              {issue.key}
                            </span>
                            <span className="flex-1 truncate text-zinc-200">
                              {issue.title}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              {filteredIssues.length > 100 && (
                <p className="mt-1 text-xs text-zinc-500">
                  Showing first 100 of {filteredIssues.length}. Refine the
                  search to narrow.
                </p>
              )}
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-md border border-red-700/50 bg-red-900/20 px-3 py-2 text-sm text-red-200"
              >
                {error}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-2 border-t border-zinc-800 px-6 py-3">
            <button
              type="button"
              onClick={onClose}
              disabled={createGroup.isPending}
              className="rounded-md px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createGroup.isPending || !title.trim()}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {createGroup.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Create group
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
