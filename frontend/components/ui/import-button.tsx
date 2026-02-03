'use client';

/**
 * ImportButton Component
 * A button that navigates to the import page or triggers import functionality
 */

import { useRouter } from 'next/navigation';
import { FolderInput } from 'lucide-react';
import { Button, type ButtonProps } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface ImportButtonProps extends Omit<ButtonProps, 'children'> {
  showLabel?: boolean;
  label?: string;
}

export function ImportButton({
  showLabel = true,
  label = 'Import',
  variant = 'outline',
  size = 'default',
  className,
  onClick,
  ...props
}: ImportButtonProps) {
  const router = useRouter();

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (onClick) {
      onClick(e);
    } else {
      router.push('/import');
    }
  };

  return (
    <Button
      variant={variant}
      size={showLabel ? size : 'icon'}
      className={cn(className)}
      onClick={handleClick}
      {...props}
    >
      <FolderInput className="h-4 w-4" />
      {showLabel && <span>{label}</span>}
    </Button>
  );
}
