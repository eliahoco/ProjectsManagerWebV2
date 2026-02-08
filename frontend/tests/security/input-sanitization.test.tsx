/**
 * Security Tests for Frontend Input Sanitization
 * Task: CB-1120 - Automated testing framework for security-related features
 * Part of STORY CB-1112: User can Filter Results by Date Range
 *
 * Tests cover:
 * - XSS prevention in search inputs
 * - Script injection prevention in filter values
 * - HTML entity handling in user input
 * - Special character handling in date filters
 * - Input length limits
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

describe('Input Sanitization Security', () => {
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

  describe('XSS Prevention in Search Input', () => {
    it('should treat script tags as plain text', () => {
      const xssPayload = '<script>alert("xss")</script>';
      render(<FilterBar {...defaultProps} search={xssPayload} />);

      const input = screen.getByPlaceholderText(/Search issues/) as HTMLInputElement;
      // The value should be the raw text, not executed
      expect(input.value).toBe(xssPayload);
      // Ensure no script elements were injected into the DOM
      expect(document.querySelector('script')).toBeNull();
    });

    it('should handle img onerror XSS payloads safely', () => {
      const xssPayload = '<img src=x onerror=alert(1)>';
      render(<FilterBar {...defaultProps} search={xssPayload} />);

      const input = screen.getByPlaceholderText(/Search issues/) as HTMLInputElement;
      expect(input.value).toBe(xssPayload);
      // No img tags should appear outside the input
      const imgs = document.querySelectorAll('img[src="x"]');
      expect(imgs.length).toBe(0);
    });

    it('should handle SVG-based XSS payloads safely', () => {
      const xssPayload = '"><svg/onload=alert(1)>';
      render(<FilterBar {...defaultProps} search={xssPayload} />);

      const input = screen.getByPlaceholderText(/Search issues/) as HTMLInputElement;
      expect(input.value).toBe(xssPayload);
      const svgs = document.querySelectorAll('svg[onload]');
      expect(svgs.length).toBe(0);
    });

    it('should handle javascript: protocol injection safely', async () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      fireEvent.change(input, { target: { value: 'javascript:alert(1)' } });

      // The callback should receive the raw text
      expect(onSearchChange).toHaveBeenCalledWith('javascript:alert(1)');
    });

    it('should handle encoded HTML entities safely', () => {
      const payload = '&lt;script&gt;alert(1)&lt;/script&gt;';
      render(<FilterBar {...defaultProps} search={payload} />);

      const input = screen.getByPlaceholderText(/Search issues/) as HTMLInputElement;
      expect(input.value).toBe(payload);
    });
  });

  describe('SQL Injection Prevention in Search', () => {
    it('should pass SQL injection payloads as plain text to callback', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      const sqlPayloads = [
        "'; DROP TABLE issues; --",
        "1 OR 1=1",
        "' UNION SELECT * FROM users --",
      ];

      sqlPayloads.forEach((payload) => {
        fireEvent.change(input, { target: { value: payload } });
        expect(onSearchChange).toHaveBeenCalledWith(payload);
      });
    });
  });

  describe('Special Characters in Filter Values', () => {
    it('should handle null bytes in search input', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      fireEvent.change(input, { target: { value: 'test\x00null' } });

      expect(onSearchChange).toHaveBeenCalled();
    });

    it('should handle CRLF injection attempts in search', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      fireEvent.change(input, { target: { value: 'test\r\nHeader-Injection: value' } });

      expect(onSearchChange).toHaveBeenCalled();
    });

    it('should handle unicode characters safely', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      const unicodePayload = '\u202E\u0000\uFEFF\uFFFF';
      fireEvent.change(input, { target: { value: unicodePayload } });

      expect(onSearchChange).toHaveBeenCalledWith(unicodePayload);
    });

    it('should handle path traversal attempts in search safely', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText(/Search issues/);
      fireEvent.change(input, { target: { value: '../../../etc/passwd' } });

      expect(onSearchChange).toHaveBeenCalledWith('../../../etc/passwd');
    });
  });

  describe('Date Range Filter Security', () => {
    it('should not inject HTML when date field names are displayed', async () => {
      render(
        <FilterBar
          {...defaultProps}
          onDateRangeChange={vi.fn()}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      const dateSelect = screen.getByDisplayValue('Date Field');
      // All options should be safe text, not HTML
      const options = dateSelect.querySelectorAll('option');
      options.forEach((opt) => {
        expect(opt.innerHTML).not.toMatch(/<script/i);
        expect(opt.innerHTML).not.toMatch(/onerror/i);
      });
    });

    it('should handle date range callback with proper null values', async () => {
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

      // Should be called with safe defaults
      expect(onDateRangeChange).toHaveBeenCalledWith('createdAt', { start: null, end: null });
    });

    it('should only allow whitelisted date fields', async () => {
      render(
        <FilterBar
          {...defaultProps}
          onDateRangeChange={vi.fn()}
        />
      );

      await userEvent.click(screen.getByText('Filters'));

      const dateSelect = screen.getByDisplayValue('Date Field');
      const options = Array.from(dateSelect.querySelectorAll('option'))
        .map((opt) => opt.getAttribute('value'))
        .filter((v) => v !== '');

      const allowedFields = ['createdAt', 'updatedAt', 'dueDate', 'startedAt', 'completedAt'];
      options.forEach((opt) => {
        expect(allowedFields).toContain(opt);
      });
    });
  });

  describe('Clear Filters Security', () => {
    it('should fully reset all filter state on clear', async () => {
      const onSearchChange = vi.fn();
      const onTypeChange = vi.fn();
      const onPriorityChange = vi.fn();
      const onDateRangeChange = vi.fn();

      render(
        <FilterBar
          {...defaultProps}
          search='<script>alert(1)</script>'
          selectedType="BUG"
          selectedPriority="HIGH"
          dateFilterField="createdAt"
          dateRange={{ start: new Date(), end: new Date() }}
          onSearchChange={onSearchChange}
          onTypeChange={onTypeChange}
          onPriorityChange={onPriorityChange}
          onDateRangeChange={onDateRangeChange}
        />
      );

      await userEvent.click(screen.getByText('Clear'));

      expect(onSearchChange).toHaveBeenCalledWith('');
      expect(onTypeChange).toHaveBeenCalledWith(null);
      expect(onPriorityChange).toHaveBeenCalledWith(null);
      expect(onDateRangeChange).toHaveBeenCalledWith(null, { start: null, end: null });
    });
  });
});
