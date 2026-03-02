/**
 * Watchdog API Route
 * GET  /api/watchdog - List all projects with watchdog status + recent event counts
 * PATCH /api/watchdog - Toggle watchdogEnabled for a project
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';

export async function GET() {
  try {
    const projects = await prisma.project.findMany({
      select: {
        id: true,
        name: true,
        watchdogEnabled: true,
        _count: {
          select: {
            watchdogEvents: {
              where: {
                createdAt: {
                  gte: new Date(Date.now() - 24 * 60 * 60 * 1000),
                },
              },
            },
          },
        },
      },
      orderBy: { name: 'asc' },
    });

    return NextResponse.json({
      success: true,
      data: projects.map((p) => ({
        id: p.id,
        name: p.name,
        watchdogEnabled: p.watchdogEnabled,
        recentEventCount: p._count.watchdogEvents,
      })),
    });
  } catch (error) {
    console.error('Error fetching watchdog status:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch watchdog status' },
      { status: 500 }
    );
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json();
    const { projectId, enabled } = body;

    if (!projectId || typeof enabled !== 'boolean') {
      return NextResponse.json(
        { success: false, error: 'projectId and enabled (boolean) are required' },
        { status: 400 }
      );
    }

    const project = await prisma.project.update({
      where: { id: projectId },
      data: { watchdogEnabled: enabled },
      select: { id: true, name: true, watchdogEnabled: true },
    });

    return NextResponse.json({
      success: true,
      data: project,
    });
  } catch (error) {
    console.error('Error toggling watchdog:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to toggle watchdog' },
      { status: 500 }
    );
  }
}
