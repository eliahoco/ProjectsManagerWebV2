'use client';

/**
 * Chat — Compound Component for Studio conversations.
 *
 * Pattern:
 *   <Chat.Provider sessionId={id} workspaceId={workspaceId}>
 *     <Chat.MessageList />
 *     <Chat.Input />
 *     <Chat.Actions />
 *   </Chat.Provider>
 *
 * State management:
 *   - Server state (messages) via React Query (useStudioMessages)
 *   - Draft text via Zustand (useStudioStore)
 *   - Streaming tokens via useConversationStream (ref buffer + 50ms flush)
 *
 * The Provider exposes the context via useChatContext() so child components
 * can access session state without prop drilling.
 */

import React, {
  createContext,
  useContext,
  useCallback,
  type ReactNode,
} from 'react';
import { useStudioMessages, useSendMessage } from '@/hooks/useStudio';
import { useConversationStream } from '@/hooks/useConversationStream';
import { useStudioStore } from '@/stores/useStudioStore';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';
import { cn } from '@/lib/utils';

// ─── Context ──────────────────────────────────────────────────────────────────

interface ChatContextValue {
  sessionId: string | null;
  workspaceId: string;
  isStreaming: boolean;
  streamedContent: string;
}

const ChatContext = createContext<ChatContextValue | null>(null);

function useChatContext(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used inside Chat.Provider');
  return ctx;
}

// ─── Provider ─────────────────────────────────────────────────────────────────

interface ProviderProps {
  sessionId: string | null;
  workspaceId: string;
  children: ReactNode;
}

function Provider({ sessionId, workspaceId, children }: ProviderProps) {
  // Single EventSource per session — children read `streamedContent` from
  // context rather than re-invoking the hook (which would open a second
  // SSE connection for every consumer).
  const { streamedContent } = useConversationStream(sessionId, workspaceId);
  const isStreaming = streamedContent.length > 0;

  return (
    <ChatContext.Provider value={{ sessionId, workspaceId, isStreaming, streamedContent }}>
      {children}
    </ChatContext.Provider>
  );
}

// ─── MessageList ──────────────────────────────────────────────────────────────

interface MessageListProps {
  className?: string;
}

function MessageList({ className }: MessageListProps) {
  const { sessionId, streamedContent } = useChatContext();
  const { data: messages = [], isLoading } = useStudioMessages(sessionId);

  return (
    <ChatMessageList
      messages={messages}
      streamedContent={streamedContent}
      isLoading={isLoading}
      className={className}
    />
  );
}

// ─── Input ────────────────────────────────────────────────────────────────────

interface InputProps {
  className?: string;
}

function Input({ className }: InputProps) {
  const { sessionId, workspaceId, isStreaming } = useChatContext();
  const sendMessage = useSendMessage(sessionId);
  const { drafts, setDraft } = useStudioStore();

  const draft = sessionId ? (drafts[sessionId] ?? '') : '';

  const handleChange = useCallback(
    (value: string) => {
      if (sessionId) setDraft(sessionId, value);
    },
    [sessionId, setDraft],
  );

  const handleSubmit = useCallback(
    (value: string) => {
      if (!sessionId) return;
      setDraft(sessionId, '');
      sendMessage.mutate({ content: value });
    },
    [sessionId, setDraft, sendMessage],
  );

  return (
    <ChatInput
      value={draft}
      onChange={handleChange}
      onSubmit={handleSubmit}
      isStreaming={isStreaming || sendMessage.isPending}
      className={className}
    />
  );
}

// ─── Actions ──────────────────────────────────────────────────────────────────

interface ActionsProps {
  className?: string;
}

function Actions({ className }: ActionsProps) {
  // Phase 0 stub — Pause and Save deferred to Phase 1
  return (
    <div className={cn('flex items-center gap-2 px-3 py-1.5 border-t border-zinc-800/30', className)}>
      <span className="text-xs text-zinc-600">
        Cmd+Enter to send · Phase 0 stub
      </span>
    </div>
  );
}

// ─── Export as Compound Component ─────────────────────────────────────────────

export const Chat = {
  Provider,
  MessageList,
  Input,
  Actions,
};
