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
    projectId: 'p-1',
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
});
