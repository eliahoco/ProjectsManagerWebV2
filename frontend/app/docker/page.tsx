'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Play,
  Square,
  RotateCw,
  RefreshCw,
  Search,
  FileText,
  X,
  Cpu,
  HardDrive,
  MemoryStick,
  Server,
  Container,
  AlertTriangle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ColimaStatus, DockerInfo, DockerContainer } from '@/types/docker';

export default function DockerPage() {
  const [colima, setColima] = useState<ColimaStatus | null>(null);
  const [docker, setDocker] = useState<DockerInfo | null>(null);
  const [containers, setContainers] = useState<DockerContainer[]>([]);
  const [loading, setLoading] = useState(true);
  const [vmAction, setVmAction] = useState<string | null>(null);
  const [containerAction, setContainerAction] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [logsModal, setLogsModal] = useState<{ id: string; name: string } | null>(null);
  const [logs, setLogs] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/docker/status');
      const data = await res.json();
      if (data.success) {
        setColima(data.data.colima);
        setDocker(data.data.docker);
        setContainers(data.data.containers);
      }
    } catch (err) {
      console.error('Failed to fetch Docker status:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 10000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  const handleVmAction = async (action: 'start' | 'stop' | 'restart') => {
    setVmAction(action);
    setError(null);
    // Pause polling during VM operations
    if (pollRef.current) clearInterval(pollRef.current);

    // Tell the watchdog to pause during VM operations
    window.dispatchEvent(new CustomEvent('docker-vm-operation', {
      detail: { action }
    }));

    let success = false;
    try {
      const res = await fetch('/api/docker/vm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      if (!data.success) {
        setError(data.error || `Failed to ${action} VM`);
      } else {
        success = true;
      }
      await fetchStatus();
    } catch {
      setError(`Network error during ${action}`);
    } finally {
      setVmAction(null);
      // Resume polling
      pollRef.current = setInterval(fetchStatus, 10000);

      // Tell the watchdog the VM operation completed — triggers immediate health check
      window.dispatchEvent(new CustomEvent('docker-vm-ready', {
        detail: { action, success }
      }));
    }
  };

  const handleContainerAction = async (containerId: string, action: 'start' | 'stop' | 'restart') => {
    setContainerAction(containerId);
    try {
      const res = await fetch(`/api/docker/containers/${containerId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      if (!data.success) {
        setError(data.error || `Failed to ${action} container`);
      }
      await fetchStatus();
    } catch {
      setError(`Network error during container ${action}`);
    } finally {
      setContainerAction(null);
    }
  };

  const openLogs = async (containerId: string, containerName: string) => {
    setLogsModal({ id: containerId, name: containerName });
    setLogsLoading(true);
    try {
      const res = await fetch(`/api/docker/containers/${containerId}/logs?tail=200`);
      const data = await res.json();
      if (data.success) {
        setLogs(data.data.stdout || data.data.stderr || '(no output)');
      } else {
        setLogs(`Error: ${data.error}`);
      }
    } catch {
      setLogs('Failed to fetch logs');
    } finally {
      setLogsLoading(false);
    }
  };

  const refreshLogs = async () => {
    if (!logsModal) return;
    setLogsLoading(true);
    try {
      const res = await fetch(`/api/docker/containers/${logsModal.id}/logs?tail=200`);
      const data = await res.json();
      if (data.success) {
        setLogs(data.data.stdout || data.data.stderr || '(no output)');
      }
    } catch {
      // keep existing logs
    } finally {
      setLogsLoading(false);
    }
  };

  const filteredContainers = containers.filter(
    (c) =>
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.image.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const stateColor = (state: string) => {
    switch (state) {
      case 'running':
        return 'bg-green-500';
      case 'exited':
      case 'dead':
        return 'bg-red-500';
      case 'paused':
        return 'bg-yellow-500';
      case 'restarting':
        return 'bg-blue-500';
      default:
        return 'bg-zinc-500';
    }
  };

  const stateTextColor = (state: string) => {
    switch (state) {
      case 'running':
        return 'text-green-400';
      case 'exited':
      case 'dead':
        return 'text-red-400';
      case 'paused':
        return 'text-yellow-400';
      case 'restarting':
        return 'text-blue-400';
      default:
        return 'text-zinc-400';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  const isVmRunning = colima?.running ?? false;
  // Colima is up but Docker daemon inside is dead — degraded state
  const isDegraded = isVmRunning && docker === null;

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Docker VM</h1>
          <p className="text-zinc-400 mt-1">
            Manage Colima VM and Docker containers
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchStatus}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center justify-between">
          <span className="text-red-400 text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Degraded Warning Banner — Colima running but Docker daemon dead */}
      {isDegraded && (
        <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <span className="text-amber-400 text-sm font-medium">
              Docker daemon is not responding — VM is running but Docker is unavailable. Try restarting the VM.
            </span>
          </div>
        </div>
      )}

      {/* VM Status Card */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 mb-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div
              className={cn(
                'w-3 h-3 rounded-full',
                isDegraded ? 'bg-amber-500 animate-pulse' :
                isVmRunning ? 'bg-green-500 animate-pulse' : 'bg-red-500'
              )}
            />
            <div>
              <h2 className="text-lg font-semibold text-white">
                Colima VM — {isDegraded ? 'Degraded' : isVmRunning ? 'Running' : 'Stopped'}
              </h2>
              {isVmRunning && colima && (
                <p className={cn('text-sm mt-1', isDegraded ? 'text-amber-400' : 'text-zinc-400')}>
                  {isDegraded
                    ? 'VM is running but Docker daemon is not responding'
                    : `${colima.runtime} runtime \u00b7 ${colima.arch}`}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isVmRunning ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleVmAction('restart')}
                  loading={vmAction === 'restart'}
                  disabled={vmAction !== null}
                >
                  <RotateCw className="h-3.5 w-3.5" />
                  Restart
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleVmAction('stop')}
                  loading={vmAction === 'stop'}
                  disabled={vmAction !== null}
                >
                  <Square className="h-3.5 w-3.5" />
                  Stop
                </Button>
              </>
            ) : (
              <Button
                variant="success"
                size="sm"
                onClick={() => handleVmAction('start')}
                loading={vmAction === 'start'}
                disabled={vmAction !== null}
              >
                <Play className="h-3.5 w-3.5" />
                Start
              </Button>
            )}
          </div>
        </div>

        {/* VM Stats Grid */}
        {isVmRunning && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-4 border-t border-zinc-800">
            <div className="flex items-center gap-3">
              <Cpu className="h-5 w-5 text-cyan-500" />
              <div>
                <p className="text-xs text-zinc-500">CPU Cores</p>
                <p className="text-white font-medium">{colima?.cpu || docker?.cpus || '—'}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <MemoryStick className="h-5 w-5 text-purple-500" />
              <div>
                <p className="text-xs text-zinc-500">Memory</p>
                <p className="text-white font-medium">
                  {colima?.memory ? `${colima.memory} GB` : docker?.memoryLimit ? `${docker.memoryLimit} GB` : '—'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <HardDrive className="h-5 w-5 text-orange-500" />
              <div>
                <p className="text-xs text-zinc-500">Disk</p>
                <p className="text-white font-medium">
                  {colima?.disk ? `${colima.disk} GB` : '—'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Server className="h-5 w-5 text-green-500" />
              <div>
                <p className="text-xs text-zinc-500">Docker</p>
                <p className="text-white font-medium">
                  {docker?.serverVersion || '—'}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* VM Operation Loading */}
        {vmAction && (
          <div className="mt-4 pt-4 border-t border-zinc-800 flex items-center gap-3">
            <RefreshCw className="h-4 w-4 animate-spin text-cyan-500" />
            <span className="text-zinc-400 text-sm">
              {vmAction === 'start' && 'Starting Colima VM... this may take 20-30 seconds'}
              {vmAction === 'stop' && 'Stopping Colima VM...'}
              {vmAction === 'restart' && 'Restarting Colima VM... this may take 30-60 seconds'}
            </span>
          </div>
        )}
      </div>

      {/* Container Summary */}
      {isVmRunning && docker && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <p className="text-xs text-zinc-500 mb-1">Containers</p>
            <p className="text-xl font-bold text-white">{docker.containers.total}</p>
            <p className="text-xs text-zinc-500 mt-1">
              <span className="text-green-400">{docker.containers.running} running</span>
              {docker.containers.stopped > 0 && (
                <span className="text-zinc-500"> &middot; {docker.containers.stopped} stopped</span>
              )}
            </p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <p className="text-xs text-zinc-500 mb-1">Images</p>
            <p className="text-xl font-bold text-white">{docker.images}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <p className="text-xs text-zinc-500 mb-1">Resources</p>
            <p className="text-sm font-medium text-white">
              {docker.cpus} CPU &middot; {docker.memoryLimit} GB RAM
            </p>
          </div>
        </div>
      )}

      {/* Containers Table */}
      {isVmRunning ? (
        <>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Containers</h2>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
              <input
                type="text"
                placeholder="Filter containers..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 w-64"
              />
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left p-4 text-zinc-400 font-medium">Status</th>
                  <th className="text-left p-4 text-zinc-400 font-medium">Name</th>
                  <th className="text-left p-4 text-zinc-400 font-medium">Image</th>
                  <th className="text-left p-4 text-zinc-400 font-medium">Ports</th>
                  <th className="text-left p-4 text-zinc-400 font-medium">Uptime</th>
                  <th className="text-left p-4 text-zinc-400 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredContainers.map((container) => (
                  <tr key={container.id} className="border-b border-zinc-800 hover:bg-zinc-800/50">
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <div className={cn('w-2.5 h-2.5 rounded-full', stateColor(container.state))} />
                        <span className={cn('text-xs font-medium capitalize', stateTextColor(container.state))}>
                          {container.state}
                        </span>
                      </div>
                    </td>
                    <td className="p-4">
                      <span className="text-white font-medium text-sm">{container.name}</span>
                    </td>
                    <td className="p-4">
                      <span className="text-zinc-400 text-sm truncate max-w-[200px] block">{container.image}</span>
                    </td>
                    <td className="p-4">
                      <span className="text-zinc-400 text-xs font-mono truncate max-w-[200px] block">
                        {container.ports || '—'}
                      </span>
                    </td>
                    <td className="p-4">
                      <span className="text-zinc-500 text-xs">{container.status}</span>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-1.5">
                        {container.state === 'running' ? (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleContainerAction(container.id, 'restart')}
                              loading={containerAction === container.id}
                              disabled={containerAction !== null}
                              title="Restart"
                            >
                              <RotateCw className="h-3 w-3" />
                            </Button>
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => handleContainerAction(container.id, 'stop')}
                              loading={containerAction === container.id}
                              disabled={containerAction !== null}
                              title="Stop"
                            >
                              <Square className="h-3 w-3" />
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="success"
                            size="sm"
                            onClick={() => handleContainerAction(container.id, 'start')}
                            loading={containerAction === container.id}
                            disabled={containerAction !== null}
                            title="Start"
                          >
                            <Play className="h-3 w-3" />
                          </Button>
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openLogs(container.id, container.name)}
                          title="View logs"
                        >
                          <FileText className="h-3 w-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredContainers.length === 0 && (
              <div className="p-8 text-center text-zinc-500">
                {searchQuery ? `No containers matching "${searchQuery}"` : 'No containers found'}
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-12 text-center">
          <Container className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-zinc-400 mb-2">VM Not Running</h3>
          <p className="text-zinc-500 text-sm mb-4">Start the Colima VM to view and manage containers.</p>
          <Button
            variant="success"
            size="sm"
            onClick={() => handleVmAction('start')}
            loading={vmAction === 'start'}
          >
            <Play className="h-3.5 w-3.5" />
            Start Colima
          </Button>
        </div>
      )}

      {/* Logs Modal */}
      {logsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg w-[90vw] max-w-4xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-zinc-800">
              <h3 className="text-white font-medium">
                Logs — {logsModal.name}
              </h3>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={refreshLogs}
                  loading={logsLoading}
                >
                  <RefreshCw className="h-3 w-3" />
                  Refresh
                </Button>
                <button
                  onClick={() => setLogsModal(null)}
                  className="text-zinc-400 hover:text-white transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <pre className="text-xs text-zinc-300 font-mono whitespace-pre-wrap leading-relaxed">
                {logsLoading && !logs ? 'Loading...' : logs}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
