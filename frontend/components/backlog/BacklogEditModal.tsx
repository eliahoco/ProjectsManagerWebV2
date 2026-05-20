'use client';

/**
 * BacklogEditModal — create / edit a backlog item.
 *
 * Fields: title, description, priority, status.
 * No scheduler (deferred per MVP slice).
 * No CodeBoard promotion (deferred per MVP slice).
 *
 * Uses the existing ui/modal.tsx pattern.
 */

import { useState, useEffect, useCallback } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCreateBacklogItem, useUpdateBacklogItem } from '@/hooks/useBacklog';
import type {
  BacklogItem,
  BacklogPriority,
  BacklogStatus,
  CreateBacklogItemInput,
} from '@/hooks/useBacklog';

const PRIORITIES: Array<{ value: BacklogPriority; label: string }> = [
  { value: 'CRITICAL', label: 'Critical' },
  { value: 'HIGH',     label: 'High' },
  { value: 'MEDIUM',   label: 'Medium' },
  { value: 'LOW',      label: 'Low' },
];

const STATUSES: Array<{ value: BacklogStatus; label: string }> = [
  { value: 'DRAFT',       label: 'Draft' },
  { value: 'READY',       label: 'Ready' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'DONE',        label: 'Done' },
  { value: 'CANCELLED',   label: 'Cancelled' },
];

function PillGroup<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-zinc-400 mb-1.5">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cn(
              'px-3 py-1 rounded-full text-xs font-medium border transition-colors',
              value === opt.value
                ? 'bg-cyan-900/50 text-cyan-200 border-cyan-700'
                : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:text-zinc-200',
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Modal ────────────────────────────────────────────────────────────────────

interface BacklogEditModalProps {
  item?: BacklogItem | null; // null = create mode
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (item: BacklogItem) => void;
}

export function BacklogEditModal({
  item,
  isOpen,
  onClose,
  onSuccess,
}: BacklogEditModalProps) {
  const isCreate = !item;
  const createItem = useCreateBacklogItem();
  const updateItem = useUpdateBacklogItem();
  const isPending = createItem.isPending || updateItem.isPending;

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<BacklogPriority>('MEDIUM');
  const [status, setStatus] = useState<BacklogStatus>('DRAFT');

  // Populate form when editing an existing item
  useEffect(() => {
    if (item) {
      setTitle(item.title);
      setDescription(item.description ?? '');
      setPriority(item.priority);
      setStatus(item.status);
    } else {
      setTitle('');
      setDescription('');
      setPriority('MEDIUM');
      setStatus('DRAFT');
    }
  }, [item, isOpen]);

  const handleSubmit = useCallback(async () => {
    if (!title.trim()) return;

    try {
      if (isCreate) {
        const input: CreateBacklogItemInput = {
          title: title.trim(),
          description: description.trim() || undefined,
          priority,
          status,
        };
        const created = await createItem.mutateAsync(input);
        onSuccess?.(created);
      } else if (item) {
        const updated = await updateItem.mutateAsync({
          id: item.id,
          data: {
            title: title.trim(),
            description: description.trim() || undefined,
            priority,
            status,
          },
        });
        onSuccess?.(updated);
      }
      onClose();
    } catch {
      // Error toast is handled by React Query's MutationCache in providers.tsx
    }
  }, [title, description, priority, status, isCreate, item, createItem, updateItem, onClose, onSuccess]);

  if (!isOpen) return null;

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={isCreate ? 'Create backlog item' : 'Edit backlog item'}
    >
      <div className="w-full max-w-lg bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h2 className="text-base font-semibold text-zinc-100">
            {isCreate ? 'New backlog item' : 'Edit backlog item'}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Title */}
          <div>
            <label htmlFor="backlog-title" className="text-xs font-medium text-zinc-400 block mb-1.5">
              Title <span className="text-red-400">*</span>
            </label>
            <input
              id="backlog-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Feature title…"
              autoFocus
              className={cn(
                'w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700',
                'text-sm text-zinc-100 placeholder:text-zinc-500',
                'focus:outline-none focus:border-cyan-500 transition-colors',
              )}
            />
          </div>

          {/* Description */}
          <div>
            <label htmlFor="backlog-desc" className="text-xs font-medium text-zinc-400 block mb-1.5">
              Description
            </label>
            <textarea
              id="backlog-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the feature or problem…"
              rows={3}
              className={cn(
                'w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700',
                'text-sm text-zinc-100 placeholder:text-zinc-500',
                'focus:outline-none focus:border-cyan-500 transition-colors resize-none',
              )}
            />
          </div>

          {/* Priority picker */}
          <PillGroup
            label="Priority"
            options={PRIORITIES}
            value={priority}
            onChange={setPriority}
          />

          {/* Status picker */}
          <PillGroup
            label="Status"
            options={STATUSES}
            value={status}
            onChange={setStatus}
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-zinc-800">
          <button
            onClick={onClose}
            disabled={isPending}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!title.trim() || isPending}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
              title.trim() && !isPending
                ? 'bg-cyan-600 hover:bg-cyan-500 text-white'
                : 'bg-zinc-700 text-zinc-500 cursor-not-allowed',
            )}
          >
            {isPending ? 'Saving…' : isCreate ? 'Create' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
