'use client';

/**
 * Client-side providers wrapper
 */

import { ReactNode, useState, useCallback, useRef } from 'react';
import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query';
import { ToastProvider, useToast } from '@/components/ui/toast';
import { ThemeProvider } from '@/components/theme-provider';
import { CommandPalette } from '@/components/command-palette';
import { ErrorBoundary } from '@/components/ui/error-boundary';
import { OfflineIndicator } from '@/components/ui/offline-indicator';
import { getErrorMessage } from '@/hooks/use-mutation-error';

/**
 * Extract error title based on error type
 */
function getErrorTitle(error: unknown): string {
  if (error instanceof Error) {
    if (error.message === 'Failed to fetch' || error.message.includes('NetworkError')) {
      return 'Connection Error';
    }
    if (error.name === 'AbortError') {
      return 'Request Timeout';
    }
    // Check for specific HTTP status codes in the message
    if (error.message.includes('401') || error.message.includes('Unauthorized')) {
      return 'Authentication Required';
    }
    if (error.message.includes('403') || error.message.includes('Forbidden')) {
      return 'Permission Denied';
    }
    if (error.message.includes('404') || error.message.includes('Not Found')) {
      return 'Not Found';
    }
    if (error.message.includes('500') || error.message.includes('Server Error')) {
      return 'Server Error';
    }
  }
  return 'Error';
}

/**
 * Create query client with error handling
 */
function createQueryClient(showToast: (title: string, message: string) => void) {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 1000, // 5 seconds
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Don't retry on 4xx errors (client errors)
          if (error instanceof Error) {
            const message = error.message.toLowerCase();
            if (message.includes('400') || message.includes('401') ||
                message.includes('403') || message.includes('404') ||
                message.includes('422') || message.includes('429')) {
              return false;
            }
          }
          // Retry up to 3 times for other errors
          return failureCount < 3;
        },
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      },
      mutations: {
        retry: false, // Don't retry mutations by default
      },
    },
    queryCache: new QueryCache({
      onError: (error, query) => {
        // Only show error toast for queries that had data (not initial loads)
        // This prevents showing errors for expected 404s on initial load
        if (query.state.data !== undefined) {
          const title = getErrorTitle(error);
          const message = getErrorMessage(error);
          console.error('[Query Error]', title, message, error);
          showToast(title, message);
        }
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        // Show toast for all mutation errors
        const title = getErrorTitle(error);
        const message = getErrorMessage(error);
        console.error('[Mutation Error]', title, message, error);
        showToast(title, message);
      },
    }),
  });
}

/**
 * Wrapper that creates QueryClient with toast access
 */
function QueryClientWrapper({ children }: { children: ReactNode }) {
  const toast = useToast();
  const toastRef = useRef(toast);
  toastRef.current = toast;

  // Create a stable showToast function
  const showToast = useCallback((title: string, message: string) => {
    toastRef.current.error(title, message);
  }, []);

  const [queryClient] = useState(() => createQueryClient(showToast));

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <QueryClientWrapper>
          <OfflineIndicator />
          <ErrorBoundary showDetails={process.env.NODE_ENV === 'development'}>
            {children}
          </ErrorBoundary>
          <CommandPalette />
        </QueryClientWrapper>
      </ToastProvider>
    </ThemeProvider>
  );
}
