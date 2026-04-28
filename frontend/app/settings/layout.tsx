'use client';

/**
 * Settings Layout - Provides sub-navigation for settings pages
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Settings, Bot, Workflow, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

const settingsNav = [
  { name: 'General', href: '/settings', icon: Settings },
  { name: 'AI Agents', href: '/settings/agents', icon: Bot },
  { name: 'AI Skills', href: '/settings/skills', icon: Sparkles },
  { name: 'Pipeline', href: '/settings/pipeline', icon: Workflow },
];

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="flex h-full">
      {/* Settings Sub-Navigation */}
      <div className="w-56 border-r border-zinc-800 bg-zinc-900/50 p-4 space-y-1 flex-shrink-0">
        <h2 className="text-xs font-semibold uppercase text-zinc-500 px-3 mb-3 tracking-wider">
          Settings
        </h2>
        {settingsNav.map((item) => {
          const isActive =
            item.href === '/settings'
              ? pathname === '/settings'
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-zinc-800 text-cyan-400'
                  : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          );
        })}
      </div>

      {/* Settings Content */}
      <div className="flex-1 overflow-auto">
        {children}
      </div>
    </div>
  );
}
