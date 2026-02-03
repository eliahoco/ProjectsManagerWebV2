'use client';

/**
 * Import Project Page
 * Import existing projects from the filesystem
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { FolderInput, Check, AlertCircle, FolderOpen, Package, GitBranch, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';

interface DirectoryInfo {
  name: string;
  path: string;
  hasPackageJson: boolean;
  hasGit: boolean;
  alreadyImported: boolean;
}

export default function ImportPage() {
  const router = useRouter();
  const toast = useToast();
  const [projectPath, setProjectPath] = useState('');
  const [projectName, setProjectName] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [showBrowser, setShowBrowser] = useState(false);
  const [directories, setDirectories] = useState<DirectoryInfo[]>([]);
  const [browsing, setBrowsing] = useState(false);
  const [projectsDir, setProjectsDir] = useState('');

  const handleBrowse = async () => {
    setBrowsing(true);
    try {
      const res = await fetch('/api/projects/browse');
      const data = await res.json();
      if (data.success) {
        setDirectories(data.data.directories);
        setProjectsDir(data.data.projectsDir);
        setShowBrowser(true);
      } else {
        toast.error('Browse Failed', data.error || 'Could not browse directories');
      }
    } catch (error) {
      toast.error('Browse Failed', 'Network error');
    } finally {
      setBrowsing(false);
    }
  };

  const selectDirectory = (dir: DirectoryInfo) => {
    setProjectPath(dir.path);
    setProjectName(dir.name);
    setShowBrowser(false);
  };

  const handleImport = async () => {
    if (!projectPath.trim()) {
      setError('Please enter a project path');
      return;
    }

    setIsImporting(true);
    setError(null);

    try {
      const res = await fetch('/api/projects/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: projectPath.trim(),
          name: projectName.trim() || undefined,
        }),
      });

      const data = await res.json();

      if (data.success) {
        setSuccess(true);
        toast.success('Project Imported', `${data.data.name} has been imported`);
        setTimeout(() => {
          router.push(`/projects/${data.data.id}`);
        }, 1500);
      } else {
        setError(data.error || 'Failed to import project');
        toast.error('Import Failed', data.error);
      }
    } catch (err) {
      console.error('Error importing project:', err);
      setError('Failed to import project. Please try again.');
      toast.error('Import Failed', 'Network error');
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white dark:text-white flex items-center gap-3">
          <FolderInput className="h-7 w-7 text-cyan-500" />
          Import Existing Project
        </h1>
        <p className="text-zinc-400 mt-1">
          Add an existing project from your filesystem
        </p>
      </div>

      {/* Form */}
      <div className="bg-zinc-900 dark:bg-zinc-900 border border-zinc-800 dark:border-zinc-800 rounded-lg p-6 space-y-6">
        {/* Path Input */}
        <div>
          <label htmlFor="project-path" className="block text-sm font-medium text-zinc-300 dark:text-zinc-300 mb-2">
            Project Path
          </label>
          <div className="flex gap-2">
            <input
              id="project-path"
              type="text"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              placeholder="/Users/you/projects/my-project"
              className="flex-1 px-4 py-2 bg-zinc-800 dark:bg-zinc-800 border border-zinc-700 dark:border-zinc-700 rounded-lg text-white dark:text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
            <Button variant="outline" onClick={handleBrowse} loading={browsing}>
              <FolderOpen className="h-4 w-4" />
              Browse
            </Button>
          </div>
          <p className="text-xs text-zinc-500 mt-1">
            Enter the full path or click Browse to select from available projects
          </p>
        </div>

        {/* Browse Modal */}
        {showBrowser && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-zinc-900 border border-zinc-700 rounded-lg w-full max-w-2xl max-h-[80vh] overflow-hidden">
              <div className="flex items-center justify-between p-4 border-b border-zinc-700">
                <div>
                  <h3 className="font-medium text-white">Select Project</h3>
                  <p className="text-xs text-zinc-500 mt-1">{projectsDir}</p>
                </div>
                <button
                  onClick={() => setShowBrowser(false)}
                  className="p-1 hover:bg-zinc-800 rounded"
                >
                  <X className="h-5 w-5 text-zinc-400" />
                </button>
              </div>
              <div className="overflow-y-auto max-h-[60vh] p-2">
                {directories.length === 0 ? (
                  <div className="text-center py-8 text-zinc-500">
                    No directories found
                  </div>
                ) : (
                  <div className="space-y-1">
                    {directories.map((dir) => (
                      <button
                        key={dir.path}
                        onClick={() => !dir.alreadyImported && selectDirectory(dir)}
                        disabled={dir.alreadyImported}
                        className={`w-full text-left px-4 py-3 rounded-lg flex items-center justify-between transition-colors ${
                          dir.alreadyImported
                            ? 'bg-zinc-800/50 text-zinc-600 cursor-not-allowed'
                            : 'bg-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-700'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <FolderOpen className={`h-5 w-5 ${dir.alreadyImported ? 'text-zinc-600' : 'text-cyan-500'}`} />
                          <div>
                            <div className="font-medium">{dir.name}</div>
                            <div className="text-xs text-zinc-500">{dir.path}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {dir.hasPackageJson && (
                            <span className="flex items-center gap-1 text-xs text-green-400">
                              <Package className="h-3 w-3" />
                            </span>
                          )}
                          {dir.hasGit && (
                            <span className="flex items-center gap-1 text-xs text-orange-400">
                              <GitBranch className="h-3 w-3" />
                            </span>
                          )}
                          {dir.alreadyImported && (
                            <span className="text-xs bg-zinc-700 text-zinc-400 px-2 py-0.5 rounded">
                              Imported
                            </span>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Name Override */}
        <div>
          <label htmlFor="project-name" className="block text-sm font-medium text-zinc-300 dark:text-zinc-300 mb-2">
            Project Name (optional)
          </label>
          <input
            id="project-name"
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Leave blank to use directory name"
            className="w-full px-4 py-2 bg-zinc-800 dark:bg-zinc-800 border border-zinc-700 dark:border-zinc-700 rounded-lg text-white dark:text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-cyan-500"
          />
          <p className="text-xs text-zinc-500 mt-1">
            Override the project name (defaults to directory name)
          </p>
        </div>

        {/* Info Box */}
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-4">
          <h4 className="font-medium text-cyan-400 mb-2">What gets imported?</h4>
          <ul className="text-sm text-zinc-400 space-y-1">
            <li>• Project type auto-detected from package.json, requirements.txt, etc.</li>
            <li>• Ports detected from .ports.env or docker-compose.yml</li>
            <li>• Description extracted from PROJECT_DESCRIPTOR.md</li>
            <li>• Git status if repository exists</li>
          </ul>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {/* Success */}
        {success && (
          <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400">
            <Check className="h-4 w-4 flex-shrink-0" />
            <span className="text-sm">Project imported successfully! Redirecting...</span>
          </div>
        )}

        {/* Submit Button */}
        <Button
          variant="default"
          className="w-full"
          onClick={handleImport}
          loading={isImporting}
          disabled={!projectPath.trim() || success}
        >
          {success ? (
            <>
              <Check className="h-4 w-4" />
              Imported!
            </>
          ) : (
            <>
              <FolderInput className="h-4 w-4" />
              Import Project
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
