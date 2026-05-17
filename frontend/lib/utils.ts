/**
 * Utility Functions
 */

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with clsx
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * CB-2377 / CB-2730 — Defense-in-depth UTC normalizer for naive ISO strings.
 *
 * Backend documentation-pipeline responses now serialize all datetimes with the
 * `Z` suffix via Pydantic `field_serializer`. This guard keeps any stray naive
 * ISO interpreted as UTC so a future regression on a different surface does not
 * silently re-introduce the off-by-tz-offset relative-time bug.
 *
 * Behavior:
 *   - Empty / falsy → returned as-is (caller handles "unknown").
 *   - Date-only ISO (`YYYY-MM-DD`, no `T`) → returned as-is. Spec already
 *     defines these as UTC midnight; appending `Z` is non-standard.
 *   - ISO with explicit `Z` or `±HH:MM` / `±HHMM` offset → returned as-is.
 *   - Otherwise → append `Z`.
 *
 * Originally inlined in `components/codeboard/FeatureDocumentationView.tsx`
 * (CB-2377). CB-2730 promoted it to a shared util so the
 * documentation-settings page and ImplementationTab use the same guard
 * (FeatureDocumentationView re-exports for test compatibility).
 */
export function _toUtcIso(iso: string): string {
  if (!iso) return iso;
  if (!iso.includes('T')) return iso;
  return /Z|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
}

/**
 * Format a date to a readable string
 */
export function formatDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format a relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(d);
}

/**
 * Capitalize first letter
 */
export function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

/**
 * Get project type display name
 */
export function getProjectTypeDisplay(type: string | null): string {
  if (!type) return 'Unknown';

  const typeMap: Record<string, string> = {
    nodejs: 'Node.js',
    'nodejs-react': 'React',
    'nodejs-next': 'Next.js',
    'nodejs-vue': 'Vue.js',
    python: 'Python',
    'python-fastapi': 'FastAPI',
    'python-flask': 'Flask',
    'python-django': 'Django',
    go: 'Go',
    rust: 'Rust',
    java: 'Java',
    cpp: 'C++',
    shell: 'Shell',
  };

  return typeMap[type.toLowerCase()] || capitalize(type);
}

/**
 * Get service type color class
 */
export function getServiceTypeColor(type: string): string {
  const colorMap: Record<string, string> = {
    FRONTEND: 'bg-blue-500',
    BACKEND: 'bg-green-500',
    DATABASE: 'bg-purple-500',
    CACHE: 'bg-orange-500',
    QUEUE: 'bg-yellow-500',
    MONITORING: 'bg-pink-500',
    OTHER: 'bg-gray-500',
  };

  return colorMap[type.toUpperCase()] || colorMap.OTHER;
}
