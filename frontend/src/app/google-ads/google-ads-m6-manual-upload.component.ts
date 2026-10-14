import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { Subject, takeUntil } from 'rxjs';

import {
  GoogleAdsM6ManualPreview,
  GoogleAdsM6ManualUploadService,
  GoogleAdsM6RawResult,
  GoogleAdsM6RawUpload,
  GoogleAdsM6StructuredResult
} from './google-ads-m6-manual-upload.service';

type ReportKind = 'campaign' | 'ad_group';
type ProcessingState = 'idle' | 'preview' | 'confirm' | 'ingest';

const MAX_CAMPAIGN_BYTES = 8 * 1024 * 1024;
const MAX_GROUP_BYTES = 10 * 1024 * 1024;

const RESPONSE_MESSAGES: Record<string, string> = {
  FORBIDDEN: 'Tu usuario no tiene autorización para esta operación.',
  INVALID_MANUAL_PAIR: 'Debes seleccionar exactamente los dos archivos XLSX.',
  INVALID_MANUAL_CONFIRMATION: 'La confirmación contiene datos inválidos. Valida nuevamente.',
  INVALID_XLSX_FILENAME: 'Únicamente se permiten archivos .xlsx.',
  INVALID_XLSX_SIZE: 'Uno de los archivos supera el límite o está vacío.',
  MANUAL_PAIR_TOO_LARGE: 'Los dos archivos exceden el límite de tamaño permitido.',
  INVALID_GOOGLE_ADS_XLSX: 'El formato del Excel no coincide con los reportes Google Ads esperados.',
  PAIR_PERIOD_MISMATCH: 'Los Excel corresponden a períodos diferentes.',
  DAY_NOT_CLOSED_OR_OUT_OF_SCOPE: 'Se permite únicamente un día cerrado a partir del 13 de octubre de 2026.',
  REPORT_DATE_OR_CURRENCY_MISMATCH: 'La fecha o moneda no coincide con el corte en MXN.',
  CAMPAIGN_IDENTITY_DRIFT: 'El catálogo de campañas cambió. Requiere revisión.',
  GROUP_IDENTITY_DRIFT: 'El catálogo de grupos cambió. Requiere revisión.',
  M5_IDENTITY_CATALOG_DRIFT: 'No concilian las identidades históricas aprobadas.',
  HISTORICAL_CATALOG_DRIFT: 'La referencia histórica de Google Ads requiere revisión.',
  CAMPAIGN_GROUP_RECONCILIATION_FAILED: 'Los importes o visitas no concilian entre campañas y grupos.',
  CONVERSIONS_RECONCILIATION_FAILED: 'Las conversiones entre ambos reportes no concilian.',
  EXISTING_PERIOD_CONFLICT: 'Ya existe un RAW diferente para el mismo día, incluso archivado. Se requiere revisión explícita.',
  REVALIDATION_REJECTED: 'Cambió el resultado de validación. Valida nuevamente.',
  CONFIRMATION_MISMATCH: 'Los archivos o el usuario ya no coinciden con la validación. Valida nuevamente.',
  INVALID_OR_EXPIRED_CONFIRMATION: 'La validación venció (15 minutos) o no es válida. Valida nuevamente.',
  INVALID_CONFIRMATION_TICKET: 'No hay comprobante de validación válido. Valida nuevamente.',
  SERVER_SIGNING_KEY_MISSING: 'No se pudo preparar la confirmación. Contacta a Sistemas.',
  GOOGLE_ADS_M6_PREVIEW_UNAVAILABLE: 'No está disponible la vista previa. Intenta más tarde.',
  GOOGLE_ADS_M6_INTERNAL_ERROR: 'No se pudo comprobar la autorización. Intenta más tarde.',
  M6_RAW_STAGE_UNAVAILABLE: 'No se pudo completar el guardado RAW. Revisa el estado antes de reintentar.',
  M6_STRUCTURED_INGESTION_DISABLED: 'La ingesta estructurada M6 todavía está deshabilitada en el servidor. RAW conservados.',
  M6_APPROVAL_REQUIRED: 'Antes de importar métricas debe aprobarse explícitamente la continuidad de las 26 identidades M6.',
  M6_APPROVED_IDENTITIES_MISMATCH: 'Las identidades aprobadas no concilian con el histórico. Se requiere revisión.',
  RAW_PAIR_UNREADABLE: 'No se pueden volver a leer los RAW de Warehouse.',
  RAW_PAIR_INVALID_PERIOD: 'El período del RAW no es un día cerrado válido para M6.',
  RAW_PAIR_METADATA_MISMATCH: 'Hash, estado o fecha del RAW no coincide con su registro.',
  RAW_PAIR_PREFLIGHT_REJECTED: 'La pareja RAW no pasó la conciliación del backend.',
  RAW_PAIR_PROVENANCE_INVALID: 'Los RAW no provienen de una confirmación manual pareada validada.',
  EXISTING_STRUCTURED_FACT_CONFLICT: 'Ya existen métricas distintas o parciales para ese día. Se requiere reconciliación manual.',
  GOOGLE_ADS_CUSTOMER_NOT_READY: 'La cuenta Google Ads configurada no está lista para esta ingesta.',
  M6_STRUCTURED_STAGE_FAILED: 'Se revirtió la operación estructurada. No se guardaron cambios parciales.'
};

@Component({
  selector: 'app-google-ads-m6-manual-upload',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './google-ads-m6-manual-upload.component.html',
  styleUrls: ['./google-ads-m6-manual-upload.component.css']
})
export class GoogleAdsM6ManualUploadComponent implements OnDestroy {
  @ViewChild('campaignInput') private campaignInput?: ElementRef<HTMLInputElement>;
  @ViewChild('adGroupInput') private adGroupInput?: ElementRef<HTMLInputElement>;

  readonly maxCampaignMb = 8;
  readonly maxGroupMb = 10;
  campaignFile: File | null = null;
  adGroupFile: File | null = null;
  previewData: GoogleAdsM6ManualPreview | null = null;
  rawResult: GoogleAdsM6RawResult | null = null;
  structuredResult: GoogleAdsM6StructuredResult | null = null;
  acceptedStructured = false;
  state: ProcessingState = 'idle';
  acceptedRawOnly = false;
  errorMessage = '';
  successMessage = '';

  private readonly destroy$ = new Subject<void>();

  constructor(private readonly api: GoogleAdsM6ManualUploadService) {}

  get busy(): boolean { return this.state !== 'idle'; }

  get validationButtonLabel(): string {
    return this.state === 'preview' ? 'Validando archivos…' : 'Validar ambos Excel';
  }

  get confirmationButtonLabel(): string {
    if (this.state === 'confirm') return 'Guardando RAW…';
    return this.isPartial ? 'Reintentar pareja RAW' : 'Confirmar carga RAW';
  }

  uploadStatusLabel(upload: GoogleAdsM6RawUpload): string {
    return upload.reused_existing ? 'RAW idéntico reutilizado' : 'RAW registrado';
  }

  onAcknowledgementChanged(event: Event): void {
    if (this.busy) return;
    this.acceptedRawOnly = (event.target as HTMLInputElement).checked;
  }

  get canIngest(): boolean {
    const uploads = this.rawResult?.uploads;
    return !this.busy && this.isStaged && this.acceptedStructured
      && this.structuredResult === null
      && Number.isInteger(uploads?.['google_ads_campaign_daily']?.upload_id ?? null)
      && Number.isInteger(uploads?.['google_ads_ad_group_daily']?.upload_id ?? null);
  }

  get ingestButtonLabel(): string {
    return this.state === 'ingest' ? 'Ingestando métricas…' : 'Ingestar ambos reportes (sin publicar)';
  }

  onStructuredAcknowledgement(event: Event): void {
    if (this.busy) return;
    this.acceptedStructured = (event.target as HTMLInputElement).checked;
  }

  get canPreview(): boolean {
    return this.state === 'idle' && this.campaignFile !== null
      && this.adGroupFile !== null;
  }

  get canConfirmRaw(): boolean {
    return this.state === 'idle' && this.acceptedRawOnly
      && this.campaignFile !== null && this.adGroupFile !== null
      && this.previewData?.status === 'PREFLIGHT_OK'
      && this.previewData.ready_to_stage_raw === true
      && Boolean(this.previewData.raw_confirm_ticket)
      && this.rawResult?.status !== 'RAW_PAIR_STAGED';
  }

  get resultItems(): { kind: string; data: GoogleAdsM6RawUpload }[] {
    return Object.entries(this.rawResult?.uploads ?? {}).map(([kind, data]) => ({
      kind: kind === 'google_ads_campaign_daily' ? 'Campañas' : 'Grupos de anuncios',
      data
    }));
  }

  get isPartial(): boolean {
    return this.rawResult?.status === 'PARTIAL_RAW';
  }

  get isStaged(): boolean {
    return this.rawResult?.status === 'RAW_PAIR_STAGED';
  }

  onFileChanged(kind: ReportKind, event: Event): void {
    if (this.busy) return;
    const element = event.target as HTMLInputElement;
    const picked = element.files?.item(0) ?? null;
    const limit = kind === 'campaign' ? MAX_CAMPAIGN_BYTES : MAX_GROUP_BYTES;
    this.invalidatePreview();
    if (picked && (!picked.name.toLowerCase().endsWith('.xlsx')
      || picked.size === 0 || picked.size > limit)) {
      if (kind === 'campaign') this.campaignFile = null;
      else this.adGroupFile = null;
      element.value = '';
      this.errorMessage = kind === 'campaign'
        ? 'El reporte de campañas debe ser XLSX válido de hasta 8 MB.'
        : 'El reporte de grupos debe ser XLSX válido de hasta 10 MB.';
      return;
    }
    if (kind === 'campaign') this.campaignFile = picked;
    else this.adGroupFile = picked;
  }

  validate(): void {
    if (!this.canPreview || !this.campaignFile || !this.adGroupFile) return;
    this.invalidatePreview();
    this.state = 'preview';

    this.api.preview(this.campaignFile, this.adGroupFile)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: response => {
          this.state = 'idle';
          if (response.status !== 'PREFLIGHT_OK'
            || response.ready_to_stage_raw !== true
            || !response.raw_confirm_ticket) {
            this.errorMessage = 'La vista previa no permite confirmar este par de reportes.';
            return;
          }
          this.previewData = response;
          this.successMessage = 'Par validado. Revisa los importes antes de confirmar RAW.';
        },
        error: (error: HttpErrorResponse) => {
          this.state = 'idle';
          this.errorMessage = this.describeError(error);
        }
      });
  }

  confirmRaw(): void {
    if (!this.canConfirmRaw || !this.previewData ||
      !this.campaignFile || !this.adGroupFile) return;

    this.errorMessage = '';
    this.successMessage = '';
    this.state = 'confirm';
    this.api.confirm(
      this.campaignFile,
      this.adGroupFile,
      this.previewData.raw_confirm_ticket
    ).pipe(takeUntil(this.destroy$)).subscribe({
      next: result => {
        this.state = 'idle';
        this.rawResult = result;
        this.acceptedRawOnly = false;
        this.acceptedStructured = false;
        this.structuredResult = null;
        if (result.status === 'RAW_PAIR_STAGED') {
          this.successMessage = 'Ambos RAW registrados. No se ejecutó ingesta estructurada ni publicación.';
        } else {
          this.errorMessage = 'La carga no terminó; revisa el estado de Warehouse antes de reintentar.';
        }
      },
      error: (error: HttpErrorResponse) => {
        this.state = 'idle';
        const response = error.error as Partial<GoogleAdsM6RawResult> | null;
        if (response?.status === 'PARTIAL_RAW' || response?.status === 'RAW_STAGE_FAILED') {
          this.rawResult = response as GoogleAdsM6RawResult;
          this.acceptedRawOnly = false;
          this.acceptedStructured = false;
          this.structuredResult = null;
          this.errorMessage = response.status === 'PARTIAL_RAW'
            ? 'Solo se guardó uno de los RAW. Puedes reintentar el mismo par, sin publicarlo.'
            : 'No se pudo guardar la pareja RAW. Puedes revisar y reintentar los mismos archivos.';
          return;
        }
        const code = typeof response?.code === 'string' ? response.code : '';
        if (['INVALID_OR_EXPIRED_CONFIRMATION', 'CONFIRMATION_MISMATCH',
              'REVALIDATION_REJECTED', 'INVALID_CONFIRMATION_TICKET'].includes(code)) {
          this.previewData = null;
          this.acceptedRawOnly = false;
        }
        this.errorMessage = this.describeError(error);
      }
    });
  }

  ingestStructured(): void {
    if (!this.canIngest || !this.rawResult) return;
    const campaigns = this.rawResult.uploads['google_ads_campaign_daily'].upload_id;
    const groups = this.rawResult.uploads['google_ads_ad_group_daily'].upload_id;
    this.state = 'ingest';
    this.errorMessage = '';
    this.successMessage = '';
    this.api.ingest(campaigns, groups).pipe(takeUntil(this.destroy$)).subscribe({
      next: result => {
        this.state = 'idle';
        this.acceptedStructured = false;
        this.structuredResult = result;
        this.successMessage = result.status === 'ALREADY_INGESTED'
          ? 'La pareja estructurada ya estaba registrada sin cambios.'
          : 'Campañas y grupos se guardaron juntos con auditoría. No se publicaron en Funnel.';
      },
      error: (error: HttpErrorResponse) => {
        this.state = 'idle';
        this.acceptedStructured = false;
        this.errorMessage = this.describeError(error);
      }
    });
  }

  reset(): void {
    if (this.busy) return;
    this.campaignFile = null;
    this.adGroupFile = null;
    if (this.campaignInput) this.campaignInput.nativeElement.value = '';
    if (this.adGroupInput) this.adGroupInput.nativeElement.value = '';
    this.invalidatePreview();
  }

  money(amount: string | undefined): string {
    const number = Number(amount);
    if (amount == null || !Number.isFinite(number)) return '—';
    return new Intl.NumberFormat('es-MX', {
      style: 'currency', currency: 'MXN',
      minimumFractionDigits: 2, maximumFractionDigits: 2
    }).format(number);
  }

  private invalidatePreview(): void {
    this.previewData = null;
    this.rawResult = null;
    this.structuredResult = null;
    this.acceptedRawOnly = false;
    this.acceptedStructured = false;
    this.errorMessage = '';
    this.successMessage = '';
  }

  private describeError(error: HttpErrorResponse): string {
    if (error.status === 401) return 'Tu sesión expiró. Inicia sesión nuevamente.';
    if (error.status === 403) return 'Tu usuario no tiene permisos para esta carga.';
    const code = typeof error.error?.code === 'string' ? error.error.code : '';
    if (code && RESPONSE_MESSAGES[code]) return RESPONSE_MESSAGES[code];
    if (error.status === 413) return 'El tamaño de la carga supera el límite permitido.';
    if (error.status === 503) return 'Servicio temporalmente no disponible. Intenta más tarde.';
    return 'No se completó la operación. Revisa los archivos y vuelve a intentar.';
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
