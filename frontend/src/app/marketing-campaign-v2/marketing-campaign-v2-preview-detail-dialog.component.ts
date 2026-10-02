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
import {
  campaignV2HistoryDecisionLabel,
  campaignV2HistoryMatchedLabel,
  campaignV2HistoryReasonsLabel,
} from './marketing-campaign-v2.logic';
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
      HISTORY_EXCLUDED: 'Excluidos por regla histórica',
      HISTORY_INCLUDED: 'Incluidos por regla histórica',
      FUNNEL_CANDIDATES: 'Leads Funnel',
      FUNNEL_BUYER_EXCLUDED: 'Compradores excluidos',
      ACTIVE_MEMBER_SUPPRESSION: 'Socios activos excluidos',
    };
    return labels[this.data.bucket];
  }

  get explanation(): string {
    if (this.data.bucket === 'HISTORY_INCLUDED') {
      return 'Contactos que permanecieron después de aplicar la regla histórica.';
    }
    if (this.data.bucket === 'HISTORY_EXCLUDED') {
      return 'Contactos descartados por el resultado de la regla histórica.';
    }
    if (this.data.bucket === 'FUNNEL_BUYER_EXCLUDED') {
      return 'Conversión detectada por la lógica Funnel vigente.';
    }
    if (this.data.bucket === 'ACTIVE_MEMBER_SUPPRESSION') {
      return 'El número está asociado actualmente a Socios Activos; no implica identidad humana.';
    }
    return '';
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

  isHistoryDecisionBucket(): boolean {
    return this.data.bucket === 'HISTORY_INCLUDED'
      || this.data.bucket === 'HISTORY_EXCLUDED';
  }

  historyDecisionLabel(
    value: CampaignV2PreviewDetailResponse['rows'][number]['history_decision'],
  ): string {
    return campaignV2HistoryDecisionLabel(value);
  }

  historyMatchedLabel(value: boolean | undefined): string {
    return campaignV2HistoryMatchedLabel(value);
  }

  historyReasonsLabel(
    row: CampaignV2PreviewDetailResponse['rows'][number],
  ): string {
    return campaignV2HistoryReasonsLabel(
      row.history_reasons,
      row.history_exclusion_reasons,
    );
  }


  evidenceLabel(value: CampaignV2PreviewDetailResponse['rows'][number]['evidence']): string {
    if (!Array.isArray(value) || !value.length || typeof value[0] !== 'string') {
      return '—';
    }
    return (value as string[]).join(', ');
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
