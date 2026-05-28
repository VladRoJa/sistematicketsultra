// frontend/src/app/planning/services/planning-targets.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface PlanningAccessResponse {
  status: string;
  has_access: boolean;
  can_view: boolean;
  can_edit: boolean;
  can_submit: boolean;
  can_approve: boolean;
  can_publish: boolean;
  can_configure_model: boolean;
}

export interface PlanningModelConfigSummary {
  id: number;
  name: string;
  version: number;
  model_status?: string;
  status?: string;
  description?: string | null;
  trend_window_months?: number;
  trend_closed_months_only?: boolean;
  arpu_strategy?: string;
  bajas_strategy?: string;
  reactivaciones_strategy?: string;
  domiciliados_strategy?: string;
  aggregators_strategy?: string;
  new_branch_strategy?: string;
  risk_rules_json?: Record<string, unknown> | null;
  parameters_json?: Record<string, unknown> | null;
  created_by_user_id?: number | null;
  activated_by_user_id?: number | null;
  activated_at?: string | null;
  replaced_by_config_id?: number | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PlanningModelConfigsResponse {
  status: string;
  items: PlanningModelConfigSummary[];
}

export interface PlanningTargetBatchSummary {
  id: number;
  target_month: string;
  version: number;
  batch_status: string;
  scope: string;
  source_type: string;
  source_upload_id?: number | null;
  model_config_id?: number | null;
  model_config?: {
    id: number;
    name: string;
    version: number;
    status: string;
  } | null;
  scenario_base?: string | null;
  proposed_by_user_id?: number | null;
  proposed_at?: string | null;
  approved_by_user_id?: number | null;
  approved_at?: string | null;
  rejected_by_user_id?: number | null;
  rejected_at?: string | null;
  rejection_comment?: string | null;
  published_at?: string | null;
  is_canonical: boolean;
  notes?: string | null;
  created_by_user_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  branch_rows_count: number;
}

export interface PlanningTargetBatchesResponse {
  status: string;
  items: PlanningTargetBatchSummary[];
}

export interface PlanningTargetBranchRowDetail {
  id: number;
  batch_id: number;
  target_month: string;
  sucursal_canon: string;
  m2_sin_circulaciones: string;
  usuarios_inicio_mes: number;
  proyeccion_usuarios_cierre_mes: number;
  meta_faycgo_mes: string;
  meta_clientes_nuevos_mes: number;
  meta_reactivaciones_mes: number;
  meta_bajas_mes: number;
  meta_nuevos_domiciliados_mes: number;
  meta_arpu_mes: string;
  meta_venta_tienda_mes: string;
  ingreso_agregadoras_estimado?: string | null;
  usuarios_agregadoras_estimado?: number | null;
  scenario_used?: string | null;
  trend_classification?: string | null;
  risk_level?: string | null;
  status: string;
  previous_branch_row_id?: number | null;
  published_track_monthly_target_id?: number | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  adjustments: PlanningTargetAdjustmentDetail[];
}

export interface PlanningTargetAdjustmentDetail {
  id: number;
  variable_key: string;
  adjustment_value?: string | null;
  adjustment_type: string;
  driver_type: string;
  justification: string;
  created_by_user_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PlanningTargetApprovalEventDetail {
  id: number;
  event_type: string;
  from_status?: string | null;
  to_status?: string | null;
  actor_user_id?: number | null;
  actor_username_snapshot?: string | null;
  comment?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at?: string | null;
  branch_row_id?: number | null;
}

export interface PlanningTargetBatchDetail {
  id: number;
  target_month: string;
  version: number;
  status: string;
  scope: string;
  source_type: string;
  source_upload_id?: number | null;
  scenario_base?: string | null;
  published_at?: string | null;
  is_canonical: boolean;
  notes?: string | null;
  created_by_user_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  model_config?: PlanningModelConfigSummary | null;
  branch_rows: PlanningTargetBranchRowDetail[];
  approval_events: PlanningTargetApprovalEventDetail[];
  rejection_comment?: string | null;
}

export interface CreatePlanningTargetBatchPayload {
  target_month: string;
  version: number;
  model_config_id?: number | null;
  scope: string;
  source_type: string;
  scenario_base?: string | null;
  notes?: string | null;
}

export interface CreatePlanningTargetBatchResponse {
  status: string;
  id: number;
  target_month: string;
  version: number;
  batch_status: string;
  scope: string;
  source_type: string;
  model_config_id?: number | null;
}

export interface AddPlanningTargetBranchRowPayload {
  sucursal_canon: string;

  m2_sin_circulaciones: number;
  usuarios_inicio_mes: number;
  proyeccion_usuarios_cierre_mes: number;

  meta_faycgo_mes: number;
  meta_clientes_nuevos_mes: number;
  meta_reactivaciones_mes: number;
  meta_bajas_mes: number;
  meta_nuevos_domiciliados_mes: number;
  meta_arpu_mes: number;
  meta_venta_tienda_mes: number;

  ingreso_agregadoras_estimado?: number | null;
  usuarios_agregadoras_estimado?: number | null;

  scenario_used?: string | null;
  trend_classification?: string | null;
  risk_level?: string | null;
  status?: string;
  previous_branch_row_id?: number | null;
  notes?: string | null;
}

export interface AddPlanningTargetBranchRowResponse {
  status: string;
  id: number;
  batch_id: number;
  target_month: string;
  sucursal_canon: string;
  row_status: string;
  meta_faycgo_mes: string;
}

export interface PlanningActionResponse {
  status: string;
  id: number;
  target_month?: string;
  version?: number;
  previous_status?: string;
  batch_status?: string;
  proposed_by_user_id?: number | null;
  proposed_at?: string | null;
  approved_by_user_id?: number | null;
  approved_at?: string | null;
  rejected_by_user_id?: number | null;
  rejected_at?: string | null;
  rejection_comment?: string | null;
  published_at?: string | null;
  is_canonical?: boolean;
  created_targets_count?: number;
  replaced_active_targets_count?: number;
  event_id?: number;
}

@Injectable({
  providedIn: 'root',
})
export class PlanningTargetsService {
  private readonly baseUrl = `${environment.apiUrl}/planning/targets`;

  constructor(private readonly http: HttpClient) {}

  getAccess(): Observable<PlanningAccessResponse> {
    return this.http.get<PlanningAccessResponse>(`${this.baseUrl}/access`);
  }

  listModelConfigs(status?: string): Observable<PlanningModelConfigsResponse> {
    let params = new HttpParams();

    if (status) {
      params = params.set('status', status);
    }

    return this.http.get<PlanningModelConfigsResponse>(
      `${this.baseUrl}/model-configs`,
      { params },
    );
  }

  listBatches(filters?: {
    target_month?: string;
    status?: string;
  }): Observable<PlanningTargetBatchesResponse> {
    let params = new HttpParams();

    if (filters?.target_month) {
      params = params.set('target_month', filters.target_month);
    }

    if (filters?.status) {
      params = params.set('status', filters.status);
    }

    return this.http.get<PlanningTargetBatchesResponse>(
      `${this.baseUrl}/batches`,
      { params },
    );
  }

  createBatch(
    payload: CreatePlanningTargetBatchPayload,
  ): Observable<CreatePlanningTargetBatchResponse> {
    return this.http.post<CreatePlanningTargetBatchResponse>(
      `${this.baseUrl}/batches`,
      payload,
    );
  }

  getBatchDetail(batchId: number): Observable<PlanningTargetBatchDetail> {
    return this.http.get<PlanningTargetBatchDetail>(
      `${this.baseUrl}/batches/${batchId}`,
    );
  }

  addBranchRowToBatch(
    batchId: number,
    payload: AddPlanningTargetBranchRowPayload,
  ): Observable<AddPlanningTargetBranchRowResponse> {
    return this.http.post<AddPlanningTargetBranchRowResponse>(
      `${this.baseUrl}/batches/${batchId}/branch-rows`,
      payload,
    );
  }

  submitBatch(batchId: number, comment: string): Observable<PlanningActionResponse> {
    return this.http.post<PlanningActionResponse>(
      `${this.baseUrl}/batches/${batchId}/submit`,
      { comment },
    );
  }

  approveBatch(batchId: number, comment: string): Observable<PlanningActionResponse> {
    return this.http.post<PlanningActionResponse>(
      `${this.baseUrl}/batches/${batchId}/approve`,
      { comment },
    );
  }

  rejectBatch(batchId: number, comment: string): Observable<PlanningActionResponse> {
    return this.http.post<PlanningActionResponse>(
      `${this.baseUrl}/batches/${batchId}/reject`,
      { comment },
    );
  }

  publishBatch(batchId: number, comment: string): Observable<PlanningActionResponse> {
    return this.http.post<PlanningActionResponse>(
      `${this.baseUrl}/batches/${batchId}/publish`,
      { comment },
    );
  }
}