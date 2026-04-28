/**
 * Lightweight Projects Status Route
 * GET /api/projects/status - Returns ONLY runtime status fields (no git, no heavy scans).
 * Safe to poll every 15 s from ServiceMonitor.
 */

import { NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { getProjectStatus } from '@/lib/shell';
import type { ServiceStatus } from '@/types';

/** Race a promise against a timeout; return fallback on timeout. */
function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((resolve) => setTimeout(() => resolve(fallback), ms)),
  ]);
}

interface ProjectStatusSummary {
  id: string;
  name: string;
  status: 'running' | 'stopped';
  ports: number[];
  runningPorts: number[];
}

export async function GET() {
  try {
    const projects = await prisma.project.findMany({
      include: { ports: true },
      orderBy: { name: 'asc' },
    });

    const results: ProjectStatusSummary[] = await Promise.all(
      projects.map(async (project) => {
        const knownPorts = project.ports.map((p) => ({
          port: p.port,
          serviceName: p.serviceName,
          serviceType: p.serviceType,
          url: p.url,
          notes: p.notes,
        }));

        const allPorts = knownPorts.map((p) => p.port);

        const fallback = {
          running: false,
          services: knownPorts.map((p) => ({
            name: p.serviceName || `Port ${p.port}`,
            status: 'stopped' as const,
            port: p.port,
          })),
        };

        const statusResult = await withTimeout(
          getProjectStatus(project.path, knownPorts),
          3000,
          fallback,
        );

        const runningPorts = (statusResult.services as ServiceStatus[])
          .filter((s) => s.status === 'running' && s.port !== undefined)
          .map((s) => s.port as number);

        return {
          id: project.id,
          name: project.name,
          status: statusResult.running ? 'running' : 'stopped',
          ports: allPorts,
          runningPorts,
        };
      })
    );

    const activeCount = results.filter((p) => p.status === 'running').length;

    return NextResponse.json({
      success: true,
      data: {
        projects: results,
        total: projects.length,
        activeCount,
      },
    });
  } catch (error) {
    console.error('Error fetching project status:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch project status' },
      { status: 500 }
    );
  }
}
