'use client';

/**
 * SkillCard — mirrors AgentCard visual language exactly.
 * Displays a single SkillProfile with toggle, delete, expandable path,
 * contextFork chip, and capability pill-tags.
 */

import { useEffect, useRef, useState } from 'react';
import {
  Sparkles,
  Power,
  PowerOff,
  ChevronDown,
  ChevronUp,
  Trash2,
  ArrowRight,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { SkillProfile } from '@/hooks/useSkills';

// ============================================
// Source badge helpers
// ============================================

function SourceBadge({ source }: { source: string }) {
  if (source === 'standalone') {
    return (
      <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-zinc-600 text-zinc-400">
        standalone
      </Badge>
    );
  }

  if (source.startsWith('plugin:')) {
    const pluginName = source.slice('plugin:'.length);
    return (
      <Badge variant="purple" className="text-[10px] px-1.5 py-0">
        plugin · {pluginName}
      </Badge>
    );
  }

  return (
    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
      {source}
    </Badge>
  );
}

// ============================================
// SkillCard
// ============================================

interface SkillCardProps {
  skill: SkillProfile;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleActive: () => void;
  onDelete: () => void;
  isToggling: boolean;
  isDeleting: boolean;
}

export function SkillCard({
  skill,
  expanded,
  onToggleExpand,
  onToggleActive,
  onDelete,
  isToggling,
  isDeleting,
}: SkillCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const capabilities = skill.capabilities ?? [];

  // Clear any in-flight confirm timer on unmount to silence the
  // "state update on unmounted component" dev warning.
  useEffect(() => () => {
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
  }, []);

  const handleDeleteClick = () => {
    if (confirmDelete) {
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
      onDelete();
      setConfirmDelete(false);
    } else {
      setConfirmDelete(true);
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
      confirmTimerRef.current = setTimeout(() => setConfirmDelete(false), 3000);
    }
  };

  return (
    <div
      className={cn(
        'bg-zinc-900 border rounded-lg transition-colors',
        skill.isActive ? 'border-zinc-800' : 'border-zinc-800/50 opacity-60'
      )}
    >
      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={cn(
                'p-2 rounded-lg flex-shrink-0',
                skill.isActive ? 'bg-violet-500/10' : 'bg-zinc-800'
              )}
            >
              <Sparkles
                className={cn(
                  'h-5 w-5',
                  skill.isActive ? 'text-violet-400' : 'text-zinc-500'
                )}
              />
            </div>
            <div className="min-w-0">
              <h3 className="text-white font-medium truncate">{skill.displayName}</h3>
              <p className="text-xs text-zinc-500 font-mono truncate">{skill.name}</p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {/* Delete button */}
            <button
              onClick={handleDeleteClick}
              disabled={isDeleting}
              className={cn(
                'p-1.5 rounded-md transition-colors text-xs',
                confirmDelete
                  ? 'text-red-400 bg-red-500/10 hover:bg-red-500/20'
                  : 'text-zinc-600 hover:text-red-400 hover:bg-red-500/10'
              )}
              title={confirmDelete ? 'Click again to confirm delete' : 'Remove skill'}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>

            {/* Active toggle */}
            <button
              onClick={onToggleActive}
              disabled={isToggling}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                skill.isActive
                  ? 'text-green-400 hover:bg-green-500/10'
                  : 'text-zinc-500 hover:bg-zinc-800'
              )}
              title={skill.isActive ? 'Deactivate skill' : 'Activate skill'}
            >
              {skill.isActive ? (
                <Power className="h-4 w-4" />
              ) : (
                <PowerOff className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>

        {/* Description */}
        {skill.description && (
          <p className="text-sm text-zinc-400 mt-2 line-clamp-2">{skill.description}</p>
        )}

        {/* Capabilities pill-tags */}
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

        {/* contextFork chip */}
        {skill.contextFork && skill.agentRef && (
          <div className="flex items-center gap-1.5 mt-2">
            <ArrowRight className="h-3 w-3 text-amber-500 flex-shrink-0" />
            <span className="text-[11px] text-amber-400 font-mono">
              forks → {skill.agentRef}
            </span>
          </div>
        )}

        {/* Bottom row: source + status + expand toggle */}
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-1.5">
            <Badge
              variant={skill.isActive ? 'success' : 'secondary'}
              className="text-[10px]"
            >
              {skill.isActive ? 'Active' : 'Inactive'}
            </Badge>
            <SourceBadge source={skill.source} />
          </div>

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

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-zinc-800 px-5 py-4 space-y-3 text-sm">
          {/* Skill Path */}
          <div>
            <span className="text-zinc-500 text-xs uppercase tracking-wide">Skill Path</span>
            <p className="text-zinc-300 font-mono text-xs mt-1 break-all">
              {skill.skillPath || 'Not set'}
            </p>
          </div>

          {/* agentRef when contextFork */}
          {skill.contextFork && (
            <div>
              <span className="text-zinc-500 text-xs uppercase tracking-wide">Forks Into</span>
              <p className="text-amber-400 font-mono text-xs mt-1">{skill.agentRef}</p>
            </div>
          )}

          {/* Priority */}
          <div className="flex justify-between">
            <span className="text-zinc-500 text-xs uppercase tracking-wide">Priority</span>
            <span className="text-zinc-300">{skill.priority}</span>
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

          {/* Dates */}
          {skill.createdAt && (
            <div className="flex justify-between text-xs">
              <span className="text-zinc-500 uppercase tracking-wide">Registered</span>
              <span className="text-zinc-400">
                {new Date(skill.createdAt).toLocaleDateString()}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
