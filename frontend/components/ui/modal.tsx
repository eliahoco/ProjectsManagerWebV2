'use client';

/**
 * Modal — accessible dialog primitive (CB-2731).
 *
 * Solves the a11y gaps surfaced by the code-reviewer audit on CB-2378's
 * portal fix (settings/documentation `ConfirmDialog`):
 *
 *   - Focus trap: Tab/Shift-Tab cycle inside the dialog, never escape into
 *     the background page.
 *   - Initial focus: first focusable element inside the dialog gets focus
 *     on open. A node carrying `data-autofocus` overrides this so callers
 *     can land focus on the safe action (e.g. "Cancel") instead of the
 *     destructive primary.
 *   - Restore focus: on close, focus returns to whichever element opened
 *     the dialog — keyboard users don't lose their place in the page.
 *   - Escape: closes the dialog (suppressed when `isPending` so a long
 *     mutation isn't dismissed mid-flight).
 *   - Body scroll lock: `overflow:hidden` on `<body>` while open so the
 *     background page does not scroll behind the backdrop. Refcounted so
 *     stacked modals don't unlock prematurely.
 *   - Backdrop click: closes by default (override with
 *     `closeOnBackdropClick={false}` for destructive flows).
 *   - aria-labelledby: heading id is owned by the primitive and wired
 *     into the dialog automatically.
 *   - Portal: rendered into `document.body` so the dialog is never a DOM
 *     child of `<tbody>` (CB-2378 hydration warning).
 *
 * Stays homegrown — no `react-focus-lock` dependency. The trap is a
 * single keydown handler that finds the focusable boundary and wraps
 * Tab. That keeps the bundle small and the behavior debuggable.
 */

import { useCallback, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

interface ModalProps {
  /** Whether the modal is open. Caller controls. */
  isOpen: boolean;
  /** Close handler — invoked by Escape, backdrop click, and the X button. */
  onClose: () => void;
  /** Title rendered as the visible heading and wired up to `aria-labelledby`. */
  title: React.ReactNode;
  /**
   * Optional icon rendered to the left of the title (e.g. an
   * `<AlertCircle />`). Aligned to the top of the heading row.
   */
  icon?: React.ReactNode;
  /**
   * Optional description rendered under the title. Use for the dialog's
   * primary message when it is short enough to live in the header.
   */
  description?: React.ReactNode;
  /**
   * Modal body content. Rendered below the heading row. Use this for the
   * action footer (Cancel / Confirm), input fields, or longer copy.
   */
  children?: React.ReactNode;
  /**
   * When true, suppresses Escape and backdrop close. The X button (if
   * the caller renders one) should also be disabled.
   * Used to prevent dismissing while a mutation is in flight.
   */
  isPending?: boolean;
  /** When false, clicking the backdrop does NOT close the modal. Default true. */
  closeOnBackdropClick?: boolean;
  /** Extra class for the inner card. Defaults to a max-w-sm card. */
  className?: string;
  /**
   * Optional data-testid for the dialog root — eases targeting in tests
   * without relying on the heading text.
   */
  testId?: string;
}

// Selector for focusable elements inside the dialog. Mirrors the WAI-ARIA
// "tabbable" set; explicitly excludes elements with a negative tabIndex
// because they are programmatically focusable but not part of the tab
// cycle. `[data-autofocus]` is matched too so a caller-provided initial
// focus target wins even if it's not first in DOM order.
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(',');

// Module-level refcount for body scroll lock + the original `body.style.overflow`
// snapshot taken on the FIRST lock. Lives outside the component so React
// StrictMode's dev-only double-invoke (mount → cleanup → mount) doesn't
// snapshot an already-`hidden` overflow as the "previous" value and lose
// the original. Dataset-based refcount also tripped on this; refs don't.
let bodyLockCount = 0;
let bodyLockPrevOverflow: string | null = null;

function getFocusable(root: HTMLElement): HTMLElement[] {
  // Tailwind's `hidden` utility (and the bare `hidden` attribute) drop the
  // node from the visible tree but leave it in the DOM, so it must NOT be
  // part of the tab cycle. `aria-hidden="true"` likewise. In a real
  // browser we additionally screen out `visibility: hidden` and
  // `display: none` via getComputedStyle; jsdom returns empty strings
  // there so the test environment falls through cleanly without
  // mis-filtering visible focusables.
  const hasComputedStyle = typeof window !== 'undefined' && typeof window.getComputedStyle === 'function';
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((el) => {
    if (el.hasAttribute('hidden')) return false;
    if (el.closest('[hidden]')) return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    if (hasComputedStyle) {
      const style = window.getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') return false;
    }
    return true;
  });
}

export function Modal({
  isOpen,
  onClose,
  title,
  icon,
  description,
  children,
  isPending = false,
  closeOnBackdropClick = true,
  className,
  testId,
}: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  // Element that had focus when the dialog opened — focus returns here
  // on close so keyboard users don't lose their place. Captured once per
  // open transition.
  const previousFocusRef = useRef<HTMLElement | null>(null);
  // Pending state mirrored in a ref so the keydown handler reads the
  // latest value without the listener tearing down + rebuilding on every
  // pending flip (which would race with an in-flight Escape press).
  const isPendingRef = useRef(isPending);
  useEffect(() => {
    isPendingRef.current = isPending;
  }, [isPending]);

  // Capture the opener and restore it on close. Run only on the open-edge
  // transition so that re-renders mid-open don't reset the captured node.
  useEffect(() => {
    if (!isOpen) return;
    previousFocusRef.current = document.activeElement as HTMLElement | null;
    return () => {
      // Only refocus a still-connected node — the opener may have
      // unmounted while the modal was open (e.g. row removed by a list
      // refetch). focus() on a detached node is a no-op but logs noise
      // in some browsers, so check first.
      const prev = previousFocusRef.current;
      if (prev && document.body.contains(prev)) {
        prev.focus();
      }
    };
  }, [isOpen]);

  // Initial focus. Prefer a node tagged `data-autofocus` so callers can
  // land focus on the safe action (e.g. Cancel) instead of the
  // destructive primary. Falls back to the first focusable element, then
  // to the dialog itself (so screen readers still announce the title and
  // Tab cycles into the dialog from the first focusable child).
  useEffect(() => {
    if (!isOpen) return;
    const root = dialogRef.current;
    if (!root) return;
    // requestAnimationFrame defers past the DOM commit so layout-deferred
    // children (portals-within-portals, conditionally-rendered buttons)
    // are mounted before we look for focusables.
    const handle = requestAnimationFrame(() => {
      // The component may unmount between rAF schedule and fire (route
      // change, parent close). focus() on a detached node is a no-op
      // but logs noise in some browsers — bail if we're not connected.
      if (!root.isConnected) return;
      const explicit = root.querySelector<HTMLElement>('[data-autofocus]');
      if (explicit) {
        explicit.focus();
        return;
      }
      const focusables = getFocusable(root);
      if (focusables.length > 0) {
        focusables[0].focus();
        return;
      }
      // No focusable child — focus the dialog wrapper itself so SR
      // announces the heading. tabIndex=-1 keeps it out of the cycle.
      root.focus();
    });
    return () => cancelAnimationFrame(handle);
  }, [isOpen]);

  // Body scroll lock with module-level refcount. Stacked modals share a
  // single body lock — only the outermost active modal owns the unlock,
  // which prevents an inner unmount from restoring scroll while the
  // outer is still open. Refcount lives on a module-level let (not
  // document.body.dataset) so React StrictMode's dev-only double-invoke
  // (mount → cleanup → mount) cannot snapshot an already-`hidden`
  // overflow as the "previous" value and lose the original. The snapshot
  // is taken exactly once, on the first lock, and only restored when the
  // count returns to zero.
  useEffect(() => {
    if (!isOpen) return;
    if (bodyLockCount === 0) {
      bodyLockPrevOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    bodyLockCount += 1;
    return () => {
      bodyLockCount = Math.max(0, bodyLockCount - 1);
      if (bodyLockCount === 0) {
        document.body.style.overflow = bodyLockPrevOverflow ?? '';
        bodyLockPrevOverflow = null;
      }
    };
  }, [isOpen]);

  // Keyboard handling: Escape closes (unless pending), Tab traps focus
  // inside the dialog. Listen on the document in the CAPTURE phase so a
  // descendant component (custom select, code editor, popover) calling
  // `e.stopPropagation()` on keydown can't swallow Escape/Tab and break
  // the trap. stopPropagation on Escape (line below) still keeps a single
  // Escape from bubbling out and dismissing a parent modal too.
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      const root = dialogRef.current;
      if (!root) return;

      if (e.key === 'Escape') {
        if (isPendingRef.current) return;
        e.stopPropagation();
        onClose();
        return;
      }

      if (e.key !== 'Tab') return;

      // Focus trap. Recompute focusables on every Tab — children
      // (selects open, inputs disable while submitting) change the cycle
      // mid-session, and a snapshot at mount would go stale.
      const focusables = getFocusable(root);
      if (focusables.length === 0) {
        e.preventDefault();
        root.focus();
        return;
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;

      // If focus has somehow escaped the dialog (e.g. user tabbed before
      // initial-focus rAF settled), pull it back to the boundary.
      if (!active || !root.contains(active)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
        return;
      }

      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKey, true);
    return () => document.removeEventListener('keydown', handleKey, true);
  }, [isOpen, onClose]);

  const handleBackdropMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!closeOnBackdropClick) return;
      if (isPendingRef.current) return;
      // Only fire on direct backdrop hits — clicks that bubble up from
      // the inner card must NOT close the modal. The check uses
      // `e.target === e.currentTarget` rather than a class probe so a
      // restyled card won't accidentally pass through.
      if (e.target !== e.currentTarget) return;
      onClose();
    },
    [closeOnBackdropClick, onClose],
  );

  if (!isOpen) return null;
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      // Backdrop. Mouse-down rather than click so a drag that started on
      // the inner card and ended on the backdrop (text selection) does
      // NOT close the modal. The dialog itself is the inner card; this
      // outer wrapper acts as both a centring container and the click
      // target.
      onMouseDown={handleBackdropMouseDown}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      data-testid={testId ? `${testId}-backdrop` : undefined}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        // tabIndex=-1 lets us programmatically focus the wrapper (for the
        // no-focusable-child fallback) without putting it in the Tab
        // cycle. Without this, focus() on a non-tabbable div is a no-op.
        tabIndex={-1}
        data-testid={testId}
        className={cn(
          'relative bg-zinc-900 border border-zinc-700 rounded-xl shadow-xl mx-4 outline-none',
          className ?? 'w-full max-w-sm p-6',
        )}
      >
        {(icon || title || description) && (
          <div className="flex items-start gap-3 mb-4">
            {icon && <div className="flex-shrink-0 mt-0.5">{icon}</div>}
            <div className="min-w-0">
              <h2 id={titleId} className="text-white font-semibold">
                {title}
              </h2>
              {description && (
                <div className="text-sm text-zinc-400 mt-1">{description}</div>
              )}
            </div>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body,
  );
}

export default Modal;
