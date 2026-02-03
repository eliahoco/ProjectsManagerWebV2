'use client';

/**
 * Custom hook for handling mutation errors with toast notifications
 * Provides consistent error feedback across the application
 */

import { useCallback } from 'react';
import { useToast } from '@/components/ui/toast';
import { APIError } from './useCodeBoard';

interface MutationErrorOptions {
  /**
   * Custom title for the error toast
   */
  title?: string;
  /**
   * Context to include in error message (e.g., issue key, operation name)
   */
  context?: string;
  /**
   * Whether to show a toast (defaults to true)
   */
  showToast?: boolean;
  /**
   * Custom callback after error handling
   */
  onError?: (error: unknown) => void;
}

/**
 * Get a user-friendly error message from an error object
 */
export function getErrorMessage(error: unknown, context?: string): string {
  const prefix = context ? `${context}: ` : '';

  if (error instanceof APIError) {
    // Use the API error message directly
    return `${prefix}${error.message}`;
  }

  if (error instanceof Error) {
    // Check for network errors
    if (error.message === 'Failed to fetch' || error.message.includes('NetworkError')) {
      return `${prefix}Unable to connect to the server. Please check your connection.`;
    }

    // Check for timeout
    if (error.name === 'AbortError') {
      return `${prefix}Request timed out. Please try again.`;
    }

    return `${prefix}${error.message}`;
  }

  return `${prefix}An unexpected error occurred`;
}

/**
 * Get error title based on error type
 */
function getErrorTitle(error: unknown, customTitle?: string): string {
  if (customTitle) return customTitle;

  if (error instanceof APIError) {
    switch (error.statusCode) {
      case 400:
        return 'Invalid Request';
      case 401:
        return 'Authentication Required';
      case 403:
        return 'Permission Denied';
      case 404:
        return 'Not Found';
      case 409:
        return 'Conflict';
      case 429:
        return 'Rate Limited';
      case 500:
      case 502:
      case 503:
        return 'Server Error';
      default:
        return 'Error';
    }
  }

  if (error instanceof Error) {
    if (error.message === 'Failed to fetch' || error.message.includes('NetworkError')) {
      return 'Connection Error';
    }
    if (error.name === 'AbortError') {
      return 'Request Timeout';
    }
  }

  return 'Error';
}

/**
 * Hook for handling mutation errors with toast notifications
 */
export function useMutationError() {
  const toast = useToast();

  const handleError = useCallback((error: unknown, options: MutationErrorOptions = {}) => {
    const { title, context, showToast = true, onError } = options;

    const errorTitle = getErrorTitle(error, title);
    const errorMessage = getErrorMessage(error, context);

    // Log error for debugging
    console.error(`[Mutation Error] ${errorTitle}:`, error);

    // Show toast notification
    if (showToast) {
      toast.error(errorTitle, errorMessage);
    }

    // Call custom error handler if provided
    onError?.(error);
  }, [toast]);

  return { handleError };
}

/**
 * Create error handlers for React Query mutations
 */
export function createMutationErrorHandler(toast: ReturnType<typeof useToast>, context?: string) {
  return (error: unknown) => {
    const errorTitle = getErrorTitle(error);
    const errorMessage = getErrorMessage(error, context);

    console.error(`[Mutation Error] ${context || 'Unknown operation'}:`, error);
    toast.error(errorTitle, errorMessage);
  };
}
