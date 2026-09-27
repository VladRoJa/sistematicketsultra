import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  AttendanceBaseHealthMemberRow,
  AttendanceBaseHealthMembersRequest,
  AttendanceBaseHealthMembersResponse,
} from './attendance.models';
import { AttendanceService } from './attendance.service';


@Component({
  selector: 'app-attendance-base-health-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './attendance-base-health-detail-dialog.component.html',
  styleUrls: ['./attendance-base-health-detail-dialog.component.css'],
})
export class AttendanceBaseHealthDetailDialogComponent
  implements OnInit {
  private readonly service = inject(AttendanceService);
  private readonly dialogRef = inject(
    MatDialogRef<AttendanceBaseHealthDetailDialogComponent>,
  );

  readonly data = inject<AttendanceBaseHealthMembersRequest>(
    MAT_DIALOG_DATA,
  );
  readonly pageSize = 50;

  detail: AttendanceBaseHealthMembersResponse | null = null;
  rows: AttendanceBaseHealthMemberRow[] = [];
  loading = true;
  errorMessage = '';

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

  formatDate(value: string | null): string {
    if (!value) {
      return '—';
    }

    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) {
      return value;
    }

    return `${match[3]}/${match[2]}/${match[1]}`;
  }

  private loadPage(page: number): void {
    this.loading = true;
    this.errorMessage = '';

    this.service.getBaseHealthMembers({
      ...this.data,
      page,
      pageSize: this.pageSize,
    }).subscribe({
      next: (detail) => {
        this.detail = detail;
        this.rows = detail.rows;
        this.loading = false;
      },
      error: (error: HttpErrorResponse) => {
        this.loading = false;
        this.errorMessage = this.resolveError(error);
      },
    });
  }

  private formatNumber(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private resolveError(error: HttpErrorResponse): string {
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

    return 'No fue posible cargar el detalle de socios.';
  }
}
