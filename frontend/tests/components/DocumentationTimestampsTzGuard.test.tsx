/**
 * CB-2730 — TZ-guard regression for documentation-pipeline timestamp formatters.
 *
 * Both surfaces below render `executedAt` / `createdAt` ISO strings via
 * `new Date(iso).toLocaleString(...)`. Without the `_toUtcIso` guard, a naive
 * ISO (no `Z`/offset) is parsed as *local* time per ECMA-262 §21.4.3.2 and the
 * displayed wall-clock drifts by the browser's UTC offset.
 *
 * These tests are TZ-independent: they assert that a naive ISO and the
 * equivalent `Z`-suffixed ISO produce **identical** output. Without the guard,
 * any non-UTC test runner would surface a mismatch (and so would a
 * future-Asia/Jerusalem regression).
 *
 * Mirrors the CB-2377 pattern (`FeatureDocumentationView.test.tsx`):
 *   - direct helper assertions in `tests/lib/utils.test.ts` (`_toUtcIso`)
 *   - per-component formatter assertions here.
 */

import { describe, it, expect } from 'vitest';
import { formatTimestamp } from '@/components/codeboard/ImplementationTab';
import { formatDate } from '@/app/settings/documentation/page';

describe('ImplementationTab.formatTimestamp — naive ISO is treated as UTC (CB-2730)', () => {
  it('renders the same output for naive and Z-suffixed ISO', () => {
    const naive = '2026-05-08T10:00:00';
    const utc = '2026-05-08T10:00:00Z';
    expect(formatTimestamp(naive)).toBe(formatTimestamp(utc));
  });

  it('renders the same output for subsecond-precision naive and Z-suffixed ISO', () => {
    const naive = '2026-05-08T10:00:00.123456';
    const utc = '2026-05-08T10:00:00.123456Z';
    expect(formatTimestamp(naive)).toBe(formatTimestamp(utc));
  });

  it('still respects an explicit ±HH:MM offset', () => {
    // 11:55:30 UTC == 14:55:30 +03:00 — both must format to the same instant.
    expect(formatTimestamp('2026-05-07T14:55:30+03:00')).toBe(
      formatTimestamp('2026-05-07T11:55:30Z'),
    );
  });

  it('returns dash for invalid ISO', () => {
    expect(formatTimestamp('not-an-iso')).toBe('—');
  });
});

describe('settings/documentation.formatDate — naive ISO is treated as UTC (CB-2730)', () => {
  it('renders the same output for naive and Z-suffixed ISO', () => {
    const naive = '2026-05-08T22:29:01.008925';
    const utc = '2026-05-08T22:29:01.008925Z';
    expect(formatDate(naive)).toBe(formatDate(utc));
  });

  it('still respects an explicit ±HH:MM offset', () => {
    expect(formatDate('2026-05-07T14:55:30+03:00')).toBe(
      formatDate('2026-05-07T11:55:30Z'),
    );
  });
});
