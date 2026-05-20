'use client';

/**
 * BacklogPage — Studio Backlog list view.
 *
 * Shows BacklogItems with priority badge, status pill, owner, created date.
 * Filter bar synced to URL search params.
 * Click on a card opens the BacklogEditModal.
 * "+ New" button at top opens create modal.
 */

import { useState, Suspense } from 'react';
import { Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useBacklogItems } from '@/hooks/useBacklog';
import { BacklogCard } from './BacklogCard';
import { BacklogFilterBar, useBacklogFilters } from './BacklogFilterBar';
import { BacklogEditModal } from './BacklogEditModal';
import { Skeleton } from '@/components/ui/skeleton';
import type { BacklogItem } from '@/hooks/useBacklog';

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function BacklogCardSkeleton() {
  return (
    <div
      className="px-4 py-3 border space-y-2"
      style={{
        backgroundColor: 'rgba(255,255,255,0.02)',
        borderColor: 'rgba(255,255,255,0.08)',
        borderRadius: '8px',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <Skeleton className="h-4 flex-1 max-w-[60%]" />
        <Skeleton className="h-4 w-14" />
      </div>
      <div className="flex items-center gap-2">
        <Skeleton className="h-4 w-16 rounded-full" />
        <Skeleton className="h-4 w-20 rounded-full" />
      </div>
    </div>
  );
}

// ─── Inner content (needs Suspense for useSearchParams) ───────────────────────

function BacklogContent() {
  const { filters } = useBacklogFilters();
  const { data: items = [], isLoading, isError } = useBacklogItems(filters);
  const [editItem, setEditItem] = useState<BacklogItem | null | undefined>(undefined);

  // undefined = modal closed, null = create mode, BacklogItem = edit mode
  const isModalOpen = editItem !== undefined;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Filter bar */}
      <BacklogFilterBar className="px-4 py-3 border-b border-zinc-800 flex-shrink-0" />

      {/* List */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <BacklogCardSkeleton key={i} />
            ))}
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center py-16 text-zinc-500 text-sm">
            Failed to load backlog items — backend may not be running yet
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center mb-3">
              <span className="text-zinc-500 text-xl" aria-hidden="true">≡</span>
            </div>
            <p className="text-zinc-500 text-sm">No backlog items</p>
            <p className="text-zinc-600 text-xs mt-1">
              Create your first item or start a Studio conversation
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <BacklogCard
                key={item.id}
                item={item}
                onEdit={setEditItem}
              />
            ))}
          </div>
        )}
      </div>

      {/* Edit / Create modal */}
      <BacklogEditModal
        item={editItem ?? null}
        isOpen={isModalOpen}
        onClose={() => setEditItem(undefined)}
      />
    </div>
  );
}

// ─── BacklogPage ──────────────────────────────────────────────────────────────

export function BacklogPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  return (
    <div className="flex flex-col h-full min-h-0 bg-zinc-950">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <h1 className="text-base font-semibold text-zinc-100">Backlog</h1>
        <button
          onClick={() => setIsCreateOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm font-medium transition-colors"
          aria-label="Create new backlog item"
        >
          <Plus className="w-4 h-4" />
          New
        </button>
      </div>

      {/* Backlog content — Suspense needed for useSearchParams */}
      <Suspense
        fallback={
          <div className="flex-1 px-4 py-4 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  'h-16 rounded-lg animate-pulse',
                )}
                style={{ backgroundColor: 'rgba(255,255,255,0.04)' }}
              />
            ))}
          </div>
        }
      >
        <BacklogContent />
      </Suspense>

      {/* Create modal (top-level, outside Suspense) */}
      <BacklogEditModal
        item={null}
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
      />
    </div>
  );
}
