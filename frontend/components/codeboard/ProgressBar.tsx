'use client';

/**
 * ProgressBar - A reusable progress bar component with multiple variants
 *
 * Features:
 * - Multiple visual variants (default, success, warning, error, gradient)
 * - Multiple sizes (sm, md, lg)
 * - Optional label with percentage display
 * - Optional count display (e.g., "5/10 items")
 * - Animated and static modes
 * - Indeterminate mode for unknown progress
 * - Accessible with ARIA attributes
 * - Configurable options for appearance and behavior
 */

import { createContext, useContext, type ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

// ============================================================================
// Progress Bar Options - Consolidated configuration interface
// ============================================================================

/**
 * ProgressBarOptions - Comprehensive configuration for progress bar appearance and behavior
 *
 * These options can be:
 * 1. Passed directly to ProgressBar component via `options` prop
 * 2. Set globally via ProgressBarOptionsProvider context
 * 3. Configured per-component to override global defaults
 */
export interface ProgressBarOptions {
  // Visual Options
  /** Show rounded corners (default: true) */
  rounded?: boolean;
  /** Border radius size when rounded - 'sm' | 'md' | 'lg' | 'full' (default: 'full') */
  roundedSize?: 'sm' | 'md' | 'lg' | 'full';
  /** Show striped pattern animation (default: false) */
  striped?: boolean;
  /** Animate stripes when striped is true (default: true) */
  stripedAnimated?: boolean;
  /** Show glow effect around the progress fill (default: false) */
  glow?: boolean;
  /** Glow intensity - 'subtle' | 'normal' | 'strong' (default: 'normal') */
  glowIntensity?: 'subtle' | 'normal' | 'strong';
  /** Show shadow under progress bar (default: false) */
  shadow?: boolean;

  // Animation Options
  /** Enable smooth transitions (default: true) */
  smoothTransition?: boolean;
  /** Transition duration in milliseconds (default: 300) */
  transitionDuration?: number;
  /** Transition easing function (default: 'ease-out') */
  transitionEasing?: 'linear' | 'ease' | 'ease-in' | 'ease-out' | 'ease-in-out';
  /** Enable bounce effect at 100% (default: false) */
  bounceOnComplete?: boolean;

  // Display Options
  /** Show value inside the progress bar (only for lg size) (default: false) */
  showValueInside?: boolean;
  /** Format for displaying percentage - 'integer' | 'decimal' (default: 'integer') */
  percentageFormat?: 'integer' | 'decimal';
  /** Decimal places when percentageFormat is 'decimal' (default: 1) */
  decimalPlaces?: number;
  /** Show track border (default: false) */
  showTrackBorder?: boolean;
  /** Track border color class (default: 'border-zinc-600') */
  trackBorderColor?: string;

  // Accessibility Options
  /** Announce progress changes to screen readers (default: true) */
  announceProgress?: boolean;
  /** Minimum change percentage to trigger announcement (default: 10) */
  announceThreshold?: number;
}

/** Default progress bar options */
export const defaultProgressBarOptions: Required<ProgressBarOptions> = {
  // Visual
  rounded: true,
  roundedSize: 'full',
  striped: false,
  stripedAnimated: true,
  glow: false,
  glowIntensity: 'normal',
  shadow: false,
  // Animation
  smoothTransition: true,
  transitionDuration: 300,
  transitionEasing: 'ease-out',
  bounceOnComplete: false,
  // Display
  showValueInside: false,
  percentageFormat: 'integer',
  decimalPlaces: 1,
  showTrackBorder: false,
  trackBorderColor: 'border-zinc-600',
  // Accessibility
  announceProgress: true,
  announceThreshold: 10,
};

// ============================================================================
// Progress Bar Options Context
// ============================================================================

const ProgressBarOptionsContext = createContext<ProgressBarOptions | null>(null);

/**
 * ProgressBarOptionsProvider - Provides global progress bar options to all child components
 *
 * @example
 * ```tsx
 * <ProgressBarOptionsProvider options={{ striped: true, glow: true }}>
 *   <ProgressBar value={50} /> // Will have striped and glow effects
 * </ProgressBarOptionsProvider>
 * ```
 */
export function ProgressBarOptionsProvider({
  options,
  children,
}: {
  options: ProgressBarOptions;
  children: ReactNode;
}) {
  return (
    <ProgressBarOptionsContext.Provider value={options}>
      {children}
    </ProgressBarOptionsContext.Provider>
  );
}

/**
 * useProgressBarOptions - Hook to access progress bar options from context
 * Merges context options with defaults
 */
export function useProgressBarOptions(localOptions?: ProgressBarOptions): Required<ProgressBarOptions> {
  const contextOptions = useContext(ProgressBarOptionsContext);
  return {
    ...defaultProgressBarOptions,
    ...contextOptions,
    ...localOptions,
  };
}

// ============================================================================
// CVA Variants
// ============================================================================

// Progress bar track variants
const progressTrackVariants = cva(
  'w-full overflow-hidden bg-zinc-700',
  {
    variants: {
      size: {
        sm: 'h-1',
        md: 'h-2',
        lg: 'h-3',
        xl: 'h-4',
      },
      rounded: {
        true: '',
        false: 'rounded-none',
      },
      roundedSize: {
        sm: 'rounded-sm',
        md: 'rounded-md',
        lg: 'rounded-lg',
        full: 'rounded-full',
      },
      shadow: {
        true: 'shadow-inner',
        false: '',
      },
    },
    defaultVariants: {
      size: 'md',
      rounded: true,
      roundedSize: 'full',
      shadow: false,
    },
  }
);

// Progress bar fill variants
const progressFillVariants = cva(
  'h-full',
  {
    variants: {
      variant: {
        default: 'bg-blue-500',
        primary: 'bg-cyan-500',
        success: 'bg-green-500',
        warning: 'bg-yellow-500',
        error: 'bg-red-500',
        purple: 'bg-purple-500',
        gradient: 'bg-gradient-to-r from-cyan-600 to-green-500',
        'gradient-blue': 'bg-gradient-to-r from-blue-600 to-blue-400',
        'gradient-purple': 'bg-gradient-to-r from-purple-600 to-purple-400',
        'gradient-success': 'bg-gradient-to-r from-green-600 to-emerald-400',
        'gradient-warning': 'bg-gradient-to-r from-yellow-600 to-orange-400',
        'gradient-error': 'bg-gradient-to-r from-red-600 to-red-400',
      },
      animated: {
        true: 'animate-pulse',
        false: '',
      },
      striped: {
        true: 'progress-bar-striped',
        false: '',
      },
      stripedAnimated: {
        true: 'progress-bar-striped-animated',
        false: '',
      },
      glow: {
        true: '',
        false: '',
      },
      glowIntensity: {
        subtle: 'shadow-[0_0_6px_rgba(var(--glow-color),0.3)]',
        normal: 'shadow-[0_0_10px_rgba(var(--glow-color),0.5)]',
        strong: 'shadow-[0_0_16px_rgba(var(--glow-color),0.7)]',
      },
    },
    defaultVariants: {
      variant: 'default',
      animated: false,
      striped: false,
      stripedAnimated: false,
      glow: false,
      glowIntensity: 'normal',
    },
  }
);

// Glow color CSS variables based on variant
const glowColors: Record<string, string> = {
  default: '59,130,246', // blue-500
  primary: '6,182,212', // cyan-500
  success: '34,197,94', // green-500
  warning: '234,179,8', // yellow-500
  error: '239,68,68', // red-500
  purple: '168,85,247', // purple-500
  gradient: '6,182,212', // cyan-500
  'gradient-blue': '59,130,246', // blue-500
  'gradient-purple': '168,85,247', // purple-500
  'gradient-success': '34,197,94', // green-500
  'gradient-warning': '234,179,8', // yellow-500
  'gradient-error': '239,68,68', // red-500
};

// Animation styles for progress bar
const progressBarStyles = `
  @keyframes progress-indeterminate {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(400%);
    }
  }

  @keyframes progress-stripe {
    0% {
      background-position: 1rem 0;
    }
    100% {
      background-position: 0 0;
    }
  }

  @keyframes progress-bounce {
    0%, 100% {
      transform: scaleX(1);
    }
    50% {
      transform: scaleX(1.02);
    }
  }

  .progress-bar-striped {
    background-image: linear-gradient(
      45deg,
      rgba(255, 255, 255, 0.15) 25%,
      transparent 25%,
      transparent 50%,
      rgba(255, 255, 255, 0.15) 50%,
      rgba(255, 255, 255, 0.15) 75%,
      transparent 75%,
      transparent
    );
    background-size: 1rem 1rem;
  }

  .progress-bar-striped-animated {
    background-image: linear-gradient(
      45deg,
      rgba(255, 255, 255, 0.15) 25%,
      transparent 25%,
      transparent 50%,
      rgba(255, 255, 255, 0.15) 50%,
      rgba(255, 255, 255, 0.15) 75%,
      transparent 75%,
      transparent
    );
    background-size: 1rem 1rem;
    animation: progress-stripe 1s linear infinite;
  }

  .progress-bar-bounce {
    animation: progress-bounce 0.3s ease-out;
  }
`;

export interface ProgressBarProps
  extends VariantProps<typeof progressTrackVariants>,
    VariantProps<typeof progressFillVariants> {
  /** Progress value from 0 to 100 */
  value: number;
  /** Maximum value (default: 100) */
  max?: number;
  /** Show percentage label */
  showPercentage?: boolean;
  /** Show count label (e.g., "5/10") */
  showCount?: boolean;
  /** Current count for count display */
  current?: number;
  /** Total count for count display */
  total?: number;
  /** Custom label */
  label?: string;
  /** Label position */
  labelPosition?: 'top' | 'right' | 'inline';
  /** Show indeterminate/loading state */
  indeterminate?: boolean;
  /** Additional class names */
  className?: string;
  /** Additional track class names */
  trackClassName?: string;
  /** Additional fill class names */
  fillClassName?: string;
  /** Accessible label */
  ariaLabel?: string;
  /** Progress bar options for appearance and behavior */
  options?: ProgressBarOptions;
}

export function ProgressBar({
  value,
  max = 100,
  variant,
  size,
  animated,
  showPercentage = false,
  showCount = false,
  current,
  total,
  label,
  labelPosition = 'top',
  indeterminate = false,
  className,
  trackClassName,
  fillClassName,
  ariaLabel,
  options: localOptions,
}: ProgressBarProps) {
  // Merge options from context and local props
  const options = useProgressBarOptions(localOptions);

  // Calculate percentage
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
  const displayPercentage = options.percentageFormat === 'decimal'
    ? percentage.toFixed(options.decimalPlaces)
    : Math.round(percentage).toString();
  const roundedPercentage = Math.round(percentage);

  // Check if at 100% for bounce animation
  const isComplete = percentage >= 100;

  // Build count string
  const countString = showCount && current !== undefined && total !== undefined
    ? `${current}/${total}`
    : null;

  // Determine if we should show any label
  const hasLabel = showPercentage || countString || label;

  // Build track classes with options
  const trackClasses = cn(
    progressTrackVariants({
      size,
      rounded: options.rounded,
      roundedSize: options.rounded ? options.roundedSize : undefined,
      shadow: options.shadow,
    }),
    options.showTrackBorder && `border ${options.trackBorderColor}`,
    trackClassName
  );

  // Build fill classes with options
  const getFillClasses = (additionalClasses?: string) => cn(
    progressFillVariants({
      variant,
      animated,
      striped: options.striped && !options.stripedAnimated,
      stripedAnimated: options.striped && options.stripedAnimated,
      glow: options.glow,
      glowIntensity: options.glow ? options.glowIntensity : undefined,
    }),
    isComplete && options.bounceOnComplete && 'progress-bar-bounce',
    additionalClasses,
    fillClassName
  );

  // Build transition style
  const getTransitionStyle = () => {
    if (!options.smoothTransition) return {};
    const easing = options.transitionEasing;
    const duration = options.transitionDuration;
    return {
      transition: `width ${duration}ms ${easing}, transform ${duration}ms ${easing}`,
    };
  };

  // Get glow color CSS variable
  const getGlowStyle = () => {
    if (!options.glow) return {};
    const variantKey = (variant || 'default') as string;
    const glowColor = glowColors[variantKey] || glowColors.default;
    return { '--glow-color': glowColor } as React.CSSProperties;
  };

  // Render label content
  const renderLabelContent = () => {
    const parts: string[] = [];
    if (label) parts.push(label);
    if (countString) parts.push(countString);
    if (showPercentage) parts.push(`${displayPercentage}%`);
    return parts.join(' · ');
  };

  // Top label layout
  if (hasLabel && labelPosition === 'top') {
    return (
      <div className={cn('space-y-1.5', className)}>
        <style>{progressBarStyles}</style>
        <div className="flex items-center justify-between text-sm">
          <span className="text-zinc-300">
            {label || (countString && `Progress: ${countString}`)}
          </span>
          {showPercentage && (
            <span className="font-medium text-zinc-200">{displayPercentage}%</span>
          )}
        </div>
        <div
          className={trackClasses}
          role="progressbar"
          aria-valuenow={indeterminate ? undefined : roundedPercentage}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={ariaLabel || label || 'Progress'}
        >
          {indeterminate ? (
            <div
              className={cn(
                progressFillVariants({ variant, animated: false }),
                'w-1/4',
                fillClassName
              )}
              style={{ animation: 'progress-indeterminate 1.5s infinite linear' }}
            />
          ) : (
            <div
              className={getFillClasses()}
              style={{
                width: `${percentage}%`,
                ...getTransitionStyle(),
                ...getGlowStyle(),
              }}
            />
          )}
        </div>
      </div>
    );
  }

  // Right label layout
  if (hasLabel && labelPosition === 'right') {
    return (
      <div className={cn('flex items-center gap-3', className)}>
        <style>{progressBarStyles}</style>
        <div
          className={cn('flex-1', trackClasses)}
          role="progressbar"
          aria-valuenow={indeterminate ? undefined : roundedPercentage}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={ariaLabel || label || 'Progress'}
        >
          {indeterminate ? (
            <div
              className={cn(
                progressFillVariants({ variant, animated: false }),
                'w-1/4',
                fillClassName
              )}
              style={{ animation: 'progress-indeterminate 1.5s infinite linear' }}
            />
          ) : (
            <div
              className={getFillClasses()}
              style={{
                width: `${percentage}%`,
                ...getTransitionStyle(),
                ...getGlowStyle(),
              }}
            />
          )}
        </div>
        <span className="text-sm font-medium text-zinc-200 shrink-0 min-w-[3rem] text-right">
          {renderLabelContent()}
        </span>
      </div>
    );
  }

  // Inline label layout (percentage inside the bar for lg/xl size)
  if (hasLabel && labelPosition === 'inline' && (size === 'lg' || size === 'xl')) {
    return (
      <div
        className={cn(trackClasses, 'relative', className)}
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : roundedPercentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ariaLabel || label || 'Progress'}
      >
        <style>{progressBarStyles}</style>
        {indeterminate ? (
          <div
            className={cn(
              progressFillVariants({ variant, animated: false }),
              'w-1/4',
              fillClassName
            )}
            style={{ animation: 'progress-indeterminate 1.5s infinite linear' }}
          />
        ) : (
          <div
            className={getFillClasses()}
            style={{
              width: `${percentage}%`,
              ...getTransitionStyle(),
              ...getGlowStyle(),
            }}
          />
        )}
        {(percentage > 15 || options.showValueInside) && (
          <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white">
            {renderLabelContent()}
          </span>
        )}
      </div>
    );
  }

  // Default: just the progress bar
  return (
    <div
      className={cn(trackClasses, className)}
      role="progressbar"
      aria-valuenow={indeterminate ? undefined : roundedPercentage}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel || 'Progress'}
    >
      <style>{progressBarStyles}</style>
      {indeterminate ? (
        <div
          className={cn(
            progressFillVariants({ variant, animated: false }),
            'w-1/4',
            fillClassName
          )}
          style={{ animation: 'progress-indeterminate 1.5s infinite linear' }}
        />
      ) : (
        <div
          className={getFillClasses()}
          style={{
            width: `${percentage}%`,
            ...getTransitionStyle(),
            ...getGlowStyle(),
          }}
        />
      )}
    </div>
  );
}

// Convenience components for common use cases

export interface ProgressBarWithStatsProps {
  /** Number of completed items */
  completed: number;
  /** Total number of items */
  total: number;
  /** Optional pass count for success indicator */
  passed?: number;
  /** Optional fail count for error indicator */
  failed?: number;
  /** Progress bar variant */
  variant?: ProgressBarProps['variant'];
  /** Progress bar size */
  size?: ProgressBarProps['size'];
  /** Animate the progress bar */
  animated?: boolean;
  /** Additional class names */
  className?: string;
  /** Progress bar options */
  options?: ProgressBarOptions;
}

/**
 * ProgressBarWithStats - Progress bar with completion stats
 * Useful for task execution tracking
 */
export function ProgressBarWithStats({
  completed,
  total,
  passed,
  failed,
  variant = 'gradient',
  size = 'md',
  animated,
  className,
  options,
}: ProgressBarWithStatsProps) {
  const percentage = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className={cn('space-y-2', className)}>
      <ProgressBar
        value={percentage}
        variant={variant}
        size={size}
        animated={animated}
        options={options}
      />
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-400">
          <span className="text-white font-medium">{completed}</span>
          <span className="mx-1">/</span>
          <span>{total}</span>
          <span className="ml-1">completed</span>
        </span>
        <div className="flex items-center gap-3">
          {passed !== undefined && (
            <span className="text-green-400">
              {passed} passed
            </span>
          )}
          {failed !== undefined && (
            <span className="text-red-400">
              {failed} failed
            </span>
          )}
          <span className="text-zinc-300 font-medium">
            {Math.round(percentage)}%
          </span>
        </div>
      </div>
    </div>
  );
}

export interface CircularProgressProps {
  /** Progress value from 0 to 100 */
  value: number;
  /** Size in pixels */
  size?: number;
  /** Stroke width */
  strokeWidth?: number;
  /** Color variant */
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'purple';
  /** Show percentage in center */
  showPercentage?: boolean;
  /** Custom center content */
  children?: React.ReactNode;
  /** Additional class names */
  className?: string;
}

const circularVariantColors: Record<string, string> = {
  default: 'stroke-blue-500',
  primary: 'stroke-cyan-500',
  success: 'stroke-green-500',
  warning: 'stroke-yellow-500',
  error: 'stroke-red-500',
  purple: 'stroke-purple-500',
};

/**
 * CircularProgress - Circular progress indicator
 */
export function CircularProgress({
  value,
  size = 48,
  strokeWidth = 4,
  variant = 'default',
  showPercentage = true,
  children,
  className,
}: CircularProgressProps) {
  const percentage = Math.min(Math.max(value, 0), 100);
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (percentage / 100) * circumference;

  return (
    <div className={cn('relative inline-flex', className)} style={{ width: size, height: size }}>
      <svg className="transform -rotate-90" width={size} height={size}>
        {/* Background circle */}
        <circle
          className="stroke-zinc-700"
          strokeWidth={strokeWidth}
          fill="none"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        {/* Progress circle */}
        <circle
          className={cn(
            circularVariantColors[variant] || circularVariantColors.default,
            'transition-all duration-300 ease-out'
          )}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          style={{
            strokeDasharray: circumference,
            strokeDashoffset: offset,
          }}
        />
      </svg>
      {/* Center content */}
      <div className="absolute inset-0 flex items-center justify-center">
        {children || (showPercentage && (
          <span className="text-xs font-medium text-zinc-200">
            {Math.round(percentage)}%
          </span>
        ))}
      </div>
    </div>
  );
}

// Segmented Progress Bar for multi-status visualization (e.g., pass/fail/pending)

export interface ProgressSegment {
  /** Segment value (will be calculated as percentage of total) */
  value: number;
  /** Segment color class (Tailwind bg-* class) */
  color: string;
  /** Optional label for accessibility */
  label?: string;
}

export interface SegmentedProgressBarProps {
  /** Array of segments to display */
  segments: ProgressSegment[];
  /** Progress bar size */
  size?: 'sm' | 'md' | 'lg';
  /** Additional class names */
  className?: string;
  /** Show segment labels below the bar */
  showLabels?: boolean;
  /** Accessible label */
  ariaLabel?: string;
}

/**
 * SegmentedProgressBar - Progress bar with multiple colored segments
 * Useful for showing pass/fail/pending status in a single bar
 */
export function SegmentedProgressBar({
  segments,
  size = 'md',
  className,
  showLabels = false,
  ariaLabel = 'Progress',
}: SegmentedProgressBarProps) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);

  const sizeClasses = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3',
  };

  return (
    <div className={cn('space-y-1', className)}>
      <div
        className={cn(
          'w-full overflow-hidden rounded-full bg-zinc-700 flex',
          sizeClasses[size]
        )}
        role="progressbar"
        aria-label={ariaLabel}
        aria-valuenow={total > 0 ? Math.round((segments[0]?.value || 0) / total * 100) : 0}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {segments.map((segment, index) => {
          const percentage = total > 0 ? (segment.value / total) * 100 : 0;
          if (percentage === 0) return null;

          return (
            <div
              key={index}
              className={cn('h-full transition-all duration-300', segment.color)}
              style={{ width: `${percentage}%` }}
              title={segment.label ? `${segment.label}: ${segment.value}` : undefined}
            />
          );
        })}
      </div>

      {showLabels && (
        <div className="flex items-center gap-3 text-xs">
          {segments.map((segment, index) => (
            segment.value > 0 && (
              <div key={index} className="flex items-center gap-1">
                <span className={cn('w-2 h-2 rounded-full', segment.color)} />
                <span className="text-zinc-400">
                  {segment.label}: <span className="text-white">{segment.value}</span>
                </span>
              </div>
            )
          ))}
        </div>
      )}
    </div>
  );
}

// Pre-configured segmented progress bar for QA/test results
export interface QAProgressBarProps {
  /** Number of passed tests */
  passed: number;
  /** Number of failed tests */
  failed: number;
  /** Number of pending/not done tests */
  pending?: number;
  /** Number of in-progress tests */
  inProgress?: number;
  /** Progress bar size */
  size?: 'sm' | 'md' | 'lg';
  /** Show labels below the bar */
  showLabels?: boolean;
  /** Additional class names */
  className?: string;
}

/**
 * QAProgressBar - Pre-configured progress bar for QA test results
 */
export function QAProgressBar({
  passed,
  failed,
  pending = 0,
  inProgress = 0,
  size = 'md',
  showLabels = false,
  className,
}: QAProgressBarProps) {
  const segments: ProgressSegment[] = [
    { value: passed, color: 'bg-green-500', label: 'Passed' },
    { value: failed, color: 'bg-red-500', label: 'Failed' },
    { value: inProgress, color: 'bg-blue-500', label: 'In Progress' },
    { value: pending, color: 'bg-zinc-500', label: 'Pending' },
  ].filter(s => s.value > 0);

  return (
    <SegmentedProgressBar
      segments={segments}
      size={size}
      showLabels={showLabels}
      className={className}
      ariaLabel="Test results progress"
    />
  );
}

export default ProgressBar;
