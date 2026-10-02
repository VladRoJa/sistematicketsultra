import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Inject, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2ObservedFamily,
  CampaignV2PreviewBucket,
  CampaignV2PreviewDetailResponse,
} from './marketing-campaign-v2.models';
import { campaignV2HistoryReasonLabel } from './marketing-campaign-v2.logic';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

export interface MarketingCampaignV2PreviewDetailDialogData {
  audience: CampaignV2AudienceDefinitionRequest;
  bucket: CampaignV2PreviewBucket;
  audienceFamily?: CampaignV2ObservedFamily;
}

@Component({
  selector: 'app-marketing-campaign-v2-preview-detail-dialog',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatDialogModule, MatProgressSpinnerModule],
  templateUrl: './marketing-campaign-v2-preview-detail-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-preview-detail-dialog.component.css'],
})
export class MarketingCampaignV2PreviewDetailDialogComponent implements OnInit {
  private readonly service = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);

  response: CampaignV2PreviewDetailResponse | null = null;
  loading = false;
  error = '';
  readonly pageSize = 25;

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MarketingCampaignV2PreviewDetailDialogData,
  ) {}

  ngOnInit(): void {
    this.load(1);
  }

  get title(): string {
    if (this.data.bucket === 'FAMILY' && this.data.audienceFamily) {
      return `Detalle · ${this.familyLabel(this.data.audienceFamily)}`;
    }
    const labels: Record<CampaignV2PreviewBucket, string> = {
      RECIPIENTS: 'Destinatarios finales',
      INVALID_PHONE: 'Teléfonos inválidos',
      DUPLICATES: 'Duplicados',
      OUT_OF_SEGMENT: 'Fuera de segmento',
      UNCLASSIFIED: 'Tarifa sin clasificación',
      FAMILY: 'Familia',
      CURRENT_STATUS_BLOCKED: 'Bloqueados por estado actual',
      HISTORY_EXCLUDED: 'Excluidos por historial',
    };
    return labels[this.data.bucket];
  }

  load(page: number): void {
    if (this.loading) {
      return;
    }
    this.loading = true;
    this.error = '';

    this.service.previewDetail({
      ...this.data.audience,
      bucket: this.data.bucket,
      audience_family: this.data.audienceFamily,
      page,
      page_size: this.pageSize,
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: response => {
          this.loading = false;
          this.response = response;
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.error = this.errorMessage(error);
        },
      });
  }

  previousPage(): void {
    if (this.response && this.response.page > 1) {
      this.load(this.response.page - 1);
    }
  }

  nextPage(): void {
    if (this.response && this.response.page < this.response.pages) {
      this.load(this.response.page + 1);
    }
  }

  historyReasonsLabel(reasons: string[] | undefined): string {
    if (!reasons?.length) {
      return '—';
    }
    return reasons.map(campaignV2HistoryReasonLabel).join(', ');
  }

  familyLabel(value: CampaignV2ObservedFamily | null | undefined): string {
    if (!value) {
      return '—';
    }
    const labels: Record<CampaignV2ObservedFamily, string> = {
      DOMICILIADO: 'Domiciliado',
      TRIMESTRAL: 'Trimestral',
      CONVENIO: 'Convenio',
      SEMESTRE: 'Semestre',
      ESTUDIANTE: 'Estudiante',
      MES: 'Mes',
      OUT_OF_SEGMENT: 'Fuera de segmento',
    };
    return labels[value];
  }

  private errorMessage(error: HttpErrorResponse): string {
    if (error.status === 409) {
      return 'El detalle ya no coincide con el Preview. Cierra este panel y vuelve a revisar la audiencia.';
    }
    if (error.status === 403) {
      return 'No tienes acceso a este detalle.';
    }
    const body = error.error as { message?: string } | null;
    return body?.message || 'No fue posible cargar el detalle del Preview.';
  }
}
