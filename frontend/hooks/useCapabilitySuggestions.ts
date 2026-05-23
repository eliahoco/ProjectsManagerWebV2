/**
 * useCapabilitySuggestions — CB-2914 E5.1.2.
 *
 * React Query hook that fetches the top-N ranked capabilities for the
 * Studio chat's current session. Powers the CapabilityRibbon UI and is
 * the same data source the Studio Investigation Engine consumes to
 * auto-pick layer-investigators (per E5.1.1 of the SIE plan).
 *
 * Backend: GET /api/studio/capabilities/suggest
 *   query: session_id, message (optional — falls back to last persisted user msg), top_n
 *   returns: [{ name, kind, description, score, reasons }, ...]
 */

'use client';

import { useQuery } from '@tanstack/react-query';
import { workspaceFetch } from '@/lib/workspaceFetch';
import { useTenant } from '@/contexts/TenantContext';

export interface CapabilitySuggestion {
  name: string;
  kind: 'agent' | 'skill';
  description: string;
  score: number;
  reasons: string[];
}

interface UseCapabilitySuggestionsArgs {
  sessionId: string | null;
  /** Optional in-flight textarea content — server falls back to last user msg when empty. */
  message?: string;
  topN?: number;
  /** Disable while textarea is empty if you want to avoid extra calls. */
  enabled?: boolean;
}

export function useCapabilitySuggestions({
  sessionId,
  message = '',
  topN = 7,
  enabled = true,
}: UseCapabilitySuggestionsArgs) {
  const { workspaceId, tenantId } = useTenant();

  return useQuery<CapabilitySuggestion[]>({
    queryKey: [
      'workspace', workspaceId,
      'studio', 'capabilities', 'suggest',
      sessionId, message, topN,
    ],
    queryFn: async () => {
      if (!sessionId) return [];
      const qs = new URLSearchParams({
        session_id: sessionId,
        top_n: String(topN),
      });
      if (message) qs.set('message', message);
      try {
        return await workspaceFetch<CapabilitySuggestion[]>(
          `/api/studio/capabilities/suggest?${qs}`,
          workspaceId,
          tenantId,
        );
      } catch (err) {
        const status = (err as Error & { status?: number }).status;
        // Backend not yet deployed / endpoint missing -> graceful empty list.
        if (status === 404 || status === 0) return [];
        throw err;
      }
    },
    enabled: enabled && !!sessionId,
    // CB-2914 spec: ribbon refreshes per turn, 5s stale window is enough.
    staleTime: 5_000,
    gcTime: 60_000,
    retry: (failureCount, error) => {
      const status = (error as Error & { status?: number }).status;
      if (status === 404 || status === 422) return false;
      return failureCount < 1;
    },
  });
}
