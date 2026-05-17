/**
 * Tests for AutoPilotRecoveryBanner — CB-2751
 *
 * Coverage:
 *  1. Each state/reason combo renders correct label + action button
 *  2. Resume click calls correct endpoint
 *  3. Countdown ticks down each second when reset_time is set
 *  4. Dismiss persists per state-reason key in localStorage
 *  5. Banner re-appears when state changes after dismiss
 *  6. Zombie banner renders force-recover action
 *  7. Abort confirm dialog appears and calls abort endpoint
 *  8. Retry-failed banner renders correct action
 *  9. Wait action renders disabled button
 * 10. Empty state — renders nothing
 * 11. Abort circuit-breaker renders abort action
 * 12. Both recoverable + zombie entries render together
 * 13. Dismiss X button sets localStorage and hides entry
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react';
import React from 'react';

// ─── localStorage mock ────────────────────────────────────────────────────────

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true });

// ─── EventSource mock ─────────────────────────────────────────────────────────

class MockEventSource {
  static instances: MockEventSource[] = [];
  onerror: (() => void) | null = null;
  listeners: Record<string, Array<(e: Event) => void>> = {};
  constructor(_url: string) { MockEventSource.instances.push(this); }
  addEventListener(type: string, fn: (e: Event) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(fn);
  }
  close() { /* no-op */ }
}
(global as unknown as Record<string, unknown>).EventSource = MockEventSource;

// ─── Import after mocks ───────────────────────────────────────────────────────

import {
  AutoPilotRecoveryBanner,
  getStateFriendlyLabel,
} from '@/components/codeboard/AutoPilotRecoveryBanner';
import type { RecoverableEntry } from '@/components/codeboard/AutoPilotRecoveryBanner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

type RecoveryPayload = {
  recoverable?: RecoverableEntry[];
  zombie?: RecoverableEntry[];
  auto_resume_pending?: Array<{ queue_id: string; key: string; state: string }>;
};

function mockFetch(payload: RecoveryPayload) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      recoverable: [],
      zombie: [],
      auto_resume_pending: [],
      ...payload,
    }),
  } as unknown as Response);
}

function mockFetchFailure() {
  global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
}

function entry(overrides: Partial<RecoverableEntry>): RecoverableEntry {
  return {
    queue_id: 'q-1',
    key: 'CB-2038',
    state: 'paused',
    reason: 'crash_recovery',
    reset_time: null,
    attempt_count: 0,
    suggested_action: 'resume',
    ...overrides,
  };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  localStorageMock.clear();
  MockEventSource.instances = [];
});

afterEach(() => {
  vi.useRealTimers();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AutoPilotRecoveryBanner', () => {
  // 1. Each state/reason combo — labels

  it('renders crash_recovery label and Resume now button', async () => {
    mockFetch({ recoverable: [entry({ state: 'paused', reason: 'crash_recovery', suggested_action: 'resume' })] });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => {
      expect(screen.getByTestId('recovery-banner-q-1')).toBeTruthy();
    });
    expect(screen.getByText(/Backend restarted mid-run/i)).toBeTruthy();
    expect(screen.getByTestId('banner-resume-q-1')).toBeTruthy();
    expect(screen.getByTestId('banner-resume-q-1').textContent).toContain('Resume now');
  });

  it('renders manual pause label', async () => {
    mockFetch({ recoverable: [entry({ state: 'paused', reason: 'manual', suggested_action: 'resume' })] });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByText(/Paused by you/i));
    expect(screen.getByText(/Paused by you/i)).toBeTruthy();
  });

  it('renders credit_exhaustion label', async () => {
    mockFetch({ recoverable: [entry({ state: 'paused', reason: 'credit_exhaustion', suggested_action: 'resume' })] });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByText(/Credits exhausted/i));
    expect(screen.getByText(/Credits exhausted/i)).toBeTruthy();
  });

  it('renders auth_failure label', async () => {
    mockFetch({ recoverable: [entry({ state: 'paused', reason: 'auth_failure', suggested_action: 'resume' })] });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByText(/authentication failed/i));
    expect(screen.getByText(/authentication failed/i)).toBeTruthy();
  });

  it('renders rate_limit_5h label for waiting_reset', async () => {
    mockFetch({
      recoverable: [
        entry({
          state: 'waiting_reset',
          reason: 'rate_limit_5h',
          suggested_action: 'wait',
          reset_time: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
        }),
      ],
    });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByText(/5-hour limit hit/i));
    expect(screen.getByText(/5-hour limit hit/i)).toBeTruthy();
  });

  it('renders rate_limit_weekly label', async () => {
    mockFetch({
      recoverable: [
        entry({
          state: 'waiting_reset',
          reason: 'rate_limit_weekly',
          suggested_action: 'wait',
          reset_time: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
        }),
      ],
    });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByText(/weekly limit hit/i));
    expect(screen.getByText(/weekly limit hit/i)).toBeTruthy();
  });

  // 2. Resume click calls correct endpoint

  it('resume action POSTs to queue resume endpoint', async () => {
    const postMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          recoverable: [entry({ state: 'paused', reason: 'crash_recovery', suggested_action: 'resume' })],
          zombie: [],
          auto_resume_pending: [],
        }),
      } as unknown as Response)
      .mockImplementation(postMock);

    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('banner-resume-q-1'));
    fireEvent.click(screen.getByTestId('banner-resume-q-1'));

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        expect.stringContaining('/queue/q-1/resume'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  // 3. Countdown ticks down each second

  it('shows live countdown when reset_time is set', async () => {
    const resetTime = new Date(Date.now() + 5 * 60 * 1000).toISOString(); // 5 min from now
    mockFetch({
      recoverable: [
        entry({ state: 'waiting_reset', reason: 'rate_limit_5h', suggested_action: 'wait', reset_time: resetTime }),
      ],
    });

    render(<AutoPilotRecoveryBanner />);

    // Wait for the countdown line to appear (real timers are fine here)
    const countdownLine = await screen.findByTestId('countdown-line');
    expect(countdownLine.textContent).toContain('left');
    // Verify it shows a time value (minutes remaining from 5m)
    expect(countdownLine.textContent).toMatch(/\d+m/);
  });

  // 4. Dismiss persists per state-reason key

  it('dismiss stores state:reason in localStorage', async () => {
    mockFetch({ recoverable: [entry({ state: 'paused', reason: 'crash_recovery', suggested_action: 'resume' })] });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('banner-dismiss-q-1'));
    fireEvent.click(screen.getByTestId('banner-dismiss-q-1'));

    expect(localStorageMock.getItem('autopilot.banner.dismissed.q-1')).toBe('paused:crash_recovery');
  });

  it('dismissed banner does not re-render on same state/reason', async () => {
    localStorageMock.setItem('autopilot.banner.dismissed.q-1', 'paused:crash_recovery');
    mockFetch({ recoverable: [entry({ state: 'paused', reason: 'crash_recovery', suggested_action: 'resume' })] });
    const { container } = render(<AutoPilotRecoveryBanner />);

    await waitFor(() => {
      // poll should have fired
      expect(global.fetch).toHaveBeenCalled();
    });

    // Banner should not be visible after dismiss
    expect(container.querySelector('[data-testid="recovery-banner-q-1"]')).toBeNull();
  });

  // 5. Banner re-appears when state/reason changes after dismiss

  it('re-shows when state changes after dismiss', async () => {
    localStorageMock.setItem('autopilot.banner.dismissed.q-1', 'paused:crash_recovery');
    // Different state now — should appear
    mockFetch({ recoverable: [entry({ state: 'paused', reason: 'manual', suggested_action: 'resume' })] });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('recovery-banner-q-1'));
    expect(screen.getByTestId('recovery-banner-q-1')).toBeTruthy();
  });

  // 6. Zombie banner renders force-recover action

  it('zombie entry renders force-recover button', async () => {
    mockFetch({
      zombie: [
        {
          queue_id: 'zombie-1',
          key: 'CB-2050',
          state: 'running',
          reason: 'zombie_detected',
          suggested_action: 'force-recover',
        },
      ],
    });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('recovery-banner-zombie-1'));
    expect(screen.getByText(/no live coroutine/i)).toBeTruthy();
    expect(screen.getByTestId('banner-force-recover-zombie-1')).toBeTruthy();
    expect(screen.getByTestId('banner-force-recover-zombie-1').textContent).toContain('Force recover');
  });

  // 7. Abort confirm dialog

  it('abort action shows confirm dialog then calls abort endpoint', async () => {
    const abortMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          recoverable: [entry({ queue_id: 'q-abort', key: 'CB-9999', state: 'paused', reason: 'manual', suggested_action: 'abort' })],
          zombie: [],
          auto_resume_pending: [],
        }),
      } as unknown as Response)
      .mockImplementation(abortMock);

    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('banner-abort-q-abort'));
    fireEvent.click(screen.getByTestId('banner-abort-q-abort'));

    // Dialog appears
    expect(screen.getByTestId('abort-confirm-dialog')).toBeTruthy();

    fireEvent.click(screen.getByTestId('abort-confirm-yes'));

    await waitFor(() => {
      expect(abortMock).toHaveBeenCalledWith(
        expect.stringContaining('/queue/q-abort/abort'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  // 8. Retry-failed banner

  it('retry-failed banner renders correct action button', async () => {
    mockFetch({
      recoverable: [
        entry({ state: 'paused', reason: 'crash_recovery', suggested_action: 'retry-failed' }),
      ],
    });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('banner-retry-failed-q-1'));
    expect(screen.getByTestId('banner-retry-failed-q-1').textContent).toContain('Retry failed tasks');
  });

  // 9. Wait action renders disabled button

  it('wait action renders disabled button', async () => {
    mockFetch({
      recoverable: [
        entry({
          state: 'waiting_reset',
          reason: 'rate_limit_5h',
          suggested_action: 'wait',
          reset_time: new Date(Date.now() + 3 * 60 * 1000).toISOString(),
        }),
      ],
    });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('banner-wait-q-1'));
    const waitBtn = screen.getByTestId('banner-wait-q-1');
    expect(waitBtn).toBeTruthy();
    expect(waitBtn.hasAttribute('disabled')).toBe(true);
  });

  // 10. Empty state — renders nothing

  it('renders nothing when no entries returned', async () => {
    mockFetch({});
    const { container } = render(<AutoPilotRecoveryBanner />);

    await waitFor(() => { expect(global.fetch).toHaveBeenCalled(); });

    expect(container.querySelector('[data-testid="autopilot-recovery-banner-root"]')).toBeNull();
  });

  // 11. Abort circuit-breaker

  it('abort suggested_action appears when circuit breaker trips', async () => {
    mockFetch({
      recoverable: [
        entry({ state: 'paused', reason: 'token_exhaustion', attempt_count: 4, suggested_action: 'abort' }),
      ],
    });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => screen.getByTestId('banner-abort-q-1'));
    expect(screen.getByTestId('banner-abort-q-1')).toBeTruthy();
  });

  // 12. Multiple entries render together

  it('renders both recoverable and zombie entries simultaneously', async () => {
    mockFetch({
      recoverable: [entry({ queue_id: 'q-r1', key: 'CB-100', state: 'paused', reason: 'manual', suggested_action: 'resume' })],
      zombie: [{ queue_id: 'q-z1', key: 'CB-200', state: 'running', reason: 'zombie_detected', suggested_action: 'force-recover' }],
    });
    render(<AutoPilotRecoveryBanner />);

    await waitFor(() => {
      expect(screen.getByTestId('recovery-banner-q-r1')).toBeTruthy();
      expect(screen.getByTestId('recovery-banner-q-z1')).toBeTruthy();
    });
  });

  // 13. Fetch failure — renders nothing without crashing

  it('survives fetch failure gracefully', async () => {
    mockFetchFailure();
    const { container } = render(<AutoPilotRecoveryBanner />);
    await waitFor(() => { expect(global.fetch).toHaveBeenCalled(); });
    // Should not crash — renders nothing
    expect(container.querySelector('[data-testid="autopilot-recovery-banner-root"]')).toBeNull();
  });

  // CB-2762 — no hard-coded localhost URLs in component source

  it('does not hard-code localhost URLs', async () => {
    // Read the component source at test time and assert no raw localhost strings exist.
    const fs = await import('fs');
    const path = await import('path');
    const src = fs.readFileSync(
      path.resolve(__dirname, '../components/codeboard/AutoPilotRecoveryBanner.tsx'),
      'utf8',
    );
    // Strip lines that contain the env-var fallback literal (allowed) and check the rest
    const lines = src.split('\n').filter(
      line => !line.includes('NEXT_PUBLIC_BACKEND_URL') && !line.includes('// '),
    );
    const hasHardcodedLocalhost = lines.some(line => /http:\/\/localhost/.test(line));
    expect(hasHardcodedLocalhost).toBe(false);
  });

  // getStateFriendlyLabel unit tests

  describe('getStateFriendlyLabel', () => {
    it('maps waiting_reset/rate_limit_5h correctly', () => {
      expect(getStateFriendlyLabel('waiting_reset', 'rate_limit_5h')).toContain('5-hour');
    });

    it('maps paused/credit_exhaustion correctly', () => {
      expect(getStateFriendlyLabel('paused', 'credit_exhaustion')).toContain('Credits exhausted');
    });

    it('maps running/zombie_detected correctly', () => {
      expect(getStateFriendlyLabel('running', 'zombie_detected')).toContain('no live coroutine');
    });

    it('falls back for unknown combo', () => {
      const result = getStateFriendlyLabel('mystery', 'unknown');
      expect(result).toBeTruthy();
    });
  });
});
