/**
 * Tests for useAutoPilotEvents hook — E5
 *
 * - Subscribes to SSE and fires toasts on lifecycle events
 * - Cleans up EventSource on unmount
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ─── Mock useToast ────────────────────────────────────────────────────────────

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  toasts: [],
  addToast: vi.fn(),
  removeToast: vi.fn(),
};

vi.mock('@/components/ui/toast', () => ({
  useToast: () => mockToast,
}));

// ─── Mock EventSource ─────────────────────────────────────────────────────────

type EventHandler = (event: MessageEvent) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners: Map<string, EventHandler[]> = new Map();
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: EventHandler) {
    const existing = this.listeners.get(type) ?? [];
    this.listeners.set(type, [...existing, handler]);
  }

  removeEventListener(type: string, handler: EventHandler) {
    const existing = this.listeners.get(type) ?? [];
    this.listeners.set(type, existing.filter(h => h !== handler));
  }

  /** Test helper: simulate an event being dispatched */
  dispatchTypedEvent(type: string, data: unknown) {
    const handlers = this.listeners.get(type) ?? [];
    const event = { data: JSON.stringify(data), type } as unknown as MessageEvent;
    for (const h of handlers) h(event);
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  MockEventSource.instances = [];
  (global as unknown as Record<string, unknown>).EventSource = MockEventSource;
});

afterEach(() => {
  delete (global as unknown as Record<string, unknown>).EventSource;
});

// ─── Import hook (after mocks) ────────────────────────────────────────────────

import { useAutoPilotEvents } from '@/hooks/useAutoPilotEvents';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeEventPayload(type: string, extra: Record<string, unknown> = {}) {
  return {
    id: 'evt-1',
    queueId: 'q-1',
    type,
    payload: JSON.stringify({ reset_time: '2026-05-03T15:00:00Z', ...extra }),
    createdAt: new Date().toISOString(),
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useAutoPilotEvents', () => {
  it('connects to the backend SSE endpoint on mount', () => {
    renderHook(() => useAutoPilotEvents());

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toContain('/api/execute/queue/events');
  });

  it('returns connected: false initially (before onopen fires)', () => {
    const { result } = renderHook(() => useAutoPilotEvents());
    expect(result.current.connected).toBe(false);
  });

  it('sets connected: true when onopen fires', async () => {
    const { result } = renderHook(() => useAutoPilotEvents());

    act(() => {
      MockEventSource.instances[0].onopen?.();
    });

    expect(result.current.connected).toBe(true);
  });

  it('fires toast.warning for auto_paused event', async () => {
    renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    act(() => {
      es.dispatchTypedEvent('auto_paused', makeEventPayload('auto_paused'));
    });

    expect(mockToast.warning).toHaveBeenCalledTimes(1);
    expect(mockToast.warning).toHaveBeenCalledWith(
      expect.stringMatching(/AutoPilot Paused/i),
      expect.stringMatching(/token exhaustion/i),
    );
  });

  it('fires toast.success for auto_resume_fired event', async () => {
    renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    act(() => {
      es.dispatchTypedEvent('auto_resume_fired', makeEventPayload('auto_resume_fired'));
    });

    expect(mockToast.success).toHaveBeenCalledTimes(1);
    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringMatching(/AutoPilot Resumed/i),
      expect.any(String),
    );
  });

  it('fires toast.error for auto_resume_circuit_breaker_tripped event', async () => {
    renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    act(() => {
      es.dispatchTypedEvent(
        'auto_resume_circuit_breaker_tripped',
        makeEventPayload('auto_resume_circuit_breaker_tripped'),
      );
    });

    expect(mockToast.error).toHaveBeenCalledTimes(1);
    expect(mockToast.error).toHaveBeenCalledWith(
      expect.stringMatching(/Auto-Resume Disabled/i),
      expect.stringMatching(/consecutive failures/i),
    );
  });

  it('fires toast.warning for crash_recovery_detected event', async () => {
    renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    act(() => {
      es.dispatchTypedEvent(
        'crash_recovery_detected',
        makeEventPayload('crash_recovery_detected'),
      );
    });

    expect(mockToast.warning).toHaveBeenCalledTimes(1);
    expect(mockToast.warning).toHaveBeenCalledWith(
      expect.stringMatching(/AutoPilot Recovered/i),
      expect.any(String),
    );
  });

  it('does not fire toast for unlisted event types', async () => {
    renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    act(() => {
      es.dispatchTypedEvent('task_started', makeEventPayload('task_started'));
    });

    expect(mockToast.success).not.toHaveBeenCalled();
    expect(mockToast.warning).not.toHaveBeenCalled();
    expect(mockToast.error).not.toHaveBeenCalled();
  });

  it('sets connected: false and closes EventSource on error', async () => {
    const { result } = renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    act(() => {
      es.onopen?.();
    });
    expect(result.current.connected).toBe(true);

    act(() => {
      es.onerror?.();
    });
    expect(result.current.connected).toBe(false);
  });

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    expect(es.closed).toBe(false);
    unmount();
    expect(es.closed).toBe(true);
  });

  it('does not fire toast after unmount', async () => {
    const { unmount } = renderHook(() => useAutoPilotEvents());
    const es = MockEventSource.instances[0];

    unmount();

    // Dispatching after unmount should not cause toast calls
    act(() => {
      es.dispatchTypedEvent('auto_paused', makeEventPayload('auto_paused'));
    });

    expect(mockToast.warning).not.toHaveBeenCalled();
  });
});
