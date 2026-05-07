/**
 * Unit tests for useReorderGroupMembers (CB-2015).
 *
 * Coverage:
 *   - PATCH to /api/codeboard/groups/{id}/members/reorder with payload
 *   - Optimistic update: cache reflects new order before request lands
 *   - onSuccess: cache replaced with server response.members
 *   - onError: cache rolls back to pre-mutation snapshot
 *   - groupId path-segment is URL-encoded (defense-in-depth)
 *   - Surfaces APIError with backend `code` so consumers can branch
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useReorderGroupMembers } from '@/hooks/useGroups';
import { APIError } from '@/lib/api/api-client';
import type {
  IssueGroupDetailResponse,
  IssueGroupMembersReorderResponse,
} from '@/types/codeboard';

// ---- helpers --------------------------------------------------------------

function createWrapper(): {
  wrapper: ({ children }: { children: React.ReactNode }) => React.ReactElement;
  queryClient: QueryClient;
} {
  // gcTime: Infinity — without an active useQuery observer the cache row
  // would be garbage-collected at gcTime=0 between setQueryData() and the
  // mutation's onMutate, breaking the optimistic-update assertions. The
  // production caller (the page mounts useGroup as an observer) doesn't
  // hit this; the test does because we drive the mutation in isolation.
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
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

const GROUP_ID = 'grp-1';

function makeMember(
  id: string,
  issueId: string,
  position: number,
  status = 'BACKLOG',
) {
  return {
    id,
    groupId: GROUP_ID,
    issueId,
    position,
    createdAt: '2026-05-01T10:00:00Z',
    issue: {
      id: issueId,
      key: `CB-${position}`,
      title: `Issue ${position}`,
      status,
    },
  };
}

function makeDetail(
  members = [
    makeMember('m1', 'i1', 1),
    makeMember('m2', 'i2', 2),
    makeMember('m3', 'i3', 3),
  ],
): IssueGroupDetailResponse {
  return {
    id: GROUP_ID,
    projectId: 'proj-1',
    title: 'Test Group',
    description: null,
    createdAt: '2026-05-01T10:00:00Z',
    updatedAt: '2026-05-01T10:00:00Z',
    members,
    aggregateStatus: {
      statusBreakdown: { BACKLOG: 3 },
      completionPercent: 0,
      dominantStatus: 'BACKLOG',
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---- tests ----------------------------------------------------------------

describe('useReorderGroupMembers', () => {
  it('PATCHes the reorder endpoint with orderedIssueIds payload', async () => {
    const response: IssueGroupMembersReorderResponse = {
      reordered: 2,
      members: [
        makeMember('m3', 'i3', 1),
        makeMember('m2', 'i2', 2),
        makeMember('m1', 'i1', 3),
      ],
    };
    mockFetchResponse(response);
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(['issue-group', GROUP_ID], makeDetail());

    const { result } = renderHook(() => useReorderGroupMembers(GROUP_ID), {
      wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        orderedIssueIds: ['i3', 'i2', 'i1'],
      });
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/api/codeboard/groups/${GROUP_ID}/members/reorder`,
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ orderedIssueIds: ['i3', 'i2', 'i1'] }),
      }),
    );
  });

  it('applies optimistic order to the cache before the request resolves', async () => {
    // Don't resolve until we say so — verifies optimistic-update timing.
    let resolveFetch!: (v: unknown) => void;
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((res) => {
        resolveFetch = res;
      }),
    );

    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(['issue-group', GROUP_ID], makeDetail());

    const { result } = renderHook(() => useReorderGroupMembers(GROUP_ID), {
      wrapper,
    });

    act(() => {
      result.current.mutate({ orderedIssueIds: ['i3', 'i2', 'i1'] });
    });

    // Optimistic update should have hit the cache synchronously after
    // onMutate runs — wait for it.
    await waitFor(() => {
      const cached = queryClient.getQueryData<IssueGroupDetailResponse>([
        'issue-group',
        GROUP_ID,
      ]);
      expect(cached?.members.map((m) => m.issueId)).toEqual([
        'i3',
        'i2',
        'i1',
      ]);
      expect(cached?.members.map((m) => m.position)).toEqual([1, 2, 3]);
    });

    // Resolve so the test cleans up.
    resolveFetch({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          reordered: 2,
          members: [
            makeMember('m3', 'i3', 1),
            makeMember('m2', 'i2', 2),
            makeMember('m1', 'i1', 3),
          ],
        }),
    });
  });

  it('replaces cache.members with the server response on success', async () => {
    // Server returns a slightly different shape (e.g. an updated status on
    // one of the members) — the optimistic state should be replaced
    // wholesale.
    const serverMembers = [
      makeMember('m3', 'i3', 1, 'IN_PROGRESS'),
      makeMember('m2', 'i2', 2),
      makeMember('m1', 'i1', 3),
    ];
    mockFetchResponse({ reordered: 2, members: serverMembers });

    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(['issue-group', GROUP_ID], makeDetail());

    const { result } = renderHook(() => useReorderGroupMembers(GROUP_ID), {
      wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        orderedIssueIds: ['i3', 'i2', 'i1'],
      });
    });

    // Settle hook re-fetch (none mocked — should remain at server response).
    await waitFor(() => {
      const cached = queryClient.getQueryData<IssueGroupDetailResponse>([
        'issue-group',
        GROUP_ID,
      ]);
      expect(cached?.members[0].issue?.status).toBe('IN_PROGRESS');
    });
  });

  it('rolls back the cache on error', async () => {
    // Pre-populate cache with original order, then mock a 400 from the
    // server. The hook should restore the cached snapshot on error.
    mockFetchError(400, {
      message: 'orderedIssueIds must equal the current member set exactly',
      code: 'VALIDATION_ERROR',
      details: { groupId: GROUP_ID, missing: ['i3'], extra: [] },
    });

    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(['issue-group', GROUP_ID], makeDetail());

    const { result } = renderHook(() => useReorderGroupMembers(GROUP_ID), {
      wrapper,
    });

    await act(async () => {
      try {
        await result.current.mutateAsync({
          orderedIssueIds: ['i2', 'i1'], // missing i3
        });
      } catch {
        // expected — we just want the rollback to fire.
      }
    });

    const cached = queryClient.getQueryData<IssueGroupDetailResponse>([
      'issue-group',
      GROUP_ID,
    ]);
    // Original order intact.
    expect(cached?.members.map((m) => m.issueId)).toEqual(['i1', 'i2', 'i3']);
    expect(cached?.members.map((m) => m.position)).toEqual([1, 2, 3]);
  });

  it('surfaces APIError with backend code so consumers can branch', async () => {
    mockFetchError(400, {
      message: 'orderedIssueIds must equal the current member set exactly',
      code: 'VALIDATION_ERROR',
      details: { groupId: GROUP_ID, missing: ['i3'], extra: [] },
    });

    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(['issue-group', GROUP_ID], makeDetail());

    const { result } = renderHook(() => useReorderGroupMembers(GROUP_ID), {
      wrapper,
    });

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({
          orderedIssueIds: ['i2', 'i1'],
        });
      } catch (err) {
        caught = err;
      }
    });

    expect(caught).toBeInstanceOf(APIError);
    expect((caught as APIError).code).toBe('VALIDATION_ERROR');
    expect((caught as APIError).statusCode).toBe(400);
    expect((caught as APIError).details).toEqual({
      groupId: GROUP_ID,
      missing: ['i3'],
      extra: [],
    });
  });

  it('URL-encodes the groupId path segment', async () => {
    // Group ids are UUIDs today (no special chars), but a future change
    // mustn't silently re-route via an unescaped slash.
    mockFetchResponse({ reordered: 0, members: [] });

    const weirdGroupId = 'grp/with slash';
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(
      ['issue-group', weirdGroupId],
      makeDetail([makeMember('m1', 'i1', 1)]),
    );

    const { result } = renderHook(
      () => useReorderGroupMembers(weirdGroupId),
      { wrapper },
    );

    await act(async () => {
      await result.current.mutateAsync({ orderedIssueIds: ['i1'] });
    });

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/codeboard/groups/grp%2Fwith%20slash/members/reorder',
      expect.any(Object),
    );
  });

  it('throws when groupId is null', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReorderGroupMembers(null), {
      wrapper,
    });

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({ orderedIssueIds: ['i1'] });
      } catch (err) {
        caught = err;
      }
    });

    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toMatch(/groupId is required/);
  });
});
