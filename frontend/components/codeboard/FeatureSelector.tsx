'use client';

/**
 * Feature Selector - CB-829, CB-840
 * A UI component for browsing and selecting features
 * Allows users to quickly find and select a feature to work on
 * Includes guided selection questions to help users find the right feature
 */

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import {
  X, Search, Rocket, ChevronRight, CheckCircle2, Circle,
  Clock, Target, TrendingUp, Filter, ArrowRight, Play, Layers,
  HelpCircle, Zap, ListTodo, Bug, Star, Timer, Sparkles, RotateCcw,
  Scale, Calendar, Hourglass, Box, Boxes, Package, RefreshCw, CalendarPlus, History
} from 'lucide-react';
import { Issue, IssueStatus, ISSUE_TYPES, STATUS_COLUMNS, PRIORITIES } from '@/types/codeboard';
import { cn } from '@/lib/utils';
import { isExecutableType } from '@/lib/codeboard';

// Feature selection question types - CB-840
type WorkType = 'any' | 'fresh' | 'in_progress' | 'quick_wins';
type PriorityPreference = 'any' | 'critical_high' | 'medium' | 'low';
type ProgressPreference = 'any' | 'not_started' | 'partially_done' | 'almost_done';
type ComplexityPreference = 'any' | 'small' | 'medium' | 'large';
type TimeFramePreference = 'any' | 'recent' | 'stale' | 'new';
type EffortPreference = 'any' | 'quick' | 'moderate' | 'significant';

interface SelectionQuestions {
  workType: WorkType;
  priorityPreference: PriorityPreference;
  progressPreference: ProgressPreference;
  complexityPreference: ComplexityPreference;
  timeFramePreference: TimeFramePreference;
  effortPreference: EffortPreference;
}

const DEFAULT_QUESTIONS: SelectionQuestions = {
  workType: 'any',
  priorityPreference: 'any',
  progressPreference: 'any',
  complexityPreference: 'any',
  timeFramePreference: 'any',
  effortPreference: 'any',
};

// Question option configurations
const WORK_TYPE_OPTIONS: { value: WorkType; label: string; description: string; icon: React.ReactNode }[] = [
  { value: 'any', label: 'Show All', description: 'No preference, show everything', icon: <Layers className="w-4 h-4" /> },
  { value: 'fresh', label: 'Fresh Start', description: 'Features not yet started', icon: <Sparkles className="w-4 h-4" /> },
  { value: 'in_progress', label: 'Continue Work', description: 'Features already in progress', icon: <Play className="w-4 h-4" /> },
  { value: 'quick_wins', label: 'Quick Wins', description: 'Features close to completion', icon: <Zap className="w-4 h-4" /> },
];

const PRIORITY_OPTIONS: { value: PriorityPreference; label: string; description: string; icon: React.ReactNode; color: string }[] = [
  { value: 'any', label: 'Any Priority', description: 'No preference', icon: <Star className="w-4 h-4" />, color: 'text-zinc-400' },
  { value: 'critical_high', label: 'High Priority', description: 'Critical or high priority', icon: <Target className="w-4 h-4" />, color: 'text-red-400' },
  { value: 'medium', label: 'Medium Priority', description: 'Medium priority tasks', icon: <TrendingUp className="w-4 h-4" />, color: 'text-yellow-400' },
  { value: 'low', label: 'Low Priority', description: 'Low priority, less urgent', icon: <Clock className="w-4 h-4" />, color: 'text-green-400' },
];

const PROGRESS_OPTIONS: { value: ProgressPreference; label: string; description: string; icon: React.ReactNode }[] = [
  { value: 'any', label: 'Any Progress', description: 'No preference', icon: <Circle className="w-4 h-4" /> },
  { value: 'not_started', label: 'Not Started', description: '0% complete', icon: <ListTodo className="w-4 h-4" /> },
  { value: 'partially_done', label: 'In Progress', description: '1-80% complete', icon: <Timer className="w-4 h-4" /> },
  { value: 'almost_done', label: 'Almost Done', description: '80%+ complete', icon: <CheckCircle2 className="w-4 h-4" /> },
];

// CB-840: Additional feature selection questions
const COMPLEXITY_OPTIONS: { value: ComplexityPreference; label: string; description: string; icon: React.ReactNode }[] = [
  { value: 'any', label: 'Any Size', description: 'No preference', icon: <Layers className="w-4 h-4" /> },
  { value: 'small', label: 'Small', description: 'Less than 5 tasks', icon: <Box className="w-4 h-4" /> },
  { value: 'medium', label: 'Medium', description: '5-15 tasks', icon: <Boxes className="w-4 h-4" /> },
  { value: 'large', label: 'Large', description: 'More than 15 tasks', icon: <Package className="w-4 h-4" /> },
];

const TIME_FRAME_OPTIONS: { value: TimeFramePreference; label: string; description: string; icon: React.ReactNode }[] = [
  { value: 'any', label: 'Any Time', description: 'No preference', icon: <Clock className="w-4 h-4" /> },
  { value: 'recent', label: 'Recently Active', description: 'Updated in last 7 days', icon: <RefreshCw className="w-4 h-4" /> },
  { value: 'stale', label: 'Needs Attention', description: 'No updates in 14+ days', icon: <History className="w-4 h-4" /> },
  { value: 'new', label: 'Newly Created', description: 'Created in last 7 days', icon: <CalendarPlus className="w-4 h-4" /> },
];

const EFFORT_OPTIONS: { value: EffortPreference; label: string; description: string; icon: React.ReactNode }[] = [
  { value: 'any', label: 'Any Effort', description: 'No preference', icon: <Scale className="w-4 h-4" /> },
  { value: 'quick', label: 'Quick Task', description: '1-3 story points', icon: <Zap className="w-4 h-4" /> },
  { value: 'moderate', label: 'Moderate', description: '4-8 story points', icon: <Hourglass className="w-4 h-4" /> },
  { value: 'significant', label: 'Significant', description: '8+ story points', icon: <Calendar className="w-4 h-4" /> },
];

interface FeatureSelectorProps {
  isOpen: boolean;
  onClose: () => void;
  features: Issue[];
  allIssues: Issue[];
  onFeatureSelect: (feature: Issue) => void;
  onFeatureExecute?: (feature: Issue) => void;
}

interface FeatureProgress {
  total: number;
  done: number;
  inProgress: number;
  todo: number;
  percent: number;
}

// Calculate progress for a feature based on its descendants
function calculateFeatureProgress(feature: Issue, allIssues: Issue[]): FeatureProgress {
  const descendants = getDescendants(feature.id, allIssues);
  const executableItems = descendants.filter(i => isExecutableType(i.type));

  const total = executableItems.length;
  const done = executableItems.filter(i => i.status === 'DONE').length;
  const inProgress = executableItems.filter(i => i.status === 'IN_PROGRESS').length;
  const todo = executableItems.filter(i => i.status === 'TODO' || i.status === 'BACKLOG').length;
  const percent = total > 0 ? Math.round((done / total) * 100) : 0;

  return { total, done, inProgress, todo, percent };
}

// Get all descendant issues of a parent
function getDescendants(parentId: string, allIssues: Issue[]): Issue[] {
  const children = allIssues.filter(i => i.parentId === parentId);
  let descendants = [...children];
  for (const child of children) {
    descendants = [...descendants, ...getDescendants(child.id, allIssues)];
  }
  return descendants;
}

// Get direct children count by type
function getChildCounts(parentId: string, allIssues: Issue[]): Record<string, number> {
  const descendants = getDescendants(parentId, allIssues);
  const counts: Record<string, number> = {};
  descendants.forEach(d => {
    counts[d.type] = (counts[d.type] || 0) + 1;
  });
  return counts;
}

export function FeatureSelector({
  isOpen,
  onClose,
  features,
  allIssues,
  onFeatureSelect,
  onFeatureExecute,
}: FeatureSelectorProps) {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<IssueStatus | 'ALL'>('ALL');
  const [priorityFilter, setPriorityFilter] = useState<string | 'ALL'>('ALL');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Guided selection mode state - CB-840
  const [isGuidedMode, setIsGuidedMode] = useState(false);
  const [selectionQuestions, setSelectionQuestions] = useState<SelectionQuestions>(DEFAULT_QUESTIONS);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);

  // Filter features based on search, filters, and guided selection questions - CB-840
  const filteredFeatures = useMemo(() => {
    return features.filter(f => {
      // Search filter
      if (search) {
        const searchLower = search.toLowerCase();
        const matchesSearch =
          f.title.toLowerCase().includes(searchLower) ||
          f.key.toLowerCase().includes(searchLower) ||
          f.description?.toLowerCase().includes(searchLower);
        if (!matchesSearch) return false;
      }

      // Status filter
      if (statusFilter !== 'ALL' && f.status !== statusFilter) return false;

      // Priority filter
      if (priorityFilter !== 'ALL' && f.priority !== priorityFilter) return false;

      // Guided selection filters (CB-840)
      if (isGuidedMode) {
        const progress = calculateFeatureProgress(f, allIssues);

        // Work type filter
        if (selectionQuestions.workType !== 'any') {
          switch (selectionQuestions.workType) {
            case 'fresh':
              if (f.status !== 'BACKLOG' && f.status !== 'TODO') return false;
              if (progress.percent > 0) return false;
              break;
            case 'in_progress':
              if (f.status !== 'IN_PROGRESS') return false;
              break;
            case 'quick_wins':
              if (progress.percent < 70) return false;
              break;
          }
        }

        // Priority preference filter
        if (selectionQuestions.priorityPreference !== 'any') {
          switch (selectionQuestions.priorityPreference) {
            case 'critical_high':
              if (f.priority !== 'CRITICAL' && f.priority !== 'HIGH') return false;
              break;
            case 'medium':
              if (f.priority !== 'MEDIUM') return false;
              break;
            case 'low':
              if (f.priority !== 'LOW') return false;
              break;
          }
        }

        // Progress preference filter
        if (selectionQuestions.progressPreference !== 'any') {
          switch (selectionQuestions.progressPreference) {
            case 'not_started':
              if (progress.percent !== 0) return false;
              break;
            case 'partially_done':
              if (progress.percent === 0 || progress.percent >= 80) return false;
              break;
            case 'almost_done':
              if (progress.percent < 80) return false;
              break;
          }
        }

        // CB-840: Complexity preference filter (based on number of tasks)
        if (selectionQuestions.complexityPreference !== 'any') {
          switch (selectionQuestions.complexityPreference) {
            case 'small':
              if (progress.total >= 5) return false;
              break;
            case 'medium':
              if (progress.total < 5 || progress.total > 15) return false;
              break;
            case 'large':
              if (progress.total <= 15) return false;
              break;
          }
        }

        // CB-840: Time frame preference filter
        if (selectionQuestions.timeFramePreference !== 'any') {
          const now = new Date();
          const updatedAt = new Date(f.updatedAt);
          const createdAt = new Date(f.createdAt);
          const daysSinceUpdate = Math.floor((now.getTime() - updatedAt.getTime()) / (1000 * 60 * 60 * 24));
          const daysSinceCreation = Math.floor((now.getTime() - createdAt.getTime()) / (1000 * 60 * 60 * 24));

          switch (selectionQuestions.timeFramePreference) {
            case 'recent':
              if (daysSinceUpdate > 7) return false;
              break;
            case 'stale':
              if (daysSinceUpdate < 14) return false;
              break;
            case 'new':
              if (daysSinceCreation > 7) return false;
              break;
          }
        }

        // CB-840: Effort preference filter (based on story points)
        if (selectionQuestions.effortPreference !== 'any') {
          const storyPoints = f.storyPoints || 0;
          switch (selectionQuestions.effortPreference) {
            case 'quick':
              if (storyPoints < 1 || storyPoints > 3) return false;
              break;
            case 'moderate':
              if (storyPoints < 4 || storyPoints > 8) return false;
              break;
            case 'significant':
              if (storyPoints < 8) return false;
              break;
          }
        }
      }

      return true;
    });
  }, [features, search, statusFilter, priorityFilter, isGuidedMode, selectionQuestions, allIssues]);

  // Calculate progress for all filtered features
  const featureProgressMap = useMemo(() => {
    const map = new Map<string, FeatureProgress>();
    filteredFeatures.forEach(f => {
      map.set(f.id, calculateFeatureProgress(f, allIssues));
    });
    return map;
  }, [filteredFeatures, allIssues]);

  // Reset selected index when filters change
  useEffect(() => {
    setSelectedIndex(0);
  }, [search, statusFilter, priorityFilter, selectionQuestions]);

  // Reset guided mode state when modal closes - CB-840
  useEffect(() => {
    if (!isOpen) {
      setIsGuidedMode(false);
      setSelectionQuestions(DEFAULT_QUESTIONS);
      setCurrentQuestionIndex(0);
    }
  }, [isOpen]);

  // Handler to update a selection question - CB-840
  const handleQuestionChange = useCallback(<K extends keyof SelectionQuestions>(
    key: K,
    value: SelectionQuestions[K]
  ) => {
    setSelectionQuestions(prev => ({ ...prev, [key]: value }));
  }, []);

  // Reset guided selection to defaults - CB-840
  const handleResetGuidedSelection = useCallback(() => {
    setSelectionQuestions(DEFAULT_QUESTIONS);
  }, []);

  // Count active filters in guided mode - CB-840
  const activeGuidedFilters = useMemo(() => {
    if (!isGuidedMode) return 0;
    let count = 0;
    if (selectionQuestions.workType !== 'any') count++;
    if (selectionQuestions.priorityPreference !== 'any') count++;
    if (selectionQuestions.progressPreference !== 'any') count++;
    if (selectionQuestions.complexityPreference !== 'any') count++;
    if (selectionQuestions.timeFramePreference !== 'any') count++;
    if (selectionQuestions.effortPreference !== 'any') count++;
    return count;
  }, [isGuidedMode, selectionQuestions]);

  // Focus search input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => searchInputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex(prev =>
            prev < filteredFeatures.length - 1 ? prev + 1 : prev
          );
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex(prev => prev > 0 ? prev - 1 : prev);
          break;
        case 'Enter':
          e.preventDefault();
          if (filteredFeatures[selectedIndex]) {
            handleFeatureClick(filteredFeatures[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, selectedIndex, filteredFeatures, onClose]);

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current && filteredFeatures[selectedIndex]) {
      const selectedElement = listRef.current.querySelector(`[data-feature-index="${selectedIndex}"]`);
      selectedElement?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [selectedIndex, filteredFeatures]);

  const handleFeatureClick = useCallback((feature: Issue) => {
    onFeatureSelect(feature);
    onClose();
    router.push(`/codeboard/feature/${feature.id}`);
  }, [onFeatureSelect, onClose, router]);

  const handleExecuteClick = useCallback((feature: Issue, e: React.MouseEvent) => {
    e.stopPropagation();
    if (onFeatureExecute) {
      onFeatureExecute(feature);
    }
    onClose();
  }, [onFeatureExecute, onClose]);

  // Get status configuration
  const getStatusConfig = (status: IssueStatus) => {
    return STATUS_COLUMNS.find(s => s.status === status);
  };

  // Get priority configuration
  const getPriorityConfig = (priority: string) => {
    return PRIORITIES.find(p => p.priority === priority);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh]">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-full max-w-2xl max-h-[80vh] bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header with search */}
        <div className="flex-shrink-0 px-4 py-3 border-b border-zinc-700">
          <div className="flex items-center gap-3">
            <Rocket className="w-5 h-5 text-amber-500" />
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                ref={searchInputRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search features by title, key, or description..."
                className="w-full pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                           text-sm focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20"
              />
            </div>
            <button
              onClick={onClose}
              className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Filters and Guided Mode Toggle - CB-840 */}
          <div className="flex items-center gap-2 mt-3">
            <Filter className="w-4 h-4 text-zinc-500" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as IssueStatus | 'ALL')}
              className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded
                         focus:outline-none focus:border-amber-500/50"
              disabled={isGuidedMode}
            >
              <option value="ALL">All Statuses</option>
              {STATUS_COLUMNS.map(s => (
                <option key={s.status} value={s.status}>{s.label}</option>
              ))}
            </select>
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="px-2 py-1 text-xs bg-zinc-800 border border-zinc-700 rounded
                         focus:outline-none focus:border-amber-500/50"
              disabled={isGuidedMode}
            >
              <option value="ALL">All Priorities</option>
              {PRIORITIES.map(p => (
                <option key={p.priority} value={p.priority}>{p.label}</option>
              ))}
            </select>

            {/* Guided Mode Toggle - CB-840 */}
            <button
              onClick={() => setIsGuidedMode(!isGuidedMode)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 text-xs rounded transition-all',
                isGuidedMode
                  ? 'bg-amber-600/20 text-amber-400 border border-amber-500/50'
                  : 'bg-zinc-800 text-zinc-400 border border-zinc-700 hover:border-zinc-600 hover:text-zinc-300'
              )}
            >
              <HelpCircle className="w-3.5 h-3.5" />
              <span>Guided</span>
              {activeGuidedFilters > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-amber-500/30 rounded-full text-xs">
                  {activeGuidedFilters}
                </span>
              )}
            </button>

            <span className="ml-auto text-xs text-zinc-500">
              {filteredFeatures.length} feature{filteredFeatures.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        {/* Guided Selection Questions Panel - CB-840 */}
        {isGuidedMode && (
          <div className="flex-shrink-0 px-4 py-3 border-b border-zinc-700 bg-zinc-800/30">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-amber-400" />
                <span className="text-sm font-medium text-zinc-200">What are you looking for?</span>
              </div>
              {activeGuidedFilters > 0 && (
                <button
                  onClick={handleResetGuidedSelection}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 rounded"
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset
                </button>
              )}
            </div>

            <div className="space-y-3">
              {/* Work Type Question */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Type of work</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {WORK_TYPE_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => handleQuestionChange('workType', option.value)}
                      className={cn(
                        'flex flex-col items-center gap-1 p-2 rounded-lg border transition-all text-center',
                        selectionQuestions.workType === option.value
                          ? 'border-amber-500 bg-amber-900/30 text-amber-200'
                          : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                      )}
                    >
                      <div className={cn(
                        'p-1.5 rounded',
                        selectionQuestions.workType === option.value ? 'bg-amber-600/30' : 'bg-zinc-700'
                      )}>
                        {option.icon}
                      </div>
                      <span className="text-xs font-medium">{option.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Priority Question */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Priority preference</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {PRIORITY_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => handleQuestionChange('priorityPreference', option.value)}
                      className={cn(
                        'flex flex-col items-center gap-1 p-2 rounded-lg border transition-all text-center',
                        selectionQuestions.priorityPreference === option.value
                          ? 'border-amber-500 bg-amber-900/30 text-amber-200'
                          : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                      )}
                    >
                      <div className={cn(
                        'p-1.5 rounded',
                        selectionQuestions.priorityPreference === option.value ? 'bg-amber-600/30' : 'bg-zinc-700',
                        option.color
                      )}>
                        {option.icon}
                      </div>
                      <span className="text-xs font-medium">{option.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Progress Question */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Progress level</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {PROGRESS_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => handleQuestionChange('progressPreference', option.value)}
                      className={cn(
                        'flex flex-col items-center gap-1 p-2 rounded-lg border transition-all text-center',
                        selectionQuestions.progressPreference === option.value
                          ? 'border-amber-500 bg-amber-900/30 text-amber-200'
                          : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                      )}
                    >
                      <div className={cn(
                        'p-1.5 rounded',
                        selectionQuestions.progressPreference === option.value ? 'bg-amber-600/30' : 'bg-zinc-700'
                      )}>
                        {option.icon}
                      </div>
                      <span className="text-xs font-medium">{option.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* CB-840: Complexity/Size Question */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Feature size</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {COMPLEXITY_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => handleQuestionChange('complexityPreference', option.value)}
                      className={cn(
                        'flex flex-col items-center gap-1 p-2 rounded-lg border transition-all text-center',
                        selectionQuestions.complexityPreference === option.value
                          ? 'border-amber-500 bg-amber-900/30 text-amber-200'
                          : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                      )}
                    >
                      <div className={cn(
                        'p-1.5 rounded',
                        selectionQuestions.complexityPreference === option.value ? 'bg-amber-600/30' : 'bg-zinc-700'
                      )}>
                        {option.icon}
                      </div>
                      <span className="text-xs font-medium">{option.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* CB-840: Time Frame Question */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Activity timeframe</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {TIME_FRAME_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => handleQuestionChange('timeFramePreference', option.value)}
                      className={cn(
                        'flex flex-col items-center gap-1 p-2 rounded-lg border transition-all text-center',
                        selectionQuestions.timeFramePreference === option.value
                          ? 'border-amber-500 bg-amber-900/30 text-amber-200'
                          : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                      )}
                    >
                      <div className={cn(
                        'p-1.5 rounded',
                        selectionQuestions.timeFramePreference === option.value ? 'bg-amber-600/30' : 'bg-zinc-700'
                      )}>
                        {option.icon}
                      </div>
                      <span className="text-xs font-medium">{option.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* CB-840: Effort/Story Points Question */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Estimated effort</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {EFFORT_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      onClick={() => handleQuestionChange('effortPreference', option.value)}
                      className={cn(
                        'flex flex-col items-center gap-1 p-2 rounded-lg border transition-all text-center',
                        selectionQuestions.effortPreference === option.value
                          ? 'border-amber-500 bg-amber-900/30 text-amber-200'
                          : 'border-zinc-700 bg-zinc-800/50 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                      )}
                    >
                      <div className={cn(
                        'p-1.5 rounded',
                        selectionQuestions.effortPreference === option.value ? 'bg-amber-600/30' : 'bg-zinc-700'
                      )}>
                        {option.icon}
                      </div>
                      <span className="text-xs font-medium">{option.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Feature list */}
        <div ref={listRef} className="flex-1 overflow-y-auto">
          {filteredFeatures.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
              <Rocket className="w-12 h-12 mb-4 opacity-30" />
              <p className="text-sm">No features found</p>
              {search && (
                <p className="text-xs mt-1">Try a different search term</p>
              )}
              {isGuidedMode && activeGuidedFilters > 0 && !search && (
                <div className="mt-3 text-center">
                  <p className="text-xs">No features match your criteria</p>
                  <button
                    onClick={handleResetGuidedSelection}
                    className="mt-2 flex items-center gap-1 px-3 py-1.5 text-xs text-amber-400 hover:text-amber-300 bg-amber-900/20 hover:bg-amber-900/30 rounded"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Reset filters
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="py-2">
              {filteredFeatures.map((feature, index) => {
                const progress = featureProgressMap.get(feature.id) || { total: 0, done: 0, inProgress: 0, todo: 0, percent: 0 };
                const childCounts = getChildCounts(feature.id, allIssues);
                const statusConfig = getStatusConfig(feature.status);
                const priorityConfig = getPriorityConfig(feature.priority);
                const isSelected = index === selectedIndex;

                return (
                  <div
                    key={feature.id}
                    data-feature-index={index}
                    onClick={() => handleFeatureClick(feature)}
                    className={cn(
                      'flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors',
                      'hover:bg-zinc-800/70',
                      isSelected && 'bg-zinc-800 border-l-2 border-amber-500'
                    )}
                  >
                    {/* Feature icon and key */}
                    <div className="flex-shrink-0 flex items-center gap-2">
                      <Rocket className="w-5 h-5 text-amber-500" />
                      <span className="font-mono text-xs text-zinc-500">{feature.key}</span>
                    </div>

                    {/* Feature info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-zinc-100 truncate">
                          {feature.title}
                        </h3>
                        {/* Priority badge */}
                        <span className={cn('text-xs', priorityConfig?.color)}>
                          {feature.priority}
                        </span>
                      </div>

                      {/* Progress and child counts */}
                      <div className="flex items-center gap-4 mt-1">
                        {/* Progress bar */}
                        {progress.total > 0 && (
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-amber-600 to-green-500 transition-all"
                                style={{ width: `${progress.percent}%` }}
                              />
                            </div>
                            <span className="text-xs text-zinc-400">
                              {progress.percent}%
                            </span>
                          </div>
                        )}

                        {/* Child counts */}
                        <div className="flex items-center gap-2 text-xs text-zinc-500">
                          {childCounts['EPIC'] > 0 && (
                            <span className="flex items-center gap-0.5">
                              <span className="text-purple-400">⚡</span>{childCounts['EPIC']}
                            </span>
                          )}
                          {childCounts['STORY'] > 0 && (
                            <span className="flex items-center gap-0.5">
                              <span className="text-green-400">📖</span>{childCounts['STORY']}
                            </span>
                          )}
                          {childCounts['TASK'] > 0 && (
                            <span className="flex items-center gap-0.5">
                              <span className="text-blue-400">✓</span>{childCounts['TASK']}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Status badge */}
                    <div className="flex-shrink-0 flex items-center gap-2">
                      <span className={cn(
                        'px-2 py-0.5 text-xs rounded',
                        statusConfig?.color,
                        'bg-opacity-20'
                      )}>
                        {statusConfig?.label || feature.status}
                      </span>

                      {/* Execute button */}
                      {onFeatureExecute && (feature.status === 'TODO' || feature.status === 'IN_PROGRESS') && (
                        <button
                          onClick={(e) => handleExecuteClick(feature, e)}
                          className="p-1.5 text-amber-400 hover:text-amber-300 hover:bg-amber-900/30 rounded transition-colors"
                          title="Execute Feature"
                        >
                          <Play className="w-4 h-4" />
                        </button>
                      )}

                      <ChevronRight className="w-4 h-4 text-zinc-600" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer with keyboard hints */}
        <div className="flex-shrink-0 px-4 py-2 border-t border-zinc-800 bg-zinc-900/80">
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded">↑</kbd>
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded">↓</kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded">↵</kbd>
                select
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded">esc</kbd>
                close
              </span>
            </div>
            <span>
              {features.length} total features
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
