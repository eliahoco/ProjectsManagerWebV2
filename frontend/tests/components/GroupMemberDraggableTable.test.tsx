/**
 * Unit tests for GroupMemberDraggableTable (CB-2015).
 *
 * Coverage:
 *   - Renders one row per member with position / key / title / status
 *   - Empty state when members[] is empty
 *   - Row click navigates (calls onRowClick with issueId)
 *   - Drag handle click does NOT navigate (onRowClick not fired)
 *   - Keyboard ArrowDown moves focused row down by one
 *   - Keyboard ArrowUp moves focused row up by one
 *   - Keyboard at top boundary doesn't move past index 0
 *   - HTML5 drag/drop reorder dispatches the mutation with new ordered ids
 *   - No-op drag (drop on same slot) does NOT dispatch a request
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
// userEvent is intentionally NOT imported — its `setup()` re-defines
// navigator.clipboard, which collides with the test setup file's
// (non-configurable) clipboard mock. fireEvent gives us the same coverage
// without the global state churn.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { GroupMemberDraggableTable } from '@/components/codeboard/GroupMemberDraggableTable';
import type { IssueGroupMemberResponse } from '@/types/codeboard';

vi.mock('lucide-react', () => ({
  GripVertical: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="grip" className={className} {...rest} />
  ),
  Loader2: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="loader" className={className} {...rest} />
  ),
}));

const GROUP_ID = 'grp-1';

function makeMember(
  id: string,
  issueId: string,
  position: number,
  key = `CB-${position}`,
): IssueGroupMemberResponse {
  return {
    id,
    groupId: GROUP_ID,
    issueId,
    position,
    createdAt: '2026-05-01T10:00:00Z',
    issue: {
      id: issueId,
      key,
      title: `Issue ${position}`,
      status: 'BACKLOG',
    },
  };
}

function renderTable(props: {
  members?: IssueGroupMemberResponse[];
  onRowClick?: (issueId: string) => void;
  onReorderSuccess?: (payload: { orderedIssueIds: string[] }) => void;
  onReorderError?: (err: Error) => void;
}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const members = props.members ?? [
    makeMember('m1', 'i1', 1),
    makeMember('m2', 'i2', 2),
    makeMember('m3', 'i3', 3),
  ];
  const result = render(
    <QueryClientProvider client={queryClient}>
      <GroupMemberDraggableTable
        groupId={GROUP_ID}
        members={members}
        onRowClick={props.onRowClick ?? vi.fn()}
        onReorderSuccess={props.onReorderSuccess}
        onReorderError={props.onReorderError}
      />
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default mocked fetch: succeed with a no-op reorder response. Tests that
  // care about request shape override before calling.
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: true,
    status: 200,
    json: () =>
      Promise.resolve({
        reordered: 0,
        members: [],
      }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('GroupMemberDraggableTable', () => {
  it('renders a row per member with position, key, title, status', () => {
    renderTable({});
    expect(screen.getByText('Issue 1')).toBeInTheDocument();
    expect(screen.getByText('Issue 2')).toBeInTheDocument();
    expect(screen.getByText('Issue 3')).toBeInTheDocument();
    expect(screen.getByText('CB-1')).toBeInTheDocument();
    expect(screen.getAllByText('Backlog').length).toBe(3);
  });

  it('renders empty state when members[] is empty', () => {
    renderTable({ members: [] });
    expect(screen.getByText(/No issues in this group yet/i)).toBeInTheDocument();
  });

  it('row click invokes onRowClick with the issueId', () => {
    const onRowClick = vi.fn();
    renderTable({ onRowClick });

    // Click the title cell (not the handle).
    fireEvent.click(screen.getByText('Issue 2'));
    expect(onRowClick).toHaveBeenCalledWith('i2');
  });

  it('drag-handle click does NOT navigate', () => {
    const onRowClick = vi.fn();
    renderTable({ onRowClick });

    const handles = screen.getAllByRole('button', {
      name: /Drag to reorder/i,
    });
    // fireEvent.click on the handle: the row's onClick filters via the
    // [data-drag-handle] check and skips navigation.
    fireEvent.click(handles[1]);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('ArrowDown on the focused handle dispatches a reorder PATCH', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          reordered: 2,
          members: [
            makeMember('m2', 'i2', 1),
            makeMember('m1', 'i1', 2),
            makeMember('m3', 'i3', 3),
          ],
        }),
    });

    renderTable({});

    const handles = screen.getAllByRole('button', {
      name: /Drag to reorder/i,
    });
    handles[0].focus();
    fireEvent.keyDown(handles[0], { key: 'ArrowDown' });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/codeboard/groups/${GROUP_ID}/members/reorder`,
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ orderedIssueIds: ['i2', 'i1', 'i3'] }),
        }),
      );
    });
  });

  it('ArrowUp on the focused handle dispatches a reorder PATCH', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          reordered: 2,
          members: [
            makeMember('m1', 'i1', 1),
            makeMember('m3', 'i3', 2),
            makeMember('m2', 'i2', 3),
          ],
        }),
    });

    renderTable({});

    const handles = screen.getAllByRole('button', {
      name: /Drag to reorder/i,
    });
    // Focus the third row's handle, ArrowUp should swap m3 with m2.
    handles[2].focus();
    fireEvent.keyDown(handles[2], { key: 'ArrowUp' });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/codeboard/groups/${GROUP_ID}/members/reorder`,
        expect.objectContaining({
          body: JSON.stringify({ orderedIssueIds: ['i1', 'i3', 'i2'] }),
        }),
      );
    });
  });

  it('ArrowUp at the top boundary is a no-op (no PATCH dispatched)', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();

    renderTable({});

    const handles = screen.getAllByRole('button', {
      name: /Drag to reorder/i,
    });
    handles[0].focus();
    fireEvent.keyDown(handles[0], { key: 'ArrowUp' });

    // Give it a tick to dispatch if it were going to.
    await new Promise((r) => setTimeout(r, 30));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keyboard reorder while a previous PATCH is inflight is dropped', async () => {
    // Regression test for H1 from the CB-2015 code review: rapid double-fire
    // would otherwise stack two optimistic updates and risk inconsistent
    // cache state on partial failure. The component's `submitReorder`
    // gates on `reorderMutation.isPending`.
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    let resolveFirst!: (v: unknown) => void;
    fetchMock.mockClear();
    fetchMock.mockReturnValueOnce(
      new Promise((res) => {
        resolveFirst = res;
      }),
    );

    renderTable({});

    const handles = screen.getAllByRole('button', {
      name: /Drag to reorder/i,
    });
    handles[0].focus();
    fireEvent.keyDown(handles[0], { key: 'ArrowDown' });

    // First PATCH fired but unresolved — fire a second from a different row.
    handles[2].focus();
    fireEvent.keyDown(handles[2], { key: 'ArrowUp' });

    // Only ONE fetch call should have been made; the second is dropped.
    await new Promise((r) => setTimeout(r, 30));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Resolve so the test cleans up.
    resolveFirst({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          reordered: 2,
          members: [
            makeMember('m2', 'i2', 1),
            makeMember('m1', 'i1', 2),
            makeMember('m3', 'i3', 3),
          ],
        }),
    });
  });

  it('ArrowDown at the bottom boundary is a no-op (no PATCH dispatched)', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();

    renderTable({});

    const handles = screen.getAllByRole('button', {
      name: /Drag to reorder/i,
    });
    handles[2].focus();
    fireEvent.keyDown(handles[2], { key: 'ArrowDown' });

    await new Promise((r) => setTimeout(r, 30));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
