'use client';

/**
 * Project Card Component
 * Displays project info with status and quick actions
 */

import { useState } from 'react';
import Link from 'next/link';
import { Play, Square, Terminal, MoreVertical, GitBranch, ExternalLink, List } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn, getServiceTypeColor } from '@/lib/utils';
import type { ProjectWithStatus } from '@/types';

interface ProjectCardProps {
  project: ProjectWithStatus;
  onLaunch: (id: string) => Promise<void>;
  onStop: (id: string) => Promise<void>;
  onOpenClaude: (id: string) => Promise<void>;
}

export function ProjectCard({ project, onLaunch, onStop, onOpenClaude }: ProjectCardProps) {
  const [isLaunching, setIsLaunching] = useState(false);
  const [isStopping, setIsStopping] = useState(false);

  const handleLaunch = async () => {
    setIsLaunching(true);
    try {
      await onLaunch(project.id);
    } finally {
      setIsLaunching(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);
    try {
      await onStop(project.id);
    } finally {
      setIsStopping(false);
    }
  };

  // Get frontend URL for quick access
  const frontendPort = project.ports.find(
    (p) => p.serviceType === 'FRONTEND' && p.url?.startsWith('http')
  );

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 hover:border-zinc-700 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {/* Status indicator */}
          <div
            className={cn(
              'w-2.5 h-2.5 rounded-full',
              project.isRunning ? 'bg-green-500 animate-pulse' : 'bg-zinc-600'
            )}
          />
          <Link href={`/projects/${project.id}`} className="font-medium text-white truncate hover:text-cyan-400 transition-colors">
            {project.name}
          </Link>
        </div>
        <Button variant="ghost" size="icon" className="h-8 w-8 text-zinc-400">
          <MoreVertical className="h-4 w-4" />
        </Button>
      </div>

      {/* Description */}
      {project.description && (
        <p className="text-sm text-zinc-400 mb-3 line-clamp-2">{project.description}</p>
      )}

      {/* Ports */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {project.ports.slice(0, 5).map((port) => (
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
        {project.ports.length > 5 && (
          <span className="px-2 py-0.5 text-xs rounded-full bg-zinc-700 text-zinc-300">
            +{project.ports.length - 5}
          </span>
        )}
      </div>

      {/* Git status */}
      {project.gitStatus?.hasGit && (
        <div className="flex items-center gap-2 text-xs text-zinc-500 mb-3">
          <GitBranch className="h-3 w-3" />
          <span>{project.gitStatus.branch}</span>
          {project.gitStatus.isDirty && (
            <span className="text-yellow-500">• {project.gitStatus.uncommittedFiles} changes</span>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        {project.isRunning ? (
          <Button
            variant="destructive"
            size="sm"
            onClick={handleStop}
            loading={isStopping}
            className="flex-1"
          >
            <Square className="h-3 w-3" />
            Stop
          </Button>
        ) : (
          <Button
            variant="success"
            size="sm"
            onClick={handleLaunch}
            loading={isLaunching}
            className="flex-1"
          >
            <Play className="h-3 w-3" />
            Launch
          </Button>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={() => onOpenClaude(project.id)}
          title="Open in Claude"
        >
          <Terminal className="h-3 w-3" />
        </Button>

        <a
          href={`/api/projects/${project.id}/services`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center h-8 px-3 text-sm rounded-md border border-zinc-700 bg-transparent text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
          title="View services"
        >
          <List className="h-3 w-3" />
        </a>

        {frontendPort && project.isRunning && (
          <a
            href={frontendPort.url!}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center h-8 px-3 text-sm rounded-md bg-transparent text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
            title="Open in browser"
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </div>
  );
}
