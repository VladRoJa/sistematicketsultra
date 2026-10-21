import { Injectable } from '@angular/core';
import {
  HttpInterceptor, HttpRequest, HttpHandler,
  HttpEvent, HttpErrorResponse,
} from '@angular/common/http';
import { Router } from '@angular/router';
import { JwtHelperService } from '@auth0/angular-jwt';
import { from, Observable, throwError } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { SessionService } from '../core/auth/session.service';
import { SessionRefreshService } from '../core/auth/session-refresh.service';
import { AuthActivityService } from '../core/auth/auth-activity.service';
import { environment } from 'src/environments/environment';

/** Sole Authorization interceptor: never attach Suite JWTs to foreign hosts. */
@Injectable()
export class TokenInterceptor implements HttpInterceptor {
  constructor(
    private readonly session: SessionService,
    private readonly refresh: SessionRefreshService,
    private readonly activity: AuthActivityService,
    private readonly jwt: JwtHelperService,
    private readonly router: Router,
  ) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    if (!this.isApiRequest(req.url) || this.isLoginRequest(req.url)) {
      return next.handle(req);
    }

    const observed = this.session.getToken();
    if (!observed) return next.handle(req);

    if (this.refresh.shouldRenewSoon(observed)) {
      // Renew *before* sending writes: do not blindly replay POST/PUT/DELETE
      // after a 401 because domain endpoints may not all be idempotent.
      return from(this.refresh.renewIfNeeded(observed)).pipe(
        catchError(error => {
          if (error instanceof HttpErrorResponse && error.status === 401) {
            this.endInvalidSession();
            return throwError(() => error);
          }
          // Network errors leave the still-valid access token usable.
          if (this.isValidToken(observed)) return from(Promise.resolve(observed));
          return throwError(() => error);
        }),
        switchMap(token => {
          if (!token || this.session.getToken() !== token) {
            // A concurrent logout must never resurrect authorization.
            return throwError(() => new Error('La sesión cambió durante la renovación'));
          }
          return this.dispatch(req, next, token);
        }),
      );
    }

    return this.dispatch(req, next, observed);
  }

  private dispatch(
    req: HttpRequest<any>, next: HttpHandler, token: string
  ): Observable<HttpEvent<any>> {
    const authReq = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
    return next.handle(authReq).pipe(
      catchError(error => {
        if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
          return throwError(() => error);
        }
        // Login credentials are handled by their form; the inactivity dialog
        // is owned *only* by LayoutComponent and its human activity timer.
        if (this.activity.isLocked() || this.activity.millisecondsUntilIdle() === 0) {
          return throwError(() => error);
        }
        if (!this.activity.isRecent()) {
          // Do not treat a background scheduler 401 as a user interaction.
          return throwError(() => error);
        }

        const newest = this.session.getToken();
        if (req.method === 'GET' && newest && newest !== token &&
            this.isValidToken(newest)) {
          // Another tab renewed while this GET was in flight.
          return next.handle(req.clone({
            setHeaders: { Authorization: `Bearer ${newest}` },
          }));
        }

        this.endInvalidSession();
        return throwError(() => error);
      })
    );
  }

  private endInvalidSession(): void {
    if (this.activity.isLocked()) return;
    this.session.clearSession();
    this.activity.clear();
    if (this.router.url !== '/login') {
      this.router.navigate(['/login']);
    }
  }

  private isValidToken(token: string): boolean {
    try {
      return !this.jwt.isTokenExpired(token);
    } catch {
      return false;
    }
  }

  private isLoginRequest(url: string): boolean {
    return /\/auth\/(?:login|refresh|logout)(?:[?#]|$)/.test(url);
  }

  private isApiRequest(url: string): boolean {
    if (!url) return false;
    // In this project environment.apiUrl is /api; keep same-origin strictly.
    if (environment.apiUrl.startsWith('/')) {
      if (url === environment.apiUrl || url.startsWith(environment.apiUrl + '/')) {
        return true;
      }
      if (typeof window !== 'undefined') {
        try {
          const resolved = new URL(url, window.location.origin);
          return resolved.origin === window.location.origin &&
            (resolved.pathname === environment.apiUrl ||
             resolved.pathname.startsWith(environment.apiUrl + '/'));
        } catch { return false; }
      }
      return false;
    }
    return url.startsWith(environment.apiUrl + '/');
  }
}
