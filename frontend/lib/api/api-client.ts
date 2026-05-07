/**
 * Shared frontend API client — `APIError` + JSON-typed `apiFetch` wrapper.
 *
 * Lives at `lib/api/api-client.ts` so the hook layer (`hooks/useCodeBoard.ts`,
 * `hooks/useIssueRelations.ts`, etc.) can share one error/decoding contract
 * without re-importing through each other. Previously `APIError` lived in
 * `useCodeBoard.ts` and `useIssueRelations.ts` re-imported it from there
 * while `useCodeBoard.ts` simultaneously re-exported hooks from
 * `useIssueRelations.ts` — a fragile ESM cycle that compiled today only
 * because `APIError` is a value the bundler can hoist. Centralizing here
 * removes the cycle and the byte-equivalent duplication of `apiFetch`.
 *
 * Contract:
 *   * Non-2xx responses throw `APIError` with the parsed `code` / `details`
 *     from the JSON body when present (per the backend `app/errors.py`
 *     contract). Consumers in `AddRelationModal.mapRelationError` and
 *     elsewhere switch on `err.code` — diverging the error parsing
 *     elsewhere would silently break those switches.
 *   * 204 No Content returns `undefined as T`. Forward-compat for endpoints
 *     that move from 200+body to 204 (e.g. delete-style).
 *   * Body parse errors fall through to a generic message keyed on the
 *     status code; we never leak the raw `response` to the caller.
 */

import {
  apiFetch as apiFetchHttp,
  type ApiFetchInit,
} from '@/lib/api/api-fetch';

/**
 * Standardized error thrown by `apiFetch`. Mirrors the backend error
 * envelope from `backend/app/errors.py` (`{message, code, details}`).
 *
 * `code` is the machine-readable enum (`ALREADY_EXISTS`, `CYCLE_DETECTED`,
 * `VALIDATION_ERROR`, `NOT_FOUND`, …). `details` is open-shape JSON the
 * backend uses to ferry contextual data (e.g. cycle path, conflicting
 * field name). Consumers MUST treat both fields as untrusted text — the
 * backend is trusted, but a future MITM or proxy could swap values, and
 * any rendering must use React text escaping (never `dangerouslySetInnerHTML`).
 */
export class APIError extends Error {
  statusCode: number;
  code?: string;
  details?: Record<string, unknown>;

  constructor(
    message: string,
    statusCode: number,
    code?: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'APIError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

/** Status-code → friendly fallback when the body has no `message`. */
export function getDefaultErrorMessage(status: number): string {
  switch (status) {
    case 400:
      return 'Invalid request. Please check your input.';
    case 401:
      return 'Please log in to continue.';
    case 403:
      return 'You do not have permission to perform this action.';
    case 404:
      return 'The requested resource was not found.';
    case 409:
      return 'A conflict occurred. Please refresh and try again.';
    case 429:
      return 'Too many requests. Please wait a moment.';
    case 500:
      return 'A server error occurred. Please try again.';
    case 502:
    case 503:
      return 'The server is temporarily unavailable. Please try again.';
    default:
      return 'An unexpected error occurred.';
  }
}

/**
 * JSON fetch wrapper. Adds `Content-Type: application/json` (consumers
 * can override via `options.headers`), throws `APIError` on non-2xx, and
 * returns `undefined as T` on 204 No Content.
 *
 * Accepts the wider `ApiFetchInit` so callers can pass a per-request
 * `timeout` (default 30s) for slow endpoints like LLM aggregation —
 * see CB-2375 (`POST /features/{id}/documentation/generate`).
 */
export async function apiFetch<T>(
  url: string,
  options?: ApiFetchInit,
): Promise<T> {
  const response = await apiFetchHttp(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorData: {
      message?: string;
      error?: string;
      code?: string;
      details?: Record<string, unknown>;
    } = {};
    try {
      errorData = await response.json();
    } catch {
      // Body wasn't JSON — fall through to a generic message keyed on status.
    }

    const message =
      errorData.message ||
      errorData.error ||
      getDefaultErrorMessage(response.status);
    throw new APIError(
      message,
      response.status,
      errorData.code,
      errorData.details,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}
