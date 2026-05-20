'use client';

/**
 * TenantContext — workspaceId + tenantId for the current workspace session.
 *
 * Phase 1: single-tenant. tenantId is always "default". workspaceId comes
 * from the [id] route param.
 *
 * Phase 2: tenantId will be derived from the JWT claims injected by the
 * FastAPI InternalAuthDep. The context shape stays the same; only the
 * source of tenantId changes.
 *
 * Usage:
 *   const { workspaceId, tenantId } = useTenant();
 */

import React, {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from 'react';

export interface TenantContextValue {
  /** The active workspace ID (from URL param [id]). */
  workspaceId: string;
  /** Phase 1 default tenant. Phase 2: derived from JWT. */
  tenantId: string;
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
  const value = useMemo<TenantContextValue>(
    () => ({ workspaceId, tenantId }),
    [workspaceId, tenantId],
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
