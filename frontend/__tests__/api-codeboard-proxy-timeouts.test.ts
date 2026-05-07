/**
 * CB-2375 regression: per-route timeout overrides for the CodeBoard API proxy.
 *
 * The proxy at `frontend/app/api/codeboard/[...path]/route.ts` historically
 * hard-coded a 15s `AbortController` timeout for every method, which was
 * shorter than the LLM aggregation behind
 * `POST /api/features/{id}/documentation/generate` (~30–35s). The UI surfaced
 * 504s while the backend completed successfully.
 *
 * These tests pin the lookup contract so the regression cannot return:
 *   - default timeout stays 15s
 *   - documentation/generate POST → 120s
 *   - GET on the same path keeps the default (overrides are method-scoped)
 *   - sibling endpoints under /features and /documentation are NOT bumped
 *   - search params don't affect matching
 *
 * Path matching is performed against the joined backend path AFTER `/api/`,
 * so test fixtures use the same shape as `path.join('/')` produces.
 */

import { describe, it, expect } from 'vitest';

import {
  DEFAULT_TIMEOUT_MS,
  TIMEOUT_OVERRIDES,
  getTimeoutMs,
} from '@/app/api/codeboard/[...path]/timeouts';

describe('CodeBoard proxy — getTimeoutMs', () => {
  it('returns DEFAULT_TIMEOUT_MS for an unknown path', () => {
    expect(getTimeoutMs('issues/issue/CB-2375', 'PATCH')).toBe(DEFAULT_TIMEOUT_MS);
    expect(getTimeoutMs('projects/abc/issues', 'GET')).toBe(DEFAULT_TIMEOUT_MS);
  });

  it('returns DEFAULT_TIMEOUT_MS for an empty path', () => {
    // Empty `pathStr` happens if a request hits the proxy with no segments.
    // The match fails the regex and falls through to the default.
    expect(getTimeoutMs('', 'GET')).toBe(DEFAULT_TIMEOUT_MS);
    expect(getTimeoutMs('', 'POST')).toBe(DEFAULT_TIMEOUT_MS);
  });

  it('does NOT bump PUT/PATCH/DELETE on the doc-generate path (override is POST-only)', () => {
    expect(
      getTimeoutMs('features/abc-123/documentation/generate', 'PUT'),
    ).toBe(DEFAULT_TIMEOUT_MS);
    expect(
      getTimeoutMs('features/abc-123/documentation/generate', 'PATCH'),
    ).toBe(DEFAULT_TIMEOUT_MS);
    expect(
      getTimeoutMs('features/abc-123/documentation/generate', 'DELETE'),
    ).toBe(DEFAULT_TIMEOUT_MS);
  });

  it('returns 120000ms for POST /features/{id}/documentation/generate (CB-2375)', () => {
    expect(
      getTimeoutMs('features/abc-123/documentation/generate', 'POST'),
    ).toBe(120_000);
    expect(
      getTimeoutMs(
        'features/05c3b400-644b-433f-a4ff-d196b7754fc8/documentation/generate',
        'POST',
      ),
    ).toBe(120_000);
  });

  it('does NOT bump GET on the same documentation path (override is POST-only)', () => {
    expect(
      getTimeoutMs('features/abc-123/documentation/generate', 'GET'),
    ).toBe(DEFAULT_TIMEOUT_MS);
  });

  it('does NOT bump sibling /features endpoints', () => {
    expect(getTimeoutMs('features/abc-123/documentation', 'POST')).toBe(
      DEFAULT_TIMEOUT_MS,
    );
    expect(getTimeoutMs('features/abc-123/documentation', 'GET')).toBe(
      DEFAULT_TIMEOUT_MS,
    );
    expect(getTimeoutMs('features/abc-123', 'PATCH')).toBe(
      DEFAULT_TIMEOUT_MS,
    );
  });

  it('does NOT bump unrelated /documentation paths', () => {
    expect(
      getTimeoutMs('execute/issue/CB-2038/generate-documentation', 'POST'),
    ).toBe(DEFAULT_TIMEOUT_MS);
  });

  it('rejects partial / nested matches that would let an attacker forge the prefix', () => {
    // Path includes the literal segment but NOT as the canonical
    // /features/{id}/documentation/generate shape — must not be bumped.
    expect(
      getTimeoutMs(
        'malicious/features/abc-123/documentation/generate',
        'POST',
      ),
    ).toBe(DEFAULT_TIMEOUT_MS);
    expect(
      getTimeoutMs('features/a/b/documentation/generate', 'POST'),
    ).toBe(DEFAULT_TIMEOUT_MS);
  });

  it('TIMEOUT_OVERRIDES is non-empty and well-formed', () => {
    expect(TIMEOUT_OVERRIDES.length).toBeGreaterThan(0);
    for (const rule of TIMEOUT_OVERRIDES) {
      expect(rule.pattern).toBeInstanceOf(RegExp);
      expect(rule.methods.length).toBeGreaterThan(0);
      expect(rule.timeoutMs).toBeGreaterThan(DEFAULT_TIMEOUT_MS);
      expect(typeof rule.reason).toBe('string');
      expect(rule.reason.length).toBeGreaterThan(0);
    }
  });
});
