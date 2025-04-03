//auth.interceptor.ts

import { Injectable } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpHandler, HttpEvent, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { MatDialog } from '@angular/material/dialog';
import { AuthService } from '../services/auth.service';
import { ReauthModalComponent } from '../reauth-modal/reauth-modal.component';

@Injectable()
export class TokenInterceptor implements HttpInterceptor {
  constructor(private authService: AuthService, private dialog: MatDialog) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    // Clonar la petición e incluir el token si existe
    let authReq = req;
    const token = this.authService.getToken();
    if (token) {
      authReq = req.clone({
        headers: req.headers.set('Authorization', `Bearer ${token}`)
      });
    }

    return next.handle(authReq).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 401) {
          // Se abre el modal de reautenticación si el token ha expirado
          const dialogRef = this.dialog.open(ReauthModalComponent, {
            disableClose: true // Evita que se cierre sin acción
          });
          return dialogRef.afterClosed().pipe(
            switchMap(result => {
              if (result && result.token) {
                // Se actualiza el token en el AuthService
                this.authService.setSession(result.token, result.user || {});
                // Se reintenta la petición original con el nuevo token
                const newRequest = req.clone({
                  headers: req.headers.set('Authorization', `Bearer ${result.token}`)
                });
                return next.handle(newRequest);
              }
              // Si no se obtuvo un nuevo token, se propaga el error
              return throwError(() => error);
            })
          );
        }
        return throwError(() => error);
      })
    );
  }
}
