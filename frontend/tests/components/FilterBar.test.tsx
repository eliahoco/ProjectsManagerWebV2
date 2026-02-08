/**
 * Unit Tests for FilterBar Component
 * Task: CB-1116 - Testing framework for frontend UI
 * Part of STORY CB-1112: User can Filter Results by Date Range
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FilterBar } from '@/components/codeboard/FilterBar';
import type { SortField, SortOrder } from '@/types/codeboard';

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  Search: ({ className }: { className?: string }) => (
    <span data-testid="search-icon" className={className} />
  ),
  Filter: ({ className }: { className?: string }) => (
    <span data-testid="filter-icon" className={className} />
  ),
  X: ({ className }: { className?: string }) => (
    <span data-testid="x-icon" className={className} />
  ),
  ArrowUpDown: ({ className }: { className?: string }) => (
    <span data-testid="arrow-updown-icon" className={className} />
  ),
  ArrowUp: ({ className }: { className?: string }) => (
    <span data-testid="arrow-up-icon" className={className} />
  ),
  ArrowDown: ({ className }: { className?: string }) => (
    <span data-testid="arrow-down-icon" className={className} />
  ),
  Sparkles: ({ className }: { className?: string }) => (
    <span data-testid="sparkles-icon" className={className} />
  ),
  Tag: ({ className }: { className?: string }) => (
    <span data-testid="tag-icon" className={className} />
  ),
  Calendar: ({ className }: { className?: string }) => (
    <span data-testid="calendar-icon" className={className} />
  ),
  ChevronLeft: ({ className }: { className?: string }) => (
    <span data-testid="chevron-left-icon" className={className} />
  ),
  ChevronRight: ({ className }: { className?: string }) => (
    <span data-testid="chevron-right-icon" className={className} />
  ),
}));

// Mock keyboard shortcuts
vi.mock('@/hooks/use-keyboard-shortcuts', () => ({
  formatShortcut: vi.fn(() => '/'),
  SHORTCUTS: {
    FOCUS_SEARCH: { key: '/', description: 'Focus search input' },
  },
}));

describe('FilterBar', () => {
  const defaultProps = {
    onSearchChange: vi.fn(),
    onTypeChange: vi.fn(),
    onPriorityChange: vi.fn(),
    onSortChange: vi.fn(),
    search: '',
    selectedType: null as string | null,
    selectedPriority: null as string | null,
    sortField: 'sequence' as SortField,
    sortOrder: 'asc' as SortOrder,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the search input', () => {
      render(<FilterBar {...defaultProps} />);
      expect(screen.getByPlaceholderText(/Search issues/)).toBeInTheDocument();
    });

    it('should render the search icon', () => {
      render(<FilterBar {...defaultProps} />);
      expect(screen.getByTestId('search-icon')).toBeInTheDocument();
    });

    it('should render the filter toggle button', () => {
      render(<FilterBar {...defaultProps} />);
      expect(screen.getByText('Filters')).toBeInTheDocument();
    });

    it('should render sort controls', () => {
      render(<FilterBar {...defaultProps} />);
      expect(screen.getByTestId('arrow-updown-icon')).toBeInTheDocument();
    });

    it('should render sort field dropdown with correct initial value', () => {
      render(<FilterBar {...defaultProps} />);
      const sortSelect = screen.getByDisplayValue('Manual Order');
      expect(sortSelect).toBeInTheDocument();
    });

    it('should show ascending sort icon when sortOrder is asc', () => {
      render(<FilterBar {...defaultProps} sortOrder="asc" />);
      expect(screen.getByTestId('arrow-up-icon')).toBeInTheDocument();
    });

    it('should show descending sort icon when sortOrder is desc', () => {
      render(<FilterBar {...defaultProps} sortOrder="desc" />);
      expect(screen.getByTestId('arrow-down-icon')).toBeInTheDocument();
    });

    it('should not show filter dropdowns initially', () => {
      render(<FilterBar {...defaultProps} />);
      expect(screen.queryByDisplayValue('All Types')).not.toBeInTheDocument();
      expect(screen.queryByDisplayValue('All Priorities')).not.toBeInTheDocument();
    });
  });

  describe('Search', () => {
    it('should display current search value', () => {
      render(<FilterBar {...defaultProps} search="test query" />);
      expect(screen.getByDisplayValue('test query')).toBeInTheDocument();
    });

    it('should call onSearchChange when typing', async () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      await userEvent.type(input, 'a');

      expect(onSearchChange).toHaveBeenCalled();
    });

    it('should call onSearchChange with full value on input change', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      fireEvent.change(input, { target: { value: 'test query' } });

      expect(onSearchChange).toHaveBeenCalledWith('test query');
    });
  });

  describe('AI Search Button', () => {
    it('should render AI Search button when onSemanticSearchClick is provided', () => {
      render(
        <FilterBar {...defaultProps} onSemanticSearchClick={vi.fn()} />
      );
      expect(screen.getByText('AI Search')).toBeInTheDocument();
    });

    it('should not render AI Search button when onSemanticSearchClick is not provided', () => {
      render(<FilterBar {...defaultProps} />);
      expect(screen.queryByText('AI Search')).not.toBeInTheDocument();
    });

    it('should call onSemanticSearchClick when AI Search is clicked', async () => {
      const onSemanticSearchClick = vi.fn();
      render(
        <FilterBar {...defaultProps} onSemanticSearchClick={onSemanticSearchClick} />
      );

      await userEvent.click(screen.getByText('AI Search'));
      expect(onSemanticSearchClick).toHaveBeenCalledTimes(1);
    });
  });

  describe('Filter Toggle', () => {
    it('should show filter dropdowns when Filters button is clicked', async () => {
      render(<FilterBar {...defaultProps} />);

      await userEvent.click(screen.getByText('Filters'));

      expect(screen.getByDisplayValue('All Types')).toBeInTheDocument();
      expect(screen.getByDisplayValue('All Priorities')).toBeInTheDocument();
    });

    it('should hide filter dropdowns when Filters button is clicked again', async () => {
      render(<FilterBar {...defaultProps} />);

      await userEvent.click(screen.getByText('Filters'));
      expect(screen.getByDisplayValue('All Types')).toBeInTheDocument();

      await userEvent.click(screen.getByText('Filters'));
      expect(screen.queryByDisplayValue('All Types')).not.toBeInTheDocument();
    });
  });

  describe('Type Filter', () => {
    it('should call onTypeChange when a type is selected', async () => {
      const onTypeChange = vi.fn();
      render(<FilterBar {...defaultProps} onTypeChange={onTypeChange} />);

      // Open filters
      await userEvent.click(screen.getByText('Filters'));

      const typeSelect = screen.getByDisplayValue('All Types');
      fireEvent.change(typeSelect, { target: { value: 'BUG' } });

      expect(onTypeChange).toHaveBeenCalledWith('BUG');
    });

    it('should call onTypeChange with null when "All Types" is selected', async () => {
      const onTypeChange = vi.fn();
      render(<FilterBar {...defaultProps} onTypeChange={onTypeChange} selectedType="BUG" />);

      // Open filters
      await userEvent.click(screen.getByText('Filters'));

      // When selectedType is "BUG", the select's value is "BUG"
      const typeSelect = screen.getByDisplayValue('🐛 Bug');
      fireEvent.change(typeSelect, { target: { value: '' } });

      expect(onTypeChange).toHaveBeenCalledWith(null);
    });

    it('should list all issue types in the dropdown', async () => {
      render(<FilterBar {...defaultProps} />);
      await userEvent.click(screen.getByText('Filters'));

      const typeSelect = screen.getByDisplayValue('All Types');
      const options = typeSelect.querySelectorAll('option');

      // "All Types" + 6 issue types
      expect(options.length).toBe(7);
    });
  });

  describe('Priority Filter', () => {
    it('should call onPriorityChange when a priority is selected', async () => {
      const onPriorityChange = vi.fn();
      render(<FilterBar {...defaultProps} onPriorityChange={onPriorityChange} />);

      await userEvent.click(screen.getByText('Filters'));

      const prioritySelect = screen.getByDisplayValue('All Priorities');
      fireEvent.change(prioritySelect, { target: { value: 'HIGH' } });

      expect(onPriorityChange).toHaveBeenCalledWith('HIGH');
    });

    it('should call onPriorityChange with null when "All Priorities" is selected', async () => {
      const onPriorityChange = vi.fn();
      render(
        <FilterBar
          {...defaultProps}
          onPriorityChange={onPriorityChange}
          selectedPriority="HIGH"
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      // When selectedPriority is "HIGH", the select's displayed value is "High"
      const prioritySelect = screen.getByDisplayValue('High');
      fireEvent.change(prioritySelect, { target: { value: '' } });

      expect(onPriorityChange).toHaveBeenCalledWith(null);
    });

    it('should list all priority levels in the dropdown', async () => {
      render(<FilterBar {...defaultProps} />);
      await userEvent.click(screen.getByText('Filters'));

      const prioritySelect = screen.getByDisplayValue('All Priorities');
      const options = prioritySelect.querySelectorAll('option');

      // "All Priorities" + 4 priority levels
      expect(options.length).toBe(5);
    });
  });

  describe('Label Filter', () => {
    it('should show label filter when labels and handler are provided', async () => {
      render(
        <FilterBar
          {...defaultProps}
          availableLabels={['frontend', 'backend', 'urgent']}
          onLabelChange={vi.fn()}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      expect(screen.getByDisplayValue('All Labels')).toBeInTheDocument();
    });

    it('should not show label filter when no labels are available', async () => {
      render(
        <FilterBar
          {...defaultProps}
          availableLabels={[]}
          onLabelChange={vi.fn()}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      expect(screen.queryByDisplayValue('All Labels')).not.toBeInTheDocument();
    });

    it('should call onLabelChange when a label is selected', async () => {
      const onLabelChange = vi.fn();
      render(
        <FilterBar
          {...defaultProps}
          availableLabels={['frontend', 'backend']}
          onLabelChange={onLabelChange}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      const labelSelect = screen.getByDisplayValue('All Labels');
      fireEvent.change(labelSelect, { target: { value: 'frontend' } });

      expect(onLabelChange).toHaveBeenCalledWith('frontend');
    });
  });

  describe('Sort Controls', () => {
    it('should call onSortChange when sort field is changed', () => {
      const onSortChange = vi.fn();
      render(<FilterBar {...defaultProps} onSortChange={onSortChange} />);

      const sortSelect = screen.getByDisplayValue('Manual Order');
      fireEvent.change(sortSelect, { target: { value: 'priority' } });

      expect(onSortChange).toHaveBeenCalledWith('priority', 'asc');
    });

    it('should toggle sort order when sort direction button is clicked', async () => {
      const onSortChange = vi.fn();
      render(<FilterBar {...defaultProps} onSortChange={onSortChange} sortOrder="asc" />);

      const sortOrderButton = screen.getByTitle('Ascending (click to change)');
      await userEvent.click(sortOrderButton);

      expect(onSortChange).toHaveBeenCalledWith('sequence', 'desc');
    });

    it('should toggle from desc to asc', async () => {
      const onSortChange = vi.fn();
      render(<FilterBar {...defaultProps} onSortChange={onSortChange} sortOrder="desc" />);

      const sortOrderButton = screen.getByTitle('Descending (click to change)');
      await userEvent.click(sortOrderButton);

      expect(onSortChange).toHaveBeenCalledWith('sequence', 'asc');
    });

    it('should show all sort options', () => {
      render(<FilterBar {...defaultProps} />);

      const sortSelect = screen.getByDisplayValue('Manual Order');
      const options = sortSelect.querySelectorAll('option');

      expect(options.length).toBe(8); // 8 sort options
    });

    it('should include date-related sort options', () => {
      render(<FilterBar {...defaultProps} />);

      const sortSelect = screen.getByDisplayValue('Manual Order');
      const optionTexts = Array.from(sortSelect.querySelectorAll('option')).map(
        opt => opt.textContent
      );

      expect(optionTexts).toContain('Created Date');
      expect(optionTexts).toContain('Updated Date');
      expect(optionTexts).toContain('Due Date');
    });
  });

  describe('Active Filter Indicator', () => {
    it('should show active filter dot when search has a value', () => {
      render(<FilterBar {...defaultProps} search="query" />);
      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      expect(dot).toBeInTheDocument();
    });

    it('should show active filter dot when type is selected', () => {
      render(<FilterBar {...defaultProps} selectedType="BUG" />);
      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      expect(dot).toBeInTheDocument();
    });

    it('should show active filter dot when priority is selected', () => {
      render(<FilterBar {...defaultProps} selectedPriority="HIGH" />);
      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      expect(dot).toBeInTheDocument();
    });

    it('should not show active filter dot when no filters are active', () => {
      render(<FilterBar {...defaultProps} />);
      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      expect(dot).not.toBeInTheDocument();
    });
  });

  describe('Clear Filters', () => {
    it('should show Clear button when filters are active', () => {
      render(<FilterBar {...defaultProps} search="test" />);
      expect(screen.getByText('Clear')).toBeInTheDocument();
    });

    it('should not show Clear button when no filters are active', () => {
      render(<FilterBar {...defaultProps} />);
      expect(screen.queryByText('Clear')).not.toBeInTheDocument();
    });

    it('should clear all filters when Clear is clicked', async () => {
      const onSearchChange = vi.fn();
      const onTypeChange = vi.fn();
      const onPriorityChange = vi.fn();
      const onLabelChange = vi.fn();

      render(
        <FilterBar
          {...defaultProps}
          search="test"
          selectedType="BUG"
          selectedPriority="HIGH"
          onSearchChange={onSearchChange}
          onTypeChange={onTypeChange}
          onPriorityChange={onPriorityChange}
          onLabelChange={onLabelChange}
        />
      );

      await userEvent.click(screen.getByText('Clear'));

      expect(onSearchChange).toHaveBeenCalledWith('');
      expect(onTypeChange).toHaveBeenCalledWith(null);
      expect(onPriorityChange).toHaveBeenCalledWith(null);
      expect(onLabelChange).toHaveBeenCalledWith(null);
    });

    it('should clear date range filter when Clear is clicked', async () => {
      const onDateRangeChange = vi.fn();
      const dateRange = { start: new Date('2026-01-01'), end: new Date('2026-01-31') };

      render(
        <FilterBar
          {...defaultProps}
          search="test"
          dateFilterField="createdAt"
          dateRange={dateRange}
          onDateRangeChange={onDateRangeChange}
        />
      );

      await userEvent.click(screen.getByText('Clear'));

      expect(onDateRangeChange).toHaveBeenCalledWith(null, { start: null, end: null });
    });
  });

  describe('Date Range Filter', () => {
    it('should show date field selector when onDateRangeChange is provided and filters are open', async () => {
      render(
        <FilterBar
          {...defaultProps}
          onDateRangeChange={vi.fn()}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      expect(screen.getByDisplayValue('Date Field')).toBeInTheDocument();
    });

    it('should not show date field selector when onDateRangeChange is not provided', async () => {
      render(<FilterBar {...defaultProps} />);

      await userEvent.click(screen.getByText('Filters'));

      expect(screen.queryByDisplayValue('Date Field')).not.toBeInTheDocument();
    });

    it('should list all date filter options in the dropdown', async () => {
      render(
        <FilterBar
          {...defaultProps}
          onDateRangeChange={vi.fn()}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      const dateSelect = screen.getByDisplayValue('Date Field');
      const options = dateSelect.querySelectorAll('option');

      // "Date Field" placeholder + 5 date field options
      expect(options.length).toBe(6);
    });

    it('should call onDateRangeChange when a date field is selected', async () => {
      const onDateRangeChange = vi.fn();
      render(
        <FilterBar
          {...defaultProps}
          onDateRangeChange={onDateRangeChange}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      const dateSelect = screen.getByDisplayValue('Date Field');
      fireEvent.change(dateSelect, { target: { value: 'createdAt' } });

      expect(onDateRangeChange).toHaveBeenCalledWith('createdAt', { start: null, end: null });
    });

    it('should show DateRangePicker when a date field is selected', async () => {
      render(
        <FilterBar
          {...defaultProps}
          dateFilterField="createdAt"
          dateRange={{ start: null, end: null }}
          onDateRangeChange={vi.fn()}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      // DateRangePicker should be visible with placeholder text
      expect(screen.getByText('Select range...')).toBeInTheDocument();
    });

    it('should show active filter indicator when date range is set', () => {
      render(
        <FilterBar
          {...defaultProps}
          dateFilterField="createdAt"
          dateRange={{ start: new Date('2026-01-01'), end: new Date('2026-01-31') }}
          onDateRangeChange={vi.fn()}
        />
      );

      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      expect(dot).toBeInTheDocument();
    });

    it('should not show active filter indicator when no date range is set', () => {
      render(
        <FilterBar
          {...defaultProps}
          dateFilterField={null}
          dateRange={{ start: null, end: null }}
          onDateRangeChange={vi.fn()}
        />
      );

      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      expect(dot).not.toBeInTheDocument();
    });
  });
});
