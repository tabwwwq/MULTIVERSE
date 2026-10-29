"use client";

import { useCallback, useSyncExternalStore } from "react";
import { EMPTY_NOTEBOOK, type Notebook } from "@/notebook/model";
import {
  browserStorage,
  deleteAll,
  type LoadResult,
  loadNotebook,
  NOTEBOOK_KEY,
  type StorageStatus,
  writeNotebook,
} from "@/notebook/storage";

/*
 * One notebook state per tab, shared by every component through useSyncExternalStore.
 * Changes from another tab arrive through the storage event, so a refresh or a second
 * tab never shows stale scenarios.
 */

export interface NotebookState extends LoadResult {
  /** True once the state reflects this device; false during server rendering. */
  ready: boolean;
}

const SERVER_STATE: NotebookState = {
  notebook: EMPTY_NOTEBOOK,
  status: "ok",
  unreadable: null,
  ready: false,
};

let state: NotebookState | null = null;
const listeners = new Set<() => void>();

function current(): NotebookState {
  state ??= { ...loadNotebook(browserStorage()), ready: true };
  return state;
}

function emit(next: NotebookState): void {
  state = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === NOTEBOOK_KEY || event.key === null) {
      emit({ ...loadNotebook(browserStorage()), ready: true });
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export type SaveOutcome = { ok: true } | { ok: false; status: Exclude<StorageStatus, "ok"> };

export function useNotebook() {
  const snapshot = useSyncExternalStore(subscribe, current, () => SERVER_STATE);

  /** Keeps the change in this tab even when storage fails, and says why it was not saved. */
  const save = useCallback((next: Notebook): SaveOutcome => {
    const before = current();
    const result = writeNotebook(browserStorage(), next, before.status, new Date().toISOString());
    if (result.ok) {
      emit({ notebook: next, status: "ok", unreadable: null, ready: true });
      return { ok: true };
    }
    if (result.status === "corrupt") return result;
    emit({ notebook: next, status: result.status, unreadable: null, ready: true });
    return result;
  }, []);

  /** Clears unreadable or all stored data after the user confirmed it. */
  const reset = useCallback((): boolean => {
    const removed = deleteAll(browserStorage());
    emit({ ...loadNotebook(browserStorage()), ready: true });
    return removed;
  }, []);

  return { ...snapshot, save, reset };
}
