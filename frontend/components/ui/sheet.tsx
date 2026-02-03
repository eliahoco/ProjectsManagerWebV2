'use client';

/**
 * Sheet Component - Slide-over panel
 * Based on shadcn/ui patterns
 */

import * as React from 'react';
import { cn } from '@/lib/utils';
import { X } from 'lucide-react';

interface SheetContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const SheetContext = React.createContext<SheetContextValue | undefined>(undefined);

function useSheetContext() {
  const context = React.useContext(SheetContext);
  if (!context) {
    throw new Error('Sheet components must be used within a Sheet');
  }
  return context;
}

interface SheetProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

function Sheet({ open = false, onOpenChange, children }: SheetProps) {
  const handleOpenChange = React.useCallback((newOpen: boolean) => {
    onOpenChange?.(newOpen);
  }, [onOpenChange]);

  return (
    <SheetContext.Provider value={{ open, onOpenChange: handleOpenChange }}>
      {children}
    </SheetContext.Provider>
  );
}

interface SheetContentProps extends React.HTMLAttributes<HTMLDivElement> {
  side?: 'top' | 'right' | 'bottom' | 'left';
}

function SheetContent({
  side = 'right',
  className,
  children,
  ...props
}: SheetContentProps) {
  const { open, onOpenChange } = useSheetContext();

  // Handle escape key
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onOpenChange(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onOpenChange]);

  // Prevent body scroll when open
  React.useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  if (!open) return null;

  const sideStyles = {
    top: 'inset-x-0 top-0 border-b',
    right: 'inset-y-0 right-0 h-full border-l',
    bottom: 'inset-x-0 bottom-0 border-t',
    left: 'inset-y-0 left-0 h-full border-r',
  };

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />
      {/* Panel */}
      <div
        className={cn(
          'fixed bg-zinc-900 border-zinc-800 shadow-lg transition-transform duration-300',
          sideStyles[side],
          className
        )}
        {...props}
      >
        {children}
      </div>
    </div>
  );
}

interface SheetHeaderProps extends React.HTMLAttributes<HTMLDivElement> {}

function SheetHeader({ className, ...props }: SheetHeaderProps) {
  return (
    <div
      className={cn('flex flex-col space-y-2 p-6', className)}
      {...props}
    />
  );
}

interface SheetTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {}

function SheetTitle({ className, ...props }: SheetTitleProps) {
  return (
    <h2
      className={cn('text-lg font-semibold text-zinc-100', className)}
      {...props}
    />
  );
}

interface SheetDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {}

function SheetDescription({ className, ...props }: SheetDescriptionProps) {
  return (
    <p
      className={cn('text-sm text-zinc-400', className)}
      {...props}
    />
  );
}

interface SheetCloseProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

function SheetClose({ className, children, ...props }: SheetCloseProps) {
  const { onOpenChange } = useSheetContext();

  return (
    <button
      type="button"
      className={cn(
        'absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none',
        className
      )}
      onClick={() => onOpenChange(false)}
      {...props}
    >
      {children || <X className="h-4 w-4" />}
      <span className="sr-only">Close</span>
    </button>
  );
}

export {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetClose,
};
