'use client';

/**
 * Fast QA Page - Streamlined QA execution interface
 *
 * Features:
 * - Quick access to all QA tasks
 * - One-click execution
 * - Keyboard shortcuts
 * - Real-time progress tracking
 * - Minimal, focused UI
 */

import { useState, useMemo, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Zap,
  ArrowLeft,
  Settings,
  ChevronDown,
  RefreshCw,
} from 'lucide-react';
import { useProjects, useIssues } from '@/hooks/useCodeBoard';
import { useQATasks } from '@/hooks/useQABoard';
import { useQuickQAExecution } from '@/hooks/useQuickQAExecution';
import { useToast } from '@/components/ui/toast';
import { FastQAPanel } from '@/components/codeboard/FastQAPanel';
import { FloatingQuickExecuteButton } from '@/components/codeboard/QuickExecuteButton';
import { useUrlState, optionalStringParam } from '@/hooks/use-url-state';

// Loading fallback for Suspense boundary
function FastQAPageLoading() {
  return (
    <div className="h-full flex flex-col bg-zinc-950">
      <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-3">
          <Zap className="w-5 h-5 text-yellow-500" />
          <h1 className="text-lg font-semibold text-white">Fast QA</h1>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
    </div>
  );
}

export default function FastQAPage() {
  return (
    <Suspense fallback={<FastQAPageLoading />}>
      <FastQAPageContent />
    </Suspense>
  );
}

function FastQAPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();

  // URL-backed project + issue selection — survives back/refresh.
  const [urlState, setUrlState] = useUrlState({
    project: optionalStringParam('project'),
    issue: optionalStringParam('issue'),
  });

  // Project state
  const { data: projects, isLoading: projectsLoading } = useProjects();
  const selectedProjectId = urlState.project;

  // Effective project ID - use selected or first available
  const effectiveProjectId = selectedProjectId ?? projects?.[0]?.id ?? null;

  // Issue filter (optional)
  const selectedIssueId = urlState.issue;
  const { data: issuesData } = useIssues(effectiveProjectId, { pageSize: 100 });

  // Quick QA execution hook
  const qa = useQuickQAExecution({
    projectId: effectiveProjectId,
    issueId: selectedIssueId,
    onTaskComplete: (taskKey, status) => {
      // Show quick toast for each task
      const icon = status === 'PASS' ? '✓' : '✗';
      const color = status === 'PASS' ? 'success' : 'error';
      // Optional: toast.info(`${icon} ${taskKey}`, status);
    },
    onAllComplete: (passed, failed) => {
      toast.success(
        'Execution Complete',
        `${passed} passed, ${failed} failed`
      );
    },
    onError: (error) => {
      toast.error('Error', error);
    },
  });

  // Issues for the dropdown
  const issueOptions = useMemo(() => {
    if (!issuesData?.items) return [];
    return issuesData.items.map(i => ({
      id: i.id,
      key: i.key,
      title: i.title,
      type: i.type,
    }));
  }, [issuesData]);

  // Handle project change — URL sync is automatic via useUrlState.
  const handleProjectChange = (projectId: string | null) => {
    setUrlState({ project: projectId, issue: null });
  };

  // Handle issue filter change
  const handleIssueChange = (issueId: string | null) => {
    setUrlState({ issue: issueId });
  };

  return (
    <div className="h-full flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/codeboard/qa"
              className="p-1 text-zinc-400 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-yellow-500" />
              <h1 className="text-lg font-semibold text-white">Fast QA</h1>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Project selector */}
            <select
              value={effectiveProjectId || ''}
              onChange={(e) => handleProjectChange(e.target.value || null)}
              className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-white text-sm min-w-[150px]"
            >
              <option value="">Select Project</option>
              {projects?.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>

            {/* Issue filter (optional) */}
            <select
              value={selectedIssueId || ''}
              onChange={(e) => handleIssueChange(e.target.value || null)}
              className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-white text-sm min-w-[150px]"
              disabled={!effectiveProjectId}
            >
              <option value="">All Issues</option>
              {issueOptions.map((issue) => (
                <option key={issue.id} value={issue.id}>
                  {issue.key}: {issue.title.slice(0, 30)}...
                </option>
              ))}
            </select>

            {/* Refresh button */}
            <button
              onClick={() => qa.refetch()}
              disabled={qa.isLoading}
              className="p-1.5 text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
              title="Refresh tasks"
            >
              <RefreshCw className={`w-4 h-4 ${qa.isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {!effectiveProjectId ? (
        <div className="flex-1 flex items-center justify-center text-zinc-500">
          Select a project to get started
        </div>
      ) : qa.isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
        </div>
      ) : (
        <FastQAPanel
          tasks={qa.tasks}
          isExecuting={qa.isExecuting}
          executionMode={qa.executionMode}
          progress={qa.progress}
          completedTasks={qa.completedTasks}
          totalTasks={qa.totalTasks}
          currentTaskKey={qa.currentTaskKey}
          taskResults={qa.taskResults}
          // Execution actions
          onExecuteAll={qa.executeAll}
          onExecuteSelected={qa.executeSelected}
          onExecuteSingle={qa.executeSingle}
          onRetryFailed={qa.retryFailed}
          onAbort={qa.abort}
          onMarkManual={(taskId, status, result) => {
            if (status === 'PASS') {
              qa.markManualPass(taskId, result);
            } else {
              qa.markManualFail(taskId, result);
            }
          }}
          onToggleMode={qa.toggleExecutionMode}
          onClearResults={qa.reset}
          // Fast QA options
          maxConcurrent={qa.maxConcurrent}
          priorityFilter={qa.priorityFilter}
          autoRetryFailed={qa.autoRetryFailed}
          stopOnFirstFailure={qa.stopOnFirstFailure}
          soundEnabled={qa.soundEnabled}
          showNotifications={qa.showNotifications}
          // Fast QA option setters
          onSetMaxConcurrent={qa.setMaxConcurrent}
          onSetPriorityFilter={qa.setPriorityFilter}
          onSetAutoRetryFailed={qa.setAutoRetryFailed}
          onSetStopOnFirstFailure={qa.setStopOnFirstFailure}
          onSetSoundEnabled={qa.setSoundEnabled}
          onSetShowNotifications={qa.setShowNotifications}
          // UI options
          className="flex-1"
          failedCount={qa.tasks.filter(t => t.status === 'FAILED').length}
        />
      )}

      {/* Floating execute button for quick access */}
      <FloatingQuickExecuteButton
        pendingCount={qa.filteredPendingTasks.length}
        isExecuting={qa.isExecuting}
        progress={qa.progress}
        onExecute={qa.executeAll}
        onAbort={qa.abort}
        position="bottom-right"
      />
    </div>
  );
}
