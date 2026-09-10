import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  CampaignAudienceBucket,
  CampaignAudienceCompositionRow,
  CampaignAudiencePreviewDetailResponse,
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
    MatButtonModule,
    MatDialogModule,
    MatProgressSpinnerModule,
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
  result: CampaignAudiencePreviewDetailResponse | null = null;
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

  loadPage(page: number): void {
    if (this.loading || page < 1) return;
    this.loading = true;
    this.error = '';

    this.service.previewCampaignDetail({
      ...this.data.request,
      bucket: this.data.bucket,
      page,
      page_size: this.pageSize,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.result = result;
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
