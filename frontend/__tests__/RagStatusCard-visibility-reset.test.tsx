/**
 * CB-2664 regression: visibility-return MUST clear and re-arm the
 * setInterval, otherwise a return late in the 30s cycle produces a
 * near-duplicate fetch (visibility-return refresh + scheduled tick
 * fires seconds later).
 *
 * Pins the phase-reset behavior so the bug cannot regress silently.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';

import { ServiceMonitor } from '@/components/service-monitor';

const RAG_STATUS_POLL_MS = 30_000;

const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;

function jsonOk(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function ragStatusPayload() {
  return {
    mode: 'HTTP',
    endpoint: 'chromadb',
    port: 8000,
    fallback_active: false,
    collections: [],
    total_docs: 0,
    healthy: true,
  };
}

function projectsStatusPayload() {
  return { success: true, data: { projects: [] } };
}

function routeFetch(url: string | URL | Request) {
  const u = typeof url === 'string' ? url : url instanceof URL ? url.toString() : url.url;
  if (u.includes('/api/system/rag/status')) return jsonOk(ragStatusPayload());
  if (u.includes('/api/projects/status')) return jsonOk(projectsStatusPayload());
  return jsonOk({});
}

function ragFetchCount(): number {
  return fetchMock.mock.calls.filter(([url]) => {
    const u = typeof url === 'string' ? url : url instanceof URL ? url.toString() : (url as Request).url;
    return u.includes('/api/system/rag/status');
  }).length;
}

function setHidden(value: boolean) {
  Object.defineProperty(document, 'hidden', {
    configurable: true,
    get: () => value,
  });
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => (value ? 'hidden' : 'visible'),
  });
}

describe('RagStatusCard visibility-return phase reset (CB-2664)', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockImplementation((input: string | URL | Request) => Promise.resolve(routeFetch(input)));
    setHidden(false);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    setHidden(false);
  });

  it('does not fire a duplicate /api/system/rag/status fetch right after a visibility-return late in the cycle', async () => {
    render(<ServiceMonitor />);

    // Drain initial 1 s warm-up tick.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    const baseline = ragFetchCount();
    expect(baseline).toBeGreaterThanOrEqual(1);

    // Sit ~29 s into the 30 s interval cycle, then simulate the user
    // hiding then re-showing the tab (visibilitychange → visible).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RAG_STATUS_POLL_MS - 1_000);
    });
    const beforeReturn = ragFetchCount();

    await act(async () => {
      setHidden(true);
      document.dispatchEvent(new Event('visibilitychange'));
      setHidden(false);
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Visibility-return should have fired exactly one extra fetch.
    const afterReturn = ragFetchCount();
    expect(afterReturn - beforeReturn).toBe(1);

    // CB-2664: the next fetch must be a full RAG_STATUS_POLL_MS away,
    // not the residual ~1 s left in the original interval phase.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RAG_STATUS_POLL_MS - 1_000);
    });
    expect(ragFetchCount()).toBe(afterReturn);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(ragFetchCount()).toBe(afterReturn + 1);
  });
});
