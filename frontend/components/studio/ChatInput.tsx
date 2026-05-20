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
        // CB-2813: theme-aware. Light = parchment, Dark = zinc-900 match.
        'flex items-end gap-2 border-t px-3 py-3 backdrop-blur-sm',
        'bg-[#f5f4ed]/90 border-zinc-200/40',
        'dark:bg-zinc-900/90 dark:border-zinc-800/60',
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
          // light theme
          'bg-white/70 border-zinc-200 text-zinc-800 placeholder:text-zinc-400',
          // dark theme override
          'dark:bg-zinc-950/60 dark:border-zinc-700 dark:text-zinc-100 dark:placeholder:text-zinc-500',
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
          canSubmit
            ? 'bg-cyan-600 hover:bg-cyan-500 text-white'
            : 'bg-zinc-200 text-zinc-400 cursor-not-allowed dark:bg-zinc-800 dark:text-zinc-600',
        )}
      >
        <Send className="w-4 h-4" />
      </button>
    </div>
  );
}
