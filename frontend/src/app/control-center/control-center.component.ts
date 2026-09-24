import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Subject, forkJoin, takeUntil } from 'rxjs';

import {
  TrackForecastCenterCatalogsResponse,
  TrackForecastCenterParams,
  TrackForecastCenterResponse,
} from '../services/track.service';
import {
  MarketingSalesFunnelBranch,
  MarketingSalesFunnelResponse,
} from '../marketing-sales-funnel/marketing-sales-funnel.models';
import {
  MaintenancePlannerBoard,
  MaintenancePlannerTicket,
} from '../maintenance-planner/maintenance-planner.service';
import {
  ControlCenterService,
  ControlContextRequest,
  ControlContextResponse,
  ControlHistoricalComparisonPeriod,
  ControlHistoricalComparisonValue,
  ControlOperationalForecastMetric,
  ControlOperationalForecastMetricKey,
  ControlOperationalForecastResponse,
  ControlRetentionResponse,
  ControlScope,
} from './control-center.service';

type ControlMetricKey = 'forecast' | 'conversion' | 'retention' | 'maintenance';
type ControlDetailLevel = 'summary' | 'why' | 'where' | 'source';
type ControlTone = 'normal' | 'attention' | 'critical' | 'muted';

interface ControlScopeOption {
  key: string;
  label: string;
  request: ControlContextRequest;
}

interface ControlMetricCard {
  key: ControlMetricKey;
  title: string;
  value: string;
  supportingText: string;
  freshnessText?: string;
  tone: ControlTone;
}

interface ControlDetailRow {
  label: string;
  value: string;
  supportingText?: string;
}

interface MarketingOverview {
  leads: number | null;
  visits: number;
  sales: number | null;
  salesRevenue: number;
  leadToVisitRate: number | null;
  visitToSaleRate: number | null;
  leadToSaleRate: number | null;
  branches: MarketingSalesFunnelBranch[];
}

interface MaintenanceOverview {
  active: number;
  overdue: number;
  today: number;
  week: number;
  unscheduled: number;
  needsSparePart: number;
  tickets: MaintenancePlannerTicket[];
}

interface ControlOperationalForecastRow {
  key: ControlOperationalForecastMetricKey;
  label: string;
  money: boolean;
  metric: ControlOperationalForecastMetric;
}

type ControlVisualTone = 'neutral' | 'benchmark' | 'good' | 'attention';
type ControlExecutivePillKey =
  | ControlOperationalForecastMetricKey
  | 'funnel'
  | 'maintenance';

interface ControlExecutivePill {
  key: ControlExecutivePillKey;
  label: string;
  group: 'forecast' | 'module';
}

interface ControlExecutiveStat {
  label: string;
  value: string;
  supportingText?: string;
  tone: ControlVisualTone;
}

interface ControlComparisonBar {
  label: string;
  value: string;
  percent: number;
  tone: ControlVisualTone;
}

interface ControlWhereBar {
  label: string;
  value: string;
  supportingText: string;
  percent: number;
  tone: ControlVisualTone;
}

interface ControlHistoricalComparisonCard {
  label: string;
  mtdLabel: string;
  mtdValue: string;
  mtdDetail: string;
  mtdTone: ControlVisualTone;
  closeLabel: string;
  closeValue: string;
  closeDetail: string;
  closeTone: ControlVisualTone;
}

interface ControlAttentionItem {
  metric: ControlMetricKey;
  forecastMetric?: ControlOperationalForecastMetricKey;
  title: string;
  text: string;
  severity?: number;
}

@Component({
  selector: 'app-control-center',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './control-center.component.html',
  styleUrls: ['./control-center.component.css'],
})
export class ControlCenterComponent implements OnInit, OnDestroy {
  readonly pageTitle = 'Centro de Control';
  readonly detailLevels: Array<{ key: ControlDetailLevel; label: string }> = [
    { key: 'summary', label: 'Resumen' },
    { key: 'why', label: 'Por qué' },
    { key: 'where', label: 'Dónde' },
    { key: 'source', label: 'Fuente' },
  ];

  readonly executiveContextPills: ControlExecutivePill[] = [
    { key: 'ingreso', label: 'Ingresos', group: 'forecast' },
    { key: 'clientes_nuevos', label: 'Venta nueva', group: 'forecast' },
    { key: 'reactivaciones', label: 'Reactivaciones', group: 'forecast' },
    { key: 'bajas', label: 'Bajas', group: 'forecast' },
    { key: 'tienda', label: 'Tienda', group: 'forecast' },
    { key: 'funnel', label: 'Funnel', group: 'module' },
    { key: 'maintenance', label: 'Mantenimiento', group: 'module' },
  ];

  cutoffDate = this.getTodayIsoDate();
  context: ControlContextResponse | null = null;
  catalogs: TrackForecastCenterCatalogsResponse | null = null;
  forecastData: TrackForecastCenterResponse | null = null;
  operationalForecastData: ControlOperationalForecastResponse | null = null;
  marketingData: MarketingSalesFunnelResponse | null = null;
  retentionData: ControlRetentionResponse | null = null;
  maintenanceData: MaintenancePlannerBoard | null = null;

  scopeOptions: ControlScopeOption[] = [];
  selectedScopeKey = '';
  selectedMetric: ControlMetricKey = 'forecast';
  selectedForecastMetric: ControlOperationalForecastMetricKey = 'ingreso';
  selectedLevel: ControlDetailLevel = 'summary';

  loadingContext = false;
  loadingSources = false;
  errorMessage = '';

  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly controlService: ControlCenterService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.loadControlBase();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  get isLoading(): boolean {
    return this.loadingContext || this.loadingSources;
  }

  get canOpenSelectedModule(): boolean {
    if (this.selectedMetric === 'retention') {
      return false;
    }

    if (
      this.selectedMetric === 'forecast'
      && this.selectedForecastMetric !== 'ingreso'
    ) {
      return false;
    }

    return true;
  }

  get selectedExecutiveTitle(): string {
    if (this.selectedMetric === 'forecast') {
      const row = this.selectedOperationalForecastRow;
      return `${row?.label || 'Ingresos'} · Forecast de cierre`;
    }

    if (this.selectedMetric === 'conversion') {
      return 'Lead → venta';
    }

    return this.selectedMetricCard.title;
  }

  get selectedOperationalForecastRow(): ControlOperationalForecastRow | null {
    return this.operationalForecastRows.find(
      (row) => row.key === this.selectedForecastMetric,
    ) || null;
  }

  get scopeLabel(): string {
    const selected = this.scopeOptions.find(
      (option) => option.key === this.selectedScopeKey,
    );
    return selected?.label || this.defaultScopeLabel(this.context?.effective_scope);
  }

  get marketingFreshnessLabel(): string {
    const sourceCutoff = this.marketingData?.selected_cutoff_date;

    if (!sourceCutoff || sourceCutoff >= this.cutoffDate) {
      return '';
    }

    const lagDays = this.daysBetweenIsoDates(
      sourceCutoff,
      this.cutoffDate,
    );

    if (lagDays <= 0) {
      return '';
    }

    return (
      `Corte ${this.formatShortIsoDate(sourceCutoff)} · `
      + `${lagDays} día${lagDays === 1 ? '' : 's'} de atraso`
    );
  }

  get operationalForecastRows(): ControlOperationalForecastRow[] {
    const metrics = this.operationalForecastData?.summary.metrics;
    if (!metrics) return [];

    const config: Array<{
      key: ControlOperationalForecastMetricKey;
      label: string;
      money: boolean;
    }> = [
      { key: 'ingreso', label: 'Ingresos', money: true },
      { key: 'clientes_nuevos', label: 'Venta nueva', money: false },
      { key: 'reactivaciones', label: 'Reactivaciones', money: false },
      { key: 'bajas', label: 'Bajas', money: false },
      { key: 'tienda', label: 'Tienda', money: true },
    ];

    return config.map((item) => ({
      ...item,
      metric: metrics[item.key],
    }));
  }

  get showOperationalSummaryVisual(): boolean {
    return (
      this.selectedMetric === 'forecast'
      && this.selectedLevel === 'summary'
      && this.selectedOperationalForecastRow !== null
    );
  }

  get showOperationalWhereVisual(): boolean {
    return (
      this.selectedMetric === 'forecast'
      && this.selectedLevel === 'where'
      && this.selectedOperationalForecastRow !== null
    );
  }

  get operationalExecutiveStats(): ControlExecutiveStat[] {
    const row = this.selectedOperationalForecastRow;
    if (!row) return [];

    const projected = this.toFiniteNumber(row.metric.projected_close);
    const benchmark = this.toFiniteNumber(row.metric.benchmark);
    const gap = this.toFiniteNumber(row.metric.projected_gap);
    const attainment = (
      projected !== null
      && benchmark !== null
      && benchmark > 0
    )
      ? projected / benchmark
      : null;

    const adverse = gap !== null && (
      row.key === 'bajas' ? gap > 0 : gap < 0
    );

    return [
      {
        label: 'Real MTD',
        value: this.formatOperationalForecastValue(
          row,
          row.metric.actual_mtd,
        ),
        tone: 'neutral',
      },
      {
        label: 'Forecast cierre',
        value: this.formatOperationalForecastValue(
          row,
          row.metric.projected_close,
        ),
        tone: adverse ? 'attention' : 'good',
      },
      {
        label: row.key === 'bajas' ? 'Límite mensual' : 'Meta mensual',
        value: this.formatOperationalForecastValue(
          row,
          row.metric.benchmark,
        ),
        tone: 'benchmark',
      },
      {
        label: row.key === 'bajas'
          ? (gap !== null && gap > 0
            ? 'Exceso proyectado'
            : 'Margen proyectado')
          : 'Brecha proyectada',
        value: this.formatOperationalForecastGap(row),
        tone: adverse ? 'attention' : 'good',
      },
      {
        label: row.key === 'bajas'
          ? 'Uso proyectado del límite'
          : 'Cumplimiento proyectado',
        value: this.formatPercent(attainment),
        supportingText: this.operationalForecastMethodLabel(row.metric),
        tone: adverse ? 'attention' : 'good',
      },
    ];
  }

  get operationalComparisonBars(): ControlComparisonBar[] {
    const row = this.selectedOperationalForecastRow;
    if (!row) return [];

    const actual = this.toFiniteNumber(row.metric.actual_mtd);
    const projected = this.toFiniteNumber(row.metric.projected_close);
    const benchmark = this.toFiniteNumber(row.metric.benchmark);

    const available = [actual, projected, benchmark]
      .filter((value): value is number => value !== null)
      .map((value) => Math.abs(value));
    const maxValue = available.length > 0
      ? Math.max(...available, 1)
      : 1;

    const gap = this.toFiniteNumber(row.metric.projected_gap);
    const adverse = gap !== null && (
      row.key === 'bajas' ? gap > 0 : gap < 0
    );

    return [
      {
        label: 'Real MTD',
        value: this.formatOperationalNumber(row, actual),
        percent: this.comparisonPercent(actual, maxValue),
        tone: 'neutral',
      },
      {
        label: 'Forecast cierre',
        value: this.formatOperationalNumber(row, projected),
        percent: this.comparisonPercent(projected, maxValue),
        tone: adverse ? 'attention' : 'good',
      },
      {
        label: row.key === 'bajas' ? 'Límite' : 'Meta',
        value: this.formatOperationalNumber(row, benchmark),
        percent: this.comparisonPercent(benchmark, maxValue),
        tone: 'benchmark',
      },
    ];
  }

  get operationalHistoricalComparisonCards(): ControlHistoricalComparisonCard[] {
    const row = this.selectedOperationalForecastRow;
    const comparisons = this.operationalForecastData
      ?.historical_comparison.metrics[this.selectedForecastMetric];

    if (!row || !comparisons) {
      return [];
    }

    return [
      this.buildHistoricalComparisonCard(
        'Mes anterior',
        comparisons.previous_month,
        row,
      ),
      this.buildHistoricalComparisonCard(
        'Año anterior',
        comparisons.previous_year,
        row,
      ),
    ];
  }

  get operationalWhereBars(): ControlWhereBar[] {
    const row = this.selectedOperationalForecastRow;
    if (!row) return [];

    const key = row.key;
    const items = (this.operationalForecastData?.branches || [])
      .map((branch) => {
        const metric = branch.metrics?.[key];
        const gap = this.toFiniteNumber(metric?.projected_gap);
        const projected = this.toFiniteNumber(metric?.projected_close);
        const benchmark = this.toFiniteNumber(metric?.benchmark);

        return {
          branch,
          metric,
          gap,
          projected,
          benchmark,
        };
      })
      .filter((item) => item.metric && item.gap !== null)
      .sort((a, b) => {
        const gapA = a.gap ?? 0;
        const gapB = b.gap ?? 0;
        return key === 'bajas'
          ? gapB - gapA
          : gapA - gapB;
      })
      .slice(0, 8);

    const maxGap = Math.max(
      ...items.map((item) => Math.abs(item.gap ?? 0)),
      1,
    );

    return items.map((item) => {
      const gap = item.gap ?? 0;
      const adverse = key === 'bajas' ? gap > 0 : gap < 0;

      return {
        label: item.branch.sucursal,
        value: this.formatOperationalGapByKey(
          key,
          gap,
          row.money,
        ),
        supportingText: (
          `Forecast ${this.formatOperationalNumber(
            row,
            item.projected,
          )} · `
          + `${key === 'bajas' ? 'Límite' : 'Meta'} `
          + this.formatOperationalNumber(row, item.benchmark)
        ),
        percent: this.comparisonPercent(gap, maxGap),
        tone: adverse ? 'attention' : 'good',
      };
    });
  }

  get metricCards(): ControlMetricCard[] {
    const forecast = this.forecastData?.summary;
    const marketing = this.marketingOverview;
    const marketingFreshness = this.marketingFreshnessLabel;
    const retention = this.retentionData?.summary;
    const maintenance = this.maintenanceOverview;

    const forecastGap = forecast?.projected_gap_to_goal ?? null;
    const forecastTone: ControlTone = forecastGap === null
      ? 'muted'
      : forecastGap < 0
        ? 'attention'
        : 'normal';

    const conversion = marketing.leadToSaleRate;
    const retentionUsage = retention?.limit_usage_ratio ?? null;
    const retentionTone: ControlTone = retentionUsage === null
      ? 'muted'
      : retentionUsage > 1
        ? 'critical'
        : retentionUsage >= 0.85
          ? 'attention'
          : 'normal';

    return [
      {
        key: 'forecast',
        title: 'Forecast de cierre',
        value: this.formatCurrency(
          forecast?.projected_close_comparable_to_goal ?? null,
        ),
        supportingText: forecastGap === null
          ? 'Sin proyección comparable disponible'
          : `Brecha ${this.formatSignedCurrency(forecastGap)} vs meta comparable`,
        tone: forecastTone,
      },
      {
        key: 'conversion',
        title: 'Conversión',
        value: this.formatPercent(conversion),
        supportingText: (
          marketing.leads === null || marketing.sales === null
        )
          ? 'Lead → venta · histórico CRM no disponible para el alcance actual'
          : `Lead → venta · ${this.formatInteger(marketing.sales)} ventas digitales de ${this.formatInteger(marketing.leads)} leads`,
        freshnessText: marketingFreshness || undefined,
        tone: conversion === null ? 'muted' : 'normal',
      },
      {
        key: 'retention',
        title: 'Bajas',
        value: this.formatInteger(retention?.bajas_reales_mtd),
        supportingText: retentionUsage === null
          ? 'Sin meta comparable disponible'
          : `${this.formatPercent(retentionUsage)} del límite mensual`,
        tone: retentionTone,
      },
      {
        key: 'maintenance',
        title: 'Mantenimiento',
        value: `${maintenance.overdue} vencidos`,
        supportingText: `${maintenance.unscheduled} sin fecha · ${maintenance.needsSparePart} con refacción`,
        tone: maintenance.overdue > 0 || maintenance.unscheduled > 0
          ? 'attention'
          : 'normal',
      },
    ];
  }

  get attentionItems(): ControlAttentionItem[] {
    const items: ControlAttentionItem[] = [];

    const forecastItems = this.operationalForecastRows
      .map((row) => {
        const gap = this.toFiniteNumber(row.metric.projected_gap);
        const benchmark = this.toFiniteNumber(row.metric.benchmark);
        const adverse = gap !== null && (
          row.key === 'bajas'
            ? gap > 0
            : gap < 0
        );

        return {
          row,
          gap,
          adverse,
          severity: (
            adverse
            && benchmark !== null
            && Math.abs(benchmark) > 0
            && gap !== null
          )
            ? Math.abs(gap) / Math.abs(benchmark)
            : 0,
        };
      })
      .filter((item) => item.adverse)
      .sort((a, b) => b.severity - a.severity)
      .slice(0, 3);

    for (const item of forecastItems) {
      const row = item.row;
      const title = row.key === 'bajas'
        ? 'Bajas proyectadas sobre límite'
        : row.key === 'ingreso'
          ? 'Ingresos proyectados debajo de meta'
          : row.key === 'clientes_nuevos'
            ? 'Venta nueva proyectada debajo de meta'
            : row.key === 'reactivaciones'
              ? 'Reactivaciones proyectadas debajo de meta'
              : 'Tienda proyectada debajo de meta';

      items.push({
        metric: 'forecast',
        forecastMetric: row.key,
        title,
        text: `Brecha proyectada ${this.formatOperationalForecastGap(row)}.`,
        severity: item.severity,
      });
    }

    const retention = this.retentionData?.summary;
    const bajasForecast = this.operationalForecastData?.summary.metrics.bajas;
    const bajasGap = this.toFiniteNumber(bajasForecast?.projected_gap);
    const projectedBajasAlreadyFlagged = bajasGap !== null && bajasGap > 0;

    if (
      !projectedBajasAlreadyFlagged
      && retention?.limit_usage_ratio !== null
      && retention?.limit_usage_ratio !== undefined
      && retention.limit_usage_ratio > 1
    ) {
      items.push({
        metric: 'retention',
        title: 'Bajas ya rebasaron el límite',
        text: `${this.formatPercent(retention.limit_usage_ratio)} del límite mensual consumido.`,
      });
    }

    const maintenance = this.maintenanceOverview;
    if (maintenance.overdue > 0) {
      items.push({
        metric: 'maintenance',
        title: `${maintenance.overdue} compromisos vencidos`,
        text: `${maintenance.unscheduled} tickets adicionales siguen sin fecha.`,
      });
    } else if (maintenance.unscheduled > 0) {
      items.push({
        metric: 'maintenance',
        title: `${maintenance.unscheduled} tickets sin compromiso`,
        text: 'Todavía no tienen fecha de atención registrada.',
      });
    }

    if (this.marketingData?.data_quality.visit_conversion_cohort_complete === false) {
      items.push({
        metric: 'conversion',
        title: 'Cohorte comercial en curso',
        text: 'Las conversiones del mes todavía pueden cambiar mientras madura la cohorte.',
      });
    }

    return items.slice(0, 4);
  }

  get selectedMetricCard(): ControlMetricCard {
    return this.metricCards.find(
      (card) => card.key === this.selectedMetric,
    ) || this.metricCards[0];
  }

  get detailRows(): ControlDetailRow[] {
    switch (this.selectedLevel) {
      case 'why':
        return this.buildWhyRows();
      case 'where':
        return this.buildWhereRows();
      case 'source':
        return this.buildSourceRows();
      default:
        return this.buildSummaryRows();
    }
  }

  loadControlBase(): void {
    this.loadingContext = true;
    this.errorMessage = '';

    forkJoin({
      context: this.controlService.getContext({ cutoffDate: this.cutoffDate }),
      catalogs: this.controlService.getForecastCatalogs(),
    })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ({ context, catalogs }) => {
          this.context = context;
          this.catalogs = catalogs;
          this.scopeOptions = this.buildScopeOptions(context, catalogs);
          this.selectedScopeKey = this.keyForScope(context.effective_scope);
          this.loadingContext = false;
          this.loadSources();
        },
        error: (error) => {
          this.loadingContext = false;
          this.errorMessage = this.resolveError(
            error,
            'No se pudo inicializar el Centro de Control.',
          );
        },
      });
  }

  onCutoffDateChange(): void {
    if (!this.cutoffDate) return;
    this.loadControlBase();
  }

  onScopeChange(): void {
    const option = this.scopeOptions.find(
      (item) => item.key === this.selectedScopeKey,
    );
    if (!option) return;

    this.loadingContext = true;
    this.errorMessage = '';

    this.controlService
      .getContext({
        ...option.request,
        cutoffDate: this.cutoffDate,
      })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (context) => {
          this.context = context;
          this.loadingContext = false;
          this.loadSources();
        },
        error: (error) => {
          this.loadingContext = false;
          this.errorMessage = this.resolveError(
            error,
            'El alcance solicitado no está autorizado.',
          );
          if (this.context) {
            this.selectedScopeKey = this.keyForScope(this.context.effective_scope);
          }
        },
      });
  }

  refresh(): void {
    this.loadSources();
  }

  selectMetric(metric: ControlMetricKey): void {
    this.selectedMetric = metric;
    if (metric === 'forecast') {
      this.selectedForecastMetric = 'ingreso';
    }
    this.selectedLevel = 'summary';
  }

  selectOperationalForecastMetric(
    metric: ControlOperationalForecastMetricKey,
  ): void {
    this.selectedMetric = 'forecast';
    this.selectedForecastMetric = metric;
    this.selectedLevel = 'summary';
  }

  isExecutiveContextPillActive(
    key: ControlExecutivePillKey,
  ): boolean {
    if (key === 'funnel') {
      return this.selectedMetric === 'conversion';
    }

    if (key === 'maintenance') {
      return this.selectedMetric === 'maintenance';
    }

    return (
      this.selectedMetric === 'forecast'
      && this.selectedForecastMetric === key
    );
  }

  isExecutiveContextPillSeparated(
    pill: ControlExecutivePill,
  ): boolean {
    return pill.group === 'module';
  }

  selectExecutiveContextPill(
    key: ControlExecutivePillKey,
  ): void {
    if (key === 'funnel') {
      this.selectMetric('conversion');
      return;
    }

    if (key === 'maintenance') {
      this.selectMetric('maintenance');
      return;
    }

    this.selectOperationalForecastMetric(key);
  }

  selectAttentionItem(item: ControlAttentionItem): void {
    if (item.forecastMetric) {
      this.selectOperationalForecastMetric(item.forecastMetric);
      return;
    }

    this.selectMetric(item.metric);
  }

  selectLevel(level: ControlDetailLevel): void {
    this.selectedLevel = level;
  }

  openSelectedModule(): void {
    const scope = this.context?.effective_scope;

    if (this.selectedMetric === 'forecast') {
      const forecastScope = this.buildForecastScope(scope);
      void this.router.navigate(['/warehouse/track/forecast-center'], {
        queryParams: {
          track_date: this.cutoffDate,
          generation_mode: 'manual_preview',
          scope: forecastScope.scope,
          scope_id: forecastScope.scope_id,
          cohort: 'all',
          breakdown: forecastScope.scope === 'national' ? 'region' : 'none',
          view: 'summary',
        },
      });
      return;
    }

    if (this.selectedMetric === 'conversion') {
      void this.router.navigate(['/marketing-conversion/venta-total']);
      return;
    }

    if (this.selectedMetric === 'maintenance') {
      void this.router.navigate(['/maintenance-planner']);
    }
  }

  formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value);
  }

  formatSignedCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return '—';
    }
    const formatted = this.formatCurrency(Math.abs(value));
    return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
  }

  formatPercent(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }

  formatInteger(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value);
  }

  formatOperationalForecastValue(
    row: ControlOperationalForecastRow,
    value: string | null,
  ): string {
    const numericValue = this.toFiniteNumber(value);
    if (numericValue === null) return '—';

    return row.money
      ? this.formatCurrency(numericValue)
      : this.formatInteger(numericValue);
  }

  formatOperationalForecastGap(
    row: ControlOperationalForecastRow,
  ): string {
    const gap = this.toFiniteNumber(row.metric.projected_gap);
    if (gap === null) return '—';

    if (row.key === 'bajas') {
      if (gap > 0) {
        return `+${this.formatInteger(gap)} sobre límite`;
      }
      if (gap < 0) {
        return `${this.formatInteger(Math.abs(gap))} de margen`;
      }
      return 'En límite';
    }

    if (row.money) {
      return this.formatSignedCurrency(gap);
    }

    return this.formatSignedInteger(gap);
  }

  operationalForecastGapClass(
    row: ControlOperationalForecastRow,
  ): string {
    const gap = this.toFiniteNumber(row.metric.projected_gap);

    if (gap === null || row.metric.status !== 'available') {
      return 'forecast-gap forecast-gap--muted';
    }

    const adverse = row.key === 'bajas'
      ? gap > 0
      : gap < 0;

    return adverse
      ? 'forecast-gap forecast-gap--attention'
      : 'forecast-gap forecast-gap--good';
  }

  operationalForecastCoverageLabel(
    row: ControlOperationalForecastRow,
  ): string {
    const coverage = row.metric.coverage;

    if (
      coverage.projected_available_branches
      === coverage.total_branches
    ) {
      return '';
    }

    return (
      `Cobertura ${coverage.projected_available_branches}/`
      + `${coverage.total_branches} sucursales`
    );
  }

  private formatSignedInteger(value: number): string {
    const formatted = this.formatInteger(Math.abs(value));
    return value > 0
      ? `+${formatted}`
      : value < 0
        ? `-${formatted}`
        : formatted;
  }

  private toFiniteNumber(
    value: string | number | null | undefined,
  ): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }

    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : null;
  }

  private loadSources(): void {
    if (!this.context || !this.catalogs) return;

    const week = this.resolveWeek(this.cutoffDate);
    const month = this.cutoffDate.slice(0, 7);
    const forecastParams = this.buildForecastParams(this.context.effective_scope);
    const scopeRequest = this.requestForEffectiveScope(this.context.effective_scope);

    this.loadingSources = true;
    this.errorMessage = '';

    forkJoin({
      forecast: this.controlService.getForecast(forecastParams),
      operationalForecast: this.controlService.getOperationalForecast(
        {
          ...scopeRequest,
          cutoffDate: this.cutoffDate,
        },
      ),
      marketing: this.controlService.getMarketing(month, this.cutoffDate),
      retention: this.controlService.getRetention({
        ...scopeRequest,
        cutoffDate: this.cutoffDate,
      }),
      maintenance: this.controlService.getMaintenance(week.start, week.end),
    })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ({
          forecast,
          operationalForecast,
          marketing,
          retention,
          maintenance,
        }) => {
          this.forecastData = forecast;
          this.operationalForecastData = operationalForecast;
          this.marketingData = marketing;
          this.retentionData = retention;
          this.maintenanceData = maintenance;
          this.loadingSources = false;
        },
        error: (error) => {
          this.loadingSources = false;
          this.errorMessage = this.resolveError(
            error,
            'No fue posible cargar una de las fuentes del Centro de Control.',
          );
        },
      });
  }

  private get marketingOverview(): MarketingOverview {
    const dashboard = this.marketingData;
    const scope = this.context?.effective_scope;

    if (!dashboard) {
      return {
        leads: null,
        visits: 0,
        sales: 0,
        salesRevenue: 0,
        leadToVisitRate: null,
        visitToSaleRate: null,
        leadToSaleRate: null,
        branches: [],
      };
    }

    const branches = this.filterMarketingBranches(dashboard.branches, scope);
    const crmAvailable = branches.every(
      (branch) => (
        branch.leads_meta !== null
        && branch.sales_digital !== null
      ),
    );
    const leads = crmAvailable
      ? branches.reduce(
          (total, branch) => total + (branch.leads_meta ?? 0),
          0,
        )
      : null;
    const visits = branches.reduce(
      (total, branch) => total + branch.visits_total,
      0,
    );
    const sales = crmAvailable
      ? branches.reduce(
          (total, branch) => total + (branch.sales_digital ?? 0),
          0,
        )
      : null;
    const salesRevenue = branches.reduce(
      (total, branch) => total + branch.revenue_digital,
      0,
    );

    return {
      leads,
      visits,
      sales,
      salesRevenue,
      leadToVisitRate: (
        leads !== null && leads > 0
          ? visits / leads
          : null
      ),
      visitToSaleRate: (
        sales !== null && visits > 0
          ? sales / visits
          : null
      ),
      leadToSaleRate: (
        leads !== null && sales !== null && leads > 0
          ? sales / leads
          : null
      ),
      branches,
    };
  }

  private get maintenanceOverview(): MaintenanceOverview {
    const scope = this.context?.effective_scope;
    const board = this.maintenanceData;
    if (!board) {
      return {
        active: 0,
        overdue: 0,
        today: 0,
        week: 0,
        unscheduled: 0,
        needsSparePart: 0,
        tickets: [],
      };
    }

    const byId = new Map<number, MaintenancePlannerTicket>();
    const sources = [
      ...board.overdue,
      ...board.unscheduled,
      ...board.today_items,
      ...board.future,
      ...board.days.flatMap((day) => day.items),
    ];

    for (const ticket of sources) {
      byId.set(ticket.ticket_id, ticket);
    }

    const tickets = [...byId.values()].filter((ticket) =>
      this.scopeContainsBranch(scope, ticket.sucursal_id),
    );
    const active = tickets.filter((ticket) =>
      ['abierto', 'en progreso', 'por_validar'].includes(
        String(ticket.estado || '').toLowerCase(),
      ),
    );

    return {
      active: active.length,
      overdue: active.filter((ticket) => ticket.planner_status === 'VENCIDO').length,
      today: active.filter((ticket) => ticket.planner_status === 'HOY').length,
      week: tickets.filter((ticket) => {
        const date = ticket.fecha_solucion_date;
        return Boolean(
          date
          && date >= board.window.start_date
          && date <= board.window.end_date,
        );
      }).length,
      unscheduled: active.filter((ticket) => ticket.planner_status === 'SIN_FECHA').length,
      needsSparePart: active.filter((ticket) => ticket.necesita_refaccion).length,
      tickets,
    };
  }

  private buildSummaryRows(): ControlDetailRow[] {
    const marketing = this.marketingOverview;
    const retention = this.retentionData?.summary;
    const maintenance = this.maintenanceOverview;

    switch (this.selectedMetric) {
      case 'forecast':
        return this.buildOperationalForecastSummaryRows();
      case 'conversion':
        return [
          { label: 'Lead → venta', value: this.formatPercent(marketing.leadToSaleRate) },
          { label: 'Lead → visita', value: this.formatPercent(marketing.leadToVisitRate) },
          { label: 'Visita → venta digital', value: this.formatPercent(marketing.visitToSaleRate) },
          { label: 'Leads iVentas', value: marketing.leads === null ? '—' : this.formatInteger(marketing.leads) },
          { label: 'Ventas digitales', value: marketing.sales === null ? '—' : this.formatInteger(marketing.sales) },
        ];
      case 'retention':
        return [
          { label: 'Bajas MTD', value: this.formatInteger(retention?.bajas_reales_mtd) },
          { label: 'Límite / meta mensual', value: this.formatInteger(retention?.meta_bajas_mes) },
          { label: 'Límite consumido', value: this.formatPercent(retention?.limit_usage_ratio) },
          { label: 'Margen restante', value: this.formatInteger(retention?.remaining_margin) },
        ];
      default:
        return [
          { label: 'Activos', value: this.formatInteger(maintenance.active) },
          { label: 'Vencidos', value: this.formatInteger(maintenance.overdue) },
          { label: 'Sin fecha', value: this.formatInteger(maintenance.unscheduled) },
          { label: 'Con refacción', value: this.formatInteger(maintenance.needsSparePart) },
        ];
    }
  }

  private buildWhyRows(): ControlDetailRow[] {
    const marketing = this.marketingOverview;
    const retention = this.retentionData?.summary;
    const maintenance = this.maintenanceOverview;

    switch (this.selectedMetric) {
      case 'forecast':
        return this.buildOperationalForecastWhyRows();
      case 'conversion':
        return [
          { label: 'Leads iVentas', value: marketing.leads === null ? '—' : this.formatInteger(marketing.leads) },
          { label: 'Visitas', value: this.formatInteger(marketing.visits) },
          { label: 'Ventas digitales', value: marketing.sales === null ? '—' : this.formatInteger(marketing.sales) },
          { label: 'Lead → visita', value: this.formatPercent(marketing.leadToVisitRate) },
          { label: 'Visita → venta digital', value: this.formatPercent(marketing.visitToSaleRate) },
        ];
      case 'retention':
        return [
          {
            label: 'Bajas acumuladas',
            value: this.formatInteger(retention?.bajas_reales_mtd),
            supportingText: 'En control de bajas, un número mayor es peor.',
          },
          {
            label: 'Límite mensual',
            value: this.formatInteger(retention?.meta_bajas_mes),
            supportingText: 'Suma de las metas/límites de las sucursales del alcance.',
          },
          {
            label: 'Consumo del límite',
            value: this.formatPercent(retention?.limit_usage_ratio),
            supportingText: 'Más de 100% significa que el límite mensual ya fue rebasado.',
          },
        ];
      default:
        return [
          { label: 'Vencidos', value: this.formatInteger(maintenance.overdue) },
          { label: 'Sin compromiso', value: this.formatInteger(maintenance.unscheduled) },
          { label: 'Para hoy', value: this.formatInteger(maintenance.today) },
          { label: 'Con refacción', value: this.formatInteger(maintenance.needsSparePart) },
        ];
    }
  }

  private buildWhereRows(): ControlDetailRow[] {
    if (this.selectedMetric === 'forecast') {
      return this.buildOperationalForecastWhereRows();
    }

    if (this.selectedMetric === 'conversion') {
      return [...this.marketingOverview.branches]
        .map((branch) => ({
          branch,
          leadToSaleRate: this.marketingBranchLeadToSaleRate(branch),
        }))
        .sort((a, b) =>
          (a.leadToSaleRate ?? Number.POSITIVE_INFINITY)
          - (b.leadToSaleRate ?? Number.POSITIVE_INFINITY),
        )
        .slice(0, 8)
        .map(({ branch, leadToSaleRate }) => ({
          label: branch.sucursal,
          value: this.formatPercent(leadToSaleRate),
          supportingText: `${this.formatInteger(branch.leads_meta)} leads · ${this.formatInteger(branch.sales_digital)} ventas digitales`,
        }));
    }

    if (this.selectedMetric === 'retention') {
      return [...(this.retentionData?.branches || [])]
        .sort((a, b) =>
          (b.limit_usage_ratio ?? -1) - (a.limit_usage_ratio ?? -1),
        )
        .slice(0, 8)
        .map((branch) => ({
          label: branch.sucursal,
          value: this.formatInteger(branch.bajas_reales_mtd),
          supportingText: `${this.formatPercent(branch.limit_usage_ratio)} de su límite`,
        }));
    }

    const counts = new Map<string, number>();
    for (const ticket of this.maintenanceOverview.tickets) {
      if (!['VENCIDO', 'SIN_FECHA'].includes(ticket.planner_status)) continue;
      counts.set(ticket.sucursal, (counts.get(ticket.sucursal) || 0) + 1);
    }

    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([branch, count]) => ({
        label: branch,
        value: `${count} pendientes`,
        supportingText: 'Vencidos o todavía sin fecha compromiso.',
      }));
  }

  private buildSourceRows(): ControlDetailRow[] {
    switch (this.selectedMetric) {
      case 'forecast':
        return this.buildOperationalForecastSourceRows();
      case 'conversion':
        return [
          { label: 'Módulo dueño', value: 'Marketing / Funnel de Venta Nueva' },
          { label: 'Mes', value: this.marketingData?.month || this.cutoffDate.slice(0, 7) },
          { label: 'Corte', value: this.marketingData?.selected_cutoff_date || this.cutoffDate },
          { label: 'Alcance', value: this.scopeLabel },
        ];
      case 'retention':
        return [
          { label: 'Módulo dueño', value: 'Control / adapter Retención' },
          { label: 'Fuente canónica', value: 'track_daily_mart' },
          { label: 'Versión Track', value: this.retentionData?.resolved_version ? `#${this.retentionData.resolved_version.id}` : '—' },
          { label: 'Corte', value: this.retentionData?.cutoff_date || this.cutoffDate },
        ];
      default:
        return [
          { label: 'Módulo dueño', value: 'Maintenance Planner' },
          { label: 'Entidad', value: 'Tickets de Mantenimiento' },
          { label: 'Compromiso', value: 'Ticket.fecha_solucion' },
          { label: 'Trazabilidad', value: 'Ticket.historial_fechas' },
        ];
    }
  }

  private buildOperationalForecastSummaryRows(): ControlDetailRow[] {
    const row = this.selectedOperationalForecastRow;
    if (!row) return [];

    const projected = this.toFiniteNumber(row.metric.projected_close);
    const benchmark = this.toFiniteNumber(row.metric.benchmark);
    const gap = this.toFiniteNumber(row.metric.projected_gap);
    const attainment = (
      projected !== null
      && benchmark !== null
      && benchmark > 0
    )
      ? projected / benchmark
      : null;

    return [
      {
        label: 'Real MTD',
        value: this.formatOperationalForecastValue(
          row,
          row.metric.actual_mtd,
        ),
      },
      {
        label: row.key === 'bajas'
          ? 'Límite mensual'
          : 'Meta mensual',
        value: this.formatOperationalForecastValue(
          row,
          row.metric.benchmark,
        ),
      },
      {
        label: 'Forecast cierre',
        value: this.formatOperationalForecastValue(
          row,
          row.metric.projected_close,
        ),
      },
      {
        label: row.key === 'bajas'
          ? (gap !== null && gap > 0
            ? 'Exceso proyectado'
            : 'Margen proyectado')
          : 'Brecha proyectada',
        value: this.formatOperationalForecastGap(row),
      },
      {
        label: row.key === 'bajas'
          ? 'Consumo proyectado del límite'
          : 'Cumplimiento proyectado',
        value: this.formatPercent(attainment),
      },
    ];
  }

  private buildOperationalForecastWhyRows(): ControlDetailRow[] {
    const row = this.selectedOperationalForecastRow;
    if (!row) return [];

    const actual = this.toFiniteNumber(row.metric.actual_mtd);
    const projected = this.toFiniteNumber(row.metric.projected_close);
    const benchmark = this.toFiniteNumber(row.metric.benchmark);
    const remainingDays = this.remainingDaysInSelectedMonth();
    const projectedRemaining = (
      actual !== null && projected !== null
    )
      ? projected - actual
      : null;
    const benchmarkRemaining = (
      actual !== null && benchmark !== null
    )
      ? benchmark - actual
      : null;
    const projectedDaily = (
      projectedRemaining !== null && remainingDays > 0
    )
      ? projectedRemaining / remainingDays
      : null;
    const benchmarkDaily = (
      benchmarkRemaining !== null && remainingDays > 0
    )
      ? benchmarkRemaining / remainingDays
      : null;

    const rows: ControlDetailRow[] = [
      {
        label: row.key === 'bajas'
          ? 'Bajas proyectadas restantes'
          : 'Avance proyectado restante',
        value: this.formatOperationalNumber(
          row,
          projectedRemaining,
        ),
        supportingText: `${remainingDays} días restantes en el mes.`,
      },
      {
        label: row.key === 'bajas'
          ? 'Promedio diario proyectado de bajas'
          : 'Ritmo diario proyectado',
        value: this.formatOperationalNumber(
          row,
          projectedDaily,
        ),
        supportingText: 'Ritmo implícito en el forecast oficial.',
      },
      {
        label: row.key === 'bajas'
          ? 'Margen diario hasta el límite'
          : 'Ritmo diario necesario para meta',
        value: this.formatOperationalNumber(
          row,
          benchmarkDaily,
        ),
        supportingText: row.key === 'bajas'
          ? 'Capacidad diaria restante antes de alcanzar el límite.'
          : 'Ritmo requerido desde hoy para alcanzar la meta mensual.',
      },
      {
        label: 'Método',
        value: this.operationalForecastMethodLabel(row.metric),
      },
      {
        label: 'Cobertura',
        value: `${row.metric.coverage.projected_available_branches}/${row.metric.coverage.total_branches} sucursales`,
      },
    ];

    return rows;
  }

  private buildOperationalForecastWhereRows(): ControlDetailRow[] {
    const selectedRow = this.selectedOperationalForecastRow;
    if (!selectedRow) return [];

    const branches = this.operationalForecastData?.branches || [];
    const key = selectedRow.key;

    return branches
      .map((branch) => {
        const metric = branch.metrics?.[key];
        const gap = this.toFiniteNumber(metric?.projected_gap);
        return { branch, metric, gap };
      })
      .filter((item) => item.metric && item.gap !== null)
      .sort((a, b) => {
        const gapA = a.gap ?? 0;
        const gapB = b.gap ?? 0;
        return key === 'bajas'
          ? gapB - gapA
          : gapA - gapB;
      })
      .slice(0, 8)
      .map(({ branch, metric, gap }) => ({
        label: branch.sucursal,
        value: this.formatOperationalGapByKey(
          key,
          gap,
          selectedRow.money,
        ),
        supportingText: (
          `Forecast ${this.formatOperationalNumber(
            selectedRow,
            this.toFiniteNumber(metric?.projected_close),
          )} · `
          + `${key === 'bajas' ? 'Límite' : 'Meta'} `
          + this.formatOperationalNumber(
            selectedRow,
            this.toFiniteNumber(metric?.benchmark),
          )
        ),
      }));
  }

  private buildOperationalForecastSourceRows(): ControlDetailRow[] {
    const row = this.selectedOperationalForecastRow;
    if (!row) return [];

    return [
      {
        label: 'Módulo dueño',
        value: row.key === 'ingreso'
          ? 'Track / Centro de Forecast'
          : 'Track / Seguimiento Regional',
      },
      {
        label: 'Fuente canónica',
        value: 'track_daily_mart',
      },
      {
        label: 'Versión Track',
        value: this.operationalForecastData?.resolved_version
          ? `#${this.operationalForecastData.resolved_version.id}`
          : '—',
      },
      {
        label: 'Corte',
        value: this.operationalForecastData?.cutoff_date || this.cutoffDate,
      },
      {
        label: 'Método',
        value: this.operationalForecastMethodLabel(row.metric),
      },
      {
        label: 'Cobertura',
        value: `${row.metric.coverage.projected_available_branches}/${row.metric.coverage.total_branches} sucursales`,
      },
    ];
  }

  private operationalForecastMethodLabel(
    metric: ControlOperationalForecastMetric,
  ): string {
    const methods = metric.branch_methods || [];

    if (methods.length > 1) {
      return 'Mixto por sucursal';
    }

    const method = methods[0] || metric.method;

    switch (method) {
      case 'linear_mtd_pace':
        return 'Proyección lineal MTD';
      case 'existing_stable_historical_pace':
        return 'Avance histórico propio';
      case 'recent_valid_daily_average_7_calendar_days':
        return 'Promedio reciente · 7 días';
      case 'chain_daily_median_share_of_month_close':
        return 'Curva histórica por día';
      case 'sum_branch_operational_forecasts':
        return 'Suma de forecasts por sucursal';
      default:
        return String(method || '—');
    }
  }

  private formatOperationalNumber(
    row: ControlOperationalForecastRow,
    value: number | null,
  ): string {
    if (value === null || !Number.isFinite(value)) {
      return '—';
    }

    return row.money
      ? this.formatCurrency(value)
      : this.formatInteger(value);
  }

  private formatOperationalGapByKey(
    key: ControlOperationalForecastMetricKey,
    gap: number | null,
    money: boolean,
  ): string {
    if (gap === null || !Number.isFinite(gap)) {
      return '—';
    }

    if (key === 'bajas') {
      if (gap > 0) {
        return `+${this.formatInteger(gap)} sobre límite`;
      }
      if (gap < 0) {
        return `${this.formatInteger(Math.abs(gap))} de margen`;
      }
      return 'En límite';
    }

    return money
      ? this.formatSignedCurrency(gap)
      : this.formatSignedInteger(gap);
  }

  private remainingDaysInSelectedMonth(): number {
    const [year, month, day] = this.cutoffDate.split('-').map(Number);
    const lastDay = new Date(year, month, 0).getDate();
    return Math.max(lastDay - day, 0);
  }

  private buildHistoricalComparisonCard(
    label: string,
    period: ControlHistoricalComparisonPeriod,
    row: ControlOperationalForecastRow,
  ): ControlHistoricalComparisonCard {
    const mtd = this.describeHistoricalComparison(
      period.mtd,
      row,
    );
    const close = this.describeHistoricalComparison(
      period.close,
      row,
    );

    return {
      label,
      mtdLabel: 'MTD homologado',
      mtdValue: mtd.value,
      mtdDetail: mtd.detail,
      mtdTone: mtd.tone,
      closeLabel: 'Forecast vs cierre',
      closeValue: close.value,
      closeDetail: close.detail,
      closeTone: close.tone,
    };
  }

  private describeHistoricalComparison(
    comparison: ControlHistoricalComparisonValue,
    row: ControlOperationalForecastRow,
  ): {
    value: string;
    detail: string;
    tone: ControlVisualTone;
  } {
    const ratio = this.toFiniteNumber(comparison.change_ratio);
    const current = this.toFiniteNumber(comparison.current_comparable);
    const historical = this.toFiniteNumber(comparison.historical);
    const tone = this.historicalComparisonTone(row.key, ratio);
    const coverage = (
      `${comparison.comparable_branches}/`
      + `${comparison.total_current_branches} sucursales comparables`
    );
    const dateLabel = this.formatShortIsoDate(
      comparison.comparison_date,
    );

    if (comparison.status !== 'available') {
      return {
        value: 'N/D',
        detail: `Sin corte comparable para ${dateLabel}`,
        tone: 'neutral',
      };
    }

    return {
      value: this.formatSignedPercent(ratio),
      detail: (
        `${this.formatOperationalNumber(row, current)} vs `
        + `${this.formatOperationalNumber(row, historical)} · `
        + `${dateLabel} · ${coverage}`
      ),
      tone,
    };
  }

  private historicalComparisonTone(
    metricKey: ControlOperationalForecastMetricKey,
    ratio: number | null,
  ): ControlVisualTone {
    if (ratio === null || ratio === 0) {
      return 'neutral';
    }

    const favorable = metricKey === 'bajas'
      ? ratio < 0
      : ratio > 0;

    return favorable ? 'good' : 'attention';
  }

  private formatSignedPercent(
    value: number | null,
  ): string {
    if (value === null || !Number.isFinite(value)) {
      return '—';
    }

    const formatted = this.formatPercent(Math.abs(value));
    return value > 0
      ? `+${formatted}`
      : value < 0
        ? `-${formatted}`
        : formatted;
  }

  visualToneClass(tone: ControlVisualTone): string {
    return `visual-tone visual-tone--${tone}`;
  }

  private comparisonPercent(
    value: number | null,
    maxValue: number,
  ): number {
    if (
      value === null
      || value === 0
      || !Number.isFinite(value)
      || !Number.isFinite(maxValue)
      || maxValue <= 0
    ) {
      return 0;
    }

    return Math.max(
      2,
      Math.min(100, Math.abs(value) / maxValue * 100),
    );
  }

  private buildScopeOptions(
    context: ControlContextResponse,
    catalogs: TrackForecastCenterCatalogsResponse,
  ): ControlScopeOption[] {
    const authorized = context.access.authorized_scope;
    const options: ControlScopeOption[] = [];

    if (authorized.type === 'GLOBAL') {
      options.push({
        key: 'GLOBAL',
        label: 'Ultra total',
        request: { scopeType: 'GLOBAL' },
      });

      for (const region of catalogs.regions || []) {
        options.push({
          key: `REGION:${region.region_key}`,
          label: `Región · ${region.label}`,
          request: {
            scopeType: 'REGION',
            regionKey: region.region_key,
          },
        });
      }
    } else if (authorized.type === 'REGION') {
      const regionKey = authorized.region_keys[0];
      const region = (catalogs.regions || []).find(
        (item) => item.region_key === regionKey,
      );
      options.push({
        key: `REGION:${regionKey}`,
        label: region?.label || `Mi región · ${regionKey}`,
        request: {
          scopeType: 'REGION',
          regionKey,
        },
      });
    } else if (authorized.type === 'BRANCH_POOL') {
      options.push({
        key: 'BRANCH_POOL',
        label: 'Mi pool de sucursales',
        request: { scopeType: 'BRANCH_POOL' },
      });
    }

    const allowedBranchIds = authorized.type === 'GLOBAL'
      ? null
      : new Set(authorized.branch_ids);

    for (const branch of catalogs.branches || []) {
      if (allowedBranchIds && !allowedBranchIds.has(branch.sucursal_id)) {
        continue;
      }
      options.push({
        key: `BRANCH:${branch.sucursal_id}`,
        label: `Sucursal · ${branch.label}`,
        request: {
          scopeType: 'BRANCH',
          branchId: branch.sucursal_id,
        },
      });
    }

    if (authorized.type === 'BRANCH' && options.length === 0) {
      const branchId = authorized.branch_ids[0];
      options.push({
        key: `BRANCH:${branchId}`,
        label: `Mi sucursal · #${branchId}`,
        request: {
          scopeType: 'BRANCH',
          branchId,
        },
      });
    }

    return options;
  }

  private buildForecastParams(scope: ControlScope): TrackForecastCenterParams {
    const resolved = this.buildForecastScope(scope);
    return {
      track_date: this.cutoffDate,
      generation_mode: 'manual_preview',
      scope: resolved.scope,
      scope_id: resolved.scope_id,
      cohort: 'all',
      breakdown: resolved.scope === 'national' ? 'region' : 'none',
    };
  }

  private buildForecastScope(scope?: ControlScope | null): {
    scope: TrackForecastCenterParams['scope'];
    scope_id: string | null;
  } {
    if (!scope || scope.type === 'GLOBAL') {
      return { scope: 'national', scope_id: null };
    }

    if (scope.type === 'REGION') {
      return {
        scope: 'region',
        scope_id: scope.region_keys[0] || null,
      };
    }

    if (scope.type === 'BRANCH_POOL') {
      return { scope: 'authorized_pool', scope_id: null };
    }

    const branchId = scope.branch_ids[0];
    const branch = (this.catalogs?.branches || []).find(
      (item) => item.sucursal_id === branchId,
    );

    if (!branch) {
      return { scope: 'authorized_pool', scope_id: null };
    }

    return {
      scope: 'branch',
      scope_id: branch.sucursal_canon,
    };
  }

  private requestForEffectiveScope(scope: ControlScope): ControlContextRequest {
    if (scope.type === 'GLOBAL') {
      return { scopeType: 'GLOBAL' };
    }
    if (scope.type === 'REGION') {
      return {
        scopeType: 'REGION',
        regionKey: scope.region_keys[0] || null,
      };
    }
    if (scope.type === 'BRANCH_POOL') {
      return { scopeType: 'BRANCH_POOL' };
    }
    return {
      scopeType: 'BRANCH',
      branchId: scope.branch_ids[0] || null,
    };
  }

  private marketingBranchLeadToSaleRate(
    branch: MarketingSalesFunnelBranch,
  ): number | null {
    if (
      branch.leads_meta === null
      || branch.sales_digital === null
      || branch.leads_meta <= 0
    ) {
      return null;
    }
    return branch.sales_digital / branch.leads_meta;
  }

  private filterMarketingBranches(
    branches: MarketingSalesFunnelBranch[],
    scope?: ControlScope | null,
  ): MarketingSalesFunnelBranch[] {
    const operationalBranchIds = new Set(
      (this.catalogs?.branches || []).map((branch) => branch.sucursal_id),
    );

    if (!scope || scope.type === 'GLOBAL') {
      return branches.filter((branch) =>
        operationalBranchIds.has(branch.sucursal_id),
      );
    }

    const allowedScopeBranchIds = new Set(scope.branch_ids);
    return branches.filter((branch) =>
      operationalBranchIds.has(branch.sucursal_id)
      && allowedScopeBranchIds.has(branch.sucursal_id),
    );
  }

  private scopeContainsBranch(
    scope: ControlScope | null | undefined,
    branchId: number | null,
  ): boolean {
    if (!scope || scope.type === 'GLOBAL') return true;
    return branchId !== null && scope.branch_ids.includes(branchId);
  }

  private keyForScope(scope: ControlScope): string {
    if (scope.type === 'REGION') {
      return `REGION:${scope.region_keys[0] || ''}`;
    }
    if (scope.type === 'BRANCH') {
      return `BRANCH:${scope.branch_ids[0] || ''}`;
    }
    return scope.type;
  }

  private defaultScopeLabel(scope?: ControlScope | null): string {
    if (!scope) return 'Sin alcance';
    if (scope.type === 'GLOBAL') return 'Ultra total';
    if (scope.type === 'REGION') return `Región ${scope.region_keys[0] || ''}`;
    if (scope.type === 'BRANCH_POOL') return 'Mi pool de sucursales';
    return `Sucursal #${scope.branch_ids[0] || ''}`;
  }

  private resolveWeek(isoDate: string): { start: string; end: string } {
    const [year, month, day] = isoDate.split('-').map(Number);
    const date = new Date(year, month - 1, day, 12, 0, 0);
    const sunday = new Date(date);
    sunday.setDate(date.getDate() - date.getDay());
    const saturday = new Date(sunday);
    saturday.setDate(sunday.getDate() + 6);
    return {
      start: this.toDateOnly(sunday),
      end: this.toDateOnly(saturday),
    };
  }

  private toDateOnly(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private daysBetweenIsoDates(fromIso: string, toIso: string): number {
    const from = this.isoDateToUtcTimestamp(fromIso);
    const to = this.isoDateToUtcTimestamp(toIso);

    if (from === null || to === null) {
      return 0;
    }

    return Math.max(
      0,
      Math.round((to - from) / 86_400_000),
    );
  }

  private formatShortIsoDate(isoDate: string): string {
    const timestamp = this.isoDateToUtcTimestamp(isoDate);

    if (timestamp === null) {
      return isoDate;
    }

    return new Intl.DateTimeFormat('es-MX', {
      day: 'numeric',
      month: 'short',
      timeZone: 'UTC',
    })
      .format(new Date(timestamp))
      .replace('.', '');
  }

  private isoDateToUtcTimestamp(isoDate: string): number | null {
    const [year, month, day] = isoDate.split('-').map(Number);

    if (!year || !month || !day) {
      return null;
    }

    return Date.UTC(year, month - 1, day);
  }

  private getTodayIsoDate(): string {
    return this.toDateOnly(new Date());
  }

  private resolveError(error: any, fallback: string): string {
    return error?.error?.message
      || error?.error?.mensaje
      || error?.error?.error
      || fallback;
  }
}
