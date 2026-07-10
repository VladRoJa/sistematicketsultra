import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  KpiDesempenoDisplayGranularity,
  KpiDesempenoHistoricalBranchSeriesSection,
  KpiDesempenoHistoricalRow,
  KpiDesempenoHistoricalSection,
  KpiDesempenoHistoryGranularity,
  KpiDesempenoMonthlyBranchYearOverlaySection,
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
  className: string;
  label: string;
  value: number;
  branchLabel: string;
  periodLabel: string;
}

interface KpiWeeklyTargetProgress {
  x: number;
  y: number;
  width: number;
  fillWidth: number;
  labelX: number;
  labelY: number;
  percentLabel: string;
  tooltip: string;
  className: string;
  hitboxX: number;
  hitboxY: number;
  hitboxWidth: number;
  hitboxHeight: number;
}

interface KpiWeeklyChartBranch {
  label: string;
  x: number;
  width: number;
  bandX: number;
  bandWidth: number;
  bandClass: string;
  separatorX: number;
  targetProgress: KpiWeeklyTargetProgress | null;
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


interface KpiYearOverlayPoint {
  x: number;
  y: number;
  value: number;
  month: number;
  label: string;
  tooltip: string;
}

interface KpiYearOverlaySeriesModel {
  year: number;
  className: string;
  color: string;
  polylinePoints: string;
  detailPolylinePoints: string;
  points: KpiYearOverlayPoint[];
  detailPoints: KpiYearOverlayPoint[];
}

interface KpiYearOverlayTick {
  value: number;
  y: number;
  label: string;
}

interface KpiYearOverlayMonthLabel {
  x: number;
  label: string;
}

interface KpiYearOverlayComparisonModel {
  baseYear: number;
  compareYear: number;
  baseMonthLabel: string;
  compareMonthLabel: string;
  baseValueLabel: string;
  compareValueLabel: string;
  diffValue: number;
  diffLabel: string;
  percentLabel: string;
}

interface KpiYearOverlayChartModel {
  branchLabel: string;
  width: number;
  height: number;
  detailWidth: number;
  detailHeight: number;
  plotX: number;
  plotY: number;
  plotWidth: number;
  plotHeight: number;
  detailPlotX: number;
  detailPlotY: number;
  detailPlotWidth: number;
  detailPlotHeight: number;
  minValue: number;
  maxValue: number;
  ticks: KpiYearOverlayTick[];
  detailTicks: KpiYearOverlayTick[];
  monthLabels: KpiYearOverlayMonthLabel[];
  detailMonthLabels: KpiYearOverlayMonthLabel[];
  series: KpiYearOverlaySeriesModel[];
}

type KpiBranchSeriesSection =
  | KpiDesempenoHistoricalBranchSeriesSection
  | KpiDesempenoWeeklyBranchSeriesSection;

@Component({
  selector: 'app-track-kpi-desempeno',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './track-kpi-desempeno.component.html',
  styleUrls: ['./track-kpi-desempeno.component.css'],
})
export class TrackKpiDesempenoComponent implements OnInit {
  targetMonth = '';
  startMonth = '';
  historyGranularity: KpiDesempenoDisplayGranularity = 'weekly';

  loading = false;
  errorMessage = '';
  showCoverageWarnings = false;

  report: KpiDesempenoMonthlyReportResponse | null = null;
  weeklyChart: KpiWeeklyChartModel | null = null;
  yearOverlayCharts: KpiYearOverlayChartModel[] = [];
  selectedYearOverlayBranchLabel: string | null = null;
  selectedYearOverlayYear: number | null = null;
  selectedYearOverlayBaseYear: number | null = null;
  selectedYearOverlayCompareYear: number | null = null;

  readonly granularityOptions: Array<{
    value: KpiDesempenoDisplayGranularity;
    label: string;
  }> = [
    {
      value: 'weekly',
      label: 'Semanal',
    },
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

  private readonly yearOverlayColors = [
    '#2563eb',
    '#16a34a',
    '#7c3aed',
    '#f97316',
    '#0891b2',
    '#dc2626',
  ];

  constructor(
    private readonly kpiDesempenoService: TrackKpiDesempenoService,
  ) {}

  ngOnInit(): void {
    this.initializeDefaultMonths();
    this.loadReport();
  }

  private initializeDefaultMonths(): void {
    const currentMonth = this.getCurrentBusinessMonth();

    this.targetMonth = this.shiftMonth(currentMonth, -1);
    this.startMonth = this.shiftMonth(this.targetMonth, -3);
  }

  private getCurrentBusinessMonth(): string {
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Tijuana',
      year: 'numeric',
      month: '2-digit',
    });

    const parts = formatter.formatToParts(new Date());
    const year = parts.find((part) => part.type === 'year')?.value;
    const month = parts.find((part) => part.type === 'month')?.value;

    if (!year || !month) {
      throw new Error(
        'No fue posible determinar el mes actual de America/Tijuana.',
      );
    }

    return `${year}-${month}`;
  }

  private shiftMonth(value: string, offsetMonths: number): string {
    const match = /^(\d{4})-(\d{2})$/.exec(value);

    if (!match) {
      throw new Error(`Formato de mes inválido: ${value}`);
    }

    const year = Number(match[1]);
    const monthIndex = Number(match[2]) - 1;
    const shiftedDate = new Date(
      Date.UTC(year, monthIndex + offsetMonths, 1),
    );

    return [
      shiftedDate.getUTCFullYear(),
      String(shiftedDate.getUTCMonth() + 1).padStart(2, '0'),
    ].join('-');
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

  get historicalBranchSeriesSection(): KpiDesempenoHistoricalBranchSeriesSection | null {
    return (
      this.report?.sections.find(
        (section): section is KpiDesempenoHistoricalBranchSeriesSection =>
          section.key === 'historical_branch_series',
      ) ?? null
    );
  }

  get activeBranchSeriesSection(): KpiBranchSeriesSection | null {
    if (this.historyGranularity === 'weekly') {
      return this.weeklyBranchSeriesSection;
    }

    return this.historicalBranchSeriesSection ?? this.weeklyBranchSeriesSection;
  }

  get activeBranchSeriesTitle(): string {
    return this.activeBranchSeriesSection?.title || 'Crecimiento promedio de socios';
  }

  get activeBranchSeriesDescription(): string {
    const section = this.activeBranchSeriesSection;

    if (section?.key === 'historical_branch_series') {
      return `Comparativo histórico por sucursal con granularidad ${this.formatGranularityLabel(section.granularity).toLowerCase()}.`;
    }

    return 'Comparativo histórico por sucursal usando el último snapshot canónico disponible de cada semana.';
  }
  get monthlySection(): KpiDesempenoMonthlySection | null {
    return (
      this.report?.sections.find(
        (section): section is KpiDesempenoMonthlySection =>
          section.key === 'monthly_closing',
      ) ?? null
    );
  }

  get monthlyBranchYearOverlaySection(): KpiDesempenoMonthlyBranchYearOverlaySection | null {
    return (
      this.report?.sections.find(
        (section): section is KpiDesempenoMonthlyBranchYearOverlaySection =>
          section.key === 'monthly_branch_year_overlay',
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

  get coverageWarnings(): KpiDesempenoWarning[] {
    return this.activeBranchSeriesSection?.warnings ?? [];
  }

  toggleCoverageWarnings(): void {
    this.showCoverageWarnings = !this.showCoverageWarnings;
  }

  formatCoverageWarning(warning: KpiDesempenoWarning): string {
    const dateFrom = String(warning['date_from'] || '');
    const dateTo = String(warning['date_to'] || '');

    if (dateFrom && dateTo) {
      return `Falta snapshot del ${this.formatShortSpanishDateRange(dateFrom, dateTo)}.`;
    }

    return String(warning.message || 'Falta snapshot para el periodo.');
  }

  private formatShortSpanishDateRange(dateFrom: string, dateTo: string): string {
    const fromParts = this.parseIsoDateParts(dateFrom);
    const toParts = this.parseIsoDateParts(dateTo);

    if (!fromParts || !toParts) {
      return `${dateFrom} a ${dateTo}`;
    }

    const monthNames = [
      'enero',
      'febrero',
      'marzo',
      'abril',
      'mayo',
      'junio',
      'julio',
      'agosto',
      'septiembre',
      'octubre',
      'noviembre',
      'diciembre',
    ];

    const fromMonth = monthNames[fromParts.month - 1] || '';
    const toMonth = monthNames[toParts.month - 1] || '';

    if (
      fromParts.month === toParts.month &&
      fromParts.year === toParts.year
    ) {
      return `${fromParts.day} al ${toParts.day} de ${fromMonth} ${fromParts.year}`;
    }

    if (fromParts.year === toParts.year) {
      return `${fromParts.day} de ${fromMonth} al ${toParts.day} de ${toMonth} ${fromParts.year}`;
    }

    return `${fromParts.day} de ${fromMonth} ${fromParts.year} al ${toParts.day} de ${toMonth} ${toParts.year}`;
  }

  private parseIsoDateParts(value: string): { year: number; month: number; day: number } | null {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);

    if (!match) {
      return null;
    }

    return {
      year: Number(match[1]),
      month: Number(match[2]),
      day: Number(match[3]),
    };
  }

  get monthlyRows(): KpiDesempenoMonthlyRow[] {
    return this.monthlySection?.data ?? [];
  }

  get historicalRows(): KpiDesempenoHistoricalRow[] {
    return this.historicalSection?.data ?? [];
  }

  get weeklyPeriods(): KpiDesempenoWeeklyPeriod[] {
    return this.activeBranchSeriesSection?.periods ?? [];
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
        this.syncSelectedYearOverlayYear();
        this.yearOverlayCharts = this.buildYearOverlayCharts();

        if (
          this.selectedYearOverlayBranchLabel &&
          !this.yearOverlayCharts.some(
            (chart) => chart.branchLabel === this.selectedYearOverlayBranchLabel,
          )
        ) {
          this.selectedYearOverlayBranchLabel = null;
        }
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

  formatGranularityLabel(value: KpiDesempenoDisplayGranularity | string | null | undefined): string {
    const option = this.granularityOptions.find(
      (item) => item.value === value,
    );

    return option?.label || 'Sin granularidad';
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

  selectYearOverlayYear(year: number): void {
    const section = this.monthlyBranchYearOverlaySection;

    if (!section?.years?.includes(year)) {
      return;
    }

    this.selectedYearOverlayYear = year;
    this.selectedYearOverlayCompareYear = year;
    this.yearOverlayCharts = this.buildYearOverlayCharts();
  }

  isYearOverlayYearSelected(year: number): boolean {
    return this.selectedYearOverlayYear === year;
  }

  getYearOverlayColor(year: number): string {
    const section = this.monthlyBranchYearOverlaySection;
    const yearIndex = section?.years?.indexOf(year) ?? -1;

    if (yearIndex < 0) {
      return this.yearOverlayColors[0];
    }

    return this.yearOverlayColors[yearIndex % this.yearOverlayColors.length];
  }

  private syncSelectedYearOverlayYear(): void {
    const section = this.monthlyBranchYearOverlaySection;

    if (!section?.years?.length) {
      this.selectedYearOverlayYear = null;
      return;
    }

    if (
      this.selectedYearOverlayYear &&
      section.years.includes(this.selectedYearOverlayYear)
    ) {
      return;
    }

    this.selectedYearOverlayYear = section.end_year;
    this.selectedYearOverlayCompareYear = section.end_year;

    if (!this.selectedYearOverlayBaseYear || !section.years.includes(this.selectedYearOverlayBaseYear)) {
      this.selectedYearOverlayBaseYear = section.end_year;
    }
  }

  get selectedYearOverlayComparison(): KpiYearOverlayComparisonModel | null {
    const chart = this.selectedYearOverlayChart;

    if (!chart || !this.selectedYearOverlayBaseYear || !this.selectedYearOverlayCompareYear) {
      return null;
    }

    const baseSerie = chart.series.find(
      (serie) => serie.year === this.selectedYearOverlayBaseYear,
    );
    const compareSerie = chart.series.find(
      (serie) => serie.year === this.selectedYearOverlayCompareYear,
    );

    const basePoint = this.getLatestYearOverlayPoint(baseSerie);
    const comparePoint = this.getLatestYearOverlayPoint(compareSerie);

    if (!basePoint || !comparePoint) {
      return null;
    }

    const diffValue = comparePoint.value - basePoint.value;
    const percentValue = basePoint.value !== 0 ? (diffValue / basePoint.value) * 100 : null;

    return {
      baseYear: this.selectedYearOverlayBaseYear,
      compareYear: this.selectedYearOverlayCompareYear,
      baseMonthLabel: basePoint.label,
      compareMonthLabel: comparePoint.label,
      baseValueLabel: this.formatNumber(basePoint.value),
      compareValueLabel: this.formatNumber(comparePoint.value),
      diffValue,
      diffLabel: `${diffValue > 0 ? '+' : ''}${this.formatNumber(diffValue)}`,
      percentLabel:
        percentValue === null
          ? 'N/A'
          : `${percentValue > 0 ? '+' : ''}${percentValue.toFixed(1)}%`,
    };
  }

  selectYearOverlayBaseYear(year: number): void {
    const section = this.monthlyBranchYearOverlaySection;

    if (!section?.years?.includes(year)) {
      return;
    }

    this.selectedYearOverlayBaseYear = year;
    this.yearOverlayCharts = this.buildYearOverlayCharts();
  }

  selectYearOverlayCompareYear(year: number): void {
    const section = this.monthlyBranchYearOverlaySection;

    if (!section?.years?.includes(year)) {
      return;
    }

    this.selectedYearOverlayCompareYear = year;
    this.selectedYearOverlayYear = year;
    this.yearOverlayCharts = this.buildYearOverlayCharts();
  }

  isYearOverlayBaseYearSelected(year: number): boolean {
    return this.selectedYearOverlayBaseYear === year;
  }

  isYearOverlayCompareYearSelected(year: number): boolean {
    return this.selectedYearOverlayCompareYear === year;
  }

  private resolveYearOverlaySeriesClassName(year: number): string {
    const isBaseYear = this.selectedYearOverlayBaseYear === year;
    const isCompareYear =
      this.selectedYearOverlayCompareYear === year ||
      (!this.selectedYearOverlayCompareYear && this.selectedYearOverlayYear === year);

    if (isBaseYear && isCompareYear) {
      return 'year-overlay-line current base compare';
    }

    if (isCompareYear) {
      return 'year-overlay-line current compare';
    }

    if (isBaseYear) {
      return 'year-overlay-line current base';
    }

    return 'year-overlay-line shadow';
  }

  private getLatestYearOverlayPoint(
    serie: KpiYearOverlaySeriesModel | undefined,
  ): KpiYearOverlayPoint | null {
    if (!serie?.points?.length) {
      return null;
    }

    return serie.points.reduce((latest, point) =>
      point.month > latest.month ? point : latest,
    );
  }

  get selectedYearOverlayChart(): KpiYearOverlayChartModel | null {
    if (!this.selectedYearOverlayBranchLabel) {
      return null;
    }

    return (
      this.yearOverlayCharts.find(
        (chart) => chart.branchLabel === this.selectedYearOverlayBranchLabel,
      ) ?? null
    );
  }

  selectYearOverlayChart(chart: KpiYearOverlayChartModel): void {
    this.selectedYearOverlayBranchLabel =
      this.selectedYearOverlayBranchLabel === chart.branchLabel
        ? null
        : chart.branchLabel;
  }

  isYearOverlayChartSelected(chart: KpiYearOverlayChartModel): boolean {
    return this.selectedYearOverlayBranchLabel === chart.branchLabel;
  }

  private buildYearOverlayCharts(): KpiYearOverlayChartModel[] {
    const section = this.monthlyBranchYearOverlaySection;

    if (!section?.data?.length) {
      return [];
    }

    const width = 360;
    const height = 220;
    const plotX = 46;
    const plotY = 22;
    const plotWidth = 284;
    const plotHeight = 132;

    const detailWidth = 1200;
    const detailHeight = 430;
    const detailPlotX = 86;
    const detailPlotY = 36;
    const detailPlotWidth = 1048;
    const detailPlotHeight = 300;

    return section.data.map((row) => {
      const values = row.series
        .flatMap((series) => series.months)
        .map((month) => month.socios_activos_cierre_mes)
        .filter((value): value is number => value !== null && Number.isFinite(value));

      let minValue = values.length ? Math.min(...values) : 0;
      let maxValue = values.length ? Math.max(...values) : 100;

      if (minValue === maxValue) {
        minValue = Math.max(0, minValue - 50);
        maxValue += 50;
      } else {
        const padding = (maxValue - minValue) * 0.08;
        minValue = Math.max(0, Math.floor((minValue - padding) / 50) * 50);
        maxValue = Math.ceil((maxValue + padding) / 50) * 50;
      }

      const valueRange = Math.max(1, maxValue - minValue);
      const resolveX = (monthNumber: number): number =>
        plotX + ((monthNumber - 1) / 11) * plotWidth;
      const resolveY = (value: number): number =>
        plotY + plotHeight - ((value - minValue) / valueRange) * plotHeight;
      const detailResolveX = (monthNumber: number): number =>
        detailPlotX + ((monthNumber - 1) / 11) * detailPlotWidth;
      const detailResolveY = (value: number): number =>
        detailPlotY + detailPlotHeight - ((value - minValue) / valueRange) * detailPlotHeight;

      const ticks: KpiYearOverlayTick[] = [
        {
          value: maxValue,
          y: resolveY(maxValue),
          label: this.formatNumber(maxValue),
        },
        {
          value: Math.round((minValue + maxValue) / 2),
          y: resolveY(Math.round((minValue + maxValue) / 2)),
          label: this.formatNumber(Math.round((minValue + maxValue) / 2)),
        },
        {
          value: minValue,
          y: resolveY(minValue),
          label: this.formatNumber(minValue),
        },
      ];

      const detailTicks: KpiYearOverlayTick[] = Array.from(
        { length: 6 },
        (_, index) => Math.round(maxValue - ((maxValue - minValue) / 5) * index),
      ).map((value) => ({
        value,
        y: detailResolveY(value),
        label: this.formatNumber(value),
      }));

      const monthLabels: KpiYearOverlayMonthLabel[] = section.months
        .filter((month) => [1, 3, 6, 9, 12].includes(month.month))
        .map((month) => ({
          x: resolveX(month.month),
          label: month.label,
        }));

      const detailMonthLabels: KpiYearOverlayMonthLabel[] = section.months.map((month) => ({
        x: detailResolveX(month.month),
        label: month.label,
      }));

      const monthComparisonTooltipByMonth = new Map<number, string>();

      section.months.forEach((monthMeta) => {
        const monthRows = row.series
          .map((yearSeries) => {
            const monthData = yearSeries.months.find(
              (item) => item.month === monthMeta.month,
            );
            const value = monthData?.socios_activos_cierre_mes;

            if (value === null || value === undefined || !Number.isFinite(Number(value))) {
              return null;
            }

            return {
              year: yearSeries.year,
              value: Number(value),
            };
          })
          .filter(
            (item): item is { year: number; value: number } => item !== null,
          )
          .sort((left, right) => right.year - left.year);

        if (!monthRows.length) {
          return;
        }

        const tooltipLines = [
          `Sucursal: ${row.branch.track_label}`,
          `Mes: ${monthMeta.label}`,
          '',
        ];

        monthRows.forEach((item, index) => {
          const previousYearItem = monthRows[index + 1];
          const percentChange =
            previousYearItem && previousYearItem.value !== 0
              ? ((item.value - previousYearItem.value) / previousYearItem.value) * 100
              : null;

          const percentLabel =
            percentChange === null
              ? 'base'
              : `${percentChange > 0 ? '+' : ''}${percentChange.toFixed(1)}% vs ${previousYearItem.year}`;

          tooltipLines.push(
            `Año ${item.year}: ${this.formatNumber(item.value)} socios (${percentLabel})`,
          );
        });

        monthComparisonTooltipByMonth.set(monthMeta.month, tooltipLines.join('\n'));
      });

      const series: KpiYearOverlaySeriesModel[] = row.series.map((yearSeries) => {
        const points = yearSeries.months
          .filter((month) => month.socios_activos_cierre_mes !== null)
          .map((month) => {
            const value = Number(month.socios_activos_cierre_mes);

            return {
              x: resolveX(month.month),
              y: resolveY(value),
              value,
              month: month.month,
              label: month.label,
              tooltip:
                monthComparisonTooltipByMonth.get(month.month) ||
                [
                  `Sucursal: ${row.branch.track_label}`,
                  `Año: ${yearSeries.year}`,
                  `Mes: ${month.label}`,
                  `Socios cierre: ${this.formatNumber(value)}`,
                  month.source?.business_date
                    ? `Snapshot: ${month.source.business_date}`
                    : 'Snapshot: Sin dato',
                ].join('\n'),
            };
          });

        const detailPoints = points.map((point) => ({
          ...point,
          x: detailResolveX(point.month),
          y: detailResolveY(point.value),
        }));

        return {
          year: yearSeries.year,
          className: this.resolveYearOverlaySeriesClassName(yearSeries.year),
          color: this.getYearOverlayColor(yearSeries.year),
          polylinePoints: points
            .map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`)
            .join(' '),
          detailPolylinePoints: detailPoints
            .map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`)
            .join(' '),
          points,
          detailPoints,
        };
      });

      return {
        branchLabel: row.branch.track_label,
        width,
        height,
        detailWidth,
        detailHeight,
        plotX,
        plotY,
        plotWidth,
        plotHeight,
        detailPlotX,
        detailPlotY,
        detailPlotWidth,
        detailPlotHeight,
        minValue,
        maxValue,
        ticks,
        detailTicks,
        monthLabels,
        detailMonthLabels,
        series,
      };
    });
  }

  private buildWeeklyChart(): KpiWeeklyChartModel | null {
    const section = this.activeBranchSeriesSection;

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
    const height = 520;
    const plotX = 54;
    const plotY = 26;
    const plotWidth = width - 190;
    const plotHeight = 380;
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

      const target20 = Number(branchCapacity?.target_2_0 || 0);
      const target15 = Number(branchCapacity?.target_1_5 || 0);
      const m2SinCirculaciones = Number(branchCapacity?.m2_sin_circulaciones || 0);
      const targetProgressWidth = Math.min(
        94,
        Math.max(48, branchSlotWidth * 0.42),
      );
      const targetProgressX = slotX + ((branchSlotWidth - targetProgressWidth) / 2);
      const targetProgressY = plotY + plotHeight + 18;
      const targetProgressPercent =
        latestVisibleValue !== null && target20 > 0
          ? (latestVisibleValue / target20) * 100
          : 0;
      const targetProgressFillWidth =
        targetProgressPercent > 0
          ? Math.max(
              2,
              Math.min(
                targetProgressWidth,
                (Math.min(targetProgressPercent, 100) / 100) *
                  targetProgressWidth,
              ),
            )
          : 0;
      const currentDensity =
        latestVisibleValue !== null && m2SinCirculaciones > 0
          ? latestVisibleValue / m2SinCirculaciones
          : null;
      const missingForTarget20 =
        latestVisibleValue !== null
          ? Math.max(0, target20 - latestVisibleValue)
          : 0;
      const targetProgressClass =
        targetProgressPercent >= 100
          ? 'branch-target-progress-fill complete'
          : targetProgressPercent >= 75
            ? 'branch-target-progress-fill warning'
            : 'branch-target-progress-fill danger';
      const targetProgress =
        latestVisibleValue !== null && target20 > 0
          ? {
              x: targetProgressX,
              y: targetProgressY,
              width: targetProgressWidth,
              fillWidth: targetProgressFillWidth,
              labelX: targetProgressX + (targetProgressWidth / 2),
              labelY: targetProgressY + 18,
              percentLabel: `${targetProgressPercent.toFixed(0)}%`,
              className: targetProgressClass,
              hitboxX: slotX,
              hitboxY: plotY + plotHeight + 8,
              hitboxWidth: branchSlotWidth,
              hitboxHeight: 64,
              tooltip: [
                `Sucursal: ${branchLabel}`,
                `Socios actuales: ${this.formatNumber(latestVisibleValue)}`,
                m2SinCirculaciones > 0
                  ? `m² sin circulaciones: ${this.formatNumber(m2SinCirculaciones)}`
                  : 'm² sin circulaciones: Sin dato',
                currentDensity !== null
                  ? `Ocupación actual: ${currentDensity.toFixed(2)} socios/m²`
                  : 'Ocupación actual: Sin dato',
                target15 > 0
                  ? `Meta 1.5: ${this.formatNumber(target15)} socios`
                  : 'Meta 1.5: Sin dato',
                `Meta 2.0: ${this.formatNumber(target20)} socios`,
                `Avance a meta 2.0: ${targetProgressPercent.toFixed(1)}%`,
                missingForTarget20 > 0
                  ? `Faltan: ${this.formatNumber(missingForTarget20)} socios para 2.0`
                  : 'Meta 2.0 cumplida',
              ].join('\n'),
            }
          : null;

      branches.push({
        label: branchLabel,
        x: slotX + (branchSlotWidth / 2),
        width: branchSlotWidth,
        bandX: slotX,
        bandWidth: branchSlotWidth,
        bandClass: branchIndex % 2 === 0 ? 'branch-band even' : 'branch-band odd',
        separatorX: slotX + branchSlotWidth,
        targetProgress,
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

      const branchPoints = periodKeys
        .map((periodKey) => {
          const row = rowsByBranchAndPeriod.get(`${branchLabel}__${periodKey}`);

          return {
            periodKey,
            value: row ? this.resolveBranchSeriesValue(row) : 0,
          };
        })
        .filter((point) => point.value > 0);

      const branchMaxPoint = branchPoints.length > 1
        ? branchPoints.reduce((maxPoint, point) =>
            point.value > maxPoint.value ? point : maxPoint,
          )
        : null;
      const branchMinPoint = branchPoints.length > 1
        ? branchPoints.reduce((minPoint, point) =>
            point.value < minPoint.value ? point : minPoint,
          )
        : null;
      const highlightIsUseful =
        branchMaxPoint !== null &&
        branchMinPoint !== null &&
        branchMaxPoint.value !== branchMinPoint.value;

      periodKeys.forEach((periodKey, periodIndex) => {
        const row = rowsByBranchAndPeriod.get(`${branchLabel}__${periodKey}`);
        const value = row ? this.resolveBranchSeriesValue(row) : 0;
        const y = scaleY(value);
        const barHeight = plotY + plotHeight - y;

        const barX = groupX + (periodIndex * (barWidth + barGap));
        const periodLabel = this.resolvePeriodLabel(section, periodKey);

        let className = 'weekly-bar';

        if (
          highlightIsUseful &&
          branchMaxPoint &&
          periodKey === branchMaxPoint.periodKey
        ) {
          className += ' highest-in-branch';
        } else if (
          highlightIsUseful &&
          branchMinPoint &&
          periodKey === branchMinPoint.periodKey
        ) {
          className += ' lowest-in-branch';
        }

        bars.push({
          x: barX,
          y,
          width: barWidth,
          height: barHeight,
          color: this.weeklyChartColors[
            periodIndex % this.weeklyChartColors.length
          ],
          className,
          label: this.formatNumber(value),
          value,
          branchLabel,
          periodLabel,
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
        this.resolveBranchSeriesValue(candidate) > 0
      );
    });
  }
  private resolveWeeklyPeriodKeys(
    section: KpiDesempenoWeeklySection | KpiDesempenoWeeklyBranchSeriesSection | KpiDesempenoHistoricalBranchSeriesSection,
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


  private resolveBranchSeriesValue(row: KpiDesempenoWeeklyRow): number {
    return Number(
      row.metrics.socios_activos_cierre_periodo ??
      row.metrics.socios_activos_cierre_semana ??
      0,
    );
  }

  private resolveWeeklyChartMaxValue(
    rows: KpiDesempenoWeeklyRow[],
  ): number {
    const maxFromRows = Math.max(
      ...rows.map((row) =>
        this.resolveBranchSeriesValue(row),
      ),
      0,
    );

    return Math.max(100, Math.ceil((maxFromRows * 1.12) / 100) * 100);
  }

  private buildChartTicks(maxValue: number): number[] {
    const desiredTickCount = 8;
    const step = Math.max(
      100,
      Math.ceil((maxValue / desiredTickCount) / 100) * 100,
    );
    const ticks: number[] = [];

    for (let tick = 0; tick <= maxValue; tick += step) {
      ticks.push(tick);
    }

    if (ticks[ticks.length - 1] !== maxValue) {
      ticks.push(maxValue);
    }

    return ticks;
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
      const value = this.resolveBranchSeriesValue(row);

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
    section: KpiDesempenoWeeklySection | KpiDesempenoWeeklyBranchSeriesSection | KpiDesempenoHistoricalBranchSeriesSection,
    periodKey: string,
  ): string {
    return (
      section.periods.find((period) => period.period_key === periodKey)?.label ||
      periodKey
    );
  }

  private buildWeeklyChartLegend(
    section: KpiDesempenoWeeklySection | KpiDesempenoWeeklyBranchSeriesSection | KpiDesempenoHistoricalBranchSeriesSection,
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


















