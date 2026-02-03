'use client';

/**
 * Floating Execution Status - Shows execution progress in a small floating window
 * Allows navigation while task is running, with option to expand full modal
 */

import { useState, useEffect } from 'react';
import { Terminal, Maximize2, X, Loader2, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ExecutionSession } from '@/hooks/useCodeBoard';

interface FloatingExecutionStatusProps {
  session: ExecutionSession;
  onExpand: () => void;
  onClose: () => void;
}

export function FloatingExecutionStatus({
  session,
  onExpand,
  onClose
}: FloatingExecutionStatusProps) {
  const [currentSession, setCurrentSession] = useState<ExecutionSession>(session);
  const [isHovered, setIsHovered] = useState(false);

  // Poll for updates when running
  useEffect(() => {
    if (currentSession.status !== 'running') return;

    const pollStatus = async () => {
      try {
        const response = await fetch(`/api/execute/sessions`);
        if (response.ok) {
          const sessions: ExecutionSession[] = await response.json();
          const updated = sessions.find(s => s.session_id === session.session_id);
          if (updated) {
            setCurrentSession(updated);
          }
        }
      } catch (error) {
        console.error('Error polling execution status:', error);
      }
    };

    const interval = setInterval(pollStatus, 2000);
    return () => clearInterval(interval);
  }, [session.session_id, currentSession.status]);

  const getStatusIcon = () => {
    switch (currentSession.status) {
      case 'running':
        return <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />;
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-400" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-400" />;
      case 'cancelled':
        return <AlertCircle className="w-4 h-4 text-yellow-400" />;
      default:
        return <Terminal className="w-4 h-4 text-zinc-400" />;
    }
  };

  const getStatusColor = () => {
    switch (currentSession.status) {
      case 'running':
        return 'border-cyan-500/50 bg-cyan-500/10';
      case 'completed':
        return 'border-green-500/50 bg-green-500/10';
      case 'failed':
        return 'border-red-500/50 bg-red-500/10';
      case 'cancelled':
        return 'border-yellow-500/50 bg-yellow-500/10';
      default:
        return 'border-zinc-700 bg-zinc-800';
    }
  };

  const progress = currentSession.progress_percent || 0;

  return (
    <div
      className={cn(
        'fixed bottom-4 right-4 z-50 rounded-lg border shadow-xl transition-all duration-200',
        'backdrop-blur-sm',
        getStatusColor(),
        isHovered ? 'scale-105' : ''
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Progress bar at top */}
      {currentSession.status === 'running' && (
        <div className="absolute top-0 left-0 right-0 h-1 bg-zinc-700 rounded-t-lg overflow-hidden">
          <div
            className="h-full bg-cyan-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      <div className="p-3 pt-4">
        {/* Header row */}
        <div className="flex items-center justify-between gap-3 mb-2">
          <div className="flex items-center gap-2">
            {getStatusIcon()}
            <span className="font-mono text-sm font-medium text-white">
              {currentSession.issue_key}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={onExpand}
              className="p-1 rounded hover:bg-white/10 transition-colors"
              title="Open full terminal"
            >
              <Maximize2 className="w-4 h-4 text-zinc-400 hover:text-white" />
            </button>
            {currentSession.status !== 'running' && (
              <button
                onClick={onClose}
                className="p-1 rounded hover:bg-white/10 transition-colors"
                title="Close"
              >
                <X className="w-4 h-4 text-zinc-400 hover:text-white" />
              </button>
            )}
          </div>
        </div>

        {/* Status info */}
        <div className="text-xs text-zinc-400 truncate max-w-[250px]">
          {currentSession.status === 'running' ? (
            <>
              <span className="text-cyan-400">{progress}%</span>
              {currentSession.current_action && (
                <span className="ml-2">{currentSession.current_action}</span>
              )}
            </>
          ) : currentSession.status === 'completed' ? (
            <span className="text-green-400">Completed successfully</span>
          ) : currentSession.status === 'failed' ? (
            <span className="text-red-400">
              {currentSession.error || 'Execution failed'}
            </span>
          ) : (
            <span className="text-yellow-400">Cancelled</span>
          )}
        </div>

        {/* Click to expand hint */}
        {isHovered && currentSession.status === 'running' && (
          <div className="mt-2 text-xs text-zinc-500 text-center">
            Click <Maximize2 className="w-3 h-3 inline" /> to view terminal
          </div>
        )}
      </div>
    </div>
  );
}
