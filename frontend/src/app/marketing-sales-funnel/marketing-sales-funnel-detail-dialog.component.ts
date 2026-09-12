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
import { MatTooltipModule } from '@angular/material/tooltip';

import {
  MarketingSalesFunnelDetailKind,
  MarketingSalesFunnelDetailResponse,
  MarketingSalesFunnelDetailRow,
  MarketingSalesFunnelSortDirection,
} from './marketing-sales-funnel.models';
import { MarketingSalesFunnelService } from './marketing-sales-funnel.service';


export interface MarketingSalesFunnelDetailDialogData {
  month: string;
  metric: string;
  branchId?: number;
  origin?: string;
}

interface DetailColumn {
  key: string;
  label: string;
}


@Component({
  selector: 'app-marketing-sales-funnel-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTableModule,
    MatTooltipModule,
  ],
  templateUrl: './marketing-sales-funnel-detail-dialog.component.html',
  styleUrls: ['./marketing-sales-funnel-detail-dialog.component.css'],
})
export class MarketingSalesFunnelDetailDialogComponent implements OnInit {
  private readonly service = inject(MarketingSalesFunnelService);
  private readonly dialogRef = inject(
    MatDialogRef<MarketingSalesFunnelDetailDialogComponent>,
  );
  readonly data = inject<MarketingSalesFunnelDetailDialogData>(MAT_DIALOG_DATA);

  readonly pageSize = 50;

  detail: MarketingSalesFunnelDetailResponse | null = null;
  rows: MarketingSalesFunnelDetailRow[] = [];
  columns: DetailColumn[] = [];
  displayedColumns: string[] = [];

  loading = true;
  exporting = false;
  errorMessage = '';
  sortBy: string | undefined;
  sortDir: MarketingSalesFunnelSortDirection = 'asc';

  ngOnInit(): void {
    this.loadPage(1);
  }

  get canGoPrevious(): boolean {
    return Boolean(this.detail && this.detail.page > 1 && !this.loading);
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

    const start = (this.detail.page - 1) * this.detail.page_size + 1;
    const end = Math.min(
      this.detail.page * this.detail.page_size,
      this.detail.count,
    );
    return `${this.formatInteger(start)}–${this.formatInteger(end)} de ${this.formatInteger(this.detail.count)}`;
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

  toggleSort(column: string): void {
    if (this.loading) {
      return;
    }

    if (this.sortBy === column) {
      this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortBy = column;
      this.sortDir = 'asc';
    }

    this.loadPage(1);
  }

  sortIcon(column: string): string {
    if (this.sortBy !== column) {
      return 'unfold_more';
    }
    return this.sortDir === 'asc' ? 'arrow_upward' : 'arrow_downward';
  }

  sortTooltip(column: DetailColumn): string {
    if (this.sortBy !== column.key) {
      return `Ordenar por ${column.label}`;
    }
    return this.sortDir === 'asc'
      ? `Orden ascendente por ${column.label}. Clic para descendente.`
      : `Orden descendente por ${column.label}. Clic para ascendente.`;
  }

  formatCell(row: MarketingSalesFunnelDetailRow, column: string): string {
    const value = row[column as keyof MarketingSalesFunnelDetailRow];
    if (value === null || value === undefined || value === '') {
      return '—';
    }
    if (column === 'revenue') {
      return this.formatCurrency(Number(value));
    }
    return String(value);
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  exportExcel(): void {
    if (this.exporting || !this.detail) {
      return;
    }

    this.exporting = true;
    this.errorMessage = '';

    this.service
      .exportDetail(
        this.data.month,
        this.data.metric,
        this.data.branchId,
        this.data.origin,
        this.sortBy,
        this.sortDir,
      )
      .subscribe({
        next: (blob) => {
          this.exporting = false;
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = this.exportFilename();
          document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
          setTimeout(() => URL.revokeObjectURL(url), 0);
        },
        error: (error: HttpErrorResponse) => {
          this.exporting = false;
          this.errorMessage = this.resolveError(error, true);
        },
      });
  }

  private loadPage(page: number): void {
    this.loading = true;
    this.errorMessage = '';

    this.service
      .getDetail(
        this.data.month,
        this.data.metric,
        this.data.branchId,
        this.data.origin,
        page,
        this.pageSize,
        this.sortBy,
        this.sortDir,
      )
      .subscribe({
        next: (detail) => {
          this.loading = false;
          this.detail = detail;
          this.rows = detail.rows;
          this.sortBy = detail.sort_by || undefined;
          this.sortDir = detail.sort_dir || 'asc';
          this.columns = this.resolveColumns(detail.kind);
          this.displayedColumns = this.columns.map((column) => column.key);
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.errorMessage = this.resolveError(error, false);
        },
      });
  }

  private resolveColumns(kind: MarketingSalesFunnelDetailKind): DetailColumn[] {
    if (kind === 'visits') {
      return [
        { key: 'branch', label: 'Sucursal KPI' },
        { key: 'date', label: 'Fecha' },
        { key: 'phone', label: 'Teléfono' },
        { key: 'origin', label: 'Origen' },
        { key: 'source', label: 'Fuente' },
      ];
    }

    if (kind === 'leads') {
      return [
        { key: 'branch', label: 'Sucursal KPI' },
        { key: 'date', label: 'Fecha' },
        { key: 'name', label: 'Nombre' },
        { key: 'phone', label: 'Teléfono' },
        { key: 'channel', label: 'Canal' },
        { key: 'contact_id', label: 'ID contacto' },
      ];
    }

    return [
      { key: 'branch', label: 'Sucursal KPI' },
      { key: 'date', label: 'Fecha' },
      { key: 'name', label: 'Nombre' },
      { key: 'pin', label: 'PIN' },
      { key: 'phone', label: 'Teléfono' },
      { key: 'tariff', label: 'Tarifa' },
      { key: 'revenue', label: 'Ingreso' },
      { key: 'origin', label: 'Origen' },
      { key: 'survey', label: 'Encuesta' },
      { key: 'transaction_branch', label: 'Sucursal cobro' },
    ];
  }

  private exportFilename(): string {
    const metric = this.data.metric.replace(/[^A-Za-z0-9_-]+/g, '_');
    const branch = this.data.branchId !== undefined
      ? `_sucursal_${this.data.branchId}`
      : '';
    return `funnel_venta_nueva_${this.data.month}_${metric}${branch}.xlsx`;
  }

  private formatInteger(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private resolveError(error: HttpErrorResponse, exportRequest: boolean): string {
    const backendMessage = error.error?.message;
    if (typeof backendMessage === 'string' && backendMessage.trim()) {
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
