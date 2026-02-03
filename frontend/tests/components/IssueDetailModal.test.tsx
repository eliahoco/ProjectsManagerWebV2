/**
 * Unit Tests for IssueDetailModal Component
 * Task: CB-462 - Test Task (Part of CB-21: Issue Detail View)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IssueDetailModal } from '@/components/codeboard/IssueDetailModal';
import type { Issue } from '@/types/codeboard';

// Mock the hooks
vi.mock('@/hooks/useCodeBoard', () => ({
  useIssue: vi.fn(() => ({ data: null })),
  useIssueCommits: vi.fn(() => ({ data: null })),
  useLinkedCommits: vi.fn(() => ({ data: null })),
  useStartExecution: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useExecutionStatus: vi.fn(() => ({ data: null })),
}));

const mockToast = {
  toasts: [],
  addToast: vi.fn(),
  removeToast: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
};

vi.mock('@/components/ui/toast', () => ({
  useToast: vi.fn(() => mockToast),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

// Create a test issue factory
const createTestIssue = (overrides: Partial<Issue> = {}): Issue => ({
  id: 'issue-1',
  projectId: 'project-1',
  key: 'CB-123',
  sequence: 1,
  title: 'Test Issue Title',
  description: 'Test issue description',
  type: 'TASK',
  status: 'TODO',
  priority: 'MEDIUM',
  assignee: 'John Doe',
  reporter: 'Jane Smith',
  storyPoints: 5,
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-16T10:00:00Z',
  ...overrides,
});

// Helper to render with providers
const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  );
};

describe('IssueDetailModal', () => {
  const defaultProps = {
    issue: createTestIssue(),
    issues: [],
    isOpen: true,
    onClose: vi.fn(),
    onUpdate: vi.fn(),
    onDelete: vi.fn(),
    projectId: 'project-1',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should not render when isOpen is false', () => {
      renderWithProviders(
        <IssueDetailModal {...defaultProps} isOpen={false} />
      );

      expect(screen.queryByText('Test Issue Title')).not.toBeInTheDocument();
    });

    it('should not render when issue is null', () => {
      renderWithProviders(
        <IssueDetailModal {...defaultProps} issue={null} />
      );

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('should render the issue title', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      expect(screen.getByText('Test Issue Title')).toBeInTheDocument();
    });

    it('should render the issue key with link', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      const link = screen.getByText('CB-123');
      expect(link).toBeInTheDocument();
      expect(link.closest('a')).toHaveAttribute('href', '/codeboard/issues/issue-1');
    });

    it('should render the issue description', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      expect(screen.getByText('Test issue description')).toBeInTheDocument();
    });

    it('should render the status badge', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      // Status badge is in a span with specific class
      const statusBadge = screen.getByText('To Do', { selector: 'span.text-xs' });
      expect(statusBadge).toBeInTheDocument();
    });

    it('should render the issue type icon', () => {
      const issue = createTestIssue({ type: 'BUG' });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('🐛')).toBeInTheDocument();
    });

    it('should render assignee information', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });

    it('should render reporter information', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      expect(screen.getByText('Jane Smith')).toBeInTheDocument();
    });

    it('should render story points', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('should render created date', () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      // The date format depends on locale, so we check for the date label
      expect(screen.getByText('Created:')).toBeInTheDocument();
    });

    it('should show "Unassigned" when no assignee', () => {
      const issue = createTestIssue({ assignee: undefined });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('Unassigned')).toBeInTheDocument();
    });

    it('should show "Unknown" when no reporter', () => {
      const issue = createTestIssue({ reporter: undefined });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('Unknown')).toBeInTheDocument();
    });

    it('should show "-" when no story points', () => {
      const issue = createTestIssue({ storyPoints: undefined });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('-')).toBeInTheDocument();
    });
  });

  describe('Parent Issue Display', () => {
    it('should display parent breadcrumb when issue has a parent', () => {
      const parentIssue = createTestIssue({
        id: 'parent-1',
        key: 'CB-100',
        title: 'Parent Epic',
        type: 'EPIC',
      });

      const childIssue = createTestIssue({
        id: 'child-1',
        key: 'CB-101',
        parentId: 'parent-1',
      });

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={childIssue}
          issues={[parentIssue, childIssue]}
        />
      );

      expect(screen.getByText('Part of:')).toBeInTheDocument();
      expect(screen.getByText('CB-100')).toBeInTheDocument();
      expect(screen.getByText('Parent Epic')).toBeInTheDocument();
    });

    it('should call onIssueClick when parent breadcrumb is clicked', async () => {
      const onIssueClick = vi.fn();
      const parentIssue = createTestIssue({
        id: 'parent-1',
        key: 'CB-100',
        title: 'Parent Epic',
        type: 'EPIC',
      });

      const childIssue = createTestIssue({
        id: 'child-1',
        parentId: 'parent-1',
      });

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={childIssue}
          issues={[parentIssue, childIssue]}
          onIssueClick={onIssueClick}
        />
      );

      const breadcrumb = screen.getByText('Part of:').closest('div');
      fireEvent.click(breadcrumb!);

      expect(onIssueClick).toHaveBeenCalledWith(parentIssue);
    });
  });

  describe('Child Issues Display', () => {
    it('should show child issues section for EPIC type', () => {
      const issue = createTestIssue({ type: 'EPIC' });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('Stories (0)')).toBeInTheDocument();
    });

    it('should show child issues section for STORY type', () => {
      const issue = createTestIssue({ type: 'STORY' });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('Tasks (0)')).toBeInTheDocument();
    });

    it('should not show child issues section for TASK type', () => {
      const issue = createTestIssue({ type: 'TASK' });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.queryByText(/Stories|Tasks/)).not.toBeInTheDocument();
    });

    it('should display child issues when available', () => {
      const parentIssue = createTestIssue({
        id: 'epic-1',
        key: 'CB-100',
        type: 'EPIC',
      });

      const childIssue = createTestIssue({
        id: 'story-1',
        key: 'CB-101',
        title: 'Child Story',
        type: 'STORY',
        parentId: 'epic-1',
      });

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={parentIssue}
          issues={[parentIssue, childIssue]}
        />
      );

      expect(screen.getByText('Stories (1)')).toBeInTheDocument();
      expect(screen.getByText('Child Story')).toBeInTheDocument();
      expect(screen.getByText('CB-101')).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should call onClose when close button is clicked', async () => {
      const onClose = vi.fn();
      renderWithProviders(<IssueDetailModal {...defaultProps} onClose={onClose} />);

      // Find the close button (X icon)
      const closeButtons = screen.getAllByRole('button');
      const closeButton = closeButtons.find(btn => btn.querySelector('.lucide-x'));
      fireEvent.click(closeButton!);

      expect(onClose).toHaveBeenCalled();
    });

    it('should call onClose when backdrop is clicked', async () => {
      const onClose = vi.fn();
      renderWithProviders(<IssueDetailModal {...defaultProps} onClose={onClose} />);

      // The backdrop is the div with bg-black/60 class
      const backdrop = document.querySelector('.bg-black\\/60');
      fireEvent.click(backdrop!);

      expect(onClose).toHaveBeenCalled();
    });

    it('should call onDelete when delete button is clicked', async () => {
      const onDelete = vi.fn();
      renderWithProviders(<IssueDetailModal {...defaultProps} onDelete={onDelete} />);

      // Find button with title containing "Delete"
      const deleteButton = screen.getByTitle(/Delete/);
      fireEvent.click(deleteButton);

      expect(onDelete).toHaveBeenCalled();
    });

    it('should enter edit mode when edit button is clicked', async () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      // Find button with title containing "Edit"
      const editButton = screen.getByTitle(/^Edit/);
      fireEvent.click(editButton);

      // Should now show input fields
      expect(screen.getByDisplayValue('Test Issue Title')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Test issue description')).toBeInTheDocument();
      expect(screen.getByText('Save')).toBeInTheDocument();
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });

    it('should exit edit mode when cancel is clicked', async () => {
      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      // Enter edit mode
      const editButton = screen.getByTitle(/^Edit/);
      fireEvent.click(editButton);

      // Click cancel
      fireEvent.click(screen.getByText('Cancel'));

      // Should show normal view again
      expect(screen.queryByDisplayValue('Test Issue Title')).not.toBeInTheDocument();
      expect(screen.getByText('Test Issue Title')).toBeInTheDocument();
    });

    it('should call onUpdate with edited values when save is clicked', async () => {
      const onUpdate = vi.fn();
      renderWithProviders(<IssueDetailModal {...defaultProps} onUpdate={onUpdate} />);

      // Enter edit mode
      const editButton = screen.getByTitle(/^Edit/);
      fireEvent.click(editButton);

      // Change title
      const titleInput = screen.getByDisplayValue('Test Issue Title');
      fireEvent.change(titleInput, { target: { value: 'Updated Title' } });

      // Click save
      fireEvent.click(screen.getByText('Save'));

      expect(onUpdate).toHaveBeenCalledWith({
        title: 'Updated Title',
        description: 'Test issue description',
      });
    });
  });

  describe('Status and Priority Updates', () => {
    it('should call onUpdate when status is changed', async () => {
      const onUpdate = vi.fn();
      renderWithProviders(<IssueDetailModal {...defaultProps} onUpdate={onUpdate} />);

      const statusSelect = screen.getByDisplayValue('To Do');
      fireEvent.change(statusSelect, { target: { value: 'IN_PROGRESS' } });

      expect(onUpdate).toHaveBeenCalledWith({ status: 'IN_PROGRESS' });
    });

    it('should call onUpdate when priority is changed', async () => {
      const onUpdate = vi.fn();
      renderWithProviders(<IssueDetailModal {...defaultProps} onUpdate={onUpdate} />);

      const prioritySelect = screen.getByDisplayValue('Medium');
      fireEvent.change(prioritySelect, { target: { value: 'HIGH' } });

      expect(onUpdate).toHaveBeenCalledWith({ priority: 'HIGH' });
    });

    it('should call onUpdate when type is changed', async () => {
      const onUpdate = vi.fn();
      renderWithProviders(<IssueDetailModal {...defaultProps} onUpdate={onUpdate} />);

      // Find type select - it contains the emoji with label
      const typeSelects = screen.getAllByRole('combobox');
      const typeSelect = typeSelects.find(
        select => select.querySelector('option[value="BUG"]')
      );
      fireEvent.change(typeSelect!, { target: { value: 'BUG' } });

      expect(onUpdate).toHaveBeenCalledWith({ type: 'BUG' });
    });
  });

  describe('AI Breakdown Button', () => {
    it('should show AI Breakdown button for EPIC type', () => {
      const issue = createTestIssue({ type: 'EPIC' });
      const onAIBreakdown = vi.fn();

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={issue}
          onAIBreakdown={onAIBreakdown}
        />
      );

      expect(screen.getByText('AI Breakdown')).toBeInTheDocument();
    });

    it('should show AI Breakdown button for STORY type', () => {
      const issue = createTestIssue({ type: 'STORY' });
      const onAIBreakdown = vi.fn();

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={issue}
          onAIBreakdown={onAIBreakdown}
        />
      );

      expect(screen.getByText('AI Breakdown')).toBeInTheDocument();
    });

    it('should not show AI Breakdown button for TASK type', () => {
      const issue = createTestIssue({ type: 'TASK' });
      const onAIBreakdown = vi.fn();

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={issue}
          onAIBreakdown={onAIBreakdown}
        />
      );

      expect(screen.queryByText('AI Breakdown')).not.toBeInTheDocument();
    });

    it('should call onAIBreakdown when button is clicked', () => {
      const issue = createTestIssue({ type: 'EPIC' });
      const onAIBreakdown = vi.fn();

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={issue}
          onAIBreakdown={onAIBreakdown}
        />
      );

      fireEvent.click(screen.getByText('AI Breakdown'));

      expect(onAIBreakdown).toHaveBeenCalledWith(issue);
    });
  });

  describe('Copy Issue Key', () => {
    it('should copy issue key when copy button is clicked', async () => {
      const { useToast } = await import('@/components/ui/toast');
      const localMockToast = {
        toasts: [],
        addToast: vi.fn(),
        removeToast: vi.fn(),
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn(),
        warning: vi.fn(),
      };
      vi.mocked(useToast).mockReturnValue(localMockToast);

      renderWithProviders(<IssueDetailModal {...defaultProps} />);

      const copyButtons = screen.getAllByRole('button');
      const copyButton = copyButtons.find(btn => btn.querySelector('.lucide-copy'));
      fireEvent.click(copyButton!);

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('CB-123');
    });
  });

  describe('Date Displays', () => {
    it('should render started date when available', () => {
      const issue = createTestIssue({ startedAt: '2024-01-17T10:00:00Z' });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('Started:')).toBeInTheDocument();
    });

    it('should render completed date when available', () => {
      const issue = createTestIssue({ completedAt: '2024-01-18T10:00:00Z' });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('Completed:')).toBeInTheDocument();
    });

    it('should render due date when available', () => {
      const issue = createTestIssue({ dueDate: '2024-01-20T10:00:00Z' });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText('Due:')).toBeInTheDocument();
    });

    it('should highlight overdue dates in red', () => {
      // Set a past due date
      const pastDate = new Date();
      pastDate.setDate(pastDate.getDate() - 5);
      const issue = createTestIssue({ dueDate: pastDate.toISOString() });

      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      // The due date span should have red text class
      const dueLabel = screen.getByText('Due:');
      const dueDateContainer = dueLabel.closest('div');
      const dateSpan = dueDateContainer?.querySelector('.text-red-500');
      expect(dateSpan).toBeInTheDocument();
    });
  });

  describe('Child Selection and Batch Execution', () => {
    it('should allow selecting child issues', () => {
      const parentIssue = createTestIssue({
        id: 'epic-1',
        key: 'CB-100',
        type: 'EPIC',
      });

      const childIssue = createTestIssue({
        id: 'story-1',
        key: 'CB-101',
        title: 'Child Story',
        type: 'STORY',
        parentId: 'epic-1',
      });

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={parentIssue}
          issues={[parentIssue, childIssue]}
        />
      );

      // Find and click the checkbox button
      const checkboxButtons = screen.getAllByRole('button');
      const checkboxButton = checkboxButtons.find(btn =>
        btn.querySelector('.lucide-square') || btn.querySelector('.lucide-check-square')
      );

      if (checkboxButton) {
        fireEvent.click(checkboxButton);
        // After clicking, should show execute button
        expect(screen.getByText(/Execute.*Selected/)).toBeInTheDocument();
      }
    });

    it('should show Select All / Deselect All toggle', () => {
      const parentIssue = createTestIssue({
        id: 'epic-1',
        type: 'EPIC',
      });

      const childIssue = createTestIssue({
        id: 'story-1',
        parentId: 'epic-1',
        type: 'STORY',
      });

      renderWithProviders(
        <IssueDetailModal
          {...defaultProps}
          issue={parentIssue}
          issues={[parentIssue, childIssue]}
        />
      );

      expect(screen.getByText('Select All')).toBeInTheDocument();
    });
  });

  describe('Issue Types Display', () => {
    it.each([
      ['EPIC', '⚡'],
      ['STORY', '📖'],
      ['TASK', '✓'],
      ['SUBTASK', '○'],
      ['BUG', '🐛'],
    ] as const)('should display correct icon for %s type', (type, expectedIcon) => {
      const issue = createTestIssue({ type });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      expect(screen.getByText(expectedIcon)).toBeInTheDocument();
    });
  });

  describe('Status Display', () => {
    it.each([
      ['BACKLOG', 'Backlog'],
      ['TODO', 'To Do'],
      ['IN_PROGRESS', 'In Progress'],
      ['IN_REVIEW', 'In Review'],
      ['DONE', 'Done'],
    ] as const)('should display correct label for %s status', (status, expectedLabel) => {
      const issue = createTestIssue({ status });
      renderWithProviders(<IssueDetailModal {...defaultProps} issue={issue} />);

      // Status badge is in a span with specific class (not in dropdown options)
      const statusBadge = screen.getByText(expectedLabel, { selector: 'span.text-xs' });
      expect(statusBadge).toBeInTheDocument();
    });
  });
});
