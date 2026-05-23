'use client';

/**
 * ResizableSplit — CB-3124 fix.
 *
 * Horizontal split with a drag handle. Left child gets the remaining
 * flex space; right child gets `rightWidthPx` (controlled). The handle
 * (3px wide) sits on the left edge of the right child and supports
 * mouse + touch + keyboard (←/→ when focused).
 *
 * Why not a third-party lib: Studio already has zustand persistence
 * + dark/light theming + a11y constraints. Inline implementation is
 * 80 LOC, zero deps, and re-uses studio-state-v2 for persistence.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

interface ResizableSplitProps {
  left: React.ReactNode;
  right: React.ReactNode;
  /** Initial / persisted right-pane width in px. Falls back to default. */
  rightWidthPx: number;
  onResize: (px: number) => void;
  minRightPx?: number;
  maxRightPx?: number;
  className?: string;
}

export function ResizableSplit({
  left,
  right,
  rightWidthPx,
  onResize,
  minRightPx = 280,
  maxRightPx = 1000,
  className,
}: ResizableSplitProps) {
  const [dragging, setDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<{ clientX: number; startWidth: number } | null>(null);

  // Clamp the maximum to the container width so the divider can never go
  // off-screen on narrow viewports.
  const maxAvailable = useCallback(() => {
    const containerW = containerRef.current?.offsetWidth ?? Infinity;
    return Math.min(maxRightPx, Math.max(minRightPx + 200, containerW - 320));
  }, [maxRightPx, minRightPx]);

  const beginDrag = useCallback((clientX: number) => {
    startRef.current = { clientX, startWidth: rightWidthPx };
    setDragging(true);
  }, [rightWidthPx]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    beginDrag(e.clientX);
  }, [beginDrag]);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 0) return;
    beginDrag(e.touches[0].clientX);
  }, [beginDrag]);

  useEffect(() => {
    if (!dragging) return;
    const move = (clientX: number) => {
      const start = startRef.current;
      if (!start) return;
      const delta = start.clientX - clientX; // drag left = larger right pane
      const next = Math.min(maxAvailable(), Math.max(minRightPx, start.startWidth + delta));
      onResize(next);
    };
    const onMove = (e: MouseEvent) => move(e.clientX);
    const onUp = () => { setDragging(false); startRef.current = null; };
    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length > 0) move(e.touches[0].clientX);
    };
    const onTouchEnd = () => { setDragging(false); startRef.current = null; };
    // H2 (react-specialist review): touchmove options object MUST be
    // identical at add + remove so the listener can be canceled.
    const TOUCH_MOVE_OPTS: AddEventListenerOptions = { passive: true };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchmove', onTouchMove, TOUCH_MOVE_OPTS);
    window.addEventListener('touchend', onTouchEnd);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('touchmove', onTouchMove, TOUCH_MOVE_OPTS);
      window.removeEventListener('touchend', onTouchEnd);
    };
  }, [dragging, minRightPx, maxAvailable, onResize]);

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const step = e.shiftKey ? 64 : 16;
    const delta = e.key === 'ArrowLeft' ? +step : -step;
    onResize(Math.min(maxAvailable(), Math.max(minRightPx, rightWidthPx + delta)));
  }, [rightWidthPx, minRightPx, maxAvailable, onResize]);

  return (
    <div
      ref={containerRef}
      className={cn('flex flex-row min-h-0 min-w-0 w-full h-full', className)}
    >
      <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">{left}</div>

      {/* Drag handle — 3px wide rail with a 7px hit-box overlay */}
      <div className="relative flex-shrink-0">
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize investigation panel"
          // CRITICAL C1 (react-specialist review): focusable separator
          // requires aria-valuenow/min/max + aria-valuetext per ARIA 1.2.
          aria-valuenow={rightWidthPx}
          aria-valuemin={minRightPx}
          aria-valuemax={maxRightPx}
          aria-valuetext={`Investigation panel ${rightWidthPx} pixels wide`}
          tabIndex={0}
          onMouseDown={onMouseDown}
          onTouchStart={onTouchStart}
          onKeyDown={onKeyDown}
          className={cn(
            'absolute left-[-3px] top-0 bottom-0 w-[7px] cursor-col-resize z-10',
            // CRITICAL C2: focus-visible ring instead of focus:outline-none.
            'group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 focus-visible:ring-offset-1',
          )}
        >
          <div className={cn(
            'absolute left-[2px] top-0 bottom-0 w-[3px] transition-colors',
            dragging
              ? 'bg-cyan-500 dark:bg-cyan-400'
              : 'bg-zinc-200 dark:bg-zinc-800 group-hover:bg-cyan-400 group-focus-visible:bg-cyan-400',
          )} />
        </div>
      </div>

      <div
        style={{ width: rightWidthPx, minWidth: rightWidthPx }}
        className="flex flex-col min-h-0 overflow-hidden"
      >
        {right}
      </div>
    </div>
  );
}
