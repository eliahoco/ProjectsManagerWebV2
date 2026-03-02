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
