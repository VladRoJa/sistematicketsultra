import { inject } from '@angular/core';
import {
  CanActivateFn,
  Router,
} from '@angular/router';
import {
  catchError,
  map,
  of,
} from 'rxjs';

import { SystemDailyCheckBiService } from './system-daily-check-bi.service';

export const systemDailyCheckBiAccessGuard: CanActivateFn = () => {
  const service = inject(SystemDailyCheckBiService);
  const router = inject(Router);

  return service.getContext().pipe(
    map((context) => (
      context.allowed
        ? true
        : router.createUrlTree(['/main/ver-tickets'])
    )),
    catchError(() => of(
      router.createUrlTree(['/main/ver-tickets']),
    )),
  );
};
