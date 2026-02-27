'use client';

/**
 * AI Agent Profiles Settings Page
 * Manage registered AI agents - view, scan, toggle active/inactive
 */

import { useState } from 'react';
import {
  Bot,
  Scan,
  FolderSearch,
  Power,
  PowerOff,
  Cpu,
  Tag,
  FileCode,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/toast';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useAgents, useScanAgents, useToggleAgent } from '@/hooks/useAgents';
import type { AgentProfile } from '@/hooks/useAgents';

export default function AgentProfilesPage() {
  const toast = useToast();
  const { data: agents, isLoading, error } = useAgents();
  const scanAgents = useScanAgents();
  const toggleAgent = useToggleAgent();
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  const handleScan = async () => {
    try {
      const result = await scanAgents.mutateAsync();
      toast.success(
        'Agent Scan Complete',
        `Found ${result.length} agent${result.length !== 1 ? 's' : ''}`
      );
    } catch (err) {
      toast.error('Scan Failed', err instanceof Error ? err.message : 'Could not scan agents directory');
    }
  };

  const handleToggle = async (agentId: string) => {
    try {
      const updated = await toggleAgent.mutateAsync(agentId);
      toast.success(
        updated.isActive ? 'Agent Activated' : 'Agent Deactivated',
        `${updated.displayName} is now ${updated.isActive ? 'active' : 'inactive'}`
      );
    } catch (err) {
      toast.error('Toggle Failed', err instanceof Error ? err.message : 'Could not toggle agent');
    }
  };

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Bot className="h-7 w-7 text-cyan-500" />
            AI Agent Profiles
          </h1>
          <p className="text-zinc-400 mt-1">
            Manage registered AI agents and their capabilities
          </p>
        </div>
        <Button
          variant="default"
          onClick={handleScan}
          loading={scanAgents.isPending}
        >
          <Scan className="h-4 w-4" />
          Scan Agents
        </Button>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-3">
              <div className="flex items-center gap-3">
                <Skeleton className="h-10 w-10 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-5 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-5 w-16 rounded" />
                <Skeleton className="h-5 w-20 rounded" />
                <Skeleton className="h-5 w-14 rounded" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
          <p className="font-medium">Failed to load agents</p>
          <p className="text-sm mt-1">{error instanceof Error ? error.message : 'Unknown error'}</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && agents && agents.length === 0 && (
        <div className="text-center py-16 bg-zinc-900 border border-zinc-800 rounded-lg">
          <FolderSearch className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-zinc-300">No agents registered</h3>
          <p className="text-zinc-500 mt-2 max-w-md mx-auto">
            Click &quot;Scan Agents&quot; to auto-discover agents from ~/.claude/agents/ or register them manually.
          </p>
          <Button
            variant="default"
            className="mt-6"
            onClick={handleScan}
            loading={scanAgents.isPending}
          >
            <Scan className="h-4 w-4" />
            Scan for Agents
          </Button>
        </div>
      )}

      {/* Agent Cards Grid */}
      {!isLoading && agents && agents.length > 0 && (
        <>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-400">
              {agents.length} agent{agents.length !== 1 ? 's' : ''} registered
              <span className="text-zinc-600 mx-1.5">&middot;</span>
              {agents.filter((a) => a.isActive).length} active
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
            {agents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                expanded={expandedAgent === agent.id}
                onToggleExpand={() =>
                  setExpandedAgent(expandedAgent === agent.id ? null : agent.id)
                }
                onToggleActive={() => handleToggle(agent.id)}
                isToggling={toggleAgent.isPending}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ============================================
// Agent Card Component
// ============================================

function AgentCard({
  agent,
  expanded,
  onToggleExpand,
  onToggleActive,
  isToggling,
}: {
  agent: AgentProfile;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleActive: () => void;
  isToggling: boolean;
}) {
  const capabilities = agent.capabilities || [];
  const affinity = agent.issueTypeAffinity || [];
  const patterns = agent.projectPatterns || [];

  return (
    <div
      className={cn(
        'bg-zinc-900 border rounded-lg transition-colors',
        agent.isActive ? 'border-zinc-800' : 'border-zinc-800/50 opacity-60'
      )}
    >
      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={cn(
                'p-2 rounded-lg flex-shrink-0',
                agent.isActive ? 'bg-cyan-500/10' : 'bg-zinc-800'
              )}
            >
              <Cpu
                className={cn(
                  'h-5 w-5',
                  agent.isActive ? 'text-cyan-400' : 'text-zinc-500'
                )}
              />
            </div>
            <div className="min-w-0">
              <h3 className="text-white font-medium truncate">{agent.displayName}</h3>
              <p className="text-xs text-zinc-500 font-mono truncate">{agent.name}</p>
            </div>
          </div>

          {/* Active toggle */}
          <button
            onClick={onToggleActive}
            disabled={isToggling}
            className={cn(
              'p-1.5 rounded-md transition-colors flex-shrink-0',
              agent.isActive
                ? 'text-green-400 hover:bg-green-500/10'
                : 'text-zinc-500 hover:bg-zinc-800'
            )}
            title={agent.isActive ? 'Deactivate agent' : 'Activate agent'}
          >
            {agent.isActive ? (
              <Power className="h-4 w-4" />
            ) : (
              <PowerOff className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Description */}
        {agent.description && (
          <p className="text-sm text-zinc-400 mt-2 line-clamp-2">{agent.description}</p>
        )}

        {/* Capabilities tags */}
        {capabilities.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {capabilities.slice(0, expanded ? capabilities.length : 5).map((cap) => (
              <Badge key={cap} variant="secondary" className="text-[10px] px-1.5 py-0">
                {cap}
              </Badge>
            ))}
            {!expanded && capabilities.length > 5 && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                +{capabilities.length - 5}
              </Badge>
            )}
          </div>
        )}

        {/* Issue Type Affinity */}
        {affinity.length > 0 && (
          <div className="flex items-center gap-1.5 mt-2">
            <Tag className="h-3 w-3 text-zinc-500 flex-shrink-0" />
            <div className="flex flex-wrap gap-1">
              {affinity.map((type) => (
                <Badge
                  key={type}
                  variant="outline"
                  className={cn(
                    'text-[10px] px-1.5 py-0',
                    type === 'BUG' && 'border-red-600/40 text-red-400',
                    type === 'TASK' && 'border-blue-600/40 text-blue-400',
                    type === 'STORY' && 'border-green-600/40 text-green-400',
                    type === 'SUBTASK' && 'border-purple-600/40 text-purple-400'
                  )}
                >
                  {type}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Status badge */}
        <div className="flex items-center justify-between mt-3">
          <Badge
            variant={agent.isActive ? 'success' : 'secondary'}
            className="text-[10px]"
          >
            {agent.isActive ? 'Active' : 'Inactive'}
          </Badge>

          <button
            onClick={onToggleExpand}
            className="text-zinc-500 hover:text-zinc-300 transition-colors p-1"
          >
            {expanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="border-t border-zinc-800 px-5 py-4 space-y-3 text-sm">
          {/* Agent Path */}
          <div>
            <span className="text-zinc-500 text-xs uppercase tracking-wide">Agent Path</span>
            <p className="text-zinc-300 font-mono text-xs mt-1 break-all">
              {agent.agentPath || 'Not set'}
            </p>
          </div>

          {/* File Patterns */}
          {patterns.length > 0 && (
            <div>
              <span className="text-zinc-500 text-xs uppercase tracking-wide flex items-center gap-1.5">
                <FileCode className="h-3 w-3" />
                File Patterns
              </span>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {patterns.map((pattern) => (
                  <code
                    key={pattern}
                    className="text-[10px] px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-300 font-mono"
                  >
                    {pattern}
                  </code>
                ))}
              </div>
            </div>
          )}

          {/* Priority */}
          <div className="flex justify-between">
            <span className="text-zinc-500 text-xs uppercase tracking-wide">Priority</span>
            <span className="text-zinc-300">{agent.priority}</span>
          </div>

          {/* All capabilities when expanded */}
          {capabilities.length > 5 && (
            <div>
              <span className="text-zinc-500 text-xs uppercase tracking-wide">All Capabilities</span>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {capabilities.map((cap) => (
                  <Badge key={cap} variant="secondary" className="text-[10px] px-1.5 py-0">
                    {cap}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
