'use client';

/**
 * LinkedIssuesPanel — typed issue relations rendered as a flat grouped list.
 *
 * CB-1998 (FEATURE CB-1955 → EPIC CB-1996 → STORY CB-1997).
 *
 * Design rationale (Reader's UI/UX research): Miller's Law — flat grouped
 * list, NOT a graph. One section per relation type, ordered by user
 * salience (BLOCKS first because it gates work). Per-row UI: direction
 * arrow + status pill, so the relationship reads at a glance.
 *
 * Data contract:
 *  - Consumes IssueRelationsListResponse (CB-1973). Backend writes a
 *    primary row + companion inverse row per link, so every relation
 *    surfaces in BOTH outbound and inbound lists. We render outbound only —
 *    each linkType is already from the issue's perspective on that side,
 *    so dedup is implicit (no need to merge inbound).
 *
 * Sibling tasks (NOT in this CB-1998 scope, but the API + hooks below
 * are designed to compose with them without a rewrite):
 *  - CB-1999: refine direction arrow + pill styling per row
 *  - CB-2000: progressive disclosure — 5 visible per group + "+ N more"
 *  - CB-2001: empty-state ghost CTA centered
 */

import { useCallback, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowLeftRight, Plus } from 'lucide-react';
import type {
  IssueLinkResponse,
  IssueRelationsListResponse,
  IssueSummary,
  LinkType,
} from '@/types/codeboard';
import { cn } from '@/lib/utils';

interface LinkedIssuesPanelProps {
  /** Current issue id — needed to choose which side of each row is the "other" issue. */
  issueId: string;
  /** Relations payload from useIssueRelations(). */
  relations: IssueRelationsListResponse | undefined;
  /** Loading flag from the React Query hook. */
  isLoading?: boolean;
  /** Click handler for navigating to a linked issue. */
  onIssueClick?: (issueId: string) => void;
  /**
   * CB-2001 — Click handler for the "+ Add relation" ghost CTA in the
   * empty state. When omitted the button is not rendered (the empty
   * state degrades to a plain "No linked issues" hint), so the panel
   * stays usable in read-only contexts (e.g. embedded previews) where
   * relation creation isn't wired up yet (CB-2002+).
   */
  onAddRelation?: () => void;
}

// Display order — most actionable types surface first. Block-graph rows
// gate work, so they outrank duplicates and informational relates_to.
const LINK_TYPE_ORDER: LinkType[] = [
  'IS_BLOCKED_BY',
  'BLOCKS',
  'CAUSED_BY',
  'CAUSES',
  'DUPLICATES',
  'IS_DUPLICATED_BY',
  'RELATES_TO',
];

// Hard upper bound on rendered rows. Bounds DoM size against contract
// drift / compromise. CB-2000 ships progressive disclosure (5 visible +
// "+N more"); this cap is a *safety floor*, not the UX behavior.
const RENDER_ROW_CAP = 500;

// CB-2000 — Miller's Law / Reader p. 9. Default-collapsed cap per group.
// Click "+ N more" expands the section inline (component-local state).
const VISIBLE_PER_GROUP = 5;

const LINK_TYPE_LABELS: Record<LinkType, string> = {
  RELATES_TO: 'Relates to',
  DUPLICATES: 'Duplicates',
  IS_DUPLICATED_BY: 'Duplicated by',
  BLOCKS: 'Blocks',
  IS_BLOCKED_BY: 'Blocked by',
  CAUSES: 'Causes',
  CAUSED_BY: 'Caused by',
};

// Direction semantics from the issue's POV:
//   out = this issue acts on the other (BLOCKS → ↑ outgoing)
//   in  = the other acts on this issue (IS_BLOCKED_BY → ↓ incoming)
//   sym = symmetric / non-directional (RELATES_TO → ↔)
const LINK_TYPE_DIRECTION: Record<LinkType, 'out' | 'in' | 'sym'> = {
  RELATES_TO: 'sym',
  DUPLICATES: 'out',
  IS_DUPLICATED_BY: 'in',
  BLOCKS: 'out',
  IS_BLOCKED_BY: 'in',
  CAUSES: 'out',
  CAUSED_BY: 'in',
};

// Status pill palette mirrors LinkedItems / KanbanColumn — single source of
// truth for status colors lives in those existing components; duplicating
// the literal here keeps this component self-contained for CB-1998 and the
// pill styling refinement in CB-1999 will pull from the shared constant
// once that story consolidates them.
function statusPillClass(status: string): string {
  switch (status) {
    case 'DONE':
      return 'bg-green-900/30 text-green-400';
    case 'IN_PROGRESS':
      return 'bg-blue-900/30 text-blue-400';
    case 'IN_REVIEW':
      return 'bg-purple-900/30 text-purple-400';
    case 'COMPLETED_WAITING_QA':
      return 'bg-orange-900/30 text-orange-400';
    case 'TODO':
      return 'bg-yellow-900/30 text-yellow-400';
    case 'CANCELLED':
      return 'bg-red-900/30 text-red-400';
    case 'BACKLOG':
    default:
      return 'bg-zinc-700 text-zinc-400';
  }
}

function DirectionArrow({ linkType }: { linkType: LinkType }) {
  const dir = LINK_TYPE_DIRECTION[linkType];
  // aria-label gives screen readers the relationship sense; the arrow alone
  // is not meaningful without the section heading (a11y).
  if (dir === 'out') {
    return <ArrowUp className="h-4 w-4 text-zinc-400 shrink-0" aria-label="Outgoing" />;
  }
  if (dir === 'in') {
    return <ArrowDown className="h-4 w-4 text-zinc-400 shrink-0" aria-label="Incoming" />;
  }
  return <ArrowLeftRight className="h-4 w-4 text-zinc-400 shrink-0" aria-label="Bidirectional" />;
}

interface RelationRowProps {
  link: IssueLinkResponse;
  issueId: string;
  onIssueClick?: (issueId: string) => void;
}

function RelationRow({ link, issueId, onIssueClick }: RelationRowProps) {
  // The "other" end is whichever side is NOT the current issue. We render
  // outbound rows only (see panel doc), so toIssue is normally the other end —
  // but defensively fall back to fromIssue if a future caller passes inbound
  // rows in. Defensive because backend can return either side and we don't
  // want a blank row on a contract drift.
  const other: IssueSummary | undefined =
    link.toIssueId === issueId ? link.fromIssue : link.toIssue;

  // No summary embedded → row is unrenderable. Surface a minimal id-only row
  // so the user knows the link exists, instead of silently dropping it.
  if (!other) {
    return (
      <div className="flex items-center gap-2 p-2 rounded bg-zinc-800/50 text-sm text-zinc-500">
        <DirectionArrow linkType={link.linkType} />
        <span className="font-mono text-xs">
          {link.toIssueId === issueId ? link.fromIssueId : link.toIssueId}
        </span>
        <span className="text-xs italic ml-auto">summary unavailable</span>
      </div>
    );
  }

  // Capture the handler in a local so we don't need a non-null assertion
  // inside the JSX — also keeps the click + key paths reading from the
  // same reference.
  const handler = onIssueClick;
  const interactive = !!handler;
  // Defensive coercion: backend contract is `status: string`, but a legacy
  // row could ship null/undefined and crash the renderer on .replace.
  const statusLabel = String(other.status ?? '').replace(/_/g, ' ');
  return (
    <div
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={handler ? () => handler(other.id) : undefined}
      onKeyDown={
        handler
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handler(other.id);
              }
            }
          : undefined
      }
      className={cn(
        'flex items-center gap-2 p-2 rounded bg-zinc-800/50 transition-colors',
        interactive &&
          'cursor-pointer hover:bg-zinc-800 focus-visible:bg-zinc-800 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500'
      )}
    >
      <DirectionArrow linkType={link.linkType} />
      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-100 shrink-0">
        {other.key}
      </span>
      <span className="text-sm truncate flex-1 text-zinc-200">{other.title}</span>
      <span className={cn('text-xs px-2 py-0.5 rounded shrink-0', statusPillClass(statusLabel ? other.status : 'BACKLOG'))}>
        {statusLabel || 'UNKNOWN'}
      </span>
    </div>
  );
}

export function LinkedIssuesPanel({
  issueId,
  relations,
  isLoading,
  onIssueClick,
  onAddRelation,
}: LinkedIssuesPanelProps) {
  // Group outbound rows by linkType. Outbound only — every relation has a
  // companion inverse row, so picking one side is enough and avoids
  // double-rendering (see panel doc). useMemo so the grouping doesn't
  // recompute on every parent rerender unrelated to relation data.
  //
  // Self-links (fromIssueId === toIssueId) are dropped at the boundary —
  // they'd render a row pointing at the current issue, which is noise.
  // The backend rejects self-links at create time (CB-1971), but we
  // filter here defensively so legacy rows can't bleed into the UI.
  //
  // Hard render cap (RENDER_ROW_CAP) bounds DoM size so a contract drift
  // (or a malicious/compromised backend) can't freeze the renderer with
  // tens of thousands of rows. Real-world projects rarely cross 100;
  // CB-2000 will add the proper progressive-disclosure UX (5 + N more).
  const { grouped, truncated } = useMemo<{
    grouped: Partial<Record<LinkType, IssueLinkResponse[]>>;
    truncated: boolean;
  }>(() => {
    const acc: Partial<Record<LinkType, IssueLinkResponse[]>> = {};
    let count = 0;
    let didTruncate = false;
    if (!relations) return { grouped: acc, truncated: false };
    for (const link of relations.outbound) {
      if (link.fromIssueId === link.toIssueId) continue;
      if (count >= RENDER_ROW_CAP) {
        didTruncate = true;
        break;
      }
      const list = acc[link.linkType] ?? [];
      list.push(link);
      acc[link.linkType] = list;
      count++;
    }
    return { grouped: acc, truncated: didTruncate };
  }, [relations]);

  // CB-2000 — per-group expansion state. Local-only (does NOT persist
  // across remounts / tab switches): the user's mental model is "I'm
  // exploring this issue right now"; carrying state across detail-modal
  // navigations would surprise more often than help. Set keyed by
  // LinkType so each section toggles independently.
  const [expanded, setExpanded] = useState<Set<LinkType>>(new Set());
  const toggleExpanded = useCallback((linkType: LinkType) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(linkType)) next.delete(linkType);
      else next.add(linkType);
      return next;
    });
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-2" aria-busy="true">
        <div className="h-4 w-24 bg-zinc-800 rounded animate-pulse" />
        <div className="h-9 bg-zinc-800 rounded animate-pulse" />
        <div className="h-9 bg-zinc-800 rounded animate-pulse" />
      </div>
    );
  }

  const sections = LINK_TYPE_ORDER.filter((t) => (grouped[t]?.length ?? 0) > 0);

  // CB-2001 — Empty state. Reader p. 7 rule: a panel with zero rows must
  // not render its column headings (they imply structure that isn't
  // there). Section headings already only render inside the populated
  // branch below, so the headings stay hidden here. We surface a single
  // centered hint + ghost CTA so the user gets both an explanation
  // ("nothing here") and the next action ("add one") in one glance.
  //
  // The "+ Add relation" button is conditional on a handler — when the
  // panel is rendered in a read-only context (e.g. a preview tile, or
  // before CB-2002 wires the create dialog), we degrade gracefully to a
  // plain hint rather than rendering a dead button that goes nowhere.
  if (sections.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-2 py-6 text-sm text-zinc-500"
        role="status"
        aria-live="polite"
      >
        <span>No linked issues</span>
        {onAddRelation && (
          <button
            type="button"
            onClick={onAddRelation}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded border border-zinc-700 bg-transparent text-zinc-300 hover:border-zinc-500 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Add relation</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {sections.map((linkType) => {
        const rows = grouped[linkType]!;
        const isExpanded = expanded.has(linkType);
        const overflow = Math.max(0, rows.length - VISIBLE_PER_GROUP);
        // Slice when collapsed; render full list when expanded. The cap
        // preserves the section heading count (rows.length) so the user
        // always sees how many relations exist, not how many are visible.
        const visibleRows = isExpanded ? rows : rows.slice(0, VISIBLE_PER_GROUP);
        return (
          <section key={linkType} aria-label={LINK_TYPE_LABELS[linkType]}>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-400 mb-2">
              {LINK_TYPE_LABELS[linkType]} ({rows.length})
            </h4>
            <div id={`linked-section-${issueId}-${linkType}`} className="space-y-1">
              {visibleRows.map((link) => (
                <RelationRow
                  key={link.id}
                  link={link}
                  issueId={issueId}
                  onIssueClick={onIssueClick}
                />
              ))}
            </div>
            {overflow > 0 && (
              <button
                type="button"
                onClick={() => toggleExpanded(linkType)}
                aria-expanded={isExpanded}
                aria-controls={`linked-section-${issueId}-${linkType}`}
                className="mt-1 text-xs text-zinc-400 hover:text-zinc-200 focus-visible:text-zinc-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500 rounded px-1 py-0.5 transition-colors"
              >
                {isExpanded ? 'Show less' : `+ ${overflow} more`}
              </button>
            )}
          </section>
        );
      })}
      {truncated && (
        <p
          className="text-xs italic text-zinc-500 text-center pt-2"
          role="status"
        >
          Showing first {RENDER_ROW_CAP} relations · refine your view
        </p>
      )}
    </div>
  );
}

export default LinkedIssuesPanel;
