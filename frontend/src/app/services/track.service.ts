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



export interface TrackForecastBranchOption {
  sucursal_canon: string;
  track_label: string;
  display_order?: number | null;
  sucursal_id?: number | null;
}

export interface TrackForecastBranchesResponse {
  status: string;
  items: TrackForecastBranchOption[];
  message?: string;
  detail?: string;
}

export type TrackVentaTotalForecastScope = 'national' | 'branch';

export type TrackVentaTotalGoalStatus = 'pending' | 'partial' | 'available';

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

export interface TrackVentaTotalForecastSameDayHistoryItem {
  year: number;
  business_month: string | null;
  mtd_total: number;
  month_total: number;
  remaining_total: number;
  progress_pct: number | null;
  mtd_days: number;
  month_days: number;
  gap_current_vs_mtd: number | null;
  gap_current_vs_mtd_pct: number | null;
}

export interface TrackVentaTotalForecastSameDayHistoryAverage {
  mtd_total: number | null;
  month_total: number | null;
  gap_current_vs_average_mtd: number | null;
  gap_current_vs_average_mtd_pct: number | null;
}

export interface TrackVentaTotalForecastSameDayHistoryCurrent {
  year: number;
  mtd_total: number;
  projected_close: number | null;
  historical_progress_pct: number | null;
  trend_factor: number | null;
}

export interface TrackVentaTotalForecastSameDayHistory {
  source: TrackVentaTotalForecastScope;
  branch: string | null;
  target_month: string;
  cutoff_day: number;
  historical_years: number;
  confidence: string;
  average: TrackVentaTotalForecastSameDayHistoryAverage;
  current: TrackVentaTotalForecastSameDayHistoryCurrent;
  items: TrackVentaTotalForecastSameDayHistoryItem[];
}

export interface TrackVentaTotalForecastExecutiveStatus {
  level: 'warning' | 'neutral' | 'danger' | 'success';
  code:
    | 'insufficient_branch_history'
    | 'no_projection'
    | 'below_weighted_goal'
    | 'slightly_below_weighted_goal'
    | 'above_weighted_goal'
    | 'near_weighted_goal'
    | 'projection_without_trend_factor'
    | 'well_below_historical_pace'
    | 'below_historical_pace'
    | 'near_historical_pace'
    | 'above_historical_pace';
  title: string;
  message: string;
  primary_metric_label: string;
  primary_metric_value: number | null;
  primary_metric_unit: 'MXN';
}

export interface TrackVentaTotalForecastExplanationComponents {
  cutoff_day: number;
  real_mtd: number;
  historical_progress_pct: number | null;
  historical_expected_mtd: number | null;
  trend_factor: number | null;
  projected_close: number | null;
}

export interface TrackVentaTotalForecastExplanation {
  formula_key: 'real_mtd_divided_by_historical_progress_pct';
  formula: string;
  plain_text: string;
  components: TrackVentaTotalForecastExplanationComponents;
}

export interface TrackVentaTotalForecastInfoWarning {
  code: 'goal_pending';
  severity: 'info';
  message: string;
}

export interface TrackVentaTotalForecastStandardWarning {
  code:
    | 'preview_operativo'
    | 'goal_partial'
    | 'canonical_cutoff_missing'
    | 'low_comparable_history';
  severity: 'warning';
  message: string;
}

export interface TrackVentaTotalForecastBranchHistoryWarningThresholds {
  min_historical_months: number;
  min_historical_mtd_total: number;
  max_trend_factor: number;
}

export interface TrackVentaTotalForecastBranchHistoryWarning {
  code: 'insufficient_branch_history';
  severity: 'warning';
  message: string;
  reasons: string[];
  thresholds: TrackVentaTotalForecastBranchHistoryWarningThresholds;
}

export type TrackVentaTotalForecastWarning =
  | TrackVentaTotalForecastInfoWarning
  | TrackVentaTotalForecastStandardWarning
  | TrackVentaTotalForecastBranchHistoryWarning;

export interface TrackVentaTotalForecastCanonicalCutoff {
  snapshot_id: number;
  business_date: string | null;
  aggregate_rows: number;
  first_sale_date: string | null;
  last_sale_date: string | null;
  branches: number;
}

export interface TrackVentaTotalForecastCutoff {
  track_date: string;
  target_month: string;
  cutoff_day: number;
  generation_mode: TrackGenerationMode;
  is_official_forecast: boolean;
  basis: 'official_closed_day' | 'preview_operativo';
  canonical_cutoff: TrackVentaTotalForecastCanonicalCutoff | null;
  message: string;
}

export interface TrackVentaTotalForecastBranchDriverQualityIssue {
  code: 'insufficient_branch_history';
  severity: 'warning';
  message: string;
  reasons: string[];
  thresholds: TrackVentaTotalForecastBranchHistoryWarningThresholds;
}

export interface TrackVentaTotalForecastBranchDriverItem {
  sucursal_canon: string;
  track_label: string;
  display_order: number | null;
  real_mtd: number;
  real_base_mtd: number;
  real_agregadora_mtd: number;
  historical_months: number;
  historical_expected_mtd: number | null;
  historical_expected_month_total: number | null;
  historical_progress_pct: number | null;
  gap_vs_historical_expected: number | null;
  gap_vs_historical_expected_pct: number | null;
  trend_factor: number | null;
  projected_close: number | null;
  confidence: 'alta' | 'media' | 'baja' | 'sin_historia';
  projection_quality_issue: TrackVentaTotalForecastBranchDriverQualityIssue | null;
  impact_share_pct: number;
}

export interface TrackVentaTotalForecastBranchDriversHistoryWindow {
  start: string;
  end_exclusive: string;
}

export interface TrackVentaTotalForecastBranchDriversNotApplicable {
  status: 'not_applicable';
  scope: 'branch';
  metric: 'real_mtd_vs_historical_expected_mtd';
  items: [];
}

export interface TrackVentaTotalForecastBranchDriversEmpty {
  status: 'empty';
  scope: 'national';
  metric: 'real_mtd_vs_historical_expected_mtd';
  items: [];
}

export interface TrackVentaTotalForecastBranchDriversResult {
  status: 'ok';
  scope: 'national';
  metric: 'real_mtd_vs_historical_expected_mtd';
  target_month: string;
  cutoff_day: number;
  history_window: TrackVentaTotalForecastBranchDriversHistoryWindow;
  items_count: number;
  negative_gap_total: number;
  items: TrackVentaTotalForecastBranchDriverItem[];
}

export type TrackVentaTotalForecastBranchDrivers =
  | TrackVentaTotalForecastBranchDriversNotApplicable
  | TrackVentaTotalForecastBranchDriversEmpty
  | TrackVentaTotalForecastBranchDriversResult;

export interface TrackVentaTotalForecastCohortHistoryMonth {
  business_month: string;
  month_total: number;
  mtd_total: number;
  remaining_total: number;
}

export interface TrackVentaTotalForecastCohortHistoryWindow {
  start: string;
  end_exclusive: string;
}

export interface TrackVentaTotalForecastCohortQualityThresholds {
  min_historical_months: number;
  min_historical_expected_mtd: number;
  max_trend_factor: number;
}

export interface TrackVentaTotalForecastCohortQualityIssue {
  code: 'insufficient_cohort_history';
  severity: 'warning';
  message: string;
  reasons: string[];
  thresholds: TrackVentaTotalForecastCohortQualityThresholds;
}

export interface TrackVentaTotalForecastCohortTotalQualityIssue {
  code: 'partial_cohort_history';
  severity: 'warning';
  message: string;
  reasons: string[];
}

export interface TrackVentaTotalForecastCohortComponentItem {
  cohort_key: 'legacy_21' | 'new_gyms';
  label: string;
  branches_count: number;
  branches: string[];
  real_mtd: number;
  real_base_mtd: number;
  real_agregadora_mtd: number;
  historical_months: number;
  historical_expected_mtd: number | null;
  historical_expected_remaining: number | null;
  historical_expected_month_total: number | null;
  historical_progress_pct: number | null;
  trend_factor: number | null;
  gap_vs_expected_mtd: number | null;
  gap_vs_expected_mtd_pct: number | null;
  projected_close: number | null;
  projected_close_experimental: number | null;
  confidence: 'alta' | 'media' | 'baja' | 'sin_historia';
  projection_quality_issue: TrackVentaTotalForecastCohortQualityIssue | null;
  history_months: TrackVentaTotalForecastCohortHistoryMonth[];
}

export interface TrackVentaTotalForecastCohortTotalItem {
  cohort_key: 'total_ultra';
  label: string;
  branches_count: number;
  branches: string[];
  real_mtd: number;
  real_base_mtd: number;
  real_agregadora_mtd: number;
  historical_months: null;
  historical_expected_mtd: number;
  historical_expected_remaining: number;
  historical_expected_month_total: number;
  historical_progress_pct: number | null;
  trend_factor: number | null;
  gap_vs_expected_mtd: number | null;
  gap_vs_expected_mtd_pct: number | null;
  projected_close: number | null;
  projected_close_experimental: number;
  confidence: 'mixta';
  projection_quality_issue: TrackVentaTotalForecastCohortTotalQualityIssue | null;
  history_months: [];
}

export type TrackVentaTotalForecastCohortItem =
  | TrackVentaTotalForecastCohortComponentItem
  | TrackVentaTotalForecastCohortTotalItem;

export interface TrackVentaTotalForecastCohortForecastNotApplicable {
  status: 'not_applicable';
  method: 'legacy_21_plus_new_gyms';
  scope: 'branch';
  items: [];
}

export interface TrackVentaTotalForecastCohortForecastEmpty {
  status: 'empty';
  method: 'legacy_21_plus_new_gyms';
  scope: 'national';
  items: [];
}

export interface TrackVentaTotalForecastCohortForecastResult {
  status: 'ok';
  method: 'legacy_21_plus_new_gyms';
  scope: 'national';
  target_month: string;
  cutoff_day: number;
  history_window: TrackVentaTotalForecastCohortHistoryWindow;
  items: TrackVentaTotalForecastCohortItem[];
}

export type TrackVentaTotalForecastCohortForecast =
  | TrackVentaTotalForecastCohortForecastNotApplicable
  | TrackVentaTotalForecastCohortForecastEmpty
  | TrackVentaTotalForecastCohortForecastResult;

export interface TrackVentaTotalForecastAnchoredSeasonalSample {
  year: number;
  business_month: string;
  previous_month: string;
  previous_total: number;
  month_total: number;
  factor: number;
}

export interface TrackVentaTotalForecastAnchoredCumulativeSample {
  year: number;
  business_month: string;
  mtd_total: number;
  month_total: number;
  cumulative_pct: number;
}

export interface TrackVentaTotalForecastAnchoredQualityIssue {
  code: 'insufficient_anchor_history';
  severity: 'warning';
  message: string;
  reasons: string[];
}

export interface TrackVentaTotalForecastAnchoredTotalQualityIssue {
  code: 'partial_anchor_history';
  severity: 'warning';
  message: string;
}

export interface TrackVentaTotalForecastAnchoredLegacyItem {
  cohort_key: 'legacy_21';
  label: string;
  branches_count: number;
  branches: string[];
  current_base_mtd: number;
  current_agregadora_mtd: number;
  current_total_mtd: number;
  previous_base_total: number | null;
  previous_agregadora_total: number | null;
  previous_closed_total: number | null;
  seasonal_factor: number | null;
  seasonal_factor_applied: number | null;
  seasonal_factor_source: 'same_month_historical_factor';
  seasonal_years: number;
  expected_cumulative_pct: number | null;
  expected_cumulative_method: 'same_month_history';
  cumulative_years: number;
  expected_close_before_cutoff: number | null;
  expected_mtd_at_cutoff: number | null;
  expected_remaining: number | null;
  gap_vs_expected_mtd: number | null;
  gap_vs_expected_mtd_pct: number | null;
  projected_close: number | null;
  confidence: 'alta' | 'media';
  projection_quality_issue: TrackVentaTotalForecastAnchoredQualityIssue | null;
  seasonal_samples: TrackVentaTotalForecastAnchoredSeasonalSample[];
  cumulative_samples: TrackVentaTotalForecastAnchoredCumulativeSample[];
}

export interface TrackVentaTotalForecastAnchoredNewGymsItem {
  cohort_key: 'new_gyms';
  label: string;
  branches_count: number;
  branches: string[];
  current_base_mtd: number;
  current_agregadora_mtd: number;
  current_total_mtd: number;
  previous_base_total: number | null;
  previous_agregadora_total: number | null;
  previous_closed_total: number | null;
  seasonal_factor: number | null;
  seasonal_factor_applied: 1;
  seasonal_factor_source: 'previous_close_no_seasonal_factor';
  seasonal_years: number;
  expected_cumulative_pct: number | null;
  expected_cumulative_method: 'recent_available_history';
  cumulative_years: number;
  expected_close_before_cutoff: number | null;
  expected_mtd_at_cutoff: number | null;
  expected_remaining: number | null;
  gap_vs_expected_mtd: number | null;
  gap_vs_expected_mtd_pct: number | null;
  projected_close: number | null;
  confidence: 'media' | 'baja';
  projection_quality_issue: TrackVentaTotalForecastAnchoredQualityIssue | null;
  seasonal_samples: TrackVentaTotalForecastAnchoredSeasonalSample[];
  cumulative_samples: TrackVentaTotalForecastAnchoredCumulativeSample[];
}

export interface TrackVentaTotalForecastAnchoredTotalItem {
  cohort_key: 'total_ultra';
  label: string;
  branches_count: number;
  branches: string[];
  current_base_mtd: number;
  current_agregadora_mtd: number;
  current_total_mtd: number;
  previous_base_total: number;
  previous_agregadora_total: number;
  previous_closed_total: number;
  seasonal_factor: null;
  seasonal_factor_applied: null;
  seasonal_factor_source: 'sum_of_cohorts';
  seasonal_years: null;
  expected_cumulative_pct: null;
  expected_cumulative_method: 'sum_of_cohorts';
  cumulative_years: null;
  expected_close_before_cutoff: number;
  expected_mtd_at_cutoff: number;
  expected_remaining: number;
  gap_vs_expected_mtd: number;
  gap_vs_expected_mtd_pct: number | null;
  projected_close: number | null;
  confidence: 'mixta';
  projection_quality_issue: TrackVentaTotalForecastAnchoredTotalQualityIssue | null;
  seasonal_samples: [];
  cumulative_samples: [];
}

export type TrackVentaTotalForecastAnchoredItem =
  | TrackVentaTotalForecastAnchoredLegacyItem
  | TrackVentaTotalForecastAnchoredNewGymsItem
  | TrackVentaTotalForecastAnchoredTotalItem;

export interface TrackVentaTotalForecastAnchoredRemainingForecastNotApplicable {
  status: 'not_applicable';
  method: 'previous_close_plus_expected_remaining';
  scope: 'branch';
  items: [];
}

export interface TrackVentaTotalForecastAnchoredRemainingForecastEmpty {
  status: 'empty';
  method: 'previous_close_plus_expected_remaining';
  scope: 'national';
  items: [];
}

export interface TrackVentaTotalForecastAnchoredRemainingForecastResult {
  status: 'ok';
  method: 'previous_close_plus_expected_remaining';
  scope: 'national';
  target_month: string;
  cutoff_day: number;
  previous_month: string;
  previous_month_end: string;
  items: TrackVentaTotalForecastAnchoredItem[];
}

export type TrackVentaTotalForecastAnchoredRemainingForecast =
  | TrackVentaTotalForecastAnchoredRemainingForecastNotApplicable
  | TrackVentaTotalForecastAnchoredRemainingForecastEmpty
  | TrackVentaTotalForecastAnchoredRemainingForecastResult;

export interface TrackVentaTotalForecastSummary {
  real_mtd: number;
  real_base_mtd: number;
  real_agregadora_mtd: number;
  goal_month: number | null;
  historical_expected_mtd: number | null;
  historical_expected_remaining: number | null;
  historical_expected_month_total: number | null;
  historical_expected_mtd_aggregate: number;
  historical_expected_remaining_aggregate: number;
  historical_expected_month_total_aggregate: number;
  historical_progress_pct: number | null;
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
  same_day_history?: TrackVentaTotalForecastSameDayHistory;
  executive_status?: TrackVentaTotalForecastExecutiveStatus;
  forecast_explanation?: TrackVentaTotalForecastExplanation;
  warnings?: TrackVentaTotalForecastWarning[];
  forecast_cutoff?: TrackVentaTotalForecastCutoff;
  branch_drivers?: TrackVentaTotalForecastBranchDrivers;
  cohort_forecast?: TrackVentaTotalForecastCohortForecast;
  anchored_remaining_forecast?: TrackVentaTotalForecastAnchoredRemainingForecast;
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


  getForecastBranches(): Observable<TrackForecastBranchesResponse> {
    return this.http.get<TrackForecastBranchesResponse>(
      `${this.baseUrl}/forecast/branches`,
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
