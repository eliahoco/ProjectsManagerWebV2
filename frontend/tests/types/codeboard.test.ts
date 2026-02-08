/**
 * Tests for CodeBoard Types and Constants
 * Task: CB-1116 - Testing framework for frontend UI
 * Part of STORY CB-1112: User can Filter Results by Date Range
 *
 * Validates that type constants and configuration arrays
 * are correctly defined and consistent.
 */

import { describe, it, expect } from 'vitest';
import {
  STATUS_COLUMNS,
  ISSUE_TYPES,
  ISSUE_TYPE_HIERARCHY,
  PRIORITIES,
  SORT_OPTIONS,
  DATE_FILTER_OPTIONS,
  DEFAULT_AUTO_PILOT_CONFIG,
  AUTO_PILOT_FAIL_OPTIONS,
  AUTO_PILOT_SUCCESS_OPTIONS,
} from '@/types/codeboard';

describe('CodeBoard Constants', () => {
  describe('STATUS_COLUMNS', () => {
    it('should have 6 status columns', () => {
      expect(STATUS_COLUMNS).toHaveLength(6);
    });

    it('should include all expected statuses', () => {
      const statuses = STATUS_COLUMNS.map(c => c.status);
      expect(statuses).toContain('BACKLOG');
      expect(statuses).toContain('TODO');
      expect(statuses).toContain('IN_PROGRESS');
      expect(statuses).toContain('IN_REVIEW');
      expect(statuses).toContain('COMPLETED_WAITING_QA');
      expect(statuses).toContain('DONE');
    });

    it('each column should have label and color', () => {
      STATUS_COLUMNS.forEach(column => {
        expect(column.label).toBeTruthy();
        expect(column.color).toBeTruthy();
        expect(column.color).toMatch(/^bg-/);
      });
    });
  });

  describe('ISSUE_TYPES', () => {
    it('should have 6 issue types', () => {
      expect(ISSUE_TYPES).toHaveLength(6);
    });

    it('should include all expected types', () => {
      const types = ISSUE_TYPES.map(t => t.type);
      expect(types).toContain('FEATURE');
      expect(types).toContain('EPIC');
      expect(types).toContain('STORY');
      expect(types).toContain('TASK');
      expect(types).toContain('SUBTASK');
      expect(types).toContain('BUG');
    });

    it('each type should have label, color, and icon', () => {
      ISSUE_TYPES.forEach(type => {
        expect(type.label).toBeTruthy();
        expect(type.color).toBeTruthy();
        expect(type.icon).toBeTruthy();
      });
    });
  });

  describe('ISSUE_TYPE_HIERARCHY', () => {
    it('should define hierarchy for all 6 issue types', () => {
      expect(Object.keys(ISSUE_TYPE_HIERARCHY)).toHaveLength(6);
    });

    it('FEATURE can have EPIC children', () => {
      expect(ISSUE_TYPE_HIERARCHY.FEATURE).toEqual(['EPIC']);
    });

    it('EPIC can have STORY children', () => {
      expect(ISSUE_TYPE_HIERARCHY.EPIC).toEqual(['STORY']);
    });

    it('STORY can have TASK children', () => {
      expect(ISSUE_TYPE_HIERARCHY.STORY).toEqual(['TASK']);
    });

    it('TASK can have SUBTASK children', () => {
      expect(ISSUE_TYPE_HIERARCHY.TASK).toEqual(['SUBTASK']);
    });

    it('SUBTASK has no children', () => {
      expect(ISSUE_TYPE_HIERARCHY.SUBTASK).toEqual([]);
    });

    it('BUG can have SUBTASK children', () => {
      expect(ISSUE_TYPE_HIERARCHY.BUG).toEqual(['SUBTASK']);
    });
  });

  describe('PRIORITIES', () => {
    it('should have 4 priority levels', () => {
      expect(PRIORITIES).toHaveLength(4);
    });

    it('should be ordered from LOW to CRITICAL', () => {
      const levels = PRIORITIES.map(p => p.priority);
      expect(levels).toEqual(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']);
    });

    it('each priority should have label and color', () => {
      PRIORITIES.forEach(p => {
        expect(p.label).toBeTruthy();
        expect(p.color).toBeTruthy();
      });
    });
  });

  describe('SORT_OPTIONS', () => {
    it('should have 8 sort options', () => {
      expect(SORT_OPTIONS).toHaveLength(8);
    });

    it('should include date-related sort fields', () => {
      const fields = SORT_OPTIONS.map(o => o.field);
      expect(fields).toContain('createdAt');
      expect(fields).toContain('updatedAt');
      expect(fields).toContain('dueDate');
    });

    it('should include non-date sort fields', () => {
      const fields = SORT_OPTIONS.map(o => o.field);
      expect(fields).toContain('sequence');
      expect(fields).toContain('priority');
      expect(fields).toContain('title');
      expect(fields).toContain('type');
      expect(fields).toContain('status');
    });

    it('each option should have field and label', () => {
      SORT_OPTIONS.forEach(option => {
        expect(option.field).toBeTruthy();
        expect(option.label).toBeTruthy();
      });
    });
  });

  describe('DATE_FILTER_OPTIONS', () => {
    it('should have 5 date filter options', () => {
      expect(DATE_FILTER_OPTIONS).toHaveLength(5);
    });

    it('should include all expected date fields', () => {
      const fields = DATE_FILTER_OPTIONS.map(o => o.field);
      expect(fields).toContain('createdAt');
      expect(fields).toContain('updatedAt');
      expect(fields).toContain('dueDate');
      expect(fields).toContain('startedAt');
      expect(fields).toContain('completedAt');
    });

    it('each option should have field and label', () => {
      DATE_FILTER_OPTIONS.forEach(option => {
        expect(option.field).toBeTruthy();
        expect(option.label).toBeTruthy();
      });
    });

    it('labels should be human-readable', () => {
      const labels = DATE_FILTER_OPTIONS.map(o => o.label);
      expect(labels).toContain('Created Date');
      expect(labels).toContain('Updated Date');
      expect(labels).toContain('Due Date');
      expect(labels).toContain('Started Date');
      expect(labels).toContain('Completed Date');
    });
  });

  describe('AutoPilot Configuration', () => {
    it('DEFAULT_AUTO_PILOT_CONFIG should be disabled by default', () => {
      expect(DEFAULT_AUTO_PILOT_CONFIG.enabled).toBe(false);
    });

    it('DEFAULT_AUTO_PILOT_CONFIG should have sensible defaults', () => {
      expect(DEFAULT_AUTO_PILOT_CONFIG.onFail).toBe('CONTINUE_MARK_FAILED');
      expect(DEFAULT_AUTO_PILOT_CONFIG.onSuccess).toBe('MARK_WAITING_QA');
      expect(DEFAULT_AUTO_PILOT_CONFIG.maxRetries).toBe(3);
    });

    it('AUTO_PILOT_FAIL_OPTIONS should have 4 options', () => {
      expect(AUTO_PILOT_FAIL_OPTIONS).toHaveLength(4);
    });

    it('AUTO_PILOT_FAIL_OPTIONS should include TERMINATE', () => {
      const values = AUTO_PILOT_FAIL_OPTIONS.map(o => o.value);
      expect(values).toContain('TERMINATE');
    });

    it('AUTO_PILOT_SUCCESS_OPTIONS should have 4 options', () => {
      expect(AUTO_PILOT_SUCCESS_OPTIONS).toHaveLength(4);
    });

    it('each option should have value, label, and description', () => {
      [...AUTO_PILOT_FAIL_OPTIONS, ...AUTO_PILOT_SUCCESS_OPTIONS].forEach(option => {
        expect(option.value).toBeTruthy();
        expect(option.label).toBeTruthy();
        expect(option.description).toBeTruthy();
      });
    });
  });
});
