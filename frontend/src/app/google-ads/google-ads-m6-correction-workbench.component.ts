import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';

import {
  GoogleAdsM6CorrectionWorkbenchService,
  M6CorrectionCapabilities,
  M6CorrectionCase,
  M6CorrectionCaseSummary,
  M6CorrectionCandidateResult,
  M6CorrectionPreview,
  M6CorrectionPromotionResult,
  M6CorrectionRawPair
} from './google-ads-m6-correction-workbench.service';

type Operation = 'idle' | 'capabilities' | 'list' | 'detail' | 'preview' |
  'raw' | 'stage' | 'review' | 'promote';
type ReviewDecision = 'APPROVED' | 'REJECTED';

@Component({
  selector: 'app-google-ads-m6-correction-workbench',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './google-ads-m6-correction-workbench.component.html',
  styleUrls: ['./google-ads-m6-correction-workbench.component.css']
})
export class GoogleAdsM6CorrectionWorkbenchComponent implements OnInit, OnDestroy {
  capabilities: M6CorrectionCapabilities | null = null;
  cases: M6CorrectionCaseSummary[] = [];
  selectedCase: M6CorrectionCase | null = null;
  campaignFile: File | null = null;
  groupFile: File | null = null;
  reason = '';
  previewData: M6CorrectionPreview | null = null;
  rawData: M6CorrectionRawPair | null = null;
  staged: M6CorrectionCandidateResult | null = null;
  published: M6CorrectionPromotionResult | null = null;
  reviewNote = '';
  reviewDecision: ReviewDecision = 'APPROVED';
  acceptRaw = false;
  acceptStage = false;
  acceptReview = false;
  acceptPromotion = false;
  state: Operation = 'idle';
  message = '';
  error = '';

  private readonly destroy$ = new Subject<void>();

  constructor(private readonly api: GoogleAdsM6CorrectionWorkbenchService) {}

  ngOnInit(): void {
    this.state = 'capabilities';
    this.api.capabilities().pipe(takeUntil(this.destroy$)).subscribe({
      next: value => {
        this.capabilities = value;
        this.state = 'idle';
        if (value.can_read) this.refreshCases();
      },
      error: () => {
        this.state = 'idle';
        this.capabilities = null;
      }
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  get visible(): boolean { return this.capabilities?.can_read === true; }
  get busy(): boolean { return this.state !== 'idle'; }

  get canPreview(): boolean {
    return !this.busy && this.capabilities?.can_stage_raw === true
      && this.campaignFile !== null && this.groupFile !== null
      && this.reason.trim().length >= 10 && this.reason.trim().length <= 500;
  }

  get canConfirmRaw(): boolean {
    return !this.busy && this.acceptRaw
      && this.capabilities?.can_stage_raw === true
      && !!this.previewData?.correction_ticket
      && this.campaignFile !== null && this.groupFile !== null
      && this.rawData?.status !== 'CORRECTION_RAW_PAIR_STAGED';
  }

  get canStage(): boolean {
    return !this.busy && this.acceptStage
      && this.capabilities?.can_ingest === true
      && this.rawData?.status === 'CORRECTION_RAW_PAIR_STAGED'
      && this.previewData !== null && this.staged === null
      && !!this.rawData.uploads['google_ads_campaign_daily']?.upload_id
      && !!this.rawData.uploads['google_ads_ad_group_daily']?.upload_id;
  }

  get canReview(): boolean {
    return !this.busy && this.acceptReview
      && this.capabilities?.can_review === true
      && this.selectedCase !== null && this.selectedCase.decision === null
      && this.selectedCase.campaign_rows === 27
      && this.selectedCase.group_rows === 43
      && this.reviewNote.trim().length >= 10
      && this.reviewNote.trim().length <= 1000;
  }

  get canPromote(): boolean {
    return !this.busy && this.acceptPromotion
      && this.capabilities?.can_promote === true
      && this.selectedCase?.decision?.decision === 'APPROVED'
      && this.selectedCase.promotion === null
      && this.selectedCase.campaign_rows === 27
      && this.selectedCase.group_rows === 43;
  }

  changeFile(kind: 'campaign' | 'group', event: Event): void {
    if (this.busy) return;
    const element = event.target as HTMLInputElement;
    const file = element.files?.item(0) ?? null;
    const limit = kind === 'campaign' ? 8 * 1024 * 1024 : 10 * 1024 * 1024;
    this.invalidateFiles();
    if (file && (!file.name.toLowerCase().endsWith('.xlsx')
        || file.size === 0 || file.size > limit)) {
      this.error = 'Selecciona un Excel .xlsx no vacío dentro del límite de tamaño.';
      element.value = '';
      if (kind === 'campaign') this.campaignFile = null;
      else this.groupFile = null;
      return;
    }
    if (kind === 'campaign') this.campaignFile = file;
    else this.groupFile = file;
  }

  changeReason(): void {
    if (!this.busy) this.invalidateFiles();
  }

  previewFiles(): void {
    if (!this.canPreview || !this.campaignFile || !this.groupFile) return;
    this.invalidateFiles();
    this.error = '';
    this.state = 'preview';
    this.api.preview(this.campaignFile, this.groupFile, this.reason.trim())
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: result => {
          this.state = 'idle';
          this.previewData = result;
          this.message = 'Vista previa validada. Todavía no hay ningún RAW nuevo.';
        },
        error: err => this.failed(err)
      });
  }

  confirmRaw(): void {
    if (!this.canConfirmRaw || !this.previewData ||
        !this.campaignFile || !this.groupFile) return;
    this.state = 'raw';
    this.error = '';
    this.message = '';
    this.api.confirm(this.campaignFile, this.groupFile, this.previewData.correction_ticket)
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: result => {
          this.state = 'idle';
          this.rawData = result;
          this.acceptRaw = false;
          this.message = 'RAW de corrección registrados. Todavía no se han publicado.';
        },
        error: (err: HttpErrorResponse) => {
          this.state = 'idle';
          this.acceptRaw = false;
          if (err.error?.status === 'PARTIAL_RAW') {
            this.rawData = err.error as M6CorrectionRawPair;
            this.error = 'Solo se guardó parte del par. Reintenta los mismos dos archivos.';
          } else this.error = this.describe(err);
        }
      });
  }

  stageCandidate(): void {
    if (!this.canStage || !this.previewData || !this.rawData) return;
    this.state = 'stage';
    this.error = '';
    this.message = '';
    this.api.stage(this.rawData, this.previewData, this.reason.trim())
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: result => {
          this.state = 'idle';
          this.acceptStage = false;
          this.staged = result;
          this.message = 'Expediente creado sin publicación. Requiere revisión de otra persona.';
          this.refreshCases();
        },
        error: err => this.failed(err)
      });
  }

  refreshCases(): void {
    if (this.busy || !this.visible) return;
    this.state = 'list';
    this.api.listCases().pipe(takeUntil(this.destroy$)).subscribe({
      next: result => {
        this.state = 'idle';
        this.cases = result.cases;
      },
      error: err => this.failed(err)
    });
  }

  inspect(caseId: number): void {
    if (this.busy || !Number.isInteger(caseId) || caseId <= 0) return;
    this.state = 'detail';
    this.error = '';
    this.selectedCase = null;
    this.acceptReview = false;
    this.acceptPromotion = false;
    this.published = null;
    this.api.inspectCase(caseId).pipe(takeUntil(this.destroy$)).subscribe({
      next: result => {
        this.selectedCase = result;
        this.state = 'idle';
      },
      error: err => this.failed(err)
    });
  }

  submitReview(): void {
    if (!this.canReview || !this.selectedCase) return;
    const caseId = this.selectedCase.case_id;
    this.state = 'review';
    this.message = '';
    this.error = '';
    this.api.review(caseId, this.reviewDecision, this.reviewNote.trim())
      .pipe(takeUntil(this.destroy$)).subscribe({
        next: () => {
          this.state = 'idle';
          this.acceptReview = false;
          this.reviewNote = '';
          this.message = 'Decisión independiente registrada y auditada. Sin publicación.';
          this.inspect(caseId);
          this.refreshCases();
        },
        error: err => this.failed(err)
      });
  }

  publishCorrection(): void {
    if (!this.canPromote || !this.selectedCase) return;
    const caseId = this.selectedCase.case_id;
    this.state = 'promote';
    this.message = '';
    this.error = '';
    this.api.promote(this.selectedCase).pipe(takeUntil(this.destroy$)).subscribe({
      next: result => {
        this.published = result;
        this.state = 'idle';
        this.acceptPromotion = false;
        this.message = 'La revisión aprobada ya es la publicación canónica auditada.';
        this.inspect(caseId);
        this.refreshCases();
      },
      error: err => this.failed(err)
    });
  }

  money(value: string | null | undefined): string {
    if (value == null || !Number.isFinite(Number(value))) return '—';
    return new Intl.NumberFormat('es-MX', {
      style: 'currency', currency: 'MXN'
    }).format(Number(value));
  }

  trackCase(_index: number, item: M6CorrectionCaseSummary): number {
    return item.case_id;
  }

  private invalidateFiles(): void {
    this.previewData = null;
    this.rawData = null;
    this.staged = null;
    this.acceptRaw = false;
    this.acceptStage = false;
    this.error = '';
    this.message = '';
  }

  private failed(err: HttpErrorResponse): void {
    this.state = 'idle';
    this.error = this.describe(err);
  }

  private describe(err: HttpErrorResponse): string {
    if (err.status === 401) return 'La sesión expiró. Vuelve a iniciar sesión.';
    if (err.status === 403) return 'Tu usuario no tiene autorización para este paso.';
    if (err.status === 503) return 'Esta operación sigue deshabilitada o no está disponible.';
    if (err.status === 409) return 'El expediente, la procedencia o la revisión no coinciden. Consulta su estado antes de continuar.';
    return 'No se completó la operación. Revisa los datos y vuelve a intentarlo.';
  }
}
