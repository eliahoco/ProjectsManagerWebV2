/**
 * apiFetch — wrapper around fetch() with automatic timeout via AbortController.
 *
 * All frontend → backend requests should use this instead of raw fetch().
 * Default timeout: 30 seconds.
 *
 * Usage:
 *   const res = await apiFetch('/api/projects');
 *   const res = await apiFetch('/api/slow', { timeout: 60_000 });
 */

export interface ApiFetchInit extends RequestInit {
  /** Request timeout in ms. Default: 30000 */
  timeout?: number;
}

export class ApiFetchTimeoutError extends Error {
  constructor(url: string, timeout: number) {
    super(`Request to ${url} timed out after ${timeout}ms`);
    this.name = 'ApiFetchTimeoutError';
  }
}

export async function apiFetch(
  input: RequestInfo | URL,
  init: ApiFetchInit = {}
): Promise<Response> {
  const { timeout = 30_000, signal: externalSignal, ...rest } = init;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  // Link external signal if provided
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutId);
      throw new DOMException('Aborted', 'AbortError');
    }
    externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  try {
    return await fetch(input, { ...rest, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError' && !externalSignal?.aborted) {
      throw new ApiFetchTimeoutError(String(input), timeout);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}
