'use client';

/**
 * useAutoPilotEvents — Subscribes to the global AutoPilot SSE event stream.
 *
 * Connects to GET /api/execute/queue/events (direct to backend — Next.js proxy
 * cannot stream SSE). Fires toast notifications for lifecycle events that affect
 * the user's awareness (pause, resume, circuit-breaker, crash recovery).
 *
 * EventSource reconnects natively on disconnect; we only clean up on unmount.
 */

import { useEffect, useRef, useState } from 'react';
import { useToast } from '@/components/ui/toast';

// Direct backend URL — Next.js proxy can't stream SSE responses.
const BACKEND_EVENTS_URL = 'http://localhost:8401/api/execute/queue/events';

/** Shape of the data payload emitted by each SSE event. */
interface QueueEventData {
  id: string;
  queueId: string;
  type: string;
  payload: string; // JSON string
  createdAt: string;
}

function parsePayload(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

function formatResetTime(isoString?: string): string {
  if (!isoString) return 'later';
  try {
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return 'later';
  }
}

export function useAutoPilotEvents(): { connected: boolean } {
  const toast = useToast();
  const [connected, setConnected] = useState(false);
  // Stable ref to avoid stale-closure re-subscribes when toast identity changes.
  const toastRef = useRef(toast);
  useEffect(() => {
    toastRef.current = toast;
  });

  useEffect(() => {
    let es: EventSource | null = null;
    let unmounted = false;

    function connect() {
      if (unmounted) return;

      es = new EventSource(BACKEND_EVENTS_URL);

      es.onopen = () => {
        if (!unmounted) setConnected(true);
      };

      // Handle typed events
      const handleEvent = (eventType: string, event: Event) => {
        if (unmounted) return;
        const raw = (event as MessageEvent).data ?? '{}';
        let eventData: QueueEventData | null = null;
        try {
          eventData = JSON.parse(raw) as QueueEventData;
        } catch {
          // Malformed event — ignore
          return;
        }

        const payload = parsePayload(eventData.payload ?? '{}');

        switch (eventType) {
          case 'auto_paused': {
            const resetTime = formatResetTime(payload.reset_time as string | undefined);
            toastRef.current.warning(
              'AutoPilot Paused',
              `Token exhaustion detected. Auto-resumes at ${resetTime}.`,
            );
            break;
          }
          case 'auto_resume_fired':
            toastRef.current.success(
              'AutoPilot Resumed',
              'AutoPilot auto-resumed after token reset.',
            );
            break;
          case 'auto_resume_circuit_breaker_tripped':
            toastRef.current.error(
              'Auto-Resume Disabled',
              'Too many consecutive failures. Resume manually.',
            );
            break;
          case 'crash_recovery_detected':
            toastRef.current.warning(
              'AutoPilot Recovered',
              'AutoPilot recovered from a backend crash. Review and resume.',
            );
            break;
          default:
            // Other event types (task_started, task_completed, etc.) — no toast.
            break;
        }
      };

      const SUBSCRIBED_EVENTS = [
        'auto_paused',
        'auto_resume_fired',
        'auto_resume_circuit_breaker_tripped',
        'crash_recovery_detected',
      ] as const;

      for (const eventType of SUBSCRIBED_EVENTS) {
        es.addEventListener(eventType, (e) => handleEvent(eventType, e));
      }

      es.onerror = () => {
        if (unmounted) return;
        setConnected(false);
        // EventSource will attempt its own native reconnect; we don't need to
        // manually reconnect — the browser handles exponential back-off.
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (es) {
        es.close();
        es = null;
      }
      setConnected(false);
    };
  }, []); // empty deps — connect once on mount, clean up on unmount

  return { connected };
}
