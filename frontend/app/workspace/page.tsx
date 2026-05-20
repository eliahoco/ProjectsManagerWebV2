/**
 * /workspace — server component redirect to default workspace.
 *
 * Phase 1: single tenant, redirects to /workspace/default/studio.
 * Phase 2: read last-visited workspace from session/cookie, redirect there.
 */

import { redirect } from 'next/navigation';

export default function WorkspacePage() {
  redirect('/workspace/default/studio');
}
