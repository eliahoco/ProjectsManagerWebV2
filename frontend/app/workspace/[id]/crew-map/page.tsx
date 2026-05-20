'use client';

/**
 * Crew Map page — /workspace/[id]/crew-map
 *
 * Deferred per MVP slice. Placeholder shown until Phase D.
 * Backend tables land for forward compatibility but the UI is a stub.
 */

import { GitBranch } from 'lucide-react';

export default function CrewMapPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 bg-zinc-950 p-8">
      <div className="w-14 h-14 rounded-2xl bg-zinc-800 flex items-center justify-center">
        <GitBranch className="w-7 h-7 text-zinc-500" />
      </div>
      <div className="text-center max-w-sm">
        <h2 className="text-zinc-300 font-semibold text-lg mb-2">Crew Map</h2>
        <p className="text-zinc-500 text-sm">
          The Crew Map visualizes agent assignments, skill usage, and project
          relationships. Coming in Phase D once agent assignment data is available.
        </p>
        <p className="text-zinc-600 text-xs mt-3">
          Backend schema is live — the graph will populate automatically once
          Studio conversations generate crew assignments.
        </p>
      </div>
    </div>
  );
}
