/**
 * AI API functions for CodeBoard
 */

import { apiFetch } from '@/lib/api/api-fetch';

const API_BASE = '/api/codeboard';

export interface BreakdownRequest {
  project_id: string;
  feature_title: string;
  feature_description: string;
  auto_create?: boolean;
}

export interface SuggestedIssue {
  title: string;
  type: string;
  priority: string;
  description?: string;
  storyPoints?: number;
}

export interface BreakdownResponse {
  suggestions: SuggestedIssue[];
  parent_title: string;
  ai_available: boolean;
  issues_created: string[];
  total_tasks: number;
  estimated_hours: number;
}

/**
 * Break down a feature into epics, stories, and tasks using AI
 */
export async function breakdownFeature(request: BreakdownRequest): Promise<BreakdownResponse> {
  const response = await apiFetch(`${API_BASE}/ai/${request.project_id}/breakdown`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      title: request.feature_title,
      description: request.feature_description,
      auto_create: request.auto_create ?? false,
    }),
  });

  if (!response.ok) {
    throw new Error('Failed to breakdown feature');
  }

  const data = await response.json();

  // Transform the response to match the expected interface
  return {
    suggestions: data.suggestions || [],
    parent_title: data.parent_title || request.feature_title,
    ai_available: data.ai_available ?? true,
    issues_created: data.issues_created || [],
    total_tasks: data.suggestions?.length || 0,
    estimated_hours: data.suggestions?.reduce(
      (total: number, s: SuggestedIssue) => total + (s.storyPoints || 0) * 2,
      0
    ) || 0,
  };
}
