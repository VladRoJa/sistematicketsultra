import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AttendanceService } from './attendance/attendance.service';

export const sportsAnalysisAccessGuard: CanActivateFn = () => {
  const router = inject(Router);
  const attendanceService = inject(AttendanceService);

  return attendanceService.getContext().pipe(
    map(() => true),
    catchError(() =>
      of(
        router.createUrlTree([
          '/main/ver-tickets',
        ]),
      ),
    ),
  );
};
