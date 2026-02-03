/**
 * Stop Project API Route
 * POST /api/projects/[id]/stop - Stop a project
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { stopProject } from '@/lib/shell';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    // Get project from database
    const project = await prisma.project.findUnique({
      where: { id },
    });

    if (!project) {
      return NextResponse.json(
        { success: false, error: 'Project not found' },
        { status: 404 }
      );
    }

    // Stop the project
    const result = await stopProject(project.path);

    // Update the latest session
    const latestSession = await prisma.session.findFirst({
      where: {
        projectId: project.id,
        endedAt: null,
      },
      orderBy: {
        startedAt: 'desc',
      },
    });

    if (latestSession) {
      await prisma.session.update({
        where: { id: latestSession.id },
        data: { endedAt: new Date() },
      });
    }

    if (result.exitCode !== 0) {
      return NextResponse.json({
        success: false,
        error: 'Failed to stop project cleanly',
        logs: result.stderr || result.stdout,
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      data: {
        message: `Project ${project.name} stopped successfully`,
        logs: result.stdout,
      },
    });

  } catch (error) {
    console.error('Error stopping project:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 }
    );
  }
}
