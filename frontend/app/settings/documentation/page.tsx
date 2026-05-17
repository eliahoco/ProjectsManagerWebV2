'use client';

/**
 * Documentation Settings Page (CB-2084 / S3.2)
 *
 * Covers:
 *   T3.2.1 — page skeleton with React Query data loading
 *   T3.2.2 — settings form with optimistic UI (autoGenerate toggle,
 *             retentionDays, maxPerIssue inputs + Save / status badge)
 *   T3.2.3 — recent ExecutionSummaries list (latest 20, cross-project)
 *   T3.2.4 — per-row manual re-trigger button with confirmation dialog
 */

import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import {
  FileText,
  Save,
  Check,
  Loader2,
  RefreshCw,
  ExternalLink,
  AlertCircle,
  PlayCircle,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { useToast } from '@/components/ui/toast';
import { cn, _toUtcIso } from '@/lib/utils';
import {
  useDocSettings,
  useUpdateDocSettings,
  useRecentExecutionSummaries,
  useStartExecution,
  type DocSettingsData,
  type ExecutionSummaryWithKeyData,
} from '@/hooks/useCodeBoard';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// CB-2730 — apply `_toUtcIso` so a naive backend ISO is parsed as UTC, not
// the browser's local time. Backend now emits `Z` on `executedAt`, but the
// guard preserves correctness if an older row or a future surface re-introduces
// the naive shape. Exported for direct Vitest coverage (mirrors CB-2377).
export function formatDate(iso: string) {
  return new Date(_toUtcIso(iso)).toLocaleString(undefined, {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

function parseFilesTouched(raw: string): string[] {
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function ExitCodeBadge({ code }: { code?: number | null }) {
  if (code == null) {
    return (
      <span className="text-xs text-zinc-500 font-mono">—</span>
    );
  }
  if (code === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-mono px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
        <CheckCircle2 className="h-3 w-3" />
        {code}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-mono px-1.5 py-0.5 rounded bg-red-500/15 text-red-400 border border-red-500/25">
      <XCircle className="h-3 w-3" />
      {code}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Settings form (T3.2.2)
// ---------------------------------------------------------------------------

type SaveStatus = 'idle' | 'saving' | 'saved';

function DocSettingsForm({ initial }: { initial: DocSettingsData }) {
  const toast = useToast();
  const updateMutation = useUpdateDocSettings();

  const [autoGenerate, setAutoGenerate] = useState(initial.autoGenerate);
  const [retentionDays, setRetentionDays] = useState(initial.retentionDays);
  const [maxPerIssue, setMaxPerIssue] = useState(initial.maxPerIssue);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  // Sync if the server data changes (e.g. background refetch)
  useEffect(() => {
    setAutoGenerate(initial.autoGenerate);
    setRetentionDays(initial.retentionDays);
    setMaxPerIssue(initial.maxPerIssue);
  }, [initial.autoGenerate, initial.retentionDays, initial.maxPerIssue]);

  const isPending = updateMutation.isPending;

  async function handleSave() {
    setSaveStatus('saving');
    try {
      await updateMutation.mutateAsync({ autoGenerate, retentionDays, maxPerIssue });
      setSaveStatus('saved');
      toast.success('Saved', 'Documentation settings updated');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (err) {
      setSaveStatus('idle');
      toast.error('Save Failed', err instanceof Error ? err.message : 'Could not save settings');
    }
  }

  return (
    <div className="space-y-6">
      {/* Auto-generate toggle */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-medium">Auto-generate on completion</h3>
            <p className="text-sm text-zinc-400 mt-1">
              Automatically capture execution summaries when an AI session completes
            </p>
          </div>
          <button
            onClick={() => setAutoGenerate((v) => !v)}
            disabled={isPending}
            className={cn(
              'relative w-12 h-6 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-2 focus:ring-offset-zinc-900',
              autoGenerate ? 'bg-cyan-600' : 'bg-zinc-700',
              isPending && 'opacity-50 cursor-not-allowed',
            )}
            aria-label={autoGenerate ? 'Disable auto-generate' : 'Enable auto-generate'}
          >
            <span
              className={cn(
                'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
                autoGenerate ? 'left-7' : 'left-1',
              )}
            />
          </button>
        </div>
      </div>

      {/* Retention days */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
        <div className="flex items-start gap-4">
          <div className="flex-1">
            <h3 className="text-white font-medium">Retention period</h3>
            <p className="text-sm text-zinc-400 mt-1">
              How many days to keep execution summaries (1 – 1825)
            </p>
            <div className="mt-3 flex items-center gap-3">
              <input
                type="number"
                value={retentionDays}
                onChange={(e) => {
                  const v = Math.max(1, Math.min(1825, parseInt(e.target.value) || 1));
                  setRetentionDays(v);
                }}
                min={1}
                max={1825}
                disabled={isPending}
                className="w-28 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-50"
              />
              <span className="text-sm text-zinc-400">days</span>
            </div>
          </div>
        </div>
      </div>

      {/* Max per issue */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
        <div className="flex items-start gap-4">
          <div className="flex-1">
            <h3 className="text-white font-medium">Max summaries per issue</h3>
            <p className="text-sm text-zinc-400 mt-1">
              Maximum execution summaries stored per issue (1 – 1000)
            </p>
            <div className="mt-3 flex items-center gap-3">
              <input
                type="number"
                value={maxPerIssue}
                onChange={(e) => {
                  const v = Math.max(1, Math.min(1000, parseInt(e.target.value) || 1));
                  setMaxPerIssue(v);
                }}
                min={1}
                max={1000}
                disabled={isPending}
                className="w-28 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-50"
              />
              <span className="text-sm text-zinc-400">summaries</span>
            </div>
          </div>
        </div>
      </div>

      {/* Save */}
      <div className="flex items-center justify-end gap-3">
        {saveStatus === 'saving' && (
          <span className="text-xs text-zinc-400 flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin" />
            Saving…
          </span>
        )}
        {saveStatus === 'saved' && (
          <span className="text-xs text-emerald-400 flex items-center gap-1.5">
            <Check className="h-3 w-3" />
            Saved
          </span>
        )}
        <Button
          variant="default"
          onClick={handleSave}
          loading={isPending}
          disabled={isPending}
          className="min-w-[120px]"
        >
          {saveStatus === 'saved' ? (
            <>
              <Check className="h-4 w-4" />
              Saved!
            </>
          ) : (
            <>
              <Save className="h-4 w-4" />
              Save Settings
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Confirmation dialog (T3.2.4)
// ---------------------------------------------------------------------------

interface ConfirmDialogProps {
  issueKey: string;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}

function ConfirmDialog({ issueKey, onConfirm, onCancel, isPending }: ConfirmDialogProps) {
  // CB-2731 — delegate a11y wiring (focus trap, Esc, scroll lock,
  // aria-labelledby, restore-focus) to the shared <Modal> primitive.
  // CB-2378 portal-to-body fix is preserved (Modal portals into
  // document.body), and the destructive-flow stays open mid-mutation
  // (closeOnBackdropClick={false} + Modal already suppresses Esc when
  // isPending). data-autofocus lands initial focus on Cancel so the
  // safe action wins by default — a stray Enter never starts a session.
  return (
    <Modal
      isOpen
      onClose={onCancel}
      isPending={isPending}
      closeOnBackdropClick={false}
      icon={<AlertCircle className="h-5 w-5 text-amber-400" />}
      title="Re-trigger execution?"
      description={
        <>
          This will reset{' '}
          <span className="text-cyan-400 font-mono">{issueKey}</span> to{' '}
          <span className="font-medium text-zinc-300">TODO</span> and start a fresh
          Claude Code session.
        </>
      }
    >
      <div className="flex justify-end gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={onCancel}
          disabled={isPending}
          data-autofocus
        >
          Cancel
        </Button>
        <Button
          variant="default"
          size="sm"
          onClick={onConfirm}
          loading={isPending}
          className="bg-cyan-600 hover:bg-cyan-700"
        >
          <PlayCircle className="h-4 w-4" />
          Start
        </Button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Single summary row (T3.2.3 + T3.2.4)
// ---------------------------------------------------------------------------

interface SummaryRowProps {
  summary: ExecutionSummaryWithKeyData;
}

function SummaryRow({ summary }: SummaryRowProps) {
  const toast = useToast();
  const startExecution = useStartExecution();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const files = parseFilesTouched(summary.filesTouched);
  const displayKey = summary.issueKey ?? summary.issueId.slice(0, 8);

  async function handleConfirm() {
    try {
      // rewrite mode resets the issue to TODO so re-running CWQ/DONE rows bypasses the status-dep guard.
      await startExecution.mutateAsync({
        issueId: summary.issueId,
        provider: 'claude_code',
        executionMode: 'rewrite',
      });
      // Status flipped server-side; refresh recent summaries + any open issue caches so the row + boards reflect TODO.
      queryClient.invalidateQueries({ queryKey: ['recent-execution-summaries'] });
      queryClient.invalidateQueries({ queryKey: ['issue', summary.issueId] });
      queryClient.invalidateQueries({ queryKey: ['issues'] });
      toast.success('Execution started', `Session queued for ${displayKey}`);
    } catch (err) {
      toast.error('Failed', err instanceof Error ? err.message : 'Could not start execution');
    } finally {
      setConfirming(false);
    }
  }

  return (
    <>
      {confirming && (
        <ConfirmDialog
          issueKey={displayKey}
          onConfirm={handleConfirm}
          onCancel={() => setConfirming(false)}
          isPending={startExecution.isPending}
        />
      )}
      <tr className="border-b border-zinc-800/60 hover:bg-zinc-800/30 transition-colors group">
        {/* Timestamp */}
        <td className="py-3 pl-4 pr-3 text-xs text-zinc-400 whitespace-nowrap">
          <span className="flex items-center gap-1.5">
            <Clock className="h-3 w-3 text-zinc-600 flex-shrink-0" />
            {formatDate(summary.executedAt)}
          </span>
        </td>

        {/* Issue key */}
        <td className="py-3 px-3 text-xs">
          <Link
            href={`/codeboard/issues/${summary.issueId}#implementation`}
            className="font-mono text-cyan-400 hover:text-cyan-300 hover:underline transition-colors"
          >
            {displayKey}
          </Link>
        </td>

        {/* Provider */}
        <td className="py-3 px-3 text-xs text-zinc-300 whitespace-nowrap">
          {summary.provider}
        </td>

        {/* Exit code */}
        <td className="py-3 px-3">
          <ExitCodeBadge code={summary.exitCode} />
        </td>

        {/* Files touched */}
        <td className="py-3 px-3 text-xs text-zinc-400 font-mono">
          {files.length}
        </td>

        {/* Line counts */}
        <td className="py-3 px-3 text-xs whitespace-nowrap">
          {summary.linesAdded != null && (
            <span className="text-emerald-400 mr-1">+{summary.linesAdded}</span>
          )}
          {summary.linesRemoved != null && (
            <span className="text-red-400">-{summary.linesRemoved}</span>
          )}
          {summary.linesAdded == null && summary.linesRemoved == null && (
            <span className="text-zinc-600">—</span>
          )}
        </td>

        {/* Re-trigger */}
        <td className="py-3 pl-3 pr-4 text-right">
          <button
            onClick={() => setConfirming(true)}
            title={`Re-trigger execution for ${displayKey}`}
            className="opacity-0 group-hover:opacity-100 transition-opacity inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-zinc-700"
          >
            <RefreshCw className="h-3 w-3" />
            Re-run
          </button>
        </td>
      </tr>
    </>
  );
}

// ---------------------------------------------------------------------------
// Recent summaries panel (T3.2.3)
// ---------------------------------------------------------------------------

function RecentSummariesPanel() {
  const { data: summaries, isLoading, isError } = useRecentExecutionSummaries(20);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
        <h2 className="text-white font-semibold flex items-center gap-2">
          <FileText className="h-5 w-5 text-violet-400" />
          Recent Execution Summaries
        </h2>
        <span className="text-xs text-zinc-500">latest 20 across all issues</span>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-3 p-6 text-red-400 text-sm">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          Failed to load summaries.
        </div>
      )}

      {!isLoading && !isError && (!summaries || summaries.length === 0) && (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-zinc-500">
          <FileText className="h-10 w-10 text-zinc-700" />
          <p className="text-sm">No execution summaries yet.</p>
          <p className="text-xs text-zinc-600">
            Summaries appear here after AI executions complete.
          </p>
        </div>
      )}

      {!isLoading && !isError && summaries && summaries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 bg-zinc-900/80">
                <th className="py-2.5 pl-4 pr-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  Timestamp
                </th>
                <th className="py-2.5 px-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  Issue
                </th>
                <th className="py-2.5 px-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  Provider
                </th>
                <th className="py-2.5 px-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  Exit
                </th>
                <th className="py-2.5 px-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  Files
                </th>
                <th className="py-2.5 px-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  Lines
                </th>
                <th className="py-2.5 pl-3 pr-4 text-right text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {summaries.map((s) => (
                <SummaryRow key={s.id} summary={s} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page root (T3.2.1)
// ---------------------------------------------------------------------------

export default function DocumentationSettingsPage() {
  const { data: settings, isLoading, isError } = useDocSettings();

  return (
    <div className="p-6 max-w-3xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <FileText className="h-7 w-7 text-cyan-500" />
          Documentation Settings
        </h1>
        <p className="text-zinc-400 mt-1">
          Configure automatic execution documentation and retention policy
        </p>
      </div>

      {/* Settings form */}
      {isLoading && (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="h-8 w-8 animate-spin text-zinc-500" />
        </div>
      )}

      {isError && (
        <div className="mb-6 flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <span>Failed to load documentation settings. The backend may be unavailable.</span>
        </div>
      )}

      {settings && <DocSettingsForm initial={settings} />}

      {/* Spacer */}
      <div className="my-8 border-t border-zinc-800" />

      {/* Recent summaries */}
      <RecentSummariesPanel />
    </div>
  );
}
