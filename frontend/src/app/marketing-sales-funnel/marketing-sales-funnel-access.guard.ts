import { Injectable } from '@angular/core';
import { ActivatedRouteSnapshot, CanActivate, Router, RouterStateSnapshot } from '@angular/router';
import { FUNNEL_ORIGINAL_PATH, isFunnelProvider } from '../core/auth/funnel-provider-access';

import { SessionService } from '../core/auth/session.service';

@Injectable({
  providedIn: 'root',
})
export class MarketingSalesFunnelAccessGuard implements CanActivate {
  constructor(
    private readonly session: SessionService,
    private readonly router: Router,
  ) {}

  canActivate(_route: ActivatedRouteSnapshot, state: RouterStateSnapshot): boolean {
    const user = this.session.getUser();

    if (!user) {
      this.router.navigate(['/login']);
      return false;
    }

    const username = String(user.username || '').trim().toUpperCase();
    const role = String(user.rol ?? user.role ?? '').trim().toUpperCase();
    if (isFunnelProvider(user)) {
      return state.url.split(/[?#]/)[0] === FUNNEL_ORIGINAL_PATH;
    }

    if (
      username === 'ADMICORP'
      || role === 'LECTOR_GLOBAL'
      || role === 'GERENTE'
      || role === 'GERENTE_REGIONAL'
      || role === 'MARKETING'
    ) {
      return true;
    }

    this.router.navigate(['/main/ver-tickets']);
    return false;
  }
}
