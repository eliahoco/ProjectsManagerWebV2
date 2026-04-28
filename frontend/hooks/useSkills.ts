/**
 * AI Skill Profiles Hooks
 * Provides React Query hooks for skill management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch as apiFetchHttp } from '@/lib/api/api-fetch';

const API_BASE = 'http://localhost:8401/api';

/**
 * Fetch wrapper with error handling — mirrors useAgents.ts pattern
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

export interface SkillProfile {
  id: string;
  name: string;
  displayName: string;
  description: string | null;
  skillPath: string;
  /** Backend deserializes the JsonList TypeDecorator and hands a real array over the wire. */
  capabilities: string[] | null;
  contextFork: boolean;
  agentRef: string | null;
  source: string;
  isActive: boolean;
  priority: number;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface SkillScanResult {
  count: number;
  skills: SkillProfile[];
}

/** Safely parse the JSON-encoded capabilities field into a string array. */
export function parseCapabilities(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.map(String);
    return [];
  } catch {
    return [];
  }
}

// ============================================
// Skill Hooks
// ============================================

/** Fetch all registered skills */
export function useSkills(activeOnly = false) {
  return useQuery<SkillProfile[]>({
    queryKey: ['skills', activeOnly],
    queryFn: () => {
      const params = activeOnly ? '?active_only=true' : '?active_only=false';
      return apiFetch<SkillProfile[]>(`${API_BASE}/skills${params}`);
    },
    staleTime: 30000,
  });
}

/** Fetch a single skill by ID */
export function useSkill(skillId: string | null) {
  return useQuery<SkillProfile>({
    queryKey: ['skill', skillId],
    queryFn: () => apiFetch<SkillProfile>(`${API_BASE}/skills/${skillId}`),
    enabled: !!skillId,
  });
}

/** Scan skills directories and auto-register */
export function useScanSkills() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      return apiFetch<SkillScanResult>(`${API_BASE}/skills/scan`, {
        method: 'POST',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
  });
}

/** Toggle skill active/inactive */
export function useToggleSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (skillId: string) => {
      return apiFetch<SkillProfile>(`${API_BASE}/skills/${skillId}/toggle`, {
        method: 'PATCH',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
  });
}

/** Soft-delete a skill (sets isActive=false) */
export function useDeleteSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (skillId: string) => {
      return apiFetch<void>(`${API_BASE}/skills/${skillId}`, {
        method: 'DELETE',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
  });
}
