/**
 * Smoke test — StudioPage renders without crashing when sessions list is empty.
 *
 * Mocks:
 *   - TenantContext (provides workspaceId + tenantId)
 *   - useStudio hooks (returns empty sessions list, no errors)
 *   - useConversationStream (no-op SSE hook)
 *   - useStudioStore (Zustand — empty tabs, null activeTabId)
 *   - next/navigation (useRouter, useParams stubs)
 *   - lucide-react (lightweight stubs to avoid SVG resolution issues)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// ─── Navigation mocks ────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useParams: () => ({ id: 'default' }),
  usePathname: () => '/workspace/default/studio',
  useSearchParams: () => new URLSearchParams(),
}));

// ─── TenantContext mock ───────────────────────────────────────────────────────

vi.mock('@/contexts/TenantContext', () => ({
  TenantProvider: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  useTenant: () => ({
    workspaceId: 'default',
    tenantId: 'default',
    projectId: '1511e54f71dccd3fa79f67fe',
    setProjectId: vi.fn(),
  }),
}));

// ─── Zustand store mock ───────────────────────────────────────────────────────

const mockOpenTab = vi.fn();
const mockCloseTab = vi.fn();
const mockSetActiveTab = vi.fn();
const mockSetDraft = vi.fn();

vi.mock('@/stores/useStudioStore', () => ({
  useStudioStore: () => ({
    tabs: [],
    activeTabId: null,
    drafts: {},
    panelRatio: 0.6,
    openTab: mockOpenTab,
    closeTab: mockCloseTab,
    setActiveTab: mockSetActiveTab,
    setDraft: mockSetDraft,
    setPanelRatio: vi.fn(),
    updateTab: vi.fn(),
  }),
}));

// ─── Studio hooks mock ────────────────────────────────────────────────────────

vi.mock('@/hooks/useStudio', () => ({
  useStudioSessions: () => ({
    data: [],
    isLoading: false,
    isError: false,
  }),
  useStudioMessages: () => ({
    data: [],
    isLoading: false,
    isError: false,
  }),
  useCreateStudioSession: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ id: 'session-1', title: 'New conversation' }),
    isPending: false,
  }),
  useSendMessage: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

// ─── SSE hook mock ────────────────────────────────────────────────────────────

vi.mock('@/hooks/useConversationStream', () => ({
  useConversationStream: () => ({
    streamedContent: '',
    agentStatuses: {},
    isConnected: false,
    authError: false,
    clearStreamedContent: vi.fn(),
  }),
  AGENT_COLORS: {},
}));

// ─── workspaceFetch mock ──────────────────────────────────────────────────────

vi.mock('@/lib/workspaceFetch', () => ({
  workspaceFetch: vi.fn().mockResolvedValue([]),
}));

// ─── lucide-react stubs ───────────────────────────────────────────────────────

vi.mock('lucide-react', () => ({
  MessageSquare: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-MessageSquare', ...p }),
  MessagesSquare: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-MessagesSquare', ...p }),
  ListTodo: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-ListTodo', ...p }),
  GitBranch: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-GitBranch', ...p }),
  Plus: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Plus', ...p }),
  X: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-X', ...p }),
  Loader2: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Loader2', ...p }),
  Send: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Send', ...p }),
  Search: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-Search', ...p }),
  ChevronDown: (p: Record<string, unknown>) => React.createElement('span', { 'data-testid': 'icon-ChevronDown', ...p }),
}));

// ─── Import after mocks ───────────────────────────────────────────────────────

import { StudioPage } from '@/components/studio/StudioPage';

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('StudioPage smoke test', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing when sessions list is empty', () => {
    expect(() => render(React.createElement(StudioPage))).not.toThrow();
  });

  it('shows "New conversation" button when no tabs are open', () => {
    render(React.createElement(StudioPage));
    // Should show the new conversation button in the tab bar
    const newButtons = screen.getAllByText(/new/i);
    expect(newButtons.length).toBeGreaterThan(0);
  });

  it('shows empty state prompt when no tabs are open', () => {
    render(React.createElement(StudioPage));
    expect(screen.getByText(/start a conversation/i)).toBeDefined();
  });

  it('shows "No active agents" in agent panel when there are no agents', () => {
    render(React.createElement(StudioPage));
    expect(screen.getByText(/no active agents/i)).toBeDefined();
  });

  it('renders Agents section header', () => {
    render(React.createElement(StudioPage));
    expect(screen.getByText('Agents')).toBeDefined();
  });
});
