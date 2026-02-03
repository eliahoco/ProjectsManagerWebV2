/**
 * Project Session API Route
 * GET /api/projects/[id]/session - Get session info (Last Done / Next Steps)
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import fs from 'fs/promises';
import path from 'path';

interface SessionInfo {
  lastDone: string[];
  nextSteps: string[];
  lastUpdated: string | null;
}

// Extract Last Done and Next Steps from PROMPT_HISTORY.md
async function extractSessionInfo(projectPath: string): Promise<SessionInfo> {
  const historyPath = path.join(projectPath, 'PROMPT_HISTORY.md');

  try {
    const content = await fs.readFile(historyPath, 'utf-8');
    const stats = await fs.stat(historyPath);

    const lastDone: string[] = [];
    const nextSteps: string[] = [];

    // Look for the most recent session section
    const sections = content.split(/^##\s+Session/gm);
    const latestSession = sections[sections.length - 1] || content;

    // Extract "Last Done" or "What was done" section
    const lastDoneMatch = latestSession.match(
      /(?:###?\s*(?:Last\s*Done|What\s*(?:was|we)\s*(?:done|accomplished|completed)|Done|Completed)[:\s]*\n)([\s\S]*?)(?=###|\n##|$)/i
    );

    if (lastDoneMatch) {
      const items = lastDoneMatch[1]
        .split('\n')
        .map(line => line.replace(/^[-*•]\s*/, '').trim())
        .filter(line => line.length > 0 && !line.startsWith('#'));
      lastDone.push(...items.slice(0, 10)); // Limit to 10 items
    }

    // Extract "Next Steps" or "TODO" section
    const nextStepsMatch = latestSession.match(
      /(?:###?\s*(?:Next\s*Steps?|TODO|To\s*Do|What's\s*Next|Upcoming)[:\s]*\n)([\s\S]*?)(?=###|\n##|$)/i
    );

    if (nextStepsMatch) {
      const items = nextStepsMatch[1]
        .split('\n')
        .map(line => line.replace(/^[-*•]\s*/, '').trim())
        .filter(line => line.length > 0 && !line.startsWith('#'));
      nextSteps.push(...items.slice(0, 10)); // Limit to 10 items
    }

    return {
      lastDone,
      nextSteps,
      lastUpdated: stats.mtime.toISOString(),
    };
  } catch {
    // No PROMPT_HISTORY.md file
    return {
      lastDone: [],
      nextSteps: [],
      lastUpdated: null,
    };
  }
}

export async function GET(
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

    // Extract session info from PROMPT_HISTORY.md
    const sessionInfo = await extractSessionInfo(project.path);

    // Also check for PROJECT_DESCRIPTOR.md for additional context
    const descriptorPath = path.join(project.path, 'PROJECT_DESCRIPTOR.md');
    let projectContext = '';

    try {
      const descriptor = await fs.readFile(descriptorPath, 'utf-8');
      // Extract the "What is this project?" section
      const whatMatch = descriptor.match(
        /##\s*What\s*is\s*this\s*project\??\s*\n([\s\S]*?)(?=##|$)/i
      );
      if (whatMatch) {
        projectContext = whatMatch[1].trim();
      }
    } catch {
      // No PROJECT_DESCRIPTOR.md
    }

    return NextResponse.json({
      success: true,
      data: {
        ...sessionInfo,
        projectContext,
      },
    });
  } catch (error) {
    console.error('Error getting session info:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to get session info' },
      { status: 500 }
    );
  }
}
