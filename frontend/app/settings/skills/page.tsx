'use client';

/**
 * AI Skills Settings Page
 * Manage registered AI skills - view, scan, toggle active/inactive, delete
 */

import { useState, useMemo } from 'react';
import {
  Sparkles,
  Scan,
  FolderSearch,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { Skeleton } from '@/components/ui/skeleton';
import { SkillCard } from '@/components/settings/skill-card';
import { useSkills, useScanSkills, useToggleSkill, useDeleteSkill } from '@/hooks/useSkills';
import type { SkillProfile } from '@/hooks/useSkills';

// ============================================
// Source filter helpers
// ============================================

type SourceFilter = 'all' | 'standalone' | 'plugin';

function getSourceFilterLabel(filter: SourceFilter): string {
  switch (filter) {
    case 'all': return 'All Sources';
    case 'standalone': return 'Standalone';
    case 'plugin': return 'Plugins';
  }
}

function matchesSourceFilter(skill: SkillProfile, filter: SourceFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'standalone') return skill.source === 'standalone';
  if (filter === 'plugin') return skill.source.startsWith('plugin:');
  return true;
}

// ============================================
// Page
// ============================================

export default function SkillProfilesPage() {
  const toast = useToast();
  const { data: skills, isLoading, error } = useSkills();
  const scanSkills = useScanSkills();
  const toggleSkill = useToggleSkill();
  const deleteSkill = useDeleteSkill();

  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');

  const filteredSkills = useMemo(() => {
    if (!skills) return [];
    return skills.filter((s) => matchesSourceFilter(s, sourceFilter));
  }, [skills, sourceFilter]);

  const handleScan = async () => {
    try {
      const result = await scanSkills.mutateAsync();
      toast.success(
        'Skill Scan Complete',
        `Found ${result.count} skill${result.count !== 1 ? 's' : ''}`
      );
    } catch (err) {
      toast.error('Scan Failed', err instanceof Error ? err.message : 'Could not scan skills directories');
    }
  };

  const handleToggle = async (skillId: string) => {
    try {
      const updated = await toggleSkill.mutateAsync(skillId);
      toast.success(
        updated.isActive ? 'Skill Activated' : 'Skill Deactivated',
        `${updated.displayName} is now ${updated.isActive ? 'active' : 'inactive'}`
      );
    } catch (err) {
      toast.error('Toggle Failed', err instanceof Error ? err.message : 'Could not toggle skill');
    }
  };

  const handleDelete = async (skillId: string, displayName: string) => {
    try {
      await deleteSkill.mutateAsync(skillId);
      toast.success('Skill Removed', `${displayName} has been removed`);
    } catch (err) {
      toast.error('Delete Failed', err instanceof Error ? err.message : 'Could not remove skill');
    }
  };

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Sparkles className="h-7 w-7 text-violet-500" />
            AI Skills
          </h1>
          <p className="text-zinc-400 mt-1">
            Auto-discovered from <code className="text-xs bg-zinc-800 px-1.5 py-0.5 rounded font-mono">~/.claude/skills/</code> and plugin caches
          </p>
        </div>
        <Button
          variant="default"
          onClick={handleScan}
          loading={scanSkills.isPending}
        >
          <Scan className="h-4 w-4" />
          Scan Skills
        </Button>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 space-y-3">
              <div className="flex items-center gap-3">
                <Skeleton className="h-10 w-10 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-5 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-5 w-16 rounded" />
                <Skeleton className="h-5 w-20 rounded" />
                <Skeleton className="h-5 w-14 rounded" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
          <p className="font-medium">Failed to load skills</p>
          <p className="text-sm mt-1">{error instanceof Error ? error.message : 'Unknown error'}</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && skills && skills.length === 0 && (
        <div className="text-center py-16 bg-zinc-900 border border-zinc-800 rounded-lg">
          <FolderSearch className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-zinc-300">No skills registered</h3>
          <p className="text-zinc-500 mt-2 max-w-md mx-auto">
            Click &quot;Scan Skills&quot; to auto-discover skills from{' '}
            <code className="text-xs bg-zinc-800 px-1 py-0.5 rounded font-mono">~/.claude/skills/</code>{' '}
            and installed plugins.
          </p>
          <Button
            variant="default"
            className="mt-6"
            onClick={handleScan}
            loading={scanSkills.isPending}
          >
            <Scan className="h-4 w-4" />
            Scan for Skills
          </Button>
        </div>
      )}

      {/* Skills Grid */}
      {!isLoading && skills && skills.length > 0 && (
        <>
          {/* Toolbar: count + source filter */}
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-400">
              {filteredSkills.length} skill{filteredSkills.length !== 1 ? 's' : ''}
              {sourceFilter !== 'all' && (
                <span className="text-zinc-600"> (filtered from {skills.length})</span>
              )}
              <span className="text-zinc-600 mx-1.5">&middot;</span>
              {skills.filter((s) => s.isActive).length} active
            </p>

            {/* Source filter dropdown */}
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}
              className="text-sm bg-zinc-800 border border-zinc-700 text-zinc-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-cyan-500 cursor-pointer"
            >
              {(['all', 'standalone', 'plugin'] as SourceFilter[]).map((f) => (
                <option key={f} value={f}>
                  {getSourceFilterLabel(f)}
                </option>
              ))}
            </select>
          </div>

          {/* Filtered empty state */}
          {filteredSkills.length === 0 && (
            <div className="text-center py-12 bg-zinc-900 border border-zinc-800 rounded-lg">
              <FolderSearch className="h-10 w-10 text-zinc-600 mx-auto mb-3" />
              <p className="text-zinc-400">No skills match the current filter</p>
              <button
                onClick={() => setSourceFilter('all')}
                className="text-cyan-400 hover:text-cyan-300 text-sm mt-2 transition-colors"
              >
                Clear filter
              </button>
            </div>
          )}

          {/* 2-column grid */}
          {filteredSkills.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
              {filteredSkills.map((skill) => (
                <SkillCard
                  key={skill.id}
                  skill={skill}
                  expanded={expandedSkill === skill.id}
                  onToggleExpand={() =>
                    setExpandedSkill(expandedSkill === skill.id ? null : skill.id)
                  }
                  onToggleActive={() => handleToggle(skill.id)}
                  onDelete={() => handleDelete(skill.id, skill.displayName)}
                  isToggling={toggleSkill.isPending}
                  isDeleting={deleteSkill.isPending}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
