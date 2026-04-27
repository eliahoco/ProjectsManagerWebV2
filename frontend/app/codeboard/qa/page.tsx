'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useUrlState, optionalStringParam } from '@/hooks/use-url-state';
import { Zap, FlaskConical } from 'lucide-react';
import { useProjects, useIssues } from '@/hooks/useCodeBoard';
import { useQAKanban, useUpdateQASettings } from '@/hooks/useQABoard';
import type { IssueWithQASummary, QASettings } from '@/types/qaboard';
import { useToast } from '@/components/ui/toast';
import { TestPlanGenerator } from '@/components/codeboard';

// QA Kanban Column Component
function QAKanbanColumn({
  title,
  color,
  items,
  emptyText,
}: {
  title: string;
  color: string;
  items: IssueWithQASummary[];
  emptyText: string;
}) {
  return (
    <div className="flex-1 min-w-[300px] bg-zinc-900 rounded-lg border border-zinc-800 qa-kanban-column">
      {/* Column Header */}
      <div className={`px-4 py-3 border-b border-zinc-800 ${color} bg-opacity-20 rounded-t-lg qa-kanban-header`}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white">{title}</h3>
          <span className="text-sm text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded">
            {items.length}
          </span>
        </div>
      </div>

      {/* Column Content */}
      <div className="p-2 space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto qa-scrollbar">
        {items.length === 0 ? (
          <div className="text-center py-8 text-zinc-500 text-sm qa-empty-state">{emptyText}</div>
        ) : (
          items.map((item) => (
            <Link
              key={item.id}
              href={`/codeboard/qa/${item.id}`}
              className="block p-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg border border-zinc-700 hover:border-zinc-600 transition-colors qa-task-card qa-card-enter"
            >
              <div className="flex items-start gap-2">
                <span className="text-xs text-zinc-500 font-mono">{item.key}</span>
                {(() => {
                  const normalizedType = item.type?.toUpperCase() || 'TASK';
                  return (
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${
                        normalizedType === 'FEATURE'
                          ? 'bg-amber-900/50 text-amber-400'
                          : normalizedType === 'EPIC'
                          ? 'bg-purple-900/50 text-purple-400'
                          : normalizedType === 'STORY'
                          ? 'bg-green-900/50 text-green-400'
                          : normalizedType === 'TASK'
                          ? 'bg-blue-900/50 text-blue-400'
                          : 'bg-zinc-700 text-zinc-400'
                      }`}
                    >
                      {normalizedType}
                    </span>
                  );
                })()}
              </div>
              <p className="mt-1 text-sm text-zinc-200 line-clamp-2">{item.title}</p>
              <div className="mt-2 flex items-center gap-3 text-xs text-zinc-500">
                <span>
                  {item.qaSummary.passedTasks}/{item.qaSummary.totalTasks} passed
                </span>
                {item.qaSummary.totalTasks > 0 && (
                  <span
                    className={
                      item.qaSummary.passRate >= 0.9
                        ? 'text-green-500'
                        : item.qaSummary.passRate >= 0.5
                        ? 'text-yellow-500'
                        : 'text-red-500'
                    }
                  >
                    {Math.round(item.qaSummary.passRate * 100)}%
                  </span>
                )}
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

// Settings Panel Component
function SettingsPanel({
  settings,
  onUpdate,
}: {
  settings: QASettings;
  onUpdate: (settings: Partial<Omit<QASettings, 'projectId'>>) => void;
}) {
  const [threshold, setThreshold] = useState(settings.passThreshold * 100);

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4 qa-settings-panel">
      <h3 className="font-semibold text-white mb-4">QA Settings</h3>
      <div className="space-y-4">
        <div>
          <label className="block text-sm text-zinc-400 mb-1">Pass Threshold (%)</label>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min="0"
              max="100"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="flex-1"
            />
            <input
              type="number"
              min="0"
              max="100"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              onBlur={() => onUpdate({ passThreshold: threshold / 100 })}
              className="w-16 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
            />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <label className="text-sm text-zinc-400">Auto-create bugs on failure</label>
          <button
            onClick={() => onUpdate({ autoCreateBugs: !settings.autoCreateBugs })}
            className={`relative w-10 h-5 rounded-full transition-colors ${
              settings.autoCreateBugs ? 'bg-green-600' : 'bg-zinc-700'
            }`}
          >
            <span
              className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                settings.autoCreateBugs ? 'left-5' : 'left-0.5'
              }`}
            />
          </button>
        </div>
      </div>
    </div>
  );
}

// Main QA Board Page
export default function QABoardPage() {
  const router = useRouter();
  const { data: projects } = useProjects();

  // URL-backed project selection — survives back/refresh.
  const [urlState, setUrlState] = useUrlState({
    project: optionalStringParam('project'),
  });
  const effectiveProjectId = urlState.project ?? projects?.[0]?.id ?? null;

  const [showSettings, setShowSettings] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const { data: kanbanData, isLoading, refetch: refetchKanban } = useQAKanban(effectiveProjectId);
  const { data: issuesData } = useIssues(effectiveProjectId, { pageSize: 1000 });
  const updateSettings = useUpdateQASettings();
  const toast = useToast();

  // Handler for manual project selection
  const handleProjectSelect = (projectId: string | null) => {
    setUrlState({ project: projectId });
  };

  const handleUpdateSettings = async (settings: Partial<Omit<QASettings, 'projectId'>>) => {
    if (!effectiveProjectId) return;
    try {
      await updateSettings.mutateAsync({ projectId: effectiveProjectId, settings });
      toast.success('Settings Updated');
    } catch {
      toast.error('Error', 'Failed to update settings');
    }
  };

  return (
    <div className="h-full flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="px-6 py-4 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/codeboard"
              className="text-zinc-400 hover:text-white transition-colors"
            >
              &larr; CodeBoard
            </Link>
            <h1 className="text-xl font-semibold text-white">QA Board</h1>
          </div>
          <div className="flex items-center gap-3">
            {/* Project Selector */}
            <select
              value={effectiveProjectId || ''}
              onChange={(e) => handleProjectSelect(e.target.value || null)}
              className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded text-white text-sm"
            >
              <option value="">Select Project</option>
              {projects?.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>

            {/* Fast QA Mode Button */}
            <Link
              href={`/codeboard/qa/fast${effectiveProjectId ? `?project=${effectiveProjectId}` : ''}`}
              className="flex items-center gap-1.5 px-3 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded text-sm transition-colors"
              title="Quick, streamlined QA execution"
            >
              <Zap className="w-4 h-4" />
              Fast
            </Link>

            {/* Extensive QA Mode Button */}
            <Link
              href={`/codeboard/qa/extensive${effectiveProjectId ? `?project=${effectiveProjectId}` : ''}`}
              className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm transition-colors"
              title="Comprehensive QA with full details"
            >
              <FlaskConical className="w-4 h-4" />
              Extensive
            </Link>

            {/* Settings Toggle */}
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`px-3 py-2 rounded text-sm ${
                showSettings
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
              }`}
            >
              Settings
            </button>

            {/* Create QA Plan Button */}
            <button
              onClick={() => setShowCreateModal(true)}
              disabled={!effectiveProjectId}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded text-sm disabled:opacity-50"
            >
              + Create QA Plan
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-6 overflow-hidden">
        {!effectiveProjectId ? (
          <div className="flex items-center justify-center h-full text-zinc-500">
            Select a project to view QA Board
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
          </div>
        ) : (
          <div className="flex gap-4 h-full">
            {/* Settings Panel (collapsible) */}
            {showSettings && kanbanData?.settings && (
              <div className="w-64 flex-shrink-0">
                <SettingsPanel
                  settings={kanbanData.settings}
                  onUpdate={handleUpdateSettings}
                />
              </div>
            )}

            {/* Kanban Columns */}
            <div className="flex-1 flex gap-4 overflow-x-auto qa-kanban-columns qa-scrollbar">
              <QAKanbanColumn
                title="Waiting for QA"
                color="bg-yellow-600"
                items={kanbanData?.waitingForQA || []}
                emptyText="No items waiting for QA"
              />
              <QAKanbanColumn
                title="Pass"
                color="bg-green-600"
                items={kanbanData?.passed || []}
                emptyText="No items passed QA yet"
              />
              <QAKanbanColumn
                title="Failed"
                color="bg-red-600"
                items={kanbanData?.failed || []}
                emptyText="No items failed QA"
              />
            </div>
          </div>
        )}
      </div>

      {/* Test Plan Generator Modal */}
      <TestPlanGenerator
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        issues={issuesData?.items || []}
        projectId={effectiveProjectId || ''}
        onSuccess={(result) => {
          // Refresh kanban data and optionally navigate to the issue's QA page
          refetchKanban();
          if (result.issueId) {
            router.push(`/codeboard/qa/${result.issueId}`);
          }
        }}
      />
    </div>
  );
}
