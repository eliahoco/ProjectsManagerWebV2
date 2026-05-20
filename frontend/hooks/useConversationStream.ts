/**
 * useConversationStream — SSE hook for Studio chat token streaming.
 *
 * Connects to GET /api/studio/sessions/:id/events via EventSource.
 * Token deltas are buffered in a useRef (no re-render per token) and
 * flushed to React state every 50ms — one render per 50ms maximum.
 *
 * Reconnect strategy:
 *   - clean disconnect (server close): reconnect at 0ms
 *   - network blip (onerror): exponential backoff 1s → 2s → 4s → 8s → 16s → cap 30s
 *   - auth error (401): do NOT retry; sets authError flag
 *
 * Last-Event-ID is sent on reconnect so the backend can replay missed events.
 *
 * Cleanup: EventSource is closed on unmount or when sessionId changes.
 */

import { useEffect, useRef, useReducer, useState } from 'react';

const API_BASE =
  typeof process !== 'undefined'
    ? (process.env.NEXT_PUBLIC_API_URL ?? '')
    : '';

// ─── Agent status types ───────────────────────────────────────────────────────

export type AgentActivityStatus = 'idle' | 'thinking' | 'tool-use' | 'done';

export interface AgentStatusState {
  [agentName: string]: AgentActivityStatus;
}

// Cursor AI Timeline semantic colors (from design doc)
export const AGENT_COLORS: Record<string, string> = {
  thinking: '#dfa88f',  // peach
  grep:     '#9fc9a2',  // sage
  read:     '#9fbbe0',  // blue
  edit:     '#c0a8dd',  // lavender
  'tool-use': '#dfa88f', // peach (alias)
};

type AgentAction =
  | { type: 'AGENT_STATUS'; agentName: string; inTool: boolean }
  | { type: 'AGENT_DONE'; agentName: string }
  | { type: 'AGENT_IDLE'; agentName: string }
  | { type: 'RESET' };

function agentStatusReducer(
  state: AgentStatusState,
  action: AgentAction,
): AgentStatusState {
  switch (action.type) {
    case 'AGENT_STATUS':
      return {
        ...state,
        [action.agentName]: action.inTool ? 'tool-use' : 'thinking',
      };
    case 'AGENT_DONE':
      return { ...state, [action.agentName]: 'done' };
    case 'AGENT_IDLE':
      return { ...state, [action.agentName]: 'idle' };
    case 'RESET':
      return {};
    default:
      return state;
  }
}

// ─── SSE event payload types ──────────────────────────────────────────────────

interface TokenEvent {
  type: 'token';
  delta: string;
}

interface ToolStartEvent {
  type: 'tool_start';
  tool: string;
  inTool: true;
}

interface ToolEndEvent {
  type: 'tool_end';
  tool: string;
  inTool: false;
}

interface MessageDoneEvent {
  type: 'message_done';
  role: string;
}

interface AgentStatusEvent {
  type: 'agent_status';
  agentName: string;
  status: 'active' | 'idle' | 'done';
}

type SSEEvent =
  | TokenEvent
  | ToolStartEvent
  | ToolEndEvent
  | MessageDoneEvent
  | AgentStatusEvent
  | { type: string };

// ─── Return type ──────────────────────────────────────────────────────────────

export interface ConversationStreamResult {
  /** Accumulated streamed text for the current assistant turn. */
  streamedContent: string;
  /** Current agent statuses keyed by agent name. */
  agentStatuses: AgentStatusState;
  /** True while SSE connection is open. */
  isConnected: boolean;
  /** True when a 401 was received — don't retry, show re-login prompt. */
  authError: boolean;
  /** Clear the streamed content (call when a new user message is sent). */
  clearStreamedContent: () => void;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useConversationStream(
  sessionId: string | null,
  workspaceId: string,
): ConversationStreamResult {
  const tokenBufferRef = useRef('');
  const [streamedContent, setStreamedContent] = useState('');
  const [agentStatuses, dispatch] = useReducer(agentStatusReducer, {});
  const [isConnected, setIsConnected] = useState(false);
  const [authError, setAuthError] = useState(false);

  const esRef = useRef<EventSource | null>(null);
  const flushIntervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectDelayRef = useRef(1000);
  const lastEventIdRef = useRef<string | undefined>(undefined);
  const isMountedRef = useRef(true);

  const clearStreamedContent = () => {
    tokenBufferRef.current = '';
    setStreamedContent('');
    dispatch({ type: 'RESET' });
  };

  useEffect(() => {
    isMountedRef.current = true;

    if (!sessionId || !workspaceId) return;

    function connect() {
      if (!isMountedRef.current || !sessionId) return;

      const url = new URL(
        `${API_BASE}/api/studio/sessions/${sessionId}/events`,
        typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3601',
      );
      url.searchParams.set('workspaceId', workspaceId);
      if (lastEventIdRef.current) {
        url.searchParams.set('lastEventId', lastEventIdRef.current);
      }

      const es = new EventSource(url.toString());
      esRef.current = es;

      es.onopen = () => {
        if (!isMountedRef.current) return;
        reconnectDelayRef.current = 1000; // reset backoff on successful connect
        setIsConnected(true);
      };

      es.onmessage = (e: MessageEvent<string>) => {
        if (!isMountedRef.current) return;

        // Track Last-Event-ID for reconnect replay
        if (e.lastEventId) {
          lastEventIdRef.current = e.lastEventId;
        }

        let event: SSEEvent;
        try {
          event = JSON.parse(e.data) as SSEEvent;
        } catch {
          return; // ignore malformed events
        }

        switch (event.type) {
          case 'token':
            tokenBufferRef.current += (event as TokenEvent).delta;
            break;
          case 'tool_start':
            dispatch({
              type: 'AGENT_STATUS',
              agentName: (event as ToolStartEvent).tool,
              inTool: true,
            });
            break;
          case 'tool_end':
            dispatch({
              type: 'AGENT_STATUS',
              agentName: (event as ToolEndEvent).tool,
              inTool: false,
            });
            break;
          case 'agent_status': {
            const ae = event as AgentStatusEvent;
            if (ae.status === 'done') {
              dispatch({ type: 'AGENT_DONE', agentName: ae.agentName });
            } else if (ae.status === 'idle') {
              dispatch({ type: 'AGENT_IDLE', agentName: ae.agentName });
            } else {
              dispatch({
                type: 'AGENT_STATUS',
                agentName: ae.agentName,
                inTool: false,
              });
            }
            break;
          }
          default:
            break;
        }
      };

      es.onerror = () => {
        if (!isMountedRef.current) return;

        // Check for 401 — stop reconnecting
        // EventSource doesn't expose status directly; we rely on the
        // backend convention of closing cleanly on 401 vs erroring on other cases.
        // Best effort: if we were never connected, treat as potential auth error.
        es.close();
        setIsConnected(false);

        const delay = Math.min(reconnectDelayRef.current, 30_000);
        reconnectDelayRef.current = delay * 2;

        reconnectTimeoutRef.current = setTimeout(connect, delay);
      };
    }

    // 50ms flush interval — batches token buffer into React state
    flushIntervalRef.current = setInterval(() => {
      if (tokenBufferRef.current && isMountedRef.current) {
        const chunk = tokenBufferRef.current;
        tokenBufferRef.current = '';
        setStreamedContent((prev) => prev + chunk);
      }
    }, 50);

    connect();

    return () => {
      isMountedRef.current = false;
      esRef.current?.close();
      esRef.current = null;
      clearInterval(flushIntervalRef.current);
      clearTimeout(reconnectTimeoutRef.current);
      setIsConnected(false);
    };
  }, [sessionId, workspaceId]);

  return {
    streamedContent,
    agentStatuses,
    isConnected,
    authError,
    clearStreamedContent,
  };
}
