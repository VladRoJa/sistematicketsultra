import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export type PurchaseRequisitionStatus =
  | 'PENDING_REVIEW'
  | 'NEEDS_INFO'
  | 'REJECTED'
  | 'IN_QUOTATION'
  | 'CLOSED';

export type PurchaseRequisitionPriority = 'NORMAL' | 'HIGH' | 'CRITICAL';

export interface PurchaseRequisitionItem {
  id?: number;
  requisition_id?: number;
  item_description: string;
  quantity: number;
  notes?: string | null;
  created_at?: string | null;
}

export interface PurchaseRequisitionEvent {
  id: number;
  requisition_id: number;
  event_type: string;
  actor_user_id?: number | null;
  from_status?: string | null;
  to_status?: string | null;
  comment?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface PurchaseRequisitionAttachment {
  id: number;
  requisition_id: number;
  event_id?: number | null;
  attachment_type: 'EVIDENCE' | 'QUOTE' | 'OTHER';
  original_filename: string;
  storage_key: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by_user_id?: number | null;
  created_at?: string | null;
  deleted_at?: string | null;
}

export interface PurchaseRequisition {
  id: number;
  public_id: string;
  sucursal_id: number;
  created_by_user_id: number;
  category: string;
  reason: string;
  justification: string;
  priority: PurchaseRequisitionPriority;
  status: PurchaseRequisitionStatus;
  approved_by_user_id?: number | null;
  approved_at?: string | null;
  approval_comment?: string | null;
  rejected_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  items?: PurchaseRequisitionItem[];
  events?: PurchaseRequisitionEvent[];
  attachments?: PurchaseRequisitionAttachment[];
}

export interface PurchaseRequisitionListFilters {
  status?: string;
  sucursal_id?: number | null;
  priority?: string;
  date_from?: string;
  date_to?: string;
}

export interface CreatePurchaseRequisitionPayload {
  sucursal_id: number;
  category?: 'GYM_EQUIPMENT';
  reason: string;
  justification: string;
  priority: PurchaseRequisitionPriority;
  items: Array<{
    item_description: string;
    quantity: number;
    notes?: string | null;
  }>;
}

@Injectable({
  providedIn: 'root',
})
export class PurchaseRequisitionService {
  private readonly apiUrl = `${environment.apiUrl}/purchase-requisitions`;

  constructor(private readonly http: HttpClient) {}

  listBranches(): Observable<any[]> {
    return this.http.get<any[]>(`${environment.apiUrl}/sucursales/listar`);
  }

  list(filters: PurchaseRequisitionListFilters = {}): Observable<{
    rows: PurchaseRequisition[];
    count: number;
  }> {
    let params = new HttpParams();

    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        params = params.set(key, String(value));
      }
    });

    return this.http.get<{
      rows: PurchaseRequisition[];
      count: number;
    }>(this.apiUrl, { params });
  }

  get(requisitionId: number): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.get<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}`,
    );
  }

  create(payload: CreatePurchaseRequisitionPayload): Observable<{
    requisition: PurchaseRequisition;
  }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      this.apiUrl,
      payload,
    );
  }

  requesterEdit(
    requisitionId: number,
    payload: Partial<CreatePurchaseRequisitionPayload>,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.put<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/requester-edit`,
      payload,
    );
  }

  requestInfo(
    requisitionId: number,
    comment: string,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/request-info`,
      { comment },
    );
  }

  resubmit(
    requisitionId: number,
    comment?: string,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/resubmit`,
      { comment: comment || null },
    );
  }

  approve(
    requisitionId: number,
    comment?: string,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/approve`,
      { comment: comment || null },
    );
  }

  reject(
    requisitionId: number,
    reason: string,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/reject`,
      { reason },
    );
  }

  uploadAttachment(
    requisitionId: number,
    attachmentType: 'EVIDENCE' | 'QUOTE' | 'OTHER',
    file: File,
  ): Observable<{ attachment: PurchaseRequisitionAttachment }> {
    const formData = new FormData();
    formData.append('attachment_type', attachmentType);
    formData.append('file', file, file.name);

    return this.http.post<{ attachment: PurchaseRequisitionAttachment }>(
      `${this.apiUrl}/${requisitionId}/attachments`,
      formData,
    );
  }

  downloadAttachment(
    requisitionId: number,
    attachmentId: number,
  ): Observable<Blob> {
    return this.http.get(
      `${this.apiUrl}/${requisitionId}/attachments/${attachmentId}/file`,
      { responseType: 'blob' },
    );
  }
}
