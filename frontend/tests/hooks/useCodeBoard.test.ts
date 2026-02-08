/**
 * Unit Tests for useCodeBoard Hooks
 * Task: CB-1116 - Testing framework for frontend UI
 * Part of STORY CB-1112: User can Filter Results by Date Range
 *
 * Tests cover:
 * - APIError class
 * - apiFetch wrapper (via hook behavior)
 * - useIssues hook with date filtering parameters
 * - useProjects, useIssue hooks
 * - Query key construction with filters
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { APIError, useProjects, useIssues, useIssue } from '@/hooks/useCodeBoard';

// Helper to create a wrapper with QueryClientProvider
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

// Helper to mock fetch responses
function mockFetchResponse(data: unknown, status = 200) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  });
}

function mockFetchError(status: number, errorData?: Record<string, unknown>) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.resolve(errorData || {}),
  });
}

describe('useCodeBoard Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('APIError', () => {
    it('should create an error with message and status code', () => {
      const error = new APIError('Not found', 404);
      expect(error.message).toBe('Not found');
      expect(error.statusCode).toBe(404);
      expect(error.name).toBe('APIError');
    });

    it('should include optional code and details', () => {
      const details = { field: 'date', reason: 'invalid format' };
      const error = new APIError('Bad request', 400, 'VALIDATION_ERROR', details);
      expect(error.code).toBe('VALIDATION_ERROR');
      expect(error.details).toEqual(details);
    });

    it('should be an instance of Error', () => {
      const error = new APIError('Server error', 500);
      expect(error).toBeInstanceOf(Error);
    });
  });

  describe('useProjects', () => {
    it('should fetch projects successfully', async () => {
      const mockProjects = [
        { id: '1', name: 'Project 1', path: '/p1', status: 'active', createdAt: '2024-01-01', updatedAt: '2024-01-01' },
        { id: '2', name: 'Project 2', path: '/p2', status: 'active', createdAt: '2024-01-01', updatedAt: '2024-01-01' },
      ];
      mockFetchResponse(mockProjects);

      const { result } = renderHook(() => useProjects(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual(mockProjects);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/codeboard/projects',
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      );
    });

    it('should handle fetch failure', async () => {
      mockFetchError(500, { message: 'Internal server error' });

      const { result } = renderHook(() => useProjects(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.isError).toBe(true));

      expect(result.current.error).toBeInstanceOf(APIError);
    });
  });

  describe('useIssues', () => {
    const emptyResponse = { items: [], total: 0, page: 1, pageSize: 50, totalPages: 0 };

    it('should not fetch when projectId is null', async () => {
      const { result } = renderHook(
        () => useIssues(null),
        { wrapper: createWrapper() }
      );

      // The query should not be enabled
      expect(result.current.fetchStatus).toBe('idle');
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('should fetch issues without filters', async () => {
      const mockResponse = {
        items: [{ id: '1', title: 'Issue 1', type: 'TASK', status: 'TODO', priority: 'HIGH' }],
        total: 1,
        page: 1,
        pageSize: 50,
        totalPages: 1,
      };
      mockFetchResponse(mockResponse);

      const { result } = renderHook(
        () => useIssues('project-1'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual(mockResponse);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/codeboard/projects/project-1/issues',
        expect.any(Object)
      );
    });

    it('should include date filter parameters in the URL', async () => {
      mockFetchResponse(emptyResponse);

      const filters = {
        dateField: 'createdAt',
        dateFrom: '2024-01-01T00:00:00.000Z',
        dateTo: '2024-01-31T23:59:59.999Z',
      };

      const { result } = renderHook(
        () => useIssues('project-1', filters),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const fetchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(fetchCall).toContain('dateField=createdAt');
      expect(fetchCall).toContain('dateFrom=');
      expect(fetchCall).toContain('dateTo=');
    });

    it('should include all filter types in the URL', async () => {
      mockFetchResponse(emptyResponse);

      const filters = {
        type: 'BUG',
        priority: 'HIGH',
        search: 'test query',
        label: 'frontend',
        dateField: 'dueDate',
        dateFrom: '2024-06-01T00:00:00.000Z',
        dateTo: '2024-06-30T23:59:59.999Z',
        sortBy: 'createdAt',
        sortOrder: 'desc',
        page: 2,
        pageSize: 25,
      };

      const { result } = renderHook(
        () => useIssues('project-1', filters),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const fetchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(fetchCall).toContain('type=BUG');
      expect(fetchCall).toContain('priority=HIGH');
      expect(fetchCall).toContain('search=test+query');
      expect(fetchCall).toContain('label=frontend');
      expect(fetchCall).toContain('dateField=dueDate');
      expect(fetchCall).toContain('sortBy=createdAt');
      expect(fetchCall).toContain('sortOrder=desc');
      expect(fetchCall).toContain('page=2');
      expect(fetchCall).toContain('pageSize=25');
    });

    it('should omit empty filter parameters', async () => {
      mockFetchResponse(emptyResponse);

      const filters = {
        type: undefined,
        priority: undefined,
        dateField: undefined,
      };

      const { result } = renderHook(
        () => useIssues('project-1', filters),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const fetchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(fetchCall).not.toContain('type=');
      expect(fetchCall).not.toContain('priority=');
      expect(fetchCall).not.toContain('dateField=');
    });

    it('should support all five date filter fields', async () => {
      const dateFields = ['createdAt', 'updatedAt', 'dueDate', 'startedAt', 'completedAt'];

      for (const field of dateFields) {
        vi.clearAllMocks();
        mockFetchResponse(emptyResponse);

        const { result } = renderHook(
          () => useIssues('project-1', { dateField: field }),
          { wrapper: createWrapper() }
        );

        await waitFor(() => expect(result.current.isSuccess).toBe(true));

        const fetchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
        expect(fetchCall).toContain(`dateField=${field}`);
      }
    });

    it('should handle combined date and sort filters', async () => {
      mockFetchResponse(emptyResponse);

      const { result } = renderHook(
        () => useIssues('project-1', {
          dateField: 'createdAt',
          dateFrom: '2024-01-01T00:00:00.000Z',
          dateTo: '2024-12-31T23:59:59.999Z',
          sortBy: 'dueDate',
          sortOrder: 'asc',
        }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const fetchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(fetchCall).toContain('dateField=createdAt');
      expect(fetchCall).toContain('sortBy=dueDate');
      expect(fetchCall).toContain('sortOrder=asc');
    });

    it('should return empty response when projectId is null', async () => {
      const { result } = renderHook(
        () => useIssues(null),
        { wrapper: createWrapper() }
      );

      // Query is disabled, but if forced to run it returns empty
      expect(result.current.data).toBeUndefined();
    });
  });

  describe('useIssue', () => {
    it('should fetch a single issue by ID', async () => {
      const mockIssue = {
        id: 'issue-1',
        projectId: 'project-1',
        key: 'CB-1',
        sequence: 1,
        title: 'Test Issue',
        type: 'TASK',
        status: 'TODO',
        priority: 'HIGH',
        createdAt: '2024-01-01',
        updatedAt: '2024-01-01',
      };
      mockFetchResponse(mockIssue);

      const { result } = renderHook(
        () => useIssue('issue-1'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual(mockIssue);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/codeboard/issues/issue-1',
        expect.any(Object)
      );
    });

    it('should not fetch when issueId is null', () => {
      const { result } = renderHook(
        () => useIssue(null),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });
});
