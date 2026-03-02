/**
 * Stop Project API Route
 * POST /api/projects/[id]/stop - Stop a project
 *
 * 1. Runs stop.sh / docker-compose down (handles scripted services)
 * 2. Kills any remaining processes on the project's known ports
 *    (handles detached Node/Python processes started by execDetached)
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { stopProject, execCommand } from '@/lib/shell';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    // Get project with its port records
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

    // Step 1: Run the project's stop script (stop.sh / docker-compose down)
    const result = await stopProject(project.path);

    // Step 2: Kill any remaining processes on the project's known ports.
    // This catches detached processes (Vite, Next.js, FastAPI) that stop.sh
    // doesn't know about because they were started via execDetached().
    const killResults: string[] = [];
    for (const portRecord of project.ports) {
      try {
        const lsofResult = await execCommand(
          `lsof -ti :${portRecord.port}`,
          { timeout: 5000 }
        );
        if (lsofResult.stdout.trim()) {
          const pids = lsofResult.stdout.trim().split('\n').filter(Boolean);
          for (const pid of pids) {
            // Validate PID is purely numeric to prevent command injection
            if (!/^\d+$/.test(pid)) continue;
            await execCommand(`kill -9 ${pid}`, { timeout: 5000 });
            killResults.push(`Killed PID ${pid} on port ${portRecord.port}`);
          }
        }
      } catch {
        // Non-critical — port may already be free
      }
    }

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

    // Even if stop.sh failed, if we successfully killed port processes,
    // consider it a success
    const allKilled = killResults.length > 0;
    if (result.exitCode !== 0 && !allKilled) {
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
        logs: [result.stdout, ...killResults].filter(Boolean).join('\n'),
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
