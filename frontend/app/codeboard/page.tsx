'use client';

/**
 * CodeBoard - AI-Powered Issue Tracking
 */

import { useState, useMemo, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, RefreshCw, LayoutGrid, List, Sparkles, Layers, GitCommit, Keyboard, FolderInput, Rocket } from 'lucide-react';
import { useProjects, useIssues, useCreateIssue, useUpdateIssue, useDeleteIssue, useAIStatus, useExecutionSessions, useProjectLabels, type ExecutionSession } from '@/hooks/useCodeBoard';
import { KanbanBoard, EpicSwimlanesBoard, HierarchyListView, FilterBar, CreateIssueModal, IssueDetailModal, ExecutionModal, SemanticSearchPanel, FeatureExecutionPanel, FeatureSelector } from '@/components/codeboard';
import { FloatingExecutionStatus } from '@/components/codeboard/FloatingExecutionStatus';
import { AIBreakdownModal } from '@/components/codeboard/AIBreakdownModal';
import { GitSyncPanel } from '@/components/codeboard/GitSyncPanel';
import { KeyboardShortcutsHelp } from '@/components/codeboard/KeyboardShortcutsHelp';
import { Issue, IssueStatus, CreateIssueData, Project, SortField, SortOrder, DateFilterField } from '@/types/codeboard';
import type { DateRange } from '@/components/ui/date-range-picker';
import { SkeletonKanbanBoard, SkeletonListView } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/error-boundary';
import { cn } from '@/lib/utils';
import { useKeyboardShortcuts, SHORTCUTS, formatShortcut, type ShortcutHandler } from '@/hooks/use-keyboard-shortcuts';
import { useToast } from '@/components/ui/toast';

type ViewMode = 'board' | 'swimlanes' | 'list';

export default function CodeBoardPage() {
  // Router for navigation
  const router = useRouter();

  // State
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('swimlanes'); // Default to swimlanes
  const [search, setSearch] = useState('');
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedPriority, setSelectedPriority] = useState<string | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>('sequence');
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createDefaultStatus, setCreateDefaultStatus] = useState<IssueStatus>('BACKLOG');
  const [createDefaultParentId, setCreateDefaultParentId] = useState<string | undefined>();
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [isAIBreakdownOpen, setIsAIBreakdownOpen] = useState(false);
  const [aiBreakdownIssue, setAIBreakdownIssue] = useState<Issue | null>(null);
  const [activeExecution, setActiveExecution] = useState<ExecutionSession | null>(null);
  const [isExecutionMinimized, setIsExecutionMinimized] = useState(false);
  const [isGitSyncOpen, setIsGitSyncOpen] = useState(false);
  const [isShortcutsHelpOpen, setIsShortcutsHelpOpen] = useState(false);
  const [focusedIssueId, setFocusedIssueId] = useState<string | null>(null);
  const [isSemanticSearchOpen, setIsSemanticSearchOpen] = useState(false);
  const [featureExecutionIssue, setFeatureExecutionIssue] = useState<Issue | null>(null);
  const [isFeatureSelectorOpen, setIsFeatureSelectorOpen] = useState(false);
  const [dateFilterField, setDateFilterField] = useState<DateFilterField | null>(null);
  const [dateRange, setDateRange] = useState<DateRange>({ start: null, end: null });

  // Refs
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Toast for feedback
  const toast = useToast();

  // Queries
  const { data: projects, isLoading: projectsLoading, error: projectsError } = useProjects();
  const { data: aiStatus } = useAIStatus();
  const { data: labelsData, refetch: refetchLabels } = useProjectLabels(selectedProjectId);
  const { data: issuesData, isLoading: issuesLoading, error: issuesError, refetch: refetchIssues } = useIssues(
    selectedProjectId,
    {
      search,
      type: selectedType || undefined,
      priority: selectedPriority || undefined,
      label: selectedLabel || undefined,
      dateField: dateFilterField || undefined,
      dateFrom: dateRange.start ? dateRange.start.toISOString() : undefined,
      dateTo: dateRange.end ? dateRange.end.toISOString() : undefined,
      pageSize: 500,
    }
  );
  const { data: executionSessions } = useExecutionSessions();

  // Mutations
  const createIssue = useCreateIssue();
  const updateIssue = useUpdateIssue();
  const deleteIssue = useDeleteIssue();

  // Derived data - needs to be before keyboard shortcuts
  const rawIssues = issuesData?.items || [];

  // Sort handler
  const handleSortChange = useCallback((field: SortField, order: SortOrder) => {
    setSortField(field);
    setSortOrder(order);
  }, []);

  // Date range handler
  const handleDateRangeChange = useCallback((field: DateFilterField | null, range: DateRange) => {
    setDateFilterField(field);
    setDateRange(range);
  }, []);

  // Sorting logic
  const sortIssues = useCallback((issuesToSort: Issue[]): Issue[] => {
    const priorityOrder: Record<string, number> = { 'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3 };
    const typeOrder: Record<string, number> = { 'EPIC': 0, 'STORY': 1, 'TASK': 2, 'BUG': 2, 'SUBTASK': 3 };
    const statusOrder: Record<string, number> = { 'IN_PROGRESS': 0, 'IN_REVIEW': 1, 'TODO': 2, 'BACKLOG': 3, 'DONE': 4, 'CANCELLED': 5 };

    return [...issuesToSort].sort((a, b) => {
      let comparison = 0;

      switch (sortField) {
        case 'sequence':
          comparison = a.sequence - b.sequence;
          break;
        case 'priority':
          comparison = (priorityOrder[a.priority] ?? 99) - (priorityOrder[b.priority] ?? 99);
          break;
        case 'createdAt':
          comparison = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
          break;
        case 'updatedAt':
          comparison = new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime();
          break;
        case 'dueDate':
          const aDate = a.dueDate ? new Date(a.dueDate).getTime() : Infinity;
          const bDate = b.dueDate ? new Date(b.dueDate).getTime() : Infinity;
          comparison = aDate - bDate;
          break;
        case 'title':
          comparison = a.title.localeCompare(b.title);
          break;
        case 'type':
          comparison = (typeOrder[a.type] ?? 99) - (typeOrder[b.type] ?? 99);
          break;
        case 'status':
          comparison = (statusOrder[a.status] ?? 99) - (statusOrder[b.status] ?? 99);
          break;
        default:
          comparison = 0;
      }

      return sortOrder === 'asc' ? comparison : -comparison;
    });
  }, [sortField, sortOrder]);

  // Apply sorting to issues
  const issues = useMemo(() => sortIssues(rawIssues), [rawIssues, sortIssues]);

  // Auto-select ProjectsManagerWebV2 or first project
  useMemo(() => {
    if (projects?.length && !selectedProjectId) {
      const pmv2 = projects.find(p => p.name === 'ProjectsManagerWebV2');
      setSelectedProjectId(pmv2?.id || projects[0].id);
    }
  }, [projects, selectedProjectId]);

  // Keyboard shortcuts
  const boardShortcuts = useMemo<ShortcutHandler[]>(() => [
    // New issue
    {
      ...SHORTCUTS.NEW_ISSUE,
      handler: () => {
        if (!selectedIssue && !isCreateModalOpen) {
          handleCreateClick();
        }
      },
    },
    // Focus search
    {
      ...SHORTCUTS.FOCUS_SEARCH,
      handler: () => {
        searchInputRef.current?.focus();
      },
    },
    // View modes
    {
      ...SHORTCUTS.VIEW_SWIMLANES,
      handler: () => setViewMode('swimlanes'),
    },
    {
      ...SHORTCUTS.VIEW_BOARD,
      handler: () => setViewMode('board'),
    },
    {
      ...SHORTCUTS.VIEW_LIST,
      handler: () => setViewMode('list'),
    },
    // Git sync
    {
      ...SHORTCUTS.OPEN_GIT_SYNC,
      handler: () => {
        if (selectedProjectId) setIsGitSyncOpen(true);
      },
    },
    // AI breakdown
    {
      ...SHORTCUTS.OPEN_AI_BREAKDOWN,
      handler: () => {
        if (selectedProjectId && aiStatus?.available) {
          handleAIBreakdown();
        }
      },
    },
    // Semantic search
    {
      ...SHORTCUTS.SEMANTIC_SEARCH,
      handler: () => {
        if (selectedProjectId && !selectedIssue && !isCreateModalOpen) {
          setIsSemanticSearchOpen(true);
        }
      },
    },
    // Feature selector
    {
      ...SHORTCUTS.FEATURE_SELECTOR,
      handler: () => {
        if (selectedProjectId && !selectedIssue && !isCreateModalOpen) {
          setIsFeatureSelectorOpen(true);
        }
      },
    },
    // Refresh
    {
      ...SHORTCUTS.REFRESH,
      handler: () => {
        refetchIssues();
        toast.info('Refreshing...');
      },
    },
    // Help
    {
      ...SHORTCUTS.HELP,
      handler: () => setIsShortcutsHelpOpen(true),
    },
    // Issue navigation - Next issue (j)
    {
      ...SHORTCUTS.NEXT_ISSUE,
      handler: () => {
        if (selectedIssue || isCreateModalOpen || isAIBreakdownOpen || isGitSyncOpen) return;
        if (issues.length === 0) return;
        const currentIndex = focusedIssueId ? issues.findIndex(i => i.id === focusedIssueId) : -1;
        const nextIndex = currentIndex < issues.length - 1 ? currentIndex + 1 : 0;
        const nextIssue = issues[nextIndex];
        setFocusedIssueId(nextIssue.id);
        // Scroll the focused issue into view
        const issueElement = document.querySelector(`[data-issue-id="${nextIssue.id}"]`);
        issueElement?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      },
    },
    // Issue navigation - Previous issue (k)
    {
      ...SHORTCUTS.PREV_ISSUE,
      handler: () => {
        if (selectedIssue || isCreateModalOpen || isAIBreakdownOpen || isGitSyncOpen) return;
        if (issues.length === 0) return;
        const currentIndex = focusedIssueId ? issues.findIndex(i => i.id === focusedIssueId) : issues.length;
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : issues.length - 1;
        const prevIssue = issues[prevIndex];
        setFocusedIssueId(prevIssue.id);
        // Scroll the focused issue into view
        const issueElement = document.querySelector(`[data-issue-id="${prevIssue.id}"]`);
        issueElement?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      },
    },
    // Open focused issue (Enter)
    {
      ...SHORTCUTS.OPEN_ISSUE,
      handler: () => {
        if (selectedIssue || isCreateModalOpen || isAIBreakdownOpen || isGitSyncOpen) return;
        if (focusedIssueId) {
          const focusedIssue = issues.find(i => i.id === focusedIssueId);
          if (focusedIssue) {
            setSelectedIssue(focusedIssue);
          }
        }
      },
    },
    // Global navigation - Go to home
    {
      ...SHORTCUTS.GO_HOME,
      handler: () => {
        router.push('/');
      },
    },
    // Global navigation - Go to projects
    {
      ...SHORTCUTS.GO_PROJECTS,
      handler: () => {
        router.push('/projects');
      },
    },
    // Global navigation - Go to settings
    {
      ...SHORTCUTS.GO_SETTINGS,
      handler: () => {
        router.push('/settings');
      },
    },
    // Escape to close modals or clear focus
    {
      ...SHORTCUTS.ESCAPE,
      handler: () => {
        if (isShortcutsHelpOpen) {
          setIsShortcutsHelpOpen(false);
        } else if (selectedIssue) {
          setSelectedIssue(null);
        } else if (isCreateModalOpen) {
          setIsCreateModalOpen(false);
        } else if (isAIBreakdownOpen) {
          setIsAIBreakdownOpen(false);
        } else if (isGitSyncOpen) {
          setIsGitSyncOpen(false);
        } else if (isSemanticSearchOpen) {
          setIsSemanticSearchOpen(false);
        } else if (isFeatureSelectorOpen) {
          setIsFeatureSelectorOpen(false);
        } else if (focusedIssueId) {
          setFocusedIssueId(null);
        }
      },
    },
  ], [selectedProjectId, selectedIssue, isCreateModalOpen, isAIBreakdownOpen, isGitSyncOpen, isShortcutsHelpOpen, aiStatus?.available, issues, focusedIssueId, router]);

  useKeyboardShortcuts(boardShortcuts);

  // Handlers
  const handleCreateClick = (status?: IssueStatus, parentId?: string) => {
    setCreateDefaultStatus(status || 'BACKLOG');
    setCreateDefaultParentId(parentId);
    setIsCreateModalOpen(true);
  };

  const handleCreateSubmit = (data: CreateIssueData) => {
    if (!selectedProjectId) return;

    // Add parent ID if set
    const issueData = createDefaultParentId
      ? { ...data, parentId: createDefaultParentId }
      : data;

    createIssue.mutate(
      { projectId: selectedProjectId, data: issueData },
      {
        onSuccess: () => {
          setIsCreateModalOpen(false);
          setCreateDefaultParentId(undefined);
        },
      }
    );
  };

  const handleIssueClick = (issue: Issue) => {
    // Navigate to feature detail page for FEATURE type
    if (issue.type === 'FEATURE') {
      router.push(`/codeboard/feature/${issue.id}`);
      return;
    }
    setSelectedIssue(issue);
  };

  const handleIssueUpdate = (data: Partial<Issue>) => {
    if (!selectedIssue) return;

    updateIssue.mutate(
      { issueId: selectedIssue.id, data },
      {
        onSuccess: (updatedIssue) => {
          setSelectedIssue(updatedIssue);
        },
      }
    );
  };

  const handleIssueDelete = () => {
    if (!selectedIssue) return;

    if (confirm(`Delete issue ${selectedIssue.key}?`)) {
      deleteIssue.mutate(selectedIssue.id, {
        onSuccess: () => {
          setSelectedIssue(null);
        },
      });
    }
  };

  const handleAIBreakdown = (issue?: Issue) => {
    setAIBreakdownIssue(issue || null);
    setIsAIBreakdownOpen(true);
  };

  // Handler for when a FEATURE is moved to TODO - triggers Feature Execution Panel
  const handleFeatureStatusChange = useCallback((issue: Issue, newStatus: IssueStatus) => {
    // If a FEATURE is being moved from BACKLOG to TODO, open the Feature Execution Panel
    if (issue.type === 'FEATURE' && issue.status === 'BACKLOG' && newStatus === 'TODO') {
      // Update the status first
      updateIssue.mutate(
        { issueId: issue.id, data: { status: newStatus } },
        {
          onSuccess: (updatedIssue) => {
            // Then open the Feature Execution Panel
            setFeatureExecutionIssue(updatedIssue);
          },
        }
      );
      return true; // Indicate we handled this
    }
    return false; // Let normal handling proceed
  }, [updateIssue]);

  // Handler to open Feature Execution Panel for any FEATURE
  const handleOpenFeatureExecution = useCallback((issue: Issue) => {
    if (issue.type === 'FEATURE') {
      setFeatureExecutionIssue(issue);
    }
  }, []);

  // Handler for cascade move - when a FEATURE is moved, move all its children too
  const handleCascadeMove = useCallback(async (feature: Issue, newStatus: IssueStatus) => {
    if (feature.type !== 'FEATURE') return;

    // Fetch all descendants from the API (CB-813 fix)
    // This ensures we get ALL descendants regardless of any filters applied in the UI
    let descendantIds: string[] = [];
    try {
      const response = await fetch(`/api/codeboard/issues/${feature.id}/descendants`);
      if (response.ok) {
        const descendants: Issue[] = await response.json();
        descendantIds = descendants.map(d => d.id);
      }
    } catch (error) {
      console.error('Failed to fetch descendants:', error);
    }

    // Show toast with count
    if (descendantIds.length > 0) {
      toast.info(
        `Moving ${feature.key}`,
        `Moving FEATURE and ${descendantIds.length} child items to ${newStatus.replace('_', ' ')}`
      );
    }

    // Update the FEATURE first
    updateIssue.mutate(
      { issueId: feature.id, data: { status: newStatus } },
      {
        onSuccess: () => {
          // Then update all descendants
          descendantIds.forEach(id => {
            updateIssue.mutate({ issueId: id, data: { status: newStatus } });
          });
          // Refetch after updates complete
          setTimeout(() => {
            refetchIssues();
            if (descendantIds.length > 0) {
              toast.success(
                'Move complete',
                `Moved ${descendantIds.length + 1} items to ${newStatus.replace('_', ' ')}`
              );
            }
          }, 300);
        },
      }
    );
  }, [updateIssue, refetchIssues, toast]);

  const handleExecutionStart = (sessionId: string) => {
    // Find the session from the list
    const session = executionSessions?.find(s => s.session_id === sessionId);
    if (session) {
      setActiveExecution(session);
    } else {
      // If not in list yet, create a temporary session object
      setActiveExecution({
        session_id: sessionId,
        issue_id: selectedIssue?.id || '',
        issue_key: selectedIssue?.key || '',
        provider: 'claude_code',
        status: 'running',
        output_lines: 0,
      });
    }
  };

  const selectedProject = projects?.find(p => p.id === selectedProjectId);

  // Count summary
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    issues.forEach(i => {
      counts[i.status] = (counts[i.status] || 0) + 1;
    });
    return counts;
  }, [issues]);

  // Filter features for the feature selector
  const features = useMemo(() => {
    return issues.filter(i => i.type === 'FEATURE');
  }, [issues]);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-zinc-800 px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold">CodeBoard</h1>
            <span className="text-zinc-500">AI-Powered Issue Tracking</span>
            {/* Summary */}
            <div className="flex gap-2 text-xs">
              <span className="px-2 py-1 bg-zinc-800 rounded text-zinc-400">
                {issues.length} total
              </span>
              {statusCounts['BACKLOG'] > 0 && (
                <span className="px-2 py-1 bg-yellow-900/30 rounded text-yellow-500">
                  {statusCounts['BACKLOG']} backlog
                </span>
              )}
              {statusCounts['IN_PROGRESS'] > 0 && (
                <span className="px-2 py-1 bg-blue-900/30 rounded text-blue-500">
                  {statusCounts['IN_PROGRESS']} in progress
                </span>
              )}
              {statusCounts['DONE'] > 0 && (
                <span className="px-2 py-1 bg-green-900/30 rounded text-green-500">
                  {statusCounts['DONE']} done
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Keyboard shortcuts help */}
            <button
              onClick={() => setIsShortcutsHelpOpen(true)}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Keyboard shortcuts (${formatShortcut(SHORTCUTS.HELP)})`}
            >
              <Keyboard className="w-4 h-4" />
            </button>

            {/* Refresh */}
            <button
              onClick={() => refetchIssues()}
              className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Refresh (${formatShortcut(SHORTCUTS.REFRESH)})`}
            >
              <RefreshCw className={cn('w-4 h-4', issuesLoading && 'animate-spin')} />
            </button>

            {/* View Toggle */}
            <div className="flex bg-zinc-800 rounded-lg p-1">
              <button
                onClick={() => setViewMode('swimlanes')}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  viewMode === 'swimlanes' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300'
                )}
                title={`Epic Swimlanes (${formatShortcut(SHORTCUTS.VIEW_SWIMLANES)})`}
              >
                <Layers className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('board')}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  viewMode === 'board' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300'
                )}
                title={`Kanban Board (${formatShortcut(SHORTCUTS.VIEW_BOARD)})`}
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  viewMode === 'list' ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300'
                )}
                title={`List view (${formatShortcut(SHORTCUTS.VIEW_LIST)})`}
              >
                <List className="w-4 h-4" />
              </button>
            </div>

            {/* Feature Selector Button */}
            <button
              onClick={() => setIsFeatureSelectorOpen(true)}
              className="p-2 text-zinc-500 hover:text-amber-400 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Feature Selector (${formatShortcut(SHORTCUTS.FEATURE_SELECTOR)})`}
            >
              <Rocket className="w-4 h-4" />
            </button>

            {/* Git Sync Button */}
            <button
              onClick={() => setIsGitSyncOpen(true)}
              className="p-2 text-zinc-500 hover:text-cyan-400 hover:bg-zinc-800 rounded-lg transition-colors"
              title={`Git Integration (${formatShortcut(SHORTCUTS.OPEN_GIT_SYNC)})`}
            >
              <GitCommit className="w-4 h-4" />
            </button>

            {/* AI Breakdown Button */}
            {aiStatus?.available && (
              <button
                onClick={() => handleAIBreakdown()}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg transition-colors"
                title={`AI Feature Breakdown (${formatShortcut(SHORTCUTS.OPEN_AI_BREAKDOWN)})`}
              >
                <Sparkles className="w-4 h-4" />
                <span>AI Breakdown</span>
              </button>
            )}

            {/* Create Button */}
            <button
              onClick={() => handleCreateClick()}
              className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg transition-colors"
              title={`Create new issue (${formatShortcut(SHORTCUTS.NEW_ISSUE)})`}
            >
              <Plus className="w-4 h-4" />
              <span>New Issue</span>
            </button>
          </div>
        </div>

        {/* Project Selector & Filters */}
        <div className="flex items-center gap-4">
          {/* Project Selector */}
          <select
            value={selectedProjectId || ''}
            onChange={(e) => setSelectedProjectId(e.target.value || null)}
            className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                       focus:outline-none focus:border-cyan-500 min-w-[200px]"
            disabled={projectsLoading}
          >
            {projectsLoading ? (
              <option>Loading projects...</option>
            ) : projects?.length === 0 ? (
              <option>No projects found</option>
            ) : (
              projects?.map(project => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))
            )}
          </select>

          {/* Filter Bar */}
          <FilterBar
            ref={searchInputRef}
            search={search}
            selectedType={selectedType}
            selectedPriority={selectedPriority}
            selectedLabel={selectedLabel}
            availableLabels={labelsData?.labels || []}
            onSearchChange={setSearch}
            onTypeChange={setSelectedType}
            onPriorityChange={setSelectedPriority}
            onLabelChange={setSelectedLabel}
            sortField={sortField}
            sortOrder={sortOrder}
            onSortChange={handleSortChange}
            onSemanticSearchClick={selectedProjectId ? () => setIsSemanticSearchOpen(true) : undefined}
            dateFilterField={dateFilterField}
            dateRange={dateRange}
            onDateRangeChange={handleDateRangeChange}
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden p-6">
        {!selectedProjectId ? (
          <div className="h-full flex items-center justify-center text-zinc-500">
            Select a project to view issues
          </div>
        ) : issuesError ? (
          <div className="h-full flex items-center justify-center">
            <InlineError
              message={issuesError instanceof Error ? issuesError.message : 'Failed to load issues'}
              onRetry={() => refetchIssues()}
            />
          </div>
        ) : issuesLoading ? (
          viewMode === 'list' ? (
            <SkeletonListView rowCount={12} />
          ) : (
            <SkeletonKanbanBoard />
          )
        ) : viewMode === 'swimlanes' ? (
          <EpicSwimlanesBoard
            issues={issues}
            onIssueClick={handleIssueClick}
            onCreateClick={handleCreateClick}
            focusedIssueId={focusedIssueId}
            sortField={sortField}
            sortOrder={sortOrder}
          />
        ) : viewMode === 'board' ? (
          <KanbanBoard
            issues={issues}
            onIssueClick={handleIssueClick}
            onCreateClick={handleCreateClick}
            onFeatureDropToTodo={(feature) => setFeatureExecutionIssue(feature)}
            onCascadeMove={handleCascadeMove}
            focusedIssueId={focusedIssueId}
            sortField={sortField}
            sortOrder={sortOrder}
          />
        ) : (
          <HierarchyListView
            issues={issues}
            onIssueClick={handleIssueClick}
            onCreateClick={handleCreateClick}
            focusedIssueId={focusedIssueId}
            sortField={sortField}
            sortOrder={sortOrder}
          />
        )}
      </div>

      {/* Create Issue Modal */}
      <CreateIssueModal
        isOpen={isCreateModalOpen}
        onClose={() => {
          setIsCreateModalOpen(false);
          setCreateDefaultParentId(undefined);
        }}
        onSubmit={handleCreateSubmit}
        defaultStatus={createDefaultStatus}
        isLoading={createIssue.isPending}
        projectId={selectedProjectId || undefined}
      />

      {/* Issue Detail Modal */}
      <IssueDetailModal
        issue={selectedIssue}
        issues={issues}
        isOpen={!!selectedIssue}
        onClose={() => setSelectedIssue(null)}
        onUpdate={handleIssueUpdate}
        onDelete={handleIssueDelete}
        projectId={selectedProjectId || undefined}
        onAIBreakdown={handleAIBreakdown}
        onIssueClick={handleIssueClick}
        onExecutionStart={handleExecutionStart}
      />

      {/* AI Breakdown Modal */}
      {isAIBreakdownOpen && selectedProjectId && (
        <AIBreakdownModal
          projectId={selectedProjectId}
          issue={aiBreakdownIssue || undefined}
          onClose={() => {
            setIsAIBreakdownOpen(false);
            setAIBreakdownIssue(null);
          }}
          onSuccess={() => {
            refetchIssues();
            refetchLabels();  // Refresh labels after new issues are created
          }}
        />
      )}

      {/* Execution Modal (full) */}
      {activeExecution && !isExecutionMinimized && (
        <ExecutionModal
          session={activeExecution}
          issue={issues?.find(i => i.id === activeExecution.issue_id) || selectedIssue || undefined}
          onClose={() => {
            setActiveExecution(null);
            setIsExecutionMinimized(false);
            refetchIssues();
          }}
          onMinimize={() => setIsExecutionMinimized(true)}
          onAIBreakdown={handleAIBreakdown}
          onAbortMission={() => {
            // Close everything and abort the whole mission
            setActiveExecution(null);
            setIsExecutionMinimized(false);
            setFeatureExecutionIssue(null); // This closes FeatureExecutionPanel
            refetchIssues();
          }}
        />
      )}

      {/* Floating Execution Status (minimized) */}
      {activeExecution && isExecutionMinimized && (
        <FloatingExecutionStatus
          session={activeExecution}
          onExpand={() => setIsExecutionMinimized(false)}
          onClose={() => {
            setActiveExecution(null);
            setIsExecutionMinimized(false);
            refetchIssues();
          }}
        />
      )}

      {/* Feature Execution Panel */}
      {featureExecutionIssue && (
        <FeatureExecutionPanel
          feature={featureExecutionIssue}
          allIssues={issues}
          isOpen={!!featureExecutionIssue}
          onClose={() => {
            setFeatureExecutionIssue(null);
            refetchIssues();
          }}
          onExecutionStart={(session) => {
            setActiveExecution(session);
            setIsExecutionMinimized(true); // Minimize so user can see both
          }}
          onIssueClick={handleIssueClick}
        />
      )}

      {/* Git Sync Panel */}
      {selectedProjectId && (
        <GitSyncPanel
          projectId={selectedProjectId}
          isOpen={isGitSyncOpen}
          onClose={() => setIsGitSyncOpen(false)}
        />
      )}

      {/* Keyboard Shortcuts Help */}
      <KeyboardShortcutsHelp
        isOpen={isShortcutsHelpOpen}
        onClose={() => setIsShortcutsHelpOpen(false)}
      />

      {/* Semantic Search Panel */}
      {selectedProjectId && (
        <SemanticSearchPanel
          projectId={selectedProjectId}
          isOpen={isSemanticSearchOpen}
          onClose={() => setIsSemanticSearchOpen(false)}
          onIssueClick={handleIssueClick}
          issues={issues}
        />
      )}

      {/* Feature Selector */}
      <FeatureSelector
        isOpen={isFeatureSelectorOpen}
        onClose={() => setIsFeatureSelectorOpen(false)}
        features={features}
        allIssues={issues}
        onFeatureSelect={(feature) => {
          // Navigation is handled internally by the component
        }}
        onFeatureExecute={(feature) => {
          setFeatureExecutionIssue(feature);
        }}
      />

      {/* Keyboard Navigation Indicator */}
      {focusedIssueId && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 shadow-lg flex items-center gap-4 text-sm">
          <span className="text-zinc-400">
            Keyboard navigation active
          </span>
          <div className="flex items-center gap-2 text-zinc-300">
            <kbd className="px-1.5 py-0.5 bg-zinc-700 rounded text-xs">j</kbd>
            <kbd className="px-1.5 py-0.5 bg-zinc-700 rounded text-xs">k</kbd>
            <span className="text-zinc-500">navigate</span>
          </div>
          <div className="flex items-center gap-2 text-zinc-300">
            <kbd className="px-1.5 py-0.5 bg-zinc-700 rounded text-xs">↵</kbd>
            <span className="text-zinc-500">open</span>
          </div>
          <div className="flex items-center gap-2 text-zinc-300">
            <kbd className="px-1.5 py-0.5 bg-zinc-700 rounded text-xs">Esc</kbd>
            <span className="text-zinc-500">clear</span>
          </div>
        </div>
      )}
    </div>
  );
}
