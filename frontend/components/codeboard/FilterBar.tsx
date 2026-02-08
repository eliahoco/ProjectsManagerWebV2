'use client';

/**
 * Filter Bar Component - filters and sorting for the Kanban board
 */

import { useState, forwardRef } from 'react';
import { Search, Filter, X, ArrowUpDown, ArrowUp, ArrowDown, Sparkles, Tag, Calendar } from 'lucide-react';
import { ISSUE_TYPES, PRIORITIES, SORT_OPTIONS, DATE_FILTER_OPTIONS, SortField, SortOrder, DateFilterField } from '@/types/codeboard';
import { DateRangePicker, type DateRange } from '@/components/ui/date-range-picker';
import { cn } from '@/lib/utils';
import { formatShortcut, SHORTCUTS } from '@/hooks/use-keyboard-shortcuts';

interface FilterBarProps {
  onSearchChange: (search: string) => void;
  onTypeChange: (type: string | null) => void;
  onPriorityChange: (priority: string | null) => void;
  onLabelChange?: (label: string | null) => void;
  onSortChange: (field: SortField, order: SortOrder) => void;
  onSemanticSearchClick?: () => void;
  onDateRangeChange?: (field: DateFilterField | null, range: DateRange) => void;
  search: string;
  selectedType: string | null;
  selectedPriority: string | null;
  selectedLabel?: string | null;
  availableLabels?: string[];
  sortField: SortField;
  sortOrder: SortOrder;
  dateFilterField?: DateFilterField | null;
  dateRange?: DateRange;
}

export const FilterBar = forwardRef<HTMLInputElement, FilterBarProps>(function FilterBar({
  onSearchChange,
  onTypeChange,
  onPriorityChange,
  onLabelChange,
  onSortChange,
  onSemanticSearchClick,
  onDateRangeChange,
  search,
  selectedType,
  selectedPriority,
  selectedLabel,
  availableLabels = [],
  sortField,
  sortOrder,
  dateFilterField,
  dateRange,
}, ref) {
  const [showFilters, setShowFilters] = useState(false);

  const hasDateFilter = dateFilterField && (dateRange?.start || dateRange?.end);
  const hasFilters = selectedType || selectedPriority || selectedLabel || search || hasDateFilter;

  const toggleSortOrder = () => {
    onSortChange(sortField, sortOrder === 'asc' ? 'desc' : 'asc');
  };

  const handleSortFieldChange = (field: SortField) => {
    onSortChange(field, sortOrder);
  };

  const clearFilters = () => {
    onSearchChange('');
    onTypeChange(null);
    onPriorityChange(null);
    onLabelChange?.(null);
    onDateRangeChange?.(null, { start: null, end: null });
  };

  return (
    <div className="flex items-center gap-3">
      {/* Search */}
      <div className="relative flex-1 max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
        <input
          ref={ref}
          type="text"
          placeholder={`Search issues... (${formatShortcut(SHORTCUTS.FOCUS_SEARCH)})`}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                     placeholder:text-zinc-500 focus:outline-none focus:border-cyan-500 transition-colors"
        />
      </div>

      {/* Semantic Search Button */}
      {onSemanticSearchClick && (
        <button
          onClick={onSemanticSearchClick}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors
                     bg-purple-600/20 border-purple-500/50 text-purple-400 hover:bg-purple-600/30 hover:border-purple-500"
          title="Open semantic search (AI-powered)"
        >
          <Sparkles className="w-4 h-4" />
          <span className="text-sm">AI Search</span>
        </button>
      )}

      {/* Filter Toggle */}
      <button
        onClick={() => setShowFilters(!showFilters)}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors',
          showFilters
            ? 'bg-cyan-500/20 border-cyan-500 text-cyan-500'
            : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200'
        )}
      >
        <Filter className="w-4 h-4" />
        <span className="text-sm">Filters</span>
        {hasFilters && (
          <span className="w-2 h-2 bg-cyan-500 rounded-full" />
        )}
      </button>

      {/* Clear Filters */}
      {hasFilters && (
        <button
          onClick={clearFilters}
          className="flex items-center gap-1 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
        >
          <X className="w-3 h-3" />
          Clear
        </button>
      )}

      {/* Sort Controls */}
      <div className="flex items-center gap-1 border-l border-zinc-700 pl-3 ml-1">
        <ArrowUpDown className="w-4 h-4 text-zinc-500" />
        <select
          value={sortField}
          onChange={(e) => handleSortFieldChange(e.target.value as SortField)}
          className="px-2 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                     focus:outline-none focus:border-cyan-500"
        >
          {SORT_OPTIONS.map(option => (
            <option key={option.field} value={option.field}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          onClick={toggleSortOrder}
          className={cn(
            'p-2 rounded-lg border transition-colors',
            'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600'
          )}
          title={sortOrder === 'asc' ? 'Ascending (click to change)' : 'Descending (click to change)'}
        >
          {sortOrder === 'asc' ? (
            <ArrowUp className="w-4 h-4" />
          ) : (
            <ArrowDown className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Filter Dropdowns */}
      {showFilters && (
        <div className="flex items-center gap-2">
          {/* Type Filter */}
          <select
            value={selectedType || ''}
            onChange={(e) => onTypeChange(e.target.value || null)}
            className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                       focus:outline-none focus:border-cyan-500"
          >
            <option value="">All Types</option>
            {ISSUE_TYPES.map(type => (
              <option key={type.type} value={type.type}>
                {type.icon} {type.label}
              </option>
            ))}
          </select>

          {/* Priority Filter */}
          <select
            value={selectedPriority || ''}
            onChange={(e) => onPriorityChange(e.target.value || null)}
            className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                       focus:outline-none focus:border-cyan-500"
          >
            <option value="">All Priorities</option>
            {PRIORITIES.map(p => (
              <option key={p.priority} value={p.priority}>
                {p.label}
              </option>
            ))}
          </select>

          {/* Label/Tag Filter */}
          {availableLabels.length > 0 && onLabelChange && (
            <div className="flex items-center gap-1">
              <Tag className="w-4 h-4 text-zinc-500" />
              <select
                value={selectedLabel || ''}
                onChange={(e) => onLabelChange(e.target.value || null)}
                className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-cyan-500"
              >
                <option value="">All Labels</option>
                {availableLabels.map(label => (
                  <option key={label} value={label}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Date Range Filter */}
          {onDateRangeChange && (
            <div className="flex items-center gap-1">
              <select
                value={dateFilterField || ''}
                onChange={(e) => {
                  const field = e.target.value as DateFilterField | '';
                  onDateRangeChange(field || null, dateRange || { start: null, end: null });
                }}
                className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-cyan-500"
              >
                <option value="">Date Field</option>
                {DATE_FILTER_OPTIONS.map(opt => (
                  <option key={opt.field} value={opt.field}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {dateFilterField && (
                <DateRangePicker
                  value={dateRange || { start: null, end: null }}
                  onChange={(range) => onDateRangeChange(dateFilterField, range)}
                  placeholder="Select range..."
                  showPresets={true}
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
