/**
 * Unit tests for useIssueRelations hooks (CB-2006).
 *
 * Coverage:
 *   - useIssueRelations: fetches relations, disabled when issueId is null,
 *     URL-encodes the path segment, surfaces APIError on non-2xx
 *   - useAddRelation: posts payload, invalidates BOTH ends'
 *     ['issue-relations', id] AND ['issue', id] caches
 *   - useAddRelation: surfaces backend error code (ALREADY_EXISTS) so
 *     consumers can branch on it
 *   - useAddRelationBulk: posts to /bulk, invalidates source + every
 *     requested target id (created + skipped combined)
 *   - useDeleteRelation: deletes by id, invalidates both ends when
 *     otherIssueId is provided
 *   - useDeleteRelation: skips otherIssueId fan-out when omitted
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import {
  useIssueRelations,
  useAddRelation,
  useAddRelationBulk,
  useDeleteRelation,
} from '@/hooks/useIssueRelations';
import { APIError } from '@/hooks/useCodeBoard';
import type {
  IssueLinkResponse,
  IssueRelationsListResponse,
  IssueLinkBulkResponse,
} from '@/types/codeboard';

// ---- helpers --------------------------------------------------------------

function createWrapper(): {
  wrapper: ({ children }: { children: React.ReactNode }) => React.ReactElement;
  queryClient: QueryClient;
} {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  }
  return { wrapper: Wrapper, queryClient };
}

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

const SOURCE_ID = 'issue-source';
const TARGET_ID = 'issue-target';

const sampleLink: IssueLinkResponse = {
  id: 'link-1',
  fromIssueId: SOURCE_ID,
  toIssueId: TARGET_ID,
  linkType: 'RELATES_TO',
  createdAt: '2026-05-01T10:00:00Z',
};

const sampleRelations: IssueRelationsListResponse = {
  outbound: [sampleLink],
  inbound: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useIssueRelations', () => {
  it('fetches relations for the given issue id', async () => {
    mockFetchResponse(sampleRelations);
    const { wrapper } = createWrapper();

    const { result } = renderHook(() => useIssueRelations(SOURCE_ID), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(sampleRelations);
    expect(global.fetch).toHaveBeenCalledWith(
      `/api/codeboard/issues/${SOURCE_ID}/relations`,
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      }),
    );
  });

  it('does not fetch when issueId is null', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIssueRelations(null), { wrapper });

    expect(result.current.fetchStatus).toBe('idle');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('URL-encodes the issue id (defense-in-depth path segment)', async () => {
    mockFetchResponse(sampleRelations);
    const { wrapper } = createWrapper();
    const weirdId = 'a/b?c#d';

    const { result } = renderHook(() => useIssueRelations(weirdId), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/codeboard/issues/a%2Fb%3Fc%23d/relations',
      expect.any(Object),
    );
  });

  it('surfaces APIError on non-2xx with backend code/details', async () => {
    mockFetchError(404, {
      message: 'Issue not found',
      code: 'NOT_FOUND',
      details: { issueId: 'gone' },
    });
    const { wrapper } = createWrapper();

    const { result } = renderHook(() => useIssueRelations('gone'), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));

    const err = result.current.error;
    expect(err).toBeInstanceOf(APIError);
    expect((err as APIError).statusCode).toBe(404);
    expect((err as APIError).code).toBe('NOT_FOUND');
    expect((err as APIError).details).toEqual({ issueId: 'gone' });
  });
});

describe('useAddRelation', () => {
  it('posts the payload and invalidates both ends + issue detail', async () => {
    mockFetchResponse(sampleLink, 201);
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddRelation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        issueId: SOURCE_ID,
        payload: { toIssueId: TARGET_ID, linkType: 'RELATES_TO' },
      });
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/api/codeboard/issues/${SOURCE_ID}/relations`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          toIssueId: TARGET_ID,
          linkType: 'RELATES_TO',
        }),
      }),
    );

    // Both relation caches AND both issue-detail caches refresh.
    const calledKeys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calledKeys).toContainEqual(['issue-relations', SOURCE_ID]);
    expect(calledKeys).toContainEqual(['issue-relations', TARGET_ID]);
    expect(calledKeys).toContainEqual(['issue', SOURCE_ID]);
    expect(calledKeys).toContainEqual(['issue', TARGET_ID]);
  });

  it('surfaces APIError with backend error code on conflict', async () => {
    mockFetchError(409, {
      message: 'Already linked',
      code: 'ALREADY_EXISTS',
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAddRelation(), { wrapper });

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({
          issueId: SOURCE_ID,
          payload: { toIssueId: TARGET_ID, linkType: 'RELATES_TO' },
        });
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(APIError);
    expect((caught as APIError).statusCode).toBe(409);
    expect((caught as APIError).code).toBe('ALREADY_EXISTS');
  });
});

describe('useAddRelationBulk', () => {
  it('posts to /bulk and invalidates source + every requested target', async () => {
    const bulkResponse: IssueLinkBulkResponse = {
      created: [sampleLink],
      skipped: [{ toIssueId: 'issue-skip', reason: 'DUPLICATE' }],
    };
    mockFetchResponse(bulkResponse, 201);
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddRelationBulk(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        issueId: SOURCE_ID,
        payload: {
          toIssueIds: [TARGET_ID, 'issue-skip'],
          linkType: 'BLOCKS',
        },
      });
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/api/codeboard/issues/${SOURCE_ID}/relations/bulk`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          toIssueIds: [TARGET_ID, 'issue-skip'],
          linkType: 'BLOCKS',
        }),
      }),
    );

    const calledKeys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    // Source + both targets (created AND skipped) get the relations cache
    // AND the issue-detail cache refreshed.
    expect(calledKeys).toContainEqual(['issue-relations', SOURCE_ID]);
    expect(calledKeys).toContainEqual(['issue-relations', TARGET_ID]);
    expect(calledKeys).toContainEqual(['issue-relations', 'issue-skip']);
    expect(calledKeys).toContainEqual(['issue', SOURCE_ID]);
    expect(calledKeys).toContainEqual(['issue', TARGET_ID]);
    expect(calledKeys).toContainEqual(['issue', 'issue-skip']);
  });

  it('clamps invalidation fan-out at MAX_INVALIDATE_FANOUT (defense-in-depth vs hostile/MITM response)', async () => {
    // Synthesize a payload over the backend cap. Request still goes
    // through (the test mocks the network); the assertion is that the
    // hook's fan-out caps total invalidations at 101 distinct ids
    // (source + 100 targets) regardless of what the caller passes.
    const tooManyTargets = Array.from({ length: 200 }, (_, i) => `t-${i}`);
    const bulkResponse: IssueLinkBulkResponse = {
      created: [sampleLink],
      skipped: [],
    };
    mockFetchResponse(bulkResponse, 201);
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddRelationBulk(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        issueId: SOURCE_ID,
        payload: { toIssueIds: tooManyTargets, linkType: 'RELATES_TO' },
      });
    });

    // Each id touches 2 cache slots (['issue-relations', id] + ['issue', id]).
    // Cap is 101 distinct ids → at most 202 invalidate calls. Source id
    // (first in the iterable) MUST be in the set.
    const distinctIds = new Set<string>();
    for (const call of invalidateSpy.mock.calls) {
      const key = call[0]?.queryKey as unknown[] | undefined;
      if (key && (key[0] === 'issue-relations' || key[0] === 'issue')) {
        distinctIds.add(String(key[1]));
      }
    }
    expect(distinctIds.size).toBeLessThanOrEqual(101);
    expect(distinctIds.has(SOURCE_ID)).toBe(true);
  });

  it('dedupes duplicate target ids in the invalidation fan-out', async () => {
    const bulkResponse: IssueLinkBulkResponse = {
      created: [sampleLink],
      skipped: [],
    };
    mockFetchResponse(bulkResponse, 201);
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useAddRelationBulk(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        issueId: SOURCE_ID,
        // Caller passes the same id twice — buggy upstream caller, but the
        // hook should still only invalidate once per id (set membership).
        payload: {
          toIssueIds: [TARGET_ID, TARGET_ID],
          linkType: 'RELATES_TO',
        },
      });
    });

    const targetCalls = invalidateSpy.mock.calls.filter((c) => {
      const key = c[0]?.queryKey as unknown[] | undefined;
      return key?.[0] === 'issue-relations' && key?.[1] === TARGET_ID;
    });
    expect(targetCalls).toHaveLength(1);
  });
});

describe('useDeleteRelation', () => {
  it('deletes by id and invalidates both ends when otherIssueId is provided', async () => {
    mockFetchResponse({ deleted: 2 });
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useDeleteRelation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        issueId: SOURCE_ID,
        relationId: 'link-1',
        otherIssueId: TARGET_ID,
      });
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/api/codeboard/issues/${SOURCE_ID}/relations/link-1`,
      expect.objectContaining({ method: 'DELETE' }),
    );

    const calledKeys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calledKeys).toContainEqual(['issue-relations', SOURCE_ID]);
    expect(calledKeys).toContainEqual(['issue-relations', TARGET_ID]);
    expect(calledKeys).toContainEqual(['issue', SOURCE_ID]);
    expect(calledKeys).toContainEqual(['issue', TARGET_ID]);
  });

  it('skips otherIssueId fan-out when omitted', async () => {
    mockFetchResponse({ deleted: 2 });
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useDeleteRelation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        issueId: SOURCE_ID,
        relationId: 'link-1',
      });
    });

    const calledKeys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(calledKeys).toContainEqual(['issue-relations', SOURCE_ID]);
    expect(calledKeys).toContainEqual(['issue', SOURCE_ID]);
    // No invalidations keyed off any `target`-shaped id.
    const otherTouches = invalidateSpy.mock.calls.filter((c) => {
      const key = c[0]?.queryKey as unknown[] | undefined;
      return (
        (key?.[0] === 'issue-relations' || key?.[0] === 'issue') &&
        key?.[1] !== SOURCE_ID
      );
    });
    expect(otherTouches).toHaveLength(0);
  });

  it('surfaces APIError 404 when the relation is gone', async () => {
    mockFetchError(404, { message: 'Relation not found', code: 'NOT_FOUND' });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDeleteRelation(), { wrapper });

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({
          issueId: SOURCE_ID,
          relationId: 'gone',
        });
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(APIError);
    expect((caught as APIError).statusCode).toBe(404);
    expect((caught as APIError).code).toBe('NOT_FOUND');
  });
});
