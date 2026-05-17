/**
 * Tests for FeatureExecutionPanel — CB-2383
 * Confirms BUG-type issues are treated as executable (shown in list, per-row Run button, auto-selected).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// ─── Mock AutoPilotContext ───────────────────────────────────────────────────

const mockAutoPilotState = {
  isActive: false,
  isPaused: false,
  featureId: null,
  queue: [],
  currentIndex: 0,
  progress: { total: 0, completed: 0, skipped: 0, failed: 0, pending: 0, percent: 0 },
  lastError: null,
};

const mockStartAutoPilot = vi.fn();

vi.mock('@/contexts/AutoPilotContext', () => ({
  useAutoPilot: () => ({
    state: mockAutoPilotState,
    startAutoPilot: mockStartAutoPilot,
  }),
}));

// ─── Mock useIssueDescendants ────────────────────────────────────────────────

const mockDescendants: import('@/types/codeboard').Issue[] = [];

vi.mock('@/hooks/useCodeBoard', () => ({
  useIssueDescendants: () => ({ data: mockDescendants, isLoading: false }),
}));

// ─── Mock AutoPilotConfigModal ───────────────────────────────────────────────

vi.mock('@/components/codeboard/AutoPilotConfigModal', () => ({
  AutoPilotConfigModal: () => null,
}));

// ─── Mock lucide-react (minimal) ─────────────────────────────────────────────

vi.mock('lucide-react', () => {
  const stub = (name: string) => (p: Record<string, unknown>) =>
    React.createElement('span', { 'data-testid': `icon-${name}`, ...p });
  return {
    X: stub('X'),
    Play: stub('Play'),
    CheckCircle2: stub('CheckCircle2'),
    Circle: stub('Circle'),
    ChevronRight: stub('ChevronRight'),
    ChevronDown: stub('ChevronDown'),
    Loader2: stub('Loader2'),
    AlertCircle: stub('AlertCircle'),
    SkipForward: stub('SkipForward'),
    Rocket: stub('Rocket'),
    ArrowRight: stub('ArrowRight'),
    Clock: stub('Clock'),
    Zap: stub('Zap'),
    Eye: stub('Eye'),
    RotateCcw: stub('RotateCcw'),
  };
});

// ─── Import after mocks ───────────────────────────────────────────────────────

import { FeatureExecutionPanel } from '@/components/codeboard/FeatureExecutionPanel';
import type { Issue } from '@/types/codeboard';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeIssue(overrides: Partial<Issue> & { id: string; key: string; type: Issue['type'] }): Issue {
  return {
    projectId: 'p-1',
    sequence: 1,
    title: 'Test issue',
    status: 'BACKLOG',
    priority: 'MEDIUM',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

// ─── CB-2789: initialSelectedIds pre-seeds selection ─────────────────────────

describe('FeatureExecutionPanel — initialSelectedIds (CB-2789)', () => {
  const featureIssue = makeIssue({ id: 'f-2', key: 'CB-200', type: 'FEATURE', title: 'Feature' });
  const task1 = makeIssue({ id: 't-1', key: 'CB-201', type: 'TASK', status: 'BACKLOG', title: 'Task 1', parentId: 'f-2' });
  const task2 = makeIssue({ id: 't-2', key: 'CB-202', type: 'TASK', status: 'BACKLOG', title: 'Task 2', parentId: 'f-2' });

  beforeEach(() => {
    mockDescendants.length = 0;
    mockDescendants.push(task1, task2);
    mockStartAutoPilot.mockClear();
  });

  it('pre-selects only the provided ids when initialSelectedIds is non-empty', () => {
    render(
      <FeatureExecutionPanel
        feature={featureIssue}
        allIssues={[featureIssue, task1, task2]}
        projectId="p-1"
        isOpen={true}
        onClose={vi.fn()}
        initialSelectedIds={new Set(['t-1'])}
      />
    );
    // Only 1 of 2 tasks should be pre-selected
    expect(screen.getByText(/1 items? selected/i)).toBeInTheDocument();
  });

  it('falls back to all executable when initialSelectedIds has no matching executables', () => {
    render(
      <FeatureExecutionPanel
        feature={featureIssue}
        allIssues={[featureIssue, task1, task2]}
        projectId="p-1"
        isOpen={true}
        onClose={vi.fn()}
        initialSelectedIds={new Set(['non-existent-id'])}
      />
    );
    // Falls back to all 2 tasks selected
    expect(screen.getByText(/2 items? selected/i)).toBeInTheDocument();
  });

  it('selects all when initialSelectedIds is absent (backwards-compat)', () => {
    render(
      <FeatureExecutionPanel
        feature={featureIssue}
        allIssues={[featureIssue, task1, task2]}
        projectId="p-1"
        isOpen={true}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText(/2 items? selected/i)).toBeInTheDocument();
  });
});

// ─── Original test suite ──────────────────────────────────────────────────────

describe('FeatureExecutionPanel — BUG executable (CB-2383)', () => {
  const featureIssue = makeIssue({ id: 'f-1', key: 'CB-1', type: 'FEATURE', title: 'My Feature' });
  const bugIssue = makeIssue({
    id: 'bug-1',
    key: 'CB-99',
    type: 'BUG',
    status: 'BACKLOG',
    title: 'Critical crash on login',
    parentId: 'f-1',
  });

  beforeEach(() => {
    // Seed descendants with the BUG
    mockDescendants.length = 0;
    mockDescendants.push(bugIssue);
    mockStartAutoPilot.mockClear();
  });

  it('renders a child BUG as an executable row', () => {
    render(
      <FeatureExecutionPanel
        feature={featureIssue}
        allIssues={[featureIssue, bugIssue]}
        projectId="p-1"
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    // BUG key appears in the issue list
    expect(screen.getByText('CB-99')).toBeInTheDocument();
    // BUG title appears
    expect(screen.getByText('Critical crash on login')).toBeInTheDocument();
  });

  it('auto-selects the BUG id (shown in selection count)', () => {
    render(
      <FeatureExecutionPanel
        feature={featureIssue}
        allIssues={[featureIssue, bugIssue]}
        projectId="p-1"
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    // "1 items selected" confirms the BUG is in the auto-selected set
    expect(screen.getByText(/1 items? selected/i)).toBeInTheDocument();
  });

  it('shows the selection checkbox (per-row Run) for the BUG row', () => {
    render(
      <FeatureExecutionPanel
        feature={featureIssue}
        allIssues={[featureIssue, bugIssue]}
        projectId="p-1"
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    // The BUG row has a checkbox button (isExecutable path).
    // We look for a button near CB-99 that functions as the selection toggle.
    // Since the BUG is auto-selected, it renders a filled checkbox with CheckCircle2.
    const checkIcons = screen.getAllByTestId('icon-CheckCircle2');
    // At least one CheckCircle2 inside a button (the selection checkbox)
    const inButton = checkIcons.find(el => el.closest('button'));
    expect(inButton).toBeTruthy();
  });

  it('calls startAutoPilot with the BUG in the queue when Manual Start is clicked', async () => {
    const { findByRole } = render(
      <FeatureExecutionPanel
        feature={featureIssue}
        allIssues={[featureIssue, bugIssue]}
        projectId="p-1"
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    const manualStartBtn = await findByRole('button', { name: /manual start/i });
    manualStartBtn.click();

    expect(mockStartAutoPilot).toHaveBeenCalledTimes(1);
    const callArg = mockStartAutoPilot.mock.calls[0][0] as { queue: { issue: { id: string } }[] };
    expect(callArg.queue.some(item => item.issue.id === 'bug-1')).toBe(true);
  });
});
