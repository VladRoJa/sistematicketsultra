import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { LineChart, LineSeriesOption } from 'echarts/charts';
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  LegendScrollComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { EChartsCoreOption } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import { EMPTY, auditTime, catchError, combineLatest, distinctUntilChanged, switchMap, tap } from 'rxjs';

import {
  TrackBranchForecastDetailHistoricalYearItem,
  TrackBranchForecastDetailHistoricalYearStatus,
  TrackBranchForecastDetailResponse,
  TrackGenerationMode,
  TrackService,
} from '../../services/track.service';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  LegendScrollComponent,
  MarkLineComponent,
  AriaComponent,
  CanvasRenderer,
]);

type TrackForecastCohortKey = 'legacy_21' | 'new_gyms' | 'total_ultra';

type BranchDetailRequest = {
  sucursalCanon: string;
  trackDate: string;
  generationMode: string;
  cohort: string | null;
};

type BranchDetailSummaryCard = {
  label: string;
  value: string;
  support: string;
  emphasis: 'neutral' | 'total' | 'base';
};

type BranchDetailAnnualRow = {
  yearLabel: string;
  statusLabel: string;
  available: boolean;
  mtdLabel: string;
  closeLabel: string;
  positiveDaysLabel: string;
  snapshotDateLabel: string;
  availabilityLabel: string;
  isCurrent: boolean;
};

type BranchDetailTraceItem = {
  label: string;
  value: string;
};

@Component({
  selector: 'app-track-forecast-branch-detail',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective],
  templateUrl: './track-forecast-branch-detail.component.html',
  styleUrls: ['./track-forecast-branch-detail.component.css'],
  providers: [provideEchartsCore({ echarts })],
})
export class TrackForecastBranchDetailComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);

  loading = true;
  errorMessage = '';
  detail: TrackBranchForecastDetailResponse | null = null;
  chartOption: EChartsCoreOption = {};
  summaryCards: BranchDetailSummaryCard[] = [];
  annualRows: BranchDetailAnnualRow[] = [];
  qualityItems: BranchDetailTraceItem[] = [];
  traceItems: BranchDetailTraceItem[] = [];
  chartNotes: string[] = [];
  warningMessages: string[] = [];
  usedYearsLabel = 'No disponible';
  excludedYearsLabel = 'Ninguno';

  sucursalCanon = '';
  branchDisplayName = 'Sucursal';
  trackDate = '';
  generationMode: TrackGenerationMode = 'manual_preview';
  cohort: TrackForecastCohortKey | null = null;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly trackService: TrackService,
  ) {}

  ngOnInit(): void {
    combineLatest([this.route.paramMap, this.route.queryParamMap])
      .pipe(
        auditTime(0),
        switchMap(([paramMap, queryParamMap]) => {
          const request: BranchDetailRequest = {
            sucursalCanon: paramMap.get('sucursalCanon') || '',
            trackDate: queryParamMap.get('track_date') || '',
            generationMode: queryParamMap.get('generation_mode') || '',
            cohort: queryParamMap.get('cohort'),
          };

          return [request];
        }),
        distinctUntilChanged((previous, current) => this.sameRequest(previous, current)),
        tap((request) => this.prepareRequest(request)),
        switchMap((request) => {
          if (!this.isValidRequest(request)) {
            this.loading = false;
            this.errorMessage = 'No fue posible interpretar los parámetros del detalle.';
            return EMPTY;
          }

          return this.trackService
            .getBranchForecastDetail(
              request.sucursalCanon,
              request.trackDate,
              request.generationMode,
            )
            .pipe(
              tap((response) => this.handleResponse(response)),
              catchError((error: HttpErrorResponse) => {
                this.loading = false;
                this.errorMessage = this.getErrorMessage(error.status);
                return EMPTY;
              }),
            );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }

  backToForecast(): void {
    const queryParams: {
      track_date?: string;
      generation_mode?: TrackGenerationMode;
      cohort?: TrackForecastCohortKey;
    } = {};

    if (this.trackDate) {
      queryParams.track_date = this.trackDate;
    }
    queryParams.generation_mode = this.generationMode;
    if (this.cohort) {
      queryParams.cohort = this.cohort;
    }

    void this.router.navigate(['/warehouse/track/forecast'], { queryParams });
  }

  get headerCutoffLabel(): string {
    return this.detail ? this.formatDate(this.detail.metadata.track_date) : this.formatDate(this.trackDate);
  }

  get generationModeLabel(): string {
    return this.generationMode === 'official_closed_day' ? 'Día cerrado oficial' : 'Preview operativo';
  }

  get versionLabel(): string {
    const id = this.detail?.metadata.resolved_version.id;
    return id === undefined ? 'No disponible' : `Versión ${id}`;
  }

  get versionTypeLabel(): string {
    const point = this.cutoffPoint;
    return point ? this.formatTechnicalLabel(point.version_type) : 'No disponible';
  }

  get confidenceLabel(): string {
    return this.detail?.summary.confidence
      ? this.formatTechnicalLabel(this.detail.summary.confidence)
      : 'No disponible';
  }

  get hasChartSeries(): boolean {
    const series = this.chartOption.series;
    return Array.isArray(series) && series.length > 0;
  }

  private get cutoffPoint() {
    const points = this.detail?.series.current_track.points || [];
    return points.length ? points[points.length - 1] : null;
  }

  private prepareRequest(request: BranchDetailRequest): void {
    this.loading = true;
    this.errorMessage = '';
    this.detail = null;
    this.resetPresentation();
    this.sucursalCanon = request.sucursalCanon.trim().toUpperCase();
    this.branchDisplayName = this.formatBranchName(this.sucursalCanon);
    this.trackDate = request.trackDate;

    if (request.generationMode === 'manual_preview' || request.generationMode === 'official_closed_day') {
      this.generationMode = request.generationMode;
    }

    this.cohort = this.parseCohort(request.cohort);
  }

  private handleResponse(response: TrackBranchForecastDetailResponse): void {
    this.loading = false;

    if (!this.isCompleteResponse(response)) {
      this.errorMessage = 'La respuesta del detalle está incompleta.';
      return;
    }

    this.detail = response;
    this.sucursalCanon = response.metadata.sucursal_canon;
    this.branchDisplayName = this.formatBranchName(response.metadata.sucursal_canon);
    this.buildPresentation(response);
  }

  private buildPresentation(response: TrackBranchForecastDetailResponse): void {
    const summary = response.summary;
    const qualityIssue = response.series.comparable_base_projection.quality_issue;
    const unavailableSupport = qualityIssue?.message || 'No existe un valor disponible para este corte.';

    this.summaryCards = [
      this.toSummaryCard('Real Track MTD', summary.real_mtd, 'Venta total al corte: base más agregadoras.', 'total'),
      this.toSummaryCard('Base MTD', summary.real_base_mtd, 'Venta base comparable al corte.', 'base'),
      this.toSummaryCard('Agregadoras MTD', summary.real_agregadora_mtd, 'Fuentes agregadoras integradas en Track.', 'neutral'),
      this.toSummaryCard(
        'Esperado histórico al corte',
        summary.historical_expected_mtd,
        summary.historical_expected_mtd === null
          ? `No disponible: ${this.getExpectedStatusLabel(response.series.historical_expected.status)}.`
          : 'Trayectoria histórica comparable de venta base.',
        'base',
      ),
      this.toSummaryCard(
        'Brecha contra esperado',
        response.forecast_context.same_day_history.average.gap_current_vs_average_mtd,
        'Brecha precalculada por el backend contra el promedio comparable al corte.',
        'neutral',
      ),
      this.toSummaryCard(
        'Proyección total Track',
        summary.projected_close,
        summary.projected_close === null
          ? 'No existe una proyección total disponible para este corte.'
          : 'Cierre proyectado de venta total Track, incluyendo agregadoras.',
        'total',
      ),
      this.toSummaryCard(
        'Proyección base comparable',
        response.series.comparable_base_projection.projected_close,
        response.series.comparable_base_projection.projected_close === null
          ? unavailableSupport
          : 'Cierre proyectado exclusivamente sobre venta base.',
        'base',
      ),
    ];

    this.chartOption = this.buildChartOption(response);
    this.annualRows = this.buildAnnualRows(response);
    this.warningMessages = response.data_quality.warnings.map((warning) => warning.message);
    this.usedYearsLabel = response.series.historical_expected.comparison_years_used.length
      ? response.series.historical_expected.comparison_years_used.join(', ')
      : 'Ninguno';
    this.excludedYearsLabel = response.series.historical_expected.comparison_years_excluded.length
      ? response.series.historical_expected.comparison_years_excluded
          .map((item) => `${item.year}: ${this.formatTechnicalLabel(item.reason)}`)
          .join(' · ')
      : 'Ninguno';
    this.qualityItems = this.buildQualityItems(response);
    this.traceItems = this.buildTraceItems(response);
  }

  private buildChartOption(response: TrackBranchForecastDetailResponse): EChartsCoreOption {
    const lineSeries: LineSeriesOption[] = [];
    const monthLabel = this.formatMonth(response.metadata.target_month);
    const historicalColors = ['#59697c', '#8a6742', '#6f567d', '#46766f'];
    const daysInTargetMonth = this.daysInMonth(response.metadata.target_month);
    const cutoffDay = response.metadata.cutoff_day;
    const showCutoffMarker = Number.isInteger(cutoffDay)
      && cutoffDay >= 1
      && cutoffDay <= daysInTargetMonth;
    const historicalItems = response.series.historical_years.items
      .filter((item) => item.status === 'available' && item.points.length > 0)
      .sort((left, right) => left.year - right.year);

    historicalItems.forEach((item, index) => {
      const lineType = this.getHistoricalLineType(index, historicalItems.length);
      const isMostRecent = index === historicalItems.length - 1;
      lineSeries.push({
        name: `${monthLabel} ${item.year}`,
        type: 'line',
        data: item.points.map((point) => [point.day, point.cumulative_total]),
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: {
          color: historicalColors[index % historicalColors.length],
          width: isMostRecent ? 2.25 : 1.9,
          type: lineType,
          opacity: 1,
        },
        itemStyle: { color: historicalColors[index % historicalColors.length] },
        emphasis: { focus: 'series' },
      });
    });

    const currentPoints = response.series.current_track.points;
    if (currentPoints.length) {
      lineSeries.push({
        name: `Real ${new Date(`${response.metadata.track_date}T00:00:00`).getFullYear()}`,
        type: 'line',
        data: currentPoints
          .filter((point) => point.base_mtd !== null)
          .map((point) => [point.day, point.base_mtd]),
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#315f8c', width: 3.5, type: 'solid', opacity: 1 },
        itemStyle: { color: '#315f8c' },
        emphasis: { focus: 'series' },
        markLine: showCutoffMarker ? {
          silent: true,
          symbol: 'none',
          label: {
            formatter: 'Corte actual',
            position: 'insideEndTop',
            color: '#526075',
          },
          lineStyle: {
            color: '#687386',
            type: 'dashed',
            width: 1.25,
            opacity: 1,
          },
          data: [{ xAxis: cutoffDay }],
        } : undefined,
        z: 6,
      });
    }

    const expected = response.series.historical_expected;
    if (expected.status === 'available' && expected.points.length) {
      lineSeries.push({
        name: 'Esperado histórico',
        type: 'line',
        data: expected.points.map((point) => [point.day, point.expected_cumulative_total]),
        showSymbol: false,
        lineStyle: { color: '#8a5a1f', width: 2, type: 'dashed' },
        itemStyle: { color: '#8a5a1f' },
        emphasis: { focus: 'series' },
        z: 3,
      });
    } else {
      this.chartNotes.push(`Esperado histórico: ${this.getExpectedStatusLabel(expected.status)}.`);
    }

    const projection = response.series.comparable_base_projection;
    if (projection.status === 'available' && projection.path?.status === 'available' && projection.path.points.length) {
      lineSeries.push({
        name: 'Proyección base',
        type: 'line',
        data: projection.path.points.map((point) => [point.day, point.projected_cumulative_total]),
        showSymbol: false,
        lineStyle: { color: '#278363', width: 2.5, type: 'dashed' },
        itemStyle: { color: '#278363' },
        emphasis: { focus: 'series' },
        z: 5,
      });
    } else {
      this.chartNotes.push(`Proyección base: ${this.getProjectionStatusLabel(projection.status)}.`);
    }

    return {
      animation: false,
      aria: { enabled: true, decal: { show: false } },
      grid: { left: 18, right: 24, top: 72, bottom: 45, containLabel: true },
      legend: { type: 'scroll', top: 8, left: 8, right: 8 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line' },
        valueFormatter: (value) => {
          const metricValue = Array.isArray(value) ? value[1] : value;
          return typeof metricValue === 'number' ? this.formatCurrency(metricValue) : String(metricValue);
        },
      },
      xAxis: {
        type: 'value',
        min: 1,
        max: daysInTargetMonth,
        minInterval: 1,
        axisLabel: { formatter: (value: number) => Number.isInteger(value) ? String(value) : '' },
      },
      yAxis: {
        type: 'value',
        name: 'Importe acumulado',
        axisLabel: { formatter: (value: number) => this.formatCompactCurrency(value) },
      },
      series: lineSeries,
    };
  }

  private getHistoricalLineType(
    index: number,
    total: number,
  ): 'dotted' | 'dashed' | 'solid' {
    if (total <= 1 || index === total - 1) {
      return 'solid';
    }

    if (index === 0) {
      return 'dotted';
    }

    return 'dashed';
  }

  private buildAnnualRows(response: TrackBranchForecastDetailResponse): BranchDetailAnnualRow[] {
    const historicalRows = response.series.historical_years.items.map((item) => this.toHistoricalRow(item));
    const currentYear = new Date(`${response.metadata.track_date}T00:00:00`).getFullYear();

    return [
      ...historicalRows,
      {
        yearLabel: `${currentYear} · actual`,
        statusLabel: 'Al corte',
        available: true,
        mtdLabel: this.formatCurrency(response.summary.real_base_mtd),
        closeLabel: response.series.comparable_base_projection.projected_close === null
          ? 'No disponible'
          : `${this.formatCurrency(response.series.comparable_base_projection.projected_close)} · proyección`,
        positiveDaysLabel: 'No aplica',
        snapshotDateLabel: this.formatDate(response.metadata.track_date),
        availabilityLabel: 'Base actual disponible',
        isCurrent: true,
      },
    ];
  }

  private toHistoricalRow(item: TrackBranchForecastDetailHistoricalYearItem): BranchDetailAnnualRow {
    const available = item.status === 'available';
    return {
      yearLabel: String(item.year),
      statusLabel: this.getHistoricalYearStatusLabel(item.status),
      available,
      mtdLabel: available ? this.formatCurrency(item.mtd_at_cutoff) : 'No disponible',
      closeLabel: available ? this.formatCurrency(item.full_month_total) : 'No disponible',
      positiveDaysLabel: available ? String(item.days_with_positive_sale_row) : 'No disponible',
      snapshotDateLabel: item.snapshot_business_date ? this.formatDate(item.snapshot_business_date) : 'No disponible',
      availabilityLabel: available ? 'Disponible' : 'Sin información comparable',
      isCurrent: false,
    };
  }

  private buildQualityItems(response: TrackBranchForecastDetailResponse): BranchDetailTraceItem[] {
    const forecastQuality = response.data_quality.forecast;
    const comparability = response.data_quality.source_comparability;
    return [
      { label: 'Calidad del forecast', value: forecastQuality.goal_status_message || this.formatTechnicalLabel(forecastQuality.goal_status) },
      { label: 'Cobertura histórica', value: `${forecastQuality.history_coverage.months_count} meses · confianza ${this.formatTechnicalLabel(forecastQuality.history_coverage.confidence)}` },
      { label: 'Base histórica', value: this.formatTechnicalLabel(comparability.historical_basis) },
      { label: 'Base actual comparable', value: this.formatTechnicalLabel(comparability.current_comparable_basis) },
      { label: 'Base ejecutiva total', value: this.formatTechnicalLabel(comparability.executive_total_basis) },
      { label: 'Agregadoras', value: 'No forman parte de las series históricas comparables.' },
      { label: 'Puntos Track al corte', value: `${response.data_quality.current_series.points_count} de ${response.data_quality.current_series.expected_days_to_cutoff}` },
      { label: 'Fechas Track faltantes', value: response.data_quality.current_series.missing_dates.length ? response.data_quality.current_series.missing_dates.map((date) => this.formatDate(date)).join(', ') : 'Ninguna' },
      { label: 'Calidad de proyección base', value: response.series.comparable_base_projection.quality_issue?.message || 'Sin incidencias reportadas.' },
    ];
  }

  private buildTraceItems(response: TrackBranchForecastDetailResponse): BranchDetailTraceItem[] {
    const current = response.series.current_track;
    const cutoff = current.points.length ? current.points[current.points.length - 1] : null;
    const projection = response.series.comparable_base_projection;
    return [
      { label: 'Version ID', value: String(response.metadata.resolved_version.id) },
      { label: 'Version type', value: cutoff ? this.formatTechnicalLabel(cutoff.version_type) : 'No disponible' },
      { label: 'Generation mode', value: this.formatTechnicalLabel(response.metadata.generation_mode) },
      { label: 'Selección del último punto', value: cutoff ? this.formatTechnicalLabel(cutoff.selection_reason) : 'No disponible' },
      { label: 'Serie Track actual', value: this.formatTechnicalLabel(current.source_basis) },
      { label: 'Años históricos', value: this.formatTechnicalLabel(response.series.historical_years.source_basis) },
      { label: 'Curva esperada', value: this.formatTechnicalLabel(response.series.historical_expected.source_basis) },
      { label: 'Trayectoria proyectada', value: this.formatTechnicalLabel(projection.metric_basis) },
      { label: 'Método de curva esperada', value: this.formatTechnicalLabel(response.series.historical_expected.method) },
      { label: 'Método de trayectoria', value: projection.path ? this.formatTechnicalLabel(projection.path.method) : 'No disponible' },
      { label: 'Método de proyección base', value: this.formatTechnicalLabel(projection.method) },
      { label: 'Fórmula de proyección base', value: projection.formula },
    ];
  }

  private toSummaryCard(
    label: string,
    value: number | null,
    support: string,
    emphasis: BranchDetailSummaryCard['emphasis'],
  ): BranchDetailSummaryCard {
    return {
      label,
      value: this.formatCurrency(value),
      support: value === null ? support : support,
      emphasis,
    };
  }

  private isCompleteResponse(response: TrackBranchForecastDetailResponse): boolean {
    return response?.status === 'ok'
      && Boolean(response.metadata?.sucursal_canon)
      && Boolean(response.summary)
      && Boolean(response.forecast_context)
      && Array.isArray(response.series?.current_track?.points)
      && Array.isArray(response.series?.historical_years?.items)
      && Array.isArray(response.series?.historical_expected?.points)
      && Boolean(response.series?.comparable_base_projection)
      && Array.isArray(response.data_quality?.warnings);
  }

  private isValidRequest(request: BranchDetailRequest): request is BranchDetailRequest & { generationMode: TrackGenerationMode } {
    return Boolean(request.sucursalCanon.trim())
      && /^\d{4}-\d{2}-\d{2}$/.test(request.trackDate)
      && (request.generationMode === 'manual_preview' || request.generationMode === 'official_closed_day');
  }

  private sameRequest(left: BranchDetailRequest, right: BranchDetailRequest): boolean {
    return left.sucursalCanon === right.sucursalCanon
      && left.trackDate === right.trackDate
      && left.generationMode === right.generationMode
      && left.cohort === right.cohort;
  }

  private parseCohort(value: string | null): TrackForecastCohortKey | null {
    return value === 'legacy_21' || value === 'new_gyms' || value === 'total_ultra' ? value : null;
  }

  private getErrorMessage(status: number): string {
    if (status === 400) return 'No fue posible interpretar los parámetros del detalle.';
    if (status === 403) return 'No tienes acceso a este detalle de Tendencias.';
    if (status === 404) return 'No se encontró información de forecast para esta sucursal y corte.';
    if (status === 500) return 'El detalle no pudo construirse por una inconsistencia de datos.';
    return 'No fue posible cargar el detalle de la sucursal.';
  }

  private getHistoricalYearStatusLabel(status: TrackBranchForecastDetailHistoricalYearStatus): string {
    if (status === 'available') return 'Disponible';
    if (status === 'no_canonical_snapshot') return 'Sin snapshot canónico';
    return 'Sin filas para la sucursal';
  }

  private getExpectedStatusLabel(status: TrackBranchForecastDetailResponse['series']['historical_expected']['status']): string {
    if (status === 'no_comparable_history') return 'sin histórico comparable';
    if (status === 'missing_expected_month_total') return 'sin total histórico esperado';
    return 'disponible';
  }

  private getProjectionStatusLabel(status: TrackBranchForecastDetailResponse['series']['comparable_base_projection']['status']): string {
    const labels: Record<typeof status, string> = {
      available: 'disponible',
      blocked_by_forecast_quality: 'bloqueada por calidad del forecast',
      missing_base_mtd: 'sin Base MTD',
      invalid_historical_progress: 'avance histórico no válido',
      projected_path_unavailable: 'trayectoria diaria no disponible',
    };
    return labels[status];
  }

  private formatCurrency(value: number | null): string {
    if (value === null) return 'No disponible';
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value);
  }

  private formatCompactCurrency(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value);
  }

  private formatDate(value: string): string {
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return 'No disponible';
    return new Intl.DateTimeFormat('es-MX', { day: '2-digit', month: 'short', year: 'numeric' }).format(date);
  }

  private formatMonth(value: string): string {
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return 'Mes';
    const month = new Intl.DateTimeFormat('es-MX', { month: 'long' }).format(date);
    return month.charAt(0).toUpperCase() + month.slice(1);
  }

  private formatBranchName(value: string): string {
    return value.replace(/_/g, ' ').replace(/\s+/g, ' ').trim() || 'Sucursal';
  }

  private formatTechnicalLabel(value: string): string {
    return value.replace(/_/g, ' ');
  }

  private daysInMonth(value: string): number {
    const [year, month] = value.split('-').map(Number);
    return year && month ? new Date(year, month, 0).getDate() : 31;
  }

  private resetPresentation(): void {
    this.chartOption = {};
    this.summaryCards = [];
    this.annualRows = [];
    this.qualityItems = [];
    this.traceItems = [];
    this.chartNotes = [];
    this.warningMessages = [];
    this.usedYearsLabel = 'No disponible';
    this.excludedYearsLabel = 'Ninguno';
  }
}
