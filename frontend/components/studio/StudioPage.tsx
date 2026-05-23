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
import { useStudioStore, EMPTY_TABS, type TabState } from '@/stores/useStudioStore';
import { useStudioTabsHydration } from '@/hooks/useStudioTabsHydration';
import { useCreateStudioSession } from '@/hooks/useStudio';
import { ConversationTabBar } from './ConversationTabBar';
import { Chat } from './Chat';
import { AgentActivityPanel } from './AgentActivityPanel';
import { InvestigationCyclePanel } from './InvestigationCyclePanel';
import { ResizableSplit } from './ResizableSplit';
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

// ─── Chat + resizable right rail (CB-3124) ────────────────────────────────────

function ChatWithRightRail({
  hasNoTabs,
  tabs,
  activeTabId,
  workspaceId,
  onNewTab,
  isCreating,
}: {
  hasNoTabs: boolean;
  tabs: TabState[];
  activeTabId: string | null;
  workspaceId: string;
  onNewTab: () => void;
  isCreating: boolean;
}) {
  const rightWidthPx = useStudioStore((s) => s.investigationPanelWidthPx);
  const setRightWidth = useStudioStore((s) => s.setInvestigationPanelWidth);

  const left = hasNoTabs ? (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
      <div className="text-center max-w-sm">
        <div className="w-14 h-14 rounded-2xl bg-zinc-200 dark:bg-zinc-800/60 flex items-center justify-center mx-auto mb-4">
          <span className="text-3xl text-zinc-500 dark:text-zinc-400" aria-hidden="true">✦</span>
        </div>
        <h2 className="text-zinc-800 dark:text-zinc-200 font-semibold text-lg mb-2">
          Start a conversation
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400 text-sm mb-4">
          Describe a feature, ask for a plan, or explore your codebase
        </p>
        <button
          onClick={onNewTab}
          disabled={isCreating}
          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:text-zinc-950 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          New conversation
        </button>
      </div>
    </div>
  ) : (
    tabs.map((tab) => (
      <TabChatPanel
        key={tab.id}
        sessionId={tab.id}
        workspaceId={workspaceId}
        isActive={tab.id === activeTabId}
      />
    ))
  );

  const right = activeTabId ? (
    // H1 (react-specialist review): key by sessionId so switching tabs
    // remounts the panel with clean state instead of carrying the prior
    // session's layers/deliverable into the new session.
    <InvestigationCyclePanel key={activeTabId} sessionId={activeTabId} />
  ) : (
    <ActiveAgentPanel
      sessionId={activeTabId ?? null}
      workspaceId={workspaceId}
    />
  );

  return (
    <ResizableSplit
      left={left}
      right={right}
      rightWidthPx={rightWidthPx}
      onResize={setRightWidth}
      minRightPx={280}
      maxRightPx={1000}
      className="flex-1 min-h-0"
    />
  );
}

// ─── StudioPage ───────────────────────────────────────────────────────────────

export function StudioPage() {
  const { workspaceId, projectId } = useTenant();
  // Per-project tab state (CB-2814 fix; master plan §E2.S2.T5). Reading
  // the slice keyed by projectId means switching project A↔B swaps the
  // visible tab set without leaking conversations across projects.
  const tabs = useStudioStore((s) => s.tabsByProject[projectId] ?? EMPTY_TABS) as TabState[];
  const activeTabId = useStudioStore((s) => s.activeTabIdByProject[projectId] ?? null);
  const openTab = useStudioStore((s) => s.openTab);
  const createSession = useCreateStudioSession();

  // Diff persisted tabs against the live session list; prune any tab
  // whose session vanished server-side.
  useStudioTabsHydration();

  const handleNewTab = useCallback(async () => {
    if (!projectId) return;
    try {
      const session = await createSession.mutateAsync({
        title: `Conversation ${tabs.length + 1}`,
      });
      startTransition(() => {
        openTab(projectId, { id: session.id, title: session.title });
      });
    } catch {
      // Backend not ready — open a local-only stub tab for development.
      // Stub IDs are filtered out at persist time (see useStudioStore
      // partialize) so they never resurrect on reload.
      const stubId = `stub-${Date.now()}`;
      startTransition(() => {
        openTab(projectId, { id: stubId, title: `Conversation ${tabs.length + 1}` });
      });
    }
  }, [createSession, tabs.length, openTab, projectId]);

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

      {/* Main content area — ResizableSplit (CB-3124 fix) lets the user
          drag the divider between chat and the right Investigation panel. */}
      <ChatWithRightRail
        hasNoTabs={hasNoTabs}
        tabs={tabs}
        activeTabId={activeTabId}
        workspaceId={workspaceId}
        onNewTab={handleNewTab}
        isCreating={createSession.isPending}
      />
    </div>
  );
}
