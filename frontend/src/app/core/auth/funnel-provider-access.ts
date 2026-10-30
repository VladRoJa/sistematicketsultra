import { inject } from '@angular/core';
import { CanActivateChildFn, Router } from '@angular/router';
import { JwtHelperService } from '@auth0/angular-jwt';
import { SessionService } from './session.service';

export const FUNNEL_ORIGINAL_PATH = '/marketing-conversion/venta-total-original';

export function isFunnelProvider(user: any): boolean {
  return String(user?.rol ?? user?.role ?? '').trim().toUpperCase() === 'PROVEEDOR_FUNNEL_ORIGINAL';
}

export const funnelProviderRouteGuard: CanActivateChildFn = (_route, state) => {
  const session = inject(SessionService);
  const router = inject(Router);
  let user = session.getUser();
  if (!user && session.getToken()) {
    try {
      user = inject(JwtHelperService).decodeToken(session.getToken()!);
    } catch {
      return router.parseUrl('/login');
    }
  }
  const path = state.url.split(/[?#]/)[0];
  return !isFunnelProvider(user) || path === FUNNEL_ORIGINAL_PATH || path === '/login'
    ? true : router.parseUrl(FUNNEL_ORIGINAL_PATH);
};
