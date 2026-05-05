/**
 * Issue Group React Query Hooks
 *
 * CB-2014 (TASK) → CB-2013 (STORY 5.2 — Group detail page)
 *                 → CB-2009 (EPIC 5 — Groups frontend)
 *                 → CB-1955 (FEATURE — Issue Correlation & Grouping).
 * CB-2015 (TASK) → drag-to-reorder mutation hook lands here too — single
 *                  module for all `['issue-group', groupId]` cache touchers.
 *
 * Surface:
 *   * `useGroup(groupId)`               — GET    /api/groups/{id}
 *   * `useReorderGroupMembers(groupId)` — PATCH  /api/groups/{id}/members/reorder
 *
 * Cache key contract:
 *   `['issue-group', groupId]` — namespaced under `issue-group` (singular)
 *   so a future `['issue-groups', projectId]` list-cache (CB-2010 sidebar)
 *   doesn't collide. Mutations on members/title MUST invalidate
 *   `['issue-group', groupId]` so the detail page picks up the change
 *   without a manual refresh. The reorder mutation does this in
 *   `onSettled` — runs whether the PATCH succeeded (rollback to optimistic
 *   value would lose the server's authoritative position numbers, esp.
 *   for partial-failure / no-op responses) or failed (rollback was already
 *   applied in `onError`, but the cache may have drifted from the
 *   server's view of membership during the inflight window).
 *
 * Path-segment safety:
 *   `groupId` is `encodeURIComponent`-wrapped before insertion into the URL.
 *   Group ids are server-generated UUIDs today (no `/`, `?`, `#`), but
 *   defense-in-depth keeps a future change to id format from silently
 *   re-routing the request.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api/api-client';
import type {
  IssueGroupDetailResponse,
  IssueGroupMembersReorderPayload,
  IssueGroupMembersReorderResponse,
  IssueGroupResponse,
} from '@/types/codeboard';

/**
 * Payload for POST /api/projects/{projectId}/groups (CB-2017 / CB-2019).
 * `memberIssueIds` is optional — backend accepts an empty group; the modal
 * always sends an array (possibly empty) for shape stability.
 */
export interface CreateGroupPayload {
  title: string;
  description?: string;
  memberIssueIds?: string[];
}

const API_BASE = '/api/codeboard';

/**
 * GET /api/groups/{id} — group detail with members + aggregate status.
 *
 * Matches the `useIssue` / `useIssueRelations` shape so the rest of the app
 * can use this hook the same way (`{ data, isLoading, error }`). `enabled`
 * gates on a truthy id so the page can render a loading skeleton during
 * `useParams()` hydration without firing a `/groups/null` request.
 *
 * `staleTime: 30s` matches `useIssueRelations` — the detail panel doesn't
 * re-fetch on every re-mount, but a member-mutation (CB-2015) invalidates
 * this key explicitly to force fresh data.
 */
export function useGroup(groupId: string | null) {
  return useQuery<IssueGroupDetailResponse>({
    queryKey: ['issue-group', groupId],
    queryFn: ({ signal }) => {
      // `enabled` keeps this from firing with a null id, but TypeScript can't
      // narrow across the option-object boundary. Throw rather than cast so
      // a future refactor that drops `enabled` fails loudly instead of
      // hitting `/groups/null`.
      if (!groupId) throw new Error('useGroup: groupId is required');
      // Forward React Query's AbortSignal so unmount-during-flight cancels
      // the request via `apiFetch`'s underlying AbortController. Saves the
      // discarded-cache-write churn on a fast nav-away. (`useIssueRelations`
      // doesn't do this yet — left for a separate cleanup pass; out of
      // CB-2014 scope.)
      return apiFetch<IssueGroupDetailResponse>(
        `${API_BASE}/groups/${encodeURIComponent(groupId)}`,
        { signal },
      );
    },
    enabled: !!groupId,
    staleTime: 30_000,
  });
}

/**
 * PATCH /api/groups/{id}/members/reorder — drag-to-reorder mutation (CB-2015).
 *
 * Why a bound `groupId` factory rather than passing it per-call:
 *   * The component owns the dragged-row state and dispatches a reorder per
 *     drag-end. Binding `groupId` once at hook construction time mirrors how
 *     `useIssue(id)` and `useGroup(id)` already key on a known id; the
 *     caller doesn't have to ferry the id through every `mutate()` call.
 *   * Optimistic-update plumbing (onMutate / onError / onSettled) needs the
 *     groupId in scope for cache key construction. Passing it per-call would
 *     duplicate the encode-and-key work in three places.
 *
 * Payload contract: `{orderedIssueIds}` — the COMPLETE current membership
 * in the new order. The server enforces set equality (400 with
 * `{missing, extra}`) and rejects within-payload duplicates (422). The
 * request shape mirrors the `IssueGroupMembersReorderPayload` type.
 *
 * Optimistic update strategy:
 *   * `onMutate` — snapshot the current cached `members[]` and apply the
 *     new order locally (positions renumbered 1..N). The drag UI shows the
 *     reordered list immediately, before the server round-trip lands. We
 *     also pause concurrent refetches via `cancelQueries` so a re-fetch
 *     mid-drag can't clobber the optimistic state with the pre-drag
 *     snapshot.
 *   * `onError` — restore the snapshot. The component's drag-end handler
 *     also re-renders from the cache, so a single source of truth (cache)
 *     stays consistent with the on-screen list.
 *   * `onSuccess` — write the server's authoritative response into the
 *     cache. The server returns the full members[] in the new order with
 *     embedded IssueSummary projections, so this is a clean atomic swap
 *     (no dropped issue summary fields, no half-typed positions).
 *   * `onSettled` — invalidate the key. Defense-in-depth: if a concurrent
 *     mutation (member add / remove from another tab) raced our reorder,
 *     the invalidate forces a fresh GET so the cache catches up.
 *
 * Aggregate-status freshness:
 *   The detail response embeds `aggregateStatus` (computed on-read by the
 *   backend `compute_group_status` helper). A reorder doesn't change the
 *   set of members, so the aggregate is invariant under reorder — we
 *   therefore preserve the existing `aggregateStatus` block when applying
 *   the optimistic update and trust the server response to refresh it on
 *   success. Skipping a separate aggregate refetch keeps the round-trip
 *   to one PATCH per drag.
 */
export function useReorderGroupMembers(groupId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<
    IssueGroupMembersReorderResponse,
    Error,
    IssueGroupMembersReorderPayload,
    { previous: IssueGroupDetailResponse | undefined }
  >({
    mutationFn: (payload) => {
      // Match useGroup's enabled-gate behavior — a mutate() with no bound
      // groupId is a programming error (the calling component should not
      // render the drag handles when groupId is null). Throw rather than
      // silently no-op so the bug is loud.
      if (!groupId) {
        throw new Error('useReorderGroupMembers: groupId is required');
      }
      return apiFetch<IssueGroupMembersReorderResponse>(
        `${API_BASE}/groups/${encodeURIComponent(groupId)}/members/reorder`,
        {
          method: 'PATCH',
          body: JSON.stringify(payload),
        },
      );
    },
    // Optimistic update: rewrite cache before the request lands.
    onMutate: async (payload) => {
      if (!groupId) return { previous: undefined };
      const queryKey = ['issue-group', groupId] as const;

      // Cancel any outstanding refetch on the same key so a stale GET
      // can't land on top of the optimistic state mid-drag.
      await queryClient.cancelQueries({ queryKey });

      const previous =
        queryClient.getQueryData<IssueGroupDetailResponse>(queryKey);

      if (previous) {
        // Build issueId -> existing-member lookup so we can preserve each
        // member's stable `id` (the IssueGroupMember.id, NOT the issueId)
        // and its embedded `issue` summary across the reorder. The server
        // will overwrite our optimistic positions with its authoritative
        // values on success; the optimistic step only needs to be
        // visually consistent, not byte-equal.
        const byIssueId = new Map(
          previous.members.map((m) => [m.issueId, m]),
        );
        const optimisticMembers = payload.orderedIssueIds
          .map((issueId, index) => {
            const member = byIssueId.get(issueId);
            // If the payload references an issueId we don't have cached
            // (drift between the component's view and the cache), drop
            // it from the optimistic list rather than fabricate a stub.
            // The server will reject the PATCH with VALIDATION_ERROR and
            // `onError` will rollback. Returning `null` then filtering
            // keeps the optimistic state internally consistent (every
            // visible row has a real cached membership).
            if (!member) return null;
            return { ...member, position: index + 1 };
          })
          .filter(
            (m): m is NonNullable<typeof m> => m !== null,
          );

        queryClient.setQueryData<IssueGroupDetailResponse>(queryKey, {
          ...previous,
          // aggregateStatus is invariant under reorder (same member set,
          // same statuses), so preserve the existing block. The server
          // will return the up-to-date aggregate on success and the
          // onSuccess setQueryData below will overwrite it.
          members: optimisticMembers,
        });
      }

      // Return the snapshot for onError to restore.
      return { previous };
    },
    onError: (_err, _payload, context) => {
      if (!groupId) return;
      // Restore the pre-mutation cache. The component re-renders from the
      // cache so the on-screen order also reverts.
      if (context?.previous !== undefined) {
        queryClient.setQueryData<IssueGroupDetailResponse>(
          ['issue-group', groupId],
          context.previous,
        );
      }
    },
    onSuccess: (response) => {
      if (!groupId) return;
      const queryKey = ['issue-group', groupId] as const;
      // Atomic swap: the server's full response replaces members[] with
      // authoritative positions + embedded IssueSummary projections. We
      // keep the existing `aggregateStatus` block from the cache (a
      // reorder doesn't change the set of members, so the aggregate is
      // invariant) — saves a follow-up GET round-trip.
      queryClient.setQueryData<IssueGroupDetailResponse>(
        queryKey,
        (existing) => {
          if (!existing) return existing;
          return {
            ...existing,
            members: response.members,
          };
        },
      );
    },
    onSettled: () => {
      if (!groupId) return;
      // Defense-in-depth refresh. A concurrent mutation from another tab
      // (member add / remove) could leave our cache out of sync with the
      // server even after a successful reorder; the invalidate forces a
      // fresh GET on the next read.
      queryClient.invalidateQueries({
        queryKey: ['issue-group', groupId],
      });
    },
  });
}


/**
 * POST /api/projects/{projectId}/groups — create a new group, optionally
 * with initial members. CB-2017 / CB-2019 (CreateGroupModal entry point).
 *
 * On success: invalidate the project's group list cache so a future
 * sidebar (CB-2010) picks up the new group without manual refresh. The
 * caller's `onSuccess` (passed via `mutateAsync` resolution) typically
 * navigates straight to the detail page (`/codeboard/groups/{id}`).
 */
export function useCreateGroup(projectId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<IssueGroupResponse, Error, CreateGroupPayload>({
    mutationFn: (payload) => {
      if (!projectId) {
        throw new Error('useCreateGroup: projectId is required');
      }
      return apiFetch<IssueGroupResponse>(
        `${API_BASE}/projects/${encodeURIComponent(projectId)}/groups`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      );
    },
    onSuccess: () => {
      if (!projectId) return;
      // Invalidate the per-project group list (CB-2010 sidebar key shape).
      queryClient.invalidateQueries({
        queryKey: ['issue-groups', projectId],
      });
    },
  });
}
