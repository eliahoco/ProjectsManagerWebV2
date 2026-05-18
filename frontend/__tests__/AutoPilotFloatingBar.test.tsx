/**
 * Tests for AutoPilotFloatingBar — E5 additions:
 * - Countdown timer when waiting_reset + token_exhaustion + reset_time
 * - Crash-recovery banner with Resume / Skip current task / Abort buttons
 * - "Resume now" button calls resumeAutoPilot
 * - Countdown ticks every second
 *
 * Note: uses fireEvent instead of userEvent.setup() to avoid the
 * navigator.clipboard redefinition conflict from tests/setup.ts.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, waitFor, fireEvent, within } from '@testing-library/react';
import React from 'react';

// ─── Mock AutoPilotContext ────────────────────────────────────────────────────

const mockResumeAutoPilot = vi.fn().mockResolvedValue(undefined);
const mockSkipCurrentTask = vi.fn().mockResolvedValue(undefined);
const mockAbortAutoPilot = vi.fn().mockResolvedValue(undefined);
const mockPauseAutoPilot = vi.fn().mockResolvedValue(undefined);
const mockWaitForReset = vi.fn().mockResolvedValue(undefined);
const mockSwitchModel = vi.fn().mockResolvedValue(undefined);
const mockClearRecoveredQueue = vi.fn().mockResolvedValue(undefined);
const mockSetRecoveredQueues = vi.fn();

// Mutable state that tests can override per-test.
let mockState: Record<string, unknown> = {};

vi.mock('@/contexts/AutoPilotContext', () => ({
  useAutoPilot: () => ({
    state: mockState,
    resumeAutoPilot: mockResumeAutoPilot,
    skipCurrentTask: mockSkipCurrentTask,
    abortAutoPilot: mockAbortAutoPilot,
    pauseAutoPilot: mockPauseAutoPilot,
    waitForReset: mockWaitForReset,
    switchModel: mockSwitchModel,
    clearRecoveredQueue: mockClearRecoveredQueue,
    setRecoveredQueues: mockSetRecoveredQueues,
  }),
}));

// ─── Mock lucide-react (individual named stubs) ───────────────────────────────

vi.mock('lucide-react', () => ({
  Loader2: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Loader2', ...p }),
  Pause: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Pause', ...p }),
  Play: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Play', ...p }),
  SkipForward: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-SkipForward', ...p }),
  Square: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Square', ...p }),
  ChevronDown: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-ChevronDown', ...p }),
  ChevronUp: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-ChevronUp', ...p }),
  CheckCircle2: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-CheckCircle2', ...p }),
  AlertCircle: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-AlertCircle', ...p }),
  Clock: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Clock', ...p }),
  Timer: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Timer', ...p }),
  RefreshCw: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-RefreshCw', ...p }),
  ShieldAlert: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-ShieldAlert', ...p }),
  RotateCcw: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-RotateCcw', ...p }),
}));

// ─── Import component (after mocks) ──────────────────────────────────────────

import { AutoPilotFloatingBar } from '@/components/codeboard/AutoPilotFloatingBar';

// ─── Base state factory ───────────────────────────────────────────────────────

const EMPTY_PROGRESS = { total: 5, completed: 2, skipped: 0, failed: 0, pending: 3, percent: 40 };

function makeState(overrides: Record<string, unknown> = {}) {
  return {
    isActive: true,
    isPaused: false,
    isWaitingReset: false,
    queueId: 'q-1',
    featureId: 'f-1',
    featureKey: 'CB-100',
    featureTitle: 'Feature A',
    // CB-2802: projectId is now threaded to all scoped queue API calls.
    projectId: 'project-abc',
    queue: [],
    currentIndex: 0,
    progress: EMPTY_PROGRESS,
    lastError: null,
    queueStatus: 'running',
    pauseReason: null,
    resetTime: null,
    recoveredQueues: [],
    ...overrides,
  };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockState = makeState();

  // fetch returns 200 with no recovered queues by default.
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ recovered_count: 0, queues: [] }),
  } as unknown as Response);
});

afterEach(() => {
  vi.useRealTimers();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AutoPilotFloatingBar', () => {
  it('renders nothing when isActive is false', () => {
    mockState = makeState({ isActive: false });
    const { container } = render(<AutoPilotFloatingBar />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the feature key when active', async () => {
    render(<AutoPilotFloatingBar />);
    expect(await screen.findByText('CB-100')).toBeInTheDocument();
  });

  // ── Countdown timer ─────────────────────────────────────────────────────────

  describe('WAITING_RESET state with countdown', () => {
    it('shows countdown text when isWaitingReset + token_exhaustion + reset_time', async () => {
      const resetTime = new Date(Date.now() + 10 * 60 * 1000).toISOString();
      mockState = makeState({
        isWaitingReset: true,
        isPaused: true,
        pauseReason: 'token_exhaustion',
        resetTime,
      });

      render(<AutoPilotFloatingBar />);

      await waitFor(() => {
        expect(screen.getByText(/Auto-resumes at/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/left/i)).toBeInTheDocument();
    });

    it('shows "Resume now" button in countdown row', async () => {
      const resetTime = new Date(Date.now() + 5 * 60 * 1000).toISOString();
      mockState = makeState({
        isWaitingReset: true,
        isPaused: true,
        pauseReason: 'token_exhaustion',
        resetTime,
      });

      render(<AutoPilotFloatingBar />);

      const btn = await screen.findByRole('button', { name: /resume now/i });
      expect(btn).toBeInTheDocument();
    });

    it('calls resumeAutoPilot when "Resume now" is clicked', async () => {
      const resetTime = new Date(Date.now() + 5 * 60 * 1000).toISOString();
      mockState = makeState({
        isWaitingReset: true,
        isPaused: true,
        pauseReason: 'token_exhaustion',
        resetTime,
      });

      render(<AutoPilotFloatingBar />);

      const btn = await screen.findByRole('button', { name: /resume now/i });
      fireEvent.click(btn);
      expect(mockResumeAutoPilot).toHaveBeenCalledTimes(1);
    });

    it('ticks countdown every second', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: false });

      const resetTime = new Date(Date.now() + 2 * 60 * 1000).toISOString();
      mockState = makeState({
        isWaitingReset: true,
        isPaused: true,
        pauseReason: 'token_exhaustion',
        resetTime,
      });

      render(<AutoPilotFloatingBar />);

      // Flush initial effects
      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      const initial = screen.getByText(/left/i).textContent ?? '';

      // Advance 30 seconds — countdown should have decremented
      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });

      const after = screen.getByText(/left/i).textContent ?? '';
      expect(after).not.toEqual(initial);
    });

    it('does not show countdown when pause_reason is not token_exhaustion', async () => {
      mockState = makeState({
        isWaitingReset: true,
        isPaused: true,
        pauseReason: 'crash_recovery',
        resetTime: null,
      });

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      expect(screen.queryByText(/Auto-resumes at/i)).not.toBeInTheDocument();
    });
  });

  // ── Crash-recovery banner ───────────────────────────────────────────────────

  describe('crash-recovery banner', () => {
    const recoveredQueue = {
      id: 'q-recovered-1',
      feature_key: 'CB-200',
      project_id: 'p-1',
    };

    beforeEach(() => {
      mockState = makeState({ recoveredQueues: [recoveredQueue] });
    });

    /** Helper: find buttons scoped to the recovery banner only. */
    function getBannerButtons() {
      const banner = screen.getByText(/AutoPilot recovered after backend restart/i).closest('div[class*="bg-red-900"]') as HTMLElement;
      return {
        resume: within(banner).getByRole('button', { name: /^resume$/i }),
        skip: within(banner).getByRole('button', { name: /skip current task/i }),
        abort: within(banner).getByRole('button', { name: /^abort$/i }),
      };
    }

    it('renders Resume, Skip current task, and Abort buttons', async () => {
      render(<AutoPilotFloatingBar />);
      await waitFor(() => screen.getByText(/AutoPilot recovered/i));
      const { resume, skip, abort } = getBannerButtons();
      expect(resume).toBeInTheDocument();
      expect(skip).toBeInTheDocument();
      expect(abort).toBeInTheDocument();
    });

    it('shows feature key in banner text', async () => {
      render(<AutoPilotFloatingBar />);
      await waitFor(() => {
        expect(screen.getByText(/CB-200/)).toBeInTheDocument();
      });
    });

    it('calls resumeAutoPilot and clearRecoveredQueue when Resume is clicked', async () => {
      render(<AutoPilotFloatingBar />);
      await waitFor(() => screen.getByText(/AutoPilot recovered/i));

      const { resume } = getBannerButtons();
      fireEvent.click(resume);

      await waitFor(() => {
        expect(mockResumeAutoPilot).toHaveBeenCalledTimes(1);
        expect(mockClearRecoveredQueue).toHaveBeenCalledWith('q-recovered-1');
      });
    });

    it('calls skipCurrentTask and clearRecoveredQueue when Skip is clicked', async () => {
      render(<AutoPilotFloatingBar />);
      await waitFor(() => screen.getByText(/AutoPilot recovered/i));

      const { skip } = getBannerButtons();
      fireEvent.click(skip);

      await waitFor(() => {
        expect(mockSkipCurrentTask).toHaveBeenCalledTimes(1);
        expect(mockClearRecoveredQueue).toHaveBeenCalledWith('q-recovered-1');
      });
    });

    it('opens abort dialog and calls clearRecoveredQueue when Abort is clicked', async () => {
      render(<AutoPilotFloatingBar />);
      await waitFor(() => screen.getByText(/AutoPilot recovered/i));

      const { abort } = getBannerButtons();
      fireEvent.click(abort);

      await waitFor(() => {
        expect(screen.getByText(/Keep Current Status/i)).toBeInTheDocument();
        expect(mockClearRecoveredQueue).toHaveBeenCalledWith('q-recovered-1');
      });
    });
  });

  // ── Border colours ──────────────────────────────────────────────────────────

  describe('visual border distinctions', () => {
    it('applies amber border for token_exhaustion state', async () => {
      const resetTime = new Date(Date.now() + 60_000).toISOString();
      mockState = makeState({
        isWaitingReset: true,
        pauseReason: 'token_exhaustion',
        resetTime,
      });

      const { container } = render(<AutoPilotFloatingBar />);
      await act(async () => {});
      const bar = container.firstChild as HTMLElement;
      expect(bar.className).toContain('border-amber-600/60');
    });

    it('applies red border for crash_recovery state', async () => {
      mockState = makeState({
        isWaitingReset: true,
        pauseReason: 'crash_recovery',
      });

      const { container } = render(<AutoPilotFloatingBar />);
      await act(async () => {});
      const bar = container.firstChild as HTMLElement;
      expect(bar.className).toContain('border-red-600/60');
    });

    it('applies gray border for manual pause', async () => {
      mockState = makeState({
        isPaused: true,
        pauseReason: 'manual',
      });

      const { container } = render(<AutoPilotFloatingBar />);
      await act(async () => {});
      const bar = container.firstChild as HTMLElement;
      expect(bar.className).toContain('border-zinc-500/40');
    });
  });

  // ── Recovery status fetch on mount ──────────────────────────────────────────

  describe('recovery-status fetch on mount', () => {
    it('calls setRecoveredQueues when backend reports recovered_count > 0', async () => {
      const recovered = [{ id: 'q-x', feature_key: 'CB-300', project_id: 'p-2' }];
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 1, queues: recovered }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);

      await waitFor(() => {
        expect(mockSetRecoveredQueues).toHaveBeenCalledWith(recovered);
      });
    });

    it('does not call setRecoveredQueues when recovered_count is 0', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 0, queues: [] }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      expect(mockSetRecoveredQueues).not.toHaveBeenCalled();
    });
  });

  // ── Retry button (CB-2740) ──────────────────────────────────────────────────

  describe('retry button for failed tasks', () => {
    const failedTask = {
      issue_id: 'issue-failed-1',
      issue_key: 'CB-501',
      issue_title: 'Failing task',
      order: 2,
      status: 'failed' as const,
      execution_mode: 'implement',
      session_id: null,
      started_at: null,
      completed_at: null,
      error: 'Claude exited with code 1',
      retry_count: 0,
      session_info: null,
    };

    beforeEach(() => {
      // Queue is paused so retry is allowed.
      mockState = makeState({
        queueId: 'q-retry-1',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [failedTask],
      });
    });

    it('shows a retry icon button for a failed task in the expanded queue', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 0, queues: [] }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);

      // Open the expanded task list by clicking the expand button.
      const expandBtn = screen.getByTitle('Expand queue');
      fireEvent.click(expandBtn);

      await waitFor(() => {
        expect(screen.getByLabelText('Retry CB-501')).toBeInTheDocument();
      });
    });

    it('POSTs to the reset endpoint when the retry button is clicked', async () => {
      const fetchMock = vi.fn()
        // First call: recovery-status on mount
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        // Second call: task reset POST
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ success: true, new_status: 'pending' }),
          text: async () => '',
        } as unknown as Response);

      global.fetch = fetchMock;

      render(<AutoPilotFloatingBar />);

      // Expand queue
      fireEvent.click(screen.getByTitle('Expand queue'));

      const retryBtn = await screen.findByLabelText('Retry CB-501');
      fireEvent.click(retryBtn);

      await waitFor(() => {
        // Should have called fetch twice — mount recovery + retry POST
        expect(fetchMock).toHaveBeenCalledTimes(2);
        const [url, opts] = fetchMock.mock.calls[1] as [string, RequestInit];
        expect(url).toContain('/queue/q-retry-1/task/2/reset');
        // CB-2802: project_id must be present on all scoped queue endpoints.
        expect(url).toContain('project_id=');
        expect(opts.method).toBe('POST');
      });
    });

    it('shows a toast message after successful retry', async () => {
      global.fetch = vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ success: true }),
          text: async () => '',
        } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      fireEvent.click(screen.getByTitle('Expand queue'));

      const retryBtn = await screen.findByLabelText('Retry CB-501');
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(screen.getByText(/CB-501 reset to pending/i)).toBeInTheDocument();
      });
    });

    it('disables the retry button when queueStatus is running', async () => {
      mockState = makeState({
        queueId: 'q-retry-1',
        queueStatus: 'running',
        isPaused: false,
        queue: [failedTask],
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 0, queues: [] }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      fireEvent.click(screen.getByTitle('Expand queue'));

      const retryBtn = await screen.findByLabelText('Retry CB-501');
      expect(retryBtn).toBeDisabled();
      expect(retryBtn).toHaveAttribute('title', 'Pause queue first to retry tasks');
    });

    // CB-2775: bulk "Retry all failed" button removed — replaced by header
    // "Retry failed & Resume" + per-task Retry buttons.
    it('shows failed-task counter when expanded and tasks failed', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 0, queues: [] }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      fireEvent.click(screen.getByTitle('Expand queue'));

      await waitFor(() => {
        expect(screen.getByText(/1 failed task/i)).toBeInTheDocument();
        expect(screen.queryByTestId('retry-all-failed-btn')).not.toBeInTheDocument();
      });
    });
  });

  // ── CB-2779: Resume button conditional label ─────────────────────────────────

  describe('Resume button label (CB-2779)', () => {
    const failedTask = {
      issue_id: 'issue-f-1',
      issue_key: 'CB-2731',
      issue_title: 'Task that failed',
      order: 16,
      status: 'failed' as const,
      execution_mode: 'implement',
      session_id: null,
      started_at: null,
      completed_at: null,
      error: 'exit 1',
      retry_count: 0,
      session_info: null,
    };

    it('shows plain "Resume" label when paused with no failed tasks', async () => {
      mockState = makeState({
        queueId: 'q-resume-1',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [],
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 0, queues: [] }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      const btn = screen.getByTestId('resume-btn');
      expect(btn).toHaveTextContent('Resume');
      expect(btn).not.toHaveTextContent('Retry failed');
    });

    it('shows "Retry failed & Resume" label when paused with ≥1 failed tasks', async () => {
      mockState = makeState({
        queueId: 'q-resume-2',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [failedTask],
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 0, queues: [] }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      const btn = screen.getByTestId('resume-btn');
      expect(btn).toHaveTextContent('Retry failed & Resume');
    });

    it('clicking Resume (no failed tasks) calls resumeAutoPilot once', async () => {
      mockState = makeState({
        queueId: 'q-resume-3',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [],
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ recovered_count: 0, queues: [] }),
      } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      fireEvent.click(screen.getByTestId('resume-btn'));

      await waitFor(() => {
        expect(mockResumeAutoPilot).toHaveBeenCalledTimes(1);
      });
    });

    it('clicking "Retry failed & Resume" resets all failed tasks THEN calls resumeAutoPilot', async () => {
      const failedTask2 = { ...failedTask, issue_id: 'f-2', issue_key: 'CB-2732', order: 17 };

      mockState = makeState({
        queueId: 'q-resume-4',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [failedTask, failedTask2],
      });

      const callOrder: string[] = [];

      const fetchMock = vi.fn()
        // mount: recovery-status
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        // CB-2775 race fix: queue refetch at click time
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ tasks: [failedTask, failedTask2] }),
        } as unknown as Response)
        // reset task order 16
        .mockImplementationOnce(async (url: string) => {
          callOrder.push(`reset-${url.split('/task/')[1]?.split('/')[0]}`);
          return { ok: true, status: 200, json: async () => ({}), text: async () => '' } as unknown as Response;
        })
        // reset task order 17
        .mockImplementationOnce(async (url: string) => {
          callOrder.push(`reset-${url.split('/task/')[1]?.split('/')[0]}`);
          return { ok: true, status: 200, json: async () => ({}), text: async () => '' } as unknown as Response;
        });

      global.fetch = fetchMock;
      mockResumeAutoPilot.mockImplementationOnce(async () => {
        callOrder.push('resume');
      });

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      fireEvent.click(screen.getByTestId('resume-btn'));

      await waitFor(() => {
        expect(mockResumeAutoPilot).toHaveBeenCalledTimes(1);
      });

      // Verify ordering: both resets happen BEFORE resume
      expect(callOrder).toEqual(['reset-16', 'reset-17', 'resume']);
    });

    it('aborts resume flow without calling resumeAutoPilot when reset returns 409', async () => {
      mockState = makeState({
        queueId: 'q-resume-5',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [failedTask],
      });

      global.fetch = vi.fn()
        // mount: recovery-status
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        // CB-2775 race fix: queue refetch at click time
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ tasks: [failedTask] }),
        } as unknown as Response)
        // reset POST → 409 conflict
        .mockResolvedValueOnce({
          ok: false, status: 409,
          json: async () => ({}),
          text: async () => 'queue not paused',
        } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      fireEvent.click(screen.getByTestId('resume-btn'));

      await waitFor(() => {
        expect(screen.getByText(/Cannot reset — queue is not paused/i)).toBeInTheDocument();
      });

      // resumeAutoPilot must NOT have been called
      expect(mockResumeAutoPilot).not.toHaveBeenCalled();
    });

    // CB-2802: project_id must be present on all scoped queue mutation calls.
    it('includes project_id query param on the resume mutation call (CB-2802)', async () => {
      mockState = makeState({
        queueId: 'q-proj-test',
        projectId: 'proj-xyz',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [],
      });

      const fetchMock = vi.fn()
        // mount: recovery-status
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        // refetch queue at click time (handleResumeWithRetry)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ tasks: [] }),
        } as unknown as Response)
        // plain resume
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ success: true }),
        } as unknown as Response);

      global.fetch = fetchMock;

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      fireEvent.click(screen.getByTestId('resume-btn'));

      await waitFor(() => {
        // The resume POST must carry project_id=proj-xyz.
        const calls = fetchMock.mock.calls as [string, RequestInit][];
        const resumeCall = calls.find(([url]) => url.includes('/resume'));
        expect(resumeCall).toBeDefined();
        expect(resumeCall![0]).toContain('project_id=proj-xyz');
      });
    });

    // CB-2775 race fix regression: even if state.queue is stale (no failed tasks
    // in client cache), the refetch at click time finds them and triggers reset.
    it('refetches queue at click time so stale state.queue does not skip resets', async () => {
      // state.queue = empty (stale), but backend returns 1 failed task on refetch
      mockState = makeState({
        queueId: 'q-race-1',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual',
        queue: [], // stale!
      });

      const callOrder: string[] = [];
      global.fetch = vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        // refetch returns the actual failed task
        .mockImplementationOnce(async (url: string) => {
          callOrder.push(`refetch-${url.includes('/queue/q-race-1') ? 'queue' : 'other'}`);
          return {
            ok: true,
            json: async () => ({ tasks: [failedTask] }),
          } as unknown as Response;
        })
        // reset for the failed task discovered via refetch
        .mockImplementationOnce(async (url: string) => {
          callOrder.push(`reset-${url.split('/task/')[1]?.split('/')[0]}`);
          return { ok: true, status: 200, json: async () => ({}), text: async () => '' } as unknown as Response;
        });

      mockResumeAutoPilot.mockImplementationOnce(async () => {
        callOrder.push('resume');
      });

      render(<AutoPilotFloatingBar />);
      await act(async () => {});
      fireEvent.click(screen.getByTestId('resume-btn'));

      await waitFor(() => {
        expect(mockResumeAutoPilot).toHaveBeenCalledTimes(1);
      });

      expect(callOrder).toEqual(['refetch-queue', 'reset-16', 'resume']);
    });
  });

  // ── CB-2796 (S3): 409 conflict banner + Retry & Resume button ────────────────

  describe('CB-2796 resume 409 conflict banner', () => {
    beforeEach(() => {
      // Paused queue with NO client-side failed tasks (state.queue is empty/stale).
      // The 409 should surface from the server response.
      mockState = makeState({
        queueId: 'q-conflict-1',
        queueStatus: 'paused',
        isPaused: true,
        pauseReason: 'manual_circuit_breaker',
        queue: [],
      });
    });

    it('renders "Retry & Resume" button when resume returns 409 with failed_count > 0', async () => {
      global.fetch = vi.fn()
        // mount: recovery-status
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        // refetch queue at click time (handleResumeWithRetry)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ tasks: [] }), // no failed tasks client-side
        } as unknown as Response)
        // plain resume → 409 with failed_count > 0
        .mockResolvedValueOnce({
          ok: false,
          status: 409,
          json: async () => ({
            success: false,
            error: 'CONFLICT',
            code: 'QUEUE_NOT_RESUMABLE',
            message: 'Circuit breaker tripped — 7 failed tasks remain.',
            details: {
              queue_id: 'q-conflict-1',
              status: 'paused',
              pause_reason: 'manual_circuit_breaker',
              auto_resume_attempts: 3,
              failed_count: 7,
              pending_count: 0,
              suggestion: 'Use POST .../reset-failed-tasks then resume, or POST resume?retry_failed=true',
            },
          }),
        } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      fireEvent.click(screen.getByTestId('resume-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('retry-and-resume-btn')).toBeInTheDocument();
      });

      // Banner should show failed + pending counts
      expect(screen.getByText(/7 failed task/i)).toBeInTheDocument();
    });

    it('"Retry & Resume" button POSTs to resume?retry_failed=true', async () => {
      const fetchMock = vi.fn()
        // mount: recovery-status
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        // refetch queue at click time
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ tasks: [] }),
        } as unknown as Response)
        // plain resume → 409 with failed_count > 0
        .mockResolvedValueOnce({
          ok: false,
          status: 409,
          json: async () => ({
            details: { failed_count: 5, pending_count: 0, suggestion: 'Use retry_failed=true' },
          }),
        } as unknown as Response)
        // Retry & Resume call (retry_failed=true)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ success: true, status: 'resumed' }),
        } as unknown as Response);

      global.fetch = fetchMock;

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      // Trigger plain resume → 409
      fireEvent.click(screen.getByTestId('resume-btn'));

      const retryAndResumeBtn = await screen.findByTestId('retry-and-resume-btn');
      fireEvent.click(retryAndResumeBtn);

      await waitFor(() => {
        const calls = fetchMock.mock.calls as [string, RequestInit][];
        const retryCall = calls.find(([url]) => url.includes('retry_failed=true'));
        expect(retryCall).toBeDefined();
        expect(retryCall![0]).toContain('/queue/q-conflict-1/resume?retry_failed=true');
        // CB-2802: project_id must be appended to all scoped queue endpoints.
        expect(retryCall![0]).toContain('project_id=');
        expect(retryCall![1].method).toBe('POST');
      });
    });

    it('does not render conflict banner when 409 has failed_count = 0', async () => {
      global.fetch = vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ recovered_count: 0, queues: [] }),
        } as unknown as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ tasks: [] }),
        } as unknown as Response)
        // 409 but failed_count = 0 (e.g. wrong state, not a failed-task issue)
        .mockResolvedValueOnce({
          ok: false,
          status: 409,
          json: async () => ({
            message: 'Queue is running',
            details: { failed_count: 0, pending_count: 0 },
          }),
        } as unknown as Response);

      render(<AutoPilotFloatingBar />);
      await act(async () => {});

      fireEvent.click(screen.getByTestId('resume-btn'));

      await waitFor(() => {
        expect(screen.getByText(/Queue is running|Cannot resume/i)).toBeInTheDocument();
      });

      // Conflict banner must NOT appear
      expect(screen.queryByTestId('retry-and-resume-btn')).not.toBeInTheDocument();
    });
  });
});
