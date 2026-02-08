'use client';

/**
 * FeatureSearchBar - CB-1119
 * Feature-level search interface for filtering and finding issues within a feature hierarchy.
 * Provides text search, type/status/priority filters, date range filtering, and result counts.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { Search, X, Filter } from 'lucide-react';
import { IssueType, IssueStatus, ISSUE_TYPES, STATUS_COLUMNS, PRIORITIES, DateFilterField, DATE_FILTER_OPTIONS } from '@/types/codeboard';
import { DateRangePicker, type DateRange } from '@/components/ui/date-range-picker';
import { cn } from '@/lib/utils';

export interface FeatureSearchFilters {
  query: string;
  types: IssueType[];
  statuses: IssueStatus[];
  priorities: string[];
  dateField: DateFilterField | null;
  dateRange: DateRange;
}

export const DEFAULT_FEATURE_SEARCH_FILTERS: FeatureSearchFilters = {
  query: '',
  types: [],
  statuses: [],
  priorities: [],
  dateField: null,
  dateRange: { start: null, end: null },
};

interface FeatureSearchBarProps {
  filters: FeatureSearchFilters;
  onChange: (filters: FeatureSearchFilters) => void;
  resultCount: number;
  totalCount: number;
  className?: string;
}

export function FeatureSearchBar({
  filters,
  onChange,
  resultCount,
  totalCount,
  className,
}: FeatureSearchBarProps) {
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

  const handleQueryChange = useCallback((query: string) => {
    onChange({ ...filters, query });
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

  const handleClearAll = useCallback(() => {
    onChange(DEFAULT_FEATURE_SEARCH_FILTERS);
  }, [onChange]);

  // Keyboard shortcut: / to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const target = e.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return;
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Filterable issue types (exclude FEATURE since we're inside a feature)
  const filterableTypes = ISSUE_TYPES.filter(t => t.type !== 'FEATURE');

  return (
    <div className={cn('space-y-3', className)}>
      {/* Search row */}
      <div className="flex items-center gap-2">
        {/* Search input */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            ref={searchInputRef}
            type="text"
            value={filters.query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search by title, key, or description... (press /)"
            className="w-full pl-10 pr-10 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                       placeholder:text-zinc-500 focus:outline-none focus:border-cyan-500 transition-colors"
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
              ? 'bg-cyan-500/20 border-cyan-500 text-cyan-400'
              : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600'
          )}
        >
          <Filter className="w-4 h-4" />
          <span>Filters</span>
          {activeFilterCount > 0 && (
            <span className="ml-0.5 px-1.5 py-0.5 bg-cyan-500/30 rounded-full text-xs font-medium">
              {activeFilterCount}
            </span>
          )}
        </button>

        {/* Clear all */}
        {hasActiveFilters && (
          <button
            onClick={handleClearAll}
            className="flex items-center gap-1 px-2 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <X className="w-3 h-3" />
            Clear all
          </button>
        )}

        {/* Result count */}
        {hasActiveFilters && (
          <span className="text-xs text-zinc-500 whitespace-nowrap">
            {resultCount} of {totalCount} items
          </span>
        )}
      </div>

      {/* Filter panels */}
      {showFilters && (
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-lg p-4 space-y-4">
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
                        ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300'
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
                        ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300'
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
                        ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300'
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
                           focus:outline-none focus:border-cyan-500"
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
            />
          )}
          {filters.types.map(type => {
            const config = ISSUE_TYPES.find(t => t.type === type);
            return (
              <FilterChip
                key={type}
                label={`${config?.icon || ''} ${config?.label || type}`}
                onRemove={() => handleToggleType(type)}
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
              />
            );
          })}
          {filters.dateField && (filters.dateRange.start || filters.dateRange.end) && (
            <FilterChip
              label={`Date: ${DATE_FILTER_OPTIONS.find(d => d.field === filters.dateField)?.label || filters.dateField}`}
              onRemove={() => handleDateFieldChange(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded-md text-xs text-zinc-300">
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
 * Apply feature search filters to a flat list of issues.
 * Returns the set of matching issue IDs (includes ancestors to maintain tree structure).
 */
export function applyFeatureSearchFilters(
  issues: Array<{ id: string; parentId?: string; title: string; key: string; description?: string; type: string; status: string; priority: string; createdAt: string; updatedAt: string; dueDate?: string; startedAt?: string; completedAt?: string }>,
  filters: FeatureSearchFilters,
): Set<string> {
  const hasAnyFilter = filters.query ||
    filters.types.length > 0 ||
    filters.statuses.length > 0 ||
    filters.priorities.length > 0 ||
    (filters.dateField && (filters.dateRange.start || filters.dateRange.end));

  if (!hasAnyFilter) {
    return new Set(issues.map(i => i.id));
  }

  // Step 1: Find all directly matching issues
  const directMatches = new Set<string>();

  for (const issue of issues) {
    let matches = true;

    // Text search
    if (filters.query) {
      const q = filters.query.toLowerCase();
      const textMatch =
        issue.title.toLowerCase().includes(q) ||
        issue.key.toLowerCase().includes(q) ||
        (issue.description?.toLowerCase().includes(q) ?? false);
      if (!textMatch) matches = false;
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

  // Step 3: Include all descendants of matching issues (so matched parent shows its tree)
  // Only for text search - filter by type/status/priority should not auto-expand children
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

  return visibleIds;
}
