/**
 * Shared markdown rendering presets for CodeBoard components.
 *
 * Centralised here so ImplementationTab, FeatureDocumentationView, and any
 * future markdown-rendering component all use the same locked-in URL transform
 * and link policy without duplicating the constants.
 */

import { defaultUrlTransform } from 'react-markdown';
import type React from 'react';

/**
 * Tailwind prose classes applied to all ReactMarkdown output in CodeBoard.
 * prose-invert targets the dark background; colour overrides pin specific
 * token colours to match the zinc/cyan palette.
 */
export const PROSE_CLASSES =
  'prose prose-sm prose-invert max-w-none ' +
  'prose-headings:text-zinc-200 prose-p:text-zinc-300 ' +
  'prose-a:text-cyan-400 prose-strong:text-zinc-200 ' +
  'prose-code:text-cyan-400 prose-code:bg-zinc-800 ' +
  'prose-code:px-1 prose-code:py-0.5 prose-code:rounded ' +
  'prose-pre:bg-zinc-800 prose-pre:border prose-pre:border-zinc-700 ' +
  'prose-blockquote:border-l-cyan-500 prose-blockquote:text-zinc-400 ' +
  'prose-li:text-zinc-300';

/**
 * Locked-in explicit URL transform so future react-markdown upgrades cannot
 * silently widen the URL surface.  defaultUrlTransform strips javascript:,
 * vbscript:, and data: protocols.
 */
export const SAFE_URL_TRANSFORM = defaultUrlTransform;

/**
 * Link override: all rendered markdown links open in a new tab with a full
 * noopener + noreferrer + nofollow rel triple to prevent tab-napping and
 * suppress referrer leakage.
 *
 * NOTE: rehype-raw and remark-gfm are intentionally excluded from all
 * ReactMarkdown usages across CodeBoard per the security audit decision.
 */
export const MARKDOWN_LINK_COMPONENTS = {
  a: ({
    href,
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a {...props} href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  ),
};
