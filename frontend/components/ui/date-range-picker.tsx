'use client';

/**
 * DateRangePicker Component
 * A date range selection component with calendar display and preset ranges
 */

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Calendar, ChevronLeft, ChevronRight, X } from 'lucide-react';

export interface DateRange {
  start: Date | null;
  end: Date | null;
}

export interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  minDate?: Date;
  maxDate?: Date;
  showPresets?: boolean;
}

interface PresetRange {
  label: string;
  getValue: () => DateRange;
}

const getPresetRanges = (): PresetRange[] => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const endOfToday = new Date(today);
  endOfToday.setHours(23, 59, 59, 999);

  return [
    {
      label: 'Today',
      getValue: () => ({ start: today, end: endOfToday }),
    },
    {
      label: 'Yesterday',
      getValue: () => {
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        const endOfYesterday = new Date(yesterday);
        endOfYesterday.setHours(23, 59, 59, 999);
        return { start: yesterday, end: endOfYesterday };
      },
    },
    {
      label: 'Last 7 days',
      getValue: () => {
        const start = new Date(today);
        start.setDate(start.getDate() - 6);
        return { start, end: endOfToday };
      },
    },
    {
      label: 'Last 30 days',
      getValue: () => {
        const start = new Date(today);
        start.setDate(start.getDate() - 29);
        return { start, end: endOfToday };
      },
    },
    {
      label: 'This month',
      getValue: () => {
        const start = new Date(today.getFullYear(), today.getMonth(), 1);
        return { start, end: endOfToday };
      },
    },
    {
      label: 'Last month',
      getValue: () => {
        const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        const end = new Date(today.getFullYear(), today.getMonth(), 0, 23, 59, 59, 999);
        return { start, end };
      },
    },
  ];
};

function formatDateShort(date: Date): string {
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDateDisplay(range: DateRange): string {
  if (!range.start && !range.end) return '';
  if (range.start && !range.end) return formatDateShort(range.start);
  if (!range.start && range.end) return formatDateShort(range.end);
  return `${formatDateShort(range.start!)} - ${formatDateShort(range.end!)}`;
}

function isSameDay(date1: Date, date2: Date): boolean {
  return (
    date1.getFullYear() === date2.getFullYear() &&
    date1.getMonth() === date2.getMonth() &&
    date1.getDate() === date2.getDate()
  );
}

function isDateInRange(date: Date, start: Date | null, end: Date | null): boolean {
  if (!start || !end) return false;
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  const s = new Date(start);
  s.setHours(0, 0, 0, 0);
  const e = new Date(end);
  e.setHours(0, 0, 0, 0);
  return d >= s && d <= e;
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

interface CalendarMonthProps {
  year: number;
  month: number;
  selectedRange: DateRange;
  onDateClick: (date: Date) => void;
  minDate?: Date;
  maxDate?: Date;
  hoverDate: Date | null;
  onDateHover: (date: Date | null) => void;
  selectionMode: 'start' | 'end';
}

function CalendarMonth({
  year,
  month,
  selectedRange,
  onDateClick,
  minDate,
  maxDate,
  hoverDate,
  onDateHover,
  selectionMode,
}: CalendarMonthProps) {
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const monthName = new Date(year, month).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  const days: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) {
    days.push(null);
  }
  for (let i = 1; i <= daysInMonth; i++) {
    days.push(i);
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const isDateDisabled = (date: Date): boolean => {
    if (minDate && date < minDate) return true;
    if (maxDate && date > maxDate) return true;
    return false;
  };

  const getPreviewRange = (): { start: Date | null; end: Date | null } => {
    if (!hoverDate || !selectedRange.start || selectedRange.end) {
      return selectedRange;
    }
    if (selectionMode === 'end') {
      if (hoverDate < selectedRange.start) {
        return { start: hoverDate, end: selectedRange.start };
      }
      return { start: selectedRange.start, end: hoverDate };
    }
    return selectedRange;
  };

  const previewRange = getPreviewRange();

  return (
    <div className="w-64">
      <div className="text-center text-sm font-medium text-zinc-200 mb-3">
        {monthName}
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs text-zinc-500 mb-2">
        {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map((day) => (
          <div key={day} className="h-8 flex items-center justify-center">
            {day}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map((day, index) => {
          if (day === null) {
            return <div key={`empty-${index}`} className="h-8" />;
          }

          const date = new Date(year, month, day);
          date.setHours(0, 0, 0, 0);
          const isDisabled = isDateDisabled(date);
          const isToday = isSameDay(date, today);
          const isStart = selectedRange.start && isSameDay(date, selectedRange.start);
          const isEnd = selectedRange.end && isSameDay(date, selectedRange.end);
          const isInRange = isDateInRange(date, previewRange.start, previewRange.end);
          const isPreviewStart = previewRange.start && isSameDay(date, previewRange.start);
          const isPreviewEnd = previewRange.end && isSameDay(date, previewRange.end);

          return (
            <button
              key={day}
              type="button"
              disabled={isDisabled}
              onClick={() => onDateClick(date)}
              onMouseEnter={() => onDateHover(date)}
              onMouseLeave={() => onDateHover(null)}
              className={cn(
                'h-8 w-8 rounded-md text-sm transition-colors relative',
                'focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:ring-offset-1 focus:ring-offset-zinc-900',
                isDisabled && 'text-zinc-600 cursor-not-allowed',
                !isDisabled && !isInRange && 'hover:bg-zinc-700/50 text-zinc-300',
                isToday && !isInRange && 'text-cyan-400 font-semibold',
                isInRange && !isStart && !isEnd && !isPreviewStart && !isPreviewEnd && 'bg-cyan-600/20 text-cyan-300',
                (isStart || isEnd || isPreviewStart || isPreviewEnd) && 'bg-cyan-600 text-white font-medium',
              )}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const DateRangePicker = React.forwardRef<HTMLDivElement, DateRangePickerProps>(
  (
    {
      value,
      onChange,
      disabled = false,
      placeholder = 'Select date range',
      className,
      minDate,
      maxDate,
      showPresets = true,
    },
    ref
  ) => {
    const [isOpen, setIsOpen] = React.useState(false);
    const [currentMonth, setCurrentMonth] = React.useState(() => {
      const now = value.start || new Date();
      return { year: now.getFullYear(), month: now.getMonth() };
    });
    const [hoverDate, setHoverDate] = React.useState<Date | null>(null);
    const [selectionMode, setSelectionMode] = React.useState<'start' | 'end'>('start');
    const [tempRange, setTempRange] = React.useState<DateRange>(value);
    const containerRef = React.useRef<HTMLDivElement>(null);

    const presetRanges = React.useMemo(() => getPresetRanges(), []);

    // Sync tempRange with value when picker opens
    React.useEffect(() => {
      if (isOpen) {
        setTempRange(value);
        setSelectionMode(value.start && !value.end ? 'end' : 'start');
      }
    }, [isOpen, value]);

    // Handle click outside
    React.useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
          setIsOpen(false);
        }
      };

      if (isOpen) {
        document.addEventListener('mousedown', handleClickOutside);
      }
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isOpen]);

    // Handle escape key
    React.useEffect(() => {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && isOpen) {
          setIsOpen(false);
        }
      };

      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }, [isOpen]);

    const handleDateClick = (date: Date) => {
      if (selectionMode === 'start') {
        setTempRange({ start: date, end: null });
        setSelectionMode('end');
      } else {
        let newRange: DateRange;
        if (tempRange.start && date < tempRange.start) {
          newRange = { start: date, end: tempRange.start };
        } else {
          newRange = { start: tempRange.start, end: date };
        }
        setTempRange(newRange);
        onChange(newRange);
        setIsOpen(false);
        setSelectionMode('start');
      }
    };

    const handlePresetClick = (preset: PresetRange) => {
      const range = preset.getValue();
      setTempRange(range);
      onChange(range);
      setIsOpen(false);
    };

    const handleClear = (e: React.MouseEvent) => {
      e.stopPropagation();
      onChange({ start: null, end: null });
      setTempRange({ start: null, end: null });
      setSelectionMode('start');
    };

    const navigateMonth = (direction: 'prev' | 'next') => {
      setCurrentMonth((prev) => {
        const newMonth = direction === 'prev' ? prev.month - 1 : prev.month + 1;
        if (newMonth < 0) {
          return { year: prev.year - 1, month: 11 };
        }
        if (newMonth > 11) {
          return { year: prev.year + 1, month: 0 };
        }
        return { ...prev, month: newMonth };
      });
    };

    const nextMonth = {
      year: currentMonth.month === 11 ? currentMonth.year + 1 : currentMonth.year,
      month: currentMonth.month === 11 ? 0 : currentMonth.month + 1,
    };

    const displayValue = formatDateDisplay(value);

    return (
      <div ref={containerRef} className={cn('relative', className)}>
        <div
          ref={ref}
          role="button"
          tabIndex={disabled ? -1 : 0}
          onClick={() => !disabled && setIsOpen(!isOpen)}
          onKeyDown={(e) => {
            if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
              e.preventDefault();
              setIsOpen(!isOpen);
            }
          }}
          className={cn(
            'flex items-center gap-2 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm cursor-pointer transition-colors',
            'focus:outline-none focus:border-cyan-500',
            isOpen && 'border-cyan-500',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          <Calendar className="h-4 w-4 text-zinc-400 shrink-0" />
          <span className={cn('flex-1 text-left', !displayValue && 'text-zinc-500')}>
            {displayValue || placeholder}
          </span>
          {displayValue && !disabled && (
            <button
              type="button"
              onClick={handleClear}
              className="p-0.5 hover:bg-zinc-700 rounded transition-colors"
            >
              <X className="h-3 w-3 text-zinc-400" />
            </button>
          )}
        </div>

        {isOpen && (
          <div className="absolute z-50 mt-2 bg-zinc-900 border border-zinc-800 rounded-lg shadow-lg p-4">
            <div className="flex gap-6">
              {/* Presets */}
              {showPresets && (
                <div className="border-r border-zinc-800 pr-4">
                  <div className="text-xs font-medium text-zinc-500 uppercase mb-2">
                    Quick Select
                  </div>
                  <div className="flex flex-col gap-1">
                    {presetRanges.map((preset) => (
                      <button
                        key={preset.label}
                        type="button"
                        onClick={() => handlePresetClick(preset)}
                        className="px-3 py-1.5 text-sm text-left text-zinc-300 hover:bg-zinc-800 rounded transition-colors"
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Calendar */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <button
                    type="button"
                    onClick={() => navigateMonth('prev')}
                    className="p-1 hover:bg-zinc-800 rounded transition-colors"
                  >
                    <ChevronLeft className="h-4 w-4 text-zinc-400" />
                  </button>
                  <button
                    type="button"
                    onClick={() => navigateMonth('next')}
                    className="p-1 hover:bg-zinc-800 rounded transition-colors"
                  >
                    <ChevronRight className="h-4 w-4 text-zinc-400" />
                  </button>
                </div>

                <div className="flex gap-4">
                  <CalendarMonth
                    year={currentMonth.year}
                    month={currentMonth.month}
                    selectedRange={tempRange}
                    onDateClick={handleDateClick}
                    minDate={minDate}
                    maxDate={maxDate}
                    hoverDate={hoverDate}
                    onDateHover={setHoverDate}
                    selectionMode={selectionMode}
                  />
                  <CalendarMonth
                    year={nextMonth.year}
                    month={nextMonth.month}
                    selectedRange={tempRange}
                    onDateClick={handleDateClick}
                    minDate={minDate}
                    maxDate={maxDate}
                    hoverDate={hoverDate}
                    onDateHover={setHoverDate}
                    selectionMode={selectionMode}
                  />
                </div>

                {/* Selection hint */}
                <div className="mt-3 text-xs text-zinc-500 text-center">
                  {selectionMode === 'start'
                    ? 'Click to select start date'
                    : 'Click to select end date'}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }
);

DateRangePicker.displayName = 'DateRangePicker';

export { DateRangePicker };
