/**
 * CB-2211 regression: GET /api/system/rag/status proxies to FastAPI.
 *
 * Without the route handler the relative fetch in service-monitor.tsx
 * returns 404 and the RAG status card flips permanently to "RAG offline".
 * These tests pin the proxy contract so the bug cannot regress silently.
 *
 * Note: BACKEND_URL is captured at module-import time, so env-override
 * cannot be exercised here without `vi.resetModules()` + dynamic import.
 * The integration smoke (curl through :3601) covers the env-injected case.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { GET } from '@/app/api/system/rag/status/route';

const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

describe('GET /api/system/rag/status', () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it('forwards to FastAPI status endpoint and returns the payload', async () => {
    const payload = {
      mode: 'HTTP',
      host: 'chromadb',
      port: 8000,
      collections: [{ name: 'features', count: 42 }],
      total_docs: 42,
      healthy: true,
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(payload));

    const res = await GET();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://localhost:8401/api/system/rag/status');
    expect(init).toMatchObject({ headers: { Accept: 'application/json' } });
    // Timeout signal must be plumbed through, otherwise a wedged backend
    // would hang the route forever and bring the Service Monitor down.
    expect(init.signal).toBeInstanceOf(AbortSignal);

    expect(res.status).toBe(200);
    expect(res.headers.get('Cache-Control')).toBe('no-store');
    expect(await res.json()).toEqual(payload);
  });

  it('returns 502 when the backend connection fails', async () => {
    fetchMock.mockRejectedValueOnce(new Error('ECONNREFUSED'));

    const res = await GET();

    expect(res.status).toBe(502);
    expect(res.headers.get('Cache-Control')).toBe('no-store');
    expect(await res.json()).toEqual({
      error: 'Failed to connect to backend',
    });
  });

  it('returns 504 when the upstream request times out', async () => {
    const abortErr = Object.assign(new Error('aborted'), { name: 'AbortError' });
    fetchMock.mockRejectedValueOnce(abortErr);

    const res = await GET();

    expect(res.status).toBe(504);
    expect(res.headers.get('Cache-Control')).toBe('no-store');
    expect(await res.json()).toEqual({ error: 'Gateway timeout' });
  });

  it('passes through non-2xx status codes from the backend', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('upstream down', {
        status: 503,
        headers: { 'Content-Type': 'text/plain' },
      }),
    );

    const res = await GET();

    expect(res.status).toBe(503);
    expect(res.headers.get('Cache-Control')).toBe('no-store');
    expect(await res.text()).toBe('upstream down');
  });

  it('passes through empty-body responses with the upstream status', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    const res = await GET();

    expect(res.status).toBe(204);
    expect(res.headers.get('Cache-Control')).toBe('no-store');
    expect(await res.text()).toBe('');
  });
});
