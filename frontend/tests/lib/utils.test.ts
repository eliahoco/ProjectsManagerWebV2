/**
 * Unit Tests for Utility Functions
 * Task: CB-1116 - Testing framework for frontend UI
 * Part of STORY CB-1112: User can Filter Results by Date Range
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cn, formatDate, formatRelativeTime, capitalize, getProjectTypeDisplay, getServiceTypeColor, _toUtcIso } from '@/lib/utils';

describe('Utility Functions', () => {
  describe('cn (class name merger)', () => {
    it('should merge class names', () => {
      expect(cn('foo', 'bar')).toBe('foo bar');
    });

    it('should handle conditional classes', () => {
      expect(cn('base', false && 'hidden', true && 'visible')).toBe('base visible');
    });

    it('should merge conflicting Tailwind classes', () => {
      expect(cn('px-2', 'px-4')).toBe('px-4');
    });

    it('should handle undefined and null values', () => {
      expect(cn('base', undefined, null)).toBe('base');
    });

    it('should handle empty input', () => {
      expect(cn()).toBe('');
    });

    it('should merge array of classes', () => {
      expect(cn(['foo', 'bar'])).toBe('foo bar');
    });
  });

  describe('formatDate', () => {
    it('should format a Date object', () => {
      const date = new Date(2024, 0, 15, 14, 30);
      const result = formatDate(date);
      expect(result).toContain('Jan');
      expect(result).toContain('15');
      expect(result).toContain('2024');
    });

    it('should format a date string', () => {
      const result = formatDate('2024-01-15T14:30:00Z');
      expect(result).toContain('Jan');
      expect(result).toContain('15');
      expect(result).toContain('2024');
    });

    it('should include time in the output', () => {
      const date = new Date(2024, 0, 15, 14, 30);
      const result = formatDate(date);
      // Should contain hour and minute
      expect(result).toMatch(/\d{1,2}:\d{2}/);
    });

    it('should handle different months', () => {
      expect(formatDate(new Date(2024, 5, 1))).toContain('Jun');
      expect(formatDate(new Date(2024, 11, 25))).toContain('Dec');
    });
  });

  describe('formatRelativeTime', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date(2024, 0, 15, 12, 0, 0));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return "just now" for recent dates', () => {
      const now = new Date();
      expect(formatRelativeTime(now)).toBe('just now');
    });

    it('should return minutes ago for dates within the hour', () => {
      const fiveMinAgo = new Date(2024, 0, 15, 11, 55, 0);
      expect(formatRelativeTime(fiveMinAgo)).toBe('5m ago');
    });

    it('should return hours ago for dates within the day', () => {
      const threeHoursAgo = new Date(2024, 0, 15, 9, 0, 0);
      expect(formatRelativeTime(threeHoursAgo)).toBe('3h ago');
    });

    it('should return days ago for dates within the week', () => {
      const twoDaysAgo = new Date(2024, 0, 13, 12, 0, 0);
      expect(formatRelativeTime(twoDaysAgo)).toBe('2d ago');
    });

    it('should return formatted date for dates older than a week', () => {
      const oldDate = new Date(2023, 11, 1, 12, 0, 0);
      const result = formatRelativeTime(oldDate);
      expect(result).toContain('Dec');
      expect(result).toContain('2023');
    });

    it('should accept string dates', () => {
      const result = formatRelativeTime('2024-01-15T11:55:00Z');
      expect(result).toBeTruthy();
    });
  });

  describe('capitalize', () => {
    it('should capitalize first letter', () => {
      expect(capitalize('hello')).toBe('Hello');
    });

    it('should lowercase remaining letters', () => {
      expect(capitalize('HELLO')).toBe('Hello');
    });

    it('should handle single character', () => {
      expect(capitalize('a')).toBe('A');
    });

    it('should handle empty string', () => {
      expect(capitalize('')).toBe('');
    });

    it('should handle mixed case', () => {
      expect(capitalize('hELLO wORLD')).toBe('Hello world');
    });
  });

  describe('getProjectTypeDisplay', () => {
    it('should return display name for known types', () => {
      expect(getProjectTypeDisplay('nodejs')).toBe('Node.js');
      expect(getProjectTypeDisplay('nodejs-react')).toBe('React');
      expect(getProjectTypeDisplay('nodejs-next')).toBe('Next.js');
      expect(getProjectTypeDisplay('python')).toBe('Python');
      expect(getProjectTypeDisplay('python-fastapi')).toBe('FastAPI');
      expect(getProjectTypeDisplay('go')).toBe('Go');
      expect(getProjectTypeDisplay('rust')).toBe('Rust');
    });

    it('should be case-insensitive', () => {
      expect(getProjectTypeDisplay('NODEJS')).toBe('Node.js');
      expect(getProjectTypeDisplay('Python')).toBe('Python');
    });

    it('should capitalize unknown types', () => {
      expect(getProjectTypeDisplay('kotlin')).toBe('Kotlin');
      expect(getProjectTypeDisplay('SWIFT')).toBe('Swift');
    });

    it('should return "Unknown" for null', () => {
      expect(getProjectTypeDisplay(null)).toBe('Unknown');
    });
  });

  describe('getServiceTypeColor', () => {
    it('should return correct colors for known service types', () => {
      expect(getServiceTypeColor('FRONTEND')).toBe('bg-blue-500');
      expect(getServiceTypeColor('BACKEND')).toBe('bg-green-500');
      expect(getServiceTypeColor('DATABASE')).toBe('bg-purple-500');
      expect(getServiceTypeColor('CACHE')).toBe('bg-orange-500');
      expect(getServiceTypeColor('QUEUE')).toBe('bg-yellow-500');
      expect(getServiceTypeColor('MONITORING')).toBe('bg-pink-500');
    });

    it('should be case-insensitive', () => {
      expect(getServiceTypeColor('frontend')).toBe('bg-blue-500');
      expect(getServiceTypeColor('Backend')).toBe('bg-green-500');
    });

    it('should return OTHER color for unknown types', () => {
      expect(getServiceTypeColor('UNKNOWN_TYPE')).toBe('bg-gray-500');
      expect(getServiceTypeColor('anything')).toBe('bg-gray-500');
    });
  });

  /**
   * CB-2730 — `_toUtcIso` was promoted to `@/lib/utils` from
   * `FeatureDocumentationView.tsx` (where CB-2377 first introduced it). These
   * direct assertions pin the contract independently of `new Date()`'s
   * ambient-TZ behavior, so they fail even when CI runs in UTC.
   *
   * Mirrors the CB-2377 component-level assertions and remains the canonical
   * source of truth for the helper. The original
   * `FeatureDocumentationView.test.tsx` cases stay green via the named
   * re-export from that module.
   */
  describe('_toUtcIso (CB-2730 — promoted to shared util)', () => {
    it('appends Z to a naive datetime ISO', () => {
      expect(_toUtcIso('2026-05-07T12:00:25')).toBe('2026-05-07T12:00:25Z');
    });

    it('appends Z to a naive datetime ISO with subsecond precision', () => {
      expect(_toUtcIso('2026-05-07T12:00:25.123')).toBe(
        '2026-05-07T12:00:25.123Z',
      );
    });

    it('leaves an explicit Z untouched', () => {
      expect(_toUtcIso('2026-05-07T12:00:25Z')).toBe('2026-05-07T12:00:25Z');
    });

    it('leaves an explicit +HH:MM offset untouched', () => {
      expect(_toUtcIso('2026-05-07T14:55:30+03:00')).toBe(
        '2026-05-07T14:55:30+03:00',
      );
    });

    it('leaves an explicit ±HHMM offset untouched', () => {
      expect(_toUtcIso('2026-05-07T07:55:30-0500')).toBe(
        '2026-05-07T07:55:30-0500',
      );
    });

    it('does not touch a date-only ISO (already UTC midnight per spec)', () => {
      expect(_toUtcIso('2026-05-07')).toBe('2026-05-07');
    });

    it('returns falsy input as-is', () => {
      expect(_toUtcIso('')).toBe('');
    });
  });
});
