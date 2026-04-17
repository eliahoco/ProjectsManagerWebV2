'use client';

import { useRef, useEffect, useState } from 'react';
import { X, Square, Terminal, Loader2, FileText, FileEdit, TerminalSquare } from 'lucide-react';
import { useExecutionOutput, useStopExecution, type ExecutionSession } from '@/hooks/useCodeBoard';
import { Issue } from '@/types/codeboard';
import { cn } from '@/lib/utils';

interface InlineTerminalPanelProps {
  session: ExecutionSession;
  issue?: Issue;
  onClose: () => void;
  onStop?: () => void;
}

export function InlineTerminalPanel({ session, issue, onClose, onStop }: InlineTerminalPanelProps) {
  const outputRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const { data: outputData } = useExecutionOutput(session.session_id);
  const stopExecution = useStopExecution();

  const isRunning = session.status === 'running' || session.status === 'pending';
  const isTerminal = session.status === 'completed' || session.status === 'failed' || session.status === 'cancelled';

  // Auto-scroll to bottom on new output
  useEffect(() => {
    if (autoScroll && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [outputData?.output, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  const handleScroll = () => {
    if (!outputRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = outputRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 40;
    setAutoScroll(isAtBottom);
  };

  const handleStop = () => {
    stopExecution.mutate(session.session_id);
    onStop?.();
  };

  const statusColor = session.status === 'running' ? 'text-cyan-400' :
    session.status === 'completed' ? 'text-green-400' :
    session.status === 'failed' ? 'text-red-400' :
    session.status === 'cancelled' ? 'text-yellow-400' :
    'text-zinc-400';

  return (
    <div className="flex flex-col h-full bg-zinc-950 border-l border-zinc-700 rounded-r-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-zinc-900 border-b border-zinc-700 shrink-0">
        <Terminal className="w-4 h-4 text-cyan-400" />
        <span className="text-xs font-mono text-zinc-300 truncate">
          {issue?.key || session.issue_key}
        </span>
        <span className={cn("text-xs font-medium", statusColor)}>
          {session.status === 'running' && <Loader2 className="w-3 h-3 inline animate-spin mr-1" />}
          {session.status.toUpperCase()}
        </span>
        {session.pipeline_stage && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
            {session.pipeline_stage}
          </span>
        )}
        <div className="flex-1" />
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200"
          title="Close terminal"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Progress stats bar */}
      {(outputData?.phase || outputData?.progress_percent != null) && (
        <div className="flex items-center gap-3 px-3 py-1.5 bg-zinc-900/50 border-b border-zinc-800 shrink-0">
          {outputData.phase && (
            <span className="text-[10px] font-medium text-cyan-400 uppercase tracking-wider">
              {outputData.phase}
            </span>
          )}
          {outputData.progress_percent != null && (
            <div className="flex items-center gap-2 flex-1">
              <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-cyan-500 rounded-full transition-all duration-500"
                  style={{ width: `${outputData.progress_percent}%` }}
                />
              </div>
              <span className="text-[10px] text-zinc-400 tabular-nums">
                {outputData.progress_percent}%
              </span>
            </div>
          )}
          <div className="flex items-center gap-2 text-[10px] text-zinc-500">
            {outputData.files_read != null && (
              <span className="flex items-center gap-0.5">
                <FileText className="w-3 h-3" /> {outputData.files_read}
              </span>
            )}
            {outputData.files_written != null && (
              <span className="flex items-center gap-0.5">
                <FileEdit className="w-3 h-3" /> {outputData.files_written}
              </span>
            )}
            {outputData.commands_run != null && (
              <span className="flex items-center gap-0.5">
                <TerminalSquare className="w-3 h-3" /> {outputData.commands_run}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Terminal output */}
      <div
        ref={outputRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed min-h-0"
      >
        {outputData?.output && outputData.output.length > 0 ? (
          outputData.output.map((line, index) => (
            <div
              key={index}
              className={cn(
                'py-px',
                line.startsWith('[ERROR]') && 'text-red-400',
                line.startsWith('[STDERR]') && 'text-orange-400',
                line.startsWith('[DEBUG]') && 'text-zinc-600 text-[10px]',
                line.startsWith('[INFO]') && 'text-green-400',
                line.startsWith('>') && 'text-cyan-400',
                line.startsWith('#') && 'text-yellow-400',
                !line.startsWith('[') && !line.startsWith('>') && !line.startsWith('#') && 'text-zinc-300'
              )}
            >
              {line}
            </div>
          ))
        ) : (
          <div className="text-zinc-600 text-center py-8">
            {isRunning ? 'Waiting for output...' : 'No output available'}
          </div>
        )}
      </div>

      {/* Footer actions */}
      <div className="flex items-center gap-2 px-3 py-2 bg-zinc-900 border-t border-zinc-800 shrink-0">
        {isRunning && (
          <button
            onClick={handleStop}
            disabled={stopExecution.isPending}
            className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium bg-red-600 hover:bg-red-500 text-white disabled:opacity-50"
          >
            <Square className="w-3 h-3" />
            Stop
          </button>
        )}
        {isTerminal && (
          <span className={cn("text-xs", statusColor)}>
            {session.status === 'completed' ? 'Execution completed' :
             session.status === 'failed' ? 'Execution failed' :
             'Execution cancelled'}
          </span>
        )}
        <div className="flex-1" />
        <span className="text-[10px] text-zinc-600">
          {outputData?.total_lines ?? 0} lines
        </span>
      </div>
    </div>
  );
}
