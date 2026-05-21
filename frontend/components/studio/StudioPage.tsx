'use client';

/**
 * StudioPage — top-level layout for the Studio view.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────────┐
 *   │  ConversationTabBar                                      │
 *   ├──────────────────────────────────┬──────────────────────┤
 *   │  Chat.Provider                   │  AgentActivityPanel  │
 *   │    Chat.MessageList              │  (stub)              │
 *   │    Chat.Input                    │                      │
 *   │    Chat.Actions                  │                      │
 *   └──────────────────────────────────┴──────────────────────┘
 *
 * Multi-tab: each tab has its own Chat.Provider; inactive tabs are
 * hidden (not unmounted) so SSE connections stay alive.
 */

import { useCallback, startTransition } from 'react';
import { useTenant } from '@/contexts/TenantContext';
import { useStudioStore } from '@/stores/useStudioStore';
import { useCreateStudioSession } from '@/hooks/useStudio';
import { ConversationTabBar } from './ConversationTabBar';
import { Chat } from './Chat';
import { AgentActivityPanel } from './AgentActivityPanel';
import { useConversationStream } from '@/hooks/useConversationStream';
import { cn } from '@/lib/utils';

// ─── Per-tab chat panel (manages its own stream + visibility) ─────────────────

function TabChatPanel({
  sessionId,
  workspaceId,
  isActive,
}: {
  sessionId: string;
  workspaceId: string;
  isActive: boolean;
}) {
  return (
    // Hidden but NOT unmounted — keeps SSE connection alive
    <div className={cn('flex-1 flex flex-col min-h-0', !isActive && 'hidden')}>
      <Chat.Provider sessionId={sessionId} workspaceId={workspaceId}>
        <Chat.MessageList className="flex-1 min-h-0" />
        <Chat.Input />
        <Chat.Actions />
      </Chat.Provider>
    </div>
  );
}

// ─── Agent panel driven by active tab stream ──────────────────────────────────

function ActiveAgentPanel({
  sessionId,
  workspaceId,
}: {
  sessionId: string | null;
  workspaceId: string;
}) {
  const { agentStatuses } = useConversationStream(sessionId, workspaceId);
  return (
    <AgentActivityPanel
      agentStatuses={agentStatuses}
      className="w-64 flex-shrink-0"
    />
  );
}

// ─── StudioPage ───────────────────────────────────────────────────────────────

export function StudioPage() {
  const { workspaceId } = useTenant();
  const { tabs, activeTabId, openTab } = useStudioStore();
  const createSession = useCreateStudioSession();

  const handleNewTab = useCallback(async () => {
    try {
      const session = await createSession.mutateAsync({
        title: `Conversation ${tabs.length + 1}`,
      });
      startTransition(() => {
        openTab({ id: session.id, title: session.title });
      });
    } catch {
      // Backend not ready — open a local-only stub tab for development
      const stubId = `stub-${Date.now()}`;
      startTransition(() => {
        openTab({ id: stubId, title: `Conversation ${tabs.length + 1}` });
      });
    }
  }, [createSession, tabs.length, openTab]);

  const hasNoTabs = tabs.length === 0;

  return (
    // CB-2813: outer shell uses CSS var so it tracks the studio chat bg in both modes.
    // Light: --studio-chat-bg = #f5f4ed (parchment). Dark: --studio-chat-bg = #0a0a0c.
    <div
      className="flex flex-col h-full min-h-0"
      style={{ backgroundColor: 'var(--studio-chat-bg, #0a0a0c)' }}
    >
      {/* Tab strip */}
      <ConversationTabBar
        onNew={handleNewTab}
        isCreating={createSession.isPending}
      />

      {/* Main content area */}
      <div className="flex flex-1 min-h-0">
        {/* Left: conversation panels */}
        <div className="flex-1 flex flex-col min-h-0 min-w-0">
          {hasNoTabs ? (
            // Empty state — no conversations open; inherits studio-chat-bg from parent
            <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
              <div className="text-center max-w-sm">
                {/* Icon circle — light: zinc-200, dark: zinc-800/60 */}
                <div className="w-14 h-14 rounded-2xl bg-zinc-200 dark:bg-zinc-800/60 flex items-center justify-center mx-auto mb-4">
                  <span className="text-3xl text-zinc-500 dark:text-zinc-400" aria-hidden="true">✦</span>
                </div>
                {/* Light: zinc-800 on #f5f4ed = 11.5:1 (AAA). Dark: zinc-200 on #0a0a0c = 17.0:1 (AAA). */}
                <h2 className="text-zinc-800 dark:text-zinc-200 font-semibold text-lg mb-2">
                  Start a conversation
                </h2>
                {/* Light: zinc-600 on #f5f4ed = 5.1:1 (AA). Dark: zinc-400 on #0a0a0c = 7.2:1 (AA). */}
                <p className="text-zinc-600 dark:text-zinc-400 text-sm mb-4">
                  Describe a feature, ask for a plan, or explore your codebase
                </p>
                <button
                  onClick={handleNewTab}
                  disabled={createSession.isPending}
                  className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:text-zinc-950 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                >
                  New conversation
                </button>
              </div>
            </div>
          ) : (
            // Render all tabs; only active one is visible
            tabs.map((tab) => (
              <TabChatPanel
                key={tab.id}
                sessionId={tab.id}
                workspaceId={workspaceId}
                isActive={tab.id === activeTabId}
              />
            ))
          )}
        </div>

        {/* Right: agent activity panel */}
        <ActiveAgentPanel
          sessionId={activeTabId ?? null}
          workspaceId={workspaceId}
        />
      </div>
    </div>
  );
}
