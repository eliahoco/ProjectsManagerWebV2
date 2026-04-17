/**
 * Stop Project API Route
 * POST /api/projects/[id]/stop
 *
 * Alias for the park route — delegates entirely to the park handler so
 * both endpoints behave identically.  Kept for backwards-compatibility
 * with any callers that already use `/stop`.
 */

export { POST } from '../park/route';
