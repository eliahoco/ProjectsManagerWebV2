/**
 * useStudio — React Query hooks for Studio sessions and messages.
 *
 * All query keys are prefixed ['workspace', workspaceId, 'studio', ...]
 * so the cache is fully scoped per workspace and never bleeds across
 * workspace switches.
 *
 * projectId is read from TenantContext (set via WorkspaceSwitcher). Switching
 * projects invalidates the sessions list because the query key includes
 * projectId: ['workspace', workspaceId, 'studio', 'projects', projectId, 'sessions'].
 *
 * Backend stubs: endpoints return 404 until the backend lands. All hooks
 * handle non-2xx gracefully via React Query's built-in retry + error state.
 * The components receiving these hooks must render skeleton/empty states
 * on isLoading and fallback UI on isError (they will never crash).
 *
 * Endpoints (Phase 0 stub, Phase 1 real):
 *   GET  /api/studio/projects/:projectId/sessions — list all sessions for project
 *   GET  /api/studio/sessions/:id                 — single session detail
 *   POST /api/studio/projects/:projectId/sessions — create new session
 *   GET  /api/studio/sessions/:id/messages        — messages for a session
 *   POST /api/studio/sessions/:id/messages        — send a message (returns 202 + streamUrl)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workspaceFetch } from '@/lib/workspaceFetch';
import { useTenant } from '@/contexts/TenantContext';

// ─── Types ────────────────────────────────────────────────────────────────────

export type SessionStatus = 'active' | 'idle' | 'hibernated' | 'error';

export interface StudioSession {
  id: string;
  title: string;
  status: SessionStatus;
  createdAt: string;
  updatedAt: string;
  messageCount?: number;
}

export type MessageRole = 'user' | 'assistant' | 'tool';

export interface StudioMessage {
  id: string;
  sessionId: string;
  role: MessageRole;
  content: string;
  isStreaming?: boolean;
  createdAt: string;
}

export interface CreateSessionInput {
  title?: string;
}

export interface SendMessageInput {
  content: string;
}

export interface SendMessageResponse {
  messageId: string;
  streamUrl: string;
}

// ─── Session list ─────────────────────────────────────────────────────────────

export function useStudioSessions() {
  const { workspaceId, tenantId, projectId } = useTenant();

  return useQuery<StudioSession[]>({
    queryKey: ['workspace', workspaceId, 'studio', 'projects', projectId, 'sessions'],
    queryFn: async () => {
      try {
        return await workspaceFetch<StudioSession[]>(
          `/api/studio/projects/${projectId}/sessions`,
          workspaceId,
          tenantId,
        );
      } catch (err) {
        // Backend not yet deployed — return empty list gracefully
        const status = (err as Error & { status?: number }).status;
        if (status === 404 || status === 0) return [];
        throw err;
      }
    },
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    // Don't show global error toast for expected 404s during development
    retry: (failureCount, error) => {
      const status = (error as Error & { status?: number }).status;
      if (status === 404 || status === 422) return false;
      return failureCount < 2;
    },
  });
}

// ─── Single session ───────────────────────────────────────────────────────────

export function useStudioSession(sessionId: string | null) {
  const { workspaceId, tenantId } = useTenant();

  return useQuery<StudioSession>({
    queryKey: ['workspace', workspaceId, 'studio', 'sessions', sessionId],
    queryFn: () =>
      workspaceFetch<StudioSession>(
        `/api/studio/sessions/${sessionId}`,
        workspaceId,
        tenantId,
      ),
    enabled: !!sessionId,
    staleTime: 10_000,
    retry: (failureCount, error) => {
      const status = (error as Error & { status?: number }).status;
      if (status === 404) return false;
      return failureCount < 2;
    },
  });
}

// ─── Messages for a session ───────────────────────────────────────────────────

export function useStudioMessages(sessionId: string | null) {
  const { workspaceId, tenantId } = useTenant();

  return useQuery<StudioMessage[]>({
    queryKey: ['workspace', workspaceId, 'studio', 'sessions', sessionId, 'messages'],
    queryFn: async () => {
      try {
        return await workspaceFetch<StudioMessage[]>(
          `/api/studio/sessions/${sessionId}/messages`,
          workspaceId,
          tenantId,
        );
      } catch (err) {
        const status = (err as Error & { status?: number }).status;
        if (status === 404) return [];
        throw err;
      }
    },
    enabled: !!sessionId,
    staleTime: 5_000,
    retry: (failureCount, error) => {
      const status = (error as Error & { status?: number }).status;
      if (status === 404) return false;
      return failureCount < 2;
    },
  });
}

// ─── Create session ───────────────────────────────────────────────────────────

export function useCreateStudioSession() {
  const { workspaceId, tenantId, projectId } = useTenant();
  const queryClient = useQueryClient();

  return useMutation<StudioSession, Error, CreateSessionInput>({
    mutationFn: (input) =>
      workspaceFetch<StudioSession>(
        `/api/studio/projects/${projectId}/sessions`,
        workspaceId,
        tenantId,
        {
          method: 'POST',
          // Pydantic StudioSessionCreate requires both projectId and title.
          // projectId from URL is for routing; backend re-validates against body.
          body: JSON.stringify({
            projectId,
            title: input.title ?? 'New conversation',
          }),
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['workspace', workspaceId, 'studio', 'projects', projectId, 'sessions'],
      });
    },
  });
}

// ─── Send message ─────────────────────────────────────────────────────────────

export function useSendMessage(sessionId: string | null) {
  const { workspaceId, tenantId } = useTenant();
  const queryClient = useQueryClient();

  return useMutation<SendMessageResponse, Error, SendMessageInput>({
    mutationFn: (input) =>
      workspaceFetch<SendMessageResponse>(
        `/api/studio/sessions/${sessionId}/messages`,
        workspaceId,
        tenantId,
        {
          method: 'POST',
          body: JSON.stringify(input),
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [
          'workspace',
          workspaceId,
          'studio',
          'sessions',
          sessionId,
          'messages',
        ],
      });
    },
  });
}
