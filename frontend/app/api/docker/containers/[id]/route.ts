import { NextRequest, NextResponse } from 'next/server';
import { startContainer, stopContainer, restartContainer } from '@/lib/docker';

const VALID_ACTIONS = ['start', 'stop', 'restart'] as const;
type ContainerAction = (typeof VALID_ACTIONS)[number];

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const action = body.action as string;

    if (!VALID_ACTIONS.includes(action as ContainerAction)) {
      return NextResponse.json(
        { success: false, error: `Invalid action. Must be one of: ${VALID_ACTIONS.join(', ')}` },
        { status: 400 }
      );
    }

    const handlers: Record<ContainerAction, (id: string) => Promise<{ success: boolean; output: string }>> = {
      start: startContainer,
      stop: stopContainer,
      restart: restartContainer,
    };

    const result = await handlers[action as ContainerAction](id);

    return NextResponse.json({
      success: result.success,
      output: result.output,
      error: result.success ? undefined : result.output,
    });
  } catch (error) {
    const message = (error as Error).message;
    if (message === 'Invalid container ID') {
      return NextResponse.json({ success: false, error: message }, { status: 400 });
    }
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
