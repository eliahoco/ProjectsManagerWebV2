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
import {
  AlertTriangle,
  RefreshCw,
  X,
  Play,
  CheckCircle,
  Database,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';
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

const RAG_STATUS_POLL_MS = 30_000;
// Flip the badge to "offline" only after this many consecutive fetch
// failures — keeps a single dropped poll from flickering red for 30s.
const RAG_FETCH_FAIL_THRESHOLD = 2;

type RagBadgeColor = 'green' | 'amber' | 'red' | 'gray';
type RagMode = 'HTTP' | 'PERSISTENT' | 'UNINITIALIZED';

interface RagCollectionStatus {
  // CB-2217: collection `name` is no longer surfaced — payload contains
  // only `count` so the status endpoint cannot be used to enumerate which
  // projects exist via the `project_<cuid_prefix>` collection naming.
  count: number | null;
}

interface RagStatusPayload {
  mode: RagMode | (string & {});
  // CB-2215 (F-5): renamed from `host`. For mode=HTTP this is the ChromaDB
  // host; for mode=PERSISTENT and mode=UNINITIALIZED this is "". CB-2216:
  // PERSISTENT no longer echoes the abspath — `fallback_active` is the
  // signal instead. The card already rendered "embedded" when endpoint
  // was empty for PERSISTENT, so no UI change is needed.
  endpoint: string;
  port: number;
  // CB-2216: True iff mode=PERSISTENT — the embedded ChromaDB client is in
  // use (silent HTTP fallback). Replaces the prior abspath-in-endpoint
  // disclosure. Defaults to false on legacy/unknown payload shapes so a
  // stale browser tab never falsely reports fallback.
  fallback_active: boolean;
  collections: RagCollectionStatus[];
  total_docs: number;
  healthy: boolean;
}

const DOT_CLASSES: Record<RagBadgeColor, string> = {
  green: 'bg-green-500',
  amber: 'bg-amber-500',
  red: 'bg-red-500',
  gray: 'bg-zinc-500',
};

const RING_CLASSES: Record<RagBadgeColor, string> = {
  green: 'ring-green-500/40',
  amber: 'ring-amber-500/40',
  red: 'ring-red-500/40',
  gray: 'ring-zinc-500/40',
};

// Coerce a raw fetch payload into a safe shape — backend is trusted but
// React must not crash if the response loses a field. Returns null if the
// payload is not an object.
//
// CB-2217: `name` is intentionally NOT extracted from incoming rows even if
// a stale backend still emits it. The redaction is server-side; this is a
// defence-in-depth so a stray legacy field on the wire can never make it
// into React state and from there into a screenshot or bug-report log.
function normalizeRagStatus(raw: unknown): RagStatusPayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const collectionsIn = Array.isArray(r.collections) ? r.collections : [];
  const collections: RagCollectionStatus[] = collectionsIn
    .filter((c): c is Record<string, unknown> => !!c && typeof c === 'object')
    .map(c => ({
      count: typeof c.count === 'number' ? c.count : null,
    }));
  return {
    mode: typeof r.mode === 'string' ? r.mode : 'UNINITIALIZED',
    endpoint: typeof r.endpoint === 'string' ? r.endpoint : '',
    port: typeof r.port === 'number' ? r.port : 0,
    // CB-2216: trust an explicit boolean if present; otherwise infer from
    // mode (a stale backend that doesn't yet emit the field still surfaces
    // fallback correctly). Never coerce truthy/falsy non-boolean shapes.
    fallback_active:
      typeof r.fallback_active === 'boolean'
        ? r.fallback_active
        : r.mode === 'PERSISTENT',
    collections,
    total_docs: typeof r.total_docs === 'number' ? r.total_docs : 0,
    healthy: r.healthy === true,
  };
}

/**
 * CB-2046: RAG status card.
 *
 * Always-visible compact card surfacing the active ChromaDB backend so
 * silent fallback to the embedded SQLite path (the bug that motivated
 * CB-2039) is impossible to miss going forward.
 *
 * Color logic:
 *   - mode=HTTP & healthy        → green  (container path, expected)
 *   - mode=PERSISTENT            → amber  (silent fallback — needs attention)
 *   - mode=HTTP & !healthy       → amber  (container reachable but degraded)
 *   - mode=UNINITIALIZED / fetch → red    (RAG offline)
 *
 * Polls /api/system/rag/status every 30s. Collapsed by default; click the
 * header to expand and see top-3 collections by count.
 *
 * Hidden on viewports < sm (640px) to avoid overlapping the bottom-right
 * alert popup, which has its own footprint there.
 */
function RagStatusCard() {
  const [status, setStatus] = useState<RagStatusPayload | null>(null);
  const [offline, setOffline] = useState<boolean>(false);
  const [expanded, setExpanded] = useState<boolean>(false);
  const failCountRef = useRef<number>(0);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/system/rag/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = normalizeRagStatus(await res.json());
      if (data === null) throw new Error('malformed response');
      setStatus(data);
      failCountRef.current = 0;
      setOffline(false);
    } catch (err) {
      console.error(
        '[RagStatusCard] fetch failed:',
        err instanceof Error ? err.message : String(err),
      );
      failCountRef.current += 1;
      if (failCountRef.current >= RAG_FETCH_FAIL_THRESHOLD) setOffline(true);
    }
  }, []);

  const fetchStatusRef = useRef(fetchStatus);
  fetchStatusRef.current = fetchStatus;

  // CB-2215 (F-6): Page Visibility API gating.
  // Without this, every open tab keeps polling /api/system/rag/status at
  // 30 s cadence forever, multiplying load on the FastAPI status endpoint
  // and the underlying chromadb heartbeat / list_collections fan-out (which
  // is itself the subject of CB-2218). Skip the fetch when the tab is
  // hidden, and fire one immediate refresh on visibility return so the card
  // is current the moment the user looks at it again.
  useEffect(() => {
    const tick = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      fetchStatusRef.current();
    };
    const initial = setTimeout(tick, 1000);
    const interval = setInterval(tick, RAG_STATUS_POLL_MS);
    const onVisibility = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        fetchStatusRef.current();
      }
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibility);
    }
    return () => {
      clearTimeout(initial);
      clearInterval(interval);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibility);
      }
    };
  }, []);

  let badgeColor: RagBadgeColor = 'gray';
  let modeLabel = 'RAG …';
  let unhealthyHint: string | null = null;

  if (offline) {
    badgeColor = 'red';
    modeLabel = 'RAG offline';
    unhealthyHint = 'status endpoint unreachable';
  } else if (status) {
    if (status.mode === 'HTTP' && status.healthy) {
      badgeColor = 'green';
      modeLabel = 'RAG HTTP';
    } else if (status.mode === 'HTTP' && !status.healthy) {
      badgeColor = 'amber';
      modeLabel = 'RAG HTTP';
      unhealthyHint = 'degraded — heartbeat or list_collections failed';
    } else if (status.mode === 'PERSISTENT') {
      badgeColor = 'amber';
      modeLabel = 'RAG fallback';
      // CB-2215 (F-7): softened wording — PERSISTENT mode is legitimate
      // for dev / CI runs without the chromadb container. The amber badge
      // and "fallback" label still flag it for attention, but the hint
      // no longer prejudges it as undesired.
      unhealthyHint = 'running on local PersistentClient (chromadb container not in use)';
    } else {
      badgeColor = 'red';
      modeLabel = 'RAG offline';
      unhealthyHint = 'client uninitialized';
    }
  }

  const totalDocs = status?.total_docs ?? 0;

  // CB-2217: collection rows are anonymous on the wire (no `name` field).
  // Sort by count desc; ties keep their pre-existing wire order
  // (Array.prototype.sort is stable per ECMA-262), which is deterministic
  // for a single backend response so the rank labels below are stable
  // across renders of the same payload.
  const topCollections: RagCollectionStatus[] = status
    ? [...status.collections]
        .sort((a, b) => (b.count ?? -1) - (a.count ?? -1))
        .slice(0, 3)
    : [];

  const isPersistent = status?.mode === 'PERSISTENT';
  const endpointLabel = isPersistent ? 'Path' : 'Endpoint';
  const endpointDisplay = status
    ? status.mode === 'HTTP'
      ? `${status.endpoint}:${status.port}`
      : isPersistent
      ? status.endpoint || 'embedded'
      : '—'
    : '—';

  return (
    <div className="hidden sm:block fixed bottom-4 left-4 z-40 max-w-xs">
      <div className="bg-zinc-900/95 backdrop-blur-sm border border-zinc-700 rounded-lg shadow-lg overflow-hidden">
        <button
          type="button"
          onClick={() => setExpanded(prev => !prev)}
          className="w-full flex items-center gap-2 px-3 py-2 hover:bg-zinc-800/80 transition-colors text-left"
          title={unhealthyHint || `${modeLabel} • ${totalDocs} docs`}
          aria-expanded={expanded}
        >
          <Database className="h-4 w-4 text-zinc-400 shrink-0" />
          <span
            className={cn(
              'h-2 w-2 rounded-full ring-2 shrink-0',
              DOT_CLASSES[badgeColor],
              RING_CLASSES[badgeColor],
            )}
            aria-hidden="true"
          />
          <span className="text-zinc-100 text-xs font-medium truncate">
            {modeLabel}
          </span>
          <span className="text-zinc-400 text-xs ml-auto shrink-0">
            {totalDocs.toLocaleString()} docs
          </span>
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
          )}
        </button>

        {expanded && (
          <div className="border-t border-zinc-800 px-3 py-2 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">{endpointLabel}</span>
              <span className="text-zinc-300 font-mono truncate ml-2">
                {endpointDisplay}
              </span>
            </div>

            {unhealthyHint && (
              <div className="text-amber-400 text-xs leading-snug">
                {unhealthyHint}
              </div>
            )}

            <div className="text-xs">
              <div className="text-zinc-500 mb-1">Top collections</div>
              {topCollections.length === 0 ? (
                <div className="text-zinc-600 italic">none</div>
              ) : (
                <ul className="space-y-1">
                  {/*
                    CB-2217: collections are anonymous on the wire — render
                    them as ranked rows ("Collection #1" … #3) instead of
                    echoing the `project_<cuid_prefix>` name that used to
                    leak via this surface. Rank-as-identity by design: the
                    `idx` React key means a count overtaking another count
                    on the next poll will reuse the same <li> fiber and
                    appear to "swap into" the same labeled row. That is
                    intended ("Collection #1 = whatever has the most docs
                    right now") — there is no stable per-project handle to
                    key on, and re-introducing one would re-leak the bug.
                  */}
                  {topCollections.map((col, idx) => (
                    <li
                      key={idx}
                      className="flex items-center justify-between gap-2"
                    >
                      <span className="text-zinc-300 font-mono truncate">
                        {`Collection #${idx + 1}`}
                      </span>
                      <span className="text-zinc-400 shrink-0">
                        {col.count === null ? '—' : col.count.toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

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

  // CB-2215 (F-8): hoist <RagStatusCard /> to a single top-level render so
  // its fiber position is independent of the alert branch chosen below.
  // Previously it was inlined in three separate return branches; React's
  // reconciliation kept its state today only because the branches happened
  // to render it at fiber index 0. Any future reorder (e.g., wrapping a
  // branch in <AnimatePresence> or a layout container) would shift the
  // fiber position and remount the card mid-poll — losing fetch state and
  // resetting the failCount streak. Pulling it up here makes that safe.

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

  // Build the watchdog/alerts overlay (the bottom-right panel) as a single
  // ReactNode that the unified return below renders alongside the always-on
  // RagStatusCard. Branches:
  //   * dockerPaused → cyan "watchdog paused" indicator
  //   * dockerPaused === false && activeAlerts.length > 0 → alert list
  //   * otherwise → null (card-only)
  let alertOverlay: React.ReactNode = null;

  if (dockerPaused) {
    alertOverlay = (
      <div className="fixed bottom-4 right-4 z-50 max-w-sm">
        <div className="backdrop-blur-sm border rounded-lg px-4 py-2 flex items-center gap-2 bg-cyan-900/90 border-cyan-700 text-cyan-200">
          <RefreshCw className="h-4 w-4 animate-spin" />
          <span className="font-medium text-sm">Watchdog paused — waiting for Docker</span>
        </div>
      </div>
    );
  } else if (activeAlerts.length > 0) {
    alertOverlay = (
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

  // CB-2215 (F-8): single return — RagStatusCard is at a stable fiber position
  // (index 0 of the fragment) regardless of which alertOverlay branch ran,
  // so its state survives every transition (no alerts → alerts → docker-paused
  // → no alerts) without remounting.
  return (
    <>
      <RagStatusCard />
      {alertOverlay}
    </>
  );
}
