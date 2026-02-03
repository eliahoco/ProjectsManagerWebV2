'use client';

/**
 * Issue Detail Page - Shows full details for any issue type
 */

import { useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useIssue, useIssues, useUpdateIssue, useDeleteIssue, useIssueActivities, useLinkedCommits, useIssueCommits, useComments, useAddComment } from '@/hooks/useCodeBoard';
import { IssueDetailTemplate, getDefaultTabs } from '@/components/codeboard/IssueDetailTemplate';
import { Issue } from '@/types/codeboard';

export default function IssueDetailPage() {
  const params = useParams();
  const router = useRouter();
  const issueId = params.id as string;

  // State
  const [activeTab, setActiveTab] = useState('details');
  const [isEditing, setIsEditing] = useState(false);

  // Fetch the issue
  const { data: issue, isLoading: issueLoading, error: issueError, refetch: refetchIssue } = useIssue(issueId);

  // Fetch all issues for the project to find children and parent
  const { data: issuesData } = useIssues(issue?.projectId || null, { pageSize: 1000 });

  // Fetch activities
  const { data: activities } = useIssueActivities(issueId);

  // Fetch linked commits (from commit linking system)
  const { data: linkedCommits } = useLinkedCommits(issueId);

  // Fetch related commits (from git log search)
  const { data: relatedCommits } = useIssueCommits(issue?.projectId || null, issue?.key || null);

  // Fetch comments
  const { data: comments, refetch: refetchComments } = useComments(issueId);

  // Mutations
  const updateIssue = useUpdateIssue();
  const deleteIssue = useDeleteIssue();
  const addComment = useAddComment();

  // Find parent and children
  const parent = useMemo(() => {
    if (!issue?.parentId || !issuesData?.items) return null;
    return issuesData.items.find(i => i.id === issue.parentId) || null;
  }, [issue, issuesData]);

  // Get ALL descendants (children, grandchildren, etc.) not just direct children
  const children = useMemo(() => {
    if (!issue || !issuesData?.items) return [];

    const allIssues = issuesData.items;
    const descendantIds = new Set<string>();

    // Recursively collect all descendants
    function collectDescendants(parentId: string) {
      allIssues.forEach(i => {
        if (i.parentId === parentId && !descendantIds.has(i.id)) {
          descendantIds.add(i.id);
          collectDescendants(i.id);
        }
      });
    }

    collectDescendants(issue.id);

    // Return all descendants sorted by type hierarchy then sequence
    const typeOrder: Record<string, number> = { 'FEATURE': 0, 'EPIC': 1, 'STORY': 2, 'TASK': 3, 'BUG': 3, 'SUBTASK': 4 };
    return allIssues
      .filter(i => descendantIds.has(i.id))
      .sort((a, b) => {
        const typeCompare = (typeOrder[a.type] ?? 99) - (typeOrder[b.type] ?? 99);
        if (typeCompare !== 0) return typeCompare;
        return a.sequence - b.sequence;
      });
  }, [issue, issuesData]);

  // Handle clicking on a child issue
  const handleChildClick = (child: Issue) => {
    router.push(`/codeboard/issue/${child.id}`);
  };

  // Handlers
  const handleUpdate = (data: Partial<Issue>) => {
    updateIssue.mutate(
      { issueId, data },
      {
        onSuccess: () => {
          refetchIssue();
          setIsEditing(false);
        },
      }
    );
  };

  const handleDelete = () => {
    if (confirm('Are you sure you want to delete this issue?')) {
      deleteIssue.mutate(issueId, {
        onSuccess: () => {
          router.push('/codeboard');
        },
      });
    }
  };

  const handleAddComment = (content: string) => {
    addComment.mutate(
      { issueId, content },
      {
        onSuccess: () => refetchComments(),
      }
    );
  };

  // Loading state
  if (issueLoading) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="max-w-6xl mx-auto">
          <div className="animate-pulse">
            <div className="h-8 bg-zinc-700 rounded w-1/3 mb-4" />
            <div className="h-4 bg-zinc-700 rounded w-2/3 mb-8" />
            <div className="grid grid-cols-3 gap-6">
              <div className="col-span-2 space-y-4">
                <div className="h-32 bg-zinc-700 rounded" />
                <div className="h-48 bg-zinc-700 rounded" />
              </div>
              <div className="space-y-4">
                <div className="h-24 bg-zinc-700 rounded" />
                <div className="h-24 bg-zinc-700 rounded" />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (issueError || !issue) {
    return (
      <div className="min-h-screen bg-zinc-900 p-6">
        <div className="max-w-6xl mx-auto text-center py-12">
          <h1 className="text-2xl font-bold text-zinc-100">
            {issueError ? 'Error loading issue' : 'Issue not found'}
          </h1>
          <p className="text-zinc-400 mt-2">
            {issueError?.message || 'The issue you are looking for does not exist.'}
          </p>
          <button
            onClick={() => router.push('/codeboard')}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Back to CodeBoard
          </button>
        </div>
      </div>
    );
  }

  return (
    <IssueDetailTemplate
      issue={issue}
      parent={parent}
      children={children}
      linkedCommits={linkedCommits || []}
      relatedCommits={relatedCommits}
      isEditing={isEditing}
      onEditToggle={setIsEditing}
      onUpdate={handleUpdate}
      onDelete={handleDelete}
      backUrl="/codeboard"
      backLabel="Back to CodeBoard"
      showSidebar={true}
      showTabs={true}
      tabs={getDefaultTabs(issue, children, linkedCommits || [], relatedCommits, handleChildClick)}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      fullPage={true}
      className="min-h-screen"
    />
  );
}
