'use client';

/**
 * Project Detail Page
 * Shows detailed information about a single project
 */

import { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Play,
  Square,
  Terminal,
  GitBranch,
  GitCommit,
  ExternalLink,
  RefreshCw,
  Folder,
  Clock,
  Server,
  Upload,
  Download,
  FileText,
  Archive,
  AlertTriangle,
  CheckCircle,
  MessageSquare,
  BookOpen,
  RotateCcw,
  StopCircle,
} from 'lucide-react';
import { useToast } from '@/components/ui/toast';
import { Button } from '@/components/ui/button';
import { cn, getServiceTypeColor, formatDate } from '@/lib/utils';
import type { ProjectWithStatus } from '@/types';

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const toast = useToast();
  const [project, setProject] = useState<ProjectWithStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [statusNote, setStatusNote] = useState('');
  const [serviceActionLoading, setServiceActionLoading] = useState<string | null>(null);
  const [refreshingService, setRefreshingService] = useState<string | null>(null);
  const [gitProgress, setGitProgress] = useState<{
    phase: 'idle' | 'staging' | 'committing' | 'pushing' | 'pulling' | 'done' | 'error';
    percent: number;
    output: string;
  }>({ phase: 'idle', percent: 0, output: '' });
  const [showGitTerminal, setShowGitTerminal] = useState(false);

  const fetchProject = async () => {
    try {
      const res = await fetch(`/api/projects/${id}`);
      const data = await res.json();
      if (data.success) {
        setProject(data.data);
      }
    } catch (error) {
      console.error('Failed to fetch project:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProject();
    const interval = setInterval(fetchProject, 10000);
    return () => clearInterval(interval);
  }, [id]);

  const handleLaunch = async () => {
    setActionLoading('launch');
    try {
      await fetch(`/api/projects/${id}/launch`, { method: 'POST' });
      await fetchProject();
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async () => {
    setActionLoading('stop');
    try {
      await fetch(`/api/projects/${id}/stop`, { method: 'POST' });
      await fetchProject();
    } finally {
      setActionLoading(null);
    }
  };

  const handleOpenClaude = async () => {
    setActionLoading('claude');
    try {
      await fetch(`/api/projects/${id}/claude`, { method: 'POST' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleGitPush = async () => {
    setActionLoading('push');
    setGitProgress({ phase: 'staging', percent: 10, output: 'Staging changes...\n' });

    try {
      // Simulate staging phase
      await new Promise(r => setTimeout(r, 300));
      setGitProgress(prev => ({ ...prev, phase: 'committing', percent: 30, output: prev.output + 'Committing changes...\n' }));

      await new Promise(r => setTimeout(r, 300));
      setGitProgress(prev => ({ ...prev, phase: 'pushing', percent: 50, output: prev.output + 'Pushing to remote...\n' }));

      const res = await fetch('/api/github/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectId: id,
          action: 'push',
        }),
      });
      const data = await res.json();

      if (data.success) {
        setGitProgress(prev => ({
          ...prev,
          phase: 'done',
          percent: 100,
          output: prev.output + (data.data?.output || 'Push successful!\n')
        }));
        toast.success('Pushed', 'Changes pushed to GitHub successfully');
        await fetchProject();
        // Auto-hide progress after 3 seconds on success
        setTimeout(() => setGitProgress({ phase: 'idle', percent: 0, output: '' }), 3000);
      } else {
        setGitProgress(prev => ({
          ...prev,
          phase: 'error',
          percent: 100,
          output: prev.output + `Error: ${data.error || 'Push failed'}\n`
        }));
        console.error('Push failed:', data.error);
        toast.error('Push Failed', data.error || 'Failed to push to GitHub');
      }
    } catch (error) {
      setGitProgress(prev => ({
        ...prev,
        phase: 'error',
        percent: 100,
        output: prev.output + `Network error: ${error}\n`
      }));
      console.error('Push error:', error);
      toast.error('Push Failed', 'Network error - check console for details');
    } finally {
      setActionLoading(null);
    }
  };

  const handleGitPull = async () => {
    setActionLoading('pull');
    setGitProgress({ phase: 'pulling', percent: 30, output: 'Fetching from remote...\n' });

    try {
      const res = await fetch('/api/github/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectId: id,
          action: 'pull',
        }),
      });
      const data = await res.json();

      if (data.success) {
        setGitProgress(prev => ({
          ...prev,
          phase: 'done',
          percent: 100,
          output: prev.output + (data.data?.output || 'Pull successful!\n')
        }));
        toast.success('Pulled', 'Latest changes pulled from GitHub');
        await fetchProject();
        setTimeout(() => setGitProgress({ phase: 'idle', percent: 0, output: '' }), 3000);
      } else {
        setGitProgress(prev => ({
          ...prev,
          phase: 'error',
          percent: 100,
          output: prev.output + `Error: ${data.error || 'Pull failed'}\n`
        }));
        console.error('Pull failed:', data.error);
        toast.error('Pull Failed', data.error || 'Failed to pull from GitHub');
      }
    } catch (error) {
      setGitProgress(prev => ({
        ...prev,
        phase: 'error',
        percent: 100,
        output: prev.output + `Network error: ${error}\n`
      }));
      console.error('Pull error:', error);
      toast.error('Pull Failed', 'Network error - check console for details');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRefreshService = async (serviceId: string) => {
    setRefreshingService(serviceId);
    try {
      await fetchProject();
      toast.success('Refreshed', 'Service status updated');
    } finally {
      setRefreshingService(null);
    }
  };

  const handleServiceAction = async (serviceId: string, action: 'start' | 'stop' | 'restart') => {
    setServiceActionLoading(`${serviceId}-${action}`);
    try {
      const res = await fetch(`/api/projects/${id}/services/${serviceId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();

      if (data.success) {
        toast.success(
          `Service ${action === 'start' ? 'Started' : action === 'stop' ? 'Stopped' : 'Restarted'}`,
          data.message || `Service ${action} successful`
        );
        await fetchProject();
      } else {
        toast.error('Action Failed', data.error || `Failed to ${action} service`);
      }
    } catch (error) {
      toast.error('Action Failed', 'Network error');
    } finally {
      setServiceActionLoading(null);
    }
  };

  const handleStatusChange = async (newStatus: 'ACTIVE' | 'DEPRECATED' | 'ARCHIVED') => {
    setActionLoading('status');
    try {
      const res = await fetch(`/api/projects/${id}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: newStatus,
          notes: statusNote || undefined,
        }),
      });
      const data = await res.json();
      if (data.success) {
        toast.success('Status Updated', `Project is now ${newStatus}`);
        setShowStatusModal(false);
        setStatusNote('');
        await fetchProject();
      } else {
        toast.error('Update Failed', data.error);
      }
    } catch (error) {
      toast.error('Update Failed', 'Network error');
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="p-6">
        <Button variant="ghost" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="text-center py-12">
          <p className="text-zinc-400">Project not found</p>
        </div>
      </div>
    );
  }

  const frontendPort = project.ports.find(p => p.serviceType === 'FRONTEND');

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'w-3 h-3 rounded-full',
                project.isRunning ? 'bg-green-500 animate-pulse' : 'bg-zinc-600'
              )}
            />
            <h1 className="text-2xl font-bold text-white">{project.name}</h1>
            <span className={cn(
              'px-2 py-0.5 text-xs rounded-full',
              project.status === 'ACTIVE' ? 'bg-green-500/20 text-green-400' :
              project.status === 'DEPRECATED' ? 'bg-yellow-500/20 text-yellow-400' :
              'bg-zinc-500/20 text-zinc-400'
            )}>
              {project.status}
            </span>
          </div>
          {project.description && (
            <p className="text-zinc-400 mt-1">{project.description}</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchProject}
            title="Refresh Status"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          {project.isRunning ? (
            <Button
              variant="destructive"
              onClick={handleStop}
              loading={actionLoading === 'stop'}
            >
              <Square className="h-4 w-4" />
              Stop
            </Button>
          ) : (
            <Button
              variant="success"
              onClick={handleLaunch}
              loading={actionLoading === 'launch'}
              disabled={project.ports.length === 0}
            >
              <Play className="h-4 w-4" />
              Launch
            </Button>
          )}
          <Button
            variant="outline"
            onClick={handleOpenClaude}
            loading={actionLoading === 'claude'}
          >
            <Terminal className="h-4 w-4" />
            Open in Claude
          </Button>
          {frontendPort?.url && project.isRunning && (
            <a
              href={frontendPort.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center h-9 px-4 rounded-md border border-zinc-700 text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              Open App
            </a>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="col-span-2 space-y-6">
          {/* Services */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg">
            <div className="p-4 border-b border-zinc-800">
              <h2 className="text-lg font-medium text-white flex items-center gap-2">
                <Server className="h-5 w-5 text-cyan-400" />
                Services & Ports
              </h2>
            </div>
            <div className="p-4">
              {project.ports.length > 0 ? (
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-zinc-400 text-sm">
                      <th className="pb-3">Service</th>
                      <th className="pb-3">Type</th>
                      <th className="pb-3">Port</th>
                      <th className="pb-3">Status</th>
                      <th className="pb-3">URL</th>
                      <th className="pb-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {project.ports.map((port) => {
                      const serviceStatus = project.services?.find(s => s.port === port.port);
                      const isServiceRunning = serviceStatus?.status === 'running';
                      const isLoading = serviceActionLoading?.startsWith(port.id);

                      return (
                        <tr key={port.id} className="border-t border-zinc-800">
                          <td className="py-3 text-white">{port.serviceName}</td>
                          <td className="py-3">
                            <span className={cn(
                              'px-2 py-0.5 text-xs rounded-full text-white',
                              getServiceTypeColor(port.serviceType)
                            )}>
                              {port.serviceType}
                            </span>
                          </td>
                          <td className="py-3">
                            <span className="font-mono text-cyan-400">{port.port}</span>
                            {port.internalPort && port.internalPort !== port.port && (
                              <span className="text-zinc-500 text-sm ml-1">→ {port.internalPort}</span>
                            )}
                          </td>
                          <td className="py-3">
                            <span className={cn(
                              'flex items-center gap-1.5 text-xs',
                              isServiceRunning ? 'text-green-400' : 'text-zinc-500'
                            )}>
                              <span className={cn(
                                'w-2 h-2 rounded-full',
                                isServiceRunning ? 'bg-green-500' : 'bg-zinc-600'
                              )} />
                              {isServiceRunning ? 'Running' : 'Stopped'}
                            </span>
                          </td>
                          <td className="py-3">
                            {port.url && isServiceRunning ? (
                              <a
                                href={port.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 text-sm"
                              >
                                <ExternalLink className="h-3 w-3" />
                                {port.url}
                              </a>
                            ) : port.url ? (
                              <span className="text-zinc-500 text-sm">{port.url}</span>
                            ) : (
                              <span className="text-zinc-600">-</span>
                            )}
                          </td>
                          <td className="py-3">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => handleRefreshService(port.id)}
                                disabled={refreshingService === port.id}
                                className={cn(
                                  'p-1.5 rounded-md transition-colors',
                                  refreshingService === port.id
                                    ? 'bg-zinc-700 text-zinc-400'
                                    : 'bg-zinc-700/50 hover:bg-zinc-600 text-zinc-400'
                                )}
                                title="Refresh Status"
                              >
                                <RefreshCw className={cn('h-3.5 w-3.5', refreshingService === port.id && 'animate-spin')} />
                              </button>
                              {isServiceRunning ? (
                                <>
                                  <button
                                    onClick={() => handleServiceAction(port.id, 'restart')}
                                    disabled={isLoading}
                                    className={cn(
                                      'p-1.5 rounded-md transition-colors',
                                      isLoading && serviceActionLoading === `${port.id}-restart`
                                        ? 'bg-zinc-700 text-zinc-400'
                                        : 'bg-yellow-600/20 hover:bg-yellow-600/40 text-yellow-400'
                                    )}
                                    title="Restart Service"
                                  >
                                    {isLoading && serviceActionLoading === `${port.id}-restart` ? (
                                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <RotateCcw className="h-3.5 w-3.5" />
                                    )}
                                  </button>
                                  <button
                                    onClick={() => handleServiceAction(port.id, 'stop')}
                                    disabled={isLoading}
                                    className={cn(
                                      'p-1.5 rounded-md transition-colors',
                                      isLoading && serviceActionLoading === `${port.id}-stop`
                                        ? 'bg-zinc-700 text-zinc-400'
                                        : 'bg-red-600/20 hover:bg-red-600/40 text-red-400'
                                    )}
                                    title="Stop Service"
                                  >
                                    {isLoading && serviceActionLoading === `${port.id}-stop` ? (
                                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <StopCircle className="h-3.5 w-3.5" />
                                    )}
                                  </button>
                                </>
                              ) : (
                                <button
                                  onClick={() => handleServiceAction(port.id, 'start')}
                                  disabled={isLoading}
                                  className={cn(
                                    'p-1.5 rounded-md transition-colors',
                                    isLoading && serviceActionLoading === `${port.id}-start`
                                      ? 'bg-zinc-700 text-zinc-400'
                                      : 'bg-green-600/20 hover:bg-green-600/40 text-green-400'
                                  )}
                                  title="Start Service"
                                >
                                  {isLoading && serviceActionLoading === `${port.id}-start` ? (
                                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Play className="h-3.5 w-3.5" />
                                  )}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <p className="text-zinc-500 text-center py-4">No services configured</p>
              )}
            </div>
          </div>

          {/* Running Services Status */}
          {project.services && project.services.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg">
              <div className="p-4 border-b border-zinc-800">
                <h2 className="text-lg font-medium text-white">Service Status</h2>
              </div>
              <div className="p-4">
                <div className="space-y-2">
                  {project.services.map((service, idx) => {
                    // Find the matching port for this service
                    const matchingPort = project.ports.find(p => p.port === service.port);
                    const serviceKey = matchingPort?.id || `service-${idx}`;
                    const isServiceRunning = service.status === 'running';
                    const isLoading = serviceActionLoading?.startsWith(serviceKey);

                    return (
                      <div key={idx} className="flex items-center justify-between p-3 bg-zinc-800 rounded-lg">
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            'w-2 h-2 rounded-full',
                            isServiceRunning ? 'bg-green-500' : 'bg-red-500'
                          )} />
                          <div>
                            <span className="text-white font-mono text-sm">{service.name}</span>
                            {service.port && (
                              <span className="text-zinc-500 text-xs ml-2">:{service.port}</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            'text-xs px-2 py-1 rounded',
                            isServiceRunning ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                          )}>
                            {service.status}
                          </span>
                          {matchingPort && (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => handleRefreshService(serviceKey)}
                                disabled={refreshingService === serviceKey}
                                className={cn(
                                  'p-1.5 rounded-md transition-colors',
                                  refreshingService === serviceKey
                                    ? 'bg-zinc-700 text-zinc-400'
                                    : 'bg-zinc-700/50 hover:bg-zinc-600 text-zinc-400'
                                )}
                                title="Refresh Status"
                              >
                                <RefreshCw className={cn('h-3.5 w-3.5', refreshingService === serviceKey && 'animate-spin')} />
                              </button>
                              {isServiceRunning ? (
                                <>
                                  <button
                                    onClick={() => handleServiceAction(matchingPort.id, 'restart')}
                                    disabled={isLoading}
                                    className={cn(
                                      'p-1.5 rounded-md transition-colors',
                                      isLoading && serviceActionLoading === `${matchingPort.id}-restart`
                                        ? 'bg-zinc-700 text-zinc-400'
                                        : 'bg-yellow-600/20 hover:bg-yellow-600/40 text-yellow-400'
                                    )}
                                    title="Restart Service"
                                  >
                                    {isLoading && serviceActionLoading === `${matchingPort.id}-restart` ? (
                                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <RotateCcw className="h-3.5 w-3.5" />
                                    )}
                                  </button>
                                  <button
                                    onClick={() => handleServiceAction(matchingPort.id, 'stop')}
                                    disabled={isLoading}
                                    className={cn(
                                      'p-1.5 rounded-md transition-colors',
                                      isLoading && serviceActionLoading === `${matchingPort.id}-stop`
                                        ? 'bg-zinc-700 text-zinc-400'
                                        : 'bg-red-600/20 hover:bg-red-600/40 text-red-400'
                                    )}
                                    title="Stop Service"
                                  >
                                    {isLoading && serviceActionLoading === `${matchingPort.id}-stop` ? (
                                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <StopCircle className="h-3.5 w-3.5" />
                                    )}
                                  </button>
                                </>
                              ) : (
                                <button
                                  onClick={() => handleServiceAction(matchingPort.id, 'start')}
                                  disabled={isLoading}
                                  className={cn(
                                    'p-1.5 rounded-md transition-colors',
                                    isLoading && serviceActionLoading === `${matchingPort.id}-start`
                                      ? 'bg-zinc-700 text-zinc-400'
                                      : 'bg-green-600/20 hover:bg-green-600/40 text-green-400'
                                  )}
                                  title="Start Service"
                                >
                                  {isLoading && serviceActionLoading === `${matchingPort.id}-start` ? (
                                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Play className="h-3.5 w-3.5" />
                                  )}
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Project Info */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Project Info</h3>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <Folder className="h-4 w-4 text-zinc-500 mt-0.5" />
                <div>
                  <p className="text-xs text-zinc-500">Path</p>
                  <p className="text-sm text-zinc-300 font-mono break-all">{project.path}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Clock className="h-4 w-4 text-zinc-500 mt-0.5" />
                <div>
                  <p className="text-xs text-zinc-500">Created</p>
                  <p className="text-sm text-zinc-300">{formatDate(project.createdAt)}</p>
                </div>
              </div>
              {project.type && (
                <div className="flex items-start gap-3">
                  <Server className="h-4 w-4 text-zinc-500 mt-0.5" />
                  <div>
                    <p className="text-xs text-zinc-500">Type</p>
                    <p className="text-sm text-zinc-300">{project.type}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Git Status */}
          {project.gitStatus?.hasGit && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <h3 className="text-sm font-medium text-zinc-400 mb-4 flex items-center gap-2">
                <GitBranch className="h-4 w-4" />
                Git Status
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 text-sm">Branch</span>
                  <span className="text-white text-sm font-mono">{project.gitStatus.branch}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500 text-sm">Remote</span>
                  <span className={cn(
                    'text-sm',
                    project.gitStatus.hasRemote ? 'text-green-400' : 'text-zinc-500'
                  )}>
                    {project.gitStatus.hasRemote ? 'Connected' : 'None'}
                  </span>
                </div>
                {project.gitStatus.isDirty && (
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-500 text-sm">Changes</span>
                    <span className="text-yellow-400 text-sm flex items-center gap-1">
                      <GitCommit className="h-3 w-3" />
                      {project.gitStatus.uncommittedFiles} uncommitted
                    </span>
                  </div>
                )}
              </div>
              {/* Git Sync Buttons */}
              {project.gitStatus.hasRemote && (
                <div className="mt-4 pt-4 border-t border-zinc-800">
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={handleGitPush}
                      loading={actionLoading === 'push'}
                      disabled={!project.gitStatus.isDirty || gitProgress.phase !== 'idle'}
                    >
                      <Upload className="h-4 w-4" />
                      Push
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={handleGitPull}
                      loading={actionLoading === 'pull'}
                      disabled={gitProgress.phase !== 'idle'}
                    >
                      <Download className="h-4 w-4" />
                      Pull
                    </Button>
                  </div>

                  {/* Git Progress Bar */}
                  {gitProgress.phase !== 'idle' && (
                    <div className="mt-3 space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className={cn(
                          "capitalize",
                          gitProgress.phase === 'done' && "text-green-500",
                          gitProgress.phase === 'error' && "text-red-500",
                          !['done', 'error'].includes(gitProgress.phase) && "text-blue-400"
                        )}>
                          {gitProgress.phase === 'done' ? 'Complete' :
                           gitProgress.phase === 'error' ? 'Failed' :
                           gitProgress.phase}...
                        </span>
                        <button
                          onClick={() => setShowGitTerminal(!showGitTerminal)}
                          className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1"
                        >
                          <Terminal className="h-3 w-3" />
                          {showGitTerminal ? 'Hide' : 'Show'} Output
                        </button>
                      </div>

                      {/* Progress Bar */}
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className={cn(
                            "h-full transition-all duration-300 rounded-full",
                            gitProgress.phase === 'done' && "bg-green-500",
                            gitProgress.phase === 'error' && "bg-red-500",
                            !['done', 'error'].includes(gitProgress.phase) && "bg-blue-500"
                          )}
                          style={{ width: `${gitProgress.percent}%` }}
                        />
                      </div>

                      {/* Terminal Output */}
                      {showGitTerminal && (
                        <div className="bg-black/50 border border-zinc-700 rounded-md p-2 font-mono text-xs text-zinc-400 max-h-32 overflow-y-auto">
                          <pre className="whitespace-pre-wrap">{gitProgress.output || 'Waiting...'}</pre>
                        </div>
                      )}

                      {/* Clear button when done/error */}
                      {['done', 'error'].includes(gitProgress.phase) && (
                        <button
                          onClick={() => setGitProgress({ phase: 'idle', percent: 0, output: '' })}
                          className="text-xs text-zinc-500 hover:text-zinc-300"
                        >
                          Dismiss
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Quick Actions */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">Quick Actions</h3>
            <div className="space-y-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={() => {
                  navigator.clipboard.writeText(`cd ${project.path}`);
                  toast.success('Copied', 'Path copied to clipboard');
                }}
              >
                <Terminal className="h-4 w-4" />
                Copy Path
              </Button>
              <Link href={`/projects/${id}/logs`}>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start"
                >
                  <FileText className="h-4 w-4" />
                  View Logs
                </Button>
              </Link>
              <Link href={`/projects/${id}/docs`}>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start"
                >
                  <BookOpen className="h-4 w-4" />
                  Docs & History
                </Button>
              </Link>
            </div>
          </div>

          {/* Project Status Management */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-zinc-400 mb-4 flex items-center gap-2">
              <Archive className="h-4 w-4" />
              Project Status
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-zinc-500 text-sm">Current</span>
                <span className={cn(
                  'px-2 py-0.5 text-xs rounded-full',
                  project.status === 'ACTIVE' ? 'bg-green-500/20 text-green-400' :
                  project.status === 'DEPRECATED' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-zinc-500/20 text-zinc-400'
                )}>
                  {project.status}
                </span>
              </div>

              {!showStatusModal ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => setShowStatusModal(true)}
                >
                  Change Status
                </Button>
              ) : (
                <div className="space-y-3 pt-2 border-t border-zinc-800">
                  <div className="space-y-2">
                    <button
                      onClick={() => handleStatusChange('ACTIVE')}
                      disabled={project.status === 'ACTIVE' || actionLoading === 'status'}
                      className={cn(
                        'w-full flex items-center gap-2 p-2 rounded-lg text-left text-sm transition-colors',
                        project.status === 'ACTIVE'
                          ? 'bg-green-500/10 border border-green-500/30 text-green-400 cursor-not-allowed'
                          : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'
                      )}
                    >
                      <CheckCircle className="h-4 w-4 text-green-400" />
                      <div>
                        <div className="font-medium">Active</div>
                        <div className="text-xs text-zinc-500">Project is in active development</div>
                      </div>
                    </button>
                    <button
                      onClick={() => handleStatusChange('DEPRECATED')}
                      disabled={project.status === 'DEPRECATED' || actionLoading === 'status'}
                      className={cn(
                        'w-full flex items-center gap-2 p-2 rounded-lg text-left text-sm transition-colors',
                        project.status === 'DEPRECATED'
                          ? 'bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 cursor-not-allowed'
                          : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'
                      )}
                    >
                      <AlertTriangle className="h-4 w-4 text-yellow-400" />
                      <div>
                        <div className="font-medium">Deprecated</div>
                        <div className="text-xs text-zinc-500">Project is outdated but kept for reference</div>
                      </div>
                    </button>
                    <button
                      onClick={() => handleStatusChange('ARCHIVED')}
                      disabled={project.status === 'ARCHIVED' || actionLoading === 'status'}
                      className={cn(
                        'w-full flex items-center gap-2 p-2 rounded-lg text-left text-sm transition-colors',
                        project.status === 'ARCHIVED'
                          ? 'bg-zinc-500/10 border border-zinc-500/30 text-zinc-400 cursor-not-allowed'
                          : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'
                      )}
                    >
                      <Archive className="h-4 w-4 text-zinc-400" />
                      <div>
                        <div className="font-medium">Archived</div>
                        <div className="text-xs text-zinc-500">Project is no longer maintained</div>
                      </div>
                    </button>
                  </div>

                  <div>
                    <label className="text-xs text-zinc-500 block mb-1">Note (optional)</label>
                    <input
                      type="text"
                      value={statusNote}
                      onChange={(e) => setStatusNote(e.target.value)}
                      placeholder="Reason for status change..."
                      className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  </div>

                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setShowStatusModal(false);
                      setStatusNote('');
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
