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

    // Run script detached
    const child = spawn(scriptPath, [], {
      detached: true,
      stdio: ['ignore', 'ignore', 'ignore'],
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
  const result = await execCommand(`test -f "${filePath}" && echo "exists"`, { timeout: 5000 });
  return result.stdout.trim() === 'exists';
}

/**
 * Launch a project using its launch.sh script
 */
export async function launchProject(projectPath: string): Promise<CommandResult> {
  const launchScript = path.join(projectPath, 'launch.sh');

  return execCommand(`./launch.sh`, {
    cwd: projectPath,
    timeout: 120000, // 2 minutes for project startup
    env: { ...process.env, LAUNCHED_FROM_WEB: '1' },
  });
}

/**
 * Stop a project using its stop.sh script
 */
export async function stopProject(projectPath: string): Promise<CommandResult> {
  const stopScript = path.join(projectPath, 'stop.sh');
  const dockerCompose = path.join(projectPath, 'docker-compose.yml');

  const hasStopScript = await fileExists(stopScript);
  const hasDockerCompose = await fileExists(dockerCompose);

  let stopScriptResult: CommandResult | null = null;
  let dockerResult: CommandResult | null = null;

  // Run stop.sh if it exists (stops native processes like Python services)
  if (hasStopScript) {
    stopScriptResult = await execCommand(`./stop.sh`, {
      cwd: projectPath,
      timeout: 60000,
    });
  }

  // ALSO run docker-compose down if it exists (stops Docker containers)
  if (hasDockerCompose) {
    dockerResult = await execCommand(`docker-compose down`, {
      cwd: projectPath,
      timeout: 60000,
    });
  }

  // If neither exists, return error
  if (!hasStopScript && !hasDockerCompose) {
    return {
      stdout: '',
      stderr: 'No stop.sh or docker-compose.yml found',
      exitCode: 1,
    };
  }

  // Combine results
  const stdout = [
    stopScriptResult?.stdout,
    dockerResult?.stdout
  ].filter(Boolean).join('\n');

  const stderr = [
    stopScriptResult?.stderr,
    dockerResult?.stderr
  ].filter(Boolean).join('\n');

  // Success if at least one succeeded
  const exitCode = (stopScriptResult?.exitCode === 0 || dockerResult?.exitCode === 0) ? 0 : 1;

  return { stdout, stderr, exitCode };
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
  knownPorts?: Array<{ port: number; serviceName: string; serviceType?: string }>
): Promise<{
  running: boolean;
  services: Array<{ name: string; status: ServiceStatusType; port?: number }>;
}> {
  // If we have known ports, use port checking as the ONLY source of truth
  // This is the most reliable method and avoids confusion with docker-compose
  if (knownPorts && knownPorts.length > 0) {
    try {
      const portChecks = await Promise.all(
        knownPorts.map(async (p) => {
          const inUse = await isPortInUse(p.port);
          return {
            name: p.serviceName || `Port ${p.port}`,
            status: (inUse ? 'running' : 'stopped') as ServiceStatusType,
            port: p.port,
            inUse,
          };
        })
      );

      const runningServices = portChecks.filter((s) => s.inUse);
      return {
        running: runningServices.length > 0,
        services: portChecks.map(({ name, status, port }) => ({ name, status, port })),
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
 * Start Docker Desktop (macOS only)
 */
export async function startDocker(): Promise<boolean> {
  if (process.platform !== 'darwin') return false;

  await execCommand('open -a Docker', { timeout: 5000 });

  // Wait for Docker to be ready (up to 60 seconds)
  for (let i = 0; i < 30; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    if (await isDockerRunning()) return true;
  }

  return false;
}

/**
 * Check if a port is in use
 */
export async function isPortInUse(port: number): Promise<boolean> {
  const result = await execCommand(`lsof -i :${port} -sTCP:LISTEN`, { timeout: 5000 });
  return result.exitCode === 0 && result.stdout.trim().length > 0;
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
  await execCommand('git add -A', { cwd: projectPath });

  // Commit
  const commitResult = await execCommand(`git commit -m "${commitMessage}"`, { cwd: projectPath });

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
      const nameResult = await execCommand(`git config --global user.name "${username}"`);
      if (nameResult.exitCode !== 0) {
        return { success: false, error: 'Failed to set git user.name' };
      }
    }

    if (email) {
      const emailResult = await execCommand(`git config --global user.email "${email}"`);
      if (emailResult.exitCode !== 0) {
        return { success: false, error: 'Failed to set git user.email' };
      }
    }

    // If token provided, configure credential helper for HTTPS
    if (token) {
      // Store token in git credential cache for GitHub HTTPS operations
      await execCommand('git config --global credential.helper cache');
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
  const weztermResult = await execCommand('which wezterm', { timeout: 5000 });
  if (weztermResult.exitCode === 0) {
    // Spawn the tab and capture the pane_id
    const spawnResult = await execCommand(`wezterm cli spawn --cwd "${projectPath}" -- claude "${defaultPrompt}"`, {
      timeout: 10000,
    });

    // Set the tab title to the project name
    if (spawnResult.exitCode === 0 && spawnResult.stdout.trim()) {
      const paneId = spawnResult.stdout.trim();
      await execCommand(`wezterm cli set-tab-title --pane-id "${paneId}" "${projectName}"`, {
        timeout: 5000,
      });
    }

    return spawnResult;
  }

  // Fallback to Terminal.app on macOS
  if (process.platform === 'darwin') {
    return execCommand(
      `osascript -e 'tell application "Terminal" to do script "cd \\"${projectPath}\\" && claude \\"${defaultPrompt}\\""'`,
      { timeout: 10000 }
    );
  }

  return {
    stdout: '',
    stderr: 'No supported terminal found',
    exitCode: 1,
  };
}
