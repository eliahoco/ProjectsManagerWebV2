import { NextResponse } from 'next/server';
import { getColimaStatus, getDockerInfo, getDockerContainers } from '@/lib/docker';

export async function GET() {
  try {
    const colima = await getColimaStatus();

    if (!colima.running) {
      return NextResponse.json({
        success: true,
        data: { colima, docker: null, containers: [] },
      });
    }

    const [dockerRes, containersRes] = await Promise.allSettled([
      getDockerInfo(),
      getDockerContainers(),
    ]);

    const docker = dockerRes.status === 'fulfilled' ? dockerRes.value : null;
    const containers = containersRes.status === 'fulfilled' ? containersRes.value : [];

    // Log partial failures for observability
    if (dockerRes.status === 'rejected') {
      console.warn('getDockerInfo failed:', dockerRes.reason);
    }
    if (containersRes.status === 'rejected') {
      console.warn('getDockerContainers failed:', containersRes.reason);
    }

    return NextResponse.json({
      success: true,
      data: { colima, docker, containers },
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: (error as Error).message },
      { status: 500 }
    );
  }
}
