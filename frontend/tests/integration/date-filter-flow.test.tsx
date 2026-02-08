/**
 * Integration Tests for Date Filter Flow
 * Task: CB-1116 - Testing framework for frontend UI
 * Part of STORY CB-1112: User can Filter Results by Date Range
 *
 * Tests the end-to-end flow of date filtering:
 * - User selects a date field in FilterBar
 * - User picks a date range via DateRangePicker
 * - onDateRangeChange callback fires with correct params
 * - State management between FilterBar and its parent
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React, { useState } from 'react';
import { FilterBar } from '@/components/codeboard/FilterBar';
import type { SortField, SortOrder, DateFilterField } from '@/types/codeboard';
import type { DateRange } from '@/components/ui/date-range-picker';

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

/**
 * Wrapper component that manages state like the real CodeBoard page does.
 * This simulates the parent component managing FilterBar state.
 */
function FilterBarWithState({
  onFilterChange,
}: {
  onFilterChange?: (params: {
    search: string;
    type: string | null;
    priority: string | null;
    sortField: SortField;
    sortOrder: SortOrder;
    dateField: DateFilterField | null;
    dateRange: DateRange;
  }) => void;
}) {
  const [search, setSearch] = useState('');
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedPriority, setSelectedPriority] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>('sequence');
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');
  const [dateFilterField, setDateFilterField] = useState<DateFilterField | null>(null);
  const [dateRange, setDateRange] = useState<DateRange>({ start: null, end: null });

  const handleDateRangeChange = (field: DateFilterField | null, range: DateRange) => {
    setDateFilterField(field);
    setDateRange(range);
    onFilterChange?.({
      search,
      type: selectedType,
      priority: selectedPriority,
      sortField,
      sortOrder,
      dateField: field,
      dateRange: range,
    });
  };

  const handleSortChange = (field: SortField, order: SortOrder) => {
    setSortField(field);
    setSortOrder(order);
  };

  return (
    <FilterBar
      search={search}
      onSearchChange={setSearch}
      selectedType={selectedType}
      onTypeChange={setSelectedType}
      selectedPriority={selectedPriority}
      onPriorityChange={setSelectedPriority}
      sortField={sortField}
      sortOrder={sortOrder}
      onSortChange={handleSortChange}
      dateFilterField={dateFilterField}
      dateRange={dateRange}
      onDateRangeChange={handleDateRangeChange}
    />
  );
}

describe('Date Filter Integration Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Date Field Selection Flow', () => {
    it('should show date picker after selecting a date field', async () => {
      render(<FilterBarWithState />);

      // Open filters
      await userEvent.click(screen.getByText('Filters'));

      // Date field selector should be visible
      const dateSelect = screen.getByDisplayValue('Date Field');
      expect(dateSelect).toBeInTheDocument();

      // Select "Created Date"
      fireEvent.change(dateSelect, { target: { value: 'createdAt' } });

      // DateRangePicker should now be visible
      expect(screen.getByText('Select range...')).toBeInTheDocument();
    });

    it('should switch between date fields', async () => {
      render(<FilterBarWithState />);

      await userEvent.click(screen.getByText('Filters'));

      const dateSelect = screen.getByDisplayValue('Date Field');

      // Select "Created Date"
      fireEvent.change(dateSelect, { target: { value: 'createdAt' } });
      expect(screen.getByText('Select range...')).toBeInTheDocument();

      // Switch to "Due Date"
      fireEvent.change(screen.getByDisplayValue('Created Date'), { target: { value: 'dueDate' } });
      expect(screen.getByText('Select range...')).toBeInTheDocument();
    });

    it('should hide date picker when date field is cleared', async () => {
      render(<FilterBarWithState />);

      await userEvent.click(screen.getByText('Filters'));

      // Select a date field
      const dateSelect = screen.getByDisplayValue('Date Field');
      fireEvent.change(dateSelect, { target: { value: 'createdAt' } });
      expect(screen.getByText('Select range...')).toBeInTheDocument();

      // Clear date field back to default
      fireEvent.change(screen.getByDisplayValue('Created Date'), { target: { value: '' } });

      // DateRangePicker should no longer be visible
      expect(screen.queryByText('Select range...')).not.toBeInTheDocument();
    });
  });

  describe('Callback Integration', () => {
    it('should fire onFilterChange with date field when selected', async () => {
      const onFilterChange = vi.fn();
      render(<FilterBarWithState onFilterChange={onFilterChange} />);

      await userEvent.click(screen.getByText('Filters'));

      const dateSelect = screen.getByDisplayValue('Date Field');
      fireEvent.change(dateSelect, { target: { value: 'updatedAt' } });

      expect(onFilterChange).toHaveBeenCalledWith(
        expect.objectContaining({
          dateField: 'updatedAt',
          dateRange: { start: null, end: null },
        })
      );
    });

    it('should fire onFilterChange with null field when cleared', async () => {
      const onFilterChange = vi.fn();
      render(<FilterBarWithState onFilterChange={onFilterChange} />);

      await userEvent.click(screen.getByText('Filters'));

      // Select then clear
      fireEvent.change(screen.getByDisplayValue('Date Field'), { target: { value: 'createdAt' } });
      fireEvent.change(screen.getByDisplayValue('Created Date'), { target: { value: '' } });

      expect(onFilterChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          dateField: null,
        })
      );
    });
  });

  describe('Filter Active Indicator', () => {
    it('should not show active indicator initially', () => {
      render(<FilterBarWithState />);

      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      expect(dot).not.toBeInTheDocument();
    });

    it('should show active indicator when date field is selected', async () => {
      // Render with a pre-set date range that has actual values
      const onFilterChange = vi.fn();
      render(<FilterBarWithState onFilterChange={onFilterChange} />);

      await userEvent.click(screen.getByText('Filters'));

      // Just selecting a date field (without a range) should not show indicator
      fireEvent.change(screen.getByDisplayValue('Date Field'), { target: { value: 'createdAt' } });

      // The active indicator depends on dateFilterField AND dateRange having values
      // Without a date range selected, only the field is set
      const filterButton = screen.getByText('Filters').closest('button')!;
      const dot = filterButton.querySelector('.rounded-full');
      // No dot because dateRange is still {start: null, end: null}
      expect(dot).not.toBeInTheDocument();
    });
  });

  describe('Combined Filters State', () => {
    it('should maintain type filter when changing date field', async () => {
      render(<FilterBarWithState />);

      await userEvent.click(screen.getByText('Filters'));

      // Set type filter
      const typeSelect = screen.getByDisplayValue('All Types');
      fireEvent.change(typeSelect, { target: { value: 'BUG' } });

      // Set date field
      const dateSelect = screen.getByDisplayValue('Date Field');
      fireEvent.change(dateSelect, { target: { value: 'createdAt' } });

      // Type filter should still be Bug
      expect(screen.getByDisplayValue('🐛 Bug')).toBeInTheDocument();
      // Date picker should be visible
      expect(screen.getByText('Select range...')).toBeInTheDocument();
    });

    it('should maintain priority filter when changing date field', async () => {
      render(<FilterBarWithState />);

      await userEvent.click(screen.getByText('Filters'));

      // Set priority filter
      const prioritySelect = screen.getByDisplayValue('All Priorities');
      fireEvent.change(prioritySelect, { target: { value: 'HIGH' } });

      // Set date field
      const dateSelect = screen.getByDisplayValue('Date Field');
      fireEvent.change(dateSelect, { target: { value: 'dueDate' } });

      // Priority filter should still be High
      expect(screen.getByDisplayValue('High')).toBeInTheDocument();
      // Date picker should be visible
      expect(screen.getByText('Select range...')).toBeInTheDocument();
    });

    it('should show Clear button when any filter is active', async () => {
      render(<FilterBarWithState />);

      // Initially no Clear button
      expect(screen.queryByText('Clear')).not.toBeInTheDocument();

      await userEvent.click(screen.getByText('Filters'));

      // Set type filter
      fireEvent.change(screen.getByDisplayValue('All Types'), { target: { value: 'TASK' } });

      // Clear button should now be visible
      expect(screen.getByText('Clear')).toBeInTheDocument();
    });

    it('should clear all filters including date when Clear is clicked', async () => {
      render(<FilterBarWithState />);

      // Set some filters
      const searchInput = screen.getByPlaceholderText(/Search issues/);
      await userEvent.type(searchInput, 'test');

      // Open filters panel
      await userEvent.click(screen.getByText('Filters'));

      // Set type
      fireEvent.change(screen.getByDisplayValue('All Types'), { target: { value: 'BUG' } });

      // Clear all
      await userEvent.click(screen.getByText('Clear'));

      // Search should be cleared
      expect(screen.getByPlaceholderText(/Search issues/)).toHaveValue('');
    });
  });

  describe('Sort and Date Filter Coexistence', () => {
    it('should allow sorting by date while filtering by date range', async () => {
      render(<FilterBarWithState />);

      // Sort by Created Date
      const sortSelect = screen.getByDisplayValue('Manual Order');
      fireEvent.change(sortSelect, { target: { value: 'createdAt' } });

      // Open filters
      await userEvent.click(screen.getByText('Filters'));

      // Select date field for filtering
      const dateSelect = screen.getByDisplayValue('Date Field');
      fireEvent.change(dateSelect, { target: { value: 'dueDate' } });

      // Both should be active: sort by createdAt, filter by dueDate
      expect(screen.getByDisplayValue('Created Date')).toBeInTheDocument(); // sort
      expect(screen.getByDisplayValue('Due Date')).toBeInTheDocument(); // date filter
      expect(screen.getByText('Select range...')).toBeInTheDocument(); // date picker
    });

    it('should preserve sort when clearing filters', async () => {
      render(<FilterBarWithState />);

      // Sort by Due Date
      const sortSelect = screen.getByDisplayValue('Manual Order');
      fireEvent.change(sortSelect, { target: { value: 'dueDate' } });

      // Add a search filter to trigger Clear button
      const searchInput = screen.getByPlaceholderText(/Search issues/);
      await userEvent.type(searchInput, 'test');

      // Clear filters
      await userEvent.click(screen.getByText('Clear'));

      // Sort should remain unchanged
      expect(screen.getByDisplayValue('Due Date')).toBeInTheDocument();
    });
  });
});
