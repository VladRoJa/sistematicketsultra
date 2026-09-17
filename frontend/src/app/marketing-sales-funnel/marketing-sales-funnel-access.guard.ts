import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';

import { SessionService } from '../core/auth/session.service';

@Injectable({
  providedIn: 'root',
})
export class MarketingSalesFunnelAccessGuard implements CanActivate {
  constructor(
    private readonly session: SessionService,
    private readonly router: Router,
  ) {}

  canActivate(): boolean {
    const user = this.session.getUser();

    if (!user) {
      this.router.navigate(['/login']);
      return false;
    }

    const username = String(user.username || '').trim().toUpperCase();
    const role = String(user.rol ?? user.role ?? '').trim().toUpperCase();

    if (
      username === 'ADMICORP'
      || role === 'LECTOR_GLOBAL'
      || role === 'GERENTE'
    ) {
      return true;
    }

    this.router.navigate(['/main/ver-tickets']);
    return false;
  }
}
