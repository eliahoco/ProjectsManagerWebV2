'use client';

/**
 * EpicSearchBar - CB-1122 / CB-1123
 * Feature-level search interface specifically for epics.
 * Provides text search with relevance ranking, type/status/priority filters,
 * date range filtering, quick filter presets, and result counts within an epic's descendants.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Search, X, Filter, ArrowUpDown, ArrowUp, ArrowDown, Zap, Clock, CheckCircle2, AlertTriangle } from 'lucide-react';
import { IssueType, IssueStatus, ISSUE_TYPES, STATUS_COLUMNS, PRIORITIES, DateFilterField, DATE_FILTER_OPTIONS } from '@/types/codeboard';
import { DateRangePicker, type DateRange } from '@/components/ui/date-range-picker';
import { cn } from '@/lib/utils';

// Epic search sort options
export type EpicSearchSortField = 'relevance' | 'priority' | 'createdAt' | 'updatedAt' | 'status' | 'type' | 'sequence';
export type EpicSearchSortOrder = 'asc' | 'desc';

export const EPIC_SEARCH_SORT_OPTIONS: { field: EpicSearchSortField; label: string }[] = [
  { field: 'relevance', label: 'Relevance' },
  { field: 'priority', label: 'Priority' },
  { field: 'status', label: 'Status' },
  { field: 'type', label: 'Type' },
  { field: 'sequence', label: 'Order' },
  { field: 'createdAt', label: 'Created' },
  { field: 'updatedAt', label: 'Updated' },
];

// Quick filter presets for common searches
export interface QuickFilterPreset {
  label: string;
  icon: React.ReactNode;
  apply: (current: EpicSearchFilters) => EpicSearchFilters;
}

export interface EpicSearchFilters {
  query: string;
  types: IssueType[];
  statuses: IssueStatus[];
  priorities: string[];
  dateField: DateFilterField | null;
  dateRange: DateRange;
  sortBy: EpicSearchSortField;
  sortOrder: EpicSearchSortOrder;
}

export const DEFAULT_EPIC_SEARCH_FILTERS: EpicSearchFilters = {
  query: '',
  types: [],
  statuses: [],
  priorities: [],
  dateField: null,
  dateRange: { start: null, end: null },
  sortBy: 'relevance',
  sortOrder: 'desc',
};

interface EpicSearchBarProps {
  filters: EpicSearchFilters;
  onChange: (filters: EpicSearchFilters) => void;
  resultCount: number;
  totalCount: number;
  matchCount?: number;
  epicKey?: string;
  className?: string;
  /** Auto-focus the search input when the search bar mounts */
  autoFocus?: boolean;
}

export function EpicSearchBar({
  filters,
  onChange,
  resultCount,
  totalCount,
  matchCount,
  epicKey,
  className,
  autoFocus = true,
}: EpicSearchBarProps) {
  const [showFilters, setShowFilters] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const hasActiveFilters = filters.query ||
    filters.types.length > 0 ||
    filters.statuses.length > 0 ||
    filters.priorities.length > 0 ||
    (filters.dateField && (filters.dateRange.start || filters.dateRange.end));

  const activeFilterCount = [
    filters.types.length > 0,
    filters.statuses.length > 0,
    filters.priorities.length > 0,
    filters.dateField && (filters.dateRange.start || filters.dateRange.end),
  ].filter(Boolean).length;

  // Quick filter presets
  const quickPresets: QuickFilterPreset[] = useMemo(() => [
    {
      label: 'In Progress',
      icon: <Clock className="w-3 h-3" />,
      apply: () => ({
        ...DEFAULT_EPIC_SEARCH_FILTERS,
        statuses: ['IN_PROGRESS' as IssueStatus],
        sortBy: 'priority' as EpicSearchSortField,
        sortOrder: 'desc' as EpicSearchSortOrder,
      }),
    },
    {
      label: 'Blocked / To Do',
      icon: <AlertTriangle className="w-3 h-3" />,
      apply: () => ({
        ...DEFAULT_EPIC_SEARCH_FILTERS,
        statuses: ['TODO' as IssueStatus, 'BACKLOG' as IssueStatus],
        sortBy: 'priority' as EpicSearchSortField,
        sortOrder: 'desc' as EpicSearchSortOrder,
      }),
    },
    {
      label: 'High Priority',
      icon: <Zap className="w-3 h-3" />,
      apply: () => ({
        ...DEFAULT_EPIC_SEARCH_FILTERS,
        priorities: ['HIGH', 'CRITICAL'],
        sortBy: 'priority' as EpicSearchSortField,
        sortOrder: 'desc' as EpicSearchSortOrder,
      }),
    },
    {
      label: 'Completed',
      icon: <CheckCircle2 className="w-3 h-3" />,
      apply: () => ({
        ...DEFAULT_EPIC_SEARCH_FILTERS,
        statuses: ['DONE' as IssueStatus, 'COMPLETED_WAITING_QA' as IssueStatus],
        sortBy: 'updatedAt' as EpicSearchSortField,
        sortOrder: 'desc' as EpicSearchSortOrder,
      }),
    },
  ], []);

  const handleQueryChange = useCallback((query: string) => {
    onChange({ ...filters, query, sortBy: query ? 'relevance' : filters.sortBy });
  }, [filters, onChange]);

  const handleToggleType = useCallback((type: IssueType) => {
    const types = filters.types.includes(type)
      ? filters.types.filter(t => t !== type)
      : [...filters.types, type];
    onChange({ ...filters, types });
  }, [filters, onChange]);

  const handleToggleStatus = useCallback((status: IssueStatus) => {
    const statuses = filters.statuses.includes(status)
      ? filters.statuses.filter(s => s !== status)
      : [...filters.statuses, status];
    onChange({ ...filters, statuses });
  }, [filters, onChange]);

  const handleTogglePriority = useCallback((priority: string) => {
    const priorities = filters.priorities.includes(priority)
      ? filters.priorities.filter(p => p !== priority)
      : [...filters.priorities, priority];
    onChange({ ...filters, priorities });
  }, [filters, onChange]);

  const handleDateFieldChange = useCallback((field: DateFilterField | null) => {
    onChange({
      ...filters,
      dateField: field,
      dateRange: field ? filters.dateRange : { start: null, end: null },
    });
  }, [filters, onChange]);

  const handleDateRangeChange = useCallback((range: DateRange) => {
    onChange({ ...filters, dateRange: range });
  }, [filters, onChange]);

  const handleSortChange = useCallback((sortBy: EpicSearchSortField) => {
    onChange({ ...filters, sortBy });
  }, [filters, onChange]);

  const handleSortOrderToggle = useCallback(() => {
    onChange({ ...filters, sortOrder: filters.sortOrder === 'asc' ? 'desc' : 'asc' });
  }, [filters, onChange]);

  const handleClearAll = useCallback(() => {
    onChange(DEFAULT_EPIC_SEARCH_FILTERS);
  }, [onChange]);

  const handleApplyPreset = useCallback((preset: QuickFilterPreset) => {
    onChange(preset.apply(filters));
  }, [filters, onChange]);

  // Auto-focus when mounted
  useEffect(() => {
    if (autoFocus) {
      const timer = setTimeout(() => {
        searchInputRef.current?.focus();
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [autoFocus]);

  // Filterable issue types (exclude FEATURE and EPIC since we're inside an epic)
  const filterableTypes = ISSUE_TYPES.filter(t => t.type !== 'FEATURE' && t.type !== 'EPIC');

  // Check if a quick preset is currently active
  const isPresetActive = useCallback((preset: QuickFilterPreset) => {
    const applied = preset.apply(filters);
    return (
      applied.statuses.length === filters.statuses.length &&
      applied.statuses.every(s => filters.statuses.includes(s)) &&
      applied.priorities.length === filters.priorities.length &&
      applied.priorities.every(p => filters.priorities.includes(p)) &&
      !filters.query &&
      filters.types.length === 0 &&
      !filters.dateField
    );
  }, [filters]);

  return (
    <div className={cn('space-y-3', className)}>
      {/* Search row */}
      <div className="flex items-center gap-2">
        {/* Epic badge */}
        {epicKey && (
          <span className="text-xs px-2 py-1 rounded-full font-medium bg-purple-900/50 text-purple-400 whitespace-nowrap">
            ⚡ {epicKey}
          </span>
        )}

        {/* Search input */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            ref={searchInputRef}
            type="text"
            value={filters.query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search stories, tasks, bugs within this epic..."
            className="w-full pl-10 pr-10 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                       placeholder:text-zinc-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 transition-colors"
          />
          {filters.query && (
            <button
              onClick={() => handleQueryChange('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Filter toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm transition-colors',
            showFilters || activeFilterCount > 0
              ? 'bg-purple-500/20 border-purple-500 text-purple-400'
              : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600'
          )}
        >
          <Filter className="w-4 h-4" />
          <span>Filters</span>
          {activeFilterCount > 0 && (
            <span className="ml-0.5 px-1.5 py-0.5 bg-purple-500/30 rounded-full text-xs font-medium">
              {activeFilterCount}
            </span>
          )}
        </button>

        {/* Sort controls */}
        {hasActiveFilters && (
          <div className="flex items-center gap-1">
            <ArrowUpDown className="w-3.5 h-3.5 text-zinc-500" />
            <select
              value={filters.sortBy}
              onChange={(e) => handleSortChange(e.target.value as EpicSearchSortField)}
              className="px-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-xs
                         focus:outline-none focus:border-purple-500"
            >
              {EPIC_SEARCH_SORT_OPTIONS.map(opt => (
                <option key={opt.field} value={opt.field}>{opt.label}</option>
              ))}
            </select>
            <button
              onClick={handleSortOrderToggle}
              className="p-1.5 rounded-lg border bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 transition-colors"
              title={filters.sortOrder === 'asc' ? 'Ascending' : 'Descending'}
            >
              {filters.sortOrder === 'asc' ? (
                <ArrowUp className="w-3.5 h-3.5" />
              ) : (
                <ArrowDown className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        )}

        {/* Clear all */}
        {hasActiveFilters && (
          <button
            onClick={handleClearAll}
            className="flex items-center gap-1 px-2 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <X className="w-3 h-3" />
            Clear
          </button>
        )}

        {/* Result count */}
        {hasActiveFilters && (
          <span className="text-xs text-zinc-500 whitespace-nowrap">
            {matchCount !== undefined ? (
              <>
                <span className="text-purple-400 font-medium">{matchCount}</span>
                {' '}match{matchCount !== 1 ? 'es' : ''} ({resultCount} shown)
              </>
            ) : (
              <>{resultCount} of {totalCount}</>
            )}
          </span>
        )}
      </div>

      {/* Quick filter presets - shown when no filters are active */}
      {!hasActiveFilters && !showFilters && (
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-zinc-500 mr-1">Quick:</span>
          {quickPresets.map((preset) => (
            <button
              key={preset.label}
              onClick={() => handleApplyPreset(preset)}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-colors
                         bg-zinc-800/50 border border-zinc-700/50 text-zinc-400
                         hover:border-purple-500/50 hover:text-purple-300 hover:bg-purple-500/10"
            >
              {preset.icon}
              <span>{preset.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Filter panels */}
      {showFilters && (
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-lg p-4 space-y-4">
          {/* Quick filter presets row */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Quick Filters</label>
            <div className="flex flex-wrap gap-1.5">
              {quickPresets.map((preset) => {
                const active = isPresetActive(preset);
                return (
                  <button
                    key={preset.label}
                    onClick={() => handleApplyPreset(preset)}
                    className={cn(
                      'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
                      active
                        ? 'bg-purple-500/20 border-purple-500/50 text-purple-300'
                        : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                    )}
                  >
                    {preset.icon}
                    <span>{preset.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Type filter */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Issue Type</label>
            <div className="flex flex-wrap gap-1.5">
              {filterableTypes.map(type => {
                const isActive = filters.types.includes(type.type);
                return (
                  <button
                    key={type.type}
                    onClick={() => handleToggleType(type.type)}
                    className={cn(
                      'flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
                      isActive
                        ? 'bg-purple-500/20 border-purple-500/50 text-purple-300'
                        : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                    )}
                  >
                    <span>{type.icon}</span>
                    <span>{type.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Status filter */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Status</label>
            <div className="flex flex-wrap gap-1.5">
              {STATUS_COLUMNS.map(status => {
                const isActive = filters.statuses.includes(status.status);
                return (
                  <button
                    key={status.status}
                    onClick={() => handleToggleStatus(status.status)}
                    className={cn(
                      'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
                      isActive
                        ? 'bg-purple-500/20 border-purple-500/50 text-purple-300'
                        : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                    )}
                  >
                    <span className={cn('w-2 h-2 rounded-full', status.color)} />
                    <span>{status.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Priority filter */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Priority</label>
            <div className="flex flex-wrap gap-1.5">
              {PRIORITIES.map(priority => {
                const isActive = filters.priorities.includes(priority.priority);
                return (
                  <button
                    key={priority.priority}
                    onClick={() => handleTogglePriority(priority.priority)}
                    className={cn(
                      'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
                      isActive
                        ? 'bg-purple-500/20 border-purple-500/50 text-purple-300'
                        : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
                    )}
                  >
                    <span className={cn('text-xs', priority.color)}>{priority.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Date range filter */}
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-2 block">Date Range</label>
            <div className="flex items-center gap-2">
              <select
                value={filters.dateField || ''}
                onChange={(e) => handleDateFieldChange(e.target.value as DateFilterField | '' || null)}
                className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-xs
                           focus:outline-none focus:border-purple-500"
              >
                <option value="">Select date field...</option>
                {DATE_FILTER_OPTIONS.map(opt => (
                  <option key={opt.field} value={opt.field}>{opt.label}</option>
                ))}
              </select>
              {filters.dateField && (
                <DateRangePicker
                  value={filters.dateRange}
                  onChange={handleDateRangeChange}
                  placeholder="Pick date range..."
                  showPresets={true}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Active filter chips summary (when filter panel is closed) */}
      {!showFilters && hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-1.5">
          {filters.query && (
            <FilterChip
              label={`"${filters.query}"`}
              onRemove={() => handleQueryChange('')}
              color="purple"
            />
          )}
          {filters.types.map(type => {
            const config = ISSUE_TYPES.find(t => t.type === type);
            return (
              <FilterChip
                key={type}
                label={`${config?.icon || ''} ${config?.label || type}`}
                onRemove={() => handleToggleType(type)}
                color="purple"
              />
            );
          })}
          {filters.statuses.map(status => {
            const config = STATUS_COLUMNS.find(s => s.status === status);
            return (
              <FilterChip
                key={status}
                label={config?.label || status}
                onRemove={() => handleToggleStatus(status)}
                color="purple"
              />
            );
          })}
          {filters.priorities.map(priority => {
            const config = PRIORITIES.find(p => p.priority === priority);
            return (
              <FilterChip
                key={priority}
                label={config?.label || priority}
                onRemove={() => handleTogglePriority(priority)}
                color="purple"
              />
            );
          })}
          {filters.dateField && (filters.dateRange.start || filters.dateRange.end) && (
            <FilterChip
              label={`Date: ${DATE_FILTER_OPTIONS.find(d => d.field === filters.dateField)?.label || filters.dateField}`}
              onRemove={() => handleDateFieldChange(null)}
              color="purple"
            />
          )}
        </div>
      )}
    </div>
  );
}

function FilterChip({ label, onRemove, color = 'zinc' }: { label: string; onRemove: () => void; color?: 'zinc' | 'purple' }) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs',
      color === 'purple'
        ? 'bg-purple-900/30 border border-purple-700/50 text-purple-300'
        : 'bg-zinc-800 border border-zinc-700 text-zinc-300'
    )}>
      {label}
      <button
        onClick={onRemove}
        className="p-0.5 text-zinc-500 hover:text-zinc-200 transition-colors"
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}

/**
 * RelevanceBadge - Shows relevance score for search results.
 * Use this alongside tree items to indicate match strength.
 */
export function RelevanceBadge({ score, isDirectMatch }: { score: number; isDirectMatch: boolean }) {
  if (!isDirectMatch) return null;

  const level = score >= 80 ? 'high' : score >= 40 ? 'medium' : 'low';

  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium',
        level === 'high' && 'bg-purple-500/20 text-purple-300',
        level === 'medium' && 'bg-purple-500/10 text-purple-400',
        level === 'low' && 'bg-zinc-700 text-zinc-400',
      )}
      title={`Relevance score: ${score}`}
    >
      {level === 'high' ? 'Best' : level === 'medium' ? 'Good' : 'Match'}
    </span>
  );
}

/**
 * Highlight text matches with purple styling (distinct from feature search cyan).
 * Used for epic-level search result highlighting.
 */
export function highlightEpicMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;

  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escaped})`, 'gi');
  const parts = text.split(regex);

  return parts.map((part, index) => {
    if (part.toLowerCase() === query.toLowerCase()) {
      return (
        <mark key={index} className="bg-purple-500/30 text-purple-200 rounded px-0.5">
          {part}
        </mark>
      );
    }
    return part;
  });
}

/**
 * Apply epic search filters to a flat list of issues (client-side filtering).
 * Returns the set of matching issue IDs (includes ancestors to maintain tree structure).
 * Enhanced with relevance scoring for ranking results.
 */
export function applyEpicSearchFilters(
  issues: Array<{
    id: string;
    parentId?: string;
    title: string;
    key: string;
    description?: string;
    type: string;
    status: string;
    priority: string;
    labels?: string;
    createdAt: string;
    updatedAt: string;
    dueDate?: string;
    startedAt?: string;
    completedAt?: string;
  }>,
  filters: EpicSearchFilters,
): { visibleIds: Set<string>; matchIds: Set<string>; scores: Map<string, number> } {
  const hasAnyFilter = filters.query ||
    filters.types.length > 0 ||
    filters.statuses.length > 0 ||
    filters.priorities.length > 0 ||
    (filters.dateField && (filters.dateRange.start || filters.dateRange.end));

  if (!hasAnyFilter) {
    const allIds = new Set(issues.map(i => i.id));
    return { visibleIds: allIds, matchIds: allIds, scores: new Map() };
  }

  // Step 1: Find all directly matching issues with relevance scores
  const directMatches = new Set<string>();
  const scores = new Map<string, number>();

  for (const issue of issues) {
    let matches = true;
    let score = 0;

    // Text search with relevance scoring
    if (filters.query) {
      const q = filters.query.toLowerCase();
      const titleLower = issue.title.toLowerCase();
      const descLower = (issue.description || '').toLowerCase();
      const keyLower = issue.key.toLowerCase();
      const labelsLower = (issue.labels || '').toLowerCase();

      let textScore = 0;

      // Exact key match
      if (keyLower === q) textScore += 100;
      // Title starts with
      if (titleLower.startsWith(q)) textScore += 80;
      // Word boundary match in title
      else if (` ${titleLower}`.includes(` ${q}`)) textScore += 70;
      // Title contains
      else if (titleLower.includes(q)) textScore += 60;
      // Description contains
      if (descLower.includes(q)) textScore += 30;
      // Label contains
      if (labelsLower.includes(q)) textScore += 20;

      if (textScore === 0) {
        matches = false;
      } else {
        score += textScore;
      }
    }

    // Type filter
    if (matches && filters.types.length > 0) {
      if (!filters.types.includes(issue.type as IssueType)) matches = false;
    }

    // Status filter
    if (matches && filters.statuses.length > 0) {
      if (!filters.statuses.includes(issue.status as IssueStatus)) matches = false;
    }

    // Priority filter
    if (matches && filters.priorities.length > 0) {
      if (!filters.priorities.includes(issue.priority)) matches = false;
    }

    // Date range filter
    if (matches && filters.dateField && (filters.dateRange.start || filters.dateRange.end)) {
      const dateValue = issue[filters.dateField as keyof typeof issue] as string | undefined;
      if (dateValue) {
        const date = new Date(dateValue);
        if (filters.dateRange.start && date < filters.dateRange.start) matches = false;
        if (filters.dateRange.end) {
          const endOfDay = new Date(filters.dateRange.end);
          endOfDay.setHours(23, 59, 59, 999);
          if (date > endOfDay) matches = false;
        }
      } else {
        matches = false;
      }
    }

    if (matches) {
      directMatches.add(issue.id);

      // Add type/priority/status boosts
      const typeBoost: Record<string, number> = { STORY: 10, TASK: 8, BUG: 7, SUBTASK: 5, EPIC: 3 };
      const priorityBoost: Record<string, number> = { CRITICAL: 5, HIGH: 4, MEDIUM: 2, LOW: 1 };
      const statusBoost: Record<string, number> = { IN_PROGRESS: 5, IN_REVIEW: 4, TODO: 3, BACKLOG: 2, COMPLETED_WAITING_QA: 1 };

      score += typeBoost[issue.type] || 0;
      score += priorityBoost[issue.priority] || 0;
      score += statusBoost[issue.status] || 0;

      scores.set(issue.id, score);
    }
  }

  // Step 2: Include all ancestors of matching issues to preserve tree structure
  const issueMap = new Map(issues.map(i => [i.id, i]));
  const visibleIds = new Set(directMatches);

  for (const id of directMatches) {
    let current = issueMap.get(id);
    while (current?.parentId) {
      visibleIds.add(current.parentId);
      current = issueMap.get(current.parentId);
    }
  }

  // Step 3: Include all descendants of text-matching issues (when only text search, no type/status/priority filters)
  if (filters.query && !filters.types.length && !filters.statuses.length && !filters.priorities.length) {
    const childMap = new Map<string, string[]>();
    for (const issue of issues) {
      if (issue.parentId) {
        const children = childMap.get(issue.parentId) || [];
        children.push(issue.id);
        childMap.set(issue.parentId, children);
      }
    }

    function addDescendants(parentId: string) {
      const children = childMap.get(parentId) || [];
      for (const childId of children) {
        visibleIds.add(childId);
        addDescendants(childId);
      }
    }

    for (const id of directMatches) {
      addDescendants(id);
    }
  }

  return { visibleIds, matchIds: directMatches, scores };
}
