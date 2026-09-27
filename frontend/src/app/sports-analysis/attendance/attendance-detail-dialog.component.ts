import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';

import {
  AttendanceDetailColumn,
  AttendanceDetailRequest,
  AttendanceDetailResponse,
  AttendanceDetailRow,
  AttendanceDetailSortDirection,
} from './attendance.models';
import { AttendanceService } from './attendance.service';


@Component({
  selector: 'app-attendance-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTableModule,
  ],
  templateUrl: './attendance-detail-dialog.component.html',
  styleUrls: ['./attendance-detail-dialog.component.css'],
})
export class AttendanceDetailDialogComponent implements OnInit {
  private readonly service = inject(AttendanceService);
  private readonly dialogRef = inject(
    MatDialogRef<AttendanceDetailDialogComponent>,
  );

  readonly data = inject<AttendanceDetailRequest>(MAT_DIALOG_DATA);
  readonly pageSize = 50;

  detail: AttendanceDetailResponse | null = null;
  rows: AttendanceDetailRow[] = [];
  columns: AttendanceDetailColumn[] = [];
  displayedColumns: string[] = [];

  loading = true;
  exporting = false;
  errorMessage = '';

  sortBy: string | undefined;
  sortDir: AttendanceDetailSortDirection = 'asc';

  ngOnInit(): void {
    this.loadPage(1);
  }

  get canGoPrevious(): boolean {
    return Boolean(
      this.detail
      && this.detail.page > 1
      && !this.loading,
    );
  }

  get canGoNext(): boolean {
    return Boolean(
      this.detail
      && this.detail.page < this.detail.total_pages
      && !this.loading,
    );
  }

  get rangeLabel(): string {
    if (!this.detail || this.detail.count === 0) {
      return '0 registros';
    }

    const start =
      (this.detail.page - 1) * this.detail.page_size + 1;
    const end = Math.min(
      this.detail.page * this.detail.page_size,
      this.detail.count,
    );
    return `${this.formatNumber(start)}–${this.formatNumber(end)} de ${this.formatNumber(this.detail.count)}`;
  }

  close(): void {
    this.dialogRef.close();
  }

  goToPage(page: number): void {
    if (
      !this.detail
      || this.loading
      || page < 1
      || page > this.detail.total_pages
      || page === this.detail.page
    ) {
      return;
    }

    this.loadPage(page);
  }

  toggleSort(column: AttendanceDetailColumn): void {
    if (
      this.loading
      || column.sortable === false
    ) {
      return;
    }

    if (this.sortBy === column.key) {
      this.sortDir =
        this.sortDir === 'asc'
          ? 'desc'
          : 'asc';
    } else {
      this.sortBy = column.key;
      this.sortDir = 'asc';
    }

    this.loadPage(1);
  }

  sortIcon(column: string): string {
    if (this.sortBy !== column) {
      return 'unfold_more';
    }

    return this.sortDir === 'asc'
      ? 'arrow_upward'
      : 'arrow_downward';
  }

  formatCell(
    row: AttendanceDetailRow,
    column: string,
  ): string {
    const value = row[column];
    if (
      value === null
      || value === undefined
      || value === ''
    ) {
      return '—';
    }

    if (typeof value === 'boolean') {
      return value ? 'Sí' : 'No';
    }

    return String(value);
  }

  exportExcel(): void {
    if (this.exporting || !this.detail) {
      return;
    }

    this.exporting = true;
    this.errorMessage = '';

    this.service.exportDetail({
      ...this.data,
      sortBy: this.sortBy,
      sortDir: this.sortDir,
    }).subscribe({
      next: (blob) => {
        this.exporting = false;

        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = this.exportFilename();
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();

        setTimeout(
          () => URL.revokeObjectURL(url),
          0,
        );
      },
      error: (error: HttpErrorResponse) => {
        this.exporting = false;
        this.errorMessage = this.resolveError(
          error,
          true,
        );
      },
    });
  }

  private loadPage(page: number): void {
    this.loading = true;
    this.errorMessage = '';

    this.service.getDetail({
      ...this.data,
      page,
      pageSize: this.pageSize,
      sortBy: this.sortBy,
      sortDir: this.sortDir,
    }).subscribe({
      next: (detail) => {
        this.loading = false;
        this.detail = detail;
        this.rows = detail.rows;
        this.columns = detail.columns;
        this.displayedColumns = detail.columns.map(
          (column) => column.key,
        );
        this.sortBy = detail.sort_by;
        this.sortDir = detail.sort_dir;
      },
      error: (error: HttpErrorResponse) => {
        this.loading = false;
        this.errorMessage = this.resolveError(
          error,
          false,
        );
      },
    });
  }

  private exportFilename(): string {
    const period = this.data.dateFrom === this.data.dateTo
      ? this.data.dateFrom
      : `${this.data.dateFrom}_${this.data.dateTo}`;

    return `aforo_asistencia_${this.data.metric}_${period}.xlsx`;
  }

  private formatNumber(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private resolveError(
    error: HttpErrorResponse,
    exportRequest: boolean,
  ): string {
    const backendMessage = error.error?.detail;

    if (
      typeof backendMessage === 'string'
      && backendMessage.trim()
    ) {
      return backendMessage.trim();
    }

    if (error.status === 0) {
      return 'No fue posible conectar con el backend.';
    }

    return exportRequest
      ? 'No fue posible exportar el detalle a Excel.'
      : 'No fue posible cargar el detalle del indicador.';
  }
}
