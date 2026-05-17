/**
 * FeatureDocumentationView — techStack badge regression
 * CB-2076 (E2-5): JSON `["FastAPI", "Next.js"]` → 2 badges visible.
 *
 * Locks the `techStack` JSON-string contract:
 *   - well-formed array → one Badge per unique entry
 *   - non-array / invalid JSON / null / empty → no Tech Stack section
 *   - duplicates → deduplicated
 */

import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  FeatureDocumentationView,
  _toUtcIso,
  formatIndexedAt,
} from '@/components/codeboard/FeatureDocumentationView';
import type { FeatureDocumentationData } from '@/hooks/useCodeBoard';

function makeDoc(
  overrides: Partial<FeatureDocumentationData> = {},
): FeatureDocumentationData {
  return {
    id: 'doc-1',
    projectId: 'proj-1',
    featureIssueId: 'issue-1',
    featureKey: 'CB-9999',
    title: 'Test Feature',
    overview: '',
    requirements: '',
    implementation: '',
    architecture: '',
    techStack: '[]',
    testingStrategy: '',
    totalTasks: 0,
    completedTasks: 0,
    totalQATasks: 0,
    passedQATasks: 0,
    failedQATasks: 0,
    mdFilePath: '',
    embeddingId: null,
    lastIndexedAt: null,
    createdAt: '2026-05-07T00:00:00Z',
    updatedAt: '2026-05-07T00:00:00Z',
    ...overrides,
  };
}

function getTechSection(): HTMLElement | null {
  const heading = screen.queryByRole('heading', { name: /tech stack/i });
  return heading ? (heading.closest('section') as HTMLElement | null) : null;
}

function getBadgeTexts(section: HTMLElement): string[] {
  // Badge container is the only flex-wrap child of the section's body div.
  const container = section.querySelector('.flex.flex-wrap');
  if (!container) return [];
  return Array.from(container.children).map(
    (el) => el.textContent?.trim() ?? '',
  );
}

describe('FeatureDocumentationView — techStack rendering (CB-2076)', () => {
  it('renders one badge per entry for `["FastAPI", "Next.js"]`', () => {
    const doc = makeDoc({ techStack: '["FastAPI", "Next.js"]' });
    render(<FeatureDocumentationView doc={doc} />);

    const section = getTechSection();
    expect(section).not.toBeNull();
    expect(getBadgeTexts(section!)).toEqual(['FastAPI', 'Next.js']);
  });

  it('deduplicates repeated entries', () => {
    const doc = makeDoc({
      techStack: '["FastAPI", "FastAPI", "Next.js", "Next.js", "FastAPI"]',
    });
    render(<FeatureDocumentationView doc={doc} />);

    const section = getTechSection();
    expect(section).not.toBeNull();
    expect(getBadgeTexts(section!)).toEqual(['FastAPI', 'Next.js']);
  });

  it('hides the Tech Stack section when techStack is an empty array', () => {
    render(<FeatureDocumentationView doc={makeDoc({ techStack: '[]' })} />);
    expect(getTechSection()).toBeNull();
  });

  it('hides the Tech Stack section when techStack is invalid JSON', () => {
    render(
      <FeatureDocumentationView doc={makeDoc({ techStack: 'not-json' })} />,
    );
    expect(getTechSection()).toBeNull();
  });

  it('hides the Tech Stack section when techStack is a non-array JSON value', () => {
    render(
      <FeatureDocumentationView
        doc={makeDoc({ techStack: '{"foo": "bar"}' })}
      />,
    );
    expect(getTechSection()).toBeNull();
  });

  it('filters non-string array entries', () => {
    const doc = makeDoc({
      techStack: '["FastAPI", 42, null, true, "Next.js", {"x": 1}]',
    });
    render(<FeatureDocumentationView doc={doc} />);

    const section = getTechSection();
    expect(section).not.toBeNull();
    expect(getBadgeTexts(section!)).toEqual(['FastAPI', 'Next.js']);
  });

  it('hides the Tech Stack section when techStack is undefined', () => {
    render(
      <FeatureDocumentationView
        doc={makeDoc({ techStack: undefined as unknown as string })}
      />,
    );
    expect(getTechSection()).toBeNull();
  });

  it('hides the Tech Stack section when techStack is null', () => {
    render(
      <FeatureDocumentationView
        doc={makeDoc({ techStack: null as unknown as string })}
      />,
    );
    expect(getTechSection()).toBeNull();
  });
});

/**
 * CB-2377 — formatIndexedAt must treat a naive ISO (no Z, no offset) as UTC.
 *
 * Before the fix the browser parsed naive ISO strings as *local* time, so a
 * regenerate that just finished rendered as `Xh ago` where X = the user's UTC
 * offset (3 in IDT). These cases would have caught that bug.
 */
describe('formatIndexedAt — naive UTC ISO handling (CB-2377)', () => {
  const FIXED_NOW = new Date('2026-05-07T12:00:30Z').getTime();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders "just now" for a naive ISO 5 seconds in the past', () => {
    // Naive ISO == 5s before FIXED_NOW *if interpreted as UTC*.
    expect(formatIndexedAt('2026-05-07T12:00:25')).toBe('just now');
  });

  it('renders "5m ago" for a naive ISO 5 minutes in the past', () => {
    expect(formatIndexedAt('2026-05-07T11:55:30')).toBe('5m ago');
  });

  it('still respects an explicit Z suffix', () => {
    expect(formatIndexedAt('2026-05-07T11:55:30Z')).toBe('5m ago');
  });

  it('still respects an explicit +HH:MM offset', () => {
    // 11:55:30 UTC == 14:55:30 +03:00. Both must read 5m ago.
    expect(formatIndexedAt('2026-05-07T14:55:30+03:00')).toBe('5m ago');
  });
});

/**
 * CB-2377 — direct _toUtcIso assertions. These are the tests that must fail
 * even when CI runs in UTC (security-auditor L1) — they pin the helper's
 * contract independently of `new Date()`'s ambient-TZ behavior.
 */
describe('_toUtcIso — append Z only when missing (CB-2377)', () => {
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
