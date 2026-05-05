'use client';

/**
 * GroupMemberDraggableTable — drag-to-reorder member list for a group.
 *
 * CB-2015 (TASK) → CB-2013 (STORY 5.2 — Group detail page)
 *                 → CB-2009 (EPIC 5 — Groups frontend)
 *                 → CB-1955 (FEATURE — Issue Correlation & Grouping).
 *
 * Replaces the static `MemberTable` shipped in CB-2014 with a draggable
 * variant. Same semantic table markup, same row click → issue detail nav,
 * plus:
 *   * Drag handle column (left) — pointer drag to reorder rows.
 *   * Keyboard fallback — focus a handle, press ArrowUp/ArrowDown to
 *     move that row up/down by one slot. Mirrors the dnd-kit pattern but
 *     without pulling in a new dependency: the project has no drag-drop
 *     lib today and one screen of drag UX doesn't justify adding one.
 *   * Optimistic state via `useReorderGroupMembers` — drag-end immediately
 *     mutates the React Query cache and dispatches a PATCH. Server
 *     response replaces the optimistic order; failures roll back.
 *
 * Why HTML5 drag-and-drop instead of a library:
 *   * No new dep — the bundle stays small and there's no security review
 *     of a new package to run.
 *   * The reorder is bounded (membership cap is 500 server-side, but the
 *     UX target is dozens of members per group), so the polished
 *     keyboard / touch story a lib would give us isn't load-bearing.
 *   * Keyboard fallback covers the a11y story for keyboard users; native
 *     HTML5 d&d covers mouse / touch. Screen reader announcements are
 *     basic — the row's visible position number updates on every move,
 *     which a screen reader reading the row again will pick up.
 *
 * Security notes:
 *   * `member.issue` and `member.issueId` are rendered through React text
 *     nodes (auto-escaped). No `dangerouslySetInnerHTML`.
 *   * The reorder PATCH ships only the ordered list of `issueId`s the
 *     component already trusts (sourced from the server's GET response);
 *     no user-typed text is in the payload.
 *   * The drop target's `dataTransfer` is set to `text/plain` with the
 *     dragged row's id — this is internal-to-component only and never
 *     consumed from cross-origin frames. We DO NOT call
 *     `e.dataTransfer.getData('text/plain')` on drops from external
 *     sources (the drop handler matches the dragged row by the component
 *     state, not by the dataTransfer payload), so a malicious page that
 *     drags a string into the table can't trigger an unintended reorder.
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { GripVertical, Loader2 } from 'lucide-react';
import { useReorderGroupMembers } from '@/hooks/useGroups';
import { STATUS_COLUMNS } from '@/types/codeboard';
import type {
  IssueGroupMemberResponse,
  IssueGroupMembersReorderPayload,
} from '@/types/codeboard';
import { cn } from '@/lib/utils';

// Resolve a status string to its column config (label + color). Mirrors
// the static `MemberTable` in `groups/[id]/page.tsx` so the two tables
// render identically — the only delta is the drag affordance.
function statusConfig(status: string | null | undefined) {
  if (!status) return null;
  return STATUS_COLUMNS.find((s) => s.status === status) ?? null;
}

interface StatusBadgeProps {
  status: string | null | undefined;
  compact?: boolean;
}

function StatusBadge({ status, compact = false }: StatusBadgeProps) {
  const cfg = statusConfig(status);
  const label = cfg?.label ?? (status ?? '—');
  const colorClass = cfg?.color ?? 'bg-zinc-700';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium text-white',
        compact ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        colorClass,
      )}
    >
      {label}
    </span>
  );
}

export interface GroupMemberDraggableTableProps {
  groupId: string;
  members: IssueGroupMemberResponse[];
  onRowClick: (issueId: string) => void;
  // Optional callback fired after a successful reorder PATCH lands. Used by
  // the page to show toast notifications or scroll the moved row into view.
  // Errors do NOT call this — `onError` below is the failure callback.
  onReorderSuccess?: (payload: IssueGroupMembersReorderPayload) => void;
  // Optional error callback. Defaults to a no-op; the hook's optimistic
  // rollback already restores the visible order, so the only thing left is
  // surfacing the error message to the user (toast / inline banner).
  onReorderError?: (error: Error) => void;
}

export function GroupMemberDraggableTable({
  groupId,
  members,
  onRowClick,
  onReorderSuccess,
  onReorderError,
}: GroupMemberDraggableTableProps) {
  const reorderMutation = useReorderGroupMembers(groupId);

  // Synchronous inflight gate for `submitReorder`. We can't rely on
  // `reorderMutation.isPending` for the second of two back-to-back
  // dispatches: React Query updates `isPending` in a microtask after
  // `mutate()`, but a tight ArrowDown→ArrowUp sequence runs both
  // dispatches inside the same render-cycle closure where the second
  // call still sees the stale (false) `isPending`. The ref is flipped
  // synchronously in `submitReorder` itself before `mutate()` returns,
  // so the second dispatch sees `true` and bails. Reset in the
  // mutation's onSettled callback below — runs whether the PATCH
  // succeeded or failed, and AFTER the rollback / cache-replace from
  // the hook's own onError / onSuccess.
  //
  // The `reorderMutation.isPending` flag is still the source of truth
  // for the visual disable (button + draggable attribute) since those
  // re-render naturally on state change. The ref only patches the
  // synchronous-double-fire window.
  const inflightRef = useRef(false);

  // The component renders directly off the cached `members` (passed in
  // from the parent) — no local copy. The reorder mutation's optimistic
  // update mutates the cache, so a fresh `members` prop arrives on the
  // next render. Keeping the cache as the single source of truth means
  // the keyboard handler and the drag handler agree on what's visible.
  //
  // `draggingMemberId` tracks the row currently being dragged. Used to
  // (a) lower the dragged row's opacity and (b) decide where to drop on
  // pointer-over.
  const [draggingMemberId, setDraggingMemberId] = useState<string | null>(
    null,
  );

  // `dropTargetIndex` tracks which boundary the drop indicator should
  // render at. -1 means no indicator (no active drag). This is index in
  // the FINAL list, so dropping at the top yields 0, dropping at the
  // bottom yields members.length.
  const [dropTargetIndex, setDropTargetIndex] = useState<number>(-1);

  // Cache the member ids in render order for the keyboard handler. Mapping
  // every keystroke would re-derive this list anyway; memoizing it keeps
  // the handler trivial and avoids accidental N^2 in long member lists.
  const orderedIssueIds = useMemo(
    () => members.map((m) => m.issueId),
    [members],
  );

  // Dispatch a PATCH /reorder for the given new order. Centralising the
  // call here means both the drag-drop path AND the keyboard path share
  // one no-op guard (skip the mutate if the order didn't actually change).
  // The hook's `onSettled` invalidates the cache, so concurrent
  // member-add/remove from another tab catches up on the next refetch.
  //
  // Inflight gate: if the previous PATCH is still in flight, swallow the
  // new reorder. Stacking two optimistic updates would have the second
  // `onMutate` snapshot the first's optimistic state as its rollback
  // target — on first-call failure the rollback would restore stale data
  // and the second call's success would overwrite it, leaving the cache
  // in a state that doesn't match the server. Drag handles + native
  // `draggable` attr below also gate on `isPending` so the user gets
  // visual feedback (loader on the dragged handle) instead of a silent
  // dropped event.
  const submitReorder = useCallback(
    (nextIssueIds: string[]) => {
      // Synchronous gate via ref — see `inflightRef` comment above for
      // why we can't rely on the React Query `isPending` flag here.
      if (inflightRef.current) return;

      // No-op guard: byte-equal order means no PATCH. The hook would
      // happily round-trip (server returns reordered=0), but skipping
      // the call avoids a wasted network hop on accidental drags.
      if (nextIssueIds.length === orderedIssueIds.length) {
        let same = true;
        for (let i = 0; i < nextIssueIds.length; i += 1) {
          if (nextIssueIds[i] !== orderedIssueIds[i]) {
            same = false;
            break;
          }
        }
        if (same) return;
      }

      // Flip the gate BEFORE `mutate()` so a second synchronous call
      // from the same event loop bails. `onSettled` resets it (runs on
      // both success and error after the hook's own callbacks).
      inflightRef.current = true;
      const payload: IssueGroupMembersReorderPayload = {
        orderedIssueIds: nextIssueIds,
      };
      reorderMutation.mutate(payload, {
        onSuccess: () => onReorderSuccess?.(payload),
        onError: (error) => onReorderError?.(error),
        onSettled: () => {
          inflightRef.current = false;
        },
      });
    },
    [orderedIssueIds, reorderMutation, onReorderError, onReorderSuccess],
  );

  // ---- drag handlers ------------------------------------------------------

  // We track the dragged row by member.id (the IssueGroupMember.id, NOT
  // the issueId — uniqueness across rows is the same in both today, but
  // sticking to the row's own id avoids confusion if a future feature
  // ever cross-renders the same issue in two groups on one page).
  const handleDragStart = useCallback(
    (memberId: string) => (e: React.DragEvent<HTMLTableRowElement>) => {
      // Inflight gate (matches `submitReorder`): refuse to start a new
      // drag while a previous reorder is still in flight. We check the
      // synchronous `inflightRef` first (catches a drag started in the
      // same event loop as a previous keyboard reorder) and then the
      // React-state-tracked `isPending` (catches a drag started on a
      // later tick when the visual `draggable={false}` hasn't yet
      // propagated through the render). `preventDefault` cancels the
      // drag entirely so the user sees no ghost / pointer change.
      if (inflightRef.current || reorderMutation.isPending) {
        e.preventDefault();
        return;
      }
      setDraggingMemberId(memberId);
      // `setData` is required for drag to work in some browsers (Firefox
      // historically refused to fire dragend without a payload). The
      // value is internal-only — we never read it on drop; see security
      // note in module header.
      e.dataTransfer.effectAllowed = 'move';
      try {
        e.dataTransfer.setData('text/plain', memberId);
      } catch {
        // Some browsers throw on setData during drag (e.g. when the page
        // is in a sandboxed iframe). Swallow — the drag still works for
        // us because we read state from `draggingMemberId` not from the
        // dataTransfer.
      }
    },
    [reorderMutation.isPending],
  );

  // `handleDragOver` is required to enable a drop target. We compute the
  // intended drop index from the pointer position relative to the row's
  // vertical midpoint: above midpoint => insert before, below => insert
  // after.
  const handleDragOver = useCallback(
    (rowIndex: number) => (e: React.DragEvent<HTMLTableRowElement>) => {
      if (draggingMemberId === null) return;
      e.preventDefault();
      const rect = e.currentTarget.getBoundingClientRect();
      const midpoint = rect.top + rect.height / 2;
      const insertIndex = e.clientY < midpoint ? rowIndex : rowIndex + 1;
      // Avoid useless re-renders if the same boundary is being hovered.
      setDropTargetIndex((prev) =>
        prev === insertIndex ? prev : insertIndex,
      );
    },
    [draggingMemberId],
  );

  const handleDragLeave = useCallback(
    (rowIndex: number) => () => {
      // Only clear if we're leaving the boundary we last set. Avoids a
      // flicker when the pointer crosses adjacent rows mid-drag.
      setDropTargetIndex((prev) =>
        prev === rowIndex || prev === rowIndex + 1 ? -1 : prev,
      );
    },
    [],
  );

  // Compute the next ordered id list given a source memberId and a
  // target insert index. Pulled out so both drop and keyboard handlers
  // can share the same array-rewrite logic.
  const computeNextOrder = useCallback(
    (sourceMemberId: string, insertIndex: number): string[] | null => {
      const sourceIndex = members.findIndex((m) => m.id === sourceMemberId);
      if (sourceIndex < 0) return null;
      // Removing the source row before the destination shifts indices
      // when source < destination — adjust accordingly so a "drop just
      // below the original" no-op stays a no-op rather than skipping a
      // slot.
      const destIndex =
        insertIndex > sourceIndex ? insertIndex - 1 : insertIndex;
      if (destIndex === sourceIndex) return null;

      const next = members.map((m) => m.issueId);
      const [moved] = next.splice(sourceIndex, 1);
      next.splice(destIndex, 0, moved);
      return next;
    },
    [members],
  );

  const handleDrop = useCallback(
    (rowIndex: number) => (e: React.DragEvent<HTMLTableRowElement>) => {
      e.preventDefault();
      if (draggingMemberId === null) return;
      // Use the live dropTargetIndex if it's set (pointer landed on a
      // boundary), else fall back to dropping immediately below the
      // hovered row.
      const insertIndex =
        dropTargetIndex >= 0 ? dropTargetIndex : rowIndex + 1;
      const next = computeNextOrder(draggingMemberId, insertIndex);
      setDraggingMemberId(null);
      setDropTargetIndex(-1);
      if (next) submitReorder(next);
    },
    [computeNextOrder, draggingMemberId, dropTargetIndex, submitReorder],
  );

  const handleDragEnd = useCallback(() => {
    // Always clear local drag state on dragend, even if the drop didn't
    // land on a row (drag cancelled, dropped outside the table, etc.).
    setDraggingMemberId(null);
    setDropTargetIndex(-1);
  }, []);

  // ---- keyboard handler ---------------------------------------------------

  // Move the row at `rowIndex` up or down by one. Bounded at the ends.
  const moveRow = useCallback(
    (rowIndex: number, direction: -1 | 1) => {
      const target = rowIndex + direction;
      if (target < 0 || target >= members.length) return;
      const next = members.map((m) => m.issueId);
      [next[rowIndex], next[target]] = [next[target], next[rowIndex]];
      submitReorder(next);
    },
    [members, submitReorder],
  );

  // Track the focused handle so ArrowKey events on it move the right row.
  // We use a ref array rather than state because re-rendering on focus
  // change would needlessly re-render the whole table.
  const handleRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const handleHandleKeyDown = useCallback(
    (rowIndex: number) => (e: React.KeyboardEvent<HTMLButtonElement>) => {
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveRow(rowIndex, -1);
        // Refocus the moved row's handle (it's now at rowIndex-1) so
        // the user can chain ArrowUp presses to walk a row up the list.
        // Wait a tick for the cache update to flush into the DOM.
        const target = rowIndex - 1;
        if (target >= 0) {
          requestAnimationFrame(() => {
            handleRefs.current[target]?.focus();
          });
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveRow(rowIndex, 1);
        const target = rowIndex + 1;
        if (target < members.length) {
          requestAnimationFrame(() => {
            handleRefs.current[target]?.focus();
          });
        }
      }
    },
    [members.length, moveRow],
  );

  // ---- render -------------------------------------------------------------

  if (members.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-8 text-center text-sm text-zinc-400">
        No issues in this group yet.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-zinc-900/60 text-xs uppercase tracking-wider text-zinc-400">
          <tr>
            <th scope="col" className="w-10 px-2 py-3" aria-label="Drag handle" />
            <th scope="col" className="w-16 px-4 py-3">
              #
            </th>
            <th scope="col" className="w-28 px-4 py-3">
              Key
            </th>
            <th scope="col" className="px-4 py-3">
              Title
            </th>
            <th scope="col" className="w-40 px-4 py-3">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-900/30">
          {members.map((member, rowIndex) => {
            const issue = member.issue;
            const navigable = !!issue?.id;
            const isDragging = draggingMemberId === member.id;
            // Drop indicator: a thin top border on the row at the drop
            // target index, or a thin bottom border on the last row when
            // the indicator points past the end.
            const showTopIndicator =
              dropTargetIndex === rowIndex && draggingMemberId !== null;
            const showBottomIndicator =
              rowIndex === members.length - 1 &&
              dropTargetIndex === members.length &&
              draggingMemberId !== null;

            return (
              <tr
                key={member.id}
                // `draggable` is the native HTML attribute that gates
                // pointer drag-and-drop. We also check `isPending` in
                // `handleDragStart` (defense-in-depth), but turning the
                // attribute off here is the cleanest signal to the
                // browser: no drag affordance while a reorder is in flight.
                draggable={!reorderMutation.isPending}
                onDragStart={handleDragStart(member.id)}
                onDragOver={handleDragOver(rowIndex)}
                onDragLeave={handleDragLeave(rowIndex)}
                onDrop={handleDrop(rowIndex)}
                onDragEnd={handleDragEnd}
                className={cn(
                  'transition-colors',
                  isDragging ? 'opacity-40' : '',
                  showTopIndicator
                    ? 'border-t-2 border-t-blue-500'
                    : '',
                  showBottomIndicator
                    ? 'border-b-2 border-b-blue-500'
                    : '',
                  navigable
                    ? 'cursor-pointer hover:bg-zinc-800/50'
                    : 'opacity-60',
                )}
                aria-disabled={navigable ? undefined : true}
                onClick={(e) => {
                  // The drag handle is a child <button>; clicks on it
                  // bubble here. Filter so only clicks outside the
                  // handle navigate. Without this, every drag-handle
                  // click would also re-route to the issue page.
                  const target = e.target as HTMLElement;
                  if (target.closest('[data-drag-handle="true"]')) return;
                  if (navigable) onRowClick(issue!.id);
                }}
              >
                <td className="px-2 py-3">
                  <button
                    ref={(el) => {
                      handleRefs.current[rowIndex] = el;
                    }}
                    type="button"
                    data-drag-handle="true"
                    aria-label={`Drag to reorder ${issue?.key ?? 'member'} (or use Up/Down arrows)`}
                    onKeyDown={handleHandleKeyDown(rowIndex)}
                    className={cn(
                      'flex h-6 w-6 cursor-grab items-center justify-center rounded',
                      'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200',
                      'focus:outline-none focus:ring-2 focus:ring-blue-500',
                      'active:cursor-grabbing',
                      reorderMutation.isPending && 'opacity-50',
                    )}
                    disabled={reorderMutation.isPending}
                  >
                    {reorderMutation.isPending && isDragging ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <GripVertical className="h-4 w-4" aria-hidden="true" />
                    )}
                  </button>
                </td>
                <td className="px-4 py-3 text-zinc-500 tabular-nums">
                  {member.position}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-zinc-300">
                  {issue?.key ?? '—'}
                </td>
                <td className="px-4 py-3 text-zinc-100">
                  {issue?.title ?? '(issue unavailable)'}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={issue?.status} compact />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {/* aria-live region for screen readers — announces the inflight
          reorder so non-visual users learn the row moved. The text node
          updates whenever `isPending` flips, which screen readers will
          read aloud. Errors surface through the optional onReorderError
          callback (parent can render a toast). */}
      <div className="sr-only" aria-live="polite" role="status">
        {reorderMutation.isPending ? 'Saving new order…' : ''}
      </div>
    </div>
  );
}
