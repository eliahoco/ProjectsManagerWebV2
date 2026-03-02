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

    const [docker, containers] = await Promise.all([
      getDockerInfo(),
      getDockerContainers(),
    ]);

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
