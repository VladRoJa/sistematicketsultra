import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { JwtHelperService } from '@auth0/angular-jwt';
import { Observable, from, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

import { SessionService } from '../core/auth/session.service';
import { SessionRefreshService } from '../core/auth/session-refresh.service';
import { AuthActivityService } from '../core/auth/auth-activity.service';
import { AuthService } from '../services/auth.service';

@Injectable({ providedIn: 'root' })
export class AuthGuard implements CanActivate {
  constructor(
    private readonly session: SessionService,
    private readonly authService: AuthService,
    private readonly refresh: SessionRefreshService,
    private readonly activity: AuthActivityService,
    private readonly jwt: JwtHelperService,
    private readonly router: Router,
  ) {}

  canActivate(): Observable<boolean> {
    const token = this.session.getToken();
    if (!token) return this.deny();

    let expired = true;
    try {
      expired = this.jwt.isTokenExpired(token);
    } catch {
      expired = true;
    }

    if (expired) {
      if (!this.refresh.enabled || !this.activity.isRecent()) {
        return this.deny();
      }
      return from(this.refresh.renewIfNeeded(token)).pipe(
        switchMap(fresh => fresh ? this.authorizeStoredUser() : this.deny()),
        catchError(() => this.deny()),
      );
    }
    return this.authorizeStoredUser();
  }

  private authorizeStoredUser(): Observable<boolean> {
    if (this.session.getUser()) return of(true);
    // Hydrate only after a valid access token. The backend owns permissions.
    return this.authService.obtenerUsuarioAutenticado().pipe(
      map(result => Boolean(result?.user)),
      catchError(() => this.deny()),
    );
  }

  private deny(): Observable<boolean> {
    this.session.clearSession();
    this.activity.clear();
    this.router.navigate(['/login']);
    return of(false);
  }
}
