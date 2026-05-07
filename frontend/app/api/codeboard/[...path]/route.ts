/**
 * CodeBoard API Proxy
 * Proxies requests to the FastAPI backend at localhost:8401
 *
 * Supports GET, POST, PUT, PATCH, DELETE — plus transparent passthrough of
 * Server-Sent Events (text/event-stream) responses so streaming endpoints
 * such as /qa/generate/stream and /qa/execute/stream keep working end-to-end.
 */

import { NextRequest, NextResponse } from 'next/server';
import { getTimeoutMs } from './timeouts';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8401';

function isEventStream(response: Response): boolean {
  const ct = response.headers.get('content-type') || '';
  return ct.toLowerCase().includes('text/event-stream');
}

function streamResponse(response: Response): Response {
  return new Response(response.body, {
    status: response.status,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

async function buildUrl(
  request: NextRequest,
  params: Promise<{ path: string[] }>,
): Promise<{ url: string; pathStr: string }> {
  const { path } = await params;
  const pathStr = path.join('/');
  const searchParams = request.nextUrl.searchParams.toString();
  const url = `${BACKEND_URL}/api/${pathStr}${searchParams ? `?${searchParams}` : ''}`;
  return { url, pathStr };
}

async function forwardWithBody(
  request: NextRequest,
  params: Promise<{ path: string[] }>,
  method: 'POST' | 'PUT' | 'PATCH',
): Promise<Response> {
  const { url, pathStr } = await buildUrl(request, params);
  const timeoutMs = getTimeoutMs(pathStr, method);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let body: string | undefined;
    try {
      const text = await request.text();
      if (text) body = text;
    } catch {
      // Empty body is OK for some endpoints (e.g. /complete)
    }

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      ...(body !== undefined && { body }),
      signal: controller.signal,
    });

    if (isEventStream(response)) return streamResponse(response);

    // 204 No Content
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const text = await response.text();
    if (!text) {
      return new NextResponse(null, { status: response.status });
    }
    try {
      return NextResponse.json(JSON.parse(text), { status: response.status });
    } catch {
      return new NextResponse(text, {
        status: response.status,
        headers: { 'Content-Type': response.headers.get('content-type') || 'text/plain' },
      });
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Gateway timeout', timeoutMs },
        { status: 504 },
      );
    }
    console.error('CodeBoard API proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to connect to backend' },
      { status: 502 },
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { url, pathStr } = await buildUrl(request, params);
  const timeoutMs = getTimeoutMs(pathStr, 'GET');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    });

    if (isEventStream(response)) return streamResponse(response);

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Gateway timeout', timeoutMs },
        { status: 504 },
      );
    }
    console.error('CodeBoard API proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to connect to backend' },
      { status: 502 },
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return forwardWithBody(request, params, 'POST');
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return forwardWithBody(request, params, 'PUT');
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return forwardWithBody(request, params, 'PATCH');
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { url, pathStr } = await buildUrl(request, params);
  const timeoutMs = getTimeoutMs(pathStr, 'DELETE');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    });

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Gateway timeout', timeoutMs },
        { status: 504 },
      );
    }
    console.error('CodeBoard API proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to connect to backend' },
      { status: 502 },
    );
  } finally {
    clearTimeout(timer);
  }
}

