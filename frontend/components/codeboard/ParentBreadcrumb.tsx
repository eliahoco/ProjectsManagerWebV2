'use client';

/**
 * ParentBreadcrumb
 *
 * Extracted as part of CB-2684 / CB-2690.
 *
 * Walks up the parent chain from a given issueId (up to MAX_DEPTH levels)
 * and renders a linear-style breadcrumb:
 *
 *   🚀 CB-100 Feature Title / ⚡ CB-200 Epic Title / 📖 CB-300 Story Title
 *
 * Each crumb is a clickable link that navigates to
 * /codeboard/issues/<id>.
 *
 * Design decisions:
 *   - Uses cascaded `useIssue()` React Query hooks — each level is a
 *     separate query so the cache is shared with the rest of the app.
 *   - Cycle-detection via a `Set<string>` of visited ids prevents infinite
 *     loops if the DB ever contains a parent cycle.
 *   - Max depth of 5 prevents excessive network fan-out.
 *   - Typography: Inter variable weight 510 (matches Linear UI conventions).
 *
 * Props:
 *   issueId  — the child issue whose ancestor chain to display.
 *              The component resolves ancestors bottom-up via useIssue calls.
 */

import { useMemo } from 'react';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { useIssue } from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';
import { ISSUE_TYPES } from '@/types/codeboard';
import type { Issue } from '@/types/codeboard';

// ─── Props ────────────────────────────────────────────────────────────────────

export interface ParentBreadcrumbProps {
  /** The child issue ID whose ancestor chain we render. */
  issueId: string;
  /** Additional class names for the outer wrapper. */
  className?: string;
}

// ─── Flat walker ─────────────────────────────────────────────────────────────

/**
 * Walking the chain imperatively at render time is tricky with hooks (cannot
 * call conditionally), so we use five fixed hook calls — one per possible
 * ancestor level — and trim the result.  The number of calls is always the
 * same regardless of the actual chain depth (max 5).
 */
function useParentChain(issueId: string): {
  ancestors: Issue[];
  isLoading: boolean;
} {
  // Level 0 — direct parent of the target issue
  const { data: l0Issue } = useIssue(issueId);
  const l0ParentId = l0Issue?.parentId ?? null;

  // Level 1
  const { data: l1Issue, isLoading: l1Loading } = useIssue(l0ParentId);
  const l1ParentId = l1Issue?.parentId ?? null;

  // Level 2
  const { data: l2Issue, isLoading: l2Loading } = useIssue(l1ParentId);
  const l2ParentId = l2Issue?.parentId ?? null;

  // Level 3
  const { data: l3Issue, isLoading: l3Loading } = useIssue(l2ParentId);
  const l3ParentId = l3Issue?.parentId ?? null;

  // Level 4
  const { data: l4Issue, isLoading: l4Loading } = useIssue(l3ParentId);

  const isLoading = l1Loading || l2Loading || l3Loading || l4Loading;

  const ancestors = useMemo(() => {
    const chain: Issue[] = [];
    const visited = new Set<string>();

    // Build bottom-up first, then reverse so we get root → leaf order
    const raw = [l1Issue, l2Issue, l3Issue, l4Issue].filter(Boolean) as Issue[];

    for (const issue of raw) {
      if (visited.has(issue.id)) break; // cycle guard
      visited.add(issue.id);
      chain.push(issue);
    }

    // chain is [direct-parent, grandparent, ...] — reverse for display
    return chain.reverse();
  }, [l1Issue, l2Issue, l3Issue, l4Issue]);

  return { ancestors, isLoading };
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ParentBreadcrumb({ issueId, className }: ParentBreadcrumbProps) {
  const { ancestors, isLoading } = useParentChain(issueId);

  if (isLoading && ancestors.length === 0) {
    return (
      <div
        className={cn('flex items-center gap-1.5 animate-pulse', className)}
        aria-label="Loading breadcrumb"
      >
        <div className="h-4 w-40 bg-zinc-700 rounded" />
      </div>
    );
  }

  if (ancestors.length === 0) return null;

  return (
    <nav
      aria-label="Parent hierarchy"
      className={cn('flex items-center gap-1 flex-wrap', className)}
    >
      {ancestors.map((issue, idx) => {
        const typeConfig = ISSUE_TYPES.find((t) => t.type === issue.type);

        return (
          <span key={issue.id} className="flex items-center gap-1">
            {/* Separator (not before the first crumb) */}
            {idx > 0 && <ChevronRight className="w-3 h-3 text-zinc-600 shrink-0" />}

            {/* Clickable crumb */}
            <Link
              href={`/codeboard/issues/${issue.id}`}
              className={cn(
                'flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors',
                'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60',
                // Inter variable weight 510 — matches Linear-style header breadcrumbs
                'font-[Inter_var] tracking-tight',
              )}
              style={{ fontVariationSettings: "'wght' 510" }}
              title={`${issue.type}: ${issue.title}`}
            >
              {/* Type icon */}
              {typeConfig && (
                <span className="text-xs leading-none" aria-hidden>
                  {typeConfig.icon}
                </span>
              )}

              {/* Key */}
              <span className="font-mono text-[11px] leading-none text-zinc-500">
                {issue.key}
              </span>

              {/* Title (truncated) */}
              <span
                className="text-xs leading-none max-w-[160px] truncate"
                title={issue.title}
              >
                {issue.title}
              </span>
            </Link>
          </span>
        );
      })}
    </nav>
  );
}
