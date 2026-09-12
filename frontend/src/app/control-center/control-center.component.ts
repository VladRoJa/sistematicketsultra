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
  MarketingBranchMetrics,
  MarketingDashboardResponse,
} from '../marketing-conversion/marketing.models';
import {
  MaintenancePlannerBoard,
  MaintenancePlannerTicket,
} from '../maintenance-planner/maintenance-planner.service';
import {
  ControlCenterService,
  ControlContextRequest,
  ControlContextResponse,
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
  sales: number;
  salesRevenue: number;
  leadToVisitRate: number | null;
  visitToSaleRate: number | null;
  leadToSaleRate: number | null;
  branches: MarketingBranchMetrics[];
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

  cutoffDate = this.getTodayIsoDate();
  context: ControlContextResponse | null = null;
  catalogs: TrackForecastCenterCatalogsResponse | null = null;
  forecastData: TrackForecastCenterResponse | null = null;
  marketingData: MarketingDashboardResponse | null = null;
  retentionData: ControlRetentionResponse | null = null;
  maintenanceData: MaintenancePlannerBoard | null = null;

  scopeOptions: ControlScopeOption[] = [];
  selectedScopeKey = '';
  selectedMetric: ControlMetricKey = 'forecast';
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
    return this.selectedMetric !== 'retention';
  }

  get scopeLabel(): string {
    const selected = this.scopeOptions.find(
      (option) => option.key === this.selectedScopeKey,
    );
    return selected?.label || this.defaultScopeLabel(this.context?.effective_scope);
  }

  get metricCards(): ControlMetricCard[] {
    const forecast = this.forecastData?.summary;
    const marketing = this.marketingOverview;
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
        title: 'Lead → venta',
        value: this.formatPercent(conversion),
        supportingText: marketing.leads === null
          ? 'Leads no disponibles para el alcance actual'
          : `${this.formatInteger(marketing.sales)} ventas de ${this.formatInteger(marketing.leads)} leads`,
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

  get attentionItems(): Array<{
    metric: ControlMetricKey;
    title: string;
    text: string;
  }> {
    const items: Array<{
      metric: ControlMetricKey;
      title: string;
      text: string;
    }> = [];

    const forecastGap = this.forecastData?.summary.projected_gap_to_goal ?? null;
    if (forecastGap !== null && forecastGap < 0) {
      items.push({
        metric: 'forecast',
        title: 'Forecast debajo de meta',
        text: `Brecha proyectada ${this.formatSignedCurrency(forecastGap)}.`,
      });
    }

    const retention = this.retentionData?.summary;
    if (
      retention?.limit_usage_ratio !== null
      && retention?.limit_usage_ratio !== undefined
      && retention.limit_usage_ratio > 1
    ) {
      items.push({
        metric: 'retention',
        title: 'Bajas por encima del límite',
        text: `${this.formatPercent(retention.limit_usage_ratio)} de la meta/límite mensual consumido.`,
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

    if (this.marketingData?.data_quality.cohort_complete === false) {
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
    this.selectedLevel = 'summary';
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
      void this.router.navigate(['/marketing-conversion']);
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
      marketing: this.controlService.getMarketing(month),
      retention: this.controlService.getRetention({
        ...scopeRequest,
        cutoffDate: this.cutoffDate,
      }),
      maintenance: this.controlService.getMaintenance(week.start, week.end),
    })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: ({ forecast, marketing, retention, maintenance }) => {
          this.forecastData = forecast;
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

    if (scope?.type === 'GLOBAL') {
      return {
        leads: dashboard.summary.leads,
        visits: dashboard.summary.visits,
        sales: dashboard.summary.sales,
        salesRevenue: dashboard.summary.sales_revenue,
        leadToVisitRate: dashboard.summary.lead_to_visit_rate,
        visitToSaleRate: dashboard.summary.visit_to_sale_rate,
        leadToSaleRate: dashboard.summary.lead_to_sale_rate,
        branches,
      };
    }

    const leadsValues = branches
      .map((branch) => branch.leads)
      .filter((value): value is number => value !== null && value !== undefined);
    const leads = leadsValues.length === branches.length
      ? leadsValues.reduce((total, value) => total + value, 0)
      : null;
    const visits = branches.reduce((total, branch) => total + branch.visits, 0);
    const sales = branches.reduce((total, branch) => total + branch.sales, 0);
    const salesRevenue = branches.reduce(
      (total, branch) => total + branch.sales_revenue,
      0,
    );

    return {
      leads,
      visits,
      sales,
      salesRevenue,
      leadToVisitRate: leads && leads > 0 ? visits / leads : null,
      visitToSaleRate: visits > 0 ? sales / visits : null,
      leadToSaleRate: leads && leads > 0 ? sales / leads : null,
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
    const forecast = this.forecastData?.summary;
    const marketing = this.marketingOverview;
    const retention = this.retentionData?.summary;
    const maintenance = this.maintenanceOverview;

    switch (this.selectedMetric) {
      case 'forecast':
        return [
          {
            label: 'Proyección',
            value: this.formatCurrency(forecast?.projected_close_comparable_to_goal),
          },
          {
            label: 'Meta comparable',
            value: this.formatCurrency(forecast?.goal_month_comparable_to_projection),
          },
          {
            label: 'Brecha proyectada',
            value: this.formatSignedCurrency(forecast?.projected_gap_to_goal),
          },
          {
            label: 'Cumplimiento proyectado',
            value: this.formatPercent(forecast?.projected_goal_attainment_pct),
          },
        ];
      case 'conversion':
        return [
          { label: 'Lead → venta', value: this.formatPercent(marketing.leadToSaleRate) },
          { label: 'Lead → visita', value: this.formatPercent(marketing.leadToVisitRate) },
          { label: 'Visita → venta', value: this.formatPercent(marketing.visitToSaleRate) },
          { label: 'Leads', value: marketing.leads === null ? '—' : this.formatInteger(marketing.leads) },
          { label: 'Ventas atribuidas', value: this.formatInteger(marketing.sales) },
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
    const forecast = this.forecastData?.summary;
    const marketing = this.marketingOverview;
    const retention = this.retentionData?.summary;
    const maintenance = this.maintenanceOverview;

    switch (this.selectedMetric) {
      case 'forecast':
        return [
          {
            label: 'Real MTD',
            value: this.formatCurrency(forecast?.real_mtd),
            supportingText: 'Ingreso real acumulado al corte.',
          },
          {
            label: 'Ritmo vs meta',
            value: this.formatSignedCurrency(forecast?.gap_vs_goal_pace),
            supportingText: 'Diferencia contra lo que debería llevarse al día de corte.',
          },
          {
            label: 'Proyección de cierre',
            value: this.formatCurrency(forecast?.projected_close_comparable_to_goal),
            supportingText: 'Cierre estimado comparable con la meta mensual.',
          },
        ];
      case 'conversion':
        return [
          { label: 'Leads', value: marketing.leads === null ? '—' : this.formatInteger(marketing.leads) },
          { label: 'Visitas', value: this.formatInteger(marketing.visits) },
          { label: 'Ventas', value: this.formatInteger(marketing.sales) },
          { label: 'Lead → visita', value: this.formatPercent(marketing.leadToVisitRate) },
          { label: 'Visita → venta', value: this.formatPercent(marketing.visitToSaleRate) },
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
      const items = this.forecastData?.breakdown?.items || [];
      if (items.length > 0) {
        return [...items]
          .sort((a, b) =>
            Number(a.summary.projected_gap_to_goal ?? 0)
            - Number(b.summary.projected_gap_to_goal ?? 0),
          )
          .slice(0, 8)
          .map((item) => ({
            label: item.label,
            value: this.formatSignedCurrency(item.summary.projected_gap_to_goal),
            supportingText: `Proyección ${this.formatCurrency(item.summary.projected_close_comparable_to_goal)}`,
          }));
      }

      return [{
        label: this.scopeLabel,
        value: this.formatSignedCurrency(
          this.forecastData?.summary.projected_gap_to_goal,
        ),
        supportingText: 'El alcance actual ya está en el nivel más bajo disponible para este resumen.',
      }];
    }

    if (this.selectedMetric === 'conversion') {
      return [...this.marketingOverview.branches]
        .sort((a, b) =>
          (a.lead_to_sale_rate ?? Number.POSITIVE_INFINITY)
          - (b.lead_to_sale_rate ?? Number.POSITIVE_INFINITY),
        )
        .slice(0, 8)
        .map((branch) => ({
          label: branch.sucursal,
          value: this.formatPercent(branch.lead_to_sale_rate),
          supportingText: `${branch.leads === null ? '—' : this.formatInteger(branch.leads)} leads · ${this.formatInteger(branch.sales)} ventas`,
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
        return [
          { label: 'Módulo dueño', value: 'Track / Centro de Forecast' },
          { label: 'Corte', value: this.forecastData?.context.resolved_track_date || this.cutoffDate },
          { label: 'Alcance', value: this.scopeLabel },
          { label: 'Contrato', value: 'Forecast Center' },
        ];
      case 'conversion':
        return [
          { label: 'Módulo dueño', value: 'Marketing y Conversión' },
          { label: 'Mes', value: this.marketingData?.month || this.cutoffDate.slice(0, 7) },
          { label: 'Alcance', value: this.scopeLabel },
          { label: 'Cohorte', value: this.marketingData?.cohort_mode || '—' },
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

  private filterMarketingBranches(
    branches: MarketingBranchMetrics[],
    scope?: ControlScope | null,
  ): MarketingBranchMetrics[] {
    if (!scope || scope.type === 'GLOBAL') {
      return [...branches];
    }
    const allowed = new Set(scope.branch_ids);
    return branches.filter((branch) => allowed.has(branch.sucursal_id));
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
