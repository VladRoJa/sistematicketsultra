import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';


export function canAccessTrackTiendaComposition(user: any): boolean {
  const username = String(user?.username || '').trim().toUpperCase();
  const role = String(user?.rol ?? user?.role ?? '').trim().toUpperCase();

  return username === 'ADMICORP' || role === 'TIENDA';
}


export const trackTiendaCompositionAccessGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (canAccessTrackTiendaComposition(authService.getUser())) {
    return true;
  }

  return router.createUrlTree(['/warehouse/track']);
};
