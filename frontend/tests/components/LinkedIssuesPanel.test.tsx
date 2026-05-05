/**
 * Unit Tests for LinkedIssuesPanel Component
 * Task: CB-1998 — grouped flat list rendering for typed issue relations.
 *
 * Coverage:
 *   - groups outbound rows by linkType in the configured display order
 *   - renders direction arrow per linkType (out / in / sym)
 *   - renders status pill from the embedded summary
 *   - renders empty state when no rows
 *   - renders skeleton when isLoading
 *   - falls back gracefully when fromIssue/toIssue is missing
 *   - click + keyboard activation invoke onIssueClick with the OTHER side
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LinkedIssuesPanel } from '@/components/codeboard/LinkedIssuesPanel';
import type {
  IssueLinkResponse,
  IssueRelationsListResponse,
} from '@/types/codeboard';

vi.mock('lucide-react', () => ({
  ArrowUp: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="dir-out" className={className} {...rest} />
  ),
  ArrowDown: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="dir-in" className={className} {...rest} />
  ),
  ArrowLeftRight: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="dir-sym" className={className} {...rest} />
  ),
  Plus: ({ className, ...rest }: { className?: string; [k: string]: unknown }) => (
    <span data-testid="icon-plus" className={className} {...rest} />
  ),
}));

const ISSUE_ID = 'issue-current';

function makeLink(overrides: Partial<IssueLinkResponse> = {}): IssueLinkResponse {
  return {
    id: overrides.id ?? `link-${Math.random().toString(36).slice(2, 8)}`,
    fromIssueId: overrides.fromIssueId ?? ISSUE_ID,
    toIssueId: overrides.toIssueId ?? 'issue-other',
    linkType: overrides.linkType ?? 'RELATES_TO',
    createdAt: overrides.createdAt ?? '2026-05-01T10:00:00Z',
    fromIssue: overrides.fromIssue ?? {
      id: ISSUE_ID,
      key: 'CB-100',
      title: 'Current issue',
      status: 'IN_PROGRESS',
    },
    toIssue: overrides.toIssue ?? {
      id: overrides.toIssueId ?? 'issue-other',
      key: 'CB-200',
      title: 'Linked issue',
      status: 'TODO',
    },
  };
}

function withRelations(
  outbound: IssueLinkResponse[],
  inbound: IssueLinkResponse[] = []
): IssueRelationsListResponse {
  return { outbound, inbound };
}

describe('LinkedIssuesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the loading skeleton when isLoading is true', () => {
    render(
      <LinkedIssuesPanel issueId={ISSUE_ID} relations={undefined} isLoading={true} />
    );
    const busy = document.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();
  });

  it('renders empty placeholder when there are no outbound rows', () => {
    render(
      <LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations([])} />
    );
    expect(screen.getByText(/No linked issues/i)).toBeInTheDocument();
  });

  describe('empty state CTA (CB-2001)', () => {
    it('does NOT render section headings when relations are empty', () => {
      // Reader p. 7 rule: column headers / section headings only render
      // when there's content under them. An empty panel with stray
      // "Blocked by (0)" headings would imply structure that isn't there.
      render(
        <LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations([])} />
      );
      expect(screen.queryAllByRole('heading', { level: 4 })).toHaveLength(0);
    });

    it('renders ghost "+ Add relation" button when onAddRelation is provided', () => {
      const onAddRelation = vi.fn();
      render(
        <LinkedIssuesPanel
          issueId={ISSUE_ID}
          relations={withRelations([])}
          onAddRelation={onAddRelation}
        />
      );
      const button = screen.getByRole('button', { name: /add relation/i });
      expect(button).toBeInTheDocument();
      // Status role on the wrapper announces the empty state to AT users
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('invokes onAddRelation when the ghost button is clicked', async () => {
      const onAddRelation = vi.fn();
      render(
        <LinkedIssuesPanel
          issueId={ISSUE_ID}
          relations={withRelations([])}
          onAddRelation={onAddRelation}
        />
      );
      await userEvent.click(screen.getByRole('button', { name: /add relation/i }));
      expect(onAddRelation).toHaveBeenCalledTimes(1);
    });

    it('omits the CTA when onAddRelation is not provided (read-only fallback)', () => {
      render(
        <LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations([])} />
      );
      expect(screen.queryByRole('button', { name: /add relation/i })).not.toBeInTheDocument();
      // Hint text still rendered so the panel isn't visually blank
      expect(screen.getByText(/No linked issues/i)).toBeInTheDocument();
    });

    it('does NOT render the empty-state CTA when there are populated rows', () => {
      // Defensive: the CTA is empty-state-only. If rows exist, no add button
      // should appear in the panel's empty-state slot — relation creation
      // from a populated panel is a separate UX (CB-2002+ header CTA).
      const onAddRelation = vi.fn();
      const rows: IssueLinkResponse[] = [
        makeLink({ id: 'L1', linkType: 'BLOCKS', toIssueId: 'X1' }),
      ];
      render(
        <LinkedIssuesPanel
          issueId={ISSUE_ID}
          relations={withRelations(rows)}
          onAddRelation={onAddRelation}
        />
      );
      expect(screen.queryByRole('button', { name: /add relation/i })).not.toBeInTheDocument();
    });
  });

  it('groups rows by linkType with display-order labels', () => {
    const rows: IssueLinkResponse[] = [
      makeLink({
        id: 'L1',
        linkType: 'RELATES_TO',
        toIssueId: 'X1',
        toIssue: { id: 'X1', key: 'CB-301', title: 'Relates one', status: 'TODO' },
      }),
      makeLink({
        id: 'L2',
        linkType: 'BLOCKS',
        toIssueId: 'X2',
        toIssue: { id: 'X2', key: 'CB-302', title: 'Blocks one', status: 'IN_PROGRESS' },
      }),
      makeLink({
        id: 'L3',
        linkType: 'BLOCKS',
        toIssueId: 'X3',
        toIssue: { id: 'X3', key: 'CB-303', title: 'Blocks two', status: 'DONE' },
      }),
      makeLink({
        id: 'L4',
        linkType: 'IS_BLOCKED_BY',
        toIssueId: 'X4',
        toIssue: { id: 'X4', key: 'CB-304', title: 'Blocked by one', status: 'BACKLOG' },
      }),
    ];

    render(
      <LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />
    );

    // Section headings present + counts
    expect(screen.getByText(/Blocked by \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Blocks \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Relates to \(1\)/i)).toBeInTheDocument();

    // Display order: IS_BLOCKED_BY before BLOCKS before RELATES_TO
    const headings = screen
      .getAllByRole('heading', { level: 4 })
      .map((h) => h.textContent || '');
    const idxBlockedBy = headings.findIndex((h) => h.startsWith('Blocked by'));
    const idxBlocks = headings.findIndex((h) => h.startsWith('Blocks'));
    const idxRelates = headings.findIndex((h) => h.startsWith('Relates to'));
    expect(idxBlockedBy).toBeLessThan(idxBlocks);
    expect(idxBlocks).toBeLessThan(idxRelates);
  });

  it('renders the correct direction arrow per linkType', () => {
    const rows: IssueLinkResponse[] = [
      makeLink({ id: 'a', linkType: 'BLOCKS', toIssueId: 'A' }),
      makeLink({ id: 'b', linkType: 'IS_BLOCKED_BY', toIssueId: 'B' }),
      makeLink({ id: 'c', linkType: 'RELATES_TO', toIssueId: 'C' }),
    ];
    render(
      <LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />
    );
    expect(screen.getAllByTestId('dir-out').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('dir-in').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('dir-sym').length).toBeGreaterThan(0);
  });

  it('renders the status pill text from the linked issue summary', () => {
    const rows: IssueLinkResponse[] = [
      makeLink({
        id: 'L1',
        linkType: 'BLOCKS',
        toIssueId: 'X1',
        toIssue: {
          id: 'X1',
          key: 'CB-401',
          title: 'In review issue',
          status: 'COMPLETED_WAITING_QA',
        },
      }),
    ];
    render(
      <LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />
    );
    // status replaces underscores with spaces in the visible label
    expect(screen.getByText(/COMPLETED WAITING QA/i)).toBeInTheDocument();
    expect(screen.getByText(/In review issue/)).toBeInTheDocument();
    expect(screen.getByText('CB-401')).toBeInTheDocument();
  });

  it('falls back to id-only row when summary is missing', () => {
    const rows: IssueLinkResponse[] = [
      {
        id: 'L1',
        fromIssueId: ISSUE_ID,
        toIssueId: 'orphan-id',
        linkType: 'RELATES_TO',
        createdAt: '2026-05-01T10:00:00Z',
        fromIssue: undefined,
        toIssue: undefined,
      },
    ];
    render(
      <LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />
    );
    expect(screen.getByText(/orphan-id/)).toBeInTheDocument();
    expect(screen.getByText(/summary unavailable/i)).toBeInTheDocument();
  });

  it('invokes onIssueClick with the OTHER side on click, Enter, and Space', async () => {
    const onIssueClick = vi.fn();
    const rows: IssueLinkResponse[] = [
      makeLink({
        id: 'L1',
        linkType: 'BLOCKS',
        fromIssueId: ISSUE_ID,
        toIssueId: 'other-1',
        toIssue: { id: 'other-1', key: 'CB-501', title: 'Other one', status: 'TODO' },
      }),
    ];
    render(
      <LinkedIssuesPanel
        issueId={ISSUE_ID}
        relations={withRelations(rows)}
        onIssueClick={onIssueClick}
      />
    );

    const row = screen.getByRole('button');
    fireEvent.click(row);
    expect(onIssueClick).toHaveBeenLastCalledWith('other-1');

    onIssueClick.mockClear();
    (row as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    expect(onIssueClick).toHaveBeenLastCalledWith('other-1');

    onIssueClick.mockClear();
    await userEvent.keyboard(' ');
    expect(onIssueClick).toHaveBeenLastCalledWith('other-1');
  });

  it('drops self-links from the rendered output', () => {
    const rows: IssueLinkResponse[] = [
      // Self-link — should be filtered out
      makeLink({
        id: 'self',
        linkType: 'RELATES_TO',
        fromIssueId: ISSUE_ID,
        toIssueId: ISSUE_ID,
        toIssue: { id: ISSUE_ID, key: 'CB-100', title: 'Self', status: 'TODO' },
      }),
      // Real link — should render
      makeLink({
        id: 'real',
        linkType: 'BLOCKS',
        toIssueId: 'real-other',
        toIssue: { id: 'real-other', key: 'CB-700', title: 'Real other', status: 'TODO' },
      }),
    ];
    render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
    expect(screen.queryByText('CB-100')).not.toBeInTheDocument();
    expect(screen.getByText('CB-700')).toBeInTheDocument();
    // Only one section should render (the BLOCKS row)
    expect(screen.queryByText(/Relates to/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Blocks \(1\)/i)).toBeInTheDocument();
  });

  it('caps rendering at 500 rows and shows a truncation notice', () => {
    const rows: IssueLinkResponse[] = Array.from({ length: 600 }, (_, i) =>
      makeLink({
        id: `bulk-${i}`,
        linkType: 'RELATES_TO',
        toIssueId: `b-${i}`,
        toIssue: { id: `b-${i}`, key: `CB-${1000 + i}`, title: `Row ${i}`, status: 'TODO' },
      })
    );
    render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
    // Truncation notice appears
    expect(screen.getByText(/Showing first 500 relations/i)).toBeInTheDocument();
    // Heading reflects the capped count, not 600
    expect(screen.getByText(/Relates to \(500\)/i)).toBeInTheDocument();
  });

  it('ignores inbound rows (outbound-only contract)', () => {
    const inboundOnly = withRelations(
      [],
      [
        makeLink({
          id: 'in1',
          linkType: 'BLOCKS',
          fromIssueId: 'someone-else',
          toIssueId: ISSUE_ID,
          fromIssue: { id: 'someone-else', key: 'CB-999', title: 'Inbound', status: 'TODO' },
        }),
      ]
    );
    render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={inboundOnly} />);
    expect(screen.getByText(/No linked issues/i)).toBeInTheDocument();
    expect(screen.queryByText('CB-999')).not.toBeInTheDocument();
  });

  describe('progressive disclosure (CB-2000)', () => {
    it('renders all rows when group has 5 or fewer (no toggle button)', () => {
      const rows: IssueLinkResponse[] = Array.from({ length: 5 }, (_, i) =>
        makeLink({
          id: `r${i}`,
          linkType: 'RELATES_TO',
          toIssueId: `o${i}`,
          toIssue: { id: `o${i}`, key: `CB-90${i}`, title: `Row ${i}`, status: 'TODO' },
        })
      );
      render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
      // All 5 keys rendered
      for (let i = 0; i < 5; i++) {
        expect(screen.getByText(`CB-90${i}`)).toBeInTheDocument();
      }
      // No toggle button — boundary at exactly 5 must not trigger disclosure
      expect(screen.queryByRole('button', { name: /more/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /show less/i })).not.toBeInTheDocument();
    });

    it('shows only first 5 rows + "+ N more" button when group has > 5 rows', () => {
      const rows: IssueLinkResponse[] = Array.from({ length: 7 }, (_, i) =>
        makeLink({
          id: `r${i}`,
          linkType: 'RELATES_TO',
          toIssueId: `o${i}`,
          toIssue: { id: `o${i}`, key: `CB-80${i}`, title: `Row ${i}`, status: 'TODO' },
        })
      );
      render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
      // First 5 visible
      for (let i = 0; i < 5; i++) {
        expect(screen.getByText(`CB-80${i}`)).toBeInTheDocument();
      }
      // Last 2 hidden
      expect(screen.queryByText('CB-805')).not.toBeInTheDocument();
      expect(screen.queryByText('CB-806')).not.toBeInTheDocument();
      // Toggle button shows the overflow count
      const toggle = screen.getByRole('button', { name: /\+ 2 more/i });
      expect(toggle).toBeInTheDocument();
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
      // Heading still reflects the TOTAL count (transparency principle)
      expect(screen.getByText(/Relates to \(7\)/i)).toBeInTheDocument();
    });

    it('expands inline when "+ N more" is clicked, then collapses on "Show less"', async () => {
      const rows: IssueLinkResponse[] = Array.from({ length: 8 }, (_, i) =>
        makeLink({
          id: `r${i}`,
          linkType: 'RELATES_TO',
          toIssueId: `o${i}`,
          toIssue: { id: `o${i}`, key: `CB-70${i}`, title: `Row ${i}`, status: 'TODO' },
        })
      );
      render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
      // Hidden initially
      expect(screen.queryByText('CB-707')).not.toBeInTheDocument();

      const expand = screen.getByRole('button', { name: /\+ 3 more/i });
      await userEvent.click(expand);

      // All 8 now visible
      for (let i = 0; i < 8; i++) {
        expect(screen.getByText(`CB-70${i}`)).toBeInTheDocument();
      }
      // Button label flips to "Show less" + aria-expanded toggles
      const collapse = screen.getByRole('button', { name: /show less/i });
      expect(collapse).toBeInTheDocument();
      expect(collapse).toHaveAttribute('aria-expanded', 'true');

      // Click again — collapses back to 5 visible
      await userEvent.click(collapse);
      expect(screen.queryByText('CB-707')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /\+ 3 more/i })).toBeInTheDocument();
    });

    it('toggle button has aria-controls pointing at the rows container id', () => {
      const rows: IssueLinkResponse[] = Array.from({ length: 6 }, (_, i) =>
        makeLink({
          id: `r${i}`,
          linkType: 'RELATES_TO',
          toIssueId: `o${i}`,
          toIssue: { id: `o${i}`, key: `CB-50${i}`, title: `Row ${i}`, status: 'TODO' },
        })
      );
      render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
      const toggle = screen.getByRole('button', { name: /\+ 1 more/i });
      const targetId = toggle.getAttribute('aria-controls');
      expect(targetId).toBe(`linked-section-${ISSUE_ID}-RELATES_TO`);
      // The id is wired to a real container — proves screen readers can resolve it
      expect(document.getElementById(targetId!)).not.toBeNull();
    });

    it('toggle responds to keyboard activation (Enter)', async () => {
      const rows: IssueLinkResponse[] = Array.from({ length: 7 }, (_, i) =>
        makeLink({
          id: `r${i}`,
          linkType: 'RELATES_TO',
          toIssueId: `o${i}`,
          toIssue: { id: `o${i}`, key: `CB-40${i}`, title: `Row ${i}`, status: 'TODO' },
        })
      );
      render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
      const toggle = screen.getByRole('button', { name: /\+ 2 more/i });
      toggle.focus();
      await userEvent.keyboard('{Enter}');
      // Native <button> handles Enter — last 2 rows now visible
      expect(screen.getByText('CB-405')).toBeInTheDocument();
      expect(screen.getByText('CB-406')).toBeInTheDocument();
    });

    it('expands each group independently — toggling BLOCKS does not affect RELATES_TO', async () => {
      const blockRows: IssueLinkResponse[] = Array.from({ length: 7 }, (_, i) =>
        makeLink({
          id: `b${i}`,
          linkType: 'BLOCKS',
          toIssueId: `bo${i}`,
          toIssue: { id: `bo${i}`, key: `CB-60${i}`, title: `Block ${i}`, status: 'TODO' },
        })
      );
      const relRows: IssueLinkResponse[] = Array.from({ length: 7 }, (_, i) =>
        makeLink({
          id: `rel${i}`,
          linkType: 'RELATES_TO',
          toIssueId: `ro${i}`,
          toIssue: { id: `ro${i}`, key: `CB-65${i}`, title: `Rel ${i}`, status: 'TODO' },
        })
      );
      render(
        <LinkedIssuesPanel
          issueId={ISSUE_ID}
          relations={withRelations([...blockRows, ...relRows])}
        />
      );

      // Both groups initially capped at 5
      expect(screen.queryByText('CB-606')).not.toBeInTheDocument();
      expect(screen.queryByText('CB-656')).not.toBeInTheDocument();

      // Two "+ 2 more" buttons (one per group)
      const moreButtons = screen.getAllByRole('button', { name: /\+ 2 more/i });
      expect(moreButtons).toHaveLength(2);

      // Expand only the FIRST one (BLOCKS section comes earlier in display order)
      await userEvent.click(moreButtons[0]);

      // BLOCKS group now shows row 6, RELATES_TO group still hides row 6
      expect(screen.getByText('CB-606')).toBeInTheDocument();
      expect(screen.queryByText('CB-656')).not.toBeInTheDocument();
    });
  });

  it('does not make rows interactive when onIssueClick is not provided', () => {
    const rows: IssueLinkResponse[] = [
      makeLink({ id: 'L1', linkType: 'BLOCKS', toIssueId: 'X1' }),
    ];
    render(<LinkedIssuesPanel issueId={ISSUE_ID} relations={withRelations(rows)} />);
    // No element with role=button should exist for rows when no handler
    const buttons = screen.queryAllByRole('button');
    expect(buttons.length).toBe(0);
  });
});
