/**
 * Watchdog Events API Route
 * POST /api/watchdog/events - Log a restart event
 * GET  /api/watchdog/events?projectId=xxx&limit=20 - Query restart history
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { projectId, port, serviceName, action, attempt, error } = body;

    if (!projectId || !port || !serviceName || !action || attempt === undefined) {
      return NextResponse.json(
        { success: false, error: 'projectId, port, serviceName, action, and attempt are required' },
        { status: 400 }
      );
    }

    const validActions = ['RESTART_ATTEMPTED', 'RESTART_SUCCESS', 'RESTART_FAILED', 'MAX_RETRIES_EXCEEDED'];
    if (!validActions.includes(action)) {
      return NextResponse.json(
        { success: false, error: `action must be one of: ${validActions.join(', ')}` },
        { status: 400 }
      );
    }

    const event = await prisma.watchdogEvent.create({
      data: {
        projectId,
        port,
        serviceName,
        action,
        attempt,
        error: error || null,
      },
    });

    return NextResponse.json({ success: true, data: event }, { status: 201 });
  } catch (error) {
    console.error('Error logging watchdog event:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to log watchdog event' },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const projectId = searchParams.get('projectId');
    const limit = parseInt(searchParams.get('limit') || '20', 10);

    const where = projectId ? { projectId } : {};

    const events = await prisma.watchdogEvent.findMany({
      where,
      orderBy: { createdAt: 'desc' },
      take: Math.min(limit, 100),
    });

    return NextResponse.json({ success: true, data: events });
  } catch (error) {
    console.error('Error fetching watchdog events:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch watchdog events' },
      { status: 500 }
    );
  }
}
