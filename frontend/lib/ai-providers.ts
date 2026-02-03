/**
 * AI Provider Configuration
 * Defines supported AI tools for launching projects
 */

export type AIProviderType = 'claude-code' | 'cursor' | 'vscode' | 'chatgpt' | 'gemini' | 'claude-web';

export interface AIProvider {
  id: AIProviderType;
  name: string;
  shortName: string;
  description: string;
  type: 'local' | 'web';
  icon: string; // Lucide icon name
  color: string; // Tailwind color class
  available: boolean; // Whether it can be auto-detected
}

export const AI_PROVIDERS: AIProvider[] = [
  {
    id: 'claude-code',
    name: 'Claude Code',
    shortName: 'Claude',
    description: 'Open in terminal with Claude Code CLI',
    type: 'local',
    icon: 'Terminal',
    color: 'text-orange-400',
    available: true,
  },
  {
    id: 'cursor',
    name: 'Cursor',
    shortName: 'Cursor',
    description: 'Open project in Cursor AI editor',
    type: 'local',
    icon: 'MousePointer2',
    color: 'text-purple-400',
    available: true,
  },
  {
    id: 'vscode',
    name: 'VS Code',
    shortName: 'VS Code',
    description: 'Open project in Visual Studio Code',
    type: 'local',
    icon: 'Code2',
    color: 'text-blue-400',
    available: true,
  },
  {
    id: 'chatgpt',
    name: 'ChatGPT',
    shortName: 'ChatGPT',
    description: 'Open ChatGPT with project context copied',
    type: 'web',
    icon: 'Bot',
    color: 'text-green-400',
    available: true,
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    shortName: 'Gemini',
    description: 'Open Gemini with project context copied',
    type: 'web',
    icon: 'Sparkles',
    color: 'text-cyan-400',
    available: true,
  },
  {
    id: 'claude-web',
    name: 'Claude Web',
    shortName: 'Claude.ai',
    description: 'Open Claude.ai with project context copied',
    type: 'web',
    icon: 'Globe',
    color: 'text-orange-300',
    available: true,
  },
];

export const LOCAL_PROVIDERS = AI_PROVIDERS.filter(p => p.type === 'local');
export const WEB_PROVIDERS = AI_PROVIDERS.filter(p => p.type === 'web');

export const WEB_AI_URLS: Record<string, string> = {
  'chatgpt': 'https://chat.openai.com/',
  'gemini': 'https://gemini.google.com/',
  'claude-web': 'https://claude.ai/new',
};

/**
 * Generate context prompt for a project
 */
export function generateProjectContext(project: {
  name: string;
  path: string;
  description?: string | null;
  ports?: Array<{ serviceName: string; port: number }>;
}): string {
  const portsList = project.ports
    ?.map((p) => `${p.serviceName}: ${p.port}`)
    .join(', ') || 'None configured';

  return `Project: ${project.name}
Path: ${project.path}
${project.description ? `Description: ${project.description}` : ''}
Ports: ${portsList}

Please read the PROJECT_DESCRIPTOR.md file at the project path to understand:
1. What this project is about
2. Current status and recent changes
3. What should be worked on next

Project path to navigate to: ${project.path}`;
}
