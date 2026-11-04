/**
 * Presentation-only preference for the campaign dispatch dock.
 * Stores only positive job IDs, never job payloads, phone numbers or credentials.
 * Actual job state and authorization always come from the backend.
 */
export interface BackgroundDockPreferenceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const STORAGE_PREFIX = 'suite.campaignV2.backgroundDock.dismissed.v1:';
const MAX_DISMISSED_IDS = 200;

function scopedKey(identity: string): string | null {
  const normalized = identity.trim().toUpperCase();
  return normalized ? STORAGE_PREFIX + encodeURIComponent(normalized) : null;
}

function browserStorage(): BackgroundDockPreferenceStorage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    // Privacy mode and disabled browser storage must not break monitoring.
    return null;
  }
}

function validJobId(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}

export function loadDismissedBackgroundJobIds(
  identity: string,
  storage: BackgroundDockPreferenceStorage | null = browserStorage(),
): Set<number> {
  const key = scopedKey(identity);
  if (!key || !storage) return new Set<number>();
  try {
    const parsed: unknown = JSON.parse(storage.getItem(key) || '[]');
    return new Set<number>(
      Array.isArray(parsed) ? parsed.filter(validJobId).slice(-MAX_DISMISSED_IDS) : [],
    );
  } catch {
    return new Set<number>();
  }
}

export function persistDismissedBackgroundJobIds(
  identity: string,
  previous: ReadonlySet<number>,
  newJobIds: number[],
  storage: BackgroundDockPreferenceStorage | null = browserStorage(),
): Set<number> {
  const key = scopedKey(identity);
  if (!key) return new Set<number>();
  const next = new Set<number>(
    [...previous, ...newJobIds].filter(validJobId).slice(-MAX_DISMISSED_IDS),
  );
  try {
    storage?.setItem(key, JSON.stringify([...next]));
  } catch {
    // The in-memory dismissal still works when browser storage is unavailable.
  }
  return next;
}
