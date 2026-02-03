/**
 * Create Project API Route
 * POST /api/projects/create - Create a new project
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { execCommand } from '@/lib/shell';
import path from 'path';
import fs from 'fs/promises';

interface CreateProjectRequest {
  name: string;
  description?: string;
  type: string;
  services: Array<{
    name: string;
    type: string;
    port: number;
  }>;
}

// Get next available port for a service type
async function getNextAvailablePort(serviceType: string): Promise<number> {
  const range = await prisma.portRange.findUnique({
    where: { serviceType },
  });

  if (!range) {
    // Default ranges
    const defaults: Record<string, { start: number; end: number }> = {
      FRONTEND: { start: 3000, end: 3999 },
      BACKEND: { start: 8000, end: 8999 },
      DATABASE: { start: 5432, end: 5599 },
      CACHE: { start: 6379, end: 6499 },
      OTHER: { start: 9000, end: 9999 },
    };
    const def = defaults[serviceType] || defaults.OTHER;

    // Find used ports in range
    const usedPorts = await prisma.port.findMany({
      where: {
        port: { gte: def.start, lte: def.end },
      },
      select: { port: true },
    });

    const usedSet = new Set(usedPorts.map((p) => p.port));
    for (let port = def.start; port <= def.end; port++) {
      if (!usedSet.has(port)) return port;
    }
    return def.start;
  }

  // Find used ports in range
  const usedPorts = await prisma.port.findMany({
    where: {
      port: { gte: range.rangeStart, lte: range.rangeEnd },
    },
    select: { port: true },
  });

  const usedSet = new Set(usedPorts.map((p) => p.port));
  for (let port = range.rangeStart; port <= range.rangeEnd; port++) {
    if (!usedSet.has(port)) return port;
  }
  return range.rangeStart;
}

// Generate PROJECT_DESCRIPTOR.md content
function generateProjectDescriptor(name: string, description: string, type: string): string {
  return `# Project Descriptor: ${name}

## What is this project?
${description || 'A new project.'}

## Tech Stack
- Type: ${type}

## Key Files to Know
- \`PROJECT_DESCRIPTOR.md\` - This file
- \`launch.sh\` - Start the project
- \`stop.sh\` - Stop the project

## How to Run
\`\`\`bash
./launch.sh
\`\`\`

## Port Allocation
See the Projects Manager Web dashboard for port details.
`;
}

// Generate launch.sh content
function generateLaunchScript(name: string, type: string): string {
  const scripts: Record<string, string> = {
    nextjs: `#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ${name}..."
npm run dev
`,
    fastapi: `#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ${name}..."
docker-compose up -d
`,
    express: `#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ${name}..."
npm run dev
`,
    django: `#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ${name}..."
docker-compose up -d
`,
    go: `#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ${name}..."
go run .
`,
    custom: `#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ${name}..."
# Add your launch commands here
`,
  };
  return scripts[type] || scripts.custom;
}

// Generate stop.sh content
function generateStopScript(name: string, type: string): string {
  const scripts: Record<string, string> = {
    nextjs: `#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping ${name}..."
pkill -f "next dev" || true
`,
    fastapi: `#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping ${name}..."
docker-compose down
`,
    express: `#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping ${name}..."
pkill -f "node" || true
`,
    django: `#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping ${name}..."
docker-compose down
`,
    go: `#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping ${name}..."
pkill -f "${name}" || true
`,
    custom: `#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping ${name}..."
# Add your stop commands here
`,
  };
  return scripts[type] || scripts.custom;
}

export async function POST(request: NextRequest) {
  try {
    const body: CreateProjectRequest = await request.json();
    const { name, description, type, services } = body;

    // Validate name
    if (!name || !/^[A-Za-z][A-Za-z0-9]*$/.test(name)) {
      return NextResponse.json(
        { success: false, error: 'Invalid project name. Use PascalCase with no spaces.' },
        { status: 400 }
      );
    }

    // Check if project already exists
    const existing = await prisma.project.findUnique({ where: { name } });
    if (existing) {
      return NextResponse.json(
        { success: false, error: 'A project with this name already exists.' },
        { status: 400 }
      );
    }

    // Get projects directory from settings
    const projectsDirSetting = await prisma.setting.findUnique({
      where: { key: 'projectsDir' },
    });
    const projectsDir = projectsDirSetting?.value || process.env.PROJECTS_DIR || './projects';
    const projectPath = path.join(projectsDir, name);

    // Check if directory exists
    try {
      await fs.access(projectPath);
      return NextResponse.json(
        { success: false, error: 'Directory already exists at this path.' },
        { status: 400 }
      );
    } catch {
      // Directory doesn't exist, good to proceed
    }

    // Create project directory
    await fs.mkdir(projectPath, { recursive: true });

    // Generate and write files
    await fs.writeFile(
      path.join(projectPath, 'PROJECT_DESCRIPTOR.md'),
      generateProjectDescriptor(name, description || '', type)
    );

    await fs.writeFile(
      path.join(projectPath, 'launch.sh'),
      generateLaunchScript(name, type)
    );
    await fs.chmod(path.join(projectPath, 'launch.sh'), 0o755);

    await fs.writeFile(
      path.join(projectPath, 'stop.sh'),
      generateStopScript(name, type)
    );
    await fs.chmod(path.join(projectPath, 'stop.sh'), 0o755);

    // Initialize git
    await execCommand('git init', { cwd: projectPath });

    // Create project in database
    const project = await prisma.project.create({
      data: {
        name,
        path: projectPath,
        description,
        type,
        status: 'ACTIVE',
      },
    });

    // Create ports
    for (const service of services) {
      const port = service.port || (await getNextAvailablePort(service.type));
      const url =
        service.type === 'FRONTEND' || service.type === 'BACKEND'
          ? `http://localhost:${port}`
          : `localhost:${port}`;

      await prisma.port.create({
        data: {
          projectId: project.id,
          port,
          serviceName: service.name,
          serviceType: service.type,
          url,
        },
      });
    }

    // Fetch the complete project with ports
    const createdProject = await prisma.project.findUnique({
      where: { id: project.id },
      include: { ports: true },
    });

    return NextResponse.json({
      success: true,
      data: createdProject,
    });
  } catch (error) {
    console.error('Error creating project:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to create project' },
      { status: 500 }
    );
  }
}
