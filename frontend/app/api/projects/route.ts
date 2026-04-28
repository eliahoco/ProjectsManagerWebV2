/**
 * Projects API Route
 * GET /api/projects - List all projects with status (including git data)
 * For lightweight polling use /api/projects/status instead.
 */

import { NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { getProjectStatus, getGitStatus } from '@/lib/shell';
import type { ProjectWithStatus } from '@/types';

/** Race a promise against a timeout; return fallback on timeout. */
function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((resolve) => setTimeout(() => resolve(fallback), ms)),
  ]);
}

export async function GET() {
  try {
    // Get all projects from database
    const projects = await prisma.project.findMany({
      include: {
        ports: true,
      },
      orderBy: {
        name: 'asc',
      },
    });

    // Enrich with runtime status — cap each project at 8 s to prevent thundering herd
    const projectsWithStatus: ProjectWithStatus[] = await Promise.all(
      projects.map(async (project) => {
        const knownPorts = project.ports.map((p) => ({
          port: p.port,
          serviceName: p.serviceName,
          serviceType: p.serviceType,
          url: p.url,
          notes: p.notes,
        }));

        const fallbackStatus = {
          running: false,
          services: knownPorts.map((p) => ({
            name: p.serviceName || `Port ${p.port}`,
            status: 'stopped' as const,
            port: p.port,
          })),
        };

        const fallbackGit = {
          hasGit: false,
          hasRemote: false,
          branch: 'unknown',
          isDirty: false,
          uncommittedFiles: 0,
        };

        const work = (async () => {
          const status = await getProjectStatus(project.path, knownPorts);
          const gitStatus = await getGitStatus(project.path);
          return { status, gitStatus };
        })();

        const { status, gitStatus } = await withTimeout(
          work,
          8000,
          { status: fallbackStatus, gitStatus: fallbackGit },
        );

        return {
          ...project,
          isRunning: status.running,
          services: status.services,
          gitStatus,
        };
      })
    );

    const activeCount = projectsWithStatus.filter((p) => p.isRunning).length;

    return NextResponse.json({
      success: true,
      data: {
        projects: projectsWithStatus,
        total: projects.length,
        activeCount,
      },
    });
  } catch (error) {
    console.error('Error fetching projects:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch projects' },
      { status: 500 }
    );
  }
}
