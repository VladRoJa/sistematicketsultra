import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  RoutineControlBranchCatalog,
  RoutineControlSummaryBranch,
} from '../models/routine-control.models';

export interface RoutineControlAssignmentDialogData {
  branches: RoutineControlSummaryBranch[];
  branchCatalogs: RoutineControlBranchCatalog[];
  cutoffDate: string | null;
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
export class RoutineControlAssignmentDialogComponent {
  readonly rows: RoutineControlAssignmentRow[];
  readonly totals: RoutineControlAssignmentTotals;
  readonly cutoffLabel: string;

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: RoutineControlAssignmentDialogData,
    private readonly dialogRef:
      MatDialogRef<RoutineControlAssignmentDialogComponent>,
  ) {
    this.rows = this.buildRows();
    this.totals = this.buildTotals(this.rows);
    this.cutoffLabel = this.formatCutoffDate(
      data.cutoffDate,
    );
  }

  close(): void {
    this.dialogRef.close();
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

  private buildRows(): RoutineControlAssignmentRow[] {
    const branchCatalogById = new Map(
      this.data.branchCatalogs.map(
        (branch) => [branch.id, branch],
      ),
    );

    const regionClassByKey =
      this.buildRegionClassMap(
        this.data.branchCatalogs,
      );

    return this.data.branches
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

  private formatCutoffDate(
    value: string | null,
  ): string {
    if (!value) {
      return 'corte actual';
    }

    const datePart = value.slice(0, 10);
    const parts = datePart
      .split('-')
      .map((item) => Number(item));

    if (
      parts.length !== 3
      || parts.some((item) => !Number.isInteger(item))
    ) {
      return 'corte actual';
    }

    const [year, month, day] = parts;
    const date = new Date(
      year,
      month - 1,
      day,
      12,
      0,
      0,
    );

    return new Intl.DateTimeFormat(
      'es-MX',
      {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      },
    ).format(date);
  }
}
