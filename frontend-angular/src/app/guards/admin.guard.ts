// admin.guard.ts
// ✅ Guard para proteger rutas solo para administradores

import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Injectable({
  providedIn: 'root'
})
export class AdminGuard implements CanActivate {

  constructor(private authService: AuthService, private router: Router) {}

  canActivate(): boolean {
    const user = this.authService.getUser();

    if (!user) {
      this.router.navigate(['/login']);
      return false;
    }

    // Revisa el rol en minúsculas, permite admin o super_admin (fácil de ampliar)
    const rol = (user.rol || '').toLowerCase();
    if (rol === 'administrador' || rol === 'super_admin') {
      return true;
    }

    this.router.navigate(['/ver-tickets']);
    return false;
  }
}

