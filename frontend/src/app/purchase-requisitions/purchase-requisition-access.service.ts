import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export interface PurchaseRequisitionAccess {
  allowed: boolean;
  can_create: boolean;
  can_review: boolean;
  can_manage_quotation: boolean;
  can_approve_requisition_quote: boolean;
  can_manage_requisition_logistics: boolean;
  can_confirm_receipt: boolean;
  can_admin_correct_requisition: boolean;
  can_configure_finance_approvers: boolean;
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

  constructor(private readonly http: HttpClient) {}

  getAccess(_force = false): Observable<PurchaseRequisitionAccess> {
    return this.http.get<PurchaseRequisitionAccess>(
      `${this.apiUrl}/access`,
    );
  }
}
