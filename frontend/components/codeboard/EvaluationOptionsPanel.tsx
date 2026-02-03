'use client';

/**
 * EvaluationOptionsPanel - Options panel for test plan evaluation customization
 * Part of CB-849: Add test plan evaluation options
 *
 * Features:
 * - Preset selection (default, minimal, detailed, etc.)
 * - Metric display preferences
 * - Quality threshold customization
 * - Recommendation filtering
 * - Coverage display options
 * - Flaky test detection settings
 * - Export configuration
 */

import { useState, useCallback } from 'react';
import {
  Settings2,
  Gauge,
  BarChart3,
  PieChart,
  Hash,
  Target,
  AlertTriangle,
  RefreshCw,
  Play,
  TrendingUp,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  RotateCcw,
  Download,
  Lightbulb,
  Clock,
  Sliders,
} from 'lucide-react';
import type {
  EvaluationOptions,
  EvaluationPreset,
  MetricDisplayOption,
  ChartVisualization,
  RecommendationType,
  RecommendationSeverity,
  ExportFormat,
} from '@/types/qaboard';
import {
  DEFAULT_EVALUATION_OPTIONS,
  EVALUATION_PRESETS,
  METRIC_DISPLAY_CONFIG,
  RECOMMENDATION_TYPE_CONFIG,
  RECOMMENDATION_SEVERITY_CONFIG,
  CHART_VISUALIZATION_CONFIG,
} from '@/types/qaboard';
import { cn } from '@/lib/utils';

export interface EvaluationOptionsPanelProps {
  options: EvaluationOptions;
  onOptionsChange: (options: EvaluationOptions) => void;
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
        <Icon className="w-4 h-4 text-purple-400" />
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
          'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-zinc-900',
          checked ? 'bg-purple-600' : 'bg-zinc-600',
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
          className="w-20 px-2 py-1 text-sm bg-zinc-800 border border-zinc-700 rounded text-white text-right focus:outline-none focus:border-purple-500 disabled:opacity-50"
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
              ? 'bg-purple-600 text-white'
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

// Get icon for recommendation type
function getRecommendationTypeIcon(type: RecommendationType): React.ReactNode {
  const icons: Record<RecommendationType, React.ReactNode> = {
    'coverage': <Target className="w-3 h-3" />,
    'priority': <AlertTriangle className="w-3 h-3" />,
    'flaky': <RefreshCw className="w-3 h-3" />,
    'execution': <Play className="w-3 h-3" />,
    'improvement': <TrendingUp className="w-3 h-3" />,
  };
  return icons[type];
}

// Get icon for chart visualization
function getVisualizationIcon(type: ChartVisualization): React.ReactNode {
  const icons: Record<ChartVisualization, React.ReactNode> = {
    'gauge': <Gauge className="w-4 h-4" />,
    'bar': <BarChart3 className="w-4 h-4" />,
    'donut': <PieChart className="w-4 h-4" />,
    'none': <Hash className="w-4 h-4" />,
  };
  return icons[type];
}

export function EvaluationOptionsPanel({
  options,
  onOptionsChange,
  className,
}: EvaluationOptionsPanelProps) {
  // Section visibility state
  const [openSections, setOpenSections] = useState<Set<string>>(new Set(['preset', 'metrics']));

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
    <K extends keyof EvaluationOptions>(key: K, value: EvaluationOptions[K]) => {
      onOptionsChange({
        ...options,
        [key]: value,
      });
    },
    [options, onOptionsChange]
  );

  // Apply preset
  const applyPreset = useCallback(
    (preset: EvaluationPreset) => {
      const presetOptions = EVALUATION_PRESETS[preset];
      onOptionsChange({
        ...DEFAULT_EVALUATION_OPTIONS,
        ...presetOptions,
      });
    },
    [onOptionsChange]
  );

  // Reset to defaults
  const resetToDefaults = useCallback(() => {
    onOptionsChange(DEFAULT_EVALUATION_OPTIONS);
  }, [onOptionsChange]);

  return (
    <div className={cn('space-y-3', className)}>
      {/* Header with reset button */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-purple-400" />
          <span className="text-sm font-medium text-white">Evaluation Options</span>
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
          description="Quick configurations for evaluation display"
          isOpen={openSections.has('preset')}
          onToggle={() => toggleSection('preset')}
        />
        {openSections.has('preset') && (
          <div className="p-4 border-t border-zinc-800">
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
              {(['default', 'minimal', 'detailed', 'metrics-only', 'recommendations-only'] as EvaluationPreset[]).map(
                (preset) => (
                  <button
                    key={preset}
                    onClick={() => applyPreset(preset)}
                    className={cn(
                      'px-3 py-2 rounded-lg text-xs font-medium transition-colors capitalize',
                      'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                    )}
                  >
                    {preset.replace('-', ' ')}
                  </button>
                )
              )}
            </div>
          </div>
        )}
      </div>

      {/* Metrics Display Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Gauge}
          title="Metrics Display"
          description="Configure which metrics to show and how"
          isOpen={openSections.has('metrics')}
          onToggle={() => toggleSection('metrics')}
        />
        {openSections.has('metrics') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Show Metrics</span>
              <ChipSelect
                options={METRIC_DISPLAY_CONFIG.map(c => c.metric)}
                selected={options.showMetrics}
                onChange={(v) => updateOption('showMetrics', v)}
                getLabel={(m) => METRIC_DISPLAY_CONFIG.find(c => c.metric === m)?.label || m}
              />
            </div>
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Visualization Style</span>
              <div className="flex gap-2">
                {CHART_VISUALIZATION_CONFIG.map(({ type, label }) => (
                  <button
                    key={type}
                    onClick={() => updateOption('metricsVisualization', type)}
                    className={cn(
                      'flex items-center gap-2 flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                      options.metricsVisualization === type
                        ? 'bg-purple-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                    )}
                  >
                    {getVisualizationIcon(type)}
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quality Thresholds Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Target}
          title="Quality Thresholds"
          description="Customize thresholds for good/warning status"
          isOpen={openSections.has('thresholds')}
          onToggle={() => toggleSection('thresholds')}
        />
        {openSections.has('thresholds') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div className="space-y-3">
              <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider">Pass Rate</p>
              <NumberInput
                value={options.passRateGoodThreshold}
                onChange={(v) => updateOption('passRateGoodThreshold', Math.min(100, Math.max(0, v)))}
                min={0}
                max={100}
                label="Good Threshold"
                suffix="%"
              />
              <NumberInput
                value={options.passRateWarningThreshold}
                onChange={(v) => updateOption('passRateWarningThreshold', Math.min(100, Math.max(0, v)))}
                min={0}
                max={100}
                label="Warning Threshold"
                suffix="%"
              />
            </div>
            <div className="space-y-3 pt-2 border-t border-zinc-800/50">
              <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider">Completion</p>
              <NumberInput
                value={options.completionGoodThreshold}
                onChange={(v) => updateOption('completionGoodThreshold', Math.min(100, Math.max(0, v)))}
                min={0}
                max={100}
                label="Good Threshold"
                suffix="%"
              />
              <NumberInput
                value={options.completionWarningThreshold}
                onChange={(v) => updateOption('completionWarningThreshold', Math.min(100, Math.max(0, v)))}
                min={0}
                max={100}
                label="Warning Threshold"
                suffix="%"
              />
            </div>
            <div className="space-y-3 pt-2 border-t border-zinc-800/50">
              <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider">Coverage</p>
              <NumberInput
                value={options.coverageGoodThreshold}
                onChange={(v) => updateOption('coverageGoodThreshold', Math.min(100, Math.max(0, v)))}
                min={0}
                max={100}
                label="Good Threshold"
                suffix="%"
              />
              <NumberInput
                value={options.coverageWarningThreshold}
                onChange={(v) => updateOption('coverageWarningThreshold', Math.min(100, Math.max(0, v)))}
                min={0}
                max={100}
                label="Warning Threshold"
                suffix="%"
              />
            </div>
          </div>
        )}
      </div>

      {/* Recommendations Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Lightbulb}
          title="Recommendations"
          description="Filter which recommendations to display"
          isOpen={openSections.has('recommendations')}
          onToggle={() => toggleSection('recommendations')}
        />
        {openSections.has('recommendations') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showRecommendations}
              onChange={(v) => updateOption('showRecommendations', v)}
              label="Show Recommendations"
              description="Display actionable recommendations"
            />
            {options.showRecommendations && (
              <>
                <div>
                  <span className="text-sm text-zinc-300 block mb-2">Recommendation Types</span>
                  <ChipSelect
                    options={RECOMMENDATION_TYPE_CONFIG.map(c => c.type)}
                    selected={options.recommendationTypes}
                    onChange={(v) => updateOption('recommendationTypes', v)}
                    getLabel={(t) => RECOMMENDATION_TYPE_CONFIG.find(c => c.type === t)?.label || t}
                    getIcon={(t) => getRecommendationTypeIcon(t)}
                  />
                </div>
                <div>
                  <span className="text-sm text-zinc-300 block mb-2">Severity Levels</span>
                  <ChipSelect
                    options={RECOMMENDATION_SEVERITY_CONFIG.map(c => c.severity)}
                    selected={options.recommendationSeverities}
                    onChange={(v) => updateOption('recommendationSeverities', v)}
                    getLabel={(s) => RECOMMENDATION_SEVERITY_CONFIG.find(c => c.severity === s)?.label || s}
                  />
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Coverage Display Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={BarChart3}
          title="Coverage Display"
          description="Control coverage analysis visibility"
          isOpen={openSections.has('coverage')}
          onToggle={() => toggleSection('coverage')}
        />
        {openSections.has('coverage') && (
          <div className="p-4 space-y-3 border-t border-zinc-800">
            <Toggle
              checked={options.showAreaCoverage}
              onChange={(v) => updateOption('showAreaCoverage', v)}
              label="Show Area Coverage"
              description="Coverage breakdown by test area"
            />
            <Toggle
              checked={options.showPriorityDistribution}
              onChange={(v) => updateOption('showPriorityDistribution', v)}
              label="Show Priority Distribution"
              description="Distribution by priority level"
            />
            <Toggle
              checked={options.showTypeDistribution}
              onChange={(v) => updateOption('showTypeDistribution', v)}
              label="Show Type Distribution"
              description="Automated vs manual test ratio"
            />
          </div>
        )}
      </div>

      {/* Flaky Tests & Trends Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={RefreshCw}
          title="Flaky Tests & Trends"
          description="Flaky test detection and trend analysis"
          isOpen={openSections.has('flaky')}
          onToggle={() => toggleSection('flaky')}
        />
        {openSections.has('flaky') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.detectFlakyTests}
              onChange={(v) => updateOption('detectFlakyTests', v)}
              label="Detect Flaky Tests"
              description="Identify tests with inconsistent results"
            />
            {options.detectFlakyTests && (
              <NumberInput
                value={options.flakyTestThreshold}
                onChange={(v) => updateOption('flakyTestThreshold', Math.max(10, Math.min(90, v)))}
                min={10}
                max={90}
                label="Flaky Threshold"
                suffix="%"
              />
            )}
            <Toggle
              checked={options.showTrendAnalysis}
              onChange={(v) => updateOption('showTrendAnalysis', v)}
              label="Show Trend Analysis"
              description="Display pass rate trends over time"
            />
            {options.showTrendAnalysis && (
              <NumberInput
                value={options.trendSensitivity}
                onChange={(v) => updateOption('trendSensitivity', Math.max(1, Math.min(20, v)))}
                min={1}
                max={20}
                label="Trend Sensitivity"
                suffix="%"
              />
            )}
          </div>
        )}
      </div>

      {/* Execution History Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Clock}
          title="Execution History"
          description="Recent test execution timeline"
          isOpen={openSections.has('history')}
          onToggle={() => toggleSection('history')}
        />
        {openSections.has('history') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <Toggle
              checked={options.showExecutionHistory}
              onChange={(v) => updateOption('showExecutionHistory', v)}
              label="Show Execution History"
              description="Display recent test runs"
            />
            {options.showExecutionHistory && (
              <NumberInput
                value={options.maxHistoryItems}
                onChange={(v) => updateOption('maxHistoryItems', Math.max(5, Math.min(50, v)))}
                min={5}
                max={50}
                label="Max History Items"
                suffix="items"
              />
            )}
          </div>
        )}
      </div>

      {/* Export Options Section */}
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <SectionHeader
          icon={Download}
          title="Export Options"
          description="Configure evaluation report exports"
          isOpen={openSections.has('export')}
          onToggle={() => toggleSection('export')}
        />
        {openSections.has('export') && (
          <div className="p-4 space-y-4 border-t border-zinc-800">
            <div>
              <span className="text-sm text-zinc-300 block mb-2">Export Format</span>
              <div className="flex gap-2">
                {(['json', 'csv', 'pdf'] as ExportFormat[]).map((format) => (
                  <button
                    key={format}
                    onClick={() => updateOption('exportFormat', format)}
                    className={cn(
                      'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors uppercase',
                      options.exportFormat === format
                        ? 'bg-purple-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-700'
                    )}
                  >
                    {format}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-3 pt-2">
              <Toggle
                checked={options.includeCharts}
                onChange={(v) => updateOption('includeCharts', v)}
                label="Include Charts"
                description="Add visual charts to export"
              />
              <Toggle
                checked={options.includeRecommendations}
                onChange={(v) => updateOption('includeRecommendations', v)}
                label="Include Recommendations"
                description="Add recommendations to export"
              />
              <Toggle
                checked={options.includeHistory}
                onChange={(v) => updateOption('includeHistory', v)}
                label="Include History"
                description="Add execution history to export"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default EvaluationOptionsPanel;
