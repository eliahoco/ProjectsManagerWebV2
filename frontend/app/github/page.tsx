'use client';

/**
 * GitHub Page - Git operations across all projects
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { GitBranch, GitCommit, RefreshCw, Upload, Download, AlertCircle, CheckCircle, Settings, User, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';

interface Project {
  id: string;
  name: string;
  path: string;
  gitStatus?: {
    hasGit: boolean;
    hasRemote: boolean;
    branch: string;
    isDirty: boolean;
    uncommittedFiles: number;
    aheadBy: number;
    behindBy: number;
  };
}

interface GitConfig {
  gitInstalled: boolean;
  gitVersion: string;
  globalConfig: {
    username: string;
    email: string;
  };
  savedConfig: {
    username: string;
    email: string;
    hasToken: boolean;
  };
}

export default function GitHubPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [gitConfig, setGitConfig] = useState<GitConfig | null>(null);
  const toast = useToast();

  const fetchGitConfig = async () => {
    try {
      const res = await fetch('/api/github/test');
      const data = await res.json();
      if (data.success) {
        setGitConfig(data.data);
      }
    } catch (error) {
      console.error('Failed to fetch git config:', error);
    }
  };

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/projects');
      const data = await res.json();
      if (data.success) {
        // Filter only projects with git
        const gitProjects = data.data.projects.filter((p: Project) => p.gitStatus?.hasGit);
        setProjects(gitProjects);
      }
    } catch (error) {
      console.error('Failed to fetch projects:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGitConfig();
    fetchProjects();
  }, []);

  const handlePush = async (projectId: string, projectName: string) => {
    setSyncing(projectId);
    try {
      const res = await fetch('/api/github/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId, action: 'push' }),
      });
      const data = await res.json();
      if (data.success) {
        toast.success('Push Successful', `${projectName} pushed to remote`);
        await fetchProjects();
      } else {
        toast.error('Push Failed', data.error || 'Failed to push');
      }
    } catch (error) {
      toast.error('Push Failed', 'Network error');
    } finally {
      setSyncing(null);
    }
  };

  const handlePull = async (projectId: string, projectName: string) => {
    setSyncing(projectId);
    try {
      const res = await fetch('/api/github/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId, action: 'pull' }),
      });
      const data = await res.json();
      if (data.success) {
        toast.success('Pull Successful', `${projectName} updated from remote`);
        await fetchProjects();
      } else {
        toast.error('Pull Failed', data.error || 'Failed to pull');
      }
    } catch (error) {
      toast.error('Pull Failed', 'Network error');
    } finally {
      setSyncing(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white dark:text-white flex items-center gap-3">
            <GitBranch className="h-7 w-7 text-cyan-500" />
            GitHub Sync
          </h1>
          <p className="text-zinc-400 mt-1">
            Manage git operations across all projects
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchProjects}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Git Configuration Status */}
      <div className="bg-zinc-900 dark:bg-zinc-900 border border-zinc-800 dark:border-zinc-800 rounded-lg p-4 mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <Settings className="h-5 w-5 text-zinc-400" />
            </div>
            <div>
              <h3 className="font-medium text-white dark:text-white">Git Configuration</h3>
              {gitConfig?.globalConfig?.username ? (
                <div className="flex items-center gap-4 mt-1 text-sm">
                  <span className="text-zinc-400 flex items-center gap-1">
                    <User className="h-3 w-3" />
                    {gitConfig.globalConfig.username}
                  </span>
                  <span className="text-zinc-400 flex items-center gap-1">
                    <Mail className="h-3 w-3" />
                    {gitConfig.globalConfig.email}
                  </span>
                  {gitConfig.savedConfig?.hasToken && (
                    <span className="text-green-400 flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" />
                      Token saved
                    </span>
                  )}
                </div>
              ) : (
                <p className="text-sm text-yellow-400 mt-1 flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" />
                  Git credentials not configured
                </p>
              )}
            </div>
          </div>
          <Link href="/settings">
            <Button variant="outline" size="sm">
              <Settings className="h-4 w-4" />
              Configure
            </Button>
          </Link>
        </div>
      </div>

      {/* Projects List */}
      <div className="space-y-4">
        {projects.length === 0 ? (
          <div className="text-center py-12 text-zinc-500">
            No git repositories found
          </div>
        ) : (
          projects.map((project) => (
            <div
              key={project.id}
              className="bg-zinc-900 dark:bg-zinc-900 border border-zinc-800 dark:border-zinc-800 rounded-lg p-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div>
                    <h3 className="font-medium text-white dark:text-white">{project.name}</h3>
                    <div className="flex items-center gap-3 mt-1 text-sm">
                      <span className="text-zinc-400 flex items-center gap-1">
                        <GitBranch className="h-3 w-3" />
                        {project.gitStatus?.branch || 'main'}
                      </span>
                      {project.gitStatus?.hasRemote ? (
                        <span className="text-green-400 flex items-center gap-1">
                          <CheckCircle className="h-3 w-3" />
                          Remote
                        </span>
                      ) : (
                        <span className="text-zinc-500 flex items-center gap-1">
                          <AlertCircle className="h-3 w-3" />
                          No remote
                        </span>
                      )}
                      {project.gitStatus?.isDirty && (
                        <span className="text-yellow-400 flex items-center gap-1">
                          <GitCommit className="h-3 w-3" />
                          {project.gitStatus.uncommittedFiles} changes
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePush(project.id, project.name)}
                    disabled={!project.gitStatus?.hasRemote || syncing === project.id}
                    loading={syncing === project.id}
                  >
                    <Upload className="h-4 w-4" />
                    Push
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePull(project.id, project.name)}
                    disabled={!project.gitStatus?.hasRemote || syncing === project.id}
                    loading={syncing === project.id}
                  >
                    <Download className="h-4 w-4" />
                    Pull
                  </Button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
