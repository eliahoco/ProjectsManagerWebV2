'use client';

/**
 * AI Launcher Component
 * Dropdown for launching projects with different AI tools
 */

import { useState, useRef, useEffect } from 'react';
import {
  Terminal,
  MousePointer2,
  Code2,
  Bot,
  Sparkles,
  Globe,
  ChevronDown,
  Copy,
  ExternalLink,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { AI_PROVIDERS, WEB_AI_URLS, type AIProviderType } from '@/lib/ai-providers';

interface AILauncherProps {
  projectId: string;
  projectName: string;
  onOpenAI: (projectId: string, provider: AIProviderType) => Promise<void>;
  size?: 'sm' | 'default';
  className?: string;
}

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Terminal,
  MousePointer2,
  Code2,
  Bot,
  Sparkles,
  Globe,
};

export function AILauncher({ projectId, projectName, onOpenAI, size = 'default', className }: AILauncherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState<AIProviderType | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLocalAI = async (provider: AIProviderType) => {
    setIsLoading(provider);
    try {
      await onOpenAI(projectId, provider);
    } finally {
      setIsLoading(null);
      setIsOpen(false);
    }
  };

  const handleWebAI = async (providerId: AIProviderType) => {
    try {
      // Fetch project context
      const res = await fetch(`/api/projects/${projectId}/open-ai`);
      const data = await res.json();

      if (data.success) {
        // Copy context to clipboard
        await navigator.clipboard.writeText(data.data.context);
        setCopiedId(providerId);
        setTimeout(() => setCopiedId(null), 2000);

        // Open web AI
        const url = WEB_AI_URLS[providerId];
        if (url) {
          window.open(url, '_blank');
        }
      }
    } catch (error) {
      console.error('Failed to copy context:', error);
    }
    setIsOpen(false);
  };

  const localProviders = AI_PROVIDERS.filter(p => p.type === 'local');
  const webProviders = AI_PROVIDERS.filter(p => p.type === 'web');

  const buttonHeight = size === 'sm' ? 'h-8' : 'h-9';
  const buttonPadding = size === 'sm' ? 'px-2' : 'px-3';
  const iconSize = size === 'sm' ? 'h-3 w-3' : 'h-4 w-4';
  const fontSize = size === 'sm' ? 'text-xs' : 'text-sm';

  return (
    <div className={cn('relative', className)} ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'inline-flex items-center justify-center gap-1 rounded-md border border-zinc-700 bg-transparent text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors',
          buttonHeight,
          buttonPadding,
          fontSize
        )}
        title="Open with AI"
      >
        <Terminal className={iconSize} />
        <span className="hidden sm:inline">AI</span>
        <ChevronDown className={cn(iconSize, 'opacity-50')} />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-1 z-50 w-64 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl overflow-hidden">
          {/* Local AI Tools */}
          <div className="p-2">
            <div className="text-xs text-zinc-500 px-2 py-1 font-medium">Local Editors</div>
            {localProviders.map((provider) => {
              const Icon = ICON_MAP[provider.icon];
              const loading = isLoading === provider.id;

              return (
                <button
                  key={provider.id}
                  onClick={() => handleLocalAI(provider.id)}
                  disabled={loading}
                  className={cn(
                    'w-full flex items-center gap-3 px-2 py-2 rounded-md text-left transition-colors',
                    'hover:bg-zinc-800 disabled:opacity-50'
                  )}
                >
                  <Icon className={cn('h-4 w-4', provider.color)} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white">{provider.name}</div>
                    <div className="text-xs text-zinc-500 truncate">{provider.description}</div>
                  </div>
                  {loading && (
                    <div className="h-4 w-4 border-2 border-zinc-600 border-t-white rounded-full animate-spin" />
                  )}
                </button>
              );
            })}
          </div>

          <div className="border-t border-zinc-800" />

          {/* Web AI Tools */}
          <div className="p-2">
            <div className="text-xs text-zinc-500 px-2 py-1 font-medium">
              Web AIs <span className="text-zinc-600">(copies context)</span>
            </div>
            {webProviders.map((provider) => {
              const Icon = ICON_MAP[provider.icon];
              const isCopied = copiedId === provider.id;

              return (
                <button
                  key={provider.id}
                  onClick={() => handleWebAI(provider.id)}
                  className={cn(
                    'w-full flex items-center gap-3 px-2 py-2 rounded-md text-left transition-colors',
                    'hover:bg-zinc-800'
                  )}
                >
                  <Icon className={cn('h-4 w-4', provider.color)} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white">{provider.name}</div>
                    <div className="text-xs text-zinc-500 truncate">{provider.description}</div>
                  </div>
                  {isCopied ? (
                    <Check className="h-4 w-4 text-green-400" />
                  ) : (
                    <div className="flex items-center gap-1 text-zinc-600">
                      <Copy className="h-3 w-3" />
                      <ExternalLink className="h-3 w-3" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
