import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Inject, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { forkJoin } from 'rxjs';

import {
  CampaignV2DispatchTemplate,
  CampaignV2GovernedApprovalState, CampaignV2GovernedExecutionReview,
  CampaignV2GovernedExecutionReviewReady, CampaignV2GovernedMonitor,
  CampaignV2GovernedMonitorChild, CampaignV2PreflightBatch,
  CampaignV2PreflightResponse,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

export interface MarketingCampaignV2GovernedConsoleDialogData {
  campaignId: number;
  campaignName: string;
}

type Action = 'read' | 'preflight' | 'approve' | 'materialize' | 'authorize' | 'execute';
type ExecutionReview =
  CampaignV2GovernedExecutionReview | CampaignV2GovernedExecutionReviewReady;

@Component({
  selector: 'app-marketing-campaign-v2-governed-console-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-governed-console-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-governed-console-dialog.component.css'],
})
export class MarketingCampaignV2GovernedConsoleDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2GovernedConsoleDialogComponent>);

  readonly templateId = new FormControl<number | null>(null);
  readonly approvalPhrase = new FormControl('', { nonNullable: true });
  readonly materializePhrase = new FormControl('', { nonNullable: true });
  readonly authorizationPhrase = new FormControl('', { nonNullable: true });
  readonly executionPhrase = new FormControl('', { nonNullable: true });
  readonly executionCheckbox = new FormControl(false, { nonNullable: true });
  templates: CampaignV2DispatchTemplate[] = [];
  preflight: CampaignV2PreflightResponse | null = null;
  approval: CampaignV2GovernedApprovalState | null = null;
  review: ExecutionReview | null = null;
  monitor: CampaignV2GovernedMonitor | null = null;
  holdSelected: Record<string, FormControl<boolean>> = {};
  holdSource: Record<string, FormControl<string>> = {};
  working: Action | null = null;
  error = '';
  notice = '';
  uncertainResult = false;

  constructor(@Inject(MAT_DIALOG_DATA) readonly data: MarketingCampaignV2GovernedConsoleDialogData) {}

  ngOnInit(): void {
    this.templateId.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreflight());
    this.loadCatalog();
    this.refresh();
  }

  get busy(): boolean { return this.working !== null; }
  get hasApproval(): boolean { return !!this.approval?.approval; }
  get validApproval(): boolean {
    const approval = this.approval?.approval;
    return !!approval && approval.status !== 'EXPIRED' &&
      Date.parse(approval.expires_at) > Date.now();
  }
  get readyCount(): number {
    return this.preflight?.sendable_count ?? 0;
  }
  get heldBranches(): string[] {
    return this.preflight?.batches
      .filter(batch => this.holdSelected[batch.sucursal_canon]?.value === true)
      .map(batch => batch.sucursal_canon) ?? [];
  }
  get heldSources(): Record<string, string> {
    const sources: Record<string, string> = {};
    for (const branch of this.heldBranches) {
      sources[branch] = this.holdSource[branch]?.value.trim() ?? '';
    }
    return sources;
  }
  get approvedReadyCount(): number {
    const record = this.review;
    if (!record || !('manifest' in record)) { return 0; }
    return record.manifest.batches
      .filter(batch => batch.planned_status === 'READY')
      .reduce((total, batch) => total + batch.recipients, 0);
  }
  get reviewReady(): CampaignV2GovernedExecutionReviewReady | null {
    return this.review && 'manifest' in this.review ? this.review : null;
  }
  get nextReadyChild(): CampaignV2GovernedMonitorChild | null {
    const monitor = this.monitor, review = this.reviewReady;
    if (monitor?.execution?.status !== 'AUTHORIZED' || !review?.execution ||
        review.execution.status !== 'AUTHORIZED' ||
        this.uncertainResult || !monitor || !this.validApproval) { return null; }
    if (review.manifest_digest !== monitor.approval?.manifest_digest) { return null; }
    if (monitor.children.some(child => child.needs_manual_review)) { return null; }
    const ready = review.manifest.batches.filter(batch => batch.planned_status === 'READY');
    const byBranch = new Map(monitor.children.map(child => [child.sucursal_canon, child]));
    const ordered = ready.map(batch => byBranch.get(batch.sucursal_canon));
    // Manifest is the authority on send sequence, not database child insertion order.
    if (ordered.some(child => !child ||
        (child.status !== 'READY' && child.status !== 'SUBMITTED'))) { return null; }
    const nextIndex = ordered.findIndex(child => child?.status === 'READY');
    if (nextIndex < 0 ||
        ordered.slice(0, nextIndex).some(child => child?.status !== 'SUBMITTED') ||
        ordered.slice(nextIndex).some(child => child?.status !== 'READY')) { return null; }
    return ordered[nextIndex] ?? null;
  }
  get approvalWord(): string { return 'APROBAR ' + this.readyCount; }
  get materializeWord(): string { return 'MATERIALIZAR ' + this.data.campaignId; }
  get authorizationWord(): string { return 'AUTORIZAR ' + this.approvedReadyCount; }
  get sendWord(): string {
    return this.nextReadyChild ? 'ENVIAR CHILD ' + this.nextReadyChild.child_id : '';
  }
  get canApprove(): boolean {
    const plan = this.preflight;
    return !this.busy && !this.hasApproval && !!plan && plan.ready &&
      plan.sendable_count > 0 && plan.budget?.status === 'COMPLETE' &&
      !!plan.budget.quote_fingerprint && !!plan.budget.total_estimated_mxn &&
      plan.quota?.status === 'REVIEWABLE' &&
      this.heldBranches.length < plan.batches.length &&
      this.heldBranches.every(branch => !!this.heldSources[branch]) &&
      this.approvalPhrase.value === this.approvalWord;
  }
  get canMaterialize(): boolean {
    return !this.busy && this.validApproval &&
      this.monitor?.children_count === 0 && this.materializePhrase.value === this.materializeWord;
  }
  get canAuthorize(): boolean {
    return !this.busy && this.validApproval && this.monitor !== null &&
      this.monitor.children_count > 0 && !!this.reviewReady &&
      !this.reviewReady.execution && this.approvedReadyCount > 0 &&
      this.authorizationPhrase.value === this.authorizationWord;
  }
  get canExecute(): boolean {
    const review = this.reviewReady;
    return !this.busy && !this.uncertainResult && !!this.nextReadyChild &&
      this.validApproval && !!review?.execution &&
      this.monitor?.quota.all_current === true &&
      review.execution.status === 'AUTHORIZED' &&
      review.manifest_digest === this.monitor?.approval?.manifest_digest &&
      this.executionCheckbox.value === true &&
      this.executionPhrase.value === this.sendWord;
  }

  close(): void { if (!this.busy) { this.dialogRef.close(); } }

  loadCatalog(): void {
    this.api.listDispatchTemplatesAdmin().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: data => {
        this.templates = data.rows.filter(row => row.provider === 'IVENTAS' && row.is_active);
      },
      error: () => { this.error = 'No se pudo cargar el catálogo de plantillas.'; },
    });
  }

  refresh(preserveError = false): void {
    if (this.busy) { return; }
    this.working = 'read';
    if (!preserveError) { this.error = ''; }
    // Every review is a fresh read; never call execute automatically.
    forkJoin({
      approval: this.api.getGovernedApproval(this.data.campaignId),
      execution: this.api.getGovernedExecution(this.data.campaignId),
      monitor: this.api.getGovernedMonitor(this.data.campaignId),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.approval = result.approval;
        this.review = result.execution;
        this.monitor = result.monitor;
        this.working = null;
        this.clearConfirmations();
      },
      error: (err: HttpErrorResponse) => {
        this.working = null;
        this.error = (preserveError && this.error ? this.error + ' · ' : '') +
          this.message(err, 'No fue posible consultar el estado gobernado.');
        this.approval = null;
        this.review = null;
        this.monitor = null;
        this.clearConfirmations();
      },
    });
  }

  runPreflight(): void {
    const templateId = this.templateId.value;
    if (this.busy || this.hasApproval || !templateId) { return; }
    this.working = 'preflight';
    this.invalidatePreflight();
    this.error = '';
    this.notice = '';
    this.api.preflightCampaign(this.data.campaignId, templateId)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: plan => {
          this.preflight = plan;
          this.holdSelected = {};
          this.holdSource = {};
          for (const batch of plan.batches) {
            this.holdSelected[batch.sucursal_canon] = new FormControl(false, { nonNullable: true });
            this.holdSource[batch.sucursal_canon] = new FormControl('', { nonNullable: true });
            this.holdSelected[batch.sucursal_canon].valueChanges.pipe(
              takeUntilDestroyed(this.destroyRef),
            ).subscribe(() => this.approvalPhrase.setValue(''));
            this.holdSource[batch.sucursal_canon].valueChanges.pipe(
              takeUntilDestroyed(this.destroyRef),
            ).subscribe(() => this.approvalPhrase.setValue(''));
          }
          this.working = null;
        },
        error: (err: HttpErrorResponse) => {
          this.working = null;
          this.error = this.message(err, 'Falló preflight. No se realizó ninguna aprobación.');
        },
      });
  }

  approve(): void {
    const plan = this.preflight, templateId = this.templateId.value;
    if (!this.canApprove || !plan || !templateId ||
        !plan.budget?.total_estimated_mxn || !plan.budget.quote_fingerprint) { return; }
    this.working = 'approve';
    this.error = '';
    this.api.approveGovernedCampaign(this.data.campaignId, {
      template_id: templateId,
      expected_dispatch_fingerprint: plan.dispatch_fingerprint,
      expected_quote_fingerprint: plan.budget.quote_fingerprint,
      expected_recipients: plan.sendable_count,
      expected_total_mxn: plan.budget.total_estimated_mxn,
      held_sucursal_canons: this.heldBranches,
      held_source_references: this.heldSources,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.working = null;
        this.invalidatePreflight();
        this.notice = 'Reserva aprobada. No se crearon envíos ni se contactó al proveedor.';
        this.refresh();
      },
      error: (err: HttpErrorResponse) => {
        this.working = null;
        this.invalidatePreflight();
        this.error = this.message(err, 'La aprobación no quedó confirmada. Actualiza estado.');
        this.refresh(true);
      },
    });
  }

  materialize(): void {
    if (!this.canMaterialize) { return; }
    this.working = 'materialize';
    this.materializePhrase.setValue('');
    this.error = '';
    this.api.materializeGovernedCampaign(this.data.campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: () => {
          this.working = null;
          this.notice = 'Children preparados como READY/HELD; sin llamadas al proveedor.';
          this.refresh();
        },
        error: (err: HttpErrorResponse) => this.handleWriteError(err),
      });
  }

  authorize(): void {
    const review = this.reviewReady;
    if (!this.canAuthorize || !review) { return; }
    this.working = 'authorize';
    this.authorizationPhrase.setValue('');
    this.error = '';
    this.api.authorizeGovernedCampaign(this.data.campaignId, {
      approval_id: review.approval_id,
      expected_manifest_digest: review.manifest_digest,
      expected_ready_recipients: this.approvedReadyCount,
      confirm_dispatch: true,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.working = null;
        this.notice = 'Autorización registrada; aún no se han enviado mensajes.';
        this.refresh();
      },
      error: (err: HttpErrorResponse) => this.handleWriteError(err),
    });
  }

  executeOne(): void {
    const child = this.nextReadyChild, execution = this.reviewReady?.execution;
    const digest = this.reviewReady?.manifest_digest;
    if (!this.canExecute || !child || !execution || !digest) { return; }
    this.working = 'execute';
    this.executionCheckbox.setValue(false);
    this.executionPhrase.setValue('');
    this.error = '';
    this.notice = '';
    this.api.executeGovernedChild(this.data.campaignId, {
      execution_id: execution.execution_id,
      child_id: child.child_id,
      expected_manifest_digest: digest,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.working = null;
        this.notice = result.status === 'SUBMITTED'
          ? 'iVentas aceptó este único child. Revisa el monitor antes de cualquier otro.'
          : 'Resultado del proveedor requiere revisión; no reintentes desde esta pantalla.';
        this.uncertainResult = result.status !== 'SUBMITTED';
        this.refresh();
      },
      error: (err: HttpErrorResponse) => {
        // A timeout/502 can happen AFTER provider acceptance. No retry affordance.
        this.working = null;
        this.uncertainResult = true;
        this.error = this.message(err, 'Resultado incierto: consulta y reconcilia, NUNCA reenvíes.');
        this.refresh(true);
      },
    });
  }

  private handleWriteError(err: HttpErrorResponse): void {
    this.working = null;
    this.error = this.message(err, 'La operación no fue confirmada; consulta el monitor.');
    this.refresh(true);
  }
  private invalidatePreflight(): void {
    this.preflight = null;
    this.holdSelected = {};
    this.holdSource = {};
    this.approvalPhrase.setValue('');
  }
  private clearConfirmations(): void {
    this.approvalPhrase.setValue('');
    this.materializePhrase.setValue('');
    this.authorizationPhrase.setValue('');
    this.executionPhrase.setValue('');
    this.executionCheckbox.setValue(false);
  }
  private message(err: HttpErrorResponse, fallback: string): string {
    return String(err.error?.message || fallback);
  }
}
