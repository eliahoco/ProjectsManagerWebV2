/**
 * useStudioStore — unit tests for the CB-2814 refactor.
 *
 * Coverage (qa-regression Stage 2):
 *  - Per-project tab isolation (ACs 2, 3, 8)
 *  - MAX_TABS evicts oldest per project (AC 9)
 *  - Drafts/sendCounters stay flat across projects (sessionIds are CUIDs)
 *  - Stub-prefixed session IDs are filtered out at persist (AC 4)
 *  - Stub-prefixed IDs in active pointer fall back to first real tab
 *  - panelRatio clamp + persistence (AC 11)
 *  - Migration from v1 (panelRatio-only) preserves panelRatio (AC 5)
 *  - Migration from corrupted/missing state returns safe defaults
 *
 * Tests reset localStorage + the Zustand store between runs. Each test
 * is isolated.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useStudioStore, MAX_TABS, type TabState } from '@/stores/useStudioStore';

const PA = 'project-A';
const PB = 'project-B';

function resetStore() {
  // Drop persisted state, then re-set defaults.
  localStorage.removeItem('studio-state-v2');
  localStorage.removeItem('studio-panel-v1');
  useStudioStore.setState({
    tabsByProject: {},
    activeTabIdByProject: {},
    drafts: {},
    sendCounters: {},
    panelRatio: 0.6,
  });
}

describe('useStudioStore — per-project tab isolation (CB-2814)', () => {
  beforeEach(resetStore);

  it('AC2: tabs opened in project A are NOT visible in project B', () => {
    const { openTab, getTabs } = useStudioStore.getState();
    openTab(PA, { id: 'sess-a1', title: 'A1' });
    openTab(PA, { id: 'sess-a2', title: 'A2' });
    expect(getTabs(PA).map((t) => t.id)).toEqual(['sess-a1', 'sess-a2']);
    expect(getTabs(PB)).toEqual([]);
  });

  it('AC3: switching B→A restores A tabs unchanged', () => {
    const { openTab, getTabs, getActiveTabId } = useStudioStore.getState();
    openTab(PA, { id: 'sess-a1', title: 'A1' });
    openTab(PA, { id: 'sess-a2', title: 'A2' });
    openTab(PB, { id: 'sess-b1', title: 'B1' });
    // simulate "switch back to A" — store survives switch
    expect(getTabs(PA).map((t) => t.id)).toEqual(['sess-a1', 'sess-a2']);
    expect(getActiveTabId(PA)).toBe('sess-a2');
    expect(getActiveTabId(PB)).toBe('sess-b1');
  });

  it('AC7: active tab is restored per project', () => {
    const { openTab, setActiveTab, getActiveTabId } = useStudioStore.getState();
    openTab(PA, { id: 'sess-a1', title: 'A1' });
    openTab(PA, { id: 'sess-a2', title: 'A2' });
    setActiveTab(PA, 'sess-a1');
    openTab(PB, { id: 'sess-b1', title: 'B1' });
    expect(getActiveTabId(PA)).toBe('sess-a1');
    expect(getActiveTabId(PB)).toBe('sess-b1');
  });

  it('AC8: closing the last tab in project A does not affect project B', () => {
    const { openTab, closeTab, getTabs, getActiveTabId } = useStudioStore.getState();
    openTab(PA, { id: 'sess-a1', title: 'A1' });
    openTab(PB, { id: 'sess-b1', title: 'B1' });
    openTab(PB, { id: 'sess-b2', title: 'B2' });
    closeTab(PA, 'sess-a1');
    expect(getTabs(PA)).toEqual([]);
    expect(getActiveTabId(PA)).toBeNull();
    expect(getTabs(PB).map((t) => t.id)).toEqual(['sess-b1', 'sess-b2']);
    expect(getActiveTabId(PB)).toBe('sess-b2');
  });

  it('AC9: MAX_TABS evicts oldest per project (independent counters)', () => {
    const { openTab, getTabs } = useStudioStore.getState();
    for (let i = 0; i < MAX_TABS + 2; i++) {
      openTab(PA, { id: `sess-a${i}`, title: `A${i}` });
    }
    const tabs = getTabs(PA);
    expect(tabs.length).toBe(MAX_TABS);
    // Oldest two were evicted; the rest remain in order.
    expect(tabs[0].id).toBe('sess-a2');
    expect(tabs[tabs.length - 1].id).toBe(`sess-a${MAX_TABS + 1}`);
    // Project B's cap is independent.
    expect(getTabs(PB).length).toBe(0);
  });
});

describe('useStudioStore — close/active reconciliation', () => {
  beforeEach(resetStore);

  it('closing the active tab switches to the nearest remaining tab', () => {
    const { openTab, closeTab, getActiveTabId } = useStudioStore.getState();
    openTab(PA, { id: 's1', title: '1' });
    openTab(PA, { id: 's2', title: '2' });
    openTab(PA, { id: 's3', title: '3' });
    closeTab(PA, 's2');
    expect(getActiveTabId(PA)).toBe('s3');
  });

  it('closing a tab cleans up its draft and sendCounter', () => {
    const { openTab, closeTab, setDraft, bumpSendCounter } = useStudioStore.getState();
    openTab(PA, { id: 's1', title: '1' });
    setDraft('s1', 'hello');
    bumpSendCounter('s1');
    expect(useStudioStore.getState().drafts.s1).toBe('hello');
    expect(useStudioStore.getState().sendCounters.s1).toBe(1);
    closeTab(PA, 's1');
    expect(useStudioStore.getState().drafts.s1).toBeUndefined();
    expect(useStudioStore.getState().sendCounters.s1).toBeUndefined();
  });
});

describe('useStudioStore — global state (drafts, sendCounters, panelRatio)', () => {
  beforeEach(resetStore);

  it('drafts are keyed by sessionId globally (CUIDs are unique across projects)', () => {
    const { setDraft } = useStudioStore.getState();
    setDraft('sess-a1', 'A draft');
    setDraft('sess-b1', 'B draft');
    const s = useStudioStore.getState();
    expect(s.drafts['sess-a1']).toBe('A draft');
    expect(s.drafts['sess-b1']).toBe('B draft');
  });

  it('bumpSendCounter increments per session', () => {
    const { bumpSendCounter } = useStudioStore.getState();
    bumpSendCounter('s1');
    bumpSendCounter('s1');
    bumpSendCounter('s2');
    const s = useStudioStore.getState();
    expect(s.sendCounters.s1).toBe(2);
    expect(s.sendCounters.s2).toBe(1);
  });

  it('panelRatio clamps to [0.2, 0.9]', () => {
    const { setPanelRatio } = useStudioStore.getState();
    setPanelRatio(0.05);
    expect(useStudioStore.getState().panelRatio).toBe(0.2);
    setPanelRatio(0.99);
    expect(useStudioStore.getState().panelRatio).toBe(0.9);
    setPanelRatio(0.5);
    expect(useStudioStore.getState().panelRatio).toBe(0.5);
  });
});

describe('useStudioStore — stub-ID handling (CB-2814 D4 defense)', () => {
  beforeEach(resetStore);

  it('AC4: stub-prefixed IDs are filtered out at persist time', () => {
    const { openTab } = useStudioStore.getState();
    openTab(PA, { id: 'real-1', title: 'Real' });
    openTab(PA, { id: 'stub-12345', title: 'Stub' });
    openTab(PA, { id: 'real-2', title: 'Real 2' });

    // Read the persisted payload directly.
    const raw = localStorage.getItem('studio-state-v2');
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    const persistedTabs: TabState[] = parsed.state.tabsByProject[PA] ?? [];
    expect(persistedTabs.map((t) => t.id)).toEqual(['real-1', 'real-2']);
  });

  it('AC4: activeTabIdByProject falls back to first real tab if active was a stub', () => {
    const { openTab, setActiveTab } = useStudioStore.getState();
    openTab(PA, { id: 'real-1', title: 'Real' });
    openTab(PA, { id: 'stub-12345', title: 'Stub' });
    setActiveTab(PA, 'stub-12345');
    const raw = localStorage.getItem('studio-state-v2');
    const parsed = JSON.parse(raw!);
    expect(parsed.state.activeTabIdByProject[PA]).toBe('real-1');
  });
});

describe('useStudioStore — migration from v1', () => {
  // No beforeEach reset — these tests own their seed data.
  it('AC5: v1 storage with only panelRatio migrates and does not crash', async () => {
    localStorage.clear();
    // Seed v1-shaped data (no tabs key).
    localStorage.setItem(
      'studio-state-v2',
      JSON.stringify({ state: { panelRatio: 0.75 }, version: 1 }),
    );
    // Force the store to re-hydrate.
    await useStudioStore.persist.rehydrate();
    const s = useStudioStore.getState();
    expect(s.panelRatio).toBe(0.75);
    expect(s.tabsByProject).toEqual({});
    expect(s.activeTabIdByProject).toEqual({});
  });

  it('AC5: completely malformed storage falls back to defaults without throwing', async () => {
    localStorage.clear();
    localStorage.setItem(
      'studio-state-v2',
      JSON.stringify({ state: { panelRatio: 'not-a-number', tabsByProject: 'oops' }, version: 2 }),
    );
    await expect(useStudioStore.persist.rehydrate()).resolves.not.toThrow();
    const s = useStudioStore.getState();
    expect(typeof s.panelRatio).toBe('number');
    expect(s.tabsByProject).toEqual({});
  });
});
