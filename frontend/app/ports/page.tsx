'use client';

/**
 * Ports Page - Port allocation table across all projects
 */

import { useState, useEffect } from 'react';
import { RefreshCw, Search, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn, getServiceTypeColor } from '@/lib/utils';
import { useUrlState, stringParam } from '@/hooks/use-url-state';

interface PortWithProject {
  id: string;
  port: number;
  serviceName: string;
  serviceType: string;
  protocol: string;
  internalPort: number | null;
  url: string | null;
  projectName: string;
  projectId: string;
  isRunning: boolean;
}

export default function PortsPage() {
  const [ports, setPorts] = useState<PortWithProject[]>([]);
  const [loading, setLoading] = useState(true);
  // URL-backed search + filter — survives back/refresh.
  const [{ q: searchQuery, type: filterType }, setUrlState] = useUrlState({
    q: stringParam('q', ''),
    type: stringParam('type', 'all'),
  });
  const setSearchQuery = (v: string) => setUrlState({ q: v });
  const setFilterType = (v: string) => setUrlState({ type: v });

  const fetchPorts = async () => {
    try {
      const res = await fetch('/api/projects');
      const data = await res.json();
      if (data.success) {
        // Flatten ports from all projects
        const allPorts: PortWithProject[] = data.data.projects.flatMap((project: { id: string; name: string; isRunning: boolean; ports: Array<{ id: string; port: number; serviceName: string; serviceType: string; protocol: string; internalPort: number | null; url: string | null }> }) =>
          project.ports.map((port) => ({
            ...port,
            projectName: project.name,
            projectId: project.id,
            isRunning: project.isRunning,
          }))
        );
        // Sort by port number
        allPorts.sort((a, b) => a.port - b.port);
        setPorts(allPorts);
      }
    } catch (error) {
      console.error('Failed to fetch ports:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPorts();
    const interval = setInterval(fetchPorts, 10000);
    return () => clearInterval(interval);
  }, []);

  const serviceTypes = ['all', ...new Set(ports.map(p => p.serviceType))];

  const filteredPorts = ports.filter(p => {
    const matchesSearch =
      p.serviceName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.projectName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.port.toString().includes(searchQuery);
    const matchesType = filterType === 'all' || p.serviceType === filterType;
    return matchesSearch && matchesType;
  });

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
          <h1 className="text-2xl font-bold text-white">Port Allocation</h1>
          <p className="text-zinc-400 mt-1">
            {ports.length} ports allocated across all projects
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500"
          >
            {serviceTypes.map(type => (
              <option key={type} value={type}>
                {type === 'all' ? 'All Types' : type}
              </option>
            ))}
          </select>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search ports..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 w-64"
            />
          </div>
          <Button variant="outline" size="sm" onClick={fetchPorts}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Port Ranges Legend */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-zinc-400 mb-3">Port Ranges</h3>
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-cyan-600"></span>
            <span className="text-sm text-zinc-300">Frontend: 3000-3999</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-violet-600"></span>
            <span className="text-sm text-zinc-300">Backend: 8000-8999</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-emerald-600"></span>
            <span className="text-sm text-zinc-300">Database: 5432-5599</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-amber-600"></span>
            <span className="text-sm text-zinc-300">Cache: 6379-6499</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-zinc-600"></span>
            <span className="text-sm text-zinc-300">Other: Various</span>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left p-4 text-zinc-400 font-medium">Port</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Service</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Type</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Project</th>
              <th className="text-left p-4 text-zinc-400 font-medium">Status</th>
              <th className="text-left p-4 text-zinc-400 font-medium">URL</th>
            </tr>
          </thead>
          <tbody>
            {filteredPorts.map((port) => (
              <tr key={port.id} className="border-b border-zinc-800 hover:bg-zinc-800/50">
                <td className="p-4">
                  <span className="font-mono text-white">{port.port}</span>
                  {port.internalPort && port.internalPort !== port.port && (
                    <span className="text-zinc-500 text-sm ml-2">→ {port.internalPort}</span>
                  )}
                </td>
                <td className="p-4">
                  <span className="text-white">{port.serviceName}</span>
                </td>
                <td className="p-4">
                  <span className={cn(
                    'px-2 py-1 text-xs rounded-full text-white',
                    getServiceTypeColor(port.serviceType)
                  )}>
                    {port.serviceType}
                  </span>
                </td>
                <td className="p-4">
                  <span className="text-zinc-300">{port.projectName}</span>
                </td>
                <td className="p-4">
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      'w-2 h-2 rounded-full',
                      port.isRunning ? 'bg-green-500' : 'bg-zinc-600'
                    )} />
                    <span className={cn(
                      'text-sm',
                      port.isRunning ? 'text-green-400' : 'text-zinc-500'
                    )}>
                      {port.isRunning ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                </td>
                <td className="p-4">
                  {port.url && port.isRunning ? (
                    <a
                      href={port.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
                    >
                      <ExternalLink className="h-3 w-3" />
                      <span className="text-sm truncate max-w-[200px]">{port.url}</span>
                    </a>
                  ) : port.url ? (
                    <span className="text-zinc-500 text-sm truncate max-w-[200px]">{port.url}</span>
                  ) : (
                    <span className="text-zinc-600 text-sm">-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filteredPorts.length === 0 && (
          <div className="p-8 text-center text-zinc-500">
            No ports found matching your filters
          </div>
        )}
      </div>
    </div>
  );
}
