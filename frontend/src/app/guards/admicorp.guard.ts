// frontend/src/app/guards/admicorp.guard.ts

import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { SessionService } from '../core/auth/session.service';

@Injectable({
  providedIn: 'root',
})
export class AdmicorpGuard implements CanActivate {
  constructor(
    private session: SessionService,
    private router: Router,
  ) {}

  canActivate(): boolean {
    const user = this.session.getUser();

    if (!user) {
      this.router.navigate(['/login']);
      return false;
    }

    const username = String(user.username || '').trim().toUpperCase();

    if (username === 'ADMICORP') {
      return true;
    }

    this.router.navigate(['/main/ver-tickets']);
    return false;
  }
}
