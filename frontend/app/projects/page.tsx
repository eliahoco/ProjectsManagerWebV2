'use client';

/**
 * Projects Page - Detailed project list with table view
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Play, Square, Terminal, GitBranch, ExternalLink, RefreshCw, Search, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ImportButton } from '@/components/codeboard/ImportButton';
import { cn, getServiceTypeColor } from '@/lib/utils';
import type { ProjectWithStatus } from '@/types';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);

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
    try {
      await fetch(`/api/projects/${id}/launch`, { method: 'POST' });
      await fetchProjects();
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async (id: string) => {
    setActionLoading(id);
    try {
      await fetch(`/api/projects/${id}/stop`, { method: 'POST' });
      await fetchProjects();
    } finally {
      setActionLoading(null);
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
                <td className="p-4">
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
