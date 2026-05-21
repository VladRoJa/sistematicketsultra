
// frontend-angular/src/app/interceptors/auth.interceptor.ts

import { Injectable } from '@angular/core';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse,
} from '@angular/common/http';
import { Observable, throwError, Subject } from 'rxjs';
import { catchError, switchMap, take } from 'rxjs/operators';
import { MatDialog } from '@angular/material/dialog';

import { SessionService } from '../core/auth/session.service';
import { ReauthModalComponent } from '../reauth-modal/reauth-modal.component';
import { environment } from 'src/environments/environment';

@Injectable()
export class TokenInterceptor implements HttpInterceptor {
  private isReauthInProgress = false;
  private reauthSubject = new Subject<string | null>();

  constructor(
    private session: SessionService,
    private dialog: MatDialog,
  ) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const isApiCall = this.isApiRequest(req.url);
    const token = this.session.getToken();

    const authReq =
      token && isApiCall
        ? req.clone({ headers: req.headers.set('Authorization', `Bearer ${token}`) })
        : req;

    return next.handle(authReq).pipe(
      catchError((error: HttpErrorResponse) => {
        const isLoginRequest = req.url.includes('/auth/login');

        if (error.status === 401 && isApiCall && !isLoginRequest) {
          return this.handle401Error(req, next);
        }

        return throwError(() => error);
      }),
    );
  }

  private isApiRequest(url: string): boolean {
    if (!url) return false;

    if (url.startsWith('/api')) return true;

    return url.startsWith(environment.apiUrl);
  }

  private handle401Error(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    if (!this.isReauthInProgress) {
      this.isReauthInProgress = true;
      this.reauthSubject = new Subject<string | null>();

      return this.dialog
        .open(ReauthModalComponent, {
          disableClose: true,
          width: '440px',
          maxWidth: '94vw',
          panelClass: 'suite-reauth-dialog',
          backdropClass: 'suite-dialog-backdrop',
          autoFocus: false,
          restoreFocus: false,
        })
        .afterClosed()
        .pipe(
          switchMap((result) => {
            this.isReauthInProgress = false;

            if (result?.token) {
              this.session.setSession(result.token, result.user || {});
              this.reauthSubject.next(result.token);
              this.reauthSubject.complete();

              const newRequest = req.clone({
                headers: req.headers.set('Authorization', `Bearer ${result.token}`),
              });

              return next.handle(newRequest);
            }

            this.reauthSubject.next(null);
            this.reauthSubject.complete();

            return throwError(() => new Error('Reautenticación cancelada'));
          }),
        );
    }

    return this.reauthSubject.pipe(
      take(1),
      switchMap((token) => {
        if (!token) {
          return throwError(() => new Error('Reautenticación cancelada'));
        }

        const newRequest = req.clone({
          headers: req.headers.set('Authorization', `Bearer ${token}`),
        });

        return next.handle(newRequest);
      }),
    );
  }
}