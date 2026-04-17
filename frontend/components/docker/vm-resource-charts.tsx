'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Activity, Cpu, MemoryStick } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MetricsSnapshot, MetricsDataPoint, ContainerMetrics } from '@/types/docker';

const MAX_HISTORY = 60; // 5 minutes at 5s intervals
const POLL_INTERVAL = 5000;

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatMB(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; dataKey: string; color: string }>;
  label?: string;
}

function ChartTooltipContent({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs text-zinc-400 mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="text-sm font-medium" style={{ color: entry.color }}>
          {entry.value.toFixed(1)}%
        </p>
      ))}
    </div>
  );
}

export default function VmResourceCharts() {
  const [history, setHistory] = useState<MetricsDataPoint[]>([]);
  const [containers, setContainers] = useState<ContainerMetrics[]>([]);
  const [isLive, setIsLive] = useState(true);
  const [warmingUp, setWarmingUp] = useState(true);
  const [latestVm, setLatestVm] = useState<{ cpuPercent: number; memoryPercent: number; memoryUsedMB: number; memoryTotalMB: number; loadAvg1: number; loadAvg5: number; loadAvg15: number } | null>(null);
  const historyRef = useRef<MetricsDataPoint[]>([]);
  const pausedRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMetrics = useCallback(async () => {
    if (pausedRef.current) return;

    try {
      const res = await fetch('/api/docker/metrics');
      if (!res.ok) return;

      const json = await res.json();
      if (!json.success) return;

      const snapshot: MetricsSnapshot = json.data;
      setContainers(snapshot.containers);
      setLatestVm(snapshot.vm);

      // Skip warming-up reading (cpuPercent === -1 means no previous reading)
      if (snapshot.vm.cpuPercent < 0) {
        setWarmingUp(true);
        return;
      }

      setWarmingUp(false);

      const point: MetricsDataPoint = {
        time: formatTime(snapshot.timestamp),
        timestamp: snapshot.timestamp,
        cpuPercent: snapshot.vm.cpuPercent,
        memoryPercent: snapshot.vm.memoryPercent,
        memoryUsedMB: snapshot.vm.memoryUsedMB,
        loadAvg1: snapshot.vm.loadAvg1,
      };

      const updated = [...historyRef.current, point].slice(-MAX_HISTORY);
      historyRef.current = updated;
      setHistory(updated);
    } catch {
      // Network error — skip this tick
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    intervalRef.current = setInterval(fetchMetrics, POLL_INTERVAL);

    const handlePause = () => { pausedRef.current = true; };
    const handleResume = () => {
      pausedRef.current = false;
      // Reset CPU delta since the VM might have restarted
      setWarmingUp(true);
    };

    window.addEventListener('docker-vm-operation', handlePause);
    window.addEventListener('docker-vm-ready', handleResume);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      window.removeEventListener('docker-vm-operation', handlePause);
      window.removeEventListener('docker-vm-ready', handleResume);
    };
  }, [fetchMetrics]);

  const sortedContainers = [...containers].sort((a, b) => b.cpuPercent - a.cpuPercent);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-cyan-500" />
          <h2 className="text-lg font-semibold text-white">VM Resource Monitor</h2>
        </div>
        <div className="flex items-center gap-2">
          {warmingUp && (
            <span className="text-xs text-zinc-500 animate-pulse">Warming up...</span>
          )}
          <div className={cn(
            'flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium',
            isLive ? 'bg-green-500/10 text-green-400' : 'bg-zinc-700 text-zinc-400'
          )}>
            <div className={cn('w-1.5 h-1.5 rounded-full', isLive ? 'bg-green-500 animate-pulse' : 'bg-zinc-500')} />
            {isLive ? 'Live' : 'Paused'}
          </div>
          <button
            onClick={() => {
              setIsLive(!isLive);
              pausedRef.current = isLive;
            }}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {isLive ? 'Pause' : 'Resume'}
          </button>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-5">
        {/* CPU Chart */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="h-4 w-4 text-cyan-500" />
            <span className="text-sm font-medium text-zinc-300">CPU Usage</span>
          </div>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickLine={{ stroke: '#3f3f46' }}
                  axisLine={{ stroke: '#3f3f46' }}
                  interval="preserveStartEnd"
                  minTickGap={40}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickLine={{ stroke: '#3f3f46' }}
                  axisLine={{ stroke: '#3f3f46' }}
                  tickFormatter={(v) => `${v}%`}
                  width={40}
                />
                <Tooltip content={<ChartTooltipContent />} />
                <Line
                  type="monotone"
                  dataKey="cpuPercent"
                  stroke="#06b6d4"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-zinc-500 mt-2">
            Current: <span className="text-cyan-400 font-medium">
              {latestVm && latestVm.cpuPercent >= 0 ? `${latestVm.cpuPercent.toFixed(1)}%` : '—'}
            </span>
          </p>
        </div>

        {/* Memory Chart */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <MemoryStick className="h-4 w-4 text-purple-500" />
            <span className="text-sm font-medium text-zinc-300">Memory Usage</span>
          </div>
          <div className="h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickLine={{ stroke: '#3f3f46' }}
                  axisLine={{ stroke: '#3f3f46' }}
                  interval="preserveStartEnd"
                  minTickGap={40}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickLine={{ stroke: '#3f3f46' }}
                  axisLine={{ stroke: '#3f3f46' }}
                  tickFormatter={(v) => `${v}%`}
                  width={40}
                />
                <Tooltip content={<ChartTooltipContent />} />
                <Line
                  type="monotone"
                  dataKey="memoryPercent"
                  stroke="#a855f7"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-zinc-500 mt-2">
            Current: <span className="text-purple-400 font-medium">
              {latestVm ? `${formatMB(latestVm.memoryUsedMB)} / ${formatMB(latestVm.memoryTotalMB)} (${latestVm.memoryPercent.toFixed(1)}%)` : '—'}
            </span>
          </p>
        </div>
      </div>

      {/* Load Average */}
      {latestVm && (
        <div className="flex items-center gap-4 mb-5 px-3 py-2.5 bg-zinc-800/50 rounded-lg">
          <span className="text-xs text-zinc-500 font-medium">Load Average:</span>
          <span className="text-sm text-zinc-300 font-mono">
            {latestVm.loadAvg1.toFixed(2)} / {latestVm.loadAvg5.toFixed(2)} / {latestVm.loadAvg15.toFixed(2)}
          </span>
          <span className="text-xs text-zinc-600">(1m / 5m / 15m)</span>
        </div>
      )}

      {/* Container Resources Table */}
      {sortedContainers.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-zinc-300 mb-3">Container Resources</h3>
          <div className="space-y-2">
            {sortedContainers.map((c) => (
              <div key={c.name} className="flex items-center gap-4 px-3 py-2 bg-zinc-800/30 rounded-lg">
                <span className="text-sm text-zinc-300 font-medium w-48 truncate" title={c.name}>
                  {c.name}
                </span>
                {/* CPU bar */}
                <div className="flex items-center gap-2 flex-1">
                  <span className="text-xs text-zinc-500 w-8">CPU</span>
                  <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-cyan-500 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(c.cpuPercent, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-zinc-400 w-14 text-right font-mono">
                    {c.cpuPercent.toFixed(1)}%
                  </span>
                </div>
                {/* Memory bar */}
                <div className="flex items-center gap-2 flex-1">
                  <span className="text-xs text-zinc-500 w-8">Mem</span>
                  <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-purple-500 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(c.memoryPercent, 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-zinc-400 w-14 text-right font-mono">
                    {c.memoryPercent.toFixed(1)}%
                  </span>
                </div>
                <span className="text-xs text-zinc-600 w-28 text-right">
                  {formatMB(c.memoryUsageMB)} / {formatMB(c.memoryLimitMB)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
