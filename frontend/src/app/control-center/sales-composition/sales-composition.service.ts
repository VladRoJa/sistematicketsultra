import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

export interface SalesCompositionSnapshot {
  snapshot_id: number;
  warehouse_upload_id: number;
  business_date: string;
  date_from: string;
  date_to: string;
  captured_at: string;
  is_canonical: boolean;
  current_label: string;
  comparison_label: string;
  row_count_valid: number;
  data_quality: Record<string, unknown>;
}

export interface SalesCompositionGroup {
  key: string;
  sales_mode: 'CONTRACT' | 'NO_CONTRACT';
  label: string;
  current_flow: number;
  comparison_flow: number;
  delta_flow: number;
  growth_pct: number | null;
  current_quantity: number;
  comparison_quantity: number;
  delta_quantity: number;
  quantity_growth_pct: number | null;
  current_mix_pct: number;
  comparison_mix_pct: number;
  mix_delta_pp: number;
  movement_share_pct: number;
  tariff_count: number;
}

export interface SalesCompositionTariff {
  row_index: number;
  sales_mode: 'CONTRACT' | 'NO_CONTRACT';
  group_label: string;
  family: string | null;
  contract_type: string | null;
  plan_type: string | null;
  tariff_name: string;
  source_cost: number | null;
  monthly_equivalent: number | null;
  free_months_raw: string | null;
  current_quantity: number;
  comparison_quantity: number;
  delta_quantity: number;
  current_flow: number;
  comparison_flow: number;
  delta_flow: number;
  growth_pct: number | null;
  current_mix_pct: number;
  comparison_mix_pct: number;
  mix_delta_pp: number;
}

export interface SalesCompositionBranch {
  branch: string;
  current_flow: number;
  comparison_flow: number;
  delta_flow: number;
  growth_pct: number | null;
  current_quantity: number;
  comparison_quantity: number;
  delta_quantity: number;
  current_mix_pct: number;
  comparison_mix_pct: number;
  movement_share_pct: number;
}

export interface SalesCompositionSignal {
  key: string;
  type: string;
  tone: 'positive' | 'attention' | 'critical' | 'neutral';
  metric?: string;
  label?: string;
  delta_flow?: number;
  growth_pct?: number | null;
  delta_pp?: number;
  movement_share_pct?: number;
}

export interface SalesCompositionSummary {
  current_flow: number;
  comparison_flow: number;
  delta_flow: number;
  growth_pct: number | null;
  current_quantity: number;
  comparison_quantity: number;
  delta_quantity: number;
  quantity_growth_pct: number | null;
  contract_mix_pct: number;
  comparison_contract_mix_pct: number;
  contract_mix_delta_pp: number;
  top3_concentration_pct: number;
  largest_mix_shift: SalesCompositionGroup | null;
}

export interface SalesCompositionResponse {
  status: string;
  contract_version: string;
  source: SalesCompositionSnapshot;
  summary: SalesCompositionSummary;
  groups: SalesCompositionGroup[];
  drivers: {
    positive: SalesCompositionGroup[];
    negative: SalesCompositionGroup[];
  };
  branches: SalesCompositionBranch[];
  tariffs: SalesCompositionTariff[];
  signals: SalesCompositionSignal[];
  data_quality: Record<string, unknown>;
}

export interface SalesCompositionSnapshotsResponse {
  status: string;
  contract_version: string;
  snapshots: SalesCompositionSnapshot[];
}

export interface SalesCompositionUploadResponse {
  status: string;
  message: string;
  analysis: SalesCompositionResponse;
}

@Injectable({ providedIn: 'root' })
export class SalesCompositionService {
  private readonly apiUrl = `${environment.apiUrl}/control/sales-composition`;

  constructor(private readonly http: HttpClient) {}

  getAnalysis(
    snapshotId?: number | null,
  ): Observable<SalesCompositionResponse> {
    let params = new HttpParams();
    if (snapshotId) {
      params = params.set('snapshot_id', String(snapshotId));
    }
    return this.http.get<SalesCompositionResponse>(
      this.apiUrl,
      { params },
    );
  }

  getSnapshots(): Observable<SalesCompositionSnapshotsResponse> {
    return this.http.get<SalesCompositionSnapshotsResponse>(
      `${this.apiUrl}/snapshots`,
    );
  }

  upload(
    file: File,
    dateFrom: string,
    dateTo: string,
  ): Observable<SalesCompositionUploadResponse> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    formData.append('date_from', dateFrom);
    formData.append('date_to', dateTo);
    return this.http.post<SalesCompositionUploadResponse>(
      `${this.apiUrl}/upload`,
      formData,
    );
  }
}
