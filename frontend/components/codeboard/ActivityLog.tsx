'use client';

/**
 * Activity Log Component - displays timeline of changes and events for an issue
 */

import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  MessageSquare,
  GitCommit,
  Edit2,
  Plus,
  User,
  Tag,
  AlertCircle,
  Clock,
} from 'lucide-react';
import { Activity } from '@/types/codeboard';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRelativeTime } from '@/lib/utils';

const API_BASE = '/api/codeboard';

// Map action types to icons
const ACTION_ICONS: Record<string, React.ReactNode> = {
  status_changed: <ArrowRight className="h-4 w-4" />,
  comment_added: <MessageSquare className="h-4 w-4" />,
  commit_linked: <GitCommit className="h-4 w-4" />,
  description_changed: <Edit2 className="h-4 w-4" />,
  created: <Plus className="h-4 w-4" />,
  assigned: <User className="h-4 w-4" />,
  priority_changed: <AlertCircle className="h-4 w-4" />,
  type_changed: <Tag className="h-4 w-4" />,
  estimate_changed: <Clock className="h-4 w-4" />,
};

// Map action types to background colors
const ACTION_COLORS: Record<string, string> = {
  status_changed: 'bg-blue-900/50 text-blue-400',
  comment_added: 'bg-green-900/50 text-green-400',
  commit_linked: 'bg-purple-900/50 text-purple-400',
  description_changed: 'bg-yellow-900/50 text-yellow-400',
  created: 'bg-cyan-900/50 text-cyan-400',
  assigned: 'bg-orange-900/50 text-orange-400',
  priority_changed: 'bg-red-900/50 text-red-400',
  type_changed: 'bg-pink-900/50 text-pink-400',
  estimate_changed: 'bg-zinc-700 text-zinc-400',
};

interface ActivityLogProps {
  issueId: string;
}

function getActivityIcon(action: string): React.ReactNode {
  // Normalize the action string to match our icons
  const normalizedAction = action.toLowerCase().replace(/\s+/g, '_');
  return ACTION_ICONS[normalizedAction] || <Edit2 className="h-4 w-4" />;
}

function getActivityColor(action: string): string {
  const normalizedAction = action.toLowerCase().replace(/\s+/g, '_');
  return ACTION_COLORS[normalizedAction] || 'bg-zinc-800 text-zinc-400';
}

function formatActivityDescription(activity: Activity): React.ReactNode {
  const { action, field, oldValue, newValue } = activity;

  // Build a more descriptive message based on available data
  if (field && oldValue && newValue) {
    return (
      <>
        changed <span className="font-medium text-zinc-300">{field}</span> from{' '}
        <span className="font-medium text-red-400/70 line-through">{oldValue}</span> to{' '}
        <span className="font-medium text-green-400">{newValue}</span>
      </>
    );
  }

  if (field && newValue && !oldValue) {
    return (
      <>
        set <span className="font-medium text-zinc-300">{field}</span> to{' '}
        <span className="font-medium text-green-400">{newValue}</span>
      </>
    );
  }

  // Default to the action string
  return action;
}

async function fetchActivities(issueId: string): Promise<Activity[]> {
  const res = await fetch(`${API_BASE}/issues/${issueId}/activities`);
  if (!res.ok) throw new Error('Failed to fetch activities');
  return res.json();
}

export function ActivityLog({ issueId }: ActivityLogProps) {
  const { data: activities, isLoading, error } = useQuery({
    queryKey: ['issue-activities', issueId],
    queryFn: () => fetchActivities(issueId),
    enabled: !!issueId,
    staleTime: 30000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="flex gap-3">
            <Skeleton className="h-8 w-8 rounded-full flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/4" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-red-400 p-4 bg-red-900/20 rounded-lg border border-red-800/50">
        Failed to load activity history
      </div>
    );
  }

  if (!activities || activities.length === 0) {
    return (
      <div className="text-sm text-zinc-500 p-4 text-center">
        No activity recorded yet
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {activities.map((activity, index) => (
        <div key={activity.id} className="flex gap-3 relative">
          {/* Timeline connector line */}
          {index < activities.length - 1 && (
            <div className="absolute left-4 top-8 bottom-0 w-px bg-zinc-800 -translate-x-1/2" />
          )}

          {/* Icon */}
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-full flex-shrink-0 ${getActivityColor(
              activity.action
            )}`}
          >
            {getActivityIcon(activity.action)}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-zinc-300">
              <span className="font-medium text-zinc-100">{activity.actor}</span>
              {' '}
              {formatActivityDescription(activity)}
            </p>
            <p className="text-xs text-zinc-500 mt-0.5">
              {formatRelativeTime(activity.createdAt)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
