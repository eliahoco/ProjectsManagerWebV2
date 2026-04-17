import { NextResponse } from 'next/server';
import { getVmMemory, getVmCpuTicks, getVmLoadAverage, getContainerStats } from '@/lib/docker';
import type { CpuTicks } from '@/lib/docker';

// Module-level state for CPU delta calculation
let previousCpuTicks: CpuTicks | null = null;

export async function GET() {
  try {
    const [memoryRes, cpuTicksRes, loadAvgRes, containersRes] = await Promise.allSettled([
      getVmMemory(),
      getVmCpuTicks(),
      getVmLoadAverage(),
      getContainerStats(),
    ]);

    // Log partial failures for observability
    if (memoryRes.status === 'rejected') console.warn('getVmMemory failed:', memoryRes.reason);
    if (cpuTicksRes.status === 'rejected') console.warn('getVmCpuTicks failed:', cpuTicksRes.reason);
    if (loadAvgRes.status === 'rejected') console.warn('getVmLoadAverage failed:', loadAvgRes.reason);
    if (containersRes.status === 'rejected') console.warn('getContainerStats failed:', containersRes.reason);

    const memory = memoryRes.status === 'fulfilled' ? memoryRes.value : { totalMB: 0, usedMB: 0 };
    const cpuTicks = cpuTicksRes.status === 'fulfilled' ? cpuTicksRes.value : { total: 0, idle: 0 };
    const loadAvg = loadAvgRes.status === 'fulfilled' ? loadAvgRes.value : { load1: 0, load5: 0, load15: 0 };
    const containers = containersRes.status === 'fulfilled' ? containersRes.value : [];

    // If total ticks is 0, VM commands likely failed
    if (cpuTicks.total === 0 && memory.totalMB === 0) {
      return NextResponse.json(
        { success: false, error: 'VM is not responding' },
        { status: 503 }
      );
    }

    // Calculate CPU% from delta between this reading and the previous one
    let cpuPercent = -1;
    if (previousCpuTicks && previousCpuTicks.total > 0) {
      const totalDelta = cpuTicks.total - previousCpuTicks.total;
      const idleDelta = cpuTicks.idle - previousCpuTicks.idle;
      if (totalDelta > 0) {
        cpuPercent = Math.round((1 - idleDelta / totalDelta) * 10000) / 100;
        cpuPercent = Math.max(0, Math.min(100, cpuPercent));
      }
    }
    previousCpuTicks = cpuTicks;

    const memoryPercent = memory.totalMB > 0
      ? Math.round((memory.usedMB / memory.totalMB) * 10000) / 100
      : 0;

    return NextResponse.json({
      success: true,
      data: {
        timestamp: Date.now(),
        vm: {
          cpuPercent,
          memoryUsedMB: memory.usedMB,
          memoryTotalMB: memory.totalMB,
          memoryPercent,
          loadAvg1: loadAvg.load1,
          loadAvg5: loadAvg.load5,
          loadAvg15: loadAvg.load15,
        },
        containers,
      },
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: (error as Error).message },
      { status: 500 }
    );
  }
}
