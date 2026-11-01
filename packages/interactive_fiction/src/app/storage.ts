/**
 * Guarded access to localStorage. Storage can be missing, full or blocked
 * (private windows, embedded viewers); every read then falls back and every
 * write is silently dropped — saving is a convenience, reading must go on.
 */

export const PREFIX = "if:v1:";

export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Kept for this visit only.
  }
}

export function remove(key: string): void {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    // Nothing to remove.
  }
}
