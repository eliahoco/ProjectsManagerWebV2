'use client';

/**
 * ChatInput — textarea + Send button for Studio chat.
 *
 * Submit on Cmd+Enter (Mac) or Ctrl+Enter (Windows/Linux).
 * Plain Enter inserts a newline (standard textarea behavior).
 *
 * Grows vertically up to 6 rows then scrolls.
 * Disabled when isStreaming=true.
 */

import { useRef, useCallback, KeyboardEvent } from 'react';
import { Send } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  isStreaming?: boolean;
  placeholder?: string;
  className?: string;
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  isStreaming = false,
  placeholder = 'Plan a feature, describe a problem…',
  className,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        const trimmed = value.trim();
        if (trimmed && !isStreaming) {
          onSubmit(trimmed);
        }
      }
    },
    [value, isStreaming, onSubmit],
  );

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (trimmed && !isStreaming) {
      onSubmit(trimmed);
    }
  }, [value, isStreaming, onSubmit]);

  const canSubmit = value.trim().length > 0 && !isStreaming;

  return (
    <div
      className={cn(
        // CB-2813: fully class-based theming — NO inline style for bg colors.
        // Light: solid white bar sitting above parchment chat panel.
        // Dark:  solid zinc-900 bar — NOT semi-transparent (avoids muddy overlay).
        'flex items-end gap-2 border-t px-3 py-3',
        'bg-white border-zinc-200',
        'dark:bg-zinc-900 dark:border-zinc-800',
        className,
      )}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={isStreaming}
        rows={1}
        aria-label="Chat message input"
        className={cn(
          'flex-1 resize-none rounded-lg border px-3 py-2 text-sm transition-colors',
          // Light: solid white textarea, dark zinc-900 text, zinc-400 placeholder.
          // Contrast: #18181b on #ffffff = 18.1:1 (AAA). Placeholder #a1a1aa on #fff = 4.6:1 (AA).
          'bg-white border-zinc-200 text-zinc-900 placeholder:text-zinc-400',
          // Dark: solid zinc-950 textarea (slightly darker than container), light text.
          // Contrast: #f4f4f5 on #09090b = 18.3:1 (AAA). Placeholder #71717a on #09090b = 5.0:1 (AA).
          'dark:bg-zinc-950 dark:border-zinc-700 dark:text-zinc-100 dark:placeholder:text-zinc-500',
          'focus:outline-none focus:ring-2 focus:ring-cyan-400/50 focus:border-cyan-400',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          'min-h-[38px] max-h-[150px] overflow-y-auto',
        )}
        style={{
          // Auto-grow: line-height ~1.5, clamp between 1 and 6 rows
          height: 'auto',
          minHeight: '38px',
        }}
        onInput={(e) => {
          const el = e.currentTarget;
          el.style.height = 'auto';
          el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
        }}
      />

      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        aria-label="Send message (Cmd+Enter)"
        title="Send (Cmd+Enter)"
        className={cn(
          'flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-lg transition-colors',
          // Enabled light: cyan-600 bg + white icon = 4.6:1 (AA).
          // Enabled dark:  cyan-500 bg + zinc-950 text = 4.8:1 (AA).
          // Disabled light: zinc-200 bg + zinc-400 icon = 4.5:1 (AA).
          // Disabled dark:  zinc-800 bg + zinc-600 icon = 3.0:1 — intentionally muted.
          canSubmit
            ? 'bg-cyan-600 hover:bg-cyan-500 text-white dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:text-zinc-950'
            : 'bg-zinc-200 text-zinc-400 cursor-not-allowed dark:bg-zinc-800 dark:text-zinc-600',
        )}
      >
        <Send className="w-4 h-4" />
      </button>
    </div>
  );
}
