import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { MatTooltipModule } from '@angular/material/tooltip';
import { FormsModule } from '@angular/forms';

import { AuthService } from '../../services/auth.service';
import {
  TrackForecastBranchOption,
  TrackGenerationMode,
  TrackService,
  TrackVentaTotalForecastBranchDriverItem,
  TrackVentaTotalForecastBranchDrivers,
  TrackVentaTotalForecastCohortForecast,
  TrackVentaTotalForecastCohortItem,
  TrackVentaTotalForecastCutoff,
  TrackVentaTotalForecastExecutiveStatus,
  TrackVentaTotalForecastExplanation,
  TrackVentaTotalForecastResponse,
  TrackVentaTotalForecastSameDayHistory,
  TrackVentaTotalForecastSameDayHistoryItem,
  TrackVentaTotalForecastScope,
  TrackVentaTotalForecastSummary,
  TrackVentaTotalForecastWarning,
} from '../../services/track.service';

type TrackForecastComparableBar = {
  year: number;
  mtdValue: number;
  monthTotalValue: number | null;
  isCurrent: boolean;
  mtdBarPct: number;
  monthBarPct: number;
  monthLabel: string;
  monthValueLabel: string;
};

type TrackForecastCohortViewModel = {
  cohort_key: TrackVentaTotalForecastCohortItem['cohort_key'];
  label: string;
  branches_count: number;
  real_mtd: number;
  historical_expected_mtd: number | null;
  gap_vs_expected_mtd: number | null;
  gap_vs_expected_mtd_pct: number | null;
  trend_factor: number | null;
  projected_close: number | null;
  projected_close_experimental: number | null;
  confidence: string;
  projection_quality_issue: TrackVentaTotalForecastCohortItem['projection_quality_issue'];
  visualTone: string;
  gapLabel: string;
  trendLabel: string;
  projectionLabel: string;
  experimentalLabel: string;
};

type CohortDetailMetricKey =
  | 'real_mtd'
  | 'real_base_mtd'
  | 'real_agregadora_mtd'
  | 'historical_expected_mtd'
  | 'gap'
  | 'trend_factor'
  | 'projected_close'
  | 'confidence';

const COHORT_DETAIL_METRIC_TOOLTIPS: Readonly<Record<CohortDetailMetricKey, string>> = {
  real_mtd: 'Ingreso acumulado de la sucursal hasta la fecha Track. Está compuesto por el ingreso base más el ingreso de agregadoras.',
  real_base_mtd: 'Ingreso real acumulado proveniente de la operación base de la sucursal.',
  real_agregadora_mtd: 'Ingreso real acumulado proveniente de fuentes agregadoras integradas en Track, como Wellhub o TotalPass, según la información disponible.',
  historical_expected_mtd: 'Referencia histórica de cuánto llevaba normalmente esta sucursal al mismo día del mes. Depende de los meses comparables disponibles y no representa por sí sola una proyección de cierre.',
  gap: 'Diferencia entre el ingreso real acumulado y el esperado histórico al corte. Fórmula conceptual: Real MTD menos Esperado histórico. Un valor negativo indica que la sucursal va por debajo de su ritmo histórico.',
  trend_factor: 'Ritmo actual frente al esperado histórico al corte. Un 100% indica que la sucursal avanza exactamente al ritmo histórico esperado; menos de 100% está por debajo y más de 100% está por encima.',
  projected_close: 'Estimación de cierre calculada con el avance histórico del mes. Solo se muestra cuando la sucursal supera los controles de calidad y estabilidad del forecast.',
  confidence: 'Calidad del histórico utilizado para interpretar la tendencia. Considera cobertura histórica, volumen comparable y estabilidad del factor de tendencia.',
};

type TrackForecastBranchDriverViewModel = {
  rank: number;
  track_label: string;
  sucursal_canon: string;
  real_mtd: number;
  historical_expected_mtd: number | null;
  gap_vs_historical_expected: number | null;
  gap_vs_historical_expected_pct: number | null;
  trend_factor: number | null;
  projected_close: number | null;
  impact_share_pct: number;
  confidence: string;
  projection_quality_issue: TrackVentaTotalForecastBranchDriverItem['projection_quality_issue'];
  impactBarPct: number;
  visualTone: string;
};

type TrackForecastAlertViewModel = {
  code: string;
  severity: string;
  title: string;
  message: string;
  reasons: string[];
  sourceLabel: string;
  tone: string;
};

type TrackForecastTraceItem = {
  label: string;
  value: string;
};

@Component({
  selector: 'app-track-forecast',
  standalone: true,
  imports: [CommonModule, FormsModule, MatTooltipModule],
  templateUrl: './track-forecast.component.html',
  styleUrls: ['./track-forecast.component.css'],
})
export class TrackForecastComponent implements OnInit {
  trackDate = this.getTodayIsoDate();
  generationMode: TrackGenerationMode = 'manual_preview';
  scope: TrackVentaTotalForecastScope = 'national';
  branch = '';

  loading = false;
  loadingBranches = false;
  errorMessage = '';
  branchCatalogMessage = '';
  forecast: TrackVentaTotalForecastResponse | null = null;
  branchOptions: TrackForecastBranchOption[] = [];
  selectedCohortKey: TrackVentaTotalForecastCohortItem['cohort_key'] | null = null;

  private readonly betaUserId = 47;

  constructor(
    private readonly trackService: TrackService,
    private readonly authService: AuthService,
  ) {}

  ngOnInit(): void {
    if (!this.puedeVerForecastBeta()) {
      this.errorMessage = 'No tienes acceso beta a Proyección y Metas.';
      return;
    }

    this.cargarSucursalesForecast();
    this.cargarForecast();
  }

  puedeVerForecastBeta(): boolean {
    const user = this.authService.getUser() as any;
    const userId = Number(user?.id ?? user?.user_id ?? user?.usuario_id ?? 0);

    return userId === this.betaUserId;
  }

  cargarSucursalesForecast(): void {
    this.loadingBranches = true;
    this.branchCatalogMessage = '';

    this.trackService.getForecastBranches().subscribe({
      next: (response) => {
        this.loadingBranches = false;

        if (response.status !== 'ok') {
          this.branchCatalogMessage = response.message || response.detail || 'No fue posible cargar sucursales Track.';
          return;
        }

        this.branchOptions = response.items || [];

        if (this.scope === 'branch' && !this.branch && this.branchOptions.length) {
          this.branch = this.branchOptions[0].sucursal_canon;
        }
      },
      error: (error) => {
        this.loadingBranches = false;
        this.branchCatalogMessage =
          error?.error?.message ||
          error?.error?.detail ||
          'No fue posible cargar sucursales Track.';
      },
    });
  }

  onScopeChange(): void {
    if (this.scope === 'national') {
      this.branch = '';
      return;
    }

    if (!this.branch && this.branchOptions.length) {
      this.branch = this.branchOptions[0].sucursal_canon;
    }
  }

  cargarForecast(): void {
    if (!this.puedeVerForecastBeta()) {
      this.errorMessage = 'No tienes acceso beta a Proyección y Metas.';
      return;
    }

    if (this.scope === 'branch' && !this.branch.trim()) {
      this.errorMessage = 'Selecciona una sucursal Track para consultar el forecast.';
      return;
    }

    this.loading = true;
    this.errorMessage = '';
    this.forecast = null;
    this.selectedCohortKey = null;

    this.trackService
      .getVentaTotalForecast(
        this.trackDate,
        this.generationMode,
        this.scope,
        this.branch,
      )
      .subscribe({
        next: (response) => {
          this.loading = false;

          if (response.status !== 'ok') {
            this.errorMessage = response.message || response.detail || 'No fue posible cargar la proyección.';
            return;
          }

          this.forecast = response;
        },
        error: (error) => {
          this.loading = false;
          this.errorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'No fue posible cargar la proyección.';
        },
      });
  }

  get summary(): TrackVentaTotalForecastSummary | null {
    return this.forecast?.summary ?? null;
  }

  get trackContextDateLabel(): string {
    const trackDate = this.forecast?.metadata?.track_date;
    return trackDate ? this.formatShortDate(trackDate) : 'Sin corte';
  }

  get trackContextBranchesLabel(): string {
    const count = this.forecast?.metadata?.selected_branches_count;
    return count === undefined ? 'Sin sucursales' : `${count} sucursales`;
  }

  get trackContextVersionLabel(): string {
    const versionId = this.forecast?.metadata?.resolved_version.id;
    return versionId === undefined ? 'Sin versión' : `Versión ${versionId}`;
  }

  get generationModeDisplayLabel(): string {
    const mode = this.forecast?.metadata?.generation_mode ?? this.generationMode;
    return mode === 'official_closed_day' ? 'Cierre oficial' : 'Vista preliminar';
  }

  get executiveToneClass(): string {
    const level = this.executiveStatus?.level ?? 'neutral';
    return `track-trend-tone--${level}`;
  }

  get goalToneClass(): string {
    const status = this.forecast?.data_quality?.goal_status;

    if (status === 'available') {
      return 'track-trend-tone--positive';
    }

    if (status === 'partial') {
      return 'track-trend-tone--warning';
    }

    return 'track-trend-tone--neutral';
  }

  get historicalExpectedMtdLabel(): string {
    const value = this.summary?.historical_expected_mtd;
    return value === null || value === undefined
      ? 'Sin histórico comparable'
      : this.formatCurrency(value);
  }

  get projectedCloseLabel(): string {
    const value = this.summary?.projected_close;
    return value === null || value === undefined
      ? 'Sin proyección estable'
      : this.formatCurrency(value);
  }

  get projectionSupportText(): string {
    if (this.summary?.projected_close !== null && this.summary?.projected_close !== undefined) {
      return this.executiveMessage;
    }

    return (
      this.forecast?.data_quality?.branch_projection_quality_issue?.message
      || this.forecastExplanation?.plain_text
      || 'No hay histórico suficiente para calcular una proyección estable.'
    );
  }

  get goalValueLabel(): string {
    const status = this.forecast?.data_quality?.goal_status;

    if (status === 'pending') {
      return 'Meta pendiente';
    }

    if (status === 'partial') {
      return 'Meta parcial';
    }

    return this.formatCurrency(this.summary?.goal_month);
  }

  get goalSupportText(): string {
    return this.goalStatusMessage || 'Meta mensual disponible';
  }

  get executiveStatus(): TrackVentaTotalForecastExecutiveStatus | null {
    return this.forecast?.executive_status ?? null;
  }

  get forecastExplanation(): TrackVentaTotalForecastExplanation | null {
    return this.forecast?.forecast_explanation ?? null;
  }

  get forecastWarnings(): TrackVentaTotalForecastWarning[] {
    return this.forecast?.warnings ?? [];
  }

  get forecastCutoff(): TrackVentaTotalForecastCutoff | null {
    return this.forecast?.forecast_cutoff ?? null;
  }


  get sameDayHistory(): TrackVentaTotalForecastSameDayHistory | null {
    return this.forecast?.same_day_history ?? null;
  }

  get sameDayHistoryItems(): TrackVentaTotalForecastSameDayHistoryItem[] {
    return this.sameDayHistory?.items || [];
  }

  get sameDayHistoryCurrent(): TrackVentaTotalForecastSameDayHistory['current'] | null {
    return this.sameDayHistory?.current || null;
  }

  get sameDayHistoryAverage(): TrackVentaTotalForecastSameDayHistory['average'] | null {
    return this.sameDayHistory?.average || null;
  }

  get sameDayHistoryTitle(): string {
    const cutoffDay = this.sameDayHistory?.cutoff_day || this.forecastCutoff?.cutoff_day || '—';
    return `Comparativo mismo día · día ${cutoffDay}`;
  }

  get sameDayHistorySubtitle(): string {
    const years = this.sameDayHistory?.historical_years ?? 0;
    const confidence = this.sameDayHistory?.confidence || 'sin dato';

    return `${years} años comparables · confianza ${confidence}`;
  }

  get hasSameDayHistory(): boolean {
    return this.sameDayHistoryItems.length > 0;
  }

  get comparableChartBars(): TrackForecastComparableBar[] {
    const history = this.sameDayHistory;

    if (!history || !history.items.length) {
      return [];
    }

    const rawBars: Array<Omit<
      TrackForecastComparableBar,
      'mtdBarPct' | 'monthBarPct' | 'monthLabel' | 'monthValueLabel'
    >> = history.items.map((item) => ({
      year: item.year,
      mtdValue: item.mtd_total,
      monthTotalValue: item.month_total,
      isCurrent: false,
    }));

    rawBars.push({
      year: history.current.year,
      mtdValue: history.current.mtd_total,
      monthTotalValue: history.current.projected_close,
      isCurrent: true,
    });

    const maxVisibleValue = Math.max(
      0,
      ...rawBars.flatMap((item) => [
        item.mtdValue,
        item.monthTotalValue ?? 0,
      ]),
    );

    return rawBars.map((item) => ({
      ...item,
      mtdBarPct: this.toVisualPercent(item.mtdValue, maxVisibleValue),
      monthBarPct: this.toVisualPercent(item.monthTotalValue, maxVisibleValue),
      monthLabel: item.isCurrent ? 'Proyección disponible' : 'Cierre mensual',
      monthValueLabel: item.monthTotalValue === null
        ? 'Sin proyección estable'
        : this.formatCurrency(item.monthTotalValue),
    }));
  }

  get hasComparableChart(): boolean {
    return this.comparableChartBars.length > 0;
  }

  get currentSameDayGapVsAverageLabel(): string {
    const gapPct = this.sameDayHistoryAverage?.gap_current_vs_average_mtd_pct;

    if (gapPct === null || gapPct === undefined) {
      return '';
    }

    if (gapPct > 0) {
      return `Actual: ${this.formatPercent(Math.abs(gapPct))} arriba del promedio simple comparable`;
    }

    if (gapPct < 0) {
      return `Actual: ${this.formatPercent(Math.abs(gapPct))} abajo del promedio simple comparable`;
    }

    return 'Actual: en línea con el promedio simple comparable';
  }



  get cohortForecast(): TrackVentaTotalForecastCohortForecast | null {
    return this.forecast?.cohort_forecast ?? null;
  }

  get cohortForecastItems(): TrackVentaTotalForecastCohortItem[] {
    const forecast = this.cohortForecast;
    return forecast?.status === 'ok' ? forecast.items : [];
  }

  get cohortViewModels(): TrackForecastCohortViewModel[] {
    const order: TrackVentaTotalForecastCohortItem['cohort_key'][] = ['total_ultra', 'legacy_21', 'new_gyms'];

    return [...this.cohortForecastItems]
      .sort((left, right) => order.indexOf(left.cohort_key) - order.indexOf(right.cohort_key))
      .map((item) => ({
        cohort_key: item.cohort_key,
        label: item.label || item.cohort_key,
        branches_count: item.branches_count,
        real_mtd: item.real_mtd,
        historical_expected_mtd: item.historical_expected_mtd,
        gap_vs_expected_mtd: item.gap_vs_expected_mtd,
        gap_vs_expected_mtd_pct: item.gap_vs_expected_mtd_pct,
        trend_factor: item.trend_factor,
        projected_close: item.projected_close,
        projected_close_experimental: item.projected_close_experimental,
        confidence: item.confidence,
        projection_quality_issue: item.projection_quality_issue,
        visualTone: item.gap_vs_expected_mtd !== null && item.gap_vs_expected_mtd < 0 ? 'negative' : 'neutral',
        gapLabel: `${this.formatCurrency(item.gap_vs_expected_mtd)} · ${this.formatPercent(item.gap_vs_expected_mtd_pct)}`,
        trendLabel: this.formatPercent(item.trend_factor),
        projectionLabel: item.projected_close === null ? 'Sin proyección estable' : this.formatCurrency(item.projected_close),
        experimentalLabel: item.projected_close_experimental === null ? '—' : this.formatCurrency(item.projected_close_experimental),
      }));
  }

  get cohortEmptyMessage(): string {
    return this.cohortForecast?.status === 'not_applicable'
      ? 'La composición por cohortes no aplica para el alcance por sucursal.'
      : 'No hay cohortes disponibles para este corte.';
  }

  get selectedCohortItem(): TrackVentaTotalForecastCohortItem | null {
    if (!this.selectedCohortKey) {
      return null;
    }

    return this.cohortForecastItems.find((item) => item.cohort_key === this.selectedCohortKey) ?? null;
  }

  get selectedCohortBranches(): string[] {
    return this.selectedCohortItem?.branches ?? [];
  }

  get selectedCohortBranchRows(): TrackVentaTotalForecastBranchDriverItem[] {
    const selectedBranches = new Set(this.selectedCohortBranches);

    return this.branchDriverItems.filter((item) => selectedBranches.has(item.sucursal_canon));
  }

  get selectedCohortTitle(): string {
    return this.selectedCohortItem?.label || this.selectedCohortItem?.cohort_key || '';
  }

  get selectedCohortCount(): number {
    return this.selectedCohortBranches.length;
  }

  get canOpenCohortDetails(): boolean {
    return this.branchDrivers?.status === 'ok';
  }

  selectCohort(cohortKey: TrackVentaTotalForecastCohortItem['cohort_key']): void {
    if (!this.canOpenCohortDetails) {
      return;
    }

    this.selectedCohortKey = this.selectedCohortKey === cohortKey ? null : cohortKey;
  }

  isCohortSelected(cohortKey: TrackVentaTotalForecastCohortItem['cohort_key']): boolean {
    return this.selectedCohortKey === cohortKey;
  }

  getCohortDetailTooltip(metric: CohortDetailMetricKey): string {
    return COHORT_DETAIL_METRIC_TOOLTIPS[metric];
  }

  getBlockedProjectionTooltip(row: TrackVentaTotalForecastBranchDriverItem): string {
    const qualityIssue = row.projection_quality_issue;

    if (!qualityIssue) {
      return '';
    }

    const reasons = qualityIssue.reasons.length
      ? ` Motivos: ${qualityIssue.reasons.join(' ')}`
      : '';

    return `${qualityIssue.message}${reasons}`;
  }

  get branchDrivers(): TrackVentaTotalForecastBranchDrivers | null {
    return this.forecast?.branch_drivers ?? null;
  }

  get branchDriverItems(): TrackVentaTotalForecastBranchDriverItem[] {
    const drivers = this.branchDrivers;
    return drivers?.status === 'ok' ? drivers.items : [];
  }

  get negativeBranchDrivers(): TrackVentaTotalForecastBranchDriverItem[] {
    return this.branchDriverItems
      .filter((item) => (item.gap_vs_historical_expected ?? 0) < 0)
      .slice(0, 12);
  }

  get branchDriverViewModels(): TrackForecastBranchDriverViewModel[] {
    const maxImpact = Math.max(
      0,
      ...this.negativeBranchDrivers.map((item) => item.impact_share_pct),
    );

    return this.negativeBranchDrivers.map((item, index) => ({
      rank: index + 1,
      track_label: item.track_label || item.sucursal_canon,
      sucursal_canon: item.sucursal_canon,
      real_mtd: item.real_mtd,
      historical_expected_mtd: item.historical_expected_mtd,
      gap_vs_historical_expected: item.gap_vs_historical_expected,
      gap_vs_historical_expected_pct: item.gap_vs_historical_expected_pct,
      trend_factor: item.trend_factor,
      projected_close: item.projected_close,
      impact_share_pct: item.impact_share_pct,
      confidence: item.confidence,
      projection_quality_issue: item.projection_quality_issue,
      impactBarPct: maxImpact > 0
        ? Math.min(100, Math.max(0, (item.impact_share_pct / maxImpact) * 100))
        : 0,
      visualTone: 'negative',
    }));
  }

  get branchDriversEmptyMessage(): string {
    return this.branchDrivers?.status === 'not_applicable'
      ? 'El ranking nacional no aplica para el alcance por sucursal.'
      : 'No hay sucursales con brecha negativa frente al esperado histórico.';
  }

  get branchSelectDisabled(): boolean {
    return this.loadingBranches || !this.branchOptions.length;
  }

  get branchCatalogStatusLabel(): string {
    if (this.loadingBranches) {
      return 'Cargando sucursales Track...';
    }

    if (this.branchCatalogMessage) {
      return this.branchCatalogMessage;
    }

    return `${this.branchOptions.length} sucursales Track activas`;
  }

  get selectedBranchLabel(): string {
    const selected = this.branchOptions.find(
      (item) => item.sucursal_canon === this.branch,
    );

    return selected?.track_label || selected?.sucursal_canon || this.branch || 'Sucursal';
  }

  get executiveLevelClass(): string {
    const level = this.executiveStatus?.level || 'neutral';
    return `track-forecast-hero--${level}`;
  }

  get executiveBadgeLabel(): string {
    const level = this.executiveStatus?.level || 'neutral';

    if (level === 'danger') {
      return 'Atención alta';
    }

    if (level === 'warning') {
      return 'Atención';
    }

    if (level === 'success') {
      return 'Buen ritmo';
    }

    return 'Lectura ejecutiva';
  }

  get executivePrimaryValue(): number | null | undefined {
    return this.executiveStatus?.primary_metric_value ?? this.summary?.projected_close;
  }

  get executiveTitle(): string {
    return this.executiveStatus?.title || 'Proyección de cierre';
  }

  get executiveMessage(): string {
    return this.executiveStatus?.message || 'Consulta la proyección de cierre con base en histórico y tendencia actual.';
  }

  get forecastExplanationText(): string {
    return this.forecastExplanation?.plain_text || 'Sin explicación disponible.';
  }

  get forecastFormula(): string {
    return this.forecastExplanation?.formula || 'projected_close = real_mtd / historical_progress_pct';
  }

  get goalStatusMessage(): string {
    return this.forecast?.data_quality?.goal_status_message || '';
  }

  get historyConfidence(): string {
    return this.forecast?.historical_curve?.confidence || 'sin dato';
  }

  get historyCoverageLabel(): string {
    const coverage = this.forecast?.data_quality?.history_coverage;

    if (!coverage) {
      return 'Sin cobertura histórica';
    }

    return `${coverage.months_count} meses (${coverage.first_month || '—'} a ${coverage.last_month || '—'})`;
  }

  get resolvedVersionLabel(): string {
    const version = this.forecast?.metadata?.resolved_version;

    if (!version) {
      return 'Sin versión resuelta';
    }

    return `Versión ${version.id} · ${version.version_type} · ${version.status}`;
  }

  get scopeLabel(): string {
    if (this.scope === 'branch') {
      return this.selectedBranchLabel;
    }

    return 'Nacional';
  }

  get forecastBasisLabel(): string {
    if (!this.forecastCutoff) {
      return 'Sin corte';
    }

    return this.forecastCutoff.is_official_forecast ? 'Cierre oficial' : 'Preview operativo';
  }

  get forecastCutoffMessage(): string {
    return this.forecastCutoff?.message || 'Sin mensaje de corte.';
  }

  get canonicalCutoffLabel(): string {
    const canonical = this.forecastCutoff?.canonical_cutoff;

    if (!canonical) {
      return 'Sin corte canónico agregado';
    }

    return `${canonical.business_date || '—'} · snapshot ${canonical.snapshot_id || '—'} · ${canonical.branches || 0} sucursales`;
  }

  get cutoffDateLabel(): string {
    if (!this.forecastCutoff) {
      return '—';
    }

    return `${this.forecastCutoff.track_date || '—'} · día ${this.forecastCutoff.cutoff_day || '—'}`;
  }

  get selectedBranchesCount(): number {
    return this.forecast?.metadata?.selected_branches_count || 0;
  }

  get forecastAlerts(): TrackForecastAlertViewModel[] {
    const alerts: TrackForecastAlertViewModel[] = this.forecastWarnings.map((warning) => ({
      code: warning.code,
      severity: warning.severity,
      title: this.getWarningTitle(warning),
      message: warning.message,
      reasons: 'reasons' in warning ? warning.reasons : [],
      sourceLabel: 'Warnings',
      tone: warning.severity === 'warning' ? 'warning' : 'info',
    }));
    const branchIssue = this.forecast?.data_quality?.branch_projection_quality_issue;

    if (branchIssue) {
      alerts.push(this.toQualityAlert(branchIssue, 'Calidad de proyección por sucursal'));
    }

    this.cohortForecastItems.forEach((item) => {
      if (item.projection_quality_issue) {
        alerts.push(this.toQualityAlert(item.projection_quality_issue, `Cohorte: ${item.label}`));
      }
    });

    this.negativeBranchDrivers.forEach((item) => {
      if (item.projection_quality_issue) {
        alerts.push(this.toQualityAlert(item.projection_quality_issue, `Sucursal: ${item.track_label || item.sucursal_canon}`));
      }
    });

    const uniqueAlerts = new Map<string, TrackForecastAlertViewModel>();
    alerts.forEach((alert) => {
      const key = `${alert.code}|${alert.message}|${alert.sourceLabel}`;
      if (!uniqueAlerts.has(key)) {
        uniqueAlerts.set(key, alert);
      }
    });
    return Array.from(uniqueAlerts.values());
  }

  get traceItems(): TrackForecastTraceItem[] {
    const metadata = this.forecast?.metadata;
    const curve = this.forecast?.historical_curve;
    const coverage = this.forecast?.data_quality?.history_coverage;
    const canonical = this.forecastCutoff?.canonical_cutoff;
    return [
      { label: 'Fecha Track', value: metadata?.track_date ? this.formatShortDate(metadata.track_date) : '—' },
      { label: 'Versión Track', value: this.resolvedVersionLabel },
      { label: 'Modo', value: this.generationModeDisplayLabel },
      { label: 'Scope', value: metadata?.scope || this.scope },
      ...(metadata?.branch ? [{ label: 'Sucursal', value: metadata.branch }] : []),
      { label: 'Ventana histórica', value: metadata ? `${metadata.history_window.start} a ${metadata.history_window.end_exclusive}` : '—' },
      { label: 'Fuente del histórico', value: curve?.source || '—' },
      { label: 'Meses históricos', value: this.formatNumber(curve?.historical_months ?? coverage?.months_count) },
      { label: 'Días comparables', value: this.formatNumber(curve?.distinct_days) },
      { label: 'Confianza histórica', value: curve?.confidence || coverage?.confidence || '—' },
      { label: 'Último corte canónico disponible', value: canonical ? 'Disponible' : 'No disponible' },
      { label: 'Snapshot canónico', value: canonical ? this.formatNumber(canonical.snapshot_id) : '—' },
      { label: 'Fecha comercial canónica', value: canonical?.business_date || '—' },
      { label: 'Sucursales del snapshot', value: this.formatNumber(canonical?.branches) },
      { label: 'Mensaje de forecast_cutoff', value: this.forecastCutoffMessage },
    ];
  }

  private getWarningTitle(warning: TrackVentaTotalForecastWarning): string {
    if (warning.code === 'preview_operativo') {
      return 'Preview operativo';
    }

    if (warning.code === 'goal_pending') {
      return 'Meta pendiente';
    }

    if (warning.code === 'goal_partial') {
      return 'Meta parcial';
    }

    if (warning.code === 'canonical_cutoff_missing') {
      return 'Corte canónico no encontrado';
    }

    if (warning.code === 'low_comparable_history') {
      return 'Histórico comparable bajo';
    }

    return warning.code || 'Advertencia';
  }

  private toQualityAlert(
    issue: { code: string; severity: string; message: string; reasons: string[] },
    sourceLabel: string,
  ): TrackForecastAlertViewModel {
    return {
      code: issue.code,
      severity: issue.severity,
      title: this.getQualityIssueTitle(issue.code),
      message: issue.message,
      reasons: issue.reasons,
      sourceLabel,
      tone: issue.severity === 'warning' ? 'warning' : 'info',
    };
  }

  private getQualityIssueTitle(code: string): string {
    if (code === 'partial_cohort_history') {
      return 'Histórico parcial por cohorte';
    }
    if (code === 'insufficient_cohort_history') {
      return 'Histórico de cohorte insuficiente';
    }
    if (code === 'insufficient_branch_history') {
      return 'Histórico de sucursal insuficiente';
    }
    return code;
  }

  formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value);
  }

  formatPercent(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }

  formatNumber(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 2,
    }).format(value);
  }

  private toVisualPercent(value: number | null, maximum: number): number {
    if (value === null || maximum <= 0) {
      return 0;
    }

    return Math.min(100, Math.max(0, (value / maximum) * 100));
  }

  private formatShortDate(value: string): string {
    const date = new Date(`${value}T00:00:00`);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(date);
  }

  private getTodayIsoDate(): string {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());

    return now.toISOString().slice(0, 10);
  }
}
