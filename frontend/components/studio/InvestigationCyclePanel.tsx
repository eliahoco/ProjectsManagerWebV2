'use client';

/**
 * InvestigationCyclePanel — CB-2914 E5.3 + CB-3123 fix + CB-3124 fix.
 *
 * Right-rail panel that drives the SIE investigation cycle.
 *
 * Fixes in this revision:
 *   - CB-3123: shows running spinner per layer while agents are working;
 *     previous version only flipped queued→completed at the end because
 *     the backend never emitted RUNNING events. Engine now emits
 *     QUEUED → RUNNING → COMPLETED|FAILED|TIMEOUT per layer.
 *   - CB-3124: Reset button + ReactMarkdown render of the 5-part
 *     deliverable so it reads like a document, not a JSON dump.
 *     (Panel resize is solved at the StudioPage layout level, not here.)
 *
 * SSE contract (unchanged):
 *   data: {"type":"layer_status","layer":"code","status":"queued|running|completed|failed|timeout"}
 *   data: {"type":"deliverable","markdown":"..."}
 *   data: {"type":"done","duration_s":12.3,"cost_usd":0.012,"succeeded":3,"total":3,"request_id":"..."}
 *   data: {"type":"error","error":"..."}
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Loader2, RotateCcw, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTenant } from '@/contexts/TenantContext';
// H4 (react-specialist) fix: use project-wide safe markdown presets so
// AI-generated deliverable markdown can't render javascript:/data: URLs
// or links without rel="noopener noreferrer nofollow".
import {
  SAFE_URL_TRANSFORM,
  MARKDOWN_LINK_COMPONENTS,
} from '@/components/codeboard/markdownPresets';

type LayerStatus = 'queued' | 'running' | 'completed' | 'failed' | 'timeout' | 'unavailable';

interface LayerRow {
  layer: string;
  status: LayerStatus;
  startedAt?: number; // ms timestamp when RUNNING fired
}

interface InvestigationCyclePanelProps {
  sessionId: string;
  className?: string;
}

const STATUS_GLYPH: Record<LayerStatus, string> = {
  queued: '○',
  running: '◐',
  completed: '✓',
  failed: '✗',
  timeout: '⌛',
  unavailable: '—',
};

const STATUS_TEXT_CLASS: Record<LayerStatus, string> = {
  queued: 'text-zinc-500 dark:text-zinc-400',
  running: 'text-cyan-600 dark:text-cyan-400',
  completed: 'text-emerald-600 dark:text-emerald-400',
  failed: 'text-rose-600 dark:text-rose-400',
  timeout: 'text-amber-600 dark:text-amber-400',
  unavailable: 'text-zinc-400 dark:text-zinc-500',
};

const STATUS_LABEL: Record<LayerStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Done',
  failed: 'Failed',
  timeout: 'Timed out',
  unavailable: 'Unavailable',
};

export function InvestigationCyclePanel({ sessionId, className }: InvestigationCyclePanelProps) {
  const { workspaceId, tenantId } = useTenant();
  const [running, setRunning] = useState(false);
  const [description, setDescription] = useState('');
  const [layers, setLayers] = useState<LayerRow[]>([]);
  const [deliverable, setDeliverable] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<{
    duration_s: number;
    cost_usd: number;
    succeeded: number;
    total: number;
  } | null>(null);
  // CB-3123 fix: tick the clock during long layer runs so the spinner shows real time.
  const [tick, setTick] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  // Keep the running indicator's elapsed time live without re-rendering on every keystroke.
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [running]);

  const handleStart = useCallback(async () => {
    if (!description.trim() || running) return;
    setRunning(true);
    setLayers([]);
    setDeliverable(null);
    setError(null);
    setSummary(null);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8401';
      const resp = await fetch(`${API_BASE}/api/studio/sessions/${sessionId}/investigate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Workspace-ID': workspaceId,
          'X-Tenant-ID': tenantId,
        },
        body: JSON.stringify({ description, evidence: {} }),
        signal: ctrl.signal,
      });
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          try {
            const evt = JSON.parse(line.slice(5).trim());
            handleEvent(evt);
          } catch {
            /* ignore comment-only / malformed SSE chunks */
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError((e as Error).message);
      }
    } finally {
      setRunning(false);
    }
  }, [description, running, sessionId, workspaceId, tenantId]);

  function handleEvent(evt: {
    type: 'layer_status' | 'deliverable' | 'done' | 'error';
    layer?: string;
    status?: LayerStatus;
    markdown?: string;
    error?: string;
    duration_s?: number;
    cost_usd?: number;
    succeeded?: number;
    total?: number;
  }) {
    if (evt.type === 'layer_status' && evt.layer && evt.status) {
      setLayers((prev) => {
        const idx = prev.findIndex((r) => r.layer === evt.layer);
        const nowRunning = evt.status === 'running';
        if (idx === -1) {
          return [...prev, {
            layer: evt.layer!,
            status: evt.status!,
            startedAt: nowRunning ? Date.now() : undefined,
          }];
        }
        const next = [...prev];
        const prevRow = next[idx];
        next[idx] = {
          layer: evt.layer!,
          status: evt.status!,
          startedAt: nowRunning ? Date.now() : prevRow.startedAt,
        };
        return next;
      });
    } else if (evt.type === 'deliverable' && evt.markdown) {
      setDeliverable(evt.markdown);
    } else if (evt.type === 'done') {
      setSummary({
        duration_s: evt.duration_s ?? 0,
        cost_usd: evt.cost_usd ?? 0,
        succeeded: evt.succeeded ?? 0,
        total: evt.total ?? 0,
      });
    } else if (evt.type === 'error') {
      setError(evt.error ?? 'Investigation failed');
    }
  }

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const handleReset = useCallback(() => {
    abortRef.current?.abort();
    setLayers([]);
    setDeliverable(null);
    setError(null);
    setSummary(null);
    setDescription('');
    setRunning(false);
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return (
    <div
      className={cn(
        'flex flex-col h-full text-sm overflow-hidden',
        'bg-zinc-50 dark:bg-zinc-950 border-l border-zinc-200 dark:border-zinc-800',
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-200 dark:border-zinc-800 flex-shrink-0">
        <h2 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 uppercase tracking-wider">
          Investigation
        </h2>
        <div className="flex items-center gap-2">
          {running && (
            <button
              type="button"
              onClick={handleCancel}
              className="text-xs text-rose-600 dark:text-rose-400 hover:underline flex items-center gap-1"
              aria-label="Cancel investigation"
            >
              <Square className="w-3 h-3" /> Cancel
            </button>
          )}
          {(deliverable || error || layers.length > 0) && !running && (
            <button
              type="button"
              onClick={handleReset}
              className="text-xs text-zinc-600 dark:text-zinc-400 hover:underline flex items-center gap-1"
              aria-label="Reset investigation"
              title="Clear results and start over"
            >
              <RotateCcw className="w-3 h-3" /> Reset
            </button>
          )}
        </div>
      </div>

      {/* Trigger form */}
      {!running && !deliverable && !error && (
        <div className="p-3 space-y-2 border-b border-zinc-200 dark:border-zinc-800 flex-shrink-0">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what's broken — Studio will investigate across architecture, code, and runtime."
            rows={4}
            className={cn(
              'w-full text-sm px-2 py-1.5 rounded-md resize-y min-h-[80px]',
              'bg-white text-zinc-900 border border-zinc-200',
              'dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-700',
              'focus:outline-none focus:ring-2 focus:ring-cyan-400/50 focus:border-cyan-400',
            )}
          />
          <button
            type="button"
            onClick={handleStart}
            disabled={!description.trim()}
            className={cn(
              'w-full px-3 py-2 rounded-md text-sm font-medium transition-colors',
              'bg-cyan-600 hover:bg-cyan-500 text-white',
              'dark:bg-cyan-500 dark:hover:bg-cyan-400 dark:text-zinc-950',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            )}
          >
            Investigate
          </button>
        </div>
      )}

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
        {/* Layer status list — aria-live polite so screen readers announce
            transitions per H3 (react-specialist review). */}
        {layers.length > 0 && (
          <div className="space-y-1.5" aria-live="polite" aria-atomic="false">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold px-1">
              <span>Layers</span>
              {running && (
                <span className="text-cyan-600 dark:text-cyan-400 normal-case font-normal">
                  Working…
                </span>
              )}
            </div>
            {layers.map((r) => {
              const elapsedS = r.startedAt && r.status === 'running'
                ? Math.floor((Date.now() - r.startedAt) / 1000)
                : null;
              const isRunning = r.status === 'running';
              return (
                <div
                  key={r.layer}
                  className={cn(
                    'flex items-center gap-2 px-2 py-1.5 rounded-md text-xs',
                    'bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800',
                  )}
                >
                  {isRunning ? (
                    <Loader2 className={cn('w-4 h-4 animate-spin', STATUS_TEXT_CLASS[r.status])} />
                  ) : (
                    <span className={cn('font-mono text-base leading-none', STATUS_TEXT_CLASS[r.status])}>
                      {STATUS_GLYPH[r.status]}
                    </span>
                  )}
                  <span className="font-medium text-zinc-800 dark:text-zinc-200">{r.layer}</span>
                  <span className={cn('ml-auto text-[10px] uppercase tracking-wider font-medium', STATUS_TEXT_CLASS[r.status])}>
                    {STATUS_LABEL[r.status]}
                    {elapsedS !== null && (
                      <span className="ml-1 normal-case text-zinc-500 dark:text-zinc-400">
                        {elapsedS}s
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
            {/* tick state alone triggers the parent re-render; no DOM needed */}
          </div>
        )}

        {/* Summary chip */}
        {summary && (
          <div className="flex flex-wrap items-center gap-2 text-xs px-1 py-1.5 rounded-md bg-zinc-100 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">
              {summary.succeeded}/{summary.total} layers
            </span>
            <span className="text-zinc-500 dark:text-zinc-500">·</span>
            <span className="text-zinc-600 dark:text-zinc-400">{summary.duration_s.toFixed(1)}s</span>
            <span className="text-zinc-500 dark:text-zinc-500">·</span>
            <span className="text-zinc-600 dark:text-zinc-400">${summary.cost_usd.toFixed(4)}</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="text-xs text-rose-600 dark:text-rose-400 px-2 py-1.5 rounded-md bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900">
            {error}
          </div>
        )}

        {/* Idle state */}
        {layers.length === 0 && !running && !deliverable && !error && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400 italic px-1">
            Describe a bug above, then click <span className="font-semibold">Investigate</span>.
            Three agents will work in parallel — architecture, code, and runtime — and produce a 5-part report.
          </p>
        )}

        {/* Deliverable — rendered as proper markdown so headings/tables/lists read like a document */}
        {deliverable && (
          <div className="space-y-2">
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-semibold px-1">
              Report
            </div>
            <article
              className={cn(
                'prose prose-sm max-w-none p-3 rounded-md',
                'bg-white text-zinc-800 border border-zinc-200',
                'dark:bg-zinc-900 dark:text-zinc-200 dark:border-zinc-800 dark:prose-invert',
                // Tighten heading spacing for the right-rail viewport.
                'prose-headings:mt-3 prose-headings:mb-2',
                'prose-h1:text-base prose-h2:text-sm prose-h3:text-xs prose-h3:uppercase prose-h3:tracking-wider',
                'prose-p:my-2 prose-table:text-[11px]',
                'prose-code:text-[11px] prose-pre:text-[11px]',
              )}
            >
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                urlTransform={SAFE_URL_TRANSFORM}
                components={MARKDOWN_LINK_COMPONENTS}
              >
                {deliverable}
              </ReactMarkdown>
            </article>
          </div>
        )}
      </div>
    </div>
  );
}
