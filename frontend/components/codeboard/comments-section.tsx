'use client';

/**
 * Comments Section Component
 * Displays comment list and new comment form for issues
 */

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, MessageSquare } from 'lucide-react';
import { formatRelativeTime } from '@/lib/utils';
import type { Comment } from '@/types/codeboard';

const API_BASE = '/api/codeboard';

interface CommentsSectionProps {
  issueId: string;
}

export function CommentsSection({ issueId }: CommentsSectionProps) {
  const [newComment, setNewComment] = useState('');
  const queryClient = useQueryClient();

  // Fetch comments
  const { data: comments, isLoading, error } = useQuery<Comment[]>({
    queryKey: ['comments', issueId],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/issues/${issueId}/comments`);
      if (!res.ok) throw new Error('Failed to fetch comments');
      return res.json();
    },
    enabled: !!issueId,
  });

  // Add comment mutation
  const addComment = useMutation({
    mutationFn: async (content: string) => {
      const res = await fetch(`${API_BASE}/issues/${issueId}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error('Failed to add comment');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', issueId] });
      setNewComment('');
    },
  });

  // Handle submit
  const handleSubmit = useCallback(() => {
    const trimmedComment = newComment.trim();
    if (trimmedComment) {
      addComment.mutate(trimmedComment);
    }
  }, [newComment, addComment]);

  // Handle keyboard shortcut (Cmd/Ctrl + Enter)
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  // Get author initials for avatar
  const getInitials = (name: string): string => {
    return name
      .split(' ')
      .map(part => part[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <div className="space-y-4">
      {/* Comment list */}
      <div className="space-y-4 max-h-[400px] overflow-y-auto">
        {isLoading ? (
          // Loading skeletons
          [1, 2].map(i => (
            <div key={i} className="flex gap-3 animate-pulse">
              <div className="h-8 w-8 rounded-full bg-zinc-700" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-1/4 bg-zinc-700 rounded" />
                <div className="h-12 w-full bg-zinc-700 rounded" />
              </div>
            </div>
          ))
        ) : error ? (
          <p className="text-center text-red-400 py-4">
            Failed to load comments
          </p>
        ) : comments?.length === 0 ? (
          <div className="text-center py-8">
            <MessageSquare className="h-8 w-8 text-zinc-600 mx-auto mb-2" />
            <p className="text-zinc-500">
              No comments yet. Be the first to comment!
            </p>
          </div>
        ) : (
          comments?.map(comment => (
            <div key={comment.id} className="flex gap-3">
              {/* Avatar */}
              <div className="h-8 w-8 rounded-full bg-zinc-700 flex items-center justify-center text-xs font-medium text-zinc-300 flex-shrink-0">
                {getInitials(comment.author)}
              </div>
              {/* Comment content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm text-zinc-200">
                    {comment.author}
                  </span>
                  <span className="text-xs text-zinc-500">
                    {formatRelativeTime(comment.createdAt)}
                  </span>
                </div>
                <p className="text-sm text-zinc-300 mt-1 whitespace-pre-wrap break-words">
                  {comment.content}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* New comment form */}
      <div className="border-t border-zinc-800 pt-4">
        <div className="space-y-2">
          <Textarea
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Add a comment..."
            className="min-h-[80px] resize-none"
            disabled={addComment.isPending}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">
              Cmd+Enter to submit
            </span>
            <Button
              onClick={handleSubmit}
              disabled={!newComment.trim() || addComment.isPending}
              loading={addComment.isPending}
              size="sm"
            >
              <Send className="h-4 w-4 mr-2" />
              {addComment.isPending ? 'Posting...' : 'Comment'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
