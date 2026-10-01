import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxChange, MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import {
  buildCampaignV2AudienceRequest,
  buildCampaignV2FreezeRequest,
  campaignV2FreezeErrorInvalidatesPreview,
  campaignV2MetricBucket,
  canFreezeCampaignV2,
  isCampaignV2AudienceValid,
  selectAllCampaignV2Families,
  toggleCampaignV2Family,
} from './marketing-campaign-v2.logic';
import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2AudienceFamily,
  CampaignV2CampaignSummary,
  CampaignV2ObservedFamily,
  CampaignV2OptionsResponse,
  CampaignV2PreviewBucket,
  CampaignV2PreviewResponse,
  CampaignV2Purpose,
  CampaignV2Source,
  CampaignV2SourceMetadata,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import {
  MarketingCampaignV2PreviewDetailDialogComponent,
  MarketingCampaignV2PreviewDetailDialogData,
} from './marketing-campaign-v2-preview-detail-dialog.component';
import {
  MarketingCampaignV2CampaignDetailDialogComponent,
  MarketingCampaignV2CampaignDetailDialogData,
} from './marketing-campaign-v2-campaign-detail-dialog.component';

@Component({
  selector: 'app-marketing-campaign-v2-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-page.component.html',
  styleUrls: ['./marketing-campaign-v2-page.component.css'],
})
export class MarketingCampaignV2PageComponent implements OnInit {
  private readonly service = inject(MarketingCampaignV2Service);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  readonly source = new FormControl<CampaignV2Source>('EXPIRED_MEMBERS', {
    nonNullable: true,
  });
  readonly expirationDateFrom = new FormControl('', { nonNullable: true });
  readonly expirationDateTo = new FormControl('', { nonNullable: true });
  readonly name = new FormControl('', { nonNullable: true });
  readonly purpose = new FormControl<CampaignV2Purpose>('UNCLASSIFIED', {
    nonNullable: true,
  });
  readonly historyPurpose = new FormControl<CampaignV2Purpose | ''>('', {
    nonNullable: true,
  });
  readonly historySource = new FormControl<CampaignV2Source | ''>('', {
    nonNullable: true,
  });

  options: CampaignV2OptionsResponse | null = null;
  selectedFamilies: CampaignV2AudienceFamily[] = [];
  preview: CampaignV2PreviewResponse | null = null;
  campaigns: CampaignV2CampaignSummary[] = [];

  loadingOptions = false;
  loadingPreview = false;
  creating = false;
  loadingCampaigns = false;
  accessDenied = false;
  error = '';
  success = '';

  campaignPage = 1;
  readonly campaignPageSize = 25;
  campaignTotal = 0;
  campaignTotalPages = 0;

  private previewRequest: CampaignV2AudienceDefinitionRequest | null = null;

  ngOnInit(): void {
    this.source.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(source => {
        if (source === 'ACTIVE_MEMBERS') {
          this.expirationDateFrom.setValue('', { emitEvent: false });
          this.expirationDateTo.setValue('', { emitEvent: false });
        }
        this.invalidatePreview();
      });

    this.expirationDateFrom.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.expirationDateTo.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());

    this.loadOptions();
  }

  get isExpiredSource(): boolean {
    return this.source.value === 'EXPIRED_MEMBERS';
  }

  get canReviewAudience(): boolean {
    return Boolean(
      this.options
      && !this.loadingPreview
      && !this.creating
      && isCampaignV2AudienceValid(this.audienceState()),
    );
  }

  get canFreeze(): boolean {
    return canFreezeCampaignV2({
      preview: this.preview,
      name: this.name.value,
      purpose: this.purpose.value,
      creating: this.creating || this.loadingPreview,
    });
  }

  get scopeLabel(): string {
    if (!this.options) {
      return '';
    }
    if (this.options.scope.is_global) {
      return 'Alcance: todas las sucursales autorizadas';
    }
    const count = this.options.scope.allowed_sucursal_keys?.length ?? 0;
    return count === 1
      ? 'Alcance backend: 1 sucursal autorizada'
      : `Alcance backend: ${count} sucursales autorizadas`;
  }

  get observedFamilies(): CampaignV2ObservedFamily[] {
    const selectable = this.options?.selectable_audience_families ?? [];
    return [...selectable, 'MES', 'OUT_OF_SEGMENT'];
  }

  loadOptions(): void {
    if (this.loadingOptions) {
      return;
    }
    this.loadingOptions = true;
    this.accessDenied = false;
    this.error = '';

    this.service.getOptions()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: options => {
          this.loadingOptions = false;
          this.options = options;
          this.ensureOptionDefaults(options);
          this.loadCampaigns(1);
        },
        error: (error: HttpErrorResponse) => {
          this.loadingOptions = false;
          this.options = null;
          this.campaigns = [];
          if (error.status === 403) {
            this.accessDenied = true;
            this.error = 'No tienes acceso a Campañas V2.';
            return;
          }
          this.error = this.errorMessage(error, 'No fue posible cargar Campañas V2.');
        },
      });
  }

  setFamilySelected(
    family: CampaignV2AudienceFamily,
    change: MatCheckboxChange,
  ): void {
    const available = this.options?.selectable_audience_families ?? [];
    this.selectedFamilies = toggleCampaignV2Family(
      this.selectedFamilies,
      family,
      change.checked,
      available,
    );
    this.invalidatePreview();
  }

  isFamilySelected(family: CampaignV2AudienceFamily): boolean {
    return this.selectedFamilies.includes(family);
  }

  selectAllFamilies(): void {
    this.selectedFamilies = selectAllCampaignV2Families(
      this.options?.selectable_audience_families ?? [],
    );
    this.invalidatePreview();
  }

  clearFamilies(): void {
    this.selectedFamilies = [];
    this.invalidatePreview();
  }

  reviewAudience(): void {
    if (!this.canReviewAudience) {
      this.error = this.audienceValidationMessage();
      return;
    }

    const request = buildCampaignV2AudienceRequest(this.audienceState());
    this.loadingPreview = true;
    this.error = '';
    this.success = '';
    this.preview = null;
    this.previewRequest = null;

    this.service.preview(request)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: preview => {
          this.loadingPreview = false;
          this.preview = preview;
          this.previewRequest = request;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingPreview = false;
          this.error = this.errorMessage(error, 'No fue posible revisar la audiencia.');
        },
      });
  }

  openMetric(
    metric:
      | 'recipients'
      | 'invalid_phone'
      | 'duplicates'
      | 'out_of_segment'
      | 'unclassified'
      | 'current_status_blocked',
    count: number,
  ): void {
    if (count <= 0) {
      return;
    }
    this.openPreviewDetail(campaignV2MetricBucket(metric));
  }

  openFamily(family: CampaignV2ObservedFamily): void {
    const count = this.preview?.family_counts?.[family] ?? 0;
    if (count <= 0) {
      return;
    }
    this.openPreviewDetail('FAMILY', family);
  }

  freezeCampaign(): void {
    if (!this.canFreeze || !this.preview || !this.previewRequest) {
      return;
    }

    this.creating = true;
    this.error = '';
    this.success = '';

    const request = buildCampaignV2FreezeRequest(
      this.previewRequest,
      this.name.value,
      this.purpose.value,
      this.preview.preview_fingerprint,
    );

    this.service.freeze(request)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.creating = false;
          this.success = `Campaña "${result.name}" creada con ${result.recipient_count} destinatarios.`;
          this.resetBuilderAfterFreeze();
          this.loadCampaigns(1);
        },
        error: (error: HttpErrorResponse) => {
          this.creating = false;
          if (campaignV2FreezeErrorInvalidatesPreview(error.status)) {
            const serverMessage = this.serverMessage(error);
            this.invalidatePreview();
            this.error = serverMessage?.toLowerCase().includes('vacía')
              ? 'La audiencia ya no es congelable. Vuelve a revisar la audiencia.'
              : 'La audiencia cambió desde la última revisión. Vuelve a revisar antes de crear la campaña.';
            return;
          }
          this.error = this.errorMessage(error, 'No fue posible crear la campaña.');
        },
      });
  }

  loadCampaigns(page = this.campaignPage): void {
    if (!this.options || this.accessDenied || this.loadingCampaigns) {
      return;
    }

    this.loadingCampaigns = true;
    this.error = '';
    this.service.listCampaigns({
      page,
      page_size: this.campaignPageSize,
      purpose: this.historyPurpose.value || undefined,
      source: this.historySource.value || undefined,
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.loadingCampaigns = false;
          this.campaigns = result.rows;
          this.campaignPage = result.page;
          this.campaignTotal = result.total;
          this.campaignTotalPages = result.total_pages;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingCampaigns = false;
          if (error.status === 403) {
            this.accessDenied = true;
            this.campaigns = [];
            this.error = 'No tienes acceso a Campañas V2.';
            return;
          }
          this.error = this.errorMessage(error, 'No fue posible cargar el historial.');
        },
      });
  }

  previousCampaignPage(): void {
    if (this.campaignPage > 1) {
      this.loadCampaigns(this.campaignPage - 1);
    }
  }

  nextCampaignPage(): void {
    if (this.campaignPage < this.campaignTotalPages) {
      this.loadCampaigns(this.campaignPage + 1);
    }
  }

  openCampaign(campaign: CampaignV2CampaignSummary): void {
    const ref = this.dialog.open<
      MarketingCampaignV2CampaignDetailDialogComponent,
      MarketingCampaignV2CampaignDetailDialogData,
      boolean
    >(MarketingCampaignV2CampaignDetailDialogComponent, {
      width: 'min(1180px, 96vw)',
      maxWidth: '96vw',
      maxHeight: '92vh',
      data: {
        campaignId: campaign.id,
        purposes: this.options?.purposes ?? [],
      },
    });

    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(updated => {
        if (updated) {
          this.loadCampaigns(this.campaignPage);
        }
      });
  }

  familyCount(family: CampaignV2ObservedFamily): number {
    return this.preview?.family_counts?.[family] ?? 0;
  }

  familyLabel(value: CampaignV2ObservedFamily | CampaignV2AudienceFamily): string {
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

  sourceLabel(value: CampaignV2Source): string {
    return value === 'ACTIVE_MEMBERS' ? 'Socios activos' : 'Socios vencidos';
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

  metadataRows(metadata: CampaignV2SourceMetadata): Array<{ label: string; value: string }> {
    const rows: Array<{ label: string; value: string }> = [];
    if (metadata.activos_cutoff_date) {
      rows.push({ label: 'Corte activos', value: String(metadata.activos_cutoff_date) });
    }
    if (metadata.activos_captured_at) {
      rows.push({ label: 'Captura activos', value: String(metadata.activos_captured_at) });
    }
    if (metadata.snapshot_kind) {
      rows.push({ label: 'Snapshot', value: String(metadata.snapshot_kind) });
    }
    if (metadata.expiration_date_from) {
      rows.push({ label: 'Vencimiento desde', value: String(metadata.expiration_date_from) });
    }
    if (metadata.expiration_date_to) {
      rows.push({ label: 'Vencimiento hasta', value: String(metadata.expiration_date_to) });
    }
    if (metadata.current_status_activos_cutoff_date) {
      rows.push({
        label: 'Corte usado para estado actual',
        value: String(metadata.current_status_activos_cutoff_date),
      });
    }
    return rows;
  }

  private openPreviewDetail(
    bucket: CampaignV2PreviewBucket,
    audienceFamily?: CampaignV2ObservedFamily,
  ): void {
    if (!this.previewRequest) {
      return;
    }
    this.dialog.open<
      MarketingCampaignV2PreviewDetailDialogComponent,
      MarketingCampaignV2PreviewDetailDialogData
    >(MarketingCampaignV2PreviewDetailDialogComponent, {
      width: 'min(1080px, 96vw)',
      maxWidth: '96vw',
      maxHeight: '90vh',
      data: {
        audience: this.previewRequest,
        bucket,
        audienceFamily,
      },
    });
  }

  private audienceState() {
    return {
      source: this.source.value,
      audienceFamilies: this.selectedFamilies,
      expirationDateFrom: this.expirationDateFrom.value,
      expirationDateTo: this.expirationDateTo.value,
    };
  }

  private invalidatePreview(): void {
    this.preview = null;
    this.previewRequest = null;
  }

  private resetBuilderAfterFreeze(): void {
    this.invalidatePreview();
    this.selectedFamilies = [];
    this.expirationDateFrom.setValue('', { emitEvent: false });
    this.expirationDateTo.setValue('', { emitEvent: false });
    this.name.setValue('', { emitEvent: false });
    const nextPurpose = this.options?.purposes.includes('UNCLASSIFIED')
      ? 'UNCLASSIFIED'
      : this.options?.purposes[0];
    if (nextPurpose) {
      this.purpose.setValue(nextPurpose, { emitEvent: false });
    }
  }

  private ensureOptionDefaults(options: CampaignV2OptionsResponse): void {
    if (!options.sources.includes(this.source.value) && options.sources.length) {
      this.source.setValue(options.sources[0], { emitEvent: false });
    }
    if (!options.purposes.includes(this.purpose.value)) {
      const purpose = options.purposes.includes('UNCLASSIFIED')
        ? 'UNCLASSIFIED'
        : options.purposes[0];
      if (purpose) {
        this.purpose.setValue(purpose, { emitEvent: false });
      }
    }
    this.selectedFamilies = this.selectedFamilies.filter(value =>
      options.selectable_audience_families.includes(value),
    );
  }

  private audienceValidationMessage(): string {
    if (!this.selectedFamilies.length) {
      return 'Selecciona al menos una familia comercial.';
    }
    if (this.isExpiredSource) {
      if (!this.expirationDateFrom.value || !this.expirationDateTo.value) {
        return 'Indica las dos fechas de vencimiento.';
      }
      if (this.expirationDateFrom.value > this.expirationDateTo.value) {
        return 'La fecha inicial no puede ser posterior a la fecha final.';
      }
    }
    return 'Revisa la definición de audiencia.';
  }

  private serverMessage(error: HttpErrorResponse): string | null {
    const body = error.error as { message?: string } | null;
    return typeof body?.message === 'string' && body.message.trim()
      ? body.message.trim()
      : null;
  }

  private errorMessage(error: HttpErrorResponse, fallback: string): string {
    if (error.status === 404) {
      return 'Campaña no encontrada o no disponible.';
    }
    if (error.status === 401) {
      return 'Tu sesión no es válida. Inicia sesión nuevamente.';
    }
    if (error.status === 403) {
      return 'No tienes acceso a Campañas V2.';
    }
    return this.serverMessage(error) ?? fallback;
  }
}
