import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Inject, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  CampaignV2ObservedFamily,
  CampaignV2RecipientDetail,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

export interface MarketingCampaignV2RecipientDetailDialogData {
  campaignId: number;
  recipientId: number;
}

@Component({
  selector: 'app-marketing-campaign-v2-recipient-detail-dialog',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatDialogModule, MatProgressSpinnerModule],
  templateUrl: './marketing-campaign-v2-recipient-detail-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-recipient-detail-dialog.component.css'],
})
export class MarketingCampaignV2RecipientDetailDialogComponent implements OnInit {
  private readonly service = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);

  recipient: CampaignV2RecipientDetail | null = null;
  loading = false;
  error = '';

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MarketingCampaignV2RecipientDetailDialogData,
  ) {}

  ngOnInit(): void {
    this.loading = true;
    this.service.getRecipient(this.data.campaignId, this.data.recipientId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: recipient => {
          this.loading = false;
          this.recipient = recipient;
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.error = this.errorMessage(error);
        },
      });
  }

  familyLabel(value: CampaignV2ObservedFamily | null): string {
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
    if (error.status === 404) {
      return 'Campaña no encontrada o no disponible.';
    }
    if (error.status === 403) {
      return 'No tienes acceso a este destinatario.';
    }
    const body = error.error as { message?: string } | null;
    return body?.message || 'No fue posible cargar la evidencia del destinatario.';
  }
}
