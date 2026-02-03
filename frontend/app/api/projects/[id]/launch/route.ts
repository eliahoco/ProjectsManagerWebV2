/**
 * Launch Project API Route
 * POST /api/projects/[id]/launch - Launch a project
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { launchProject, isDockerRunning, startDocker, isPortInUse } from '@/lib/shell';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    // Get project from database
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

    // Check if Docker is running
    const dockerRunning = await isDockerRunning();
    if (!dockerRunning) {
      // Try to start Docker
      const started = await startDocker();
      if (!started) {
        return NextResponse.json(
          { success: false, error: 'Docker is not running and could not be started' },
          { status: 503 }
        );
      }
    }

    // Check for port conflicts
    const portConflicts: number[] = [];
    for (const port of project.ports) {
      if (await isPortInUse(port.port)) {
        portConflicts.push(port.port);
      }
    }

    if (portConflicts.length > 0) {
      return NextResponse.json({
        success: false,
        error: `Port conflict detected: ${portConflicts.join(', ')} already in use`,
        conflicts: portConflicts,
      }, { status: 409 });
    }

    // Launch the project
    const result = await launchProject(project.path);

    if (result.exitCode !== 0) {
      return NextResponse.json({
        success: false,
        error: 'Failed to launch project',
        logs: result.stderr || result.stdout,
      }, { status: 500 });
    }

    // Create a new session
    await prisma.session.create({
      data: {
        projectId: project.id,
      },
    });

    return NextResponse.json({
      success: true,
      data: {
        message: `Project ${project.name} launched successfully`,
        logs: result.stdout,
      },
    });

  } catch (error) {
    console.error('Error launching project:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 }
    );
  }
}
