import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { JwtHelperService } from '@auth0/angular-jwt';

import { environment } from '../../../environments/environment';
import { NoAuthHttpClient } from '../../services/no-auth-http-client.service';
import { SessionService, SessionUser } from './session.service';
import { AuthActivityService } from './auth-activity.service';
import { RefreshCoordinator } from './refresh-coordinator';

interface RefreshResponse {
  token: string;
  user: SessionUser;
}

/**
 * Opt-in rotating refresh bridge. Web Locks serialize HttpOnly cookie rotation
 * across same-origin tabs; without Web Locks we fail closed rather than risk
 * replaying a previously rotated cookie.
 */
@Injectable({ providedIn: 'root' })
export class SessionRefreshService {
  readonly enabled = environment.sessionRefreshEnabled;
  private readonly coordinator: RefreshCoordinator;

  constructor(
    private readonly http: NoAuthHttpClient,
    private readonly session: SessionService,
    private readonly jwt: JwtHelperService,
    private readonly activity: AuthActivityService,
  ) {
    this.coordinator = new RefreshCoordinator(
      () => this.session.getToken(),
      token => this.isUsable(token),
      previousToken => this.exchange(previousToken),
      work => this.withBrowserLock(work),
    );
  }

  private isUsable(token: string): boolean {
    try {
      return !this.jwt.isTokenExpired(token);
    } catch {
      return false;
    }
  }

  private needsRenewal(token: string): boolean {
    try {
      const expiry = this.jwt.getTokenExpirationDate(token)?.getTime();
      return !expiry || expiry <= Date.now() + 5 * 60 * 1000;
    } catch {
      return true;
    }
  }

  /** Only renew on expiry proximity, and never for background polling. */
  shouldRenewSoon(token: string | null): boolean {
    return Boolean(
      this.enabled && token && !this.activity.isLocked()
      && this.activity.isRecent() && this.needsRenewal(token!)
    );
  }

  /** Request at most one refresh for an actual recent human interaction. */
  renewIfNeeded(observedToken: string | null): Promise<string | null> {
    if (!this.enabled || !this.activity.isRecent() || !observedToken) {
      return Promise.resolve(null);
    }
    if (!this.needsRenewal(observedToken)) {
      return Promise.resolve(observedToken);
    }
    return this.coordinator.renew(observedToken);
  }

  private withBrowserLock(
    work: () => Promise<string | null>
  ): Promise<string | null> {
    if (
      typeof window === 'undefined' ||
      !window.isSecureContext ||
      typeof navigator === 'undefined' ||
      !navigator.locks
    ) {
      // Never perform uncoordinated cross-tab rotation.
      return Promise.resolve(null);
    }
    return navigator.locks.request('suite-ultra-auth-refresh', async () => work());
  }

  private async exchange(previousToken: string): Promise<string | null> {
    const response = await firstValueFrom(
      this.http.post<RefreshResponse>(
        `${environment.apiUrl}/auth/refresh`,
        {},
        { withCredentials: true }
      )
    );

    if (!response?.token || !response?.user?.id) {
      return null;
    }

    // A logout, another login or a tab change while the request was in
    // flight must not silently recreate or overwrite an old session.
    if (this.session.getToken() !== previousToken) {
      return null;
    }

    this.session.setSession(response.token, response.user);
    return response.token;
  }
}
