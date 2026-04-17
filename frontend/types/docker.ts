export interface ColimaStatus {
  running: boolean;
  arch: string;
  runtime: string;
  cpu: number;
  memory: number;
  disk: number;
}

export interface DockerInfo {
  serverVersion: string;
  containers: { total: number; running: number; paused: number; stopped: number };
  images: number;
  memoryLimit: number;
  cpus: number;
}

export interface DockerContainer {
  id: string;
  name: string;
  image: string;
  status: string;
  state: 'running' | 'exited' | 'paused' | 'restarting' | 'dead';
  ports: string;
  created: string;
}

export interface DockerStatusResponse {
  colima: ColimaStatus;
  docker: DockerInfo | null;
  containers: DockerContainer[];
}

export interface VmMetrics {
  cpuPercent: number;
  memoryUsedMB: number;
  memoryTotalMB: number;
  memoryPercent: number;
  loadAvg1: number;
  loadAvg5: number;
  loadAvg15: number;
}

export interface ContainerMetrics {
  name: string;
  cpuPercent: number;
  memoryPercent: number;
  memoryUsageMB: number;
  memoryLimitMB: number;
}

export interface MetricsSnapshot {
  timestamp: number;
  vm: VmMetrics;
  containers: ContainerMetrics[];
}

export interface MetricsDataPoint {
  time: string;
  timestamp: number;
  cpuPercent: number;
  memoryPercent: number;
  memoryUsedMB: number;
  loadAvg1: number;
}
