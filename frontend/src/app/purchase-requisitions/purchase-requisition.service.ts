import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export type PurchaseRequisitionStatus =
  | 'PENDING_REVIEW'
  | 'NEEDS_INFO'
  | 'REJECTED'
  | 'IN_QUOTATION'
  | 'QUOTE_PENDING_FINANCE_APPROVAL'
  | 'PAYMENT_REQUESTED'
  | 'SHIPPING_IN_PROGRESS'
  | 'IMPORT_IN_PROGRESS'
  | 'FINAL_DESTINATION_SHIPMENT'
  | 'RECEIPT_ISSUE'
  | 'CLOSED';

export type PurchaseRequisitionPriority = 'NORMAL' | 'HIGH' | 'CRITICAL';

export type PurchaseRequisitionAttachmentType =
  | 'EVIDENCE'
  | 'QUOTE'
  | 'OTHER'
  | 'RECEIPT_EVIDENCE'
  | 'RECEIPT_ISSUE_EVIDENCE';

export type PurchaseRequisitionQuoteFinanceStatus =
  | 'DRAFT'
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED';

export type PurchaseRequisitionReceiptIssueType =
  | 'DAMAGED'
  | 'INCOMPLETE'
  | 'WRONG_ITEM'
  | 'OTHER';

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
  attachment_type: PurchaseRequisitionAttachmentType;
  original_filename: string;
  storage_key: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by_user_id?: number | null;
  created_at?: string | null;
  deleted_at?: string | null;
}


export interface PurchaseRequisitionQuote {
  id: number;
  requisition_id: number;
  supplier_name: string;
  amount: number;
  currency: string;
  quote_date: string;
  attachment_id: number;
  notes?: string | null;
  created_by_user_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  is_selected: boolean;
  selected_by_user_id?: number | null;
  selected_at?: string | null;
  finance_status: PurchaseRequisitionQuoteFinanceStatus;
  finance_submitted_by_user_id?: number | null;
  finance_submitted_at?: string | null;
  finance_decided_by_user_id?: number | null;
  finance_decided_at?: string | null;
  finance_comment?: string | null;
}

export interface PurchaseRequisitionFinanceApproverUser {
  id: number;
  username: string;
  email?: string | null;
  role: string;
}

export interface PurchaseRequisitionFinanceApprover {
  id: number;
  user_id: number;
  is_active: boolean;
  added_by_user_id?: number | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  user?: PurchaseRequisitionFinanceApproverUser | null;
  added_by_user?: PurchaseRequisitionFinanceApproverUser | null;
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
  quotes?: PurchaseRequisitionQuote[];
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


export interface CreatePurchaseRequisitionQuotePayload {
  supplier_name: string;
  amount: number;
  currency: string;
  quote_date: string;
  attachment_id: number;
  notes?: string | null;
}

export interface PurchaseRequisitionFinanceApproverListResponse {
  rows: PurchaseRequisitionFinanceApprover[];
  count: number;
  active_count: number;
}

export interface CreatePurchaseRequisitionFinanceApproverPayload {
  user_id: number;
  notes?: string | null;
}

export interface UpdatePurchaseRequisitionFinanceApproverPayload {
  is_active?: boolean;
  notes?: string | null;
}

export interface AdministrativeCorrectionPayload {
  target_status: PurchaseRequisitionStatus;
  reason: string;
  comment: string;
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
    attachmentType: PurchaseRequisitionAttachmentType,
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

  listFinanceApprovers(): Observable<PurchaseRequisitionFinanceApproverListResponse> {
    return this.http.get<PurchaseRequisitionFinanceApproverListResponse>(
      `${this.apiUrl}/config/finance-approvers`,
    );
  }

  createFinanceApprover(
    payload: CreatePurchaseRequisitionFinanceApproverPayload,
  ): Observable<{ approver: PurchaseRequisitionFinanceApprover }> {
    return this.http.post<{ approver: PurchaseRequisitionFinanceApprover }>(
      `${this.apiUrl}/config/finance-approvers`,
      payload,
    );
  }

  updateFinanceApprover(
    userId: number,
    payload: UpdatePurchaseRequisitionFinanceApproverPayload,
  ): Observable<{ approver: PurchaseRequisitionFinanceApprover }> {
    return this.http.put<{ approver: PurchaseRequisitionFinanceApprover }>(
      `${this.apiUrl}/config/finance-approvers/${userId}`,
      payload,
    );
  }

  createQuote(
    requisitionId: number,
    payload: CreatePurchaseRequisitionQuotePayload,
  ): Observable<{ quote: PurchaseRequisitionQuote }> {
    return this.http.post<{ quote: PurchaseRequisitionQuote }>(
      `${this.apiUrl}/${requisitionId}/quotes`,
      payload,
    );
  }

  selectQuote(
    requisitionId: number,
    quoteId: number,
  ): Observable<{ quote: PurchaseRequisitionQuote }> {
    return this.http.post<{ quote: PurchaseRequisitionQuote }>(
      `${this.apiUrl}/${requisitionId}/quotes/${quoteId}/select`,
      {},
    );
  }

  submitQuoteForFinance(
    requisitionId: number,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/submit-quote-for-finance`,
      {},
    );
  }

  approveQuoteByFinance(
    requisitionId: number,
    comment?: string,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/finance/approve-quote`,
      { comment: comment || null },
    );
  }

  rejectQuoteByFinance(
    requisitionId: number,
    reason: string,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/finance/reject-quote`,
      { reason },
    );
  }

  advanceLogistics(
    requisitionId: number,
    targetStatus: PurchaseRequisitionStatus,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/advance-logistics`,
      { target_status: targetStatus },
    );
  }

  confirmReceipt(
    requisitionId: number,
    payload: {
      comment?: string | null;
      evidence_attachment_ids?: number[];
    } = {},
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/confirm-receipt`,
      payload,
    );
  }

  reportReceiptIssue(
    requisitionId: number,
    payload: {
      issue_type: PurchaseRequisitionReceiptIssueType;
      comment: string;
      evidence_attachment_ids: number[];
    },
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/report-receipt-issue`,
      payload,
    );
  }

  resumeLogistics(
    requisitionId: number,
    comment: string,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/resume-logistics`,
      { comment },
    );
  }

  administrativeCorrection(
    requisitionId: number,
    payload: AdministrativeCorrectionPayload,
  ): Observable<{ requisition: PurchaseRequisition }> {
    return this.http.post<{ requisition: PurchaseRequisition }>(
      `${this.apiUrl}/${requisitionId}/administrative-correction`,
      payload,
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
