/**
 * CB-2379 regression — Re-run on a Recent Summaries row whose underlying
 * issue is in COMPLETED_WAITING_QA must reach the backend with
 * `execution_mode: 'rewrite'`. Without this, the default 'implement' mode
 * trips the dependency-status guard and the session fast-fails with
 * "Dependency check failed: <issue> has status COMPLETED_WAITING_QA".
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockMutateAsync = vi.fn();

vi.mock('@/hooks/useCodeBoard', () => ({
  useDocSettings: vi.fn(() => ({
    data: { autoGenerate: true, retentionDays: 30, maxPerIssue: 20 },
    isLoading: false,
    isError: false,
  })),
  useUpdateDocSettings: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),
  useRecentExecutionSummaries: vi.fn(() => ({
    data: [
      {
        id: 'sum-1',
        issueId: 'issue-cwq-1',
        issueKey: 'CB-9999',
        provider: 'claude_code',
        executedAt: '2026-05-08T10:00:00Z',
        exitCode: 0,
        filesTouched: '[]',
        linesAdded: 12,
        linesRemoved: 3,
      },
    ],
    isLoading: false,
    isError: false,
  })),
  useStartExecution: vi.fn(() => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  })),
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock('@/components/ui/toast', () => ({
  useToast: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  })),
}));

import DocumentationSettingsPage from '@/app/settings/documentation/page';

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <DocumentationSettingsPage />
    </QueryClientProvider>,
  );
}

describe('CB-2379: settings/documentation Re-run uses rewrite mode', () => {
  beforeEach(() => {
    mockMutateAsync.mockReset();
    mockMutateAsync.mockResolvedValue({ session_id: 'sess-1' });
  });

  it('passes executionMode="rewrite" so a CWQ/DONE issue is re-executed end-to-end', async () => {
    renderPage();

    const rerun = screen.getByTitle(/re-trigger execution for CB-9999/i);
    fireEvent.click(rerun);

    const dialog = await screen.findByRole('dialog');
    // Dialog must disclose the TODO reset so the user understands the side effect
    expect(dialog).toHaveTextContent(/TODO/);

    const start = await screen.findByRole('button', { name: /start/i });
    fireEvent.click(start);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledTimes(1);
    });

    const arg = mockMutateAsync.mock.calls[0][0];
    expect(arg).toEqual({
      issueId: 'issue-cwq-1',
      provider: 'claude_code',
      executionMode: 'rewrite',
    });
    // The legacy client `force` flag must NOT be sent — backend ignores it and it would mask intent.
    expect(arg).not.toHaveProperty('force');
  });
});
