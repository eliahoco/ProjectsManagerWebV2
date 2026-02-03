'use client';

/**
 * Auto Pilot Configuration Modal
 * Allows users to configure auto pilot execution settings before starting
 */

import { useState } from 'react';
import { X, Zap, AlertTriangle, CheckCircle2, RefreshCw, SkipForward, XCircle, ArrowRight, Rocket, Settings2 } from 'lucide-react';
import {
  AutoPilotConfig,
  AutoPilotFailAction,
  AutoPilotSuccessAction,
  DEFAULT_AUTO_PILOT_CONFIG,
  AUTO_PILOT_FAIL_OPTIONS,
  AUTO_PILOT_SUCCESS_OPTIONS,
} from '@/types/codeboard';
import { cn } from '@/lib/utils';

interface AutoPilotConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStart: (config: AutoPilotConfig) => void;
  taskCount: number;
}

export function AutoPilotConfigModal({
  isOpen,
  onClose,
  onStart,
  taskCount,
}: AutoPilotConfigModalProps) {
  const [config, setConfig] = useState<AutoPilotConfig>({
    ...DEFAULT_AUTO_PILOT_CONFIG,
    enabled: true,
  });

  const handleStart = () => {
    onStart(config);
    onClose();
  };

  const getFailIcon = (action: AutoPilotFailAction) => {
    switch (action) {
      case 'CONTINUE_MARK_FAILED': return <AlertTriangle className="w-4 h-4" />;
      case 'RETRY': return <RefreshCw className="w-4 h-4" />;
      case 'SKIP': return <SkipForward className="w-4 h-4" />;
      case 'TERMINATE': return <XCircle className="w-4 h-4" />;
    }
  };

  const getSuccessIcon = (action: AutoPilotSuccessAction) => {
    switch (action) {
      case 'MOVE_NEXT': return <ArrowRight className="w-4 h-4" />;
      case 'MARK_WAITING_QA': return <Rocket className="w-4 h-4" />;
      case 'MARK_DONE': return <CheckCircle2 className="w-4 h-4" />;
      case 'RUN_QA_TASK': return <Zap className="w-4 h-4" />;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-700 bg-gradient-to-r from-amber-900/30 to-orange-900/30">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-600/20 rounded-lg">
              <Zap className="w-6 h-6 text-amber-400" />
            </div>
            <div>
              <h2 className="font-semibold text-lg text-white">Auto Pilot Configuration</h2>
              <p className="text-sm text-amber-200/70">{taskCount} tasks will be executed</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* On Fail Configuration */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400" />
              <label className="text-sm font-medium text-zinc-200">On Task Failure</label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {AUTO_PILOT_FAIL_OPTIONS.map(option => (
                <button
                  key={option.value}
                  onClick={() => setConfig(prev => ({ ...prev, onFail: option.value }))}
                  className={cn(
                    'flex items-center gap-2 p-3 rounded-lg border transition-all text-left',
                    config.onFail === option.value
                      ? 'border-red-500 bg-red-900/30 text-red-200'
                      : 'border-zinc-700 bg-zinc-800/50 text-zinc-300 hover:border-zinc-600'
                  )}
                >
                  <div className={cn(
                    'p-1.5 rounded',
                    config.onFail === option.value ? 'bg-red-600/30' : 'bg-zinc-700'
                  )}>
                    {getFailIcon(option.value)}
                  </div>
                  <div>
                    <div className="text-sm font-medium">{option.label}</div>
                    <div className="text-xs text-zinc-500">{option.description}</div>
                  </div>
                </button>
              ))}
            </div>

            {/* Retry count input (only shown when RETRY is selected) */}
            {config.onFail === 'RETRY' && (
              <div className="flex items-center gap-3 pl-2 mt-2">
                <label className="text-sm text-zinc-400">Max retries:</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={config.maxRetries}
                  onChange={(e) => setConfig(prev => ({ ...prev, maxRetries: Math.max(1, Math.min(10, parseInt(e.target.value) || 1)) }))}
                  className="w-20 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-sm text-zinc-200 focus:border-amber-500 focus:outline-none"
                />
                <span className="text-xs text-zinc-500">times</span>
              </div>
            )}
          </div>

          {/* Divider */}
          <div className="border-t border-zinc-700" />

          {/* On Success Configuration */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-400" />
              <label className="text-sm font-medium text-zinc-200">On Task Success</label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {AUTO_PILOT_SUCCESS_OPTIONS.map(option => (
                <button
                  key={option.value}
                  onClick={() => setConfig(prev => ({ ...prev, onSuccess: option.value }))}
                  className={cn(
                    'flex items-center gap-2 p-3 rounded-lg border transition-all text-left',
                    config.onSuccess === option.value
                      ? 'border-green-500 bg-green-900/30 text-green-200'
                      : 'border-zinc-700 bg-zinc-800/50 text-zinc-300 hover:border-zinc-600'
                  )}
                >
                  <div className={cn(
                    'p-1.5 rounded',
                    config.onSuccess === option.value ? 'bg-green-600/30' : 'bg-zinc-700'
                  )}>
                    {getSuccessIcon(option.value)}
                  </div>
                  <div>
                    <div className="text-sm font-medium">{option.label}</div>
                    <div className="text-xs text-zinc-500">{option.description}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Configuration Summary */}
          <div className="p-4 bg-zinc-800/50 rounded-lg border border-zinc-700">
            <div className="flex items-center gap-2 mb-2">
              <Settings2 className="w-4 h-4 text-zinc-400" />
              <span className="text-sm font-medium text-zinc-300">Configuration Summary</span>
            </div>
            <div className="text-sm text-zinc-400 space-y-1">
              <p>
                <span className="text-red-400">On Fail:</span>{' '}
                {AUTO_PILOT_FAIL_OPTIONS.find(o => o.value === config.onFail)?.label}
                {config.onFail === 'RETRY' && ` (${config.maxRetries}x)`}
              </p>
              <p>
                <span className="text-green-400">On Success:</span>{' '}
                {AUTO_PILOT_SUCCESS_OPTIONS.find(o => o.value === config.onSuccess)?.label}
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-zinc-700 bg-zinc-900/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg text-sm"
          >
            Cancel
          </button>
          <button
            onClick={handleStart}
            className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white rounded-lg font-medium text-sm"
          >
            <Zap className="w-4 h-4" />
            Start Auto Pilot
          </button>
        </div>
      </div>
    </div>
  );
}
