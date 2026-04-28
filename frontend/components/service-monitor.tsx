'use client';

/**
 * Global Service Monitor
 * Watches all projects for service status changes and shows alerts.
 * Includes Watchdog auto-restart logic: when a project has watchdogEnabled,
 * down services are automatically started up to 3 times within a 5-minute window.
 *
 * Design:
 * - Manual-stop state is persisted in localStorage so it survives HMR/page refresh.
 * - First poll cycle after mount is "warm-up" — baseline recording only, no actions.
 * - After warm-up, if watchdog is ON and a service is down and NOT manually stopped → start it.
 * - Debounce: require 2+ consecutive "down" readings before acting (filters lsof false negatives).
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { AlertTriangle, RefreshCw, X, Play, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ServiceAlert {
  id: string;
  projectId: string;
  projectName: string;
  serviceName: string;
  port: number;
  status: 'parked' | 'crashed';
  timestamp: Date;
  dismissed: boolean;
  watchdogStatus?: 'restarting' | 'success' | 'failed' | 'gave-up';
  watchdogAttempt?: number;
}

interface RestartTracker {
  attempts: number;
  firstAttemptAt: number;
  lastAttemptAt: number;
  inProgress: boolean;
  gaveUp: boolean;
}

// localStorage key for persisting manually-stopped services across refreshes
const LS_MANUAL_STOPS_KEY = 'watchdog-manually-stopped';
// localStorage key for persisting Docker pause state across HMR/page refresh
const LS_DOCKER_PAUSED_KEY = 'watchdog-docker-paused';
// Docker pause safety timeout — force-resume after 5 minutes
const DOCKER_PAUSE_TIMEOUT_MS = 5 * 60 * 1000;
// Docker health poll interval — 5s (more frequent than 15s service poll for fast recovery)
const DOCKER_HEALTH_POLL_MS = 5000;
// Minimum time the watchdog must stay paused before health poll can resume it.
// This prevents the race where Docker is still "healthy" when the pause starts
// (VM hasn't shut down yet) and the immediate health check resumes too early.
const DOCKER_PAUSE_MIN_MS = 15_000;

// Helper: load manually-stopped set from localStorage
function loadManualStops(): Set<string> {
  try {
    const raw = localStorage.getItem(LS_MANUAL_STOPS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.every(item => typeof item === 'string')) {
        return new Set(parsed);
      }
    }
  } catch { /* ignore parse errors */ }
  return new Set();
}

// Helper: save manually-stopped set to localStorage
function saveManualStops(set: Set<string>) {
  try {
    localStorage.setItem(LS_MANUAL_STOPS_KEY, JSON.stringify([...set]));
  } catch { /* ignore storage errors */ }
}

// Helper: load Docker pause state from localStorage (returns { paused, startedAt } or null)
function loadDockerPause(): { paused: boolean; startedAt: number } | null {
  try {
    const raw = localStorage.getItem(LS_DOCKER_PAUSED_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed.startedAt === 'number') {
        // Only restore if < 5 minutes old
        if (Date.now() - parsed.startedAt < DOCKER_PAUSE_TIMEOUT_MS) {
          return parsed;
        }
        // Expired — clean up
        localStorage.removeItem(LS_DOCKER_PAUSED_KEY);
      }
    }
  } catch { /* ignore parse errors */ }
  return null;
}

// Helper: save Docker pause state to localStorage
function saveDockerPause(startedAt: number) {
  try {
    localStorage.setItem(LS_DOCKER_PAUSED_KEY, JSON.stringify({ paused: true, startedAt }));
  } catch { /* ignore storage errors */ }
}

// Helper: clear Docker pause state from localStorage
function clearDockerPause() {
  try {
    localStorage.removeItem(LS_DOCKER_PAUSED_KEY);
  } catch { /* ignore storage errors */ }
}

// Minimum seconds between restart attempts for the same service
const RESTART_COOLDOWN_MS = 30_000;
// Time window in which max 3 attempts are allowed
const RESTART_WINDOW_MS = 5 * 60 * 1000;

export function ServiceMonitor() {
  const [alerts, setAlerts] = useState<ServiceAlert[]>([]);
  const [restartingService, setRestartingService] = useState<string | null>(null);
  const previousStatusRef = useRef<Map<string, boolean>>(new Map());
  const [isMinimized, setIsMinimized] = useState(false);

  // Track restart attempts per PROJECT (keyed by projectId).
  // Project-level restart uses the project's own start.sh/launch.sh which
  // handles service ordering, dependencies, and environment correctly.
  const projectRestartTrackerRef = useRef<Map<string, RestartTracker>>(new Map());

  // Services the user explicitly stopped (don't auto-restart these).
  // Persisted in localStorage so manual stops survive HMR/page refresh.
  const manuallyStoppedRef = useRef<Set<string>>(loadManualStops());

  // Count consecutive "down" readings per service — only act after 2+ to debounce
  // false negatives from lsof timeouts under load
  const downCountRef = useRef<Map<string, number>>(new Map());

  // Timestamp of when a project was manually stopped — used for grace period
  const manualStopTimestampRef = useRef<Map<string, number>>(new Map());

  // Track which poll cycle we're on since mount.
  // Cycle 0 = warm-up (baseline only). Cycle 1+ = active watchdog.
  const pollCycleRef = useRef(0);

  // Docker pause state — master pause flag during VM operations
  const dockerPausedRef = useRef(false);
  const dockerHealthPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dockerPauseStartedRef = useRef(0);
  const [dockerPaused, setDockerPaused] = useState(false);

  // Restore Docker pause state from localStorage on init
  const dockerPauseRestored = useRef(false);
  if (!dockerPauseRestored.current) {
    dockerPauseRestored.current = true;
    const savedPause = loadDockerPause();
    if (savedPause) {
      dockerPausedRef.current = true;
      dockerPauseStartedRef.current = savedPause.startedAt;
      // Note: setDockerPaused(true) will be set in useEffect (can't call useState setter during render)
    }
  }

  // Use a ref for alerts so checkServices doesn't depend on alerts state
  const alertsRef = useRef<ServiceAlert[]>([]);
  alertsRef.current = alerts;

  // Log a watchdog event to the backend
  const logWatchdogEvent = useCallback(async (
    projectId: string,
    port: number,
    serviceName: string,
    action: string,
    attempt: number,
    error?: string
  ) => {
    try {
      await fetch('/api/watchdog/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId, port, serviceName, action, attempt, error }),
      });
    } catch (e) {
      console.error('Failed to log watchdog event:', e);
    }
  }, []);

  // Auto-restart a project using its own start.sh/launch.sh script.
  // This handles service dependencies, ordering, and environment correctly.
  // One attempt covers ALL down services in the project.
  const autoRestartProject = useCallback(async (
    project: { id: string; name: string },
    downServices: Array<{ name: string; port: number }>
  ) => {
    const tracker = projectRestartTrackerRef.current.get(project.id) || {
      attempts: 0,
      firstAttemptAt: Date.now(),
      lastAttemptAt: 0,
      inProgress: false,
      gaveUp: false,
    };

    // Cooldown check — don't restart if we just attempted recently
    if (tracker.lastAttemptAt > 0 && Date.now() - tracker.lastAttemptAt < RESTART_COOLDOWN_MS) {
      return;
    }

    tracker.attempts++;
    tracker.lastAttemptAt = Date.now();
    tracker.inProgress = true;
    if (tracker.attempts === 1) tracker.firstAttemptAt = Date.now();
    projectRestartTrackerRef.current.set(project.id, tracker);

    // Log attempt for each down service
    for (const svc of downServices) {
      await logWatchdogEvent(project.id, svc.port, svc.name, 'RESTART_ATTEMPTED', tracker.attempts);
    }

    // Create/update alerts for all down services with "auto-restarting" status
    setAlerts(prev => {
      const updated = [...prev];
      for (const svc of downServices) {
        const existing = updated.find(a => a.projectId === project.id && a.port === svc.port && !a.dismissed);
        if (existing) {
          Object.assign(existing, { watchdogStatus: 'restarting' as const, watchdogAttempt: tracker.attempts });
        } else {
          updated.push({
            id: `${project.id}-${svc.port}-${Date.now()}`,
            projectId: project.id,
            projectName: project.name,
            serviceName: svc.name,
            port: svc.port,
            status: 'parked' as const,
            timestamp: new Date(),
            dismissed: false,
            watchdogStatus: 'restarting' as const,
            watchdogAttempt: tracker.attempts,
          });
        }
      }
      return updated;
    });

    try {
      // Call project-level launch — uses start.sh/launch.sh with proper
      // environment, dependency ordering, and service startup sequence
      console.log(`[Watchdog] Launching project ${project.name} (attempt ${tracker.attempts}/3)`);
      const res = await fetch(`/api/projects/${project.id}/launch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();

      if (data.success) {
        console.log(`[Watchdog] Project ${project.name} launch succeeded`);
        for (const svc of downServices) {
          await logWatchdogEvent(project.id, svc.port, svc.name, 'RESTART_SUCCESS', tracker.attempts);
        }
        setAlerts(prev => prev.map(a =>
          a.projectId === project.id && !a.dismissed
            ? { ...a, watchdogStatus: 'success' as const }
            : a
        ));
        setTimeout(() => {
          setAlerts(prev => prev.map(a =>
            a.projectId === project.id && a.watchdogStatus === 'success'
              ? { ...a, dismissed: true }
              : a
          ));
        }, 5000);
      } else {
        console.log(`[Watchdog] Project ${project.name} launch failed: ${data.error}`);
        for (const svc of downServices) {
          await logWatchdogEvent(project.id, svc.port, svc.name, 'RESTART_FAILED', tracker.attempts, data.error);
        }
        setAlerts(prev => prev.map(a =>
          a.projectId === project.id && !a.dismissed
            ? { ...a, watchdogStatus: 'failed' as const }
            : a
        ));
      }
    } catch (error) {
      console.log(`[Watchdog] Project ${project.name} launch error: ${error}`);
      for (const svc of downServices) {
        await logWatchdogEvent(project.id, svc.port, svc.name, 'RESTART_FAILED', tracker.attempts, String(error));
      }
      setAlerts(prev => prev.map(a =>
        a.projectId === project.id && !a.dismissed
          ? { ...a, watchdogStatus: 'failed' as const }
          : a
      ));
    } finally {
      tracker.inProgress = false;
    }
  }, [logWatchdogEvent]);

  // Fetch all projects and their service statuses
  const checkServices = useCallback(async () => {
    // Skip all checks when Docker is paused (VM operation in progress)
    if (dockerPausedRef.current) {
      return;
    }

    try {
      const res = await fetch('/api/projects/status');
      const data = await res.json();

      if (!data.success) return;

      const cycle = pollCycleRef.current++;
      const isWarmup = cycle === 0;

      const currentAlerts = alertsRef.current;
      const newAlerts: ServiceAlert[] = [];

      // Collect confirmed-down watchdog-eligible services grouped by project.
      // After the per-service loop, these are handled with project-level restart.
      const projectsToRestart = new Map<string, {
        project: { id: string; name: string };
        services: Array<{ name: string; port: number }>;
      }>();

      for (const project of data.data.projects) {
        if (!project.services || project.services.length === 0) continue;

        // Grace period: skip projects that were manually stopped within the last 30s.
        const stopTimestamp = manualStopTimestampRef.current.get(project.id);
        if (stopTimestamp && Date.now() - stopTimestamp < RESTART_COOLDOWN_MS) {
          for (const service of project.services) {
            const serviceKey = `${project.id}-${service.port}`;
            previousStatusRef.current.set(serviceKey, service.status === 'running');
          }
          continue;
        }

        for (const service of project.services) {
          const serviceKey = `${project.id}-${service.port}`;
          const wasRunning = previousStatusRef.current.get(serviceKey);
          const isRunning = service.status === 'running';

          // Warm-up cycle: only record baseline, don't take any action.
          // This prevents mass restarts on HMR/page refresh.
          if (isWarmup) {
            previousStatusRef.current.set(serviceKey, isRunning);
            continue;
          }

          // Auto-dismiss alerts when a service comes back online
          if (!wasRunning && isRunning) {
            setAlerts(prev => prev.map(a =>
              a.projectId === project.id && a.port === service.port && !a.dismissed
                ? { ...a, dismissed: true }
                : a
            ));
            downCountRef.current.delete(serviceKey);
            // Clear project restart tracker — gives fresh attempts if other services still down
            projectRestartTrackerRef.current.delete(project.id);
          }

          // Track consecutive "down" readings for debouncing.
          if (!isRunning) {
            const count = (downCountRef.current.get(serviceKey) || 0) + 1;
            downCountRef.current.set(serviceKey, count);
          } else {
            downCountRef.current.delete(serviceKey);
          }

          const downCount = downCountRef.current.get(serviceKey) || 0;

          // Service is confirmed down (2+ consecutive readings)
          const isConfirmedDown = !isRunning && downCount >= 2;

          if (isConfirmedDown) {
            // Is this a service the watchdog should restart?
            const shouldWatchdogAct = project.watchdogEnabled
              && !manuallyStoppedRef.current.has(serviceKey);

            if (shouldWatchdogAct) {
              // Collect for project-level restart (handled after the service loop)
              if (!projectsToRestart.has(project.id)) {
                projectsToRestart.set(project.id, {
                  project: { id: project.id, name: project.name },
                  services: [],
                });
              }
              projectsToRestart.get(project.id)!.services.push({
                name: service.name,
                port: service.port,
              });
            } else if (wasRunning === true) {
              // Not watchdog-managed but was previously running — show alert for witnessed crash
              const existingAlert = currentAlerts.find(
                a => a.projectId === project.id && a.port === service.port && !a.dismissed
              );
              if (!existingAlert) {
                newAlerts.push({
                  id: `${serviceKey}-${Date.now()}`,
                  projectId: project.id,
                  projectName: project.name,
                  serviceName: service.name,
                  port: service.port,
                  status: 'parked',
                  timestamp: new Date(),
                  dismissed: false,
                });
              }
            }
          }

          // Update previous status.
          // Delay marking as "stopped" until 2+ consecutive down readings
          // (debounce lsof false negatives).
          if (isRunning || downCount >= 2) {
            previousStatusRef.current.set(serviceKey, isRunning);
          }
        }
      }

      // --- Project-level watchdog restart ---
      // For each project with confirmed-down services, attempt a project-level
      // restart using the project's own start.sh/launch.sh (handles ordering
      // and dependencies). One attempt covers all down services.
      for (const [projectId, { project, services }] of projectsToRestart) {
        const tracker = projectRestartTrackerRef.current.get(projectId);

        // Reset tracker if window expired
        if (tracker && tracker.firstAttemptAt < Date.now() - RESTART_WINDOW_MS) {
          projectRestartTrackerRef.current.delete(projectId);
        }

        const currentTracker = projectRestartTrackerRef.current.get(projectId);

        if (!currentTracker || (currentTracker.attempts < 3 && !currentTracker.gaveUp && !currentTracker.inProgress)) {
          autoRestartProject(project, services);
        } else if (currentTracker && currentTracker.attempts >= 3 && !currentTracker.gaveUp) {
          // Max retries exceeded for this project
          currentTracker.gaveUp = true;
          for (const svc of services) {
            logWatchdogEvent(projectId, svc.port, svc.name, 'MAX_RETRIES_EXCEEDED', currentTracker.attempts);
          }
          // Create/update gave-up alerts for each down service
          for (const svc of services) {
            const svcKey = `${projectId}-${svc.port}`;
            const existingAlert = currentAlerts.find(
              a => a.projectId === projectId && a.port === svc.port && !a.dismissed
            );
            if (!existingAlert) {
              newAlerts.push({
                id: `${svcKey}-${Date.now()}`,
                projectId: projectId,
                projectName: project.name,
                serviceName: svc.name,
                port: svc.port,
                status: 'parked',
                timestamp: new Date(),
                dismissed: false,
                watchdogStatus: 'gave-up',
                watchdogAttempt: currentTracker.attempts,
              });
            } else {
              setAlerts(prev => prev.map(a =>
                a.id === existingAlert.id
                  ? { ...a, watchdogStatus: 'gave-up' as const, watchdogAttempt: currentTracker.attempts }
                  : a
              ));
            }
          }
        }
      }

      if (newAlerts.length > 0) {
        setAlerts(prev => [...prev, ...newAlerts]);
      }
    } catch (error) {
      console.error('Error checking services:', error);
    }
  }, [autoRestartProject, logWatchdogEvent]);

  // Check Docker health — polls /api/docker/status to see if Docker is back
  const checkDockerHealth = useCallback(async () => {
    // Enforce minimum pause duration — prevents resuming before VM actually shuts down
    const elapsed = Date.now() - dockerPauseStartedRef.current;
    if (elapsed < DOCKER_PAUSE_MIN_MS) {
      console.log(`[Watchdog] Health check skipped — ${Math.round((DOCKER_PAUSE_MIN_MS - elapsed) / 1000)}s remaining in min pause`);
      return;
    }

    try {
      const res = await fetch('/api/docker/status');
      const data = await res.json();

      if (data.success && data.data.colima?.running && data.data.docker !== null) {
        // Docker is healthy — resume watchdog
        console.log('[Watchdog] Docker healthy — resuming');
        dockerPausedRef.current = false;
        setDockerPaused(false);
        clearDockerPause();

        // Clear health poll
        if (dockerHealthPollRef.current) {
          clearInterval(dockerHealthPollRef.current);
          dockerHealthPollRef.current = null;
        }

        // Reset warm-up cycle — next service poll is baseline only
        pollCycleRef.current = 0;

        // Clear ALL restart trackers, down counts, previous status — fresh start
        projectRestartTrackerRef.current.clear();
        downCountRef.current.clear();
        previousStatusRef.current.clear();

        // Dismiss all current alerts (they were Docker-caused)
        setAlerts(prev => prev.map(a => ({ ...a, dismissed: true })));
        return;
      }
    } catch {
      // Network error — Docker probably still down, keep polling
    }

    // Check safety timeout — force-resume if paused > 5 minutes
    if (dockerPauseStartedRef.current > 0 &&
        Date.now() - dockerPauseStartedRef.current > DOCKER_PAUSE_TIMEOUT_MS) {
      console.log('[Watchdog] Docker pause timeout (5 min) — force-resuming');
      dockerPausedRef.current = false;
      setDockerPaused(false);
      clearDockerPause();

      if (dockerHealthPollRef.current) {
        clearInterval(dockerHealthPollRef.current);
        dockerHealthPollRef.current = null;
      }

      // Reset warm-up so next poll is baseline
      pollCycleRef.current = 0;
      projectRestartTrackerRef.current.clear();
      downCountRef.current.clear();
      previousStatusRef.current.clear();
      setAlerts(prev => prev.map(a => ({ ...a, dismissed: true })));
    }
  }, []);

  // Start the Docker health poll loop
  const startDockerHealthPoll = useCallback(() => {
    // Clear any existing poll
    if (dockerHealthPollRef.current) {
      clearInterval(dockerHealthPollRef.current);
    }
    // Start polling every 5 seconds — no immediate check because
    // DOCKER_PAUSE_MIN_MS ensures we wait before allowing resume
    dockerHealthPollRef.current = setInterval(checkDockerHealth, DOCKER_HEALTH_POLL_MS);
  }, [checkDockerHealth]);

  // Listen for CustomEvents from the projects page
  useEffect(() => {
    const handleManualStop = (e: Event) => {
      const detail = (e as CustomEvent).detail as { projectId: string; ports: number[] };
      if (detail && detail.projectId && detail.ports) {
        // Record the stop timestamp for grace period
        manualStopTimestampRef.current.set(detail.projectId, Date.now());
        for (const port of detail.ports) {
          manuallyStoppedRef.current.add(`${detail.projectId}-${port}`);
        }
        // Persist to localStorage so manual stops survive HMR/page refresh
        saveManualStops(manuallyStoppedRef.current);
      }
    };

    const handleServiceLaunched = (e: Event) => {
      const detail = (e as CustomEvent).detail as { projectId: string };
      if (detail && detail.projectId) {
        // Clear grace period and manual-stop markers for this project
        manualStopTimestampRef.current.delete(detail.projectId);

        const keysToRemove: string[] = [];
        manuallyStoppedRef.current.forEach(key => {
          if (key.startsWith(`${detail.projectId}-`)) {
            keysToRemove.push(key);
          }
        });
        keysToRemove.forEach(key => manuallyStoppedRef.current.delete(key));
        // Persist the cleared state
        saveManualStops(manuallyStoppedRef.current);

        projectRestartTrackerRef.current.delete(detail.projectId);

        setAlerts(prev => prev.map(a =>
          a.projectId === detail.projectId && !a.dismissed
            ? { ...a, dismissed: true }
            : a
        ));
      }
    };

    // Also listen for watchdog toggle changes — when watchdog is disabled,
    // clear manual-stop markers for that project so re-enabling works fresh
    const handleWatchdogToggle = (e: Event) => {
      const detail = (e as CustomEvent).detail as { projectId: string; enabled: boolean };
      if (detail && detail.projectId && detail.enabled) {
        // Watchdog re-enabled — clear manual stops so it can act on down services
        const keysToRemove: string[] = [];
        manuallyStoppedRef.current.forEach(key => {
          if (key.startsWith(`${detail.projectId}-`)) {
            keysToRemove.push(key);
          }
        });
        keysToRemove.forEach(key => manuallyStoppedRef.current.delete(key));
        saveManualStops(manuallyStoppedRef.current);
        // Reset project restart tracker too
        projectRestartTrackerRef.current.delete(detail.projectId);
        // Reset poll cycle so next check acts immediately
        downCountRef.current.forEach((_, key) => {
          if (key.startsWith(`${detail.projectId}-`)) {
            downCountRef.current.delete(key);
          }
        });
      }
    };

    // Docker VM operation — pause watchdog completely
    const handleDockerVmOperation = (e: Event) => {
      const detail = (e as CustomEvent).detail as { action: string };
      console.log(`[Watchdog] Docker VM operation: ${detail?.action} — pausing watchdog`);

      dockerPausedRef.current = true;
      setDockerPaused(true);
      dockerPauseStartedRef.current = Date.now();
      saveDockerPause(Date.now());

      // Clear all restart trackers and down counts — prevent stale gave-up states
      projectRestartTrackerRef.current.clear();
      downCountRef.current.clear();

      // Dismiss all current alerts (Docker operations make them stale)
      setAlerts(prev => prev.map(a => ({ ...a, dismissed: true })));

      // Start Docker health poll
      startDockerHealthPoll();
    };

    // Docker VM ready — trigger immediate health check (belt-and-suspenders)
    const handleDockerVmReady = () => {
      if (dockerPausedRef.current) {
        console.log('[Watchdog] Docker VM ready event — checking health immediately');
        checkDockerHealth();
      }
    };

    window.addEventListener('service-manual-stop', handleManualStop);
    window.addEventListener('service-launched', handleServiceLaunched);
    window.addEventListener('watchdog-toggled', handleWatchdogToggle);
    window.addEventListener('docker-vm-operation', handleDockerVmOperation);
    window.addEventListener('docker-vm-ready', handleDockerVmReady);

    return () => {
      window.removeEventListener('service-manual-stop', handleManualStop);
      window.removeEventListener('service-launched', handleServiceLaunched);
      window.removeEventListener('watchdog-toggled', handleWatchdogToggle);
      window.removeEventListener('docker-vm-operation', handleDockerVmOperation);
      window.removeEventListener('docker-vm-ready', handleDockerVmReady);
    };
  }, [startDockerHealthPoll, checkDockerHealth]);

  // Poll every 15 seconds — use a ref for checkServices to keep the interval stable
  const checkServicesRef = useRef(checkServices);
  checkServicesRef.current = checkServices;

  useEffect(() => {
    // NOTE: setInterval captures checkServicesRef.current (the ref), not the
    // callback itself. checkServicesRef is updated on every render (above), so
    // this always calls the latest checkServices. This is the canonical pattern
    // for "use latest callback in an effect without restarting the interval".
    const initialTimeout = setTimeout(() => checkServicesRef.current(), 2000);
    const interval = setInterval(() => checkServicesRef.current(), 15000);

    return () => {
      clearTimeout(initialTimeout);
      clearInterval(interval);
    };
  }, []);

  // Mount recovery: if component starts in Docker-paused state (from localStorage),
  // sync the React state and auto-start the health poll.
  // Also cleans up the health poll interval on unmount.
  useEffect(() => {
    if (dockerPausedRef.current) {
      setDockerPaused(true);
      startDockerHealthPoll();
    }

    return () => {
      if (dockerHealthPollRef.current) {
        clearInterval(dockerHealthPollRef.current);
        dockerHealthPollRef.current = null;
      }
    };
  }, [startDockerHealthPoll]);

  const handleRestart = async (alert: ServiceAlert) => {
    setRestartingService(alert.id);
    try {
      const projectRes = await fetch(`/api/projects/${alert.projectId}`);
      const projectData = await projectRes.json();

      if (projectData.success) {
        const port = projectData.data.ports.find((p: { port: number }) => p.port === alert.port);
        if (port) {
          const res = await fetch(`/api/projects/${alert.projectId}/services/${port.id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'restart' }),
          });
          const data = await res.json();

          if (data.success) {
            setAlerts(prev =>
              prev.map(a => (a.id === alert.id ? { ...a, dismissed: true } : a))
            );
          }
        }
      }
    } catch (error) {
      console.error('Error restarting service:', error);
    } finally {
      setRestartingService(null);
    }
  };

  const handleDismiss = (alertId: string) => {
    setAlerts(prev => prev.map(a => (a.id === alertId ? { ...a, dismissed: true } : a)));
  };

  const handleDismissAll = () => {
    setAlerts(prev => prev.map(a => ({ ...a, dismissed: true })));
  };

  const activeAlerts = alerts.filter(a => !a.dismissed);

  // Docker pause indicator — show when watchdog is paused for VM operations
  if (dockerPaused) {
    return (
      <div className="fixed bottom-4 right-4 z-50 max-w-sm">
        <div className="backdrop-blur-sm border rounded-lg px-4 py-2 flex items-center gap-2 bg-cyan-900/90 border-cyan-700 text-cyan-200">
          <RefreshCw className="h-4 w-4 animate-spin" />
          <span className="font-medium text-sm">Watchdog paused — waiting for Docker</span>
        </div>
      </div>
    );
  }

  if (activeAlerts.length === 0) {
    return null;
  }

  // Determine header style and text based on watchdog statuses
  const hasRestarting = activeAlerts.some(a => a.watchdogStatus === 'restarting');
  const hasGaveUp = activeAlerts.some(a => a.watchdogStatus === 'gave-up');
  const hasSuccess = activeAlerts.some(a => a.watchdogStatus === 'success');

  let headerText = `${activeAlerts.length} Service${activeAlerts.length > 1 ? 's' : ''} Parked`;
  let headerClasses = 'bg-red-900/90 border-red-700 text-red-200';
  let headerTextColor = 'text-red-200';
  let dismissTextColor = 'text-red-300';
  let dismissHoverColor = 'hover:text-white';
  let iconDismissColor = 'text-red-300 hover:text-white';

  if (hasRestarting) {
    headerText = 'Auto-Restarting Services';
    headerClasses = 'bg-amber-900/90 border-amber-700 text-amber-200';
    headerTextColor = 'text-amber-200';
    dismissTextColor = 'text-amber-300';
    iconDismissColor = 'text-amber-300 hover:text-white';
  } else if (hasSuccess && !hasGaveUp && activeAlerts.every(a => a.watchdogStatus === 'success')) {
    headerText = 'Services Restarted';
    headerClasses = 'bg-green-900/90 border-green-700 text-green-200';
    headerTextColor = 'text-green-200';
    dismissTextColor = 'text-green-300';
    iconDismissColor = 'text-green-300 hover:text-white';
  } else if (hasGaveUp) {
    headerText = 'Services Need Attention';
    headerClasses = 'bg-red-900/90 border-red-700 text-red-200';
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm">
      {/* Header */}
      <div
        className={cn(
          'backdrop-blur-sm border rounded-t-lg px-4 py-2 flex items-center justify-between cursor-pointer',
          headerClasses,
          isMinimized && 'rounded-b-lg'
        )}
        onClick={() => setIsMinimized(!isMinimized)}
      >
        <div className={cn('flex items-center gap-2', headerTextColor)}>
          {hasRestarting ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : hasSuccess && !hasGaveUp ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <AlertTriangle className="h-4 w-4" />
          )}
          <span className="font-medium text-sm">
            {headerText}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {activeAlerts.length > 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDismissAll();
              }}
              className={cn('text-xs', dismissTextColor, dismissHoverColor)}
            >
              Dismiss All
            </button>
          )}
          <X
            className={cn('h-4 w-4 cursor-pointer', iconDismissColor)}
            onClick={(e) => {
              e.stopPropagation();
              handleDismissAll();
            }}
          />
        </div>
      </div>

      {/* Alert List */}
      {!isMinimized && (
        <div className="bg-zinc-900/95 backdrop-blur-sm border border-zinc-700 border-t-0 rounded-b-lg max-h-80 overflow-y-auto">
          {activeAlerts.map((alert) => (
            <div
              key={alert.id}
              className="p-3 border-b border-zinc-800 last:border-b-0"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">
                    {alert.projectName}
                  </p>
                  <p className="text-zinc-400 text-xs truncate">
                    {alert.serviceName} (port {alert.port})
                  </p>

                  {/* Watchdog status messages */}
                  {alert.watchdogStatus === 'restarting' && (
                    <p className="text-amber-400 text-xs mt-1 flex items-center gap-1">
                      <RefreshCw className="h-3 w-3 animate-spin" />
                      Auto-restarting... (attempt {alert.watchdogAttempt}/3)
                    </p>
                  )}
                  {alert.watchdogStatus === 'success' && (
                    <p className="text-green-400 text-xs mt-1 flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" />
                      Auto-restarted successfully
                    </p>
                  )}
                  {alert.watchdogStatus === 'failed' && (
                    <p className="text-red-400 text-xs mt-1">
                      Restart failed (attempt {alert.watchdogAttempt}/3)
                    </p>
                  )}
                  {alert.watchdogStatus === 'gave-up' && (
                    <p className="text-red-300 text-xs mt-1 font-medium">
                      3/3 retries exhausted
                    </p>
                  )}

                  {/* Timestamp for non-watchdog or gave-up alerts */}
                  {(!alert.watchdogStatus || alert.watchdogStatus === 'gave-up' || alert.watchdogStatus === 'failed') && (
                    <p className="text-zinc-500 text-xs mt-1">
                      Parked at {alert.timestamp.toLocaleTimeString()}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {/* Show manual restart button when not auto-restarting and not in success state */}
                  {alert.watchdogStatus !== 'restarting' && alert.watchdogStatus !== 'success' && (
                    <button
                      onClick={() => handleRestart(alert)}
                      disabled={restartingService === alert.id}
                      className={cn(
                        'p-1.5 rounded-md transition-colors',
                        restartingService === alert.id
                          ? 'bg-zinc-700 text-zinc-400'
                          : 'bg-green-600 hover:bg-green-500 text-white'
                      )}
                      title="Restart Service"
                    >
                      {restartingService === alert.id ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Play className="h-3.5 w-3.5" />
                      )}
                    </button>
                  )}
                  <button
                    onClick={() => handleDismiss(alert.id)}
                    className="p-1.5 rounded-md bg-zinc-700 hover:bg-zinc-600 text-zinc-300 transition-colors"
                    title="Dismiss"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
