'use client';

/**
 * ConversationTabBar — multi-tab strip for open Studio conversations.
 *
 * State lives in Zustand (useStudioStore). Tabs are hidden (not unmounted)
 * when not active so EventSource connections stay alive.
 *
 * "+ New" button calls onNew, which should:
 *   1. POST /api/studio/sessions to create a session
 *   2. Call openTab() on the store with the returned id
 */

import { useCallback } from 'react';
import { X, Plus, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStudioStore, type TabState } from '@/stores/useStudioStore';

interface ConversationTabBarProps {
  onNew?: () => void;
  isCreating?: boolean;
  className?: string;
}

function ConversationTab({
  tab,
  isActive,
  onActivate,
  onClose,
}: {
  tab: TabState;
  isActive: boolean;
  onActivate: () => void;
  onClose: () => void;
}) {
  return (
    <div
      role="tab"
      aria-selected={isActive}
      className={cn(
        'group flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg border-b-2 text-sm',
        'cursor-pointer select-none transition-colors max-w-[180px] flex-shrink-0',
        isActive
          ? 'border-cyan-500 bg-zinc-800/80 text-zinc-100'
          : 'border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40',
      )}
      onClick={onActivate}
      title={tab.title}
    >
      {/* Live indicator */}
      {tab.isStreaming && (
        <span
          className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-cyan-400 animate-agent-pulse"
          aria-label="Streaming"
        />
      )}

      <span className="truncate flex-1 min-w-0">{tab.title || 'New conversation'}</span>

      {/* Close button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        aria-label={`Close ${tab.title}`}
        className={cn(
          'flex-shrink-0 p-0.5 rounded transition-opacity opacity-0',
          'group-hover:opacity-100 hover:bg-zinc-700 text-zinc-500 hover:text-zinc-300',
          isActive && 'opacity-60',
        )}
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

export function ConversationTabBar({
  onNew,
  isCreating = false,
  className,
}: ConversationTabBarProps) {
  const { tabs, activeTabId, setActiveTab, closeTab } = useStudioStore();

  const handleClose = useCallback(
    (id: string) => {
      closeTab(id);
    },
    [closeTab],
  );

  return (
    <div
      role="tablist"
      aria-label="Open conversations"
      className={cn(
        'flex items-end gap-0.5 px-2 pt-2 border-b border-zinc-800 overflow-x-auto',
        'scrollbar-thin scrollbar-thumb-zinc-700',
        className,
      )}
    >
      {tabs.map((tab) => (
        <ConversationTab
          key={tab.id}
          tab={tab}
          isActive={tab.id === activeTabId}
          onActivate={() => setActiveTab(tab.id)}
          onClose={() => handleClose(tab.id)}
        />
      ))}

      {/* New conversation button */}
      <button
        onClick={onNew}
        disabled={isCreating}
        aria-label="New conversation"
        title="New conversation"
        className={cn(
          'flex items-center gap-1 px-2.5 py-1.5 rounded-t-lg text-sm',
          'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/40 transition-colors',
          'border-b-2 border-transparent flex-shrink-0',
          isCreating && 'cursor-not-allowed opacity-50',
        )}
      >
        {isCreating ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Plus className="w-3.5 h-3.5" />
        )}
        New
      </button>
    </div>
  );
}
