'use client';

/**
 * Semantic Search Panel Component
 * Provides AI-powered semantic search for issues using ChromaDB embeddings
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Search,
  X,
  Sparkles,
  Loader2,
  AlertCircle,
  Database,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  FileText,
  Tag,
  Clock,
} from 'lucide-react';
import { useSemanticSearch, useFindSimilar, type SearchResult } from '@/hooks/useCodeBoard';
import { Issue, ISSUE_TYPES, STATUS_COLUMNS } from '@/types/codeboard';
import { cn } from '@/lib/utils';

interface SemanticSearchPanelProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  onIssueClick: (issue: Issue) => void;
  issues: Issue[];
}

interface IndexStats {
  project_id: string;
  indexed_count: number;
  status: 'ready' | 'empty' | 'error';
  error?: string;
}

const API_BASE = '/api/codeboard';

export function SemanticSearchPanel({
  projectId,
  isOpen,
  onClose,
  onIssueClick,
  issues,
}: SemanticSearchPanelProps) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [filterType, setFilterType] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [showFilters, setShowFilters] = useState(false);
  const [indexStats, setIndexStats] = useState<IndexStats | null>(null);
  const [isIndexing, setIsIndexing] = useState(false);
  const [indexError, setIndexError] = useState<string | null>(null);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Semantic search query
  const {
    data: searchResults,
    isLoading: isSearching,
    error: searchError,
  } = useSemanticSearch(
    projectId,
    debouncedQuery,
    {
      type: filterType,
      status: filterStatus,
      enabled: debouncedQuery.length >= 2,
    }
  );

  // Fetch index stats
  const fetchIndexStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/search/${projectId}/stats`);
      if (res.ok) {
        const stats = await res.json();
        setIndexStats(stats);
      }
    } catch (err) {
      console.error('Failed to fetch index stats:', err);
    }
  }, [projectId]);

  useEffect(() => {
    if (isOpen && projectId) {
      fetchIndexStats();
    }
  }, [isOpen, projectId, fetchIndexStats]);

  // Re-index all issues
  const handleReindex = async () => {
    setIsIndexing(true);
    setIndexError(null);
    try {
      const res = await fetch(`${API_BASE}/search/${projectId}/embed-all`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error('Failed to reindex');
      }
      const result = await res.json();
      if (!result.success) {
        setIndexError(`Indexed ${result.embedded}/${result.total} issues. ${result.failed} failed.`);
      }
      await fetchIndexStats();
    } catch (err) {
      setIndexError(err instanceof Error ? err.message : 'Reindex failed');
    } finally {
      setIsIndexing(false);
    }
  };

  // Map search results to issues
  const resultIssues = useMemo(() => {
    if (!searchResults?.results) return [];

    return searchResults.results
      .map((result: SearchResult) => {
        const issue = issues.find(i => i.id === result.issue_id);
        return issue ? { issue, score: result.score || 0 } : null;
      })
      .filter((item): item is { issue: Issue; score: number } => item !== null);
  }, [searchResults, issues]);

  // Get type info
  const getTypeInfo = (type: string) => {
    return ISSUE_TYPES.find(t => t.type === type);
  };

  // Get status info
  const getStatusInfo = (status: string) => {
    return STATUS_COLUMNS.find(s => s.status === status);
  };

  // Format score as percentage
  const formatScore = (score: number) => {
    return `${Math.round(score * 100)}%`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative w-full max-w-2xl bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2 text-purple-400">
            <Sparkles className="w-5 h-5" />
            <span className="font-medium">Semantic Search</span>
          </div>
          <div className="flex-1" />

          {/* Index Stats */}
          {indexStats && (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <Database className="w-3.5 h-3.5" />
              <span>{indexStats.indexed_count} indexed</span>
              {indexStats.status === 'error' && (
                <AlertCircle className="w-3.5 h-3.5 text-red-400" />
              )}
            </div>
          )}

          {/* Reindex Button */}
          <button
            onClick={handleReindex}
            disabled={isIndexing}
            className="flex items-center gap-1.5 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200
                       bg-zinc-800 hover:bg-zinc-700 rounded transition-colors disabled:opacity-50"
            title="Re-index all issues for semantic search"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', isIndexing && 'animate-spin')} />
            {isIndexing ? 'Indexing...' : 'Reindex'}
          </button>

          <button
            onClick={onClose}
            className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search Input */}
        <div className="p-4 border-b border-zinc-800">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search using natural language... (e.g., 'authentication issues', 'UI bugs')"
              className="w-full pl-11 pr-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-base
                         placeholder:text-zinc-500 focus:outline-none focus:border-purple-500 transition-colors"
              autoFocus
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Filters Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-2 mt-3 text-sm text-zinc-400 hover:text-zinc-200"
          >
            {showFilters ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Filters
            {(filterType || filterStatus) && (
              <span className="w-2 h-2 bg-purple-500 rounded-full" />
            )}
          </button>

          {/* Filters */}
          {showFilters && (
            <div className="flex items-center gap-3 mt-3">
              <select
                value={filterType || ''}
                onChange={(e) => setFilterType(e.target.value || undefined)}
                className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-purple-500"
              >
                <option value="">All Types</option>
                {ISSUE_TYPES.map(type => (
                  <option key={type.type} value={type.type}>
                    {type.icon} {type.label}
                  </option>
                ))}
              </select>

              <select
                value={filterStatus || ''}
                onChange={(e) => setFilterStatus(e.target.value || undefined)}
                className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm
                           focus:outline-none focus:border-purple-500"
              >
                <option value="">All Statuses</option>
                {STATUS_COLUMNS.map(status => (
                  <option key={status.status} value={status.status}>
                    {status.label}
                  </option>
                ))}
              </select>

              {(filterType || filterStatus) && (
                <button
                  onClick={() => {
                    setFilterType(undefined);
                    setFilterStatus(undefined);
                  }}
                  className="text-xs text-zinc-500 hover:text-zinc-300"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}
        </div>

        {/* Index Error */}
        {indexError && (
          <div className="mx-4 mt-4 px-3 py-2 bg-red-900/20 border border-red-800 rounded-lg text-sm text-red-400 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {indexError}
          </div>
        )}

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto">
          {/* Loading */}
          {isSearching && (
            <div className="flex items-center justify-center py-12 text-zinc-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Searching...
            </div>
          )}

          {/* Search Error */}
          {searchError && (
            <div className="flex items-center justify-center py-12 text-red-400">
              <AlertCircle className="w-5 h-5 mr-2" />
              Search failed. Please try again.
            </div>
          )}

          {/* No Query */}
          {!debouncedQuery && !isSearching && (
            <div className="py-12 text-center text-zinc-500">
              <Search className="w-8 h-8 mx-auto mb-3 opacity-50" />
              <p>Enter a search query to find related issues</p>
              <p className="text-xs mt-2 text-zinc-600">
                Uses AI embeddings for semantic similarity matching
              </p>
            </div>
          )}

          {/* Query too short */}
          {debouncedQuery && debouncedQuery.length < 2 && !isSearching && (
            <div className="py-12 text-center text-zinc-500">
              <p>Enter at least 2 characters to search</p>
            </div>
          )}

          {/* No Results */}
          {debouncedQuery.length >= 2 && !isSearching && !searchError && resultIssues.length === 0 && (
            <div className="py-12 text-center text-zinc-500">
              <FileText className="w-8 h-8 mx-auto mb-3 opacity-50" />
              <p>No matching issues found</p>
              <p className="text-xs mt-2 text-zinc-600">
                Try different keywords or check the index
              </p>
            </div>
          )}

          {/* Results List */}
          {resultIssues.length > 0 && (
            <div className="p-2">
              <div className="text-xs text-zinc-500 px-2 py-1 mb-2">
                {resultIssues.length} result{resultIssues.length !== 1 ? 's' : ''} for &quot;{debouncedQuery}&quot;
              </div>

              {resultIssues.map(({ issue, score }) => {
                const typeInfo = getTypeInfo(issue.type);
                const statusInfo = getStatusInfo(issue.status);

                return (
                  <button
                    key={issue.id}
                    onClick={() => {
                      onIssueClick(issue);
                      onClose();
                    }}
                    className="w-full text-left px-3 py-3 hover:bg-zinc-800 rounded-lg transition-colors group"
                  >
                    <div className="flex items-start gap-3">
                      {/* Type Icon */}
                      <span className="text-lg flex-shrink-0" title={typeInfo?.label}>
                        {typeInfo?.icon || '📄'}
                      </span>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-zinc-500">
                            {issue.key}
                          </span>
                          <span
                            className={cn(
                              'w-2 h-2 rounded-full flex-shrink-0',
                              statusInfo?.color || 'bg-zinc-600'
                            )}
                            title={statusInfo?.label}
                          />
                        </div>

                        <h4 className="font-medium text-zinc-200 truncate mt-0.5 group-hover:text-white">
                          {issue.title}
                        </h4>

                        {issue.description && (
                          <p className="text-sm text-zinc-500 truncate mt-1">
                            {issue.description}
                          </p>
                        )}

                        {/* Labels */}
                        {issue.labels && (
                          <div className="flex items-center gap-1 mt-2">
                            <Tag className="w-3 h-3 text-zinc-600" />
                            <span className="text-xs text-zinc-600">{issue.labels}</span>
                          </div>
                        )}
                      </div>

                      {/* Score */}
                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
                        <span
                          className={cn(
                            'text-xs font-medium px-2 py-0.5 rounded',
                            score >= 0.7
                              ? 'bg-green-900/30 text-green-400'
                              : score >= 0.5
                              ? 'bg-yellow-900/30 text-yellow-400'
                              : 'bg-zinc-800 text-zinc-400'
                          )}
                          title="Similarity score"
                        >
                          {formatScore(score)}
                        </span>
                        {issue.updatedAt && (
                          <span className="text-xs text-zinc-600 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {new Date(issue.updatedAt).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <div className="flex items-center gap-4">
              <span>
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">↑</kbd>
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400 ml-1">↓</kbd>
                <span className="ml-2">navigate</span>
              </span>
              <span>
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">↵</kbd>
                <span className="ml-2">select</span>
              </span>
              <span>
                <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">Esc</kbd>
                <span className="ml-2">close</span>
              </span>
            </div>
            <span className="text-zinc-600">
              Powered by ChromaDB embeddings
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
