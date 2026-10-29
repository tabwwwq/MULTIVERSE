import type { NotebookExport } from "@multiverse/contracts";
import { CONTRACTS_VERSION } from "@multiverse/contracts";
import { EMPTY_NOTEBOOK, type Notebook } from "@/notebook/model";

/*
 * Notebook storage in the browser of this device only (decision D-07, PRD SP-02). The
 * stored value uses the same file format as an export, so one parser and one migration
 * path serve both. Storage can be missing (private mode, blocked site data), full
 * (quota) or hold data this version cannot read; each case is reported, and unreadable
 * data is never overwritten without an explicit reset (FC-10).
 */

export const NOTEBOOK_KEY = "multiverse.notebook";
export const STORAGE_PREFIX = "multiverse.";
export const SCHEMA_VERSION = 1;

/** The parts of the Web Storage API the notebook uses; tests pass a fake. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
  key(index: number): string | null;
  readonly length: number;
}

export type StorageStatus = "ok" | "unavailable" | "quota" | "corrupt";

export interface LoadResult {
  notebook: Notebook;
  status: StorageStatus;
  /** The unreadable stored text, kept so the user can download it before resetting. */
  unreadable: string | null;
}

export function toFile(notebook: Notebook, exportedAt: string): NotebookExport {
  return {
    format: "multiverse-notebook",
    schema_version: SCHEMA_VERSION,
    contracts_version: CONTRACTS_VERSION,
    exported_at: exportedAt,
    scenarios: notebook.scenarios,
    reports: notebook.reports,
  };
}

function isQuotaError(error: unknown): boolean {
  if (typeof DOMException === "undefined" || !(error instanceof DOMException)) {
    return error instanceof Error && /quota/i.test(error.name + error.message);
  }
  return error.name === "QuotaExceededError" || error.name === "NS_ERROR_DOM_QUOTA_REACHED";
}

/** A light shape check for data this app wrote itself; imports get the full validation. */
function readStored(text: string): Notebook | null {
  try {
    const value = JSON.parse(text) as Partial<NotebookExport> | null;
    if (
      value?.format !== "multiverse-notebook" ||
      value.schema_version !== SCHEMA_VERSION ||
      !Array.isArray(value.scenarios) ||
      !Array.isArray(value.reports)
    ) {
      return null;
    }
    return { scenarios: [...value.scenarios], reports: [...value.reports] };
  } catch {
    return null;
  }
}

export function loadNotebook(storage: StorageLike | null): LoadResult {
  if (!storage) return { notebook: EMPTY_NOTEBOOK, status: "unavailable", unreadable: null };
  let text: string | null;
  try {
    text = storage.getItem(NOTEBOOK_KEY);
  } catch {
    return { notebook: EMPTY_NOTEBOOK, status: "unavailable", unreadable: null };
  }
  if (text === null) return { notebook: EMPTY_NOTEBOOK, status: "ok", unreadable: null };
  const notebook = readStored(text);
  return notebook
    ? { notebook, status: "ok", unreadable: null }
    : { notebook: EMPTY_NOTEBOOK, status: "corrupt", unreadable: text };
}

export type WriteResult = { ok: true } | { ok: false; status: "quota" | "unavailable" | "corrupt" };

/** Writes the whole notebook, or reports why it could not. Unreadable data blocks writes. */
export function writeNotebook(
  storage: StorageLike | null,
  notebook: Notebook,
  current: StorageStatus,
  now: string,
): WriteResult {
  if (current === "corrupt") return { ok: false, status: "corrupt" };
  if (!storage) return { ok: false, status: "unavailable" };
  try {
    storage.setItem(NOTEBOOK_KEY, JSON.stringify(toFile(notebook, now)));
    return { ok: true };
  } catch (error) {
    return { ok: false, status: isQuotaError(error) ? "quota" : "unavailable" };
  }
}

export interface StoredItem {
  key: string;
  bytes: number;
}

/** Everything this app keeps on the device (Settings & Privacy). */
export function inventory(storage: StorageLike | null): StoredItem[] {
  if (!storage) return [];
  const items: StoredItem[] = [];
  try {
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      if (key?.startsWith(STORAGE_PREFIX)) {
        items.push({ key, bytes: new Blob([storage.getItem(key) ?? ""]).size });
      }
    }
  } catch {
    return items;
  }
  return items.sort((a, b) => a.key.localeCompare(b.key));
}

/** Removes every key of this app; other sites' data is never touched. */
export function deleteAll(storage: StorageLike | null): boolean {
  if (!storage) return false;
  try {
    for (const item of inventory(storage)) storage.removeItem(item.key);
    return inventory(storage).length === 0;
  } catch {
    return false;
  }
}

export function browserStorage(): StorageLike | null {
  try {
    const storage = window.localStorage;
    const probe = `${STORAGE_PREFIX}probe`;
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}
