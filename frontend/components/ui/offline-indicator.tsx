'use client';

/**
 * Offline Indicator Component
 * Shows a banner when the user is offline or has just reconnected
 */

import { useOnlineStatus } from '@/hooks/use-online-status';
import { WifiOff, Wifi } from 'lucide-react';
import { cn } from '@/lib/utils';

interface OfflineIndicatorProps {
  className?: string;
}

export function OfflineIndicator({ className }: OfflineIndicatorProps) {
  const { isOffline, wasOffline, isOnline } = useOnlineStatus();

  // Show nothing if online and wasn't recently offline
  if (isOnline && !wasOffline) {
    return null;
  }

  // Show reconnected message briefly
  if (isOnline && wasOffline) {
    return (
      <div
        className={cn(
          'fixed top-0 left-0 right-0 z-[100] flex items-center justify-center gap-2 py-2 px-4',
          'bg-green-600/90 text-white text-sm backdrop-blur-sm',
          'animate-in slide-in-from-top duration-300',
          className
        )}
      >
        <Wifi className="w-4 h-4" />
        <span>You're back online</span>
      </div>
    );
  }

  // Show offline banner
  return (
    <div
      className={cn(
        'fixed top-0 left-0 right-0 z-[100] flex items-center justify-center gap-2 py-2 px-4',
        'bg-amber-600/90 text-white text-sm backdrop-blur-sm',
        'animate-in slide-in-from-top duration-300',
        className
      )}
    >
      <WifiOff className="w-4 h-4" />
      <span>You're offline. Some features may not be available.</span>
    </div>
  );
}
