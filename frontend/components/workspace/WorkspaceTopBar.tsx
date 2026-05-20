'use client';

/**
 * WorkspaceTopBar — workspace switcher + Studio/Backlog/Crew Map tabs.
 *
 * Always visible above all workspace views. Rendered by WorkspaceTenantLayout.
 *
 *   ┌──────────────────────────────────────────────────────────┐
 *   │  [PMv2 Production ▾]   Studio | Backlog | Crew Map       │
 *   └──────────────────────────────────────────────────────────┘
 */

import { WorkspaceSwitcher } from './WorkspaceSwitcher';
import { WorkspaceNavTabs } from './WorkspaceNavTabs';

interface WorkspaceTopBarProps {
  workspaceId: string;
}

export function WorkspaceTopBar({ workspaceId }: WorkspaceTopBarProps) {
  return (
    <div className="flex-shrink-0 flex items-center justify-between gap-4 px-4 py-2.5 bg-zinc-900 border-b border-zinc-800">
      <WorkspaceSwitcher workspaceId={workspaceId} />
      <WorkspaceNavTabs workspaceId={workspaceId} />
    </div>
  );
}
