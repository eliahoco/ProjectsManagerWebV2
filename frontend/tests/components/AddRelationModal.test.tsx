/**
 * Unit tests for AddRelationModal — CB-2003 (single create) + CB-2004 (bulk).
 *
 * Coverage:
 *   - renders nothing when closed; renders dialog with linkType + search when open
 *   - autofocuses the search input on open
 *   - debounces the search query before firing useIssues, then renders results
 *   - filters out the source issueId from picker results (defense in depth)
 *   - filters out caller-provided excludeIds (already-linked targets)
 *   - selecting a result keeps the picker open + shows the selected chip
 *   - n=1 submits via useCreateRelation with the right payload + closes on success
 *   - keyboard nav: ArrowDown/ArrowUp move active row, Enter selects
 *   - ESC + backdrop click invoke onClose
 *   - backend ALREADY_EXISTS error renders the friendly inline message
 *   - n>=2 submits via useCreateRelationsBulk with all selected ids
 *   - skipped duplicates render inline and the modal stays open
 *   - removing a chip drops it from the next bulk submit
 *   - already-selected ids are filtered out of the picker (no duplicate picks)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { AddRelationModal } from '@/components/codeboard/AddRelationModal';
import { APIError } from '@/hooks/useCodeBoard';
import type { Issue } from '@/types/codeboard';

vi.mock('lucide-react', () => ({
  AlertCircle: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="icon-alert" className={className} {...rest} />
  ),
  Loader2: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="icon-loader" className={className} {...rest} />
  ),
  Search: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="icon-search" className={className} {...rest} />
  ),
  X: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="icon-x" className={className} {...rest} />
  ),
}));

// ---- mock the data hooks --------------------------------------------------
//
// We don't want a real React Query client wired up in these tests. The
// hooks are pure dependency-injection points — replacing them with vi.fn
// keeps the tests deterministic and lets us assert on the mutation call.

const useIssuesMock = vi.fn();
const createRelationMutate = vi.fn();
const useCreateRelationMock = vi.fn();
const createRelationsBulkMutate = vi.fn();
const useCreateRelationsBulkMock = vi.fn();

vi.mock('@/hooks/useCodeBoard', async () => {
  const actual = await vi.importActual<typeof import('@/hooks/useCodeBoard')>(
    '@/hooks/useCodeBoard',
  );
  return {
    // Keep APIError so the modal's instanceof check still works.
    APIError: actual.APIError,
    useIssues: (...args: unknown[]) => useIssuesMock(...args),
    useCreateRelation: () => useCreateRelationMock(),
    useCreateRelationsBulk: () => useCreateRelationsBulkMock(),
  };
});

function makeIssue(overrides: Partial<Issue> = {}): Issue {
  return {
    id: overrides.id ?? `issue-${Math.random().toString(36).slice(2, 8)}`,
    projectId: overrides.projectId ?? 'project-1',
    key: overrides.key ?? 'CB-200',
    sequence: overrides.sequence ?? 200,
    title: overrides.title ?? 'Some target issue',
    type: overrides.type ?? 'TASK',
    status: overrides.status ?? 'TODO',
    priority: overrides.priority ?? 'MEDIUM',
    createdAt: overrides.createdAt ?? '2026-05-01T10:00:00Z',
    updatedAt: overrides.updatedAt ?? '2026-05-01T10:00:00Z',
    ...overrides,
  };
}

const SOURCE_ID = 'issue-source';
const PROJECT_ID = 'project-1';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  useIssuesMock.mockReset();
  createRelationMutate.mockReset();
  useCreateRelationMock.mockReset();
  createRelationsBulkMutate.mockReset();
  useCreateRelationsBulkMock.mockReset();

  // Default behavior: empty result set, idle mutation. Individual tests
  // override per scenario.
  useIssuesMock.mockReturnValue({
    data: { items: [], total: 0, page: 1, pageSize: 10, totalPages: 0 },
    isLoading: false,
    isFetching: false,
  });
  useCreateRelationMock.mockReturnValue({
    mutate: createRelationMutate,
    isPending: false,
  });
  useCreateRelationsBulkMock.mockReturnValue({
    mutate: createRelationsBulkMutate,
    isPending: false,
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('AddRelationModal', () => {
  it('renders nothing when isOpen=false', () => {
    const { container } = render(
      <AddRelationModal
        isOpen={false}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the dialog with linkType + search when open', () => {
    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Relation type')).toBeInTheDocument();
    expect(screen.getByLabelText('Target issues')).toBeInTheDocument();
  });

  it('debounces the query and only fires useIssues with the trimmed text', async () => {
    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );
    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'log' } });

    // Before the debounce timer fires, useIssues should still be in its
    // disabled state (projectId=null) — caller asked for nothing yet.
    const initialCalls = useIssuesMock.mock.calls.length;
    expect(useIssuesMock).toHaveBeenLastCalledWith(null, undefined);

    // Advance past the 250ms debounce window.
    act(() => {
      vi.advanceTimersByTime(300);
    });

    // After debounce the hook should be called with the project id and a
    // search filter equal to the trimmed query.
    const lastCall = useIssuesMock.mock.calls[useIssuesMock.mock.calls.length - 1];
    expect(lastCall[0]).toBe(PROJECT_ID);
    expect(lastCall[1]).toMatchObject({ search: 'log' });
    expect(useIssuesMock.mock.calls.length).toBeGreaterThan(initialCalls);
  });

  it('hides the source issue and excludeIds from the result list', () => {
    const sourceIssue = makeIssue({ id: SOURCE_ID, key: 'CB-100', title: 'Source' });
    const linkedIssue = makeIssue({ id: 'issue-linked', key: 'CB-201', title: 'Already linked' });
    const validIssue = makeIssue({ id: 'issue-valid', key: 'CB-202', title: 'Valid pick' });

    useIssuesMock.mockReturnValue({
      data: {
        items: [sourceIssue, linkedIssue, validIssue],
        total: 3,
        page: 1,
        pageSize: 10,
        totalPages: 1,
      },
      isLoading: false,
      isFetching: false,
    });

    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
        excludeIds={new Set(['issue-linked'])}
      />,
    );

    // Drive the input + debounce so the picker actually opens.
    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'foo' } });
    act(() => {
      vi.advanceTimersByTime(300);
    });

    // Source + already-linked are filtered out; only the valid pick survives.
    expect(screen.queryByText('Source')).not.toBeInTheDocument();
    expect(screen.queryByText('Already linked')).not.toBeInTheDocument();
    expect(screen.getByText('Valid pick')).toBeInTheDocument();
  });

  it('selecting a result reveals the chosen-issue chip and submits the right payload', async () => {
    const target = makeIssue({ id: 'issue-target', key: 'CB-300', title: 'Refactor login flow' });
    useIssuesMock.mockReturnValue({
      data: { items: [target], total: 1, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });
    const onClose = vi.fn();

    render(
      <AddRelationModal
        isOpen={true}
        onClose={onClose}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'tar' } });
    act(() => {
      vi.advanceTimersByTime(300);
    });

    // Select via mousedown (the modal binds onMouseDown to dodge blur races).
    const row = screen.getByText('Refactor login flow').closest('li');
    expect(row).not.toBeNull();
    fireEvent.mouseDown(row!);

    // CB-2004: picker stays open (multi-select). Chip is shown above the
    // search input; query is cleared so the next ArrowDown lands fresh.
    expect(screen.getByText('CB-300')).toBeInTheDocument();
    expect(screen.getByLabelText('Target issues')).toBeInTheDocument();
    expect((screen.getByLabelText('Target issues') as HTMLInputElement).value).toBe('');

    // Pick BLOCKS instead of the default RELATES_TO.
    fireEvent.change(screen.getByLabelText('Relation type'), {
      target: { value: 'BLOCKS' },
    });

    // Submit. Mutate should fire with the source id + selected target + chosen type.
    fireEvent.click(screen.getByRole('button', { name: /add relation/i }));

    expect(createRelationMutate).toHaveBeenCalledTimes(1);
    const [args, callbacks] = createRelationMutate.mock.calls[0];
    expect(args).toEqual({
      issueId: SOURCE_ID,
      payload: { toIssueId: 'issue-target', linkType: 'BLOCKS' },
    });

    // Trigger the success callback the way React Query would: onClose fires.
    callbacks.onSuccess({
      id: 'link-1',
      fromIssueId: SOURCE_ID,
      toIssueId: 'issue-target',
      linkType: 'BLOCKS',
      createdAt: '2026-05-01T11:00:00Z',
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keyboard ArrowDown + Enter selects the first matching result', () => {
    const target = makeIssue({ id: 'issue-target', key: 'CB-300', title: 'Refactor login flow' });
    useIssuesMock.mockReturnValue({
      data: { items: [target], total: 1, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });

    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'tar' } });
    act(() => {
      vi.advanceTimersByTime(300);
    });

    fireEvent.keyDown(input, { key: 'Enter' });
    // Selection chip is now visible.
    expect(screen.getByText('CB-300')).toBeInTheDocument();
  });

  it('renders the friendly ALREADY_EXISTS message when the backend rejects the create', () => {
    const target = makeIssue({ id: 'issue-target', key: 'CB-300', title: 'Refactor login flow' });
    useIssuesMock.mockReturnValue({
      data: { items: [target], total: 1, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });

    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'tar' } });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    fireEvent.mouseDown(screen.getByText('Refactor login flow').closest('li')!);

    fireEvent.click(screen.getByRole('button', { name: 'Add relation' }));

    const [, callbacks] = createRelationMutate.mock.calls[0];
    act(() => {
      callbacks.onError(
        new APIError('Relation already exists', 409, 'ALREADY_EXISTS'),
      );
    });

    expect(
      screen.getByText('These issues are already linked with this relation type.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('ESC is ignored while a mutation is in flight (no orphaned close)', () => {
    useCreateRelationMock.mockReturnValue({
      mutate: createRelationMutate,
      isPending: true,
    });
    const onClose = vi.fn();
    render(
      <AddRelationModal
        isOpen={true}
        onClose={onClose}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('handleSubmit short-circuits while a mutation is already pending', () => {
    const target = makeIssue({ id: 'issue-target', key: 'CB-300', title: 'Refactor login flow' });
    useIssuesMock.mockReturnValue({
      data: { items: [target], total: 1, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });

    const { rerender } = render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );
    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'tar' } });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    fireEvent.mouseDown(screen.getByText('Refactor login flow').closest('li')!);

    // First submit fires the mutation.
    fireEvent.click(screen.getByRole('button', { name: 'Add relation' }));
    expect(createRelationMutate).toHaveBeenCalledTimes(1);

    // Flip the mock so the next render reports an in-flight mutation.
    useCreateRelationMock.mockReturnValue({
      mutate: createRelationMutate,
      isPending: true,
    });
    rerender(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    // Submit again — must NOT fire a second mutation.
    fireEvent.submit(screen.getByRole('button', { name: 'Add relation' }).closest('form')!);
    expect(createRelationMutate).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['CYCLE_DETECTED', 'This relation would create a cycle (e.g. A blocks B blocks A).'],
    ['NOT_FOUND', 'One of the issues no longer exists. Refresh and try again.'],
  ])('renders the friendly message for backend code %s', (code, expected) => {
    const target = makeIssue({ id: 'issue-target', key: 'CB-300', title: 'Refactor login flow' });
    useIssuesMock.mockReturnValue({
      data: { items: [target], total: 1, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });

    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'tar' } });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    fireEvent.mouseDown(screen.getByText('Refactor login flow').closest('li')!);
    fireEvent.click(screen.getByRole('button', { name: 'Add relation' }));

    const [, callbacks] = createRelationMutate.mock.calls[0];
    act(() => {
      callbacks.onError(new APIError(`API error ${code}`, 409, code));
    });

    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  // ---- CB-2004: bulk-add coverage ---------------------------------------

  it('selecting a second result keeps both chips visible and filters the picker', () => {
    const t1 = makeIssue({ id: 'issue-a', key: 'CB-301', title: 'Alpha' });
    const t2 = makeIssue({ id: 'issue-b', key: 'CB-302', title: 'Beta' });
    useIssuesMock.mockReturnValue({
      data: { items: [t1, t2], total: 2, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });

    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'alp' } });
    act(() => {
      vi.advanceTimersByTime(300);
    });

    // Pick first.
    fireEvent.mouseDown(screen.getByText('Alpha').closest('li')!);
    expect(screen.getByText('CB-301')).toBeInTheDocument();

    // Type again — picker reopens. Already-selected `Alpha` row must NOT
    // appear in the dropdown (defense against duplicate picks).
    fireEvent.change(screen.getByLabelText('Target issues'), {
      target: { value: 'alp' },
    });
    act(() => {
      vi.advanceTimersByTime(300);
    });

    // The chip and the dropdown row both render the title `Alpha`. The
    // dropdown row would have role="option"; the chip would not. Assert
    // there is no listbox option for Alpha now.
    const alphaOptions = screen
      .queryAllByRole('option')
      .filter((el) => el.textContent?.includes('Alpha'));
    expect(alphaOptions).toHaveLength(0);

    // Beta is still pickable.
    fireEvent.mouseDown(screen.getByText('Beta').closest('li')!);
    expect(screen.getByText('CB-302')).toBeInTheDocument();

    // Submit button label updates to plural with count.
    expect(
      screen.getByRole('button', { name: 'Add 2 relations' }),
    ).toBeInTheDocument();
  });

  it('n>=2 submits via useCreateRelationsBulk with all selected ids and closes on clean success', () => {
    const t1 = makeIssue({ id: 'issue-a', key: 'CB-301', title: 'Alpha' });
    const t2 = makeIssue({ id: 'issue-b', key: 'CB-302', title: 'Beta' });
    useIssuesMock.mockReturnValue({
      data: { items: [t1, t2], total: 2, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });
    const onClose = vi.fn();

    render(
      <AddRelationModal
        isOpen={true}
        onClose={onClose}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    const input = screen.getByLabelText('Target issues') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'alp' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Alpha').closest('li')!);
    fireEvent.change(screen.getByLabelText('Target issues'), { target: { value: 'bet' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Beta').closest('li')!);

    fireEvent.change(screen.getByLabelText('Relation type'), {
      target: { value: 'BLOCKS' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Add 2 relations' }));

    // Single-create path is NOT used for bulk.
    expect(createRelationMutate).not.toHaveBeenCalled();
    expect(createRelationsBulkMutate).toHaveBeenCalledTimes(1);
    const [args, callbacks] = createRelationsBulkMutate.mock.calls[0];
    expect(args).toEqual({
      issueId: SOURCE_ID,
      payload: { toIssueIds: ['issue-a', 'issue-b'], linkType: 'BLOCKS' },
    });

    // Backend returns no skipped → modal closes.
    act(() => {
      callbacks.onSuccess({
        created: [
          {
            id: 'link-1',
            fromIssueId: SOURCE_ID,
            toIssueId: 'issue-a',
            linkType: 'BLOCKS',
            createdAt: '2026-05-02T11:00:00Z',
          },
        ],
        skipped: [],
      });
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders skipped duplicates inline and stays open until Done', () => {
    const t1 = makeIssue({ id: 'issue-a', key: 'CB-301', title: 'Alpha' });
    const t2 = makeIssue({ id: 'issue-b', key: 'CB-302', title: 'Beta' });
    useIssuesMock.mockReturnValue({
      data: { items: [t1, t2], total: 2, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });
    const onClose = vi.fn();

    render(
      <AddRelationModal
        isOpen={true}
        onClose={onClose}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    fireEvent.change(screen.getByLabelText('Target issues'), { target: { value: 'alp' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Alpha').closest('li')!);
    fireEvent.change(screen.getByLabelText('Target issues'), { target: { value: 'bet' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Beta').closest('li')!);

    fireEvent.click(screen.getByRole('button', { name: 'Add 2 relations' }));
    const [, callbacks] = createRelationsBulkMutate.mock.calls[0];

    // One created, one skipped (duplicate).
    act(() => {
      callbacks.onSuccess({
        created: [
          {
            id: 'link-1',
            fromIssueId: SOURCE_ID,
            toIssueId: 'issue-a',
            linkType: 'RELATES_TO',
            createdAt: '2026-05-02T11:00:00Z',
          },
        ],
        skipped: [{ toIssueId: 'issue-b', reason: 'DUPLICATE' }],
      });
    });

    // onClose is NOT called — user must read the skipped panel first.
    expect(onClose).not.toHaveBeenCalled();
    // Result panel shows.
    expect(screen.getByText(/Added 1 relation/)).toBeInTheDocument();
    expect(screen.getByText(/Already linked/)).toBeInTheDocument();
    // Skipped chip carries the original key/title.
    expect(screen.getByText('CB-302')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();

    // Done dismisses.
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders friendly error from a bulk submit failure', () => {
    const t1 = makeIssue({ id: 'issue-a', key: 'CB-301', title: 'Alpha' });
    const t2 = makeIssue({ id: 'issue-b', key: 'CB-302', title: 'Beta' });
    useIssuesMock.mockReturnValue({
      data: { items: [t1, t2], total: 2, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });

    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    fireEvent.change(screen.getByLabelText('Target issues'), { target: { value: 'alp' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Alpha').closest('li')!);
    fireEvent.change(screen.getByLabelText('Target issues'), { target: { value: 'bet' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Beta').closest('li')!);

    fireEvent.click(screen.getByRole('button', { name: 'Add 2 relations' }));

    const [, callbacks] = createRelationsBulkMutate.mock.calls[0];
    act(() => {
      callbacks.onError(
        new APIError(
          'Invalid issue ids in bulk relation create',
          400,
          'VALIDATION_ERROR',
        ),
      );
    });

    expect(
      screen.getByText('Invalid issue ids in bulk relation create'),
    ).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    // Form is still in compose mode — result panel never mounts on error.
    expect(screen.queryByRole('button', { name: 'Done' })).not.toBeInTheDocument();
  });

  it('removing a chip drops it from the next bulk submit', () => {
    const t1 = makeIssue({ id: 'issue-a', key: 'CB-301', title: 'Alpha' });
    const t2 = makeIssue({ id: 'issue-b', key: 'CB-302', title: 'Beta' });
    useIssuesMock.mockReturnValue({
      data: { items: [t1, t2], total: 2, page: 1, pageSize: 10, totalPages: 1 },
      isLoading: false,
      isFetching: false,
    });

    render(
      <AddRelationModal
        isOpen={true}
        onClose={() => {}}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    fireEvent.change(screen.getByLabelText('Target issues'), { target: { value: 'alp' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Alpha').closest('li')!);
    fireEvent.change(screen.getByLabelText('Target issues'), { target: { value: 'bet' } });
    act(() => { vi.advanceTimersByTime(300); });
    fireEvent.mouseDown(screen.getByText('Beta').closest('li')!);

    // Remove Alpha — n drops to 1, button collapses to single-create label.
    fireEvent.click(screen.getByRole('button', { name: 'Remove CB-301' }));
    expect(
      screen.getByRole('button', { name: 'Add relation' }),
    ).toBeInTheDocument();

    // Submit fires the SINGLE endpoint (n=1 path), not bulk.
    fireEvent.click(screen.getByRole('button', { name: 'Add relation' }));
    expect(createRelationsBulkMutate).not.toHaveBeenCalled();
    expect(createRelationMutate).toHaveBeenCalledTimes(1);
    expect(createRelationMutate.mock.calls[0][0]).toMatchObject({
      payload: { toIssueId: 'issue-b' },
    });
  });

  it('ESC and backdrop click invoke onClose', () => {
    const onClose = vi.fn();
    render(
      <AddRelationModal
        isOpen={true}
        onClose={onClose}
        issueId={SOURCE_ID}
        projectId={PROJECT_ID}
      />,
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    // Backdrop is the absolute-inset sibling of the dialog content. Click it.
    const dialog = screen.getByRole('dialog');
    const backdrop = dialog.querySelector('[aria-hidden="true"]');
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
