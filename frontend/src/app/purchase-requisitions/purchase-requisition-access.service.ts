import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, shareReplay } from 'rxjs';

import { environment } from '../../environments/environment';

export interface PurchaseRequisitionAccess {
  allowed: boolean;
  can_create: boolean;
  can_review: boolean;
  can_manage_quotation: boolean;
  global_read: boolean;
  allowed_branch_ids: number[];
  user?: {
    id: number;
    username: string;
    role: string;
  };
}

@Injectable({
  providedIn: 'root',
})
export class PurchaseRequisitionAccessService {
  private readonly apiUrl = `${environment.apiUrl}/purchase-requisitions`;
  private accessRequest$?: Observable<PurchaseRequisitionAccess>;

  constructor(private readonly http: HttpClient) {}

  getAccess(force = false): Observable<PurchaseRequisitionAccess> {
    if (force || !this.accessRequest$) {
      this.accessRequest$ = this.http
        .get<PurchaseRequisitionAccess>(`${this.apiUrl}/access`)
        .pipe(shareReplay(1));
    }

    return this.accessRequest$;
  }
}
