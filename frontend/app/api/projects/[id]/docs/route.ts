/**
 * Project Documentation API Route
 * GET /api/projects/[id]/docs - List all documentation files
 * GET /api/projects/[id]/docs?file=filename.md - Read a specific file
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { readdir, readFile, stat } from 'fs/promises';
import path from 'path';

// Common documentation files to look for
const DOC_PATTERNS = [
  'PROJECT_DESCRIPTOR.md',
  'PROMPT_HISTORY.md',
  'ROADMAP.md',
  'STATUS.md',
  'README.md',
  'CHANGELOG.md',
  'CONTRIBUTING.md',
  'TODO.md',
  'NOTES.md',
  'ARCHITECTURE.md',
  'API.md',
  'SETUP.md',
];

interface DocFile {
  name: string;
  path: string;
  size: number;
  modified: string;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { searchParams } = new URL(request.url);
    const fileName = searchParams.get('file');

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

    // If a specific file is requested, return its contents
    if (fileName) {
      const filePath = path.join(project.path, fileName);

      // Security: ensure the file is within the project directory
      const resolvedPath = path.resolve(filePath);
      if (!resolvedPath.startsWith(path.resolve(project.path))) {
        return NextResponse.json(
          { success: false, error: 'Invalid file path' },
          { status: 400 }
        );
      }

      try {
        const content = await readFile(filePath, 'utf-8');
        const stats = await stat(filePath);

        return NextResponse.json({
          success: true,
          data: {
            name: fileName,
            path: filePath,
            content,
            size: stats.size,
            modified: stats.mtime.toISOString(),
          },
        });
      } catch {
        return NextResponse.json(
          { success: false, error: 'File not found' },
          { status: 404 }
        );
      }
    }

    // List all markdown files in the project root
    const files: DocFile[] = [];

    try {
      const entries = await readdir(project.path, { withFileTypes: true });

      for (const entry of entries) {
        if (entry.isFile() && entry.name.endsWith('.md')) {
          const filePath = path.join(project.path, entry.name);
          const stats = await stat(filePath);

          files.push({
            name: entry.name,
            path: filePath,
            size: stats.size,
            modified: stats.mtime.toISOString(),
          });
        }
      }

      // Also check for docs/ directory
      const docsDir = path.join(project.path, 'docs');
      try {
        const docsEntries = await readdir(docsDir, { withFileTypes: true });
        for (const entry of docsEntries) {
          if (entry.isFile() && entry.name.endsWith('.md')) {
            const filePath = path.join(docsDir, entry.name);
            const stats = await stat(filePath);

            files.push({
              name: `docs/${entry.name}`,
              path: filePath,
              size: stats.size,
              modified: stats.mtime.toISOString(),
            });
          }
        }
      } catch {
        // docs/ directory doesn't exist, ignore
      }

      // Sort: prioritize known doc files, then alphabetically
      files.sort((a, b) => {
        const aIndex = DOC_PATTERNS.indexOf(a.name);
        const bIndex = DOC_PATTERNS.indexOf(b.name);

        if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
        if (aIndex !== -1) return -1;
        if (bIndex !== -1) return 1;
        return a.name.localeCompare(b.name);
      });

    } catch (error) {
      console.error('Error reading project directory:', error);
    }

    return NextResponse.json({
      success: true,
      data: {
        projectPath: project.path,
        files,
      },
    });
  } catch (error) {
    console.error('Error fetching documentation:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to fetch documentation' },
      { status: 500 }
    );
  }
}
