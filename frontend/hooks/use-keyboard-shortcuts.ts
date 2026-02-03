'use client';

/**
 * Keyboard Shortcuts Hook
 * Provides global and context-specific keyboard shortcuts
 */

import { useEffect, useCallback, useRef } from 'react';

export interface ShortcutHandler {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  handler: () => void;
  description: string;
}

export interface ShortcutDefinition {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  description: string;
}

const globalShortcuts: ShortcutHandler[] = [];

/**
 * Check if an element is an input field
 */
function isInputElement(element: HTMLElement): boolean {
  return (
    element.tagName === 'INPUT' ||
    element.tagName === 'TEXTAREA' ||
    element.tagName === 'SELECT' ||
    element.isContentEditable
  );
}

/**
 * Check if running on Mac - only available on client
 * Returns undefined during SSR to avoid hydration mismatch
 */
let isMacCached: boolean | null = null;

function getIsMac(): boolean {
  if (typeof window === 'undefined') {
    return false; // Default for SSR
  }
  if (isMacCached === null) {
    isMacCached = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
  }
  return isMacCached;
}

/**
 * Format a shortcut for display (e.g., "⌘K" or "Ctrl+K")
 * Always uses Mac symbols for consistency (avoids hydration mismatch)
 */
export function formatShortcut(shortcut: ShortcutDefinition): string {
  // Always use Mac-style symbols for cleaner display and to avoid hydration mismatch
  const parts: string[] = [];

  if (shortcut.ctrl || shortcut.meta) {
    parts.push('⌘');
  }
  if (shortcut.alt) {
    parts.push('⌥');
  }
  if (shortcut.shift) {
    parts.push('⇧');
  }

  // Format the key
  let keyDisplay = shortcut.key.toUpperCase();
  if (shortcut.key === 'Escape') keyDisplay = 'Esc';
  if (shortcut.key === 'ArrowUp') keyDisplay = '↑';
  if (shortcut.key === 'ArrowDown') keyDisplay = '↓';
  if (shortcut.key === 'ArrowLeft') keyDisplay = '←';
  if (shortcut.key === 'ArrowRight') keyDisplay = '→';
  if (shortcut.key === 'Enter') keyDisplay = '↵';
  if (shortcut.key === ' ') keyDisplay = 'Space';
  if (shortcut.key === '/') keyDisplay = '/';

  parts.push(keyDisplay);

  return parts.join('');
}

/**
 * Hook to get formatted shortcut that's safe for hydration
 * Returns Mac symbols which work universally
 */
export function useFormattedShortcut(shortcut: ShortcutDefinition): string {
  return formatShortcut(shortcut);
}

/**
 * Hook for managing keyboard shortcuts
 * @param customShortcuts - Context-specific shortcuts
 * @param options - Configuration options
 */
export function useKeyboardShortcuts(
  customShortcuts?: ShortcutHandler[],
  options?: {
    allowInInputs?: boolean;
    enabled?: boolean;
  }
) {
  const { allowInInputs = false, enabled = true } = options || {};

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled) return;

      // Don't trigger shortcuts when typing in inputs (unless allowed)
      const target = event.target as HTMLElement;
      if (!allowInInputs && isInputElement(target)) {
        // Always allow Escape in inputs
        if (event.key !== 'Escape') {
          return;
        }
      }

      const allShortcuts = [...globalShortcuts, ...(customShortcuts || [])];

      for (const shortcut of allShortcuts) {
        const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase();
        const ctrlMatch = shortcut.ctrl ? event.ctrlKey || event.metaKey : !event.ctrlKey && !event.metaKey;
        const shiftMatch = shortcut.shift ? event.shiftKey : !event.shiftKey;
        const altMatch = shortcut.alt ? event.altKey : !event.altKey;

        if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
          event.preventDefault();
          event.stopPropagation();
          shortcut.handler();
          return;
        }
      }
    },
    [customShortcuts, allowInInputs, enabled]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

/**
 * Hook for registering shortcuts that auto-cleanup on unmount
 */
export function useShortcut(
  shortcut: ShortcutDefinition,
  handler: () => void,
  deps: React.DependencyList = []
) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const fullShortcut: ShortcutHandler = {
      ...shortcut,
      handler: () => handlerRef.current(),
    };
    globalShortcuts.push(fullShortcut);
    return () => {
      const index = globalShortcuts.indexOf(fullShortcut);
      if (index > -1) {
        globalShortcuts.splice(index, 1);
      }
    };
  }, deps);
}

/**
 * Register a global shortcut (returns cleanup function)
 */
export function registerShortcut(shortcut: ShortcutHandler) {
  globalShortcuts.push(shortcut);
  return () => {
    const index = globalShortcuts.indexOf(shortcut);
    if (index > -1) {
      globalShortcuts.splice(index, 1);
    }
  };
}

/**
 * Get all registered shortcuts (for help display)
 */
export function getRegisteredShortcuts(): ShortcutHandler[] {
  return [...globalShortcuts];
}

// Pre-defined common shortcuts
export const SHORTCUTS = {
  // Global navigation
  SEARCH: { key: 'k', ctrl: true, description: 'Open search/command palette' },
  HELP: { key: '?', shift: true, description: 'Show keyboard shortcuts' },
  ESCAPE: { key: 'Escape', description: 'Close modal/dialog' },
  TOGGLE_THEME: { key: 't', ctrl: true, description: 'Toggle dark/light theme' },
  REFRESH: { key: 'r', ctrl: true, description: 'Refresh data' },

  // Navigation
  GO_HOME: { key: 'h', alt: true, description: 'Go to dashboard' },
  GO_PROJECTS: { key: 'p', alt: true, description: 'Go to projects' },
  GO_CODEBOARD: { key: 'c', alt: true, description: 'Go to CodeBoard' },
  GO_SETTINGS: { key: 's', alt: true, description: 'Go to settings' },

  // Board shortcuts
  NEW_ISSUE: { key: 'n', description: 'Create new issue' },
  FOCUS_SEARCH: { key: '/', description: 'Focus search input' },
  SEMANTIC_SEARCH: { key: 's', description: 'Open semantic search (AI)' },
  FEATURE_SELECTOR: { key: 'f', description: 'Open feature selector' },
  VIEW_SWIMLANES: { key: '1', description: 'Switch to swimlanes view' },
  VIEW_BOARD: { key: '2', description: 'Switch to board view' },
  VIEW_LIST: { key: '3', description: 'Switch to list view' },
  OPEN_GIT_SYNC: { key: 'g', description: 'Open Git sync panel' },
  OPEN_AI_BREAKDOWN: { key: 'a', description: 'Open AI breakdown' },

  // Issue detail shortcuts
  EDIT_ISSUE: { key: 'e', description: 'Edit issue' },
  DELETE_ISSUE: { key: 'd', shift: true, description: 'Delete issue' },
  CLOSE_MODAL: { key: 'Escape', description: 'Close modal' },
  EXECUTE_ISSUE: { key: 'x', description: 'Execute issue with AI' },
  COPY_ISSUE_KEY: { key: 'c', ctrl: true, description: 'Copy issue key' },

  // Status shortcuts (Shift + number)
  STATUS_BACKLOG: { key: '1', shift: true, description: 'Set status to Backlog' },
  STATUS_TODO: { key: '2', shift: true, description: 'Set status to Todo' },
  STATUS_IN_PROGRESS: { key: '3', shift: true, description: 'Set status to In Progress' },
  STATUS_IN_REVIEW: { key: '4', shift: true, description: 'Set status to In Review' },
  STATUS_DONE: { key: '5', shift: true, description: 'Set status to Done' },

  // Arrow navigation
  NEXT_ISSUE: { key: 'j', description: 'Next issue' },
  PREV_ISSUE: { key: 'k', description: 'Previous issue' },
  OPEN_ISSUE: { key: 'Enter', description: 'Open selected issue' },
} as const;

// Shortcut categories for help display
export const SHORTCUT_CATEGORIES = {
  global: {
    label: 'Global',
    shortcuts: ['SEARCH', 'HELP', 'ESCAPE', 'TOGGLE_THEME', 'REFRESH'],
  },
  navigation: {
    label: 'Navigation',
    shortcuts: ['GO_HOME', 'GO_PROJECTS', 'GO_CODEBOARD', 'GO_SETTINGS'],
  },
  board: {
    label: 'Board',
    shortcuts: ['NEW_ISSUE', 'FOCUS_SEARCH', 'SEMANTIC_SEARCH', 'FEATURE_SELECTOR', 'VIEW_SWIMLANES', 'VIEW_BOARD', 'VIEW_LIST', 'OPEN_GIT_SYNC', 'OPEN_AI_BREAKDOWN'],
  },
  issue: {
    label: 'Issue Detail',
    shortcuts: ['EDIT_ISSUE', 'DELETE_ISSUE', 'EXECUTE_ISSUE', 'COPY_ISSUE_KEY', 'CLOSE_MODAL'],
  },
  status: {
    label: 'Quick Status',
    shortcuts: ['STATUS_BACKLOG', 'STATUS_TODO', 'STATUS_IN_PROGRESS', 'STATUS_IN_REVIEW', 'STATUS_DONE'],
  },
} as const;
