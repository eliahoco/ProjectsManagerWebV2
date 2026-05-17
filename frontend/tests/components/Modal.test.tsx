/**
 * CB-2731 — accessibility regression for the shared <Modal> primitive.
 *
 * The settings/documentation ConfirmDialog (CB-2378 portal fix) had four
 * a11y gaps that the audit flagged:
 *   - No focus trap (Tab escaped into the background page).
 *   - No initial focus.
 *   - No Escape handler.
 *   - No body scroll lock.
 *   - No aria-labelledby wiring the heading to the dialog.
 *
 * <Modal> is the fix; this suite locks in each acceptance bullet so a
 * future refactor can't silently regress them.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { useState } from 'react';
import { Modal } from '@/components/ui/modal';

afterEach(() => {
  // Defensive: every render uses cleanup() from the global setup, but
  // body styles aren't React-owned. Reset overflow so a leaked state
  // doesn't bleed into the next test. The module-level refcount inside
  // <Modal> resets implicitly when all modals unmount via cleanup().
  document.body.style.overflow = '';
});

function Harness({
  initialOpen = true,
  onClose,
  isPending = false,
  closeOnBackdropClick,
  withSecondaryButton = true,
}: {
  initialOpen?: boolean;
  onClose?: () => void;
  isPending?: boolean;
  closeOnBackdropClick?: boolean;
  withSecondaryButton?: boolean;
}) {
  const [open, setOpen] = useState(initialOpen);
  const handleClose = () => {
    onClose?.();
    setOpen(false);
  };
  return (
    <>
      <button data-testid="opener" onClick={() => setOpen(true)}>
        Open
      </button>
      <button data-testid="bg-button">Background button</button>
      <Modal
        isOpen={open}
        onClose={handleClose}
        title="Confirm action"
        description="Are you sure you want to proceed?"
        isPending={isPending}
        closeOnBackdropClick={closeOnBackdropClick}
        testId="test-modal"
      >
        <div className="flex justify-end gap-2">
          <button data-autofocus data-testid="cancel-btn">
            Cancel
          </button>
          {withSecondaryButton && (
            <button data-testid="confirm-btn">Confirm</button>
          )}
        </div>
      </Modal>
    </>
  );
}

describe('Modal a11y (CB-2731)', () => {
  it('exposes role="dialog" with aria-modal and aria-labelledby pointing at the title', () => {
    render(<Harness />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const labelId = dialog.getAttribute('aria-labelledby');
    expect(labelId).toBeTruthy();
    const heading = document.getElementById(labelId!);
    expect(heading).not.toBeNull();
    expect(heading).toHaveTextContent(/confirm action/i);
  });

  it('lands initial focus on the [data-autofocus] node, not the first focusable child', async () => {
    render(<Harness />);
    // requestAnimationFrame defers focus past the DOM commit; flush it.
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(undefined)));
    });
    expect(document.activeElement).toBe(screen.getByTestId('cancel-btn'));
  });

  it('locks body scroll while open and restores prior overflow on close', () => {
    document.body.style.overflow = 'auto';
    const { unmount } = render(<Harness initialOpen />);
    expect(document.body.style.overflow).toBe('hidden');
    // Full unmount drains the refcount and must restore the original
    // (`auto`) overflow — not just blank it.
    unmount();
    expect(document.body.style.overflow).toBe('auto');
  });

  it('uses capture-phase keydown so a descendant stopPropagation cannot swallow Escape', () => {
    const onClose = vi.fn();
    function GreedyChild() {
      // Mirrors a custom select / popover that calls stopPropagation on
      // every keydown. Without capture, this would block the Escape from
      // reaching the document-level handler and break the trap.
      return (
        <input
          data-testid="greedy"
          onKeyDown={(e) => e.stopPropagation()}
        />
      );
    }
    function CaptureHarness() {
      const [open, setOpen] = useState(true);
      return (
        <Modal
          isOpen={open}
          onClose={() => {
            onClose();
            setOpen(false);
          }}
          title="t"
        >
          <GreedyChild />
        </Modal>
      );
    }
    render(<CaptureHarness />);
    const greedy = screen.getByTestId('greedy');
    greedy.focus();
    fireEvent.keyDown(greedy, { key: 'Escape', bubbles: true });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT close on Escape when isPending', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} isPending />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('traps Tab forward at the last focusable element (wraps to first)', async () => {
    render(<Harness />);
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(undefined)));
    });
    const cancel = screen.getByTestId('cancel-btn');
    const confirm = screen.getByTestId('confirm-btn');
    confirm.focus();
    expect(document.activeElement).toBe(confirm);
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(cancel);
  });

  it('traps Shift+Tab backward at the first focusable element (wraps to last)', async () => {
    render(<Harness />);
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(undefined)));
    });
    const cancel = screen.getByTestId('cancel-btn');
    const confirm = screen.getByTestId('confirm-btn');
    cancel.focus();
    expect(document.activeElement).toBe(cancel);
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(confirm);
  });

  it('pulls focus back inside the dialog if it has somehow escaped', async () => {
    render(<Harness />);
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(undefined)));
    });
    const bgButton = screen.getByTestId('bg-button');
    bgButton.focus();
    expect(document.activeElement).toBe(bgButton);
    fireEvent.keyDown(document, { key: 'Tab' });
    // Forward escape recovery sends focus to the first focusable inside.
    expect(document.activeElement).toBe(screen.getByTestId('cancel-btn'));
  });

  it('closes on backdrop click by default', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const backdrop = screen.getByTestId('test-modal-backdrop');
    fireEvent.mouseDown(backdrop, { target: backdrop });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT close on backdrop click when closeOnBackdropClick is false', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} closeOnBackdropClick={false} />);
    const backdrop = screen.getByTestId('test-modal-backdrop');
    fireEvent.mouseDown(backdrop, { target: backdrop });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('does NOT close on backdrop click when isPending', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} isPending />);
    const backdrop = screen.getByTestId('test-modal-backdrop');
    fireEvent.mouseDown(backdrop, { target: backdrop });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('does NOT close when the mouseDown originates from the inner card', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const card = screen.getByTestId('test-modal');
    fireEvent.mouseDown(card);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('refcounts body scroll lock so stacked modals share a single body lock', () => {
    document.body.style.overflow = 'auto';
    function Stacked() {
      return (
        <>
          <Modal isOpen onClose={() => {}} title="Outer" testId="outer">
            <button data-testid="outer-btn">Outer</button>
          </Modal>
          <Modal isOpen onClose={() => {}} title="Inner" testId="inner">
            <button data-testid="inner-btn">Inner</button>
          </Modal>
        </>
      );
    }
    const { rerender } = render(<Stacked />);
    expect(document.body.style.overflow).toBe('hidden');
    // Close the inner only — refcount drops to 1, body still locked.
    rerender(
      <Modal isOpen onClose={() => {}} title="Outer" testId="outer">
        <button data-testid="outer-btn">Outer</button>
      </Modal>,
    );
    expect(document.body.style.overflow).toBe('hidden');
    // Close the outer — count drops to 0, prior overflow restored.
    rerender(<div />);
    expect(document.body.style.overflow).toBe('auto');
  });
});
