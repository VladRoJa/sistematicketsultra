import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import {
  CampaignAudienceBucket,
  CampaignAudienceCompositionRow,
  CampaignAudienceExplorerFilters,
  CampaignAudienceIventasStatusFilter,
  CampaignAudiencePreviewDetailResponse,
  CampaignAudienceSuiteHistoryFilter,
  CampaignV1Request,
} from './marketing-reactivation.models';
import { MarketingReactivationService } from './marketing-reactivation.service';

export interface MarketingAudienceExplorerDialogData {
  request: CampaignV1Request;
  bucket: CampaignAudienceBucket;
  label: string;
}

@Component({
  selector: 'app-marketing-audience-explorer-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './marketing-audience-explorer-dialog.component.html',
  styleUrls: ['./marketing-audience-explorer-dialog.component.css'],
})
export class MarketingAudienceExplorerDialogComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly service = inject(MarketingReactivationService);
  private readonly dialogRef = inject(
    MatDialogRef<MarketingAudienceExplorerDialogComponent>,
  );

  readonly data = inject<MarketingAudienceExplorerDialogData>(MAT_DIALOG_DATA);
  readonly pageSize = 50;
  readonly filterForm = new FormGroup({
    sucursal: new FormControl('', {nonNullable: true}),
    tariffCategory: new FormControl('', {nonNullable: true}),
    tarifa: new FormControl('', {nonNullable: true}),
    adeudoMin: new FormControl<number | null>(null),
    adeudoMax: new FormControl<number | null>(null),
    operationalStatus: new FormControl('', {nonNullable: true}),
    suiteHistory: new FormControl<CampaignAudienceSuiteHistoryFilter | ''>('', {nonNullable: true}),
    iventasStatus: new FormControl<CampaignAudienceIventasStatusFilter | ''>('', {nonNullable: true}),
  });
  readonly suiteHistoryOptions: Array<{
    value: CampaignAudienceSuiteHistoryFilter;
    label: string;
  }> = [
    {value: 'NEVER', label: 'Nunca exportado'},
    {value: 'ONE', label: '1 campaña exportada'},
    {value: 'TWO_PLUS', label: '2 o más campañas'},
  ];
  readonly iventasStatusOptions: Array<{
    value: CampaignAudienceIventasStatusFilter;
    label: string;
  }> = [
    {value: 'NONE', label: 'Sin estado'},
    {value: 'SENT', label: 'Enviado'},
    {value: 'DELIVERED', label: 'Entregado'},
    {value: 'VIEWED', label: 'Visto'},
    {value: 'FAILED', label: 'Fallido'},
  ];

  result: CampaignAudiencePreviewDetailResponse | null = null;
  appliedFilters: CampaignAudienceExplorerFilters = {};
  page = 1;
  loading = false;
  error = '';

  ngOnInit(): void {
    this.loadPage(1);
  }

  get compositionTop(): CampaignAudienceCompositionRow[] {
    return (this.result?.composition ?? []).slice(0, 10);
  }

  get operationalSummary(): Array<{ key: string; label: string; value: number }> {
    const counts = this.result?.operational_counts ?? {};
    return Object.entries(counts)
      .filter(([, value]) => value > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([key, value]) => ({
        key,
        label: this.operationalLabel(key),
        value,
      }));
  }

  get pageLabel(): string {
    if (!this.result) return '';
    return `Página ${this.result.pagination.page} de ${this.result.pagination.total_pages}`;
  }

  get headerCountLabel(): string {
    if (!this.result) return '';
    if (this.result.filtered_total !== this.result.total) {
      return `${this.formatNumber(this.result.filtered_total)} de ${this.formatNumber(this.result.total)} contactos después de filtros.`;
    }
    return `${this.formatNumber(this.result.total)} contactos en esta etapa.`;
  }

  get hasActiveFilters(): boolean {
    return Object.keys(this.appliedFilters).length > 0;
  }

  loadPage(
    page: number,
    explorerFilters: CampaignAudienceExplorerFilters = this.appliedFilters,
  ): void {
    if (this.loading || page < 1) return;
    this.loading = true;
    this.error = '';
    const requestedFilters = {...explorerFilters};

    this.service.previewCampaignDetail({
      ...this.data.request,
      bucket: this.data.bucket,
      page,
      page_size: this.pageSize,
      explorer_filters: requestedFilters,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.result = result;
        this.appliedFilters = {...result.explorer_filters};
        this.page = result.pagination.page;
        this.loading = false;
      },
      error: error => {
        this.loading = false;
        this.error = this.errorMessage(
          error,
          'No fue posible cargar el detalle de la audiencia.',
        );
      },
    });
  }

  applyFilters(): void {
    if (this.loading) return;
    const filters = this.buildExplorerFilters();
    if (filters === null) return;
    this.loadPage(1, filters);
  }

  clearFilters(): void {
    if (this.loading) return;
    this.filterForm.reset({
      sucursal: '',
      tariffCategory: '',
      tarifa: '',
      adeudoMin: null,
      adeudoMax: null,
      operationalStatus: '',
      suiteHistory: '',
      iventasStatus: '',
    });
    this.loadPage(1, {});
  }

  previousPage(): void {
    if (!this.result?.pagination.has_prev) return;
    this.loadPage(this.page - 1);
  }

  nextPage(): void {
    if (!this.result?.pagination.has_next) return;
    this.loadPage(this.page + 1);
  }

  close(): void {
    this.dialogRef.close();
  }

  operationalLabel(value: string | null): string {
    const labels: Record<string, string> = {
      AVAILABLE: 'Disponible',
      CONTACTED_THIS_MONTH: 'Contactado este mes',
      REVIEW_IDENTITY: 'Identidad por revisar',
      ACTIVE: 'Activo',
      SIN_ESTADO: 'Sin estado',
    };
    return value ? (labels[value] ?? value) : 'Sin estado';
  }

  iventasLabel(value: string | null): string {
    const normalized = (value ?? '').toLowerCase();
    const labels: Record<string, string> = {
      viewed: 'Visto',
      delivered: 'Entregado',
      sent: 'Enviado',
      failed: 'Fallido',
    };
    return labels[normalized] ?? (value || 'Sin estado');
  }

  formatDate(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(`${value}T12:00:00Z`));
  }

  formatDateTime(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/Tijuana',
    }).format(new Date(value));
  }

  formatMoney(value: string | null): string {
    if (value === null || value === '') return '—';
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return value;
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 2,
    }).format(numeric);
  }

  private buildExplorerFilters(): CampaignAudienceExplorerFilters | null {
    const value = this.filterForm.getRawValue();
    if (value.adeudoMin !== null && (!Number.isFinite(value.adeudoMin) || value.adeudoMin < 0)) {
      this.error = 'El adeudo mínimo debe ser un número igual o mayor a cero.';
      return null;
    }
    if (value.adeudoMax !== null && (!Number.isFinite(value.adeudoMax) || value.adeudoMax < 0)) {
      this.error = 'El adeudo máximo debe ser un número igual o mayor a cero.';
      return null;
    }
    if (
      value.adeudoMin !== null
      && value.adeudoMax !== null
      && value.adeudoMin > value.adeudoMax
    ) {
      this.error = 'El adeudo mínimo no puede ser mayor que el adeudo máximo.';
      return null;
    }

    const filters: CampaignAudienceExplorerFilters = {};
    if (value.sucursal) filters.sucursal = value.sucursal;
    if (value.tariffCategory) filters.tariff_category = value.tariffCategory;
    if (value.tarifa) filters.tarifa = value.tarifa;
    if (value.adeudoMin !== null) filters.adeudo_min = value.adeudoMin;
    if (value.adeudoMax !== null) filters.adeudo_max = value.adeudoMax;
    if (value.operationalStatus) filters.operational_status = value.operationalStatus;
    if (value.suiteHistory) filters.suite_history = value.suiteHistory;
    if (value.iventasStatus) filters.iventas_status = value.iventasStatus;
    return filters;
  }

  private formatNumber(value: number): string {
    return new Intl.NumberFormat('es-MX').format(value);
  }

  private errorMessage(error: unknown, fallback: string): string {
    if (
      error instanceof HttpErrorResponse
      && error.error
      && typeof error.error.message === 'string'
    ) {
      return error.error.message;
    }
    return fallback;
  }
}
