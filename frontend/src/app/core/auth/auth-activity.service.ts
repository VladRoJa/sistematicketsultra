import { Injectable } from '@angular/core';

/**
 * Browser activity is a UX signal, not authorization. Flask validates the
 * refresh session's idle and absolute expiry independently.
 */
@Injectable({ providedIn: 'root' })
export class AuthActivityService {
  private readonly activityKey = 'suite.auth.lastRealActivityAt';

  recordInteraction(): void {
    localStorage.setItem(this.activityKey, String(Date.now()));
  }

  isRecent(maxAgeMs: number = 2 * 60 * 1000): boolean {
    const last = Number(localStorage.getItem(this.activityKey));
    const elapsed = Date.now() - last;
    return Number.isFinite(last) && last > 0
      && elapsed >= 0 && elapsed < maxAgeMs;
  }

  millisecondsUntilIdle(idleMs: number = 45 * 60 * 1000): number {
    const last = Number(localStorage.getItem(this.activityKey));
    if (!Number.isFinite(last) || last <= 0) {
      return 0;
    }
    return Math.max(0, idleMs - (Date.now() - last));
  }

  clear(): void {
    localStorage.removeItem(this.activityKey);
  }
}
