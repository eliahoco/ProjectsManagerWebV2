/**
 * Security Test Utilities
 * Task: CB-1120 - Automated testing framework for security-related features
 * Part of STORY CB-1112: User can Filter Results by Date Range
 *
 * Provides reusable security test payloads and helpers for
 * both unit tests and E2E tests.
 */

/**
 * Common XSS attack payloads for input sanitization testing.
 */
export const XSS_PAYLOADS = [
  '<script>alert("xss")</script>',
  '<script>alert(String.fromCharCode(88,83,83))</script>',
  '<img src=x onerror=alert(1)>',
  '<img/src=x onerror=alert(1)>',
  '"><svg/onload=alert(1)>',
  '<body onload=alert(1)>',
  '<input onfocus=alert(1) autofocus>',
  '<iframe src="javascript:alert(1)">',
  'javascript:alert(1)',
  'data:text/html,<script>alert(1)</script>',
  '"><img src=x onerror=alert(1)//',
  '<math><mtext><table><mglyph><svg><mtext><textarea><path id=x></textarea><img src=x onerror=alert(1)>',
] as const;

/**
 * Common SQL injection payloads for backend security testing.
 */
export const SQL_INJECTION_PAYLOADS = [
  "'; DROP TABLE issues; --",
  "1 OR 1=1",
  "' UNION SELECT * FROM users --",
  "1; DELETE FROM issues WHERE 1=1",
  "' OR ''='",
  "1' AND '1'='1",
  "'; EXEC xp_cmdshell('whoami'); --",
  "1 AND (SELECT COUNT(*) FROM issues) > 0 --",
  "' OR 1=1 LIMIT 1 --",
  "admin'--",
] as const;

/**
 * Payloads for testing special character handling.
 */
export const SPECIAL_CHAR_PAYLOADS = [
  'test\x00null',             // null byte
  'test\r\ninjection',        // CRLF
  'test\nheader: value',      // header injection
  '../../../etc/passwd',       // path traversal
  '..\\..\\..\\etc\\passwd',  // Windows path traversal
  '\u202Etest',               // RTL override
  '\uFEFF\uFEFFtest',         // BOM characters
  '%00%0d%0a',                // URL-encoded special chars
] as const;

/**
 * Payloads for date field injection testing.
 */
export const DATE_INJECTION_PAYLOADS = [
  "2026-01-01'; DROP TABLE issues; --",
  "' OR 1=1 --",
  "not-a-date",
  "",
  "9999-99-99",
  "2026-01-01T99:99:99Z",
  "0000-00-00T00:00:00Z",
  "<script>alert(1)</script>",
  "null",
  "undefined",
] as const;

/**
 * Validates that a string does not contain common indicators
 * of information leakage.
 */
export function assertNoInfoLeakage(text: string): void {
  const leakagePatterns = [
    /Traceback \(most recent call/i,
    /at Object\.\<anonymous\>/,
    /node_modules\//,
    /\.ts:\d+:\d+/,
    /\.py", line \d+/,
    /ANTHROPIC_API_KEY/,
    /sk-ant-/,
    /Bearer [a-zA-Z0-9\-_.]{20,}/,
    /sqlite:\/\//,
    /password\s*[=:]\s*['"]/i,
  ];

  for (const pattern of leakagePatterns) {
    if (pattern.test(text)) {
      throw new Error(`Information leakage detected: matched pattern ${pattern}`);
    }
  }
}

/**
 * Validates that an HTML string does not contain executable script content.
 */
export function assertNoExecutableContent(html: string): void {
  const executablePatterns = [
    /<script[\s>]/i,
    /javascript:/i,
    /on\w+\s*=/i,  // event handlers like onclick=, onerror=
    /data:text\/html/i,
    /<iframe/i,
    /<object/i,
    /<embed/i,
  ];

  for (const pattern of executablePatterns) {
    if (pattern.test(html)) {
      throw new Error(`Executable content detected: matched pattern ${pattern}`);
    }
  }
}

/**
 * Generates a string of a specified length for testing input limits.
 */
export function generateLongString(length: number, char = 'A'): string {
  return char.repeat(length);
}

/**
 * Predefined set of allowed date field values for the filter.
 * Used to verify whitelist enforcement in tests.
 */
export const ALLOWED_DATE_FIELDS = [
  'createdAt',
  'updatedAt',
  'dueDate',
  'startedAt',
  'completedAt',
] as const;

/**
 * Predefined set of allowed sort fields.
 * Used to verify whitelist enforcement in tests.
 */
export const ALLOWED_SORT_FIELDS = [
  'sequence',
  'priority',
  'createdAt',
  'updatedAt',
  'dueDate',
  'title',
  'type',
  'status',
] as const;

/**
 * HTTP status codes that should use user-friendly error messages.
 */
export const SECURE_ERROR_STATUS_CODES = [400, 401, 403, 404, 409, 429, 500, 502, 503] as const;
