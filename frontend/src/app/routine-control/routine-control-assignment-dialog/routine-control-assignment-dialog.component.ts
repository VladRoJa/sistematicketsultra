import { CommonModule } from '@angular/common';
import {
  Component,
  Inject,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { Subscription } from 'rxjs';
import { finalize } from 'rxjs/operators';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  RoutineControlBranchCatalog,
  RoutineControlFilters,
  RoutineControlSummary,
  RoutineControlSummaryBranch,
} from '../models/routine-control.models';
import {
  RoutineControlAssignmentPdfService,
} from '../services/routine-control-assignment-pdf.service';
import {
  RoutineControlService,
} from '../services/routine-control.service';

export interface RoutineControlAssignmentDialogData {
  branches: RoutineControlSummaryBranch[];
  branchCatalogs: RoutineControlBranchCatalog[];
  cutoffDate: string | null;
  filters: RoutineControlFilters;
}

interface RoutineControlAssignmentRow {
  regionKey: string;
  regionName: string;
  regionClass: string;
  branchName: string;
  conRutina: number;
  sinRutina: number;
  noRequiereRutina: number;
  total: number;
  percentConRutina: number;
  percentSinRutina: number;
}

interface RoutineControlAssignmentTotals {
  conRutina: number;
  sinRutina: number;
  noRequiereRutina: number;
  total: number;
  percentConRutina: number;
  percentSinRutina: number;
}

@Component({
  selector: 'app-routine-control-assignment-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl:
    './routine-control-assignment-dialog.component.html',
  styleUrls: [
    './routine-control-assignment-dialog.component.css',
  ],
})
export class RoutineControlAssignmentDialogComponent
  implements OnInit, OnDestroy {
  rows: RoutineControlAssignmentRow[];
  totals: RoutineControlAssignmentTotals;
  selectedMonthFromValue: string;
  selectedMonthToValue: string;
  periodLabel: string;
  loading = false;
  exportingPdf = false;
  errorMessage = '';

  private readonly subscriptions =
    new Subscription();

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: RoutineControlAssignmentDialogData,
    private readonly dialogRef:
      MatDialogRef<RoutineControlAssignmentDialogComponent>,
    private readonly service: RoutineControlService,
    private readonly pdfService:
      RoutineControlAssignmentPdfService,
  ) {
    const initialRange =
      this.resolveInitialMonthRange();

    this.selectedMonthFromValue =
      initialRange.monthFrom;

    this.selectedMonthToValue =
      initialRange.monthTo;

    this.periodLabel =
      this.formatPeriodLabel(
        this.selectedMonthFromValue,
        this.selectedMonthToValue,
      );

    this.rows = this.buildRows(
      data.branches,
    );

    this.totals = this.buildTotals(
      this.rows,
    );
  }

  ngOnInit(): void {
    this.loadSelectedMonthRange();
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  selectMonthRange(
    monthFromValue: string,
    monthToValue: string,
  ): void {
    const range = this.monthRange(
      monthFromValue,
      monthToValue,
    );

    if (!range) {
      this.errorMessage =
        'Selecciona un rango mensual válido. '
        + 'El mes final no puede ser anterior '
        + 'al mes inicial.';
      return;
    }

    if (
      monthFromValue
        === this.selectedMonthFromValue
      && monthToValue
        === this.selectedMonthToValue
    ) {
      return;
    }

    this.selectedMonthFromValue =
      monthFromValue;

    this.selectedMonthToValue =
      monthToValue;

    this.periodLabel =
      this.formatPeriodLabel(
        monthFromValue,
        monthToValue,
      );

    this.loadSelectedMonthRange();
  }

  close(): void {
    this.dialogRef.close();
  }

  async exportPdf(): Promise<void> {
    if (
      this.loading
      || this.exportingPdf
    ) {
      return;
    }

    this.exportingPdf = true;
    this.errorMessage = '';

    try {
      await this.pdfService.exportReport({
        monthFromValue:
          this.selectedMonthFromValue,
        monthToValue:
          this.selectedMonthToValue,
        periodLabel:
          this.periodLabel,
        rows:
          this.rows,
        totals:
          this.totals,
      });
    } catch {
      this.errorMessage =
        'No fue posible generar el PDF. '
        + 'Intenta nuevamente.';
    } finally {
      this.exportingPdf = false;
    }
  }

  conPercentClass(value: number): string {
    if (value >= 70) {
      return 'percentage percentage--success';
    }

    if (value >= 40) {
      return 'percentage percentage--warning';
    }

    if (value > 0) {
      return 'percentage percentage--attention';
    }

    return 'percentage percentage--danger';
  }

  sinPercentClass(value: number): string {
    if (value <= 30) {
      return 'percentage percentage--success';
    }

    if (value <= 60) {
      return 'percentage percentage--warning';
    }

    if (value < 100) {
      return 'percentage percentage--attention';
    }

    return 'percentage percentage--danger';
  }

  private loadSelectedMonthRange(): void {
    const range = this.monthRange(
      this.selectedMonthFromValue,
      this.selectedMonthToValue,
    );

    if (!range) {
      this.errorMessage =
        'El rango mensual seleccionado '
        + 'no es válido.';
      return;
    }

    this.loading = true;
    this.errorMessage = '';

    const filters: RoutineControlFilters = {
      ...this.data.filters,
      sale_date_from: range.dateFrom,
      sale_date_to: range.dateTo,
      page: undefined,
      page_size: undefined,
    };

    this.subscriptions.add(
      this.service.getSummary(filters)
        .pipe(
          finalize(
            () => this.loading = false,
          ),
        )
        .subscribe({
          next: (
            summary: RoutineControlSummary,
          ) => {
            this.rows = this.buildRows(
              summary.branches,
            );

            this.totals = this.buildTotals(
              this.rows,
            );
          },
          error: () => {
            this.errorMessage =
              'No fue posible consultar el '
              + 'rango seleccionado.';
          },
        }),
    );
  }

  private buildRows(
    branches: RoutineControlSummaryBranch[],
  ): RoutineControlAssignmentRow[] {
    const branchCatalogById = new Map(
      this.data.branchCatalogs.map(
        (branch) => [branch.id, branch],
      ),
    );

    const regionClassByKey =
      this.buildRegionClassMap(
        this.data.branchCatalogs,
      );

    return branches
      .map((branch) => {
        const catalog = branch.branch_id === null
          ? undefined
          : branchCatalogById.get(branch.branch_id);

        const regionKey =
          catalog?.region_key || 'SIN_REGION';

        const regionName =
          catalog?.region_name || 'Sin región';

        const conRutina =
          Number(branch.con_rutina || 0);

        const sinRutina =
          Number(branch.sin_rutina || 0);

        const noRequiereRutina =
          Number(branch.no_desea_rutina || 0);

        const total = conRutina + sinRutina;

        return {
          regionKey,
          regionName,
          regionClass:
            regionClassByKey.get(regionKey)
            || 'region-tone-0',
          branchName: branch.branch_name,
          conRutina,
          sinRutina,
          noRequiereRutina,
          total,
          percentConRutina:
            this.percentage(conRutina, total),
          percentSinRutina:
            this.percentage(sinRutina, total),
        };
      })
      .sort((left, right) => {
        const percentageDifference =
          right.percentConRutina
          - left.percentConRutina;

        if (percentageDifference !== 0) {
          return percentageDifference;
        }

        const routineDifference =
          right.conRutina - left.conRutina;

        if (routineDifference !== 0) {
          return routineDifference;
        }

        return left.branchName.localeCompare(
          right.branchName,
          'es',
          {
            sensitivity: 'base',
          },
        );
      });
  }

  private buildTotals(
    rows: RoutineControlAssignmentRow[],
  ): RoutineControlAssignmentTotals {
    const totals = rows.reduce(
      (accumulator, row) => ({
        conRutina:
          accumulator.conRutina + row.conRutina,
        sinRutina:
          accumulator.sinRutina + row.sinRutina,
        noRequiereRutina:
          accumulator.noRequiereRutina
          + row.noRequiereRutina,
      }),
      {
        conRutina: 0,
        sinRutina: 0,
        noRequiereRutina: 0,
      },
    );

    const total =
      totals.conRutina + totals.sinRutina;

    return {
      ...totals,
      total,
      percentConRutina:
        this.percentage(
          totals.conRutina,
          total,
        ),
      percentSinRutina:
        this.percentage(
          totals.sinRutina,
          total,
        ),
    };
  }

  private buildRegionClassMap(
    branches: RoutineControlBranchCatalog[],
  ): Map<string, string> {
    const regionKeys = Array.from(
      new Set(
        branches.map(
          (branch) =>
            branch.region_key || 'SIN_REGION',
        ),
      ),
    ).sort((left, right) =>
      left.localeCompare(
        right,
        'es',
        {
          sensitivity: 'base',
        },
      ),
    );

    return new Map(
      regionKeys.map(
        (regionKey, index) => [
          regionKey,
          `region-tone-${index % 6}`,
        ],
      ),
    );
  }

  private percentage(
    value: number,
    total: number,
  ): number {
    if (total <= 0) {
      return 0;
    }

    return Number(
      ((value / total) * 100).toFixed(1),
    );
  }

  private resolveInitialMonthRange(): {
    monthFrom: string;
    monthTo: string;
  } {
    const currentMonth =
      this.currentMonthValue();

    const monthFrom =
      this.monthValueFromDate(
        this.data.filters.sale_date_from,
      )
      ?? this.monthValueFromDate(
        this.data.filters.sale_date_to,
      )
      ?? this.monthValueFromDate(
        this.data.cutoffDate,
      )
      ?? currentMonth;

    const candidateMonthTo =
      this.monthValueFromDate(
        this.data.filters.sale_date_to,
      )
      ?? this.monthValueFromDate(
        this.data.cutoffDate,
      )
      ?? monthFrom;

    return {
      monthFrom,
      monthTo:
        candidateMonthTo >= monthFrom
          ? candidateMonthTo
          : monthFrom,
    };
  }

  private currentMonthValue(): string {
    const today = new Date();

    return [
      String(today.getFullYear()).padStart(
        4,
        '0',
      ),
      String(today.getMonth() + 1).padStart(
        2,
        '0',
      ),
    ].join('-');
  }

  private monthValueFromDate(
    value: string | null | undefined,
  ): string | null {
    const normalized = String(
      value || '',
    );

    if (!/^\d{4}-\d{2}/.test(normalized)) {
      return null;
    }

    const monthValue =
      normalized.slice(0, 7);

    return this.parseMonth(monthValue)
      ? monthValue
      : null;
  }

  private parseMonth(
    value: string,
  ): {
    year: number;
    month: number;
  } | null {
    const match = /^(\d{4})-(\d{2})$/.exec(
      value,
    );

    if (!match) {
      return null;
    }

    const year = Number(match[1]);
    const month = Number(match[2]);

    if (
      !Number.isInteger(year)
      || month < 1
      || month > 12
    ) {
      return null;
    }

    return {
      year,
      month,
    };
  }

  private monthRange(
    monthFromValue: string,
    monthToValue: string,
  ): {
    dateFrom: string;
    dateTo: string;
  } | null {
    const monthFrom =
      this.parseMonth(monthFromValue);

    const monthTo =
      this.parseMonth(monthToValue);

    if (!monthFrom || !monthTo) {
      return null;
    }

    const fromIndex =
      monthFrom.year * 12
      + monthFrom.month;

    const toIndex =
      monthTo.year * 12
      + monthTo.month;

    if (toIndex < fromIndex) {
      return null;
    }

    const lastDay = new Date(
      monthTo.year,
      monthTo.month,
      0,
    ).getDate();

    return {
      dateFrom: this.formatDateForApi(
        monthFrom.year,
        monthFrom.month,
        1,
      ),
      dateTo: this.formatDateForApi(
        monthTo.year,
        monthTo.month,
        lastDay,
      ),
    };
  }

  private formatPeriodLabel(
    monthFromValue: string,
    monthToValue: string,
  ): string {
    const fromLabel =
      this.formatMonthLabel(
        monthFromValue,
      );

    const toLabel =
      this.formatMonthLabel(
        monthToValue,
      );

    if (monthFromValue === monthToValue) {
      return fromLabel;
    }

    return `${fromLabel} a ${toLabel}`;
  }

  private formatMonthLabel(
    value: string,
  ): string {
    const month = this.parseMonth(value);

    if (!month) {
      return 'Periodo no válido';
    }

    return new Intl.DateTimeFormat(
      'es-MX',
      {
        month: 'long',
        year: 'numeric',
      },
    ).format(
      new Date(
        month.year,
        month.month - 1,
        1,
        12,
        0,
        0,
      ),
    );
  }

  private formatDateForApi(
    year: number,
    month: number,
    day: number,
  ): string {
    return [
      String(year).padStart(4, '0'),
      String(month).padStart(2, '0'),
      String(day).padStart(2, '0'),
    ].join('-');
  }
}
