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
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { firstValueFrom, forkJoin } from 'rxjs';

import {
  CampaignV2DispatchTemplate,
  CampaignV2GovernedApprovalState, CampaignV2GovernedExecutionReview,
  CampaignV2GovernedExecutionReviewReady, CampaignV2GovernedMonitor,
  CampaignV2GovernedMonitorChild, CampaignV2PreflightBatch,
  CampaignV2PreflightResponse,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { pendingGovernedBatchIds } from './marketing-campaign-v2-bulk-dispatch.logic';

export interface MarketingCampaignV2GovernedConsoleDialogData {
  campaignId: number;
  campaignName: string;
}

type Action = 'read' | 'preflight' | 'approve' | 'materialize' | 'authorize' | 'execute' | 'bulk';
type ExecutionReview =
  CampaignV2GovernedExecutionReview | CampaignV2GovernedExecutionReviewReady;

@Component({
  selector: 'app-marketing-campaign-v2-governed-console-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
    MatProgressSpinnerModule,
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
  readonly executionPassword = new FormControl('', { nonNullable: true });
  readonly executionCheckbox = new FormControl(false, { nonNullable: true });
  readonly bulkPhrase = new FormControl('', { nonNullable: true });
  readonly bulkPassword = new FormControl('', { nonNullable: true });
  readonly bulkCheckbox = new FormControl(false, { nonNullable: true });
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
  bulkTotal = 0;
  bulkAccepted = 0;
  bulkCurrentChildId: number | null = null;
  bulkStopRequested = false;
  private destroyed = false;

  constructor(@Inject(MAT_DIALOG_DATA) readonly data: MarketingCampaignV2GovernedConsoleDialogData) {}

  ngOnInit(): void {
    this.templateId.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreflight());
    this.destroyRef.onDestroy(() => { this.destroyed = true; this.bulkStopRequested = true; });
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
  // Presentación para operadores: los códigos permanecen intactos en los contratos.
  get preflightStatusLabel(): string {
    if (!this.preflight) { return 'Pendiente de revisión'; }
    return this.preflight.ready ? 'Destinatarios revisados' : 'Destinatarios con problemas';
  }
  get budgetStatusLabel(): string {
    return this.preflight?.budget_usd
      ? 'Cálculo automático en USD' : 'Costo en USD no disponible';
  }
  get quotaStatusLabel(): string {
    const quota = this.preflight?.quota;
    if (!quota) { return 'Pendiente de revisión'; }
    if (quota.basis === 'SUITE_BRANCH_EXCEPTION_CAPS_V1') {
      const restricted = quota.batches.some(row =>
        row.restriction_kind === 'CHANNEL_250_ROLLING_24H');
      return quota.status === 'REVIEWABLE'
        ? (restricted ? '250 diarios por canal: correcto' : 'Sin límite interno diario')
        : 'Revisar límite especial o canal';
    }
    return quota.status === 'REVIEWABLE'
      ? 'Límite revisado' : 'Falta revisar el límite de envío';
  }
  get creativePurposeNotice(): string {
    const purpose = this.preflight?.campaign_purpose;
    const template = this.templates.find(item => item.id === this.preflight?.template?.id);
    if (!purpose || !template || !template.purposes.length ||
        template.purposes.includes(purpose)) { return ''; }
    return 'El público se clasifica como ' + purpose +
      ', pero la plantilla está catalogada como ' + template.purposes.join(', ') +
      '. Es una diferencia de clasificación, no un bloqueo técnico; confirma que el contenido promocional sea adecuado para este público.';
  }

  get preparationIssue(): string {
    const plan = this.preflight;
    if (!plan) { return ''; }
    if (!plan.ready) {
      return 'Hay problemas en los destinatarios o canales. Corrige los datos señalados antes de continuar.';
    }
    if (!plan.budget_usd) {
      return 'Aún no está disponible el costo estimado automático en USD. Vuelve a revisar los destinatarios.';
    }
    if (plan.quota?.status !== 'REVIEWABLE') {
      return plan.quota?.basis === 'SUITE_BRANCH_EXCEPTION_CAPS_V1'
        ? 'Si Insurgentes o Independencia alcanzaron 250 diarios o tienen resultados inciertos, marca esos lotes en espera y registra el motivo para continuar con las demás sucursales. Un canal sin identificar siempre bloquea la preparación.'
        : 'Falta revisar la capacidad de envío de este canal en Límites de envío. La aprobación continuará bloqueada.';
    }
    return '';
  }
  statusLabel(value: string | null | undefined): string {
    const labels: Record<string, string> = {
      READY: 'Listo para enviar (sin envío)',
      HELD: 'En espera (no enviar)',
      SUBMITTED: 'Aceptado por iVentas',
      SCHEDULED: 'Programado',
      SUBMITTING: 'Envío en proceso: no repetir',
      AUTHORIZED: 'Autorizado, aún sin enviar',
      IN_FLIGHT: 'Envío en proceso: revisar',
      IN_FLIGHT_STALE: 'Envío sin confirmación: revisar manualmente',
      RECONCILIATION_REQUIRED: 'Resultado incierto: revisar manualmente',
      PROVIDER_ERROR: 'Error del proveedor: revisar antes de actuar',
      REVIEW_REQUIRED: 'Requiere revisión manual',
      COMPLETE: 'Proceso terminado',
      APPROVAL_EXPIRED: 'Aprobación vencida',
      AUTHORIZED_NOT_DISPATCHED: 'Autorizado, sin enviar',
      PREPARED_NOT_DISPATCHED: 'Lotes preparados, sin enviar',
      RESERVED_NOT_PREPARED: 'Costo aprobado, faltan preparar los lotes',
      NO_GOVERNED_APPROVAL: 'Sin aprobación de envío',
      RETRY_ELIGIBLE: 'Revisión de posible reintento requerida',
      RETRY_EXHAUSTED: 'Sin reintentos disponibles',
    };
    return value ? labels[value] ?? 'Estado pendiente de revisión' : 'Sin estado';
  }
  nextActionLabel(value: string | null | undefined): string {
    const labels: Record<string, string> = {
      VERIFY_PROVIDER_OUTCOME_MANUALLY: 'Comprobar el resultado directamente con iVentas antes de actuar',
      DO_NOT_RESEND: 'No reenviar; solicitar revisión manual',
      REVIEW_BEFORE_ANY_NEW_APPROVAL: 'Revisar la campaña antes de aprobar nuevamente',
      NEW_AUTHORIZATION_POLICY_REQUIRED: 'Solicitar una nueva autorización',
      MANUAL_NEXT_CHILD_ONLY: 'Revisar y enviar solo el siguiente lote, si está autorizado',
      INDEPENDENT_AUTHORIZATION_REQUIRED: 'Falta autorización independiente',
      MATERIALIZE_BEFORE_EXPIRY: 'Preparar los lotes antes de que venza la aprobación',
    };
    return value ? labels[value] ?? 'Consultar el detalle antes de continuar' : 'Sin acción pendiente';
  }
  get workingLabel(): string {
    const labels: Record<Action, string> = {
      read: 'Consultando', preflight: 'Revisando destinatarios',
      approve: 'Aprobando costo', materialize: 'Preparando lotes',
      authorize: 'Autorizando', execute: 'Enviando un lote', bulk: 'Enviando lotes pendientes',
    };
    return this.working ? labels[this.working] : '';
  }

  get approvalWord(): string { return 'APROBAR ' + this.readyCount; }
  get materializeWord(): string { return 'PREPARAR ' + this.data.campaignId; }
  get authorizationWord(): string { return 'AUTORIZAR ' + this.approvedReadyCount; }
  get bulkPendingIds(): number[] {
    return pendingGovernedBatchIds(this.monitor, this.reviewReady);
  }
  get bulkWord(): string { return 'ENVIAR PENDIENTES ' + this.bulkPendingIds.length; }
  get sendWord(): string {
    return this.nextReadyChild ? 'ENVIAR LOTE ' + this.nextReadyChild.child_id : '';
  }
  get isSelectionWithinCapacity(): boolean {
    const quota = this.preflight?.quota;
    if (!quota) { return false; }
    if (quota.status === 'REVIEWABLE') { return true; }
    if (quota.basis !== 'SUITE_BRANCH_EXCEPTION_CAPS_V1') { return false; }
    const blocked = quota.batches.filter(row => row.recommendation === 'REVIEW_HOLD');
    // Never allow a missing channel to be bypassed as an exception.
    return blocked.length > 0 && blocked.every(row =>
      ['CHANNEL_EXCEPTION_250_EXCEEDED', 'UNRESOLVED_PROVIDER_ACTIVITY']
        .includes(row.blocking_reason || '') &&
      this.heldBranches.includes(row.sucursal_canon) &&
      !!this.heldSources[row.sucursal_canon]
    );
  }
  get canApprove(): boolean {
    const plan = this.preflight;
    return !this.busy && !this.hasApproval && !!plan && plan.ready &&
      plan.sendable_count > 0 && this.isSelectionWithinCapacity &&
      !!plan.budget_usd?.quote_fingerprint &&
      plan.budget_usd.status === 'COMPLETE' &&
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
      this.executionPassword.value.length > 0 &&
      this.executionPassword.value.length <= 256 &&
      this.executionPhrase.value === this.sendWord;
  }

  get canBulkSend(): boolean {
    const ids = this.bulkPendingIds;
    return !this.busy && !this.uncertainResult && this.validApproval &&
      ids.length > 0 && ids.length <= 30 &&
      this.nextReadyChild?.child_id === ids[0] &&
      this.bulkCheckbox.value === true &&
      this.bulkPhrase.value === this.bulkWord &&
      this.bulkPassword.value.length > 0 && this.bulkPassword.value.length <= 256;
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
          this.error = this.message(err, 'No se pudieron revisar los destinatarios. No se aprobó ningún costo.');
        },
      });
  }

  approve(): void {
    const plan = this.preflight, templateId = this.templateId.value;
    if (!this.canApprove || !plan || !templateId ||
        !plan.budget_usd?.quote_fingerprint) { return; }
    this.working = 'approve';
    this.error = '';
    this.api.approveGovernedCampaign(this.data.campaignId, {
      template_id: templateId,
      expected_dispatch_fingerprint: plan.dispatch_fingerprint,
      expected_quote_fingerprint: plan.budget_usd.quote_fingerprint,
      expected_recipients: plan.sendable_count,
      pricing_currency: 'USD',
      held_sucursal_canons: this.heldBranches,
      held_source_references: this.heldSources,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.working = null;
        this.invalidatePreflight();
        this.notice = 'Destinatarios y límite autorizados. El precio en USD se calculó automáticamente; no se enviaron mensajes.';
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
          this.notice = 'Lotes preparados para revisión. No se enviaron mensajes.';
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
    const operatorPassword = this.executionPassword.value;
    this.executionPassword.setValue('');
    this.working = 'execute';
    this.executionCheckbox.setValue(false);
    this.executionPhrase.setValue('');
    this.error = '';
    this.notice = '';
    this.api.executeGovernedChild(this.data.campaignId, {
      execution_id: execution.execution_id,
      child_id: child.child_id,
      expected_manifest_digest: digest,
      operator_password: operatorPassword,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.working = null;
        this.notice = result.status === 'SUBMITTED'
          ? 'iVentas aceptó este único lote. Consulta el resultado antes de preparar otro.'
          : 'El resultado de iVentas requiere revisión. No vuelvas a enviar desde esta pantalla.';
        this.uncertainResult = result.status !== 'SUBMITTED';
        this.refresh();
      },
      error: (err: HttpErrorResponse) => {
        this.working = null;
        // Auth/kill-switch denial happens before any provider request.
        // The operator may retry their password; a timeout/502 must NEVER
        // offer an automatic repeat because iVentas might have accepted it.
        if (err.status === 403 || err.status === 423) {
          this.uncertainResult = false;
          this.error = this.message(err, 'Acceso denegado. Verifica tu contraseña y permisos.');
          this.refresh(true);
          return;
        }
        this.uncertainResult = true;
        this.error = this.message(err, 'No está confirmado si se envió el mensaje. Compruébalo directamente con iVentas. No lo reenvíes.');
        this.refresh(true);
      },
    });
  }

  /**
   * One user-initiated operation; one existing guarded provider request per
   * DISTINCT pending child. No timers, retries, stored credentials or resume.
   * Fresh backend monitor + manifest review must pass before EVERY next child.
   */
  async executePendingSequentially(): Promise<void> {
    if (!this.canBulkSend) { return; }
    const pendingIds = [...this.bulkPendingIds];
    const expectedDigest = this.reviewReady!.manifest_digest;
    const expectedExecutionId = this.reviewReady!.execution!.execution_id;
    let password = this.bulkPassword.value;
    this.bulkPassword.setValue('');
    this.bulkCheckbox.setValue(false);
    this.bulkPhrase.setValue('');
    this.executionPassword.setValue('');
    this.executionCheckbox.setValue(false);
    this.executionPhrase.setValue('');
    this.bulkStopRequested = false;
    this.bulkTotal = pendingIds.length;
    this.bulkAccepted = 0;
    this.bulkCurrentChildId = null;
    this.working = 'bulk';
    this.error = '';
    this.notice = '';

    try {
      for (let index = 0; index < pendingIds.length; index += 1) {
        if (this.bulkStopRequested || this.destroyed) { break; }
        // Fail closed if approval, manifest, quota, child order or provider state
        // changed between operator review and this exact provider request.
        await this.readFreshBulkState();
        const expected = pendingIds.slice(index);
        const current = pendingGovernedBatchIds(this.monitor, this.reviewReady);
        if (!this.validApproval || !this.reviewReady ||
            this.reviewReady.manifest_digest !== expectedDigest ||
            this.reviewReady.execution?.execution_id !== expectedExecutionId ||
            current.length !== expected.length ||
            current.some((id, position) => id !== expected[position])) {
          throw new Error('Cambió la autorización, límite u orden de lotes. Se detuvo el envío.');
        }
        if (this.bulkStopRequested || this.destroyed) { break; }
        const childId = pendingIds[index];
        this.bulkCurrentChildId = childId;
        const result = await firstValueFrom(this.api.executeGovernedChild(this.data.campaignId, {
          execution_id: expectedExecutionId,
          child_id: childId,
          expected_manifest_digest: expectedDigest,
          operator_password: password,
        }).pipe(takeUntilDestroyed(this.destroyRef)));
        if (result.status !== 'SUBMITTED' || result.child_id !== childId) {
          throw new Error('iVentas no confirmó este lote. Revisar el estado antes de continuar.');
        }
        this.bulkAccepted += 1;
        // Require durable backend confirmation of the exact accepted child.
        await this.readFreshBulkState();
        const persisted = this.monitor?.children.find(child => child.child_id === childId);
        if (persisted?.status !== 'SUBMITTED' || !persisted.provider_campaign_id) {
          throw new Error('No se pudo verificar la aceptación persistida del lote. No continuar.');
        }
        if (index + 1 < pendingIds.length) {
          const remaining = pendingGovernedBatchIds(this.monitor, this.reviewReady);
          if (remaining.length !== pendingIds.length - index - 1 ||
              remaining.some((id, position) => id !== pendingIds[index + 1 + position])) {
            throw new Error('Cambió el siguiente lote autorizado. No continuar.');
          }
        } else if (this.monitor?.execution?.status !== 'COMPLETE') {
          throw new Error('El último lote fue aceptado, pero la ejecución requiere revisión.');
        }
      }
      if (!this.destroyed) {
        this.notice = this.bulkStopRequested
          ? `Envío detenido por el operador: ${this.bulkAccepted}/${this.bulkTotal} lotes aceptados. Consulta el estado antes de continuar.`
          : `Proceso terminado: ${this.bulkAccepted}/${this.bulkTotal} lotes aceptados por iVentas. Revisa las estadísticas del proveedor.`;
      }
    } catch (error: unknown) {
      if (!this.destroyed) {
        this.uncertainResult = true;
        this.error = error instanceof HttpErrorResponse
          ? this.message(error, 'No se pudo confirmar el estado del lote. No reenviar.')
          : error instanceof Error ? error.message : 'Resultado incierto. No reenviar.';
        this.notice = `Proceso detenido tras ${this.bulkAccepted} de ${this.bulkTotal} aceptaciones confirmadas. Revisa iVentas antes de cualquier continuación.`;
      }
    } finally {
      password = '';
      this.bulkCurrentChildId = null;
      this.working = null;
      if (!this.destroyed) {
        // A fresh manual consultation is always available; there is no
        // automatic continuation after an error, expiry, stop or reload.
        this.refresh(true);
      }
    }
  }

  requestBulkStop(): void {
    if (this.working === 'bulk') {
      this.bulkStopRequested = true;
    }
  }

  private async readFreshBulkState(): Promise<void> {
    const latest = await firstValueFrom(forkJoin({
      approval: this.api.getGovernedApproval(this.data.campaignId),
      execution: this.api.getGovernedExecution(this.data.campaignId),
      monitor: this.api.getGovernedMonitor(this.data.campaignId),
    }).pipe(takeUntilDestroyed(this.destroyRef)));
    if (this.destroyed) { throw new Error('Pantalla cerrada.'); }
    this.approval = latest.approval;
    this.review = latest.execution;
    this.monitor = latest.monitor;
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
    this.executionPassword.setValue('');
    this.executionCheckbox.setValue(false);
    this.bulkCheckbox.setValue(false);
    this.bulkPhrase.setValue('');
    this.bulkPassword.setValue('');
  }
  private message(err: HttpErrorResponse, fallback: string): string {
    return String(err.error?.message || fallback);
  }
}
