'use client';

/**
 * Skeleton Loading Components
 * Provides visual placeholders while content is loading
 */

import { cn } from '@/lib/utils';

interface SkeletonProps {
  className?: string;
}

/**
 * Base skeleton component - a pulsing placeholder
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-zinc-800',
        className
      )}
    />
  );
}

/**
 * Skeleton for text lines
 */
export function SkeletonText({ className, lines = 1 }: SkeletonProps & { lines?: number }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn(
            'h-4',
            i === lines - 1 ? 'w-3/4' : 'w-full'
          )}
        />
      ))}
    </div>
  );
}

/**
 * Skeleton for an issue card
 */
export function SkeletonIssueCard({ className }: SkeletonProps) {
  return (
    <div className={cn('p-3 bg-zinc-800/50 rounded-lg border border-zinc-700 space-y-2', className)}>
      <div className="flex items-center gap-2">
        <Skeleton className="w-5 h-5 rounded" />
        <Skeleton className="w-16 h-4" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
      <div className="flex items-center gap-2 mt-2">
        <Skeleton className="w-12 h-5 rounded" />
        <Skeleton className="w-16 h-5 rounded" />
      </div>
    </div>
  );
}

/**
 * Skeleton for a kanban column
 */
export function SkeletonKanbanColumn({ className, cardCount = 3 }: SkeletonProps & { cardCount?: number }) {
  return (
    <div className={cn('w-80 flex-shrink-0 space-y-3', className)}>
      {/* Column header */}
      <div className="flex items-center gap-2 px-1">
        <Skeleton className="w-3 h-3 rounded-full" />
        <Skeleton className="w-20 h-5" />
        <Skeleton className="w-6 h-5 rounded-full" />
      </div>
      {/* Cards */}
      <div className="space-y-2 p-2 bg-zinc-900/50 rounded-lg border border-zinc-800">
        {Array.from({ length: cardCount }).map((_, i) => (
          <SkeletonIssueCard key={i} />
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton for the full kanban board
 */
export function SkeletonKanbanBoard({ className }: SkeletonProps) {
  return (
    <div className={cn('flex gap-4 overflow-x-auto pb-4 h-full', className)}>
      <SkeletonKanbanColumn cardCount={3} />
      <SkeletonKanbanColumn cardCount={2} />
      <SkeletonKanbanColumn cardCount={4} />
      <SkeletonKanbanColumn cardCount={2} />
      <SkeletonKanbanColumn cardCount={1} />
    </div>
  );
}

/**
 * Skeleton for a list row
 */
export function SkeletonListRow({ className }: SkeletonProps) {
  return (
    <div className={cn('flex items-center gap-3 p-3 border-b border-zinc-800', className)}>
      <Skeleton className="w-5 h-5 rounded" />
      <Skeleton className="w-16 h-4" />
      <Skeleton className="flex-1 h-4" />
      <Skeleton className="w-16 h-5 rounded" />
      <Skeleton className="w-16 h-5 rounded" />
    </div>
  );
}

/**
 * Skeleton for a list view
 */
export function SkeletonListView({ className, rowCount = 10 }: SkeletonProps & { rowCount?: number }) {
  return (
    <div className={cn('bg-zinc-900/50 rounded-lg border border-zinc-800', className)}>
      {Array.from({ length: rowCount }).map((_, i) => (
        <SkeletonListRow key={i} />
      ))}
    </div>
  );
}
