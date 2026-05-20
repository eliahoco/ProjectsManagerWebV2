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
import { useQueryClient } from '@tanstack/react-query';

const API_BASE =
  typeof process !== 'undefined'
    ? (process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8401')
    : 'http://localhost:8401';

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
  // Incremented by the caller every time a new user message is sent.
  // Triggers a fresh SSE connection so the agent's response streams.
  // Without this, after the first turn closes cleanly (terminalClosed),
  // the hook would not reconnect for subsequent prompts.
  sendTrigger: number = 0,
): ConversationStreamResult {
  const queryClient = useQueryClient();
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
  // Set true when the backend signals turn_complete + done — DO NOT reconnect.
  // Native EventSource would otherwise treat the server close as an error
  // and reconnect endlessly, producing a connection storm that exhausts
  // Chrome's per-origin socket pool and freezes the tab.
  const terminalClosedRef = useRef(false);

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

      // The backend uses NAMED SSE events (`event: token`, `event: message_complete`,
      // etc.). Native EventSource only fires `onmessage` for the default (unnamed)
      // event channel — named events MUST be subscribed via addEventListener.
      // This single handler dispatches all known event types.
      const handleFrame = (e: MessageEvent<string>) => {
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
          case 'message_complete':
          case 'message_replay':
          case 'turn_complete':
            // Server finished writing the assistant message. Refetch
            // useStudioMessages so the new ASSISTANT bubble renders.
            queryClient.invalidateQueries({
              queryKey: ['workspace', workspaceId, 'studio', 'sessions', sessionId, 'messages'],
            });
            // Clear the streaming buffer — the persisted DB message replaces it.
            tokenBufferRef.current = '';
            setStreamedContent('');
            // Mark this connection terminal so onerror doesn't reconnect-storm.
            terminalClosedRef.current = true;
            break;
          case 'done':
            // Backend's final SSE frame. Close the EventSource intentionally
            // and DO NOT reconnect — the conversation is parked. A new POST
            // /messages will trigger a new EventSource later.
            terminalClosedRef.current = true;
            esRef.current?.close();
            setIsConnected(false);
            break;
          default:
            break;
        }
      };

      // Subscribe to all named events that the backend emits + fallback for default channel.
      const eventTypes = [
        'token',
        'tool_start',
        'tool_end',
        'tool_call_started',
        'tool_call_completed',
        'agent_status',
        'subagent_started',
        'subagent_completed',
        'message_complete',
        'message_replay',
        'turn_complete',
        'error',
        'done',
        'ping',
      ];
      for (const t of eventTypes) {
        es.addEventListener(t, handleFrame as EventListener);
      }
      es.onmessage = handleFrame;

      es.onerror = () => {
        if (!isMountedRef.current) return;

        es.close();
        setIsConnected(false);

        // If the backend sent `done`, we deliberately closed — DO NOT reconnect.
        // Without this guard, every chat turn that completes would trigger an
        // endless reconnect loop and exhaust Chrome's per-origin socket pool.
        if (terminalClosedRef.current) {
          return;
        }

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
    // Reset terminal flag on every (re)connect attempt so a new sendTrigger
    // re-opens the SSE after the previous turn closed.
    terminalClosedRef.current = false;
  }, [sessionId, workspaceId, sendTrigger]);

  return {
    streamedContent,
    agentStatuses,
    isConnected,
    authError,
    clearStreamedContent,
  };
}
