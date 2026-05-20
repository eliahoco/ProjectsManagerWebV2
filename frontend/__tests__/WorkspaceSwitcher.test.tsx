/**
 * Smoke tests — WorkspaceSwitcher renders the real project list and wires to context.
 *
 * Mocks:
 *   - @tanstack/react-query useQuery → controlled via mockQueryResult ref
 *   - TenantContext → provides projectId + setProjectId spy
 *   - lucide-react ChevronDown → lightweight stub
 *   - next/navigation → no-op stubs
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

// ─── Mock next/navigation ────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useParams: () => ({ id: 'default' }),
  usePathname: () => '/workspace/default/studio',
  useSearchParams: () => new URLSearchParams(),
}));

// ─── Stub projects ────────────────────────────────────────────────────────────

const STUB_PROJECTS = [
  { id: 'proj-aaa', name: 'Alpha Project' },
  { id: 'proj-bbb', name: 'Beta Project' },
  { id: 'proj-ccc', name: 'Gamma Project' },
];

// ─── Mock React Query useQuery — controlled state ─────────────────────────────

// Mutable control object that individual tests can override before render.
let mockQueryResult: { data: typeof STUB_PROJECTS | undefined; isLoading: boolean; isError: boolean } = {
  data: STUB_PROJECTS,
  isLoading: false,
  isError: false,
};

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => mockQueryResult,
}));

// ─── Mock TenantContext ───────────────────────────────────────────────────────

const mockSetProjectId = vi.fn();
let mockProjectId = 'proj-aaa';

vi.mock('@/contexts/TenantContext', () => ({
  TenantProvider: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  useTenant: () => ({
    workspaceId: 'default',
    tenantId: 'default',
    projectId: mockProjectId,
    setProjectId: mockSetProjectId,
  }),
}));

// ─── Mock lucide-react ────────────────────────────────────────────────────────

vi.mock('lucide-react', () => ({
  ChevronDown: (p: Record<string, unknown>) =>
    React.createElement('span', { 'data-testid': 'icon-ChevronDown', ...p }),
}));

// ─── Import after mocks ───────────────────────────────────────────────────────

import { WorkspaceSwitcher } from '@/components/workspace/WorkspaceSwitcher';

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('WorkspaceSwitcher — loaded state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProjectId = 'proj-aaa';
    mockQueryResult = { data: STUB_PROJECTS, isLoading: false, isError: false };
  });

  it('renders all 3 projects in the dropdown', () => {
    render(React.createElement(WorkspaceSwitcher));

    const select = screen.getByRole('combobox', { name: /switch active project/i });
    expect(select).toBeDefined();

    const options = select.querySelectorAll('option');
    expect(options.length).toBe(3);

    const texts = Array.from(options).map((o) => o.textContent);
    expect(texts).toContain('Alpha Project');
    expect(texts).toContain('Beta Project');
    expect(texts).toContain('Gamma Project');
  });

  it('selects the current projectId from context by default', () => {
    render(React.createElement(WorkspaceSwitcher));

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('proj-aaa');
  });

  it('calls setProjectId when a different project is selected', () => {
    render(React.createElement(WorkspaceSwitcher));

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'proj-bbb' } });

    expect(mockSetProjectId).toHaveBeenCalledTimes(1);
    expect(mockSetProjectId).toHaveBeenCalledWith('proj-bbb');
  });

  it('does not call setProjectId when the same project is selected', () => {
    render(React.createElement(WorkspaceSwitcher));

    const select = screen.getByRole('combobox');
    // Simulate selecting the already-active project
    fireEvent.change(select, { target: { value: 'proj-aaa' } });

    expect(mockSetProjectId).not.toHaveBeenCalled();
  });

  it('renders the ChevronDown icon', () => {
    render(React.createElement(WorkspaceSwitcher));
    expect(screen.getByTestId('icon-ChevronDown')).toBeDefined();
  });
});

describe('WorkspaceSwitcher — loading state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProjectId = 'proj-aaa';
    mockQueryResult = { data: undefined, isLoading: true, isError: false };
  });

  it('disables the select while loading', () => {
    render(React.createElement(WorkspaceSwitcher));
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });

  it('shows a loading placeholder option', () => {
    render(React.createElement(WorkspaceSwitcher));
    expect(screen.getByText(/loading projects/i)).toBeDefined();
  });
});

describe('WorkspaceSwitcher — error state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProjectId = 'proj-aaa';
    mockQueryResult = { data: undefined, isLoading: false, isError: true };
  });

  it('disables the select on error', () => {
    render(React.createElement(WorkspaceSwitcher));
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });

  it('shows an error placeholder option', () => {
    render(React.createElement(WorkspaceSwitcher));
    expect(screen.getByText(/failed to load projects/i)).toBeDefined();
  });
});
