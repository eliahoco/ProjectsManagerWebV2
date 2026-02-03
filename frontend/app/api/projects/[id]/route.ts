/**
 * Single Project API Route
 * GET /api/projects/[id] - Get project details with status
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { getProjectStatus, getGitStatus } from '@/lib/shell';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

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

    // Get runtime status - pass known ports for reliable detection
    const knownPorts = project.ports.map((p) => ({
      port: p.port,
      serviceName: p.serviceName,
      serviceType: p.serviceType,
    }));
    const status = await getProjectStatus(project.path, knownPorts);
    const gitStatus = await getGitStatus(project.path);

    const projectWithStatus = {
      ...project,
      isRunning: status.running,
      services: status.services,
      gitStatus,
    };

    return NextResponse.json({
      success: true,
      data: projectWithStatus,
    });
  } catch (error) {
    console.error('Error fetching project:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch project' },
      { status: 500 }
    );
  }
}
