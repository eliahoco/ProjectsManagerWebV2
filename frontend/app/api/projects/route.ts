/**
 * Projects API Route
 * GET /api/projects - List all projects with status
 */

import { NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { getProjectStatus, getGitStatus } from '@/lib/shell';
import type { ProjectWithStatus } from '@/types';

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

    // Enrich with runtime status
    const projectsWithStatus: ProjectWithStatus[] = await Promise.all(
      projects.map(async (project) => {
        // Get runtime status - pass known ports for reliable detection
        const knownPorts = project.ports.map((p) => ({
          port: p.port,
          serviceName: p.serviceName,
          serviceType: p.serviceType,
        }));
        const status = await getProjectStatus(project.path, knownPorts);
        const gitStatus = await getGitStatus(project.path);

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
