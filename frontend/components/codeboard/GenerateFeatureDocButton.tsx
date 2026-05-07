'use client';

/**
 * GenerateFeatureDocButton — CB-2062 (T2.2.3)
 *
 * Calls useGenerateFeatureDocumentation().
 * Shows "Generate Documentation" when no doc exists, "Regenerate" when it does.
 * Disabled + spinner while the mutation is in-flight.
 * Toast on success / failure via the existing useToast hook.
 */

import { Loader2, RefreshCw, Sparkles } from 'lucide-react';
import {
  useGenerateFeatureDocumentation,
  type FeatureDocumentationData,
} from '@/hooks/useCodeBoard';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';

interface GenerateFeatureDocButtonProps {
  issueId: string;
  /**
   * Project the feature belongs to. Required by the backend (CB-2117) so
   * the generate endpoint is scoped to ``(issueId, projectId)``. Pass the
   * value off the loaded issue — the button is disabled until it arrives.
   */
  projectId: string | undefined;
  existingDoc: FeatureDocumentationData | null | undefined;
  /** Optional: called after successful generation so parents can react. */
  onGenerated?: (doc: FeatureDocumentationData) => void;
  className?: string;
}

export function GenerateFeatureDocButton({
  issueId,
  projectId,
  existingDoc,
  onGenerated,
  className,
}: GenerateFeatureDocButtonProps) {
  const toast = useToast();
  const generate = useGenerateFeatureDocumentation();

  const hasDoc = !!existingDoc;
  const isPending = generate.isPending;
  const canGenerate = !!projectId && !isPending;

  async function handleClick() {
    if (!projectId) return;
    try {
      const result = await generate.mutateAsync({ issueId, projectId });
      toast.success(
        hasDoc ? 'Documentation regenerated' : 'Documentation generated',
        `Feature documentation for ${result.featureKey} is ready.`,
      );
      onGenerated?.(result);
    } catch (err) {
      toast.error(
        'Generation failed',
        err instanceof Error ? err.message : 'Failed to generate feature documentation.',
      );
    }
  }

  return (
    <Button
      variant={hasDoc ? 'outline' : 'default'}
      size="sm"
      onClick={handleClick}
      disabled={!canGenerate}
      className={className}
      aria-label={hasDoc ? 'Regenerate feature documentation' : 'Generate feature documentation'}
    >
      {isPending ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : hasDoc ? (
        <RefreshCw className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Sparkles className="h-4 w-4" aria-hidden="true" />
      )}
      {isPending
        ? hasDoc
          ? 'Regenerating…'
          : 'Generating…'
        : hasDoc
          ? 'Regenerate'
          : 'Generate Documentation'}
    </Button>
  );
}
