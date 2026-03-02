// frontend/src/app/guards/auth.guard.ts

import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { Observable, of } from 'rxjs';
import { catchError, map, tap } from 'rxjs/operators';

import { SessionService } from '../core/auth/session.service';
import { AuthService } from '../services/auth.service';

@Injectable({
  providedIn: 'root'
})
export class AuthGuard implements CanActivate {
  constructor(
    private session: SessionService,
    private authService: AuthService,
    private router: Router
  ) {}

  canActivate(): Observable<boolean> {
    const token = this.session.getToken();
    const user = this.session.getUser();

    // 1) Sin token => login
    if (!token) {
      this.router.navigate(['/login']);
      return of(false);
    }

    // 2) Ya hay user => ok
    if (user) {
      return of(true);
    }

    // 3) Token existe pero user aún no => hidratar
    return this.authService.obtenerUsuarioAutenticado().pipe(
      map(() => true),
      tap(() => console.log('✅ AuthGuard: sesión hidratada')),
      catchError((err) => { 
        this.session.clearSession();
        this.router.navigate(['/login']);
        console.log('AuthGuard hydration error status:', err?.status, err);
        return of(false);
      }),
    );
  }
}