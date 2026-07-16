import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges } from '@angular/core';
import { EChartsCoreOption } from 'echarts/core';
import { NgxEchartsDirective } from 'ngx-echarts';

import { TrackForecastCenterResponse, TrackForecastCenterSeriesItem } from '../../services/track.service';

type PaceMode = 'goal' | 'projection';

@Component({
  selector: 'app-track-forecast-center-pace',
  standalone: true,
  imports: [CommonModule, NgxEchartsDirective],
  templateUrl: './track-forecast-center-pace.component.html',
  styleUrls: ['./track-forecast-center-pace.component.css'],
})
export class TrackForecastCenterPaceComponent implements OnChanges {
  @Input({ required: true }) response!: TrackForecastCenterResponse;

  mode: PaceMode = 'goal';
  cumulativeOption: EChartsCoreOption = {};
  dailyOption: EChartsCoreOption = {};
  coverageLabel = '';
  includedLabel = '';
  excludedLabel = '';
  statusLabel = '';
  remainingDaysLabel = '';
  requiredAverageLabel = '';
  explanation = '';

  ngOnChanges(): void {
    this.buildPresentation();
  }

  setMode(mode: PaceMode): void {
    this.mode = mode;
    this.buildPresentation();
  }

  private buildPresentation(): void {
    if (!this.response) return;
    const coverageSeries = this.mode === 'goal'
      ? this.response.series.pace_actual
      : this.response.series.projected;
    const coveragePoint = this.mode === 'goal'
      ? coverageSeries.points.find((point) => point.date === this.response.context.requested_track_date)
      : [...coverageSeries.points].reverse().find((point) => point.included_branch_count > 0);
    const included = coveragePoint?.included_branch_count ?? 0;
    const eligible = coveragePoint?.eligible_branch_count ?? this.response.quality.branches.selected;
    const excluded = coveragePoint?.excluded_branch_count ?? 0;
    this.coverageLabel = `${included} de ${eligible} sucursales`;
    this.includedLabel = `${included} incluidas`;
    this.excludedLabel = `${excluded} excluidas`;
    this.statusLabel = this.statusText(coveragePoint?.coverage.status ?? 'unavailable');
    this.remainingDaysLabel = `${this.response.summary.remaining_days} días restantes`;
    this.requiredAverageLabel = `${this.formatCurrency(this.response.summary.required_daily_average)} promedio diario requerido`;
    this.explanation = this.buildExplanation();
    this.cumulativeOption = this.buildChart('cumulative');
    this.dailyOption = this.buildChart('daily');
  }

  private buildChart(valueKey: 'daily' | 'cumulative'): EChartsCoreOption {
    const required = this.mode === 'goal'
      ? this.response.series.required
      : this.response.series.projection_required;
    const actual = this.mode === 'goal'
      ? this.response.series.pace_actual
      : this.response.series.projection_actual;
    const chartSeries = [
      this.series('Real', actual, valueKey, '#1769aa'),
      this.series('Requerido', required, valueKey, '#d97706'),
    ];
    if (this.mode === 'projection') {
      chartSeries.push(this.series('Proyectado', this.response.series.projected, valueKey, '#198754', true));
    }
    return {
      aria: { enabled: true },
      tooltip: { trigger: 'axis', valueFormatter: (value: number) => this.formatCurrency(value) },
      legend: { type: 'scroll', top: 0 },
      grid: { left: 70, right: 22, top: 48, bottom: 48 },
      xAxis: { type: 'category', data: required.points.map((point) => point.date) },
      yAxis: { type: 'value', axisLabel: { formatter: (value: number) => this.compactCurrency(value) } },
      series: chartSeries.map((item, index) => ({
        ...item,
        markLine: index === 0 ? {
          symbol: 'none',
          label: { formatter: 'Corte' },
          data: [{ xAxis: this.response.context.requested_track_date }],
        } : undefined,
      })),
    };
  }

  private series(
    name: string,
    series: TrackForecastCenterSeriesItem,
    key: 'daily' | 'cumulative',
    color: string,
    omitProjectedAnchor = false,
  ) {
    return {
      name,
      type: key === 'daily' ? 'bar' as const : 'line' as const,
      showSymbol: false,
      itemStyle: { color },
      lineStyle: { color, width: 2 },
      data: series.points.map((point) => {
        if (omitProjectedAnchor && key === 'daily' && point.date === this.response.context.requested_track_date) {
          return null;
        }
        return point[key];
      }),
    };
  }

  private buildExplanation(): string {
    if (this.mode === 'goal') {
      return 'El requerido marca el ritmo diario necesario de la meta; el real comparable muestra únicamente las sucursales que comparten ese universo.';
    }
    return 'El requerido representa la trayectoria de la meta comparable. El proyectado refleja el cierre estimado por el backend; una diferencia entre ambos indica que el ritmo proyectado no coincide con el necesario para alcanzar la meta.';
  }

  private statusText(status: string): string {
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
}
