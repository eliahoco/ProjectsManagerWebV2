/**
 * FeatureDocumentationView — techStack badge regression
 * CB-2076 (E2-5): JSON `["FastAPI", "Next.js"]` → 2 badges visible.
 *
 * Locks the `techStack` JSON-string contract:
 *   - well-formed array → one Badge per unique entry
 *   - non-array / invalid JSON / null / empty → no Tech Stack section
 *   - duplicates → deduplicated
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FeatureDocumentationView } from '@/components/codeboard/FeatureDocumentationView';
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
