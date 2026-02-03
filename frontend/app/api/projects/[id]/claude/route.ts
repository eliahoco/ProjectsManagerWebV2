/**
 * Open Claude API Route
 * POST /api/projects/[id]/claude - Open Claude with project context
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { openClaudeWithContext } from '@/lib/shell';

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

    // Build context prompt
    const portsList = project.ports
      .map((p) => `${p.serviceName}: ${p.port}`)
      .join(', ');

    const prompt = `You are resuming work on the ${project.name} project.

Read PROJECT_DESCRIPTOR.md now to understand the project.

Project Ports (USE ONLY THESE): ${portsList}

After reading the files, provide:
1. A brief summary of what this project is
2. Current status and what was last worked on
3. What should be done next`;

    // Open Claude with context
    const result = await openClaudeWithContext(project.path, prompt);

    if (result.exitCode !== 0) {
      return NextResponse.json({
        success: false,
        error: 'Failed to open Claude',
        logs: result.stderr,
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      data: {
        message: `Claude opened for ${project.name}`,
      },
    });

  } catch (error) {
    console.error('Error opening Claude:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 }
    );
  }
}
