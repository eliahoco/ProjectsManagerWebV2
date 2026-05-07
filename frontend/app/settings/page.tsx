'use client';

/**
 * Settings Page - Global application settings
 */

import { useState, useEffect } from 'react';
import { Settings, FolderOpen, RefreshCw, Database, Terminal, Save, Check, Loader2, Github, Eye, EyeOff, Brain, Sparkles, CheckCircle, XCircle, Activity, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8401';

interface SettingsData {
  projectsDir: string;
  autoRefresh: string;
  refreshInterval: string;
  terminalApp: string;
  githubUsername: string;
  githubEmail: string;
  githubToken: string;
  githubAutoConnect: string;
}

interface ApiKeyStatus {
  configured: boolean;
  masked_key: string;
  provider: string;
  available: boolean;
}

interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
}

interface OllamaStatus {
  available: boolean;
  models: OllamaModel[];
  current_model: string;
}

export default function SettingsPage() {
  const toast = useToast();
  const [settings, setSettings] = useState<SettingsData>({
    projectsDir: '/Users/elic/Documents/Claude',
    autoRefresh: 'true',
    refreshInterval: '10',
    terminalApp: 'wezterm',
    githubUsername: '',
    githubEmail: '',
    githubToken: '',
    githubAutoConnect: 'true',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [testingGithub, setTestingGithub] = useState(false);

  // Anthropic API Key state
  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus | null>(null);
  const [newApiKey, setNewApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [savingApiKey, setSavingApiKey] = useState(false);
  const [testingApiKey, setTestingApiKey] = useState(false);
  const [apiKeyTestResult, setApiKeyTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Ollama state
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null);

  useEffect(() => {
    fetchSettings();
    fetchApiKeyStatus();
    fetchOllamaStatus();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      if (data.success) {
        setSettings(data.data);
      }
    } catch (error) {
      console.error('Failed to fetch settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchApiKeyStatus = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/ai/api-key`);
      if (res.ok) {
        const data = await res.json();
        setApiKeyStatus(data);
      }
    } catch (error) {
      console.error('Failed to fetch API key status:', error);
    }
  };

  const fetchOllamaStatus = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/ai/ollama/models`);
      if (res.ok) {
        setOllamaStatus(await res.json());
      }
    } catch (error) {
      console.error('Failed to fetch Ollama status:', error);
    }
  };

  const handleSelectOllamaModel = async (model: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/ai/ollama/model`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      });
      if (res.ok) {
        fetchOllamaStatus();
        fetchApiKeyStatus();
        toast.success('Model Selected', `Ollama model set to ${model}`);
      }
    } catch (error) {
      toast.error('Failed', 'Could not set Ollama model');
    }
  };

  const handleSaveApiKey = async () => {
    if (!newApiKey.trim()) return;
    setSavingApiKey(true);
    setApiKeyTestResult(null);
    try {
      const res = await fetch(`${BACKEND_URL}/api/ai/api-key`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: newApiKey.trim() }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setApiKeyStatus(data);
        setNewApiKey('');
        toast.success('API Key Saved', 'Anthropic API key has been configured');
      } else {
        toast.error('Save Failed', data.detail || 'Failed to save API key');
      }
    } catch (error) {
      toast.error('Save Failed', 'Could not connect to backend');
    } finally {
      setSavingApiKey(false);
    }
  };

  const handleTestApiKey = async () => {
    setTestingApiKey(true);
    setApiKeyTestResult(null);
    try {
      const res = await fetch(`${BACKEND_URL}/api/ai/api-key/test`, { method: 'POST' });
      const data = await res.json();
      setApiKeyTestResult({
        success: data.success,
        message: data.success ? data.message : data.error,
      });
    } catch (error) {
      setApiKeyTestResult({ success: false, message: 'Could not connect to backend' });
    } finally {
      setTestingApiKey(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      const data = await res.json();
      if (data.success) {
        setSettings(data.data);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (key: keyof SettingsData, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <Settings className="h-7 w-7 text-cyan-500" />
          Settings
        </h1>
        <p className="text-zinc-400 mt-1">
          Configure Projects Manager preferences
        </p>
      </div>

      <div className="space-y-6">
        {/* Projects Directory */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <FolderOpen className="h-5 w-5 text-cyan-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-white font-medium">Projects Directory</h3>
              <p className="text-sm text-zinc-400 mt-1">
                The root directory where all projects are located
              </p>
              <input
                type="text"
                value={settings.projectsDir}
                onChange={(e) => updateSetting('projectsDir', e.target.value)}
                className="mt-3 w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
            </div>
          </div>
        </div>

        {/* Auto Refresh */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <RefreshCw className="h-5 w-5 text-emerald-400" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-white font-medium">Auto Refresh</h3>
                  <p className="text-sm text-zinc-400 mt-1">
                    Automatically refresh project status
                  </p>
                </div>
                <button
                  onClick={() => updateSetting('autoRefresh', settings.autoRefresh === 'true' ? 'false' : 'true')}
                  className={cn(
                    'relative w-12 h-6 rounded-full transition-colors',
                    settings.autoRefresh === 'true' ? 'bg-cyan-600' : 'bg-zinc-700'
                  )}
                >
                  <span
                    className={cn(
                      'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
                      settings.autoRefresh === 'true' ? 'left-7' : 'left-1'
                    )}
                  />
                </button>
              </div>
              {settings.autoRefresh === 'true' && (
                <div className="mt-4">
                  <label className="text-sm text-zinc-400">Refresh interval (seconds)</label>
                  <input
                    type="number"
                    value={settings.refreshInterval}
                    onChange={(e) => updateSetting('refreshInterval', e.target.value)}
                    min={5}
                    max={60}
                    className="mt-2 w-24 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Terminal Application */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <Terminal className="h-5 w-5 text-violet-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-white font-medium">Terminal Application</h3>
              <p className="text-sm text-zinc-400 mt-1">
                Preferred terminal for opening Claude
              </p>
              <select
                value={settings.terminalApp}
                onChange={(e) => updateSetting('terminalApp', e.target.value)}
                className="mt-3 w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                <option value="wezterm">WezTerm</option>
                <option value="iterm">iTerm2</option>
                <option value="terminal">Terminal.app</option>
                <option value="alacritty">Alacritty</option>
              </select>
            </div>
          </div>
        </div>

        {/* AI Provider Configuration */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <Brain className="h-5 w-5 text-orange-400" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-white font-medium">AI Provider</h3>
                  <p className="text-sm text-zinc-400 mt-1">
                    Configure AI for feature breakdown, analysis, and execution
                  </p>
                </div>
                {apiKeyStatus && (
                  <span className={cn(
                    'flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border',
                    apiKeyStatus.available
                      ? 'text-green-400 bg-green-500/10 border-green-500/30'
                      : 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30'
                  )}>
                    {apiKeyStatus.available ? (
                      <><CheckCircle className="h-3 w-3" /> {apiKeyStatus.provider}</>
                    ) : (
                      <><XCircle className="h-3 w-3" /> Not configured</>
                    )}
                  </span>
                )}
              </div>

              <div className="mt-4 space-y-5">
                {/* Claude API Section */}
                <div className="border border-zinc-700 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-orange-400 mb-3 flex items-center gap-2">
                    <Sparkles className="h-4 w-4" />
                    Claude (Anthropic API)
                  </h4>

                  {/* Current key status */}
                  {apiKeyStatus?.configured && (
                    <div className="p-3 bg-zinc-800 rounded-lg mb-3">
                      <div className="flex justify-between text-sm">
                        <span className="text-zinc-400">Current Key</span>
                        <span className="text-zinc-300 font-mono text-xs">{apiKeyStatus.masked_key}</span>
                      </div>
                    </div>
                  )}

                  {/* New key input */}
                  <div>
                    <label className="text-sm text-zinc-400">
                      {apiKeyStatus?.configured ? 'Update API Key' : 'Enter API Key'}
                    </label>
                    <div className="relative mt-2">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={newApiKey}
                        onChange={(e) => setNewApiKey(e.target.value)}
                        placeholder="sk-ant-api03-..."
                        className="w-full px-4 py-2 pr-10 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-500"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white"
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    <p className="text-xs text-zinc-500 mt-1">
                      Get your key from console.anthropic.com/settings/keys
                    </p>
                  </div>

                  {/* Test result */}
                  {apiKeyTestResult && (
                    <div className={cn(
                      'mt-3 p-3 rounded-lg text-sm flex items-center gap-2',
                      apiKeyTestResult.success
                        ? 'bg-green-900/30 border border-green-700/50 text-green-400'
                        : 'bg-red-900/30 border border-red-700/50 text-red-400'
                    )}>
                      {apiKeyTestResult.success
                        ? <CheckCircle className="h-4 w-4 flex-shrink-0" />
                        : <XCircle className="h-4 w-4 flex-shrink-0" />
                      }
                      {apiKeyTestResult.message}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex items-center gap-3 mt-3">
                    <Button
                      variant="default"
                      size="sm"
                      onClick={handleSaveApiKey}
                      loading={savingApiKey}
                      disabled={!newApiKey.trim()}
                      className="bg-orange-600 hover:bg-orange-700"
                    >
                      <Save className="h-3.5 w-3.5" />
                      Save Key
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleTestApiKey}
                      loading={testingApiKey}
                      disabled={!apiKeyStatus?.configured}
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      Test Connection
                    </Button>
                  </div>
                </div>

                {/* Ollama Section */}
                <div className="border border-zinc-700 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium text-violet-400 flex items-center gap-2">
                      <Terminal className="h-4 w-4" />
                      Ollama (Local AI)
                    </h4>
                    <span className={cn(
                      'text-xs px-2 py-0.5 rounded-full',
                      ollamaStatus?.available
                        ? 'text-green-400 bg-green-500/10'
                        : 'text-zinc-500 bg-zinc-800'
                    )}>
                      {ollamaStatus?.available ? 'Running' : 'Not running'}
                    </span>
                  </div>

                  {ollamaStatus?.available ? (
                    <div className="space-y-3">
                      <div>
                        <label className="text-sm text-zinc-400">Model</label>
                        <select
                          value={ollamaStatus.current_model}
                          onChange={(e) => handleSelectOllamaModel(e.target.value)}
                          className="mt-2 w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                        >
                          {ollamaStatus.models.map((m) => (
                            <option key={m.name} value={m.name}>
                              {m.name} {m.size ? `(${(m.size / 1e9).toFixed(1)}GB)` : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={fetchOllamaStatus}
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Refresh Models
                      </Button>
                    </div>
                  ) : (
                    <div className="p-3 bg-zinc-800 rounded-lg">
                      <p className="text-sm text-zinc-400">
                        Ollama is not running. Start it with <code className="text-zinc-300 bg-zinc-700 px-1.5 py-0.5 rounded text-xs">ollama serve</code> to use local AI models.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* GitHub Settings */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <Github className="h-5 w-5 text-white" />
            </div>
            <div className="flex-1">
              <h3 className="text-white font-medium">GitHub Configuration</h3>
              <p className="text-sm text-zinc-400 mt-1">
                Configure git credentials for push/pull operations
              </p>

              <div className="mt-4 space-y-4">
                {/* Username */}
                <div>
                  <label className="text-sm text-zinc-400">Git Username</label>
                  <input
                    type="text"
                    value={settings.githubUsername}
                    onChange={(e) => updateSetting('githubUsername', e.target.value)}
                    placeholder="Your Name"
                    className="mt-2 w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>

                {/* Email */}
                <div>
                  <label className="text-sm text-zinc-400">Git Email</label>
                  <input
                    type="email"
                    value={settings.githubEmail}
                    onChange={(e) => updateSetting('githubEmail', e.target.value)}
                    placeholder="you@example.com"
                    className="mt-2 w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>

                {/* Token */}
                <div>
                  <label className="text-sm text-zinc-400">Personal Access Token (optional)</label>
                  <div className="relative mt-2">
                    <input
                      type={showToken ? 'text' : 'password'}
                      value={settings.githubToken}
                      onChange={(e) => updateSetting('githubToken', e.target.value)}
                      placeholder="ghp_xxxxxxxxxxxx"
                      className="w-full px-4 py-2 pr-10 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    />
                    <button
                      type="button"
                      onClick={() => setShowToken(!showToken)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white"
                    >
                      {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <p className="text-xs text-zinc-500 mt-1">
                    For HTTPS authentication. Leave blank to use SSH keys.
                  </p>
                </div>

                {/* Auto Connect */}
                <div className="flex items-center justify-between pt-2">
                  <div>
                    <span className="text-sm text-zinc-300">Auto-configure git</span>
                    <p className="text-xs text-zinc-500">
                      Automatically set git config for new projects
                    </p>
                  </div>
                  <button
                    onClick={() => updateSetting('githubAutoConnect', settings.githubAutoConnect === 'true' ? 'false' : 'true')}
                    className={cn(
                      'relative w-12 h-6 rounded-full transition-colors',
                      settings.githubAutoConnect === 'true' ? 'bg-cyan-600' : 'bg-zinc-700'
                    )}
                  >
                    <span
                      className={cn(
                        'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
                        settings.githubAutoConnect === 'true' ? 'left-7' : 'left-1'
                      )}
                    />
                  </button>
                </div>

                {/* Test Button */}
                <div className="pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      setTestingGithub(true);
                      try {
                        const res = await fetch('/api/github/test', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            username: settings.githubUsername,
                            email: settings.githubEmail,
                          }),
                        });
                        const data = await res.json();
                        if (data.success) {
                          toast.success('Git Configured', 'Git credentials are valid');
                        } else {
                          toast.error('Configuration Error', data.error);
                        }
                      } catch {
                        toast.error('Test Failed', 'Could not verify git configuration');
                      } finally {
                        setTestingGithub(false);
                      }
                    }}
                    loading={testingGithub}
                    disabled={!settings.githubUsername || !settings.githubEmail}
                  >
                    Test Configuration
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Database Info */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <Database className="h-5 w-5 text-amber-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-white font-medium">Database</h3>
              <p className="text-sm text-zinc-400 mt-1">
                SQLite database for project and port data
              </p>
              <div className="mt-3 p-3 bg-zinc-800 rounded-lg">
                <div className="flex justify-between text-sm">
                  <span className="text-zinc-400">Location</span>
                  <span className="text-zinc-300 font-mono">prisma/dev.db</span>
                </div>
                <div className="flex justify-between text-sm mt-2">
                  <span className="text-zinc-400">Status</span>
                  <span className="text-green-400">Connected</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* About */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
          <h3 className="text-white font-medium mb-3">About</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-400">Version</span>
              <span className="text-zinc-300">1.0.0</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-400">Framework</span>
              <span className="text-zinc-300">Next.js 16</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-400">Database</span>
              <span className="text-zinc-300">Prisma + SQLite</span>
            </div>
          </div>
        </div>

        {/* Save Button */}
        {/* CB-1951 E6.3.2 + E10.1.2 — AutoPilot section */}
        <AutoPilotSettingsSection />

        <div className="flex justify-end">
          <Button
            variant="default"
            onClick={handleSave}
            loading={saving}
            className="min-w-[120px]"
          >
            {saved ? (
              <>
                <Check className="h-4 w-4" />
                Saved!
              </>
            ) : (
              <>
                <Save className="h-4 w-4" />
                Save Settings
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}


// ============================================================================
// AutoPilot section (CB-1951 E6.3.2 metrics tile + E10.1.2 persistence toggle)
// ============================================================================

interface AutoPilotMetrics {
  pending: number;
  running: number;
  paused: number;
  waiting_reset: number;
  completed: number;
  aborted: number;
  autoPause24h: number;
  circuitBreakerTrips24h: number;
  crashRecovery24h: number;
}

function AutoPilotSettingsSection() {
  const toast = useToast();
  const [metrics, setMetrics] = useState<AutoPilotMetrics | null>(null);
  const [persistenceEnabled, setPersistenceEnabled] = useState<boolean | null>(null);
  const [togglingPersistence, setTogglingPersistence] = useState(false);

  // Poll metrics every 30s
  useEffect(() => {
    let cancelled = false;
    const fetchMetrics = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/execute/queue/metrics`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setMetrics(data);
      } catch {
        // network errors are silent — tile just shows last value
      }
    };
    fetchMetrics();
    const id = setInterval(fetchMetrics, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Fetch persistence flag once on mount
  useEffect(() => {
    fetch(`${BACKEND_URL}/api/execute/queue/settings/persistence-enabled`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && typeof data.enabled === 'boolean') {
          setPersistenceEnabled(data.enabled);
        }
      })
      .catch(() => {});
  }, []);

  const handleTogglePersistence = async () => {
    if (persistenceEnabled === null) return;
    const next = !persistenceEnabled;
    setTogglingPersistence(true);
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/execute/queue/settings/persistence-enabled`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: next }),
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPersistenceEnabled(data.enabled);
      toast.success(
        'AutoPilot persistence',
        data.enabled
          ? 'Enabled — queues will survive backend restarts.'
          : 'Disabled — queues run in-memory only (pre-CB-1951 behaviour).',
      );
    } catch (e) {
      toast.error('Toggle failed', String(e));
    } finally {
      setTogglingPersistence(false);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
      <div className="flex items-start gap-4 mb-4">
        <div className="p-2 bg-zinc-800 rounded-lg">
          <Zap className="h-5 w-5 text-amber-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-zinc-100">AutoPilot</h3>
          <p className="text-sm text-zinc-400">
            Live queue metrics and persistence settings (CB-1951).
          </p>
        </div>
      </div>

      {/* Metrics tile (E6.3.2) */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3 text-sm font-medium text-zinc-300">
          <Activity className="h-4 w-4 text-amber-400" />
          Live queue counts
          <span className="text-xs text-zinc-500">(refreshes every 30s)</span>
        </div>
        {metrics === null ? (
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            <MetricCell label="Running" value={metrics.running} accent="text-amber-400" />
            <MetricCell label="Paused" value={metrics.paused} accent="text-zinc-300" />
            <MetricCell label="Waiting reset" value={metrics.waiting_reset} accent="text-yellow-400" />
            <MetricCell label="Completed" value={metrics.completed} accent="text-emerald-400" />
            <MetricCell label="Aborted" value={metrics.aborted} accent="text-rose-400" />
            <MetricCell label="Pending" value={metrics.pending} accent="text-zinc-300" />
            <MetricCell label="Auto-pauses (24h)" value={metrics.autoPause24h} accent="text-yellow-400" />
            <MetricCell label="Breaker trips (24h)" value={metrics.circuitBreakerTrips24h} accent="text-rose-400" />
            <MetricCell label="Crash recovery (24h)" value={metrics.crashRecovery24h} accent="text-rose-400" />
          </div>
        )}
      </div>

      {/* Persistence toggle (E10.1.2) */}
      <div className="border-t border-zinc-800 pt-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="text-sm font-medium text-zinc-200">
              Persistence enabled
            </div>
            <p className="text-xs text-zinc-500 mt-1">
              When ON, queues survive backend restarts and crash recovery is
              available. Disabling reverts to the original in-memory behaviour
              (use only if persistence misbehaves). In-flight queues snapshot
              this flag at creation time — toggling affects only future queues.
            </p>
          </div>
          <button
            type="button"
            disabled={persistenceEnabled === null || togglingPersistence}
            onClick={handleTogglePersistence}
            className={cn(
              'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors',
              persistenceEnabled ? 'bg-amber-500' : 'bg-zinc-700',
              (persistenceEnabled === null || togglingPersistence) && 'opacity-50 cursor-not-allowed',
            )}
            aria-label={persistenceEnabled ? 'Disable AutoPilot persistence' : 'Enable AutoPilot persistence'}
            aria-pressed={!!persistenceEnabled}
          >
            <span
              className={cn(
                'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                persistenceEnabled ? 'translate-x-6' : 'translate-x-1',
              )}
            />
          </button>
        </div>
      </div>
    </div>
  );
}

function MetricCell({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="bg-zinc-800/50 border border-zinc-800 rounded-md px-3 py-2">
      <div className={cn('text-xl font-semibold', accent)}>{value}</div>
      <div className="text-xs text-zinc-500 mt-0.5">{label}</div>
    </div>
  );
}
