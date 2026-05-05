/**
 * Issue Relations React Query Hooks
 *
 * CB-2006 (TASK) → CB-2005 (STORY) → CB-1996 (EPIC) → CB-1955 (FEATURE).
 *
 * Surface:
 *   * `useIssueRelations(issueId)` — GET /api/issues/{id}/relations
 *   * `useAddRelation()`           — POST /api/issues/{id}/relations
 *   * `useAddRelationBulk()`       — POST /api/issues/{id}/relations/bulk
 *   * `useDeleteRelation()`        — DELETE /api/issues/{id}/relations/{relationId}
 *
 * Cache invalidation contract (CB-2006 acceptance):
 *   The backend writes a primary row + companion inverse row per link
 *   (CB-1971), so every mutation MUST invalidate BOTH ends'
 *   `['issue-relations', id]` cache keys — invalidating only the source
 *   would leave the other side's panel stale until next refetch. The
 *   single-create + delete paths know both ids; the bulk path fans out
 *   across every requested target id (created + skipped combined — a
 *   skipped DUPLICATE means the cache is already stale on that side, so
 *   refresh anyway).
 *
 *   We also invalidate `['issue', id]` for both ends. The issue detail
 *   payload doesn't include relations today, but `IssueDetail` panels
 *   render `LinkedIssuesPanel` alongside other detail-derived state and
 *   the task spec calls for "optimistic invalidation of issue detail".
 *   Refreshing the cached detail row keeps any future
 *   `relationsCount` / status-summary fields honest the moment the
 *   relation lands.
 *
 * Compatibility note:
 *   `useCodeBoard.ts` re-exports the previous names
 *   (`useCreateRelation`, `useCreateRelationsBulk`) so existing callers
 *   (AddRelationModal at `frontend/components/codeboard/AddRelationModal.tsx`)
 *   keep importing from one place. New callers should import from this
 *   module.
 *
 * Path-segment safety:
 *   Every dynamic id is `encodeURIComponent`-wrapped before insertion
 *   into the URL. CUIDs (the project's id format) don't contain
 *   `/`, `?`, or `#` today, but defense-in-depth keeps a future change
 *   to id format from silently re-routing the request.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api/api-client';
import type {
  IssueLinkBulkCreatePayload,
  IssueLinkBulkResponse,
  IssueLinkCreatePayload,
  IssueLinkResponse,
  IssueRelationsListResponse,
} from '@/types/codeboard';

const API_BASE = '/api/codeboard';

/**
 * Hard cap on per-mutation invalidation fan-out (defense-in-depth).
 * Mirrors the backend's `_ISSUE_LINK_BULK_MAX_TARGETS` so a buggy or
 * MITM'd response that smuggles a giant target list can't loop us
 * through tens of thousands of cache invalidations. The +1 leaves room
 * for the source id alongside up to 100 targets. The backend rejects
 * over-cap requests at 400, so this code path only runs on a contract
 * violation — the cap exists so the violation degrades gracefully
 * (drop the tail) instead of freezing the renderer.
 */
const MAX_INVALIDATE_FANOUT = 101;

/**
 * Invalidate every cache keyed off a relation that touched `ids`.
 *
 * Called from every mutation. The `ids` set is the primary + companion
 * participant pair (single + delete) or every requested target plus the
 * source (bulk). Centralizing the fan-out here keeps the contract trivial
 * to audit: one place owns "what does a relation mutation need to refresh".
 */
function invalidateRelations(
  queryClient: QueryClient,
  ids: Iterable<string>,
): void {
  // Set membership keeps the per-id work O(1); a 100-target bulk request
  // would otherwise schedule duplicate invalidations for any id repeated
  // by a buggy caller. Skipping `null` / `undefined` defends against the
  // bulk fan-out helper being passed a sparse list.
  //
  // `MAX_INVALIDATE_FANOUT` clamps total work — a hostile/MITM'd response
  // smuggling a 100k-target list would otherwise schedule 200k
  // invalidations and freeze the renderer. The backend caps requests at
  // 100 targets, so this only kicks in on a contract violation; we drop
  // the tail rather than abort, so the source id (always first in the
  // iterable from the call sites below) still gets refreshed.
  const seen = new Set<string>();
  for (const id of ids) {
    if (!id) continue;
    if (seen.has(id)) continue;
    if (seen.size >= MAX_INVALIDATE_FANOUT) break;
    seen.add(id);
    queryClient.invalidateQueries({ queryKey: ['issue-relations', id] });
    queryClient.invalidateQueries({ queryKey: ['issue', id] });
  }
}

/**
 * GET /api/issues/{id}/relations — typed relations rendered by
 * `LinkedIssuesPanel`. Returns `{outbound, inbound}`; each row carries
 * `fromIssue` / `toIssue` summaries so consumers don't fan out a fetch per
 * row.
 *
 * `staleTime` matches the previous useCodeBoard.ts setting (30s) so the
 * panel doesn't re-fetch on every detail re-mount; cache invalidation
 * after a mutation is what guarantees freshness.
 */
export function useIssueRelations(issueId: string | null) {
  return useQuery<IssueRelationsListResponse>({
    queryKey: ['issue-relations', issueId],
    queryFn: () => {
      // `enabled` keeps this from running with a null id, but TypeScript
      // can't narrow across the option-object boundary. Throw rather than
      // cast so a future refactor that drops `enabled` fails loudly
      // instead of firing a request to `/issues/null/relations`.
      if (!issueId) throw new Error('useIssueRelations: issueId is required');
      return apiFetch<IssueRelationsListResponse>(
        `${API_BASE}/issues/${encodeURIComponent(issueId)}/relations`,
      );
    },
    enabled: !!issueId,
    staleTime: 30_000,
  });
}

/**
 * POST /api/issues/{id}/relations — create a typed link from `issueId`
 * to `payload.toIssueId`. Backend writes the primary row + companion
 * inverse in the same transaction (CB-1971), so we invalidate BOTH ends'
 * `['issue-relations', id]` AND `['issue', id]` caches.
 *
 * Errors surface as `APIError` with `code` set per the CB-1971 contract:
 *   * `ALREADY_EXISTS`   — same (from, to, type) already linked
 *   * `CYCLE_DETECTED`   — would close a cycle in BLOCKS / CAUSES
 *   * `VALIDATION_ERROR` — self-link or cross-project
 *   * `NOT_FOUND`        — either source or target gone
 *
 * Callers map these via `AddRelationModal:mapRelationError`.
 */
export function useAddRelation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      issueId,
      payload,
    }: {
      issueId: string;
      payload: IssueLinkCreatePayload;
    }) =>
      apiFetch<IssueLinkResponse>(
        `${API_BASE}/issues/${encodeURIComponent(issueId)}/relations`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      ),
    onSuccess: (_data, variables) => {
      invalidateRelations(queryClient, [
        variables.issueId,
        variables.payload.toIssueId,
      ]);
    },
  });
}

/**
 * POST /api/issues/{id}/relations/bulk — same primary+companion write
 * fan-out as the single-create path, for up to `_ISSUE_LINK_BULK_MAX_TARGETS`
 * targets in one transaction (default 100, enforced server-side). Backend
 * silently skips DUPLICATE / CYCLE candidates and returns
 * `{created, skipped}`; consumers render `skipped` inline.
 *
 * Cache fan-out invalidates the source AND every requested target id —
 * including those skipped as DUPLICATE, since the local cache may already
 * be inconsistent with the DB (which is precisely *why* the row was a
 * duplicate). Skipping invalidation there would let the inconsistency
 * persist until the next manual refresh.
 */
export function useAddRelationBulk() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      issueId,
      payload,
    }: {
      issueId: string;
      payload: IssueLinkBulkCreatePayload;
    }) =>
      apiFetch<IssueLinkBulkResponse>(
        `${API_BASE}/issues/${encodeURIComponent(issueId)}/relations/bulk`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      ),
    onSuccess: (_data, variables) => {
      invalidateRelations(queryClient, [
        variables.issueId,
        ...variables.payload.toIssueIds,
      ]);
    },
  });
}

/**
 * DELETE /api/issues/{issueId}/relations/{relationId} — remove a typed
 * relation. Backend deletes the primary AND companion row in one txn
 * (CB-1974), so a successful delete *removes* both directions of the
 * link — same fan-out guarantee as create.
 *
 * The caller passes `otherIssueId` so we can fan invalidations to the
 * other end without re-fetching `['issue-relations', issueId]` first to
 * learn which row it was. The id is optional for forward compat — if a
 * future caller doesn't have it on hand we still invalidate the source
 * side; the other side's panel will refresh on its next natural fetch.
 *
 * Errors surface as `APIError`:
 *   * 404 NOT_FOUND — relation gone, or issueId not a participant.
 */
export function useDeleteRelation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      issueId,
      relationId,
    }: {
      issueId: string;
      relationId: string;
      // `otherIssueId` is read in `onSuccess` only; declaring it here so
      // the mutation typing accepts it as part of `variables`.
      otherIssueId?: string;
    }) =>
      apiFetch<{ deleted: number }>(
        `${API_BASE}/issues/${encodeURIComponent(issueId)}/relations/${encodeURIComponent(relationId)}`,
        { method: 'DELETE' },
      ),
    onSuccess: (_data, variables) => {
      const ids: string[] = [variables.issueId];
      if (variables.otherIssueId) ids.push(variables.otherIssueId);
      invalidateRelations(queryClient, ids);
    },
  });
}
