'use client';

/**
 * Feature Documentation Page — CB-2060 (T2.2.1) + CB-2066 (T2.3.2)
 *
 * Route: /codeboard/features/[id]/documentation
 *
 * - Validates issue.type === 'FEATURE', otherwise shows an error card.
 * - Calls useFeatureDocumentation(issueId).
 * - Renders FeatureDocumentationView when data exists.
 * - Renders the empty-state card (T2.3.2) when documentation has not been
 *   generated yet (hook returns null).
 */

import { use } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  Loader2,
  Sparkles,
} from 'lucide-react';
import {
  useFeatureDocumentation,
  useIssue,
} from '@/hooks/useCodeBoard';
import { FeatureDocumentationView } from '@/components/codeboard/FeatureDocumentationView';
import { GenerateFeatureDocButton } from '@/components/codeboard/GenerateFeatureDocButton';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function FeatureDocumentationPage({ params }: PageProps) {
  const { id: issueId } = use(params);

  const {
    data: issue,
    isLoading: issueLoading,
    isError: issueError,
  } = useIssue(issueId);

  const {
    data: doc,
    isLoading: docLoading,
    isError: docError,
    error: docErrorObj,
  } = useFeatureDocumentation(issueId, issue?.projectId);

  // Loading state
  if (issueLoading || docLoading) {
    return (
      <PageShell
        issueId={issueId}
        projectId={undefined}
        issueKey={null}
        title={null}
        doc={null}
      >
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 p-8 text-sm text-zinc-500"
        >
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading…
        </div>
      </PageShell>
    );
  }

  // Issue fetch error
  if (issueError || !issue) {
    return (
      <PageShell
        issueId={issueId}
        projectId={undefined}
        issueKey={null}
        title={null}
        doc={null}
      >
        <ErrorCard message="Could not load the issue. It may have been deleted or you may not have access." />
      </PageShell>
    );
  }

  // Type guard — only FEATURE issues have feature documentation
  if (issue.type !== 'FEATURE') {
    return (
      <PageShell
        issueId={issueId}
        projectId={issue.projectId}
        issueKey={issue.key}
        title={issue.title}
        doc={null}
      >
        <ErrorCard
          message={`Feature documentation is only available for FEATURE-type issues. This issue is type "${issue.type}".`}
          action={
            <Link
              href={`/codeboard/issues/${encodeURIComponent(issueId)}`}
              className="mt-3 inline-flex items-center gap-1.5 text-sm text-cyan-400 hover:text-cyan-300"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Back to issue
            </Link>
          }
        />
      </PageShell>
    );
  }

  // Documentation fetch error (not a 404 — those return null)
  if (docError) {
    return (
      <PageShell
        issueId={issueId}
        projectId={issue.projectId}
        issueKey={issue.key}
        title={issue.title}
        doc={null}
      >
        <ErrorCard
          message={
            docErrorObj instanceof Error
              ? docErrorObj.message
              : 'Failed to load feature documentation.'
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      issueId={issueId}
      projectId={issue.projectId}
      issueKey={issue.key}
      title={issue.title}
      doc={doc ?? null}
    >
      {doc ? (
        <FeatureDocumentationView doc={doc} />
      ) : (
        /* T2.3.2 — Empty state */
        <EmptyState issueId={issueId} projectId={issue.projectId} />
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Layout shell
// ---------------------------------------------------------------------------

interface PageShellProps {
  issueId: string;
  projectId: string | undefined;
  issueKey: string | null;
  title: string | null;
  doc: import('@/hooks/useCodeBoard').FeatureDocumentationData | null;
  children: React.ReactNode;
}

function PageShell({
  issueId,
  projectId,
  issueKey,
  title,
  doc,
  children,
}: PageShellProps) {
  return (
    <div className="min-h-screen bg-zinc-950 p-4 md:p-6">
      <div className="mx-auto space-y-4">
        {/* Header row */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <Link
              href={issueId ? `/codeboard/issues/${encodeURIComponent(issueId)}` : '/codeboard'}
              className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              {issueKey ?? 'Back'}
            </Link>

            <div className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-cyan-400" aria-hidden="true" />
              <h1 className="text-lg font-semibold text-zinc-100">
                {issueKey && (
                  <span className="mr-2 font-mono text-zinc-400">{issueKey}</span>
                )}
                {title ?? 'Feature Documentation'}
              </h1>
            </div>
          </div>

          {issueKey && (
            <GenerateFeatureDocButton
              issueId={issueId}
              projectId={projectId}
              existingDoc={doc}
            />
          )}
        </div>

        {/* Page body */}
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state (T2.3.2)
// ---------------------------------------------------------------------------

function EmptyState({
  issueId,
  projectId,
}: {
  issueId: string;
  projectId: string | undefined;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-zinc-800 bg-zinc-950/40 px-6 py-16 text-center">
      <Sparkles className="h-10 w-10 text-zinc-600" aria-hidden="true" />
      <div className="space-y-1">
        <p className="text-base font-semibold text-zinc-200">
          No documentation generated yet
        </p>
        <p className="max-w-sm text-sm text-zinc-500">
          Click <span className="font-medium text-zinc-300">Generate</span> to build
          documentation from execution history, tasks, and QA results for this feature.
        </p>
      </div>
      <GenerateFeatureDocButton
        issueId={issueId}
        projectId={projectId}
        existingDoc={null}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error card helper
// ---------------------------------------------------------------------------

function ErrorCard({
  message,
  action,
}: {
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col rounded-lg border border-red-900/50 bg-red-950/20 p-5',
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle
          className="mt-0.5 h-5 w-5 shrink-0 text-red-400"
          aria-hidden="true"
        />
        <p className="text-sm text-red-300">{message}</p>
      </div>
      {action && <div className="mt-1 pl-8">{action}</div>}
    </div>
  );
}
