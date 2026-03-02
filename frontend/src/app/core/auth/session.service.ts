// frontend-angular/src/app/core/auth/session.service.ts

import { Injectable } from '@angular/core';

export interface SessionUser {
  id?: number;
  username?: string;
  rol?: string;
  sucursal_id?: number;
  department_id?: number;
  email?: string;
  // deja abierto para tu payload real
  [key: string]: any;
}

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly TOKEN_KEY = 'token';
  private readonly USER_KEY = 'user';

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getUser(): SessionUser | null {
    const raw = localStorage.getItem(this.USER_KEY);
    if (!raw) return null;

    try {
      return JSON.parse(raw) as SessionUser;
    } catch {
      // si se corrompe, limpiamos para evitar loops raros
      localStorage.removeItem(this.USER_KEY);
      return null;
    }
  }

  getRol(): string | null {
    const user = this.getUser();
    return user?.rol ?? null;
  }

  setSession(token: string, user: SessionUser): void {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user || {}));
  }

  clearSession(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  }

  isLoggedIn(): boolean {
    return !!this.getToken();
  }

  // Helpers mínimos (ya los migramos después si quieres)
  isAdmin(): boolean {
    const rol = (this.getRol() || '').toLowerCase();
    return rol === 'administrador' || rol === 'super_admin' || rol === 'admin';
  }
}