'use client';

/**
 * Projects Page - Detailed project list with table view
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Play, Square, Terminal, GitBranch, ExternalLink, RefreshCw, Search, ChevronRight, AlertTriangle, X, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ImportButton } from '@/components/codeboard/ImportButton';
import { cn, getServiceTypeColor } from '@/lib/utils';
import type { ProjectWithStatus } from '@/types';

interface PortConflictInfo {
  port: number;
  service: string;
  owner: string;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ id: string; message: string } | null>(null);
  const [portConflicts, setPortConflicts] = useState<{ id: string; conflicts: PortConflictInfo[] } | null>(null);
  const [watchdogLoading, setWatchdogLoading] = useState<string | null>(null);

  const fetchProjects = async () => {
    try {
      const res = await fetch('/api/projects');
      const data = await res.json();
      if (data.success) {
        setProjects(data.data.projects);
      }
    } catch (error) {
      console.error('Failed to fetch projects:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
    const interval = setInterval(fetchProjects, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleLaunch = async (id: string) => {
    setActionLoading(id);
    setActionError(null);
    setPortConflicts(null);
    try {
      const res = await fetch(`/api/projects/${id}/launch`, { method: 'POST' });
      const data = await res.json();
      if (!data.success) {
        // Check for port conflict response (HTTP 409)
        if (data.portConflicts && data.portConflicts.length > 0) {
          setPortConflicts({ id, conflicts: data.portConflicts });
        } else {
          setActionError({ id, message: data.error || 'Failed to launch project' });
        }
      }
      await fetchProjects();
      if (data.success || !data.error) {
        // Tell ServiceMonitor this project was launched (clear manual-stop state)
        window.dispatchEvent(new CustomEvent('service-launched', {
          detail: { projectId: id }
        }));
      }
    } catch (error) {
      setActionError({ id, message: 'Network error launching project' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async (id: string) => {
    setActionLoading(id);
    setActionError(null);
    try {
      // Tell ServiceMonitor BEFORE we stop — prevents watchdog from restarting
      // services during the stop transition
      const projectPorts = projects.find(p => p.id === id)?.ports.map(p => p.port) || [];
      window.dispatchEvent(new CustomEvent('service-manual-stop', {
        detail: { projectId: id, ports: projectPorts }
      }));

      const res = await fetch(`/api/projects/${id}/stop`, { method: 'POST' });
      const data = await res.json();
      if (!data.success) {
        setActionError({ id, message: data.error || 'Failed to stop project' });
      }
      await fetchProjects();
    } catch (error) {
      setActionError({ id, message: 'Network error stopping project' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleWatchdog = async (projectId: string, currentEnabled: boolean) => {
    setWatchdogLoading(projectId);
    try {
      const res = await fetch('/api/watchdog', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId, enabled: !currentEnabled }),
      });
      const data = await res.json();
      if (data.success) {
        const newEnabled = !currentEnabled;
        // Update local state
        setProjects(prev => prev.map(p =>
          p.id === projectId ? { ...p, watchdogEnabled: newEnabled } : p
        ));
        // Notify ServiceMonitor so it can clear manual-stop markers on re-enable
        window.dispatchEvent(new CustomEvent('watchdog-toggled', {
          detail: { projectId, enabled: newEnabled }
        }));
      }
    } catch (error) {
      console.error('Failed to toggle watchdog:', error);
    } finally {
      setWatchdogLoading(null);
    }
  };

  const handleOpenClaude = async (id: string) => {
    await fetch(`/api/projects/${id}/claude`, { method: 'POST' });
  };

  const filteredProjects = projects.filter(p =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const activeCount = projects.filter(p => p.isRunning).length;

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
          <h1 className="text-2xl font-bold text-white">Projects</h1>
          <p className="text-zinc-400 mt-1">
            {activeCount} of {projects.length} projects running
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search projects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 w-64"
            />
          </div>
          <ImportButton variant="compact" onImportSuccess={fetchProjects} />
          <Button variant="outline" size="sm" onClick={fetchProjects}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left p-4 text-zinc-400 font-medium">Status</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Name</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Ports</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Git</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredProjects.map((project) => (
              <tr key={project.id} className="border-b border-zinc-800 hover:bg-zinc-800/50">
                {/* Status */}
                <td className="p-4">
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        'w-2.5 h-2.5 rounded-full',
                        project.isRunning ? 'bg-green-500 animate-pulse' : 'bg-zinc-600'
                      )}
                    />
                    <span className={cn(
                      'text-xs font-medium',
                      project.isRunning ? 'text-green-400' : 'text-zinc-500'
                    )}>
                      {project.isRunning ? 'Running' : 'Stopped'}
                    </span>
                  </div>
                </td>

                {/* Name */}
                <td className="p-4">
                  <Link href={`/projects/${project.id}`} className="block group">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-white group-hover:text-cyan-400 transition-colors">{project.name}</p>
                      <ChevronRight className="h-4 w-4 text-zinc-600 group-hover:text-cyan-400 transition-colors" />
                    </div>
                    {project.description && (
                      <p className="text-sm text-zinc-500 truncate max-w-xs">{project.description}</p>
                    )}
                  </Link>
                </td>

                {/* Ports */}
                <td className="p-4">
                  <div className="flex flex-wrap gap-1">
                    {project.ports.slice(0, 4).map((port) => (
                      <span
                        key={port.id}
                        className={cn(
                          'px-2 py-0.5 text-xs rounded-full text-white',
                          getServiceTypeColor(port.serviceType)
                        )}
                        title={port.serviceName}
                      >
                        {port.port}
                      </span>
                    ))}
                    {project.ports.length > 4 && (
                      <span className="px-2 py-0.5 text-xs rounded-full bg-zinc-700 text-zinc-300">
                        +{project.ports.length - 4}
                      </span>
                    )}
                  </div>
                </td>

                {/* Git */}
                <td className="p-4">
                  {project.gitStatus?.hasGit ? (
                    <div className="flex items-center gap-2 text-sm">
                      <GitBranch className="h-4 w-4 text-zinc-500" />
                      <span className="text-zinc-400">{project.gitStatus.branch}</span>
                      {!project.gitStatus.hasRemote && (
                        <span className="text-orange-500 text-xs bg-orange-500/10 px-1.5 py-0.5 rounded" title="Never synced to GitHub">
                          Not synced
                        </span>
                      )}
                      {project.gitStatus.isDirty && project.gitStatus.hasRemote && (
                        <span className="text-yellow-500 text-xs">
                          {project.gitStatus.uncommittedFiles} changes
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="text-zinc-600 text-sm">No git</span>
                  )}
                </td>

                {/* Actions */}
                <td className="p-4 relative">
                  <div className="flex items-center gap-2">
                    {project.isRunning ? (
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleStop(project.id)}
                        loading={actionLoading === project.id}
                      >
                        <Square className="h-3 w-3" />
                        Stop
                      </Button>
                    ) : (
                      <Button
                        variant="success"
                        size="sm"
                        onClick={() => handleLaunch(project.id)}
                        loading={actionLoading === project.id}
                      >
                        <Play className="h-3 w-3" />
                        Launch
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleOpenClaude(project.id)}
                      title="Open in Claude"
                    >
                      <Terminal className="h-3 w-3" />
                    </Button>
                    <button
                      onClick={() => handleToggleWatchdog(project.id, project.watchdogEnabled ?? false)}
                      disabled={watchdogLoading === project.id}
                      title={project.watchdogEnabled ? 'Watchdog active — click to disable' : 'Watchdog off — click to enable'}
                      className="flex items-center gap-1.5 group disabled:opacity-50"
                    >
                      {watchdogLoading === project.id ? (
                        <RefreshCw className="h-3 w-3 animate-spin text-zinc-400" />
                      ) : (
                        <>
                          <div className={cn(
                            'relative w-7 h-4 rounded-full transition-colors duration-200',
                            project.watchdogEnabled ? 'bg-green-500' : 'bg-red-500/60'
                          )}>
                            <div className={cn(
                              'absolute top-0.5 w-3 h-3 rounded-full bg-white shadow-sm transition-transform duration-200',
                              project.watchdogEnabled ? 'translate-x-3.5' : 'translate-x-0.5'
                            )} />
                          </div>
                          <Shield className={cn(
                            'h-3.5 w-3.5 transition-colors',
                            project.watchdogEnabled
                              ? 'text-green-400 fill-green-400/20'
                              : 'text-red-400/60'
                          )} />
                        </>
                      )}
                    </button>
                    {project.isRunning && project.ports.find(p => p.serviceType === 'FRONTEND')?.url && (
                      <a
                        href={project.ports.find(p => p.serviceType === 'FRONTEND')?.url!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center h-8 px-3 text-sm rounded-md bg-transparent text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                        title="Open in browser"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                    {actionError?.id === project.id && (
                      <span
                        className="text-red-400 text-xs max-w-xs truncate cursor-pointer"
                        title={actionError.message}
                        onClick={() => setActionError(null)}
                      >
                        {actionError.message}
                      </span>
                    )}
                    {portConflicts?.id === project.id && (
                      <div className="absolute top-full left-0 mt-1 z-10 bg-zinc-900 border border-red-500/30 rounded-lg p-3 shadow-xl min-w-[340px]">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-1.5 text-red-400 text-xs font-medium">
                            <AlertTriangle className="h-3.5 w-3.5" />
                            Port conflict detected
                          </div>
                          <button
                            onClick={() => setPortConflicts(null)}
                            className="text-zinc-500 hover:text-zinc-300 transition-colors"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-zinc-500">
                              <th className="text-left pr-3 pb-1">Port</th>
                              <th className="text-left pr-3 pb-1">Service</th>
                              <th className="text-left pb-1">Conflicting Process</th>
                            </tr>
                          </thead>
                          <tbody>
                            {portConflicts.conflicts.map((c) => (
                              <tr key={c.port} className="text-zinc-300">
                                <td className="pr-3 py-0.5 text-red-400 font-mono">{c.port}</td>
                                <td className="pr-3 py-0.5">{c.service}</td>
                                <td className="py-0.5 text-orange-400 truncate max-w-[160px]" title={c.owner}>{c.owner}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filteredProjects.length === 0 && (
          <div className="p-8 text-center text-zinc-500">
            No projects found matching "{searchQuery}"
          </div>
        )}
      </div>
    </div>
  );
}
