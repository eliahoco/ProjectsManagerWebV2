'use client';

/**
 * Implementation Tab — displays the latest ExecutionSummary for an issue
 * (CB-1608) plus the editable ImplementationNotes section (CB-1609).
 */

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  AlertCircle,
  Clock,
  Cpu,
  FileCode,
  GitBranch,
  Layers,
  Lightbulb,
  Loader2,
  Plus,
  Sparkles,
  StickyNote,
  TriangleAlert,
  Wrench,
  X,
} from 'lucide-react';
import {
  ExecutionSummaryData,
  ImplementationNoteData,
  NoteCategory,
  NoteImportance,
  useCreateImplementationNote,
  useExecutionSummaries,
  useImplementationNotes,
} from '@/hooks/useCodeBoard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn, _toUtcIso } from '@/lib/utils';
import {
  PROSE_CLASSES,
  SAFE_URL_TRANSFORM,
  MARKDOWN_LINK_COMPONENTS,
} from './markdownPresets';

interface ImplementationTabProps {
  issueId: string | undefined;
  /**
   * Project the issue belongs to. Required by the backend (CB-2117) so
   * documentation lookups are scoped to ``(issueId, projectId)``. The
   * underlying hooks stay disabled until both ids are present.
   */
  projectId: string | undefined;
  className?: string;
}

// Cap rendered file lists so a malformed/giant payload cannot freeze the tab.
const MAX_FILES_DISPLAY = 500;

function parseJsonStringArray(raw: string | undefined | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const strings = parsed.filter(
      (item): item is string => typeof item === 'string',
    );
    return Array.from(new Set(strings));
  } catch {
    return [];
  }
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const rem = Math.round(seconds % 60);
  return rem === 0 ? `${mins}m` : `${mins}m ${rem}s`;
}

// CB-2730 — apply `_toUtcIso` so naive ISO strings (older ExecutionSummary /
// ImplementationNote rows, or any future surface that re-introduces the naive
// shape) parse as UTC, not browser-local time. Exported for direct Vitest
// coverage (mirrors CB-2377).
export function formatTimestamp(iso: string): string {
  const d = new Date(_toUtcIso(iso));
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface SectionProps {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  rightSlot?: React.ReactNode;
}

function Section({ icon, title, children, rightSlot }: SectionProps) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <header className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-zinc-200">
          <span aria-hidden="true" className="text-zinc-400">
            {icon}
          </span>
          {title}
        </h3>
        {rightSlot}
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

interface FilesSectionProps {
  files: string[];
  components: string[];
  linesAdded: number | null | undefined;
  linesRemoved: number | null | undefined;
}

function FilesSection({
  files,
  components,
  linesAdded,
  linesRemoved,
}: FilesSectionProps) {
  const hasLineCounts =
    typeof linesAdded === 'number' || typeof linesRemoved === 'number';

  const visibleFiles = files.slice(0, MAX_FILES_DISPLAY);
  const overflow = Math.max(0, files.length - MAX_FILES_DISPLAY);

  return (
    <Section
      icon={<FileCode aria-hidden="true" className="h-4 w-4" />}
      title="Files Modified"
      rightSlot={
        hasLineCounts ? (
          <div className="flex items-center gap-1.5 text-xs">
            {typeof linesAdded === 'number' && (
              <Badge variant="success" className="font-mono">
                +{linesAdded}
              </Badge>
            )}
            {typeof linesRemoved === 'number' && (
              <Badge variant="destructive" className="font-mono">
                -{linesRemoved}
              </Badge>
            )}
          </div>
        ) : null
      }
    >
      {components.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs uppercase tracking-wide text-zinc-500">
            Components:
          </span>
          {components.map((c) => (
            <Badge key={c} variant="outline" className="font-mono text-[11px]">
              {c}
            </Badge>
          ))}
        </div>
      )}

      {visibleFiles.length === 0 ? (
        <p className="text-zinc-500 italic">No files recorded.</p>
      ) : (
        <ul className="space-y-1">
          {visibleFiles.map((path) => (
            <li
              key={path}
              className="flex items-center gap-2 rounded border border-zinc-800/60 bg-zinc-950/40 px-2 py-1 font-mono text-xs text-zinc-300"
            >
              <FileCode
                aria-hidden="true"
                className="h-3.5 w-3.5 shrink-0 text-zinc-500"
              />
              <span className="truncate" title={path}>
                {path}
              </span>
            </li>
          ))}
        </ul>
      )}

      {overflow > 0 && (
        <p className="mt-2 text-xs text-zinc-500">
          +{overflow} more file{overflow === 1 ? '' : 's'} not shown
        </p>
      )}
    </Section>
  );
}

interface SummaryHeaderProps {
  summary: ExecutionSummaryData;
  totalRuns: number;
}

function SummaryHeader({ summary, totalRuns }: SummaryHeaderProps) {
  const commits = useMemo(
    () => parseJsonStringArray(summary.commitHashes),
    [summary.commitHashes],
  );

  return (
    <div className="rounded-lg border border-cyan-900/40 bg-cyan-950/10 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <Sparkles
            aria-hidden="true"
            className="mt-0.5 h-4 w-4 shrink-0 text-cyan-400"
          />
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              Latest Execution
            </h2>
            <p className="mt-0.5 text-xs text-zinc-400">
              {totalRuns > 1
                ? `Most recent of ${totalRuns} executions`
                : 'First execution'}
            </p>
          </div>
        </div>

        <div className="flex flex-col items-end gap-1 text-xs text-zinc-400">
          <span className="flex items-center gap-1">
            <Clock aria-hidden="true" className="h-3.5 w-3.5" />
            <time dateTime={summary.executedAt}>
              {formatTimestamp(summary.executedAt)}
            </time>
          </span>
          <span className="flex items-center gap-1">
            <Cpu aria-hidden="true" className="h-3.5 w-3.5" />
            {formatDuration(summary.executionTime)}
          </span>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Badge variant="secondary" className="font-mono text-[11px]">
          {summary.provider}
        </Badge>
        {summary.model && (
          <Badge variant="outline" className="font-mono text-[11px]">
            {summary.model}
          </Badge>
        )}
        {typeof summary.exitCode === 'number' && (
          <Badge
            variant={summary.exitCode === 0 ? 'success' : 'destructive'}
            className="font-mono text-[11px]"
          >
            exit {summary.exitCode}
          </Badge>
        )}
        {commits.map((hash) => (
          <Badge
            key={hash}
            variant="outline"
            title={hash}
            className="flex items-center gap-1 font-mono text-[11px]"
          >
            <GitBranch aria-hidden="true" className="h-3 w-3" />
            {hash.slice(0, 7)}
          </Badge>
        ))}
      </div>
    </div>
  );
}

// CB-1609: Implementation Notes — category-coded list + inline Add form.

const NOTE_CATEGORY_OPTIONS: NoteCategory[] = [
  'DECISION',
  'APPROACH',
  'TRADEOFF',
  'DEPENDENCY',
  'RISK',
  'LESSON',
  'GENERAL',
];

const NOTE_IMPORTANCE_OPTIONS: NoteImportance[] = ['LOW', 'MEDIUM', 'HIGH'];

interface CategoryStyle {
  border: string;
  bg: string;
  badge: string;
  label: string;
}

const CATEGORY_STYLES: Record<NoteCategory, CategoryStyle> = {
  DECISION: {
    border: 'border-purple-900/50',
    bg: 'bg-purple-950/20',
    badge: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
    label: 'Decision',
  },
  APPROACH: {
    border: 'border-blue-900/50',
    bg: 'bg-blue-950/20',
    badge: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
    label: 'Approach',
  },
  TRADEOFF: {
    border: 'border-amber-900/50',
    bg: 'bg-amber-950/20',
    badge: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    label: 'Tradeoff',
  },
  RISK: {
    border: 'border-red-900/50',
    bg: 'bg-red-950/20',
    badge: 'bg-red-500/15 text-red-300 border-red-500/30',
    label: 'Risk',
  },
  LESSON: {
    border: 'border-green-900/50',
    bg: 'bg-green-950/20',
    badge: 'bg-green-500/15 text-green-300 border-green-500/30',
    label: 'Lesson',
  },
  DEPENDENCY: {
    border: 'border-cyan-900/50',
    bg: 'bg-cyan-950/20',
    badge: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
    label: 'Dependency',
  },
  GENERAL: {
    border: 'border-zinc-800',
    bg: 'bg-zinc-900/40',
    badge: 'bg-zinc-700/40 text-zinc-300 border-zinc-600/40',
    label: 'General',
  },
};

const IMPORTANCE_BADGE: Record<NoteImportance, string> = {
  HIGH: 'bg-red-500/15 text-red-300 border-red-500/30',
  MEDIUM: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  LOW: 'bg-zinc-700/40 text-zinc-300 border-zinc-600/40',
};

const SELECT_CLASSES =
  'h-9 rounded-md border border-zinc-700 bg-zinc-800 px-2 text-sm text-zinc-200 ' +
  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cyan-500 ' +
  'focus-visible:border-cyan-500 disabled:cursor-not-allowed disabled:opacity-50';

const INPUT_CLASSES =
  'flex h-9 w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1 text-sm shadow-sm ' +
  'placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-1 ' +
  'focus-visible:ring-cyan-500 focus-visible:border-cyan-500 disabled:cursor-not-allowed disabled:opacity-50';

interface NoteCardProps {
  note: ImplementationNoteData;
}

function NoteCard({ note }: NoteCardProps) {
  const style =
    CATEGORY_STYLES[note.category] ?? CATEGORY_STYLES.GENERAL;
  const importanceClass =
    IMPORTANCE_BADGE[note.importance] ?? IMPORTANCE_BADGE.MEDIUM;
  return (
    <li
      className={cn(
        'rounded-lg border p-3 transition-colors',
        style.border,
        style.bg,
      )}
    >
      <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className={cn('text-[11px] font-semibold uppercase tracking-wide', style.badge)}
          >
            {style.label}
          </Badge>
          <Badge
            variant="outline"
            className={cn('text-[11px] font-semibold uppercase tracking-wide', importanceClass)}
          >
            {note.importance}
          </Badge>
          <h4 className="text-sm font-semibold text-zinc-100">{note.title}</h4>
        </div>
        <time
          dateTime={note.createdAt}
          className="text-xs text-zinc-500"
          title={note.createdAt}
        >
          {formatTimestamp(note.createdAt)}
        </time>
      </header>
      <div className={PROSE_CLASSES}>
        <ReactMarkdown
          urlTransform={SAFE_URL_TRANSFORM}
          components={MARKDOWN_LINK_COMPONENTS}
        >
          {note.content}
        </ReactMarkdown>
      </div>
      <p className="mt-2 text-xs text-zinc-500">— {note.author}</p>
    </li>
  );
}

interface AddNoteFormProps {
  issueId: string;
  projectId: string;
  onClose: () => void;
}

function AddNoteForm({ issueId, projectId, onClose }: AddNoteFormProps) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState<NoteCategory>('GENERAL');
  const [importance, setImportance] = useState<NoteImportance>('MEDIUM');
  const [submitError, setSubmitError] = useState<string | null>(null);

  const createNote = useCreateImplementationNote();

  const trimmedTitle = title.trim();
  const trimmedContent = content.trim();
  const canSubmit =
    trimmedTitle.length > 0 && trimmedContent.length > 0 && !createNote.isPending;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitError(null);
    try {
      await createNote.mutateAsync({
        issueId,
        projectId,
        data: {
          title: trimmedTitle,
          content: trimmedContent,
          category,
          importance,
        },
      });
      onClose();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to add note');
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-zinc-200">Add Note</h4>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label="Cancel"
          onClick={onClose}
          disabled={createNote.isPending}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>

      <div className="space-y-1">
        <label htmlFor="note-title" className="text-xs uppercase tracking-wide text-zinc-500">
          Title
        </label>
        <input
          id="note-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          placeholder="Short headline"
          className={INPUT_CLASSES}
          required
          disabled={createNote.isPending}
        />
      </div>

      <div className="space-y-1">
        <label htmlFor="note-content" className="text-xs uppercase tracking-wide text-zinc-500">
          Content
        </label>
        <Textarea
          id="note-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          maxLength={10_000}
          placeholder="Markdown supported"
          required
          disabled={createNote.isPending}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label htmlFor="note-category" className="text-xs uppercase tracking-wide text-zinc-500">
            Category
          </label>
          <select
            id="note-category"
            value={category}
            onChange={(e) => setCategory(e.target.value as NoteCategory)}
            className={cn(SELECT_CLASSES, 'w-full')}
            disabled={createNote.isPending}
          >
            {NOTE_CATEGORY_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {CATEGORY_STYLES[opt].label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <label htmlFor="note-importance" className="text-xs uppercase tracking-wide text-zinc-500">
            Importance
          </label>
          <select
            id="note-importance"
            value={importance}
            onChange={(e) => setImportance(e.target.value as NoteImportance)}
            className={cn(SELECT_CLASSES, 'w-full')}
            disabled={createNote.isPending}
          >
            {NOTE_IMPORTANCE_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt.charAt(0) + opt.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </div>
      </div>

      {submitError && (
        <p role="alert" className="text-xs text-red-300">
          {submitError}
        </p>
      )}

      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClose}
          disabled={createNote.isPending}
        >
          Cancel
        </Button>
        <Button type="submit" size="sm" loading={createNote.isPending} disabled={!canSubmit}>
          Save Note
        </Button>
      </div>
    </form>
  );
}

interface NotesSectionProps {
  issueId: string;
  projectId: string;
}

function NotesSection({ issueId, projectId }: NotesSectionProps) {
  const [adding, setAdding] = useState(false);
  const { data: notes, isLoading, isError, error } = useImplementationNotes(
    issueId,
    projectId,
  );

  // Defensive sort — backend orders DESC but the contract is documented here.
  const sortedNotes = useMemo(() => {
    if (!notes) return [];
    return [...notes].sort(
      (a, b) =>
        new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    );
  }, [notes]);

  return (
    <Section
      icon={<StickyNote aria-hidden="true" className="h-4 w-4" />}
      title="Implementation Notes"
      rightSlot={
        !adding && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setAdding(true)}
            aria-label="Add implementation note"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            Add
          </Button>
        )
      }
    >
      <div className="space-y-3">
        {adding && (
          <AddNoteForm
            issueId={issueId}
            projectId={projectId}
            onClose={() => setAdding(false)}
          />
        )}

        {isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 text-sm text-zinc-500"
          >
            <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            Loading notes…
          </div>
        )}

        {isError && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-red-900/50 bg-red-950/20 p-3 text-xs text-red-300"
          >
            <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              {error instanceof Error ? error.message : 'Failed to load notes.'}
            </span>
          </div>
        )}

        {!isLoading && !isError && sortedNotes.length === 0 && !adding && (
          <p className="text-sm italic text-zinc-500">
            No notes yet. Click <span className="font-medium text-zinc-300">Add</span>{' '}
            to capture a decision, tradeoff, or lesson.
          </p>
        )}

        {sortedNotes.length > 0 && (
          <ul className="space-y-2">
            {sortedNotes.map((note) => (
              <NoteCard key={note.id} note={note} />
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}

export function ImplementationTab({
  issueId,
  projectId,
  className,
}: ImplementationTabProps) {
  const {
    data: summaries,
    isLoading,
    isError,
    error,
  } = useExecutionSummaries(issueId, projectId);

  const latest = summaries?.[0];
  const files = useMemo(
    () => parseJsonStringArray(latest?.filesTouched),
    [latest?.filesTouched],
  );
  const components = useMemo(
    () => parseJsonStringArray(latest?.componentsModified),
    [latest?.componentsModified],
  );

  if (!issueId || !projectId) {
    return (
      <div className={cn('p-6 text-sm text-zinc-500', className)}>
        Select an issue to view its implementation.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={cn(
          'flex items-center gap-2 p-6 text-sm text-zinc-500',
          className,
        )}
      >
        <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
        Loading implementation…
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className={cn(
          'flex items-start gap-2 rounded-lg border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-300',
          className,
        )}
      >
        <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p className="font-semibold">Failed to load implementation.</p>
          <p className="mt-1 text-xs text-red-300/80">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      </div>
    );
  }

  if (!latest) {
    return (
      <div className={cn('space-y-4', className)}>
        <div
          role="status"
          className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-800 bg-zinc-950/40 p-8 text-center"
        >
          <Sparkles aria-hidden="true" className="h-6 w-6 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-300">
            No implementation summary yet
          </p>
          <p className="max-w-sm text-xs text-zinc-500">
            Once an AI execution finishes for this issue, the summary, file
            changes, and architecture notes will appear here.
          </p>
        </div>
        <NotesSection issueId={issueId} projectId={projectId} />
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      <SummaryHeader summary={latest} totalRuns={summaries?.length ?? 1} />

      <MarkdownSection
        icon={<Layers className="h-4 w-4" />}
        title="Summary"
        body={latest.summary}
      />

      <FilesSection
        files={files}
        components={components}
        linesAdded={latest.linesAdded}
        linesRemoved={latest.linesRemoved}
      />

      <MarkdownSection
        icon={<Layers className="h-4 w-4" />}
        title="Architecture Notes"
        body={latest.architectureNotes}
      />

      <MarkdownSection
        icon={<Wrench className="h-4 w-4" />}
        title="Technical Notes"
        body={latest.technicalNotes}
      />

      <MarkdownSection
        icon={<TriangleAlert className="h-4 w-4" />}
        title="Challenges"
        body={latest.challengesFaced}
      />

      <MarkdownSection
        icon={<Lightbulb className="h-4 w-4" />}
        title="Lessons Learned"
        body={latest.lessonsLearned}
      />

      <NotesSection issueId={issueId} projectId={projectId} />
    </div>
  );
}
