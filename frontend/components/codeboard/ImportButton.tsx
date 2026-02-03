'use client';

/**
 * ImportButton - Quick access button to import projects
 *
 * Can be used as a simple link button or with a dropdown showing
 * recently browsed directories for quick import.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FolderInput, FolderOpen, Package, GitBranch, ChevronDown, X, Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';

interface DirectoryInfo {
  name: string;
  path: string;
  hasPackageJson: boolean;
  hasGit: boolean;
  alreadyImported: boolean;
}

interface ImportButtonProps {
  /** Display variant */
  variant?: 'default' | 'compact' | 'icon-only';
  /** Additional CSS classes */
  className?: string;
  /** Callback when a project is imported */
  onImportSuccess?: (projectId: string, projectName: string) => void;
}

export function ImportButton({
  variant = 'default',
  className,
  onImportSuccess
}: ImportButtonProps) {
  const router = useRouter();
  const toast = useToast();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [directories, setDirectories] = useState<DirectoryInfo[]>([]);
  const [projectsDir, setProjectsDir] = useState('');
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState<string | null>(null);

  const handleDropdownToggle = async () => {
    if (isDropdownOpen) {
      setIsDropdownOpen(false);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch('/api/projects/browse');
      const data = await res.json();
      if (data.success) {
        setDirectories(data.data.directories);
        setProjectsDir(data.data.projectsDir);
        setIsDropdownOpen(true);
      } else {
        toast.error('Browse Failed', data.error || 'Could not browse directories');
      }
    } catch (error) {
      toast.error('Browse Failed', 'Network error');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickImport = async (dir: DirectoryInfo) => {
    if (dir.alreadyImported) return;

    setImporting(dir.path);
    try {
      const res = await fetch('/api/projects/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: dir.path,
          name: dir.name,
        }),
      });

      const data = await res.json();

      if (data.success) {
        toast.success('Project Imported', `${data.data.name} has been imported`);
        setIsDropdownOpen(false);

        // Update directory list to show as imported
        setDirectories(dirs =>
          dirs.map(d => d.path === dir.path ? { ...d, alreadyImported: true } : d)
        );

        onImportSuccess?.(data.data.id, data.data.name);

        // Navigate to the new project
        router.push(`/projects/${data.data.id}`);
      } else {
        toast.error('Import Failed', data.error);
      }
    } catch (err) {
      toast.error('Import Failed', 'Network error');
    } finally {
      setImporting(null);
    }
  };

  // Icon-only variant - just links to import page
  if (variant === 'icon-only') {
    return (
      <Link href="/import">
        <Button
          variant="outline"
          size="icon"
          className={className}
          title="Import Project"
        >
          <FolderInput className="h-4 w-4" />
        </Button>
      </Link>
    );
  }

  // Compact variant - smaller button with dropdown
  if (variant === 'compact') {
    return (
      <div className="relative">
        <Button
          variant="outline"
          size="sm"
          onClick={handleDropdownToggle}
          loading={loading}
          className={cn('gap-1.5', className)}
        >
          <FolderInput className="h-3.5 w-3.5" />
          Import
          <ChevronDown className={cn(
            'h-3 w-3 transition-transform',
            isDropdownOpen && 'rotate-180'
          )} />
        </Button>

        {isDropdownOpen && (
          <ImportDropdown
            directories={directories}
            projectsDir={projectsDir}
            importing={importing}
            onClose={() => setIsDropdownOpen(false)}
            onSelect={handleQuickImport}
          />
        )}
      </div>
    );
  }

  // Default variant - full button with dropdown
  return (
    <div className="relative">
      <Button
        variant="outline"
        onClick={handleDropdownToggle}
        loading={loading}
        className={cn('gap-2', className)}
      >
        <FolderInput className="h-4 w-4" />
        Import Project
        <ChevronDown className={cn(
          'h-4 w-4 transition-transform',
          isDropdownOpen && 'rotate-180'
        )} />
      </Button>

      {isDropdownOpen && (
        <ImportDropdown
          directories={directories}
          projectsDir={projectsDir}
          importing={importing}
          onClose={() => setIsDropdownOpen(false)}
          onSelect={handleQuickImport}
        />
      )}
    </div>
  );
}

interface ImportDropdownProps {
  directories: DirectoryInfo[];
  projectsDir: string;
  importing: string | null;
  onClose: () => void;
  onSelect: (dir: DirectoryInfo) => void;
}

function ImportDropdown({
  directories,
  projectsDir,
  importing,
  onClose,
  onSelect
}: ImportDropdownProps) {
  // Filter to show only unimported projects first
  const availableProjects = directories.filter(d => !d.alreadyImported);
  const importedProjects = directories.filter(d => d.alreadyImported);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40"
        onClick={onClose}
      />

      {/* Dropdown */}
      <div className="absolute right-0 top-full mt-2 z-50 w-80 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-700 bg-zinc-800/50">
          <div>
            <h4 className="text-sm font-medium text-white">Quick Import</h4>
            <p className="text-xs text-zinc-500 truncate max-w-[200px]">{projectsDir}</p>
          </div>
          <div className="flex items-center gap-1">
            <Link
              href="/import"
              className="text-xs text-cyan-400 hover:text-cyan-300 px-2 py-1 rounded hover:bg-zinc-700"
            >
              Advanced
            </Link>
            <button
              onClick={onClose}
              className="p-1 hover:bg-zinc-700 rounded text-zinc-400 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="max-h-64 overflow-y-auto">
          {availableProjects.length === 0 && importedProjects.length === 0 ? (
            <div className="py-8 text-center text-zinc-500 text-sm">
              No projects found in directory
            </div>
          ) : availableProjects.length === 0 ? (
            <div className="py-4 text-center text-zinc-500 text-sm">
              All projects already imported
            </div>
          ) : (
            <div className="py-1">
              {availableProjects.map((dir) => (
                <button
                  key={dir.path}
                  onClick={() => onSelect(dir)}
                  disabled={importing === dir.path}
                  className="w-full text-left px-3 py-2 hover:bg-zinc-800 flex items-center justify-between gap-2 transition-colors disabled:opacity-50"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <FolderOpen className="h-4 w-4 text-cyan-500 flex-shrink-0" />
                    <span className="text-sm text-white truncate">{dir.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {dir.hasPackageJson && (
                      <span title="Has package.json">
                        <Package className="h-3.5 w-3.5 text-green-400" />
                      </span>
                    )}
                    {dir.hasGit && (
                      <span title="Git repository">
                        <GitBranch className="h-3.5 w-3.5 text-orange-400" />
                      </span>
                    )}
                    {importing === dir.path ? (
                      <Loader2 className="h-3.5 w-3.5 text-cyan-400 animate-spin" />
                    ) : (
                      <FolderInput className="h-3.5 w-3.5 text-zinc-500" />
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer - show count of already imported */}
        {importedProjects.length > 0 && (
          <div className="px-3 py-2 border-t border-zinc-700 bg-zinc-800/30">
            <p className="text-xs text-zinc-500 flex items-center gap-1">
              <Check className="h-3 w-3" />
              {importedProjects.length} project{importedProjects.length !== 1 ? 's' : ''} already imported
            </p>
          </div>
        )}
      </div>
    </>
  );
}

export default ImportButton;
