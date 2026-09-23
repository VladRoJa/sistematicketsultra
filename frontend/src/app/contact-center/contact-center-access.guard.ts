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

const CONTACT_CENTER_MANAGER_ALLOWED_BRANCH_IDS = new Set([
  1,
  7,
  8,
  9,
  10,
  11,
  12,
  13,
]);


export function canAccessContactCenter(user: unknown): boolean {
  const value = (user || {}) as {
    username?: string;
    rol?: string;
    role?: string;
    sucursal_id?: number | string | null;
    sucursales_ids?: Array<number | string>;
  };

  const username = String(value.username || '').trim().toUpperCase();
  const role = String(value.rol ?? value.role ?? '').trim().toUpperCase();

  const branchIds = new Set<number>();
  const primaryBranchId = Number(value.sucursal_id);
  if (Number.isInteger(primaryBranchId) && primaryBranchId > 0) {
    branchIds.add(primaryBranchId);
  }
  for (const rawValue of value.sucursales_ids ?? []) {
    const branchId = Number(rawValue);
    if (Number.isInteger(branchId) && branchId > 0) {
      branchIds.add(branchId);
    }
  }

  const managerPilotAccess = (
    role === 'GERENTE'
    && [...branchIds].some(
      (branchId) => CONTACT_CENTER_MANAGER_ALLOWED_BRANCH_IDS.has(branchId),
    )
  );

  return (
    CONTACT_CENTER_INITIAL_USERS.has(username)
    || CONTACT_CENTER_INITIAL_ROLES.has(role)
    || managerPilotAccess
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