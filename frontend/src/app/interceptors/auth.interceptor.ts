// frontend-angular/src/app/interceptors/auth.interceptor.ts

import { Injectable } from '@angular/core';
import {
  HttpInterceptor,
  HttpRequest,
  HttpHandler,
  HttpEvent,
  HttpErrorResponse,
} from '@angular/common/http';
import { Observable, throwError, BehaviorSubject } from 'rxjs';
import { catchError, filter, switchMap, take } from 'rxjs/operators';
import { MatDialog } from '@angular/material/dialog';

import { AuthService } from '../services/auth.service';
import { ReauthModalComponent } from '../reauth-modal/reauth-modal.component';
import { environment } from 'src/environments/environment';

@Injectable()
export class TokenInterceptor implements HttpInterceptor {
  private isReauthInProgress = false;
  private reauthSubject = new BehaviorSubject<string | null>(null);

  constructor(
    private authService: AuthService,
    private dialog: MatDialog,
  ) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    /**
     * ✅ Solo agregamos Authorization a llamadas a nuestra API.
     * Evita mandar token a:
     * - assets (json, png, etc.)
     * - dominios externos
     * - llamadas no relacionadas
     */
    const isApiCall = this.isApiRequest(req.url);

    const token = this.authService.getToken();

    const authReq =
      token && isApiCall
        ? req.clone({ headers: req.headers.set('Authorization', `Bearer ${token}`) })
        : req;

    return next.handle(authReq).pipe(
      catchError((error: HttpErrorResponse) => {
        /**
         * ⛔ Ignorar 401 en el login para evitar abrir modal
         * Nota: usamos req.url para mantener tu comportamiento actual.
         */
        if (error.status === 401 && !req.url.includes('/auth/login')) {
          return this.handle401Error(req, next);
        }
        return throwError(() => error);
      }),
    );
  }

  /**
   * Determina si la URL pertenece a nuestra API.
   * Soporta:
   * - URLs relativas tipo "/api/..."
   * - URLs absolutas tipo "http://IP:5000/api/..."
   */
  private isApiRequest(url: string): boolean {
    if (!url) return false;

    // Caso 1: proxy local /api...
    if (url.startsWith('/api')) return true;

    // Caso 2: url absoluta (environment.apiUrl)
    // Ej: environment.apiUrl = "http://184.107.165.75:5000/api"
    return url.startsWith(environment.apiUrl);
  }

  private handle401Error(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    if (!this.isReauthInProgress) {
      this.isReauthInProgress = true;
      this.reauthSubject.next(null);

      return this.dialog
        .open(ReauthModalComponent, { disableClose: true })
        .afterClosed()
        .pipe(
          switchMap((result) => {
            this.isReauthInProgress = false;

            if (result && result.token) {
              this.authService.setSession(result.token, result.user || {}, false);
              this.reauthSubject.next(result.token);

              // Reintentar request original con nuevo token
              const newRequest = req.clone({
                headers: req.headers.set('Authorization', `Bearer ${result.token}`),
              });
              return next.handle(newRequest);
            }

            return throwError(() => new Error('Reautenticación cancelada'));
          }),
        );
    }

    // Si ya hay reauth en progreso, esperamos a que llegue token y reintentamos
    return this.reauthSubject.pipe(
      filter((token) => token !== null),
      take(1),
      switchMap((token) => {
        const newRequest = req.clone({
          headers: req.headers.set('Authorization', `Bearer ${token}`),
        });
        return next.handle(newRequest);
      }),
    );
  }
}