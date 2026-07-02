// frontend\src\app\services\track.service.ts


import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export type TrackGenerationMode = 'manual_preview' | 'official_closed_day';

export interface TrackPipelineRequest {
  track_date: string;
  generation_mode: TrackGenerationMode;
}

export interface TrackPipelineResult {
  status: string;
  track_date: string;
  generation_mode: TrackGenerationMode;
  refresh_dates: Record<string, string>;
  raw_ingestion: unknown;
  source_refresh_results: unknown;
  mart_refresh_result: {
    status: string;
    track_date: string;
    generation_mode: TrackGenerationMode;
    rows_inserted: number;
  };
}

export interface TrackPipelineResponse {
  status: 'ok' | 'error';
  result?: TrackPipelineResult;
  message?: string;
  detail?: string;
}

export interface TrackResolvedVersion {
  id: number;
  version_type: string;
  status: string;
  generated_at_utc: string | null;
  started_at_utc: string | null;
  finished_at_utc: string | null;
}


export type TrackVentaTotalForecastScope = 'national' | 'branch';

export type TrackVentaTotalGoalStatus = 'pending' | 'partial' | 'ready';

export interface TrackVentaTotalForecastResolvedVersion {
  id: number;
  version_type: string;
  status: string;
  generated_at_utc: string | null;
  started_at_utc: string | null;
  finished_at_utc: string | null;
}

export interface TrackVentaTotalForecastHistoryCoverage {
  months_count: number;
  first_month: string | null;
  last_month: string | null;
  confidence: string;
}

export interface TrackVentaTotalForecastDataQuality {
  goal_status: TrackVentaTotalGoalStatus;
  goal_status_message: string | null;
  history_coverage: TrackVentaTotalForecastHistoryCoverage;
}

export interface TrackVentaTotalForecastHistoricalCurve {
  source: TrackVentaTotalForecastScope;
  historical_months: number;
  historical_month_total: number | null;
  historical_mtd_total: number | null;
  historical_remaining_total: number | null;
  historical_progress_pct: number | null;
  distinct_days: number;
  confidence: string;
}

export interface TrackVentaTotalForecastSummary {
  real_mtd: number;
  real_base_mtd: number;
  real_agregadora_mtd: number;
  goal_month: number | null;
  historical_progress_pct: number | null;
  historical_expected_mtd: number | null;
  historical_expected_remaining: number | null;
  trend_factor_raw: number | null;
  projected_close: number | null;
  weighted_goal_mtd: number | null;
  gap_vs_weighted_goal: number | null;
  gap_vs_weighted_goal_pct: number | null;
  status_vs_goal: string | null;
  confidence: string;
}

export interface TrackVentaTotalForecastMetadata {
  track_date: string;
  target_month: string;
  generation_mode: TrackGenerationMode;
  track_daily_version_id: number;
  scope: TrackVentaTotalForecastScope;
  branch: string | null;
  selected_branches_count: number;
  excluded_branches: string[];
  history_window?: {
    start: string;
    end_exclusive: string;
  };
  resolved_version?: TrackVentaTotalForecastResolvedVersion;
}

export interface TrackVentaTotalForecastResponse {
  status: 'ok' | 'error';
  metadata?: TrackVentaTotalForecastMetadata;
  data_quality?: TrackVentaTotalForecastDataQuality;
  summary?: TrackVentaTotalForecastSummary;
  historical_curve?: TrackVentaTotalForecastHistoricalCurve;
  message?: string;
  detail?: string;
}

export interface TrackDailyMartRow {
  track_daily_version_id?: number | null;
  track_date: string;
  generation_mode: TrackGenerationMode;
  sucursal_canon: string;
  target_month: string | null;
  m2_sin_circulaciones: number | null;
  usuarios_inicio_mes: number | null;
  proyeccion_usuarios_cierre_mes: number | null;
  meta_faycgo_mes: number | null;
  meta_clientes_nuevos_mes: number | null;
  meta_reactivaciones_mes: number | null;
  meta_bajas_mes: number | null;
  meta_nuevos_domiciliados_mes: number | null;
  meta_arpu_mes: number | null;
  meta_venta_tienda_mes: number | null;
  venta_tienda_real_mtd: number | null;
  source_business_date_tienda: string | null;
  source_snapshot_id_tienda: number | null;
  usuarios_activos_actual: number | null;
  reactivaciones_real_mtd: number | null;
  bajas_reales_mtd: number | null;
  ingreso_real_base_mtd: number | null;
  ingreso_real_agregadora_mtd: number | null;
  ingreso_real_mtd: number | null;
  clientes_nuevos_real_mtd: number | null;
  nuevos_domiciliados_real_mtd: number | null;
  source_business_date_desempeno: string | null;
  source_business_date_ingresos: string | null;
  source_business_date_agregadoras?: string | null;
  source_business_date_nuevos: string | null;
  source_business_date_domiciliados: string | null;
  source_snapshot_id_desempeno: number | null;
  source_snapshot_id_ingresos: number | null;
  source_snapshot_id_nuevos: number | null;
  source_snapshot_id_domiciliados: number | null;
}

export interface TrackDailyMartResponse {
  status: 'ok' | 'error';
  track_date?: string;
  generation_mode?: TrackGenerationMode;
  resolved_version?: TrackResolvedVersion | null;
  total_rows?: number;
  rows?: TrackDailyMartRow[];
  message?: string;
  detail?: string;
}

export interface TrackAgregadorasIntegrationRequest {
  track_date: string;
  requested_by?: string;
  trigger_source?: string;
}

export interface TrackAgregadorasIntegrationResult {
  status: string;
  track_date: string;
  generation_mode: string;
  requested_by: string;
  trigger_source: string;
  source_refresh_results: {
    ingresos: {
      status: string;
      business_date: string;
      rows_inserted: number;
    };
  };
  mart_refresh_result: {
    status: string;
    track_date: string;
    generation_mode: string;
    rows_inserted: number;
  };
}

export interface TrackAgregadorasIntegrationResponse {
  status: string;
  result: TrackAgregadorasIntegrationResult | null;
  message?: string;
  detail?: string;
}

export interface TrackRegionalRankingItem {
  region_key: string;
  region_label: string;
  ranking_position: number;
  total_regions: number;
  ingreso_real_total_mtd: string;
  meta_faycgo_mes: string;
  clientes_nuevos_real_mtd: number;
  total_branches: number;
  cumplimiento_ingreso_pct: string | null;
}

export interface TrackRegionalBranchDetailItem {
  sucursal_id: number | null;
  sucursal_canon: string;
  sucursal_name: string;
  orden_apertura: number | null;
  ingreso_real_total_mtd: string;
  meta_faycgo_mes: string;
  clientes_nuevos_real_mtd: number;
  cumplimiento_ingreso_pct: string | null;
}

export interface TrackRegionalDetailRankings {
  income_compliance_position: number | null;
  income_position: number | null;
  new_clients_position: number | null;
  total_regions: number;
}

export interface TrackRegionalDetailSummary {
  region_key: string;
  region_label: string;
  ingreso_real_total_mtd: string;
  meta_faycgo_mes: string;
  clientes_nuevos_real_mtd: number;
  total_branches: number;
  total_regions: number;
  cumplimiento_ingreso_pct: string | null;
}

export interface TrackRegionalDetailRegion {
  region_key: string;
  region_label: string;
  summary: TrackRegionalDetailSummary;
  rankings: TrackRegionalDetailRankings;
  branches: TrackRegionalBranchDetailItem[];
}

export interface TrackRegionalBusinessRule {
  key: string;
  label: string;
  description: string;
}

export interface TrackRegionalDetailResponse {
  track_date: string;
  generation_mode: TrackGenerationMode;
  rankings: {
    income_compliance: TrackRegionalRankingItem[];
    income: TrackRegionalRankingItem[];
    new_clients: TrackRegionalRankingItem[];
  };
  regions: TrackRegionalDetailRegion[];
  business_rules: TrackRegionalBusinessRule[];
}

@Injectable({
  providedIn: 'root',
})
export class TrackService {
  private readonly baseUrl = `${environment.apiUrl}/track`;
  private readonly trackAlertsBaseUrl = `${environment.apiUrl}/track-alerts`;

  constructor(private readonly http: HttpClient) {}

  runDailyPipeline(
    trackDate: string,
    generationMode: TrackGenerationMode,
  ): Observable<TrackPipelineResponse> {
    const payload: TrackPipelineRequest = {
      track_date: trackDate,
      generation_mode: generationMode,
    };

    return this.http.post<TrackPipelineResponse>(
      `${this.baseUrl}/run-daily-pipeline`,
      payload,
    );
  }

  runAgregadorasIntegration(
    payload: TrackAgregadorasIntegrationRequest,
  ) {
    return this.http.post<TrackAgregadorasIntegrationResponse>(
      `${this.baseUrl}/run-agregadoras-integration`,
      payload,
    );
  }

  getDailyMart(
    trackDate: string,
    generationMode: TrackGenerationMode,
  ): Observable<TrackDailyMartResponse> {
    const params = new HttpParams()
      .set('track_date', trackDate)
      .set('generation_mode', generationMode);

    return this.http.get<TrackDailyMartResponse>(
      `${this.baseUrl}/daily-mart`,
      { params },
    );
  }

  downloadDailyMartExcel(
    trackDate: string,
    generationMode: TrackGenerationMode,
  ) {
    const params = new HttpParams()
      .set('track_date', trackDate)
      .set('generation_mode', generationMode);

    return this.http.get(`${this.baseUrl}/daily-mart/export-xlsx`, {
      params,
      responseType: 'blob',
    });
  }

  getRegionalDetail(
    trackDate: string,
    generationMode: TrackGenerationMode = 'manual_preview',
  ): Observable<TrackRegionalDetailResponse> {
    const params = new HttpParams()
      .set('track_date', trackDate)
      .set('generation_mode', generationMode);

    return this.http.get<TrackRegionalDetailResponse>(
      `${this.trackAlertsBaseUrl}/regional-detail`,
      { params },
    );
  }

  getVentaTotalForecast(
    trackDate: string,
    generationMode: TrackGenerationMode,
    scope: TrackVentaTotalForecastScope = 'national',
    branch?: string | null,
  ): Observable<TrackVentaTotalForecastResponse> {
    let params = new HttpParams()
      .set('track_date', trackDate)
      .set('generation_mode', generationMode)
      .set('scope', scope);

    const branchValue = (branch || '').trim();

    if (scope === 'branch' && branchValue) {
      params = params.set('branch', branchValue.toUpperCase());
    }

    return this.http.get<TrackVentaTotalForecastResponse>(
      `${this.baseUrl}/forecast/venta-total`,
      { params },
    );
  }

  getBranchHistory(
    sucursalCanon: string,
    targetMonth: string,
    generationMode: TrackGenerationMode,
  ): Observable<TrackBranchHistoryResponse> {
    const params = new HttpParams()
      .set('sucursal_canon', sucursalCanon)
      .set('target_month', targetMonth)
      .set('generation_mode', generationMode);

    return this.http.get<TrackBranchHistoryResponse>(
      `${this.baseUrl}/branch-history`,
      { params },
    );
  }
}




export interface TrackBranchHistoryResponse {
  status: 'ok' | 'error';
  sucursal_canon?: string;
  generation_mode?: TrackGenerationMode;
  days_requested?: number;
  total_rows?: number;
  rows?: TrackDailyMartRow[];
  message?: string;
  detail?: string;
}
