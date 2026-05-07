/**
 * Per-route timeout configuration for the CodeBoard API proxy
 * (`frontend/app/api/codeboard/[...path]/route.ts`).
 *
 * The proxy aborts upstream fetches at `DEFAULT_TIMEOUT_MS` unless an entry
 * in `TIMEOUT_OVERRIDES` matches the joined backend path + HTTP method, in
 * which case the override wins. First match wins.
 *
 * `pathStr` is the path AFTER `/api/` (e.g. "features/abc/documentation/generate"),
 * so patterns must NOT include a leading slash or "/api".
 *
 * Add new entries only when an endpoint legitimately exceeds the default
 * (LLM aggregation, batch jobs, long-running indexing). Keep the surface as
 * small as possible and document the reason.
 */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export const DEFAULT_TIMEOUT_MS = 15_000;

export interface TimeoutOverride {
  pattern: RegExp;
  methods: ReadonlyArray<HttpMethod>;
  timeoutMs: number;
  reason: string;
}

export const TIMEOUT_OVERRIDES: ReadonlyArray<TimeoutOverride> = [
  {
    // CB-2375 — POST /api/features/{id}/documentation/generate runs an LLM
    // aggregation across execution summaries / implementation notes / QA tasks
    // and routinely takes 30–35s. Default 15s previously surfaced 504s in UI.
    pattern: /^features\/[^/]+\/documentation\/generate$/,
    methods: ['POST'],
    timeoutMs: 120_000,
    reason: 'doc-generate-llm-aggregation',
  },
];

export function getTimeoutMs(pathStr: string, method: HttpMethod): number {
  for (const rule of TIMEOUT_OVERRIDES) {
    if (rule.methods.includes(method) && rule.pattern.test(pathStr)) {
      return rule.timeoutMs;
    }
  }
  return DEFAULT_TIMEOUT_MS;
}
