/**
 * Docker/Colima Shell Utilities
 * Functions for managing Docker VM lifecycle and containers
 */

import { execCommand } from './shell';

import type { ColimaStatus, DockerInfo, DockerContainer, ContainerMetrics } from '@/types/docker';

export async function getColimaStatus(): Promise<ColimaStatus> {
  const result = await execCommand('colima status --json', { timeout: 10000 });

  if (result.exitCode !== 0) {
    return { running: false, arch: '', runtime: '', cpu: 0, memory: 0, disk: 0 };
  }

  try {
    const data = JSON.parse(result.stdout);
    // colima status --json returns data on success (exit 0 = running)
    // memory and disk are in bytes — convert to GB
    return {
      running: true,
      arch: data.arch || '',
      runtime: data.runtime || '',
      cpu: data.cpu || 0,
      memory: data.memory ? Math.round(data.memory / (1024 * 1024 * 1024) * 10) / 10 : 0,
      disk: data.disk ? Math.round(data.disk / (1024 * 1024 * 1024) * 10) / 10 : 0,
    };
  } catch {
    return { running: false, arch: '', runtime: '', cpu: 0, memory: 0, disk: 0 };
  }
}

export async function startColima(): Promise<{ success: boolean; output: string }> {
  const result = await execCommand('colima start', {
    timeout: 90000,
    cwd: '/tmp',
  });
  return {
    success: result.exitCode === 0,
    output: result.stdout || result.stderr,
  };
}

export async function stopColima(): Promise<{ success: boolean; output: string }> {
  const result = await execCommand('colima stop', { timeout: 60000 });
  return {
    success: result.exitCode === 0,
    output: result.stdout || result.stderr,
  };
}

export async function restartColima(): Promise<{ success: boolean; output: string }> {
  const stopResult = await stopColima();
  if (!stopResult.success) {
    return { success: false, output: `Stop failed: ${stopResult.output}` };
  }
  const startResult = await startColima();
  return {
    success: startResult.success,
    output: `${stopResult.output}\n${startResult.output}`,
  };
}

export async function getDockerInfo(): Promise<DockerInfo | null> {
  const result = await execCommand('docker info --format "{{json .}}"', { timeout: 10000 });

  if (result.exitCode !== 0) {
    return null;
  }

  try {
    const data = JSON.parse(result.stdout);
    return {
      serverVersion: data.ServerVersion || '',
      containers: {
        total: data.Containers || 0,
        running: data.ContainersRunning || 0,
        paused: data.ContainersPaused || 0,
        stopped: data.ContainersStopped || 0,
      },
      images: data.Images || 0,
      memoryLimit: data.MemTotal ? Math.round(data.MemTotal / (1024 * 1024 * 1024) * 10) / 10 : 0,
      cpus: data.NCPU || 0,
    };
  } catch {
    return null;
  }
}

export async function getDockerContainers(): Promise<DockerContainer[]> {
  const result = await execCommand(
    'docker ps -a --format "{{json .}}"',
    { timeout: 10000 }
  );

  if (result.exitCode !== 0 || !result.stdout.trim()) {
    return [];
  }

  try {
    const lines = result.stdout.trim().split('\n');
    return lines.map((line) => {
      const data = JSON.parse(line);
      return {
        id: data.ID || '',
        name: (data.Names || '').replace(/^\//, ''),
        image: data.Image || '',
        status: data.Status || '',
        state: (data.State || 'dead').toLowerCase() as DockerContainer['state'],
        ports: data.Ports || '',
        created: data.CreatedAt || data.RunningFor || '',
      };
    });
  } catch {
    return [];
  }
}

export async function stopContainer(id: string): Promise<{ success: boolean; output: string }> {
  const result = await execCommand(`docker stop ${sanitizeContainerId(id)}`, { timeout: 30000 });
  return { success: result.exitCode === 0, output: result.stdout || result.stderr };
}

export async function startContainer(id: string): Promise<{ success: boolean; output: string }> {
  const result = await execCommand(`docker start ${sanitizeContainerId(id)}`, { timeout: 30000 });
  return { success: result.exitCode === 0, output: result.stdout || result.stderr };
}

export async function restartContainer(id: string): Promise<{ success: boolean; output: string }> {
  const result = await execCommand(`docker restart ${sanitizeContainerId(id)}`, { timeout: 30000 });
  return { success: result.exitCode === 0, output: result.stdout || result.stderr };
}

export async function getContainerLogs(
  id: string,
  tail: number = 100
): Promise<{ stdout: string; stderr: string }> {
  const safeTail = Math.min(Math.max(1, Math.floor(tail)), 5000);
  const result = await execCommand(
    `docker logs --tail ${safeTail} ${sanitizeContainerId(id)} 2>&1`,
    { timeout: 10000 }
  );
  return { stdout: result.stdout, stderr: result.stderr };
}

export async function getVmMemory(): Promise<{ totalMB: number; usedMB: number; freeMB: number; availableMB: number }> {
  const result = await execCommand('colima ssh -- free -m', { timeout: 10000 });
  if (result.exitCode !== 0) {
    return { totalMB: 0, usedMB: 0, freeMB: 0, availableMB: 0 };
  }

  // Parse "Mem:" line: total used free shared buff/cache available
  const memLine = result.stdout.split('\n').find((l) => l.startsWith('Mem:'));
  if (!memLine) {
    return { totalMB: 0, usedMB: 0, freeMB: 0, availableMB: 0 };
  }

  const parts = memLine.split(/\s+/);
  return {
    totalMB: parseInt(parts[1], 10) || 0,
    usedMB: parseInt(parts[2], 10) || 0,
    freeMB: parseInt(parts[3], 10) || 0,
    availableMB: parseInt(parts[6], 10) || 0,
  };
}

export interface CpuTicks {
  user: number;
  nice: number;
  system: number;
  idle: number;
  iowait: number;
  total: number;
}

export async function getVmCpuTicks(): Promise<CpuTicks> {
  const result = await execCommand('colima ssh -- cat /proc/stat', { timeout: 10000 });
  if (result.exitCode !== 0) {
    return { user: 0, nice: 0, system: 0, idle: 0, iowait: 0, total: 0 };
  }

  // First line: cpu  user nice system idle iowait irq softirq steal guest guest_nice
  const cpuLine = result.stdout.split('\n').find((l) => l.startsWith('cpu '));
  if (!cpuLine) {
    return { user: 0, nice: 0, system: 0, idle: 0, iowait: 0, total: 0 };
  }

  const parts = cpuLine.split(/\s+/).slice(1).map(Number);
  const [user, nice, system, idle, iowait] = parts;
  const total = parts.reduce((a, b) => a + b, 0);
  return { user, nice, system, idle, iowait, total };
}

export async function getVmLoadAverage(): Promise<{ load1: number; load5: number; load15: number }> {
  const result = await execCommand('colima ssh -- uptime', { timeout: 10000 });
  if (result.exitCode !== 0) {
    return { load1: 0, load5: 0, load15: 0 };
  }

  // Parse "load average: 0.36, 0.15, 0.06"
  const match = result.stdout.match(/load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)/);
  if (!match) {
    return { load1: 0, load5: 0, load15: 0 };
  }

  return {
    load1: parseFloat(match[1]) || 0,
    load5: parseFloat(match[2]) || 0,
    load15: parseFloat(match[3]) || 0,
  };
}

export async function getContainerStats(): Promise<ContainerMetrics[]> {
  const result = await execCommand('docker stats --no-stream --format "{{json .}}"', { timeout: 15000 });
  if (result.exitCode !== 0 || !result.stdout.trim()) {
    return [];
  }

  try {
    const lines = result.stdout.trim().split('\n');
    return lines.map((line) => {
      const data = JSON.parse(line);
      // CPUPerc comes as "5.10%" — strip the %
      const cpuPercent = parseFloat((data.CPUPerc || '0').replace('%', '')) || 0;
      const memPercent = parseFloat((data.MemPerc || '0').replace('%', '')) || 0;

      // MemUsage comes as "168MiB / 7.737GiB" — parse both sides
      const memParts = (data.MemUsage || '').split('/').map((s: string) => s.trim());
      const memUsageMB = parseMemToMB(memParts[0] || '0');
      const memLimitMB = parseMemToMB(memParts[1] || '0');

      return {
        name: (data.Name || '').replace(/^\//, ''),
        cpuPercent,
        memoryPercent: memPercent,
        memoryUsageMB: memUsageMB,
        memoryLimitMB: memLimitMB,
      };
    });
  } catch {
    return [];
  }
}

function parseMemToMB(str: string): number {
  const match = str.match(/([\d.]+)\s*(B|KiB|MiB|GiB|TiB|KB|MB|GB|TB)/i);
  if (!match) return 0;
  const value = parseFloat(match[1]);
  const unit = match[2].toLowerCase();
  switch (unit) {
    case 'b': return value / (1024 * 1024);
    case 'kib': case 'kb': return value / 1024;
    case 'mib': case 'mb': return value;
    case 'gib': case 'gb': return value * 1024;
    case 'tib': case 'tb': return value * 1024 * 1024;
    default: return value;
  }
}

function sanitizeContainerId(id: string): string {
  if (!id || id.length > 128) {
    throw new Error('Invalid container ID');
  }
  // Only allow alphanumeric, hyphens, underscores, dots (valid Docker container ID/name chars)
  const sanitized = id.replace(/[^a-zA-Z0-9_.\-]/g, '');
  if (!sanitized || sanitized !== id) {
    throw new Error('Invalid container ID');
  }
  return sanitized;
}
