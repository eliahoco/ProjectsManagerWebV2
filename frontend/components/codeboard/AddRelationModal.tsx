'use client';

/**
 * AddRelationModal — typeahead issue picker + linkType selector + bulk-add.
 *
 * CB-2003 (single-target picker) → CB-2004 (multi-select bulk-add).
 *
 * Two submit paths share the same modal:
 *   * 1 selected target  → POST /issues/{id}/relations (single create).
 *     Surface backend error codes (ALREADY_EXISTS / CYCLE_DETECTED / ...)
 *     inline so the user understands *why* the one row was rejected.
 *   * 2..N selected      → POST /issues/{id}/relations/bulk. Backend
 *     silently skips DUPLICATE / CYCLE candidates and returns a
 *     {created, skipped} envelope. We render `skipped` inline (per
 *     CB-2004 acceptance) so the user sees which rows didn't go through
 *     and why, instead of leaving them to discover via a second open of
 *     the panel.
 *
 * Routing by count (instead of always-bulk) keeps the n=1 flow's clean
 * error contract — the bulk endpoint silently skips a single duplicate /
 * cycle, which would close the modal with no feedback at all.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Loader2, Search, X } from 'lucide-react';
import type {
  Issue,
  IssueLinkBulkCreatePayload,
  IssueLinkBulkResponse,
  IssueLinkBulkSkipped,
  IssueLinkCreatePayload,
  IssueLinkResponse,
  LinkType,
} from '@/types/codeboard';
import {
  APIError,
  useCreateRelation,
  useCreateRelationsBulk,
  useIssues,
} from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';

interface AddRelationModalProps {
  /** Whether the modal is open. Caller controls. */
  isOpen: boolean;
  /** Close handler — called on backdrop click, ESC, X button, or after success. */
  onClose: () => void;
  /** Source issue id — the "from" side of the relation about to be created. */
  issueId: string;
  /** Source issue's project — picker results are scoped to this project. */
  projectId: string;
  /**
   * Optional set of issue ids to hide from picker results — typically the
   * already-linked targets (from `useIssueRelations`) plus the source
   * issue itself. The source is always filtered defensively even when
   * this set is missing it.
   */
  excludeIds?: Set<string>;
  /**
   * Optional success callback. Fires only on a clean close: the n=1 path
   * fires it with the created link, and the bulk path fires it with the
   * first created link IFF the response has zero skipped rows. A bulk
   * response with any skipped row (mixed or all-skipped) intentionally
   * does NOT fire onSuccess — the cache invalidation in the hook already
   * refreshes the parent panel, and firing onSuccess while the result
   * panel is still mounted would let parents scroll/close behind a
   * visible modal. Parents that need a "scroll to new" hook should rely
   * on the close + cache-driven refetch instead.
   */
  onSuccess?: (link: IssueLinkResponse) => void;
}

// Display order mirrors LinkedIssuesPanel (block-graph rows surface first
// because they gate work). The default ("RELATES_TO") is intentionally the
// least-committal type — anyone using a different relationship has to
// pick it, which prevents accidental BLOCKS rows.
const LINK_TYPE_OPTIONS: { value: LinkType; label: string }[] = [
  { value: 'RELATES_TO', label: 'Relates to' },
  { value: 'BLOCKS', label: 'Blocks' },
  { value: 'IS_BLOCKED_BY', label: 'Is blocked by' },
  { value: 'DUPLICATES', label: 'Duplicates' },
  { value: 'IS_DUPLICATED_BY', label: 'Is duplicated by' },
  { value: 'CAUSES', label: 'Causes' },
  { value: 'CAUSED_BY', label: 'Caused by' },
];

// Debounce window for the typeahead. 250ms is the lower bound where most
// users finish a keystroke burst without firing per-character requests;
// short enough that the dropdown still feels live.
const SEARCH_DEBOUNCE_MS = 250;

// Cap on rendered results in the picker. The backend already paginates,
// but slicing client-side keeps the dropdown a single screen even on
// projects where titles share prefixes.
const RESULTS_VISIBLE = 8;

// Minimum query length before the picker fires. <2 chars produces too many
// hits to be useful and burns network round-trips on every keystroke.
const MIN_QUERY_LENGTH = 2;

// Hard cap on selected targets per submit. Mirrors the backend's
// `_ISSUE_LINK_BULK_MAX_TARGETS` (backend/models/schemas.py) — going
// above that limit makes the request 422 at validation. Bound the UI at
// the same value so the form button disables before the user can build
// a request the server will reject.
const MAX_BULK_TARGETS = 100;

// Map backend error codes (CB-1971 contract) → friendly messages. Keep the
// raw code path open: anything not listed falls back to the server's
// `message`, which is already user-readable.
function mapRelationError(err: unknown): string {
  if (!(err instanceof APIError)) {
    return 'Failed to create relation. Please try again.';
  }
  switch (err.code) {
    case 'ALREADY_EXISTS':
      return 'These issues are already linked with this relation type.';
    case 'CYCLE_DETECTED':
      return 'This relation would create a cycle (e.g. A blocks B blocks A).';
    case 'VALIDATION_ERROR':
      return err.message || 'Invalid relation: pick a target in the same project.';
    case 'NOT_FOUND':
      return 'One of the issues no longer exists. Refresh and try again.';
    default:
      return err.message || 'Failed to create relation.';
  }
}

// Display label for a skip reason in the bulk response. Anything outside
// the known set renders generically — see IssueLinkBulkSkipReason type
// note about forward compatibility.
function skipReasonLabel(reason: string): string {
  switch (reason) {
    case 'DUPLICATE':
      return 'Already linked';
    case 'CYCLE':
      return 'Would create a cycle';
    default:
      return 'Skipped';
  }
}

export function AddRelationModal({
  isOpen,
  onClose,
  issueId,
  projectId,
  excludeIds,
  onSuccess,
}: AddRelationModalProps) {
  // Picker state. Two strings — `query` is what the user is typing,
  // `debouncedQuery` is what the network actually fires on. Splitting them
  // makes the input feel responsive without spamming the API.
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  // Multi-select state. Stored as an ordered array (NOT a Set) so the
  // chips render in the order the user picked them — predictable for the
  // user, and for the bulk POST request body (server preserves caller
  // order in the response). De-dup happens at insertion via the
  // selectedIds set below.
  const [selected, setSelected] = useState<Issue[]>([]);
  const [linkType, setLinkType] = useState<LinkType>('RELATES_TO');
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Bulk result (after a successful POST /relations/bulk). When set, the
  // form is replaced by a result panel showing created+skipped — see the
  // CB-2004 acceptance "renders skipped duplicates inline". null means
  // we're in compose mode.
  const [bulkResult, setBulkResult] = useState<IssueLinkBulkResponse | null>(null);
  // Active descendant for keyboard nav. -1 means "no active row" — first
  // ArrowDown moves to 0 (the top result), matching standard combobox UX.
  const [activeIndex, setActiveIndex] = useState<number>(-1);

  const inputRef = useRef<HTMLInputElement | null>(null);
  // Tracks whether the modal is still open at the moment a mutation
  // resolves. The user can dismiss the modal (ESC, backdrop, X) while a
  // POST is in flight — without this guard the late `onSuccess` /
  // `onError` callback would call `setState` on a closed modal and either
  // momentarily flash a stale error on the next reopen, or trigger a
  // React-19 detached-state warning. We deliberately do NOT cancel the
  // request itself: the backend write should still land so cache
  // invalidation runs and a future open of the panel reflects truth.
  const isOpenRef = useRef(isOpen);
  useEffect(() => {
    isOpenRef.current = isOpen;
  }, [isOpen]);
  // Per-submit token. The isOpenRef guard alone covers "user closed and
  // stayed closed", but a long-mounted parent (e.g. the panel renders
  // <AddRelationModal isOpen={open} /> always-mounted) can do
  // close → reopen while a POST is still in flight; on reopen
  // isOpenRef.current is `true` again and a stale callback would close
  // the brand-new compose session out from under the user. Capture the
  // token at submit time and bail on mismatch in every callback.
  const submitTokenRef = useRef(0);
  const createRelation = useCreateRelation();
  const createRelationsBulk = useCreateRelationsBulk();

  // Debounce the query. The timer is captured in a useEffect so a fast
  // typist's burst collapses into a single network call.
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setDebouncedQuery('');
      return;
    }
    const handle = setTimeout(() => {
      setDebouncedQuery(trimmed);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query]);

  // Reset everything when the modal closes — leaving stale query/selected
  // state around would surprise the next open with a pre-filled picker
  // pointing at issues the user no longer cares about.
  useEffect(() => {
    if (!isOpen) {
      // Bump the submit token so any in-flight callback that hasn't
      // resolved yet sees a stale token and bails — protects against the
      // close → reopen race for always-mounted parents.
      submitTokenRef.current += 1;
      setQuery('');
      setDebouncedQuery('');
      setSelected([]);
      setLinkType('RELATES_TO');
      setSubmitError(null);
      setBulkResult(null);
      setActiveIndex(-1);
    }
  }, [isOpen]);

  // Autofocus the search input on open. Run on isOpen edge so reopening
  // the modal mid-session lands the cursor in the picker.
  useEffect(() => {
    if (isOpen) {
      // setTimeout(0) defers focus to after the DOM mounts the input.
      const handle = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(handle);
    }
  }, [isOpen]);

  // ESC closes. Listening on document so focus inside any input still
  // dismisses the modal — capturing-phase listener would be overkill.
  // Guarded against the in-flight mutation: closing mid-submit would
  // surprise the user with no feedback (request still completes server-
  // side; see isOpenRef above). The submit button shows a spinner during
  // pending so the user has a visible reason to wait.
  const isSubmitting = createRelation.isPending || createRelationsBulk.isPending;
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (isSubmitting) return;
      e.stopPropagation();
      onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, onClose, isSubmitting]);

  // Lock body scroll while open so a tall picker dropdown doesn't trigger
  // page-behind scrolling.
  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [isOpen]);

  // ids of currently selected targets — fast membership for filter +
  // dedupe. Recomputed only when `selected` changes.
  const selectedIds = useMemo(() => {
    const set = new Set<string>();
    for (const issue of selected) set.add(issue.id);
    return set;
  }, [selected]);

  // Picker query. `enabled` only fires when there's a real debounced
  // query AND we're still in compose mode (no result panel rendered).
  const isComposing = bulkResult === null;
  const issuesQuery = useIssues(
    debouncedQuery && isComposing ? projectId : null,
    debouncedQuery && isComposing
      ? { search: debouncedQuery, pageSize: RESULTS_VISIBLE * 2 }
      : undefined,
  );

  // Filter results. Always drop the source issue (defense in depth — even
  // if the caller forgot to populate excludeIds), drop already-selected
  // targets so they don't appear duplicated in the dropdown, and drop any
  // additional ids the caller passes (typically the already-linked set so
  // the user doesn't pick a duplicate).
  const results = useMemo<Issue[]>(() => {
    const items = issuesQuery.data?.items ?? [];
    const filtered = items.filter((i) => {
      if (i.id === issueId) return false;
      if (selectedIds.has(i.id)) return false;
      if (excludeIds?.has(i.id)) return false;
      return true;
    });
    return filtered.slice(0, RESULTS_VISIBLE);
  }, [issuesQuery.data, issueId, excludeIds, selectedIds]);

  // Reset active index whenever the result set changes meaningfully.
  // Depending on `results` directly fires on unrelated re-renders (the
  // memo can rebuild while the membership stays the same) and would snap
  // the user's ArrowDown selection back to row 0. Depending on length +
  // first-row id keeps the reset tied to actual list churn.
  const firstResultId = results[0]?.id;
  useEffect(() => {
    setActiveIndex(results.length > 0 ? 0 : -1);
  }, [results.length, firstResultId]);

  const handleSelect = useCallback(
    (issue: Issue) => {
      setSelected((prev) => {
        // Defensive de-dupe: handleSelect is called from picker rows that
        // were already filtered against selectedIds, but a fast click on a
        // stale row (e.g. mid-result-refresh) could still slip through.
        if (prev.some((s) => s.id === issue.id)) return prev;
        if (prev.length >= MAX_BULK_TARGETS) return prev;
        return [...prev, issue];
      });
      setQuery('');
      setDebouncedQuery('');
      setActiveIndex(-1);
      setSubmitError(null);
      // Refocus so the user can immediately type the next query without
      // a click. Defer past the DOM commit so the input is mounted.
      setTimeout(() => inputRef.current?.focus(), 0);
    },
    [],
  );

  const handleRemoveSelected = useCallback((id: string) => {
    setSelected((prev) => prev.filter((s) => s.id !== id));
    setSubmitError(null);
  }, []);

  // Single-target submit. Preserves the n=1 error contract — the bulk
  // endpoint would silently skip a duplicate/cycle and close the modal
  // with no inline feedback, which is exactly the surprise CB-2003 was
  // built to avoid.
  const submitSingle = useCallback(
    (target: Issue) => {
      const payload: IssueLinkCreatePayload = {
        toIssueId: target.id,
        linkType,
      };
      // Capture the submit generation. If the user closes (or closes +
      // reopens) the modal mid-flight, the next reset bump will leave
      // this token stale and the callback short-circuits.
      submitTokenRef.current += 1;
      const token = submitTokenRef.current;
      createRelation.mutate(
        { issueId, payload },
        {
          onSuccess: (link) => {
            if (!isOpenRef.current) return;
            if (submitTokenRef.current !== token) return;
            onSuccess?.(link);
            onClose();
          },
          onError: (err) => {
            if (!isOpenRef.current) return;
            if (submitTokenRef.current !== token) return;
            setSubmitError(mapRelationError(err));
          },
        },
      );
    },
    [linkType, createRelation, issueId, onSuccess, onClose],
  );

  // Bulk submit. On success: if the response has any `skipped` rows we
  // stay open and render the result panel inline (CB-2004 acceptance) so
  // the user sees what didn't go through and why. If everything was
  // accepted, fire onSuccess (with the first created row, mirroring the
  // single-create callback contract) and close.
  //
  // Mixed responses (some created + some skipped) intentionally do NOT
  // fire onSuccess immediately — the cache invalidation in the hook
  // already refreshes the parent panel, and firing onSuccess while the
  // modal is *still open* with the result panel would let parents
  // scroll/close behind a visible modal (CB-2004 review feedback). The
  // BulkResultPanel "Done" button calls onClose, at which point the
  // parent learns about the bulk via cache.
  const submitBulk = useCallback(
    (targets: Issue[]) => {
      const payload: IssueLinkBulkCreatePayload = {
        toIssueIds: targets.map((t) => t.id),
        linkType,
      };
      submitTokenRef.current += 1;
      const token = submitTokenRef.current;
      createRelationsBulk.mutate(
        { issueId, payload },
        {
          onSuccess: (response) => {
            if (!isOpenRef.current) return;
            if (submitTokenRef.current !== token) return;
            if (response.skipped.length === 0) {
              if (response.created.length > 0) {
                onSuccess?.(response.created[0]);
              }
              onClose();
              return;
            }
            // Mixed or all-skipped — stay open, render the result panel,
            // do not fire onSuccess (see docblock above).
            setBulkResult(response);
          },
          onError: (err) => {
            if (!isOpenRef.current) return;
            if (submitTokenRef.current !== token) return;
            setSubmitError(mapRelationError(err));
          },
        },
      );
    },
    [linkType, createRelationsBulk, issueId, onSuccess, onClose],
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      // Block double-submit: native form Enter key can fire submit even
      // when the button is `disabled` if focus is in an input that
      // doesn't intercept. React Query would happily queue a second
      // mutation; the backend deduplicates (CB-1971 ALREADY_EXISTS) but
      // the user would see a confusing flash of a second error toast.
      if (isSubmitting) return;
      if (selected.length === 0) {
        setSubmitError('Pick at least one target issue.');
        return;
      }
      setSubmitError(null);
      // Route by count. n=1 stays on the single-create endpoint to
      // preserve its richer error contract; n>=2 switches to bulk.
      if (selected.length === 1) {
        submitSingle(selected[0]);
      } else {
        submitBulk(selected);
      }
    },
    [isSubmitting, selected, submitSingle, submitBulk],
  );

  // Keyboard nav inside the search input. Up/Down move active row, Enter
  // selects, Tab/blur is left to default behavior so the user can keyboard
  // out of the picker without trapping.
  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (results.length === 0) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1 >= results.length ? 0 : i + 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => (i <= 0 ? results.length - 1 : i - 1));
      } else if (e.key === 'Enter') {
        if (activeIndex >= 0 && activeIndex < results.length) {
          e.preventDefault();
          handleSelect(results[activeIndex]);
        }
      }
    },
    [results, activeIndex, handleSelect],
  );

  // Lookup of original Issue rows by id, used to render skipped chips
  // with their key/title (the response only carries the id). Selected
  // chips disappear once the result panel is shown, so we keep this
  // built off the most recent `selected` snapshot. Declared above the
  // `isOpen` early return so hook order is stable across renders.
  const selectedById = useMemo(() => {
    const map = new Map<string, Issue>();
    for (const issue of selected) map.set(issue.id, issue);
    return map;
  }, [selected]);

  if (!isOpen) return null;

  const showResults =
    isComposing && debouncedQuery.length >= MIN_QUERY_LENGTH;
  const isLoadingResults = issuesQuery.isLoading || issuesQuery.isFetching;
  const atCap = selected.length >= MAX_BULK_TARGETS;

  // Friendly counter for the submit button. Defaults to "Add relation"
  // until the user picks the first target so the empty-state CTA matches
  // the modal's title.
  const submitLabel =
    selected.length <= 1
      ? 'Add relation'
      : `Add ${selected.length} relations`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-relation-title"
    >
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-lg mx-4 bg-zinc-900 rounded-xl border border-zinc-800 shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <h2 id="add-relation-title" className="text-lg font-semibold text-zinc-100">
            {bulkResult ? 'Bulk add result' : 'Add relation'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-zinc-500 hover:text-zinc-300 rounded transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {bulkResult ? (
          <BulkResultPanel
            result={bulkResult}
            selectedById={selectedById}
            onClose={onClose}
          />
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            <div>
              <label
                htmlFor="add-relation-link-type"
                className="block text-sm font-medium text-zinc-400 mb-1"
              >
                Relation type
              </label>
              <select
                id="add-relation-link-type"
                value={linkType}
                onChange={(e) => setLinkType(e.target.value as LinkType)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:border-cyan-500"
                disabled={isSubmitting}
              >
                {LINK_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="add-relation-search"
                className="block text-sm font-medium text-zinc-400 mb-1"
              >
                Target issues
              </label>

              {selected.length > 0 && (
                <ul
                  className="mb-2 flex flex-wrap gap-1.5"
                  aria-label="Selected target issues"
                >
                  {selected.map((issue) => (
                    <li
                      key={issue.id}
                      className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-zinc-800 border border-zinc-700 text-xs"
                    >
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-100">
                        {issue.key}
                      </span>
                      <span className="text-zinc-200 truncate max-w-[14rem]">
                        {issue.title}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRemoveSelected(issue.id)}
                        className="p-0.5 text-zinc-500 hover:text-zinc-200 rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500"
                        aria-label={`Remove ${issue.key}`}
                        disabled={isSubmitting}
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input
                  ref={inputRef}
                  id="add-relation-search"
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                  placeholder={
                    atCap
                      ? `Up to ${MAX_BULK_TARGETS} targets per request`
                      : 'Search issues by key or title…'
                  }
                  className="w-full pl-9 pr-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-cyan-500 disabled:opacity-50"
                  autoComplete="off"
                  role="combobox"
                  aria-expanded={showResults}
                  aria-autocomplete="list"
                  aria-controls="add-relation-results"
                  aria-activedescendant={
                    activeIndex >= 0 && results[activeIndex]
                      ? `add-relation-result-${results[activeIndex].id}`
                      : undefined
                  }
                  disabled={isSubmitting || atCap}
                />
                {showResults && (
                  <ul
                    id="add-relation-results"
                    role="listbox"
                    className="mt-1 max-h-72 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-800"
                  >
                    {isLoadingResults && results.length === 0 && (
                      // Status row, not an option — drop role="option" so
                      // screen readers don't announce it as selectable.
                      <li
                        className="flex items-center gap-2 px-3 py-2 text-sm text-zinc-400"
                        role="presentation"
                      >
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Searching…
                      </li>
                    )}
                    {!isLoadingResults && results.length === 0 && (
                      <li
                        className="px-3 py-2 text-sm text-zinc-500"
                        role="presentation"
                      >
                        No matching issues
                      </li>
                    )}
                    {results.map((issue, idx) => {
                      const isActive = idx === activeIndex;
                      return (
                        <li
                          key={issue.id}
                          id={`add-relation-result-${issue.id}`}
                          role="option"
                          aria-selected={isActive}
                          // onMouseDown (not onClick) so the picker doesn't
                          // close from input blur before the click fires.
                          onMouseDown={(e) => {
                            e.preventDefault();
                            handleSelect(issue);
                          }}
                          onMouseEnter={() => setActiveIndex(idx)}
                          className={cn(
                            'flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors',
                            isActive ? 'bg-zinc-700' : 'hover:bg-zinc-700/60',
                          )}
                        >
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-100 shrink-0">
                            {issue.key}
                          </span>
                          <span className="text-sm text-zinc-200 truncate flex-1">
                            {issue.title}
                          </span>
                          <span className="text-[10px] uppercase tracking-wide text-zinc-500 shrink-0">
                            {issue.type}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              {selected.length > 1 && (
                <p className="mt-1.5 text-xs text-zinc-500">
                  {selected.length} of {MAX_BULK_TARGETS} targets
                  {atCap ? ' (limit reached)' : ''}
                </p>
              )}
            </div>

            {submitError && (
              <div
                className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-start gap-2 text-red-400"
                role="alert"
              >
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                <span className="text-sm">{submitError}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-sm rounded-lg border border-zinc-700 bg-transparent text-zinc-300 hover:border-zinc-500 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500 transition-colors"
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-3 py-1.5 text-sm rounded-lg bg-cyan-600 text-white hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-400 transition-colors flex items-center gap-2"
                disabled={selected.length === 0 || isSubmitting}
              >
                {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {submitLabel}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

interface BulkResultPanelProps {
  result: IssueLinkBulkResponse;
  /**
   * Map of id → originally-selected Issue. Used to enrich the skipped
   * list with the issue's key/title — the response only carries the id,
   * so without this we'd render bare ids.
   */
  selectedById: Map<string, Issue>;
  onClose: () => void;
}

/**
 * Inline summary panel for a successful bulk POST. Renders once the modal
 * has at least one skipped row — the user needs to see *which* targets
 * weren't linked and why before dismissing. CB-2004 acceptance.
 */
function BulkResultPanel({ result, selectedById, onClose }: BulkResultPanelProps) {
  // Group skipped by reason so the user reads "X duplicates, Y cycles"
  // instead of a scattershot list. Order: DUPLICATE first (most common),
  // CYCLE second, anything else last.
  const grouped = useMemo(() => {
    const map = new Map<string, IssueLinkBulkSkipped[]>();
    for (const row of result.skipped) {
      const list = map.get(row.reason);
      if (list) list.push(row);
      else map.set(row.reason, [row]);
    }
    const order = ['DUPLICATE', 'CYCLE'];
    return [
      ...order
        .filter((r) => map.has(r))
        .map((r) => [r, map.get(r) as IssueLinkBulkSkipped[]] as const),
      ...[...map.entries()].filter(([r]) => !order.includes(r)),
    ];
  }, [result.skipped]);

  return (
    <div className="p-6 space-y-4" role="status" aria-live="polite">
      <div className="text-sm text-zinc-300">
        <span className="text-zinc-100 font-medium">
          Added {result.created.length}
          {result.created.length === 1 ? ' relation' : ' relations'}
        </span>
        {result.skipped.length > 0 && (
          <>
            {' '}· skipped{' '}
            <span className="text-zinc-100 font-medium">
              {result.skipped.length}
            </span>
          </>
        )}
        .
      </div>

      {grouped.length > 0 && (
        <div className="space-y-3">
          {grouped.map(([reason, rows]) => (
            <div key={reason}>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1.5">
                {skipReasonLabel(reason)} ({rows.length})
              </div>
              <ul className="flex flex-wrap gap-1.5">
                {rows.map((row) => {
                  const issue = selectedById.get(row.toIssueId);
                  return (
                    <li
                      key={row.toIssueId}
                      className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-zinc-800 border border-zinc-700 text-xs"
                    >
                      {/* max-w bounds rendered length: defense-in-depth
                          against a hostile/MITM'd backend echoing a giant
                          string in toIssueId. JSX text-escapes XSS, but
                          a 10KB id would still wreck the layout. */}
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-100 truncate max-w-[8rem]">
                        {issue?.key ?? row.toIssueId}
                      </span>
                      {issue?.title && (
                        <span className="text-zinc-300 truncate max-w-[14rem]">
                          {issue.title}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onClose}
          className="px-3 py-1.5 text-sm rounded-lg bg-cyan-600 text-white hover:bg-cyan-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-400 transition-colors"
        >
          Done
        </button>
      </div>
    </div>
  );
}

export default AddRelationModal;
