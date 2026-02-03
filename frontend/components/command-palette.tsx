'use client';

/**
 * Command Palette - Global search and actions (Cmd+K)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import {
  Search,
  Folder,
  Play,
  Square,
  Terminal,
  Settings,
  Moon,
  Sun,
  Keyboard,
  X,
  ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTheme } from '@/components/theme-provider';
import { SHORTCUTS } from '@/hooks/use-keyboard-shortcuts';

interface Project {
  id: string;
  name: string;
  path: string;
  status: string;
  isRunning?: boolean;
}

interface CommandItem {
  id: string;
  icon: typeof Search;
  label: string;
  description?: string;
  shortcut?: string;
  action: () => void;
  category: 'navigation' | 'action' | 'project';
}

export function CommandPalette() {
  const router = useRouter();
  const { toggleTheme, resolvedTheme } = useTheme();
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch projects for search
  useEffect(() => {
    if (isOpen) {
      fetch('/api/projects')
        .then((res) => res.json())
        .then((data) => {
          if (data.success) {
            setProjects(data.data.projects);
          }
        })
        .catch(console.error);
    }
  }, [isOpen]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Open command palette with Cmd+K or Ctrl+K
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(true);
        setShowShortcuts(false);
      }

      // Show shortcuts with ?
      if (e.key === '?' && e.shiftKey && !isOpen) {
        e.preventDefault();
        setIsOpen(true);
        setShowShortcuts(true);
      }

      // Toggle theme with Ctrl+T
      if ((e.metaKey || e.ctrlKey) && e.key === 't') {
        e.preventDefault();
        toggleTheme();
      }

      // Close with Escape
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, toggleTheme]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
    if (!isOpen) {
      setSearch('');
      setSelectedIndex(0);
      setShowShortcuts(false);
    }
  }, [isOpen]);

  // Build command items
  const commands: CommandItem[] = [
    {
      id: 'nav-dashboard',
      icon: Folder,
      label: 'Go to Dashboard',
      shortcut: 'Alt+H',
      action: () => {
        router.push('/');
        setIsOpen(false);
      },
      category: 'navigation',
    },
    {
      id: 'nav-projects',
      icon: Folder,
      label: 'Go to Projects',
      shortcut: 'Alt+P',
      action: () => {
        router.push('/projects');
        setIsOpen(false);
      },
      category: 'navigation',
    },
    {
      id: 'nav-settings',
      icon: Settings,
      label: 'Go to Settings',
      shortcut: 'Alt+S',
      action: () => {
        router.push('/settings');
        setIsOpen(false);
      },
      category: 'navigation',
    },
    {
      id: 'action-theme',
      icon: resolvedTheme === 'dark' ? Sun : Moon,
      label: `Switch to ${resolvedTheme === 'dark' ? 'Light' : 'Dark'} Mode`,
      shortcut: 'Ctrl+T',
      action: () => {
        toggleTheme();
        setIsOpen(false);
      },
      category: 'action',
    },
    {
      id: 'action-shortcuts',
      icon: Keyboard,
      label: 'Show Keyboard Shortcuts',
      shortcut: 'Shift+?',
      action: () => {
        setShowShortcuts(true);
      },
      category: 'action',
    },
  ];

  // Add project commands
  const projectCommands: CommandItem[] = projects.map((project) => ({
    id: `project-${project.id}`,
    icon: Folder,
    label: project.name,
    description: project.path,
    action: () => {
      router.push(`/projects/${project.id}`);
      setIsOpen(false);
    },
    category: 'project',
  }));

  // Filter items based on search
  const allItems = [...commands, ...projectCommands];
  const filteredItems = search
    ? allItems.filter(
        (item) =>
          item.label.toLowerCase().includes(search.toLowerCase()) ||
          item.description?.toLowerCase().includes(search.toLowerCase())
      )
    : allItems;

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, filteredItems.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter' && filteredItems[selectedIndex]) {
      e.preventDefault();
      filteredItems[selectedIndex].action();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => setIsOpen(false)}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl overflow-hidden">
        {showShortcuts ? (
          // Shortcuts view
          <div className="p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-medium text-white">Keyboard Shortcuts</h3>
              <button
                onClick={() => setShowShortcuts(false)}
                className="text-zinc-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3">
              {Object.entries(SHORTCUTS).map(([key, shortcut]) => (
                <div key={key} className="flex items-center justify-between py-2 border-b border-zinc-800">
                  <span className="text-zinc-300">{shortcut.description}</span>
                  <kbd className="px-2 py-1 bg-zinc-800 rounded text-xs text-zinc-400 font-mono">
                    {'ctrl' in shortcut && shortcut.ctrl && 'Ctrl+'}
                    {'alt' in shortcut && shortcut.alt && 'Alt+'}
                    {'shift' in shortcut && shortcut.shift && 'Shift+'}
                    {shortcut.key}
                  </kbd>
                </div>
              ))}
            </div>
          </div>
        ) : (
          // Search view
          <>
            {/* Search input */}
            <div className="flex items-center gap-3 p-4 border-b border-zinc-800">
              <Search className="h-5 w-5 text-zinc-500" />
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setSelectedIndex(0);
                }}
                onKeyDown={handleKeyDown}
                placeholder="Search projects, commands..."
                className="flex-1 bg-transparent text-white placeholder:text-zinc-500 focus:outline-none"
              />
              <kbd className="px-2 py-1 bg-zinc-800 rounded text-xs text-zinc-500">
                ESC
              </kbd>
            </div>

            {/* Results */}
            <div className="max-h-80 overflow-y-auto">
              {filteredItems.length === 0 ? (
                <div className="p-4 text-center text-zinc-500">No results found</div>
              ) : (
                <div className="py-2">
                  {filteredItems.map((item, index) => (
                    <button
                      key={item.id}
                      onClick={item.action}
                      className={cn(
                        'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors',
                        index === selectedIndex
                          ? 'bg-cyan-500/20 text-white'
                          : 'text-zinc-300 hover:bg-zinc-800'
                      )}
                    >
                      <item.icon className="h-4 w-4 text-zinc-500" />
                      <div className="flex-1 min-w-0">
                        <p className="truncate">{item.label}</p>
                        {item.description && (
                          <p className="text-xs text-zinc-500 truncate">{item.description}</p>
                        )}
                      </div>
                      {item.shortcut && (
                        <kbd className="px-2 py-0.5 bg-zinc-800 rounded text-xs text-zinc-500">
                          {item.shortcut}
                        </kbd>
                      )}
                      <ArrowRight className="h-4 w-4 text-zinc-600" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between p-2 border-t border-zinc-800 text-xs text-zinc-500">
              <span>
                <kbd className="px-1 bg-zinc-800 rounded">↑↓</kbd> navigate
                <kbd className="px-1 bg-zinc-800 rounded ml-2">↵</kbd> select
              </span>
              <span>
                <kbd className="px-1 bg-zinc-800 rounded">?</kbd> shortcuts
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
