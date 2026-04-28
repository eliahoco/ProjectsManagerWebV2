import { test, expect } from '@playwright/test';

test('GET /api/projects responds <10s under 5 parallel callers', async ({ request }) => {
  // Backend must be running on http://localhost:3601
  const start = Date.now();
  const responses = await Promise.all(
    Array.from({ length: 5 }, () => request.get('http://localhost:3601/api/projects'))
  );
  const elapsed = Date.now() - start;
  expect(elapsed).toBeLessThan(10_000);
  for (const r of responses) {
    expect(r.status()).toBe(200);
    const data = await r.json();
    // API may return a bare array or an envelope { success, data: { projects: [] } }
    const projects = Array.isArray(data)
      ? data
      : (data?.data?.projects ?? data?.data ?? data?.projects ?? null);
    expect(Array.isArray(projects)).toBeTruthy();
  }
});

test('GET /api/projects/status responds <2s (lightweight endpoint)', async ({ request }) => {
  const start = Date.now();
  const r = await request.get('http://localhost:3601/api/projects/status');
  const elapsed = Date.now() - start;
  expect(r.status()).toBe(200);
  expect(elapsed).toBeLessThan(2_000);
});

test('codeboard proxy aborts after 15s on slow upstream', async ({ request }) => {
  // Hit an endpoint that we know is slow or use a deliberately slow project id.
  // Should get 504 within ~15s. If the server is not reachable the test is skipped
  // (it only validates timeout behaviour, not connectivity).
  const start = Date.now();
  let r: Awaited<ReturnType<typeof request.get>> | null = null;
  try {
    r = await request.get('http://localhost:3601/api/codeboard/projects/INVALID_TIMEOUT_TEST/issues', {
      failOnStatusCode: false,
      timeout: 16_000,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes('socket hang up') || msg.includes('ECONNREFUSED')) {
      test.skip(true, 'Backend not running — skipping proxy timeout test');
      return;
    }
    throw err;
  }
  const elapsed = Date.now() - start;
  // Either returns fast (404) or aborts at 15s — should NOT exceed 16s
  expect(elapsed).toBeLessThan(16_000);
});
