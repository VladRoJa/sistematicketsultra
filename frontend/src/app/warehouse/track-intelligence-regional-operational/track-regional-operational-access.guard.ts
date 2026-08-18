import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';


const ENABLED_USERNAMES = ['ADMICORP'];

const ENABLED_ROLES: string[] = [
  // 'ADMIN',
  // 'ADMINISTRADOR',
  // 'SUPER_ADMIN',
  // 'LECTOR_GLOBAL',
  // 'GERENTE_REGIONAL',
];


export function canAccessTrackRegionalOperational(user: any): boolean {
  const username = String(user?.username || '').trim().toUpperCase();
  const role = String(user?.rol || '').trim().toUpperCase();

  return (
    ENABLED_USERNAMES.includes(username) ||
    ENABLED_ROLES.includes(role)
  );
}


export const trackRegionalOperationalAccessGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (canAccessTrackRegionalOperational(authService.getUser())) {
    return true;
  }

  return router.createUrlTree(['/warehouse/track']);
};
