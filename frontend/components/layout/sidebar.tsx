'use client';

/**
 * Sidebar Navigation Component
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  FolderOpen,
  Plus,
  FolderInput,
  Package,
  Network,
  Github,
  Settings,
  Terminal,
  Search,
  Moon,
  Sun,
  Keyboard,
  Kanban,
  ClipboardCheck,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTheme } from '@/components/theme-provider';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'CodeBoard', href: '/codeboard', icon: Kanban },
  { name: 'QA Board', href: '/codeboard/qa', icon: ClipboardCheck },
  { name: 'Projects', href: '/projects', icon: FolderOpen },
  { name: 'Create', href: '/create', icon: Plus },
  { name: 'Import', href: '/import', icon: FolderInput },
  { name: 'Build', href: '/build', icon: Package },
  { name: 'Ports', href: '/ports', icon: Network },
  { name: 'GitHub', href: '/github', icon: Github },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { resolvedTheme, toggleTheme } = useTheme();

  const openCommandPalette = () => {
    // Dispatch keyboard event to trigger command palette
    const event = new KeyboardEvent('keydown', {
      key: 'k',
      ctrlKey: true,
      bubbles: true,
    });
    window.dispatchEvent(event);
  };

  return (
    <div className="flex h-full w-64 flex-col bg-zinc-900 border-r border-zinc-800">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 px-6 border-b border-zinc-800">
        <Terminal className="h-6 w-6 text-cyan-500" />
        <span className="text-lg font-semibold text-zinc-100">Projects Manager V2</span>
      </div>

      {/* Search Button */}
      <div className="px-3 pt-4">
        <button
          onClick={openCommandPalette}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <Search className="h-4 w-4" />
          <span className="text-sm">Search...</span>
          <kbd className="ml-auto px-1.5 py-0.5 text-xs bg-zinc-700 text-zinc-300 rounded">⌘K</kbd>
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href ||
            (item.href !== '/' && pathname.startsWith(item.href));

          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-zinc-800 text-cyan-500'
                  : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Theme Toggle & Shortcuts */}
      <div className="px-3 pb-2 space-y-1">
        <button
          onClick={toggleTheme}
          className="w-full flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
        >
          {resolvedTheme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
          {resolvedTheme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        </button>
        <button
          onClick={() => {
            const event = new KeyboardEvent('keydown', {
              key: '?',
              shiftKey: true,
              bubbles: true,
            });
            window.dispatchEvent(event);
          }}
          className="w-full flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
        >
          <Keyboard className="h-5 w-5" />
          Shortcuts
          <kbd className="ml-auto px-1.5 py-0.5 text-xs bg-zinc-700 text-zinc-300 rounded">?</kbd>
        </button>
      </div>

      {/* Footer */}
      <div className="border-t border-zinc-800 p-4">
        <div className="text-xs text-zinc-500">
          <p>Projects Manager Web</p>
          <p>v1.0.0</p>
        </div>
      </div>
    </div>
  );
}
