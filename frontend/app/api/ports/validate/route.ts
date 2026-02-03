/**
 * Port Validation API Route
 * POST /api/ports/validate - Check for port conflicts
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';

interface ValidateRequest {
  port: number;
  excludeProjectId?: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: ValidateRequest = await request.json();
    const { port, excludeProjectId } = body;

    // Find any existing port allocation
    const existingPort = await prisma.port.findFirst({
      where: {
        port,
        ...(excludeProjectId ? { projectId: { not: excludeProjectId } } : {}),
      },
      include: {
        project: {
          select: { id: true, name: true },
        },
      },
    });

    if (existingPort) {
      return NextResponse.json({
        success: true,
        data: {
          available: false,
          conflict: {
            port: existingPort.port,
            projectId: existingPort.project.id,
            projectName: existingPort.project.name,
            serviceName: existingPort.serviceName,
          },
        },
      });
    }

    return NextResponse.json({
      success: true,
      data: {
        available: true,
        conflict: null,
      },
    });
  } catch (error) {
    console.error('Error validating port:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to validate port' },
      { status: 500 }
    );
  }
}

// GET - Get all port conflicts across projects
export async function GET() {
  try {
    // Find duplicate ports
    const ports = await prisma.port.findMany({
      include: {
        project: {
          select: { id: true, name: true, status: true },
        },
      },
      orderBy: { port: 'asc' },
    });

    // Group by port number to find conflicts
    const portMap = new Map<number, typeof ports>();
    for (const p of ports) {
      const existing = portMap.get(p.port) || [];
      existing.push(p);
      portMap.set(p.port, existing);
    }

    // Find conflicts (ports used by multiple projects)
    const conflicts: Array<{
      port: number;
      projects: Array<{
        projectId: string;
        projectName: string;
        serviceName: string;
        status: string;
      }>;
    }> = [];

    for (const [port, allocations] of portMap) {
      if (allocations.length > 1) {
        conflicts.push({
          port,
          projects: allocations.map((a) => ({
            projectId: a.project.id,
            projectName: a.project.name,
            serviceName: a.serviceName,
            status: a.project.status,
          })),
        });
      }
    }

    return NextResponse.json({
      success: true,
      data: {
        conflicts,
        totalConflicts: conflicts.length,
      },
    });
  } catch (error) {
    console.error('Error getting port conflicts:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to get port conflicts' },
      { status: 500 }
    );
  }
}
