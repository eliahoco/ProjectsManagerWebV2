'use client';

/**
 * CapabilityRibbon — CB-2914 E5.2.1.
 *
 * 24px-tall strip rendered ABOVE ChatInput. Shows the top-N capabilities
 * (agents + skills) most relevant to the current chat turn, fetched from
 * /api/studio/capabilities/suggest (CB-2914 E5.1.1). Each chip is a button:
 *
 *   - Single click  -> inserts a mention/slash-command into the textarea
 *                      (skills: `/qa-regression `, agents: `@code-reviewer `)
 *   - Shift+click   -> launches the capability immediately (Phase 2 — for
 *                      now, also inserts; explicit launch lives in CB-2914 E2)
 *
 * The same ribbon is used by the Studio Investigation Engine (E2/E3) as a
 * VISIBLE projection of its auto-picker — the user sees which capabilities
 * the SIE would dispatch BEFORE the cycle launches.
 */

import { cn } from '@/lib/utils';
import {
  useCapabilitySuggestions,
  type CapabilitySuggestion,
} from '@/hooks/useCapabilitySuggestions';

interface CapabilityRibbonProps {
  sessionId: string | null;
  /** Current textarea draft — passes through to the suggest endpoint as the active message. */
  draft?: string;
  /** Called when the user picks a capability. Parent inserts the token into the textarea. */
  onInsert: (token: string, suggestion: CapabilitySuggestion) => void;
  /** Optional override of top-N. Default 7. */
  topN?: number;
  className?: string;
}

// Tiny icon-glyph map by kind/name. Avoid a heavy icon font; just emoji for now.
// Override per-capability if needed; otherwise fall back to kind default.
const KIND_GLYPH: Record<string, string> = {
  agent: '◆',
  skill: '◇',
};
const NAME_GLYPH: Record<string, string> = {
  'bug-repro': '🐛',
  'code-reviewer': '🔎',
  'security-auditor': '🛡',
  'qa-regression': '✅',
  debugger: '🪲',
  atlas: '📚',
  'python-pro': '🐍',
  'react-specialist': '⚛',
  'nextjs-developer': '▲',
  'frontend-design': '🎨',
  'docker-expert': '🐳',
  candlekeep: '📖',
  jonny: '👔',
  'chrome-devtools': '🌐',
  verification: '🔍',
};

function glyph(s: CapabilitySuggestion): string {
  return NAME_GLYPH[s.name] ?? KIND_GLYPH[s.kind] ?? '◇';
}

function token(s: CapabilitySuggestion): string {
  // Skills become `/name ` (slash command); agents become `@name ` (mention).
  return s.kind === 'skill' ? `/${s.name} ` : `@${s.name} `;
}

export function CapabilityRibbon({
  sessionId,
  draft = '',
  onInsert,
  topN = 7,
  className,
}: CapabilityRibbonProps) {
  const { data, isLoading, isError } = useCapabilitySuggestions({
    sessionId,
    message: draft,
    topN,
  });

  // Hidden until there's signal to show OR until parent decides to render.
  // The ribbon ALWAYS reserves space (24px) so the textarea doesn't jump
  // when suggestions arrive.
  const suggestions = data ?? [];

  return (
    <div
      role="toolbar"
      aria-label="Suggested capabilities"
      className={cn(
        // 24px slim strip above the composer. Theme-aware bg matches ChatInput.
        'flex items-center gap-1.5 px-3 h-7 overflow-x-auto',
        'scrollbar-thin scrollbar-thumb-zinc-300 dark:scrollbar-thumb-zinc-700',
        'border-t border-zinc-200 dark:border-zinc-800',
        'bg-zinc-50 dark:bg-zinc-900/60',
        className,
      )}
    >
      <span
        className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 flex-shrink-0 font-medium"
        aria-hidden="true"
      >
        Suggest
      </span>

      {isLoading && suggestions.length === 0 && (
        <span className="text-xs text-zinc-400 italic">ranking…</span>
      )}

      {isError && (
        <span className="text-xs text-amber-600 dark:text-amber-400">
          ribbon unavailable
        </span>
      )}

      {!isLoading && !isError && suggestions.length === 0 && (
        <span className="text-xs text-zinc-400 italic">type something…</span>
      )}

      {suggestions.map((s) => (
        <button
          key={`${s.kind}:${s.name}`}
          type="button"
          onClick={() => onInsert(token(s), s)}
          title={`${s.kind === 'skill' ? '/' : '@'}${s.name} — ${s.description}`}
          aria-label={`Insert ${s.kind} ${s.name}: ${s.description}`}
          className={cn(
            // Compact chip. Theme tokens match CB-2813 contrast bands.
            'group inline-flex items-center gap-1 px-2 py-0.5 rounded-md',
            'text-xs font-medium leading-none flex-shrink-0',
            'border transition-colors',
            // Light: zinc-100 bg + zinc-700 text on white-ish surface — 9.5:1.
            // Dark : zinc-800 bg + zinc-200 text — 10.7:1.
            'bg-white text-zinc-700 border-zinc-200 hover:bg-cyan-50 hover:border-cyan-300',
            'dark:bg-zinc-900 dark:text-zinc-200 dark:border-zinc-700 dark:hover:bg-cyan-950 dark:hover:border-cyan-600',
            'focus:outline-none focus:ring-2 focus:ring-cyan-400/60',
          )}
        >
          <span aria-hidden="true" className="text-[12px]">{glyph(s)}</span>
          <span className="font-mono text-[11px]">
            {s.kind === 'skill' ? '/' : '@'}{s.name}
          </span>
        </button>
      ))}
    </div>
  );
}
