/**
 * Project Status API Route
 * PATCH /api/projects/[id]/status - Update project status (suspend/archive)
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';

interface StatusUpdateRequest {
  status: 'ACTIVE' | 'DEPRECATED' | 'ARCHIVED';
  notes?: string;
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body: StatusUpdateRequest = await request.json();
    const { status, notes } = body;

    // Validate status
    if (!['ACTIVE', 'DEPRECATED', 'ARCHIVED'].includes(status)) {
      return NextResponse.json(
        { success: false, error: 'Invalid status' },
        { status: 400 }
      );
    }

    // Get current project
    const project = await prisma.project.findUnique({
      where: { id },
    });

    if (!project) {
      return NextResponse.json(
        { success: false, error: 'Project not found' },
        { status: 404 }
      );
    }

    // Update project status
    const updatedProject = await prisma.project.update({
      where: { id },
      data: {
        status,
        description: notes ? `${project.description || ''}\n\n[${status}] ${notes}`.trim() : project.description,
      },
      include: { ports: true },
    });

    return NextResponse.json({
      success: true,
      data: updatedProject,
    });
  } catch (error) {
    console.error('Error updating project status:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to update project status' },
      { status: 500 }
    );
  }
}
