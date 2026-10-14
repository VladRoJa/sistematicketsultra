import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';

import {
  CampaignV2PortfolioReviewFlag, CampaignV2PortfolioReviewResponse,
  CampaignV2PortfolioReviewRow, CampaignV2PortfolioReviewState,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { MarketingCampaignV2ChannelPortfolioDialogComponent } from './marketing-campaign-v2-channel-portfolio-dialog.component';

type ReviewFilter = 'ALL' | 'ACTION' | 'DOCUMENTED' | 'DECLARED';

interface PresentationRow extends CampaignV2PortfolioReviewRow {
  stateLabel: string;
  reasonLabels: string[];
  requiresAction: boolean;
}

const ISSUE_LABELS: Record<CampaignV2PortfolioReviewFlag, string> = {
  MISSING_PORTFOLIO_CATALOG: 'Business ID no existe en el catálogo actual',
  HISTORICAL_BUSINESS_CHANGE: 'Se declararon distintos Business IDs en el historial',
  WABA_CROSS_BUSINESS: 'Mismo WABA declarado bajo negocios diferentes',
  MULTIPLE_DEFAULT_BRANCH: 'La sucursal tiene más de un canal predeterminado activo',
  OPERATOR_ONLY: 'Solo declaración del operador; pedir comprobante externo',
  WABA_NOT_RECORDED: 'WABA ID no registrado (opcional, no inventar)',
};

const STATE_LABELS: Record<CampaignV2PortfolioReviewState, string> = {
  PENDING: 'Sin evidencia',
  WITHDRAWN: 'Asociación retirada',
  DECLARED_UNVERIFIED: 'Declaración sin corroboración',
  DOCUMENTED_UNVERIFIED: 'Documento declarado · Meta no verificado',
  REVIEW_REQUIRED: 'Revisión necesaria',
};

@Component({
  selector: 'app-marketing-campaign-v2-portfolio-review-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule,
    MatDialogModule, MatFormFieldModule, MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-portfolio-review-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-portfolio-review-dialog.component.css'],
})
export class MarketingCampaignV2PortfolioReviewDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2PortfolioReviewDialogComponent>);

  readonly filter = new FormControl<ReviewFilter>('ACTION', { nonNullable: true });
  report: CampaignV2PortfolioReviewResponse | null = null;
  rows: PresentationRow[] = [];
  loading = false;
  error = '';

  ngOnInit(): void { this.reload(); }
  close(): void { this.dialogRef.close(); }

  get filteredRows(): PresentationRow[] {
    switch (this.filter.value) {
      case 'ACTION': return this.rows.filter(row => row.requiresAction);
      case 'DOCUMENTED': return this.rows.filter(row => row.review_state === 'DOCUMENTED_UNVERIFIED');
      case 'DECLARED': return this.rows.filter(row => row.review_state === 'DECLARED_UNVERIFIED');
      default: return this.rows;
    }
  }

  get actionCount(): number {
    return this.rows.filter(row => row.requiresAction).length;
  }

  reload(): void {
    if (this.loading) { return; }
    this.loading = true;
    this.error = '';
    this.api.listPortfolioReview().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: report => {
        this.report = report;
        this.rows = report.rows.map(row => ({
          ...row,
          stateLabel: STATE_LABELS[row.review_state],
          reasonLabels: row.flags.map(flag => ISSUE_LABELS[flag]),
          requiresAction: row.review_state !== 'DOCUMENTED_UNVERIFIED',
        }));
        this.loading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.report = null;
        this.rows = [];
        this.error = String(err.error?.message ||
          'No se pudo obtener el diagnóstico documental. Verifica permisos y migraciones.');
      },
    });
  }

  openEvidence(row: CampaignV2PortfolioReviewRow): void {
    const ref = this.dialog.open(MarketingCampaignV2ChannelPortfolioDialogComponent, {
      panelClass: 'campaign-v2-admin-dialog',
      width: 'min(1080px, 96vw)', maxWidth: '96vw',
      maxHeight: '94vh', autoFocus: false,
      data: { channelId: row.provider_channel_id },
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.reload());
  }
}
