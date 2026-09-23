import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { SessionService } from '../core/auth/session.service';


const CONTACT_CENTER_INITIAL_USERS = new Set([
  'ADMICORP',
  'SANDRA',
]);

const CONTACT_CENTER_INITIAL_ROLES = new Set([
  'SANDRA',
]);


export function canAccessContactCenter(user: unknown): boolean {
  const value = (user || {}) as {
    username?: string;
    rol?: string;
    role?: string;
  };

  const username = String(value.username || '').trim().toUpperCase();
  const role = String(value.rol ?? value.role ?? '').trim().toUpperCase();

  return (
    CONTACT_CENTER_INITIAL_USERS.has(username)
    || CONTACT_CENTER_INITIAL_ROLES.has(role)
  );
}


export const contactCenterAccessGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  const user = session.getUser();

  if (!user) {
    return router.createUrlTree(['/login']);
  }

  if (canAccessContactCenter(user)) {
    return true;
  }

  return router.createUrlTree(['/main/ver-tickets']);
};
