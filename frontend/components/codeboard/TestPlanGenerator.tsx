'use client';

/**
 * Test Plan Generator - CB-831
 * A comprehensive UI component for generating AI-powered test plans
 *
 * Features:
 * - Issue browser with search and filtering
 * - Multiple test plan templates
 * - Preview before generation
 * - Streaming progress updates
 * - Customization options
 */

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  X, Search, ClipboardCheck, ChevronRight, CheckCircle2, Circle,
  Sparkles, FileText, Settings2, Play, ArrowLeft, ArrowRight,
  Zap, Shield, Eye, Gauge, Accessibility, Puzzle, Bug, Layers,
  RefreshCw, AlertCircle, Check, ChevronDown, Beaker, Tag, Hash,
  ToggleLeft, ToggleRight, Info, Monitor, Smartphone, Tablet,
  Globe, Database, Clock, ListChecks, Trash2, Server, GitBranch,
  AlertTriangle, Users, LayoutGrid
} from 'lucide-react';
import { Issue, IssueStatus, ISSUE_TYPES, STATUS_COLUMNS, PRIORITIES } from '@/types/codeboard';
import { useStreamingQAPlanGeneration } from '@/hooks/useQABoard';
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface TestPlanGeneratorProps {
  isOpen: boolean;
  onClose: () => void;
  issues: Issue[];
  projectId: string;
  preSelectedIssueId?: string;
  onSuccess?: (result: { issueId: string; tasksCreated: number; taskKeys: string[] }) => void;
}

type WizardStep = 'issue' | 'template' | 'customize' | 'preview' | 'generating';

type TestingLevel = 'basic' | 'standard' | 'comprehensive';

type TestArea = 'functional' | 'ui' | 'integration' | 'performance' | 'security' | 'accessibility';

type TestPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

type TestType = 'AUTOMATED' | 'MANUAL' | 'MIXED';

// Environment options for test generation
type BrowserTarget = 'chrome' | 'firefox' | 'safari' | 'edge' | 'all';
type DeviceTarget = 'desktop' | 'tablet' | 'mobile' | 'all';

// Test complexity levels
type TestComplexity = 'simple' | 'moderate' | 'detailed';

// Advanced options for test generation
interface AdvancedOptions {
  // Test scope options
  includeEdgeCases: boolean;
  includeNegativeTesting: boolean;
  includeBoundaryTesting: boolean;
  includeHappyPath: boolean;

  // Output preferences
  defaultPriority: TestPriority;
  preferredTestType: TestType;

  // Organization
  testKeyPrefix: string;
  autoTags: string[];

  // Environment options
  targetBrowsers: BrowserTarget[];
  targetDevices: DeviceTarget[];
  includeResponsiveTests: boolean;

  // Test data options
  includeDataVariations: boolean;
  includeLocalization: boolean;
  locales: string[];

  // Execution options
  estimateExecutionTime: boolean;
  includePrerequisites: boolean;
  includeCleanupSteps: boolean;

  // Test depth and complexity options
  testComplexity: TestComplexity;
  includeApiTests: boolean;
  includeDataIntegrityTests: boolean;
  includeErrorRecoveryTests: boolean;
  includeConcurrencyTests: boolean;
  includeStateManagementTests: boolean;
}

const DEFAULT_ADVANCED_OPTIONS: AdvancedOptions = {
  includeEdgeCases: true,
  includeNegativeTesting: true,
  includeBoundaryTesting: false,
  includeHappyPath: true,
  defaultPriority: 'MEDIUM',
  preferredTestType: 'AUTOMATED',
  testKeyPrefix: '',
  autoTags: [],
  // Environment options
  targetBrowsers: ['all'],
  targetDevices: ['desktop'],
  includeResponsiveTests: false,
  // Test data options
  includeDataVariations: false,
  includeLocalization: false,
  locales: [],
  // Execution options
  estimateExecutionTime: true,
  includePrerequisites: true,
  includeCleanupSteps: false,
  // Test depth and complexity options
  testComplexity: 'moderate',
  includeApiTests: false,
  includeDataIntegrityTests: false,
  includeErrorRecoveryTests: false,
  includeConcurrencyTests: false,
  includeStateManagementTests: false,
};

// Test complexity configuration
const TEST_COMPLEXITY_OPTIONS: { value: TestComplexity; label: string; description: string }[] = [
  { value: 'simple', label: 'Simple', description: 'Basic steps, single assertions' },
  { value: 'moderate', label: 'Moderate', description: 'Multi-step scenarios with validations' },
  { value: 'detailed', label: 'Detailed', description: 'Comprehensive steps with edge cases' },
];

// Browser options configuration
const BROWSER_OPTIONS: { value: BrowserTarget; label: string }[] = [
  { value: 'all', label: 'All Browsers' },
  { value: 'chrome', label: 'Chrome' },
  { value: 'firefox', label: 'Firefox' },
  { value: 'safari', label: 'Safari' },
  { value: 'edge', label: 'Edge' },
];

// Device options configuration
const DEVICE_OPTIONS: { value: DeviceTarget; label: string }[] = [
  { value: 'all', label: 'All Devices' },
  { value: 'desktop', label: 'Desktop' },
  { value: 'tablet', label: 'Tablet' },
  { value: 'mobile', label: 'Mobile' },
];

// Common locales for localization testing
const LOCALE_OPTIONS: { value: string; label: string }[] = [
  { value: 'en-US', label: 'English (US)' },
  { value: 'en-GB', label: 'English (UK)' },
  { value: 'es-ES', label: 'Spanish' },
  { value: 'fr-FR', label: 'French' },
  { value: 'de-DE', label: 'German' },
  { value: 'ja-JP', label: 'Japanese' },
  { value: 'zh-CN', label: 'Chinese (Simplified)' },
  { value: 'pt-BR', label: 'Portuguese (Brazil)' },
  { value: 'ar-SA', label: 'Arabic' },
];

interface TestPlanTemplate {
  id: string;
  name: string;
  description: string;
  level: TestingLevel;
  areas: TestArea[];
  cycles: number;
  icon: React.ReactNode;
  estimatedTasks: string;
  recommended?: boolean;
}

interface TestAreaConfig {
  id: TestArea;
  name: string;
  description: string;
  icon: React.ReactNode;
  color: string;
}

// ==================== Configuration ====================

const TEST_AREAS: TestAreaConfig[] = [
  {
    id: 'functional',
    name: 'Functional',
    description: 'Core feature functionality and business logic validation',
    icon: <Puzzle className="w-4 h-4" />,
    color: 'text-blue-400 bg-blue-900/30',
  },
  {
    id: 'ui',
    name: 'UI/UX',
    description: 'User interface interactions and visual regression',
    icon: <Eye className="w-4 h-4" />,
    color: 'text-purple-400 bg-purple-900/30',
  },
  {
    id: 'integration',
    name: 'Integration',
    description: 'API endpoints, services, and component interactions',
    icon: <Zap className="w-4 h-4" />,
    color: 'text-yellow-400 bg-yellow-900/30',
  },
  {
    id: 'performance',
    name: 'Performance',
    description: 'Load times, responsiveness, and resource usage',
    icon: <Gauge className="w-4 h-4" />,
    color: 'text-orange-400 bg-orange-900/30',
  },
  {
    id: 'security',
    name: 'Security',
    description: 'Authentication, authorization, and vulnerability testing',
    icon: <Shield className="w-4 h-4" />,
    color: 'text-red-400 bg-red-900/30',
  },
  {
    id: 'accessibility',
    name: 'Accessibility',
    description: 'WCAG compliance and assistive technology support',
    icon: <Accessibility className="w-4 h-4" />,
    color: 'text-green-400 bg-green-900/30',
  },
];

const TEST_TEMPLATES: TestPlanTemplate[] = [
  {
    id: 'quick-smoke',
    name: 'Quick Smoke Test',
    description: 'Fast verification of critical paths and core functionality',
    level: 'basic',
    areas: ['functional'],
    cycles: 1,
    icon: <Zap className="w-5 h-5" />,
    estimatedTasks: '3-5 tests',
  },
  {
    id: 'standard',
    name: 'Standard Coverage',
    description: 'Balanced testing covering main features and edge cases',
    level: 'standard',
    areas: ['functional', 'ui', 'integration'],
    cycles: 1,
    icon: <ClipboardCheck className="w-5 h-5" />,
    estimatedTasks: '8-12 tests',
    recommended: true,
  },
  {
    id: 'comprehensive',
    name: 'Comprehensive Suite',
    description: 'Full coverage including performance and security testing',
    level: 'comprehensive',
    areas: ['functional', 'ui', 'integration', 'performance', 'security'],
    cycles: 2,
    icon: <Shield className="w-5 h-5" />,
    estimatedTasks: '15-20 tests',
  },
  {
    id: 'regression',
    name: 'Regression Pack',
    description: 'Multi-cycle regression testing for stable releases',
    level: 'comprehensive',
    areas: ['functional', 'ui', 'integration'],
    cycles: 3,
    icon: <RefreshCw className="w-5 h-5" />,
    estimatedTasks: '12-18 tests',
  },
  {
    id: 'accessibility',
    name: 'Accessibility Audit',
    description: 'WCAG compliance verification and accessibility testing',
    level: 'standard',
    areas: ['ui', 'accessibility'],
    cycles: 1,
    icon: <Accessibility className="w-5 h-5" />,
    estimatedTasks: '6-10 tests',
  },
  {
    id: 'custom',
    name: 'Custom Plan',
    description: 'Build your own test plan with custom settings',
    level: 'standard',
    areas: ['functional', 'ui'],
    cycles: 1,
    icon: <Settings2 className="w-5 h-5" />,
    estimatedTasks: 'Varies',
  },
];

const LEVEL_CONFIG = {
  basic: { label: 'Basic', taskRange: '3-5', color: 'text-green-400' },
  standard: { label: 'Standard', taskRange: '8-12', color: 'text-blue-400' },
  comprehensive: { label: 'Comprehensive', taskRange: '15-20', color: 'text-purple-400' },
};

const PRIORITY_OPTIONS: { value: TestPriority; label: string; color: string }[] = [
  { value: 'LOW', label: 'Low', color: 'text-zinc-400' },
  { value: 'MEDIUM', label: 'Medium', color: 'text-yellow-400' },
  { value: 'HIGH', label: 'High', color: 'text-orange-400' },
  { value: 'CRITICAL', label: 'Critical', color: 'text-red-400' },
];

const TEST_TYPE_OPTIONS: { value: TestType; label: string; description: string }[] = [
  { value: 'AUTOMATED', label: 'Automated', description: 'AI-executable tests only' },
  { value: 'MANUAL', label: 'Manual', description: 'Human verification tests only' },
  { value: 'MIXED', label: 'Mixed', description: 'Both automated and manual tests' },
];

const TEST_SCOPE_OPTIONS: { key: keyof Pick<AdvancedOptions, 'includeEdgeCases' | 'includeNegativeTesting' | 'includeBoundaryTesting' | 'includeHappyPath'>; label: string; description: string }[] = [
  { key: 'includeHappyPath', label: 'Happy Path', description: 'Standard successful scenarios' },
  { key: 'includeEdgeCases', label: 'Edge Cases', description: 'Unusual but valid inputs' },
  { key: 'includeNegativeTesting', label: 'Negative Testing', description: 'Invalid inputs & error handling' },
  { key: 'includeBoundaryTesting', label: 'Boundary Testing', description: 'Min/max value boundaries' },
];

// ==================== Sub-components ====================

// Issue browser for step 1
function IssueBrowser({
  issues,
  selectedIssueId,
  onSelect,
}: {
  issues: Issue[];
  selectedIssueId: string | null;
  onSelect: (issue: Issue) => void;
}) {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Filter issues (only show FEATURE, EPIC, STORY types which are good for test plans)
  const filteredIssues = useMemo(() => {
    const allowedTypes = ['FEATURE', 'EPIC', 'STORY'];
    return issues.filter(issue => {
      const normalizedType = issue.type?.toUpperCase() || 'TASK';
      if (!allowedTypes.includes(normalizedType)) return false;
      if (typeFilter !== 'ALL' && normalizedType !== typeFilter) return false;
      if (search) {
        const searchLower = search.toLowerCase();
        return (
          issue.title.toLowerCase().includes(searchLower) ||
          issue.key.toLowerCase().includes(searchLower) ||
          issue.description?.toLowerCase().includes(searchLower)
        );
      }
      return true;
    });
  }, [issues, search, typeFilter]);

  // Focus search on mount
  useEffect(() => {
    searchInputRef.current?.focus();
  }, []);

  const getTypeConfig = (type: string) => {
    const normalizedType = type?.toUpperCase() || 'TASK';
    switch (normalizedType) {
      case 'FEATURE': return { color: 'text-blue-400 bg-blue-900/30', icon: '🚀' };
      case 'EPIC': return { color: 'text-purple-400 bg-purple-900/30', icon: '⚡' };
      case 'STORY': return { color: 'text-green-400 bg-green-900/30', icon: '📖' };
      default: return { color: 'text-zinc-400 bg-zinc-800', icon: '📋' };
    }
  };

  return (
    <div className="space-y-4">
      {/* Search and filters */}
      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            ref={searchInputRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search issues by title, key, or description..."
            className="w-full pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                       text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="px-3 py-2 text-sm bg-zinc-800 border border-zinc-700 rounded-lg
                     focus:outline-none focus:border-blue-500"
        >
          <option value="ALL">All Types</option>
          <option value="FEATURE">Features</option>
          <option value="EPIC">Epics</option>
          <option value="STORY">Stories</option>
        </select>
      </div>

      {/* Issue list */}
      <div className="max-h-[400px] overflow-y-auto border border-zinc-700 rounded-lg divide-y divide-zinc-800">
        {filteredIssues.length === 0 ? (
          <div className="py-12 text-center text-zinc-500">
            <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No matching issues found</p>
            <p className="text-xs mt-1">Try adjusting your search or filters</p>
          </div>
        ) : (
          filteredIssues.map(issue => {
            const typeConfig = getTypeConfig(issue.type);
            const isSelected = selectedIssueId === issue.id;

            return (
              <button
                key={issue.id}
                onClick={() => onSelect(issue)}
                className={cn(
                  'w-full px-4 py-3 flex items-center gap-3 text-left transition-colors',
                  'hover:bg-zinc-800/70',
                  isSelected && 'bg-zinc-800 border-l-2 border-blue-500'
                )}
              >
                {/* Selection indicator */}
                <div className="flex-shrink-0">
                  {isSelected ? (
                    <CheckCircle2 className="w-5 h-5 text-blue-500" />
                  ) : (
                    <Circle className="w-5 h-5 text-zinc-600" />
                  )}
                </div>

                {/* Issue info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn('px-1.5 py-0.5 text-xs rounded', typeConfig.color)}>
                      {typeConfig.icon} {issue.type?.toUpperCase()}
                    </span>
                    <span className="font-mono text-xs text-zinc-500">{issue.key}</span>
                  </div>
                  <p className="mt-1 text-sm text-zinc-200 truncate">{issue.title}</p>
                  {issue.description && (
                    <p className="mt-0.5 text-xs text-zinc-500 truncate">{issue.description}</p>
                  )}
                </div>

                {/* Arrow */}
                <ChevronRight className="w-4 h-4 text-zinc-600 flex-shrink-0" />
              </button>
            );
          })
        )}
      </div>

      <p className="text-xs text-zinc-500 text-center">
        {filteredIssues.length} issue{filteredIssues.length !== 1 ? 's' : ''} available for test plan generation
      </p>
    </div>
  );
}

// Template selector for step 2
function TemplateSelector({
  selectedTemplate,
  onSelect,
  wantsCustomization,
  onWantsCustomizationChange,
}: {
  selectedTemplate: TestPlanTemplate | null;
  onSelect: (template: TestPlanTemplate) => void;
  wantsCustomization: boolean;
  onWantsCustomizationChange: (wants: boolean) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {TEST_TEMPLATES.map(template => {
          const isSelected = selectedTemplate?.id === template.id;
          const levelConfig = LEVEL_CONFIG[template.level];

          return (
            <button
              key={template.id}
              onClick={() => onSelect(template)}
              className={cn(
                'relative p-4 rounded-lg border text-left transition-all',
                'hover:border-zinc-600',
                isSelected
                  ? 'border-blue-500 bg-blue-500/10 ring-1 ring-blue-500/20'
                  : 'border-zinc-700 bg-zinc-800/50'
              )}
            >
              {/* Recommended badge */}
              {template.recommended && (
                <span className="absolute top-2 right-2 px-1.5 py-0.5 text-[10px] font-medium
                               bg-amber-500/20 text-amber-400 rounded">
                  RECOMMENDED
                </span>
              )}

              {/* Icon and name */}
              <div className="flex items-center gap-2 mb-2">
                <span className={cn(
                  'p-1.5 rounded',
                  isSelected ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-700 text-zinc-400'
                )}>
                  {template.icon}
                </span>
                <span className="font-medium text-zinc-100">{template.name}</span>
              </div>

              {/* Description */}
              <p className="text-xs text-zinc-400 mb-3 line-clamp-2">
                {template.description}
              </p>

              {/* Stats */}
              <div className="flex items-center gap-3 text-xs">
                <span className={levelConfig.color}>{levelConfig.label}</span>
                <span className="text-zinc-500">•</span>
                <span className="text-zinc-400">{template.estimatedTasks}</span>
                <span className="text-zinc-500">•</span>
                <span className="text-zinc-400">{template.cycles} cycle{template.cycles > 1 ? 's' : ''}</span>
              </div>

              {/* Selected indicator */}
              {isSelected && (
                <div className="absolute top-4 left-4">
                  <CheckCircle2 className="w-5 h-5 text-blue-500" />
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Customize Options Toggle - shown for non-custom templates */}
      {selectedTemplate && selectedTemplate.id !== 'custom' && (
        <div className="mt-4 p-3 bg-zinc-800/50 rounded-lg border border-zinc-700">
          <label className="flex items-center justify-between cursor-pointer">
            <div className="flex items-center gap-2">
              <Settings2 className="w-4 h-4 text-zinc-400" />
              <span className="text-sm text-zinc-300">Customize generation options</span>
            </div>
            <button
              type="button"
              onClick={() => onWantsCustomizationChange(!wantsCustomization)}
              className={cn(
                'relative w-10 h-5 rounded-full transition-colors',
                wantsCustomization ? 'bg-blue-600' : 'bg-zinc-700'
              )}
            >
              <span
                className={cn(
                  'absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform',
                  wantsCustomization ? 'left-5' : 'left-0.5'
                )}
              />
            </button>
          </label>
          <p className="text-xs text-zinc-500 mt-1.5 ml-6">
            {wantsCustomization
              ? 'You can adjust testing level, areas, cycles, and add custom instructions'
              : 'Enable to fine-tune the template settings before generation'}
          </p>
        </div>
      )}
    </div>
  );
}

// Customization panel for step 3
function CustomizationPanel({
  template,
  level,
  areas,
  cycles,
  notes,
  onLevelChange,
  onAreasChange,
  onCyclesChange,
  onNotesChange,
}: {
  template: TestPlanTemplate;
  level: TestingLevel;
  areas: TestArea[];
  cycles: number;
  notes: string;
  onLevelChange: (level: TestingLevel) => void;
  onAreasChange: (areas: TestArea[]) => void;
  onCyclesChange: (cycles: number) => void;
  onNotesChange: (notes: string) => void;
}) {
  const toggleArea = (area: TestArea) => {
    if (areas.includes(area)) {
      onAreasChange(areas.filter(a => a !== area));
    } else {
      onAreasChange([...areas, area]);
    }
  };

  return (
    <div className="space-y-6">
      {/* Testing Level */}
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">Testing Level</label>
        <div className="grid grid-cols-3 gap-2">
          {(Object.keys(LEVEL_CONFIG) as TestingLevel[]).map(lvl => {
            const config = LEVEL_CONFIG[lvl];
            const isSelected = level === lvl;

            return (
              <button
                key={lvl}
                onClick={() => onLevelChange(lvl)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-center transition-all',
                  isSelected
                    ? 'border-blue-500 bg-blue-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <span className={cn('text-sm font-medium', isSelected ? 'text-blue-400' : 'text-zinc-300')}>
                  {config.label}
                </span>
                <p className="text-xs text-zinc-500 mt-0.5">{config.taskRange} tests</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Test Areas */}
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">Test Areas</label>
        <div className="grid grid-cols-2 gap-2">
          {TEST_AREAS.map(area => {
            const isSelected = areas.includes(area.id);

            return (
              <button
                key={area.id}
                onClick={() => toggleArea(area.id)}
                className={cn(
                  'px-3 py-2.5 rounded-lg border text-left transition-all flex items-center gap-2',
                  isSelected
                    ? 'border-blue-500 bg-blue-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <span className={cn('p-1 rounded', area.color)}>
                  {area.icon}
                </span>
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', isSelected ? 'text-blue-300' : 'text-zinc-300')}>
                    {area.name}
                  </span>
                </div>
                {isSelected && <Check className="w-4 h-4 text-blue-500 flex-shrink-0" />}
              </button>
            );
          })}
        </div>
        {areas.length === 0 && (
          <p className="text-xs text-red-400 mt-2">Please select at least one test area</p>
        )}
      </div>

      {/* Test Cycles */}
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">Test Cycles</label>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min="1"
            max="5"
            value={cycles}
            onChange={(e) => onCyclesChange(Number(e.target.value))}
            className="flex-1 accent-blue-500"
          />
          <span className="text-2xl font-bold text-white w-8 text-center">{cycles}</span>
        </div>
        <p className="text-xs text-zinc-500 mt-2">
          {cycles === 1
            ? 'Single execution cycle for one-time validation'
            : cycles === 2
            ? 'Two cycles with regression validation'
            : `${cycles} cycles for comprehensive iterative testing`}
        </p>
      </div>

      {/* Additional Notes */}
      <div>
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          Additional Instructions (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          placeholder="Any specific requirements, edge cases to focus on, or areas to skip..."
          rows={3}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                     text-sm resize-none focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20"
        />
      </div>
    </div>
  );
}

// Advanced Options Panel (collapsible)
function AdvancedOptionsPanel({
  options,
  onChange,
}: {
  options: AdvancedOptions;
  onChange: (options: AdvancedOptions) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [tagInput, setTagInput] = useState('');

  const updateOption = <K extends keyof AdvancedOptions>(key: K, value: AdvancedOptions[K]) => {
    onChange({ ...options, [key]: value });
  };

  const addTag = () => {
    const tag = tagInput.trim().toLowerCase().replace(/[^a-z0-9-]/g, '-');
    if (tag && !options.autoTags.includes(tag)) {
      updateOption('autoTags', [...options.autoTags, tag]);
    }
    setTagInput('');
  };

  const removeTag = (tag: string) => {
    updateOption('autoTags', options.autoTags.filter(t => t !== tag));
  };

  return (
    <div className="mt-6 border border-zinc-700 rounded-lg overflow-hidden">
      {/* Header - Toggle */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between bg-zinc-800/50 hover:bg-zinc-800 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-zinc-400" />
          <span className="text-sm font-medium text-zinc-300">Advanced Options</span>
          <span className="text-xs text-zinc-500">(optional)</span>
        </div>
        <ChevronDown className={cn(
          'w-4 h-4 text-zinc-400 transition-transform',
          isExpanded && 'rotate-180'
        )} />
      </button>

      {/* Expandable Content */}
      {isExpanded && (
        <div className="p-4 space-y-6 border-t border-zinc-700 bg-zinc-900/30">
          {/* Test Scope Options */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Beaker className="w-4 h-4 text-blue-400" />
              <label className="text-sm font-medium text-zinc-300">Test Scope</label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {TEST_SCOPE_OPTIONS.map(scope => {
                const isEnabled = options[scope.key];
                return (
                  <button
                    key={scope.key}
                    onClick={() => updateOption(scope.key, !isEnabled)}
                    className={cn(
                      'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                      isEnabled
                        ? 'border-blue-500 bg-blue-500/10'
                        : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                    )}
                  >
                    <div className="flex-shrink-0">
                      {isEnabled ? (
                        <ToggleRight className="w-4 h-4 text-blue-500" />
                      ) : (
                        <ToggleLeft className="w-4 h-4 text-zinc-500" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className={cn('text-sm', isEnabled ? 'text-blue-300' : 'text-zinc-400')}>
                        {scope.label}
                      </span>
                      <p className="text-xs text-zinc-500 truncate">{scope.description}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Output Preferences */}
          <div className="grid grid-cols-2 gap-4">
            {/* Default Priority */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Default Priority
              </label>
              <select
                value={options.defaultPriority}
                onChange={(e) => updateOption('defaultPriority', e.target.value as TestPriority)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                           text-sm focus:outline-none focus:border-blue-500"
              >
                {PRIORITY_OPTIONS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            {/* Test Type */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Test Type
              </label>
              <select
                value={options.preferredTestType}
                onChange={(e) => updateOption('preferredTestType', e.target.value as TestType)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                           text-sm focus:outline-none focus:border-blue-500"
              >
                {TEST_TYPE_OPTIONS.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                {TEST_TYPE_OPTIONS.find(t => t.value === options.preferredTestType)?.description}
              </p>
            </div>
          </div>

          {/* Naming & Organization */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Hash className="w-4 h-4 text-purple-400" />
              <label className="text-sm font-medium text-zinc-300">Naming & Organization</label>
            </div>

            {/* Test Key Prefix */}
            <div className="mb-4">
              <label className="block text-xs text-zinc-400 mb-1.5">
                Test Key Prefix (optional)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={options.testKeyPrefix}
                  onChange={(e) => updateOption('testKeyPrefix', e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, ''))}
                  placeholder="e.g., AUTH, CART"
                  maxLength={10}
                  className="flex-1 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg
                             text-sm focus:outline-none focus:border-blue-500 font-mono"
                />
                {options.testKeyPrefix && (
                  <span className="text-xs text-zinc-500">
                    Preview: <span className="font-mono text-zinc-300">QA-{options.testKeyPrefix}-001</span>
                  </span>
                )}
              </div>
            </div>

            {/* Auto Tags */}
            <div>
              <label className="block text-xs text-zinc-400 mb-1.5">
                Auto Tags (applied to all generated tests)
              </label>
              <div className="flex items-center gap-2 mb-2">
                <div className="flex-1 relative">
                  <Tag className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
                  <input
                    type="text"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
                    placeholder="Add a tag..."
                    maxLength={20}
                    className="w-full pl-9 pr-4 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg
                               text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <button
                  onClick={addTag}
                  disabled={!tagInput.trim()}
                  className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-sm rounded-lg
                             disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Add
                </button>
              </div>
              {options.autoTags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {options.autoTags.map(tag => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded"
                    >
                      #{tag}
                      <button
                        onClick={() => removeTag(tag)}
                        className="hover:text-purple-100"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Environment & Device Options */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Monitor className="w-4 h-4 text-cyan-400" />
              <label className="text-sm font-medium text-zinc-300">Environment & Devices</label>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4">
              {/* Target Browsers */}
              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">Target Browsers</label>
                <div className="flex flex-wrap gap-1.5">
                  {BROWSER_OPTIONS.map(browser => {
                    const isSelected = options.targetBrowsers.includes(browser.value);
                    const isAll = browser.value === 'all';
                    return (
                      <button
                        key={browser.value}
                        onClick={() => {
                          if (isAll) {
                            updateOption('targetBrowsers', ['all']);
                          } else {
                            const filtered = options.targetBrowsers.filter(b => b !== 'all');
                            if (isSelected) {
                              const newBrowsers = filtered.filter(b => b !== browser.value);
                              updateOption('targetBrowsers', newBrowsers.length ? newBrowsers : ['all']);
                            } else {
                              updateOption('targetBrowsers', [...filtered, browser.value]);
                            }
                          }
                        }}
                        className={cn(
                          'px-2 py-1 text-xs rounded border transition-colors',
                          isSelected
                            ? 'border-cyan-500 bg-cyan-500/20 text-cyan-300'
                            : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                        )}
                      >
                        {browser.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Target Devices */}
              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">Target Devices</label>
                <div className="flex flex-wrap gap-1.5">
                  {DEVICE_OPTIONS.map(device => {
                    const isSelected = options.targetDevices.includes(device.value);
                    const isAll = device.value === 'all';
                    const DeviceIcon = device.value === 'mobile' ? Smartphone :
                                      device.value === 'tablet' ? Tablet : Monitor;
                    return (
                      <button
                        key={device.value}
                        onClick={() => {
                          if (isAll) {
                            updateOption('targetDevices', ['all']);
                          } else {
                            const filtered = options.targetDevices.filter(d => d !== 'all');
                            if (isSelected) {
                              const newDevices = filtered.filter(d => d !== device.value);
                              updateOption('targetDevices', newDevices.length ? newDevices : ['all']);
                            } else {
                              updateOption('targetDevices', [...filtered, device.value]);
                            }
                          }
                        }}
                        className={cn(
                          'px-2 py-1 text-xs rounded border transition-colors flex items-center gap-1',
                          isSelected
                            ? 'border-cyan-500 bg-cyan-500/20 text-cyan-300'
                            : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                        )}
                      >
                        {!isAll && <DeviceIcon className="w-3 h-3" />}
                        {device.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Responsive Testing Toggle */}
            <button
              onClick={() => updateOption('includeResponsiveTests', !options.includeResponsiveTests)}
              className={cn(
                'w-full px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                options.includeResponsiveTests
                  ? 'border-cyan-500 bg-cyan-500/10'
                  : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
              )}
            >
              <div className="flex-shrink-0">
                {options.includeResponsiveTests ? (
                  <ToggleRight className="w-4 h-4 text-cyan-500" />
                ) : (
                  <ToggleLeft className="w-4 h-4 text-zinc-500" />
                )}
              </div>
              <div className="flex-1">
                <span className={cn('text-sm', options.includeResponsiveTests ? 'text-cyan-300' : 'text-zinc-400')}>
                  Include Responsive Tests
                </span>
                <p className="text-xs text-zinc-500">Add tests for responsive breakpoints and layout changes</p>
              </div>
            </button>
          </div>

          {/* Test Data Options */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Database className="w-4 h-4 text-green-400" />
              <label className="text-sm font-medium text-zinc-300">Test Data Options</label>
            </div>

            <div className="space-y-2">
              {/* Data Variations Toggle */}
              <button
                onClick={() => updateOption('includeDataVariations', !options.includeDataVariations)}
                className={cn(
                  'w-full px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.includeDataVariations
                    ? 'border-green-500 bg-green-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <div className="flex-shrink-0">
                  {options.includeDataVariations ? (
                    <ToggleRight className="w-4 h-4 text-green-500" />
                  ) : (
                    <ToggleLeft className="w-4 h-4 text-zinc-500" />
                  )}
                </div>
                <div className="flex-1">
                  <span className={cn('text-sm', options.includeDataVariations ? 'text-green-300' : 'text-zinc-400')}>
                    Include Data Variations
                  </span>
                  <p className="text-xs text-zinc-500">Generate tests with different data sets and scenarios</p>
                </div>
              </button>

              {/* Localization Toggle */}
              <button
                onClick={() => updateOption('includeLocalization', !options.includeLocalization)}
                className={cn(
                  'w-full px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.includeLocalization
                    ? 'border-green-500 bg-green-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <div className="flex-shrink-0">
                  {options.includeLocalization ? (
                    <ToggleRight className="w-4 h-4 text-green-500" />
                  ) : (
                    <ToggleLeft className="w-4 h-4 text-zinc-500" />
                  )}
                </div>
                <div className="flex-1">
                  <span className={cn('text-sm', options.includeLocalization ? 'text-green-300' : 'text-zinc-400')}>
                    Include Localization Testing
                  </span>
                  <p className="text-xs text-zinc-500">Add tests for multi-language and locale support</p>
                </div>
              </button>

              {/* Locale Selection - shown when localization is enabled */}
              {options.includeLocalization && (
                <div className="ml-6 mt-2">
                  <label className="block text-xs text-zinc-400 mb-1.5">Target Locales</label>
                  <div className="flex flex-wrap gap-1.5">
                    {LOCALE_OPTIONS.map(locale => {
                      const isSelected = options.locales.includes(locale.value);
                      return (
                        <button
                          key={locale.value}
                          onClick={() => {
                            if (isSelected) {
                              updateOption('locales', options.locales.filter(l => l !== locale.value));
                            } else {
                              updateOption('locales', [...options.locales, locale.value]);
                            }
                          }}
                          className={cn(
                            'px-2 py-1 text-xs rounded border transition-colors flex items-center gap-1',
                            isSelected
                              ? 'border-green-500 bg-green-500/20 text-green-300'
                              : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                          )}
                        >
                          <Globe className="w-3 h-3" />
                          {locale.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Execution Options */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <ListChecks className="w-4 h-4 text-amber-400" />
              <label className="text-sm font-medium text-zinc-300">Execution Options</label>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {/* Time Estimates */}
              <button
                onClick={() => updateOption('estimateExecutionTime', !options.estimateExecutionTime)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.estimateExecutionTime
                    ? 'border-amber-500 bg-amber-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <Clock className={cn('w-4 h-4', options.estimateExecutionTime ? 'text-amber-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.estimateExecutionTime ? 'text-amber-300' : 'text-zinc-400')}>
                    Time Estimates
                  </span>
                  <p className="text-xs text-zinc-500 truncate">Add execution time estimates</p>
                </div>
              </button>

              {/* Prerequisites */}
              <button
                onClick={() => updateOption('includePrerequisites', !options.includePrerequisites)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.includePrerequisites
                    ? 'border-amber-500 bg-amber-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <ListChecks className={cn('w-4 h-4', options.includePrerequisites ? 'text-amber-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.includePrerequisites ? 'text-amber-300' : 'text-zinc-400')}>
                    Prerequisites
                  </span>
                  <p className="text-xs text-zinc-500 truncate">Include setup requirements</p>
                </div>
              </button>

              {/* Cleanup Steps */}
              <button
                onClick={() => updateOption('includeCleanupSteps', !options.includeCleanupSteps)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2 col-span-2',
                  options.includeCleanupSteps
                    ? 'border-amber-500 bg-amber-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <Trash2 className={cn('w-4 h-4', options.includeCleanupSteps ? 'text-amber-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.includeCleanupSteps ? 'text-amber-300' : 'text-zinc-400')}>
                    Cleanup Steps
                  </span>
                  <p className="text-xs text-zinc-500">Include teardown/cleanup steps after each test</p>
                </div>
              </button>
            </div>
          </div>

          {/* Test Depth & Complexity */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Layers className="w-4 h-4 text-indigo-400" />
              <label className="text-sm font-medium text-zinc-300">Test Depth & Complexity</label>
            </div>

            {/* Complexity Level Selector */}
            <div className="mb-4">
              <label className="block text-xs text-zinc-400 mb-1.5">Test Complexity Level</label>
              <div className="grid grid-cols-3 gap-2">
                {TEST_COMPLEXITY_OPTIONS.map(complexity => {
                  const isSelected = options.testComplexity === complexity.value;
                  return (
                    <button
                      key={complexity.value}
                      onClick={() => updateOption('testComplexity', complexity.value)}
                      className={cn(
                        'px-3 py-2 rounded-lg border text-center transition-all',
                        isSelected
                          ? 'border-indigo-500 bg-indigo-500/10'
                          : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                      )}
                    >
                      <span className={cn('text-sm font-medium', isSelected ? 'text-indigo-300' : 'text-zinc-400')}>
                        {complexity.label}
                      </span>
                      <p className="text-xs text-zinc-500 mt-0.5">{complexity.description}</p>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Specialized Testing Options */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Server className="w-4 h-4 text-rose-400" />
              <label className="text-sm font-medium text-zinc-300">Specialized Testing</label>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {/* API Tests */}
              <button
                onClick={() => updateOption('includeApiTests', !options.includeApiTests)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.includeApiTests
                    ? 'border-rose-500 bg-rose-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <Server className={cn('w-4 h-4', options.includeApiTests ? 'text-rose-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.includeApiTests ? 'text-rose-300' : 'text-zinc-400')}>
                    API Tests
                  </span>
                  <p className="text-xs text-zinc-500 truncate">REST/GraphQL endpoint testing</p>
                </div>
              </button>

              {/* Data Integrity Tests */}
              <button
                onClick={() => updateOption('includeDataIntegrityTests', !options.includeDataIntegrityTests)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.includeDataIntegrityTests
                    ? 'border-rose-500 bg-rose-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <Database className={cn('w-4 h-4', options.includeDataIntegrityTests ? 'text-rose-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.includeDataIntegrityTests ? 'text-rose-300' : 'text-zinc-400')}>
                    Data Integrity
                  </span>
                  <p className="text-xs text-zinc-500 truncate">Database & data consistency</p>
                </div>
              </button>

              {/* Error Recovery Tests */}
              <button
                onClick={() => updateOption('includeErrorRecoveryTests', !options.includeErrorRecoveryTests)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.includeErrorRecoveryTests
                    ? 'border-rose-500 bg-rose-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <AlertTriangle className={cn('w-4 h-4', options.includeErrorRecoveryTests ? 'text-rose-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.includeErrorRecoveryTests ? 'text-rose-300' : 'text-zinc-400')}>
                    Error Recovery
                  </span>
                  <p className="text-xs text-zinc-500 truncate">Resilience & failure recovery</p>
                </div>
              </button>

              {/* Concurrency Tests */}
              <button
                onClick={() => updateOption('includeConcurrencyTests', !options.includeConcurrencyTests)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2',
                  options.includeConcurrencyTests
                    ? 'border-rose-500 bg-rose-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <Users className={cn('w-4 h-4', options.includeConcurrencyTests ? 'text-rose-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.includeConcurrencyTests ? 'text-rose-300' : 'text-zinc-400')}>
                    Concurrency
                  </span>
                  <p className="text-xs text-zinc-500 truncate">Multi-user & race conditions</p>
                </div>
              </button>

              {/* State Management Tests */}
              <button
                onClick={() => updateOption('includeStateManagementTests', !options.includeStateManagementTests)}
                className={cn(
                  'px-3 py-2 rounded-lg border text-left transition-all flex items-center gap-2 col-span-2',
                  options.includeStateManagementTests
                    ? 'border-rose-500 bg-rose-500/10'
                    : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                )}
              >
                <GitBranch className={cn('w-4 h-4', options.includeStateManagementTests ? 'text-rose-500' : 'text-zinc-500')} />
                <div className="flex-1 min-w-0">
                  <span className={cn('text-sm', options.includeStateManagementTests ? 'text-rose-300' : 'text-zinc-400')}>
                    State Management
                  </span>
                  <p className="text-xs text-zinc-500">Application state transitions and persistence</p>
                </div>
              </button>
            </div>
          </div>

          {/* Info Note */}
          <div className="flex items-start gap-2 p-3 bg-zinc-800/50 rounded-lg border border-zinc-700">
            <Info className="w-4 h-4 text-zinc-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-zinc-400">
              Advanced options help customize how tests are generated and organized.
              These settings are passed to the AI model to guide test creation.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// Preview panel for step 4
function PreviewPanel({
  issue,
  template,
  level,
  areas,
  cycles,
  notes,
  advancedOptions,
}: {
  issue: Issue;
  template: TestPlanTemplate;
  level: TestingLevel;
  areas: TestArea[];
  cycles: number;
  notes: string;
  advancedOptions: AdvancedOptions;
}) {
  const levelConfig = LEVEL_CONFIG[level];
  const selectedAreas = TEST_AREAS.filter(a => areas.includes(a.id));

  return (
    <div className="space-y-4">
      {/* Summary card */}
      <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
        <h4 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-400" />
          Test Plan Summary
        </h4>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-zinc-500">Target Issue:</span>
            <p className="text-zinc-200 font-mono">{issue.key}</p>
          </div>
          <div>
            <span className="text-zinc-500">Template:</span>
            <p className="text-zinc-200">{template.name}</p>
          </div>
          <div>
            <span className="text-zinc-500">Testing Level:</span>
            <p className={levelConfig.color}>{levelConfig.label}</p>
          </div>
          <div>
            <span className="text-zinc-500">Expected Tests:</span>
            <p className="text-zinc-200">{levelConfig.taskRange}</p>
          </div>
          <div>
            <span className="text-zinc-500">Test Cycles:</span>
            <p className="text-zinc-200">{cycles}</p>
          </div>
          <div>
            <span className="text-zinc-500">Test Areas:</span>
            <p className="text-zinc-200">{areas.length} selected</p>
          </div>
        </div>
      </div>

      {/* Test areas breakdown */}
      <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
        <h4 className="font-medium text-zinc-200 mb-3">Areas to Test</h4>
        <div className="flex flex-wrap gap-2">
          {selectedAreas.map(area => (
            <span
              key={area.id}
              className={cn('px-2 py-1 text-xs rounded flex items-center gap-1', area.color)}
            >
              {area.icon}
              {area.name}
            </span>
          ))}
        </div>
      </div>

      {/* Test Scope & Output Options - show if any non-default values */}
      {(advancedOptions.includeEdgeCases ||
        advancedOptions.includeNegativeTesting ||
        advancedOptions.includeBoundaryTesting ||
        advancedOptions.defaultPriority !== 'MEDIUM' ||
        advancedOptions.preferredTestType !== 'AUTOMATED' ||
        advancedOptions.testKeyPrefix ||
        advancedOptions.autoTags.length > 0) && (
        <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
          <h4 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-zinc-400" />
            Advanced Options
          </h4>

          <div className="space-y-3 text-sm">
            {/* Test Scope */}
            <div className="flex flex-wrap gap-1.5">
              {advancedOptions.includeHappyPath && (
                <span className="px-2 py-0.5 text-xs bg-green-900/30 text-green-400 rounded">Happy Path</span>
              )}
              {advancedOptions.includeEdgeCases && (
                <span className="px-2 py-0.5 text-xs bg-blue-900/30 text-blue-400 rounded">Edge Cases</span>
              )}
              {advancedOptions.includeNegativeTesting && (
                <span className="px-2 py-0.5 text-xs bg-orange-900/30 text-orange-400 rounded">Negative Testing</span>
              )}
              {advancedOptions.includeBoundaryTesting && (
                <span className="px-2 py-0.5 text-xs bg-purple-900/30 text-purple-400 rounded">Boundary Testing</span>
              )}
            </div>

            {/* Output Preferences */}
            {(advancedOptions.defaultPriority !== 'MEDIUM' || advancedOptions.preferredTestType !== 'AUTOMATED') && (
              <div className="flex items-center gap-4 text-zinc-400">
                {advancedOptions.defaultPriority !== 'MEDIUM' && (
                  <span>Priority: <span className={PRIORITY_OPTIONS.find(p => p.value === advancedOptions.defaultPriority)?.color}>{advancedOptions.defaultPriority}</span></span>
                )}
                {advancedOptions.preferredTestType !== 'AUTOMATED' && (
                  <span>Type: <span className="text-zinc-200">{advancedOptions.preferredTestType}</span></span>
                )}
              </div>
            )}

            {/* Naming/Tags */}
            {(advancedOptions.testKeyPrefix || advancedOptions.autoTags.length > 0) && (
              <div className="flex items-center gap-3 text-zinc-400">
                {advancedOptions.testKeyPrefix && (
                  <span>Prefix: <span className="font-mono text-zinc-200">{advancedOptions.testKeyPrefix}</span></span>
                )}
                {advancedOptions.autoTags.length > 0 && (
                  <span className="flex items-center gap-1">
                    Tags:
                    {advancedOptions.autoTags.map(tag => (
                      <span key={tag} className="text-purple-400">#{tag}</span>
                    ))}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Environment & Device Options - show if non-default */}
      {((!advancedOptions.targetBrowsers.includes('all') && advancedOptions.targetBrowsers.length > 0) ||
        (!advancedOptions.targetDevices.includes('all') && advancedOptions.targetDevices.length > 0) ||
        advancedOptions.includeResponsiveTests) && (
        <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
          <h4 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
            <Monitor className="w-4 h-4 text-cyan-400" />
            Environment & Devices
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {!advancedOptions.targetBrowsers.includes('all') && advancedOptions.targetBrowsers.map(browser => (
              <span key={browser} className="px-2 py-0.5 text-xs bg-cyan-900/30 text-cyan-400 rounded">
                {BROWSER_OPTIONS.find(b => b.value === browser)?.label || browser}
              </span>
            ))}
            {!advancedOptions.targetDevices.includes('all') && advancedOptions.targetDevices.map(device => (
              <span key={device} className="px-2 py-0.5 text-xs bg-cyan-900/30 text-cyan-300 rounded flex items-center gap-1">
                {device === 'mobile' && <Smartphone className="w-3 h-3" />}
                {device === 'tablet' && <Tablet className="w-3 h-3" />}
                {device === 'desktop' && <Monitor className="w-3 h-3" />}
                {DEVICE_OPTIONS.find(d => d.value === device)?.label || device}
              </span>
            ))}
            {advancedOptions.includeResponsiveTests && (
              <span className="px-2 py-0.5 text-xs bg-cyan-900/30 text-cyan-400 rounded">Responsive Tests</span>
            )}
          </div>
        </div>
      )}

      {/* Test Data Options - show if enabled */}
      {(advancedOptions.includeDataVariations || advancedOptions.includeLocalization) && (
        <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
          <h4 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
            <Database className="w-4 h-4 text-green-400" />
            Test Data Options
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {advancedOptions.includeDataVariations && (
              <span className="px-2 py-0.5 text-xs bg-green-900/30 text-green-400 rounded">Data Variations</span>
            )}
            {advancedOptions.includeLocalization && (
              <span className="px-2 py-0.5 text-xs bg-green-900/30 text-green-400 rounded flex items-center gap-1">
                <Globe className="w-3 h-3" />
                Localization
              </span>
            )}
            {advancedOptions.locales.length > 0 && advancedOptions.locales.map(locale => (
              <span key={locale} className="px-2 py-0.5 text-xs bg-green-900/30 text-green-300 rounded">
                {LOCALE_OPTIONS.find(l => l.value === locale)?.label || locale}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Execution Options - show if non-default */}
      {(advancedOptions.includeCleanupSteps || !advancedOptions.estimateExecutionTime || !advancedOptions.includePrerequisites) && (
        <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
          <h4 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-amber-400" />
            Execution Options
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {advancedOptions.estimateExecutionTime && (
              <span className="px-2 py-0.5 text-xs bg-amber-900/30 text-amber-400 rounded flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Time Estimates
              </span>
            )}
            {advancedOptions.includePrerequisites && (
              <span className="px-2 py-0.5 text-xs bg-amber-900/30 text-amber-400 rounded">Prerequisites</span>
            )}
            {advancedOptions.includeCleanupSteps && (
              <span className="px-2 py-0.5 text-xs bg-amber-900/30 text-amber-400 rounded flex items-center gap-1">
                <Trash2 className="w-3 h-3" />
                Cleanup Steps
              </span>
            )}
          </div>
        </div>
      )}

      {/* Test Depth & Complexity - show if non-default or specialized tests enabled */}
      {(advancedOptions.testComplexity !== 'moderate' ||
        advancedOptions.includeApiTests ||
        advancedOptions.includeDataIntegrityTests ||
        advancedOptions.includeErrorRecoveryTests ||
        advancedOptions.includeConcurrencyTests ||
        advancedOptions.includeStateManagementTests) && (
        <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
          <h4 className="font-medium text-zinc-200 mb-3 flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-400" />
            Test Depth & Specialized Testing
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {advancedOptions.testComplexity !== 'moderate' && (
              <span className="px-2 py-0.5 text-xs bg-indigo-900/30 text-indigo-400 rounded">
                {TEST_COMPLEXITY_OPTIONS.find(c => c.value === advancedOptions.testComplexity)?.label || advancedOptions.testComplexity} Complexity
              </span>
            )}
            {advancedOptions.includeApiTests && (
              <span className="px-2 py-0.5 text-xs bg-rose-900/30 text-rose-400 rounded flex items-center gap-1">
                <Server className="w-3 h-3" />
                API Tests
              </span>
            )}
            {advancedOptions.includeDataIntegrityTests && (
              <span className="px-2 py-0.5 text-xs bg-rose-900/30 text-rose-400 rounded flex items-center gap-1">
                <Database className="w-3 h-3" />
                Data Integrity
              </span>
            )}
            {advancedOptions.includeErrorRecoveryTests && (
              <span className="px-2 py-0.5 text-xs bg-rose-900/30 text-rose-400 rounded flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                Error Recovery
              </span>
            )}
            {advancedOptions.includeConcurrencyTests && (
              <span className="px-2 py-0.5 text-xs bg-rose-900/30 text-rose-400 rounded flex items-center gap-1">
                <Users className="w-3 h-3" />
                Concurrency
              </span>
            )}
            {advancedOptions.includeStateManagementTests && (
              <span className="px-2 py-0.5 text-xs bg-rose-900/30 text-rose-400 rounded flex items-center gap-1">
                <GitBranch className="w-3 h-3" />
                State Management
              </span>
            )}
          </div>
        </div>
      )}

      {/* Issue details */}
      <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
        <h4 className="font-medium text-zinc-200 mb-2">Issue Details</h4>
        <p className="text-sm text-zinc-300">{issue.title}</p>
        {issue.description && (
          <p className="text-xs text-zinc-500 mt-1 line-clamp-3">{issue.description}</p>
        )}
      </div>

      {/* Additional notes */}
      {notes && (
        <div className="bg-zinc-800 rounded-lg p-4 border border-zinc-700">
          <h4 className="font-medium text-zinc-200 mb-2">Additional Instructions</h4>
          <p className="text-sm text-zinc-400 whitespace-pre-wrap">{notes}</p>
        </div>
      )}

      {/* AI note */}
      <div className="bg-blue-500/10 rounded-lg p-3 border border-blue-500/20">
        <p className="text-xs text-blue-300 flex items-start gap-2">
          <Sparkles className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>
            AI will analyze the issue context and generate detailed test scenarios based on your configuration.
            Each test will include steps, expected results, and type classification.
          </span>
        </p>
      </div>
    </div>
  );
}

// Generation progress panel
function GenerationProgress({
  progress,
  message,
  error,
  issue,
  onRetry,
}: {
  progress: number;
  message: string;
  error: string | null;
  issue: Issue;
  onRetry: () => void;
}) {
  const isComplete = progress >= 100 && !error;
  const hasError = !!error;

  return (
    <div className="py-8">
      <div className="text-center mb-8">
        {/* Status icon */}
        <div className={cn(
          'inline-flex items-center justify-center w-20 h-20 rounded-full mb-4',
          hasError ? 'bg-red-500/20' : isComplete ? 'bg-green-500/20' : 'bg-blue-500/20'
        )}>
          {hasError ? (
            <AlertCircle className="w-10 h-10 text-red-500" />
          ) : isComplete ? (
            <CheckCircle2 className="w-10 h-10 text-green-500" />
          ) : (
            <div className="w-10 h-10 border-3 border-blue-500 border-t-transparent rounded-full animate-spin" />
          )}
        </div>

        {/* Status text */}
        <h3 className="text-lg font-medium text-white mb-2">
          {hasError
            ? 'Generation Failed'
            : isComplete
            ? 'Test Plan Generated!'
            : 'Generating Test Plan...'}
        </h3>
        <p className={cn('text-sm', hasError ? 'text-red-400' : 'text-zinc-400')}>
          {error || message || 'Initializing...'}
        </p>
      </div>

      {/* Progress bar */}
      <div className="max-w-md mx-auto space-y-2">
        <div className="h-3 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full transition-all duration-500 ease-out',
              hasError
                ? 'bg-red-500'
                : isComplete
                ? 'bg-gradient-to-r from-green-600 to-green-400'
                : 'bg-gradient-to-r from-blue-600 to-blue-400'
            )}
            style={{ width: `${hasError ? 100 : progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-zinc-500">
          <span>{hasError ? 'Error' : `${Math.round(progress)}%`}</span>
          <span>{hasError ? 'Failed' : isComplete ? 'Complete!' : 'Please wait...'}</span>
        </div>
      </div>

      {/* Target issue reminder */}
      <div className="mt-8 text-center">
        <p className="text-xs text-zinc-500">
          Target: <span className="text-zinc-300 font-mono">{issue.key}</span> - {issue.title}
        </p>
      </div>

      {/* Error retry button */}
      {hasError && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={onRetry}
            className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white rounded-lg
                       transition-colors flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Go Back and Retry
          </button>
        </div>
      )}
    </div>
  );
}

// ==================== Main Component ====================

export function TestPlanGenerator({
  isOpen,
  onClose,
  issues,
  projectId,
  preSelectedIssueId,
  onSuccess,
}: TestPlanGeneratorProps) {
  // Wizard state
  const [step, setStep] = useState<WizardStep>('issue');
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<TestPlanTemplate | null>(null);
  const [wantsCustomization, setWantsCustomization] = useState(false);

  // Customization state
  const [level, setLevel] = useState<TestingLevel>('standard');
  const [areas, setAreas] = useState<TestArea[]>(['functional', 'ui']);
  const [cycles, setCycles] = useState(1);
  const [notes, setNotes] = useState('');
  const [advancedOptions, setAdvancedOptions] = useState<AdvancedOptions>(DEFAULT_ADVANCED_OPTIONS);

  // Generation state
  const {
    isGenerating,
    progress,
    message,
    error,
    generate,
    reset: resetGeneration,
  } = useStreamingQAPlanGeneration();

  const toast = useToast();

  // Initialize with pre-selected issue
  useEffect(() => {
    if (preSelectedIssueId && issues.length > 0) {
      const issue = issues.find(i => i.id === preSelectedIssueId);
      if (issue) {
        setSelectedIssue(issue);
        setStep('template');
      }
    }
  }, [preSelectedIssueId, issues]);

  // Apply template settings when template is selected
  useEffect(() => {
    if (selectedTemplate) {
      setLevel(selectedTemplate.level);
      setAreas([...selectedTemplate.areas]);
      setCycles(selectedTemplate.cycles);
    }
  }, [selectedTemplate]);

  // Reset wizard when closed
  const handleClose = useCallback(() => {
    setStep('issue');
    setSelectedIssue(null);
    setSelectedTemplate(null);
    setWantsCustomization(false);
    setLevel('standard');
    setAreas(['functional', 'ui']);
    setCycles(1);
    setNotes('');
    setAdvancedOptions(DEFAULT_ADVANCED_OPTIONS);
    resetGeneration();
    onClose();
  }, [onClose, resetGeneration]);

  // Build custom instructions from wizard inputs
  const buildCustomInstructions = useCallback(() => {
    if (!selectedTemplate) return '';

    const levelConfig = LEVEL_CONFIG[level];
    const selectedAreas = TEST_AREAS.filter(a => areas.includes(a.id));

    let instructions = `## Test Plan Configuration\n\n`;
    instructions += `### Template: ${selectedTemplate.name}\n`;
    instructions += `### Testing Level: ${levelConfig.label}\n`;
    instructions += `- Target: ${levelConfig.taskRange} test cases\n\n`;

    instructions += `### Test Cycles: ${cycles}\n`;
    if (cycles > 1) {
      instructions += `- Plan should support ${cycles} execution cycles\n`;
      instructions += `- Include regression tests for subsequent cycles\n\n`;
    }

    instructions += `### Areas to Test:\n`;
    selectedAreas.forEach(area => {
      instructions += `- **${area.name}**: ${area.description}\n`;
    });

    // Add test scope preferences
    instructions += `\n### Test Scope:\n`;
    if (advancedOptions.includeHappyPath) {
      instructions += `- Include happy path scenarios (standard successful flows)\n`;
    }
    if (advancedOptions.includeEdgeCases) {
      instructions += `- Include edge cases (unusual but valid inputs)\n`;
    }
    if (advancedOptions.includeNegativeTesting) {
      instructions += `- Include negative testing (invalid inputs, error handling)\n`;
    }
    if (advancedOptions.includeBoundaryTesting) {
      instructions += `- Include boundary testing (min/max values, limits)\n`;
    }

    // Add output preferences
    instructions += `\n### Output Preferences:\n`;
    instructions += `- Default Priority: ${advancedOptions.defaultPriority}\n`;
    instructions += `- Test Type: ${advancedOptions.preferredTestType === 'MIXED'
      ? 'Generate both automated and manual tests'
      : advancedOptions.preferredTestType === 'AUTOMATED'
        ? 'Generate automated tests only'
        : 'Generate manual tests only'}\n`;

    // Add naming/organization if specified
    if (advancedOptions.testKeyPrefix) {
      instructions += `\n### Naming:\n`;
      instructions += `- Test Key Prefix: ${advancedOptions.testKeyPrefix}\n`;
    }

    if (advancedOptions.autoTags.length > 0) {
      instructions += `\n### Tags:\n`;
      instructions += `- Auto-apply tags: ${advancedOptions.autoTags.map(t => `#${t}`).join(', ')}\n`;
    }

    // Add environment/device options
    const hasBrowserTargets = advancedOptions.targetBrowsers.length > 0 && !advancedOptions.targetBrowsers.includes('all');
    const hasDeviceTargets = advancedOptions.targetDevices.length > 0 && !advancedOptions.targetDevices.includes('all');

    if (hasBrowserTargets || hasDeviceTargets || advancedOptions.includeResponsiveTests) {
      instructions += `\n### Environment & Devices:\n`;
      if (hasBrowserTargets) {
        const browserLabels = advancedOptions.targetBrowsers.map(b =>
          BROWSER_OPTIONS.find(opt => opt.value === b)?.label || b
        );
        instructions += `- Target Browsers: ${browserLabels.join(', ')}\n`;
      }
      if (hasDeviceTargets) {
        const deviceLabels = advancedOptions.targetDevices.map(d =>
          DEVICE_OPTIONS.find(opt => opt.value === d)?.label || d
        );
        instructions += `- Target Devices: ${deviceLabels.join(', ')}\n`;
      }
      if (advancedOptions.includeResponsiveTests) {
        instructions += `- Include responsive design tests for different screen sizes\n`;
      }
    }

    // Add test data options
    if (advancedOptions.includeDataVariations || advancedOptions.includeLocalization) {
      instructions += `\n### Test Data Options:\n`;
      if (advancedOptions.includeDataVariations) {
        instructions += `- Include tests with varied data sets (valid, invalid, edge case data)\n`;
      }
      if (advancedOptions.includeLocalization) {
        instructions += `- Include localization/internationalization tests\n`;
        if (advancedOptions.locales.length > 0) {
          const localeLabels = advancedOptions.locales.map(l =>
            LOCALE_OPTIONS.find(opt => opt.value === l)?.label || l
          );
          instructions += `- Target Locales: ${localeLabels.join(', ')}\n`;
        }
      }
    }

    // Add execution options
    const hasExecutionOptions = advancedOptions.estimateExecutionTime ||
                                advancedOptions.includePrerequisites ||
                                advancedOptions.includeCleanupSteps;
    if (hasExecutionOptions) {
      instructions += `\n### Execution Options:\n`;
      if (advancedOptions.estimateExecutionTime) {
        instructions += `- Include estimated execution time for each test\n`;
      }
      if (advancedOptions.includePrerequisites) {
        instructions += `- Include prerequisites/preconditions for each test\n`;
      }
      if (advancedOptions.includeCleanupSteps) {
        instructions += `- Include cleanup/teardown steps after each test\n`;
      }
    }

    // Add test depth and complexity options
    instructions += `\n### Test Depth & Complexity:\n`;
    instructions += `- Complexity Level: ${advancedOptions.testComplexity}\n`;
    const complexityDesc = TEST_COMPLEXITY_OPTIONS.find(c => c.value === advancedOptions.testComplexity);
    if (complexityDesc) {
      instructions += `  (${complexityDesc.description})\n`;
    }

    // Add specialized testing options
    const hasSpecializedTests = advancedOptions.includeApiTests ||
                                advancedOptions.includeDataIntegrityTests ||
                                advancedOptions.includeErrorRecoveryTests ||
                                advancedOptions.includeConcurrencyTests ||
                                advancedOptions.includeStateManagementTests;
    if (hasSpecializedTests) {
      instructions += `\n### Specialized Testing:\n`;
      if (advancedOptions.includeApiTests) {
        instructions += `- Include API/endpoint tests (REST/GraphQL validation, response codes, payloads)\n`;
      }
      if (advancedOptions.includeDataIntegrityTests) {
        instructions += `- Include data integrity tests (database consistency, data persistence, CRUD operations)\n`;
      }
      if (advancedOptions.includeErrorRecoveryTests) {
        instructions += `- Include error recovery tests (resilience, graceful degradation, retry mechanisms)\n`;
      }
      if (advancedOptions.includeConcurrencyTests) {
        instructions += `- Include concurrency tests (multi-user scenarios, race conditions, simultaneous operations)\n`;
      }
      if (advancedOptions.includeStateManagementTests) {
        instructions += `- Include state management tests (state transitions, persistence, undo/redo, session handling)\n`;
      }
    }

    if (notes) {
      instructions += `\n### Additional Requirements:\n${notes}\n`;
    }

    return instructions;
  }, [selectedTemplate, level, areas, cycles, notes, advancedOptions]);

  // Handle generation
  const handleGenerate = async () => {
    if (!selectedIssue) return;

    setStep('generating');

    try {
      const customInstructions = buildCustomInstructions();
      const result = await generate(
        {
          issueId: selectedIssue.id,
          customInstructions,
        },
        {
          onComplete: (result) => {
            toast.success(
              'Test Plan Generated',
              `Created ${result.qaTasksCreated} QA tasks for ${selectedIssue.key}`
            );
            onSuccess?.({
              issueId: result.issueId,
              tasksCreated: result.qaTasksCreated,
              taskKeys: result.qaTaskKeys,
            });
            // Short delay to show completion state
            setTimeout(() => {
              handleClose();
            }, 1000);
          },
          onError: (error) => {
            toast.error('Generation Failed', error || 'Failed to generate test plan');
          },
        }
      );

      if (!result) {
        // Generation was cancelled or failed without throwing
        setStep('preview');
      }
    } catch {
      // Error is already handled by the hook
      setStep('preview');
    }
  };

  // Determine if customization step should be shown
  const shouldShowCustomization = selectedTemplate?.id === 'custom' || wantsCustomization;

  // Navigation
  const canGoNext = () => {
    switch (step) {
      case 'issue': return !!selectedIssue;
      case 'template': return !!selectedTemplate;
      case 'customize': return areas.length > 0 && cycles >= 1;
      case 'preview': return true;
      default: return false;
    }
  };

  const goNext = () => {
    switch (step) {
      case 'issue': setStep('template'); break;
      case 'template':
        setStep(shouldShowCustomization ? 'customize' : 'preview');
        break;
      case 'customize': setStep('preview'); break;
      case 'preview': handleGenerate(); break;
    }
  };

  const goBack = () => {
    switch (step) {
      case 'template': setStep('issue'); break;
      case 'customize': setStep('template'); break;
      case 'preview':
        setStep(shouldShowCustomization ? 'customize' : 'template');
        break;
      case 'generating':
        resetGeneration();
        setStep('preview');
        break;
    }
  };

  if (!isOpen) return null;

  // Calculate progress
  const steps = ['issue', 'template', 'customize', 'preview', 'generating'];
  const currentStepIndex = steps.indexOf(step);
  const totalSteps = shouldShowCustomization ? 4 : 3;
  const displayStepIndex = step === 'generating'
    ? totalSteps
    : shouldShowCustomization
    ? currentStepIndex
    : currentStepIndex > 2 ? currentStepIndex - 1 : currentStepIndex;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={handleClose} />

      {/* Modal */}
      <div className="relative w-full max-w-2xl max-h-[90vh] bg-zinc-900 border border-zinc-700
                      rounded-xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-zinc-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/20 rounded-lg">
                <ClipboardCheck className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">Generate Test Plan</h2>
                <p className="text-xs text-zinc-500">Create AI-powered QA test cases</p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className="p-2 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Progress bar */}
          {step !== 'generating' && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-xs text-zinc-500 mb-2">
                <span>
                  Step {displayStepIndex + 1} of {totalSteps}
                  {step === 'issue' && ' - Select Issue'}
                  {step === 'template' && ' - Choose Template'}
                  {step === 'customize' && ' - Customize'}
                  {step === 'preview' && ' - Review & Generate'}
                </span>
                <span>{Math.round(((displayStepIndex + 1) / totalSteps) * 100)}%</span>
              </div>
              <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-600 transition-all duration-300"
                  style={{ width: `${((displayStepIndex + 1) / totalSteps) * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Step 1: Issue Selection */}
          {step === 'issue' && (
            <div>
              <h3 className="text-white font-medium mb-1">Select Issue</h3>
              <p className="text-sm text-zinc-400 mb-4">
                Choose the feature, epic, or story to generate a test plan for.
              </p>
              <IssueBrowser
                issues={issues}
                selectedIssueId={selectedIssue?.id || null}
                onSelect={setSelectedIssue}
              />
            </div>
          )}

          {/* Step 2: Template Selection */}
          {step === 'template' && (
            <div>
              <h3 className="text-white font-medium mb-1">Choose Template</h3>
              <p className="text-sm text-zinc-400 mb-4">
                Select a test plan template that best fits your testing needs.
              </p>
              <TemplateSelector
                selectedTemplate={selectedTemplate}
                onSelect={setSelectedTemplate}
                wantsCustomization={wantsCustomization}
                onWantsCustomizationChange={setWantsCustomization}
              />
            </div>
          )}

          {/* Step 3: Customization (only for custom template) */}
          {step === 'customize' && selectedTemplate && (
            <div>
              <h3 className="text-white font-medium mb-1">Customize Test Plan</h3>
              <p className="text-sm text-zinc-400 mb-4">
                Fine-tune your test plan settings.
              </p>
              <CustomizationPanel
                template={selectedTemplate}
                level={level}
                areas={areas}
                cycles={cycles}
                notes={notes}
                onLevelChange={setLevel}
                onAreasChange={setAreas}
                onCyclesChange={setCycles}
                onNotesChange={setNotes}
              />

              {/* Advanced Options - Collapsible */}
              <AdvancedOptionsPanel
                options={advancedOptions}
                onChange={setAdvancedOptions}
              />
            </div>
          )}

          {/* Step 4: Preview */}
          {step === 'preview' && selectedIssue && selectedTemplate && (
            <div>
              <h3 className="text-white font-medium mb-1">Review & Generate</h3>
              <p className="text-sm text-zinc-400 mb-4">
                Review your test plan configuration before generation.
              </p>
              <PreviewPanel
                issue={selectedIssue}
                template={selectedTemplate}
                level={level}
                areas={areas}
                cycles={cycles}
                notes={notes}
                advancedOptions={advancedOptions}
              />
            </div>
          )}

          {/* Step 5: Generation */}
          {step === 'generating' && selectedIssue && (
            <GenerationProgress
              progress={progress}
              message={message}
              error={error}
              issue={selectedIssue}
              onRetry={goBack}
            />
          )}
        </div>

        {/* Footer */}
        {step !== 'generating' && (
          <div className="flex-shrink-0 px-6 py-4 border-t border-zinc-700 flex items-center justify-between">
            <button
              onClick={step === 'issue' ? handleClose : goBack}
              className="px-4 py-2 text-zinc-400 hover:text-white transition-colors flex items-center gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              {step === 'issue' ? 'Cancel' : 'Back'}
            </button>
            <button
              onClick={goNext}
              disabled={!canGoNext()}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors
                         flex items-center gap-2"
            >
              {step === 'preview' ? (
                <>
                  <Sparkles className="w-4 h-4" />
                  Generate Test Plan
                </>
              ) : (
                <>
                  Next
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
