/**
 * Tests for BUG detail view components (CB-2706 / CB-2708..CB-2711)
 *
 * Strategy: test HierarchyTreeSection + ParentBreadcrumb components directly,
 * and test the page's conditional rendering logic via a thin wrapper component
 * that avoids React.use(Promise) Suspense complexity in jsdom.
 *
 * CB-2708: BUG with children → HierarchyTreeSection renders child rows
 * CB-2709: BUG with parentId → ParentBreadcrumb shows ancestor chain
 * CB-2710: Execute button calls useStartExecution with the correct issue id
 * CB-2711: Leaf BUG → no tree, no breadcrumb, metadata sections present
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

// ─── Mock next/navigation ────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({ get: () => null, toString: () => '' }),
  usePathname: () => '/',
}));

// ─── Mock next/link ──────────────────────────────────────────────────────────

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [k: string]: unknown;
  }) => React.createElement('a', { href, ...rest }, children),
}));

// ─── Shared issue factory ────────────────────────────────────────────────────

import type { Issue } from '@/types/codeboard';

function makeIssue(
  overrides: Partial<Issue> & { id: string; key: string; type: Issue['type'] },
): Issue {
  return {
    projectId: 'proj-1',
    sequence: 1,
    title: 'Default Title',
    status: 'BACKLOG',
    priority: 'MEDIUM',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

// ─── Fixture issues ──────────────────────────────────────────────────────────

const childTask1 = makeIssue({
  id: 'child-1',
  key: 'CB-501',
  type: 'TASK',
  title: 'Child Task One',
  parentId: 'bug-1',
  projectId: 'proj-1',
  sequence: 1,
});
const childTask2 = makeIssue({
  id: 'child-2',
  key: 'CB-502',
  type: 'TASK',
  title: 'Child Task Two',
  parentId: 'bug-1',
  projectId: 'proj-1',
  sequence: 2,
});
const childTask3 = makeIssue({
  id: 'child-3',
  key: 'CB-503',
  type: 'TASK',
  title: 'Child Task Three',
  parentId: 'bug-1',
  projectId: 'proj-1',
  sequence: 3,
});
const bugWithChildren = makeIssue({
  id: 'bug-1',
  key: 'CB-500',
  type: 'BUG',
  title: 'Critical bug with children',
  projectId: 'proj-1',
  children: [childTask1, childTask2, childTask3],
  sequence: 10,
});

const featureAncestor = makeIssue({
  id: 'feat-1',
  key: 'CB-100',
  type: 'FEATURE',
  title: 'Root Feature',
  projectId: 'proj-1',
  sequence: 1,
});
const bugWithParent = makeIssue({
  id: 'bug-2',
  key: 'CB-600',
  type: 'BUG',
  title: 'Bug with parent',
  projectId: 'proj-1',
  parentId: 'feat-1',
  sequence: 5,
});

const leafBug = makeIssue({
  id: 'bug-3',
  key: 'CB-700',
  type: 'BUG',
  title: 'Leaf bug description present',
  description: 'Some detailed description text for the bug',
  projectId: 'proj-1',
  sequence: 7,
});

// ─── Mutable cursor — tests point this at which issue to serve ───────────────

let currentIssue: Issue = bugWithChildren;

// ─── Mock useCodeBoard hooks ─────────────────────────────────────────────────

const mockStartExecutionMutateAsync = vi
  .fn()
  .mockResolvedValue({ session_id: 'sess-abc' });
const mockStartExecutionMutate = vi.fn();

vi.mock('@/hooks/useCodeBoard', () => ({
  useIssue: (id: string | null) => {
    if (!id) return { data: undefined, isLoading: false, error: null };
    if (id === currentIssue.id) return { data: currentIssue, isLoading: false, error: null };
    if (id === featureAncestor.id) return { data: featureAncestor, isLoading: false, error: null };
    if (id === bugWithParent.id) return { data: bugWithParent, isLoading: false, error: null };
    return { data: undefined, isLoading: false, error: null };
  },
  useIssues: () => ({
    data: {
      items: [
        currentIssue,
        childTask1,
        childTask2,
        childTask3,
      ],
      totalPages: 1,
    },
    isLoading: false,
    refetch: vi.fn(),
  }),
  useUpdateIssue: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useDeleteIssue: () => ({ mutate: vi.fn() }),
  useProjects: () => ({ data: [{ id: 'proj-1', name: 'Test Project' }] }),
  useIssueCommits: () => ({ data: null }),
  useLinkedCommits: () => ({ data: null }),
  useExecutionSummaries: () => ({ data: [] }),
  useStartExecution: () => ({
    mutateAsync: mockStartExecutionMutateAsync,
    mutate: mockStartExecutionMutate,
    isPending: false,
  }),
  useExecutionStatus: () => ({ data: null }),
  useFeatureLiveData: () => ({
    activeSessionMap: new Map(),
    hasActiveSessions: false,
  }),
  useIssueDescendants: () => ({ data: [], isLoading: false }),
}));

// ─── Mock AutoPilotContext ───────────────────────────────────────────────────

vi.mock('@/contexts/AutoPilotContext', () => ({
  useAutoPilot: () => ({
    state: {
      isActive: false,
      isPaused: false,
      featureId: null,
      queue: [],
      currentIndex: 0,
      progress: { total: 0, completed: 0, skipped: 0, failed: 0, pending: 0, percent: 0 },
      lastError: null,
    },
    startAutoPilot: vi.fn(),
  }),
}));

// ─── Mock useUrlState (used by HierarchyTreeSection) ────────────────────────

vi.mock('@/hooks/use-url-state', () => ({
  useUrlState: () => [
    { tab: 'overview', expanded: new Set<string>() },
    vi.fn(),
  ],
  enumParam: (_key: string, _values: readonly string[], defaultVal: string) => defaultVal,
  stringSetParam: (_key: string) => new Set<string>(),
}));

// ─── Mock heavy sub-components ───────────────────────────────────────────────

vi.mock('@/components/codeboard/ExecutionModal', () => ({
  ExecutionModal: () => null,
}));

vi.mock('@/components/codeboard/comments-section', () => ({
  CommentsSection: () =>
    React.createElement('div', { 'data-testid': 'comments-section' }, 'Comments'),
}));

vi.mock('@/components/codeboard/ImplementationTab', () => ({
  ImplementationTab: () => null,
}));

vi.mock('@/components/codeboard/FeatureSearchBar', () => ({
  FeatureSearchBar: () => null,
  applyFeatureSearchFilters: (_issues: unknown[], _filters: unknown) => {
    // Return all ids so nothing gets filtered out
    if (Array.isArray(_issues)) {
      return new Set(_issues.map((i: { id?: string }) => i.id));
    }
    return new Set<string>();
  },
  DEFAULT_FEATURE_SEARCH_FILTERS: {
    query: '',
    types: [],
    statuses: [],
    priorities: [],
    dateField: null,
    dateRange: { start: null, end: null },
  },
}));

vi.mock('@/components/codeboard/EpicSearchBar', () => ({
  EpicSearchBar: () => null,
  applyEpicSearchFilters: (
    _issues: unknown[],
    _filters: unknown,
  ): { visibleIds: Set<string>; matchIds: Set<string>; scores: Map<string, number> } => ({
    visibleIds: new Set<string>(),
    matchIds: new Set<string>(),
    scores: new Map<string, number>(),
  }),
  DEFAULT_EPIC_SEARCH_FILTERS: {
    query: '',
    types: [],
    statuses: [],
    priorities: [],
    dateField: null,
    dateRange: { start: null, end: null },
  },
  RelevanceBadge: () => null,
  highlightEpicMatch: (text: string) => text,
}));

vi.mock('@/components/codeboard/FeatureTestingPanel', () => ({
  FeatureTestingPanel: () => null,
}));

vi.mock('@/components/codeboard/InlineTerminalPanel', () => ({
  InlineTerminalPanel: () => null,
}));

vi.mock('@/components/codeboard/IssueSearchBar', () => ({
  highlightMatch: (text: string) => text,
}));

vi.mock('@/lib/codeboard', () => ({
  isExecutableType: (type: string) =>
    ['TASK', 'SUBTASK', 'BUG', 'STORY'].includes(type),
}));

vi.mock('@/components/codeboard/AutoPilotConfigModal', () => ({
  AutoPilotConfigModal: () => null,
}));

// ─── Mock lucide-react — proxy so any named export returns a stub ────────────

vi.mock('lucide-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lucide-react')>();
  const stub =
    (name: string) =>
    (props: Record<string, unknown>) =>
      React.createElement('span', { 'data-testid': `icon-${name}`, ...props });

  const stubs: Record<string, unknown> = {};
  for (const key of Object.keys(actual)) {
    stubs[key] = stub(key);
  }
  return stubs;
});

// ─── Import components after mocks ───────────────────────────────────────────

import { HierarchyTreeSection } from '@/components/codeboard/HierarchyTreeSection';
import { ParentBreadcrumb } from '@/components/codeboard/ParentBreadcrumb';
import { ExecuteButton } from '@/components/codeboard/ExecuteButton';

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('BUG detail view components (CB-2706)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentIssue = bugWithChildren;
  });

  // ── CB-2708: BUG with children → HierarchyTreeSection renders ────────────

  describe('CB-2708: BUG with children → tree section renders child rows', () => {
    it('renders all 3 child issue keys inside the HierarchyTreeSection', () => {
      currentIssue = bugWithChildren;
      render(
        <HierarchyTreeSection
          issueId="bug-1"
          projectId="proj-1"
          viewKind="bug"
        />,
      );

      expect(screen.getByText('CB-501')).toBeInTheDocument();
      expect(screen.getByText('CB-502')).toBeInTheDocument();
      expect(screen.getByText('CB-503')).toBeInTheDocument();
    });

    it('renders all 3 child titles inside the HierarchyTreeSection', () => {
      currentIssue = bugWithChildren;
      render(
        <HierarchyTreeSection
          issueId="bug-1"
          projectId="proj-1"
          viewKind="bug"
        />,
      );

      expect(screen.getByText('Child Task One')).toBeInTheDocument();
      expect(screen.getByText('Child Task Two')).toBeInTheDocument();
      expect(screen.getByText('Child Task Three')).toBeInTheDocument();
    });

    it('shows the Auto Pilot button when there are executable child tasks', () => {
      currentIssue = bugWithChildren;
      render(
        <HierarchyTreeSection
          issueId="bug-1"
          projectId="proj-1"
          viewKind="bug"
        />,
      );

      // The component renders "Auto Pilot (N)" button when executableTasks.length > 0
      const autoPilotBtn = screen.getByRole('button', { name: /auto pilot/i });
      expect(autoPilotBtn).toBeInTheDocument();
    });
  });

  // ── CB-2709: BUG with parentId → ParentBreadcrumb shows ancestor chain ───

  describe('CB-2709: BUG with parentId → breadcrumb shows ancestor chain', () => {
    it('renders a nav with aria-label "Parent hierarchy" for bugWithParent', () => {
      currentIssue = bugWithParent;
      render(<ParentBreadcrumb issueId="bug-2" />);

      const nav = screen.getByRole('navigation', { name: /parent hierarchy/i });
      expect(nav).toBeInTheDocument();
    });

    it('includes the ancestor FEATURE key CB-100 in the breadcrumb', () => {
      currentIssue = bugWithParent;
      render(<ParentBreadcrumb issueId="bug-2" />);

      // ParentBreadcrumb calls useIssue(bug-2) → finds parentId=feat-1
      // Then calls useIssue(feat-1) → returns featureAncestor
      const nav = screen.getByRole('navigation', { name: /parent hierarchy/i });
      expect(nav).toHaveTextContent('CB-100');
    });

    it('includes the ancestor FEATURE title in the breadcrumb', () => {
      currentIssue = bugWithParent;
      render(<ParentBreadcrumb issueId="bug-2" />);

      const nav = screen.getByRole('navigation', { name: /parent hierarchy/i });
      expect(nav).toHaveTextContent('Root Feature');
    });

    it('renders null (no nav) when issueId has no parentId (leaf issue)', () => {
      currentIssue = leafBug;
      const { container } = render(<ParentBreadcrumb issueId="bug-3" />);

      // leafBug has no parentId so no ancestors are found → component returns null
      expect(container.firstChild).toBeNull();
      expect(screen.queryByRole('navigation', { name: /parent hierarchy/i })).not.toBeInTheDocument();
    });
  });

  // ── CB-2710: AutoPilot button calls correct endpoint ──────────────────────

  describe('CB-2710: Execute button calls useStartExecution with the BUG id', () => {
    it('clicking Execute → Claude Code calls mutateAsync with bugWithChildren.id', async () => {
      currentIssue = bugWithChildren;
      const onExecutionStart = vi.fn();
      render(<ExecuteButton issue={bugWithChildren} onExecutionStart={onExecutionStart} size="md" />);

      // Open the Execute dropdown
      const executeBtn = screen.getByRole('button', { name: /execute/i });
      fireEvent.click(executeBtn);

      // Click "Claude Code" option
      const claudeCodeOption = await screen.findByRole('button', { name: /claude code/i });
      fireEvent.click(claudeCodeOption);

      // mutateAsync must have been called with the BUG's id
      await waitFor(() => {
        expect(mockStartExecutionMutateAsync).toHaveBeenCalledTimes(1);
      });

      const callArg = mockStartExecutionMutateAsync.mock.calls[0][0] as {
        issueId: string;
        provider: string;
      };
      expect(callArg.issueId).toBe('bug-1');
      expect(callArg.provider).toBe('claude_code');
    });

    it('onExecutionStart callback receives the returned session_id', async () => {
      currentIssue = bugWithChildren;
      const onExecutionStart = vi.fn();
      render(<ExecuteButton issue={bugWithChildren} onExecutionStart={onExecutionStart} size="md" />);

      fireEvent.click(screen.getByRole('button', { name: /execute/i }));
      fireEvent.click(await screen.findByRole('button', { name: /claude code/i }));

      await waitFor(() => {
        expect(onExecutionStart).toHaveBeenCalledWith('sess-abc');
      });
    });
  });

  // ── CB-2711: Leaf BUG → metadata-only view ───────────────────────────────

  describe('CB-2711: Leaf BUG — HierarchyTreeSection and ParentBreadcrumb absent', () => {
    it('HierarchyTreeSection with no descendants renders "No issues found" placeholder', () => {
      // When issueId has no children in the issues list, tree shows placeholder
      currentIssue = leafBug;

      // Override useIssues to return only the leaf bug with no children
      vi.mocked(
        // We rely on the module mock — useIssues always returns items from `currentIssue`
        // For leaf bug the items array won't contain children with parentId=bug-3
        // But we still need to render the component — it will show empty state
        // The HierarchyTreeSection itself doesn't prevent rendering; the PAGE does.
        // So we verify the page's conditional: hasChildren drives whether to mount HierarchyTreeSection.
        // Here we test that HierarchyTreeSection shows empty state when no descendants found.
        // We assert the Overview tab is present (component mounted) but tree shows empty.
      );

      render(
        <HierarchyTreeSection
          issueId="bug-3"
          projectId="proj-1"
          viewKind="bug"
        />,
      );

      // Tree shows "No issues found" when there are no descendants
      expect(screen.getByText(/no issues found under this issue/i)).toBeInTheDocument();
    });

    it('ParentBreadcrumb renders nothing for a leaf bug with no parentId', () => {
      currentIssue = leafBug;
      const { container } = render(<ParentBreadcrumb issueId="bug-3" />);

      expect(container.firstChild).toBeNull();
    });

    it('page-level: hasChildren=false means HierarchyTreeSection is NOT mounted', () => {
      // Verify the conditional logic: page only mounts HierarchyTreeSection when hasChildren.
      // We test this by rendering a minimal wrapper that mirrors the page's conditional.
      currentIssue = leafBug;

      const BugDetailConditionals = ({
        issue,
      }: {
        issue: Issue;
      }) => {
        const children =
          issue.children && issue.children.length > 0 ? issue.children : [];
        const hasChildren = children.length > 0;

        return (
          <div>
            {issue.parentId && (
              <ParentBreadcrumb issueId={issue.id} />
            )}
            <h1>{issue.title}</h1>
            {issue.description && <p>{issue.description}</p>}
            {hasChildren && (
              <HierarchyTreeSection
                issueId={issue.id}
                projectId={issue.projectId}
                viewKind="bug"
              />
            )}
            <div data-testid="comments-section">Comments</div>
          </div>
        );
      };

      render(<BugDetailConditionals issue={leafBug} />);

      // Title + description visible
      expect(screen.getByText('Leaf bug description present')).toBeInTheDocument();
      expect(screen.getByText('Some detailed description text for the bug')).toBeInTheDocument();

      // Comments section present
      expect(screen.getByTestId('comments-section')).toBeInTheDocument();

      // No HierarchyTreeSection (no Overview/Testing tabs)
      expect(screen.queryByRole('button', { name: /^overview$/i })).not.toBeInTheDocument();

      // No ParentBreadcrumb nav
      expect(
        screen.queryByRole('navigation', { name: /parent hierarchy/i }),
      ).not.toBeInTheDocument();
    });

    it('page-level: issue WITH parentId → ParentBreadcrumb IS mounted', () => {
      currentIssue = bugWithParent;

      const BugDetailConditionals = ({ issue }: { issue: Issue }) => {
        return (
          <div>
            {issue.parentId && <ParentBreadcrumb issueId={issue.id} />}
            <h1>{issue.title}</h1>
          </div>
        );
      };

      render(<BugDetailConditionals issue={bugWithParent} />);

      // Breadcrumb nav is present
      expect(
        screen.getByRole('navigation', { name: /parent hierarchy/i }),
      ).toBeInTheDocument();
    });
  });
});
