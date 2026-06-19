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
  KpiDesempenoWeeklySection,
  TrackKpiDesempenoService,
} from '../services/track-kpi-desempeno.service';

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
        this.loading = false;
      },
      error: (error) => {
        this.errorMessage = this.resolveErrorMessage(error);
        this.report = null;
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
