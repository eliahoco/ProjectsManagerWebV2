/**
 * useStudioStore — Zustand store for Studio client state.
 *
 * Per CB-2814 fix (2026-05-22): tabs + activeTabId are project-scoped
 * (keyed by projectId from TenantContext). Persistence covers tabs,
 * drafts, sendCounters and panelRatio so a refresh + project switch
 * preserves the user's open conversations exactly as planned in
 * `docs/plans/2026-05-07-ai-project-workspace-master-plan.md` §E2.S2.T5
 * — "Tab persistence — tabs survive reload".
 *
 * Storage key: `studio-state-v2` (renamed from `studio-panel-v1`).
 * The Zustand `name` field switched between releases, so an orphaned
 * `studio-panel-v1` record can survive in a user's localStorage. We
 * bridge it once at module load: read v1 → seed v2 with the same
 * panelRatio (if v2 is empty) → delete v1. The migrate() callback
 * below covers the in-key version path (records stored under the
 * new name but with `version: 1`).
 *
 * Stub-prefixed session IDs (`stub-…`, used while a real session ID
 * is still being created server-side) are filtered out before
 * persistence — persisting them would resurrect garbage tabs on
 * reload.
 *
 * State (scoped):
 *   tabsByProject[pid]              — ordered list of open tabs for project pid
 *   activeTabIdByProject[pid]       — focused tab id for project pid (null = none)
 *
 * State (global — safe because session IDs are globally-unique CUIDs):
 *   drafts                          — textarea draft per conversation ID
 *   sendCounters                    — turn counter per conversation ID (drives
 *                                     re-arming of useConversationStream's SSE)
 *   panelRatio                      — chat:preview split (0.6 = 60% chat)
 *
 * Actions (all project-scoped actions take projectId as first arg):
 *   openTab(projectId, tab)
 *   closeTab(projectId, id)
 *   setActiveTab(projectId, id)
 *   updateTab(projectId, id, patch)
 *   setDraft(sessionId, text)
 *   setPanelRatio(ratio)
 *   bumpSendCounter(sessionId)
 *
 * Selectors:
 *   getTabs(projectId)              — TabState[] for project
 *   getActiveTabId(projectId)       — string | null for project
 */

import { create } from 'zustand';
import { persist, type PersistOptions } from 'zustand/middleware';

const MAX_TABS = 8;
const STUB_ID_PREFIX = 'stub-';

// Stable empty default — used by selectors so that `selector(s) => s.tabsByProject[pid] ?? EMPTY_TABS`
// returns the SAME reference across renders when no tabs exist for that project.
// Returning a fresh `[]` each call would create a new ref → zustand triggers
// re-render → selector runs again → another new ref → infinite loop.
const EMPTY_TABS: readonly TabState[] = Object.freeze([]);

// One-time cross-key bridge from the previous storage `name` (studio-panel-v1)
// to the new name (studio-state-v2). Runs at module load. Idempotent: if v2
// already exists it leaves both alone except for deleting the orphan v1.
function bridgeLegacyPanelV1Storage(): void {
  if (typeof window === 'undefined') return;
  try {
    const v1Raw = window.localStorage.getItem('studio-panel-v1');
    if (!v1Raw) return;
    const v2Raw = window.localStorage.getItem('studio-state-v2');
    if (!v2Raw) {
      const v1 = JSON.parse(v1Raw);
      const panelRatio =
        typeof v1?.state?.panelRatio === 'number' && Number.isFinite(v1.state.panelRatio)
          ? v1.state.panelRatio
          : 0.6;
      window.localStorage.setItem(
        'studio-state-v2',
        JSON.stringify({ state: { panelRatio }, version: 1 }),
      );
    }
    window.localStorage.removeItem('studio-panel-v1');
  } catch {
    // Malformed v1 record — nothing to migrate; the migrate() / merge()
    // fallbacks downstream will boot v2 with defaults.
  }
}
bridgeLegacyPanelV1Storage();

export interface TabState {
  id: string;
  title: string;
  isStreaming?: boolean;
}

interface PersistedShape {
  panelRatio: number;
  tabsByProject: Record<string, TabState[]>;
  activeTabIdByProject: Record<string, string | null>;
  drafts: Record<string, string>;
  sendCounters: Record<string, number>;
  /** CB-3124: persisted width of the right-rail investigation panel. */
  investigationPanelWidthPx: number;
}

interface StudioStoreState extends PersistedShape {
  // Actions — project-scoped
  openTab: (projectId: string, tab: TabState) => void;
  closeTab: (projectId: string, id: string) => void;
  setActiveTab: (projectId: string, id: string) => void;
  updateTab: (
    projectId: string,
    id: string,
    patch: Partial<Omit<TabState, 'id'>>,
  ) => void;

  // Actions — global
  setDraft: (sessionId: string, text: string) => void;
  setPanelRatio: (ratio: number) => void;
  setInvestigationPanelWidth: (px: number) => void;
  bumpSendCounter: (sessionId: string) => void;

  // Selectors (convenience — components can also read state directly)
  getTabs: (projectId: string) => TabState[];
  getActiveTabId: (projectId: string) => string | null;
}

const isRealId = (id: string): boolean =>
  typeof id === 'string' && id.length > 0 && !id.startsWith(STUB_ID_PREFIX);

const persistOptions: PersistOptions<StudioStoreState, PersistedShape> = {
  name: 'studio-state-v2',
  version: 2,
  // Persist 5 fields: layout + scoped tab state + per-session draft + counters.
  partialize: (s): PersistedShape => {
    // Strip stub-prefixed tab IDs from per-project tab lists; they are
    // ephemeral placeholders for sessions still being created server-side
    // and persisting them resurrects garbage tabs on reload.
    const cleanTabs: Record<string, TabState[]> = {};
    for (const [pid, tabs] of Object.entries(s.tabsByProject)) {
      cleanTabs[pid] = tabs.filter((t) => isRealId(t.id));
    }
    // Clear activeTabId pointers that reference stub IDs (or vanished tabs).
    const cleanActive: Record<string, string | null> = {};
    for (const [pid, active] of Object.entries(s.activeTabIdByProject)) {
      if (active && isRealId(active) && cleanTabs[pid]?.some((t) => t.id === active)) {
        cleanActive[pid] = active;
      } else {
        cleanActive[pid] = cleanTabs[pid]?.[0]?.id ?? null;
      }
    }
    return {
      panelRatio: s.panelRatio,
      tabsByProject: cleanTabs,
      activeTabIdByProject: cleanActive,
      drafts: s.drafts,
      sendCounters: s.sendCounters,
      investigationPanelWidthPx: s.investigationPanelWidthPx,
    };
  },
  // Corruption-safe migration from any older shape. v1 only carried
  // `panelRatio`; if anything else is malformed (manual edit, partial
  // write, version drift) fall back to defaults rather than crash.
  migrate: (persisted: unknown, version: number): PersistedShape => {
    return sanitizePersisted(persisted, version);
  },
  // merge runs even when version matches — defends against corrupted v2
  // payloads (e.g. panelRatio: "not-a-number" from manual edit).
  merge: (persisted: unknown, current: StudioStoreState): StudioStoreState => {
    const safe = sanitizePersisted(persisted, 2);
    return { ...current, ...safe };
  },
};

function sanitizePersisted(persisted: unknown, version: number): PersistedShape {
  const defaults: PersistedShape = {
    panelRatio: 0.6,
    tabsByProject: {},
    activeTabIdByProject: {},
    drafts: {},
    sendCounters: {},
    investigationPanelWidthPx: 360,
  };
  if (!persisted || typeof persisted !== 'object') return defaults;
  const p = persisted as Record<string, unknown>;
  const safeNumber = (v: unknown, fallback: number): number =>
    typeof v === 'number' && Number.isFinite(v) ? v : fallback;
  const safeRecord = <T,>(v: unknown): Record<string, T> =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? (v as Record<string, T>)
      : {};

  if (version < 2) {
    // v1: only panelRatio was persisted.
    return { ...defaults, panelRatio: safeNumber(p.panelRatio, 0.6) };
  }
  // v2+ — accept any subset; backfill missing fields.
  return {
    panelRatio: safeNumber(p.panelRatio, 0.6),
    tabsByProject: safeRecord<TabState[]>(p.tabsByProject),
    activeTabIdByProject: safeRecord<string | null>(p.activeTabIdByProject),
    drafts: safeRecord<string>(p.drafts),
    sendCounters: safeRecord<number>(p.sendCounters),
    investigationPanelWidthPx: safeNumber(p.investigationPanelWidthPx, 360),
  };
}

export const useStudioStore = create<StudioStoreState>()(
  persist(
    (set, get) => ({
      // ─── Initial state ────────────────────────────────────────────────
      tabsByProject: {},
      activeTabIdByProject: {},
      drafts: {},
      sendCounters: {},
      panelRatio: 0.6,
      investigationPanelWidthPx: 360,

      // ─── Actions — project-scoped ─────────────────────────────────────

      openTab(projectId, tab) {
        if (!projectId) return;
        set((s) => {
          const current = s.tabsByProject[projectId] ?? [];
          // Already open — just activate
          if (current.some((t) => t.id === tab.id)) {
            return {
              activeTabIdByProject: { ...s.activeTabIdByProject, [projectId]: tab.id },
            };
          }

          let next = [...current, tab];
          // Enforce MAX_TABS per project — evict the oldest at the limit.
          if (next.length > MAX_TABS) {
            next = next.slice(next.length - MAX_TABS);
          }

          return {
            tabsByProject: { ...s.tabsByProject, [projectId]: next },
            activeTabIdByProject: { ...s.activeTabIdByProject, [projectId]: tab.id },
          };
        });
      },

      closeTab(projectId, id) {
        if (!projectId) return;
        set((s) => {
          const current = s.tabsByProject[projectId] ?? [];
          const next = current.filter((t) => t.id !== id);

          let activeId = s.activeTabIdByProject[projectId] ?? null;
          if (activeId === id) {
            // Switch to the nearest remaining tab (same index, or previous, or first).
            const idx = current.findIndex((t) => t.id === id);
            const nextActive = next[idx] ?? next[idx - 1] ?? next[0] ?? null;
            activeId = nextActive?.id ?? null;
          }

          // Clean up draft + counter for the closed tab.
          const drafts = { ...s.drafts };
          delete drafts[id];
          const sendCounters = { ...s.sendCounters };
          delete sendCounters[id];

          return {
            tabsByProject: { ...s.tabsByProject, [projectId]: next },
            activeTabIdByProject: { ...s.activeTabIdByProject, [projectId]: activeId },
            drafts,
            sendCounters,
          };
        });
      },

      setActiveTab(projectId, id) {
        if (!projectId) return;
        // Reject ids that don't correspond to an open tab in this project —
        // prevents callers from leaving the active pointer dangling at a
        // vanished or stub id. Stub-flow callers should `openTab` first
        // (which sets active atomically), not poke setActiveTab directly.
        set((s) => {
          const tabs = s.tabsByProject[projectId] ?? [];
          if (!tabs.some((t) => t.id === id)) return {} as Partial<StudioStoreState>;
          return {
            activeTabIdByProject: { ...s.activeTabIdByProject, [projectId]: id },
          };
        });
      },

      updateTab(projectId, id, patch) {
        if (!projectId) return;
        set((s) => {
          const current = s.tabsByProject[projectId] ?? [];
          const next = current.map((t) => (t.id === id ? { ...t, ...patch } : t));
          return {
            tabsByProject: { ...s.tabsByProject, [projectId]: next },
          };
        });
      },

      // ─── Actions — global (sessionIds are globally-unique CUIDs) ──────

      setDraft(sessionId, text) {
        set((s) => ({
          drafts: { ...s.drafts, [sessionId]: text },
        }));
      },

      setPanelRatio(ratio) {
        set({ panelRatio: Math.min(0.9, Math.max(0.2, ratio)) });
      },

      setInvestigationPanelWidth(px) {
        // M4 (react-specialist review): align ceiling with ResizableSplit prop.
        set({ investigationPanelWidthPx: Math.min(1000, Math.max(280, Math.round(px))) });
      },

      bumpSendCounter(sessionId) {
        set((s) => ({
          sendCounters: {
            ...s.sendCounters,
            [sessionId]: (s.sendCounters[sessionId] ?? 0) + 1,
          },
        }));
      },

      // ─── Selectors ────────────────────────────────────────────────────

      getTabs(projectId) {
        return get().tabsByProject[projectId] ?? [];
      },

      getActiveTabId(projectId) {
        return get().activeTabIdByProject[projectId] ?? null;
      },
    }),
    persistOptions,
  ),
);

export { MAX_TABS, STUB_ID_PREFIX, isRealId, EMPTY_TABS };
