import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  KpiDesempenoHistoricalRow,
  KpiDesempenoHistoricalSection,
  KpiDesempenoHistoryGranularity,
  KpiDesempenoMonthlyRow,
  KpiDesempenoMonthlySection,
  KpiDesempenoMonthlyReportResponse,
  KpiDesempenoWarning,
  KpiDesempenoWeeklyPeriod,
  KpiDesempenoWeeklyBranchSeriesSection,
  KpiDesempenoWeeklyRow,
  KpiDesempenoWeeklySection,
  TrackKpiDesempenoService,
} from '../services/track-kpi-desempeno.service';

interface KpiWeeklyChartBar {
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  label: string;
  value: number;
  branchLabel: string;
  periodLabel: string;
}

interface KpiWeeklyChartBranch {
  label: string;
  x: number;
  width: number;
  bandX: number;
  bandWidth: number;
  bandClass: string;
  separatorX: number;
}


interface KpiWeeklyChartLegendItem {
  label: string;
  color: string;
  snapshotLabel: string;
}

interface KpiWeeklyChartReferenceLine {
  y: number;
  value: number;
  label: string;
  className: string;
}

interface KpiWeeklyChartCapacityLine {
  branchLabel: string;
  x1: number;
  x2: number;
  y: number;
  markerPoints: string;
  value: number;
  label: string;
  className: string;
}

interface KpiWeeklyChartModel {
  width: number;
  height: number;
  plotX: number;
  plotY: number;
  plotWidth: number;
  plotHeight: number;
  maxValue: number;
  ticks: number[];
  bars: KpiWeeklyChartBar[];
  branches: KpiWeeklyChartBranch[];
  legend: KpiWeeklyChartLegendItem[];
  referenceLines: KpiWeeklyChartReferenceLine[];
  capacityLines: KpiWeeklyChartCapacityLine[];
}

@Component({
  selector: 'app-track-kpi-desempeno',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './track-kpi-desempeno.component.html',
  styleUrls: ['./track-kpi-desempeno.component.css'],
})
export class TrackKpiDesempenoComponent implements OnInit {
  targetMonth = '2026-05';
  startMonth = '2026-03';
  historyGranularity: KpiDesempenoHistoryGranularity = 'monthly';

  loading = false;
  errorMessage = '';

  report: KpiDesempenoMonthlyReportResponse | null = null;
  weeklyChart: KpiWeeklyChartModel | null = null;

  readonly granularityOptions: Array<{
    value: KpiDesempenoHistoryGranularity;
    label: string;
  }> = [
    {
      value: 'monthly',
      label: 'Mensual',
    },
    {
      value: 'bimonthly',
      label: 'Bimestral',
    },
    {
      value: 'quarterly',
      label: 'Trimestral',
    },
  ];

  private readonly numberFormatter = new Intl.NumberFormat('es-MX');
  private readonly weeklyChartColors = [
    '#2563eb',
    '#f97316',
    '#16a34a',
    '#7c3aed',
    '#0891b2',
  ];

  constructor(
    private readonly kpiDesempenoService: TrackKpiDesempenoService,
  ) {}

  ngOnInit(): void {
    this.loadReport();
  }

  get weeklySection(): KpiDesempenoWeeklySection | null {
    return (
      this.report?.sections.find(
        (section): section is KpiDesempenoWeeklySection =>
          section.key === 'weekly_closing',
      ) ?? null
    );
  }

  get weeklyBranchSeriesSection(): KpiDesempenoWeeklyBranchSeriesSection | null {
    return (
      this.report?.sections.find(
        (section): section is KpiDesempenoWeeklyBranchSeriesSection =>
          section.key === 'weekly_branch_series',
      ) ?? null
    );
  }
  get monthlySection(): KpiDesempenoMonthlySection | null {
    return (
      this.report?.sections.find(
        (section): section is KpiDesempenoMonthlySection =>
          section.key === 'monthly_closing',
      ) ?? null
    );
  }

  get historicalSection(): KpiDesempenoHistoricalSection | null {
    return (
      this.report?.sections.find(
        (section): section is KpiDesempenoHistoricalSection =>
          section.key === 'historical_closing',
      ) ?? null
    );
  }

  get allWarnings(): KpiDesempenoWarning[] {
    return this.report?.sections.flatMap(
      (section) => section.warnings || [],
    ) ?? [];
  }

  get monthlyRows(): KpiDesempenoMonthlyRow[] {
    return this.monthlySection?.data ?? [];
  }

  get historicalRows(): KpiDesempenoHistoricalRow[] {
    return this.historicalSection?.data ?? [];
  }

  get weeklyPeriods(): KpiDesempenoWeeklyPeriod[] {
    return this.weeklySection?.periods ?? [];
  }

  loadReport(): void {
    this.loading = true;
    this.errorMessage = '';

    this.kpiDesempenoService.getMonthlyReport({
      targetMonth: this.targetMonth,
      startMonth: this.startMonth,
      historyGranularity: this.historyGranularity,
    }).subscribe({
      next: (response) => {
        this.report = response;
        this.weeklyChart = this.buildWeeklyChart();
        this.loading = false;
      },
      error: (error) => {
        this.errorMessage = this.resolveErrorMessage(error);
        this.report = null;
        this.weeklyChart = null;
        this.loading = false;
      },
    });
  }

  formatNumber(value: number | null | undefined): string {
    return this.numberFormatter.format(Number(value || 0));
  }

  formatSignedNumber(value: number | null | undefined): string {
    const normalizedValue = Number(value || 0);
    const formattedValue = this.numberFormatter.format(normalizedValue);

    if (normalizedValue > 0) {
      return `+${formattedValue}`;
    }

    return formattedValue;
  }

  formatDate(value: string | null | undefined): string {
    if (!value) {
      return 'Sin fecha';
    }

    return value;
  }

  formatSnapshotLabel(period: KpiDesempenoWeeklyPeriod): string {
    if (!period.resolved_snapshot) {
      return 'Sin snapshot';
    }

    return period.resolved_snapshot.business_date;
  }

  resolveMovementClass(value: number | null | undefined): string {
    const normalizedValue = Number(value || 0);

    if (normalizedValue > 0) {
      return 'positive';
    }

    if (normalizedValue < 0) {
      return 'negative';
    }

    return 'neutral';
  }

  trackByBranchCanon(
    _index: number,
    row: KpiDesempenoMonthlyRow,
  ): string {
    return row.branch.sucursal_canon || row.branch.sucursal_raw;
  }

  trackByWeeklyPeriod(
    _index: number,
    period: KpiDesempenoWeeklyPeriod,
  ): string {
    return period.period_key;
  }

  trackByHistoricalPeriod(
    _index: number,
    row: KpiDesempenoHistoricalRow,
  ): string {
    return row.period_key;
  }

  trackByWeeklyChartBar(
    _index: number,
    bar: KpiWeeklyChartBar,
  ): string {
    return `${bar.branchLabel}-${bar.periodLabel}`;
  }

  trackByWeeklyChartBranch(
    _index: number,
    branch: KpiWeeklyChartBranch,
  ): string {
    return branch.label;
  }

  trackByWeeklyLegendItem(
    _index: number,
    item: KpiWeeklyChartLegendItem,
  ): string {
    return item.label;
  }

  trackByReferenceLine(
    _index: number,
    item: KpiWeeklyChartReferenceLine,
  ): string {
    return item.label;
  }

  trackByCapacityLine(
    _index: number,
    item: KpiWeeklyChartCapacityLine,
  ): string {
    return `${item.branchLabel}-${item.label}`;
  }

  private buildWeeklyChart(): KpiWeeklyChartModel | null {
    const section = this.weeklyBranchSeriesSection;

    if (!section || !section.data.length) {
      return null;
    }

    const rows = this.filterWeeklyChartRows(section.data);
    const periodKeys = this.resolveWeeklyPeriodKeys(section);
    const branchLabels = this.resolveWeeklyBranchLabels(rows);

    if (!periodKeys.length || !branchLabels.length) {
      return null;
    }

    const minBranchSlotWidth = Math.max(132, periodKeys.length * 14);
    const width = Math.max(
      2800,
      (branchLabels.length * minBranchSlotWidth) + 280,
    );
    const height = 500;
    const plotX = 54;
    const plotY = 26;
    const plotWidth = width - 190;
    const plotHeight = 250;
    const maxValue = this.resolveWeeklyChartMaxValue(rows);
    const ticks = this.buildChartTicks(maxValue);
    const scaleY = (value: number): number =>
      plotY + plotHeight - ((value / maxValue) * plotHeight);

    const branchSlotWidth = plotWidth / branchLabels.length;
    const groupInnerPadding = 26;
    const availableGroupWidth = Math.max(
      24,
      branchSlotWidth - groupInnerPadding,
    );
    const barGap = 1;
    const barWidth = Math.max(
      4,
      (availableGroupWidth - (barGap * Math.max(0, periodKeys.length - 1))) /
        periodKeys.length,
    );

    const rowsByBranchAndPeriod = this.indexWeeklyRowsByBranchAndPeriod(rows);
    const capacityByBranch = this.indexWeeklyCapacityByBranch(rows);
    const bars: KpiWeeklyChartBar[] = [];
    const branches: KpiWeeklyChartBranch[] = [];
    const capacityLines: KpiWeeklyChartCapacityLine[] = [];

    branchLabels.forEach((branchLabel, branchIndex) => {
      const slotX = plotX + (branchIndex * branchSlotWidth);
      const groupX = slotX + ((branchSlotWidth - availableGroupWidth) / 2);

      const branchCapacity = capacityByBranch.get(branchLabel);
      const latestVisibleValue = this.resolveLatestWeeklyBranchValue(
        branchLabel,
        periodKeys,
        rows,
      );
      const branchCapacityStatus = this.resolveWeeklyBranchCapacityStatus(
        latestVisibleValue,
        branchCapacity,
      );

      branches.push({
        label: branchLabel,
        x: slotX + (branchSlotWidth / 2),
        width: branchSlotWidth,
        bandX: slotX,
        bandWidth: branchSlotWidth,
        bandClass: branchIndex % 2 === 0 ? 'branch-band even' : 'branch-band odd',
        separatorX: slotX + branchSlotWidth,
      });

      if (branchCapacity) {
        [
          {
            value: Number(branchCapacity.target_1_5 || 0),
            label: 'Meta 1.5 socios/m²',
            className: 'capacity-line target-1-5',
          },
          {
            value: Number(branchCapacity.target_2_0 || 0),
            label: 'Meta 2.0 socios/m²',
            className: 'capacity-line target-2-0',
          },
        ].forEach((targetLine) => {
          if (targetLine.value <= 0 || targetLine.value > maxValue) {
            return;
          }

          const markerY = scaleY(targetLine.value);

          /**
           * Ambos marcadores deben ir alineados en la misma vertical.
           * Solo cambia su Y según la meta (1.5 o 2.0).
           */
          const markerOffset = 2;
          const markerWidth = 13;
          const markerHalfHeight = 6;

          const markerX = Math.min(
            plotX + plotWidth - 18,
            groupX + availableGroupWidth + markerOffset,
          );

          capacityLines.push({
            branchLabel,
            x1: markerX,
            x2: markerX + markerWidth,
            y: markerY,
            markerPoints: `${markerX},${markerY} ${markerX + markerWidth},${markerY - markerHalfHeight} ${markerX + markerWidth},${markerY + markerHalfHeight}`,
            value: targetLine.value,
            label: targetLine.label,
            className: targetLine.className,
          });
        });
      }

      periodKeys.forEach((periodKey, periodIndex) => {
        const row = rowsByBranchAndPeriod.get(`${branchLabel}__${periodKey}`);
        const value = Number(row?.metrics.socios_activos_cierre_semana || 0);
        const y = scaleY(value);
        const barHeight = plotY + plotHeight - y;

        const barX = groupX + (periodIndex * (barWidth + barGap));

        bars.push({
          x: barX,
          y,
          width: barWidth,
          height: barHeight,
          color: this.weeklyChartColors[
            periodIndex % this.weeklyChartColors.length
          ],
          label: this.formatNumber(value),
          value,
          branchLabel,
          periodLabel: this.resolvePeriodLabel(section, periodKey),
        });

      });

    });

    return {
      width,
      height,
      plotX,
      plotY,
      plotWidth,
      plotHeight,
      maxValue,
      ticks,
      bars,
      branches,
      legend: this.buildWeeklyChartLegend(section, periodKeys),
      referenceLines: [],
      capacityLines,
    };
  }

  private filterWeeklyChartRows(
    rows: KpiDesempenoWeeklyRow[],
  ): KpiDesempenoWeeklyRow[] {
    return rows.filter((row) => {
      if (this.isExcludedWeeklyBranch(row)) {
        return false;
      }

      return this.hasWeeklyBranchAnyValue(row, rows);
    });
  }

  private isExcludedWeeklyBranch(row: KpiDesempenoWeeklyRow): boolean {
    const values = [
      row.branch.track_label,
      row.branch.sucursal_raw,
      row.branch.sucursal_canon || '',
    ].map((value) => value.trim().toUpperCase());

    const isCancelledBranch = values.some((value) =>
      value === 'LA VIGA' ||
      value === 'LA_VIGA' ||
      value === 'SERRANIA' ||
      value === 'SERRANÍA'
    );

    return row.branch.is_track_active === false || isCancelledBranch;
  }

  private hasWeeklyBranchAnyValue(
    row: KpiDesempenoWeeklyRow,
    rows: KpiDesempenoWeeklyRow[],
  ): boolean {
    const targetValues = [
      row.branch.track_label,
      row.branch.sucursal_raw,
      row.branch.sucursal_canon || '',
    ].map((value) => value.trim().toUpperCase());

    return rows.some((candidate) => {
      const candidateValues = [
        candidate.branch.track_label,
        candidate.branch.sucursal_raw,
        candidate.branch.sucursal_canon || '',
      ].map((value) => value.trim().toUpperCase());

      const sameBranch = candidateValues.some((candidateValue) =>
        targetValues.includes(candidateValue)
      );

      return (
        sameBranch &&
        Number(candidate.metrics.socios_activos_cierre_semana || 0) > 0
      );
    });
  }
  private resolveWeeklyPeriodKeys(
    section: KpiDesempenoWeeklySection | KpiDesempenoWeeklyBranchSeriesSection,
  ): string[] {
    return section.periods
      .filter((period) => period.resolved_snapshot)
      .map((period) => period.period_key);
  }

  private resolveWeeklyBranchLabels(
    rows: KpiDesempenoWeeklyRow[],
  ): string[] {
    const labels: string[] = [];

    rows.forEach((row) => {
      const label = row.branch.track_label || row.branch.sucursal_raw;

      if (!labels.includes(label)) {
        labels.push(label);
      }
    });

    return labels;
  }

  private resolveWeeklyChartMaxValue(
    rows: KpiDesempenoWeeklyRow[],
  ): number {
    const maxFromRows = Math.max(
      ...rows.map((row) =>
        Number(row.metrics.socios_activos_cierre_semana || 0),
      ),
      0,
    );

    return Math.max(100, Math.ceil((maxFromRows * 1.12) / 100) * 100);
  }

  private buildChartTicks(maxValue: number): number[] {
    const step = Math.max(100, Math.ceil((maxValue / 4) / 100) * 100);

    return [
      0,
      step,
      step * 2,
      step * 3,
      Math.max(maxValue, step * 4),
    ];
  }

  private resolveLatestWeeklyBranchValue(
    branchLabel: string,
    periodKeys: string[],
    rows: KpiDesempenoWeeklyRow[],
  ): number | null {
    const periodIndexByKey = new Map<string, number>();

    periodKeys.forEach((periodKey, index) => {
      periodIndexByKey.set(periodKey, index);
    });

    const branchRows = rows
      .filter((row) => {
        const rowBranchLabel =
          row.branch?.track_label ||
          row.branch?.sucursal_canon ||
          row.branch?.sucursal_raw ||
          'Sin sucursal';

        return (
          rowBranchLabel === branchLabel &&
          periodIndexByKey.has(row.period.period_key)
        );
      })
      .sort((a, b) => {
        const periodA = periodIndexByKey.get(a.period.period_key) ?? -1;
        const periodB = periodIndexByKey.get(b.period.period_key) ?? -1;

        return periodB - periodA;
      });

    for (const row of branchRows) {
      const value = Number(row.metrics.socios_activos_cierre_semana || 0);

      if (value > 0) {
        return value;
      }
    }

    return null;
  }

  private resolveWeeklyBranchCapacityStatus(
    latestVisibleValue: number | null,
    capacity:
      | NonNullable<KpiDesempenoWeeklyRow['branch']['capacity']>
      | undefined,
  ): { className: string; title: string } {
    if (
      latestVisibleValue === null ||
      !capacity ||
      !capacity.m2_sin_circulaciones
    ) {
      return {
        className: 'branch-status-dot unknown',
        title: 'Sin dato de ocupación disponible',
      };
    }

    const m2 = Number(capacity.m2_sin_circulaciones || 0);

    if (m2 <= 0) {
      return {
        className: 'branch-status-dot unknown',
        title: 'Sin m² válidos para calcular ocupación',
      };
    }

    const occupancyRatio = latestVisibleValue / m2;
    const formattedRatio = occupancyRatio.toFixed(2);

    if (occupancyRatio >= 2) {
      return {
        className: 'branch-status-dot target-2-0',
        title: `Ocupación ${formattedRatio} socios/m² · supera meta 2.0`,
      };
    }

    if (occupancyRatio >= 1.5) {
      return {
        className: 'branch-status-dot target-1-5',
        title: `Ocupación ${formattedRatio} socios/m² · supera meta 1.5`,
      };
    }

    return {
      className: 'branch-status-dot below-target',
      title: `Ocupación ${formattedRatio} socios/m² · debajo de meta 1.5`,
    };
  }

  private indexWeeklyCapacityByBranch(
    rows: KpiDesempenoWeeklyRow[],
  ): Map<string, NonNullable<KpiDesempenoWeeklyRow['branch']['capacity']>> {
    const index = new Map<string, NonNullable<KpiDesempenoWeeklyRow['branch']['capacity']>>();

    rows.forEach((row) => {
      const branchLabel =
        row.branch?.track_label ||
        row.branch?.sucursal_canon ||
        row.branch?.sucursal_raw ||
        'Sin sucursal';

      const capacity = row.branch?.capacity;

      if (!index.has(branchLabel) && capacity) {
        index.set(branchLabel, capacity);
      }
    });

    return index;
  }

  private indexWeeklyRowsByBranchAndPeriod(
    rows: KpiDesempenoWeeklyRow[],
  ): Map<string, KpiDesempenoWeeklyRow> {
    const index = new Map<string, KpiDesempenoWeeklyRow>();

    rows.forEach((row) => {
      const branchLabel = row.branch.track_label || row.branch.sucursal_raw;
      index.set(`${branchLabel}__${row.period.period_key}`, row);
    });

    return index;
  }

  private resolvePeriodLabel(
    section: KpiDesempenoWeeklySection | KpiDesempenoWeeklyBranchSeriesSection,
    periodKey: string,
  ): string {
    return (
      section.periods.find((period) => period.period_key === periodKey)?.label ||
      periodKey
    );
  }

  private buildWeeklyChartLegend(
    section: KpiDesempenoWeeklySection | KpiDesempenoWeeklyBranchSeriesSection,
    periodKeys: string[],
  ): KpiWeeklyChartLegendItem[] {
    return periodKeys.map((periodKey, index) => {
      const period = section.periods.find(
        (item) => item.period_key === periodKey,
      );

      return {
        label: period?.label || periodKey,
        color: this.weeklyChartColors[index % this.weeklyChartColors.length],
        snapshotLabel: period?.resolved_snapshot?.business_date || 'Sin snapshot',
      };
    });
  }

  private buildWeeklyReferenceLines(
    scaleY: (value: number) => number,
    maxValue: number,
  ): KpiWeeklyChartReferenceLine[] {
    const referenceValues = [
      {
        value: 1500,
        label: 'Meta 1,500',
        className: 'target-line',
      },
      {
        value: 1000,
        label: 'Referencia 1,000',
        className: 'warning-line',
      },
      {
        value: 500,
        label: 'Referencia 500',
        className: 'warning-line',
      },
    ];

    return referenceValues
      .filter((line) => line.value <= maxValue)
      .map((line) => ({
        ...line,
        y: scaleY(line.value),
      }));
  }

  private resolveErrorMessage(error: unknown): string {
    if (
      typeof error === 'object' &&
      error !== null &&
      'error' in error
    ) {
      const maybeHttpError = error as {
        error?: {
          message?: string;
        };
      };

      if (maybeHttpError.error?.message) {
        return maybeHttpError.error.message;
      }
    }

    return 'No se pudo cargar KPI Desempeño.';
  }
}


















