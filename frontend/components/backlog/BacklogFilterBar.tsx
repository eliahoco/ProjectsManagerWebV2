'use client';

/**
 * BacklogFilterBar — status / priority / search filters.
 *
 * Filter state is URL-synced via useSearchParams + router.replace so it
 * survives refresh and is bookmarkable / shareable.
 */

import { useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { BacklogFilters, BacklogPriority, BacklogStatus } from '@/hooks/useBacklog';

const STATUSES: Array<{ value: BacklogStatus; label: string }> = [
  { value: 'DRAFT',       label: 'Draft' },
  { value: 'READY',       label: 'Ready' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'DONE',        label: 'Done' },
  { value: 'CANCELLED',   label: 'Cancelled' },
];

const PRIORITIES: Array<{ value: BacklogPriority; label: string }> = [
  { value: 'CRITICAL', label: 'Critical' },
  { value: 'HIGH',     label: 'High' },
  { value: 'MEDIUM',   label: 'Medium' },
  { value: 'LOW',      label: 'Low' },
];

function FilterPill({
  label,
  isActive,
  onToggle,
}: {
  label: string;
  isActive: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        'inline-flex items-center gap-1 px-3 py-1 text-xs font-medium transition-colors',
        'rounded-full border',
        isActive
          ? 'bg-cyan-900/50 text-cyan-200 border-cyan-700/60'
          : 'bg-zinc-800/60 text-zinc-400 border-zinc-700/60 hover:text-zinc-200 hover:border-zinc-600',
      )}
    >
      {label}
      {isActive && <X className="w-2.5 h-2.5" />}
    </button>
  );
}

export function useBacklogFilters(): {
  filters: BacklogFilters;
  setStatus: (s: BacklogStatus | undefined) => void;
  setPriority: (p: BacklogPriority | undefined) => void;
  setSearch: (q: string) => void;
  clearAll: () => void;
} {
  const router = useRouter();
  const searchParams = useSearchParams();

  const updateParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      Object.entries(updates).forEach(([key, val]) => {
        if (val) params.set(key, val);
        else params.delete(key);
      });
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const status = searchParams.get('status') as BacklogStatus | null;
  const priority = searchParams.get('priority') as BacklogPriority | null;
  const search = searchParams.get('search') ?? '';

  return {
    filters: {
      status: status ?? undefined,
      priority: priority ?? undefined,
      search: search || undefined,
    },
    setStatus: (s) => updateParams({ status: s }),
    setPriority: (p) => updateParams({ priority: p }),
    setSearch: (q) => updateParams({ search: q || undefined }),
    clearAll: () => updateParams({ status: undefined, priority: undefined, search: undefined }),
  };
}

interface BacklogFilterBarProps {
  onSearch?: (q: string) => void;
  className?: string;
}

export function BacklogFilterBar({ className }: BacklogFilterBarProps) {
  const { filters, setStatus, setPriority, setSearch, clearAll } = useBacklogFilters();
  const hasActiveFilters = !!(filters.status || filters.priority || filters.search);

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
        <input
          type="text"
          placeholder="Search…"
          value={filters.search ?? ''}
          onChange={(e) => setSearch(e.target.value)}
          className={cn(
            'pl-8 pr-3 py-1.5 text-sm bg-zinc-800/60 border border-zinc-700',
            'rounded-full text-zinc-200 placeholder:text-zinc-500',
            'focus:outline-none focus:border-cyan-500 w-40 transition-colors',
          )}
          aria-label="Search backlog items"
        />
      </div>

      {/* Divider */}
      <div className="w-px h-4 bg-zinc-700" aria-hidden="true" />

      {/* Status filters */}
      {STATUSES.map((s) => (
        <FilterPill
          key={s.value}
          label={s.label}
          isActive={filters.status === s.value}
          onToggle={() => setStatus(filters.status === s.value ? undefined : s.value)}
        />
      ))}

      {/* Divider */}
      <div className="w-px h-4 bg-zinc-700" aria-hidden="true" />

      {/* Priority filters */}
      {PRIORITIES.map((p) => (
        <FilterPill
          key={p.value}
          label={p.label}
          isActive={filters.priority === p.value}
          onToggle={() => setPriority(filters.priority === p.value ? undefined : p.value)}
        />
      ))}

      {/* Clear all */}
      {hasActiveFilters && (
        <button
          onClick={clearAll}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors ml-1"
          aria-label="Clear all filters"
        >
          Clear all
        </button>
      )}
    </div>
  );
}
