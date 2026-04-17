/**
 * Park Project API Route
 * POST /api/projects/[id]/park
 *
 * Orchestrates a graceful, ordered shutdown of all project services:
 *  1. Stop active AI execution sessions and pipelines (via backend API)
 *  2. Stop each registered service port in priority order
 *     (FRONTEND → BACKEND → CACHE → QUEUE → DATABASE → MONITORING → OTHER)
 *     - First attempts `docker compose stop --time 10 <service>`
 *     - Falls back to SIGTERM → 3 s grace → SIGKILL via lsof PIDs
 *  3. Close the open Prisma session record
 *  4. Kill any remaining zombie processes on all registered ports
 *  5. Record the park event in the backend (non-critical)
 *
 * Returns a step-by-step log and total duration.
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { execCommand, parkProject } from '@/lib/shell';

// Priority order for service teardown — lower number = stopped first
const SERVICE_STOP_PRIORITY: Record<string, number> = {
  FRONTEND: 1,
  BACKEND: 2,
  CACHE: 3,
  QUEUE: 4,
  DATABASE: 5,
  MONITORING: 6,
  OTHER: 7,
};

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const startTime = Date.now();
  const { id } = await params;

  // -------------------------------------------------------------------------
  // Load project
  // -------------------------------------------------------------------------
  const project = await prisma.project.findUnique({
    where: { id },
    include: { ports: true },
  });

  if (!project) {
    return NextResponse.json(
      { success: false, error: 'Project not found' },
      { status: 404 }
    );
  }

  const steps: Array<{ name: string; status: 'done' | 'skipped' | 'failed'; detail?: string }> = [];

  // -------------------------------------------------------------------------
  // Step 1: Stop AI execution sessions + pipelines (best-effort)
  // -------------------------------------------------------------------------
  let sessData: { stopped_count?: number } = {};
  let pipeData: { cancelled_count?: number } = {};

  try {
    const [sessRes, pipeRes] = await Promise.all([
      fetch('http://localhost:8401/api/execute/sessions/stop-all', { method: 'POST' }),
      fetch('http://localhost:8401/api/execute/pipeline/stop-all', { method: 'POST' }),
    ]);

    if (sessRes.ok) {
      sessData = (await sessRes.json()) as { stopped_count?: number };
    }
    if (pipeRes.ok) {
      pipeData = (await pipeRes.json()) as { cancelled_count?: number };
    }

    steps.push({
      name: 'Stop AI Executions',
      status: 'done',
      detail: `${sessData.stopped_count ?? 0} sessions, ${pipeData.cancelled_count ?? 0} pipelines`,
    });
  } catch {
    steps.push({
      name: 'Stop AI Executions',
      status: 'skipped',
      detail: 'Backend not reachable',
    });
  }

  // -------------------------------------------------------------------------
  // Step 2: Stop services in priority order using parkProject()
  // -------------------------------------------------------------------------
  const sortedPorts = [...project.ports].sort(
    (a, b) =>
      (SERVICE_STOP_PRIORITY[a.serviceType] ?? 99) -
      (SERVICE_STOP_PRIORITY[b.serviceType] ?? 99)
  );

  const parkResult = await parkProject(
    project.path,
    sortedPorts.map((p) => ({
      port: p.port,
      serviceType: p.serviceType,
      serviceName: p.serviceName,
    }))
  );

  steps.push(...parkResult.steps);

  // -------------------------------------------------------------------------
  // Step 3: Close the open Prisma session record
  // -------------------------------------------------------------------------
  try {
    const latestSession = await prisma.session.findFirst({
      where: { projectId: id, endedAt: null },
      orderBy: { startedAt: 'desc' },
    });

    if (latestSession) {
      await prisma.session.update({
        where: { id: latestSession.id },
        data: { endedAt: new Date() },
      });
      steps.push({ name: 'Close Session', status: 'done', detail: `Closed session ${latestSession.id}` });
    } else {
      steps.push({ name: 'Close Session', status: 'skipped', detail: 'No open session' });
    }
  } catch (err) {
    steps.push({ name: 'Close Session', status: 'failed', detail: (err as Error).message });
  }

  // -------------------------------------------------------------------------
  // Step 4: Cleanup zombie processes on all registered ports (belt-and-suspenders)
  // -------------------------------------------------------------------------
  for (const portRecord of project.ports) {
    // Validate port is a safe integer before passing to shell
    if (!Number.isInteger(portRecord.port) || portRecord.port < 1 || portRecord.port > 65535) {
      continue;
    }

    try {
      const lsofResult = await execCommand(`lsof -ti :${portRecord.port}`, { timeout: 5000 });
      if (lsofResult.stdout.trim()) {
        const pids = lsofResult.stdout
          .trim()
          .split('\n')
          .filter((p) => /^\d+$/.test(p)); // Security: only numeric PIDs

        for (const pid of pids) {
          await execCommand(`kill -9 ${pid}`, { timeout: 5000 });
        }
      }
    } catch {
      // Non-critical — port may already be free
    }
  }

  // -------------------------------------------------------------------------
  // Step 5: Record park event in backend (non-critical)
  // -------------------------------------------------------------------------
  try {
    await fetch('http://localhost:8401/api/park/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: id,
        services_snapshot: project.ports.map((p) => ({
          port: p.port,
          name: p.serviceName,
          type: p.serviceType,
        })),
        ai_sessions_stopped: sessData.stopped_count ?? 0,
        pipelines_cancelled: pipeData.cancelled_count ?? 0,
        parking_steps_log: steps.map((s) => ({
          ...s,
          // Sanitize detail: truncate and strip potential secrets
          detail: s.detail ? s.detail.slice(0, 500).replace(/(?:key|token|secret|password|auth)[=:]\S+/gi, '[REDACTED]') : undefined,
        })),
        duration_ms: Date.now() - startTime,
      }),
    });
  } catch {
    // Non-critical — backend may already be stopped at this point
  }

  return NextResponse.json({
    success: true,
    steps,
    duration_ms: Date.now() - startTime,
  });
}
