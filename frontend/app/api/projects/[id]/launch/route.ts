/**
 * Launch Project API Route
 * POST /api/projects/[id]/launch - Launch a project
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { launchProject, isDockerRunning } from '@/lib/shell';

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

    // Check if Docker is running (provided by Colima)
    const dockerRunning = await isDockerRunning();
    if (!dockerRunning) {
      return NextResponse.json(
        { success: false, error: 'Docker is not running. Please start Colima first: colima start' },
        { status: 503 }
      );
    }

    // Launch the project (includes pre-launch port validation)
    const result = await launchProject(project.path);

    // Port conflict — exitCode 2 from validateProjectPorts
    if (result.exitCode === 2) {
      return NextResponse.json({
        success: false,
        error: result.stdout, // Human-readable conflict message
        portConflicts: (() => {
          try { return JSON.parse(result.stderr); } catch { return []; }
        })(),
      }, { status: 409 }); // 409 Conflict
    }

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
