'use client';

/**
 * Keyboard Shortcuts Help Modal
 * Displays all available keyboard shortcuts organized by category
 */

import { X, Keyboard } from 'lucide-react';
import { SHORTCUTS, SHORTCUT_CATEGORIES, formatShortcut, type ShortcutDefinition } from '@/hooks/use-keyboard-shortcuts';
import { cn } from '@/lib/utils';

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

export function KeyboardShortcutsHelp({ isOpen, onClose }: KeyboardShortcutsHelpProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-2xl mx-4 max-h-[80vh] bg-zinc-900 rounded-xl border border-zinc-800 shadow-xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-3">
            <Keyboard className="w-5 h-5 text-cyan-400" />
            <h2 className="text-lg font-semibold">Keyboard Shortcuts</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {Object.entries(SHORTCUT_CATEGORIES).map(([categoryKey, category]) => (
              <div key={categoryKey} className="space-y-3">
                <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
                  {category.label}
                </h3>
                <div className="space-y-2">
                  {category.shortcuts.map((shortcutKey) => {
                    const shortcut = SHORTCUTS[shortcutKey as keyof typeof SHORTCUTS];
                    if (!shortcut) return null;

                    return (
                      <div
                        key={shortcutKey}
                        className="flex items-center justify-between py-1.5"
                      >
                        <span className="text-sm text-zinc-300">
                          {shortcut.description}
                        </span>
                        <ShortcutBadge shortcut={shortcut} />
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Tips */}
          <div className="mt-8 p-4 bg-zinc-800/50 rounded-lg">
            <h4 className="text-sm font-medium text-zinc-300 mb-2">Tips</h4>
            <ul className="text-sm text-zinc-400 space-y-1">
              <li>• Press <ShortcutBadge shortcut={SHORTCUTS.HELP} size="sm" /> anytime to show this help</li>
              <li>• Use <ShortcutBadge shortcut={SHORTCUTS.ESCAPE} size="sm" /> to close any modal or dialog</li>
              <li>• Shortcuts are disabled when typing in text fields</li>
            </ul>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-zinc-800 shrink-0">
          <p className="text-xs text-zinc-500 text-center">
            Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-300">Esc</kbd> to close
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Shortcut Badge Component
 */
interface ShortcutBadgeProps {
  shortcut: ShortcutDefinition;
  size?: 'sm' | 'md';
  className?: string;
}

export function ShortcutBadge({ shortcut, size = 'md', className }: ShortcutBadgeProps) {
  const formatted = formatShortcut(shortcut);
  const keys = formatted.split(/(?=[+⌘⌥⇧])/).filter(Boolean);

  return (
    <span className={cn('inline-flex items-center gap-0.5', className)}>
      {keys.map((key, i) => (
        <kbd
          key={i}
          className={cn(
            'inline-flex items-center justify-center rounded font-mono font-medium',
            'bg-zinc-800 text-zinc-300 border border-zinc-700',
            size === 'sm' ? 'px-1 py-0.5 text-[10px] min-w-[18px]' : 'px-1.5 py-0.5 text-xs min-w-[22px]'
          )}
        >
          {key.replace('+', '')}
        </kbd>
      ))}
    </span>
  );
}
