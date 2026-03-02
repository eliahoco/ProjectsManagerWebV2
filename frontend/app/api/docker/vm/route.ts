import { NextRequest, NextResponse } from 'next/server';
import { startColima, stopColima, restartColima } from '@/lib/docker';

const VALID_ACTIONS = ['start', 'stop', 'restart'] as const;
type VmAction = (typeof VALID_ACTIONS)[number];

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const action = body.action as string;

    if (!VALID_ACTIONS.includes(action as VmAction)) {
      return NextResponse.json(
        { success: false, error: `Invalid action. Must be one of: ${VALID_ACTIONS.join(', ')}` },
        { status: 400 }
      );
    }

    const handlers: Record<VmAction, () => Promise<{ success: boolean; output: string }>> = {
      start: startColima,
      stop: stopColima,
      restart: restartColima,
    };

    const result = await handlers[action as VmAction]();

    return NextResponse.json({
      success: result.success,
      output: result.output,
      error: result.success ? undefined : result.output,
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: (error as Error).message },
      { status: 500 }
    );
  }
}
