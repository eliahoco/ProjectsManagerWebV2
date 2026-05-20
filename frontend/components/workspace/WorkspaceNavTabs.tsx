'use client';

/**
 * WorkspaceNavTabs — Studio | Backlog | Crew Map tab strip.
 *
 * Active tab is derived from pathname. Crew Map is marked as "deferred" in
 * the MVP but the tab still renders (leads to the placeholder page).
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { MessageSquare, ListTodo, GitBranch } from 'lucide-react';
import { cn } from '@/lib/utils';

interface NavTab {
  name: string;
  segment: string;
  icon: React.ElementType;
}

const TABS: NavTab[] = [
  { name: 'Studio', segment: 'studio', icon: MessageSquare },
  { name: 'Backlog', segment: 'backlog', icon: ListTodo },
  { name: 'Crew Map', segment: 'crew-map', icon: GitBranch },
];

interface WorkspaceNavTabsProps {
  workspaceId: string;
  className?: string;
}

export function WorkspaceNavTabs({ workspaceId, className }: WorkspaceNavTabsProps) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Workspace views"
      className={cn('flex items-center gap-1', className)}
    >
      {TABS.map((tab) => {
        const href = `/workspace/${workspaceId}/${tab.segment}`;
        const isActive = pathname.includes(`/${tab.segment}`);

        return (
          <Link
            key={tab.segment}
            href={href}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              isActive
                ? 'bg-zinc-800 text-zinc-100'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60',
            )}
            aria-current={isActive ? 'page' : undefined}
          >
            <tab.icon className="w-4 h-4" aria-hidden="true" />
            {tab.name}
          </Link>
        );
      })}
    </nav>
  );
}
