import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges } from '@angular/core';
import { EChartsCoreOption } from 'echarts/core';
import { NgxEchartsDirective } from 'ngx-echarts';

import {
  TrackForecastCenterBreakdownItem,
  TrackForecastCenterMetricCoverage,
  TrackForecastCenterMetricKey,
  TrackForecastCenterResponse,
  TrackForecastCenterSeriesItem,
} from '../../services/track.service';

type ComparisonMode = 'goal' | 'projection';

interface SummaryCard {
  label: string;
  value: string;
  secondary: string[];
  coverage: string;
  tone: 'neutral' | 'positive' | 'negative';
}

interface CohortCard {
  label: string;
  branchCount: string;
  goal: string;
  real: string;
  gap: string;
  projection: string;
  attainment: string;
  quality: string;
  coverage: string;
  method: string;
  methodCoverage: string;
  methodReason: string;
}

@Component({
  selector: 'app-track-forecast-center-summary',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective],
  templateUrl: './track-forecast-center-summary.component.html',
  styleUrls: ['./track-forecast-center-summary.component.css'],
})
export class TrackForecastCenterSummaryComponent implements OnChanges {
  @Input({ required: true }) response!: TrackForecastCenterResponse;

  comparisonMode: ComparisonMode = 'goal';
  cards: SummaryCard[] = [];
  cohortCards: CohortCard[] = [];
  executiveMessage = '';
  chartOption: EChartsCoreOption = {};
  chartCoverageNote = '';
  chartMethodologyNote = '';

  ngOnChanges(): void {
    this.buildPresentation();
  }

  setComparisonMode(mode: ComparisonMode): void {
    this.comparisonMode = mode;
    this.buildChart();
  }

  private buildPresentation(): void {
    if (!this.response) {
      return;
    }
    const summary = this.response.summary;
    this.cards = [
      this.card('Meta mensual total', summary.goal_month, 'goal_month'),
      this.card('Real operativo total', summary.real_mtd, 'real_mtd'),
      this.card('Real comparable contra ritmo', summary.real_mtd_comparable_to_pace, 'real_mtd_comparable_to_pace'),
      this.card('Ritmo esperado al corte', summary.goal_expected_mtd_at_cutoff, 'goal_expected_mtd_at_cutoff'),
      this.card(
        'Brecha contra ritmo',
        summary.gap_vs_goal_pace,
        'gap_vs_goal_pace',
        this.formatPercent(summary.gap_vs_goal_pace_pct),
      ),
      this.projectionCard(),
      this.card(
        'Meta comparable a proyección',
        summary.goal_month_comparable_to_projection,
        'goal_month_comparable_to_projection',
      ),
      this.card(
        'Cumplimiento proyectado comparable',
        summary.projected_goal_attainment_pct,
        'projected_goal_attainment_pct',
        `Brecha ${this.formatCurrency(summary.projected_gap_to_goal)}`,
        true,
      ),
    ];
    this.executiveMessage = this.buildExecutiveMessage();
    this.cohortCards = this.response.breakdown.dimension === 'cohort'
      ? this.response.breakdown.items.map((item) => this.toCohortCard(item))
      : [];
    this.buildChart();
  }

  private card(
    label: string,
    value: number | null,
    metric: Exclude<TrackForecastCenterMetricKey, 'remaining_days'>,
    secondary = '',
    percentValue = false,
  ): SummaryCard {
    const coverage = this.response.summary.metric_coverage[metric];
    return {
      label,
      value: percentValue ? this.formatPercent(value) : this.formatCurrency(value),
      secondary: secondary ? [secondary] : [],
      coverage: this.formatCoverage(coverage),
      tone: value === null ? 'neutral' : value < 0 ? 'negative' : 'neutral',
    };
  }

  private toCohortCard(item: TrackForecastCenterBreakdownItem): CohortCard {
    const summary = item.summary;
    const projectionCoverage = item.metric_coverage.projected_close_comparable_to_goal;
    return {
      label: item.label,
      branchCount: `${item.branch_count} sucursales`,
      goal: this.formatCurrency(summary.goal_month),
      real: this.formatCurrency(summary.real_mtd),
      gap: this.formatCurrency(summary.gap_vs_goal_pace),
      projection: summary.projected_close_comparable_to_goal === null
        ? 'Proyección no disponible'
        : this.formatCurrency(summary.projected_close_comparable_to_goal),
      attainment: summary.projected_goal_attainment_pct === null
        ? '—'
        : this.formatPercent(summary.projected_goal_attainment_pct),
      quality: this.statusLabel(item.quality_status),
      coverage: this.formatCoverage(projectionCoverage),
      method: this.cohortMethodLabel(item),
      methodCoverage: this.cohortMethodCoverage(item),
      methodReason: this.cohortMethodReason(item),
    };
  }

  private projectionCard(): SummaryCard {
    const summary = this.response.summary;
    const methods = this.response.quality.projection_methods;
    const historical = methods.branch_historical_calendar_weights.branch_count;
    const linear = methods.linear_mtd_pace.branch_count;
    const provisional = methods.legacy_21_calendar_weights.branch_count;
    const unavailable = methods.unavailable.branch_count;
    const projected = historical + linear + provisional;
    const total = projected + unavailable;
    const referenceBranches = this.response.quality.legacy_21_curve.contributing_branch_count;

    let label = 'Proyección estimada total';
    let secondary: string[] = [];

    if (historical > 0) {
      secondary.push(`${historical} sucursales con proyección histórica`);
    }
    if (linear > 0) {
      secondary.push(`${linear} sucursales con proyección lineal`);
    }
    if (provisional > 0) {
      secondary.push(`${provisional} sucursales con patrón Ultra provisional`);
    }

    if (historical > 0 && linear === 0 && provisional === 0) {
      label = 'Proyección de cierre';
      secondary = [
        `${historical} de ${total} sucursales con proyección histórica.`,
      ];
    } else if (linear > 0 && historical === 0 && provisional === 0) {
      label = 'Proyección lineal';
      secondary = [
        `${linear} de ${total} sucursales proyectadas según su ritmo real MTD.`,
      ];
    } else if (provisional > 0 && historical === 0 && linear === 0) {
      label = 'Proyección provisional con patrón Ultra';
      secondary = [
        `Basada en la distribución histórica diaria de las ${referenceBranches} sucursales maduras.`,
        `${projected} de ${total} sucursales estimadas · Sin histórico propio comparable.`,
      ];
    }

    if (unavailable > 0) {
      secondary.push(`${unavailable} sucursales sin proyección disponible.`);
    }

    const coverage = summary.metric_coverage.projected_close_comparable_to_goal;
    return {
      label,
      value: this.formatCurrency(summary.projected_close_comparable_to_goal),
      secondary,
      coverage: this.formatCoverage(coverage),
      tone: 'neutral',
    };
  }

  private buildExecutiveMessage(): string {
    const summary = this.response.summary;
    const methods = this.response.quality.projection_methods;
    const historical = methods.branch_historical_calendar_weights.branch_count;
    const linear = methods.linear_mtd_pace.branch_count;
    const provisional = methods.legacy_21_calendar_weights.branch_count;
    const branchCount = this.response.summary.branch_count;
    const projected = this.formatCurrency(summary.projected_close_comparable_to_goal);
    const attainment = this.formatPercent(summary.projected_goal_attainment_pct);

    if (
      this.response.context.cohort === 'new_gyms'
      && linear > 0
      && historical === 0
      && provisional === 0
    ) {
      return `Las ${branchCount} sucursales nuevas proyectan cerrar en ${projected}, equivalente a ${attainment} de su meta. La proyección es lineal y utiliza el ritmo real MTD de cada sucursal.`;
    }

    if (
      this.response.context.cohort === 'new_gyms'
      && provisional > 0
      && historical === 0
      && linear === 0
    ) {
      const referenceBranches = this.response.quality.legacy_21_curve.contributing_branch_count;
      return `Las ${branchCount} sucursales nuevas proyectan cerrar en ${projected}, equivalente a ${attainment} de su meta. La estimación es provisional y utiliza el patrón calendario histórico de ${referenceBranches} Gyms.`;
    }

    const methodsUsed: string[] = [];
    if (historical > 0) {
      methodsUsed.push(`${historical} proyecciones históricas`);
    }
    if (linear > 0) {
      methodsUsed.push(`${linear} proyecciones lineales`);
    }
    if (provisional > 0) {
      methodsUsed.push(`${provisional} estimaciones provisionales con patrón Ultra`);
    }

    const scopeLabel = this.response.context.scope === 'national'
      ? 'Total Ultra'
      : 'El alcance';

    if (methodsUsed.length > 1) {
      return `${scopeLabel} proyecta cerrar en ${projected}, equivalente a ${attainment} de la meta. La estimación combina ${methodsUsed.join(', ')}.`;
    }

    if (linear > 0) {
      return `${scopeLabel} proyecta cerrar en ${projected}, equivalente a ${attainment} de la meta, mediante proyección lineal basada en el ritmo real MTD de ${linear} sucursales.`;
    }

    if (provisional > 0) {
      return `${scopeLabel} proyecta cerrar en ${projected}, equivalente a ${attainment} de la meta. La estimación es provisional y utiliza el patrón diario de las sucursales maduras.`;
    }

    return `${scopeLabel} proyecta cerrar en ${projected}, equivalente a ${attainment} de la meta, mediante proyección histórica de ${historical} sucursales.`;
  }

  private buildChart(): void {
    const isGoal = this.comparisonMode === 'goal';
    const series = isGoal
      ? [
          this.line('Real comparable', this.response.series.pace_actual, '#1769aa'),
          this.line('Ritmo requerido', this.response.series.required, '#d97706'),
        ]
      : [
          this.line('Real proyectable', this.response.series.projection_actual, '#1769aa'),
          this.line('Meta comparable', this.response.series.projection_required, '#d97706'),
          this.line('Proyección', this.response.series.projected, '#198754'),
        ];
    const coverageSeries = isGoal
      ? this.response.series.pace_actual
      : this.response.series.projected;
    const coveragePoint = this.findCoveragePoint(coverageSeries, isGoal);
    this.chartCoverageNote = coveragePoint
      ? `Comparación basada en ${coveragePoint.included_branch_count} de ${coveragePoint.eligible_branch_count} sucursales.`
      : 'Comparación sin cobertura disponible.';
    this.chartMethodologyNote = isGoal ? '' : this.projectionMethodologyNote();
    this.chartOption = {
      aria: { enabled: true },
      color: series.map((item) => item.lineStyle.color),
      tooltip: { trigger: 'axis', valueFormatter: (value: number) => this.formatCurrency(value) },
      legend: { type: 'scroll', top: 0 },
      grid: { left: 70, right: 24, top: 48, bottom: 48 },
      xAxis: { type: 'category', data: this.response.series.required.points.map((point) => point.date) },
      yAxis: { type: 'value', axisLabel: { formatter: (value: number) => this.compactCurrency(value) } },
      series: series.map((item, index) => ({
        ...item,
        markLine: index === 0 ? {
          symbol: 'none',
          label: { formatter: 'Corte' },
          data: [{ xAxis: this.response.context.requested_track_date }],
        } : undefined,
      })),
    };
  }

  private projectionMethodologyNote(): string {
    const methods = this.response.quality.projection_methods;
    const historical = methods.branch_historical_calendar_weights.branch_count;
    const linear = methods.linear_mtd_pace.branch_count;
    const provisional = methods.legacy_21_calendar_weights.branch_count;

    if (
      this.response.context.cohort === 'new_gyms'
      && linear > 0
      && historical === 0
      && provisional === 0
    ) {
      return `Proyección lineal basada en el ritmo real MTD de ${linear} sucursales.`;
    }

    if (
      this.response.context.cohort === 'new_gyms'
      && provisional > 0
      && historical === 0
      && linear === 0
    ) {
      const referenceBranches = this.response.quality.legacy_21_curve.contributing_branch_count;
      return `Proyección provisional basada en el patrón calendario de las ${referenceBranches} sucursales maduras.`;
    }

    const parts: string[] = [];
    if (historical > 0) {
      parts.push(`${historical} históricas`);
    }
    if (linear > 0) {
      parts.push(`${linear} lineales`);
    }
    if (provisional > 0) {
      parts.push(`${provisional} provisionales con patrón Ultra`);
    }

    return parts.length > 1
      ? `Proyección compuesta por ${parts.join(', ')}.`
      : '';
  }

  private cohortMethodLabel(item: TrackForecastCenterBreakdownItem): string {
    const historical = item.projection_methods.branch_historical_calendar_weights.branch_count;
    const linear = item.projection_methods.linear_mtd_pace.branch_count;
    const provisional = item.projection_methods.legacy_21_calendar_weights.branch_count;

    const methodCount = [
      historical > 0,
      linear > 0,
      provisional > 0,
    ].filter(Boolean).length;

    if (methodCount > 1) return 'Metodología mixta';
    if (historical > 0) return 'Proyección histórica';
    if (linear > 0) return 'Proyección lineal';
    if (provisional > 0) return 'Proyección provisional con patrón Ultra';
    return 'Sin proyección';
  }

  private cohortMethodCoverage(item: TrackForecastCenterBreakdownItem): string {
    const historical = item.projection_methods.branch_historical_calendar_weights.projected_branch_count;
    const linear = item.projection_methods.linear_mtd_pace.projected_branch_count;
    const provisional = item.projection_methods.legacy_21_calendar_weights.projected_branch_count;
    const projected = historical + linear + provisional;

    if (historical > 0 && linear === 0 && provisional === 0) {
      return `${historical} de ${item.branch_count} sucursales con proyección histórica`;
    }

    if (linear > 0 && historical === 0 && provisional === 0) {
      return `${linear} de ${item.branch_count} sucursales con proyección lineal`;
    }

    return `${projected} de ${item.branch_count} sucursales proyectadas`;
  }

  private cohortMethodReason(item: TrackForecastCenterBreakdownItem): string {
    return item.projection_methods.legacy_21_calendar_weights.branch_count > 0
      ? 'Sin histórico propio comparable'
      : '';
  }

  private line(name: string, series: TrackForecastCenterSeriesItem, color: string) {
    return {
      name,
      type: 'line' as const,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 2, color },
      data: series.points.map((point) => point.cumulative),
    };
  }

  private findCoveragePoint(series: TrackForecastCenterSeriesItem, cutoff: boolean) {
    if (cutoff) {
      return series.points.find((point) => point.date === this.response.context.requested_track_date);
    }
    return [...series.points].reverse().find((point) => point.included_branch_count > 0);
  }

  private formatCoverage(coverage: TrackForecastCenterMetricCoverage): string {
    return `${coverage.included_branch_count} de ${coverage.eligible_branch_count} sucursales`;
  }

  private statusLabel(status: string): string {
    if (status === 'available') return 'Disponible';
    if (status === 'partial') return 'Cobertura parcial';
    return 'No disponible';
  }

  private formatCurrency(value: number | null): string {
    if (value === null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(value);
  }

  private compactCurrency(value: number): string {
    return new Intl.NumberFormat('es-MX', { notation: 'compact', style: 'currency', currency: 'MXN', maximumFractionDigits: 1 }).format(value);
  }

  private formatPercent(value: number | null): string {
    if (value === null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value);
  }
}

