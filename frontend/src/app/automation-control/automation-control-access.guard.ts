import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AutomationControlService } from './automation-control.service';
export const automationControlAccessGuard:CanActivateFn = () => {
  const service = inject(AutomationControlService);
  const router = inject(Router);
  return service.summary().pipe(map(() => true),catchError(() => of(router.createUrlTree(['/main/ver-tickets']))));
};
