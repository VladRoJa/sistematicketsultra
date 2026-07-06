import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService } from '../../services/auth.service';
import {
  TrackForecastBranchOption,
  TrackGenerationMode,
  TrackService,
  TrackVentaTotalForecastResponse,
  TrackVentaTotalForecastScope,
  TrackVentaTotalForecastSummary,
} from '../../services/track.service';


type SameDayHistoryItem = {
  year?: number;
  business_month?: string | null;
  mtd_total?: number | null;
  month_total?: number | null;
  remaining_total?: number | null;
  progress_pct?: number | null;
  mtd_days?: number | null;
  month_days?: number | null;
  gap_current_vs_mtd?: number | null;
  gap_current_vs_mtd_pct?: number | null;
};

type SameDayHistory = {
  source?: 'national' | 'branch' | string;
  branch?: string | null;
  target_month?: string;
  cutoff_day?: number;
  historical_years?: number;
  confidence?: string;
  average?: {
    mtd_total?: number | null;
    month_total?: number | null;
    gap_current_vs_average_mtd?: number | null;
    gap_current_vs_average_mtd_pct?: number | null;
  };
  current?: {
    year?: number;
    mtd_total?: number | null;
    projected_close?: number | null;
    historical_progress_pct?: number | null;
    trend_factor?: number | null;
  };
  items?: SameDayHistoryItem[];
};


type BranchDriverItem = {
  sucursal_canon?: string;
  track_label?: string;
  display_order?: number | null;
  real_mtd?: number | null;
  real_base_mtd?: number | null;
  real_agregadora_mtd?: number | null;
  historical_months?: number | null;
  historical_expected_mtd?: number | null;
  historical_expected_month_total?: number | null;
  historical_progress_pct?: number | null;
  gap_vs_historical_expected?: number | null;
  gap_vs_historical_expected_pct?: number | null;
  trend_factor?: number | null;
  projected_close?: number | null;
  impact_share_pct?: number | null;
  confidence?: string;
  projection_quality_issue?: {
    code?: string;
    severity?: string;
    message?: string;
    reasons?: string[];
  } | null;
};

type BranchDrivers = {
  status?: string;
  scope?: string;
  metric?: string;
  target_month?: string;
  cutoff_day?: number;
  items_count?: number;
  negative_gap_total?: number | null;
  items?: BranchDriverItem[];
};

type ForecastExecutiveStatus = {
  level?: 'success' | 'warning' | 'danger' | 'neutral' | string;
  code?: string;
  title?: string;
  message?: string;
  primary_metric_label?: string;
  primary_metric_value?: number | null;
  primary_metric_unit?: string;
};

type ForecastExplanation = {
  formula_key?: string;
  formula?: string;
  plain_text?: string;
  components?: {
    cutoff_day?: number;
    real_mtd?: number | null;
    historical_progress_pct?: number | null;
    historical_expected_mtd?: number | null;
    trend_factor?: number | null;
    projected_close?: number | null;
  };
};

type ForecastWarning = {
  code?: string;
  severity?: 'info' | 'warning' | 'danger' | string;
  message?: string;
};

type ForecastCutoff = {
  track_date?: string;
  target_month?: string;
  cutoff_day?: number;
  generation_mode?: string;
  is_official_forecast?: boolean;
  basis?: string;
  message?: string;
  canonical_cutoff?: {
    snapshot_id?: number;
    business_date?: string;
    aggregate_rows?: number;
    first_sale_date?: string;
    last_sale_date?: string;
    branches?: number;
  } | null;
};

@Component({
  selector: 'app-track-forecast',
  standalone: true,
  imports: [CommonModule, FormsModule],
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

  get executiveStatus(): ForecastExecutiveStatus | null {
    return ((this.forecast as any)?.executive_status ?? null) as ForecastExecutiveStatus | null;
  }

  get forecastExplanation(): ForecastExplanation | null {
    return ((this.forecast as any)?.forecast_explanation ?? null) as ForecastExplanation | null;
  }

  get forecastWarnings(): ForecastWarning[] {
    return (((this.forecast as any)?.warnings ?? []) as ForecastWarning[]);
  }

  get forecastCutoff(): ForecastCutoff | null {
    return ((this.forecast as any)?.forecast_cutoff ?? null) as ForecastCutoff | null;
  }


  get sameDayHistory(): SameDayHistory | null {
    return ((this.forecast as any)?.same_day_history ?? null) as SameDayHistory | null;
  }

  get sameDayHistoryItems(): SameDayHistoryItem[] {
    return this.sameDayHistory?.items || [];
  }

  get sameDayHistoryCurrent(): SameDayHistory['current'] | null {
    return this.sameDayHistory?.current || null;
  }

  get sameDayHistoryAverage(): SameDayHistory['average'] | null {
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

  get currentSameDayGapVsAverageLabel(): string {
    const gapPct = this.sameDayHistoryAverage?.gap_current_vs_average_mtd_pct;

    if (gapPct === null || gapPct === undefined) {
      return 'Sin promedio comparable';
    }

    if (gapPct >= 0) {
      return `${this.formatPercent(gapPct)} arriba del promedio`;
    }

    return `${this.formatPercent(Math.abs(gapPct))} abajo del promedio`;
  }


  get branchDrivers(): BranchDrivers | null {
    return ((this.forecast as any)?.branch_drivers ?? null) as BranchDrivers | null;
  }

  get branchDriverItems(): BranchDriverItem[] {
    return this.branchDrivers?.items || [];
  }

  get negativeBranchDrivers(): BranchDriverItem[] {
    return this.branchDriverItems
      .filter((item) => (item.gap_vs_historical_expected ?? 0) < 0)
      .slice(0, 12);
  }

  get hasBranchDrivers(): boolean {
    return this.negativeBranchDrivers.length > 0;
  }

  get branchDriversTitle(): string {
    const cutoffDay = this.branchDrivers?.cutoff_day || this.forecastCutoff?.cutoff_day || '—';
    return `Tendencias por sucursal · día ${cutoffDay}`;
  }

  get branchDriversSubtitle(): string {
    const count = this.branchDrivers?.items_count || this.branchDriverItems.length || 0;
    return `${count} sucursales analizadas · ordenado por mayor gap negativo`;
  }

  get negativeGapTotalLabel(): string {
    return this.formatCurrency(this.branchDrivers?.negative_gap_total);
  }

  get topNegativeDriverLabel(): string {
    const top = this.negativeBranchDrivers[0];

    if (!top) {
      return 'Sin rezagos detectados';
    }

    return `${top.track_label || top.sucursal_canon} · ${this.formatPercent(top.impact_share_pct)} del gap`;
  }

  getDriverTrendClass(item: BranchDriverItem): string {
    const gap = item.gap_vs_historical_expected ?? 0;

    if (gap < 0) {
      return 'track-forecast-delta--negative';
    }

    if (gap > 0) {
      return 'track-forecast-delta--positive';
    }

    return 'track-forecast-delta--neutral';
  }

  getDriverProjectionLabel(item: BranchDriverItem): string {
    if (item.projection_quality_issue) {
      return 'Sin proyección estable';
    }

    return this.formatCurrency(item.projected_close);
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

  getWarningTitle(warning: ForecastWarning): string {
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

  getWarningClass(warning: ForecastWarning): string {
    const severity = warning.severity || 'info';
    return `track-forecast-warning--${severity}`;
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

  private getTodayIsoDate(): string {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());

    return now.toISOString().slice(0, 10);
  }
}
