//frontend/src/app/warehouse/services/warehouse-uploads.service.ts

import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface WarehouseUploadListItem {
  id: number;
  original_filename: string;
  stored_filename: string;
  stored_path: string;
  file_size_bytes: number;
  file_hash_sha256: string;
  mime_type: string | null;
  extension: string;
  report_type_id: number;
  report_type_key: string | null;
  report_type_label: string | null;
  source_id: number;
  source_key: string | null;
  source_label: string | null;
  family_id: number;
  family_key: string | null;
  family_label: string | null;
  operational_role_id: number;
  operational_role_key: string | null;
  operational_role_label: string | null;
  period_type: string;
  cutoff_date: string | null;
  date_from: string | null;
  date_to: string | null;
  status: string;
  uploaded_by_user_id: number;
  uploaded_by_username: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type WarehouseUploadDatePreset =
  | 'today'
  | 'yesterday'
  | 'last_7_days'
  | 'current_month'
  | 'custom'
  | 'all';

export type WarehouseUploadStatusFilter = 'ALL' | 'ACTIVE' | 'ARCHIVED';

export interface WarehouseUploadListParams {
  page?: number;
  page_size?: number;
  date_preset?: WarehouseUploadDatePreset;
  date_from?: string;
  date_to?: string;
  source_key?: string;
  report_type_key?: string;
  status?: WarehouseUploadStatusFilter;
  period_type?: string;
  search?: string;
}

export interface WarehouseUploadListResponse {
  items: WarehouseUploadListItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
  filters?: Record<string, unknown>;
}

export interface WarehouseUploadDetail {
  id: number;
  original_filename: string;
  stored_filename: string;
  stored_path: string;
  file_size_bytes: number;
  file_hash_sha256: string;
  mime_type: string | null;
  extension: string;
  report_type_id: number;
  report_type_key: string | null;
  report_type_label: string | null;
  source_id: number;
  source_key: string | null;
  source_label: string | null;
  family_id: number;
  family_key: string | null;
  family_label: string | null;
  operational_role_id: number;
  operational_role_key: string | null;
  operational_role_label: string | null;
  period_type: string;
  cutoff_date: string | null;
  date_from: string | null;
  date_to: string | null;
  status: string;
  uploaded_by_user_id: number;
  uploaded_by_username: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface WarehouseCreateUploadRequest {
  file: File;
  report_type_key: string;
  cutoff_date?: string;
  date_from?: string;
  date_to?: string;
  target_month?: string;
}

export interface WarehouseCreateUploadResponse {
  message: string;
  upload_id: number;
  filename: string;
  stored_filename: string;
  stored_path: string;
  file_size_bytes: number;
  file_hash_sha256: string;
  report_type_key: string;
  report_type_id: number;
  family_id: number;
  source_id: number;
  operational_role_id: number;
  period_type: string;
  cutoff_date: string;
  date_from: string;
  date_to: string;
  duplicate_detected: boolean;
  duplicate_upload_id: number | null;
}


export interface WarehouseUploadAuditItem {
  id: number;
  upload_id: number;
  action: string;
  performed_by_user_id: number;
  details: Record<string, unknown> | null;
  created_at: string | null;
}

export interface WarehouseUploadAuditResponse {
  items: WarehouseUploadAuditItem[];
}


@Injectable({
  providedIn: 'root'
})
export class WarehouseUploadsService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/warehouse/uploads`;

  getUploads(params: WarehouseUploadListParams = {}): Observable<WarehouseUploadListResponse> {
    return this.http.get<WarehouseUploadListResponse>(this.apiUrl, {
      headers: this.buildAuthHeaders(),
      params: this.buildListParams(params),
    });
  }

private buildListParams(params: WarehouseUploadListParams): HttpParams {
  let httpParams = new HttpParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }

    httpParams = httpParams.set(key, String(value));
  });

  return httpParams;
}

  private buildAuthHeaders(): HttpHeaders {
    const token = localStorage.getItem('token') || '';

    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });
  }

  downloadUpload(uploadId: number) {
  return this.http.get(`${this.apiUrl}/${uploadId}/download`, {
    headers: this.buildAuthHeaders(),
    responseType: 'blob',
  });
}


getUploadDetail(uploadId: number): Observable<WarehouseUploadDetail> {
  return this.http.get<WarehouseUploadDetail>(`${this.apiUrl}/${uploadId}`, {
    headers: this.buildAuthHeaders(),
  });
}

archiveUpload(uploadId: number) {
  return this.http.patch<{ message: string; upload_id: number; status: string }>(
    `${this.apiUrl}/${uploadId}/archive`,
    {},
    {
      headers: this.buildAuthHeaders(),
    }
  );
}

createUpload(payload: WarehouseCreateUploadRequest) {
  const formData = new FormData();

  formData.append('file', payload.file);
  formData.append('report_type_key', payload.report_type_key);

  if (payload.cutoff_date) {
    formData.append('cutoff_date', payload.cutoff_date);
  }

  if (payload.date_from) {
    formData.append('date_from', payload.date_from);
  }

  if (payload.date_to) {
    formData.append('date_to', payload.date_to);
  }
  if (payload.target_month) {
    formData.append('target_month', payload.target_month);
  }

  return this.http.post<WarehouseCreateUploadResponse>(this.apiUrl, formData, {
    headers: this.buildAuthHeaders(),
  });
}

getUploadAudit(uploadId: number): Observable<WarehouseUploadAuditResponse> {
  return this.http.get<WarehouseUploadAuditResponse>(`${this.apiUrl}/${uploadId}/audit`, {
    headers: this.buildAuthHeaders(),
  });
}

}

