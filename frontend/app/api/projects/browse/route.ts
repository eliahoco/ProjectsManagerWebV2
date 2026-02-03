/**
 * Browse Projects API Route
 * GET /api/projects/browse - List directories available for import
 */

import { NextResponse } from 'next/server';
import prisma from '@/lib/db';
import fs from 'fs/promises';
import path from 'path';

interface DirectoryInfo {
  name: string;
  path: string;
  hasPackageJson: boolean;
  hasGit: boolean;
  alreadyImported: boolean;
}

export async function GET() {
  try {
    // Get projects directory from settings
    const projectsDirSetting = await prisma.setting.findUnique({
      where: { key: 'projectsDir' },
    });
    const projectsDir = projectsDirSetting?.value || process.env.PROJECTS_DIR || './projects';

    // Get already imported project paths
    const existingProjects = await prisma.project.findMany({
      select: { path: true },
    });
    const importedPaths = new Set(existingProjects.map(p => p.path));

    // Read directory contents
    const entries = await fs.readdir(projectsDir, { withFileTypes: true });

    // Filter to directories and gather info
    const directories: DirectoryInfo[] = [];

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      if (entry.name.startsWith('.')) continue; // Skip hidden directories

      const dirPath = path.join(projectsDir, entry.name);

      // Check for package.json
      let hasPackageJson = false;
      try {
        await fs.access(path.join(dirPath, 'package.json'));
        hasPackageJson = true;
      } catch {}

      // Check for .git
      let hasGit = false;
      try {
        await fs.access(path.join(dirPath, '.git'));
        hasGit = true;
      } catch {}

      directories.push({
        name: entry.name,
        path: dirPath,
        hasPackageJson,
        hasGit,
        alreadyImported: importedPaths.has(dirPath),
      });
    }

    // Sort: not imported first, then by name
    directories.sort((a, b) => {
      if (a.alreadyImported !== b.alreadyImported) {
        return a.alreadyImported ? 1 : -1;
      }
      return a.name.localeCompare(b.name);
    });

    return NextResponse.json({
      success: true,
      data: {
        projectsDir,
        directories,
      },
    });
  } catch (error) {
    console.error('Error browsing directories:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to browse directories' },
      { status: 500 }
    );
  }
}
