'use client';

/**
 * Search bar component for Issue Detail modal
 * Allows users to filter content within the issue detail view
 */

import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface IssueSearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  resultCount?: number;
  showResultCount?: boolean;
}

export function IssueSearchBar({
  value,
  onChange,
  placeholder = 'Search in this issue...',
  className,
  resultCount,
  showResultCount = true,
}: IssueSearchBarProps) {
  return (
    <div className={cn('relative', className)}>
      <div className="relative flex items-center">
        <Search className="absolute left-3 w-4 h-4 text-zinc-500 pointer-events-none" />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full pl-10 pr-10 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                     placeholder:text-zinc-500 focus:outline-none focus:border-cyan-500 transition-colors"
        />
        {value && (
          <button
            onClick={() => onChange('')}
            className="absolute right-3 p-0.5 text-zinc-500 hover:text-zinc-300 transition-colors"
            title="Clear search"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
      {showResultCount && value && resultCount !== undefined && (
        <div className="absolute right-10 top-1/2 -translate-y-1/2 text-xs text-zinc-500">
          {resultCount} {resultCount === 1 ? 'match' : 'matches'}
        </div>
      )}
    </div>
  );
}

/**
 * Helper function to highlight matching text in a string
 */
export function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;

  const regex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
  const parts = text.split(regex);

  return parts.map((part, index) => {
    if (part.toLowerCase() === query.toLowerCase()) {
      return (
        <mark key={index} className="bg-cyan-500/30 text-cyan-300 rounded px-0.5">
          {part}
        </mark>
      );
    }
    return part;
  });
}

/**
 * Escape special regex characters in a string
 */
function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Check if a string matches the search query
 */
export function matchesSearch(text: string | undefined | null, query: string): boolean {
  if (!text || !query.trim()) return true;
  return text.toLowerCase().includes(query.toLowerCase());
}
