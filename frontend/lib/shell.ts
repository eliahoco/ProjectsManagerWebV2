/**
 * Shell Execution Utilities
 * Safe command execution for Docker, Git, and project management
 */

import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import path from 'path';

const execAsync = promisify(exec);

export interface CommandResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

/**
 * Execute a command in a detached background process
 * Creates temp script to properly handle background execution
 */
export function execDetached(
  command: string,
  options: {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    logFile?: string;
  } = {}
): { pid: number | undefined } {
  const { cwd, logFile = '/dev/null' } = options;
  const fs = require('fs');
  const os = require('os');

  // Create a temp script
  const scriptPath = path.join(os.tmpdir(), `svc-${Date.now()}.sh`);
  const scriptContent = `#!/bin/bash
cd "${cwd || process.cwd()}"
${command} > "${logFile}" 2>&1
`;

  try {
    // Write script
    fs.writeFileSync(scriptPath, scriptContent, { mode: 0o755 });

    // Run script detached — pass env if provided, otherwise inherit parent env
    const child = spawn(scriptPath, [], {
      detached: true,
      stdio: ['ignore', 'ignore', 'ignore'],
      env: options.env || process.env,
    });

    child.unref();

    // Clean up script after delay
    setTimeout(() => {
      try { fs.unlinkSync(scriptPath); } catch {}
    }, 5000);

    return { pid: child.pid };
  } catch (err) {
    console.error('execDetached error:', err);
    return { pid: undefined };
  }
}

export interface SpawnResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

/**
 * Safe command execution using spawn() with argv arrays.
 * Unlike execCommand (which goes through /bin/sh -c), this does NOT
 * interpret shell metacharacters. Use this for all commands that include
 * user- or DB-sourced arguments to prevent shell injection.
 */
export async function spawnCommand(
  cmd: string,
  args: string[],
  options: { cwd?: string; env?: NodeJS.ProcessEnv; timeout?: number } = {}
): Promise<SpawnResult> {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, {
      cwd: options.cwd,
      env: options.env ? { ...process.env, ...options.env } : process.env,
      shell: false, // CRITICAL: no shell interpretation
    });

    let stdout = '';
    let stderr = '';
    let settled = false;

    const timer = options.timeout
      ? setTimeout(() => {
          if (settled) return;
          settled = true;
          proc.kill('SIGKILL');
          reject(new Error(`Command timed out after ${options.timeout}ms`));
        }, options.timeout)
      : null;

    proc.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
    proc.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });

    proc.on('close', (code: number | null) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve({ stdout, stderr, exitCode: code ?? 1 });
    });

    proc.on('error', (err: Error) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      reject(err);
    });
  });
}

/**
 * Execute a shell command with timeout
 */
export async function execCommand(
  command: string,
  options: {
    cwd?: string;
    timeout?: number;
    env?: NodeJS.ProcessEnv;
  } = {}
): Promise<CommandResult> {
  const { cwd, timeout = 30000, env } = options;

  try {
    const result = await execAsync(command, {
      cwd,
      timeout,
      env: { ...process.env, ...env },
      maxBuffer: 10 * 1024 * 1024, // 10MB buffer
    });

    return {
      stdout: result.stdout,
      stderr: result.stderr,
      exitCode: 0,
    };
  } catch (error: unknown) {
    const execError = error as { stdout?: string; stderr?: string; code?: number };
    return {
      stdout: execError.stdout || '',
      stderr: execError.stderr || (error as Error).message,
      exitCode: execError.code || 1,
    };
  }
}

/**
 * Check if a file exists
 */
async function fileExists(filePath: string): Promise<boolean> {
  // spawnCommand: filePath comes from callers — must not be shell-interpolated
  const result = await spawnCommand('test', ['-f', filePath], { timeout: 5000 });
  return result.exitCode === 0;
}

/**
 * Launch a project using its startup script
 * Prefers start.sh (non-interactive, starts everything) over launch.sh
 * Falls back to launch.sh -a if start.sh doesn't exist
 */
export async function launchProject(projectPath: string): Promise<CommandResult> {
  // Ensure Colima (Docker VM) is running — auto-start if needed
  await ensureColima();

  // Validate ports before launching — abort early if conflicts detected
  const portValidation = await validateProjectPorts(projectPath);
  if (!portValidation.valid) {
    const conflictLines = portValidation.conflicts.map(
      (c) => `  Port ${c.port} (${c.service}) — in use by: ${c.owner}`
    );
    return {
      stdout: `Port conflict detected for ${portValidation.project}:\n${conflictLines.join('\n')}`,
      stderr: JSON.stringify(portValidation.conflicts),
      exitCode: 2, // Distinct exit code for port conflicts
    };
  }

  const startScript = path.join(projectPath, 'start.sh');
  const launchScript = path.join(projectPath, 'launch.sh');

  const hasStartScript = await fileExists(startScript);
  const hasLaunchScript = await fileExists(launchScript);

  // Build a clean environment for the child project.
  // Remove vars from the V2 platform that could pollute child processes:
  // - DATABASE_URL (V2 uses SQLite "file:./dev.db", would break PostgreSQL services)
  // - PORT (Next.js sets this to 3601, would make child frontends bind to wrong port)
  // - Other Next.js-internal vars that shouldn't leak
  const cleanEnv = { ...process.env };
  delete cleanEnv.DATABASE_URL;
  delete cleanEnv.PORT;
  delete cleanEnv.__NEXT_PRIVATE_ORIGIN;
  delete cleanEnv.__NEXT_PRIVATE_STANDALONE_CONFIG;
  const webEnv = { ...cleanEnv, LAUNCHED_FROM_WEB: '1', NONINTERACTIVE: '1' };

  if (hasStartScript) {
    // Prefer start.sh — it's typically non-interactive and starts all services
    return execCommand(`bash start.sh`, {
      cwd: projectPath,
      timeout: 180000, // 3 minutes for full startup with services
      env: webEnv,
    });
  }

  if (hasLaunchScript) {
    // Fall back to launch.sh with -a flag to start everything
    return execCommand(`bash launch.sh -a`, {
      cwd: projectPath,
      timeout: 120000, // 2 minutes for project startup
      env: webEnv,
    });
  }

  return {
    stdout: '',
    stderr: 'No start.sh or launch.sh found in project directory',
    exitCode: 1,
  };
}

/**
 * Stop a project using its stop.sh script
 * Passes LAUNCHED_FROM_WEB=1 so stop scripts know to stop everything
 * including Docker infrastructure without prompting
 *
 * Delegates to parkProject() for consistent teardown behaviour.
 */
export async function stopProject(projectPath: string): Promise<CommandResult> {
  const result = await parkProject(projectPath);
  return {
    stdout: JSON.stringify(result.steps),
    stderr: result.success ? '' : 'One or more stop steps failed',
    exitCode: result.success ? 0 : 1,
  };
}

// ---------------------------------------------------------------------------
// Park / graceful shutdown helpers
// ---------------------------------------------------------------------------

export type RunMode = 'docker' | 'local' | 'hybrid';

/**
 * Detect whether the project services are running via Docker, local processes,
 * or a mix of both.
 *
 * Strategy:
 *  - Run `docker ps --format "{{.Ports}}"` and check if any of the project
 *    ports appear in published container ports.
 *  - Count how many ports have a matching Docker mapping vs. a plain local PID.
 */
export async function detectRunMode(
  _projectPath: string,
  ports: Array<{ port: number }>
): Promise<RunMode> {
  if (!ports || ports.length === 0) return 'local';

  try {
    const dockerResult = await execCommand(
      'docker ps --format "{{.Ports}}"',
      { timeout: 8000 }
    );

    if (dockerResult.exitCode !== 0 || !dockerResult.stdout.trim()) {
      return 'local';
    }

    const dockerPortLine = dockerResult.stdout;
    let dockerCount = 0;
    let localCount = 0;

    for (const { port } of ports) {
      // Published port pattern: "0.0.0.0:3000->3000/tcp" or ":::3000->3000/tcp"
      const inDocker = dockerPortLine.includes(`:${port}->`);
      if (inDocker) {
        dockerCount++;
      } else {
        localCount++;
      }
    }

    if (dockerCount > 0 && localCount > 0) return 'hybrid';
    if (dockerCount > 0) return 'docker';
    return 'local';
  } catch {
    return 'local';
  }
}

export interface ParkStep {
  name: string;
  port?: number;
  status: 'done' | 'skipped' | 'failed';
  detail?: string;
}

export interface ParkResult {
  success: boolean;
  steps: ParkStep[];
  duration_ms: number;
}

const SERVICE_STOP_PRIORITY: Record<string, number> = {
  FRONTEND: 1,
  BACKEND: 2,
  CACHE: 3,
  QUEUE: 4,
  DATABASE: 5,
  MONITORING: 6,
  OTHER: 7,
};

/**
 * Park (gracefully shut down) a project.
 *
 * If ports are provided the function stops each service individually using
 * SIGTERM → 3 s grace period → SIGKILL.  It also attempts a
 * `docker compose stop --time 10 <service>` for any Docker-managed port.
 *
 * If no ports are provided it falls back to the project's stop.sh /
 * docker-compose down scripts (legacy behaviour).
 */
export async function parkProject(
  projectPath: string,
  ports?: Array<{ port: number; serviceType: string; serviceName: string }>
): Promise<ParkResult> {
  const startTime = Date.now();
  const steps: ParkStep[] = [];

  // ---- Fallback: no port metadata — use stop scripts ----------------------
  if (!ports || ports.length === 0) {
    const stopScript = path.join(projectPath, 'stop.sh');
    const hasStopScript = await fileExists(stopScript);

    if (hasStopScript) {
      const result = await execCommand('bash stop.sh', {
        cwd: projectPath,
        timeout: 60000,
        env: { ...process.env, LAUNCHED_FROM_WEB: '1', NONINTERACTIVE: '1' },
      });
      steps.push({
        name: 'Run stop.sh',
        status: result.exitCode === 0 ? 'done' : 'failed',
        detail: result.stderr || result.stdout || undefined,
      });
      return { success: result.exitCode === 0, steps, duration_ms: Date.now() - startTime };
    }

    // Try docker-compose down
    const composePaths = [
      path.join(projectPath, 'docker-compose.yml'),
      path.join(projectPath, 'infrastructure', 'docker', 'docker-compose.yml'),
    ];
    for (const composePath of composePaths) {
      if (await fileExists(composePath)) {
        const composeDir = path.dirname(composePath);
        const result = await execCommand('docker compose down', {
          cwd: composeDir,
          timeout: 60000,
        });
        steps.push({
          name: 'docker compose down',
          status: result.exitCode === 0 ? 'done' : 'failed',
          detail: result.stderr || result.stdout || undefined,
        });
        return { success: result.exitCode === 0, steps, duration_ms: Date.now() - startTime };
      }
    }

    steps.push({ name: 'No stop mechanism found', status: 'skipped', detail: 'No stop.sh or docker-compose.yml' });
    return { success: false, steps, duration_ms: Date.now() - startTime };
  }

  // ---- Port-aware teardown ------------------------------------------------
  const sortedPorts = [...ports].sort(
    (a, b) =>
      (SERVICE_STOP_PRIORITY[a.serviceType] ?? 99) -
      (SERVICE_STOP_PRIORITY[b.serviceType] ?? 99)
  );

  let overallSuccess = true;

  for (const portRecord of sortedPorts) {
    const { port, serviceName, serviceType } = portRecord;
    const stepName = `Stop ${serviceName} (${serviceType} :${port})`;

    // Validate port is a safe integer
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      steps.push({ name: stepName, port, status: 'skipped', detail: 'Invalid port number' });
      continue;
    }

    let stopped = false;

    // 1. Try docker compose stop for this service first
    try {
      // Sanitize serviceName for shell — only allow word chars, hyphens, dots
      const safeServiceName = serviceName.replace(/[^a-zA-Z0-9_.\-]/g, '');
      if (safeServiceName && safeServiceName === serviceName) {
        const dockerResult = await execCommand(
          `docker compose stop --time 10 ${safeServiceName}`,
          { cwd: projectPath, timeout: 20000 }
        );
        if (dockerResult.exitCode === 0) {
          stopped = true;
          steps.push({ name: stepName, port, status: 'done', detail: 'docker compose stop' });
          continue;
        }
      }
    } catch {
      // Not a Docker service or compose not available — fall through to PID kill
    }

    // 2. Graceful PID-based stop: SIGTERM → 3 s → SIGKILL
    try {
      const lsofResult = await execCommand(`lsof -ti :${port}`, { timeout: 5000 });
      const rawPids = lsofResult.stdout.trim().split('\n').filter(Boolean);

      // Security: validate every PID is purely numeric
      const pids = rawPids.filter((p) => /^\d+$/.test(p));

      if (pids.length === 0) {
        steps.push({ name: stepName, port, status: 'skipped', detail: 'Port already free' });
        continue;
      }

      // SIGTERM
      for (const pid of pids) {
        await execCommand(`kill -15 ${pid}`, { timeout: 5000 });
      }

      // 3-second grace period
      await new Promise((resolve) => setTimeout(resolve, 3000));

      // Check if still alive, then SIGKILL
      const checkResult = await execCommand(`lsof -ti :${port}`, { timeout: 5000 });
      const remainingPids = checkResult.stdout
        .trim()
        .split('\n')
        .filter((p) => /^\d+$/.test(p));

      if (remainingPids.length > 0) {
        for (const pid of remainingPids) {
          await execCommand(`kill -9 ${pid}`, { timeout: 5000 });
        }
        steps.push({
          name: stepName,
          port,
          status: 'done',
          detail: `SIGKILL ${remainingPids.join(', ')} after grace period`,
        });
      } else {
        steps.push({
          name: stepName,
          port,
          status: 'done',
          detail: `SIGTERM ${pids.join(', ')}`,
        });
      }

      stopped = true;
    } catch (err) {
      steps.push({
        name: stepName,
        port,
        status: 'failed',
        detail: (err as Error).message,
      });
      overallSuccess = false;
    }

    if (!stopped && !steps.find((s) => s.port === port && s.status !== 'skipped')) {
      steps.push({ name: stepName, port, status: 'skipped', detail: 'Nothing to stop' });
    }
  }

  return { success: overallSuccess, steps, duration_ms: Date.now() - startTime };
}

// --- Colima (Docker VM) Auto-Start -------------------------------------------

/**
 * Ensure Colima is running before launching any project.
 * If Docker is not available, attempts to start Colima automatically.
 * Silently succeeds if Docker is already running or Colima starts successfully.
 */
async function ensureColima(): Promise<void> {
  // Check if Docker is already available
  const dockerCheck = await execCommand('docker info', { timeout: 10000 });
  if (dockerCheck.exitCode === 0) return;

  // Docker not available — try to start Colima
  const colimaCheck = await execCommand('command -v colima', { timeout: 5000 });
  if (colimaCheck.exitCode !== 0) return; // Colima not installed, let launch script handle it

  console.log('[shell] Docker not available — starting Colima...');
  const startResult = await execCommand('colima start', { timeout: 120000 });

  if (startResult.exitCode === 0) {
    console.log('[shell] Colima started successfully');
  } else {
    console.error('[shell] Colima start failed:', startResult.stderr);
  }
}

// --- Port Validation Types ---------------------------------------------------

export interface PortStatus {
  port: number;
  service: string;
  type: string;
  status: 'free' | 'self' | 'conflict';
}

export interface PortConflict {
  port: number;
  service: string;
  owner: string;
}

export interface PortValidationResult {
  valid: boolean;
  project: string;
  ports: PortStatus[];
  conflicts: PortConflict[];
}

const VALIDATE_PORTS_SCRIPT = '/Volumes/Seagate/Claude/_shared/validate-ports.sh';

/**
 * Validate project ports before launch using the central validate-ports.sh script.
 * Returns { valid: true } on any error so we never block launches due to validation issues.
 */
export async function validateProjectPorts(projectPath: string): Promise<PortValidationResult> {
  const projectName = path.basename(projectPath);
  const emptyResult: PortValidationResult = {
    valid: true,
    project: projectName,
    ports: [],
    conflicts: [],
  };

  try {
    // Check if the validation script exists
    const scriptExists = await fileExists(VALIDATE_PORTS_SCRIPT);
    if (!scriptExists) {
      return emptyResult;
    }

    // spawnCommand: projectName is path.basename(projectPath) — must not be shell-interpolated
    const result = await spawnCommand(
      'bash',
      [VALIDATE_PORTS_SCRIPT, '--check-only', '--json', projectName],
      { timeout: 15000 }
    );

    if (result.exitCode !== 0 && !result.stdout.trim()) {
      // Script failed and produced no JSON output — don't block launch
      return emptyResult;
    }

    // Parse JSON from stdout (the script outputs JSON to stdout)
    const output = result.stdout.trim();
    if (!output) {
      return emptyResult;
    }

    const parsed = JSON.parse(output);

    const ports: PortStatus[] = (parsed.ports || []).map((p: Record<string, unknown>) => ({
      port: p.port as number,
      service: p.service as string,
      type: p.type as string,
      status: p.status as 'free' | 'self' | 'conflict',
    }));

    const conflicts: PortConflict[] = (parsed.conflicts || []).map((c: Record<string, unknown>) => ({
      port: c.port as number,
      service: c.service as string,
      owner: c.owner as string,
    }));

    return {
      valid: conflicts.length === 0,
      project: parsed.project || projectName,
      ports,
      conflicts,
    };
  } catch {
    // Any error (script not found, JSON parse error, etc.) — don't block launch
    return emptyResult;
  }
}

export type ServiceStatusType = 'running' | 'stopped' | 'error';

/**
 * Map Docker container state to our status type
 */
function mapContainerState(state: string): ServiceStatusType {
  const lowerState = state.toLowerCase();
  if (lowerState === 'running' || lowerState === 'up') return 'running';
  if (lowerState === 'exited' || lowerState === 'stopped' || lowerState === 'dead') return 'stopped';
  return 'error';
}

/**
 * Get project status using port checks, docker-compose, or PID files
 */
export async function getProjectStatus(
  projectPath: string,
  knownPorts?: Array<{ port: number; serviceName: string; serviceType?: string; url?: string | null; notes?: string | null }>
): Promise<{
  running: boolean;
  services: Array<{ name: string; status: ServiceStatusType; port?: number; remote?: boolean }>;
}> {
  // If we have known ports, use port checking as the ONLY source of truth
  // This is the most reliable method and avoids confusion with docker-compose
  if (knownPorts && knownPorts.length > 0) {
    try {
      const portChecks = await Promise.all(
        knownPorts.map(async (p) => {
          const isRemote = p.notes?.startsWith('REMOTE:') || false;
          let inUse = false;

          if (isRemote && p.url) {
            // Remote service — check via HTTP curl instead of local lsof
            inUse = await isRemoteServiceUp(p.url);
          } else {
            // Local service — check via lsof
            inUse = await isPortInUse(p.port);
          }

          return {
            name: `${p.serviceName || `Port ${p.port}`}${isRemote ? ' (remote)' : ''}`,
            status: (inUse ? 'running' : 'stopped') as ServiceStatusType,
            port: p.port,
            inUse,
            remote: isRemote,
          };
        })
      );

      const runningServices = portChecks.filter((s) => s.inUse);
      return {
        running: runningServices.length > 0,
        services: portChecks.map(({ name, status, port, remote }) => ({ name, status, port, remote })),
      };
    } catch (error) {
      // If port checking fails, return all as stopped
      console.error('Port checking failed:', error);
      return {
        running: false,
        services: knownPorts.map((p) => ({
          name: p.serviceName || `Port ${p.port}`,
          status: 'stopped' as ServiceStatusType,
          port: p.port,
        })),
      };
    }
  }

  // No known ports - try docker-compose (for projects without configured ports)
  try {
    const dockerResult = await execCommand('docker-compose ps --format json', {
      cwd: projectPath,
      timeout: 5000,
    });

    if (dockerResult.exitCode === 0 && dockerResult.stdout.trim()) {
      const containers = JSON.parse(`[${dockerResult.stdout.trim().split('\n').join(',')}]`);
      const services = containers.map((c: { Name: string; State: string; Publishers?: Array<{ PublishedPort: number }> }) => ({
        name: c.Name,
        status: mapContainerState(c.State),
        port: c.Publishers?.[0]?.PublishedPort,
      }));
      if (services.length > 0) {
        return {
          running: services.some((s: { status: ServiceStatusType }) => s.status === 'running'),
          services,
        };
      }
    }
  } catch {
    // Docker-compose failed, continue to next method
  }

  // Try checking for PID files
  try {
    const pidResult = await execCommand('ls logs/*.pid 2>/dev/null', {
      cwd: projectPath,
      timeout: 3000,
    });

    if (pidResult.exitCode === 0 && pidResult.stdout.trim()) {
      const pidFiles = pidResult.stdout.trim().split('\n');
      const services = pidFiles.map((file) => ({
        name: path.basename(file, '.pid'),
        status: 'running' as ServiceStatusType,
      }));
      return { running: true, services };
    }
  } catch {
    // PID check failed
  }

  return { running: false, services: [] };
}

/**
 * Check if Docker is running
 */
export async function isDockerRunning(): Promise<boolean> {
  const result = await execCommand('docker info', { timeout: 5000 });
  return result.exitCode === 0;
}

/**
 * Check if Docker can be started (Colima-based setup)
 * Note: Docker is provided by Colima, not Docker Desktop.
 * If Colima is not running, the user must start it manually with: colima start
 */
export async function startDocker(): Promise<boolean> {
  // Docker should already be running via Colima (auto-starts on boot via brew services).
  // If it's not running, we can't auto-start it from here — user needs to run: colima start
  return await isDockerRunning();
}

/**
 * Check if a port is in use
 */
export async function isPortInUse(port: number): Promise<boolean> {
  const result = await execCommand(`lsof -i :${port} -sTCP:LISTEN`, { timeout: 5000 });
  return result.exitCode === 0 && result.stdout.trim().length > 0;
}

/**
 * Check if a remote service is reachable via HTTP
 * Used for services running on remote machines (e.g., PC at 192.168.1.209)
 */
export async function isRemoteServiceUp(url: string): Promise<boolean> {
  try {
    // spawnCommand: url comes from DB Port.url field — must not be shell-interpolated
    const result = await spawnCommand(
      'curl',
      ['-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '3', url],
      { timeout: 5000 }
    );
    const statusCode = parseInt(result.stdout.trim(), 10);
    return statusCode > 0 && statusCode < 500;
  } catch {
    return false;
  }
}

/**
 * Get Git status for a project
 */
export async function getGitStatus(projectPath: string): Promise<{
  hasGit: boolean;
  hasRemote: boolean;
  branch: string;
  isDirty: boolean;
  uncommittedFiles: number;
}> {
  const hasGitResult = await execCommand('git rev-parse --git-dir', { cwd: projectPath });
  if (hasGitResult.exitCode !== 0) {
    return { hasGit: false, hasRemote: false, branch: '', isDirty: false, uncommittedFiles: 0 };
  }

  const branchResult = await execCommand('git branch --show-current', { cwd: projectPath });
  const remoteResult = await execCommand('git remote get-url origin', { cwd: projectPath });
  const statusResult = await execCommand('git status --porcelain', { cwd: projectPath });

  const uncommittedFiles = statusResult.stdout.trim().split('\n').filter(Boolean).length;

  return {
    hasGit: true,
    hasRemote: remoteResult.exitCode === 0,
    branch: branchResult.stdout.trim(),
    isDirty: uncommittedFiles > 0,
    uncommittedFiles,
  };
}

/**
 * Sync project to GitHub (push)
 */
export async function syncToGitHub(projectPath: string, message?: string): Promise<CommandResult> {
  const commitMessage = message || `Update ${path.basename(projectPath)} - ${new Date().toISOString().split('T')[0]}`;

  // Add all changes
  await execCommand('git add -A', { cwd: projectPath }); // SAFE: constant args, no user input

  // Commit
  // spawnCommand: commitMessage comes from caller — must not be shell-interpolated
  const commitResult = await spawnCommand('git', ['commit', '-m', commitMessage], { cwd: projectPath });

  // Push
  if (commitResult.exitCode === 0 || commitResult.stderr.includes('nothing to commit')) {
    return execCommand('git push', { cwd: projectPath, timeout: 60000 });
  }

  return commitResult;
}

/**
 * Configure git credentials from saved settings
 */
export async function configureGitCredentials(
  username: string,
  email: string,
  token?: string
): Promise<{ success: boolean; error?: string }> {
  try {
    if (username) {
      // spawnCommand: username comes from caller — must not be shell-interpolated
      const nameResult = await spawnCommand('git', ['config', '--global', 'user.name', username]);
      if (nameResult.exitCode !== 0) {
        return { success: false, error: 'Failed to set git user.name' };
      }
    }

    if (email) {
      // spawnCommand: email comes from caller — must not be shell-interpolated
      const emailResult = await spawnCommand('git', ['config', '--global', 'user.email', email]);
      if (emailResult.exitCode !== 0) {
        return { success: false, error: 'Failed to set git user.email' };
      }
    }

    // If token provided, configure credential helper for HTTPS
    if (token) {
      // Store token in git credential cache for GitHub HTTPS operations
      await execCommand('git config --global credential.helper cache'); // SAFE: constant args, no user input
    }

    return { success: true };
  } catch (error) {
    return { success: false, error: (error as Error).message };
  }
}

/**
 * Open Claude with project context
 */
export async function openClaudeWithContext(
  projectPath: string,
  prompt?: string
): Promise<CommandResult> {
  const defaultPrompt = prompt ||
    `Read the file ${projectPath}/PROJECT_DESCRIPTOR.md now and summarize what this project is about.`;

  // Extract project name from path for tab title
  const projectName = path.basename(projectPath);

  // Try WezTerm first
  const weztermResult = await execCommand('which wezterm', { timeout: 5000 }); // SAFE: constant args, no user input
  if (weztermResult.exitCode === 0) {
    // spawnCommand: projectPath and defaultPrompt come from callers — must not be shell-interpolated
    const spawnResult = await spawnCommand(
      'wezterm',
      ['cli', 'spawn', '--cwd', projectPath, '--', 'claude', defaultPrompt],
      { timeout: 10000 }
    );

    // Set the tab title to the project name
    if (spawnResult.exitCode === 0 && spawnResult.stdout.trim()) {
      const paneId = spawnResult.stdout.trim();
      // spawnCommand: paneId comes from wezterm output; projectName from path.basename — must not be shell-interpolated
      await spawnCommand(
        'wezterm',
        ['cli', 'set-tab-title', '--pane-id', paneId, projectName],
        { timeout: 5000 }
      );
    }

    return spawnResult;
  }

  // Fallback to Terminal.app on macOS
  if (process.platform === 'darwin') {
    // osascript requires a single AppleScript string; we build it safely using JSON.stringify
    // to escape projectPath and defaultPrompt, preventing shell/AppleScript injection.
    const script = `tell application "Terminal" to do script ${JSON.stringify(
      'cd ' + JSON.stringify(projectPath) + ' && claude ' + JSON.stringify(defaultPrompt)
    )}`;
    // spawnCommand: the script string is built by JS (not user-interpolated into a shell command)
    return spawnCommand('osascript', ['-e', script], { timeout: 10000 });
  }

  return {
    stdout: '',
    stderr: 'No supported terminal found',
    exitCode: 1,
  };
}
