/**
 * RAG Status Proxy (CB-2211)
 *
 * GET /api/system/rag/status — proxies to FastAPI at
 * `${BACKEND_URL}/api/system/rag/status`. Mirrors the existing
 * /api/codeboard catch-all proxy shape but as a single dedicated
 * route so the Service Monitor card (CB-2046) can poll it via the
 * relative URL it already uses.
 *
 * Without this route the browser fetch returns 404 every poll and
 * the card flips to "RAG offline" permanently — see CB-2048 F-1.
 *
 * The upstream endpoint is parameterless; query-string forwarding is
 * intentionally omitted. If that ever changes, mirror the pattern in
 * `frontend/app/api/codeboard/[...path]/route.ts`.
 */

import { NextResponse } from 'next/server';

// Force dynamic execution — the response wraps a live infra heartbeat,
// must never be statically optimized or cached at build time.
export const dynamic = 'force-dynamic';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8401';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };

export async function GET() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${BACKEND_URL}/api/system/rag/status`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    const text = await response.text();
    if (!text) {
      return new NextResponse(null, {
        status: response.status,
        headers: NO_STORE_HEADERS,
      });
    }
    try {
      return NextResponse.json(JSON.parse(text), {
        status: response.status,
        headers: NO_STORE_HEADERS,
      });
    } catch {
      return new NextResponse(text, {
        status: response.status,
        headers: {
          ...NO_STORE_HEADERS,
          'Content-Type':
            response.headers.get('content-type') || 'text/plain',
        },
      });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown';
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Gateway timeout' },
        { status: 504, headers: NO_STORE_HEADERS },
      );
    }
    // Log only the message — avoid leaking internal hostname/IP from
    // DNS/TLS error objects that include resolved BACKEND_URL details.
    console.error('[rag-status proxy] upstream error:', message);
    return NextResponse.json(
      { error: 'Failed to connect to backend' },
      { status: 502, headers: NO_STORE_HEADERS },
    );
  } finally {
    clearTimeout(timer);
  }
}
