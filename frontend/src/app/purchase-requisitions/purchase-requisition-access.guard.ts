import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { PurchaseRequisitionAccessService } from './purchase-requisition-access.service';

export const purchaseRequisitionAccessGuard: CanActivateFn = () => {
  const accessService = inject(PurchaseRequisitionAccessService);
  const router = inject(Router);

  return accessService.getAccess().pipe(
    map((access) => (
      access?.allowed
        ? true
        : router.createUrlTree(['/main/ver-tickets'])
    )),
    catchError(() => of(router.createUrlTree(['/main/ver-tickets']))),
  );
};
