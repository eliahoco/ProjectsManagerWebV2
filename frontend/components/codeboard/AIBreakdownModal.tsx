'use client';

/**
 * AI Breakdown Modal - Break down features into hierarchical structure
 * Creates Epics, Stories, Tasks, and Subtasks with proper parent-child relationships
 */

import { useState, useMemo } from 'react';
import { X, Sparkles, Plus, Check, Loader2, ChevronRight, ChevronDown, Layers, Code, Database, Shield, TestTube, Layout, Tag } from 'lucide-react';
import { useAIBreakdown, useCreateIssue, type SuggestedIssue } from '@/hooks/useCodeBoard';
import { ISSUE_TYPES, PRIORITIES } from '@/types/codeboard';
import type { IssueType, Priority } from '@/types/codeboard';

// Generate a unique batch ID for grouping breakdown issues
function generateBatchId(): string {
  return `batch-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

interface AIBreakdownModalProps {
  projectId: string;
  issue?: {
    id: string;
    title: string;
    description?: string;
    type: string;
  };
  onClose: () => void;
  onSuccess?: () => void;
}

// Category icons and colors
const CATEGORY_CONFIG: Record<string, { icon: typeof Code; color: string; label: string }> = {
  frontend: { icon: Layout, color: 'text-blue-400 bg-blue-500/20', label: 'Frontend' },
  backend: { icon: Code, color: 'text-green-400 bg-green-500/20', label: 'Backend' },
  database: { icon: Database, color: 'text-orange-400 bg-orange-500/20', label: 'Database' },
  security: { icon: Shield, color: 'text-red-400 bg-red-500/20', label: 'Security' },
  testing: { icon: TestTube, color: 'text-purple-400 bg-purple-500/20', label: 'Testing' },
  integration: { icon: Layers, color: 'text-cyan-400 bg-cyan-500/20', label: 'Integration' },
};

// Type hierarchy colors
const TYPE_COLORS: Record<string, string> = {
  EPIC: 'bg-purple-600 text-white',
  STORY: 'bg-green-600 text-white',
  TASK: 'bg-blue-600 text-white',
  SUBTASK: 'bg-zinc-600 text-white',
};

// Indentation levels
const INDENT_LEVELS: Record<string, number> = {
  EPIC: 0,
  STORY: 1,
  TASK: 2,
  SUBTASK: 3,
};

export function AIBreakdownModal({
  projectId,
  issue,
  onClose,
  onSuccess,
}: AIBreakdownModalProps) {
  const [title, setTitle] = useState(issue?.title || '');
  const [description, setDescription] = useState(issue?.description || '');
  const [featureTag, setFeatureTag] = useState('');  // Tag to group all issues from this breakdown
  const [suggestions, setSuggestions] = useState<SuggestedIssue[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [createdCount, setCreatedCount] = useState(0);
  const [originalInput, setOriginalInput] = useState<string>('');
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set(['EPIC', 'STORY', 'TASK', 'SUBTASK']));

  const breakdown = useAIBreakdown();
  const createIssue = useCreateIssue();

  // Group suggestions by type for summary
  const summaryByType = useMemo(() => {
    const summary: Record<string, number> = { EPIC: 0, STORY: 0, TASK: 0, SUBTASK: 0 };
    suggestions.forEach(s => {
      const type = s.type?.toUpperCase() || 'TASK';
      summary[type] = (summary[type] || 0) + 1;
    });
    return summary;
  }, [suggestions]);

  // Group suggestions by category for summary
  const summaryByCategory = useMemo(() => {
    const summary: Record<string, number> = {};
    suggestions.forEach(s => {
      const cat = s.category || 'other';
      summary[cat] = (summary[cat] || 0) + 1;
    });
    return summary;
  }, [suggestions]);

  const handleBreakdown = async () => {
    try {
      const result = await breakdown.mutateAsync({
        projectId,
        title,
        description,
        parentType: issue?.type || 'EPIC',
      });

      if (result.suggestions.length > 0) {
        setSuggestions(result.suggestions);
        setSelected(new Set(result.suggestions.map((_, i) => i)));
        if (result.original_input) {
          setOriginalInput(result.original_input);
        }
      }
    } catch (error) {
      console.error('Breakdown failed:', error);
    }
  };

  const handleCreateSelected = async () => {
    if (selected.size === 0) return;

    setCreating(true);
    setCreatedCount(0);

    // Generate batch ID for this breakdown session
    const batchId = generateBatchId();

    // Prepare labels - use feature tag if provided, otherwise use title
    const tagName = featureTag.trim() || title.trim();
    const labelsJson = tagName ? JSON.stringify([tagName]) : null;

    // Sort suggestions by hierarchy: FEATURE -> EPIC -> STORY -> TASK -> SUBTASK
    const typeOrder: Record<string, number> = { FEATURE: 0, EPIC: 1, STORY: 2, TASK: 3, SUBTASK: 4 };
    const selectedSuggestions = suggestions
      .map((s, i) => ({ ...s, originalIndex: i }))
      .filter((_, i) => selected.has(i))
      .sort((a, b) => {
        const orderA = typeOrder[a.type?.toUpperCase() as keyof typeof typeOrder] ?? 4;
        const orderB = typeOrder[b.type?.toUpperCase() as keyof typeof typeOrder] ?? 4;
        return orderA - orderB;
      });

    // Map to track created issues by title for parent lookup
    const createdIssues: Map<string, string> = new Map();
    // Track issue ID to type for parent type verification
    const issueIdToType: Map<string, string> = new Map();
    // Also track by type for fallback parent lookup
    const createdByType: Map<string, string> = new Map();
    let firstCreatedIssueId: string | null = null;

    for (const suggestion of selectedSuggestions) {
      try {
        // Find parent ID using hierarchy rules and title matching
        let parentId = issue?.id;
        const suggestionType = suggestion.type?.toUpperCase() || 'TASK';

        // Helper function to find parent by title with fuzzy matching
        // Returns undefined if parent is found but is of wrong type
        const findParentByTitle = (parentTitle: string, allowedParentTypes?: string[]): string | undefined => {
          // Try exact match first
          let foundId = createdIssues.get(parentTitle);

          // Try case-insensitive match
          if (!foundId) {
            const lowerTitle = parentTitle.toLowerCase();
            for (const [key, value] of createdIssues.entries()) {
              if (key.toLowerCase() === lowerTitle) {
                foundId = value;
                break;
              }
            }
          }

          // Try partial match (contains)
          if (!foundId) {
            const lowerTitle = parentTitle.toLowerCase();
            for (const [key, value] of createdIssues.entries()) {
              if (key.toLowerCase().includes(lowerTitle) || lowerTitle.includes(key.toLowerCase())) {
                foundId = value;
                break;
              }
            }
          }

          // Verify parent type if restrictions specified
          if (foundId && allowedParentTypes && allowedParentTypes.length > 0) {
            const foundType = issueIdToType.get(foundId);
            if (foundType && !allowedParentTypes.includes(foundType)) {
              return undefined; // Parent is wrong type, don't use it
            }
          }

          return foundId;
        };

        // Apply hierarchy-based parent resolution with type validation
        // Hierarchy: FEATURE -> EPIC -> STORY -> TASK -> SUBTASK
        if (suggestionType === 'FEATURE') {
          // Features have no parent (top level)
          parentId = undefined;
        } else if (suggestionType === 'EPIC') {
          // EPICs must be children of FEATURE only
          if (suggestion.parentTitle) {
            parentId = findParentByTitle(suggestion.parentTitle, ['FEATURE']);
          }
          // Always fall back to FEATURE if no match
          if (!parentId) {
            parentId = createdByType.get('FEATURE') || issue?.id;
          }
        } else if (suggestionType === 'STORY') {
          // STORYs must be children of EPIC (or FEATURE if no EPIC)
          if (suggestion.parentTitle) {
            parentId = findParentByTitle(suggestion.parentTitle, ['EPIC', 'FEATURE']);
          }
          // Fall back to most recent EPIC
          if (!parentId) {
            parentId = createdByType.get('EPIC') || createdByType.get('FEATURE') || issue?.id;
          }
        } else if (suggestionType === 'TASK') {
          // TASKs must be children of STORY (or EPIC if no STORY)
          // TASKs should NOT be children of other TASKs
          if (suggestion.parentTitle) {
            parentId = findParentByTitle(suggestion.parentTitle, ['STORY', 'EPIC']);
          }
          // Fall back to most recent STORY
          if (!parentId) {
            parentId = createdByType.get('STORY') || createdByType.get('EPIC') || issue?.id;
          }
        } else if (suggestionType === 'SUBTASK') {
          // SUBTASKs must be children of TASK (NOT other SUBTASKs)
          if (suggestion.parentTitle) {
            parentId = findParentByTitle(suggestion.parentTitle, ['TASK']);
          }
          // Always fall back to most recent TASK for SUBTASKs
          if (!parentId) {
            parentId = createdByType.get('TASK') || createdByType.get('STORY') || issue?.id;
          }
        } else {
          // Unknown type - try title match or use issue parent
          if (suggestion.parentTitle) {
            parentId = findParentByTitle(suggestion.parentTitle) || issue?.id;
          }
        }

        const result = await createIssue.mutateAsync({
          projectId,
          data: {
            title: suggestion.title,
            description: suggestion.description,
            type: (suggestion.type?.toUpperCase() || 'TASK') as IssueType,
            priority: (suggestion.priority?.toUpperCase() || 'MEDIUM') as Priority,
            storyPoints: suggestion.storyPoints,
            parentId,
            labels: labelsJson ?? undefined,
            breakdownBatchId: batchId,
          },
        });

        if (result?.id) {
          const type = suggestion.type?.toUpperCase() || 'TASK';

          // Store issue by title for parent lookup
          createdIssues.set(suggestion.title, result.id);

          // Store issue type for parent type validation
          issueIdToType.set(result.id, type);

          // Store by type for fallback - always update to most recent for TASK
          // (so SUBTASKs attach to the correct TASK)
          if (type === 'TASK') {
            // Always update TASK to most recent one
            createdByType.set(type, result.id);
          } else if (!createdByType.has(type)) {
            // For other types, only store the first one
            createdByType.set(type, result.id);
          }

          // Store FEATURE under user-provided title as well
          if (type === 'FEATURE' && title) {
            createdIssues.set(title, result.id);
          }

          if (!firstCreatedIssueId) {
            firstCreatedIssueId = result.id;
          }
        }

        setCreatedCount((c) => c + 1);
      } catch (error) {
        console.error('Failed to create issue:', error);
      }
    }

    // Log the original specification
    if (firstCreatedIssueId && originalInput) {
      try {
        await fetch(`/api/codeboard/issues/${firstCreatedIssueId}/log-breakdown-spec?original_spec=${encodeURIComponent(originalInput)}`, {
          method: 'POST',
        });
      } catch (error) {
        console.error('Failed to log breakdown spec:', error);
      }
    }

    setCreating(false);
    onSuccess?.();
    onClose();
  };

  const toggleSelection = (index: number) => {
    const newSelected = new Set(selected);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelected(newSelected);
  };

  const toggleAll = () => {
    if (selected.size === suggestions.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(suggestions.map((_, i) => i)));
    }
  };

  const toggleType = (type: string) => {
    const newExpanded = new Set(expandedTypes);
    if (newExpanded.has(type)) {
      newExpanded.delete(type);
    } else {
      newExpanded.add(type);
    }
    setExpandedTypes(newExpanded);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-zinc-900 rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-purple-500" />
            <h2 className="text-lg font-semibold text-white">AI Feature Breakdown</h2>
          </div>
          <button onClick={onClose} className="p-1 text-zinc-400 hover:text-white rounded">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Input Section */}
          {suggestions.length === 0 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">
                  Feature Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g., Smart Import Feature"
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">
                  Detailed Specifications
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe the feature in detail including:
• UI components and user interactions
• Backend APIs and services
• Database models and storage
• Security requirements
• Testing requirements

The more detail you provide, the better the breakdown will be."
                  rows={10}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none font-mono text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">
                  <span className="flex items-center gap-1">
                    <Tag className="h-4 w-4" />
                    Feature Tag (for filtering)
                  </span>
                </label>
                <input
                  type="text"
                  value={featureTag}
                  onChange={(e) => setFeatureTag(e.target.value)}
                  placeholder={title || "e.g., Import Feature, User Auth, Dashboard v2"}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <p className="text-xs text-zinc-500 mt-1">
                  All created issues will be tagged with this label for easy filtering. Defaults to feature title if empty.
                </p>
              </div>

              <button
                onClick={handleBreakdown}
                disabled={!title.trim() || breakdown.isPending}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-zinc-700 disabled:cursor-not-allowed text-white rounded-md transition-colors"
              >
                {breakdown.isPending ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Analyzing with AI (this may take a moment)...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-5 w-5" />
                    Generate Hierarchical Breakdown
                  </>
                )}
              </button>

              {breakdown.isError && (
                <p className="text-sm text-red-400">
                  Failed to analyze feature. Please try again.
                </p>
              )}
            </div>
          )}

          {/* Suggestions Section */}
          {suggestions.length > 0 && (
            <div className="space-y-4">
              {/* Summary */}
              <div className="flex flex-wrap items-center gap-4 p-3 bg-zinc-800 rounded-lg">
                <span className="text-sm text-zinc-400">Generated:</span>
                {Object.entries(summaryByType).map(([type, count]) => count > 0 && (
                  <span key={type} className={`text-xs px-2 py-1 rounded ${TYPE_COLORS[type] || 'bg-zinc-700'}`}>
                    {count} {type}{count > 1 ? 's' : ''}
                  </span>
                ))}
                <span className="text-zinc-600">|</span>
                {Object.entries(summaryByCategory).map(([cat, count]) => {
                  const config = CATEGORY_CONFIG[cat];
                  if (!config) return null;
                  const Icon = config.icon;
                  return (
                    <span key={cat} className={`text-xs px-2 py-1 rounded flex items-center gap-1 ${config.color}`}>
                      <Icon className="h-3 w-3" />
                      {count}
                    </span>
                  );
                })}
              </div>

              <div className="flex items-center justify-between">
                <p className="text-sm text-zinc-400">
                  {selected.size} of {suggestions.length} items selected
                </p>
                <button onClick={toggleAll} className="text-sm text-purple-400 hover:text-purple-300">
                  {selected.size === suggestions.length ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              {/* Hierarchical List */}
              <div className="space-y-1 max-h-[50vh] overflow-y-auto">
                {suggestions.map((suggestion, index) => {
                  const type = suggestion.type?.toUpperCase() || 'TASK';
                  const indent = INDENT_LEVELS[type] || 0;
                  const category = suggestion.category || 'other';
                  const categoryConfig = CATEGORY_CONFIG[category];
                  const CategoryIcon = categoryConfig?.icon || Code;

                  return (
                    <div
                      key={index}
                      onClick={() => toggleSelection(index)}
                      style={{ paddingLeft: `${indent * 20 + 12}px` }}
                      className={`p-2 rounded-lg border cursor-pointer transition-colors ${
                        selected.has(index)
                          ? 'bg-purple-500/10 border-purple-500/50'
                          : 'bg-zinc-800/50 border-zinc-700/50 hover:border-zinc-600'
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <div
                          className={`mt-1 w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                            selected.has(index) ? 'bg-purple-500 border-purple-500' : 'border-zinc-600'
                          }`}
                        >
                          {selected.has(index) && <Check className="h-2.5 w-2.5 text-white" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${TYPE_COLORS[type] || 'bg-zinc-700'}`}>
                              {type}
                            </span>
                            {categoryConfig && (
                              <span className={`text-xs px-1.5 py-0.5 rounded flex items-center gap-1 ${categoryConfig.color}`}>
                                <CategoryIcon className="h-3 w-3" />
                                {categoryConfig.label}
                              </span>
                            )}
                            <span className="font-medium text-white text-sm truncate">
                              {suggestion.title}
                            </span>
                          </div>
                          {suggestion.description && (
                            <p className="text-xs text-zinc-500 mt-1 line-clamp-2">
                              {suggestion.description}
                            </p>
                          )}
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              PRIORITIES.find(p => p.priority === suggestion.priority?.toUpperCase())?.color || 'bg-zinc-700'
                            }`}>
                              {suggestion.priority}
                            </span>
                            {suggestion.storyPoints && (
                              <span className="text-xs text-zinc-500">{suggestion.storyPoints} pts</span>
                            )}
                            {suggestion.parentTitle && (
                              <span className="text-xs text-zinc-600">→ {suggestion.parentTitle}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-4 border-t border-zinc-800">
          {suggestions.length > 0 ? (
            <>
              <button
                onClick={() => setSuggestions([])}
                className="px-4 py-2 text-zinc-400 hover:text-white transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleCreateSelected}
                disabled={selected.size === 0 || creating}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-zinc-700 disabled:cursor-not-allowed text-white rounded-md transition-colors"
              >
                {creating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Creating {createdCount}/{selected.size}...
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4" />
                    Create {selected.size} Issue{selected.size !== 1 ? 's' : ''}
                  </>
                )}
              </button>
            </>
          ) : (
            <button
              onClick={onClose}
              className="px-4 py-2 text-zinc-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
