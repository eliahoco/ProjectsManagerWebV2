'use client';

/**
 * Pipeline Configuration Settings Page
 * Configure per-project pipeline execution settings
 */

import { useState, useEffect, useMemo } from 'react';
import {
  Workflow,
  Shield,
  Zap,
  RotateCcw,
  Bot,
  Save,
  Check,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/toast';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  useAgents,
  usePipelineConfig,
  useUpdatePipelineConfig,
} from '@/hooks/useAgents';
import type { PipelineConfigUpdate } from '@/hooks/useAgents';

// We also need the projects list
import { useProjects } from '@/hooks/useCodeBoard';

export default function PipelineConfigPage() {
  const toast = useToast();
  const { data: projects, isLoading: projectsLoading } = useProjects();
  const { data: agents } = useAgents();
  const updateConfig = useUpdatePipelineConfig();

  // Project selection
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  // Auto-select first project
  useEffect(() => {
    if (projects && projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  // Fetch config for selected project
  const {
    data: config,
    isLoading: configLoading,
    error: configError,
  } = usePipelineConfig(selectedProjectId);

  // Local form state
  const [localConfig, setLocalConfig] = useState<PipelineConfigUpdate>({
    verifyEnabled: true,
    autoFix: false,
    maxRetries: 3,
    defaultAgentId: null,
  });
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Sync local state when config loads
  useEffect(() => {
    if (config) {
      setLocalConfig({
        verifyEnabled: config.verifyEnabled,
        autoFix: config.autoFix,
        maxRetries: config.maxRetries,
        defaultAgentId: config.defaultAgentId,
      });
      setHasChanges(false);
    }
  }, [config]);

  const activeAgents = useMemo(() => {
    return (agents || []).filter((a) => a.isActive);
  }, [agents]);

  const updateField = <K extends keyof PipelineConfigUpdate>(
    key: K,
    value: PipelineConfigUpdate[K]
  ) => {
    setLocalConfig((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
    setSaved(false);
  };

  const handleSave = async () => {
    if (!selectedProjectId) return;
    try {
      await updateConfig.mutateAsync({
        projectId: selectedProjectId,
        config: localConfig,
      });
      setSaved(true);
      setHasChanges(false);
      setTimeout(() => setSaved(false), 2000);
      toast.success('Pipeline Config Saved', 'Configuration updated successfully');
    } catch (err) {
      toast.error(
        'Save Failed',
        err instanceof Error ? err.message : 'Could not save pipeline config'
      );
    }
  };

  return (
    <div className="p-6 max-w-3xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <Workflow className="h-7 w-7 text-cyan-500" />
          Pipeline Configuration
        </h1>
        <p className="text-zinc-400 mt-1">
          Configure the multi-stage AI execution pipeline per project
        </p>
      </div>

      {/* Project Selector */}
      <div className="mb-6">
        <label className="block text-sm text-zinc-400 mb-2">Select Project</label>
        {projectsLoading ? (
          <Skeleton className="h-10 w-full rounded-lg" />
        ) : projects && projects.length > 0 ? (
          <select
            value={selectedProjectId || ''}
            onChange={(e) => {
              setSelectedProjectId(e.target.value || null);
              setHasChanges(false);
            }}
            className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500"
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        ) : (
          <div className="text-zinc-500 text-sm p-4 bg-zinc-900 border border-zinc-800 rounded-lg">
            No projects found. Create a project first.
          </div>
        )}
      </div>

      {/* Config loading state */}
      {configLoading && selectedProjectId && (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        </div>
      )}

      {/* Config error state -- 404 is OK, means we create new */}
      {configError && !configLoading && selectedProjectId && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 text-yellow-400 mb-4 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-sm">No configuration found</p>
            <p className="text-xs text-yellow-400/70 mt-1">
              Default settings will be used. Save to create a custom configuration for this project.
            </p>
          </div>
        </div>
      )}

      {/* Configuration Form */}
      {selectedProjectId && !configLoading && (
        <div className="space-y-6">
          {/* Verification Stage Toggle */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <div className="flex items-start gap-4">
              <div className="p-2 bg-zinc-800 rounded-lg">
                <Shield className="h-5 w-5 text-emerald-400" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-white font-medium">Verification Stage</h3>
                    <p className="text-sm text-zinc-400 mt-1">
                      Run automated verification after implementation to validate changes
                    </p>
                  </div>
                  <button
                    onClick={() => updateField('verifyEnabled', !localConfig.verifyEnabled)}
                    className={cn(
                      'relative w-12 h-6 rounded-full transition-colors',
                      localConfig.verifyEnabled ? 'bg-cyan-600' : 'bg-zinc-700'
                    )}
                  >
                    <span
                      className={cn(
                        'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
                        localConfig.verifyEnabled ? 'left-7' : 'left-1'
                      )}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Auto-Fix Toggle */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <div className="flex items-start gap-4">
              <div className="p-2 bg-zinc-800 rounded-lg">
                <Zap className="h-5 w-5 text-amber-400" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-white font-medium">Auto-Fix on Failure</h3>
                    <p className="text-sm text-zinc-400 mt-1">
                      Automatically attempt to fix issues when verification fails
                    </p>
                  </div>
                  <button
                    onClick={() => updateField('autoFix', !localConfig.autoFix)}
                    className={cn(
                      'relative w-12 h-6 rounded-full transition-colors',
                      localConfig.autoFix ? 'bg-cyan-600' : 'bg-zinc-700'
                    )}
                  >
                    <span
                      className={cn(
                        'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
                        localConfig.autoFix ? 'left-7' : 'left-1'
                      )}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Max Retries */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <div className="flex items-start gap-4">
              <div className="p-2 bg-zinc-800 rounded-lg">
                <RotateCcw className="h-5 w-5 text-violet-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-white font-medium">Max Retries</h3>
                <p className="text-sm text-zinc-400 mt-1">
                  Maximum number of retry attempts when verification fails (1-5)
                </p>
                <input
                  type="number"
                  value={localConfig.maxRetries ?? 3}
                  onChange={(e) => {
                    const val = Math.max(1, Math.min(5, parseInt(e.target.value) || 1));
                    updateField('maxRetries', val);
                  }}
                  min={1}
                  max={5}
                  className="mt-3 w-24 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                />
              </div>
            </div>
          </div>

          {/* Default Agent Selector */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
            <div className="flex items-start gap-4">
              <div className="p-2 bg-zinc-800 rounded-lg">
                <Bot className="h-5 w-5 text-cyan-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-white font-medium">Default Agent</h3>
                <p className="text-sm text-zinc-400 mt-1">
                  Select the default AI agent for pipeline execution. Leave blank for automatic matching.
                </p>
                <select
                  value={localConfig.defaultAgentId || ''}
                  onChange={(e) =>
                    updateField('defaultAgentId', e.target.value || null)
                  }
                  className="mt-3 w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500"
                >
                  <option value="">Auto-match (recommended)</option>
                  {activeAgents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.displayName}
                      {agent.description ? ` - ${agent.description}` : ''}
                    </option>
                  ))}
                </select>
                {activeAgents.length === 0 && (
                  <p className="text-xs text-zinc-500 mt-2">
                    No active agents found. Go to AI Agents settings to scan and register agents.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex items-center justify-between">
            {hasChanges && (
              <Badge variant="warning" className="text-xs">
                Unsaved changes
              </Badge>
            )}
            <div className="ml-auto">
              <Button
                variant="default"
                onClick={handleSave}
                loading={updateConfig.isPending}
                disabled={!hasChanges && !configError}
                className="min-w-[140px]"
              >
                {saved ? (
                  <>
                    <Check className="h-4 w-4" />
                    Saved!
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save Configuration
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
