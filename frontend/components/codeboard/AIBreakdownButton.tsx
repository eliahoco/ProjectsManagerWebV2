'use client';

/**
 * AI Breakdown Button - Opens a dialog to break down features using AI
 */

import { useState } from 'react';
import { Sparkles, Loader2, X, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { breakdownFeature, type SuggestedIssue } from '@/lib/api/ai';
import { ISSUE_TYPES, PRIORITIES } from '@/types/codeboard';

interface AIBreakdownButtonProps {
  projectId: string;
  onComplete: () => void;
}

export function AIBreakdownButton({ projectId, onComplete }: AIBreakdownButtonProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [autoCreate, setAutoCreate] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<{
    suggestions: SuggestedIssue[];
    issues_created: string[];
    total_tasks: number;
    estimated_hours: number;
  } | null>(null);

  const handleBreakdown = async () => {
    setIsLoading(true);
    try {
      const data = await breakdownFeature({
        project_id: projectId,
        feature_title: title,
        feature_description: description,
        auto_create: autoCreate,
      });
      setResult(data);
      if (autoCreate) {
        onComplete();
      }
    } catch (error) {
      console.error('Breakdown failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setOpen(false);
    setTitle('');
    setDescription('');
    setResult(null);
  };

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Sparkles className="h-4 w-4 mr-2 text-purple-500" />
        AI Breakdown
      </Button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-zinc-900 rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-zinc-800">
              <div>
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-purple-500" />
                  AI Feature Breakdown
                </h2>
                <p className="text-sm text-zinc-400 mt-1">
                  Describe a feature and let AI break it down into epics, stories, and tasks.
                </p>
              </div>
              <button
                onClick={handleClose}
                className="p-1 text-zinc-400 hover:text-white rounded"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {!result ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-1">
                      Feature Title
                    </label>
                    <input
                      type="text"
                      placeholder="Feature title"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-zinc-300 mb-1">
                      Description
                    </label>
                    <Textarea
                      placeholder="Describe the feature in detail..."
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={6}
                      className="focus:ring-purple-500 focus:border-purple-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="auto-create"
                      checked={autoCreate}
                      onChange={(e) => setAutoCreate(e.target.checked)}
                      className="h-4 w-4 rounded border-zinc-600 bg-zinc-800 text-purple-500 focus:ring-purple-500 focus:ring-offset-zinc-900"
                    />
                    <label htmlFor="auto-create" className="text-sm text-zinc-300">
                      Automatically create issues
                    </label>
                  </div>
                  <Button
                    onClick={handleBreakdown}
                    disabled={!title || !description || isLoading}
                    className="w-full bg-purple-600 hover:bg-purple-700"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Breaking down...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Generate Breakdown
                      </>
                    )}
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="p-4 bg-green-900/30 border border-green-700/50 rounded-lg">
                    <p className="font-medium text-green-400 flex items-center gap-2">
                      <Check className="h-4 w-4" />
                      Breakdown Complete!
                    </p>
                    <p className="text-sm text-zinc-400 mt-1">
                      Created {result.issues_created.length} issues
                      ({result.total_tasks} tasks, ~{result.estimated_hours}h estimated)
                    </p>
                  </div>

                  {/* Show breakdown preview */}
                  {result.suggestions.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-zinc-300">Generated Issues:</p>
                      <div className="space-y-2 max-h-64 overflow-y-auto">
                        {result.suggestions.map((suggestion, index) => (
                          <div
                            key={index}
                            className="p-3 bg-zinc-800 border border-zinc-700 rounded-lg"
                          >
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-white text-sm">
                                {suggestion.title}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                              <span
                                className={`text-xs px-2 py-0.5 rounded ${
                                  ISSUE_TYPES.find((t) => t.type === suggestion.type)?.color ||
                                  'bg-zinc-700'
                                }`}
                              >
                                {suggestion.type}
                              </span>
                              <span
                                className={`text-xs px-2 py-0.5 rounded ${
                                  PRIORITIES.find((p) => p.priority === suggestion.priority)
                                    ?.color || 'bg-zinc-700'
                                }`}
                              >
                                {suggestion.priority}
                              </span>
                              {suggestion.storyPoints && (
                                <span className="text-xs text-zinc-400">
                                  {suggestion.storyPoints} pts
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex justify-end">
                    <Button variant="outline" onClick={handleClose}>
                      Close
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
