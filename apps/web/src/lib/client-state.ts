"use client";

import { useCallback, useSyncExternalStore } from "react";

const noopSubscribe = () => () => {};

/** False during server rendering and hydration, true afterwards (e.g. before using portals). */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

/*
 * A boolean preference kept in localStorage. Storage can throw (private mode,
 * blocked cookies), so values are also kept in memory and the UI keeps working;
 * the preference simply does not survive a reload then.
 */

const memory = new Map<string, boolean>();
const listeners = new Set<() => void>();

function read(key: string): boolean | undefined {
  try {
    const stored = window.localStorage.getItem(key);
    if (stored !== null) return stored === "true";
  } catch {
    // Fall through to the in-memory value.
  }
  return memory.get(key);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function usePersistedFlag(
  key: string,
  fallback: boolean,
): readonly [boolean, (next: boolean) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => read(key) ?? fallback,
    () => fallback,
  );
  const setValue = useCallback(
    (next: boolean) => {
      memory.set(key, next);
      try {
        window.localStorage.setItem(key, String(next));
      } catch {
        // Not persisted; the in-memory value still updates the UI.
      }
      for (const listener of listeners) listener();
    },
    [key],
  );
  return [value, setValue] as const;
}
