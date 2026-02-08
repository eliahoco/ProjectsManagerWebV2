/**
 * Unit Tests for DateRangePicker Component
 * Task: CB-1116 - Testing framework for frontend UI
 * Part of STORY CB-1112: User can Filter Results by Date Range
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DateRangePicker, type DateRange } from '@/components/ui/date-range-picker';

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  Calendar: ({ className }: { className?: string }) => (
    <span data-testid="calendar-icon" className={className} />
  ),
  ChevronLeft: ({ className }: { className?: string }) => (
    <span data-testid="chevron-left" className={className} />
  ),
  ChevronRight: ({ className }: { className?: string }) => (
    <span data-testid="chevron-right" className={className} />
  ),
  X: ({ className }: { className?: string }) => (
    <span data-testid="x-icon" className={className} />
  ),
}));

describe('DateRangePicker', () => {
  const defaultProps = {
    value: { start: null, end: null } as DateRange,
    onChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render with default placeholder', () => {
      render(<DateRangePicker {...defaultProps} />);
      expect(screen.getByText('Select date range')).toBeInTheDocument();
    });

    it('should render with custom placeholder', () => {
      render(
        <DateRangePicker {...defaultProps} placeholder="Pick dates" />
      );
      expect(screen.getByText('Pick dates')).toBeInTheDocument();
    });

    it('should render the calendar icon', () => {
      render(<DateRangePicker {...defaultProps} />);
      expect(screen.getByTestId('calendar-icon')).toBeInTheDocument();
    });

    it('should display formatted date range when value is set', () => {
      const value: DateRange = {
        start: new Date(2024, 0, 15), // Jan 15, 2024
        end: new Date(2024, 0, 20),   // Jan 20, 2024
      };
      render(<DateRangePicker {...defaultProps} value={value} />);
      expect(screen.getByText('Jan 15, 2024 - Jan 20, 2024')).toBeInTheDocument();
    });

    it('should display single date when only start is set', () => {
      const value: DateRange = {
        start: new Date(2024, 0, 15),
        end: null,
      };
      render(<DateRangePicker {...defaultProps} value={value} />);
      expect(screen.getByText('Jan 15, 2024')).toBeInTheDocument();
    });

    it('should show clear button when value is set', () => {
      const value: DateRange = {
        start: new Date(2024, 0, 15),
        end: new Date(2024, 0, 20),
      };
      render(<DateRangePicker {...defaultProps} value={value} />);
      expect(screen.getByTestId('x-icon')).toBeInTheDocument();
    });

    it('should not show clear button when value is empty', () => {
      render(<DateRangePicker {...defaultProps} />);
      expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument();
    });

    it('should not show clear button when disabled', () => {
      const value: DateRange = {
        start: new Date(2024, 0, 15),
        end: new Date(2024, 0, 20),
      };
      render(<DateRangePicker {...defaultProps} value={value} disabled />);
      expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument();
    });
  });

  describe('Opening and Closing', () => {
    it('should open calendar when trigger is clicked', async () => {
      render(<DateRangePicker {...defaultProps} />);
      const trigger = screen.getByRole('button');
      await userEvent.click(trigger);
      expect(screen.getByText('Quick Select')).toBeInTheDocument();
    });

    it('should show calendar with day headers when open', async () => {
      render(<DateRangePicker {...defaultProps} />);
      const trigger = screen.getByRole('button');
      await userEvent.click(trigger);
      // Two calendar months are shown, so day headers appear twice
      expect(screen.getAllByText('Su').length).toBe(2);
      expect(screen.getAllByText('Mo').length).toBe(2);
      expect(screen.getAllByText('Fr').length).toBe(2);
    });

    it('should not open when disabled', async () => {
      render(<DateRangePicker {...defaultProps} disabled />);
      const trigger = screen.getByRole('button');
      await userEvent.click(trigger);
      expect(screen.queryByText('Quick Select')).not.toBeInTheDocument();
    });

    it('should close on Escape key', async () => {
      render(<DateRangePicker {...defaultProps} />);
      const trigger = screen.getByRole('button');
      await userEvent.click(trigger);
      expect(screen.getByText('Quick Select')).toBeInTheDocument();

      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByText('Quick Select')).not.toBeInTheDocument();
    });

    it('should open when Enter key is pressed', async () => {
      render(<DateRangePicker {...defaultProps} />);
      const trigger = screen.getByRole('button');
      fireEvent.keyDown(trigger, { key: 'Enter' });
      expect(screen.getByText('Quick Select')).toBeInTheDocument();
    });

    it('should open when Space key is pressed', async () => {
      render(<DateRangePicker {...defaultProps} />);
      const trigger = screen.getByRole('button');
      fireEvent.keyDown(trigger, { key: ' ' });
      expect(screen.getByText('Quick Select')).toBeInTheDocument();
    });

    it('should close when clicking outside the picker', async () => {
      render(
        <div>
          <div data-testid="outside">Outside</div>
          <DateRangePicker {...defaultProps} />
        </div>
      );
      const trigger = screen.getByRole('button');
      await userEvent.click(trigger);
      expect(screen.getByText('Quick Select')).toBeInTheDocument();

      fireEvent.mouseDown(screen.getByTestId('outside'));
      expect(screen.queryByText('Quick Select')).not.toBeInTheDocument();
    });
  });

  describe('Preset Ranges', () => {
    it('should display all preset options', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));

      expect(screen.getByText('Today')).toBeInTheDocument();
      expect(screen.getByText('Yesterday')).toBeInTheDocument();
      expect(screen.getByText('Last 7 days')).toBeInTheDocument();
      expect(screen.getByText('Last 30 days')).toBeInTheDocument();
      expect(screen.getByText('This month')).toBeInTheDocument();
      expect(screen.getByText('Last month')).toBeInTheDocument();
    });

    it('should call onChange when a preset is clicked', async () => {
      const onChange = vi.fn();
      render(<DateRangePicker {...defaultProps} onChange={onChange} />);
      await userEvent.click(screen.getByRole('button'));
      await userEvent.click(screen.getByText('Today'));

      expect(onChange).toHaveBeenCalledTimes(1);
      const range = onChange.mock.calls[0][0];
      expect(range.start).toBeInstanceOf(Date);
      expect(range.end).toBeInstanceOf(Date);
    });

    it('should close picker after selecting a preset', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));
      await userEvent.click(screen.getByText('Today'));

      expect(screen.queryByText('Quick Select')).not.toBeInTheDocument();
    });

    it('should not show presets when showPresets is false', async () => {
      render(<DateRangePicker {...defaultProps} showPresets={false} />);
      await userEvent.click(screen.getByRole('button'));

      expect(screen.queryByText('Quick Select')).not.toBeInTheDocument();
      expect(screen.queryByText('Today')).not.toBeInTheDocument();
    });

    it('Today preset should set start and end to today', async () => {
      const onChange = vi.fn();
      render(<DateRangePicker {...defaultProps} onChange={onChange} />);
      await userEvent.click(screen.getByRole('button'));
      await userEvent.click(screen.getByText('Today'));

      const range = onChange.mock.calls[0][0] as DateRange;
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      expect(range.start!.getFullYear()).toBe(today.getFullYear());
      expect(range.start!.getMonth()).toBe(today.getMonth());
      expect(range.start!.getDate()).toBe(today.getDate());
      expect(range.end!.getFullYear()).toBe(today.getFullYear());
      expect(range.end!.getMonth()).toBe(today.getMonth());
      expect(range.end!.getDate()).toBe(today.getDate());
    });
  });

  describe('Clear Functionality', () => {
    it('should call onChange with null dates when clear is clicked', async () => {
      const onChange = vi.fn();
      const value: DateRange = {
        start: new Date(2024, 0, 15),
        end: new Date(2024, 0, 20),
      };
      render(<DateRangePicker {...defaultProps} value={value} onChange={onChange} />);

      const clearButton = screen.getByTestId('x-icon').closest('button')!;
      await userEvent.click(clearButton);

      expect(onChange).toHaveBeenCalledWith({ start: null, end: null });
    });

    it('should not open the picker when clear button is clicked', async () => {
      const value: DateRange = {
        start: new Date(2024, 0, 15),
        end: new Date(2024, 0, 20),
      };
      render(<DateRangePicker {...defaultProps} value={value} />);

      const clearButton = screen.getByTestId('x-icon').closest('button')!;
      await userEvent.click(clearButton);

      // The picker should not open because stopPropagation is called
      expect(screen.queryByText('Quick Select')).not.toBeInTheDocument();
    });
  });

  describe('Calendar Navigation', () => {
    it('should show two months side by side', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));

      // Should show current month and next month names
      const now = new Date();
      const currentMonthName = now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1);
      const nextMonthName = nextMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

      expect(screen.getByText(currentMonthName)).toBeInTheDocument();
      expect(screen.getByText(nextMonthName)).toBeInTheDocument();
    });

    it('should navigate to previous month', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));

      const prevButton = screen.getByTestId('chevron-left').closest('button')!;
      await userEvent.click(prevButton);

      const now = new Date();
      const prevMonth = new Date(now.getFullYear(), now.getMonth() - 1);
      const prevMonthName = prevMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      expect(screen.getByText(prevMonthName)).toBeInTheDocument();
    });

    it('should navigate to next month', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));

      const nextButton = screen.getByTestId('chevron-right').closest('button')!;
      await userEvent.click(nextButton);

      const now = new Date();
      const twoMonthsAhead = new Date(now.getFullYear(), now.getMonth() + 2);
      const twoMonthsAheadName = twoMonthsAhead.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      expect(screen.getByText(twoMonthsAheadName)).toBeInTheDocument();
    });
  });

  describe('Date Selection', () => {
    it('should show selection hint for start date initially', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));
      expect(screen.getByText('Click to select start date')).toBeInTheDocument();
    });

    it('should show selection hint for end date after start is selected', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));

      // Click a day number in the calendar
      const dayButtons = screen.getAllByRole('button').filter(
        btn => btn.textContent?.match(/^\d{1,2}$/) && !btn.hasAttribute('disabled')
      );
      if (dayButtons.length > 0) {
        await userEvent.click(dayButtons[0]);
        expect(screen.getByText('Click to select end date')).toBeInTheDocument();
      }
    });

    it('should call onChange when both start and end are selected', async () => {
      const onChange = vi.fn();
      render(<DateRangePicker {...defaultProps} onChange={onChange} />);
      await userEvent.click(screen.getByRole('button'));

      const dayButtons = screen.getAllByRole('button').filter(
        btn => btn.textContent?.match(/^\d{1,2}$/) && !btn.hasAttribute('disabled')
      );

      if (dayButtons.length >= 2) {
        // Click first day (start)
        await userEvent.click(dayButtons[0]);
        // Click second day (end)
        await userEvent.click(dayButtons[1]);

        expect(onChange).toHaveBeenCalledTimes(1);
        const range = onChange.mock.calls[0][0] as DateRange;
        expect(range.start).toBeInstanceOf(Date);
        expect(range.end).toBeInstanceOf(Date);
      }
    });

    it('should auto-swap dates if end is before start', async () => {
      const onChange = vi.fn();
      render(<DateRangePicker {...defaultProps} onChange={onChange} />);
      await userEvent.click(screen.getByRole('button'));

      const dayButtons = screen.getAllByRole('button').filter(
        btn => btn.textContent?.match(/^\d{1,2}$/) && !btn.hasAttribute('disabled')
      );

      if (dayButtons.length >= 5) {
        // Click a later day first (start)
        await userEvent.click(dayButtons[4]);
        // Click an earlier day (end) - should auto-swap
        await userEvent.click(dayButtons[0]);

        expect(onChange).toHaveBeenCalledTimes(1);
        const range = onChange.mock.calls[0][0] as DateRange;
        expect(range.start!.getTime()).toBeLessThanOrEqual(range.end!.getTime());
      }
    });

    it('should close the picker after full range selection', async () => {
      render(<DateRangePicker {...defaultProps} />);
      await userEvent.click(screen.getByRole('button'));

      const dayButtons = screen.getAllByRole('button').filter(
        btn => btn.textContent?.match(/^\d{1,2}$/) && !btn.hasAttribute('disabled')
      );

      if (dayButtons.length >= 2) {
        await userEvent.click(dayButtons[0]);
        await userEvent.click(dayButtons[1]);
        expect(screen.queryByText('Click to select start date')).not.toBeInTheDocument();
      }
    });
  });

  describe('Min/Max Date Constraints', () => {
    it('should disable dates before minDate', async () => {
      const minDate = new Date(2024, 0, 15); // Jan 15, 2024
      // Set initial month view to January 2024
      const value: DateRange = { start: new Date(2024, 0, 15), end: null };
      render(
        <DateRangePicker
          {...defaultProps}
          value={value}
          minDate={minDate}
        />
      );
      // Click the trigger (div with role="button", not the clear button)
      const triggers = screen.getAllByRole('button');
      const trigger = triggers.find(el => el.getAttribute('tabindex') === '0')!;
      await userEvent.click(trigger);

      // Days before the 15th should be disabled
      const allButtons = screen.getAllByRole('button');
      const dayButtons = allButtons.filter(
        btn => btn.textContent?.match(/^\d{1,2}$/)
      );

      const disabledDays = dayButtons.filter(btn => btn.hasAttribute('disabled'));
      expect(disabledDays.length).toBeGreaterThan(0);
    });

    it('should disable dates after maxDate', async () => {
      const maxDate = new Date(2024, 0, 20); // Jan 20, 2024
      const value: DateRange = { start: new Date(2024, 0, 15), end: null };
      render(
        <DateRangePicker
          {...defaultProps}
          value={value}
          maxDate={maxDate}
        />
      );
      // Click the trigger (div with role="button", not the clear button)
      const triggers = screen.getAllByRole('button');
      const trigger = triggers.find(el => el.getAttribute('tabindex') === '0')!;
      await userEvent.click(trigger);

      const allButtons = screen.getAllByRole('button');
      const dayButtons = allButtons.filter(
        btn => btn.textContent?.match(/^\d{1,2}$/)
      );

      const disabledDays = dayButtons.filter(btn => btn.hasAttribute('disabled'));
      expect(disabledDays.length).toBeGreaterThan(0);
    });
  });

  describe('Accessibility', () => {
    it('should have role="button" on the trigger', () => {
      render(<DateRangePicker {...defaultProps} />);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    it('should be focusable when not disabled', () => {
      render(<DateRangePicker {...defaultProps} />);
      const trigger = screen.getByRole('button');
      expect(trigger).toHaveAttribute('tabindex', '0');
    });

    it('should not be focusable when disabled', () => {
      render(<DateRangePicker {...defaultProps} disabled />);
      const trigger = screen.getByRole('button');
      expect(trigger).toHaveAttribute('tabindex', '-1');
    });

    it('should apply custom className', () => {
      const { container } = render(
        <DateRangePicker {...defaultProps} className="custom-class" />
      );
      expect(container.firstChild).toHaveClass('custom-class');
    });
  });
});
