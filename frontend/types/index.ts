/**
 * TypeScript Type Definitions
 */

export type ProjectStatus = 'ACTIVE' | 'DEPRECATED' | 'ARCHIVED';

export interface Project {
  id: string;
  name: string;
  path: string;
  status: string; // Prisma returns string from DB
  description: string | null;
  type: string | null;
  version: string | null;
  createdAt: Date;
  updatedAt: Date;
  ports: Port[];
}

export interface Port {
  id: string;
  projectId: string;
  port: number;
  serviceName: string;
  serviceType: string; // Prisma returns string from DB
  protocol: string;
  internalPort: number | null;
  url: string | null;
  notes: string | null;
  createdAt: Date;
}

export type ServiceType =
  | 'FRONTEND'
  | 'BACKEND'
  | 'DATABASE'
  | 'CACHE'
  | 'QUEUE'
  | 'MONITORING'
  | 'OTHER';

export interface PortRange {
  id: string;
  serviceType: string;
  rangeStart: number;
  rangeEnd: number;
  description: string | null;
}

export interface Session {
  id: string;
  projectId: string;
  startedAt: Date;
  endedAt: Date | null;
  lastDone: string | null;
  nextSteps: string | null;
}

export interface ProjectWithStatus extends Project {
  isRunning: boolean;
  services: ServiceStatus[];
  gitStatus?: GitStatus;
  watchdogEnabled?: boolean;
}

export type ServiceStatusType = 'running' | 'stopped' | 'error';

export interface ServiceStatus {
  name: string;
  status: ServiceStatusType;
  port?: number;
}

export interface GitStatus {
  hasGit: boolean;
  hasRemote: boolean;
  branch: string;
  isDirty: boolean;
  uncommittedFiles: number;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface ProjectListResponse {
  projects: ProjectWithStatus[];
  total: number;
  activeCount: number;
}

export interface LaunchResult {
  success: boolean;
  message: string;
  logs?: string;
}

// Watchdog
export type WatchdogAction = 'RESTART_ATTEMPTED' | 'RESTART_SUCCESS' | 'RESTART_FAILED' | 'MAX_RETRIES_EXCEEDED';

export interface WatchdogEvent {
  id: string;
  projectId: string;
  port: number;
  serviceName: string;
  action: WatchdogAction;
  attempt: number;
  error: string | null;
  createdAt: string;
}
