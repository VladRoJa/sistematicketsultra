import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export type GascaSmsRequestStatus =
  | 'pending'
  | 'gasca_searching'
  | 'ready_to_send'
  | 'multiple_candidates_selected_latest'
  | 'sms_sending'
  | 'sent'
  | 'code_not_found'
  | 'phone_not_found_for_pin'
  | 'code_not_generated_today'
  | 'code_already_used'
  | 'phone_required_for_contract'
  | 'manual_review'
  | 'failed';

export type GascaSmsMotivo =
  | 'HUELLA_NO_LEIDA'
  | 'VISITA_PROSPECTO'
  | 'SMS_NO_LLEGA'
  | 'OTRO';

export interface GascaSmsCatalogsResponse {
  motivos: GascaSmsMotivo[];
  global_access: boolean;
  allowed_sucursales_ids: number[] | null;
}

export interface GascaSmsRequest {
  id: number;
  pin_normalized: string;
  requested_phone_masked: string;
  motivo: GascaSmsMotivo | string;
  motivo_detalle: string | null;
  status: GascaSmsRequestStatus | string;
  user_message: string | null;
  sucursal_id: number | null;
  requested_by_user_id: number | null;
  gasca_nombre_masked: string | null;
  gasca_phone_masked: string | null;
  gasca_code_masked: string | null;
  gasca_generated_raw: string | null;
  gasca_used_raw: string | null;
  gasca_sucursal: string | null;
  sms_provider: string | null;
  attempt_count: number;
  last_attempt_at: string | null;
  processed_at: string | null;
  sent_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateGascaSmsRequestPayload {
  pin: string;
  telefono: string;
  motivo: GascaSmsMotivo | string;
  motivo_detalle?: string | null;
  sucursal_id?: number | null;
}

export interface CreateGascaSmsRequestResponse {
  message: string;
  request: GascaSmsRequest;
}

export interface GascaSmsRequestsListResponse {
  items: GascaSmsRequest[];
  count: number;
  limit: number;
}

export interface GascaSmsRequestDetailResponse {
  request: GascaSmsRequest;
}

export interface GascaSmsRequestsListParams {
  limit?: number;
  status?: string;
  pin?: string;
  sucursal_id?: number | null;
}

@Injectable({
  providedIn: 'root',
})
export class RpaGascaSmsService {
  private readonly apiUrl = `${environment.apiUrl}/rpa/gasca-sms`;

  constructor(private http: HttpClient) {}

  getCatalogs(): Observable<GascaSmsCatalogsResponse> {
    return this.http.get<GascaSmsCatalogsResponse>(`${this.apiUrl}/catalogs`);
  }

  createRequest(
    payload: CreateGascaSmsRequestPayload,
  ): Observable<CreateGascaSmsRequestResponse> {
    return this.http.post<CreateGascaSmsRequestResponse>(
      `${this.apiUrl}/requests`,
      payload,
    );
  }

  listRequests(
    params: GascaSmsRequestsListParams = {},
  ): Observable<GascaSmsRequestsListResponse> {
    let httpParams = new HttpParams();

    if (params.limit != null) {
      httpParams = httpParams.set('limit', String(params.limit));
    }

    if (params.status) {
      httpParams = httpParams.set('status', params.status);
    }

    if (params.pin) {
      httpParams = httpParams.set('pin', params.pin);
    }

    if (params.sucursal_id != null) {
      httpParams = httpParams.set('sucursal_id', String(params.sucursal_id));
    }

    return this.http.get<GascaSmsRequestsListResponse>(
      `${this.apiUrl}/requests`,
      { params: httpParams },
    );
  }

  getRequest(id: number): Observable<GascaSmsRequestDetailResponse> {
    return this.http.get<GascaSmsRequestDetailResponse>(
      `${this.apiUrl}/requests/${id}`,
    );
  }
}
