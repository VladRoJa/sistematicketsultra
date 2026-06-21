import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment'; 

export type KpiDesempenoSectionStatus = 'ok' | 'empty';

export type KpiDesempenoHistoryGranularity =
  | 'monthly'
  | 'bimonthly'
  | 'quarterly';

export interface KpiDesempenoMonthlyReportParams {
  targetMonth: string;
  startMonth?: string;
  historyGranularity?: KpiDesempenoHistoryGranularity;
}

export interface KpiDesempenoMetadata {
  source: string;
  report_type_key: string;
  snapshot_kind: string;
  canonical_only: boolean;
  target_month: string;
  start_month: string;
  history_granularity: KpiDesempenoHistoryGranularity;
  timezone: string;
  permissions_mode: string;
}

export interface KpiDesempenoWarning {
  code: string;
  message: string;
  [key: string]: unknown;
}

export interface KpiDesempenoResolvedSnapshot {
  snapshot_id: number;
  business_date: string;
  captured_at?: string | null;
  row_count_valid?: number | null;
  row_count_rejected?: number | null;
}

export interface KpiDesempenoSource {
  snapshot_id: number;
  business_date: string;
  report_type_key: string;
  snapshot_kind: string;
  is_canonical: boolean;
}

export interface KpiDesempenoBranchCapacity {
  m2_sin_circulaciones: number;
  target_1_5: number;
  target_2_0: number;
  source?: {
    track_daily_mart_id?: number | null;
    track_date?: string | null;
    target_month?: string | null;
  } | null;
}

export interface KpiDesempenoBranch {
  sucursal_raw: string;
  sucursal_canon: string | null;
  track_label: string;
  display_order: number | null;
  is_track_active: boolean | null;
  capacity?: KpiDesempenoBranchCapacity | null;
}

export interface KpiDesempenoMonthlyMetrics {
  socios_activos_inicio_mes: number;
  socios_activos_cierre_mes: number;
  clientes_nuevos: number;
  reactivaciones: number;
  bajas: number;
  crecimiento_real: number;
  movimiento_reportado: number;
  ajuste_no_explicado: number;
}

export interface KpiDesempenoMonthlyRow {
  branch: KpiDesempenoBranch;
  metrics: KpiDesempenoMonthlyMetrics;
  source: KpiDesempenoSource;
}

export interface KpiDesempenoWeeklyPeriod {
  period_key: string;
  label: string;
  date_from: string;
  date_to: string;
  resolved_snapshot: KpiDesempenoResolvedSnapshot | null;
}

export interface KpiDesempenoWeeklyMetrics {
  socios_activos_inicio_mes: number;
  socios_activos_cierre_semana: number;
  clientes_nuevos_mtd: number;
  reactivaciones_mtd: number;
  bajas_mtd: number;
  crecimiento_real_mtd: number;
  movimiento_reportado_mtd: number;
  ajuste_no_explicado_mtd: number;
}

export interface KpiDesempenoWeeklyRow {
  period: {
    period_key: string;
    label: string;
    date_from: string;
    date_to: string;
  };
  branch: KpiDesempenoBranch;
  metrics: KpiDesempenoWeeklyMetrics;
  source: KpiDesempenoSource;
}

export interface KpiDesempenoHistoricalMetrics {
  socios_activos_inicio_periodo: number;
  socios_activos_cierre_periodo: number;
  clientes_nuevos_mtd_snapshot: number;
  reactivaciones_mtd_snapshot: number;
  bajas_mtd_snapshot: number;
  crecimiento_real_snapshot: number;
  movimiento_reportado_snapshot: number;
  ajuste_no_explicado_snapshot: number;
}

export interface KpiDesempenoHistoricalRow {
  period_key: string;
  label: string;
  date_from: string;
  date_to: string;
  resolved_snapshot: KpiDesempenoResolvedSnapshot | null;
  metrics: KpiDesempenoHistoricalMetrics | null;
  source: KpiDesempenoSource | null;
}

export interface KpiDesempenoBaseSection {
  key: string;
  title: string;
  chart_type: string;
  status: KpiDesempenoSectionStatus;
  target_month?: string;
  warnings: KpiDesempenoWarning[];
}

export interface KpiDesempenoWeeklySection extends KpiDesempenoBaseSection {
  key: 'weekly_closing';
  periods: KpiDesempenoWeeklyPeriod[];
  totals_by_period: Record<string, KpiDesempenoWeeklyMetrics>;
  data: KpiDesempenoWeeklyRow[];
}

export interface KpiDesempenoWeeklyBranchSeriesSection extends KpiDesempenoBaseSection {
  key: 'weekly_branch_series';
  start_month: string;
  end_month: string;
  periods: KpiDesempenoWeeklyPeriod[];
  data: KpiDesempenoWeeklyRow[];
}
export interface KpiDesempenoMonthlySection extends KpiDesempenoBaseSection {
  key: 'monthly_closing';
  resolved_snapshot: KpiDesempenoResolvedSnapshot | null;
  totals: KpiDesempenoMonthlyMetrics | Record<string, never>;
  data: KpiDesempenoMonthlyRow[];
}

export interface KpiDesempenoHistoricalSection extends KpiDesempenoBaseSection {
  key: 'historical_closing';
  start_month: string;
  end_month: string;
  granularity: KpiDesempenoHistoryGranularity;
  periods_count: number;
  resolved_periods_count: number;
  data: KpiDesempenoHistoricalRow[];
}

export type KpiDesempenoSection =
  | KpiDesempenoWeeklyBranchSeriesSection
  | KpiDesempenoWeeklySection
  | KpiDesempenoMonthlySection
  | KpiDesempenoHistoricalSection;

export interface KpiDesempenoMonthlyReportResponse {
  status: string;
  module: string;
  phase: string;
  metadata: KpiDesempenoMetadata;
  sections: KpiDesempenoSection[];
}

@Injectable({
  providedIn: 'root',
})
export class TrackKpiDesempenoService {
  private readonly apiUrl = `${environment.apiUrl}/track/kpi-desempeno`;

  constructor(private readonly http: HttpClient) {}

  getMonthlyReport(
    params: KpiDesempenoMonthlyReportParams,
  ): Observable<KpiDesempenoMonthlyReportResponse> {
    let httpParams = new HttpParams().set('target_month', params.targetMonth);

    if (params.startMonth) {
      httpParams = httpParams.set('start_month', params.startMonth);
    }

    if (params.historyGranularity) {
      httpParams = httpParams.set(
        'history_granularity',
        params.historyGranularity,
      );
    }

    return this.http.get<KpiDesempenoMonthlyReportResponse>(
      `${this.apiUrl}/monthly-report`,
      {
        params: httpParams,
      },
    );
  }
}



