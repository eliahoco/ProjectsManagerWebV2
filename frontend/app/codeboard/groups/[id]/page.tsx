'use client';

/**
 * Group Detail Page — `/codeboard/groups/[id]`
 *
 * CB-2014 (TASK) → CB-2013 (STORY 5.2 — Group detail page)
 * CB-2015 (TASK) → drag-to-reorder member list (uses position field)
 *                 → CB-2009 (EPIC 5 — Groups frontend)
 *                 → CB-1955 (FEATURE — Issue Correlation & Grouping).
 *
 * Scope:
 *   * `useGroup(id)` data fetch + loading / error / not-found states.
 *   * Header: title, description, dominant-status pill + completion percent.
 *   * Member table: drag-to-reorder + row click → issue detail. The
 *     `GroupMemberDraggableTable` component owns the drag UX and
 *     dispatches the `useReorderGroupMembers` mutation; this page hosts
 *     it and surfaces reorder failures via an inline alert (the hook's
 *     optimistic rollback already restores the visible order).
 *
 * Out of scope (sibling tasks own these):
 *   * Edit / delete / member add+remove — separate stories under EPIC 5.
 *
 * CB-2016 implemented inline below: `AggregateHeader` now also renders a
 * segmented horizontal progress bar with one slice per non-zero status,
 * coloured to match the kanban columns, plus per-segment hover tooltips
 * showing the count + percentage. Falls back to the minimal pill+percent
 * line for empty groups.
 *
 * Security notes:
 *   * `id` from `useParams()` is user-controlled. It's only ever interpolated
 *     into the API URL via `encodeURIComponent` (in the hook), never into
 *     `dangerouslySetInnerHTML` and never re-emitted into the DOM. React
 *     escapes its children by default; backend `description`, member titles,
 *     and aggregate keys all render through React text nodes.
 *   * No auth header — this app currently has no per-project auth at the
 *     network boundary; matches the pattern used by every other CodeBoard
 *     page. If auth lands later, the hook's `apiFetch` wrapper is the
 *     single chokepoint to upgrade.
 */

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AlertCircle, ArrowLeft } from 'lucide-react';
import { useGroup } from '@/hooks/useGroups';
import { GroupMemberDraggableTable } from '@/components/codeboard/GroupMemberDraggableTable';
import { STATUS_COLUMNS } from '@/types/codeboard';
import type { GroupAggregateStatus } from '@/types/codeboard';
import { cn } from '@/lib/utils';

// Resolve a status string to its column config (label + color). Backend
// `dominantStatus` and member `issue.status` are typed as plain strings —
// not `IssueStatus` — because legacy rows can carry statuses outside the
// current enum. `find` returns `undefined` on miss; the caller renders a
// neutral fallback so an unknown status surfaces as text instead of a
// crash.
function statusConfig(status: string | null | undefined) {
  if (!status) return null;
  // String compare; no `as IssueStatus` cast — backend explicitly may return
  // legacy values outside the enum (see `GroupAggregateStatus` docstring).
  return STATUS_COLUMNS.find((s) => s.status === status) ?? null;
}

interface StatusBadgeProps {
  status: string | null | undefined;
  // `compact` shrinks padding for inline use inside table rows.
  compact?: boolean;
}

function StatusBadge({ status, compact = false }: StatusBadgeProps) {
  const cfg = statusConfig(status);
  // Unknown status → render the raw string in a neutral pill so the row
  // remains identifiable; never blank, never a crash.
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

interface AggregateHeaderProps {
  aggregate: GroupAggregateStatus;
  memberCount: number;
}

function AggregateHeader({ aggregate, memberCount }: AggregateHeaderProps) {
  // Empty group (memberCount === 0) reads as "No members yet". The backend
  // would return completionPercent=0 / dominantStatus=null in that case;
  // surfacing that explicitly avoids a misleading "0% complete" pill on a
  // group that has nothing to be complete *of*.
  if (memberCount === 0) {
    return (
      <div className="flex items-center gap-3 text-sm text-zinc-400">
        <span>No members yet</span>
      </div>
    );
  }

  // `completionPercent` arrives as a float 0–100 from the backend (clamped
  // server-side via Pydantic ge/le). Round for display so we don't render
  // "33.33333…%". Math.round hits the nearest integer; trailing-decimal
  // precision isn't useful at this size.
  const percent = Math.round(aggregate.completionPercent);

  // CB-2016: build segments from statusBreakdown. Iterate STATUS_COLUMNS to
  // get a stable ordering matching the kanban (BACKLOG → DONE), then fall
  // through to any unknown statuses appended at the end. Segments with zero
  // count are dropped (no zero-width slivers in the bar).
  const total = memberCount;
  const knownStatuses = new Set<string>(STATUS_COLUMNS.map((s) => s.status));
  const orderedSegments = [
    ...STATUS_COLUMNS.map((col) => ({
      status: col.status,
      label: col.label,
      color: col.color,
      count: aggregate.statusBreakdown[col.status] ?? 0,
    })),
    // Surface any statuses the backend reported that aren't in STATUS_COLUMNS
    // (legacy enum values). They render with a neutral colour so the bar
    // doesn't silently lose member counts.
    ...Object.entries(aggregate.statusBreakdown)
      .filter(([s]) => !knownStatuses.has(s))
      .map(([status, count]) => ({
        status,
        label: status,
        color: 'bg-zinc-600',
        count,
      })),
  ].filter((s) => s.count > 0);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <StatusBadge status={aggregate.dominantStatus} />
        <span className="text-zinc-300">{percent}% complete</span>
        <span className="text-zinc-500">·</span>
        <span className="text-zinc-400">
          {total} {total === 1 ? 'member' : 'members'}
        </span>
      </div>

      {/* CB-2016 — segmented status breakdown bar. Tailwind flex with each
          segment's flex-grow proportional to its count. Width-driven via
          flex rather than percent strings to avoid sub-pixel rounding holes
          between segments. role=img + aria-label gives screen readers the
          summary; the per-segment `title` attribute provides a native hover
          tooltip without a JS popover dependency. */}
      <div
        role="img"
        aria-label={
          orderedSegments
            .map((s) => `${s.count} ${s.label}`)
            .join(', ') || 'No member status data'
        }
        className="flex h-2 w-full overflow-hidden rounded-full bg-zinc-800"
      >
        {orderedSegments.map((seg) => (
          <div
            key={seg.status}
            className={cn('h-full transition-[flex-grow] duration-200', seg.color)}
            style={{ flexGrow: seg.count }}
            title={`${seg.label}: ${seg.count} (${
              total > 0 ? Math.round((seg.count / total) * 100) : 0
            }%)`}
          />
        ))}
      </div>
    </div>
  );
}

export default function GroupDetailPage() {
  const params = useParams();
  const router = useRouter();

  // `params.id` is `string | string[] | undefined` per Next.js typing.
  // The route is `[id]` (not `[...id]`), so the runtime value is always a
  // string when present — but defensively narrow to null on anything else
  // so the loading/error states render instead of crashing on a framework
  // contract change.
  const groupId: string | null =
    typeof params?.id === 'string' ? params.id : null;

  const { data: group, isLoading, error } = useGroup(groupId);

  // Surface CB-2015 reorder failures inline. The hook's optimistic
  // rollback already restores the visible order on failure; this just
  // tells the user *why* — `APIError` from `apiFetch` carries `message`
  // and `details.{missing, extra}` for the 400 set-mismatch case. We
  // keep one slot (latest error wins) to avoid a stack of stale toasts
  // after a flaky network spell.
  const [reorderError, setReorderError] = useState<string | null>(null);

  const handleMemberClick = (issueId: string) => {
    router.push(`/codeboard/issue/${encodeURIComponent(issueId)}`);
  };

  // Loading skeleton mirrors `app/codeboard/issue/[id]/page.tsx` so the
  // visual shape is consistent across detail pages.
  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="mx-auto max-w-5xl">
          <div className="animate-pulse space-y-4">
            <div className="h-4 w-32 rounded bg-zinc-700" />
            <div className="h-8 w-1/3 rounded bg-zinc-700" />
            <div className="h-4 w-2/3 rounded bg-zinc-700" />
            <div className="h-32 rounded bg-zinc-700" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !group) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="mx-auto max-w-5xl py-12 text-center">
          <h1 className="text-2xl font-bold text-zinc-100">
            {error ? 'Error loading group' : 'Group not found'}
          </h1>
          <p className="mt-2 text-zinc-400">
            {error?.message ?? 'The group you are looking for does not exist.'}
          </p>
          <button
            type="button"
            onClick={() => router.push('/codeboard')}
            className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          >
            Back to CodeBoard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-900 p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <button
          type="button"
          onClick={() => router.push('/codeboard')}
          className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-200"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to CodeBoard
        </button>

        <header className="space-y-3">
          <h1 className="text-3xl font-bold text-zinc-100">{group.title}</h1>
          {group.description && (
            <p className="whitespace-pre-wrap text-zinc-300">
              {group.description}
            </p>
          )}
          <AggregateHeader
            aggregate={group.aggregateStatus}
            memberCount={group.members.length}
          />
        </header>

        <section aria-label="Group members" className="space-y-3">
          {reorderError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-red-700/50 bg-red-900/20 px-4 py-2 text-sm text-red-200"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
              <div className="flex-1">
                <span className="font-medium">Could not save new order.</span>{' '}
                {reorderError}
              </div>
              <button
                type="button"
                onClick={() => setReorderError(null)}
                className="text-xs text-red-300 hover:text-red-100"
                aria-label="Dismiss error"
              >
                Dismiss
              </button>
            </div>
          )}
          <GroupMemberDraggableTable
            groupId={group.id}
            members={group.members}
            onRowClick={handleMemberClick}
            onReorderSuccess={() => setReorderError(null)}
            onReorderError={(err) => setReorderError(err.message)}
          />
        </section>
      </div>
    </div>
  );
}
