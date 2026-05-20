'use client';

/**
 * WorkspaceTenantLayout — client component that wraps all workspace views.
 *
 * Responsibilities:
 * 1. Read the [id] param via useParams()
 * 2. Provide TenantContext to the entire subtree
 * 3. Render WorkspaceTopBar (switcher + tabs) above all child routes
 *
 * Phase 1: tenantId = "default" (single tenant).
 */

import { useParams } from 'next/navigation';
import { type ReactNode } from 'react';
import { TenantProvider } from '@/contexts/TenantContext';
import { WorkspaceTopBar } from '@/components/workspace/WorkspaceTopBar';

interface WorkspaceLayoutProps {
  children: ReactNode;
}

export default function WorkspaceTenantLayout({ children }: WorkspaceLayoutProps) {
  const params = useParams();
  const workspaceId = (params.id as string) || 'default';

  return (
    <TenantProvider workspaceId={workspaceId} tenantId="default">
      <div className="flex flex-col h-full min-h-0">
        <WorkspaceTopBar workspaceId={workspaceId} />
        <div className="flex-1 min-h-0 overflow-hidden">
          {children}
        </div>
      </div>
    </TenantProvider>
  );
}
