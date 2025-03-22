// admin.guard.ts
// ✅ Guard para proteger rutas solo para administradores

import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Injectable({
  providedIn: 'root'
})
export class AdminGuard implements CanActivate {

  constructor(private authService: AuthService, private router: Router) {console.log("🔥 AdminGuard inicializado.");}

  canActivate(): boolean {
    console.log("🛑 AdminGuard activado para:", this.router.url);

    console.log("🟡 AdminGuard ejecutado.");

    const user = this.authService.getUser();
    console.log("🔍 Usuario detectado en AdminGuard:", user);

    if (!user) {
        console.warn("🚫 No hay usuario autenticado. Redirigiendo a login...");
        this.router.navigate(['/login']);
        return false;
    }

    if (user.rol === "ADMINISTRADOR") { 
        console.log("✅ Acceso permitido: Usuario es administrador.");
        return true;
    } else {
        console.warn("🚫 Acceso denegado en AdminGuard: Usuario no es administrador.");
        this.router.navigate(['/ver-tickets']);
        return false;
    }
}





}
