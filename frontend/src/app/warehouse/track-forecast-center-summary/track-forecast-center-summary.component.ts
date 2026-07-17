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
  secondary: string;
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
      this.card(
        'Proyección comparable',
        summary.projected_close_comparable_to_goal,
        'projected_close_comparable_to_goal',
        'Universo con proyección disponible',
      ),
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
      secondary,
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
    };
  }

  private buildExecutiveMessage(): string {
    const summary = this.response.summary;
    const paceCoverage = summary.metric_coverage.real_mtd_comparable_to_pace;
    const projectionCoverage = summary.metric_coverage.projected_close_comparable_to_goal;
    return `El alcance lleva ${this.formatCurrency(summary.real_mtd_comparable_to_pace)} frente a un ritmo esperado de ${this.formatCurrency(summary.goal_expected_mtd_at_cutoff)} en ${this.formatCoverage(paceCoverage)}. Las sucursales proyectables estiman cerrar en ${this.formatCurrency(summary.projected_close_comparable_to_goal)}, equivalente a ${this.formatPercent(summary.projected_goal_attainment_pct)} de su meta comparable (${this.formatCoverage(projectionCoverage)}).`;
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

