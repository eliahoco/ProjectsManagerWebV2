/**
 * CodeBoard API Hooks
 * Provides React Query hooks for all CodeBoard API operations
 * with error handling and retry logic
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type {
  Issue,
  Project,
  Activity,
  Comment,
  PaginatedResponse,
  CreateIssueData,
  UpdateIssueData,
  IssueStatus
} from '@/types/codeboard';
import { apiFetch as apiFetchHttp } from '@/lib/api/api-fetch';

const API_BASE = '/api/codeboard';

/**
 * Custom error class for API errors
 */
export class APIError extends Error {
  statusCode: number;
  code?: string;
  details?: Record<string, unknown>;

  constructor(message: string, statusCode: number, code?: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'APIError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

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
    let errorData: { message?: string; error?: string; code?: string; details?: Record<string, unknown> } = {};
    try {
      errorData = await response.json();
    } catch {
      // Response wasn't JSON
    }

    const message = errorData.message || errorData.error || getDefaultErrorMessage(response.status);
    throw new APIError(message, response.status, errorData.code, errorData.details);
  }

  // Handle empty responses (204 No Content)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

/**
 * Get user-friendly error message based on status code
 */
function getDefaultErrorMessage(status: number): string {
  switch (status) {
    case 400:
      return 'Invalid request. Please check your input.';
    case 401:
      return 'Please log in to continue.';
    case 403:
      return 'You do not have permission to perform this action.';
    case 404:
      return 'The requested resource was not found.';
    case 409:
      return 'A conflict occurred. Please refresh and try again.';
    case 429:
      return 'Too many requests. Please wait a moment.';
    case 500:
      return 'A server error occurred. Please try again.';
    case 502:
    case 503:
      return 'The server is temporarily unavailable. Please try again.';
    default:
      return 'An unexpected error occurred.';
  }
}

// Fetch projects
export function useProjects() {
  return useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: () => apiFetch<Project[]>(`${API_BASE}/projects`),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
}

// Fetch issues for a project
export function useIssues(projectId: string | null, filters?: {
  status?: string;
  type?: string;
  priority?: string;
  search?: string;
  label?: string;
  breakdownBatchId?: string;
  dateField?: string;
  dateFrom?: string;
  dateTo?: string;
  sortBy?: string;
  sortOrder?: string;
  page?: number;
  pageSize?: number;
  refetchInterval?: number | false;
}) {
  return useQuery<PaginatedResponse<Issue>>({
    queryKey: ['issues', projectId, filters],
    queryFn: async () => {
      if (!projectId) return { items: [], total: 0, page: 1, pageSize: 50, totalPages: 0 };

      const params = new URLSearchParams();
      if (filters?.status) params.set('status', filters.status);
      if (filters?.type) params.set('type', filters.type);
      if (filters?.priority) params.set('priority', filters.priority);
      if (filters?.search) params.set('search', filters.search);
      if (filters?.label) params.set('label', filters.label);
      if (filters?.breakdownBatchId) params.set('breakdownBatchId', filters.breakdownBatchId);
      if (filters?.dateField) params.set('dateField', filters.dateField);
      if (filters?.dateFrom) params.set('dateFrom', filters.dateFrom);
      if (filters?.dateTo) params.set('dateTo', filters.dateTo);
      if (filters?.sortBy) params.set('sortBy', filters.sortBy);
      if (filters?.sortOrder) params.set('sortOrder', filters.sortOrder);
      if (filters?.page) params.set('page', filters.page.toString());
      if (filters?.pageSize) params.set('pageSize', filters.pageSize.toString());

      const url = `${API_BASE}/projects/${projectId}/issues${params.toString() ? `?${params}` : ''}`;
      return apiFetch<PaginatedResponse<Issue>>(url);
    },
    enabled: !!projectId,
    refetchInterval: filters?.refetchInterval,
  });
}

// Fetch single issue
export function useIssue(issueId: string | null) {
  return useQuery<Issue>({
    queryKey: ['issue', issueId],
    queryFn: () => apiFetch<Issue>(`${API_BASE}/issues/${issueId}`),
    enabled: !!issueId,
  });
}

// Fetch activities for an issue
export function useIssueActivities(issueId: string | null, limit = 50) {
  return useQuery<Activity[]>({
    queryKey: ['issue-activities', issueId, limit],
    queryFn: async () => {
      if (!issueId) return [];
      return apiFetch<Activity[]>(`${API_BASE}/issues/${issueId}/activities?limit=${limit}`);
    },
    enabled: !!issueId,
    staleTime: 30000,
  });
}

// Fetch all descendants of an issue (for Feature Execution Panel and cascade moves)
export function useIssueDescendants(issueId: string | null) {
  return useQuery<Issue[]>({
    queryKey: ['issue-descendants', issueId],
    queryFn: async () => {
      if (!issueId) return [];
      return apiFetch<Issue[]>(`${API_BASE}/issues/${issueId}/descendants`);
    },
    enabled: !!issueId,
  });
}

// Search within an issue's descendants with filtering and relevance ranking (CB-1122)
export interface EpicSearchParams {
  search?: string;
  types?: string[];
  statuses?: string[];
  priorities?: string[];
  dateField?: string;
  dateFrom?: string;
  dateTo?: string;
  sortBy?: string;
  sortOrder?: string;
}

export interface EpicSearchResult {
  items: Array<Issue & { relevanceScore: number; isDirectMatch: boolean }>;
  total: number;
  matchCount: number;
}

export function useEpicDescendantSearch(issueId: string | null, params?: EpicSearchParams) {
  return useQuery<EpicSearchResult>({
    queryKey: ['epic-descendant-search', issueId, params],
    queryFn: async () => {
      if (!issueId) return { items: [], total: 0, matchCount: 0 };

      const searchParams = new URLSearchParams();
      if (params?.search) searchParams.set('search', params.search);
      if (params?.types?.length) searchParams.set('type', params.types.join(','));
      if (params?.statuses?.length) searchParams.set('status', params.statuses.join(','));
      if (params?.priorities?.length) searchParams.set('priority', params.priorities.join(','));
      if (params?.dateField) searchParams.set('dateField', params.dateField);
      if (params?.dateFrom) searchParams.set('dateFrom', params.dateFrom);
      if (params?.dateTo) searchParams.set('dateTo', params.dateTo);
      if (params?.sortBy) searchParams.set('sortBy', params.sortBy);
      if (params?.sortOrder) searchParams.set('sortOrder', params.sortOrder);

      const url = `${API_BASE}/issues/${issueId}/descendants/search${searchParams.toString() ? `?${searchParams}` : ''}`;
      return apiFetch<EpicSearchResult>(url);
    },
    enabled: !!issueId,
    staleTime: 10000,
  });
}

// Create issue
export function useCreateIssue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ projectId, data }: { projectId: string; data: CreateIssueData }) => {
      return apiFetch<Issue>(`${API_BASE}/projects/${projectId}/issues`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['issues', variables.projectId] });
    },
  });
}

// Update issue
export function useUpdateIssue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ issueId, data }: { issueId: string; data: UpdateIssueData }) => {
      return apiFetch<Issue>(`${API_BASE}/issues/${issueId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['issues'] });
      queryClient.invalidateQueries({ queryKey: ['issue', data.id] });
    },
  });
}

// Delete issue
export function useDeleteIssue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (issueId: string) => {
      return apiFetch<void>(`${API_BASE}/issues/${issueId}`, {
        method: 'DELETE',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issues'] });
    },
  });
}

// Batch update status (for drag & drop)
export function useBatchUpdateStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ issueIds, status }: { issueIds: string[]; status: IssueStatus }) => {
      return apiFetch<Issue[]>(`${API_BASE}/issues/batch/status`, {
        method: 'POST',
        body: JSON.stringify({ issueIds, status }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issues'] });
    },
  });
}

// ============================================
// Labels Hooks
// ============================================

// Fetch labels for a project
export function useProjectLabels(projectId: string | null) {
  return useQuery<{ labels: string[] }>({
    queryKey: ['project-labels', projectId],
    queryFn: async () => {
      if (!projectId) return { labels: [] };
      return apiFetch<{ labels: string[] }>(`${API_BASE}/projects/${projectId}/labels`);
    },
    enabled: !!projectId,
    staleTime: 30000, // 30 seconds
  });
}

// Batch add labels to issues
export function useBatchAddLabels() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      issueIds,
      labels,
      breakdownBatchId,
    }: {
      issueIds: string[];
      labels: string[];
      breakdownBatchId?: string;
    }) => {
      const params = new URLSearchParams();
      issueIds.forEach(id => params.append('issue_ids', id));
      labels.forEach(label => params.append('labels', label));
      if (breakdownBatchId) params.set('breakdownBatchId', breakdownBatchId);

      return apiFetch<{ success: boolean; updated_count: number }>(
        `${API_BASE}/issues/batch/labels?${params}`,
        { method: 'POST' }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issues'] });
      queryClient.invalidateQueries({ queryKey: ['project-labels'] });
    },
  });
}

// ============================================
// AI & Search Hooks
// ============================================

export interface SuggestedIssue {
  title: string;
  type: string;  // EPIC, STORY, TASK, SUBTASK
  priority: string;
  description?: string;
  storyPoints?: number;
  parentTitle?: string | null;  // For hierarchical structure
  category?: string;  // frontend, backend, database, security, testing
}

export interface SearchResult {
  issue_id?: string;
  key?: string;
  type?: string;
  status?: string;
  document?: string;
  score?: number;
}

// Check AI status
export function useAIStatus() {
  return useQuery<{ available: boolean; model: string | null }>({
    queryKey: ['ai-status'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/ai/status`);
      if (!res.ok) return { available: false, model: null };
      return res.json();
    },
    staleTime: 60000, // 1 minute
  });
}

// AI Feature Breakdown
export function useAIBreakdown() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      title,
      description,
      parentType = 'EPIC',
    }: {
      projectId: string;
      title: string;
      description?: string;
      parentType?: string;
    }) => {
      const res = await fetch(`${API_BASE}/ai/${projectId}/breakdown`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, description, parent_type: parentType }),
      });
      if (!res.ok) throw new Error('Failed to breakdown feature');
      return res.json() as Promise<{
        suggestions: SuggestedIssue[];
        parent_title: string;
        ai_available: boolean;
        original_input?: string;  // Original specification for audit trail
      }>;
    },
  });
}

// AI Bug Detection
export function useAIDetectBug() {
  return useMutation({
    mutationFn: async ({ title, description }: { title: string; description?: string }) => {
      const params = new URLSearchParams({ title });
      if (description) params.set('description', description);

      const res = await fetch(`${API_BASE}/ai/detect-bug?${params}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to detect bug');
      return res.json() as Promise<{
        is_bug: boolean;
        confidence?: number;
        severity?: string;
        reason?: string;
      }>;
    },
  });
}

// AI Generate QA Tasks
export function useAIGenerateQA() {
  return useMutation({
    mutationFn: async ({
      projectId,
      featureTitle,
      featureDescription,
    }: {
      projectId: string;
      featureTitle: string;
      featureDescription?: string;
    }) => {
      const params = new URLSearchParams({ feature_title: featureTitle });
      if (featureDescription) params.set('feature_description', featureDescription);

      const res = await fetch(`${API_BASE}/ai/${projectId}/generate-qa?${params}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to generate QA tasks');
      return res.json() as Promise<{
        tasks: SuggestedIssue[];
        feature_title: string;
        ai_available: boolean;
      }>;
    },
  });
}

// Semantic Search
export function useSemanticSearch(
  projectId: string | null,
  query: string,
  options?: { type?: string; status?: string; enabled?: boolean }
) {
  return useQuery<{ results: SearchResult[]; query: string; total: number }>({
    queryKey: ['semantic-search', projectId, query, options?.type, options?.status],
    queryFn: async () => {
      if (!projectId || !query) return { results: [], query: '', total: 0 };

      const params = new URLSearchParams({ q: query });
      if (options?.type) params.set('type', options.type);
      if (options?.status) params.set('status', options.status);

      const res = await fetch(`${API_BASE}/search/${projectId}?${params}`);
      if (!res.ok) throw new Error('Search failed');
      return res.json();
    },
    enabled: !!(projectId && query && (options?.enabled !== false)),
    staleTime: 10000, // 10 seconds
  });
}

// Find Similar Issues
export function useFindSimilar() {
  return useMutation({
    mutationFn: async ({
      projectId,
      title,
      description,
    }: {
      projectId: string;
      title: string;
      description?: string;
    }) => {
      const params = new URLSearchParams({ title });
      if (description) params.set('description', description);

      const res = await fetch(`${API_BASE}/search/${projectId}/similar?${params}`);
      if (!res.ok) throw new Error('Failed to find similar issues');
      return res.json() as Promise<{ results: SearchResult[]; total: number }>;
    },
  });
}

// ============================================
// Git Hooks
// ============================================

export interface GitCommit {
  hash: string;
  short_hash: string;
  author: string;
  email: string;
  date: string;
  message: string;
  branch?: string;
}

export interface GitBranch {
  name: string;
  is_current: boolean;
  tracking?: string;
  ahead: number;
  behind: number;
}

export interface GitStatus {
  is_repo: boolean;
  branch?: string;
  clean: boolean;
  staged: string[];
  modified: string[];
  untracked: string[];
  ahead: number;
  behind: number;
}

export interface RepoSummary {
  is_repo: boolean;
  branch?: string;
  clean?: boolean;
  changes?: { staged: number; modified: number; untracked: number };
  sync?: { ahead: number; behind: number };
  branches?: string[];
  recent_commits?: Array<{
    hash: string;
    message: string;
    author: string;
    date: string;
  }>;
  remote_url?: string;
}

// Get Git status for a project
export function useGitStatus(projectId: string | null) {
  return useQuery<GitStatus>({
    queryKey: ['git-status', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('No project ID');
      const res = await fetch(`${API_BASE}/git/project/${projectId}/status`);
      if (!res.ok) throw new Error('Failed to fetch git status');
      return res.json();
    },
    enabled: !!projectId,
    staleTime: 30000, // 30 seconds
    refetchInterval: 60000, // 1 minute
  });
}

// Get Git branches for a project
export function useGitBranches(projectId: string | null, limit = 20) {
  return useQuery<GitBranch[]>({
    queryKey: ['git-branches', projectId, limit],
    queryFn: async () => {
      if (!projectId) return [];
      const res = await fetch(`${API_BASE}/git/project/${projectId}/branches?limit=${limit}`);
      if (!res.ok) throw new Error('Failed to fetch branches');
      return res.json();
    },
    enabled: !!projectId,
    staleTime: 60000, // 1 minute
  });
}

// Get Git commits for a project
export function useGitCommits(
  projectId: string | null,
  options?: { branch?: string; limit?: number }
) {
  return useQuery<GitCommit[]>({
    queryKey: ['git-commits', projectId, options?.branch, options?.limit],
    queryFn: async () => {
      if (!projectId) return [];
      const params = new URLSearchParams();
      if (options?.branch) params.set('branch', options.branch);
      if (options?.limit) params.set('limit', options.limit.toString());

      const res = await fetch(`${API_BASE}/git/project/${projectId}/commits?${params}`);
      if (!res.ok) throw new Error('Failed to fetch commits');
      return res.json();
    },
    enabled: !!projectId,
    staleTime: 30000, // 30 seconds
  });
}

// Get repository summary
export function useRepoSummary(projectId: string | null) {
  return useQuery<RepoSummary>({
    queryKey: ['repo-summary', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('No project ID');
      const res = await fetch(`${API_BASE}/git/project/${projectId}/summary`);
      if (!res.ok) throw new Error('Failed to fetch repo summary');
      return res.json();
    },
    enabled: !!projectId,
    staleTime: 30000, // 30 seconds
  });
}

// Find commits related to an issue
export function useIssueCommits(
  projectId: string | null,
  issueKey: string | null,
  limit = 10
) {
  return useQuery<{ issue_key: string; commits: GitCommit[]; total: number }>({
    queryKey: ['issue-commits', projectId, issueKey, limit],
    queryFn: async () => {
      if (!projectId || !issueKey) throw new Error('Missing project or issue');
      const res = await fetch(
        `${API_BASE}/git/project/${projectId}/commits/issue/${issueKey}?limit=${limit}`
      );
      if (!res.ok) throw new Error('Failed to fetch commits for issue');
      return res.json();
    },
    enabled: !!(projectId && issueKey),
    staleTime: 30000, // 30 seconds
  });
}

// ============================================
// Commit Link Hooks
// ============================================

export interface CommitLink {
  id: string;
  issueId: string;
  projectId: string;
  commitHash: string;
  shortHash: string;
  message: string;
  author: string;
  authorEmail?: string;
  committedAt: string;
  linkType: 'MENTIONS' | 'FIXES' | 'CLOSES' | 'IMPLEMENTS';
  autoLinked: boolean;
  triggeredStatusChange: boolean;
  createdAt: string;
}

export interface SyncSettings {
  has_sync_state: boolean;
  total_commits_linked: number;
  total_status_updates: number;
  last_synced_at?: string;
  last_synced_commit?: string;
  auto_sync_enabled: boolean;
  auto_status_update_enabled: boolean;
}

export interface SyncResult {
  success: boolean;
  commits_scanned: number;
  commits_linked: number;
  status_updates: number;
  issues_affected: string[];
  last_commit?: string;
  error?: string;
  message?: string;
}

// Get linked commits for an issue
export function useLinkedCommits(issueId: string | null, limit = 50) {
  return useQuery<CommitLink[]>({
    queryKey: ['linked-commits', issueId, limit],
    queryFn: async () => {
      if (!issueId) return [];
      const res = await fetch(`${API_BASE}/git/issues/${issueId}/linked-commits?limit=${limit}`);
      if (!res.ok) throw new Error('Failed to fetch linked commits');
      return res.json();
    },
    enabled: !!issueId,
    staleTime: 30000,
  });
}

// Get linked commits for a project
export function useProjectLinkedCommits(projectId: string | null, limit = 100) {
  return useQuery<CommitLink[]>({
    queryKey: ['project-linked-commits', projectId, limit],
    queryFn: async () => {
      if (!projectId) return [];
      const res = await fetch(`${API_BASE}/git/project/${projectId}/linked-commits?limit=${limit}`);
      if (!res.ok) throw new Error('Failed to fetch linked commits');
      return res.json();
    },
    enabled: !!projectId,
    staleTime: 30000,
  });
}

// Get sync settings for a project
export function useSyncSettings(projectId: string | null) {
  return useQuery<SyncSettings>({
    queryKey: ['sync-settings', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('No project ID');
      const res = await fetch(`${API_BASE}/git/project/${projectId}/sync/settings`);
      if (!res.ok) throw new Error('Failed to fetch sync settings');
      return res.json();
    },
    enabled: !!projectId,
    staleTime: 60000,
  });
}

// Update sync settings
export function useUpdateSyncSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      settings,
    }: {
      projectId: string;
      settings: { autoSyncEnabled?: boolean; autoStatusUpdateEnabled?: boolean };
    }) => {
      const res = await fetch(`${API_BASE}/git/project/${projectId}/sync/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (!res.ok) throw new Error('Failed to update sync settings');
      return res.json() as Promise<SyncSettings>;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sync-settings', variables.projectId] });
    },
  });
}

// Trigger a sync
export function useSyncProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      forceFullScan = false,
      limit = 100,
    }: {
      projectId: string;
      forceFullScan?: boolean;
      limit?: number;
    }) => {
      const params = new URLSearchParams();
      if (forceFullScan) params.set('force_full_scan', 'true');
      params.set('limit', limit.toString());

      const res = await fetch(`${API_BASE}/git/project/${projectId}/sync?${params}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to sync project');
      return res.json() as Promise<SyncResult>;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['linked-commits'] });
      queryClient.invalidateQueries({ queryKey: ['project-linked-commits', variables.projectId] });
      queryClient.invalidateQueries({ queryKey: ['sync-settings', variables.projectId] });
      queryClient.invalidateQueries({ queryKey: ['issues'] });
    },
  });
}

// Delete a commit link
export function useDeleteCommitLink() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (linkId: string) => {
      const res = await fetch(`${API_BASE}/git/linked-commits/${linkId}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error('Failed to delete commit link');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['linked-commits'] });
      queryClient.invalidateQueries({ queryKey: ['project-linked-commits'] });
    },
  });
}

// ============================================
// Execution Hooks
// ============================================

export interface ExecutionSession {
  session_id: string;
  issue_id: string;
  issue_key: string;
  project_id?: string;
  provider: 'claude_code' | 'local_ai';
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at?: string;
  completed_at?: string;
  output_lines: number;
  // Progress tracking
  progress_percent?: number;
  current_action?: string;
  phase?: string;
  error?: string;
  // Pipeline tracking
  pipeline_stage?: string;  // IMPLEMENT, VERIFY, FIX, RE_VERIFY
  retry_count?: number;
  max_retries?: number;
}

export interface ExecutionOutput {
  session_id: string;
  status: string;
  output: string[];
  total_lines: number;
  exit_code?: number;
  // Progress tracking
  phase?: string;
  progress_percent?: number;
  current_action?: string;
  files_read?: number;
  files_written?: number;
  commands_run?: number;
}

// Start execution for an issue
export function useStartExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      issueId,
      provider,
      executionMode,
      force,
    }: {
      issueId: string;
      provider: 'claude_code' | 'local_ai';
      executionMode?: string;  // 'implement' | 'audit' | 'rewrite'
      force?: boolean;
    }) => {
      const body: Record<string, unknown> = { provider };
      if (executionMode) body.execution_mode = executionMode;
      if (force) body.force = force;

      const res = await fetch(`${API_BASE}/execute/issue/${issueId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to start execution');
      return res.json() as Promise<ExecutionSession>;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['execution', variables.issueId] });
      queryClient.invalidateQueries({ queryKey: ['executions'] });
    },
  });
}

// Get execution status for an issue
export function useExecutionStatus(issueId: string | null) {
  return useQuery<ExecutionSession | null>({
    queryKey: ['execution', issueId],
    queryFn: async () => {
      if (!issueId) return null;
      const res = await fetch(`${API_BASE}/execute/issue/${issueId}`);
      if (!res.ok) return null;
      const data = await res.json();
      return data || null;
    },
    enabled: !!issueId,
    refetchInterval: (query) => {
      // Poll every 2 seconds if running, otherwise stop
      if (query.state.data?.status === 'running') return 2000;
      return false;
    },
  });
}

// Get execution output
export function useExecutionOutput(sessionId: string | null, sinceLine = 0) {
  return useQuery<ExecutionOutput>({
    queryKey: ['execution-output', sessionId, sinceLine],
    queryFn: async () => {
      if (!sessionId) throw new Error('No session ID');
      const res = await fetch(`${API_BASE}/execute/session/${sessionId}/output?since_line=${sinceLine}`);
      if (!res.ok) {
        // Return a special status to indicate session is gone
        if (res.status === 404) {
          return { session_id: sessionId, status: 'not_found', output: [], total_lines: 0 } as ExecutionOutput;
        }
        throw new Error('Failed to get output');
      }
      return res.json();
    },
    enabled: !!sessionId,
    // Poll every 3000ms while running, stop polling once completed/failed/cancelled/not_found
    refetchInterval: (query) => {
      // Stop polling if there's an error
      if (query.state.error) {
        return false;
      }
      const status = query.state.data?.status;
      // Stop polling for terminal states
      if (status === 'completed' || status === 'failed' || status === 'cancelled' || status === 'not_found') {
        return false;
      }
      // Continue polling for running/pending states
      if (status === 'running' || status === 'pending') {
        return 3000;
      }
      // For unknown status (initial load), poll but slower
      return 3000;
    },
    retry: false, // Don't retry on errors
  });
}

// Send input to execution
export function useSendExecutionInput() {
  return useMutation({
    mutationFn: async ({
      sessionId,
      text,
    }: {
      sessionId: string;
      text: string;
    }) => {
      const res = await fetch(`${API_BASE}/execute/session/${sessionId}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error('Failed to send input');
      return res.json();
    },
  });
}

// Stop execution
export function useStopExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (sessionId: string) => {
      const res = await fetch(`${API_BASE}/execute/session/${sessionId}/stop`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to stop execution');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['execution'] });
      queryClient.invalidateQueries({ queryKey: ['executions'] });
    },
  });
}

// Complete execution and mark issue as done
export function useCompleteExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ sessionId, issueId }: { sessionId: string; issueId?: string }) => {
      const params = issueId ? `?issue_id=${issueId}` : '';
      const res = await fetch(`${API_BASE}/execute/session/${sessionId}/complete${params}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to complete execution');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['execution'] });
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      queryClient.invalidateQueries({ queryKey: ['issues'] });
    },
  });
}

// SSE backend URL - connect directly to FastAPI for streaming
const SSE_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8401';

/**
 * SSE hook for real-time execution session updates.
 * Connects directly to the FastAPI backend SSE endpoint.
 */
export function useExecutionSessionsSSE() {
  const [sessions, setSessions] = useState<ExecutionSession[]>([]);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let isMounted = true;

    function connect() {
      // Clean up any existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const eventSource = new EventSource(
        `${SSE_BACKEND_URL}/api/execute/sessions/stream`
      );
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        if (isMounted) {
          setConnected(true);
        }
      };

      eventSource.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const data = JSON.parse(event.data) as ExecutionSession[];
          setSessions(data);
        } catch (e) {
          console.error('[SSE] Failed to parse execution sessions data:', e);
        }
      };

      eventSource.onerror = () => {
        if (!isMounted) return;
        setConnected(false);
        // EventSource auto-reconnects on most errors, but if it's in CLOSED state
        // we need to reconnect manually after a delay
        if (eventSource.readyState === EventSource.CLOSED) {
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMounted) {
              connect();
            }
          }, 3000);
        }
      };
    }

    connect();

    return () => {
      isMounted = false;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, []);

  return { data: sessions, connected };
}

/**
 * List all execution sessions with SSE for real-time updates
 * and polling as a fallback when SSE is disconnected.
 */
export function useExecutionSessions() {
  const sse = useExecutionSessionsSSE();

  // Polling fallback - only active when SSE is disconnected
  const polling = useQuery<ExecutionSession[]>({
    queryKey: ['executions'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/execute/sessions`);
      if (!res.ok) return [];
      return res.json();
    },
    refetchInterval: sse.connected ? false : 5000, // Disable polling when SSE is connected
    enabled: !sse.connected, // Only fetch when SSE is not connected
  });

  return {
    data: sse.connected ? sse.data : polling.data,
    isLoading: !sse.connected && polling.isLoading,
    connected: sse.connected,
  };
}

// ==================== Comments Hooks ====================

// Fetch comments for an issue
export function useComments(issueId: string | null) {
  return useQuery<Comment[]>({
    queryKey: ['comments', issueId],
    queryFn: async () => {
      if (!issueId) throw new Error('No issue ID');
      const res = await fetch(`${API_BASE}/issues/${issueId}/comments`);
      if (!res.ok) throw new Error('Failed to fetch comments');
      return res.json();
    },
    enabled: !!issueId,
  });
}

// Add a comment to an issue
export function useAddComment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ issueId, content }: { issueId: string; content: string }) => {
      const res = await fetch(`${API_BASE}/issues/${issueId}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error('Failed to add comment');
      return res.json();
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['comments', variables.issueId] });
    },
  });
}

// ==================== Documentation Generation ====================

export interface DocumentationResponse {
  issue_id: string;
  issue_key: string;
  documentation: string;
  tasks_documented: number;
  comment_id?: string;
}

/**
 * Hook for real-time feature page data.
 * Combines SSE execution sessions with a derived activeSessionMap
 * keyed by issue_id for O(1) lookups in the tree.
 */
export function useFeatureLiveData(projectId: string | null) {
  const { data: sessions, connected } = useExecutionSessions();

  const activeSessionMap = useMemo(() => {
    const map = new Map<string, ExecutionSession>();
    if (!sessions || !projectId) return map;
    for (const session of sessions) {
      if (
        (session.status === 'running' || session.status === 'pending') &&
        session.project_id === projectId
      ) {
        map.set(session.issue_id, session);
      }
    }
    return map;
  }, [sessions, projectId]);

  return {
    activeSessionMap,
    hasActiveSessions: activeSessionMap.size > 0,
    sseConnected: connected,
    allSessions: sessions || [],
  };
}

// ============================================
// Documentation Hooks (CB-1606)
// ============================================

export type NoteCategory =
  | 'DECISION'
  | 'APPROACH'
  | 'TRADEOFF'
  | 'DEPENDENCY'
  | 'RISK'
  | 'LESSON'
  | 'GENERAL';

export type NoteImportance = 'LOW' | 'MEDIUM' | 'HIGH';

export interface ExecutionSummaryData {
  id: string;
  issueId: string;
  summary: string;
  executedAt: string;
  executionTime: number;
  provider: string;
  model?: string;
  exitCode?: number;
  componentsModified: string; // JSON array
  filesTouched: string; // JSON array
  linesAdded?: number;
  linesRemoved?: number;
  architectureNotes?: string;
  technicalNotes?: string;
  challengesFaced?: string;
  lessonsLearned?: string;
  commitHashes?: string; // JSON array
  docFilePath?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ImplementationNoteData {
  id: string;
  issueId: string;
  title: string;
  content: string;
  category: NoteCategory;
  author: string;
  importance: NoteImportance;
  tags?: string;
  references?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateImplementationNoteData {
  title: string;
  content: string;
  category?: NoteCategory;
  importance?: NoteImportance;
  tags?: string;
  references?: string;
  author?: string;
}

// Fetch execution summaries for an issue
export function useExecutionSummaries(issueId: string | undefined) {
  return useQuery<ExecutionSummaryData[]>({
    queryKey: ['execution-summaries', issueId],
    queryFn: async () => {
      if (!issueId) return [];
      return apiFetch<ExecutionSummaryData[]>(
        `${API_BASE}/issues/${issueId}/documentation`
      );
    },
    enabled: !!issueId,
    staleTime: 30_000,
  });
}

// Fetch implementation notes for an issue
export function useImplementationNotes(issueId: string | undefined) {
  return useQuery<ImplementationNoteData[]>({
    queryKey: ['implementation-notes', issueId],
    queryFn: async () => {
      if (!issueId) return [];
      return apiFetch<ImplementationNoteData[]>(
        `${API_BASE}/issues/${issueId}/documentation/notes`
      );
    },
    enabled: !!issueId,
    staleTime: 30_000,
  });
}

// Create implementation note
export function useCreateImplementationNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      issueId,
      data,
    }: {
      issueId: string;
      data: CreateImplementationNoteData;
    }) => {
      return apiFetch<ImplementationNoteData>(
        `${API_BASE}/issues/${issueId}/documentation/notes`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        }
      );
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['implementation-notes', variables.issueId],
      });
    },
  });
}

// ============================================
// Feature Documentation (CB-2054)
// ============================================

/**
 * T2.1.3 — TypeScript interface mirroring backend FeatureDocumentationResponse.
 * All optional fields nullable to handle partially-populated rows.
 */
export interface FeatureDocumentationData {
  id: string;
  projectId: string;
  featureIssueId: string;
  featureKey: string;
  title: string;
  overview: string;
  requirements: string;
  implementation: string;
  architecture: string;
  /** JSON-encoded string array, e.g. '["TypeScript","FastAPI"]' */
  techStack: string;
  testingStrategy: string;
  totalTasks: number;
  completedTasks: number;
  totalQATasks: number;
  passedQATasks: number;
  failedQATasks: number;
  mdFilePath: string;
  embeddingId: string | null;
  lastIndexedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * T2.1.1 — GET feature documentation for a single FEATURE-type issue.
 * Returns null when the backend responds 404 (not yet generated).
 * Throws on 400 (issue is not FEATURE type) or other errors.
 */
export function useFeatureDocumentation(issueId: string | undefined) {
  return useQuery<FeatureDocumentationData | null>({
    queryKey: ['feature-documentation', issueId],
    queryFn: async () => {
      if (!issueId) return null;
      return apiFetch<FeatureDocumentationData | null>(
        `${API_BASE}/features/${issueId}/documentation`,
      ).catch((err: unknown) => {
        // 404 means not generated yet — return null rather than throwing.
        if (err instanceof APIError && err.statusCode === 404) return null;
        throw err;
      });
    },
    enabled: !!issueId,
    staleTime: 30_000,
  });
}

/**
 * T2.1.2 — POST to generate (or regenerate) feature documentation.
 * Invalidates the feature-documentation query on success so the view
 * automatically refreshes.
 */
export function useGenerateFeatureDocumentation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ issueId }: { issueId: string }) => {
      return apiFetch<FeatureDocumentationData>(
        `${API_BASE}/features/${issueId}/documentation/generate`,
        { method: 'POST' },
      );
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['feature-documentation', variables.issueId],
      });
    },
  });
}

// Generate execution documentation for an Epic/Story
export function useGenerateDocumentation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      issueId,
      includeArchitecture = true,
      includeTaskDetails = true,
    }: {
      issueId: string;
      includeArchitecture?: boolean;
      includeTaskDetails?: boolean;
    }) => {
      const res = await fetch(`${API_BASE}/execute/issue/${issueId}/generate-documentation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          include_architecture: includeArchitecture,
          include_task_details: includeTaskDetails,
        }),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to generate documentation');
      }
      return res.json() as Promise<DocumentationResponse>;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['comments', variables.issueId] });
      queryClient.invalidateQueries({ queryKey: ['issue', variables.issueId] });
      queryClient.invalidateQueries({ queryKey: ['issue-activities', variables.issueId] });
    },
  });
}
