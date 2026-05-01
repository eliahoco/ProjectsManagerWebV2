'use client';

/**
 * FeatureDocumentationView — CB-2061 (T2.2.2) + CB-2063 (T2.2.4)
 *
 * Renders all sections of a FeatureDocumentationData record:
 *   overview · requirements · implementation · architecture · testingStrategy
 *   techStack badges · metrics card
 *
 * Header strip (T2.2.4) shows "Indexed Xm ago" with an embedding-status dot.
 */

import ReactMarkdown from 'react-markdown';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  CircleDot,
  ClipboardList,
  Code2,
  FlaskConical,
  Layers,
  ListChecks,
  Shapes,
  XCircle,
} from 'lucide-react';
import type { FeatureDocumentationData } from '@/hooks/useCodeBoard';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  MARKDOWN_LINK_COMPONENTS,
  PROSE_CLASSES,
  SAFE_URL_TRANSFORM,
} from './markdownPresets';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface FeatureDocumentationViewProps {
  doc: FeatureDocumentationData;
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Parse the JSON-string techStack field into a deduplicated string[]. */
function parseTechStack(raw: string | undefined | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const strings = parsed.filter((x): x is string => typeof x === 'string');
    return Array.from(new Set(strings));
  } catch {
    return [];
  }
}

/**
 * T2.2.4 — Format a UTC ISO timestamp as "Xm ago", "Xh ago", "Xd ago".
 * Falls back to the locale date string for anything older than 30 days.
 */
export function formatIndexedAt(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 'unknown';

  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay <= 30) return `${diffDay}d ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SectionProps {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}

function Section({ icon, title, children }: SectionProps) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <header className="mb-3 flex items-center gap-2">
        <span aria-hidden="true" className="text-zinc-400">
          {icon}
        </span>
        <h3 className="text-sm font-semibold text-zinc-200">{title}</h3>
      </header>
      <div className="text-sm text-zinc-300">{children}</div>
    </section>
  );
}

interface MarkdownSectionProps {
  icon: React.ReactNode;
  title: string;
  body: string | undefined | null;
}

function MarkdownSection({ icon, title, body }: MarkdownSectionProps) {
  if (!body || !body.trim()) return null;
  return (
    <Section icon={icon} title={title}>
      <div className={PROSE_CLASSES}>
        <ReactMarkdown
          urlTransform={SAFE_URL_TRANSFORM}
          components={MARKDOWN_LINK_COMPONENTS}
        >
          {body}
        </ReactMarkdown>
      </div>
    </Section>
  );
}

interface MetricItemProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  colourClass?: string;
}

function MetricItem({ label, value, icon, colourClass = 'text-zinc-300' }: MetricItemProps) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950/40 px-4 py-3">
      <span aria-hidden="true" className={cn('h-5 w-5', colourClass)}>
        {icon}
      </span>
      <span className={cn('text-xl font-bold tabular-nums', colourClass)}>{value}</span>
      <span className="text-center text-[11px] uppercase tracking-wide text-zinc-500">
        {label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// IndexingHeader (T2.2.4)
// ---------------------------------------------------------------------------

interface IndexingHeaderProps {
  embeddingId: string | null;
  lastIndexedAt: string | null;
}

function IndexingHeader({ embeddingId, lastIndexedAt }: IndexingHeaderProps) {
  const isIndexed = !!embeddingId;

  return (
    <div className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-1.5 text-xs">
      {isIndexed ? (
        <>
          <span
            aria-label="Indexed in ChromaDB"
            className="h-2 w-2 shrink-0 rounded-full bg-green-400"
          />
          <span className="text-zinc-400">
            Indexed
            {lastIndexedAt ? (
              <>
                {' '}
                <time
                  dateTime={lastIndexedAt}
                  title={new Date(lastIndexedAt).toLocaleString()}
                >
                  {formatIndexedAt(lastIndexedAt)}
                </time>
              </>
            ) : null}
          </span>
        </>
      ) : (
        <>
          <span
            aria-label="Not indexed in ChromaDB"
            className="h-2 w-2 shrink-0 rounded-full bg-amber-400"
            title="Not indexed in ChromaDB"
          />
          <span className="text-amber-400" title="Not indexed in ChromaDB">
            Not indexed in ChromaDB
          </span>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function FeatureDocumentationView({
  doc,
  className,
}: FeatureDocumentationViewProps) {
  const techItems = parseTechStack(doc.techStack);

  return (
    <div className={cn('space-y-4', className)}>
      {/* T2.2.4 — Indexing status strip */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <IndexingHeader
          embeddingId={doc.embeddingId}
          lastIndexedAt={doc.lastIndexedAt}
        />
        <span className="text-xs text-zinc-500">
          Last updated{' '}
          <time
            dateTime={doc.updatedAt}
            title={new Date(doc.updatedAt).toLocaleString()}
          >
            {formatIndexedAt(doc.updatedAt)}
          </time>
        </span>
      </div>

      {/* Metrics card */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <header className="mb-3 flex items-center gap-2">
          <span aria-hidden="true" className="text-zinc-400">
            <ListChecks className="h-4 w-4" />
          </span>
          <h3 className="text-sm font-semibold text-zinc-200">Progress</h3>
        </header>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <MetricItem
            label="Total Tasks"
            value={doc.totalTasks}
            icon={<Shapes className="h-5 w-5" />}
            colourClass="text-zinc-300"
          />
          <MetricItem
            label="Completed"
            value={doc.completedTasks}
            icon={<CheckCircle2 className="h-5 w-5" />}
            colourClass="text-green-400"
          />
          <MetricItem
            label="QA Tasks"
            value={doc.totalQATasks}
            icon={<CircleDot className="h-5 w-5" />}
            colourClass="text-cyan-400"
          />
          <MetricItem
            label="QA Passed"
            value={doc.passedQATasks}
            icon={<CheckCircle2 className="h-5 w-5" />}
            colourClass="text-emerald-400"
          />
          <MetricItem
            label="QA Failed"
            value={doc.failedQATasks}
            icon={<XCircle className="h-5 w-5" />}
            colourClass={doc.failedQATasks > 0 ? 'text-red-400' : 'text-zinc-500'}
          />
        </div>
      </section>

      {/* Tech stack badges */}
      {techItems.length > 0 && (
        <Section
          icon={<Code2 className="h-4 w-4" />}
          title="Tech Stack"
        >
          <div className="flex flex-wrap gap-1.5">
            {techItems.map((tech) => (
              <Badge
                key={tech}
                variant="outline"
                className="font-mono text-[11px] text-cyan-300 border-cyan-800/50"
              >
                {tech}
              </Badge>
            ))}
          </div>
        </Section>
      )}

      {/* Markdown sections */}
      <MarkdownSection
        icon={<BookOpen className="h-4 w-4" />}
        title="Overview"
        body={doc.overview}
      />

      <MarkdownSection
        icon={<ClipboardList className="h-4 w-4" />}
        title="Requirements"
        body={doc.requirements}
      />

      <MarkdownSection
        icon={<AlertCircle className="h-4 w-4" />}
        title="Implementation"
        body={doc.implementation}
      />

      <MarkdownSection
        icon={<Layers className="h-4 w-4" />}
        title="Architecture"
        body={doc.architecture}
      />

      <MarkdownSection
        icon={<FlaskConical className="h-4 w-4" />}
        title="Testing Strategy"
        body={doc.testingStrategy}
      />
    </div>
  );
}
