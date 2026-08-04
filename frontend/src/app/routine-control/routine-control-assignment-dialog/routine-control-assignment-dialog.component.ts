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
  selectedMonthValue: string;
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
    this.selectedMonthValue =
      this.resolveInitialMonth();

    this.periodLabel =
      this.formatMonthLabel(
        this.selectedMonthValue,
      );

    this.rows = this.buildRows(
      data.branches,
    );

    this.totals = this.buildTotals(
      this.rows,
    );
  }

  ngOnInit(): void {
    this.loadSelectedMonth();
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  selectMonth(value: string): void {
    if (
      !/^\d{4}-\d{2}$/.test(value)
      || value === this.selectedMonthValue
    ) {
      return;
    }

    this.selectedMonthValue = value;
    this.periodLabel =
      this.formatMonthLabel(value);

    this.loadSelectedMonth();
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
        monthValue:
          this.selectedMonthValue,
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

  private loadSelectedMonth(): void {
    const range = this.monthRange(
      this.selectedMonthValue,
    );

    if (!range) {
      this.errorMessage =
        'El mes seleccionado no es válido.';
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
              + 'mes seleccionado.';
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

  private resolveInitialMonth(): string {
    const candidates = [
      this.data.filters.sale_date_to,
      this.data.cutoffDate,
      this.data.filters.sale_date_from,
    ];

    for (const candidate of candidates) {
      const value = String(candidate || '');

      if (/^\d{4}-\d{2}/.test(value)) {
        return value.slice(0, 7);
      }
    }

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

  private monthRange(
    value: string,
  ): {
    dateFrom: string;
    dateTo: string;
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

    const lastDay = new Date(
      year,
      month,
      0,
    ).getDate();

    return {
      dateFrom: this.formatDateForApi(
        year,
        month,
        1,
      ),
      dateTo: this.formatDateForApi(
        year,
        month,
        lastDay,
      ),
    };
  }

  private formatMonthLabel(
    value: string,
  ): string {
    const range = this.monthRange(value);

    if (!range) {
      return 'Mes no válido';
    }

    const [year, month] = value
      .split('-')
      .map((item) => Number(item));

    return new Intl.DateTimeFormat(
      'es-MX',
      {
        month: 'long',
        year: 'numeric',
      },
    ).format(
      new Date(
        year,
        month - 1,
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
