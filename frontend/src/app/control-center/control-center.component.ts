import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subject, takeUntil } from 'rxjs';

import {
  TrackForecastCenterResponse,
  TrackGenerationMode,
  TrackRegionalOperationalResponse,
  TrackService,
} from '../services/track.service';

type RegionalPulseMetricKey =
  | 'clientes_nuevos'
  | 'reactivaciones'
  | 'domiciliados'
  | 'ingreso'
  | 'bajas';

type RegionalPulseMetricBehavior =
  | 'higher_is_better'
  | 'lower_is_better';

interface RegionalPulseMetricViewModel {
  metricKey: RegionalPulseMetricKey;
  label: string;
  behavior: RegionalPulseMetricBehavior;

  actualValue: string | null;
  benchmarkValue: string | null;
  actualPct: string | null;

  projectedClose: string | null;
  projectedPct: string | null;

  currentStatus: string;
  projectionStatus: string;
}

interface RegionalPulseBarGeometry {
  scaleMaxPct: number;
  benchmarkPositionPct: number;

  hasActual: boolean;
  hasProjection: boolean;

  actualWidthPct: number;
  projectedWidthPct: number;

  projectionExtensionLeftPct: number;
  projectionExtensionWidthPct: number;

  projectionDirection:
    | 'forward'
    | 'backward'
    | 'same'
    | 'unavailable';
}

interface RegionalPulseViewModel {
  regionKey: string;
  regionLabel: string;
  totalBranches: number;
  metrics: RegionalPulseMetricViewModel[];
}

@Component({
  selector: 'app-control-center',
  standalone: true,
  imports: [
    CommonModule,
  ],
  templateUrl: './control-center.component.html',
  styleUrls: ['./control-center.component.css'],
})
export class ControlCenterComponent implements OnInit, OnDestroy {
  readonly pageTitle = 'Centro de Control';
  readonly generationMode: TrackGenerationMode = 'manual_preview';

  data: TrackRegionalOperationalResponse | null = null;
  forecastData: TrackForecastCenterResponse | null = null;
  isForecastLoading = false;
  forecastErrorMessage = '';
  trackDate = '';
  isLoading = false;
  errorMessage = '';

  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly trackService: TrackService,
  ) {}

  ngOnInit(): void {
    this.trackDate = this.getTodayIsoDate();
    this.loadControlData();
    this.loadForecastData();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadControlData(): void {
    this.isLoading = true;
    this.errorMessage = '';

    this.trackService
      .getRegionalOperationalDetail(
        this.trackDate,
        this.generationMode,
      )
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.data = response;
          this.isLoading = false;
        },
        error: (error) => {
          console.error(
            'Error loading Suite Control data',
            error,
          );

          this.data = null;
          this.errorMessage = (
            error?.error?.error ||
            'No se pudo cargar la información del Centro de Control.'
          );
          this.isLoading = false;
        },
      });
  }

  getRegionalPulse(): RegionalPulseViewModel[] {
    return (this.data?.regions || []).map((region) => {
      const metrics = region.summary.metrics;

      return {
        regionKey: region.region_key,
        regionLabel: region.region_label,
        totalBranches: region.summary.total_branches,
        metrics: [
          {
            metricKey: 'clientes_nuevos',
            label: 'Venta nueva',
            behavior: 'higher_is_better',
            actualValue: metrics.clientes_nuevos.actual_mtd,
            benchmarkValue: metrics.clientes_nuevos.monthly_target,
            actualPct: metrics.clientes_nuevos.actual_progress_pct,
            projectedClose:
              metrics.clientes_nuevos.projection?.projected_close ??
              null,
            projectedPct:
              metrics.clientes_nuevos.projection
                ?.projected_compliance_pct ??
              null,
            currentStatus: metrics.clientes_nuevos.status,
            projectionStatus:
              metrics.clientes_nuevos.projection?.status ??
              'unavailable',
          },
          {
            metricKey: 'reactivaciones',
            label: 'Reactivaciones',
            behavior: 'higher_is_better',
            actualValue: metrics.reactivaciones.actual_mtd,
            benchmarkValue: metrics.reactivaciones.monthly_target,
            actualPct: metrics.reactivaciones.actual_progress_pct,
            projectedClose:
              metrics.reactivaciones.projection?.projected_close ??
              null,
            projectedPct:
              metrics.reactivaciones.projection
                ?.projected_compliance_pct ??
              null,
            currentStatus: metrics.reactivaciones.status,
            projectionStatus:
              metrics.reactivaciones.projection?.status ??
              'unavailable',
          },
          {
            metricKey: 'domiciliados',
            label: 'Domiciliados',
            behavior: 'higher_is_better',
            actualValue: metrics.domiciliados.actual_mtd,
            benchmarkValue: metrics.domiciliados.monthly_target,
            actualPct: metrics.domiciliados.compliance_pct,
            projectedClose:
              metrics.domiciliados.projection?.projected_close ??
              null,
            projectedPct: this.getProjectionString(
              metrics.domiciliados.projection,
              'projected_compliance_pct',
            ),
            currentStatus: metrics.domiciliados.status,
            projectionStatus:
              metrics.domiciliados.projection?.status ??
              'unavailable',
          },
          {
            metricKey: 'ingreso',
            label: 'Ingreso',
            behavior: 'higher_is_better',
            actualValue: metrics.ingreso.actual_mtd,
            benchmarkValue: metrics.ingreso.monthly_target,
            actualPct: metrics.ingreso.compliance_pct,
            projectedClose:
              metrics.ingreso.projection?.projected_close ??
              null,
            projectedPct: this.getProjectionString(
              metrics.ingreso.projection,
              'projected_compliance_pct',
            ),
            currentStatus: metrics.ingreso.status,
            projectionStatus:
              metrics.ingreso.projection?.status ??
              'unavailable',
          },
          {
            metricKey: 'bajas',
            label: 'Bajas',
            behavior: 'lower_is_better',
            actualValue: metrics.bajas.actual_mtd,
            benchmarkValue: metrics.bajas.monthly_limit,
            actualPct: metrics.bajas.limit_usage_pct,
            projectedClose:
              metrics.bajas.projection?.projected_close ??
              null,
            projectedPct:
              metrics.bajas.projection
                ?.projected_limit_usage_pct ??
              null,
            currentStatus: metrics.bajas.status,
            projectionStatus:
              metrics.bajas.projection?.status ??
              'unavailable',
          },
        ],
      };
    });
  }

  private getProjectionString(
    projection: unknown,
    key:
      | 'projected_compliance_pct'
      | 'projected_limit_usage_pct',
  ): string | null {
    if (
      !projection ||
      typeof projection !== 'object'
    ) {
      return null;
    }

    const value = (
      projection as Record<string, unknown>
    )[key];

    return typeof value === 'string'
      ? value
      : null;
  }

  formatPulsePercent(
    value: string | null,
  ): string {
    const numericValue =
      this.toOptionalFiniteNumber(value);

    if (numericValue === null) {
      return '—';
    }

    return new Intl.NumberFormat(
      'es-MX',
      {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      },
    ).format(numericValue) + '%';
  }

  formatPulseValue(
    metric: RegionalPulseMetricViewModel,
    value: string | null,
  ): string {
    const numericValue =
      this.toOptionalFiniteNumber(value);

    if (numericValue === null) {
      return '—';
    }

    if (metric.metricKey === 'ingreso') {
      return new Intl.NumberFormat(
        'es-MX',
        {
          style: 'currency',
          currency: 'MXN',
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        },
      ).format(numericValue);
    }

    return new Intl.NumberFormat(
      'es-MX',
      {
        maximumFractionDigits: 0,
      },
    ).format(numericValue);
  }

  getPulseBarGeometry(
    metric: RegionalPulseMetricViewModel,
  ): RegionalPulseBarGeometry {
    const scaleMaxPct = 125;
    const benchmarkPositionPct =
      this.toPulseVisualPosition(
        100,
        scaleMaxPct,
      );

    const actualPct = this.toOptionalFiniteNumber(
      metric.actualPct,
    );
    const projectedPct = this.toOptionalFiniteNumber(
      metric.projectedPct,
    );

    const hasActual = actualPct !== null;
    const hasProjection = projectedPct !== null;

    const actualWidthPct = hasActual
      ? this.toPulseVisualPosition(
          actualPct,
          scaleMaxPct,
        )
      : 0;

    const projectedWidthPct = hasProjection
      ? this.toPulseVisualPosition(
          projectedPct,
          scaleMaxPct,
        )
      : actualWidthPct;

    let projectionDirection:
      RegionalPulseBarGeometry['projectionDirection'] =
        'unavailable';

    if (hasProjection) {
      if (projectedWidthPct > actualWidthPct) {
        projectionDirection = 'forward';
      } else if (projectedWidthPct < actualWidthPct) {
        projectionDirection = 'backward';
      } else {
        projectionDirection = 'same';
      }
    }

    return {
      scaleMaxPct,
      benchmarkPositionPct,
      hasActual,
      hasProjection,
      actualWidthPct,
      projectedWidthPct,
      projectionExtensionLeftPct: Math.min(
        actualWidthPct,
        projectedWidthPct,
      ),
      projectionExtensionWidthPct: Math.abs(
        projectedWidthPct - actualWidthPct,
      ),
      projectionDirection,
    };
  }

  private toPulseVisualPosition(
    rawPct: number,
    scaleMaxPct: number,
  ): number {
    const clampedPct = Math.min(
      Math.max(rawPct, 0),
      scaleMaxPct,
    );

    return (
      clampedPct
      / scaleMaxPct
      * 100
    );
  }

  private toOptionalFiniteNumber(
    value: string | null | undefined,
  ): number | null {
    if (
      value === null ||
      value === undefined ||
      value.trim() === ''
    ) {
      return null;
    }

    const parsed = Number(value);

    return Number.isFinite(parsed)
      ? parsed
      : null;
  }

  getRegionalRadar(): Array<{
    regionKey: string;
    regionLabel: string;
    totalBranches: number;
    newClientsStatus: string;
    domiciliadosStatus: string;
    incomeStatus: string;
    incomeProjectionStatus: string;
  }> {
    return (this.data?.regions || []).map((region) => ({
      regionKey: region.region_key,
      regionLabel: region.region_label,
      totalBranches: region.summary.total_branches,
      newClientsStatus:
        region.summary.metrics.clientes_nuevos.status,
      domiciliadosStatus:
        region.summary.metrics.domiciliados.status,
      incomeStatus:
        region.summary.metrics.ingreso.status,
      incomeProjectionStatus:
        region.summary.metrics.ingreso.projection?.status ||
        'unavailable',
    }));
  }
  getRadarStatusPresentation(
    status: string | null | undefined,
  ): {
    label: string;
    tone: 'positive' | 'attention' | 'neutral' | 'muted';
  } {
    const presentations: Record<
      string,
      {
        label: string;
        tone: 'positive' | 'attention' | 'neutral' | 'muted';
      }
    > = {
      ADELANTADO: {
        label: 'Adelantado',
        tone: 'positive',
      },
      EN_RITMO: {
        label: 'En ritmo',
        tone: 'positive',
      },
      META_SUPERADA: {
        label: 'Meta superada',
        tone: 'positive',
      },
      DENTRO_LIMITE: {
        label: 'Dentro del límite',
        tone: 'positive',
      },
      DEBAJO_RITMO: {
        label: 'Debajo del ritmo',
        tone: 'attention',
      },
      DEBAJO_META: {
        label: 'Pendiente de meta',
        tone: 'attention',
      },
      LIMITE_EXCEDIDO: {
        label: 'Límite excedido',
        tone: 'attention',
      },
      SIN_META: {
        label: 'Sin meta',
        tone: 'muted',
      },
      DATOS_INSUFICIENTES: {
        label: 'Datos insuficientes',
        tone: 'muted',
      },
      INFORMATIVO: {
        label: 'Informativo',
        tone: 'neutral',
      },
      available: {
        label: 'Disponible',
        tone: 'positive',
      },
      insufficient_history: {
        label: 'Historia insuficiente',
        tone: 'muted',
      },
      unavailable: {
        label: 'No disponible',
        tone: 'muted',
      },
    };

    return (
      presentations[status || ''] || {
        label: status || 'Sin dato',
        tone: 'neutral',
      }
    );
  }
  getOperationalOverview(): {
    laggingNewClients: number;
    laggingDomiciliados: number;
    topNewClientsBranch: string | null;
    topDomiciliadosBranch: string | null;
  } {
    const groups = this.data?.priorities || [];

    const newClientsGroup = groups.find(
      (group) => group.metric_key === 'clientes_nuevos',
    );

    const domiciliadosGroup = groups.find(
      (group) => group.metric_key === 'domiciliados',
    );

    const laggingNewClients = (newClientsGroup?.items || []).filter(
      (item) => item.status === 'DEBAJO_RITMO',
    );

    const laggingDomiciliados = (domiciliadosGroup?.items || []).filter(
      (item) => item.status === 'DEBAJO_RITMO',
    );

    const topNewClients = [...laggingNewClients].sort(
      (a, b) =>
        Number(a.gap_pct_points ?? 0) -
        Number(b.gap_pct_points ?? 0),
    )[0];

    const topDomiciliados = [...laggingDomiciliados].sort(
      (a, b) =>
        Number(a.gap_pct_points ?? 0) -
        Number(b.gap_pct_points ?? 0),
    )[0];

    return {
      laggingNewClients: laggingNewClients.length,
      laggingDomiciliados: laggingDomiciliados.length,
      topNewClientsBranch: topNewClients?.sucursal_name || null,
      topDomiciliadosBranch: topDomiciliados?.sucursal_name || null,
    };
  }

  loadForecastData(): void {
    this.isForecastLoading = true;
    this.forecastErrorMessage = '';

    this.trackService
      .getForecastCenter({
        track_date: this.trackDate,
        generation_mode: this.generationMode,
        scope: 'national',
        scope_id: null,
        cohort: 'all',
        breakdown: 'cohort',
      })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.forecastData = response;
          this.isForecastLoading = false;
        },
        error: (error) => {
          console.error('Error loading Suite Control forecast data', error);
          this.forecastData = null;
          this.forecastErrorMessage = (
            error?.error?.error ||
            'No se pudo cargar la proyección nacional.'
          );
          this.isForecastLoading = false;
        },
      });
  }
  getControlCutoffContext(): {
    trackDateLabel: string;
    generationModeLabel: string;
    operationalBranches: number;
  } {
    const resolvedTrackDate =
      this.forecastData?.context.resolved_track_date ||
      this.trackDate;

    const resolvedGenerationMode =
      this.forecastData?.context.generation_mode ||
      this.generationMode;

    return {
      trackDateLabel: this.formatShortDate(resolvedTrackDate),
      generationModeLabel:
        resolvedGenerationMode === 'manual_preview'
          ? 'Preview operativo'
          : 'Cierre oficial',
      operationalBranches:
        this.forecastData?.summary.branch_count ?? 0,
    };
  }
  getDirectionOverview(): {
    totalBranches: number;
    realMtd: number | null;
    goalMonth: number | null;
    projectedClose: number | null;
    comparableGoal: number | null;
    projectedGap: number | null;
    projectedAttainment: number | null;
    projectionIncludedBranches: number;
    projectionEligibleBranches: number;
    projectionStatus: string;
    paceIncludedBranches: number;
    paceEligibleBranches: number;
    paceStatus: string;
    gapVsGoalPace: number | null;
    qualityStatus: string;
  } {
    const response = this.forecastData;

    if (!response) {
      return {
        totalBranches: 0,
        realMtd: null,
        goalMonth: null,
        projectedClose: null,
        comparableGoal: null,
        projectedGap: null,
        projectedAttainment: null,
        projectionIncludedBranches: 0,
        projectionEligibleBranches: 0,
        projectionStatus: 'unavailable',
        paceIncludedBranches: 0,
        paceEligibleBranches: 0,
        paceStatus: 'unavailable',
        gapVsGoalPace: null,
        qualityStatus: 'unavailable',
      };
    }

    const summary = response.summary;
    const projectionCoverage =
      summary.metric_coverage.projected_close;
    const paceCoverage =
      summary.metric_coverage.gap_vs_goal_pace;

    return {
      totalBranches: summary.branch_count,
      realMtd: summary.real_mtd,
      goalMonth: summary.goal_month,
      projectedClose:
        summary.projected_close_comparable_to_goal,
      comparableGoal:
        summary.goal_month_comparable_to_projection,
      projectedGap: summary.projected_gap_to_goal,
      projectedAttainment:
        summary.projected_goal_attainment_pct,
      projectionIncludedBranches:
        projectionCoverage.included_branch_count,
      projectionEligibleBranches:
        projectionCoverage.eligible_branch_count,
      projectionStatus: projectionCoverage.status,
      paceIncludedBranches:
        paceCoverage.included_branch_count,
      paceEligibleBranches:
        paceCoverage.eligible_branch_count,
      paceStatus: paceCoverage.status,
      gapVsGoalPace: summary.gap_vs_goal_pace,
      qualityStatus: response.quality.status,
    };
  }
  getRegionalOverview(): {
    totalRegions: number;
    totalBranches: number;
    laggingClientRegions: number;
    unavailableIncomeProjectionRegions: number;
  } {
    const regions = this.data?.regions || [];

    return {
      totalRegions: regions.length,
      totalBranches: regions.reduce(
        (total, region) => total + region.summary.total_branches,
        0,
      ),
      laggingClientRegions: regions.filter(
        (region) =>
          region.summary.metrics.clientes_nuevos.status === 'DEBAJO_RITMO',
      ).length,
      unavailableIncomeProjectionRegions: regions.filter(
        (region) =>
          region.summary.metrics.ingreso.projection?.status !== 'available',
      ).length,
    };
  }

  private formatShortDate(isoDate: string): string {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);

    if (!match) {
      return isoDate;
    }

    const months = [
      'ene',
      'feb',
      'mar',
      'abr',
      'may',
      'jun',
      'jul',
      'ago',
      'sep',
      'oct',
      'nov',
      'dic',
    ];

    const year = match[1];
    const monthIndex = Number(match[2]) - 1;
    const day = match[3];

    if (monthIndex < 0 || monthIndex >= months.length) {
      return isoDate;
    }

    return `${day} ${months[monthIndex]} ${year}`;
  }
  private getTodayIsoDate(): string {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
  }
}