'use client';

/**
 * Generic URL-backed state primitive.
 *
 * Lets a page declare a typed schema mapping React state keys to URL search
 * params, with codecs for serialisation. State changes flow into the URL
 * (debounced router.replace, no scroll jump). External URL changes (back /
 * forward) flow back into state. Default values are omitted from the URL.
 *
 * Usage:
 *   const [state, setState] = useUrlState({
 *     project: stringParam('project'),
 *     view: enumParam('view', ['board', 'list'] as const, 'board'),
 *     q: stringParam('q', ''),
 *     priority: optionalStringParam('priority'),
 *     dateFrom: dateParam('dateFrom'),
 *   });
 *   setState({ q: 'auth' });
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

// ─── Codec definitions ─────────────────────────────────────────────────────

export interface UrlCodec<T> {
  /** URL search-param name */
  key: string;
  /** Default value; omitted from the URL when state matches */
  defaultValue: T;
  /** Read URL string → T (returns defaultValue on missing/invalid) */
  read: (raw: string | null) => T;
  /** Serialise T → URL string, or null to omit from URL when at default */
  write: (value: T) => string | null;
  /** Equality for change detection (default: ===) */
  equals?: (a: T, b: T) => boolean;
}

export function stringParam(key: string, defaultValue = ''): UrlCodec<string> {
  return {
    key,
    defaultValue,
    read: (raw) => raw ?? defaultValue,
    write: (v) => (v === defaultValue ? null : v),
  };
}

export function optionalStringParam(key: string): UrlCodec<string | null> {
  return {
    key,
    defaultValue: null,
    read: (raw) => raw,
    write: (v) => v,
  };
}

export function enumParam<T extends string>(
  key: string,
  allowed: readonly T[],
  defaultValue: T,
): UrlCodec<T> {
  const set = new Set(allowed as readonly string[]);
  return {
    key,
    defaultValue,
    read: (raw) => (raw && set.has(raw) ? (raw as T) : defaultValue),
    write: (v) => (v === defaultValue ? null : v),
  };
}

export function optionalEnumParam<T extends string>(
  key: string,
  allowed: readonly T[],
): UrlCodec<T | null> {
  const set = new Set(allowed as readonly string[]);
  return {
    key,
    defaultValue: null,
    read: (raw) => (raw && set.has(raw) ? (raw as T) : null),
    write: (v) => v,
  };
}

export function intParam(key: string, defaultValue: number): UrlCodec<number> {
  return {
    key,
    defaultValue,
    read: (raw) => {
      if (raw == null) return defaultValue;
      const n = Number.parseInt(raw, 10);
      return Number.isFinite(n) ? n : defaultValue;
    },
    write: (v) => (v === defaultValue ? null : String(v)),
  };
}

export function boolParam(key: string, defaultValue = false): UrlCodec<boolean> {
  return {
    key,
    defaultValue,
    read: (raw) => (raw == null ? defaultValue : raw === '1' || raw === 'true'),
    write: (v) => (v === defaultValue ? null : v ? '1' : '0'),
  };
}

export function dateParam(key: string): UrlCodec<Date | null> {
  return {
    key,
    defaultValue: null,
    read: (raw) => {
      if (!raw) return null;
      const d = new Date(raw);
      return Number.isNaN(d.getTime()) ? null : d;
    },
    write: (v) => (v ? v.toISOString() : null),
    equals: (a, b) => (a?.getTime() ?? null) === (b?.getTime() ?? null),
  };
}

/** A delimited set of strings, e.g. ?selected=a,b,c */
export function stringSetParam(key: string, separator = ','): UrlCodec<Set<string>> {
  return {
    key,
    defaultValue: new Set<string>(),
    read: (raw) => (raw ? new Set(raw.split(separator).filter(Boolean)) : new Set()),
    write: (v) => (v.size === 0 ? null : Array.from(v).join(separator)),
    equals: (a, b) => {
      if (a.size !== b.size) return false;
      for (const x of a) if (!b.has(x)) return false;
      return true;
    },
  };
}

// ─── Hook ───────────────────────────────────────────────────────────────────

// Schema constraint must allow any T per key — `unknown` over-constrains
// (would force read() to return unknown, losing inference). `any` here is
// purely for the constraint position; per-key inference still flows through
// StateOf<S>, so callers see the precise type.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyCodec = UrlCodec<any>;
type Schema = Record<string, AnyCodec>;

type StateOf<S extends Schema> = {
  [K in keyof S]: S[K] extends UrlCodec<infer T> ? T : never;
};

function readState<S extends Schema>(
  schema: S,
  params: URLSearchParams | null,
): StateOf<S> {
  const out: Record<string, unknown> = {};
  for (const k in schema) {
    const codec = schema[k];
    const raw = params ? params.get(codec.key) : null;
    out[k] = codec.read(raw);
  }
  return out as StateOf<S>;
}

function writeState<S extends Schema>(schema: S, state: StateOf<S>): URLSearchParams {
  const out = new URLSearchParams();
  for (const k in schema) {
    const codec = schema[k];
    const value = (state as Record<string, unknown>)[k];
    const raw = codec.write(value);
    if (raw != null) out.set(codec.key, raw);
  }
  return out;
}

function statesEqual<S extends Schema>(
  schema: S,
  a: StateOf<S>,
  b: StateOf<S>,
): boolean {
  for (const k in schema) {
    const codec = schema[k];
    const eq = codec.equals ?? ((x: unknown, y: unknown) => x === y);
    const av = (a as Record<string, unknown>)[k];
    const bv = (b as Record<string, unknown>)[k];
    if (!eq(av, bv)) return false;
  }
  return true;
}

export interface UrlStateOptions {
  /** Debounce window for URL writes (ms). Default 250. */
  debounceMs?: number;
  /** Pass false to use router.push instead of replace (rarely needed). Default true. */
  replace?: boolean;
}

export function useUrlState<S extends Schema>(
  schema: S,
  options: UrlStateOptions = {},
): readonly [StateOf<S>, (patch: Partial<StateOf<S>>) => void] {
  const { debounceMs = 250, replace = true } = options;

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Schema is treated as stable across renders (caller declares it once).
  const schemaRef = useRef(schema);
  schemaRef.current = schema;

  const [state, setStateRaw] = useState<StateOf<S>>(() =>
    readState(schemaRef.current, searchParams),
  );

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextSyncRef = useRef(false);

  const flushUrl = useCallback(
    (next: StateOf<S>) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const qs = writeState(schemaRef.current, next).toString();
        const url = qs ? `${pathname}?${qs}` : pathname;
        skipNextSyncRef.current = true;
        if (replace) {
          router.replace(url, { scroll: false });
        } else {
          router.push(url, { scroll: false });
        }
      }, debounceMs);
    },
    [pathname, router, replace, debounceMs],
  );

  const setState = useCallback(
    (patch: Partial<StateOf<S>>) => {
      setStateRaw((prev) => {
        const next = { ...prev, ...patch } as StateOf<S>;
        if (statesEqual(schemaRef.current, prev, next)) return prev;
        flushUrl(next);
        return next;
      });
    },
    [flushUrl],
  );

  // Sync from URL on external nav (back/forward/direct).
  useEffect(() => {
    if (skipNextSyncRef.current) {
      skipNextSyncRef.current = false;
      return;
    }
    const fromUrl = readState(schemaRef.current, searchParams);
    setStateRaw((prev) => (statesEqual(schemaRef.current, prev, fromUrl) ? prev : fromUrl));
  }, [searchParams]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return [state, setState] as const;
}

// ─── Same-origin back-button helper ────────────────────────────────────────

import type { useRouter as UseRouter } from 'next/navigation';
type Router = ReturnType<typeof UseRouter>;

/**
 * Build a back-button handler that prefers browser history (preserves
 * previous page state) but falls back to a fixed route for direct hits.
 */
export function useNavigateBack(router: Router, fallbackPath: string) {
  return useCallback(() => {
    const sameOriginReferrer =
      typeof document !== 'undefined' &&
      document.referrer &&
      (() => {
        try {
          return new URL(document.referrer).origin === window.location.origin;
        } catch {
          return false;
        }
      })();
    if (sameOriginReferrer || (typeof window !== 'undefined' && window.history.length > 1)) {
      router.back();
    } else {
      router.push(fallbackPath);
    }
  }, [router, fallbackPath]);
}

// ─── Scroll restoration ────────────────────────────────────────────────────

export function useScrollRestoration(key: string) {
  useEffect(() => {
    const storeKey = `urlstate:scroll:${key}`;
    const saved = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(storeKey) : null;
    if (saved) {
      const y = Number.parseInt(saved, 10);
      if (Number.isFinite(y)) {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => window.scrollTo(0, y));
        });
      }
    }
    const onHide = () => {
      try {
        sessionStorage.setItem(storeKey, String(window.scrollY));
      } catch {
        /* ignore quota errors */
      }
    };
    window.addEventListener('pagehide', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      try {
        sessionStorage.setItem(storeKey, String(window.scrollY));
      } catch {
        /* ignore */
      }
    };
  }, [key]);
}
