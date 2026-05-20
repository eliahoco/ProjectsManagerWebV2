/**
 * workspaceFetch — tenant-aware fetch wrapper.
 *
 * Injects X-Tenant-ID and X-Workspace-Id headers on every request to
 * /api/studio/, /api/backlog/, /api/crew-map/ (and any other Studio-layer
 * endpoint). No localhost hardcodes — API base URL comes from
 * NEXT_PUBLIC_API_URL or falls back to an empty string (same origin).
 *
 * Phase 1: single tenant; tenantId defaults to "default".
 * Phase 2: JWT will replace this header; workspaceFetch shape stays the same.
 */

const API_BASE =
  typeof process !== 'undefined'
    ? (process.env.NEXT_PUBLIC_API_URL ?? '')
    : '';

export interface WorkspaceFetchOptions extends Omit<RequestInit, 'headers'> {
  headers?: Record<string, string>;
}

/**
 * Typed fetch wrapper that:
 * 1. Prepends API_BASE to relative paths
 * 2. Injects X-Tenant-ID and X-Workspace-Id headers
 * 3. Parses JSON response as T
 * 4. Throws descriptive errors for non-2xx responses
 * 5. Returns undefined for 204 No Content
 */
export async function workspaceFetch<T>(
  path: string,
  workspaceId: string,
  tenantId: string = 'default',
  options: WorkspaceFetchOptions = {},
): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Tenant-ID': tenantId,
    'X-Workspace-Id': workspaceId,
    ...options.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // 204 No Content — nothing to parse
  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body?.message ?? body?.detail ?? message;
    } catch {
      // swallow parse errors — keep the HTTP status message
    }
    const err = new Error(message);
    (err as Error & { status: number }).status = response.status;
    throw err;
  }

  try {
    return (await response.json()) as T;
  } catch {
    return undefined as T;
  }
}
