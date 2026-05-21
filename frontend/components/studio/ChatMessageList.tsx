'use client';

/**
 * ChatMessageList — renders a list of chat messages with support for
 * streaming partial assistant content.
 *
 * Background: warm parchment #f5f4ed (Claude style) per design doc.
 * Streaming content is displayed in a separate streaming bubble that
 * updates every 50ms via the ref-buffer flush from useConversationStream.
 */

import { useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import type { StudioMessage } from '@/hooks/useStudio';

// ─── Role badge ───────────────────────────────────────────────────────────────

const ROLE_STYLES: Record<string, { label: string; className: string }> = {
  // CB-2813: theme-aware badge colors so labels read on both surfaces.
  user:      { label: 'You',   className: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200' },
  assistant: { label: 'Jonny', className: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/50 dark:text-cyan-300' },
  tool:      { label: 'Tool',  className: 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300' },
};

function RoleBadge({ role }: { role: string }) {
  // Backend persists role uppercase (StudioMessageRole.USER / ASSISTANT / TOOL_RESULT
  // / SUB_AGENT). Normalize to lowercase for the style lookup.
  const key = String(role || '').toLowerCase().split('_')[0];
  const style = ROLE_STYLES[key] ?? ROLE_STYLES.assistant;
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium flex-shrink-0',
        style.className,
      )}
    >
      {style.label}
    </span>
  );
}

// ─── Single message bubble ────────────────────────────────────────────────────

function ChatMessageBubble({ message }: { message: StudioMessage }) {
  const isUser = String(message.role || '').toLowerCase() === 'user';

  return (
    <div
      className={cn(
        'flex gap-3 px-4 py-3',
        isUser ? 'flex-row-reverse' : 'flex-row',
      )}
    >
      <div className="flex-shrink-0 pt-0.5">
        <RoleBadge role={message.role} />
      </div>
      <div
        className={cn(
          'max-w-[80%] rounded-xl px-3 py-2 text-sm leading-relaxed',
          // CB-2813: fully theme-aware bubbles.
          // User light: zinc-200 bg (#e4e4e7) + zinc-900 text (#18181b) = 14.7:1 (AAA).
          //             subtle border for definition on parchment bg.
          // User dark:  zinc-800 bg (#27272a) + zinc-100 text (#f4f4f5) = 14.3:1 (AAA).
          // Assistant light: transparent + zinc-800 body (#27272a on #f5f4ed) = 11.6:1 (AAA).
          // Assistant dark:  transparent + zinc-200 body (#e4e4e7 on #0a0a0c) = 17.0:1 (AAA).
          isUser
            ? 'bg-zinc-200 text-zinc-900 border border-zinc-300/60 dark:bg-zinc-800 dark:text-zinc-100 dark:border-zinc-700/40'
            : 'bg-transparent text-zinc-800 dark:text-zinc-200',
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </div>
    </div>
  );
}

// ─── Streaming bubble ─────────────────────────────────────────────────────────

function StreamingBubble({ content }: { content: string }) {
  if (!content) return null;

  return (
    <div className="flex gap-3 px-4 py-3 flex-row" role="status" aria-live="polite">
      <div className="flex-shrink-0 pt-0.5">
        <RoleBadge role="assistant" />
      </div>
      {/* CB-2813: text-zinc-800 light (11.6:1 on parchment) / text-zinc-200 dark (17:1). */}
      <div className="max-w-[80%] rounded-xl px-3 py-2 text-sm leading-relaxed bg-transparent text-zinc-800 dark:text-zinc-200">
        <p className="whitespace-pre-wrap break-words">{content}</p>
        {/* Streaming cursor */}
        <span
          className="inline-block w-0.5 h-4 bg-cyan-400 ml-0.5 animate-pulse align-middle"
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

// ─── Loading skeletons ────────────────────────────────────────────────────────

const SKELETON_WIDTHS = ['w-[90%]', 'w-[60%]', 'w-[75%]', 'w-[50%]'] as const;

export function ChatMessageSkeleton() {
  return (
    <div className="space-y-4 px-4 py-3">
      {SKELETON_WIDTHS.map((w, i) => (
        <div key={i} className={cn('flex gap-3', i % 2 === 1 && 'flex-row-reverse')}>
          <Skeleton className="w-12 h-5 rounded flex-shrink-0" />
          <Skeleton className={cn('h-10 rounded-xl', w)} />
        </div>
      ))}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface ChatMessageListProps {
  messages: StudioMessage[];
  streamedContent?: string;
  isLoading?: boolean;
  className?: string;
}

export function ChatMessageList({
  messages,
  streamedContent = '',
  isLoading = false,
  className,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages / streaming updates
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, streamedContent]);

  return (
    <div
      className={cn(
        'flex-1 overflow-y-auto',
        // Claude parchment background
        'studio-chat-bg',
        className,
      )}
      style={{ backgroundColor: 'var(--studio-chat-bg, #f5f4ed)' }}
      aria-label="Chat messages"
    >
      {isLoading ? (
        <ChatMessageSkeleton />
      ) : messages.length === 0 && !streamedContent ? (
        <div className="flex flex-col items-center justify-center h-full py-16 px-6 text-center">
          {/* CB-2813: icon circle — light: zinc-200 bg, dark: zinc-800/60 bg. */}
          <div className="w-12 h-12 rounded-full bg-zinc-200 dark:bg-zinc-800/60 flex items-center justify-center mb-4">
            <span className="text-2xl text-zinc-500 dark:text-zinc-400" aria-hidden="true">✦</span>
          </div>
          {/* Light: zinc-600 on parchment #f5f4ed = 5.1:1 (AA). Dark: zinc-400 on #0a0a0c = 7.2:1 (AA). */}
          <p className="text-zinc-600 dark:text-zinc-400 text-sm">No messages yet</p>
          <p className="text-zinc-500 dark:text-zinc-500 text-xs mt-1">
            Start a conversation to plan your next feature
          </p>
        </div>
      ) : (
        <>
          {messages.map((msg) => (
            <ChatMessageBubble key={msg.id} message={msg} />
          ))}
          {streamedContent && <StreamingBubble content={streamedContent} />}
        </>
      )}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  );
}
