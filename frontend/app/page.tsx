'use client';

/**
 * Dashboard Page
 * Main view showing all projects with status and quick actions
 */

import { useEffect, useState, useMemo } from 'react';
import { RefreshCw, Play, Square, AlertCircle, Search, Filter } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProjectCard } from '@/components/projects/project-card';
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';
import type { ProjectWithStatus, ProjectListResponse } from '@/types';

type FilterOption = 'all' | 'running' | 'stopped' | 'active' | 'deprecated' | 'archived';

export default function DashboardPage() {
  const [projects, setProjects] = useState<ProjectWithStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCount, setActiveCount] = useState(0);
  const [isLaunchingAll, setIsLaunchingAll] = useState(false);
  const [isStoppingAll, setIsStoppingAll] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<FilterOption>('all');
  const toast = useToast();

  const fetchProjects = async () => {
    try {
      setIsLoading(true);
      setError(null);

      const response = await fetch('/api/projects');
      const data = await response.json();

      if (data.success) {
        const result = data.data as ProjectListResponse;
        setProjects(result.projects);
        setActiveCount(result.activeCount);
      } else {
        setError(data.error || 'Failed to fetch projects');
      }
    } catch (err) {
      setError('Network error. Please try again.');
      console.error('Error fetching projects:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();

    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchProjects, 10000);
    return () => clearInterval(interval);
  }, []);

  // Filter and search projects
  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      // Search filter
      const matchesSearch =
        searchQuery === '' ||
        project.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        project.path.toLowerCase().includes(searchQuery.toLowerCase()) ||
        project.type?.toLowerCase().includes(searchQuery.toLowerCase());

      // Status filter
      let matchesFilter = true;
      switch (statusFilter) {
        case 'running':
          matchesFilter = project.isRunning === true;
          break;
        case 'stopped':
          matchesFilter = project.isRunning === false;
          break;
        case 'active':
          matchesFilter = project.status === 'ACTIVE';
          break;
        case 'deprecated':
          matchesFilter = project.status === 'DEPRECATED';
          break;
        case 'archived':
          matchesFilter = project.status === 'ARCHIVED';
          break;
      }

      return matchesSearch && matchesFilter;
    });
  }, [projects, searchQuery, statusFilter]);

  const handleLaunch = async (id: string) => {
    const project = projects.find((p) => p.id === id);
    try {
      const response = await fetch(`/api/projects/${id}/launch`, {
        method: 'POST',
      });
      const data = await response.json();

      if (data.success) {
        toast.success('Project Launched', `${project?.name} is starting up`);
      } else {
        toast.error('Launch Failed', data.error || 'Failed to launch project');
      }

      // Refresh project list
      await fetchProjects();
    } catch (err) {
      console.error('Error launching project:', err);
      toast.error('Launch Failed', 'Network error occurred');
    }
  };

  const handleStop = async (id: string) => {
    const project = projects.find((p) => p.id === id);
    try {
      const response = await fetch(`/api/projects/${id}/stop`, {
        method: 'POST',
      });
      const data = await response.json();

      if (data.success) {
        toast.success('Project Stopped', `${project?.name} has been stopped`);
      } else {
        toast.error('Stop Failed', data.error || 'Failed to stop project');
      }

      // Refresh project list
      await fetchProjects();
    } catch (err) {
      console.error('Error stopping project:', err);
      toast.error('Stop Failed', 'Network error occurred');
    }
  };

  const handleOpenClaude = async (id: string) => {
    const project = projects.find((p) => p.id === id);
    try {
      const response = await fetch(`/api/projects/${id}/claude`, {
        method: 'POST',
      });
      const data = await response.json();

      if (data.success) {
        toast.info('Opening Claude', `Launching Claude for ${project?.name}`);
      } else {
        toast.error('Failed', data.error || 'Failed to open Claude');
      }
    } catch (err) {
      console.error('Error opening Claude:', err);
      toast.error('Failed', 'Network error occurred');
    }
  };

  const handleLaunchAll = async () => {
    const inactiveProjects = filteredProjects.filter(
      (p) => !p.isRunning && p.ports.length > 0
    );

    if (inactiveProjects.length === 0) {
      return;
    }

    setIsLaunchingAll(true);
    toast.info('Launching Projects', `Starting ${inactiveProjects.length} projects...`);
    try {
      for (const project of inactiveProjects) {
        await fetch(`/api/projects/${project.id}/launch`, { method: 'POST' });
      }
      await fetchProjects();
      toast.success('All Launched', `${inactiveProjects.length} projects started`);
    } catch {
      toast.error('Launch Failed', 'Some projects failed to start');
    } finally {
      setIsLaunchingAll(false);
    }
  };

  const handleStopAll = async () => {
    const activeProjects = filteredProjects.filter((p) => p.isRunning);

    if (activeProjects.length === 0) {
      return;
    }

    setIsStoppingAll(true);
    toast.info('Stopping Projects', `Stopping ${activeProjects.length} projects...`);
    try {
      for (const project of activeProjects) {
        await fetch(`/api/projects/${project.id}/stop`, { method: 'POST' });
      }
      await fetchProjects();
      toast.success('All Stopped', `${activeProjects.length} projects stopped`);
    } catch {
      toast.error('Stop Failed', 'Some projects failed to stop');
    } finally {
      setIsStoppingAll(false);
    }
  };

  const filterOptions: { value: FilterOption; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'running', label: 'Running' },
    { value: 'stopped', label: 'Stopped' },
    { value: 'active', label: 'Active' },
    { value: 'deprecated', label: 'Deprecated' },
    { value: 'archived', label: 'Archived' },
  ];

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-zinc-400">
            {activeCount} of {projects.length} projects running
            {filteredProjects.length !== projects.length && (
              <span className="text-cyan-400 ml-2">
                (showing {filteredProjects.length})
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchProjects} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button
            variant="success"
            size="sm"
            onClick={handleLaunchAll}
            loading={isLaunchingAll}
            disabled={isLaunchingAll || isStoppingAll || filteredProjects.filter(p => !p.isRunning && p.ports.length > 0).length === 0}
          >
            <Play className="h-4 w-4" />
            Launch All
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleStopAll}
            loading={isStoppingAll}
            disabled={isLaunchingAll || isStoppingAll || filteredProjects.filter(p => p.isRunning).length === 0}
          >
            <Square className="h-4 w-4" />
            Stop All
          </Button>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="flex items-center gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search projects..."
            className="w-full pl-10 pr-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-zinc-500" />
          <div className="flex rounded-lg border border-zinc-800 overflow-hidden">
            {filterOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => setStatusFilter(option.value)}
                className={cn(
                  'px-3 py-1.5 text-sm transition-colors',
                  statusFilter === option.value
                    ? 'bg-cyan-500 text-white'
                    : 'bg-zinc-900 text-zinc-400 hover:text-white'
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-500" />
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Loading state */}
      {isLoading && projects.length === 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 animate-pulse"
            >
              <div className="h-4 bg-zinc-800 rounded w-3/4 mb-3" />
              <div className="h-3 bg-zinc-800 rounded w-full mb-2" />
              <div className="h-3 bg-zinc-800 rounded w-2/3 mb-4" />
              <div className="flex gap-2">
                <div className="h-6 bg-zinc-800 rounded w-12" />
                <div className="h-6 bg-zinc-800 rounded w-12" />
                <div className="h-6 bg-zinc-800 rounded w-12" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Project grid */}
      {!isLoading || projects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredProjects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onLaunch={handleLaunch}
              onStop={handleStop}
              onOpenClaude={handleOpenClaude}
            />
          ))}
        </div>
      ) : null}

      {/* Empty state */}
      {!isLoading && projects.length === 0 && !error && (
        <div className="text-center py-12">
          <p className="text-zinc-400">No projects found.</p>
          <p className="text-zinc-500 text-sm mt-1">
            Run the seed script to migrate your existing projects.
          </p>
        </div>
      )}

      {/* No results from filter/search */}
      {!isLoading && projects.length > 0 && filteredProjects.length === 0 && (
        <div className="text-center py-12">
          <p className="text-zinc-400">No projects match your search.</p>
          <button
            onClick={() => {
              setSearchQuery('');
              setStatusFilter('all');
            }}
            className="text-cyan-400 hover:text-cyan-300 text-sm mt-2"
          >
            Clear filters
          </button>
        </div>
      )}
    </div>
  );
}
