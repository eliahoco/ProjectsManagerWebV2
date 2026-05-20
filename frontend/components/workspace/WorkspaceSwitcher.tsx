'use client';

/**
 * WorkspaceSwitcher — dropdown stub for workspace selection.
 *
 * Phase 1: single tenant, single workspace ("default"). The dropdown
 * shows just the current workspace name. Switching navigates to
 * /workspace/[newId]/studio on selection.
 *
 * Phase 2: populated from GET /api/workspaces.
 */

import { useRouter } from 'next/navigation';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface WorkspaceSwitcherProps {
  workspaceId: string;
  className?: string;
}

export function WorkspaceSwitcher({ workspaceId, className }: WorkspaceSwitcherProps) {
  const router = useRouter();

  // Phase 1: single workspace stub
  const workspaces = [{ id: 'default', name: 'PMv2 Production' }];
  const current = workspaces.find((w) => w.id === workspaceId) ?? workspaces[0];

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const newId = e.target.value;
    if (newId !== workspaceId) {
      router.replace(`/workspace/${newId}/studio`);
    }
  }

  return (
    <div className={cn('relative flex items-center', className)}>
      <select
        value={workspaceId}
        onChange={handleChange}
        aria-label="Switch workspace"
        className={cn(
          'appearance-none bg-transparent border border-zinc-700 rounded-lg',
          'pl-3 pr-8 py-1.5 text-sm font-medium text-zinc-200',
          'focus:outline-none focus:border-cyan-500 cursor-pointer',
          'hover:border-zinc-500 transition-colors',
        )}
      >
        {workspaces.map((ws) => (
          <option key={ws.id} value={ws.id}>
            {ws.name}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 w-3.5 h-3.5 text-zinc-400 pointer-events-none" />
    </div>
  );
}
