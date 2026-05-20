'use client';

/**
 * TenantContext — workspaceId + tenantId + projectId for the current workspace session.
 *
 * Phase 1: single-tenant. tenantId is always "default". workspaceId comes
 * from the [id] route param. projectId is the active CodeBoard project the
 * user has selected in WorkspaceSwitcher (persisted to localStorage).
 *
 * Phase 2: tenantId will be derived from the JWT claims injected by the
 * FastAPI InternalAuthDep. The context shape stays the same; only the
 * source of tenantId changes.
 *
 * Usage:
 *   const { workspaceId, tenantId, projectId, setProjectId } = useTenant();
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

const DEFAULT_PROJECT_ID = '1511e54f71dccd3fa79f67fe';
const STORAGE_KEY = 'studio-active-project-id';

function readStoredProjectId(): string {
  if (typeof window === 'undefined') return DEFAULT_PROJECT_ID;
  return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_PROJECT_ID;
}

export interface TenantContextValue {
  /** The active workspace ID (from URL param [id]). */
  workspaceId: string;
  /** Phase 1 default tenant. Phase 2: derived from JWT. */
  tenantId: string;
  /** The active CodeBoard project ID selected in WorkspaceSwitcher. */
  projectId: string;
  /** Update the active project; persists to localStorage. */
  setProjectId: (id: string) => void;
}

const TenantContext = createContext<TenantContextValue | null>(null);

export interface TenantProviderProps {
  workspaceId: string;
  tenantId?: string;
  children: ReactNode;
}

export function TenantProvider({
  workspaceId,
  tenantId = 'default',
  children,
}: TenantProviderProps) {
  const [projectId, setProjectIdState] = useState<string>(readStoredProjectId);

  // Persist to localStorage whenever the selection changes.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    localStorage.setItem(STORAGE_KEY, projectId);
  }, [projectId]);

  const setProjectId = useCallback((id: string) => {
    setProjectIdState(id);
  }, []);

  const value = useMemo<TenantContextValue>(
    () => ({ workspaceId, tenantId, projectId, setProjectId }),
    [workspaceId, tenantId, projectId, setProjectId],
  );

  return (
    <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
  );
}

export function useTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) {
    throw new Error('useTenant must be used inside <TenantProvider>');
  }
  return ctx;
}
