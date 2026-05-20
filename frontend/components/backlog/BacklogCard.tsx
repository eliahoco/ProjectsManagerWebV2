'use client';

/**
 * BacklogCard — Linear-style card for a backlog item.
 *
 * Styling:
 *   bg: rgba(255,255,255,0.02)
 *   radius: 8px
 *   border: rgba(255,255,255,0.08)
 *
 * Click opens the edit modal via onEdit callback.
 */

import { cn } from '@/lib/utils';
import { formatRelativeTime } from '@/lib/utils';
import type { BacklogItem } from '@/hooks/useBacklog';

// ─── Priority badge ───────────────────────────────────────────────────────────

const PRIORITY_STYLES: Record<string, { label: string; className: string }> = {
  CRITICAL: { label: 'Critical', className: 'bg-red-900/50 text-red-300 border-red-700/50' },
  HIGH:     { label: 'High',     className: 'bg-orange-900/50 text-orange-300 border-orange-700/50' },
  MEDIUM:   { label: 'Medium',   className: 'bg-yellow-900/50 text-yellow-300 border-yellow-700/50' },
  LOW:      { label: 'Low',      className: 'bg-zinc-800 text-zinc-400 border-zinc-700' },
};

function PriorityBadge({ priority }: { priority: string }) {
  const style = PRIORITY_STYLES[priority] ?? PRIORITY_STYLES.MEDIUM;
  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0.5 border text-xs font-medium',
        style.className,
      )}
      style={{ borderRadius: '2px' }} // Linear-style square corners
    >
      {style.label}
    </span>
  );
}

// ─── Status pill ──────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  DRAFT:       { label: 'Draft',       className: 'bg-zinc-800 text-zinc-400' },
  READY:       { label: 'Ready',       className: 'bg-blue-900/50 text-blue-300' },
  IN_PROGRESS: { label: 'In Progress', className: 'bg-cyan-900/50 text-cyan-300' },
  DONE:        { label: 'Done',        className: 'bg-green-900/50 text-green-300' },
  CANCELLED:   { label: 'Cancelled',   className: 'bg-zinc-800 text-zinc-500' },
};

function StatusPill({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.DRAFT;
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        style.className,
      )}
    >
      {style.label}
    </span>
  );
}

// ─── BacklogCard ──────────────────────────────────────────────────────────────

interface BacklogCardProps {
  item: BacklogItem;
  onEdit: (item: BacklogItem) => void;
  className?: string;
}

export function BacklogCard({ item, onEdit, className }: BacklogCardProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Edit: ${item.title}`}
      onClick={() => onEdit(item)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onEdit(item);
        }
      }}
      className={cn(
        'group w-full text-left px-4 py-3 border cursor-pointer',
        'transition-colors duration-150 select-none',
        'hover:bg-white/[0.04] focus-visible:outline-none',
        'focus-visible:ring-2 focus-visible:ring-cyan-500/50 focus-visible:ring-offset-0',
        className,
      )}
      style={{
        backgroundColor: 'rgba(255,255,255,0.02)',
        borderColor: 'rgba(255,255,255,0.08)',
        borderRadius: '8px',
      }}
    >
      {/* Title row */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="text-sm font-medium text-zinc-200 leading-snug line-clamp-2 flex-1">
          {item.title}
        </p>
        <PriorityBadge priority={item.priority} />
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-2 flex-wrap">
        <StatusPill status={item.status} />

        {item.owner && (
          <span className="text-xs text-zinc-500">{item.owner}</span>
        )}

        {item.tags && item.tags.length > 0 && (
          <div className="flex items-center gap-1">
            {item.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="px-1.5 py-0.5 rounded text-xs bg-zinc-800 text-zinc-400"
              >
                {tag}
              </span>
            ))}
            {item.tags.length > 3 && (
              <span className="text-xs text-zinc-600">+{item.tags.length - 3}</span>
            )}
          </div>
        )}

        <span className="ml-auto text-xs text-zinc-600">
          {formatRelativeTime(item.createdAt)}
        </span>
      </div>
    </div>
  );
}
