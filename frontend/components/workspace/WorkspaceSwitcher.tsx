'use client';

/**
 * WorkspaceSwitcher — project picker for the workspace Studio.
 *
 * Fetches all projects from GET /api/projects via React Query and renders
 * a <select> dropdown showing every project. The selected project is stored
 * in TenantContext (projectId) and persisted to localStorage under the key
 * "studio-active-project-id" so reloads remember the selection.
 *
 * Switching the selected project changes TenantContext.projectId, which
 * causes useStudio and useBacklog to use new query keys and refetch data
 * for the newly selected project.
 */

import { useQuery } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTenant } from '@/contexts/TenantContext';

interface Project {
  id: string;
  name: string;
}

const PROJECTS_API_URL = 'http://localhost:8401/api/projects';

async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(PROJECTS_API_URL);
  if (!res.ok) {
    throw new Error(`Failed to fetch projects: ${res.status}`);
  }
  return res.json();
}

interface WorkspaceSwitcherProps {
  workspaceId?: string;
  className?: string;
}

export function WorkspaceSwitcher({ className }: WorkspaceSwitcherProps) {
  const { projectId, setProjectId } = useTenant();

  const { data: projects, isLoading, isError } = useQuery<Project[]>({
    queryKey: ['projects-list'],
    queryFn: fetchProjects,
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    retry: 1,
  });

  const selectedProject = projects?.find((p) => p.id === projectId);
  const displayName = selectedProject?.name ?? 'Select project…';

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const newId = e.target.value;
    if (newId && newId !== projectId) {
      setProjectId(newId);
    }
  }

  return (
    <div className={cn('relative flex items-center', className)}>
      <select
        value={projectId}
        onChange={handleChange}
        aria-label="Switch active project"
        disabled={isLoading || isError}
        className={cn(
          'appearance-none bg-transparent border border-zinc-700 rounded-lg',
          'pl-3 pr-8 py-1.5 text-sm font-medium text-zinc-200',
          'focus:outline-none focus:border-cyan-500 cursor-pointer',
          'hover:border-zinc-500 transition-colors',
          'disabled:opacity-50 disabled:cursor-not-allowed',
        )}
      >
        {isLoading && (
          <option value={projectId} disabled>
            Loading projects…
          </option>
        )}
        {isError && (
          <option value={projectId} disabled>
            Failed to load projects
          </option>
        )}
        {!isLoading && !isError && projects && projects.length === 0 && (
          <option value="" disabled>
            No projects found
          </option>
        )}
        {!isLoading && !isError && projects?.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 w-3.5 h-3.5 text-zinc-400 pointer-events-none" />
    </div>
  );
}
