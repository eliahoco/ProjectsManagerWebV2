'use client';

/**
 * Settings Page - Global application settings
 */

import { useState, useEffect } from 'react';
import { Settings, FolderOpen, RefreshCw, Database, Terminal, Save, Check, Loader2, Github, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';

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

  useEffect(() => {
    fetchSettings();
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
