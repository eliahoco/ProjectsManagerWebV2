/**
 * Individual Service Control API
 * POST /api/projects/[id]/services/[serviceId] - Start/Stop/Restart a service
 */

import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/db';
import { execCommand, execDetached, isPortInUse } from '@/lib/shell';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; serviceId: string }> }
) {
  try {
    const { id, serviceId } = await params;
    const body = await request.json();
    const { action } = body; // 'start' | 'stop' | 'restart'

    if (!['start', 'stop', 'restart'].includes(action)) {
      return NextResponse.json(
        { success: false, error: 'Invalid action. Use start, stop, or restart.' },
        { status: 400 }
      );
    }

    // Get project and port info
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

    const port = project.ports.find(p => p.id === serviceId);
    if (!port) {
      return NextResponse.json(
        { success: false, error: 'Service not found' },
        { status: 404 }
      );
    }

    const isRunning = await isPortInUse(port.port);

    // Handle actions
    if (action === 'stop' || action === 'restart') {
      if (isRunning) {
        // Kill process on this port - get PIDs first, then kill each
        const pidsResult = await execCommand(
          `lsof -ti :${port.port}`,
          { timeout: 5000 }
        );

        if (pidsResult.stdout.trim()) {
          const pids = pidsResult.stdout.trim().split('\n').filter(Boolean);
          for (const pid of pids) {
            await execCommand(`kill -9 ${pid}`, { timeout: 5000 });
          }
        }

        // Wait for process to stop
        await new Promise(resolve => setTimeout(resolve, 1500));

        // Verify it actually stopped
        const stillRunning = await isPortInUse(port.port);
        if (stillRunning && action === 'stop') {
          return NextResponse.json({
            success: false,
            error: 'Failed to stop service - process still running',
            data: { port: port.port, status: 'running' }
          }, { status: 500 });
        }
      }
    }

    if (action === 'start' || action === 'restart') {
      // Check if already running (for start action)
      const stillRunning = await isPortInUse(port.port);
      if (stillRunning && action === 'start') {
        return NextResponse.json({
          success: true,
          message: 'Service is already running',
          data: { port: port.port, status: 'running' },
        });
      }

      // Try to start the service based on service type
      let startCommand = '';
      const serviceType = port.serviceType?.toUpperCase();
      const serviceName = port.serviceName?.toLowerCase() || '';

      // Detect how to start the service - commands should NOT include nohup/& as execDetached handles that
      let useDetached = false;
      let startCwd = project.path;

      if (serviceName.includes('next') || serviceName.includes('frontend')) {
        // Next.js frontend
        const frontendPath = `${project.path}/frontend`;
        startCwd = frontendPath;
        startCommand = `npm run dev -- --port ${port.port}`;
        useDetached = true;
      } else if (serviceName.includes('fastapi') || serviceName.includes('backend')) {
        // FastAPI backend - use full paths for reliability
        const backendPath = `${project.path}/backend`;
        startCwd = backendPath;
        // Export env vars, then run uvicorn with the venv python (cd is handled by execDetached)
        startCommand = `export $(grep -v '^#' .env | xargs) 2>/dev/null; "${backendPath}/venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port ${port.port}`;
        useDetached = true;
      } else if (serviceName.includes('postgres')) {
        // PostgreSQL - typically managed by docker
        startCommand = `docker-compose up -d postgres 2>/dev/null || docker start $(docker ps -a --filter "publish=${port.port}" -q) 2>/dev/null`;
      } else if (serviceName.includes('redis')) {
        // Redis - typically managed by docker
        startCommand = `docker-compose up -d redis 2>/dev/null || docker start $(docker ps -a --filter "publish=${port.port}" -q) 2>/dev/null`;
      } else if (serviceName.includes('chroma')) {
        // ChromaDB
        startCommand = `docker-compose up -d chromadb 2>/dev/null`;
      } else if (serviceName.includes('vite')) {
        // Vite frontend
        const frontendPath = `${project.path}/frontend`;
        startCwd = frontendPath;
        startCommand = `npm run dev`;
        useDetached = true;
      } else {
        // Generic - try docker-compose or launch.sh
        startCommand = `docker-compose up -d 2>/dev/null || ./launch.sh 2>/dev/null || echo "No start method found"`;
      }

      if (startCommand) {
        if (useDetached) {
          const result = execDetached(startCommand, {
            cwd: startCwd,
            logFile: `/tmp/service-${port.port}.log`
          });
          console.log(`Started service with PID: ${result.pid}`);
        } else {
          // For docker-compose and other commands, use regular exec
          await execCommand(startCommand, {
            timeout: 30000,
            cwd: project.path
          });
        }

        // Wait for service to start
        await new Promise(resolve => setTimeout(resolve, 3000));

        // Check if it started
        const nowRunning = await isPortInUse(port.port);

        return NextResponse.json({
          success: true,
          message: nowRunning ? `Service ${action}ed successfully` : `Service ${action} initiated but may still be starting`,
          data: {
            port: port.port,
            status: nowRunning ? 'running' : 'starting',
          },
        });
      }
    }

    // For stop action, verify it stopped
    const finalStatus = await isPortInUse(port.port);

    return NextResponse.json({
      success: true,
      message: `Service ${action} completed`,
      data: {
        port: port.port,
        status: finalStatus ? 'running' : 'stopped'
      },
    });

  } catch (error) {
    console.error('Service control error:', error);
    return NextResponse.json(
      { success: false, error: 'Failed to control service' },
      { status: 500 }
    );
  }
}
