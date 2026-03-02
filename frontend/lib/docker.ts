/**
 * Docker/Colima Shell Utilities
 * Functions for managing Docker VM lifecycle and containers
 */

import { execCommand } from './shell';

import type { ColimaStatus, DockerInfo, DockerContainer } from '@/types/docker';

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
