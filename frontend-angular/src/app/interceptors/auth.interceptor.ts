// frontend-angular/src/app/interceptors/auth.interceptor.ts

import { Injectable } from '@angular/core';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse
} from '@angular/common/http';
import { Observable, throwError, BehaviorSubject } from 'rxjs';
import { catchError, filter, switchMap, take } from 'rxjs/operators';
import { MatDialog } from '@angular/material/dialog';
import { AuthService } from '../services/auth.service';
import { ReauthModalComponent } from '../reauth-modal/reauth-modal.component';

@Injectable()
export class TokenInterceptor implements HttpInterceptor {
  private isReauthInProgress = false;
  private reauthSubject = new BehaviorSubject<string | null>(null);

  constructor(
    private authService: AuthService,
    private dialog: MatDialog
  ) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    // Clonar la petición e incluir el token si existe
    const token = this.authService.getToken();
    const authReq = token
      ? req.clone({ headers: req.headers.set('Authorization', `Bearer ${token}`) })
      : req;

    return next.handle(authReq).pipe(
      catchError((error: HttpErrorResponse) => {
        // ⛔ Ignorar 401 en el login para evitar abrir modal
        if (error.status === 401 && !req.url.includes('/auth/login')) {
          return this.handle401Error(req, next);
        }
        return throwError(() => error);
      })
    );
  }

  private handle401Error(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    if (!this.isReauthInProgress) {
      this.isReauthInProgress = true;
      this.reauthSubject.next(null);

      return this.dialog.open(ReauthModalComponent, { disableClose: true })
        .afterClosed()
        .pipe(
          switchMap(result => {
            this.isReauthInProgress = false;

            if (result && result.token) {
              this.authService.setSession(result.token, result.user || {}, false);
              this.reauthSubject.next(result.token);

              const newRequest = req.clone({
                headers: req.headers.set('Authorization', `Bearer ${result.token}`)
              });
              return next.handle(newRequest);
            }

            return throwError(() => new Error('Reautenticación cancelada'));
          })
        );
    } else {
      return this.reauthSubject.pipe(
        filter(token => token !== null),
        take(1),
        switchMap(token => {
          const newRequest = req.clone({
            headers: req.headers.set('Authorization', `Bearer ${token}`)
          });
          return next.handle(newRequest);
        })
      );
    }
  }
}
