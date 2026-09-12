import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { ControlCenterService } from './control-center.service';

export const controlAccessGuard: CanActivateFn = () => {
  const controlService = inject(ControlCenterService);
  const router = inject(Router);

  return controlService.getContext().pipe(
    map(() => true),
    catchError(() => of(router.createUrlTree(['/main/ver-tickets']))),
  );
};
