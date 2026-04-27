'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import type { SortField, SortOrder, DateFilterField } from '@/types/codeboard';
import type { DateRange } from '@/components/ui/date-range-picker';

export type ViewMode = 'board' | 'swimlanes' | 'list';

interface CodeboardState {
  selectedProjectId: string | null;
  viewMode: ViewMode;
  search: string;
  selectedType: string | null;
  selectedPriority: string | null;
  selectedLabel: string | null;
  sortField: SortField;
  sortOrder: SortOrder;
  dateFilterField: DateFilterField | null;
  dateRange: DateRange;
}

const DEFAULT_STATE: CodeboardState = {
  selectedProjectId: null,
  viewMode: 'swimlanes',
  search: '',
  selectedType: null,
  selectedPriority: null,
  selectedLabel: null,
  sortField: 'sequence',
  sortOrder: 'asc',
  dateFilterField: null,
  dateRange: { start: null, end: null },
};

function safeDate(input: string | null): Date | null {
  if (!input) return null;
  const d = new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

function readFromParams(params: URLSearchParams | null): CodeboardState {
  if (!params) return { ...DEFAULT_STATE };
  return {
    selectedProjectId: params.get('project'),
    viewMode: (params.get('view') as ViewMode) || DEFAULT_STATE.viewMode,
    search: params.get('q') ?? DEFAULT_STATE.search,
    selectedType: params.get('type'),
    selectedPriority: params.get('priority'),
    selectedLabel: params.get('label'),
    sortField: (params.get('sortBy') as SortField) || DEFAULT_STATE.sortField,
    sortOrder: (params.get('sortDir') as SortOrder) || DEFAULT_STATE.sortOrder,
    dateFilterField: (params.get('dateField') as DateFilterField) || null,
    dateRange: {
      start: safeDate(params.get('dateFrom')),
      end: safeDate(params.get('dateTo')),
    },
  };
}

function writeToParams(state: CodeboardState): URLSearchParams {
  const p = new URLSearchParams();
  if (state.selectedProjectId) p.set('project', state.selectedProjectId);
  if (state.viewMode !== DEFAULT_STATE.viewMode) p.set('view', state.viewMode);
  if (state.search) p.set('q', state.search);
  if (state.selectedType) p.set('type', state.selectedType);
  if (state.selectedPriority) p.set('priority', state.selectedPriority);
  if (state.selectedLabel) p.set('label', state.selectedLabel);
  if (state.sortField !== DEFAULT_STATE.sortField) p.set('sortBy', state.sortField);
  if (state.sortOrder !== DEFAULT_STATE.sortOrder) p.set('sortDir', state.sortOrder);
  if (state.dateFilterField) p.set('dateField', state.dateFilterField);
  if (state.dateRange.start) p.set('dateFrom', state.dateRange.start.toISOString());
  if (state.dateRange.end) p.set('dateTo', state.dateRange.end.toISOString());
  return p;
}

function statesEqual(a: CodeboardState, b: CodeboardState): boolean {
  return (
    a.selectedProjectId === b.selectedProjectId &&
    a.viewMode === b.viewMode &&
    a.search === b.search &&
    a.selectedType === b.selectedType &&
    a.selectedPriority === b.selectedPriority &&
    a.selectedLabel === b.selectedLabel &&
    a.sortField === b.sortField &&
    a.sortOrder === b.sortOrder &&
    a.dateFilterField === b.dateFilterField &&
    (a.dateRange.start?.getTime() ?? null) === (b.dateRange.start?.getTime() ?? null) &&
    (a.dateRange.end?.getTime() ?? null) === (b.dateRange.end?.getTime() ?? null)
  );
}

/**
 * Single hook backing CodeBoard's filter / view / project state via URL search params.
 * Survives navigation, refresh, and browser back/forward. Default values are omitted
 * from the URL to keep it short. Updates are debounced 250ms to avoid spamming
 * router.replace during typing.
 */
export function useCodeboardState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [state, setStateRaw] = useState<CodeboardState>(() => readFromParams(searchParams));

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextSyncRef = useRef(false);

  const flushUrl = useCallback(
    (next: CodeboardState) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const qs = writeToParams(next).toString();
        const url = qs ? `${pathname}?${qs}` : pathname;
        skipNextSyncRef.current = true;
        router.replace(url, { scroll: false });
      }, 250);
    },
    [pathname, router],
  );

  // External setter — updates state and URL atomically.
  const updateState = useCallback(
    (patch: Partial<CodeboardState>) => {
      setStateRaw((prev) => {
        const next = { ...prev, ...patch };
        if (statesEqual(prev, next)) return prev;
        flushUrl(next);
        return next;
      });
    },
    [flushUrl],
  );

  // When URL changes externally (back / forward / direct navigation), reflect in state.
  useEffect(() => {
    if (skipNextSyncRef.current) {
      skipNextSyncRef.current = false;
      return;
    }
    const fromUrl = readFromParams(searchParams);
    setStateRaw((prev) => (statesEqual(prev, fromUrl) ? prev : fromUrl));
  }, [searchParams]);

  // Cleanup pending debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // Stable individual setters
  const setSelectedProjectId = useCallback(
    (v: string | null | ((prev: string | null) => string | null)) => {
      updateState({
        selectedProjectId: typeof v === 'function' ? v(state.selectedProjectId) : v,
      });
    },
    [state.selectedProjectId, updateState],
  );

  const setViewMode = useCallback(
    (v: ViewMode | ((prev: ViewMode) => ViewMode)) => {
      updateState({ viewMode: typeof v === 'function' ? v(state.viewMode) : v });
    },
    [state.viewMode, updateState],
  );

  const setSearch = useCallback(
    (v: string | ((prev: string) => string)) => {
      updateState({ search: typeof v === 'function' ? v(state.search) : v });
    },
    [state.search, updateState],
  );

  const setSelectedType = useCallback(
    (v: string | null | ((prev: string | null) => string | null)) => {
      updateState({ selectedType: typeof v === 'function' ? v(state.selectedType) : v });
    },
    [state.selectedType, updateState],
  );

  const setSelectedPriority = useCallback(
    (v: string | null | ((prev: string | null) => string | null)) => {
      updateState({
        selectedPriority: typeof v === 'function' ? v(state.selectedPriority) : v,
      });
    },
    [state.selectedPriority, updateState],
  );

  const setSelectedLabel = useCallback(
    (v: string | null | ((prev: string | null) => string | null)) => {
      updateState({ selectedLabel: typeof v === 'function' ? v(state.selectedLabel) : v });
    },
    [state.selectedLabel, updateState],
  );

  const setSortField = useCallback(
    (v: SortField | ((prev: SortField) => SortField)) => {
      updateState({ sortField: typeof v === 'function' ? v(state.sortField) : v });
    },
    [state.sortField, updateState],
  );

  const setSortOrder = useCallback(
    (v: SortOrder | ((prev: SortOrder) => SortOrder)) => {
      updateState({ sortOrder: typeof v === 'function' ? v(state.sortOrder) : v });
    },
    [state.sortOrder, updateState],
  );

  const setDateFilterField = useCallback(
    (v: DateFilterField | null | ((prev: DateFilterField | null) => DateFilterField | null)) => {
      updateState({
        dateFilterField: typeof v === 'function' ? v(state.dateFilterField) : v,
      });
    },
    [state.dateFilterField, updateState],
  );

  const setDateRange = useCallback(
    (v: DateRange | ((prev: DateRange) => DateRange)) => {
      updateState({ dateRange: typeof v === 'function' ? v(state.dateRange) : v });
    },
    [state.dateRange, updateState],
  );

  return useMemo(
    () => ({
      // values
      selectedProjectId: state.selectedProjectId,
      viewMode: state.viewMode,
      search: state.search,
      selectedType: state.selectedType,
      selectedPriority: state.selectedPriority,
      selectedLabel: state.selectedLabel,
      sortField: state.sortField,
      sortOrder: state.sortOrder,
      dateFilterField: state.dateFilterField,
      dateRange: state.dateRange,
      // setters
      setSelectedProjectId,
      setViewMode,
      setSearch,
      setSelectedType,
      setSelectedPriority,
      setSelectedLabel,
      setSortField,
      setSortOrder,
      setDateFilterField,
      setDateRange,
      // bulk setter (rarely needed)
      updateState,
    }),
    [
      state,
      setSelectedProjectId,
      setViewMode,
      setSearch,
      setSelectedType,
      setSelectedPriority,
      setSelectedLabel,
      setSortField,
      setSortOrder,
      setDateFilterField,
      setDateRange,
      updateState,
    ],
  );
}

/**
 * Save / restore window.scrollY keyed by the current URL. Saves on `pagehide`
 * (which fires before SPA navigation away) and restores on mount.
 */
export function useScrollRestoration(key: string) {
  useEffect(() => {
    const storeKey = `cb:scroll:${key}`;
    const saved = sessionStorage.getItem(storeKey);
    if (saved) {
      const y = parseInt(saved, 10);
      // Defer until after content paints
      requestAnimationFrame(() => {
        requestAnimationFrame(() => window.scrollTo(0, y));
      });
    }
    const onHide = () => {
      sessionStorage.setItem(storeKey, String(window.scrollY));
    };
    window.addEventListener('pagehide', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      // Also save on unmount (SPA-internal navigation away)
      sessionStorage.setItem(storeKey, String(window.scrollY));
    };
  }, [key]);
}
