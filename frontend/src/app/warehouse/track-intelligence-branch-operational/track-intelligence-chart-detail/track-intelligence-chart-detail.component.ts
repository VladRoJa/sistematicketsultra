import { CommonModule } from '@angular/common';
import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
} from '@angular/core';

import {
  TrackBranchOperationalChartComparisonMetric,
  TrackBranchOperationalChartComparisonPeriod,
  TrackBranchOperationalChartComparisonPeriodKey,
} from '../../../services/track.service';


export interface TrackIntelligenceChartDetailMarker {
  x: number;
  y: number;
  label: string;
}

export interface TrackIntelligenceChartDetailAxisLabel {
  x: number;
  label: string;
}

export interface TrackIntelligenceChartDetailYAxisTick {
  y: number;
  label: string;
}

export interface TrackIntelligenceChartDetailSeriesPoint {
  day: number;
  date: string;
  value: number;
  label: string;
}

export interface TrackIntelligenceChartDetailView {
  title: string;
  daysInMonth: number;
  actualPoints: string;
  benchmarkPoints: string;
  projectionPoints: string;
  actualSeries: TrackIntelligenceChartDetailSeriesPoint[];
  benchmarkSeries: TrackIntelligenceChartDetailSeriesPoint[];
  projectionSeries: TrackIntelligenceChartDetailSeriesPoint[];
  actualMarkers: TrackIntelligenceChartDetailMarker[];
  benchmarkMarkers: TrackIntelligenceChartDetailMarker[];
  projectionMarkers: TrackIntelligenceChartDetailMarker[];
  axisLabels: TrackIntelligenceChartDetailAxisLabel[];
  yAxisTicks: TrackIntelligenceChartDetailYAxisTick[];
  benchmarkLabel: string | null;
}

export interface TrackIntelligenceChartDetailKpi {
  label: string;
  value: string;
  emphasis?: boolean;
}

export interface TrackIntelligenceChartDetailContext {
  branchLabel: string;
  metricLabel: string;
  cutoffLabel: string;
  targetMonthLabel: string;
  generationLabel: string;
  versionLabel: string;
  kpis: TrackIntelligenceChartDetailKpi[];
}

type HistoricalPeriodKey = Exclude<
  TrackBranchOperationalChartComparisonPeriodKey,
  'current_month'
>;

interface TrackIntelligenceChartDetailExpandedMarker
  extends TrackIntelligenceChartDetailMarker {
  day: number;
}

interface TrackIntelligenceChartDetailValueLabel {
  day: number;
  x: number;
  y: number;
  text: string;
  placement: 'above' | 'below';
}

interface TrackIntelligenceChartDetailHistoricalSeries {
  periodKey: HistoricalPeriodKey;
  label: string;
  classModifier: 'previous-month' | 'previous-year';
  segments: string[];
  markers: TrackIntelligenceChartDetailExpandedMarker[];
}

interface TrackIntelligenceChartDetailExpandedView {
  actualPoints: string;
  benchmarkPoints: string;
  projectionPoints: string;
  actualMarkers: TrackIntelligenceChartDetailMarker[];
  benchmarkMarkers: TrackIntelligenceChartDetailMarker[];
  projectionMarkers: TrackIntelligenceChartDetailMarker[];
  actualValueLabels: TrackIntelligenceChartDetailValueLabel[];
  historicalSeries: TrackIntelligenceChartDetailHistoricalSeries[];
  selectedHistoricalSeries: TrackIntelligenceChartDetailHistoricalSeries | null;
  selectedHistoricalValueLabels: TrackIntelligenceChartDetailValueLabel[];
  axisLabels: TrackIntelligenceChartDetailAxisLabel[];
  yAxisTicks: TrackIntelligenceChartDetailYAxisTick[];
}

interface TrackIntelligenceChartDetailComparisonSummary {
  periodKey: HistoricalPeriodKey;
  label: string;
  periodLabel: string;
  comparisonDayLabel: string;
  value: string;
  available: boolean;
}


@Component({
  selector: 'app-track-intelligence-chart-detail',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './track-intelligence-chart-detail.component.html',
  styleUrls: ['./track-intelligence-chart-detail.component.css'],
})
export class TrackIntelligenceChartDetailComponent {
  @Input() chart: TrackIntelligenceChartDetailView | null = null;
  @Input() context: TrackIntelligenceChartDetailContext | null = null;
  @Input() comparisons: TrackBranchOperationalChartComparisonMetric | null = null;
  @Input() comparisonPeriods: Record<
    TrackBranchOperationalChartComparisonPeriodKey,
    TrackBranchOperationalChartComparisonPeriod
  > | null = null;
  @Output() readonly closeDetail = new EventEmitter<void>();

  showPreviousMonth = false;
  showPreviousYearSameMonth = false;
  selectedHistoricalPeriod: HistoricalPeriodKey | null = null;
  expandedChart: TrackIntelligenceChartDetailExpandedView | null = null;
  comparisonSummaries: TrackIntelligenceChartDetailComparisonSummary[] = [];

  ngOnChanges(changes: SimpleChanges): void {
    const comparisonChange = changes['comparisons'];
    const previousMetric = comparisonChange?.previousValue?.metric_key;
    const currentMetric = comparisonChange?.currentValue?.metric_key;

    if (previousMetric && currentMetric && previousMetric !== currentMetric) {
      this.showPreviousMonth = false;
      this.showPreviousYearSameMonth = false;
      this.selectedHistoricalPeriod = null;
    }

    this.rebuildExpandedChart();
  }

  toggleComparison(periodKey: HistoricalPeriodKey): void {
    if (periodKey === 'previous_month') {
      this.showPreviousMonth = !this.showPreviousMonth;
    } else {
      this.showPreviousYearSameMonth = !this.showPreviousYearSameMonth;
    }

    const periodStillVisible = periodKey === 'previous_month'
      ? this.showPreviousMonth
      : this.showPreviousYearSameMonth;

    if (
      this.selectedHistoricalPeriod === periodKey &&
      !periodStillVisible
    ) {
      this.selectedHistoricalPeriod = null;
    }

    this.rebuildExpandedChart();
  }

  selectHistoricalSeries(periodKey: HistoricalPeriodKey): void {
    this.selectedHistoricalPeriod =
      this.selectedHistoricalPeriod === periodKey
        ? null
        : periodKey;

    this.rebuildExpandedChart();
  }

  close(): void {
    this.closeDetail.emit();
  }

  private rebuildExpandedChart(): void {
    if (!this.chart) {
      this.expandedChart = null;
      this.comparisonSummaries = [];
      return;
    }

    const historicalSeries = this.buildHistoricalSeries();
    const visibleValues = [
      ...this.chart.actualSeries.map((point) => point.value),
      ...this.chart.benchmarkSeries.map((point) => point.value),
      ...this.chart.projectionSeries.map((point) => point.value),
      ...historicalSeries.flatMap((series) => (
        series.markers.map((point) => this.getHistoricalMarkerValue(
          series.periodKey,
          point.day,
        ))
      )),
    ].filter((value): value is number => value !== null);
    const yAxisScale = this.buildYAxisScale(visibleValues);
    const daysInMonth = Math.max(
      this.chart.daysInMonth,
      ...historicalSeries.map((series) => (
        this.comparisonPeriods?.[series.periodKey].days_in_month || 0
      )),
    );
    const xForDay = (day: number): number => (
      14 + ((day - 1) / Math.max(daysInMonth - 1, 1)) * 82
    );
    const yForValue = (value: number): number => (
      31 - (
        (value - yAxisScale.minimum) /
        (yAxisScale.maximum - yAxisScale.minimum)
      ) * 27
    );

    const actualMarkers = this.mapCurrentMarkers(
      this.chart.actualSeries,
      xForDay,
      yForValue,
    );
    const benchmarkMarkers = this.mapCurrentMarkers(
      this.chart.benchmarkSeries,
      xForDay,
      yForValue,
    );
    const projectionMarkers = this.mapCurrentMarkers(
      this.chart.projectionSeries,
      xForDay,
      yForValue,
    );
    const scaledHistoricalSeries = historicalSeries.map((series) => (
      this.scaleHistoricalSeries(series, xForDay, yForValue)
    ));

    const selectedHistoricalSeries = this.selectedHistoricalPeriod
      ? scaledHistoricalSeries.find(
          (series) => series.periodKey === this.selectedHistoricalPeriod,
        ) ?? null
      : null;

    const actualValueLabels = selectedHistoricalSeries
      ? []
      : this.resolveValueLabelCollisions(
          this.buildActualValueLabels(
            this.chart.actualSeries,
            xForDay,
            yForValue,
          ),
        );

    const selectedHistoricalValueLabels = selectedHistoricalSeries
      ? this.resolveValueLabelCollisions(
          this.buildHistoricalValueLabels(selectedHistoricalSeries),
        )
      : [];

    this.expandedChart = {
      actualPoints: this.toPolyline(actualMarkers),
      benchmarkPoints: this.toPolyline(benchmarkMarkers),
      projectionPoints: this.toPolyline(projectionMarkers),
      actualMarkers,
      benchmarkMarkers,
      projectionMarkers,
      actualValueLabels,
      historicalSeries: scaledHistoricalSeries,
      selectedHistoricalSeries,
      selectedHistoricalValueLabels,
      axisLabels: this.buildAxisLabels(daysInMonth, xForDay),
      yAxisTicks: yAxisScale.ticks.map((value) => ({
        y: yForValue(value),
        label: this.formatNumber(value),
      })),
    };

    this.comparisonSummaries = this.buildComparisonSummaries();
  }

  private buildHistoricalSeries(): TrackIntelligenceChartDetailHistoricalSeries[] {
    if (!this.comparisons || !this.comparisonPeriods) {
      return [];
    }

    const activePeriods: Array<{
      periodKey: HistoricalPeriodKey;
      label: string;
      classModifier: 'previous-month' | 'previous-year';
    }> = [];

    if (this.showPreviousMonth) {
      activePeriods.push({
        periodKey: 'previous_month',
        label: 'Mes anterior',
        classModifier: 'previous-month',
      });
    }
    if (this.showPreviousYearSameMonth) {
      activePeriods.push({
        periodKey: 'previous_year_same_month',
        label: 'Mismo mes año anterior',
        classModifier: 'previous-year',
      });
    }

    return activePeriods.map(({ periodKey, label, classModifier }) => {
      const period = this.comparisonPeriods![periodKey];
      const rawPoints = this.comparisons!.periods[periodKey].points
        .slice()
        .sort((left, right) => left.day_of_month - right.day_of_month);
      const markers = rawPoints.flatMap((point) => {
        const value = this.toNumber(point.actual_mtd);
        if (value === null) {
          return [];
        }
        return [{
          day: point.day_of_month,
          x: point.day_of_month,
          y: value,
          label: (
            `${this.formatDate(point.track_date)} · ${label} ` +
            `(${this.formatTargetMonth(period.target_month)}) · ` +
            `Real acumulado ${this.formatNumber(value)}`
          ),
        }];
      });

      return {
        periodKey,
        label: `${label} · ${this.formatTargetMonth(period.target_month)}`,
        classModifier,
        segments: this.buildHistoricalRawSegments(rawPoints),
        markers,
      };
    });
  }

  private buildHistoricalRawSegments(
    points: TrackBranchOperationalChartComparisonMetric['periods'][HistoricalPeriodKey]['points'],
  ): string[] {
    const segments: string[] = [];
    let currentSegment: string[] = [];
    let previousDay: number | null = null;

    const flushSegment = (): void => {
      if (currentSegment.length) {
        segments.push(currentSegment.join(' '));
      }
      currentSegment = [];
      previousDay = null;
    };

    for (const point of points) {
      const value = this.toNumber(point.actual_mtd);
      if (value === null) {
        flushSegment();
        continue;
      }
      if (previousDay !== null && point.day_of_month !== previousDay + 1) {
        flushSegment();
      }
      currentSegment.push(`${point.day_of_month},${value}`);
      previousDay = point.day_of_month;
    }

    flushSegment();
    return segments;
  }

  private scaleHistoricalSeries(
    series: TrackIntelligenceChartDetailHistoricalSeries,
    xForDay: (day: number) => number,
    yForValue: (value: number) => number,
  ): TrackIntelligenceChartDetailHistoricalSeries {
    return {
      ...series,
      segments: series.segments.map((segment) => (
        segment.split(' ').map((pair) => {
          const [day, value] = pair.split(',').map(Number);
          return `${xForDay(day)},${yForValue(value)}`;
        }).join(' ')
      )),
      markers: series.markers.map((marker) => ({
        ...marker,
        x: xForDay(marker.day),
        y: yForValue(marker.y),
      })),
    };
  }

  private getHistoricalMarkerValue(
    periodKey: HistoricalPeriodKey,
    day: number,
  ): number | null {
    const point = this.comparisons?.periods[periodKey].points.find(
      (candidate) => candidate.day_of_month === day,
    );
    return this.toNumber(point?.actual_mtd);
  }

  private mapCurrentMarkers(
    points: TrackIntelligenceChartDetailSeriesPoint[],
    xForDay: (day: number) => number,
    yForValue: (value: number) => number,
  ): TrackIntelligenceChartDetailMarker[] {
    return points.map((point) => ({
      x: xForDay(point.day),
      y: yForValue(point.value),
      label: point.label,
    }));
  }

  private buildActualValueLabels(
    points: TrackIntelligenceChartDetailSeriesPoint[],
    xForDay: (day: number) => number,
    yForValue: (value: number) => number,
  ): TrackIntelligenceChartDetailValueLabel[] {
    if (!points.length) {
      return [];
    }

    const sortedPoints = points
      .slice()
      .filter((point) => (
        Number.isFinite(point.day) &&
        Number.isFinite(point.value)
      ))
      .sort((left, right) => left.day - right.day);

    if (!sortedPoints.length) {
      return [];
    }

    const referenceDays = new Set([5, 10, 15, 20, 25]);
    const lastPoint = sortedPoints[sortedPoints.length - 1];
    referenceDays.add(lastPoint.day);

    return sortedPoints
      .filter((point) => referenceDays.has(point.day))
      .map((point) => {
        const pointY = yForValue(point.value);

        // El área útil empieza alrededor de y=4.
        // Si estamos demasiado cerca de arriba, ponemos el texto debajo.
        const placement: 'above' | 'below' = pointY <= 7
          ? 'below'
          : 'above';

        return {
          day: point.day,
          x: xForDay(point.day),
          y: placement === 'below'
            ? pointY + 2.15
            : pointY - 1.35,
          text: this.formatNumber(point.value),
          placement,
        };
      });
  }

  private resolveValueLabelCollisions(
    labels: TrackIntelligenceChartDetailValueLabel[],
  ): TrackIntelligenceChartDetailValueLabel[] {
    if (labels.length <= 1) {
      return labels;
    }

    const sortedLabels = labels
      .slice()
      .sort((left, right) => left.day - right.day);

    const placed: Array<{
      left: number;
      right: number;
      top: number;
      bottom: number;
    }> = [];

    const candidateOffsets = [
      0,
      -2.2,
      2.2,
      -4.4,
      4.4,
      -6.6,
      6.6,
    ];

    const estimateHalfWidth = (label: string): number => (
      Math.max(2.2, label.length * 0.48)
    );

    const labelHalfHeight = 1.05;
    const horizontalPadding = 0.45;
    const verticalPadding = 0.25;

    const overlaps = (
      left: number,
      right: number,
      top: number,
      bottom: number,
    ): boolean => (
      placed.some((candidate) => !(
        right + horizontalPadding < candidate.left ||
        left - horizontalPadding > candidate.right ||
        bottom + verticalPadding < candidate.top ||
        top - verticalPadding > candidate.bottom
      ))
    );

    return sortedLabels.map((label) => {
      const halfWidth = estimateHalfWidth(label.text);
      let resolvedY = label.y;

      for (const offset of candidateOffsets) {
        // El área útil SVG de la gráfica está entre y≈4 y y≈31.
        // Dejamos margen para que el texto no choque con los bordes.
        const candidateY = Math.min(
          29.2,
          Math.max(5.4, label.y + offset),
        );

        const left = label.x - halfWidth;
        const right = label.x + halfWidth;
        const top = candidateY - labelHalfHeight;
        const bottom = candidateY + labelHalfHeight;

        if (!overlaps(left, right, top, bottom)) {
          resolvedY = candidateY;

          placed.push({
            left,
            right,
            top,
            bottom,
          });

          return {
            ...label,
            y: resolvedY,
          };
        }
      }

      // Fallback determinista para un caso extremadamente apretado.
      resolvedY = Math.min(
        29.2,
        Math.max(
          5.4,
          label.y + (
            placed.length % 2 === 0
              ? -6.6
              : 6.6
          ),
        ),
      );

      placed.push({
        left: label.x - halfWidth,
        right: label.x + halfWidth,
        top: resolvedY - labelHalfHeight,
        bottom: resolvedY + labelHalfHeight,
      });

      return {
        ...label,
        y: resolvedY,
      };
    });
  }

  private buildHistoricalValueLabels(
    series: TrackIntelligenceChartDetailHistoricalSeries,
  ): TrackIntelligenceChartDetailValueLabel[] {
    const markers = series.markers
      .slice()
      .sort((left, right) => left.day - right.day);

    if (!markers.length) {
      return [];
    }

    const referenceDays = new Set([5, 10, 15, 20, 25]);
    referenceDays.add(markers[markers.length - 1].day);

    return markers.flatMap((marker) => {
      if (!referenceDays.has(marker.day)) {
        return [];
      }

      const value = this.getHistoricalMarkerValue(
        series.periodKey,
        marker.day,
      );

      if (value === null) {
        return [];
      }

      const placement: 'above' | 'below' = marker.y <= 7
        ? 'below'
        : 'above';

      return [{
        day: marker.day,
        x: marker.x,
        y: placement === 'below'
          ? marker.y + 2.15
          : marker.y - 1.35,
        text: this.formatNumber(value),
        placement,
      }];
    });
  }

  private toPolyline(points: TrackIntelligenceChartDetailMarker[]): string {
    return points.map((point) => `${point.x},${point.y}`).join(' ');
  }

  private buildComparisonSummaries(): TrackIntelligenceChartDetailComparisonSummary[] {
    if (!this.comparisons || !this.comparisonPeriods) {
      return [];
    }

    const activePeriods: Array<{
      periodKey: HistoricalPeriodKey;
      label: string;
    }> = [];
    if (this.showPreviousMonth) {
      activePeriods.push({
        periodKey: 'previous_month',
        label: 'Mes anterior',
      });
    }
    if (this.showPreviousYearSameMonth) {
      activePeriods.push({
        periodKey: 'previous_year_same_month',
        label: 'Mismo mes año anterior',
      });
    }

    return activePeriods.map(({ periodKey, label }) => {
      const period = this.comparisonPeriods![periodKey];
      const point = this.comparisons!.periods[periodKey].same_day_point;
      const value = this.toNumber(point?.actual_mtd);
      return {
        periodKey,
        label,
        periodLabel: this.formatTargetMonth(period.target_month),
        comparisonDayLabel: `Al día ${period.comparison_day}`,
        value: value === null ? 'Dato no disponible' : this.formatNumber(value),
        available: value !== null,
      };
    });
  }

  private buildAxisLabels(
    daysInMonth: number,
    xForDay: (day: number) => number,
  ): TrackIntelligenceChartDetailAxisLabel[] {
    const baseReferenceDays = [1, 5, 10, 15, 20, 25, 30]
      .filter((day) => (
        day < daysInMonth &&
        !(daysInMonth === 31 && day === 30)
      ));
    return Array.from(new Set([...baseReferenceDays, daysInMonth]))
      .sort((left, right) => left - right)
      .map((day) => ({
        x: xForDay(day),
        label: String(day),
      }));
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
    const multiplier = normalized <= 1
      ? 1
      : normalized <= 2
        ? 2
        : normalized <= 2.5
          ? 2.5
          : normalized <= 5
            ? 5
            : 10;
    return multiplier * magnitude;
  }

  private toNumber(value: string | number | null | undefined): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  private formatNumber(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 1,
    }).format(value);
  }

  private formatDate(value: string): string {
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }

  private formatTargetMonth(value: string): string {
    const [year, month] = value.split('-').map(Number);
    if (!year || !month) {
      return value;
    }
    return new Intl.DateTimeFormat('es-MX', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(Date.UTC(year, month - 1, 1)));
  }
}
