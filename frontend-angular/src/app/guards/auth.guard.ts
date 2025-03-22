//auth.guard.ts

import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Injectable({
  providedIn: 'root'
})
export class AuthGuard implements CanActivate {
  constructor(private authService: AuthService, private router: Router) {console.log("🔥 AuthGuard inicializado.");}

  canActivate(): boolean {
    console.log("🛑 AuthGuard activado para:", this.router.url);

    console.log("🟡 AuthGuard ejecutado.");

    const user = this.authService.getUser();
    console.log("🔍 Usuario detectado en AuthGuard:", user);

    if (!user) {
        console.warn("🚫 No hay usuario autenticado. Redirigiendo a login...");
        this.router.navigate(['/login']);
        return false;
    }

    return true;
}


}
