'use client';

/**
 * Error Boundary Component
 * Catches JavaScript errors in child components and displays a fallback UI
 */

import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw, Home, Bug } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  showDetails?: boolean;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });

    // Log error to console
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Call custom error handler if provided
    this.props.onError?.(error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      return (
        <ErrorFallback
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          onReset={this.handleReset}
          onReload={this.handleReload}
          onGoHome={this.handleGoHome}
          showDetails={this.props.showDetails}
        />
      );
    }

    return this.props.children;
  }
}

/**
 * Default Error Fallback Component
 */
interface ErrorFallbackProps {
  error: Error | null;
  errorInfo?: ErrorInfo | null;
  onReset?: () => void;
  onReload?: () => void;
  onGoHome?: () => void;
  showDetails?: boolean;
  className?: string;
}

export function ErrorFallback({
  error,
  errorInfo,
  onReset,
  onReload,
  onGoHome,
  showDetails = false,
  className,
}: ErrorFallbackProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center min-h-[400px] p-8 text-center',
        className
      )}
    >
      <div className="max-w-md">
        {/* Icon */}
        <div className="flex justify-center mb-6">
          <div className="p-4 bg-red-500/10 rounded-full">
            <AlertCircle className="w-12 h-12 text-red-400" />
          </div>
        </div>

        {/* Title */}
        <h2 className="text-xl font-semibold text-white mb-2">
          Something went wrong
        </h2>

        {/* Error message */}
        <p className="text-zinc-400 mb-6">
          {error?.message || 'An unexpected error occurred. Please try again.'}
        </p>

        {/* Actions */}
        <div className="flex flex-wrap gap-3 justify-center mb-6">
          {onReset && (
            <button
              onClick={onReset}
              className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Try Again
            </button>
          )}
          {onReload && (
            <button
              onClick={onReload}
              className="flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Reload Page
            </button>
          )}
          {onGoHome && (
            <button
              onClick={onGoHome}
              className="flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors"
            >
              <Home className="w-4 h-4" />
              Go Home
            </button>
          )}
        </div>

        {/* Error details (collapsible) */}
        {showDetails && error && (
          <details className="text-left bg-zinc-800/50 rounded-lg p-4 mt-4">
            <summary className="flex items-center gap-2 cursor-pointer text-sm text-zinc-400 hover:text-zinc-300">
              <Bug className="w-4 h-4" />
              Error Details
            </summary>
            <div className="mt-3 space-y-2">
              <div>
                <p className="text-xs text-zinc-500">Error Name:</p>
                <p className="text-sm text-red-400 font-mono">{error.name}</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Error Message:</p>
                <p className="text-sm text-zinc-300 font-mono break-words">
                  {error.message}
                </p>
              </div>
              {error.stack && (
                <div>
                  <p className="text-xs text-zinc-500">Stack Trace:</p>
                  <pre className="text-xs text-zinc-400 font-mono overflow-x-auto whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {error.stack}
                  </pre>
                </div>
              )}
              {errorInfo?.componentStack && (
                <div>
                  <p className="text-xs text-zinc-500">Component Stack:</p>
                  <pre className="text-xs text-zinc-400 font-mono overflow-x-auto whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {errorInfo.componentStack}
                  </pre>
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

/**
 * Inline Error Display Component
 * For smaller, inline error states
 */
interface InlineErrorProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function InlineError({ message, onRetry, className }: InlineErrorProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-lg',
        className
      )}
    >
      <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
      <p className="text-sm text-red-300 flex-1">
        {message || 'Something went wrong'}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-1 px-3 py-1 text-sm bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * API Error Display Component
 * For displaying API/network errors with more context
 */
interface APIErrorProps {
  error: Error | null;
  statusCode?: number;
  onRetry?: () => void;
  className?: string;
}

export function APIError({ error, statusCode, onRetry, className }: APIErrorProps) {
  const getStatusMessage = (code: number) => {
    switch (code) {
      case 400:
        return 'Bad Request - The server could not understand the request.';
      case 401:
        return 'Unauthorized - Please log in to continue.';
      case 403:
        return 'Forbidden - You do not have permission to access this resource.';
      case 404:
        return 'Not Found - The requested resource could not be found.';
      case 429:
        return 'Too Many Requests - Please wait a moment and try again.';
      case 500:
        return 'Server Error - Something went wrong on our end.';
      case 502:
        return 'Bad Gateway - The server is temporarily unavailable.';
      case 503:
        return 'Service Unavailable - The server is temporarily unavailable.';
      default:
        return error?.message || 'An unexpected error occurred.';
    }
  };

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-8 text-center',
        className
      )}
    >
      <div className="p-3 bg-red-500/10 rounded-full mb-4">
        <AlertCircle className="w-8 h-8 text-red-400" />
      </div>

      {statusCode && (
        <p className="text-3xl font-bold text-zinc-400 mb-2">{statusCode}</p>
      )}

      <p className="text-zinc-300 mb-4 max-w-md">
        {statusCode ? getStatusMessage(statusCode) : error?.message || 'An error occurred'}
      </p>

      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Try Again
        </button>
      )}
    </div>
  );
}

/**
 * Connection Error Component
 * For network/connection issues
 */
interface ConnectionErrorProps {
  onRetry?: () => void;
  className?: string;
}

export function ConnectionError({ onRetry, className }: ConnectionErrorProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-8 text-center',
        className
      )}
    >
      <div className="p-3 bg-yellow-500/10 rounded-full mb-4">
        <AlertCircle className="w-8 h-8 text-yellow-400" />
      </div>

      <h3 className="text-lg font-semibold text-white mb-2">
        Connection Problem
      </h3>

      <p className="text-zinc-400 mb-4 max-w-md">
        Unable to connect to the server. Please check your internet connection and try again.
      </p>

      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Retry Connection
        </button>
      )}
    </div>
  );
}
