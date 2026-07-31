import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import {
  FormControl,
  ReactiveFormsModule,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import {
  MatSnackBar,
  MatSnackBarModule,
} from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  debounceTime,
  distinctUntilChanged,
} from 'rxjs';

import {
  MarketingAttributionDetailResponse,
  MarketingAttributionDetailRow,
} from './marketing.models';
import {
  MarketingExcelExportService,
} from './marketing-excel-export.service';
import { MarketingService } from './marketing.service';

export interface MarketingAttributionDialogData {
  month: string;
  branchId?: number;
  branchName?: string;
}

@Component({
  selector: 'app-marketing-attribution-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTableModule,
    ReactiveFormsModule,
  ],
  templateUrl:
    './marketing-attribution-detail-dialog.component.html',
  styleUrls: [
    './marketing-attribution-detail-dialog.component.css',
  ],
})
export class MarketingAttributionDetailDialogComponent
  implements OnInit
{
  private readonly destroyRef = inject(DestroyRef);
  private readonly marketingService = inject(MarketingService);
  private readonly excelExport = inject(
    MarketingExcelExportService,
  );
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialogRef = inject(
    MatDialogRef<MarketingAttributionDetailDialogComponent>,
  );

  readonly data = inject(
    MAT_DIALOG_DATA,
  ) as MarketingAttributionDialogData;

  readonly searchControl = new FormControl('', {
    nonNullable: true,
  });

  readonly onlyNonPositiveControl = new FormControl(false, {
    nonNullable: true,
  });

  private readonly globalColumns = [
    'sucursal',
    'socio',
    'visita',
    'pago',
    'dias',
    'membresia',
    'tarifa',
    'ingreso',
  ];

  private readonly branchColumns = [
    'socio',
    'visita',
    'pago',
    'dias',
    'membresia',
    'tarifa',
    'ingreso',
  ];

  get columns(): string[] {
    return this.data.branchId === undefined
      ? this.globalColumns
      : this.branchColumns;
  }

  get isBranchDetail(): boolean {
    return this.data.branchId !== undefined;
  }

  detail: MarketingAttributionDetailResponse | null = null;
  rows: MarketingAttributionDetailRow[] = [];
  filteredRows: MarketingAttributionDetailRow[] = [];

  loading = true;
  errorMessage = '';
  exportingCohort = false;

  get title(): string {
    return this.data.branchName
      ? `Ventas atribuidas · ${this.data.branchName}`
      : 'Ventas atribuidas · Todas las sucursales';
  }

  get resultCountLabel(): string {
    return `${this.filteredRows.length} de ${this.rows.length} ventas`;
  }

  get nonPositiveFilterActive(): boolean {
    return this.onlyNonPositiveControl.value;
  }

  get nonPositiveActionLabel(): string {
    return this.nonPositiveFilterActive
      ? 'Mostrar todas las ventas'
      : 'Ver ventas que requieren revisión';
  }

  ngOnInit(): void {
    this.searchControl.valueChanges
      .pipe(
        debounceTime(150),
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.applyFilters());

    this.onlyNonPositiveControl.valueChanges
      .pipe(
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.applyFilters());

    this.loadDetail();
  }

  loadDetail(): void {
    this.loading = true;
    this.errorMessage = '';

    this.marketingService
      .getAttributions(
        this.data.month,
        this.data.branchId,
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.detail = response;
          this.rows = response.rows;
          this.applyFilters();
          this.loading = false;
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.errorMessage = this.resolveErrorMessage(error);
        },
      });
  }

  async exportCohort(): Promise<void> {
    if (!this.detail || this.exportingCohort) {
      return;
    }

    this.exportingCohort = true;

    try {
      await this.excelExport.exportAttributionCohort(
        this.detail,
      );

      this.snackBar.open(
        'Excel de cohorte generado.',
        'Cerrar',
        {
          duration: 3000,
        },
      );
    } catch {
      this.snackBar.open(
        'No fue posible generar el Excel de cohorte.',
        'Cerrar',
        {
          duration: 4500,
        },
      );
    } finally {
      this.exportingCohort = false;
    }
  }

  close(): void {
    this.dialogRef.close();
  }

  toggleNonPositiveFilter(): void {
    if (
      !this.detail ||
      this.detail.summary.non_positive_sales === 0
    ) {
      return;
    }

    this.onlyNonPositiveControl.setValue(
      !this.onlyNonPositiveControl.value,
    );
  }

  trackRow(
    _index: number,
    row: MarketingAttributionDetailRow,
  ): string {
    return `${row.sale_key}:${row.sucursal_id}`;
  }

  formatCurrency(value: number | null): string {
    if (value === null) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 2,
    }).format(value);
  }

  formatDate(value: string): string {
    const date = new Date(`${value}T12:00:00`);

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(date);
  }

  private applyFilters(): void {
    const query = this.normalizeText(
      this.searchControl.value,
    );
    const onlyNonPositive =
      this.onlyNonPositiveControl.value;

    this.filteredRows = this.rows.filter((row) => {
      if (
        onlyNonPositive &&
        !row.venta_sin_ingreso_positivo
      ) {
        return false;
      }

      if (!query) {
        return true;
      }

      const searchableText = [
        row.sucursal,
        row.socio,
        row.id_socio,
        row.id_folio,
        row.telefono,
        row.tipo_visita,
        row.tipo_membresia,
        row.tarifa,
        row.inscripcion,
        row.pase,
        row.lugar_pago,
        row.fecha_visita,
        row.fecha_pago,
        row.total_pagado,
      ]
        .map((value) => String(value ?? ''))
        .join(' ');

      return this.normalizeText(searchableText).includes(query);
    });
  }

  private normalizeText(value: string): string {
    return value
      .trim()
      .toLocaleLowerCase('es-MX')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  private resolveErrorMessage(
    error: HttpErrorResponse,
  ): string {
    const backendMessage = error.error?.message;

    return typeof backendMessage === 'string' &&
      backendMessage.trim()
      ? backendMessage.trim()
      : 'No fue posible cargar el detalle atribuido.';
  }
}
