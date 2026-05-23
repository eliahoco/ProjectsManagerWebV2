/**
 * useStudioTabsHydration — keep the persisted Studio tab set honest.
 *
 * CB-2814 fix (2026-05-22). The store now persists `tabsByProject` so
 * tabs survive a reload (master plan `docs/plans/2026-05-07-ai-project-workspace-master-plan.md` §E2.S2.T5
 * — "Tab persistence — tabs survive reload"). That introduces a new
 * failure mode: a tab's underlying StudioSession can be deleted, archived,
 * or never have existed (manual localStorage edit, schema drift,
 * cross-environment paste). Persisting a tab that points at a vanished
 * session would resurrect a broken Chat that 404s on every render.
 *
 * This hook diff-reconciles the persisted tab set for the active
 * project against the live session list from the backend and calls
 * `closeTab` on any tab whose session no longer exists. It runs at
 * mount and any time the projectId or session list changes.
 *
 * Scope: this is **hydration-time reconciliation**. It is NOT a live
 * diff-tracker for `openTab` — newly opened tabs are not pruned the
 * instant they appear, only on the next sessions-query refresh (after
 * a `useCreateStudioSession` invalidation, project switch, or refetch).
 *
 * Stub-prefixed tab IDs (`stub-…`) are skipped — those are ephemeral
 * placeholders for sessions still being created server-side, and they
 * are filtered out at the persistence layer (see `useStudioStore`
 * partialize). They won't be present after a reload, but they may
 * exist in-memory mid-create, so the diff must ignore them too.
 */

'use client';

import { useEffect, useRef } from 'react';
import { useStudioStore, isRealId } from '@/stores/useStudioStore';
import { useStudioSessions } from '@/hooks/useStudio';
import { useTenant } from '@/contexts/TenantContext';

export function useStudioTabsHydration() {
  const { projectId } = useTenant();
  const { data: sessions, isSuccess } = useStudioSessions();
  const closeTab = useStudioStore((s) => s.closeTab);
  // Track which projectIds have already been reconciled in this page mount.
  // Pruning must happen ONCE per project per mount — re-running on every
  // sessions refetch (e.g. after `useCreateStudioSession` invalidates the
  // cache) races against the just-created tab and prunes it before the
  // refetched list catches up. Discovered live in Stage 3 of qa-regression
  // run on 2026-05-22 (CB-2814 fix self-QA caught the regression).
  const reconciledProjects = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!projectId) return;
    if (!isSuccess) return;
    if (!sessions) return;
    if (reconciledProjects.current.has(projectId)) return;

    // Snapshot persisted tabs at the moment we reconcile — accessed via
    // getState() so this effect does not subscribe to tabsByProject changes
    // (which would re-fire the effect on every closeTab and create a loop).
    const persistedTabs =
      useStudioStore.getState().tabsByProject[projectId] ?? [];
    const liveIds = new Set(sessions.map((s) => s.id));

    for (const tab of persistedTabs) {
      // Skip stub IDs — ephemeral placeholders for sessions still being
      // created server-side; the create-mutation path promotes them in
      // place. Filtered at persist (useStudioStore partialize) anyway.
      if (!isRealId(tab.id)) continue;
      if (!liveIds.has(tab.id)) {
        closeTab(projectId, tab.id);
      }
    }
    reconciledProjects.current.add(projectId);
  }, [projectId, sessions, isSuccess, closeTab]);
}
