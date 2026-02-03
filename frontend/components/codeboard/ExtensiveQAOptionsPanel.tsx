'use client';

/**
 * ExtensiveQAOptionsPanel - Advanced options panel for extensive QA testing
 *
 * Features:
 * - Execution profile selection (smoke, regression, full-suite, etc.)
 * - Test coverage configuration
 * - Test depth and complexity settings
 * - Environment and browser targeting
 * - Execution control (cycles, timeouts, retry)
 * - Reporting and notification options
 * - Advanced filtering options
 */

import { useState, useCallback } from 'react';
import {
  Settings2,
  Target,
  Layers,
  Globe,
  Timer,
  RefreshCw,
  FileText,
  Bell,
  Filter,
  ChevronDown,
  ChevronRight,
  Zap,
  Shield,
  Eye,
  Server,
  Database,
  AlertTriangle,
  CornerUpRight,
  Link,
  Layout,
  CheckCircle2,
  Monitor,
  Tablet,
  Smartphone,
  Chrome,
  Compass,
  Info,
  RotateCcw,
} from 'lucide-react';
import type {
  ExtensiveQAOptions,
  ExecutionProfile,
  TestArea,
  TestComplexity,
  TargetBrowser,
  TargetDevice,
  TargetEnvironment,
  QAPriority,
} from '@/types/qaboard';
import {
  DEFAULT_EXTENSIVE_QA_OPTIONS,
  EXECUTION_PROFILES,
  TEST_AREA_CONFIG,
  COMPLEXITY_CONFIG,
  BROWSER_CONFIG,
  DEVICE_CONFIG,
  ENVIRONMENT_CONFIG,
} from '@/types/qaboard';
import { cn } from '@/lib/utils';

export interface ExtensiveQAOptionsPanelProps {
  options: ExtensiveQAOptions;
  onOptionsChange: (options: ExtensiveQAOptions) => void;
  isExecuting?: boolean;
  className?: string;
}

// Section header component
function SectionHeader({
  icon: Icon,
  title,
  description,
  isOpen,
  onToggle,
}: {
  icon: React.ElementType;
  title: string;
  description?: string;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between p-3 bg-zinc-800/50 hover:bg-zinc-800 rounded-lg transition-colors"
    >
      <div className="flex items-center gap-3">
        <Icon className="w-4 h-4 text-blue-400" />
        <div className="text-left">
          <span className="text-sm font-medium text-white">{title}</span>
          {description && (
            <p className="text-xs text-zinc-500">{description}</p>
          )}
        </div>
      </div>
      {isOpen ? (
        <ChevronDown className="w-4 h-4 text-zinc-400" />
      ) : (
        <ChevronRight className="w-4 h-4 text-zinc-400" />
      )}
    </button>
  );
}

// Toggle switch component
function Toggle({
  checked,
  onChange,
  disabled,
  label,
  description,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
  description?: string;
}) {
  return (
    <label className={cn('flex items-center justify-between cursor-pointer group', disabled && 'opacity-50 cursor-not-allowed')}>
      <div>
        <span className="text-sm text-zinc-300 group-hover:text-white">{label}</span>
        {description && <p className="text-xs text-zinc-500">{description}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={cn(
          'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-zinc-900',
          checked ? 'bg-blue-600' : 'bg-zinc-600',
          disabled && 'cursor-not-allowed'
        )}
      >
        <span
          className={cn(
            'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
            checked ? 'translate-x-4' : 'translate-x-0.5',
            'mt-0.5'
          )}
        />
      </button>
    </label>
  );
}

// Number input component
function NumberInput({
  value,
  onChange,
  min,
  max,
  disabled,
  label,
  suffix,
}: {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
  label: string;
  suffix?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-zinc-300">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(parseInt(e.target.value) || min || 0)}
          min={min}
          max={max}
          disabled={disabled}
          className="w-20 px-2 py-1 text-sm bg-zinc-800 border border-zinc-700 rounded text-white text-right focus:outline-none focus:border-blue-500 disabled:opacity-50"
        />
        {suffix && <span className="text-xs text-zinc-500">{suffix}</span>}
      </div>
    </div>
  );
}

// Multi-select chip component
function ChipSelect<T extends string>({
  options,
  selected,
  onChange,
  disabled,
  getLabel,
  getIcon,
}: {
  options: T[];
  selected: T[];
  onChange: (selected: T[]) => void;
  disabled?: boolean;
  getLabel: (option: T) => string;
  getIcon?: (option: T) => React.ReactNode;
}) {
  const toggleOption = (option: T) => {
    if (disabled) return;
    if (selected.includes(option)) {
      onChange(selected.filter((o) => o !== option));
    } else {
      onChange([...selected, option]);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option}
          onClick={() => toggleOption(option)}
          disabled={disabled}
          className={cn(
            'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-colors',
            selected.includes(option)
              ? 'bg-blue-600 text-white'
              : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          {getIcon && getIcon(option)}
          {getLabel(option)}
        </button>
      ))}
    </div>
  );
}

// Get icon for test area
function getTestAreaIcon(area: TestArea): React.ReactNode {
  const icons: Record<TestArea, React.ReactNode> = {
    'functional': <CheckCircle2 className="w-3 h-3" />,
    'ui': <Layout className="w-3 h-3" />,
    'integration': <Link className="w-3 h-3" />,
    'performance': <Zap className="w-3 h-3" />,
    'security': <Shield className="w-3 h-3" />,
    'accessibility': <Eye className="w-3 h-3" />,
    'api': <Server className="w-3 h-3" />,
    'database': <Database className="w-3 h-3" />,
    'error-handling': <AlertTriangle className="w-3 h-3" />,
    'edge-cases': <CornerUpRight className="w-3 h-3" />,
  };
  return icons[area];
}

// Get icon for device
function getDeviceIcon(device: TargetDevice): React.ReactNode {
  const icons: Record<TargetDevice, React.ReactNode> = {
    'desktop': <Monitor className="w-3 h-3" />,
    'tablet': <Tablet className="w-3 h-3" />,
    'mobile': <Smartphone className="w-3 h-3" />,
  };
  return icons[device];
}

export function ExtensiveQAOptionsPanel({
  options,
  onOptionsChange,
  isExecuting = false,
  className,
}: ExtensiveQAOptionsPanelProps) {
  // Section visibility state
  const [openSections, setOpenSections] = useState<Set<string>>(new Set(['profile', 'coverage']));

  const toggleSection = useCallback((section: string) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  }, []);

  // Update single option
  const updateOption = useCallback(
    <K extends keyof ExtensiveQAOptions>(key: K, value: ExtensiveQAOptions[K]) => {
      onOptionsChange({
        ...options,
        [key]: value,
      });
    },
    [options, onOptionsChange]
  );

  // Apply execution profile preset
  const applyProfile = useCallback(
    (profile: ExecutionProfile) => {
      const preset = EXECUTION_PROFILES[profile];
      onOptionsChange({
        ...DEFAULT_EXTENSIVE_QA_OPTIONS,
        ...preset,
        executionProfile: profile,
      });
    },
    [onOptionsChange]
  );

  // Reset to defaults
  const resetToDefaults = useCallback(() => {
    onOptionsChange(DEFAULT_EXTENSIVE_QA_OPTIONS);
  }, [onOptionsChange]);

  return (
    <div className={cn('space-y-3', className)}>
      {/* Header with reset button */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-white">Extensive Options</span>
        </div>
        <button
          onClick={resetToDefaults}
          disabled={isExecuting}
          className="flex items-center gap-1 px-2 py-1 text-xs text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
        >
          <RotateCcw className="w-3 h-3" />
          Reset
        </button>
      </div>

      {/* Execution Profile Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Zap}
          title="Execution Profile"
          description="Quick presets for common testing scenarios"
          isOpen={openSections.has('profile')}
          onToggle={() => toggleSection('profile')}
        />
        {openSections.has('profile') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
              {(['smoke', 'critical-path', 'regression', 'full-suite', 'custom'] as ExecutionProfile[]).map(
                (profile) => (
                  <button
                    key={profile}
                    onClick={() => applyProfile(profile)}
                    disabled={isExecuting}
                    className={cn(
                      'px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                      options.executionProfile === profile
                        ? 'bg-blue-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700',
                      isExecuting && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {profile === 'smoke' && 'Smoke Test'}
                    {profile === 'critical-path' && 'Critical Path'}
                    {profile === 'regression' && 'Regression'}
                    {profile === 'full-suite' && 'Full Suite'}
                    {profile === 'custom' && 'Custom'}
                  </button>
                )
              )}
            </div>
            {options.executionProfile === 'custom' && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-500">Profile name:</span>
                <input
                  type="text"
                  value={options.customProfileName || ''}
                  onChange={(e) => updateOption('customProfileName', e.target.value)}
                  placeholder="My Custom Profile"
                  disabled={isExecuting}
                  className="flex-1 px-2 py-1 text-sm bg-zinc-800 border border-zinc-700 rounded text-white placeholder-zinc-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Test Coverage Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Target}
          title="Test Coverage"
          description="Configure coverage targets and priority filters"
          isOpen={openSections.has('coverage')}
          onToggle={() => toggleSection('coverage')}
        />
        {openSections.has('coverage') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <NumberInput
              value={options.targetCoveragePercent}
              onChange={(v) => updateOption('targetCoveragePercent', Math.min(100, Math.max(0, v)))}
              min={0}
              max={100}
              disabled={isExecuting}
              label="Target Coverage"
              suffix="%"
            />
            <NumberInput
              value={options.mandatoryTaskCount}
              onChange={(v) => updateOption('mandatoryTaskCount', Math.max(0, v))}
              min={0}
              disabled={isExecuting}
              label="Mandatory Task Count"
              suffix="tasks"
            />
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Include Priorities</span>
              <ChipSelect
                options={['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as QAPriority[]}
                selected={options.includePriorities}
                onChange={(v) => updateOption('includePriorities', v)}
                disabled={isExecuting}
                getLabel={(p) => p.charAt(0) + p.slice(1).toLowerCase()}
              />
            </div>
          </div>
        )}
      </div>

      {/* Test Depth & Complexity Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Layers}
          title="Test Depth & Complexity"
          description="Configure test areas and complexity levels"
          isOpen={openSections.has('depth')}
          onToggle={() => toggleSection('depth')}
        />
        {openSections.has('depth') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Max Complexity Level</span>
              <div className="flex gap-2">
                {COMPLEXITY_CONFIG.map(({ level, label }) => (
                  <button
                    key={level}
                    onClick={() => updateOption('maxComplexityLevel', level)}
                    disabled={isExecuting}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                      options.maxComplexityLevel === level
                        ? 'bg-blue-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700',
                      isExecuting && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Test Areas</span>
              <ChipSelect
                options={TEST_AREA_CONFIG.map((c) => c.area)}
                selected={options.includeTestAreas}
                onChange={(v) => updateOption('includeTestAreas', v)}
                disabled={isExecuting}
                getLabel={(area) => TEST_AREA_CONFIG.find((c) => c.area === area)?.label || area}
                getIcon={(area) => getTestAreaIcon(area)}
              />
            </div>
            <div className="space-y-3 pt-2">
              <Toggle
                checked={options.includeApiTests}
                onChange={(v) => updateOption('includeApiTests', v)}
                disabled={isExecuting}
                label="Include API Tests"
              />
              <Toggle
                checked={options.includeDataIntegrityTests}
                onChange={(v) => updateOption('includeDataIntegrityTests', v)}
                disabled={isExecuting}
                label="Include Data Integrity Tests"
              />
              <Toggle
                checked={options.includeErrorRecoveryTests}
                onChange={(v) => updateOption('includeErrorRecoveryTests', v)}
                disabled={isExecuting}
                label="Include Error Recovery Tests"
              />
              <Toggle
                checked={options.includeConcurrencyTests}
                onChange={(v) => updateOption('includeConcurrencyTests', v)}
                disabled={isExecuting}
                label="Include Concurrency Tests"
              />
              <Toggle
                checked={options.includeStateManagementTests}
                onChange={(v) => updateOption('includeStateManagementTests', v)}
                disabled={isExecuting}
                label="Include State Management Tests"
              />
            </div>
          </div>
        )}
      </div>

      {/* Environment & Browser Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Globe}
          title="Environment & Browser"
          description="Target platforms and environments"
          isOpen={openSections.has('environment')}
          onToggle={() => toggleSection('environment')}
        />
        {openSections.has('environment') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Target Environment</span>
              <div className="flex gap-2">
                {ENVIRONMENT_CONFIG.map(({ env, label }) => (
                  <button
                    key={env}
                    onClick={() => updateOption('targetEnvironment', env)}
                    disabled={isExecuting}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                      options.targetEnvironment === env
                        ? 'bg-blue-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700',
                      isExecuting && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Target Devices</span>
              <ChipSelect
                options={['desktop', 'tablet', 'mobile'] as TargetDevice[]}
                selected={options.targetDevices}
                onChange={(v) => updateOption('targetDevices', v)}
                disabled={isExecuting}
                getLabel={(d) => d.charAt(0).toUpperCase() + d.slice(1)}
                getIcon={(d) => getDeviceIcon(d)}
              />
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Target Browsers</span>
              <ChipSelect
                options={['chrome', 'firefox', 'safari', 'edge'] as TargetBrowser[]}
                selected={options.targetBrowsers}
                onChange={(v) => updateOption('targetBrowsers', v)}
                disabled={isExecuting}
                getLabel={(b) => b.charAt(0).toUpperCase() + b.slice(1)}
              />
            </div>
            <div className="space-y-3 pt-2">
              <Toggle
                checked={options.includeResponsiveTests}
                onChange={(v) => updateOption('includeResponsiveTests', v)}
                disabled={isExecuting}
                label="Include Responsive Tests"
                description="Test across different viewport sizes"
              />
              <Toggle
                checked={options.includeLocalizationTests}
                onChange={(v) => updateOption('includeLocalizationTests', v)}
                disabled={isExecuting}
                label="Include Localization Tests"
                description="Test multiple locales"
              />
            </div>
          </div>
        )}
      </div>

      {/* Execution Control Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Timer}
          title="Execution Control"
          description="Test cycles, timeouts, and failure tolerance"
          isOpen={openSections.has('execution')}
          onToggle={() => toggleSection('execution')}
        />
        {openSections.has('execution') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <NumberInput
              value={options.testCycles}
              onChange={(v) => updateOption('testCycles', Math.max(1, v))}
              min={1}
              max={10}
              disabled={isExecuting}
              label="Test Cycles"
              suffix="cycles"
            />
            <NumberInput
              value={options.taskTimeoutSeconds}
              onChange={(v) => updateOption('taskTimeoutSeconds', Math.max(30, v))}
              min={30}
              max={600}
              disabled={isExecuting}
              label="Task Timeout"
              suffix="sec"
            />
            <NumberInput
              value={options.failureTolerance}
              onChange={(v) => updateOption('failureTolerance', Math.min(100, Math.max(0, v)))}
              min={0}
              max={100}
              disabled={isExecuting}
              label="Failure Tolerance"
              suffix="%"
            />
            <div className="space-y-3 pt-2">
              <Toggle
                checked={options.runPrerequisites}
                onChange={(v) => updateOption('runPrerequisites', v)}
                disabled={isExecuting}
                label="Run Prerequisites"
                description="Execute setup tasks before tests"
              />
              <Toggle
                checked={options.runCleanup}
                onChange={(v) => updateOption('runCleanup', v)}
                disabled={isExecuting}
                label="Run Cleanup"
                description="Execute cleanup tasks after tests"
              />
            </div>
          </div>
        )}
      </div>

      {/* Retry & Recovery Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={RefreshCw}
          title="Retry & Recovery"
          description="Automatic retry and failure handling"
          isOpen={openSections.has('retry')}
          onToggle={() => toggleSection('retry')}
        />
        {openSections.has('retry') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.autoRetryFailed}
              onChange={(v) => updateOption('autoRetryFailed', v)}
              disabled={isExecuting}
              label="Auto Retry Failed Tests"
              description="Automatically retry failed tests"
            />
            {options.autoRetryFailed && (
              <>
                <NumberInput
                  value={options.maxRetryAttempts}
                  onChange={(v) => updateOption('maxRetryAttempts', Math.max(1, Math.min(5, v)))}
                  min={1}
                  max={5}
                  disabled={isExecuting}
                  label="Max Retry Attempts"
                  suffix="attempts"
                />
                <NumberInput
                  value={options.retryDelaySeconds}
                  onChange={(v) => updateOption('retryDelaySeconds', Math.max(0, v))}
                  min={0}
                  max={60}
                  disabled={isExecuting}
                  label="Retry Delay"
                  suffix="sec"
                />
              </>
            )}
            <NumberInput
              value={options.stopOnConsecutiveFailures}
              onChange={(v) => updateOption('stopOnConsecutiveFailures', Math.max(0, v))}
              min={0}
              max={20}
              disabled={isExecuting}
              label="Stop After Consecutive Failures"
              suffix="failures"
            />
            <p className="text-xs text-zinc-500 flex items-center gap-1">
              <Info className="w-3 h-3" />
              Set to 0 to disable
            </p>
          </div>
        )}
      </div>

      {/* Reporting Options Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={FileText}
          title="Reporting & Analysis"
          description="Reports, metrics, and flaky test detection"
          isOpen={openSections.has('reporting')}
          onToggle={() => toggleSection('reporting')}
        />
        {openSections.has('reporting') && (
          <div className="p-4 space-y-3 border-t border-zinc-800">
            <Toggle
              checked={options.generateDetailedReport}
              onChange={(v) => updateOption('generateDetailedReport', v)}
              disabled={isExecuting}
              label="Generate Detailed Report"
              description="Create comprehensive test report"
            />
            <Toggle
              checked={options.trackPerformanceMetrics}
              onChange={(v) => updateOption('trackPerformanceMetrics', v)}
              disabled={isExecuting}
              label="Track Performance Metrics"
              description="Record execution times and trends"
            />
            <Toggle
              checked={options.enableTrendAnalysis}
              onChange={(v) => updateOption('enableTrendAnalysis', v)}
              disabled={isExecuting}
              label="Enable Trend Analysis"
              description="Analyze pass/fail trends over time"
            />
            <Toggle
              checked={options.detectFlakyTests}
              onChange={(v) => updateOption('detectFlakyTests', v)}
              disabled={isExecuting}
              label="Detect Flaky Tests"
              description="Identify tests with inconsistent results"
            />
            {options.detectFlakyTests && (
              <NumberInput
                value={options.flakyTestThreshold}
                onChange={(v) => updateOption('flakyTestThreshold', Math.max(2, v))}
                min={2}
                max={10}
                disabled={isExecuting}
                label="Flaky Test Threshold"
                suffix="state changes"
              />
            )}
          </div>
        )}
      </div>

      {/* Notification Options Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Bell}
          title="Notifications"
          description="Sound and browser notification settings"
          isOpen={openSections.has('notifications')}
          onToggle={() => toggleSection('notifications')}
        />
        {openSections.has('notifications') && (
          <div className="p-4 space-y-3 border-t border-zinc-800">
            <Toggle
              checked={options.soundEnabled}
              onChange={(v) => updateOption('soundEnabled', v)}
              disabled={isExecuting}
              label="Sound Notifications"
              description="Play sound on completion/failure"
            />
            <Toggle
              checked={options.browserNotifications}
              onChange={(v) => updateOption('browserNotifications', v)}
              disabled={isExecuting}
              label="Browser Notifications"
              description="Show system notifications"
            />
            <Toggle
              checked={options.notifyOnCompletion}
              onChange={(v) => updateOption('notifyOnCompletion', v)}
              disabled={isExecuting}
              label="Notify on Completion"
            />
            <Toggle
              checked={options.notifyOnFailure}
              onChange={(v) => updateOption('notifyOnFailure', v)}
              disabled={isExecuting}
              label="Notify on Failure"
            />
          </div>
        )}
      </div>

      {/* Advanced Filtering Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Filter}
          title="Advanced Filtering"
          description="Filter tests by area, complexity, and stability"
          isOpen={openSections.has('filtering')}
          onToggle={() => toggleSection('filtering')}
        />
        {openSections.has('filtering') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Filter by Test Areas</span>
              <ChipSelect
                options={TEST_AREA_CONFIG.map((c) => c.area)}
                selected={options.filterByTestAreas}
                onChange={(v) => updateOption('filterByTestAreas', v)}
                disabled={isExecuting}
                getLabel={(area) => TEST_AREA_CONFIG.find((c) => c.area === area)?.label || area}
                getIcon={(area) => getTestAreaIcon(area)}
              />
              <p className="text-xs text-zinc-500 mt-1">Leave empty to include all areas</p>
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Filter by Complexity</span>
              <div className="flex gap-2">
                {(['all', 'simple', 'moderate', 'complex'] as const).map((level) => (
                  <button
                    key={level}
                    onClick={() => updateOption('filterByComplexity', level)}
                    disabled={isExecuting}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                      options.filterByComplexity === level
                        ? 'bg-blue-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700',
                      isExecuting && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {level === 'all' ? 'All' : level.charAt(0).toUpperCase() + level.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Filter by Duration</span>
              <div className="flex gap-2">
                {(['all', 'short', 'medium', 'long'] as const).map((duration) => (
                  <button
                    key={duration}
                    onClick={() => updateOption('filterByEstimatedDuration', duration)}
                    disabled={isExecuting}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                      options.filterByEstimatedDuration === duration
                        ? 'bg-blue-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700',
                      isExecuting && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {duration === 'all' ? 'All' : duration.charAt(0).toUpperCase() + duration.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Filter by Stability</span>
              <div className="flex gap-2">
                {(['all', 'stable', 'flaky'] as const).map((stability) => (
                  <button
                    key={stability}
                    onClick={() => updateOption('filterByFailureRate', stability)}
                    disabled={isExecuting}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                      options.filterByFailureRate === stability
                        ? 'bg-blue-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700',
                      isExecuting && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {stability === 'all' ? 'All' : stability.charAt(0).toUpperCase() + stability.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ExtensiveQAOptionsPanel;
