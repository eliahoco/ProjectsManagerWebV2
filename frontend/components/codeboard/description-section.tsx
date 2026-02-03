'use client';

/**
 * Description Section Component
 * Renders Markdown description with inline editing capabilities
 */

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Edit2, Check, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface DescriptionSectionProps {
  description?: string;
  onSave: (description: string) => void;
}

export function DescriptionSection({ description, onSave }: DescriptionSectionProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(description || '');

  // Sync editValue when description prop changes
  useEffect(() => {
    if (!isEditing) {
      setEditValue(description || '');
    }
  }, [description, isEditing]);

  const handleSave = useCallback(() => {
    onSave(editValue);
    setIsEditing(false);
  }, [editValue, onSave]);

  const handleCancel = useCallback(() => {
    setEditValue(description || '');
    setIsEditing(false);
  }, [description]);

  // Handle keyboard shortcuts
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl/Cmd + Enter to save
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    }
    // Escape to cancel
    if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    }
  }, [handleSave, handleCancel]);

  if (isEditing) {
    return (
      <div className="space-y-2">
        <Textarea
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a description... (Markdown supported)"
          className="min-h-[200px] font-mono text-sm"
          autoFocus
        />
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={handleSave}>
            <Check className="h-4 w-4 mr-1" />
            Save
          </Button>
          <Button size="sm" variant="outline" onClick={handleCancel}>
            <X className="h-4 w-4 mr-1" />
            Cancel
          </Button>
          <span className="text-xs text-zinc-500 ml-2">
            Ctrl+Enter to save, Esc to cancel
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="group relative">
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-0 top-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={() => setIsEditing(true)}
        title="Edit description"
      >
        <Edit2 className="h-4 w-4" />
      </Button>
      {description ? (
        <div className="prose prose-sm prose-invert max-w-none prose-headings:text-zinc-200 prose-p:text-zinc-300 prose-a:text-cyan-400 prose-strong:text-zinc-200 prose-code:text-cyan-400 prose-code:bg-zinc-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-zinc-800 prose-pre:border prose-pre:border-zinc-700 prose-blockquote:border-l-cyan-500 prose-blockquote:text-zinc-400 prose-li:text-zinc-300">
          <ReactMarkdown>{description}</ReactMarkdown>
        </div>
      ) : (
        <p
          className="text-zinc-500 cursor-pointer hover:text-zinc-300 transition-colors py-2"
          onClick={() => setIsEditing(true)}
        >
          Click to add a description...
        </p>
      )}
    </div>
  );
}
