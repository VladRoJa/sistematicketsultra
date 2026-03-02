// frontend/src/app/guards/admin.guard.ts
// ✅ Guard para proteger rutas solo para administradores

import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { SessionService } from '../core/auth/session.service';

@Injectable({
  providedIn: 'root'
})
export class AdminGuard implements CanActivate {

  constructor(private session: SessionService, private router: Router) {}

  canActivate(): boolean {
    const user = this.session.getUser();

    if (!user) {
      this.router.navigate(['/login']);
      return false;
    }

    if (this.session.isAdmin()) {
      return true;
    }

    this.router.navigate(['/ver-tickets']);
    return false;
  }
}