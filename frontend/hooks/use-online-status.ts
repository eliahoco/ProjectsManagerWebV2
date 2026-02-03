'use client';

/**
 * Custom hook for detecting online/offline status
 * Provides real-time network status updates
 */

import { useState, useEffect, useCallback } from 'react';

interface OnlineStatus {
  isOnline: boolean;
  isOffline: boolean;
  wasOffline: boolean;
}

/**
 * Hook to detect online/offline status
 * @returns Object with isOnline, isOffline, and wasOffline flags
 */
export function useOnlineStatus(): OnlineStatus {
  const [isOnline, setIsOnline] = useState(true);
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    // Initialize with actual status (only runs in browser)
    if (typeof navigator !== 'undefined') {
      setIsOnline(navigator.onLine);
    }

    const handleOnline = () => {
      setIsOnline(true);
      // Keep wasOffline true for a short period to allow UI to show "reconnected" message
      setTimeout(() => {
        setWasOffline(false);
      }, 3000);
    };

    const handleOffline = () => {
      setIsOnline(false);
      setWasOffline(true);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return {
    isOnline,
    isOffline: !isOnline,
    wasOffline,
  };
}

/**
 * Hook to check if a fetch error is likely a network issue
 */
export function useNetworkErrorCheck() {
  const { isOnline } = useOnlineStatus();

  const isNetworkError = useCallback((error: unknown): boolean => {
    if (!isOnline) return true;

    if (error instanceof Error) {
      return (
        error.message === 'Failed to fetch' ||
        error.message.includes('NetworkError') ||
        error.message.includes('network') ||
        error.name === 'AbortError'
      );
    }

    return false;
  }, [isOnline]);

  return { isNetworkError };
}
