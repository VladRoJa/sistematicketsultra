import { Injectable } from '@angular/core';

/**
 * Only captured human events advance this clock, never HTTP polling or timers.
 * The server independently enforces refresh-session idle/absolute expiry.
 */
@Injectable({ providedIn: 'root' })
export class AuthActivityService {
  readonly storageKey = 'suite.auth.lastRealActivityAt';
  private locked = false;
  private lastWriteMs = 0;

  initializeIfAbsent(): void {
    const raw = Number(localStorage.getItem(this.storageKey));
    if (!Number.isFinite(raw) || raw <= 0 || raw > Date.now()) {
      this.recordInteraction();
    }
  }

  recordInteraction(): void {
    if (this.locked) return;
    const now = Date.now();
    // Pointer movement must not write to localStorage dozens of times/sec.
    if (now - this.lastWriteMs < 1000) return;
    this.lastWriteMs = now;
    localStorage.setItem(this.storageKey, String(now));
  }

  isRecent(maxAgeMs = 2 * 60 * 1000): boolean {
    if (this.locked) return false;
    const last = Number(localStorage.getItem(this.storageKey));
    const elapsed = Date.now() - last;
    return Number.isFinite(last) && last > 0
      && elapsed >= 0 && elapsed < maxAgeMs;
  }

  millisecondsUntilIdle(idleMs = 45 * 60 * 1000): number {
    const last = Number(localStorage.getItem(this.storageKey));
    if (!Number.isFinite(last) || last <= 0) return 0;
    return Math.max(0, idleMs - (Date.now() - last));
  }

  lock(): void {
    this.locked = true;
  }

  unlock(): void {
    this.locked = false;
    this.lastWriteMs = 0;
  }

  isLocked(): boolean {
    return this.locked;
  }

  clear(): void {
    this.locked = false;
    this.lastWriteMs = 0;
    localStorage.removeItem(this.storageKey);
  }
}
