/**
 * Import Project API Route
 * POST /api/projects/import - Import an existing project from filesystem
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import fs from 'fs/promises';
import path from 'path';

interface ImportRequest {
  path: string;
  name?: string;
}

// Detect project type from files
async function detectProjectType(projectPath: string): Promise<string | null> {
  try {
    // Check for package.json (Node.js)
    try {
      const content = await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8');
      const pkg = JSON.parse(content);
      if (pkg.dependencies?.next) return 'nextjs';
      if (pkg.dependencies?.express) return 'express';
      if (pkg.dependencies?.fastify) return 'fastify';
      return 'nodejs';
    } catch {}

    // Check for requirements.txt (Python)
    try {
      const content = await fs.readFile(path.join(projectPath, 'requirements.txt'), 'utf-8');
      if (content.includes('fastapi')) return 'fastapi';
      if (content.includes('django')) return 'django';
      if (content.includes('flask')) return 'flask';
      return 'python';
    } catch {}

    // Check for go.mod (Go)
    try {
      await fs.access(path.join(projectPath, 'go.mod'));
      return 'go';
    } catch {}

    // Check for Cargo.toml (Rust)
    try {
      await fs.access(path.join(projectPath, 'Cargo.toml'));
      return 'rust';
    } catch {}

    return null;
  } catch {
    return null;
  }
}

// Read existing port configuration from .ports.env or docker-compose.yml
async function detectPorts(projectPath: string): Promise<Array<{ port: number; serviceName: string; serviceType: string }>> {
  const ports: Array<{ port: number; serviceName: string; serviceType: string }> = [];

  // Check .ports.env
  try {
    const portsEnv = await fs.readFile(path.join(projectPath, '.ports.env'), 'utf-8');
    const lines = portsEnv.split('\n');
    for (const line of lines) {
      const match = line.match(/^(\w+)_PORT=(\d+)/);
      if (match) {
        const name = match[1].toLowerCase();
        const port = parseInt(match[2]);
        let serviceType = 'OTHER';
        if (name.includes('frontend') || name.includes('ui') || name.includes('web')) {
          serviceType = 'FRONTEND';
        } else if (name.includes('backend') || name.includes('api')) {
          serviceType = 'BACKEND';
        } else if (name.includes('db') || name.includes('postgres') || name.includes('mysql')) {
          serviceType = 'DATABASE';
        } else if (name.includes('redis') || name.includes('cache')) {
          serviceType = 'CACHE';
        }
        ports.push({ port, serviceName: match[1], serviceType });
      }
    }
  } catch {}

  // Check docker-compose.yml
  try {
    const compose = await fs.readFile(path.join(projectPath, 'docker-compose.yml'), 'utf-8');
    const portMatches = compose.matchAll(/- "?(\d+):(\d+)"?/g);
    for (const match of portMatches) {
      const externalPort = parseInt(match[1]);
      // Only add if not already detected
      if (!ports.find(p => p.port === externalPort)) {
        ports.push({ port: externalPort, serviceName: 'Docker Service', serviceType: 'OTHER' });
      }
    }
  } catch {}

  return ports;
}

// Extract description from PROJECT_DESCRIPTOR.md
async function getProjectDescription(projectPath: string): Promise<string | null> {
  try {
    const descriptor = await fs.readFile(path.join(projectPath, 'PROJECT_DESCRIPTOR.md'), 'utf-8');
    const match = descriptor.match(/##\s*What\s*is\s*this\s*project\??\s*\n([\s\S]*?)(?=##|$)/i);
    if (match) {
      return match[1].trim().slice(0, 500);
    }
  } catch {}
  return null;
}

export async function POST(request: NextRequest) {
  try {
    const body: ImportRequest = await request.json();
    const { path: projectPath, name } = body;

    // Validate path exists
    try {
      const stats = await fs.stat(projectPath);
      if (!stats.isDirectory()) {
        return NextResponse.json(
          { success: false, error: 'Path is not a directory' },
          { status: 400 }
        );
      }
    } catch {
      return NextResponse.json(
        { success: false, error: 'Path does not exist' },
        { status: 400 }
      );
    }

    // Derive name from path if not provided
    const projectName = name || path.basename(projectPath);

    // Check if project already exists
    const existing = await prisma.project.findFirst({
      where: {
        OR: [
          { name: projectName },
          { path: projectPath },
        ],
      },
    });

    if (existing) {
      return NextResponse.json(
        { success: false, error: 'Project already exists with this name or path' },
        { status: 400 }
      );
    }

    // Detect project type
    const projectType = await detectProjectType(projectPath);

    // Get description
    const description = await getProjectDescription(projectPath);

    // Detect ports
    const detectedPorts = await detectPorts(projectPath);

    // Create project in database
    const project = await prisma.project.create({
      data: {
        name: projectName,
        path: projectPath,
        type: projectType,
        description,
        status: 'ACTIVE',
      },
    });

    // Create port entries
    for (const portInfo of detectedPorts) {
      const url = portInfo.serviceType === 'FRONTEND' || portInfo.serviceType === 'BACKEND'
        ? `http://localhost:${portInfo.port}`
        : `localhost:${portInfo.port}`;

      await prisma.port.create({
        data: {
          projectId: project.id,
          port: portInfo.port,
          serviceName: portInfo.serviceName,
          serviceType: portInfo.serviceType,
          url,
        },
      });
    }

    // Fetch complete project with ports
    const importedProject = await prisma.project.findUnique({
      where: { id: project.id },
      include: { ports: true },
    });

    return NextResponse.json({
      success: true,
      data: importedProject,
    });
  } catch (error) {
    console.error('Error importing project:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to import project' },
      { status: 500 }
    );
  }
}
