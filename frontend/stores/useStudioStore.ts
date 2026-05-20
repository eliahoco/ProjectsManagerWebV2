/**
 * useStudioStore — Zustand store for Studio client state.
 *
 * Persists panelRatio to localStorage (key: studio-panel-v1).
 * Draft text is session-only (not persisted — intentional per architecture doc).
 *
 * State:
 *   tabs             — ordered list of open conversation tab IDs
 *   activeTabId      — which tab is in focus (null = none open)
 *   panelRatio       — chat:preview split (0.6 = 60% chat, 40% preview)
 *   drafts           — textarea draft per conversation ID
 *
 * Actions:
 *   openTab          — add a tab (max 8; oldest idle tab evicted at limit)
 *   closeTab         — remove a tab, update activeTabId
 *   setActiveTab     — switch focus to a tab
 *   setDraft         — update textarea draft for a conversation
 *   setPanelRatio    — update split ratio (persisted)
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const MAX_TABS = 8;

export interface TabState {
  id: string;
  title: string;
  isStreaming?: boolean;
}

interface PersistedShape {
  panelRatio: number;
}

interface StudioStoreState extends PersistedShape {
  tabs: TabState[];
  activeTabId: string | null;
  drafts: Record<string, string>;

  // Actions
  openTab: (tab: TabState) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  setDraft: (sessionId: string, text: string) => void;
  setPanelRatio: (ratio: number) => void;
  updateTab: (id: string, patch: Partial<Omit<TabState, 'id'>>) => void;
}

export const useStudioStore = create<StudioStoreState>()(
  persist(
    (set, get) => ({
      // ─── Initial state ────────────────────────────────────────────────
      tabs: [],
      activeTabId: null,
      drafts: {},
      panelRatio: 0.6,

      // ─── Actions ──────────────────────────────────────────────────────

      openTab(tab) {
        set((s) => {
          // Already open — just activate
          if (s.tabs.some((t) => t.id === tab.id)) {
            return { activeTabId: tab.id };
          }

          let tabs = [...s.tabs, tab];

          // Enforce max 8 tabs — evict the oldest (first in array)
          if (tabs.length > MAX_TABS) {
            tabs = tabs.slice(tabs.length - MAX_TABS);
          }

          return { tabs, activeTabId: tab.id };
        });
      },

      closeTab(id) {
        set((s) => {
          const tabs = s.tabs.filter((t) => t.id !== id);
          let activeTabId = s.activeTabId;

          if (activeTabId === id) {
            // Switch to the nearest remaining tab
            const idx = s.tabs.findIndex((t) => t.id === id);
            const next = tabs[idx] ?? tabs[idx - 1] ?? tabs[0] ?? null;
            activeTabId = next?.id ?? null;
          }

          // Clean up draft for closed tab
          const drafts = { ...s.drafts };
          delete drafts[id];

          return { tabs, activeTabId, drafts };
        });
      },

      setActiveTab(id) {
        set({ activeTabId: id });
      },

      setDraft(sessionId, text) {
        set((s) => ({
          drafts: { ...s.drafts, [sessionId]: text },
        }));
      },

      setPanelRatio(ratio) {
        set({ panelRatio: Math.min(0.9, Math.max(0.2, ratio)) });
      },

      updateTab(id, patch) {
        set((s) => ({
          tabs: s.tabs.map((t) => (t.id === id ? { ...t, ...patch } : t)),
        }));
      },
    }),
    {
      name: 'studio-panel-v1',
      // Only persist layout preferences, not ephemeral tab/draft state
      partialize: (s): PersistedShape => ({
        panelRatio: s.panelRatio,
      }),
    },
  ),
);
