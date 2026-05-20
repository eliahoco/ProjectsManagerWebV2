'use client';

/**
 * AgentActivityPanel — stub panel showing active agent tasks.
 *
 * Cursor AI Timeline coloring per design doc:
 *   Thinking  → peach   #dfa88f
 *   Grep/tool → sage    #9fc9a2
 *   Read      → blue    #9fbbe0
 *   Edit      → lavender #c0a8dd
 *
 * Phase 0: static "No active agents" empty state.
 * Phase 1: driven by SSE agent_status events from useConversationStream.
 */

import { cn } from '@/lib/utils';
import type { AgentStatusState } from '@/hooks/useConversationStream';

// Cursor AI Timeline color map
const STATUS_COLORS: Record<string, string> = {
  thinking:  '#dfa88f',
  'tool-use': '#9fc9a2',
  read:      '#9fbbe0',
  edit:      '#c0a8dd',
  idle:      '#52525b',
  done:      '#27a644',
};

function getStatusColor(status: string): string {
  return STATUS_COLORS[status] ?? STATUS_COLORS.idle;
}

function statusLabel(status: string): string {
  switch (status) {
    case 'thinking':  return 'Thinking';
    case 'tool-use':  return 'Using tool';
    case 'idle':      return 'Idle';
    case 'done':      return 'Done';
    default:          return status;
  }
}

interface AgentRowProps {
  name: string;
  status: string;
}

function AgentRow({ name, status }: AgentRowProps) {
  const color = getStatusColor(status);
  const isPulsing = status === 'thinking' || status === 'tool-use';

  return (
    <div className="flex items-center gap-2 px-3 py-2 text-sm">
      <span
        className={cn('w-2.5 h-2.5 rounded-full flex-shrink-0', isPulsing && 'animate-agent-pulse')}
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span className="flex-1 text-zinc-300 truncate font-studio">{name}</span>
      <span className="text-xs font-medium" style={{ color }}>
        {statusLabel(status)}
      </span>
    </div>
  );
}

interface AgentActivityPanelProps {
  agentStatuses?: AgentStatusState;
  className?: string;
}

export function AgentActivityPanel({ agentStatuses = {}, className }: AgentActivityPanelProps) {
  const agents = Object.entries(agentStatuses);
  const hasAgents = agents.length > 0;

  return (
    <aside
      aria-label="Agent activity"
      className={cn(
        'flex flex-col border-l border-zinc-800 bg-zinc-900/50',
        className,
      )}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
        <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          Agents
        </h2>
        {hasAgents && (
          <span className="text-xs text-zinc-500">{agents.length} active</span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {hasAgents ? (
          <div className="divide-y divide-zinc-800/50">
            {agents.map(([name, status]) => (
              <AgentRow key={name} name={name} status={status} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full py-8 px-4 text-center">
            <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center mb-3">
              <span className="text-zinc-500 text-lg" aria-hidden="true">·</span>
            </div>
            <p className="text-sm text-zinc-500">No active agents</p>
            <p className="text-xs text-zinc-600 mt-1">
              Agents will appear here when Studio is processing
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
