import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Inject, OnInit, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import {
  CampaignV2AudienceDefinition,
  CampaignV2CampaignDetail,
  CampaignV2DispatchTemplate,
  CampaignV2IndividualReport,
  CampaignV2ObservedFamily,
  CampaignV2PreflightResponse,
  CampaignV2Purpose,
  CampaignV2ProviderChildReportingRow,
  CampaignV2ProviderStatsCompleteness,
  CampaignV2SubmitResponse,
  CampaignV2RecipientSummary,
  CampaignV2Source,
  CampaignV2SourceMetadata,
} from './marketing-campaign-v2.models';
import {
  campaignV2DownloadBlob,
  campaignV2HistoricalTargetingMatchLabel,
  campaignV2HistoricalTargetingModeLabel,
  campaignV2HistoricalTargetingSummary,
  campaignV2HistoricalTargetingWindowLabel,
  campaignV2HistoryExclusionSummary,
  campaignV2HistoryWindowLabel,
  campaignV2IventasCurrentStatusLabel,
  campaignV2ReportingCostLabel,
  campaignV2ProviderBatchLabel,
  campaignV2ProviderBatchStatsLabel,
  campaignV2ProviderStatsLabel,
  campaignV2ReportingPercent,
  campaignV2ReportingSnapshotLabel,
  campaignV2ReportingValue,
} from './marketing-campaign-v2.logic';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import {
  MarketingCampaignV2RecipientDetailDialogComponent,
  MarketingCampaignV2RecipientDetailDialogData,
} from './marketing-campaign-v2-recipient-detail-dialog.component';
import {
  MarketingCampaignV2SubmitConfirmDialogComponent,
  MarketingCampaignV2SubmitConfirmDialogData,
} from './marketing-campaign-v2-submit-confirm-dialog.component';

export interface MarketingCampaignV2CampaignDetailDialogData {
  campaignId: number;
  purposes: CampaignV2Purpose[];
}

@Component({
  selector: 'app-marketing-campaign-v2-campaign-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-campaign-detail-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-campaign-detail-dialog.component.css'],
})
export class MarketingCampaignV2CampaignDetailDialogComponent implements OnInit {
  private readonly service = inject(MarketingCampaignV2Service);
  private readonly dialog = inject(MatDialog);
  private readonly dialogRef = inject(
    MatDialogRef<MarketingCampaignV2CampaignDetailDialogComponent, boolean>,
  );
  private readonly destroyRef = inject(DestroyRef);

  readonly purposeControl = new FormControl<CampaignV2Purpose>('UNCLASSIFIED', {
    nonNullable: true,
  });
  readonly dispatchTemplateControl = new FormControl<number | null>(null);

  campaign: CampaignV2CampaignDetail | null = null;
  reporting: CampaignV2IndividualReport | null = null;
  dispatchTemplates: CampaignV2DispatchTemplate[] = [];
  preflight: CampaignV2PreflightResponse | null = null;
  submitResult: CampaignV2SubmitResponse | null = null;
  recipients: CampaignV2RecipientSummary[] = [];
  recipientsPage = 1;
  readonly recipientsPageSize = 25;
  recipientsTotal = 0;
  recipientsTotalPages = 0;

  loadingCampaignDetail = false;
  loadingRecipients = false;
  loadingReporting = false;
  loadingDispatchTemplates = false;
  preflighting = false;
  submitting = false;
  exportingReporting = false;
  exportingDeliveryPackage = false;
  exportingSendablePackage = false;
  updatingPurpose = false;
  error = '';
  preflightError = '';
  submitError = '';
  submitSuccess = '';
  deliveryExportError = '';
  deliveryExportSuccess = '';
  sendableExportError = '';
  sendableExportSuccess = '';
  reportingError = '';
  reportingSuccess = '';
  purposeUpdated = false;

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MarketingCampaignV2CampaignDetailDialogData,
  ) {}

  ngOnInit(): void {
    this.dispatchTemplateControl.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.preflight = null;
        this.submitResult = null;
        this.preflightError = '';
        this.submitError = '';
        this.submitSuccess = '';
      });
    this.loadCampaign();
  }

  loadCampaign(): void {
    this.loadingCampaignDetail = true;
    this.error = '';
    this.service.getCampaign(this.data.campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: campaign => {
          this.loadingCampaignDetail = false;
          this.campaign = campaign;
          this.purposeControl.setValue(campaign.purpose, { emitEvent: false });
          this.loadRecipients(1);
          this.loadDispatchTemplates(campaign.purpose);
        },
        error: (error: HttpErrorResponse) => {
          this.loadingCampaignDetail = false;
          this.error = this.errorMessage(error, 'No fue posible cargar la campaña.');
        },
      });
  }

  loadRecipients(page: number): void {
    if (this.loadingRecipients) {
      return;
    }
    this.loadingRecipients = true;
    this.error = '';
    this.service.listRecipients(this.data.campaignId, page, this.recipientsPageSize)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.loadingRecipients = false;
          this.recipients = result.rows;
          this.recipientsPage = result.page;
          this.recipientsTotal = result.total;
          this.recipientsTotalPages = result.total_pages;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingRecipients = false;
          this.error = this.errorMessage(error, 'No fue posible cargar los destinatarios.');
        },
      });
  }

  loadDispatchTemplates(purpose: CampaignV2Purpose): void {
    if (this.loadingDispatchTemplates) {
      return;
    }
    this.loadingDispatchTemplates = true;
    this.preflight = null;
    this.preflightError = '';
    this.dispatchTemplates = [];
    this.dispatchTemplateControl.setValue(null, { emitEvent: false });

    this.service.listDispatchTemplates(purpose)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.loadingDispatchTemplates = false;
          this.dispatchTemplates = result.rows;
          if (result.rows.length === 1) {
            this.dispatchTemplateControl.setValue(result.rows[0].id);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.loadingDispatchTemplates = false;
          this.preflightError = this.errorMessage(
            error,
            'No fue posible cargar los templates de envío.',
          );
        },
      });
  }

  reviewDispatch(): void {
    const templateId = this.dispatchTemplateControl.value;
    if (!this.campaign || templateId === null || this.preflighting) {
      return;
    }

    this.preflighting = true;
    this.preflight = null;
    this.preflightError = '';
    this.service.preflightCampaign(this.campaign.id, templateId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.preflighting = false;
          this.preflight = result;
        },
        error: (error: HttpErrorResponse) => {
          this.preflighting = false;
          this.preflightError = this.errorMessage(
            error,
            'No fue posible preparar la revisión de envío.',
          );
        },
      });
  }

  get canReviewDispatch(): boolean {
    return Boolean(
      this.campaign
      && this.dispatchTemplateControl.value !== null
      && !this.loadingDispatchTemplates
      && !this.preflighting,
    );
  }

  get canSubmitDispatch(): boolean {
    const plan = this.preflight;
    if (!plan || !plan.ready || this.submitting) {
      return false;
    }
    const state = plan.submission;
    return Boolean(
      state.enabled
      && state.can_send
      && (state.status === 'NOT_STARTED' || state.status === 'READY'),
    );
  }

  submitAvailabilityLabel(): string {
    const plan = this.preflight;
    if (!plan) {
      return '';
    }
    if (!plan.submission.can_send) {
      return 'Tu usuario no tiene permiso de envío Campaign V2.';
    }
    if (!plan.submission.enabled) {
      return 'Envío real deshabilitado por kill switch backend.';
    }
    if (!plan.ready) {
      return 'El preflight tiene bloqueos.';
    }
    if (plan.submission.status === 'SUBMITTED') {
      return 'Los provider campaigns de este plan ya fueron enviados.';
    }
    if (plan.submission.status === 'SUBMITTING') {
      return 'Hay un provider campaign en proceso; no se permite otro submit.';
    }
    if (plan.submission.status === 'RECONCILIATION_REQUIRED') {
      return 'Existe un resultado ambiguo que requiere reconciliación antes de reintentar.';
    }
    if (plan.submission.status === 'PROVIDER_ERROR' || plan.submission.status === 'PARTIAL') {
      return 'Existe una operación parcial o fallida; M2 no permite retry automático.';
    }
    return 'El plan puede pasar a confirmación de envío inmediato.';
  }

  confirmAndSubmitDispatch(): void {
    const plan = this.preflight;
    if (!plan || !this.canSubmitDispatch || !plan.template) {
      return;
    }

    const ref = this.dialog.open<
      MarketingCampaignV2SubmitConfirmDialogComponent,
      MarketingCampaignV2SubmitConfirmDialogData,
      boolean
    >(MarketingCampaignV2SubmitConfirmDialogComponent, {
      width: 'min(720px, 96vw)',
      maxWidth: '96vw',
      maxHeight: '90vh',
      disableClose: true,
      data: {
        campaignName: plan.campaign_name,
        purposeLabel: this.purposeLabel(plan.campaign_purpose),
        templateName: plan.template.template_name,
        frozenCount: plan.frozen_count,
        blacklistedCount: plan.suppressed.blacklist,
        recipientCount: plan.sendable_count,
        providerCampaignCount: plan.provider_campaign_count,
        fingerprintVersion: plan.dispatch_fingerprint_version,
        fingerprint: plan.dispatch_fingerprint,
        batches: plan.batches.map(batch => ({
          trackLabel: batch.track_label,
          sucursalCanon: batch.sucursal_canon,
          channelId: batch.provider_channel_id || '—',
          recipientCount: batch.recipient_count,
        })),
      },
    });

    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(confirmed => {
        if (confirmed === true) {
          this.submitDispatch();
        }
      });
  }

  submitDispatch(): void {
    const plan = this.preflight;
    const templateId = this.dispatchTemplateControl.value;
    if (!plan || templateId === null || !this.canSubmitDispatch) {
      return;
    }

    this.submitting = true;
    this.submitError = '';
    this.submitSuccess = '';
    this.submitResult = null;

    this.service.submitCampaign(
      plan.campaign_id,
      templateId,
      plan.dispatch_fingerprint,
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.submitting = false;
          this.submitResult = result;
          this.submitSuccess = 'Submit aceptado y auditado por Suite.';
          this.reviewDispatch();
        },
        error: (error: HttpErrorResponse) => {
          this.submitting = false;
          this.submitError = this.errorMessage(
            error,
            'El submit no terminó completamente. Revisa el estado de los provider campaigns antes de cualquier otra acción.',
          );
          this.reviewDispatch();
        },
      });
  }

  preflightBlockedTotal(): number {
    const blocked = this.preflight?.blocked;
    if (!blocked) {
      return 0;
    }
    return (
      blocked.missing_branch
      + blocked.missing_channel
      + blocked.missing_required_variable
      + blocked.invalid_phone
      + blocked.template_channel_mismatch
    );
  }

  batchBlockLabel(reason: string): string {
    const labels: Record<string, string> = {
      MISSING_CHANNEL: 'Sin channel configurado',
      MISSING_REQUIRED_VARIABLE: 'Falta variable requerida',
      TEMPLATE_CHANNEL_MISMATCH: 'Template incompatible con channel',
    };
    return labels[reason] || reason;
  }

  loadReporting(): void {
    if (this.loadingReporting) {
      return;
    }
    this.loadingReporting = true;
    this.reportingError = '';
    this.reportingSuccess = '';

    this.service.getCampaignReport(this.data.campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: report => {
          this.loadingReporting = false;
          this.reporting = report;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingReporting = false;
          this.reporting = null;
          this.reportingError = this.errorMessage(
            error,
            'No fue posible cargar los resultados de Reporting.',
          );
        },
      });
  }

  exportReporting(): void {
    if (this.exportingReporting) {
      return;
    }
    this.exportingReporting = true;
    this.reportingError = '';
    this.reportingSuccess = '';

    this.service.exportCampaignReport(this.data.campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: blob => {
          this.exportingReporting = false;
          campaignV2DownloadBlob(
            blob,
            `campaign_v2_${this.data.campaignId}_report.xlsx`,
          );
          this.reportingSuccess = 'Reporte individual exportado.';
        },
        error: (error: HttpErrorResponse) => {
          this.exportingReporting = false;
          this.reportingError = this.errorMessage(
            error,
            'No fue posible exportar el reporte individual.',
          );
        },
      });
  }

  exportDeliveryPackage(): void {
    if (this.exportingDeliveryPackage || this.recipientsTotal <= 0) {
      return;
    }

    this.exportingDeliveryPackage = true;
    this.deliveryExportError = '';
    this.deliveryExportSuccess = '';

    this.service.exportCampaignDeliveryPackage(this.data.campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: blob => {
          this.exportingDeliveryPackage = false;
          campaignV2DownloadBlob(
            blob,
            this.deliveryPackageFilename(blob, 'COHORTE_CONGELADA'),
          );
          this.deliveryExportSuccess = 'Cohorte congelada exportada sin supresiones dinámicas.';
        },
        error: (error: HttpErrorResponse) => {
          this.exportingDeliveryPackage = false;
          this.deliveryExportError = this.errorMessage(
            error,
            'No fue posible exportar la cohorte congelada.',
          );
        },
      });
  }

  exportSendablePackage(): void {
    if (this.exportingSendablePackage || this.recipientsTotal <= 0) {
      return;
    }

    this.exportingSendablePackage = true;
    this.sendableExportError = '';
    this.sendableExportSuccess = '';

    this.service.exportCampaignSendablePackage(this.data.campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: blob => {
          this.exportingSendablePackage = false;
          campaignV2DownloadBlob(
            blob,
            this.deliveryPackageFilename(blob, 'LISTA_ENVIO'),
          );
          this.sendableExportSuccess = 'Lista para envío exportada con supresiones vigentes.';
        },
        error: (error: HttpErrorResponse) => {
          this.exportingSendablePackage = false;
          this.sendableExportError = this.errorMessage(
            error,
            'No fue posible exportar la lista para envío.',
          );
        },
      });
  }

  reportingPercent(value: number | null | undefined): string {
    return campaignV2ReportingPercent(value);
  }

  reportingValue(value: number | string | null | undefined): string {
    return campaignV2ReportingValue(value);
  }

  reportingSnapshotLabel(): string {
    return this.reporting
      ? campaignV2ReportingSnapshotLabel(this.reporting.observation)
      : '—';
  }

  reportingObservedAt(value: string | null): string {
    return value ? this.formatHistoryObservedAt(value) : '—';
  }

  reportingCostLabel(status: string): string {
    return campaignV2ReportingCostLabel(status);
  }

  providerStatsLabel(status: CampaignV2ProviderStatsCompleteness): string {
    return campaignV2ProviderStatsLabel(status);
  }

  providerBatchLabel(status: string): string {
    return campaignV2ProviderBatchLabel(status);
  }

  providerBatchStatsLabel(batch: CampaignV2ProviderChildReportingRow): string {
    return campaignV2ProviderBatchStatsLabel(batch);
  }

  previousRecipientsPage(): void {
    if (this.recipientsPage > 1) {
      this.loadRecipients(this.recipientsPage - 1);
    }
  }

  nextRecipientsPage(): void {
    if (this.recipientsPage < this.recipientsTotalPages) {
      this.loadRecipients(this.recipientsPage + 1);
    }
  }

  savePurpose(): void {
    if (!this.campaign || this.updatingPurpose) {
      return;
    }
    if (this.purposeControl.value === this.campaign.purpose) {
      return;
    }

    this.updatingPurpose = true;
    this.error = '';
    this.service.updatePurpose(this.campaign.id, this.purposeControl.value)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: campaign => {
          this.updatingPurpose = false;
          this.campaign = campaign;
          this.purposeUpdated = true;
          this.loadDispatchTemplates(campaign.purpose);
        },
        error: (error: HttpErrorResponse) => {
          this.updatingPurpose = false;
          this.error = this.errorMessage(error, 'No fue posible actualizar el purpose.');
        },
      });
  }

  openRecipient(recipient: CampaignV2RecipientSummary): void {
    this.dialog.open<
      MarketingCampaignV2RecipientDetailDialogComponent,
      MarketingCampaignV2RecipientDetailDialogData
    >(MarketingCampaignV2RecipientDetailDialogComponent, {
      width: 'min(980px, 96vw)',
      maxWidth: '96vw',
      maxHeight: '90vh',
      data: {
        campaignId: this.data.campaignId,
        recipientId: recipient.id,
      },
    });
  }

  close(): void {
    this.dialogRef.close(this.purposeUpdated);
  }

  purposeLabel(value: CampaignV2Purpose): string {
    const labels: Record<CampaignV2Purpose, string> = {
      NEW_SALE: 'Venta nueva',
      REACTIVATION: 'Reactivación',
      ACTIVE_MEMBERS: 'Socios activos',
      UNCLASSIFIED: 'Sin clasificar',
    };
    return labels[value];
  }

  sourceLabel(value: CampaignV2Source): string {
    const labels: Record<CampaignV2Source, string> = {
      EXPIRED_MEMBERS: 'Socios vencidos',
      ACTIVE_MEMBERS: 'Socios activos',
      FUNNEL_PORTFOLIO: 'Cartera Funnel / Venta Nueva',
    };
    return labels[value];
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

  filterRows(definition: CampaignV2AudienceDefinition): Array<{ label: string; value: string }> {
    const rows: Array<{ label: string; value: string }> = [
      { label: 'Fuente', value: this.sourceLabel(definition.filters.source) },
      {
        label: 'Alcance congelado',
        value: definition.filters.allowed_sucursal_keys === null
          ? 'Global autorizado'
          : `${definition.filters.allowed_sucursal_keys.length} sucursales`,
      },
    ];
    if (definition.filters.audience_families?.length) {
      rows.push({
        label: 'Familias',
        value: definition.filters.audience_families
          .map(value => this.familyLabel(value))
          .join(', '),
      });
    }
    if (definition.filters.funnel_month) {
      rows.push({ label: 'Mes Funnel', value: definition.filters.funnel_month });
    }
    if (definition.filters.funnel_cutoff_date) {
      rows.push({ label: 'Corte Funnel', value: definition.filters.funnel_cutoff_date });
    }
    if (definition.filters.expiration_date_from) {
      rows.push({ label: 'Vencimiento desde', value: definition.filters.expiration_date_from });
    }
    if (definition.filters.expiration_date_to) {
      rows.push({ label: 'Vencimiento hasta', value: definition.filters.expiration_date_to });
    }
    if (definition.filters.adeudo_min) {
      rows.push({
        label: 'Adeudo mínimo',
        value: this.currencyLabel(definition.filters.adeudo_min),
      });
    }
    if (definition.filters.iventas_current_statuses?.length) {
      rows.push({
        label: 'Estado actual en iVentas',
        value: definition.filters.iventas_current_statuses
          .map(campaignV2IventasCurrentStatusLabel)
          .join(', '),
      });
    }
    if (definition.filters.historical_targeting) {
      const targeting = definition.filters.historical_targeting;
      const conditionLabels = campaignV2HistoricalTargetingSummary(targeting);
      rows.push({
        label: 'Historial de campañas · Modo',
        value: campaignV2HistoricalTargetingModeLabel(targeting.mode),
      });
      rows.push({
        label: 'Historial de campañas · Cumplimiento',
        value: campaignV2HistoricalTargetingMatchLabel(targeting.match),
      });
      rows.push({
        label: 'Historial de campañas · Condiciones',
        value: conditionLabels.length ? conditionLabels.join(', ') : '—',
      });
      rows.push({
        label: 'Historial de campañas · Ventana',
        value: campaignV2HistoricalTargetingWindowLabel(targeting),
      });
    } else if (definition.filters.history_exclusion) {
      const exclusionLabels = campaignV2HistoryExclusionSummary(
        definition.filters.history_exclusion,
      );
      rows.push({
        label: 'Exclusión histórica',
        value: exclusionLabels.length ? exclusionLabels.join(', ') : '—',
      });
      rows.push({
        label: 'Ventana histórica legacy',
        value: campaignV2HistoryWindowLabel(definition.filters.history_exclusion),
      });
    }
    return rows;
  }

  metadataRows(metadata: CampaignV2SourceMetadata): Array<{ label: string; value: string }> {
    const rows: Array<{ label: string; value: string }> = [];
    const values: Array<[string, string | number | null | undefined]> = [
      ['Corte activos', metadata.activos_cutoff_date],
      ['Captura activos', metadata.activos_captured_at],
      ['Tipo de snapshot', metadata.snapshot_kind],
      ['Vencimiento desde', metadata.expiration_date_from],
      ['Vencimiento hasta', metadata.expiration_date_to],
      ['Corte de estado actual', metadata.current_status_activos_cutoff_date],
      ['Mes Funnel', metadata.funnel_month],
      ['Corte Funnel', metadata.funnel_cutoff_date],
      ['Corte Socios Activos', metadata.active_members_cutoff_date],
    ];
    for (const [label, value] of values) {
      if (value !== null && value !== undefined && value !== '') {
        rows.push({ label, value: String(value) });
      }
    }

    const historyEvaluation = metadata.history_evaluation;
    if (historyEvaluation?.observed_after) {
      rows.push({
        label: 'Historial observado desde',
        value: this.formatHistoryObservedAt(historyEvaluation.observed_after),
      });
    }
    if (historyEvaluation?.observed_before) {
      rows.push({
        label: 'Historial evaluado hasta',
        value: this.formatHistoryObservedAt(historyEvaluation.observed_before),
      });
    }
    return rows;
  }

  private deliveryPackageFilename(
    blob: Blob,
    label: 'COHORTE_CONGELADA' | 'LISTA_ENVIO',
  ): string {
    const normalized = (this.campaign?.name || `CAMPANA_V2_${this.data.campaignId}`)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 80) || `CAMPANA_V2_${this.data.campaignId}`;
    const extension = blob.type === 'application/zip' ? 'zip' : 'xlsx';
    return `${normalized}__${label}.${extension}`;
  }

  private currencyLabel(value: string): string {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return value;
    }
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(parsed);
  }

  private formatHistoryObservedAt(value: string): string {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/Tijuana',
    }).format(parsed);
  }

  private errorMessage(error: HttpErrorResponse, fallback: string): string {
    if (error.status === 404) {
      return 'Campaña no encontrada o no disponible.';
    }
    if (error.status === 403) {
      return 'No tienes acceso a esta campaña.';
    }
    const body = error.error as { message?: string } | null;
    return body?.message || fallback;
  }
}
