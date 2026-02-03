'use client';

/**
 * Git Sync Settings Panel
 * Allows users to configure and trigger git-to-issue linking sync
 */

import { useState } from 'react';
import {
  GitCommit,
  RefreshCw,
  Settings,
  CheckCircle,
  AlertCircle,
  Link2,
  Clock,
  Zap
} from 'lucide-react';
import {
  useSyncSettings,
  useUpdateSyncSettings,
  useSyncProject,
  useProjectLinkedCommits,
  SyncResult
} from '@/hooks/useCodeBoard';
import { cn } from '@/lib/utils';

interface GitSyncPanelProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function GitSyncPanel({ projectId, isOpen, onClose }: GitSyncPanelProps) {
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [forceFullScan, setForceFullScan] = useState(false);

  const { data: settings, isLoading: settingsLoading } = useSyncSettings(projectId);
  const { data: linkedCommits } = useProjectLinkedCommits(projectId, 20);
  const updateSettings = useUpdateSyncSettings();
  const syncProject = useSyncProject();

  if (!isOpen) return null;

  const handleSync = async () => {
    try {
      const result = await syncProject.mutateAsync({
        projectId,
        forceFullScan,
        limit: 100,
      });
      setSyncResult(result);
    } catch (error) {
      console.error('Sync failed:', error);
    }
  };

  const handleToggleAutoSync = async () => {
    if (!settings) return;
    await updateSettings.mutateAsync({
      projectId,
      settings: { autoSyncEnabled: !settings.auto_sync_enabled },
    });
  };

  const handleToggleAutoStatus = async () => {
    if (!settings) return;
    await updateSettings.mutateAsync({
      projectId,
      settings: { autoStatusUpdateEnabled: !settings.auto_status_update_enabled },
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative w-full max-w-lg bg-zinc-900 rounded-xl border border-zinc-800 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-900/30 rounded-lg">
              <GitCommit className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Git Integration</h2>
              <p className="text-xs text-zinc-500">Link commits to issues automatically</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-lg transition-colors"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Statistics */}
          {settings && (
            <div className="grid grid-cols-3 gap-4">
              <div className="p-4 bg-zinc-800/50 rounded-lg text-center">
                <div className="text-2xl font-bold text-cyan-400">
                  {settings.total_commits_linked}
                </div>
                <div className="text-xs text-zinc-500 mt-1">Commits Linked</div>
              </div>
              <div className="p-4 bg-zinc-800/50 rounded-lg text-center">
                <div className="text-2xl font-bold text-green-400">
                  {settings.total_status_updates}
                </div>
                <div className="text-xs text-zinc-500 mt-1">Status Updates</div>
              </div>
              <div className="p-4 bg-zinc-800/50 rounded-lg text-center">
                <div className="text-xs text-zinc-400">
                  {settings.last_synced_at
                    ? new Date(settings.last_synced_at).toLocaleString()
                    : 'Never'
                  }
                </div>
                <div className="text-xs text-zinc-500 mt-1">Last Synced</div>
              </div>
            </div>
          )}

          {/* Settings */}
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
              <Settings className="w-4 h-4" />
              Settings
            </h3>

            {/* Auto Sync Toggle */}
            <div className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
              <div>
                <div className="text-sm font-medium">Auto-sync on Webhook</div>
                <div className="text-xs text-zinc-500">
                  Automatically process commits from GitHub webhooks
                </div>
              </div>
              <button
                onClick={handleToggleAutoSync}
                disabled={updateSettings.isPending || settingsLoading}
                className={cn(
                  "relative w-11 h-6 rounded-full transition-colors",
                  settings?.auto_sync_enabled ? "bg-cyan-600" : "bg-zinc-700"
                )}
              >
                <span
                  className={cn(
                    "absolute top-1 w-4 h-4 rounded-full bg-white transition-transform",
                    settings?.auto_sync_enabled ? "left-6" : "left-1"
                  )}
                />
              </button>
            </div>

            {/* Auto Status Update Toggle */}
            <div className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
              <div>
                <div className="text-sm font-medium">Auto-update Issue Status</div>
                <div className="text-xs text-zinc-500">
                  Update issue status based on commit keywords (fixes, closes, implements)
                </div>
              </div>
              <button
                onClick={handleToggleAutoStatus}
                disabled={updateSettings.isPending || settingsLoading}
                className={cn(
                  "relative w-11 h-6 rounded-full transition-colors",
                  settings?.auto_status_update_enabled ? "bg-cyan-600" : "bg-zinc-700"
                )}
              >
                <span
                  className={cn(
                    "absolute top-1 w-4 h-4 rounded-full bg-white transition-transform",
                    settings?.auto_status_update_enabled ? "left-6" : "left-1"
                  )}
                />
              </button>
            </div>
          </div>

          {/* Manual Sync */}
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
              <RefreshCw className="w-4 h-4" />
              Manual Sync
            </h3>

            <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={forceFullScan}
                  onChange={(e) => setForceFullScan(e.target.checked)}
                  className="w-4 h-4 rounded border-zinc-600 bg-zinc-700 text-cyan-500 focus:ring-cyan-500"
                />
                Force full scan (rescan all commits)
              </label>
            </div>

            <button
              onClick={handleSync}
              disabled={syncProject.isPending}
              className={cn(
                "w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium transition-colors",
                syncProject.isPending
                  ? "bg-zinc-700 text-zinc-400 cursor-wait"
                  : "bg-cyan-600 hover:bg-cyan-500 text-white"
              )}
            >
              {syncProject.isPending ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Syncing...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Sync Now
                </>
              )}
            </button>

            {/* Sync Result */}
            {syncResult && (
              <div className={cn(
                "p-4 rounded-lg",
                syncResult.success ? "bg-green-900/20 border border-green-800" : "bg-red-900/20 border border-red-800"
              )}>
                {syncResult.success ? (
                  <>
                    <div className="flex items-center gap-2 text-green-400 font-medium">
                      <CheckCircle className="w-4 h-4" />
                      Sync Completed
                    </div>
                    <div className="mt-2 text-sm text-zinc-300 space-y-1">
                      <p>Commits scanned: {syncResult.commits_scanned}</p>
                      <p>New links created: {syncResult.commits_linked}</p>
                      <p>Status updates: {syncResult.status_updates}</p>
                    </div>
                    {syncResult.message && (
                      <p className="mt-2 text-xs text-zinc-500">{syncResult.message}</p>
                    )}
                  </>
                ) : (
                  <>
                    <div className="flex items-center gap-2 text-red-400 font-medium">
                      <AlertCircle className="w-4 h-4" />
                      Sync Failed
                    </div>
                    {syncResult.error && (
                      <p className="mt-2 text-sm text-red-300">{syncResult.error}</p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Recent Linked Commits */}
          {linkedCommits && linkedCommits.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <Link2 className="w-4 h-4" />
                Recent Linked Commits
              </h3>
              <div className="max-h-40 overflow-y-auto space-y-2">
                {linkedCommits.slice(0, 5).map((link) => (
                  <div
                    key={link.id}
                    className="flex items-center gap-2 p-2 bg-zinc-800/50 rounded-lg text-sm"
                  >
                    <code className="text-xs text-cyan-500">{link.shortHash}</code>
                    <span className="flex-1 truncate text-zinc-300">{link.message}</span>
                    <span className={cn(
                      "text-xs px-1.5 py-0.5 rounded",
                      link.linkType === 'FIXES' && "bg-green-900/40 text-green-400",
                      link.linkType === 'CLOSES' && "bg-green-900/40 text-green-400",
                      link.linkType === 'IMPLEMENTS' && "bg-blue-900/40 text-blue-400",
                      link.linkType === 'MENTIONS' && "bg-zinc-700 text-zinc-400"
                    )}>
                      {link.linkType.toLowerCase()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Keyword Reference */}
          <div className="p-4 bg-zinc-800/30 rounded-lg text-xs text-zinc-500">
            <div className="font-medium text-zinc-400 mb-2">Commit Message Keywords</div>
            <div className="space-y-1">
              <p><code className="text-green-400">fixes CB-123</code> or <code className="text-green-400">closes CB-123</code> → marks issue as Done</p>
              <p><code className="text-blue-400">implements CB-123</code> → marks issue as In Review</p>
              <p><code className="text-zinc-400">CB-123</code> → links without status change</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
