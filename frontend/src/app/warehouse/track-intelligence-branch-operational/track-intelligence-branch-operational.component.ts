import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  HostListener,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { combineLatest, Subject, takeUntil } from 'rxjs';

import {
  TrackBranchOperationalActiveMembersProjection,
  TrackBranchOperationalBusinessRules,
  TrackBranchOperationalDetailResponse,
  TrackBranchOperationalHistoryPoint,
  TrackBranchOperationalLimitProjection,
  TrackBranchOperationalMetricChange,
  TrackBranchOperationalMetrics,
  TrackBranchOperationalSummary,
  TrackBranchOperationalTargetProjection,
  TrackForecastCenterCatalogBranch,
  TrackGenerationMode,
  TrackService,
} from '../../services/track.service';
import {
  TrackIntelligenceChartDetailComponent,
  TrackIntelligenceChartDetailContext,
  TrackIntelligenceChartDetailSeriesPoint,
} from './track-intelligence-chart-detail/track-intelligence-chart-detail.component';


type PriorityMetricKey =
  | 'clientes_nuevos'
  | 'reactivaciones'
  | 'bajas'
  | 'domiciliados';

type ChartMetricKey = PriorityMetricKey | 'socios_activos';

interface PriorityCardView {
  key: PriorityMetricKey;
  label: string;
  mainValue: string;
  progressValue: number;
  progressLabel: string;
  secondaryLabel: string | null;
  status: string;
  trend: string;
  trendStartDate: string | null;
  changeLabel: string;
}

interface DailyChangePointView {
  dayLabel: string;
  value: string;
}

interface ChangeCardView {
  key: PriorityMetricKey;
  label: string;
  todayDelta: string;
  todayDeltaRaw: string | null;
  lastSevenDays: DailyChangePointView[];
}

interface ChartMarker {
  x: number;
  y: number;
  label: string;
}

interface ChartAxisLabel {
  x: number;
  label: string;
}

interface ChartYAxisTick {
  y: number;
  label: string;
}

interface ChartView {
  key: ChartMetricKey;
  title: string;
  daysInMonth: number;
  actualPoints: string;
  benchmarkPoints: string;
  projectionPoints: string;
  actualSeries: TrackIntelligenceChartDetailSeriesPoint[];
  benchmarkSeries: TrackIntelligenceChartDetailSeriesPoint[];
  projectionSeries: TrackIntelligenceChartDetailSeriesPoint[];
  actualMarkers: ChartMarker[];
  benchmarkMarkers: ChartMarker[];
  projectionMarkers: ChartMarker[];
  axisLabels: ChartAxisLabel[];
  yAxisTicks: ChartYAxisTick[];
  benchmarkLabel: string | null;
  projectionHeadline: string;
  projectionBenchmark: string | null;
  projectionComparison: string | null;
  empty: boolean;
}

type OperationalProjection =
  | TrackBranchOperationalTargetProjection
  | TrackBranchOperationalLimitProjection
  | TrackBranchOperationalActiveMembersProjection;

interface OperationalSummaryRowView {
  label: string;
  value: string;
  emphasis?: boolean;
}

interface OperationalSummaryCardView {
  metricKey: string;
  label: string;
  severity: string;
  title: string;
  rows: OperationalSummaryRowView[];
}

interface BusinessRuleView {
  key: keyof TrackBranchOperationalBusinessRules;
  label: string;
  value: string;
}


@Component({
  selector: 'app-track-intelligence-branch-operational',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    TrackIntelligenceChartDetailComponent,
  ],
  templateUrl: './track-intelligence-branch-operational.component.html',
  styleUrls: ['./track-intelligence-branch-operational.component.css'],
})
export class TrackIntelligenceBranchOperationalComponent
  implements OnInit, OnDestroy {
  data: TrackBranchOperationalDetailResponse | null = null;
  branchOptions: TrackForecastCenterCatalogBranch[] = [];
  priorityCards: PriorityCardView[] = [];
  changeCards: ChangeCardView[] = [];
  charts: ChartView[] = [];
  selectedChart: ChartView | null = null;
  selectedChartContext: TrackIntelligenceChartDetailContext | null = null;
  operationalSummaryCards: OperationalSummaryCardView[] = [];
  businessRuleViews: BusinessRuleView[] = [];
  selectedBranch = '';
  selectedTrackDate = '';
  generationMode: TrackGenerationMode = 'manual_preview';
  maxTrackDate = '';
  isLoading = false;
  isRulesModalOpen = false;
  errorMessage = '';
  catalogWarning = '';

  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly trackService: TrackService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.maxTrackDate = this.getTijuanaTodayIsoDate();
    this.loadBranchOptions();

    combineLatest([
      this.route.paramMap,
      this.route.queryParamMap,
    ])
      .pipe(takeUntil(this.destroy$))
      .subscribe(([params, queryParams]) => {
        this.selectedBranch = String(
          params.get('sucursalCanon') || '',
        ).trim().toUpperCase();
        this.selectedTrackDate = (
          queryParams.get('track_date') || this.maxTrackDate
        );
        this.generationMode = this.normalizeGenerationMode(
          queryParams.get('generation_mode'),
        );
        this.loadDetail();
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  @HostListener('document:keydown.escape')
  closeRulesOnEscape(): void {
    this.closeRulesModal();
  }

  loadDetail(): void {
    if (!this.selectedBranch || !this.selectedTrackDate) {
      this.errorMessage = 'La sucursal y la fecha de corte son requeridas.';
      return;
    }
    if (this.selectedTrackDate > this.maxTrackDate) {
      this.errorMessage = 'No se puede consultar una fecha futura.';
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';
    this.data = null;
    this.priorityCards = [];
    this.changeCards = [];
    this.charts = [];
    this.clearChartSelection();
    this.operationalSummaryCards = [];

    this.trackService
      .getBranchOperationalDetail(
        this.selectedBranch,
        this.selectedTrackDate,
        this.generationMode,
      )
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.data = response;
          this.priorityCards = this.buildPriorityCards(response);
          this.changeCards = this.buildChangeCards(response);
          this.charts = this.buildCharts(response);
          this.operationalSummaryCards = (
            this.buildOperationalSummaryCards(response)
          );
          this.businessRuleViews = this.buildBusinessRuleViews(
            response.business_rules,
          );
          this.isLoading = false;
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage = (
            error.error?.error ||
            'No se pudo cargar el Deep Dive operacional.'
          );
          this.isLoading = false;
        },
      });
  }

  applyFilters(): void {
    if (!this.selectedBranch || !this.selectedTrackDate) {
      this.errorMessage = 'Selecciona una sucursal y una fecha válidas.';
      return;
    }
    if (this.selectedTrackDate > this.maxTrackDate) {
      this.errorMessage = 'No se puede consultar una fecha futura.';
      return;
    }

    this.router.navigate(
      [
        '/warehouse/track-intelligence/branch',
        this.selectedBranch,
      ],
      {
        queryParams: {
          track_date: this.selectedTrackDate,
          generation_mode: this.generationMode,
        },
      },
    );
  }

  goBackToRegional(): void {
    this.router.navigate(
      ['/warehouse/track-intelligence/regional-operational'],
      {
        queryParams: {
          track_date: this.selectedTrackDate,
          generation_mode: this.generationMode,
          region_key: this.data?.identity.region_key || null,
        },
      },
    );
  }

  openRulesModal(): void {
    this.isRulesModalOpen = true;
  }

  closeRulesModal(): void {
    this.isRulesModalOpen = false;
  }

  stopModalClose(event: MouseEvent): void {
    event.stopPropagation();
  }

  branchOptionExists(): boolean {
    return this.branchOptions.some(
      (branch) => branch.sucursal_canon === this.selectedBranch,
    );
  }

  getCutLabel(): string {
    return this.data?.change_vs_previous.is_consecutive_previous_date
      ? 'Ayer → hoy'
      : 'Último corte → hoy';
  }

  getGenerationModeLabel(): string {
    return this.generationMode === 'official_closed_day'
      ? 'Día cerrado oficial'
      : 'Preview operativo';
  }

  getStatusLabel(status: string | null | undefined): string {
    const labels: Record<string, string> = {
      ADELANTADO: 'Adelantado',
      EN_RITMO: 'En ritmo',
      DEBAJO_RITMO: 'Debajo del ritmo',
      META_SUPERADA: 'Meta superada',
      LIMITE_EXCEDIDO: 'Límite excedido',
      CERCA_LIMITE: 'Cerca del límite',
      CONSUMO_ALTO: 'Consumo alto',
      DENTRO_LIMITE: 'Dentro del límite',
      SIN_META: 'Sin meta',
      DATOS_INSUFICIENTES: 'Datos insuficientes',
      AVAILABLE: 'Disponible',
    };
    return labels[status || ''] || status || '—';
  }

  getTrendLabel(trend: string | null | undefined): string {
    const labels: Record<string, string> = {
      IMPROVING: 'Mejorando',
      DETERIORATING: 'Deteriorándose',
      STABLE: 'Estable',
      INSUFFICIENT_DATA: 'Tendencia insuficiente',
    };
    return labels[trend || ''] || trend || 'Tendencia insuficiente';
  }

  getDirectionIcon(direction: string): string {
    if (direction === 'IMPROVING') {
      return '↑';
    }
    if (direction === 'WORSENING') {
      return '↓';
    }
    return '→';
  }

  getSemanticClass(value: string | null | undefined): string {
    const normalized = String(value || '').toLowerCase();
    if (
      ['critical', 'deteriorating', 'worsening', 'limite_excedido'].includes(
        normalized,
      )
    ) {
      return 'semantic semantic--critical';
    }
    if (
      [
        'warning',
        'attention_required',
        'debajo_ritmo',
        'consumo_alto',
        'cerca_limite',
      ].includes(normalized)
    ) {
      return 'semantic semantic--warning';
    }
    if (
      ['success', 'healthy', 'improving', 'adelantado', 'meta_superada'].includes(
        normalized,
      )
    ) {
      return 'semantic semantic--success';
    }
    return 'semantic semantic--neutral';
  }

  getMonthlyGoalCardClass(
    metricKey: 'ingreso' | 'usuarios' | 'tienda',
    metrics: TrackBranchOperationalMetrics,
  ): string {
    let compliance: number | null = null;

    if (metricKey === 'ingreso') {
      compliance = this.toNumber(metrics.ingreso.compliance_pct);
    } else if (metricKey === 'tienda') {
      compliance = this.toNumber(metrics.tienda.compliance_pct);
    } else {
      compliance = this.toNumber(metrics.usuarios.compliance_pct);
    }

    if (compliance === null || compliance < 80) {
      return 'monthly-goal-card';
    }

    if (compliance < 90) {
      return 'monthly-goal-card monthly-goal-card--orange';
    }

    if (compliance < 100) {
      return 'monthly-goal-card monthly-goal-card--yellow';
    }

    return 'monthly-goal-card monthly-goal-card--green';
  }

  formatNumber(
    value: string | number | null | undefined,
    decimalPlaces?: number,
  ): string {
    const numeric = this.toNumber(value);

    if (numeric === null) {
      return '—';
    }

    if (decimalPlaces !== undefined) {
      return numeric.toLocaleString('es-MX', {
        minimumFractionDigits: decimalPlaces,
        maximumFractionDigits: decimalPlaces,
      });
    }

    return numeric.toLocaleString('es-MX', {
      maximumFractionDigits: 1,
    });
  }

  formatMoney(value: string | number | null | undefined): string {
    const numeric = this.toNumber(value);
    return numeric === null
      ? '—'
      : numeric.toLocaleString('es-MX', {
        style: 'currency',
        currency: 'MXN',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      });
  }

  formatPercent(value: string | number | null | undefined): string {
    const numeric = this.toNumber(value);
    return numeric === null ? '—' : `${numeric.toFixed(1)}%`;
  }

  formatSigned(
    value: string | number | null | undefined,
    suffix = '',
  ): string {
    const numeric = this.toNumber(value);
    if (numeric === null) {
      return '—';
    }
    return `${numeric > 0 ? '+' : ''}${numeric.toFixed(1)}${suffix}`;
  }

  formatDate(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }

  selectChart(chart: ChartView): void {
    if (this.selectedChart?.key === chart.key) {
      this.clearChartSelection();
      return;
    }

    this.selectedChart = chart;
    this.selectedChartContext = this.buildChartDetailContext(chart);
  }

  clearChartSelection(): void {
    this.selectedChart = null;
    this.selectedChartContext = null;
  }

  isChartSelected(chart: ChartView): boolean {
    return this.selectedChart?.key === chart.key;
  }

  formatCodeLabel(value: string): string {
    return value.split('_').join(' ');
  }

  private loadBranchOptions(): void {
    this.trackService
      .getForecastCenterCatalogs()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.branchOptions = response.branches;
          this.catalogWarning = '';
        },
        error: () => {
          this.catalogWarning = (
            'No se pudo cargar el catálogo autorizado; la sucursal actual ' +
            'permanece disponible.'
          );
        },
      });
  }

  private buildPriorityCards(
    response: TrackBranchOperationalDetailResponse,
  ): PriorityCardView[] {
    const metrics = response.current.metrics;
    if (metrics === null) {
      return [];
    }

    return [
      this.buildPaceCard(
        'clientes_nuevos',
        'Clientes nuevos',
        metrics,
        response.change_vs_previous.metrics.clientes_nuevos,
      ),
      this.buildPaceCard(
        'reactivaciones',
        'Reactivaciones',
        metrics,
        response.change_vs_previous.metrics.reactivaciones,
      ),
      this.buildBajasCard(
        metrics,
        response.change_vs_previous.metrics.bajas,
      ),
      this.buildPaceCard(
        'domiciliados',
        'Domiciliados',
        metrics,
        response.change_vs_previous.metrics.domiciliados,
      ),
    ];
  }

  private buildPaceCard(
    key: Exclude<PriorityMetricKey, 'bajas'>,
    label: string,
    metrics: TrackBranchOperationalMetrics,
    change: TrackBranchOperationalMetricChange | undefined,
  ): PriorityCardView {
    const metric = metrics[key];
    return {
      key,
      label,
      mainValue: (
        `${this.formatNumber(metric.actual_mtd)} / ` +
        `${this.formatNumber(metric.expected_mtd)} esperado`
      ),
      progressValue: this.clampPercent(metric.pace_pct),
      progressLabel: `${this.formatPercent(metric.pace_pct)} del ritmo esperado`,
      secondaryLabel: `${this.formatPercent(metric.actual_progress_pct)} de la meta mensual`,
      status: metric.status,
      trend: metric.trend || 'INSUFFICIENT_DATA',
      trendStartDate: metric.trend_start_date || null,
      changeLabel: this.buildChangeLabel(change),
    };
  }

  private buildBajasCard(
    metrics: TrackBranchOperationalMetrics,
    change: TrackBranchOperationalMetricChange | undefined,
  ): PriorityCardView {
    const metric = metrics.bajas;
    return {
      key: 'bajas',
      label: 'Bajas',
      mainValue: (
        `${this.formatNumber(metric.actual_mtd)} / límite ` +
        `${this.formatNumber(metric.monthly_limit)}`
      ),
      progressValue: this.clampPercent(metric.limit_usage_pct),
      progressLabel: `${this.formatPercent(metric.limit_usage_pct)} del límite consumido`,
      secondaryLabel: (
        metric.status === 'LIMITE_EXCEDIDO'
          ? `Exceso: ${this.formatNumber(metric.excess_units)}`
          : `Margen: ${this.formatNumber(metric.remaining_before_limit)}`
      ),
      status: metric.status,
      trend: metric.trend || 'INSUFFICIENT_DATA',
      trendStartDate: metric.trend_start_date || null,
      changeLabel: this.buildChangeLabel(change, true),
    };
  }

  private buildChangeLabel(
    change: TrackBranchOperationalMetricChange | undefined,
    useUnits = false,
  ): string {
    if (!change) {
      return 'Sin corte anterior comparable';
    }
    const value = useUnits
      ? this.formatSigned(change.actual_delta)
      : this.formatSigned(change.comparison_delta_pp, ' pp');
    return `${this.getDirectionIcon(change.direction)} ${value} desde el último corte`;
  }

  private buildChangeCards(
    response: TrackBranchOperationalDetailResponse,
  ): ChangeCardView[] {
    const labels: Record<PriorityMetricKey, string> = {
      clientes_nuevos: 'Clientes nuevos',
      reactivaciones: 'Reactivaciones',
      bajas: 'Bajas',
      domiciliados: 'Domiciliados',
    };
    const keys: PriorityMetricKey[] = [
      'clientes_nuevos',
      'reactivaciones',
      'bajas',
      'domiciliados',
    ];

    const pointsByDate = new Map(
      response.history.map((point) => [point.track_date, point]),
    );

    return keys.map((key) => {
      const currentPoint = pointsByDate.get(response.cutoff.track_date);
      const todayDeltaRaw = currentPoint
        ? this.getValidDailyDelta(currentPoint, key)
        : null;

      return {
        key,
        label: labels[key],
        todayDelta: this.formatSignedDailyUnit(todayDeltaRaw),
        todayDeltaRaw,
        lastSevenDays: this.buildLastSevenDays(
          response,
          key,
          pointsByDate,
        ),
      };
    });
  }

  private buildLastSevenDays(
    response: TrackBranchOperationalDetailResponse,
    key: PriorityMetricKey,
    pointsByDate: Map<string, TrackBranchOperationalHistoryPoint>,
  ): DailyChangePointView[] {
    const [year, month, day] = response.cutoff.track_date
      .split('-')
      .map(Number);

    const cutoff = new Date(Date.UTC(year, month - 1, day));
    const values: DailyChangePointView[] = [];

    for (let offset = 6; offset >= 0; offset -= 1) {
      const currentDate = new Date(cutoff);
      currentDate.setUTCDate(cutoff.getUTCDate() - offset);

      const isoDate = currentDate.toISOString().slice(0, 10);
      const point = pointsByDate.get(isoDate);

      values.push({
        dayLabel: this.getWeekdayShortLabel(currentDate),
        value: point
          ? this.formatDailyUnit(
              this.getValidDailyDelta(point, key),
            )
          : '—',
      });
    }

    return values;
  }

  private getWeekdayShortLabel(date: Date): string {
    const labels = ['D', 'L', 'M', 'm', 'J', 'V', 'S'];
    return labels[date.getUTCDay()];
  }

  private getValidDailyDelta(
    point: TrackBranchOperationalHistoryPoint,
    key: PriorityMetricKey,
  ): string | null {
    const metric = point.metrics[key];
    const dayOfMonth = Number(point.track_date.slice(-2));

    if (
      dayOfMonth > 1 &&
      !point.is_consecutive_previous_date
    ) {
      return null;
    }

    return metric.daily_delta;
  }

  private formatSignedDailyUnit(
    value: string | number | null | undefined,
  ): string {
    const numeric = this.toNumber(value);

    if (numeric === null) {
      return '—';
    }

    const rounded = Math.round(numeric);

    if (rounded > 0) {
      return `+${this.formatNumber(rounded)}`;
    }

    return this.formatNumber(rounded);
  }

  private formatDailyUnit(
    value: string | number | null | undefined,
  ): string {
    const numeric = this.toNumber(value);

    if (numeric === null) {
      return '—';
    }

    if (numeric === 0) {
      return '0';
    }

    return this.formatNumber(numeric);
  }

  getDailyDeltaClass(
    key: PriorityMetricKey,
    value: string | null,
  ): string {
    if (key !== 'bajas') {
      return 'change-today';
    }

    const numeric = this.toNumber(value);

    if (numeric === null || numeric === 0) {
      return 'change-today';
    }

    return numeric > 0
      ? 'change-today change-today--critical'
      : 'change-today change-today--success';
  }

  private buildCharts(
    response: TrackBranchOperationalDetailResponse,
  ): ChartView[] {
    const metrics = response.current.metrics;

    return [
      this.buildChart(
        response.history,
        response.cutoff.day_of_month,
        response.cutoff.days_in_month,
        response.cutoff.target_month,
        'clientes_nuevos',
        'Clientes nuevos: real, esperado y proyección',
        metrics?.clientes_nuevos.projection,
      ),
      this.buildChart(
        response.history,
        response.cutoff.day_of_month,
        response.cutoff.days_in_month,
        response.cutoff.target_month,
        'reactivaciones',
        'Reactivaciones: real, esperado y proyección',
        metrics?.reactivaciones.projection,
      ),
      this.buildChart(
        response.history,
        response.cutoff.day_of_month,
        response.cutoff.days_in_month,
        response.cutoff.target_month,
        'domiciliados',
        'Domiciliados: real, esperado y proyección',
        metrics?.domiciliados.projection,
      ),
      this.buildChart(
        response.history,
        response.cutoff.day_of_month,
        response.cutoff.days_in_month,
        response.cutoff.target_month,
        'bajas',
        'Bajas: real, límite y proyección',
        metrics?.bajas.projection,
      ),
      this.buildChart(
        response.history,
        response.cutoff.day_of_month,
        response.cutoff.days_in_month,
        response.cutoff.target_month,
        'socios_activos',
        'Socios activos: real y proyección',
        metrics?.socios_activos.projection,
      ),
    ];
  }

  private buildChart(
    history: TrackBranchOperationalHistoryPoint[],
    cutoffDay: number,
    daysInMonth: number,
    targetMonth: string,
    metricKey: ChartMetricKey,
    title: string,
    projection: OperationalProjection | undefined,
  ): ChartView {
    const rawPoints = history.flatMap((point) => {
      const metric = point.metrics[metricKey];
      const actual = this.toNumber(metric.actual_mtd);
      let benchmark: number | null;
      let pace: string | null;

      if (metricKey === 'bajas') {
        benchmark = this.toNumber(point.metrics.bajas.monthly_limit);
        pace = point.metrics.bajas.limit_usage_pct;
      } else if (metricKey === 'socios_activos') {
        benchmark = null;
        pace = null;
      } else {
        const paceMetric = point.metrics[metricKey];
        benchmark = this.toNumber(paceMetric.expected_mtd);
        pace = paceMetric.pace_pct;
      }

      if (actual === null && benchmark === null) {
        return [];
      }
      return [{
        day: Number(point.track_date.slice(-2)),
        date: point.track_date,
        actual,
        benchmark,
        dailyDelta: metric.daily_delta,
        pace,
      }];
    });
    const projectedRawPoints = projection?.status === 'available'
      ? projection.projected_points.flatMap((point) => {
          const value = this.toNumber(point.projected_mtd);
          return value === null ? [] : [{
            day: Number(point.track_date.slice(-2)),
            date: point.track_date,
            value,
          }];
        })
      : [];
    const visibleValues = [
      ...rawPoints.flatMap((point) => [
        point.actual,
        point.benchmark,
      ]),
      ...projectedRawPoints.map((point) => point.value),
    ].filter((value): value is number => value !== null);
    const yAxisScale = this.buildYAxisScale(visibleValues);
    const xForDay = (day: number): number => (
      14 + ((day - 1) / Math.max(daysInMonth - 1, 1)) * 82
    );
    const yForValue = (value: number): number => (
      31 - (
        (value - yAxisScale.minimum) /
        (yAxisScale.maximum - yAxisScale.minimum)
      ) * 27
    );
    const yAxisTicks = yAxisScale.ticks.map((value) => ({
      y: yForValue(value),
      label: this.formatNumber(value),
    }));
    const actualSeries = rawPoints.flatMap((point) => {
      if (point.actual === null) {
        return [];
      }
      return [{
        day: point.day,
        date: point.date,
        value: point.actual,
        label: (
          `${this.formatDate(point.date)} · Real ${this.formatNumber(point.actual)} · ` +
          `Delta ${this.formatSigned(point.dailyDelta)}` +
          (
            metricKey === 'socios_activos'
              ? ''
              : (
                  ` · ${metricKey === 'bajas' ? 'Consumo' : 'Ritmo'} ` +
                  this.formatPercent(point.pace)
                )
          )
        ),
      }];
    });
    const actualMarkers = actualSeries.map((point) => ({
      x: xForDay(point.day),
      y: yForValue(point.value),
      label: point.label,
    }));
    const actualPoints = actualMarkers
      .map((point) => `${point.x},${point.y}`)
      .join(' ');
    const benchmarkRawPoints = rawPoints
      .flatMap((point) => point.benchmark === null ? [] : [{
        day: point.day,
        date: point.date,
        value: point.benchmark,
      }]);
    if (
      metricKey === 'bajas' &&
      benchmarkRawPoints.length > 0 &&
      benchmarkRawPoints[benchmarkRawPoints.length - 1].day < daysInMonth
    ) {
      benchmarkRawPoints.push({
        day: daysInMonth,
        date: `${targetMonth}-${String(daysInMonth).padStart(2, '0')}`,
        value: benchmarkRawPoints[benchmarkRawPoints.length - 1].value,
      });
    }
    const benchmarkSeries = benchmarkRawPoints
      .map((point) => ({
        day: point.day,
        date: point.date,
        value: point.value,
        label: (
          `${this.formatDate(point.date)} · ${
            metricKey === 'bajas' ? 'Límite mensual' : 'Esperado'
          } ${this.formatNumber(point.value)}`
        ),
      }));
    const benchmarkMarkers = benchmarkSeries.map((point) => ({
      x: xForDay(point.day),
      y: yForValue(point.value),
      label: point.label,
    }));
    const benchmarkPoints = benchmarkMarkers
      .map((point) => `${point.x},${point.y}`)
      .join(' ');
    const projectionSeries = projectedRawPoints.map((point) => ({
      day: point.day,
      date: point.date,
      value: point.value,
      label: (
        `${this.formatDate(point.date)} · Proyección ` +
        this.formatNumber(point.value)
      ),
    }));
    const projectionMarkers = projectionSeries.map((point) => ({
      x: xForDay(point.day),
      y: yForValue(point.value),
      label: point.label,
    }));
    const projectionPoints = projectionMarkers
      .map((point) => `${point.x},${point.y}`)
      .join(' ');

    const baseReferenceDays = [1, 5, 10, 15, 20, 25, 30]
      .filter(
        (day) => (
          day < daysInMonth &&
          !(daysInMonth === 31 && day === 30)
        ),
      );

    const referenceDays = Array.from(
      new Set([...baseReferenceDays, daysInMonth]),
    );

    const axisLabels: ChartAxisLabel[] = referenceDays
      .sort((left, right) => left - right)
      .map((day) => ({
        x: xForDay(day),
        label: String(day),
      }));

    const projectionSummary = this.buildProjectionSummary(
      metricKey,
      projection,
      cutoffDay,
      daysInMonth,
    );

    return {
      key: metricKey,
      title,
      daysInMonth,
      actualPoints,
      benchmarkPoints,
      projectionPoints,
      actualSeries,
      benchmarkSeries,
      projectionSeries,
      actualMarkers,
      benchmarkMarkers,
      projectionMarkers,
      axisLabels,
      yAxisTicks,
      benchmarkLabel: metricKey === 'socios_activos'
        ? null
        : metricKey === 'bajas'
          ? 'Límite mensual'
          : 'Esperado',
      ...projectionSummary,
      empty: actualMarkers.length === 0,
    };
  }

  private buildChartDetailContext(
    chart: ChartView,
  ): TrackIntelligenceChartDetailContext | null {
    const response = this.data;
    const metrics = response?.current.metrics;

    if (!response || !metrics) {
      return null;
    }

    const versionParts = [
      response.cutoff.track_daily_version_id !== null
        ? `#${response.cutoff.track_daily_version_id}`
        : null,
      response.cutoff.version_type
        ? this.formatCodeLabel(response.cutoff.version_type)
        : null,
    ].filter((value): value is string => Boolean(value));

    if (chart.key === 'socios_activos') {
      const metric = metrics.socios_activos;
      const projection = metric.projection;
      const missingComponents = projection?.missing_components || [];

      return {
        branchLabel: response.identity.sucursal_label,
        metricLabel: 'Socios activos',
        cutoffLabel: this.formatDate(response.cutoff.track_date),
        targetMonthLabel: this.formatTargetMonth(response.cutoff.target_month),
        generationLabel: this.getGenerationModeLabel(),
        versionLabel: versionParts.join(' · ') || 'Sin versión efectiva',
        kpis: [
          {
            label: 'Real observado',
            value: this.formatNumber(metric.actual_mtd),
            emphasis: true,
          },
          {
            label: 'Inicio observado',
            value: metric.start_month === null
              ? 'Dato no disponible'
              : this.formatNumber(metric.start_month),
          },
          {
            label: 'Cambio vs inicio observado',
            value: metric.change_from_start === null
              ? 'Dato no disponible'
              : this.formatSigned(metric.change_from_start),
          },
          {
            label: 'Proyección de cierre',
            value: this.formatNumber(projection?.projected_close),
            emphasis: true,
          },
          {
            label: 'Estado de proyección',
            value: projection?.status === 'available'
              ? 'Disponible'
              : 'Datos insuficientes',
          },
          {
            label: 'Componentes faltantes',
            value: missingComponents.length
              ? missingComponents.map((value) => this.formatCodeLabel(value)).join(', ')
              : 'Ninguno',
          },
        ],
      };
    }

    if (chart.key === 'bajas') {
      const metric = metrics.bajas;
      const projection = metric.projection;

      return {
        branchLabel: response.identity.sucursal_label,
        metricLabel: 'Bajas',
        cutoffLabel: this.formatDate(response.cutoff.track_date),
        targetMonthLabel: this.formatTargetMonth(response.cutoff.target_month),
        generationLabel: this.getGenerationModeLabel(),
        versionLabel: versionParts.join(' · ') || 'Sin versión efectiva',
        kpis: [
          {
            label: 'Bajas actuales',
            value: this.formatNumber(metric.actual_mtd),
            emphasis: true,
          },
          {
            label: 'Límite mensual',
            value: this.formatNumber(metric.monthly_limit),
          },
          {
            label: 'Consumo del límite',
            value: this.formatPercent(metric.limit_usage_pct),
          },
          {
            label: 'Proyección de cierre',
            value: this.formatNumber(projection?.projected_close),
            emphasis: true,
          },
          {
            label: 'Exceso proyectado',
            value: this.formatNumber(projection?.projected_excess_units),
          },
          {
            label: 'Margen proyectado',
            value: this.formatNumber(projection?.projected_remaining_margin),
          },
        ],
      };
    }

    const metric = metrics[chart.key];
    const projection = metric.projection;
    const projectedGap = this.toNumber(projection?.projected_gap_units);
    const metricLabels: Record<Exclude<PriorityMetricKey, 'bajas'>, string> = {
      clientes_nuevos: 'Clientes nuevos',
      reactivaciones: 'Reactivaciones',
      domiciliados: 'Domiciliados',
    };

    return {
      branchLabel: response.identity.sucursal_label,
      metricLabel: metricLabels[chart.key],
      cutoffLabel: this.formatDate(response.cutoff.track_date),
      targetMonthLabel: this.formatTargetMonth(response.cutoff.target_month),
      generationLabel: this.getGenerationModeLabel(),
      versionLabel: versionParts.join(' · ') || 'Sin versión efectiva',
      kpis: [
        {
          label: 'Real al corte',
          value: this.formatNumber(metric.actual_mtd),
          emphasis: true,
        },
        {
          label: 'Esperado al corte',
          value: this.formatNumber(metric.expected_mtd),
        },
        {
          label: 'Ritmo al corte',
          value: this.formatPercent(metric.pace_pct),
        },
        {
          label: 'Proyección de cierre',
          value: this.formatNumber(projection?.projected_close),
          emphasis: true,
        },
        {
          label: 'Meta mensual',
          value: this.formatNumber(metric.monthly_target),
        },
        {
          label: 'Brecha proyectada',
          value: (
            projectedGap === null
              ? '—'
              : `${projectedGap > 0 ? '+' : ''}${this.formatNumber(projectedGap)}`
          ),
        },
      ],
    };
  }

  private formatTargetMonth(value: string): string {
    const [year, month] = value.split('-').map(Number);

    if (!year || !month) {
      return value || '—';
    }

    return new Intl.DateTimeFormat('es-MX', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(Date.UTC(year, month - 1, 1)));
  }

  private buildYAxisScale(values: number[]): {
    minimum: number;
    maximum: number;
    ticks: number[];
  } {
    const finiteValues = values.filter((value) => Number.isFinite(value));
    const dataMinimum = Math.min(0, ...finiteValues);
    const dataMaximum = Math.max(0, ...finiteValues);
    const dataRange = Math.max(1, dataMaximum - dataMinimum);
    const step = this.resolveNiceTickStep(dataRange / 4);
    const minimum = Math.floor(dataMinimum / step) * step;
    let maximum = Math.ceil(dataMaximum / step) * step;

    if (maximum === minimum) {
      maximum = minimum + step;
    }

    const tickCount = Math.round((maximum - minimum) / step);
    const ticks = Array.from(
      { length: tickCount + 1 },
      (_, index) => minimum + step * index,
    );

    return { minimum, maximum, ticks };
  }

  private resolveNiceTickStep(roughStep: number): number {
    if (!Number.isFinite(roughStep) || roughStep <= 0) {
      return 1;
    }

    const magnitude = 10 ** Math.floor(Math.log10(roughStep));
    const normalized = roughStep / magnitude;
    let multiplier: number;

    if (normalized <= 1) {
      multiplier = 1;
    } else if (normalized <= 2) {
      multiplier = 2;
    } else if (normalized <= 2.5) {
      multiplier = 2.5;
    } else if (normalized <= 5) {
      multiplier = 5;
    } else {
      multiplier = 10;
    }

    return multiplier * magnitude;
  }

  private buildProjectionSummary(
    metricKey: ChartMetricKey,
    projection: OperationalProjection | undefined,
    cutoffDay: number,
    daysInMonth: number,
  ): Pick<
    ChartView,
    'projectionHeadline' | 'projectionBenchmark' | 'projectionComparison'
  > {
    if (!projection || projection.status !== 'available') {
      return {
        projectionHeadline: metricKey === 'socios_activos'
          ? 'Proyección: datos insuficientes'
          : 'Proyección: historia insuficiente',
        projectionBenchmark: null,
        projectionComparison: null,
      };
    }

    const metrics = this.data?.current.metrics;
    const isObservedClose = cutoffDay === daysInMonth;
    const headlinePrefix = isObservedClose
      ? 'Cierre observado'
      : 'Proyección cierre';

    const comparisonSuffix = isObservedClose
      ? 'observado'
      : 'proyectado';

    if (metricKey === 'socios_activos') {
      return {
        projectionHeadline: (
          `${headlinePrefix}: ${this.formatNumber(projection.projected_close)}`
        ),
        projectionBenchmark: null,
        projectionComparison: null,
      };
    }

    if (metricKey === 'bajas') {
      const limitProjection = projection as TrackBranchOperationalLimitProjection;
      const limit = metrics?.bajas.monthly_limit;
      const excess = this.toNumber(limitProjection.projected_excess_units);
      return {
        projectionHeadline: (
          `${headlinePrefix}: ${this.formatNumber(projection.projected_close)}`
        ),
        projectionBenchmark: limit === null || limit === undefined
          ? 'Límite: —'
          : (
              `Límite: ${this.formatNumber(limit)} · ` +
              `${this.formatPercent(limitProjection.projected_limit_usage_pct)}`
            ),
        projectionComparison: excess !== null && excess > 0
          ? `Exceso ${comparisonSuffix}: +${this.formatNumber(excess)}`
          : (
              `Margen ${comparisonSuffix}: ` +
              this.formatNumber(limitProjection.projected_remaining_margin)
            ),
      };
    }

    const targetProjection = projection as TrackBranchOperationalTargetProjection;
    const target = metrics?.[metricKey].monthly_target;
    const gap = this.toNumber(targetProjection.projected_gap_units);
    return {
      projectionHeadline: (
        `${headlinePrefix}: ${this.formatNumber(projection.projected_close)}`
      ),
      projectionBenchmark: target === null || target === undefined
        ? 'Meta: —'
        : (
            `Meta: ${this.formatNumber(target)} · ` +
            `${this.formatPercent(targetProjection.projected_compliance_pct)}`
          ),
      projectionComparison: gap !== null && gap > 0
        ? `Superávit ${comparisonSuffix}: +${this.formatNumber(gap)}`
        : `Brecha ${comparisonSuffix}: ${this.formatNumber(gap)}`,
    };
  }

  private buildOperationalSummaryCards(
    response: TrackBranchOperationalDetailResponse,
  ): OperationalSummaryCardView[] {
    return response.operational_summaries.map((summary) => ({
      metricKey: summary.metric_key,
      label: this.getOperationalSummaryLabel(summary.metric_key),
      severity: summary.severity,
      title: summary.title,
      rows: this.buildOperationalSummaryRows(summary),
    }));
  }

  private getOperationalSummaryLabel(metricKey: string): string {
    const labels: Record<string, string> = {
      clientes_nuevos: 'Clientes nuevos',
      reactivaciones: 'Reactivaciones',
      domiciliados: 'Domiciliados',
      bajas: 'Bajas',
      ingreso: 'Ingreso',
    };

    return labels[metricKey] || this.formatCodeLabel(metricKey);
  }

  private buildOperationalSummaryRows(
    summary: TrackBranchOperationalSummary,
  ): OperationalSummaryRowView[] {
    if (summary.metric_key === 'ingreso') {
      return this.buildIncomeOperationalSummaryRows(summary);
    }

    if (summary.metric_key === 'bajas') {
      return this.buildBajasOperationalSummaryRows(summary);
    }

    return this.buildPaceOperationalSummaryRows(summary);
  }

  private buildPaceOperationalSummaryRows(
    summary: TrackBranchOperationalSummary,
  ): OperationalSummaryRowView[] {
    const rows: OperationalSummaryRowView[] = [];
    const isClosedMonth = summary.remaining_days === 0;

    rows.push({
      label: 'Hoy',
      value: this.formatSignedDailyUnit(summary.today_delta),
    });

    if (summary.recent_daily_average !== null &&
        summary.recent_daily_average !== undefined) {
      rows.push({
        label: 'Promedio diario (7 días)',
        value: `${this.formatNumber(summary.recent_daily_average, 1)}/día`,
      });
    }

    if (!isClosedMonth &&
        summary.required_daily_average !== null &&
        summary.required_daily_average !== undefined) {
      rows.push({
        label: 'Necesita en los días restantes',
        value: `${this.formatNumber(summary.required_daily_average, 1)}/día`,
        emphasis: true,
      });
    }

    rows.push({
      label: isClosedMonth ? 'Cierre observado' : 'Cierre proyectado',
      value: (
        `${this.formatNumber(summary.projected_close)} / meta ` +
        `${this.formatNumber(summary.benchmark)}`
      ),
    });

    if (isClosedMonth &&
        summary.projected_compliance_pct !== null &&
        summary.projected_compliance_pct !== undefined) {
      rows.push({
        label: 'Cumplimiento final',
        value: this.formatPercent(summary.projected_compliance_pct),
      });
    }

    const gap = this.toNumber(summary.projected_gap_units);

    if (gap !== null) {
      rows.push({
        label: isClosedMonth ? 'Brecha final' : 'Brecha al cierre',
        value: gap >= 0
          ? (
            isClosedMonth
              ? `superávit final +${this.formatNumber(gap)}`
              : `superávit +${this.formatNumber(gap)}`
          )
          : (
            isClosedMonth
              ? `faltaron ${this.formatNumber(Math.abs(gap))}`
              : `faltarán ${this.formatNumber(Math.abs(gap))}`
          ),
        emphasis: true,
      });
    }

    return rows;
  }

  private buildBajasOperationalSummaryRows(
    summary: TrackBranchOperationalSummary,
  ): OperationalSummaryRowView[] {
    const rows: OperationalSummaryRowView[] = [];
    const isClosedMonth = summary.remaining_days === 0;

    const today = this.toNumber(summary.today_delta);
    rows.push({
      label: 'Hoy',
      value: today === null
        ? '—'
        : `${this.formatSignedDailyUnit(today)} bajas`,
    });

    if (summary.recent_daily_average !== null &&
        summary.recent_daily_average !== undefined) {
      rows.push({
        label: 'Promedio diario (7 días)',
        value: `${this.formatNumber(summary.recent_daily_average, 1)}/día`,
      });
    }

    rows.push({
      label: isClosedMonth ? 'Cierre observado' : 'Cierre proyectado',
      value: (
        `${this.formatNumber(summary.projected_close)} / límite ` +
        `${this.formatNumber(summary.benchmark)}`
      ),
    });

    if (isClosedMonth &&
        summary.projected_limit_usage_pct !== null &&
        summary.projected_limit_usage_pct !== undefined) {
      rows.push({
        label: 'Consumo final',
        value: this.formatPercent(summary.projected_limit_usage_pct),
      });
    }

    const excess = this.toNumber(summary.projected_excess_units);
    const margin = this.toNumber(summary.projected_remaining_margin);

    if (excess !== null && excess > 0) {
      rows.push({
        label: isClosedMonth ? 'Exceso final' : 'Riesgo al cierre',
        value: `exceso +${this.formatNumber(excess)}`,
        emphasis: true,
      });
    } else if (margin !== null) {
      rows.push({
        label: isClosedMonth ? 'Margen final' : 'Margen al cierre',
        value: this.formatNumber(margin),
        emphasis: true,
      });
    }

    return rows;
  }

  private buildIncomeOperationalSummaryRows(
    summary: TrackBranchOperationalSummary,
  ): OperationalSummaryRowView[] {
    const rows: OperationalSummaryRowView[] = [
      {
        label: 'Ingreso MTD',
        value: this.formatMoney(summary.actual_mtd),
      },
      {
        label: 'Cierre proyectado',
        value: (
          `${this.formatMoney(summary.projected_close)} / meta ` +
          `${this.formatMoney(summary.benchmark)}`
        ),
      },
    ];

    const gap = this.toNumber(summary.projected_gap_units);

    if (gap !== null) {
      rows.push({
        label: 'Brecha al cierre',
        value: gap >= 0
          ? `superávit +${this.formatMoney(gap)}`
          : `faltarán ${this.formatMoney(Math.abs(gap))}`,
        emphasis: true,
      });
    }

    return rows;
  }

  private buildBusinessRuleViews(
    rules: TrackBranchOperationalBusinessRules,
  ): BusinessRuleView[] {
    const labels: Record<keyof TrackBranchOperationalBusinessRules, string> = {
      clientes_nuevos_pacing: 'Ritmo de clientes nuevos',
      reactivaciones_pacing: 'Ritmo de reactivaciones',
      bajas_rule: 'Regla de bajas',
      domiciliados_pacing: 'Ritmo de domiciliados',
      domiciliados_formula: 'Curva base de domiciliados',
      projection_method: 'Método de proyección de ingreso',
      operational_projection_method: 'Método de proyección operativa',
      operational_projection_window_calendar_days: 'Ventana de proyección operativa',
      operational_projection_min_valid_deltas: 'Mínimo de deltas válidos',
      active_members_observed_source: 'Fuente observada de Socios activos',
      active_members_start_source: 'Fuente de inicio de Socios activos',
      active_members_projection_method: 'Método de proyección de Socios activos',
      active_members_projection_formula: 'Fórmula de proyección de Socios activos',
      income_signal_basis: 'Base de señal de ingreso',
      trend_window_valid_cuts: 'Ventana de tendencia',
      trend_dead_band_pp: 'Banda muerta de tendencia',
      pace_severely_below_pct: 'Ritmo severamente bajo',
      bajas_high_limit_usage_pct: 'Consumo alto de bajas',
      bajas_near_limit_usage_pct: 'Bajas cerca del límite',
      bajas_signal_precedence: 'Precedencia de señales de bajas',
      income_linear_pacing_used: 'Ritmo lineal de ingreso',
      recommendation_strategy: 'Estrategia de recomendaciones',
      recommendation_max_items: 'Máximo de acciones sugeridas',
    };

    return (Object.keys(labels) as Array<keyof TrackBranchOperationalBusinessRules>)
      .map((key) => ({
        key,
        label: labels[key],
        value: this.formatBusinessRuleValue(key, rules[key]),
      }));
  }

  private formatBusinessRuleValue(
    key: keyof TrackBranchOperationalBusinessRules,
    value: TrackBranchOperationalBusinessRules[
      keyof TrackBranchOperationalBusinessRules
    ],
  ): string {
    const valueLabels: Record<string, string> = {
      weekday_curve: 'Curva histórica por día de semana',
      clientes_nuevos_weekday_curve: (
        'Misma curva weekday que Clientes nuevos'
      ),
      monthly_limit_consumption: 'Consumo contra límite mensual',
      calendar_linear: 'Ritmo lineal por día calendario',
      'day_of_month / days_in_month': (
        'Día del mes ÷ días naturales del mes'
      ),
      existing_stable_historical_pace: (
        'Ritmo histórico estable disponible'
      ),
      recent_valid_daily_average_7_calendar_days: (
        'Promedio diario de deltas válidos'
      ),
      remaining_operational_component_projections: (
        'Remanentes de las proyecciones operativas existentes'
      ),
      usuarios_activos_actual: 'Usuarios activos observados al corte',
      socios_activos_inicio_mes_not_propagated_to_track_daily_mart: (
        'socios_activos_inicio_mes no disponible en Track Daily Mart'
      ),
      'usuarios_activos_actual+clientes_nuevos_remaining_projected+reactivaciones_remaining_projected-bajas_remaining_projected': (
        'Observado + clientes nuevos restantes + reactivaciones restantes − bajas restantes'
      ),
      projected_close_vs_monthly_target_only: (
        'Proyección de cierre vs meta mensual'
      ),
      bajas_limit_exceeded: 'Límite de bajas excedido',
      bajas_near_limit: 'Bajas cerca del límite',
      bajas_high_limit_usage: 'Consumo alto del límite de bajas',
      primary_blocker_plus_distinct_operational_risks: (
        'Bloqueo principal + riesgos operativos distintos no cubiertos'
      ),
    };

    const formatCode = (item: unknown): string => {
      const normalized = String(item ?? '');
      return valueLabels[normalized] || normalized.split('_').join(' ');
    };

    if (Array.isArray(value)) {
      return value.map((item) => formatCode(item)).join(' → ');
    }
    if (typeof value === 'boolean') {
      return value ? 'Sí' : 'No';
    }
    if (key === 'trend_window_valid_cuts') {
      return `${value} cortes válidos`;
    }
    if (key === 'recommendation_max_items') {
      return `${value} acciones`;
    }
    if (key === 'operational_projection_window_calendar_days') {
      return `${value} días calendario`;
    }
    if (key === 'operational_projection_min_valid_deltas') {
      return `${value} días`;
    }
    if (key === 'trend_dead_band_pp') {
      return `±${value} pp`;
    }
    if (
      key === 'pace_severely_below_pct' ||
      key === 'bajas_high_limit_usage_pct' ||
      key === 'bajas_near_limit_usage_pct'
    ) {
      return `${value}%`;
    }

    return formatCode(value);
  }

  private normalizeGenerationMode(value: string | null): TrackGenerationMode {
    return value === 'official_closed_day'
      ? 'official_closed_day'
      : 'manual_preview';
  }

  private clampPercent(value: string | number | null | undefined): number {
    const numeric = this.toNumber(value);
    return numeric === null ? 0 : Math.min(Math.max(numeric, 0), 100);
  }

  private toNumber(
    value: string | number | null | undefined,
  ): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  private getTijuanaTodayIsoDate(): string {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Tijuana',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date());
    const values = Object.fromEntries(
      parts.map((part) => [part.type, part.value]),
    );
    return `${values['year']}-${values['month']}-${values['day']}`;
  }
}
