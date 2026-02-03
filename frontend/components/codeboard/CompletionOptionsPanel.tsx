'use client';

/**
 * CompletionOptionsPanel - Options panel for test plan completion customization
 * Part of CB-850: Add test plan completion options
 *
 * Features:
 * - Preset selection (default, minimal, detailed, quick-summary, report-ready)
 * - Pass rate gauge display options
 * - Metric display preferences
 * - Progress bar customization
 * - Failed tests display settings
 * - Next steps & actions configuration
 * - Export options
 * - Celebration & notification settings
 * - Auto-action configuration
 */

import { useState, useCallback } from 'react';
import {
  Settings2,
  Gauge,
  BarChart3,
  ListChecks,
  Flag,
  Download,
  Archive,
  RefreshCw,
  Bug,
  ChevronDown,
  ChevronRight,
  RotateCcw,
  Sliders,
  PartyPopper,
  Bell,
  Play,
  FileText,
  Eye,
  Clock,
  Zap,
  AlertTriangle,
  Target,
  Lightbulb,
} from 'lucide-react';
import type {
  CompletionOptions,
  CompletionPreset,
  CompletionAction,
  CompletionReportSection,
  CelebrationStyle,
  ExportFormat,
} from '@/types/qaboard';
import {
  DEFAULT_COMPLETION_OPTIONS,
  COMPLETION_PRESETS,
  COMPLETION_METRICS_CONFIG,
  COMPLETION_ACTIONS_CONFIG,
  COMPLETION_REPORT_SECTIONS_CONFIG,
  CELEBRATION_STYLES_CONFIG,
  GAUGE_SIZE_CONFIG,
  PROGRESS_BAR_STYLE_CONFIG,
} from '@/types/qaboard';
import { cn } from '@/lib/utils';

export interface CompletionOptionsPanelProps {
  options: CompletionOptions;
  onOptionsChange: (options: CompletionOptions) => void;
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
        <Icon className="w-4 h-4 text-green-400" />
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
          'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:ring-offset-zinc-900',
          checked ? 'bg-green-600' : 'bg-zinc-600',
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
          className="w-20 px-2 py-1 text-sm bg-zinc-800 border border-zinc-700 rounded text-white text-right focus:outline-none focus:border-green-500 disabled:opacity-50"
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
              ? 'bg-green-600 text-white'
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

// Get icon for completion action
function getActionIcon(action: CompletionAction): React.ReactNode {
  const icons: Record<CompletionAction, React.ReactNode> = {
    'mark-complete': <Flag className="w-3 h-3" />,
    'export': <Download className="w-3 h-3" />,
    'archive': <Archive className="w-3 h-3" />,
    'rerun-failed': <RefreshCw className="w-3 h-3" />,
    'create-bugs': <Bug className="w-3 h-3" />,
  };
  return icons[action];
}

// Get icon for report section
function getReportSectionIcon(section: CompletionReportSection): React.ReactNode {
  const icons: Record<CompletionReportSection, React.ReactNode> = {
    'summary': <FileText className="w-3 h-3" />,
    'metrics': <BarChart3 className="w-3 h-3" />,
    'failed-tests': <AlertTriangle className="w-3 h-3" />,
    'execution-timeline': <Clock className="w-3 h-3" />,
    'recommendations': <Lightbulb className="w-3 h-3" />,
  };
  return icons[section];
}

// Get icon for next step type
function getNextStepIcon(type: 'action' | 'recommendation' | 'warning'): React.ReactNode {
  const icons: Record<'action' | 'recommendation' | 'warning', React.ReactNode> = {
    'action': <Play className="w-3 h-3" />,
    'recommendation': <Target className="w-3 h-3" />,
    'warning': <AlertTriangle className="w-3 h-3" />,
  };
  return icons[type];
}

export function CompletionOptionsPanel({
  options,
  onOptionsChange,
  className,
}: CompletionOptionsPanelProps) {
  // Section visibility state
  const [openSections, setOpenSections] = useState<Set<string>>(new Set(['preset', 'gauge']));

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
    <K extends keyof CompletionOptions>(key: K, value: CompletionOptions[K]) => {
      onOptionsChange({
        ...options,
        [key]: value,
      });
    },
    [options, onOptionsChange]
  );

  // Apply preset
  const applyPreset = useCallback(
    (preset: CompletionPreset) => {
      const presetOptions = COMPLETION_PRESETS[preset];
      onOptionsChange({
        ...DEFAULT_COMPLETION_OPTIONS,
        ...presetOptions,
      });
    },
    [onOptionsChange]
  );

  // Reset to defaults
  const resetToDefaults = useCallback(() => {
    onOptionsChange(DEFAULT_COMPLETION_OPTIONS);
  }, [onOptionsChange]);

  return (
    <div className={cn('space-y-3', className)}>
      {/* Header with reset button */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-green-400" />
          <span className="text-sm font-medium text-white">Completion Options</span>
        </div>
        <button
          onClick={resetToDefaults}
          className="flex items-center gap-1 px-2 py-1 text-xs text-zinc-400 hover:text-white transition-colors"
        >
          <RotateCcw className="w-3 h-3" />
          Reset
        </button>
      </div>

      {/* Preset Selection Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Sliders}
          title="Presets"
          description="Quick configurations for completion display"
          isOpen={openSections.has('preset')}
          onToggle={() => toggleSection('preset')}
        />
        {openSections.has('preset') && (
          <div className="p-4 border-t border-zinc-800">
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
              {(['default', 'minimal', 'detailed', 'quick-summary', 'report-ready'] as CompletionPreset[]).map(
                (preset) => (
                  <button
                    key={preset}
                    onClick={() => applyPreset(preset)}
                    className={cn(
                      'px-3 py-2 rounded-lg text-xs font-medium transition-colors capitalize',
                      options.preset === preset
                        ? 'bg-green-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                    )}
                  >
                    {preset.replace(/-/g, ' ')}
                  </button>
                )
              )}
            </div>
          </div>
        )}
      </div>

      {/* Pass Rate Gauge Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Gauge}
          title="Pass Rate Gauge"
          description="Configure the main pass rate display"
          isOpen={openSections.has('gauge')}
          onToggle={() => toggleSection('gauge')}
        />
        {openSections.has('gauge') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showPassRateGauge}
              onChange={(v) => updateOption('showPassRateGauge', v)}
              label="Show Pass Rate Gauge"
              description="Display the circular pass rate indicator"
            />
            {options.showPassRateGauge && (
              <>
                <div>
                  <span className="text-sm text-zinc-300 block mb-2">Gauge Size</span>
                  <div className="flex gap-2">
                    {GAUGE_SIZE_CONFIG.map(({ size, label }) => (
                      <button
                        key={size}
                        onClick={() => updateOption('gaugeSize', size)}
                        className={cn(
                          'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                          options.gaugeSize === size
                            ? 'bg-green-600 text-white'
                            : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <Toggle
                  checked={options.showThresholdMarker}
                  onChange={(v) => updateOption('showThresholdMarker', v)}
                  label="Show Threshold Marker"
                  description="Display threshold indicator on gauge"
                />
              </>
            )}
          </div>
        )}
      </div>

      {/* Metrics Display Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={BarChart3}
          title="Metrics Display"
          description="Configure which metrics to show"
          isOpen={openSections.has('metrics')}
          onToggle={() => toggleSection('metrics')}
        />
        {openSections.has('metrics') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showMetricCards}
              onChange={(v) => updateOption('showMetricCards', v)}
              label="Show Metric Cards"
              description="Display summary metric cards"
            />
            {options.showMetricCards && (
              <>
                <div>
                  <span className="text-sm text-zinc-300 block mb-2">Metrics to Show</span>
                  <ChipSelect
                    options={COMPLETION_METRICS_CONFIG.map(c => c.metric)}
                    selected={options.metricsToShow}
                    onChange={(v) => updateOption('metricsToShow', v)}
                    getLabel={(m) => COMPLETION_METRICS_CONFIG.find(c => c.metric === m)?.label || m}
                  />
                </div>
                <Toggle
                  checked={options.showTrends}
                  onChange={(v) => updateOption('showTrends', v)}
                  label="Show Trends"
                  description="Display trend indicators on metrics"
                />
              </>
            )}
          </div>
        )}
      </div>

      {/* Progress Bar Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={ListChecks}
          title="Progress Bar"
          description="Configure completion progress display"
          isOpen={openSections.has('progress')}
          onToggle={() => toggleSection('progress')}
        />
        {openSections.has('progress') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showProgressBar}
              onChange={(v) => updateOption('showProgressBar', v)}
              label="Show Progress Bar"
              description="Display completion progress bar"
            />
            {options.showProgressBar && (
              <>
                <div>
                  <span className="text-sm text-zinc-300 block mb-2">Progress Bar Style</span>
                  <div className="flex gap-2">
                    {PROGRESS_BAR_STYLE_CONFIG.map(({ style, label }) => (
                      <button
                        key={style}
                        onClick={() => updateOption('progressBarStyle', style)}
                        className={cn(
                          'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                          options.progressBarStyle === style
                            ? 'bg-green-600 text-white'
                            : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <Toggle
                  checked={options.showLegend}
                  onChange={(v) => updateOption('showLegend', v)}
                  label="Show Legend"
                  description="Display color legend below progress bar"
                />
              </>
            )}
          </div>
        )}
      </div>

      {/* Test Type Breakdown Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Zap}
          title="Test Type Breakdown"
          description="Automated vs manual test display"
          isOpen={openSections.has('testType')}
          onToggle={() => toggleSection('testType')}
        />
        {openSections.has('testType') && (
          <div className="p-4 space-y-3 border-t border-zinc-800">
            <Toggle
              checked={options.showTestTypeBreakdown}
              onChange={(v) => updateOption('showTestTypeBreakdown', v)}
              label="Show Test Type Breakdown"
              description="Display automated/manual test counts"
            />
            {options.showTestTypeBreakdown && (
              <Toggle
                checked={options.showAutomatedVsManual}
                onChange={(v) => updateOption('showAutomatedVsManual', v)}
                label="Show Side-by-Side Comparison"
                description="Show automated vs manual in cards"
              />
            )}
          </div>
        )}
      </div>

      {/* Failed Tests Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={AlertTriangle}
          title="Failed Tests"
          description="Configure failed tests display"
          isOpen={openSections.has('failed')}
          onToggle={() => toggleSection('failed')}
        />
        {openSections.has('failed') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showFailedTestsSummary}
              onChange={(v) => updateOption('showFailedTestsSummary', v)}
              label="Show Failed Tests Summary"
              description="Display list of failed tests"
            />
            {options.showFailedTestsSummary && (
              <>
                <NumberInput
                  value={options.maxFailedTestsShown}
                  onChange={(v) => updateOption('maxFailedTestsShown', Math.max(1, Math.min(20, v)))}
                  min={1}
                  max={20}
                  label="Max Tests Shown"
                  suffix="tests"
                />
                <Toggle
                  checked={options.allowBugCreation}
                  onChange={(v) => updateOption('allowBugCreation', v)}
                  label="Allow Bug Creation"
                  description="Enable creating bugs from failed tests"
                />
              </>
            )}
          </div>
        )}
      </div>

      {/* Next Steps Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Lightbulb}
          title="Next Steps"
          description="Configure recommendations display"
          isOpen={openSections.has('nextSteps')}
          onToggle={() => toggleSection('nextSteps')}
        />
        {openSections.has('nextSteps') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showNextSteps}
              onChange={(v) => updateOption('showNextSteps', v)}
              label="Show Next Steps"
              description="Display recommended next actions"
            />
            {options.showNextSteps && (
              <div>
                <span className="text-sm text-zinc-300 block mb-2">Step Types to Show</span>
                <ChipSelect
                  options={['action', 'recommendation', 'warning'] as const}
                  selected={options.nextStepTypes}
                  onChange={(v) => updateOption('nextStepTypes', v)}
                  getLabel={(t) => t.charAt(0).toUpperCase() + t.slice(1)}
                  getIcon={(t) => getNextStepIcon(t)}
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Actions Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Flag}
          title="Actions"
          description="Configure available completion actions"
          isOpen={openSections.has('actions')}
          onToggle={() => toggleSection('actions')}
        />
        {openSections.has('actions') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Enabled Actions</span>
              <ChipSelect
                options={COMPLETION_ACTIONS_CONFIG.map(c => c.action)}
                selected={options.enabledActions}
                onChange={(v) => updateOption('enabledActions', v)}
                getLabel={(a) => COMPLETION_ACTIONS_CONFIG.find(c => c.action === a)?.label || a}
                getIcon={(a) => getActionIcon(a)}
              />
            </div>
            <Toggle
              checked={options.showQuickActions}
              onChange={(v) => updateOption('showQuickActions', v)}
              label="Show Quick Actions"
              description="Display action buttons in footer"
            />
            <Toggle
              checked={options.confirmBeforeComplete}
              onChange={(v) => updateOption('confirmBeforeComplete', v)}
              label="Confirm Before Complete"
              description="Show confirmation dialog before marking complete"
            />
            <Toggle
              checked={options.confirmBeforeArchive}
              onChange={(v) => updateOption('confirmBeforeArchive', v)}
              label="Confirm Before Archive"
              description="Show confirmation dialog before archiving"
            />
          </div>
        )}
      </div>

      {/* Export Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Download}
          title="Export Options"
          description="Configure report export settings"
          isOpen={openSections.has('export')}
          onToggle={() => toggleSection('export')}
        />
        {openSections.has('export') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Default Export Format</span>
              <div className="flex gap-2">
                {(['json', 'csv', 'pdf'] as ExportFormat[]).map((format) => (
                  <button
                    key={format}
                    onClick={() => updateOption('defaultExportFormat', format)}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors uppercase',
                      options.defaultExportFormat === format
                        ? 'bg-green-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                    )}
                  >
                    {format}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Export Sections</span>
              <ChipSelect
                options={COMPLETION_REPORT_SECTIONS_CONFIG.map(c => c.section)}
                selected={options.exportSections}
                onChange={(v) => updateOption('exportSections', v)}
                getLabel={(s) => COMPLETION_REPORT_SECTIONS_CONFIG.find(c => c.section === s)?.label || s}
                getIcon={(s) => getReportSectionIcon(s)}
              />
            </div>
            <Toggle
              checked={options.includeExecutionHistory}
              onChange={(v) => updateOption('includeExecutionHistory', v)}
              label="Include Execution History"
              description="Add test execution timeline to export"
            />
            <Toggle
              checked={options.includeScreenshots}
              onChange={(v) => updateOption('includeScreenshots', v)}
              label="Include Screenshots"
              description="Add test screenshots to export (PDF only)"
            />
          </div>
        )}
      </div>

      {/* Celebration Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={PartyPopper}
          title="Celebration"
          description="Configure completion celebration"
          isOpen={openSections.has('celebration')}
          onToggle={() => toggleSection('celebration')}
        />
        {openSections.has('celebration') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showCelebrationOnPass}
              onChange={(v) => updateOption('showCelebrationOnPass', v)}
              label="Celebrate on Pass"
              description="Show celebration when tests pass threshold"
            />
            {options.showCelebrationOnPass && (
              <>
                <div>
                  <span className="text-sm text-zinc-300 block mb-2">Celebration Style</span>
                  <div className="flex gap-2">
                    {CELEBRATION_STYLES_CONFIG.map(({ style, label }) => (
                      <button
                        key={style}
                        onClick={() => updateOption('celebrationStyle', style)}
                        className={cn(
                          'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                          options.celebrationStyle === style
                            ? 'bg-green-600 text-white'
                            : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <NumberInput
                  value={options.celebrationDuration / 1000}
                  onChange={(v) => updateOption('celebrationDuration', Math.max(1, Math.min(10, v)) * 1000)}
                  min={1}
                  max={10}
                  label="Duration"
                  suffix="seconds"
                />
              </>
            )}
          </div>
        )}
      </div>

      {/* Notifications Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Bell}
          title="Notifications"
          description="Configure completion notifications"
          isOpen={openSections.has('notifications')}
          onToggle={() => toggleSection('notifications')}
        />
        {openSections.has('notifications') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.notifyOnCompletion}
              onChange={(v) => updateOption('notifyOnCompletion', v)}
              label="Notify on Completion"
              description="Send notification when tests complete"
            />
            {options.notifyOnCompletion && (
              <div>
                <span className="text-sm text-zinc-300 block mb-2">Notification Types</span>
                <ChipSelect
                  options={['in-app', 'browser', 'sound'] as const}
                  selected={options.notificationTypes}
                  onChange={(v) => updateOption('notificationTypes', v)}
                  getLabel={(t) => t === 'in-app' ? 'In-App' : t.charAt(0).toUpperCase() + t.slice(1)}
                />
              </div>
            )}
            <Toggle
              checked={options.playSoundOnComplete}
              onChange={(v) => updateOption('playSoundOnComplete', v)}
              label="Play Sound"
              description="Play a sound when tests complete"
            />
          </div>
        )}
      </div>

      {/* Auto Actions Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Zap}
          title="Auto Actions"
          description="Configure automatic actions"
          isOpen={openSections.has('autoActions')}
          onToggle={() => toggleSection('autoActions')}
        />
        {openSections.has('autoActions') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <NumberInput
              value={options.autoArchiveAfterDays}
              onChange={(v) => updateOption('autoArchiveAfterDays', Math.max(0, Math.min(365, v)))}
              min={0}
              max={365}
              label="Auto Archive After"
              suffix="days (0=off)"
            />
            <Toggle
              checked={options.autoExportOnComplete}
              onChange={(v) => updateOption('autoExportOnComplete', v)}
              label="Auto Export on Complete"
              description="Automatically export results when marked complete"
            />
            <Toggle
              checked={options.autoCreateBugsForFailed}
              onChange={(v) => updateOption('autoCreateBugsForFailed', v)}
              label="Auto Create Bugs"
              description="Automatically create bug issues for failed tests"
            />
          </div>
        )}
      </div>

      {/* Thresholds Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Target}
          title="Thresholds"
          description="Configure pass/warning thresholds"
          isOpen={openSections.has('thresholds')}
          onToggle={() => toggleSection('thresholds')}
        />
        {openSections.has('thresholds') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-zinc-300">Custom Pass Threshold</span>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={options.customPassThreshold ?? ''}
                    placeholder="Default"
                    onChange={(e) => {
                      const val = e.target.value;
                      updateOption('customPassThreshold', val === '' ? null : Math.min(100, Math.max(0, parseInt(val) || 0)));
                    }}
                    min={0}
                    max={100}
                    className="w-20 px-2 py-1 text-sm bg-zinc-800 border border-zinc-700 rounded text-white text-right focus:outline-none focus:border-green-500 placeholder:text-zinc-600"
                  />
                  <span className="text-xs text-zinc-500">%</span>
                </div>
              </div>
              <p className="text-xs text-zinc-500">Leave empty to use project default threshold</p>
            </div>
            <NumberInput
              value={options.warningThreshold}
              onChange={(v) => updateOption('warningThreshold', Math.max(0, Math.min(100, v)))}
              min={0}
              max={100}
              label="Warning Threshold"
              suffix="%"
            />
            <p className="text-xs text-zinc-500">Show warning when pass rate falls below this value</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default CompletionOptionsPanel;
