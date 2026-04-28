/**
 * Agent Registry & Pipeline Config Hooks
 * Provides React Query hooks for agent management and pipeline configuration
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch as apiFetchHttp } from '@/lib/api/api-fetch';

const API_BASE = 'http://localhost:8401/api';

/**
 * Fetch wrapper with error handling
 */
async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await apiFetchHttp(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorData: { message?: string; detail?: string } = {};
    try {
      errorData = await response.json();
    } catch {
      // Response wasn't JSON
    }
    const message = errorData.detail || errorData.message || `Request failed (${response.status})`;
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ============================================
// Types
// ============================================

export interface AgentProfile {
  id: string;
  name: string;
  displayName: string;
  description: string | null;
  agentPath: string;
  capabilities: string[] | null;
  issueTypeAffinity: string[] | null;
  projectPatterns: string[] | null;
  /** "standalone" | "plugin:<name>" */
  source: string;
  isActive: boolean;
  priority: number;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface AgentCreateData {
  name: string;
  displayName?: string;
  description?: string;
  agentPath?: string;
  capabilities?: string[];
  issueTypeAffinity?: string[];
  projectPatterns?: string[];
  isActive?: boolean;
  priority?: number;
}

export interface PipelineConfig {
  id: string;
  projectId: string;
  enabled: boolean;
  defaultAgentId: string | null;
  maxRetries: number;
  verifyEnabled: boolean;
  autoFix: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface PipelineConfigUpdate {
  enabled?: boolean;
  defaultAgentId?: string | null;
  maxRetries?: number;
  verifyEnabled?: boolean;
  autoFix?: boolean;
}

// ============================================
// Agent Hooks
// ============================================

/** Fetch all registered agents */
export function useAgents(activeOnly = false) {
  return useQuery<AgentProfile[]>({
    queryKey: ['agents', activeOnly],
    queryFn: () => {
      const params = activeOnly ? '?active_only=true' : '';
      return apiFetch<AgentProfile[]>(`${API_BASE}/agents${params}`);
    },
    staleTime: 30000,
  });
}

/** Fetch a single agent by ID */
export function useAgent(agentId: string | null) {
  return useQuery<AgentProfile>({
    queryKey: ['agent', agentId],
    queryFn: () => apiFetch<AgentProfile>(`${API_BASE}/agents/${agentId}`),
    enabled: !!agentId,
  });
}

/** Scan agents directory and auto-register */
export function useScanAgents() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (directory?: string) => {
      return apiFetch<AgentProfile[]>(`${API_BASE}/agents/scan`, {
        method: 'POST',
        body: JSON.stringify({ directory: directory || null }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

/** Create or update an agent */
export function useCreateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: AgentCreateData) => {
      return apiFetch<AgentProfile>(`${API_BASE}/agents`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

/** Toggle agent active/inactive */
export function useToggleAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (agentId: string) => {
      return apiFetch<AgentProfile>(`${API_BASE}/agents/${agentId}/toggle`, {
        method: 'PATCH',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

/** Deactivate (soft delete) an agent */
export function useDeactivateAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (agentId: string) => {
      return apiFetch<{ success: boolean }>(`${API_BASE}/agents/${agentId}`, {
        method: 'DELETE',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    },
  });
}

// ============================================
// Pipeline Config Hooks
// ============================================

/** Fetch pipeline config for a project */
export function usePipelineConfig(projectId: string | null) {
  return useQuery<PipelineConfig>({
    queryKey: ['pipeline-config', projectId],
    queryFn: () => apiFetch<PipelineConfig>(`${API_BASE}/pipeline/config/${projectId}`),
    enabled: !!projectId,
    staleTime: 30000,
    retry: false, // Don't retry 404s -- config may not exist yet
  });
}

/** Update pipeline config for a project */
export function useUpdatePipelineConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      config,
    }: {
      projectId: string;
      config: PipelineConfigUpdate;
    }) => {
      return apiFetch<PipelineConfig>(`${API_BASE}/pipeline/config/${projectId}`, {
        method: 'PUT',
        body: JSON.stringify(config),
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pipeline-config', variables.projectId] });
    },
  });
}
