/**
 * useBacklog — React Query hooks for the Studio Backlog feature.
 *
 * All query keys prefixed ['workspace', workspaceId, 'backlog', projectId, ...]
 * for workspace- and project-scoped cache isolation. Switching projects via
 * WorkspaceSwitcher causes the query keys to change, correctly invalidating
 * the backlog cache for the previous project.
 *
 * projectId is read from TenantContext (set via WorkspaceSwitcher).
 *
 * 10-second polling keeps the list live without requiring SSE for backlog.
 *
 * Endpoints (Phase 0 stub):
 *   GET   /api/backlog/items           — list items (with filter params)
 *   POST  /api/backlog/items           — create item
 *   PATCH /api/backlog/items/:id       — update item
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workspaceFetch } from '@/lib/workspaceFetch';
import { useTenant } from '@/contexts/TenantContext';

// ─── Types ────────────────────────────────────────────────────────────────────

export type BacklogPriority = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type BacklogStatus =
  | 'DRAFT'
  | 'READY'
  | 'IN_PROGRESS'
  | 'DONE'
  | 'CANCELLED';

export interface BacklogItem {
  id: string;
  title: string;
  description?: string;
  priority: BacklogPriority;
  status: BacklogStatus;
  owner?: string;
  tags?: string[];
  studioSessionId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface BacklogFilters {
  status?: BacklogStatus;
  priority?: BacklogPriority;
  search?: string;
  tag?: string;
}

export interface CreateBacklogItemInput {
  title: string;
  description?: string;
  priority?: BacklogPriority;
  status?: BacklogStatus;
  tags?: string[];
}

export type UpdateBacklogItemInput = Partial<Omit<BacklogItem, 'id' | 'createdAt' | 'updatedAt'>>;

// ─── List backlog items ───────────────────────────────────────────────────────

export function useBacklogItems(filters: BacklogFilters = {}) {
  const { workspaceId, tenantId, projectId } = useTenant();

  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.priority) params.set('priority', filters.priority);
  if (filters.search) params.set('search', filters.search);
  if (filters.tag) params.set('tag', filters.tag);

  const queryString = params.toString();
  const path = `/api/backlog/items${queryString ? `?${queryString}` : ''}`;

  return useQuery<BacklogItem[]>({
    queryKey: ['workspace', workspaceId, 'backlog', projectId, filters],
    queryFn: async () => {
      try {
        return await workspaceFetch<BacklogItem[]>(path, workspaceId, tenantId);
      } catch (err) {
        const status = (err as Error & { status?: number }).status;
        // Backend not deployed yet — return empty list gracefully
        if (status === 404 || status === 0) return [];
        throw err;
      }
    },
    staleTime: 10_000,
    refetchInterval: 10_000,
    retry: (failureCount, error) => {
      const status = (error as Error & { status?: number }).status;
      if (status === 404 || status === 422) return false;
      return failureCount < 2;
    },
  });
}

// ─── Create backlog item ──────────────────────────────────────────────────────

export function useCreateBacklogItem() {
  const { workspaceId, tenantId, projectId } = useTenant();
  const queryClient = useQueryClient();

  return useMutation<BacklogItem, Error, CreateBacklogItemInput>({
    mutationFn: (input) =>
      workspaceFetch<BacklogItem>('/api/backlog/items', workspaceId, tenantId, {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['workspace', workspaceId, 'backlog', projectId],
      });
    },
  });
}

// ─── Update backlog item ──────────────────────────────────────────────────────

export function useUpdateBacklogItem() {
  const { workspaceId, tenantId, projectId } = useTenant();
  const queryClient = useQueryClient();

  return useMutation<
    BacklogItem,
    Error,
    { id: string; data: UpdateBacklogItemInput }
  >({
    mutationFn: ({ id, data }) =>
      workspaceFetch<BacklogItem>(
        `/api/backlog/items/${id}`,
        workspaceId,
        tenantId,
        {
          method: 'PATCH',
          body: JSON.stringify(data),
        },
      ),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({
        queryKey: ['workspace', workspaceId, 'backlog', projectId],
      });
      queryClient.invalidateQueries({
        queryKey: ['workspace', workspaceId, 'backlog', projectId, id],
      });
    },
  });
}
