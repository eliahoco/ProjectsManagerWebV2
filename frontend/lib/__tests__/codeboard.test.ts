import { describe, it, expect } from 'vitest';
import { isExecutableType, EXECUTABLE_TYPES } from '@/lib/codeboard';

describe('isExecutableType', () => {
  it('returns true for TASK, SUBTASK, BUG', () => {
    expect(isExecutableType('TASK')).toBe(true);
    expect(isExecutableType('SUBTASK')).toBe(true);
    expect(isExecutableType('BUG')).toBe(true);
  });

  it('returns false for FEATURE, EPIC, STORY', () => {
    expect(isExecutableType('FEATURE')).toBe(false);
    expect(isExecutableType('EPIC')).toBe(false);
    expect(isExecutableType('STORY')).toBe(false);
  });
});

describe('EXECUTABLE_TYPES', () => {
  it('contains exactly TASK, SUBTASK, BUG (length 3)', () => {
    expect(EXECUTABLE_TYPES).toHaveLength(3);
    expect(EXECUTABLE_TYPES).toContain('TASK');
    expect(EXECUTABLE_TYPES).toContain('SUBTASK');
    expect(EXECUTABLE_TYPES).toContain('BUG');
  });
});
